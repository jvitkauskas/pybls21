"""Asynchronous Modbus TCP client for Blauberg S21 devices."""

import asyncio
import math
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace

from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException
from pymodbus.pdu import ExceptionResponse, ModbusPDU

from . import constants as reg
from ._decoder import MODE_TO_REGISTER, decode_device
from .exceptions import ModbusCommunicationException, UnsupportedDeviceException
from .models import BypassMode, BypassType, ClimateDevice, HVACMode


class S21Client:
    """Serialize requests and open a fresh connection for each public operation.

    ``timeout`` is the timeout per Modbus request, not a deadline for a complete
    poll. ``retries`` controls pymodbus request retries. Writes do not update the
    cached snapshot; call :meth:`poll` to obtain device-confirmed state.
    """

    def __init__(
        self, host: str, port: int = 502, *, timeout: float = 3.0, retries: int = 3
    ) -> None:
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Timeout must be finite and greater than zero")
        if type(retries) is not int or retries < 0:
            raise ValueError("Retries must be a nonnegative integer")
        self.host = host
        self.port = port
        self._client = AsyncModbusTcpClient(
            host, port=port, timeout=timeout, retries=retries
        )
        self._device: ClimateDevice | None = None
        self._lock = asyncio.Lock()

    @property
    def device(self) -> ClimateDevice | None:
        """Latest snapshot, or None before the first successful poll."""
        return self._device

    async def poll(self) -> ClimateDevice:
        """Read a complete snapshot; mark cached state unavailable on failure."""
        async with self._connection():
            self._device = await self._poll()
            return self._device

    async def turn_on(self) -> None:
        """Enable the unit without changing its configured operating mode."""
        async with self._connection():
            await self._write_coil(reg.CL_POWER, True)

    async def turn_off(self) -> None:
        """Disable the unit."""
        async with self._connection():
            await self._write_coil(reg.CL_POWER, False)

    async def set_hvac_mode(self, hvac_mode: HVACMode | str) -> None:
        """Set a supported mode; invalid values raise ValueError before I/O."""
        mode = HVACMode(hvac_mode)
        async with self._connection():
            if mode == HVACMode.OFF:
                await self._write_coil(reg.CL_POWER, False)
            else:
                await self._write_coil(reg.CL_POWER, True)
                await self._write_register(
                    reg.HR_OPERATION_MODE, MODE_TO_REGISTER[mode]
                )

    async def set_fan_mode(self, mode: int) -> None:
        """Set normal fan level (1–5), or 255 for manual percentage control."""
        self._validate_fan_mode(mode)
        async with self._connection():
            await self._write_register(reg.HR_SPEED_MODE, mode)

    async def set_manual_fan_speed_percent(self, speed_percent: int) -> None:
        """Set manual fan percentage (0–100); does not select manual mode."""
        self._validate_manual_fan_speed_percent(speed_percent)
        async with self._connection():
            await self._write_register(reg.HR_ManualSPEED, speed_percent)

    async def set_temperature(self, temp_celsius: int) -> None:
        """Set target temperature to an integer from 15 through 30 °C."""
        self._validate_temperature(temp_celsius)
        async with self._connection():
            await self._write_register(reg.HR_SetTEMP, temp_celsius)

    async def reset_filter_change_timer(self) -> None:
        """Restart the filter countdown using the device's configured interval."""
        async with self._connection():
            await self._write_coil(reg.CL_RESET_FILTER_TIMER, True)

    async def reset_alarm(self) -> None:
        """Request an alarm reset."""
        async with self._connection():
            await self._write_coil(reg.CL_RESET_ALARM, True)

    async def boost_on(self) -> None:
        """Enable boost mode."""
        async with self._connection():
            await self._write_coil(reg.CL_BoostSWITCH_CTRL, True)

    async def boost_off(self) -> None:
        """Disable boost mode."""
        async with self._connection():
            await self._write_coil(reg.CL_BoostSWITCH_CTRL, False)

    async def set_timer_on(self) -> None:
        """Enable the timer already configured on the device."""
        async with self._connection():
            await self._write_coil(reg.CL_TIMER, True)

    async def set_timer_off(self) -> None:
        """Disable the device timer."""
        async with self._connection():
            await self._write_coil(reg.CL_TIMER, False)

    async def set_scheduler_mode_on(self) -> None:
        """Enable the weekly schedule already configured on the device."""
        async with self._connection():
            await self._write_coil(reg.CL_WEEK, True)

    async def set_scheduler_mode_off(self) -> None:
        """Disable the weekly schedule."""
        async with self._connection():
            await self._write_coil(reg.CL_WEEK, False)

    async def set_bypass_mode(self, mode: BypassMode | int) -> None:
        """Select closed, open/manual, or automatic bypass/rotor control."""
        if isinstance(mode, bool):
            raise ValueError("Bypass mode must not be a boolean")
        mode = BypassMode(mode)
        async with self._connection():
            await self._write_register(reg.HR_BPS_ROTOR_MODE, int(mode))

    async def set_bypass_position(self, position_percent: int) -> None:
        """Set manual bypass position (0–100); does not select manual mode."""
        self._validate_bypass_position(position_percent)
        async with self._connection():
            await self._write_register(reg.HR_SetBpsRotorMANUAL, position_percent)

    @staticmethod
    def _validate_modbus_response(
        response: ModbusPDU | None, operation: str
    ) -> ModbusPDU:
        if response is None:
            raise ModbusCommunicationException(
                f"Modbus {operation} failed: empty response"
            )

        if response.isError():
            raise ModbusCommunicationException(
                f"Modbus {operation} failed: {response!r}"
            )

        return response

    def _get_registers(
        self, response: ModbusPDU | None, count: int, operation: str
    ) -> list[int]:
        registers = self._validate_modbus_response(response, operation).registers
        if not isinstance(registers, list) or len(registers) < count:
            raise ModbusCommunicationException(
                f"Modbus {operation} failed: expected {count} registers"
            )
        return registers

    def _get_bits(
        self, response: ModbusPDU | None, count: int, operation: str
    ) -> list[bool]:
        bits = self._validate_modbus_response(response, operation).bits
        if not isinstance(bits, list) or len(bits) < count:
            raise ModbusCommunicationException(
                f"Modbus {operation} failed: expected {count} coil bits"
            )
        return bits

    @staticmethod
    def _validate_fan_mode(mode: int) -> None:
        if type(mode) is not int or mode not in (1, 2, 3, 4, 5, 255):
            raise ValueError("Fan mode must be one of: 1, 2, 3, 4, 5, 255")

    @staticmethod
    def _validate_manual_fan_speed_percent(speed_percent: int) -> None:
        if type(speed_percent) is not int or not 0 <= speed_percent <= 100:
            raise ValueError("Manual fan speed percent must be between 0 and 100")

    @staticmethod
    def _validate_temperature(temp_celsius: int) -> None:
        if type(temp_celsius) is not int or not 15 <= temp_celsius <= 30:
            raise ValueError("Temperature must be between 15 and 30 °C")

    @staticmethod
    def _validate_bypass_position(position_percent: int) -> None:
        if type(position_percent) is not int or not 0 <= position_percent <= 100:
            raise ValueError("Bypass position percent must be between 0 and 100")

    async def _read_input_registers(self, address: int, count: int) -> list[int]:
        response = await self._client.read_input_registers(address, count=count)
        return self._get_registers(
            response, count, f"read input registers at {address}"
        )

    async def _read_optional_input_registers(
        self, address: int, count: int
    ) -> list[int] | None:
        response = await self._client.read_input_registers(address, count=count)
        # Treat Illegal Data Address as an unsupported optional reading, without
        # assuming a firmware cutoff. Other communication errors must surface.
        if isinstance(response, ExceptionResponse) and response.exception_code == 2:
            return None
        return self._get_registers(
            response, count, f"read input registers at {address}"
        )

    async def _read_alarm_codes(self) -> list[int]:
        response = await self._client.read_discrete_inputs(
            reg.DI_ALARM_START, count=reg.DI_ALARM_COUNT
        )
        bits = self._get_bits(response, reg.DI_ALARM_COUNT, "read alarm codes")
        # Modbus pads bit responses to whole bytes; ignore bits beyond code 52.
        return [code for code in range(reg.DI_ALARM_COUNT) if bits[code]]

    async def _read_holding_registers(self, address: int, count: int) -> list[int]:
        response = await self._client.read_holding_registers(address, count=count)
        return self._get_registers(
            response, count, f"read holding registers at {address}"
        )

    async def _read_coils(self, address: int, count: int) -> list[bool]:
        response = await self._client.read_coils(address, count=count)
        return self._get_bits(response, count, f"read coils at {address}")

    async def _write_register(self, address: int, value: int) -> None:
        response = await self._client.write_register(address, value)
        self._validate_modbus_response(response, f"write register {address}")

    async def _write_coil(self, address: int, value: bool) -> None:
        response = await self._client.write_coil(address, value)
        self._validate_modbus_response(response, f"write coil {address}")

    @asynccontextmanager
    async def _connection(self) -> AsyncIterator[None]:
        # The device supports a single connection and long-lived connections
        # become unreliable. Keep the lock until cleanup completes.
        async with self._lock:
            try:
                if not await self._client.connect():
                    raise ModbusCommunicationException(
                        "Failed to open Modbus TCP connection"
                    )
                yield
            except (OSError, ModbusException) as error:
                self._mark_unavailable()
                raise ModbusCommunicationException(str(error)) from error
            except Exception, asyncio.CancelledError:
                self._mark_unavailable()
                raise
            finally:
                self._client.close()

    def _mark_unavailable(self) -> None:
        if self._device is not None:
            self._device = replace(self._device, available=False)

    async def _poll(self) -> ClimateDevice:
        if (await self._read_input_registers(reg.IR_DeviceTYPE, count=1))[0] != 1:
            raise UnsupportedDeviceException("Unsupported device (IR_DeviceTYPE != 1)")
        coils = await self._read_coils(0, count=4)
        holding_registers = await self._read_holding_registers(0, count=76)
        input_registers = await self._read_input_registers(0, count=39)
        alarm_codes = (
            await self._read_alarm_codes() if input_registers[reg.IR_ALARM] else []
        )
        bypass_registers = (
            await self._read_optional_input_registers(reg.IR_StatusBpsRotor, count=1)
            if holding_registers[reg.HR_BPS_ROTOR_TYPE] != BypassType.NOT_AVAILABLE
            else None
        )
        fan_percentages = await self._read_optional_input_registers(
            reg.IR_CurSuFanSpeed, count=2
        )
        try:
            return decode_device(
                coils=coils,
                holding_registers=holding_registers,
                input_registers=input_registers,
                alarm_codes=alarm_codes,
                bypass_registers=bypass_registers,
                fan_percentages=fan_percentages,
            )
        except (ValueError, KeyError, OverflowError) as error:
            raise ModbusCommunicationException(
                "Invalid register value in device response"
            ) from error
