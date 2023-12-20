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
