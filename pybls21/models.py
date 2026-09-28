from dataclasses import dataclass, field
from datetime import timedelta
from enum import IntEnum, StrEnum

TEMP_CELSIUS: str = "°C"


class HVACMode(StrEnum):
    OFF = "off"
    HEAT = "heat"
    COOL = "cool"
    AUTO = "auto"
    FAN_ONLY = "fan_only"


class HVACAction(StrEnum):
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

    available: bool = field(
        doc="Whether the most recent operation left the cached device state available."
    )
    name: str = field(doc="Descriptive device name; not a stable hardware identifier.")
    temperature_unit: str = field(
        doc="Temperature unit used by the device readings (°C)."
    )
    precision: float = field(doc="Suggested temperature display precision in °C.")
    current_temperature: float | None = field(
        doc="Supply outlet temperature in °C; None for a missing or faulty sensor."
    )
    target_temperature: float = field(doc="Configured target temperature in °C.")
    target_temperature_step: float = field(
        doc="Supported target-temperature increment in °C."
    )
    max_temp: float = field(doc="Maximum supported target temperature in °C.")
    min_temp: float = field(doc="Minimum supported target temperature in °C.")
    current_humidity: float | None = field(
        doc="Internal relative humidity in percent; a raw zero is reported as None."
    )
    hvac_mode: HVACMode = field(
        doc="Configured HVAC mode, or OFF when the unit is disabled."
    )
    hvac_action: HVACAction | None = field(
        doc="Action inferred from mode and supply temperatures; None when it cannot be inferred."
    )
    hvac_modes: tuple[HVACMode, ...] = field(doc="HVAC modes supported by this client.")
    fan_mode: int | None = field(
        doc="Configured normal fan level (1–5 or 255 for manual), independent of overrides; None if unknown."
    )
    fan_modes: tuple[int, ...] = field(
        doc="Normal fan levels available on the device, including 255 for manual control."
    )
    manufacturer: str = field(doc="Device manufacturer name.")
    model: str | None = field(doc="Device model name; None if unknown.")
    sw_version: str | None = field(
        doc="Firmware version and build date; None if unknown."
    )
    is_boosting: bool = field(doc="Whether the device reports boost mode active.")
    current_intake_temperature: float | None = field(
        doc="Supply inlet temperature before heating in °C; None for a missing or faulty sensor."
    )
    manual_fan_speed_percent: int = field(
        doc="Configured manual fan percentage (0–100), not measured fan performance."
    )
    max_fan_level: int = field(doc="Maximum normal fan level reported by the device.")
    filter_state: int = field(doc="Raw filter-status value from IR31.")
    alarm_state: int = field(doc="Alarm summary: 0 means none, 1 alarm, and 2 warning.")
    supply_fan_speed: int = field(doc="Measured supply fan speed in RPM.")
    extract_fan_speed: int = field(doc="Measured extract fan speed in RPM.")
    current_extract_temperature: float | None = field(
        default=None,
        doc="Extract air temperature from the rooms in °C; None for a missing or faulty sensor.",
    )
    current_exhaust_temperature: float | None = field(
        default=None,
        doc="Exhaust air temperature leaving the unit in °C; None for a missing or faulty sensor.",
    )
    supply_pressure: int | None = field(
        default=None, doc="Supply duct pressure in Pa; None when unavailable."
    )
    extract_pressure: int | None = field(
        default=None, doc="Extract duct pressure in Pa; None when unavailable."
    )
    filter_countdown_days: int | None = field(
        default=None,
        doc="Whole days remaining until filter service; combine with hours and minutes. None if unknown.",
    )
    bypass_type: BypassType = field(
        default=BypassType.NOT_AVAILABLE,
        doc="Installed bypass/rotor control type, or NOT_AVAILABLE if none is fitted.",
    )
    bypass_mode: BypassMode | None = field(
        default=None,
        doc="Configured bypass/rotor mode; None when no bypass/rotor is fitted.",
    )
    bypass_position: int | None = field(
        default=None,
        doc="Reported bypass/rotor position in percent (0–100); None for unsupported or invalid readings.",
    )
    manual_bypass_position: int | None = field(
        default=None,
        doc="Configured manual bypass/rotor percentage; None when no bypass/rotor is fitted.",
    )
    is_timer: bool = field(
        default=False, doc="Whether the main device timer is enabled."
    )
    timer_countdown: timedelta | None = field(
        default=None,
        doc="Remaining main timer duration; zero is valid and None means unknown.",
    )
    is_schedule_mode: bool = field(
        default=False, doc="Whether the weekly schedule is enabled."
    )
    fan_level_schedule_mode: int | None = field(
        default=None,
        doc="Current scheduled fan level (0 means standby); None if unknown.",
    )
    fan_level_timer_mode: int | None = field(
        default=None,
        doc="Configured timer fan level (0 means standby); None if unknown.",
    )
    alarm_codes: tuple[int, ...] = field(
        default=(),
        doc="Active numeric alarm/warning codes (0–52); empty when none are reported.",
    )
    supply_airflow: int | None = field(
        default=None, doc="Supply airflow in m³/h; None when unavailable."
    )
    extract_airflow: int | None = field(
        default=None, doc="Extract airflow in m³/h; None when unavailable."
    )
    operating_time_minutes: int | None = field(
        default=None,
        doc="Accumulated device operating time in minutes; None if unknown.",
    )
    filter_countdown_hours: int | None = field(
        default=None,
        doc="Remaining hours in addition to whole filter-countdown days; None if unknown.",
    )
    filter_countdown_minutes: int | None = field(
        default=None,
        doc="Remaining minutes in addition to filter-countdown days and hours; None if unknown.",
    )
    supply_fan_speed_percent: int | None = field(
        default=None,
        doc="Actual supply fan performance in percent (0–100); None for unsupported or invalid readings.",
    )
    extract_fan_speed_percent: int | None = field(
        default=None,
        doc="Actual extract fan performance in percent (0–100); None for unsupported or invalid readings.",
    )
