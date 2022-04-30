from typing import List, NamedTuple, Optional

from enum import Enum


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


class ClimateDevice(NamedTuple):
    available: bool
    name: str
    unique_id: str
    temperature_unit: str
    precision: float
    current_temperature: float
    target_temperature: float
    target_temperature_step: float
    max_temp: float
    min_temp: float
    current_humidity: Optional[float]
    hvac_mode: str
    hvac_action: str
    hvac_modes: List[str]
    fan_mode: Optional[int]
    fan_modes: Optional[List[int]]
    supported_features: int
    manufacturer: str
    model: Optional[str]
    sw_version: Optional[str]
    is_boosting: bool
    current_intake_temperature: float
    manual_fan_speed_percent: int
