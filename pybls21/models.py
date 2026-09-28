from dataclasses import dataclass
from datetime import timedelta
from enum import Enum, IntEnum

TEMP_CELSIUS: str = "°C"


class HVACMode(str, Enum):
    OFF = "off"
    HEAT = "heat"
    COOL = "cool"
    AUTO = "auto"
    FAN_ONLY = "fan_only"


class HVACAction(str, Enum):
    COOLING = "cooling"
    FAN = "fan"
    HEATING = "heating"
    IDLE = "idle"
    OFF = "off"


class BypassType(IntEnum):
    NOT_AVAILABLE = 0
    BYPASS_TWO_POINT = 1  # Discrete open/closed bypass damper control
    BYPASS_ANALOGUE = 2  # Bypass damper position controlled 0-100%
    ROTOR_DISCRETE = 3  # Discrete on/off rotary heat exchanger control
    ROTOR_ANALOGUE = 4  # Rotary heat exchanger speed controlled 0-100%
    BYPASS_THREE_POINT = 5  # Bypass damper driven open/closed via timed pulses


class BypassMode(IntEnum):
    CLOSED = 0  # Close the bypass / start the rotor
    OPEN = 1  # Open the bypass / stop the rotor (discrete), or manual % (analogue)
    AUTO = 2  # Device controls bypass/rotor automatically based on temperature


@dataclass(frozen=True, slots=True, kw_only=True)
class ClimateDevice:
    """Immutable snapshot of device state.

    Temperatures are °C, humidity and positions are percent, pressures are Pa,
    airflow is m³/h, and fan speeds are RPM unless named ``*_percent``.
    None means unavailable/unsupported, never zero. HVAC action is inferred
    from the configured mode and supply temperatures, not directly measured.
    """

    available: bool
    name: str
    temperature_unit: str
    precision: float
    current_temperature: float | None
    target_temperature: float
    target_temperature_step: float
    max_temp: float
    min_temp: float
    current_humidity: float | None
    hvac_mode: HVACMode
    hvac_action: HVACAction | None
    hvac_modes: tuple[HVACMode, ...]
    fan_mode: int | None
    fan_modes: tuple[int, ...]
    manufacturer: str
    model: str | None
    sw_version: str | None
    is_boosting: bool
    current_intake_temperature: float | None
    manual_fan_speed_percent: int
    max_fan_level: int
    filter_state: int
    alarm_state: int
    supply_fan_speed: int
    extract_fan_speed: int
    current_extract_temperature: float | None = None
    current_exhaust_temperature: float | None = None
    supply_pressure: int | None = None
    extract_pressure: int | None = None
    filter_countdown_days: int | None = None
    bypass_type: BypassType = BypassType.NOT_AVAILABLE
    bypass_mode: BypassMode | None = None
    bypass_position: int | None = None
    manual_bypass_position: int | None = None
    is_timer: bool = False
    timer_countdown: timedelta | None = None
    is_schedule_mode: bool = False
    fan_level_schedule_mode: int | None = None
    fan_level_timer_mode: int | None = None
    alarm_codes: tuple[int, ...] = ()
    supply_airflow: int | None = None
    extract_airflow: int | None = None
    operating_time_minutes: int | None = None
    filter_countdown_hours: int | None = None
    filter_countdown_minutes: int | None = None
    supply_fan_speed_percent: int | None = None
    extract_fan_speed_percent: int | None = None
