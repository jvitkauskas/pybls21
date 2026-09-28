"""UDP discovery framing, real loopback I/O, and resource lifecycle tests."""

import asyncio
import socket
import unittest
from dataclasses import FrozenInstanceError
from unittest.mock import AsyncMock, Mock, patch

from pybls21 import DiscoveredDevice, DiscoveryError, S21Error, discover
from pybls21.discovery import _parse_response

# Captured from the physical S21, firmware 0.36 (2019-05-08).
CAPTURED = bytes.fromhex(
    "fdfd0210303032343030353433333337353130370006"
    "fe02b90100fe107c30303234303035343333333735313037b409"
)
IDENTITY = b"0024005433375107"


def frame(body):
    return b"\xfd\xfd" + body + sum(body).to_bytes(2, "little")


def response(parameters=None, identity=IDENTITY, password=b"", function=6):
    if parameters is None:
        parameters = b"\xfe\x02\xb9\x01\x00\xfe\x10\x7c" + identity
    return frame(
        b"\x02\x10"
        + identity
        + bytes([len(password)])
        + password
        + bytes([function])
        + parameters
    )


class TestDiscoveryParser(unittest.TestCase):
    def test_hardware_capture(self):
        self.assertEqual(response(), CAPTURED)
        device = _parse_response(CAPTURED, "192.168.1.149")
        self.assertEqual(
            device,
            DiscoveredDevice(host="192.168.1.149", device_id=IDENTITY.decode()),
        )
        with self.assertRaises(FrozenInstanceError):
            device.host = "192.168.1.1"

    def test_parameter_order_lengths_and_unknown_parameters(self):
        parameters = (
            b"\xfe\x10\x7c"
            + IDENTITY
            + b"\x42\x09"  # Unknown, default one-byte value.
            + b"\xff\x01\xb9\x42"  # Different page, not device type.
            + b"\xff\x00\xfe\x02\xb9\x01\x00"
        )
        self.assertIsNotNone(
            _parse_response(response(parameters, password=b"1111"), "127.0.0.1")
        )

    def test_rejects_bad_header_checksum_identity_and_other_devices(self):
        good_params = b"\xfe\x02\xb9\x01\x00\xfe\x10\x7c" + IDENTITY
        bad_packets = [
            b"",
            CAPTURED[:-1],
            CAPTURED + b"\x00",
            b"\x00" * 257,
            frame(b"\x03" + CAPTURED[3:-2]),
            frame(b"\x02\x0f" + CAPTURED[4:-2]),
            response(identity=b"DEFAULT_DEVICEID"),
            response(identity=b"\xff" * 16),
            response(password=b"123456789"),
            frame(b"\x02\x10" + IDENTITY + b"\x08\x00\x00"),
            response(function=1),
            response(b"\xfe\x10\x7c" + IDENTITY),
            response(b"\xfe\x02\xb9\x03\x00\xfe\x10\x7c" + IDENTITY),
            response(b"\xb9\x01\xfe\x10\x7c" + IDENTITY),
            response(good_params[:-1] + b"8"),
            response(good_params + b"\xfe\x02\xb9\x01\x00"),
        ]
        for packet in bad_packets:
            with self.subTest(packet=packet):
                self.assertIsNone(_parse_response(packet, "127.0.0.1"))

    def test_rejects_truncated_or_invalid_parameter_blocks(self):
        for suffix in (
            b"\xff",
            b"\xfe",
            b"\xfe\x10",
            b"\xfe\x10\x7cshort",
            b"\xfe\x00\x01",
            b"\xfc",
            b"\xfd\x7c",
            b"\xfe\x01\xff\x00",
        ):
            with self.subTest(suffix=suffix):
                self.assertIsNone(_parse_response(response(suffix), "127.0.0.1"))


