"""Device metadata and conservative discovery; no hardware writes on import."""
import json
import os
from dataclasses import dataclass, field
from pathlib import Path


def read_text(path: Path, default: str = '') -> str:
    try:
        return path.read_text().strip().strip('\0')
    except OSError:
        return default


def cpu_set(value: str) -> set:
    result=set()
    for part in value.split(','):
        if not part: continue
        ends=list(map(int,part.split('-')))
        result.update(range(ends[0],ends[-1]+1))
    return result


def format_cpu_set(values) -> str:
    groups=[]
    for cpu in sorted(set(values)):
        if groups and cpu==groups[-1][-1]+1: groups[-1].append(cpu)
        else: groups.append([cpu])
    return ','.join(str(group[0]) if len(group)==1 else f'{group[0]}-{group[-1]}' for group in groups)


@dataclass
class Device:
    identity: str = 'generic'
    backend: str = 'generic'
    model: str = ''
    displays: dict = field(default_factory=dict)
    backlights: dict = field(default_factory=dict)
    gpu: str = ''
    gpu_utilization: str = ''
    battery: str = ''
    charger: str = ''
    hardware_control: str = ''
    hardware_config: str = ''
    fan_control: str = ''
    fan_service: str = ''
    composite_match: str = ''
    profile_prefix: str = 'HandheldDash'
    performance_modes: dict = field(default_factory=dict)
    irq_cpu_sets: dict = field(default_factory=dict)
    hotkey_devices: list = field(default_factory=list)
    led_patterns: dict = field(default_factory=dict)
    touchscreen: str = ''
    touchscreens: dict = field(default_factory=dict)
    touchscreen_reset: str = ''
    fan_name: str = ''
    fan_reset_workaround: bool = False

    @classmethod
    def discover(cls, root: Path = Path('/')):
        model = read_text(root/'proc/device-tree/model') or read_text(root/'sys/devices/virtual/dmi/id/product_name')
        profile_dir = Path(__file__).parent/'profiles'
        config = {}
        for path in sorted(profile_dir.glob('*.json')):
            candidate = json.loads(path.read_text())
            if model.casefold() in [name.casefold() for name in candidate.get('models',[])]:
                config = {key:value for key,value in candidate.items() if key != 'models'}
                break
        # Explicit operator overrides, never inferred from an installed vendor CLI.
        override = Path(os.environ.get('HANDHELDDASH_DEVICE_CONFIG','/etc/handhelddash/device.json'))
        if override.is_file():
            config.update({key:value for key,value in json.loads(override.read_text()).items() if key!='models'})
        unknown = set(config)-set(cls.__dataclass_fields__)
        if unknown: raise ValueError('Unknown device configuration fields: '+', '.join(sorted(unknown)))
        config['model'] = model
        device = cls(**config)
        lights = sorted((root/'sys/class/backlight').glob('*'))
        # A single discovered backlight is unambiguous; multi-panel ordering isn't.
        if not device.backlights and len(lights)==1:
            device.backlights = {'bottom':lights[0].name}
        if not device.gpu:
            nodes = [p for p in (root/'sys/class/devfreq').glob('*') if (p/'cur_freq').is_file() and ('gpu' in p.name.casefold() or 'gpu' in read_text(p/'name').casefold())]
            if len(nodes)==1: device.gpu = '/sys/class/devfreq/'+nodes[0].name
        supplies = sorted((root/'sys/class/power_supply').glob('*'))
        if not device.battery:
            batteries = [p for p in supplies if read_text(p/'type')=='Battery']
            if len(batteries)==1: device.battery = '/sys/class/power_supply/'+batteries[0].name
        if not device.charger:
            chargers = [p for p in supplies if read_text(p/'type') in ('USB','USB_C','Mains')]
            if len(chargers)==1: device.charger = '/sys/class/power_supply/'+chargers[0].name
        return device

    def gpu_path(self, name: str) -> str:
        return str(Path(self.gpu)/name) if self.gpu else '/nonexistent/handhelddash/gpu/'+name

    def screen_name(self, role: str, screens=()) -> str:
        name = self.displays.get(role,'')
        available = [screen.name() for screen in screens]
        if name and (not available or name in available): return name
        # Generic single-screen devices share one display; never guess dual roles.
        return available[0] if len(available)==1 else ''

    def capabilities(self) -> dict:
        return {'id':self.identity,'model':self.model,'displays':self.displays,
                'backlights':self.backlights,'hardware_control':bool(self.hardware_control and Path(self.hardware_control).is_file()),
                'touchscreen_reset':bool(self.touchscreen_reset),'gpu_frequency':bool(self.gpu)}


DEVICE = Device.discover()
