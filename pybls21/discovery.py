"""Read-only IPv4 discovery using the controller's UDP protocol."""

import asyncio
import math
import socket
from dataclasses import dataclass, field
from ipaddress import IPv4Address

from .exceptions import DiscoveryError

_DISCOVERY_PORT = 4000
_MAX_PACKET_SIZE = 256
# Read device ID (0x007c) and device type (0x00b9), with an empty password.
_BODY = b"\x02\x10DEFAULT_DEVICEID\x00\x01\x7c\xb9"
_REQUEST = b"\xfd\xfd" + _BODY + sum(_BODY).to_bytes(2, "little")


@dataclass(frozen=True, slots=True, kw_only=True)
class DiscoveredDevice:
    """An S21 discovery reply; use host with S21Client's Modbus TCP port."""

    host: str = field(doc="IPv4 address from which the reply was received.")
    device_id: str = field(doc="16-character controller ID, independent of its IP.")


def _parse_response(data: bytes, host: str) -> DiscoveredDevice | None:
    """Ignore malformed packets and other products sharing the UDP protocol."""
    if (
        not 25 <= len(data) <= _MAX_PACKET_SIZE
        or data[:4] != b"\xfd\xfd\x02\x10"
        or sum(data[2:-2]) != int.from_bytes(data[-2:], "little")
    ):
        return None
    identity = data[4:20]
    if not identity.isalnum():
        return None
    password_size = data[20]
    position = 21 + password_size
    end = len(data) - 2
    if password_size > 8 or position >= end or data[position] != 6:
        return None
    position += 1
    parameters: dict[int, bytes] = {}
    high_byte = 0
    while position < end:
        parameter = data[position]
        position += 1
        size = 1
        if parameter == 0xFF:  # Change the high byte of subsequent parameter IDs.
            if position >= end:
                return None
            high_byte = data[position] << 8
            position += 1
            continue
        if parameter == 0xFE:  # Explicit length for the following parameter.
            if position + 2 > end:
                return None
            size, parameter = data[position : position + 2]
            position += 2
        if parameter >= 0xFC or size == 0 or position + size > end:
            return None
        key = high_byte | parameter
        if key in parameters:
            return None
        parameters[key] = data[position : position + size]
        position += size
    # S21 is type 1. Do not mistake VENTO and related products for an S21.
    if parameters.get(0xB9) != b"\x01\x00" or parameters.get(0x7C) != identity:
        return None
    return DiscoveredDevice(host=host, device_id=identity.decode("ascii"))


async def discover(
    *,
    timeout: float = 3.0,
    address: str = "255.255.255.255",
    local_address: str = "0.0.0.0",
) -> tuple[DiscoveredDevice, ...]:
    """Find S21 controllers without changing device settings.

    Send one UDP broadcast and collect replies for ``timeout`` seconds. ``address``
    may be a subnet broadcast or a known device's IPv4 address for unicast lookup.
    Bind ``local_address`` to a local IPv4 address to select a network interface.
    Hostnames and IPv6 are not supported. Broadcasts normally stay on the local
    subnet; call separately for each desired interface on a multihomed host.

    Return devices sorted by ID, retaining the first address seen for each ID.
    Silence returns an empty tuple. Invalid arguments raise ValueError; socket
    failures raise DiscoveryError. Cancellation propagates and closes the socket.
    The timeout bounds sending and receiving, not just the first reply.
    """
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not math.isfinite(timeout)
        or timeout <= 0
    ):
        raise ValueError("timeout must be a finite positive number")
    if not isinstance(address, str) or not isinstance(local_address, str):
        raise ValueError("address and local_address must be IPv4 address strings")
    destination = str(IPv4Address(address))
    interface = str(IPv4Address(local_address))
    loop = asyncio.get_running_loop()
    devices: dict[str, DiscoveredDevice] = {}
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setblocking(False)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.bind((interface, 0))
            deadline = asyncio.timeout(timeout)
            try:
                async with deadline:
                    await loop.sock_sendto(
                        sock, _REQUEST, (destination, _DISCOVERY_PORT)
                    )
                    while True:
                        data, source = await loop.sock_recvfrom(
                            sock, _MAX_PACKET_SIZE + 1
                        )
                        # Yield even if a busy socket has another packet ready,
                        # so deadlines and cancellation cannot be starved.
                        await asyncio.sleep(0)
                        if source[1] != _DISCOVERY_PORT:
                            continue
                        device = _parse_response(data, source[0])
                        if device is not None:
                            devices.setdefault(device.device_id, device)
            except TimeoutError:
                if not deadline.expired():
                    raise
    except OSError as error:
        raise DiscoveryError("UDP discovery failed") from error
    return tuple(devices[key] for key in sorted(devices))
