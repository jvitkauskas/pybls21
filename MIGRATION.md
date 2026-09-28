# Migrating from 4.4 to 5.0

Version 5 keeps the async control methods and Modbus mappings, but changes the
state model, error contract, and packaging. Update the Home Assistant component
before changing its pinned dependency to `pybls21==5.0.0`.

## Python requirement

Version 5 requires Python 3.14.2 or newer, matching Home Assistant 2026.9.4.
Python 3.10–3.13 and Python 3.14.0–3.14.1 are no longer supported. Update the
runtime before upgrading; older Home Assistant installations may need an update.

## Device snapshots

`ClimateDevice` is now a frozen, keyword-only dataclass with slots. Attribute
access is unchanged. Tuple indexing, unpacking, `_fields`, `_asdict()`, and
`_replace()` are removed. Use the standard dataclass helpers when needed:

```python
from dataclasses import asdict, replace

values = asdict(snapshot)
updated = replace(snapshot, available=False)
```

`asdict()` is a Python mapping, not a JSON serialization contract: enum and
`timedelta` values may need conversion for diagnostics or storage.

`hvac_modes`, `fan_modes`, and `alarm_codes` are tuples. `alarm_codes` is an empty
tuple when no alarms are reported. `hvac_mode` and `hvac_action` are annotated
with their enum types. Both enums now use `StrEnum`: string conversion and
formatting return the value, so `str(HVACMode.HEAT)` and `f"{HVACMode.HEAT}"`
produce `"heat"` instead of `"HVACMode.HEAT"`. String equality and value-based
construction remain supported. `BypassMode` and `BypassType` are now `IntEnum`
classes. Snapshot fields include Python 3.14 `field(doc=...)` documentation
for their meaning, units, and unavailable values.

`timer_countdown` is a `datetime.timedelta` rather than an `HH:MM:SS` string.
Use `snapshot.timer_countdown.total_seconds()` for a Home Assistant duration
sensor; handle `None` for an unknown value. A zero duration is a valid value.

## Home Assistant identity and features

The IP-derived `unique_id` is removed. The protocol mapping implemented by this
library does not expose a stable hardware identifier. The integration must own
identity: use a device-provided identifier if available, or a config-entry ID
as a last resort. Do not rebuild entity IDs from the current host address.

For existing installations, explicitly migrate the entity/device registry
identifiers while preserving the registered entities and their user settings;
simply assigning new identifiers can create duplicates. Inspect the component's
existing identifier format before implementing that migration.

`ClimateEntityFeature` and `snapshot.supported_features` are removed. Set the
feature flags in the component using Home Assistant's own `ClimateEntityFeature`.
Other descriptive fields, including manufacturer, model, temperature unit, and
supported modes, remain available.

## Optional percentage readings

`bypass_position`, `supply_fan_speed_percent`, and `extract_fan_speed_percent`
now report `None` for values outside 0–100, including the `65535` observed on
physical hardware. Valid readings remain usable even if another optional
percentage is unknown; the device is still available after a successful poll.

## Errors and inputs

Catch `S21Error` for all library device/communication failures, or its subclasses:

- `UnsupportedDeviceException`: the device type is not S21.
- `ModbusCommunicationException`: connection failure, timeout, pymodbus failure,
  error response, or invalid response data.

`OSError`, `TimeoutError`, and pymodbus transport exceptions are now wrapped in
`ModbusCommunicationException`, with the original error in `__cause__`.
Unexpected programming errors are not wrapped. Task cancellation propagates as
`asyncio.CancelledError`; cleanup still runs and cached state becomes unavailable.

Invalid control arguments raise `ValueError` before connecting. An unknown HVAC
mode no longer silently selects AUTO. Booleans are rejected for numeric controls.
An unknown operating mode in a powered-on device response is a communication
error rather than an assumed AUTO state.

## Client ownership

`client.device` remains readable but is now a read-only property. Before the
first successful poll it is `None`. Successful writes do not optimistically
change the snapshot: poll to read confirmed state. A failed operation replaces
the cached snapshot with an unavailable one; previously returned snapshots remain
unchanged.

The underlying pymodbus client and lock are private implementation details;
`client.client` and `client.lock` are removed. All public control methods are
still async. No persistent connection or explicit public `close()` is needed:
each operation connects, performs its work, and closes under one shared lock.

Optional keyword arguments `timeout` (seconds per Modbus request) and `retries`
(request retry count) are now available. Defaults remain 3 seconds and 3 retries.
They are not a total poll deadline. Callers can bound an entire operation with
`asyncio.timeout()`, including time waiting for the client lock:

```python
try:
    async with asyncio.timeout(10):
        snapshot = await client.poll()
except TimeoutError:
    # The caller's total deadline expired; handle outside the timeout block.
    ...
except S21Error:
    # A device/transport failure occurred, including per-request timeouts.
    ...
```

An expired outer deadline cancels the operation and raises `TimeoutError` to
the caller. An operation that acquired the lock closes its connection and marks
cached state unavailable; one cancelled while waiting for the lock has not
started I/O and leaves the active operation and cached state untouched.

## Development and releases

Metadata now lives in `pyproject.toml`; `setup.py` is removed. Install with
`pip install -e '.[dev]'` or `pip install -r requirements.txt` (the latter pins
pymodbus to the minimum supported version).

Pushes and pull requests run validation only. To publish, merge the version bump
and changes, then publish a GitHub release with the matching tag, such as
`v5.0.0`. A bare tag push or a draft release does not publish to PyPI. The release
workflow reruns tests, typing, lint, coverage, and packaging checks, verifies the
tag against the built package version, and uploads those same validated artifacts
using the existing `pypi` environment and Trusted Publisher configuration.
Published prereleases also trigger publishing; use a matching PEP 440 prerelease
version/tag (for example `5.1.0rc1` / `v5.1.0rc1`).
