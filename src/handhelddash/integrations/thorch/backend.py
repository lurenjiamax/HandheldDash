"""Thorch command adapter behind the hardware service contract."""
import json
import subprocess
from pathlib import Path
from handhelddash.services.contracts import HardwareBackend


class ThorchHardwareBackend(HardwareBackend):
    def __init__(self,device):
        self.device=device

    @property
    def available(self):
        return bool(self.device.hardware_control and Path(self.device.hardware_control).is_file())

    @staticmethod
    def run(command,*args,timeout=25):
        result=subprocess.run([command,*map(str,args)],capture_output=True,text=True,timeout=timeout)
        if result.returncode: raise RuntimeError(result.stderr.strip() or result.stdout.strip())
        return result.stdout.strip()

    def status(self):
        return json.loads(self.run(self.device.hardware_control,'status-json'))

    def set(self,operation,*values):
        self.run(self.device.hardware_control,'set',operation,*values)

    def fan_status(self):
        return json.loads(self.run(self.device.fan_control,'status-json',timeout=5)) if self.device.fan_control else {}

