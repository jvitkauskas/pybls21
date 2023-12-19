from pyModbusTCP.client import ModbusClient

from .constants import *
from .exceptions import *
from .models import ClimateDevice, ClimateEntityFeature, HVACAction, HVACMode, TEMP_CELSIUS

from typing import Callable, List, Optional
from threading import Lock


def _parse_firmware_version(firmware_info: List[int]) -> str:
    major_minor = firmware_info[0]
    major = (major_minor & 0xff00) >> 8
    minor = major_minor & 0xff

    day_month: int = firmware_info[1]
    day: int = (day_month & 0xff00) >> 8
    month: int = day_month & 0xff
    year: int = firmware_info[2]

    return f'{major}.{minor} ({year}-{month:02d}-{day:02d})'


class S21Client:
    def __init__(self, host: str, port: int = 502):
        self.host = host
        self.port = port
        self.client = ModbusClient(host=self.host, port=self.port, auto_open=False, auto_close=False)
        self.device: Optional[ClimateDevice] = None
        self.lock = Lock()

    def poll(self) -> ClimateDevice:
        return self._do_with_connection(self._poll)

    def turn_on(self) -> None:
        self._do_with_connection(self._turn_on)

    def turn_off(self) -> None:
        self._do_with_connection(self._turn_off)

    def set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        self._do_with_connection(lambda: self._set_hvac_mode(hvac_mode))

    def set_fan_mode(self, mode: int) -> None:
        self._do_with_connection(lambda: self._set_fan_mode(mode))

    def set_manual_fan_speed_percent(self, speed_percent: int) -> None:
        self._do_with_connection(lambda: self._set_manual_fan_speed_percent(speed_percent))

    def set_temperature(self, temp_celsius: int) -> None:
        self._do_with_connection(lambda: self._set_temperature(temp_celsius))

    def _do_with_connection(self, func: Callable):
        with self.lock:  # Device does not support multiple connections
            if not self.client.open():
                raise Exception("Failed to open connection")

            try:
                return func()
            except Exception:
                if isinstance(self.device, ClimateDevice):
                    self.device.available = False
                raise
            finally:
                self.client.close()  # Also, long connections break over time and become unusable

    def _poll(self) -> ClimateDevice:
        if self.client.read_input_registers(IR_DeviceTYPE)[0] != 1:
            raise UnsupportedDeviceException("Unsupported device (IR_DeviceTYPE != 1)")

        coils = self.client.read_coils(0, 4)
        holding_registers = self.client.read_holding_registers(0, 45)
        input_registers = self.client.read_input_registers(0, 39)

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
        firmware_info: List[int] = input_registers[IR_VerMAIN_FMW_start:IR_VerMAIN_FMW_end+1]
        operation_mode: int = holding_registers[HR_OPERATION_MODE]
        manual_fan_speed_percent: int = holding_registers[HR_ManualSPEED]

        self.device = ClimateDevice(
            available=True,
            name="Blauberg S21",
            unique_id=f'S21_{self.host}_{self.port}',
            temperature_unit=TEMP_CELSIUS,  # Seems like no Fahrenheit option is available
            precision=1,
            current_temperature=temp_after_heating_x10 / 10,
            target_temperature=set_temperature,
            target_temperature_step=1,
            min_temp=15,
            max_temp=30,
            current_humidity=None if current_humidity == 0 else current_humidity,
            hvac_mode=HVACMode.OFF if not is_on
            else HVACMode.FAN_ONLY if operation_mode == 0
            else HVACMode.HEAT if operation_mode == 1
            else HVACMode.COOL if operation_mode == 2
            else HVACMode.AUTO,
            hvac_action=HVACAction.OFF if not is_on
            else HVACAction.FAN if operation_mode == 0
            else HVACAction.HEATING if temp_before_heating_x10 < temp_after_heating_x10
            else HVACAction.COOLING if temp_before_heating_x10 > temp_after_heating_x10
            else HVACAction.IDLE,
            hvac_modes=[HVACMode.OFF, HVACMode.HEAT, HVACMode.COOL, HVACMode.AUTO, HVACMode.FAN_ONLY],
            fan_mode=current_fan_level,
            fan_modes=[x + 1 for x in range(max_fan_level)] + [255],
            supported_features=ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.FAN_MODE,
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

    def _turn_on(self) -> None:
        self.client.write_single_coil(CL_POWER, True)

    def _turn_off(self) -> None:
        self.client.write_single_coil(CL_POWER, False)

    def _set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.OFF:
            self._turn_off()
        elif hvac_mode == HVACMode.FAN_ONLY:
            self._turn_on()
            self.client.write_single_register(HR_OPERATION_MODE, 0)
        elif hvac_mode == HVACMode.HEAT:
            self._turn_on()
            self.client.write_single_register(HR_OPERATION_MODE, 1)
        elif hvac_mode == HVACMode.COOL:
            self._turn_on()
            self.client.write_single_register(HR_OPERATION_MODE, 2)
        elif hvac_mode == HVACMode.AUTO:
            self._turn_on()
            self.client.write_single_register(HR_OPERATION_MODE, 3)

    def _set_fan_mode(self, mode: int) -> None:
        self.client.write_single_register(HR_SPEED_MODE, mode)

    def _set_manual_fan_speed_percent(self, speed_percent: int) -> None:
        self.client.write_single_register(HR_ManualSPEED, speed_percent)

    def _set_temperature(self, temp_celsius: int) -> None:
        self.client.write_single_register(HR_SetTEMP, temp_celsius)
