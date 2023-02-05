from pymodbus.exceptions import ConnectionException

from .models import ClimateDevice, HVACMode, HVACAction, TEMP_CELSIUS, ClimateEntityFeature
from .retrying_modbus_client import RetryingModbusClient

from typing import Optional


def _parse_firmware_version(firmware_info: list[int]):
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
        self.client = RetryingModbusClient(host=self.host, port=self.port)
        self.device: Optional[ClimateDevice] = None

    async def poll(self) -> ClimateDevice:
        try:
            coils = await self.client.read_coils(0, 4)
            holding_registers = await self.client.read_holding_registers(0, 45)
            input_registers = await self.client.read_input_registers(0, 38)

            is_on: bool = coils[0]
            is_boosting: bool = coils[3]
            set_temperature: int = holding_registers[44]
            current_humidity: int = input_registers[10]
            # filter_state: int = input_registers[31]
            # alarm_state: int = input_registers[38]
            max_fan_level: int = holding_registers[1]
            current_fan_level: int = holding_registers[2]  # 255 - manual
            temp_before_heating_x10: int = input_registers[1]
            temp_after_heating_x10: int = input_registers[2]
            firmware_info: list[int] = input_registers[34:37]
            device_type: int = input_registers[37]
            operation_mode: int = holding_registers[43]
            manual_fan_speed_percent: int = holding_registers[17]

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
                manual_fan_speed_percent=manual_fan_speed_percent
            )

            return self.device
        except ConnectionException as ce:
            if isinstance(self.device, ClimateDevice):
                self.device.available = False
            raise ConnectionError(ce) from ce
        except Exception:
            if isinstance(self.device, ClimateDevice):
                self.device.available = False
            raise

    async def turn_on(self) -> None:
        await self.client.write_coil(0, True)

    async def turn_off(self) -> None:
        await self.client.write_coil(0, False)

    async def set_hvac_mode(self, hvac_mode: HVACMode):
        if hvac_mode == HVACMode.OFF:
            await self.turn_off()
        elif hvac_mode == HVACMode.FAN_ONLY:
            await self.turn_on()
            await self.client.write_register(43, 0)
        elif hvac_mode == HVACMode.HEAT:
            await self.turn_on()
            await self.client.write_register(43, 1)
        elif hvac_mode == HVACMode.COOL:
            await self.turn_on()
            await self.client.write_register(43, 2)
        elif hvac_mode == HVACMode.AUTO:
            await self.turn_on()
            await self.client.write_register(43, 3)

    async def set_fan_mode(self, mode: int) -> None:
        await self.client.write_register(2, mode)

    async def set_manual_fan_speed_percent(self, speed_percent: int) -> None:
        await self.client.write_register(17, speed_percent)

    async def set_temperature(self, temp_celsius: int) -> None:
        await self.client.write_register(44, temp_celsius)
