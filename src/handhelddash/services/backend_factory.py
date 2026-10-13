"""Select the configured hardware integration."""
from .backends import GenericHardwareBackend
from .contracts import HardwareBackend
from handhelddash.integrations.thorch.backend import ThorchHardwareBackend


def hardware_backend(device) -> HardwareBackend:
    if device.backend=='thorch':
        backend=ThorchHardwareBackend(device)
        if backend.available: return backend
    return GenericHardwareBackend()
