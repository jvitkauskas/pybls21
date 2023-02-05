from pymodbus.exceptions import ConnectionException

from .models import ClimateDevice, HVACMode, HVACAction, TEMP_CELSIUS, ClimateEntityFeature

from pymodbus.client.sync import ModbusTcpClient

from typing import List, Optional


def _parse_firmware_version(firmware_info: List[int]):
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
        self.client: ModbusTcpClient = ModbusTcpClient(host=self.host, port=self.port)
        self.device: Optional[ClimateDevice] = None

    def poll_status(self) -> ClimateDevice:
        try:
            is_on: bool = (self.client.read_coils(0, 1)).bits[0]
            is_boosting: bool = (self.client.read_coils(3, 1)).bits[0]
            set_temperature: int = (self.client.read_holding_registers(44, 1)).registers[0]
            current_humidity: int = (self.client.read_input_registers(10, 1)).registers[0]
            # filter_state: int = (self.client.read_input_registers(31, 1)).registers[0]
            # alarm_state: int = (self.client.read_input_registers(38, 1)).registers[0]
            max_fan_level: int = (self.client.read_holding_registers(1, 1)).registers[0]
            current_fan_level: int = (self.client.read_holding_registers(2, 1)).registers[0]  # 255 - manual
            temp_before_heating_x10: int = (self.client.read_input_registers(1, 1)).registers[0]
            temp_after_heating_x10: int = (self.client.read_input_registers(2, 1)).registers[0]
            firmware_info: List[int] = (self.client.read_input_registers(34, 3)).registers
            device_type: int = (self.client.read_input_registers(37, 1)).registers[0]
            operation_mode: int = (self.client.read_holding_registers(43, 1)).registers[0]
            manual_fan_speed_percent: int = (self.client.read_holding_registers(17, 1)).registers[0]

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
                fan_modes=[x+1 for x in range(max_fan_level)] + [255],
                supported_features=ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.FAN_MODE,
                manufacturer="Blauberg",
                model=model,
                sw_version=_parse_firmware_version(firmware_info),
                is_boosting=is_boosting,
                current_intake_temperature=temp_before_heating_x10 / 10,
                manual_fan_speed_percent=manual_fan_speed_percent
            )

            return self.device
        except ConnectionException as ce:
            if self.device:
                self.device.available = False
            raise ConnectionError(ce) from ce
        except Exception:
            if self.device:
                self.device.available = False
            raise

    def turn_on(self) -> None:
        self.client.write_coil(0, 1)

    def turn_off(self) -> None:
        self.client.write_coil(0, 0)

    def set_hvac_mode(self, hvac_mode: HVACMode):
        if hvac_mode == HVACMode.OFF:
            self.client.write_coil(0, 0)
        elif hvac_mode == HVACMode.FAN_ONLY:
            self.client.write_coil(0, 1)
            self.client.write_register(43, 0)
        elif hvac_mode == HVACMode.HEAT:
            self.client.write_coil(0, 1)
            self.client.write_register(43, 1)
        elif hvac_mode == HVACMode.COOL:
            self.client.write_coil(0, 1)
            self.client.write_register(43, 2)
        elif hvac_mode == HVACMode.AUTO:
            self.client.write_coil(0, 1)
            self.client.write_register(43, 3)

    def set_fan_mode(self, mode: int) -> None:
        self.client.write_register(2, mode)

    def set_manual_fan_speed_percent(self, speed_percent: int) -> None:
        self.client.write_register(17, speed_percent)

    def set_temperature(self, temp_celsius: int) -> None:
        self.client.write_register(44, temp_celsius)
