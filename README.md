# Blauberg S21 Python TCP API
An api allowing control of AC state (temperature, on/off, speed) of an Blauberg S21 device locally over TCP.

## Usage
To initialize:
`client = S21Client("192.168.0.125")`

To load:
`client.poll_status()`

The following functions are available:
`turn_on`
`turn_off`
`set_hvac_mode`
`set_fan_mode`
`set_manual_fan_speed_percent`
`set_temperature`
