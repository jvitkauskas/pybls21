# AGENTS.md

This file defines how coding agents should work in this repository.

## Project Scope

`pybls21` is an async Python client for controlling a Blauberg S21 ventilation/HVAC device over Modbus TCP.

Core capabilities in this project:
- Poll device state and map Modbus registers/coils to a `ClimateDevice` model.
- Control power (`turn_on`, `turn_off`).
- Set HVAC mode (`OFF`, `FAN_ONLY`, `HEAT`, `COOL`, `AUTO`).
- Set fan mode and manual fan speed.
- Set target temperature.
- Reset filter timer.

## Repository Map

- `pybls21/pybls21/client.py`: Main async client implementation (`S21Client`).
- `pybls21/pybls21/constants.py`: Modbus register/coil constants.
- `pybls21/pybls21/models.py`: Data models and HVAC enums.
- `pybls21/pybls21/exceptions.py`: Custom exceptions.
- `pybls21/tests/test_client.py`: Async unit tests with a local Modbus test server.
- `pybls21/demo.py`: Usage example.
- `pybls21/setup.py`: Packaging metadata.

## Development Setup

Use Python 3.10+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

## Test Commands

Run all tests:

```bash
python -m unittest -v
```

Run one test module:

```bash
python -m unittest -v tests.test_client
```

## Editing Rules

- Keep all public client methods async.
- Preserve compatibility with `pymodbus>=3.11.2,<4.0`.
- When changing Modbus mappings, update tests in `pybls21/tests/test_client.py` in the same change.
- Keep API behavior stable unless explicitly requested; this package may be used by Home Assistant integrations.

## Verification Checklist

Before finishing a change:
- Run tests.
- Confirm new or changed behavior is covered by unit tests.
- Ensure import paths and package metadata still work (`pip install -e .`).

