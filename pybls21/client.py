from pyModbusTCP.client import ModbusClient

from .models import ClimateDevice, HVACMode, HVACAction, TEMP_CELSIUS, ClimateEntityFeature

from typing import Callable, Optional
from threading import Lock


def _parse_firmware_version(firmware_info: list[int]) -> str:
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
        coils = self.client.read_coils(0, 4)
        holding_registers = self.client.read_holding_registers(0, 45)
        input_registers = self.client.read_input_registers(0, 39)

        is_on: bool = coils[0]
        is_boosting: bool = coils[3]
        set_temperature: int = holding_registers[44]
        current_humidity: int = input_registers[10]
        filter_state: int = input_registers[31]
        alarm_state: int = input_registers[38]
        max_fan_level: int = holding_registers[1]
        current_fan_level: int = holding_registers[2]  # 255 - manual
        temp_before_heating_x10: int = input_registers[1]
        temp_after_heating_x10: int = input_registers[2]
        firmware_info: list[int] = input_registers[34:37]
        device_type: int = input_registers[37]
        operation_mode: int = holding_registers[43]
        manual_fan_speed_percent: int = holding_registers[17]

        self.client.close()

        model: str = "S21" if device_type == 1 else "Unknown"

        self.device = ClimateDevice(
            available=True,
            name=model,
            unique_id=f'{model}_{self.host}_{self.port}',
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
            model=model,
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
        self.client.write_single_coil(0, True)

    def _turn_off(self) -> None:
        self.client.write_single_coil(0, False)

    def _set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.OFF:
            self.turn_off()
        elif hvac_mode == HVACMode.FAN_ONLY:
            self.turn_on()
            self.client.write_single_register(43, 0)
        elif hvac_mode == HVACMode.HEAT:
            self.turn_on()
            self.client.write_single_register(43, 1)
        elif hvac_mode == HVACMode.COOL:
            self.turn_on()
            self.client.write_single_register(43, 2)
        elif hvac_mode == HVACMode.AUTO:
            self.turn_on()
            self.client.write_single_register(43, 3)

    def _set_fan_mode(self, mode: int) -> None:
        self.client.write_single_register(2, mode)

    def _set_manual_fan_speed_percent(self, speed_percent: int) -> None:
        self.client.write_single_register(17, speed_percent)

    def _set_temperature(self, temp_celsius: int) -> None:
        self.client.write_single_register(44, temp_celsius)
