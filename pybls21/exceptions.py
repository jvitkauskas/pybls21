"""Public exceptions raised by the S21 client."""


class S21Error(Exception):
    """Base class for device and communication errors (not invalid arguments)."""


class UnsupportedDeviceException(S21Error):
    """The endpoint does not identify itself as a supported S21 device."""


class ModbusCommunicationException(S21Error):
    """Connection, timeout, Modbus error, or invalid device response.

    Transport exceptions are retained as ``__cause__`` when wrapped.
    """
