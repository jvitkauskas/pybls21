from threading import Lock
from typing import Callable, List, Optional

from pymodbus.client import AsyncModbusTcpClient

from .constants import *
from .exceptions import *
from .models import (
    TEMP_CELSIUS,
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


class S21Client:
    def __init__(self, host: str, port: int = 502):
        self.host = host
        self.port = port
        self.client = AsyncModbusTcpClient(host=self.host, port=self.port)
        self.device: Optional[ClimateDevice] = None
        self.lock = Lock()

    async def poll(self) -> ClimateDevice:
        return await self._do_with_connection(self._poll)

    async def turn_on(self) -> None:
        await self._do_with_connection(self._turn_on)

    async def turn_off(self) -> None:
        await self._do_with_connection(self._turn_off)

    async def set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        await self._do_with_connection(lambda: self._set_hvac_mode(hvac_mode))

    async def set_fan_mode(self, mode: int) -> None:
        await self._do_with_connection(lambda: self._set_fan_mode(mode))

    async def set_manual_fan_speed_percent(self, speed_percent: int) -> None:
        await self._do_with_connection(
            lambda: self._set_manual_fan_speed_percent(speed_percent)
        )

    async def set_temperature(self, temp_celsius: int) -> None:
        await self._do_with_connection(lambda: self._set_temperature(temp_celsius))

    async def reset_filter_change_timer(self) -> None:
        await self._do_with_connection(self._reset_filter_change_timer)

    async def _do_with_connection(self, func: Callable):
        with self.lock:  # Device does not support multiple connections
            if not await self.client.connect():
                raise Exception("Failed to open connection")

            try:
                return await func()
            except Exception:
                if isinstance(self.device, ClimateDevice):
                    self.device.available = False
                raise
            finally:
                self.client.close()  # Also, long connections break over time and become unusable

    async def _poll(self) -> ClimateDevice:
        if (await self.client.read_input_registers(IR_DeviceTYPE)).registers[0] != 1:
            raise UnsupportedDeviceException("Unsupported device (IR_DeviceTYPE != 1)")

        coils = (await self.client.read_coils(0, 4)).bits
        holding_registers = (await self.client.read_holding_registers(0, 45)).registers
        input_registers = (await self.client.read_input_registers(0, 39)).registers

        is_on: bool = coils[CL_POWER]
        is_boosting: bool = coils[CL_Boost_MODE]
        set_temperature: int = holding_registers[HR_SetTEMP]
        current_humidity: int = input_registers[IR_CurRH_Int]
        filter_state: int = input_registers[IR_StateFILTER]
        alarm_state: int = input_registers[IR_ALARM]
        max_fan_level: int = holding_registers[HR_MaxSPEED_MODE]
        current_fan_level: int = holding_registers[HR_SPEED_MODE]  # 255 - manual
        temp_before_heating_x10: int = input_registers[IR_CurTEMP_SuAirIn]
        temp_after_heating_x10: int = input_registers[IR_CurTEMP_SuAirOut]
        firmware_info: List[int] = input_registers[
            IR_VerMAIN_FMW_start : IR_VerMAIN_FMW_end + 1
        ]
        operation_mode: int = holding_registers[HR_OPERATION_MODE]
        manual_fan_speed_percent: int = holding_registers[HR_ManualSPEED]

        self.device = ClimateDevice(
            available=True,
            name="Blauberg S21",
            unique_id=f"S21_{self.host}_{self.port}",
            temperature_unit=TEMP_CELSIUS,  # Seems like no Fahrenheit option is available
            precision=1,
            current_temperature=temp_after_heating_x10 / 10,
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
            else HVACAction.HEATING
            if temp_before_heating_x10 < temp_after_heating_x10
            else HVACAction.COOLING
            if temp_before_heating_x10 > temp_after_heating_x10
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
            current_intake_temperature=temp_before_heating_x10 / 10,
            manual_fan_speed_percent=manual_fan_speed_percent,
            max_fan_level=max_fan_level,
            filter_state=filter_state,
            alarm_state=alarm_state,
        )

        return self.device

    async def _turn_on(self) -> None:
        await self.client.write_coil(CL_POWER, True)

    async def _turn_off(self) -> None:
        await self.client.write_coil(CL_POWER, False)

    async def _set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.OFF:
            await self._turn_off()
        elif hvac_mode == HVACMode.FAN_ONLY:
            await self._turn_on()
            await self.client.write_register(HR_OPERATION_MODE, 0)
        elif hvac_mode == HVACMode.HEAT:
            await self._turn_on()
            await self.client.write_register(HR_OPERATION_MODE, 1)
        elif hvac_mode == HVACMode.COOL:
            await self._turn_on()
            await self.client.write_register(HR_OPERATION_MODE, 2)
        elif hvac_mode == HVACMode.AUTO:
            await self._turn_on()
            await self.client.write_register(HR_OPERATION_MODE, 3)

    async def _set_fan_mode(self, mode: int) -> None:
        await self.client.write_register(HR_SPEED_MODE, mode)

    async def _set_manual_fan_speed_percent(self, speed_percent: int) -> None:
        await self.client.write_register(HR_ManualSPEED, speed_percent)

    async def _set_temperature(self, temp_celsius: int) -> None:
        await self.client.write_register(HR_SetTEMP, temp_celsius)

    async def _reset_filter_change_timer(self) -> None:
        await self.client.write_coil(CL_RESET_FILTER_TIMER, True)
