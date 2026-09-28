# Blauberg S21 Asynchronous Python API
An api allowing control of AC state (temperature, on/off, speed) of an Blauberg S21 device locally over TCP.

## Usage
To initialize:
`client = S21Client("192.168.0.125")`

To load:
`await client.poll()`

The following functions are available:
`turn_on()`
`turn_off()`
`set_hvac_mode(hvac_mode: HVACMode)`
`set_fan_mode(mode: int)`
`set_manual_fan_speed_percent(speed_percent: int)`
`set_temperature(temp_celsius: int)`
`reset_filter_change_timer()`
`reset_alarm()`
`boost_on()`
`boost_off()`
`set_bypass_mode(mode: BypassMode)`
`set_bypass_position(position_percent: int)`
`set_timer_on()` / `set_timer_off()`
`set_scheduler_mode_on()` / `set_scheduler_mode_off()`


## Additional readings

`await client.poll()` also returns extract and exhaust air temperatures
(`current_extract_temperature`, `current_exhaust_temperature`), supply and
extract duct pressure in Pa (`supply_pressure`, `extract_pressure`), and whole
days remaining until filter replacement (`filter_countdown_days`).

Missing or short-circuited temperature sensors are reported as `None`, including
`current_temperature` and `current_intake_temperature`. In AUTO mode,
`hvac_action` is also `None` when either temperature needed to infer the action
is unavailable. Other readings remain usable and `available` stays true after
a successful poll. Connection and communication failures mark
`client.device.available` false if a previous poll populated the device; a
successful subsequent poll restores it. Previously returned models are immutable
snapshots, so read `client.device` for the updated availability.

## Bypass control

```python
from pybls21.models import BypassMode

# AUTO lets the device control its bypass or rotary heat exchanger.
await client.set_bypass_mode(BypassMode.AUTO)

# For analogue control, set the manual percentage and select manual mode.
await client.set_bypass_position(60)
await client.set_bypass_mode(BypassMode.OPEN)
```

`CLOSED` closes the bypass or starts the rotor. `OPEN` opens the bypass or stops
the rotor for discrete control; with analogue control it selects the percentage
set by `set_bypass_position()`. That setter alone does not change the mode.
A value of 0 means closed bypass / maximum rotor speed; 100 means open bypass /
stopped rotor. Choose controls appropriate to the reported `bypass_type`.

The model exposes `bypass_type`, `bypass_mode`, `manual_bypass_position`, and
`bypass_position`. Position is read separately from optional input register 51.
On older firmware that rejects this address, `bypass_position` is `None` and
polling the other readings still succeeds. Other communication errors are
propagated. When no bypass/rotor is fitted, its mode and positions are `None`
and the optional read is skipped.

New model fields have defaults, preserving construction with the original
positional or keyword arguments. The tuple now contains additional fields;
consumers should access readings by attribute rather than unpacking a fixed
number of values.

## Timer, scheduler, and telemetry

`set_timer_on()` / `set_timer_off()` enable or disable the device's existing
main timer. `set_scheduler_mode_on()` / `set_scheduler_mode_off()` enable or
disable its existing weekly schedule. Configure the timer duration and weekly
schedule on the device; these methods only toggle their activation.

The following fields are available after `await client.poll()`:

| Field | Meaning |
| --- | --- |
| `is_timer` | Whether the main timer is active |
| `timer_countdown` | Remaining main timer time as `HH:MM:SS` |
| `is_schedule_mode` | Whether the weekly schedule is enabled |
| `fan_level_schedule_mode` | Current scheduled fan level; 0 means standby |
| `fan_level_timer_mode` | Configured timer fan level; 0 means standby |
| `alarm_codes` | Active numeric alarm codes (0–52); empty list when no alarm or warning is reported |
| `supply_airflow`, `extract_airflow` | Airflow in m³/h |
| `operating_time_minutes` | Total device operating time in minutes |
| `filter_countdown_hours`, `filter_countdown_minutes` | Remaining hours and minutes in addition to `filter_countdown_days` |
| `supply_fan_speed_percent`, `extract_fan_speed_percent` | Actual fan performance in percent, or `None` on older firmware |

`fan_mode` remains the configured normal fan level and `set_fan_mode(mode)`
still takes one argument. Timer and schedule levels are separate readings, not
an inferred effective fan level during overrides. The existing
`supply_fan_speed` and `extract_fan_speed` fields continue to report **RPM**.

The timer, schedule, airflow, operating time, and filter readings use the blocks
already fetched by polling. Detailed alarm codes add a discrete-input read only
when an alarm or warning is active. Fan percentages add a separate read of
IR52–53; an Illegal Data Address response leaves both percentages unknown without
interrupting other readings. Timeouts and other errors still propagate and
invalidate cached availability.

These additions are adapted from [marni-xyz's fork](https://github.com/marni-xyz/pybls21),
including its operating-time, airflow, and fan-performance work attributed to
[birdie1](https://github.com/birdie1).

The copyright and MIT terms for these ported portions are retained in
[THIRD_PARTY_NOTICES](THIRD_PARTY_NOTICES), included in both source and wheel
distributions.
