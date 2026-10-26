# SPDX-License-Identifier: LGPL-3.0-or-later
"""Per-device WirePlumber mixer preferences, run outside the UI process."""
import argparse
import fcntl
import json
import os
import re
from pathlib import Path
import subprocess
import time
import dbus

MARKER = '# Managed by HandheldDash: per-device volume control\n'
PROFILES = ['hfp_hf', 'hsp_hs', 'a2dp_sink', 'hfp_ag', 'hsp_ag', 'a2dp_source']


def run(*args: str, timeout: float = 10) -> str:
    return subprocess.check_output(args, text=True, stderr=subprocess.PIPE, timeout=timeout)


def config_path() -> Path:
    return Path(os.environ.get('XDG_CONFIG_HOME', Path.home()/'.config'))/'wireplumber/wireplumber.conf.d/99-handhelddash-volume.conf'


def load_rules(path: Path) -> dict:
    if not path.exists():
        return {}
    text = path.read_text()
    if not text.startswith(MARKER):
        raise ValueError('Volume configuration is not managed by HandheldDash')
    data = json.loads(text[len(MARKER):])
    if not isinstance(data, dict) or any(key not in ('monitor.bluez.rules', 'monitor.alsa.rules') for key in data):
        raise ValueError('Unrecognized volume configuration')
    return data


def devices(timeout: float = 10) -> list:
    return json.loads(run('pw-dump', timeout=timeout))


def selected() -> tuple:
    run('systemctl', '--user', 'is-active', '--quiet', 'wireplumber.service')
    version = re.search(r'(\d+)\.(\d+)\.', run('wireplumber', '--version'))
    if not version or tuple(map(int, version.groups())) < (0, 5):
        raise ValueError('Volume mode requires WirePlumber 0.5 or newer')
    first = run('wpctl', 'inspect', '@DEFAULT_AUDIO_SINK@').splitlines()[0]
    sink_id = int(first.split(',')[0].split()[1])
    objects = devices()
    sink = next(obj for obj in objects if obj['id'] == sink_id)
    props = sink['info']['props']
    device = next(obj for obj in objects if obj['id'] == int(props.get('device.id', -1)))
    device_props = device['info']['props']
    backend = device_props.get('device.api')
    name = device_props.get('device.name')
    if backend not in ('bluez5', 'alsa') or not name:
        raise ValueError('Volume mode requires an ALSA or Bluetooth output managed by WirePlumber')
    return sink, backend, name


def rule_group(backend: str) -> str:
    return 'monitor.bluez.rules' if backend == 'bluez5' else 'monitor.alsa.rules'


def mode_for(data: dict, backend: str, name: str) -> str:
    for rule in data.get(rule_group(backend), []):
        if rule.get('matches') == [{'device.name': name}]:
            props = rule['actions']['update-props']
            software = props.get('bluez5.hw-volume') == [] if backend == 'bluez5' else props.get('api.alsa.soft-mixer') is True
            return 'software' if software else 'hardware'
    return 'default'


def status() -> dict:
    sink, backend, name = selected()
    props = sink['info']['props']
    return {'device': name, 'backend': backend, 'description': props.get('node.description', name),
            'mode': mode_for(load_rules(config_path()), backend, name)}


def write_rules(path: Path, data: dict) -> None:
    if not any(data.values()):
        path.unlink(missing_ok=True)
        return
    stage = path.with_suffix('.new')
    with stage.open('w') as stream:
        stream.write(MARKER + json.dumps(data, indent=2) + '\n')
        stream.flush()
        os.fsync(stream.fileno())
    stage.replace(path)


def bluetooth_device(name: str):
    bus = dbus.SystemBus()
    manager = dbus.Interface(bus.get_object('org.bluez', '/'), 'org.freedesktop.DBus.ObjectManager')
    for path, interfaces in manager.GetManagedObjects(timeout=5).items():
        props = interfaces.get('org.bluez.Device1', {})
        address = str(props.get('Address', '')).replace(':', '_')
        if address and name == 'bluez_card.' + address:
            return dbus.Interface(bus.get_object('org.bluez', path), 'org.bluez.Device1')
    raise RuntimeError('The selected Bluetooth audio device is no longer available')


