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
