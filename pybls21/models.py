from enum import Enum
from typing import List, NamedTuple, Optional

TEMP_CELSIUS: str = "°C"


class ClimateEntityFeature(int, Enum):
    TARGET_TEMPERATURE = 1
    FAN_MODE = 8


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


class BypassType(int, Enum):
    NOT_AVAILABLE = 0
    BYPASS_TWO_POINT = 1  # Discrete open/closed bypass damper control
    BYPASS_ANALOGUE = 2  # Bypass damper position controlled 0-100%
    ROTOR_DISCRETE = 3  # Discrete on/off rotary heat exchanger control
    ROTOR_ANALOGUE = 4  # Rotary heat exchanger speed controlled 0-100%
    BYPASS_THREE_POINT = 5  # Bypass damper driven open/closed via timed pulses


class BypassMode(int, Enum):
    CLOSED = 0  # Close the bypass / start the rotor
    OPEN = 1  # Open the bypass / stop the rotor (discrete), or manual % (analogue)
    AUTO = 2  # Device controls bypass/rotor automatically based on temperature


class ClimateDevice(NamedTuple):
    available: bool
    name: str
    unique_id: str
    temperature_unit: str
    precision: float
    current_temperature: Optional[float]
    target_temperature: float
    target_temperature_step: float
    max_temp: float
    min_temp: float
    current_humidity: Optional[float]
    hvac_mode: str
    hvac_action: Optional[str]
    hvac_modes: List[str]
    fan_mode: Optional[int]
    fan_modes: Optional[List[int]]
    supported_features: int
    manufacturer: str
    model: Optional[str]
    sw_version: Optional[str]
    is_boosting: bool
    current_intake_temperature: Optional[float]
    manual_fan_speed_percent: int
    max_fan_level: int
    filter_state: int
    alarm_state: int
    supply_fan_speed: int
    extract_fan_speed: int
    current_extract_temperature: Optional[float] = None
    current_exhaust_temperature: Optional[float] = None
    supply_pressure: Optional[int] = None
    extract_pressure: Optional[int] = None
    filter_countdown_days: Optional[int] = None
    bypass_type: BypassType = BypassType.NOT_AVAILABLE
    bypass_mode: Optional[BypassMode] = None
    bypass_position: Optional[int] = None
    manual_bypass_position: Optional[int] = None
