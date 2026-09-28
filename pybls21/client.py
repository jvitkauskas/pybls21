import asyncio
from typing import Any, Awaitable, Callable, List, Optional

from pymodbus.client import AsyncModbusTcpClient
from pymodbus.pdu import ExceptionResponse

from .constants import *
from .exceptions import *
from .models import (
    TEMP_CELSIUS,
    BypassMode,
    BypassType,
    ClimateDevice,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)


def _parse_firmware_version(firmware_info: List[int]) -> str:
    major, minor = firmware_info[0].to_bytes(2, "big")

    day, month = firmware_info[1].to_bytes(2, "big")
    year: int = firmware_info[2]

    return f"{major}.{minor} ({year}-{month:02d}-{day:02d})"


def _to_signed_16bit(value: int) -> int:
    return value - 0x10000 if value > 0x7FFF else value


def _parse_temperature(value: int) -> Optional[float]:
    # The S21 reserves these values for a missing or short-circuited sensor.
    if value in (0x8000, 0x7FFF):
        return None
    return _to_signed_16bit(value) / 10


class S21Client:
    def __init__(self, host: str, port: int = 502):
        self.host = host
        self.port = port
        self.client = AsyncModbusTcpClient(host=self.host, port=self.port)
        self.device: Optional[ClimateDevice] = None
        self.lock = asyncio.Lock()

    async def poll(self) -> ClimateDevice:
        return await self._do_with_connection(self._poll)

    async def turn_on(self) -> None:
        await self._do_with_connection(self._turn_on)

    async def turn_off(self) -> None:
        await self._do_with_connection(self._turn_off)

    async def set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        await self._do_with_connection(lambda: self._set_hvac_mode(hvac_mode))

    async def set_fan_mode(self, mode: int) -> None:
        self._validate_fan_mode(mode)
        await self._do_with_connection(lambda: self._set_fan_mode(mode))

    async def set_manual_fan_speed_percent(self, speed_percent: int) -> None:
        self._validate_manual_fan_speed_percent(speed_percent)
        await self._do_with_connection(
            lambda: self._set_manual_fan_speed_percent(speed_percent)
        )

    async def set_temperature(self, temp_celsius: int) -> None:
        self._validate_temperature(temp_celsius)
        await self._do_with_connection(lambda: self._set_temperature(temp_celsius))

    async def reset_filter_change_timer(self) -> None:
        await self._do_with_connection(self._reset_filter_change_timer)

    async def reset_alarm(self) -> None:
        await self._do_with_connection(self._reset_alarm)

    async def boost_on(self) -> None:
        await self._do_with_connection(self._set_boost_on)

    async def boost_off(self) -> None:
        await self._do_with_connection(self._set_boost_off)

    async def set_timer_on(self) -> None:
        await self._do_with_connection(lambda: self._write_coil(CL_TIMER, True))

    async def set_timer_off(self) -> None:
        await self._do_with_connection(lambda: self._write_coil(CL_TIMER, False))

    async def set_scheduler_mode_on(self) -> None:
        await self._do_with_connection(lambda: self._write_coil(CL_WEEK, True))

    async def set_scheduler_mode_off(self) -> None:
        await self._do_with_connection(lambda: self._write_coil(CL_WEEK, False))

    async def set_bypass_mode(self, mode: BypassMode) -> None:
        mode = BypassMode(mode)
        await self._do_with_connection(lambda: self._set_bypass_mode(mode))

    async def set_bypass_position(self, position_percent: int) -> None:
        self._validate_bypass_position(position_percent)
        await self._do_with_connection(
            lambda: self._set_bypass_position(position_percent)
        )

    @staticmethod
    def _validate_modbus_response(response: Any, operation: str) -> Any:
        if response is None:
            raise ModbusCommunicationException(f"Modbus {operation} failed: empty response")

        is_error = getattr(response, "isError", None)
        if callable(is_error) and response.isError():
            raise ModbusCommunicationException(
                f"Modbus {operation} failed: {response!r}"
            )

        return response

    def _get_registers(self, response: Any, count: int, operation: str) -> List[int]:
        registers = getattr(self._validate_modbus_response(response, operation), "registers", None)
        if not isinstance(registers, list) or len(registers) < count:
            raise ModbusCommunicationException(
                f"Modbus {operation} failed: expected {count} registers"
            )
        return registers

    def _get_bits(self, response: Any, count: int, operation: str) -> List[bool]:
        bits = getattr(self._validate_modbus_response(response, operation), "bits", None)
        if not isinstance(bits, list) or len(bits) < count:
            raise ModbusCommunicationException(
                f"Modbus {operation} failed: expected {count} coil bits"
            )
        return bits

    @staticmethod
    def _validate_fan_mode(mode: int) -> None:
        if not isinstance(mode, int) or mode not in (1, 2, 3, 4, 5, 255):
            raise ValueError("Fan mode must be one of: 1, 2, 3, 4, 5, 255")

    @staticmethod
    def _validate_manual_fan_speed_percent(speed_percent: int) -> None:
        if not isinstance(speed_percent, int) or not 0 <= speed_percent <= 100:
            raise ValueError("Manual fan speed percent must be between 0 and 100")

    @staticmethod
    def _validate_temperature(temp_celsius: int) -> None:
        if not isinstance(temp_celsius, int) or not 15 <= temp_celsius <= 30:
            raise ValueError("Temperature must be between 15 and 30 °C")

    @staticmethod
    def _validate_bypass_position(position_percent: int) -> None:
        if not isinstance(position_percent, int) or not 0 <= position_percent <= 100:
            raise ValueError("Bypass position percent must be between 0 and 100")

    async def _read_input_registers(self, address: int, count: int) -> List[int]:
        response = await self.client.read_input_registers(address, count=count)
        return self._get_registers(response, count, f"read input registers at {address}")

    async def _read_optional_input_registers(
        self, address: int, count: int
    ) -> Optional[List[int]]:
        response = await self.client.read_input_registers(address, count=count)
        # Older firmware lacks IR51-53. Only Illegal Data Address is optional;
        # timeouts, malformed replies and other device errors must still surface.
        if isinstance(response, ExceptionResponse) and response.exception_code == 2:
            return None
        return self._get_registers(response, count, f"read input registers at {address}")

    async def _read_alarm_codes(self) -> List[int]:
        response = await self.client.read_discrete_inputs(
            DI_ALARM_START, count=DI_ALARM_COUNT
        )
        bits = self._get_bits(response, DI_ALARM_COUNT, "read alarm codes")
        # Modbus pads bit responses to whole bytes; ignore bits beyond code 52.
        return [code for code in range(DI_ALARM_COUNT) if bits[code]]

    async def _read_holding_registers(self, address: int, count: int) -> List[int]:
        response = await self.client.read_holding_registers(address, count=count)
        return self._get_registers(response, count, f"read holding registers at {address}")

    async def _read_coils(self, address: int, count: int) -> List[bool]:
        response = await self.client.read_coils(address, count=count)
        return self._get_bits(response, count, f"read coils at {address}")

    async def _write_register(self, address: int, value: int) -> None:
        response = await self.client.write_register(address, value)
        self._validate_modbus_response(response, f"write register {address}")

    async def _write_coil(self, address: int, value: bool) -> None:
        response = await self.client.write_coil(address, value)
        self._validate_modbus_response(response, f"write coil {address}")

    async def _do_with_connection(self, func: Callable[[], Awaitable[Any]]) -> Any:
        async with self.lock:  # Device does not support multiple connections
            try:
                if not await self.client.connect():
                    raise ModbusCommunicationException(
                        "Failed to open Modbus TCP connection"
                    )
                return await func()
            except Exception:
                if isinstance(self.device, ClimateDevice):
                    # ClimateDevice is a NamedTuple and therefore immutable,
                    # so the flag has to be replaced instead of assigned.
                    self.device = self.device._replace(available=False)
                raise
            finally:
                self.client.close()  # Also, long connections break over time and become unusable

    async def _poll(self) -> ClimateDevice:
        if (await self._read_input_registers(IR_DeviceTYPE, count=1))[0] != 1:
            raise UnsupportedDeviceException("Unsupported device (IR_DeviceTYPE != 1)")

        coils = await self._read_coils(0, count=4)
        holding_registers = await self._read_holding_registers(0, count=76)
        input_registers = await self._read_input_registers(0, count=39)

        is_on: bool = coils[CL_POWER]
        is_boosting: bool = coils[CL_Boost_MODE]
        set_temperature: int = holding_registers[HR_SetTEMP]
        current_humidity: int = input_registers[IR_CurRH_Int]
        filter_state: int = input_registers[IR_StateFILTER]
        alarm_state: int = input_registers[IR_ALARM]
        alarm_codes = await self._read_alarm_codes() if alarm_state else []
        max_fan_level: int = holding_registers[HR_MaxSPEED_MODE]
        current_fan_level: int = holding_registers[HR_SPEED_MODE]  # 255 - manual
        temp_before_heating = _parse_temperature(
            input_registers[IR_CurTEMP_SuAirIn]
        )
        temp_after_heating = _parse_temperature(
            input_registers[IR_CurTEMP_SuAirOut]
        )
        supply_fan_speed: int = input_registers[IR_SuRPM]
        extract_fan_speed: int = input_registers[IR_ExRPM]
        firmware_info: List[int] = input_registers[
            IR_VerMAIN_FMW_start : IR_VerMAIN_FMW_end + 1
        ]
        operation_mode: int = holding_registers[HR_OPERATION_MODE]
        manual_fan_speed_percent: int = holding_registers[HR_ManualSPEED]
        bypass_type: BypassType = BypassType(holding_registers[HR_BPS_ROTOR_TYPE])
        bypass_mode = (
            BypassMode(holding_registers[HR_BPS_ROTOR_MODE])
            if bypass_type != BypassType.NOT_AVAILABLE
            else None
        )
        manual_bypass_position = (
            holding_registers[HR_SetBpsRotorMANUAL]
            if bypass_type != BypassType.NOT_AVAILABLE
            else None
        )
        bypass_registers = (
            await self._read_optional_input_registers(IR_StatusBpsRotor, count=1)
            if bypass_type != BypassType.NOT_AVAILABLE
            else None
        )
        fan_percentages = await self._read_optional_input_registers(
            IR_CurSuFanSpeed, count=2
        )
        timer_minutes, timer_seconds = divmod(input_registers[IR_CurTIMER_TIME], 256)
        timer_hours = input_registers[IR_CurTIMER_TIME_HOURS] & 0xFF
        filter_hours, filter_minutes = divmod(
            input_registers[IR_CurFILTER_TIMER_HOURS_MINUTES], 256
        )
        operating_hours, operating_minutes = divmod(
            input_registers[IR_TotalWorkingTime_HOURS_MINUTES], 256
        )

        self.device = ClimateDevice(
            available=True,
            name="Blauberg S21",
            unique_id=f"S21_{self.host}_{self.port}",
            temperature_unit=TEMP_CELSIUS,  # Seems like no Fahrenheit option is available
            precision=1,
            current_temperature=temp_after_heating,
            target_temperature=set_temperature,
            target_temperature_step=1,
            min_temp=15,
            max_temp=30,
            current_humidity=None if current_humidity == 0 else current_humidity,
            hvac_mode=HVACMode.OFF
            if not is_on
            else HVACMode.FAN_ONLY
            if operation_mode == 0
            else HVACMode.HEAT
            if operation_mode == 1
            else HVACMode.COOL
            if operation_mode == 2
            else HVACMode.AUTO,
            hvac_action=HVACAction.OFF
            if not is_on
            else HVACAction.FAN
            if operation_mode == 0
            else HVACAction.HEATING
            if operation_mode == 1
            else HVACAction.COOLING
            if operation_mode == 2
            else None
            if temp_before_heating is None or temp_after_heating is None
            else HVACAction.HEATING
            if temp_before_heating < temp_after_heating
            else HVACAction.COOLING
            if temp_before_heating > temp_after_heating
            else HVACAction.IDLE,
            hvac_modes=[
                HVACMode.OFF,
                HVACMode.HEAT,
                HVACMode.COOL,
                HVACMode.AUTO,
                HVACMode.FAN_ONLY,
            ],
            fan_mode=current_fan_level,
            fan_modes=[x + 1 for x in range(max_fan_level)] + [255],
            supported_features=ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.FAN_MODE,
            manufacturer="Blauberg",
            model="S21",
            sw_version=_parse_firmware_version(firmware_info),
            is_boosting=is_boosting,
            current_intake_temperature=temp_before_heating,
            manual_fan_speed_percent=manual_fan_speed_percent,
            max_fan_level=max_fan_level,
            filter_state=filter_state,
            alarm_state=alarm_state,
            supply_fan_speed=supply_fan_speed,
            extract_fan_speed=extract_fan_speed,
            current_extract_temperature=_parse_temperature(
                input_registers[IR_CurTEMP_ExAirIn]
            ),
            current_exhaust_temperature=_parse_temperature(
                input_registers[IR_CurTEMP_ExAirOut]
            ),
            supply_pressure=input_registers[IR_CurSuPRESS],
            extract_pressure=input_registers[IR_CurExPRESS],
            filter_countdown_days=input_registers[IR_CurFILTER_TIMER_DAYS],
            bypass_type=bypass_type,
            bypass_mode=bypass_mode,
            bypass_position=bypass_registers[0] if bypass_registers is not None else None,
            manual_bypass_position=manual_bypass_position,
            is_timer=coils[CL_TIMER],
            timer_countdown=f"{timer_hours:02d}:{timer_minutes:02d}:{timer_seconds:02d}",
            is_schedule_mode=coils[CL_WEEK],
            fan_level_schedule_mode=input_registers[IR_CurWeekSpeed],
            fan_level_timer_mode=holding_registers[HR_TIMER_MODE],
            alarm_codes=alarm_codes,
            supply_airflow=input_registers[IR_CurSuAirFLOW],
            extract_airflow=input_registers[IR_CurExAirFLOW],
            operating_time_minutes=(
                input_registers[IR_TotalWorkingTime_DAYS] * 1440
                + operating_hours * 60 + operating_minutes
            ),
            filter_countdown_hours=filter_hours,
            filter_countdown_minutes=filter_minutes,
            supply_fan_speed_percent=(
                fan_percentages[0] if fan_percentages is not None else None
            ),
            extract_fan_speed_percent=(
                fan_percentages[1] if fan_percentages is not None else None
            ),
        )

        return self.device

    async def _turn_on(self) -> None:
        await self._write_coil(CL_POWER, True)

    async def _turn_off(self) -> None:
        await self._write_coil(CL_POWER, False)

    async def _set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.OFF:
            await self._turn_off()
        elif hvac_mode == HVACMode.FAN_ONLY:
            await self._turn_on()
            await self._write_register(HR_OPERATION_MODE, 0)
        elif hvac_mode == HVACMode.HEAT:
            await self._turn_on()
            await self._write_register(HR_OPERATION_MODE, 1)
        elif hvac_mode == HVACMode.COOL:
            await self._turn_on()
            await self._write_register(HR_OPERATION_MODE, 2)
        else:
            await self._turn_on()
            await self._write_register(HR_OPERATION_MODE, 3)

    async def _set_fan_mode(self, mode: int) -> None:
        await self._write_register(HR_SPEED_MODE, mode)

    async def _set_manual_fan_speed_percent(self, speed_percent: int) -> None:
        await self._write_register(HR_ManualSPEED, speed_percent)

    async def _set_temperature(self, temp_celsius: int) -> None:
        await self._write_register(HR_SetTEMP, temp_celsius)

    async def _reset_filter_change_timer(self) -> None:
        await self._write_coil(CL_RESET_FILTER_TIMER, True)

    async def _reset_alarm(self) -> None:
        await self._write_coil(CL_RESET_ALARM, True)

    async def _set_boost_on(self) -> None:
        await self._write_coil(CL_BoostSWITCH_CTRL, True)

    async def _set_boost_off(self) -> None:
        await self._write_coil(CL_BoostSWITCH_CTRL, False)

    async def _set_bypass_mode(self, mode: BypassMode) -> None:
        await self._write_register(HR_BPS_ROTOR_MODE, int(mode))

    async def _set_bypass_position(self, position_percent: int) -> None:
        await self._write_register(HR_SetBpsRotorMANUAL, position_percent)