class TestDiscovery(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.server.setblocking(False)
        self.server.bind(("127.0.0.1", 0))
        self.addCleanup(self.server.close)
        patcher = patch(
            "pybls21.discovery._DISCOVERY_PORT", self.server.getsockname()[1]
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.loop = asyncio.get_running_loop()

    async def test_collects_multiple_devices_deduplicates_and_ignores_noise(self):
        async def answer():
            request, sender = await self.loop.sock_recvfrom(self.server, 1024)
            # Exact wire contract: read only, empty password, ID and type queries.
            self.assertEqual(
                request,
                bytes.fromhex("fdfd021044454641554c545f444556494345494400017cb9e905"),
            )
            for packet in (
                b"garbage",
                response(identity=b"0024005433379999"),
                CAPTURED,
                CAPTURED,
            ):
                await self.loop.sock_sendto(self.server, packet, sender)
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as wrong_port:
                wrong_port.sendto(response(identity=b"0024005433370000"), sender)

        responder = asyncio.create_task(answer())
        try:
            devices = await discover(
                address="127.0.0.1", local_address="127.0.0.1", timeout=0.1
            )
            await asyncio.wait_for(responder, 1)
        finally:
            responder.cancel()
            await asyncio.gather(responder, return_exceptions=True)
        self.assertEqual(
            [d.device_id for d in devices], [IDENTITY.decode(), "0024005433379999"]
        )
        self.assertTrue(all(d.host == "127.0.0.1" for d in devices))

    async def test_silence_returns_empty_tuple(self):
        self.assertEqual(await discover(address="127.0.0.1", timeout=0.02), ())

    async def test_cancellation_closes_socket(self):
        original = socket.socket
        sockets = []

        def factory(*args, **kwargs):
            sock = original(*args, **kwargs)
            sockets.append(sock)
            return sock

        with patch("pybls21.discovery.socket.socket", side_effect=factory):
            task = asyncio.create_task(discover(address="127.0.0.1", timeout=30))
            try:
                await asyncio.wait_for(self.loop.sock_recvfrom(self.server, 1024), 1)
            finally:
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
        self.assertEqual(sockets[0].fileno(), -1)

    async def test_invalid_arguments_do_not_open_socket(self):
        for kwargs in (
            *(
                {"timeout": value}
                for value in (0, -1, True, float("nan"), float("inf"), "3", None)
            ),
            {"address": "example.org"},
            {"address": "::1"},
            {"local_address": "not-an-ip"},
            {"address": 123},
            {"local_address": None},
        ):
            with (
                self.subTest(kwargs=kwargs),
                patch("pybls21.discovery.socket.socket") as factory,
            ):
                with self.assertRaises(ValueError):
                    await discover(**kwargs)
                factory.assert_not_called()

    async def test_socket_errors_are_wrapped_and_close_socket(self):
        for stage in ("create", "bind", "send", "receive", "socket_timeout"):
            error = (
                TimeoutError("socket timeout")
                if stage == "socket_timeout"
                else OSError("network unavailable")
            )
            sock = Mock()
            sock.__enter__ = Mock(return_value=sock)
            sock.__exit__ = Mock(return_value=False)
            factory = Mock(return_value=sock)
            send = AsyncMock()
            receive = AsyncMock()
            if stage == "create":
                factory.side_effect = error
            elif stage == "bind":
                sock.bind.side_effect = error
            elif stage == "send":
                send.side_effect = error
            else:
                receive.side_effect = error
            with (
                self.subTest(stage=stage),
                patch("pybls21.discovery.socket.socket", factory),
                patch.object(self.loop, "sock_sendto", send),
                patch.object(self.loop, "sock_recvfrom", receive),
            ):
                with self.assertRaises(DiscoveryError) as caught:
                    await discover()
                self.assertIsInstance(caught.exception, S21Error)
                self.assertIs(caught.exception.__cause__, error)
                if stage != "create":
                    sock.__exit__.assert_called_once()

    async def test_deadline_includes_send_and_closes_socket(self):
        sock = Mock()
        sock.__enter__ = Mock(return_value=sock)
        sock.__exit__ = Mock(return_value=False)

        async def blocked_send(*args):
            await asyncio.Event().wait()

        with (
            patch("pybls21.discovery.socket.socket", return_value=sock),
            patch.object(self.loop, "sock_sendto", side_effect=blocked_send),
        ):
            self.assertEqual(await discover(timeout=0.01), ())
        sock.__exit__.assert_called_once()
