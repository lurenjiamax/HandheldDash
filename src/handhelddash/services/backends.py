"""Generic read-only hardware backend."""
from .contracts import HardwareBackend


class GenericHardwareBackend(HardwareBackend):
    available = False

    def status(self):
        return {'rgb_mode':'off','rgb_brightness':0,'rgb_static':[0,0,0]}

    def set(self,operation,*values):
        raise ValueError('No hardware backend for the selected device')

    def fan_status(self):
        return {}
