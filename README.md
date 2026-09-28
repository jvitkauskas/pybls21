# Blauberg S21 Asynchronous Python API
An api allowing control of AC state (temperature, on/off, speed) of an Blauberg S21 device locally over TCP.

## Usage

Requires Python 3.14.2+ and `pymodbus>=3.13.1,<4.0`.

```python
import asyncio

from pybls21 import HVACMode, S21Client, S21Error


async def main():
    client = S21Client("192.168.0.125", timeout=3.0, retries=3)
    try:
        snapshot = await client.poll()
        print(snapshot.current_temperature)
        await client.set_hvac_mode(HVACMode.AUTO)
        await client.set_temperature(21)
    except S21Error as error:
        print(f"Device unavailable: {error}")


asyncio.run(main())
```

Each operation opens and closes its connection. Calls on the same client are
serialized because the unit supports one connection. Reuse one client per unit.
`timeout` applies per Modbus request, not to the full poll. Writes do not update
cached readings; call `poll()` to get confirmed state.

To limit the whole poll, including waiting for the client lock, use an outer
`asyncio.timeout()` context. Handle its `TimeoutError` outside the block:

```python
try:
    async with asyncio.timeout(10):
        snapshot = await client.poll()
except TimeoutError:
    print("The total poll deadline expired")
except S21Error as error:
    print(f"Device communication failed: {error}")
```

The outer deadline also limits time spent on retries. A per-request timeout is
reported as `ModbusCommunicationException` (a subclass of `S21Error`); expiry of
the outer deadline raises `TimeoutError`. Cancellation cleans up an operation
that has started I/O. Cancelling while waiting for the lock leaves the operation
already using the connection unaffected.

Upgrading from v4? See [the migration guide](MIGRATION.md) for the changed model,
identity, exceptions, and Home Assistant component migration.

| Async method | Input / behavior |
| --- | --- |
| `poll()` | Return an immutable `ClimateDevice` snapshot |
| `turn_on()`, `turn_off()` | Enable/disable the unit |
| `set_hvac_mode(mode)` | `HVACMode` or its string value; invalid values raise `ValueError` |
| `set_fan_mode(mode)` | Level 1–5, or 255 for manual; use levels supported by the device |
| `set_manual_fan_speed_percent(value)` | Integer 0–100; does not select manual mode |
| `set_temperature(value)` | Integer 15–30 °C |
| `reset_filter_change_timer()` | Restart the configured filter interval |
| `reset_alarm()` | Request alarm reset |
| `boost_on()`, `boost_off()` | Enable/disable boost |
| `set_bypass_mode(mode)` | `BypassMode` or its integer value |
| `set_bypass_position(value)` | Integer 0–100; does not change bypass mode |
| `set_timer_on()`, `set_timer_off()` | Enable/disable the configured timer |
| `set_scheduler_mode_on()`, `set_scheduler_mode_off()` | Enable/disable the configured weekly schedule |

Booleans are not accepted as numeric control values. Bad arguments raise
`ValueError` before network I/O. `S21Error` is the base for
`UnsupportedDeviceException`, `DiscoveryError`, and `ModbusCommunicationException`; the latter
includes transport errors and timeouts, retaining the original cause.

## Discovering devices

```python
from pybls21 import discover, S21Client

# Broadcast one read-only UDP request and collect replies for three seconds.
devices = await discover()
for device in devices:
    print(device.device_id, device.host)
    snapshot = await S21Client(device.host).poll()

# Optional: target a subnet, choose a local interface, or query a known host.
devices = await discover(address="192.168.1.255", local_address="192.168.1.10")
devices = await discover(address="192.168.1.149", timeout=1.0)
```

