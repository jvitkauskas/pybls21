"""Decode the S21 register map without performing network I/O."""

from datetime import timedelta

from . import constants as reg
from .models import (
    TEMP_CELSIUS,
    BypassMode,
    BypassType,
    ClimateDevice,
    HVACAction,
    HVACMode,
)


def _parse_firmware_version(firmware_info: list[int]) -> str:
    major, minor = firmware_info[0].to_bytes(2, "big")

    day, month = firmware_info[1].to_bytes(2, "big")
    year = firmware_info[2]

    return f"{major}.{minor} ({year}-{month:02d}-{day:02d})"


def _to_signed_16bit(value: int) -> int:
    return value - 0x10000 if value > 0x7FFF else value


def _parse_temperature(value: int) -> float | None:
    # The S21 reserves these values for a missing or short-circuited sensor.
    if value in (0x8000, 0x7FFF):
        return None
    return _to_signed_16bit(value) / 10


def _parse_optional_percentage(value: int) -> int | None:
    # Firmware 0.36 (2019-05-08) was observed returning 0xFFFF for IR51-53
    # and beyond. A successful read does not imply a usable measurement.
    return value if 0 <= value <= 100 else None


MODE_TO_REGISTER = {
    HVACMode.FAN_ONLY: 0,
    HVACMode.HEAT: 1,
    HVACMode.COOL: 2,
    HVACMode.AUTO: 3,
}
REGISTER_TO_MODE = {value: mode for mode, value in MODE_TO_REGISTER.items()}


def _decode_hvac_mode(is_on: bool, operation_mode: int) -> HVACMode:
    if not is_on:
        return HVACMode.OFF
    return REGISTER_TO_MODE[operation_mode]


def _decode_hvac_action(
    mode: HVACMode, intake: float | None, supply: float | None
) -> HVACAction | None:
    # These are inferred actions, not measured heater/compressor activity.
    if mode == HVACMode.OFF:
        return HVACAction.OFF
    if mode == HVACMode.FAN_ONLY:
        return HVACAction.FAN
    if mode == HVACMode.HEAT:
        return HVACAction.HEATING
    if mode == HVACMode.COOL:
        return HVACAction.COOLING
    if intake is None or supply is None:
        return None
    if intake < supply:
        return HVACAction.HEATING
    if intake > supply:
        return HVACAction.COOLING
    return HVACAction.IDLE


def decode_device(
    *,
    coils: list[bool],
    holding_registers: list[int],
    input_registers: list[int],
    alarm_codes: list[int],
    bypass_registers: list[int] | None,
    fan_percentages: list[int] | None,
) -> ClimateDevice:
    """Decode validated blocks; unsupported enum values raise ValueError/KeyError."""
    is_on = coils[reg.CL_POWER]
    is_boosting = coils[reg.CL_Boost_MODE]
    set_temperature = holding_registers[reg.HR_SetTEMP]
    current_humidity = input_registers[reg.IR_CurRH_Int]
    filter_state = input_registers[reg.IR_StateFILTER]
    alarm_state = input_registers[reg.IR_ALARM]
    max_fan_level = holding_registers[reg.HR_MaxSPEED_MODE]
    current_fan_level = holding_registers[reg.HR_SPEED_MODE]  # 255 - manual
    temp_before_heating = _parse_temperature(input_registers[reg.IR_CurTEMP_SuAirIn])
    temp_after_heating = _parse_temperature(input_registers[reg.IR_CurTEMP_SuAirOut])
    supply_fan_speed = input_registers[reg.IR_SuRPM]
    extract_fan_speed = input_registers[reg.IR_ExRPM]
    firmware_info = input_registers[
        reg.IR_VerMAIN_FMW_start : reg.IR_VerMAIN_FMW_end + 1
    ]
    operation_mode = holding_registers[reg.HR_OPERATION_MODE]
    manual_fan_speed_percent = holding_registers[reg.HR_ManualSPEED]
    bypass_type = BypassType(holding_registers[reg.HR_BPS_ROTOR_TYPE])
    bypass_mode = (
        BypassMode(holding_registers[reg.HR_BPS_ROTOR_MODE])
        if bypass_type != BypassType.NOT_AVAILABLE
        else None
    )
    manual_bypass_position = (
        holding_registers[reg.HR_SetBpsRotorMANUAL]
        if bypass_type != BypassType.NOT_AVAILABLE
        else None
    )
    timer_minutes, timer_seconds = divmod(input_registers[reg.IR_CurTIMER_TIME], 256)
    timer_hours = input_registers[reg.IR_CurTIMER_TIME_HOURS] & 0xFF
    filter_hours, filter_minutes = divmod(
        input_registers[reg.IR_CurFILTER_TIMER_HOURS_MINUTES], 256
    )
    operating_hours, operating_minutes = divmod(
        input_registers[reg.IR_TotalWorkingTime_HOURS_MINUTES], 256
    )

    mode = _decode_hvac_mode(is_on, operation_mode)

    return ClimateDevice(
        available=True,
        name="Blauberg S21",
        temperature_unit=TEMP_CELSIUS,
        precision=1,
        current_temperature=temp_after_heating,
        target_temperature=set_temperature,
        target_temperature_step=1,
        min_temp=15,
        max_temp=30,
        current_humidity=None if current_humidity == 0 else current_humidity,
        hvac_mode=mode,
        hvac_action=_decode_hvac_action(mode, temp_before_heating, temp_after_heating),
        hvac_modes=(
            HVACMode.OFF,
            HVACMode.HEAT,
            HVACMode.COOL,
            HVACMode.AUTO,
            HVACMode.FAN_ONLY,
        ),
        fan_mode=current_fan_level,
        fan_modes=(*range(1, max_fan_level + 1), 255),
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
            input_registers[reg.IR_CurTEMP_ExAirIn]
        ),
        current_exhaust_temperature=_parse_temperature(
            input_registers[reg.IR_CurTEMP_ExAirOut]
        ),
        supply_pressure=input_registers[reg.IR_CurSuPRESS],
        extract_pressure=input_registers[reg.IR_CurExPRESS],
        filter_countdown_days=input_registers[reg.IR_CurFILTER_TIMER_DAYS],
        bypass_type=bypass_type,
        bypass_mode=bypass_mode,
        bypass_position=(
            _parse_optional_percentage(bypass_registers[0])
            if bypass_registers is not None
            else None
        ),
        manual_bypass_position=manual_bypass_position,
        is_timer=coils[reg.CL_TIMER],
        timer_countdown=timedelta(
            hours=timer_hours, minutes=timer_minutes, seconds=timer_seconds
        ),
        is_schedule_mode=coils[reg.CL_WEEK],
        fan_level_schedule_mode=input_registers[reg.IR_CurWeekSpeed],
        fan_level_timer_mode=holding_registers[reg.HR_TIMER_MODE],
        alarm_codes=tuple(alarm_codes),
        supply_airflow=input_registers[reg.IR_CurSuAirFLOW],
        extract_airflow=input_registers[reg.IR_CurExAirFLOW],
        operating_time_minutes=(
            input_registers[reg.IR_TotalWorkingTime_DAYS] * 1440
            + operating_hours * 60
            + operating_minutes
        ),
        filter_countdown_hours=filter_hours,
        filter_countdown_minutes=filter_minutes,
        supply_fan_speed_percent=(
            _parse_optional_percentage(fan_percentages[0])
            if fan_percentages is not None
            else None
        ),
        extract_fan_speed_percent=(
            _parse_optional_percentage(fan_percentages[1])
            if fan_percentages is not None
            else None
        ),
    )