def restore_output(name: str, node_name: str, volume: str, muted: bool, bluetooth=None) -> None:
    deadline = time.monotonic() + 30
    reconnect_at = time.monotonic() + 1
    attempts = 0
    last_error = ''
    while time.monotonic() < deadline:
        try:
            objects = devices(timeout=2)
        except (ValueError, subprocess.SubprocessError) as error:
            last_error = str(error)
            objects = []
        ids = {obj['id'] for obj in objects if obj.get('info', {}).get('props', {}).get('device.name') == name}
        sinks = [obj for obj in objects if obj.get('info', {}).get('props', {}).get('media.class') == 'Audio/Sink'
                 and int(obj['info']['props'].get('device.id', -1)) in ids]
        if sinks:
            target = next((obj for obj in sinks if obj['info']['props'].get('node.name') == node_name), sinks[0])
            target_id = str(target['id'])
            # Never turn the physical mixer up to 100% to enable software volume.
            try:
                run('wpctl', 'set-volume', target_id, volume, timeout=2)
                run('wpctl', 'set-mute', target_id, '1' if muted else '0', timeout=2)
                run('wpctl', 'set-default', target_id, timeout=2)
                return
            except subprocess.SubprocessError as error:
                last_error = str(error)
        elif bluetooth is not None and attempts < 3 and time.monotonic() >= reconnect_at:
            # WirePlumber registering new endpoints does not make BlueZ reconnect
            # every headset. Reconnect only the output selected before the restart.
            attempts += 1
            try:
                bluetooth.Connect(timeout=6)
            except dbus.DBusException as error:
                if error.get_dbus_name() not in ('org.bluez.Error.AlreadyConnected', 'org.bluez.Error.InProgress'):
                    last_error = str(error)
            reconnect_at = time.monotonic() + 3
        time.sleep(.25)
    raise RuntimeError('Audio device did not reconnect' + (': ' + last_error if last_error else ''))


def apply(mode: str, expected: str) -> dict:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with (path.parent/'handhelddash-volume.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        sink, backend, name = selected()
        if name != expected:
            raise ValueError('Default audio device changed; choose the volume mode again')
        original = load_rules(path)
        data = json.loads(json.dumps(original))
        if mode_for(data, backend, name) == mode:
            return status()
        group = rule_group(backend)
        data[group] = [rule for rule in data.get(group, []) if rule.get('matches') != [{'device.name': name}]]
        if mode != 'default':
            props = {'bluez5.hw-volume': [] if mode == 'software' else PROFILES} if backend == 'bluez5' else {'api.alsa.soft-mixer': mode == 'software'}
            data[group].append({'matches': [{'device.name': name}], 'actions': {'update-props': props}})
        output = run('wpctl', 'get-volume', str(sink['id'])).split()
        volume, muted = output[1], '[MUTED]' in output
        node_name = sink['info']['props']['node.name']
        bluetooth = bluetooth_device(name) if backend == 'bluez5' else None
        write_rules(path, data)
        try:
            run('systemctl', '--user', 'restart', 'wireplumber.service')
            restore_output(name, node_name, volume, muted, bluetooth)
        except Exception as error:
            write_rules(path, original)
            try:
                run('systemctl', '--user', 'restart', 'wireplumber.service')
                restore_output(name, node_name, volume, muted, bluetooth)
            except Exception as recovery:
                raise RuntimeError(f'{error}. Previous mode restored, but audio recovery failed: {recovery}') from error
            raise RuntimeError(f'{error}. Previous mode and audio output restored') from error
        return status()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('operation', choices=('status', 'set'))
    parser.add_argument('mode', nargs='?', choices=('default', 'software', 'hardware'))
    parser.add_argument('--device')
    args = parser.parse_args()
    try:
        if args.operation == 'set' and (not args.mode or not args.device):
            parser.error('set requires a mode and --device')
        result = apply(args.mode, args.device) if args.operation == 'set' else status()
        print(json.dumps(result))
    except (OSError, ValueError, RuntimeError, StopIteration, subprocess.SubprocessError, dbus.DBusException) as error:
        detail = error.stderr if isinstance(error, subprocess.CalledProcessError) else str(error)
        print(json.dumps({'error': detail or 'No supported default audio output'}))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
