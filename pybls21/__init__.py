"""Public API for the asynchronous Blauberg S21 client."""

from .client import S21Client
from .discovery import DiscoveredDevice, discover
from .exceptions import (
    DiscoveryError,
    ModbusCommunicationException,
    S21Error,
    UnsupportedDeviceException,
)
from .models import BypassMode, BypassType, ClimateDevice, HVACAction, HVACMode

__all__ = [
    "S21Client",
    "discover",
    "DiscoveredDevice",
    "DiscoveryError",
    "S21Error",
    "ModbusCommunicationException",
    "UnsupportedDeviceException",
    "BypassMode",
    "BypassType",
    "ClimateDevice",
    "HVACAction",
    "HVACMode",
]