`discover()` returns a tuple of immutable `DiscoveredDevice` objects with `host`
and `device_id`. It collects replies for the whole timeout, deduplicates by
controller ID (keeping the first address received), and sorts results by ID.
No replies means an empty tuple. Invalid arguments raise `ValueError`; socket
failures raise `DiscoveryError`, a subclass of `S21Error`, retaining the cause.
Cancellation propagates and closes the socket. No background tasks are left running.

Discovery uses IPv4 UDP port **4000**, independently of Modbus TCP port **502**.
It sends a parameter-read request for controller ID and device type using an
empty password. Replies must have a valid checksum, matching controller IDs,
and S21 device type 1. This was verified by unicast and broadcast against an S21
running firmware `0.36 (2019-05-08)`; availability on other firmware is not yet
verified. The packet format follows the manufacturer's
[UDP protocol documentation](https://device.report/m/4ad7c8426973ad1157494cc5715f286e69d244ea3fa438d4b66851938bebf485);
the [S21 manual](https://blaubergdata.de/Daten/Manual_S21.pdf) describes the app's
network-search feature.

The default broadcast address is `255.255.255.255`; it normally reaches only the
local subnet. On a host with multiple network interfaces, call discovery for
each desired interface using `local_address` and, if necessary, its subnet's
broadcast address. Arguments accept IPv4 addresses, not hostnames or IPv6.
Firewalls and network isolation can prevent replies; manual host configuration
remains supported. Discovery does not automatically run when creating a client.

The controller ID is a device-provided identifier that applications can use
across IP changes. It is separate from `ClimateDevice` and does not change
existing polling or entity IDs. UDP replies are not authenticated; validate a
candidate with `S21Client.poll()` before setting up the device. No device settings
are written and no password is needed for discovery on the tested unit.

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

## Heater and cooler activity

```python
snapshot = await client.poll()
print(snapshot.is_heating, snapshot.is_cooling)
```

`is_heating` and `is_cooling` expose the controller's operation indications at
**DI7 (`DI_StatusHEATER`)** and **DI8 (`DI_StatusCOOLER`)**, respectively. Every poll
reads both in one additional Modbus request, regardless of mode or alarm state.
These booleans come directly from the controller; temperature differences,
selected HVAC mode, and unit power do not override them. If both bits are set,
both fields remain true rather than arbitrarily selecting one action.
They indicate controller-reported operation, not independently measured power
consumption or proof that the attached heater/cooler is functioning.

A successful poll populates both fields. Failed, erroneous, or short responses
fail the poll and mark the cached snapshot unavailable, like other required
reads; they never silently report inactive equipment. The new fields default to
`None` only for manually constructed snapshots that omit them, preserving
compatibility with existing callers constructing `ClimateDevice`.

The reads were verified on a physical S21 running firmware `0.36 (2019-05-08)`:
both flags were false in fan-only mode while the fans ran. In a controlled test,
heating mode with a 15 °C target left DI7 false; raising the target to 25 °C
made DI7 true after about six seconds. Restoring fan-only mode and 15 °C made
DI7 false again, with fan level and alarm codes unchanged. No cooler was
configured, so active cooling is covered by the Modbus test server rather than
a physical cooling test. The legacy `hvac_action` field remains inferred for compatibility. Use the
new activity flags when actual heater/cooler status is needed; downstream
integrations must not treat the inferred field as measured activity.

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
If the device rejects this address with Illegal Data Address, `bypass_position` is `None` and
polling the other readings still succeeds. Other communication errors are
propagated. When no bypass/rotor is fitted, its mode and positions are `None`
and the optional read is skipped.

Snapshots are frozen dataclasses; access readings by attribute. Collections of
modes and alarm codes are immutable tuples. The component owns entity identity
and Home Assistant feature flags; the library does not generate a unique ID
from the network address.

## Timer, scheduler, and telemetry

`set_timer_on()` / `set_timer_off()` enable or disable the device's existing
main timer. `set_scheduler_mode_on()` / `set_scheduler_mode_off()` enable or
disable its existing weekly schedule. Configure the timer duration and weekly
schedule on the device; these methods only toggle their activation.

The following fields are available after `await client.poll()`:

| Field | Meaning |
| --- | --- |
| `is_timer` | Whether the main timer is active |
| `timer_countdown` | Remaining main timer time as `datetime.timedelta` |
| `is_schedule_mode` | Whether the weekly schedule is enabled |
| `fan_level_schedule_mode` | Current scheduled fan level; 0 means standby |
| `fan_level_timer_mode` | Configured timer fan level; 0 means standby |
| `alarm_codes` | Active numeric alarm codes (0–52); empty tuple when no alarm or warning is reported |
| `supply_airflow`, `extract_airflow` | Airflow in m³/h |
| `operating_time_minutes` | Total device operating time in minutes |
| `filter_countdown_hours`, `filter_countdown_minutes` | Remaining hours and minutes in addition to `filter_countdown_days` |
| `supply_fan_speed_percent`, `extract_fan_speed_percent` | Actual fan performance in percent, or `None` when unavailable |

`fan_mode` remains the configured normal fan level and `set_fan_mode(mode)`
still takes one argument. Timer and schedule levels are separate readings, not
an inferred effective fan level during overrides. The existing
`supply_fan_speed` and `extract_fan_speed` fields continue to report **RPM**.

The timer, schedule, airflow, operating time, and filter readings use the blocks
already fetched by polling. Detailed alarm codes add a discrete-input read only
when an alarm or warning is active. Fan percentages add a separate read of
IR52–53; an Illegal Data Address response leaves both percentages unknown without
interrupting other readings. Successful reads containing percentages outside
0–100 (including `65535` / `0xFFFF`) are also reported as `None`, individually
for bypass position and each fan percentage. Timeouts and other errors still propagate and
invalidate cached availability.

There is no verified firmware-version cutoff for these optional readings. The
bundled protocol table ends at IR50; a physical device reporting firmware
`0.36 (2019-05-08)` accepted IR51–53 reads but returned `0xFFFF` for all three.
It also returned `0xFFFF` at IR54–55. Those replies are not usable measurements
and do not establish that the corresponding features are implemented. Its full
DI0–71 range, including the 53 alarm bits, was readable.

These additions are adapted from [marni-xyz's fork](https://github.com/marni-xyz/pybls21),
including its operating-time, airflow, and fan-performance work attributed to
[birdie1](https://github.com/birdie1).

The copyright and MIT terms for these ported portions are retained in
[THIRD_PARTY_NOTICES](THIRD_PARTY_NOTICES), included in both source and wheel
distributions.

## Interpretation limits

`current_temperature` is the supply outlet temperature, not necessarily room
temperature. `hvac_action` is inferred: HEAT and COOL report their configured
action; AUTO compares supply temperatures before/after heating. It is not a
measurement of heater/compressor activity. Missing temperature sensors produce
`None`; zero remains a valid temperature. Optional unsupported registers also
produce `None`, while communication failures fail the poll.

## Development

```sh
python -m pip install -r requirements.txt
ruff check .
ruff format --check .
mypy
python -m coverage run -m unittest -v
python -m coverage report
python -m build
python -m twine check dist/*
```

CI tests Python 3.14.2 with minimum pymodbus and the latest Python 3.14 patch
with the newest allowed pymodbus, and requires at least 95% combined
statement/branch coverage. The Python minimum matches
[Home Assistant 2026.9.4](https://github.com/home-assistant/core/blob/2026.9.4/pyproject.toml#L22). The package ships
`py.typed` for downstream type checking.

## Releasing

Merges to `main` validate changes without publishing. Set the package version in
`pyproject.toml`, merge the change, and publish a GitHub release with its matching
`vVERSION` tag. The release workflow repeats validation, checks the tag/version
match, and publishes the validated wheel and source distribution to PyPI.
See [the release details](MIGRATION.md#development-and-releases).
