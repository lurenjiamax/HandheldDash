#!/usr/bin/python
# SPDX-License-Identifier: LGPL-3.0-or-later
# Copyright (c) 2026 lurenjiamax
"""AYN Thor hardware service. Fixed operations only; never executes client commands."""
import json
import logging
import os
import re
import struct
import sys
import threading
from pathlib import Path
import subprocess
import time

import dbus
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib
from evdev import InputDevice, UInput, ecodes, list_devices
import yaml

NAME = 'org.aynthor.Hardware1'
PATH = '/org/aynthor/Hardware1'
IP = 'org.shadowblip.InputPlumber'
CI = 'org.shadowblip.Input.CompositeDevice'
FF = 'org.shadowblip.Output.ForceFeedback'
sys.path.insert(0, '/usr/lib/aynthor')
from lpunpack import LpUnpack

STATE = Path('/var/lib/aynthor/preferences.json')
CTL = '/usr/bin/thorch-hardwarectl'


def run(*args, timeout=25):
    p = subprocess.run(args, text=True, capture_output=True, timeout=timeout)
    if p.returncode:
        raise RuntimeError(p.stderr.strip() or p.stdout.strip() or f'{args[0]} failed')
    return p.stdout.strip()


def read(path, default=None):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return default


def number(path, scale=1):
    try:
        return float(read(path)) / scale
    except (TypeError, ValueError):
        return None


def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    stage = path.with_suffix('.new')
    with stage.open('w') as f:
        json.dump(data, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    stage.replace(path)


class Hardware(dbus.service.Object):
    def __init__(self, bus):
        self.bus = bus
        self.name = dbus.service.BusName(NAME, bus, do_not_queue=True)
        super().__init__(self.name, PATH)
        self.prefs = {'performance': 'standard', 'smart': False, 'joystick': 'gamepad', 'vibration': True}
        if STATE.exists():
            self.prefs.update(json.loads(STATE.read_text()))
        self.inputs = {}
        self.stick_axes = {}
        self.stick_sent = {}
        self.feedback_busy = False
        self.keyboard = UInput({ecodes.EV_KEY: [ecodes.KEY_ESC, ecodes.KEY_LEFTSHIFT, ecodes.KEY_F4]}, name='AYN Thor Action Keyboard')
        self.cpu_previous = (0, 0)
        self.tach_previous = None
        self.tach_rpm = None
        self.mutation_lock = threading.Lock()
        self.cached_status = None
        self.led_lock = threading.Lock()
        self.led_last_frame = 0
        self.led_dirs = {side: list(Path('/sys/class/leds').glob('rgb:'+side+'[0-9]*')) for side in ('l','r')}
        GLib.timeout_add_seconds(1, self.lighting_watchdog)
        self.last_button = {}
        self.ip_ready = False
        self.initialize_fan()
        bus.add_signal_receiver(self.resume, signal_name='PrepareForSleep', dbus_interface='org.freedesktop.login1.Manager',bus_name='org.freedesktop.login1')
        bus.add_signal_receiver(self.ip_event, signal_name='InputEvent', dbus_interface='org.shadowblip.Input.DBusDevice', bus_name=IP)
        GLib.timeout_add_seconds(2, self.discover_inputs)
        self.discover_inputs()

    def initialize_fan(self):
        for hwmon in Path('/sys/class/hwmon').glob('*'):
            if read(hwmon/'name') != 'pwmfan': continue
            enable = hwmon/'pwm1_enable'
            mode = read(enable)
            if mode not in ('1','2','3'): continue
            # ponytail: cold-boot PWM state can be stale on thorch16; remove after the BSP driver is fixed.
            enable.write_text('2\n')
            enable.write_text(mode+'\n')

    def resume(self,sleeping):
        if not sleeping: self.initialize_fan()

    def write_lighting(self, colors):
        for side,color in zip(('l','r'),colors):
            channels = dict(zip(('red','green','blue'),color))
            for node in self.led_dirs[side]:
                (node/'multi_intensity').write_text(' '.join(str(channels.get(c,0)) for c in (node/'multi_index').read_text().split())+'\n')
                (node/'brightness').write_text((node/'max_brightness').read_text())

    @dbus.service.method(NAME, in_signature='iiiiii', out_signature='', sender_keyword='sender')
    def LightingFrame(self, lr, lg, lb, rr, rg, rb, sender=None):
        if int(self.bus.get_unix_user(sender)) not in self.sessions():
            raise dbus.exceptions.DBusException('An active local session is required', name=NAME+'.AccessDenied')
        colors = [list(map(int,(lr,lg,lb))),list(map(int,(rr,rg,rb)))]
        if any(not 0 <= v <= 255 for color in colors for v in color):
            raise dbus.exceptions.DBusException('RGB values must be 0..255', name=NAME+'.Failed')
        with self.led_lock:
            if self.prefs.get('lighting_mode') != 'audio': return
            self.write_lighting(colors)
            self.led_last_frame = time.monotonic()

    def lighting_watchdog(self):
        with self.led_lock:
            if self.prefs.get('lighting_mode') == 'audio' and time.monotonic()-self.led_last_frame > 2:
                try: self.write_lighting([[0,0,0],[0,0,0]])
                except OSError: logging.exception('Could not clear audio lighting')
        return True

    def sessions(self):
        obj = self.bus.get_object('org.freedesktop.login1', '/org/freedesktop/login1')
        result = []
        for _, uid, _, seat, path in obj.ListSessions(dbus_interface='org.freedesktop.login1.Manager'):
            if seat:
                p = self.bus.get_object('org.freedesktop.login1', path)
                props = p.GetAll('org.freedesktop.login1.Session', dbus_interface='org.freedesktop.DBus.Properties')
                if props['Active'] and not props['Remote']:
                    result.append(int(uid))
        return result

    def authorize(self, sender):
        uid = int(self.bus.get_unix_user(sender))
        if uid != 0 and uid not in self.sessions():
            raise dbus.exceptions.DBusException('An active local session is required', name=NAME + '.AccessDenied')
        return uid

    def composite(self):
        manager = self.bus.get_object(IP, '/org/shadowblip/InputPlumber')
        objects = manager.GetManagedObjects(dbus_interface='org.freedesktop.DBus.ObjectManager')
        for path, interfaces in objects.items():
            if CI in interfaces and any('event3' in str(p) for p in interfaces[CI].get('SourceDevicePaths', [])):
                return self.bus.get_object(IP, path)
            if CI in interfaces and 'AYN' in str(interfaces[CI].get('Name', '')):
                return self.bus.get_object(IP, path)
        raise RuntimeError('AYN InputPlumber controller is unavailable')

    def configure_input(self):
        obj = self.composite()
        base = '/usr/share/inputplumber/profiles/' + ('mouse_keyboard_wasd.yaml' if self.prefs['joystick'] == 'mouse' else 'default.yaml')
        profile = yaml.safe_load(Path(base).read_text())
        profile['name'] = 'AYN Thor ' + self.prefs['joystick']
        profile['mapping'] = [m for m in profile.get('mapping', []) if m.get('source_event', {}).get('gamepad', {}).get('button') not in ('Guide', 'QuickAccess2')]
        for button, event in [('Guide', 'ui_guide'), ('QuickAccess2', 'ui_back'), ('LeftStick','ui_left_stick'), ('RightStick','ui_right_stick')]:
            profile['mapping'].append({'name': button, 'source_event': {'gamepad': {'button': button}}, 'target_events': [{'dbus': event}]})
            if button in ('LeftStick','RightStick'): profile['mapping'][-1]['target_events'].append({'gamepad':{'button':button}})
        obj.LoadProfileFromYaml(yaml.safe_dump(profile), dbus_interface=CI)
        obj.Set(FF, 'Enabled', dbus.Boolean(self.prefs['vibration'],variant_level=1), dbus_interface='org.freedesktop.DBus.Properties')
        self.ip_ready = True

    def ip_event(self, event, value):
        if value == 1 and str(event) in ('ui_left_stick','ui_right_stick'):
            self.emit_button('lighting-left' if str(event) == 'ui_left_stick' else 'lighting-right'); return
        if value == 1 and str(event) in ('ui_guide', 'ui_back'):
            self.emit_button('home' if str(event) == 'ui_guide' else 'back')

    def emit_button(self, action):
        now = time.monotonic()
        if now - self.last_button.get(action, 0) < .2:
            return
        self.last_button[action] = now
        for uid in self.sessions():
            self.Button(uid, action)

    @dbus.service.signal(NAME, signature='us')
    def Button(self, uid, action):
        pass

    @dbus.service.signal(NAME, signature='usdd')
    def Stick(self,uid,side,x,y):
        pass

    @dbus.service.method(NAME,in_signature='',out_signature='',sender_keyword='sender')
    def Feedback(self,sender=None):
        self.authorize(sender)
        if self.feedback_busy or not self.prefs['vibration']: return
        self.feedback_busy = True
        def pulse():
            try:
                obj=self.composite(); obj.Rumble(dbus.Double(.3),dbus_interface=FF)
                time.sleep(.035); obj.Stop(dbus_interface=FF)
            except Exception: logging.exception('Color dial feedback failed')
            finally: self.feedback_busy=False
        threading.Thread(target=pulse,daemon=True).start()

    def input_event(self, fd, condition, path):
        dev = self.inputs[path][0]
        try:
            for event in dev.read():
                if dev.name == 'Microsoft Xbox Series S|X Controller':
                    axes=self.stick_axes.setdefault(path,{ecodes.ABS_X:0.,ecodes.ABS_Y:0.,ecodes.ABS_RX:0.,ecodes.ABS_RY:0.})
                    if event.type == ecodes.EV_ABS and event.code in axes:
                        info=dev.absinfo(event.code); center=(info.max+info.min)/2
                        axes[event.code]=max(-1.,min(1.,(event.value-center)/max(1,(info.max-info.min)/2)))
                    if event.type == ecodes.EV_SYN and event.code == ecodes.SYN_REPORT:
                        now=time.monotonic()
                        if now-self.stick_sent.get(path,0) >= .02:
                            self.stick_sent[path]=now
                            for uid in self.sessions():
                                self.Stick(uid,'left',axes[ecodes.ABS_X],axes[ecodes.ABS_Y])
                                self.Stick(uid,'right',axes[ecodes.ABS_RX],axes[ecodes.ABS_RY])
                if dev.name == 'Microsoft Xbox Series S|X Controller' and event.type == ecodes.EV_KEY and event.value == 1 and event.code in (ecodes.BTN_THUMBL,ecodes.BTN_THUMBR):
                    self.emit_button('lighting-left' if event.code==ecodes.BTN_THUMBL else 'lighting-right')
                if event.type == ecodes.EV_KEY and event.code == ecodes.KEY_F24 and event.value == 1:
                    self.emit_button('panel')
        except BlockingIOError:
            pass
        except OSError:
            dev.close()
            self.inputs.pop(path, None)
            return False
        return True

    def discover_inputs(self):
        for path in list_devices():
            if path in self.inputs:
                continue
            try:
                dev = InputDevice(path)
                if dev.name in ('Thorch Hardware Keys','Microsoft Xbox Series S|X Controller'):
                    watch = GLib.io_add_watch(dev.fd, GLib.IO_IN | GLib.IO_HUP, self.input_event, path)
                    self.inputs[path] = (dev, watch)
                else:
                    dev.close()
            except OSError as e:
                logging.warning('Input discovery: %s', e)
        try:
            if not self.ip_ready:
                self.configure_input()
            else:
                profile = self.composite().Get(CI, 'ProfileName', dbus_interface='org.freedesktop.DBus.Properties')
                if str(profile) != 'AYN Thor ' + self.prefs['joystick']:
                    self.configure_input()
        except (dbus.DBusException, RuntimeError, OSError, ValueError) as e:
            self.ip_ready = False
            logging.warning('InputPlumber: %s', e)
        return True

    def logical_partitions(self, super_device):
        reader = LpUnpack(SUPER_IMAGE=super_device)
        try:
            # ponytail: pinned lpunpack has no public metadata API; review this call when updating it.
            metadata = reader._read_metadata()
        finally:
            reader._fd.close()
        limit = int(run('blockdev', '--getsz', super_device))
        result = []
        for p in metadata.partitions:
            if not re.fullmatch(r'(system|system_ext|system_dlkm|vendor|vendor_dlkm|product|odm)(_[ab])?', p.name) or not p.num_extents:
                continue
            table, start = [], 0
            for extent in metadata.extents[p.first_extent_index:p.first_extent_index+p.num_extents]:
                if extent.target_source != 0 or extent.target_type not in (0,1) or extent.num_sectors <= 0:
                    raise ValueError('Unsupported Android super extent')
                if extent.target_type == 0:
                    if extent.target_data + extent.num_sectors > limit:
                        raise ValueError('Android extent exceeds super partition')
                    table.append(f'{start} {extent.num_sectors} linear {super_device} {extent.target_data}')
                else:
                    table.append(f'{start} {extent.num_sectors} zero')
                start += extent.num_sectors
            mapper = '/dev/mapper/aynthor-android-' + p.name
            result.append({'label':p.name,'device':mapper,'filesystem':None,'mountable':True,'mountpoints':[], 'reason':'Android super logical partition; read-only access', 'super_device':super_device,'table':'\n'.join(table),'size':start*512})
        return result

    def android(self):
        blocks = json.loads(run('lsblk','-J','-p','-o','NAME,FSTYPE,PARTLABEL,MOUNTPOINTS'))
        found = []
        for disk in blocks['blockdevices']:
            children = disk.get('children', [])
            if not any(p.get('partlabel') in ('super','userdata') for p in children):
                continue
            for item in children:
                label = item.get('partlabel')
                if label == 'super':
                    try:
                        found.extend(self.logical_partitions(item['name']))
                    except Exception as e:
                        found.append({'label':'super','device':item['name'],'filesystem':None,'mountable':False,'mountpoints':[], 'reason':'Super metadata unreadable: '+str(e)})
                elif label in ('userdata','system','vendor','product','system_a','system_b','vendor_a','vendor_b','product_a','product_b'):
                    fs=item.get('fstype')
                    found.append({'label':label,'device':item['name'],'filesystem':fs,'mountable':fs in ('ext4','f2fs','erofs'),'mountpoints':item.get('mountpoints'), 'reason':'' if fs in ('ext4','f2fs','erofs') else 'No readable filesystem; Android metadata encryption requires unlocked data exported from Android'})
        return found

    def fan_reading(self, hwmon):
        rpm = number(hwmon / 'fan1_input')
        source = 'hwmon'
        for line in Path('/proc/interrupts').read_text().splitlines():
            if not line.rstrip().endswith('pwm-fan'):
                continue
            fields = line.split()[1:]
            counts = []
            for field in fields:
                if not field.isdigit(): break
                counts.append(int(field))
            pulses = sum(counts)
            now = time.monotonic()
            node = hwmon / 'device/of_node/pulses-per-revolution'
            if not node.exists(): break
            ppr = struct.unpack('>I', node.read_bytes()[:4])[0]
            if self.tach_previous and ppr:
                old_time, old_pulses = self.tach_previous
                if now-old_time >= .5:
                    self.tach_rpm = max(0,(pulses-old_pulses)*60/(ppr*(now-old_time)))
                    self.tach_previous = now,pulses
            else:
                self.tach_previous = now,pulses
            if not rpm and self.tach_rpm:
                rpm = self.tach_rpm; source = 'tachometer-interrupts'
            break
        pwm = number(hwmon/'pwm1')
        if not pwm and rpm:
            for cooling in Path('/sys/class/thermal').glob('cooling_device*'):
                if read(cooling/'type') == 'pwm-fan':
                    state = int(read(cooling/'cur_state','0'))
                    raw = (hwmon/'device/of_node/cooling-levels').read_bytes()
                    levels = struct.unpack('>'+'I'*(len(raw)//4), raw)
                    if state < len(levels): pwm = levels[state]
        percent = pwm/2.55 if pwm is not None else None
        actual = re.search(r'pwm-\d+\s+\(pwm-fan.*?actual configuration:\s+(enabled|disabled),\s+(\d+)/(\d+) ns',read('/sys/kernel/debug/pwm',''),re.S)
        if actual:
            percent = 100*int(actual[2])/int(actual[3]) if actual[1] == 'enabled' and int(actual[3]) else 0
        return rpm, percent, source

    def collect_status(self):
        try:
            data = json.loads(run(CTL, 'status-json'))
            data.update(self.prefs)
            data['lighting_mode'] = self.prefs.get('lighting_mode') or data['rgb_mode']
            if data['lighting_mode'] == 'static' and self.prefs.get('lighting_colors'):
                colors = self.prefs['lighting_colors']
                with self.led_lock:
                    self.write_lighting([[round(v*data['rgb_brightness']/255) for v in colors.get(side,data['rgb_static'])] for side in ('left','right')])
            data['lighting_output'] = {}
            for side,key in (('l','left'),('r','right')):
                if not self.led_dirs[side]: continue
                node = self.led_dirs[side][0]
                channels = dict(zip(read(node/'multi_index','').split(),map(int,read(node/'multi_intensity','').split())))
                scale = (number(node/'brightness') or 0)/(number(node/'max_brightness') or 255)
                data['lighting_output'][key] = [round(channels.get(c,0)*scale) for c in ('red','green','blue')]
            battery = '/sys/class/power_supply/battery/'
            data['battery'] = {key: number(battery + key, scale) for key, scale in [('capacity', 1), ('temp', 10), ('current_now', 1e6), ('voltage_now', 1e6)]}
            data['battery']['status'] = read(battery + 'status')
            # power_now is inconsistent on this BSP; derive watts from voltage and current.
            current = data['battery']['current_now']
            voltage = data['battery']['voltage_now']
            data['battery']['watts'] = abs(current * voltage) if current is not None and voltage is not None else None
            data['cpu_mhz'] = max((number(p, 1000) or 0 for p in Path('/sys/devices/system/cpu/cpufreq').glob('policy*/scaling_cur_freq')), default=0)
            data['gpu_mhz'] = number('/sys/class/devfreq/3d00000.gpu/cur_freq', 1e6)
            hwmon = [p for p in Path('/sys/class/hwmon').glob('*') if read(p / 'name') == 'pwmfan']
            data['fan_rpm'], data['fan_percent'], data['fan_rpm_source'] = self.fan_reading(hwmon[0]) if hwmon else (None,None,'unavailable')
            data['cpu_max_mhz'] = max((number(p,1000) or 0 for p in Path('/sys/devices/system/cpu/cpufreq').glob('policy*/cpuinfo_max_freq')),default=3200)
            data['gpu_max_mhz'] = number('/sys/class/devfreq/3d00000.gpu/max_freq',1e6)
            mode_governors = {'quiet':('powersave','powersave'), 'standard':('schedutil','simple_ondemand'), 'performance':('performance','performance')}
            if (data['cpu_governor'],data['gpu_governor']) != mode_governors.get(data['performance']):
                data['performance'] = 'custom'
            data['cpu_governor_actual'] = read('/sys/devices/system/cpu/cpufreq/policy0/scaling_governor')
            data['gpu_governor_actual'] = read('/sys/class/devfreq/3d00000.gpu/governor')
            mem = {line.split(':')[0]: int(line.split()[1]) for line in Path('/proc/meminfo').read_text().splitlines() if len(line.split()) > 1 and line.split()[1].isdigit()}
            data['ram_used_gb'] = (mem['MemTotal'] - mem['MemAvailable']) / 1048576
            data['ram_total_gb'] = mem['MemTotal'] / 1048576
            fields = list(map(int, Path('/proc/stat').read_text().splitlines()[0].split()[1:9]))
            total, idle = sum(fields), fields[3] + fields[4]
            old_total, old_idle = self.cpu_previous
            data['cpu_percent'] = 100 * (1 - (idle-old_idle)/(total-old_total)) if total > old_total else 0
            self.cpu_previous = total, idle
            data['backlight'] = {name: {'value': number('/sys/class/backlight/' + node + '/brightness'), 'max': number('/sys/class/backlight/' + node + '/max_brightness')} for name, node in [('bottom', 'ae94000.dsi.0'), ('top', 'ae96000.dsi.0')]}
            data['bypass_supported'] = False
            data['bypass_reason'] = 'This kernel exposes charge thresholds but no verified bypass charging switch'
            data['fan_control'] = json.loads(run('/usr/bin/thorch-fancontrol','status-json',timeout=5))
            data['input_ready'] = self.ip_ready
            data['layout_supported'] = False
            data['layout_reason'] = 'The rsinput driver has no exposed controller layout switch'
            self.cached_status = json.dumps(data)
            return self.cached_status
        except (RuntimeError, OSError, ValueError) as e:
            raise dbus.exceptions.DBusException(str(e), name=NAME + '.Failed')

    @dbus.service.method(NAME, in_signature='', out_signature='s', async_callbacks=('reply','error'))
    def Status(self, reply=None, error=None):
        if not self.mutation_lock.acquire(blocking=False):
            if self.cached_status is not None: reply(self.cached_status)
            else: error(dbus.exceptions.DBusException('Hardware is busy', name=NAME+'.Busy'))
            return
        def execute():
            try:
                result = self.collect_status()
                GLib.idle_add(lambda: (reply(result),False)[1])
            except Exception as exc:
                GLib.idle_add(lambda e=exc: (error(e),False)[1])
            finally:
                self.mutation_lock.release()
        threading.Thread(target=execute,daemon=True).start()

    def quick_status(self):
        if self.cached_status is None: return self.collect_status()
        data = json.loads(self.cached_status)
        performance = data.get('performance')
        data.update(self.prefs); data['performance'] = performance
        data['backlight'] = {name: {'value': number('/sys/class/backlight/' + node + '/brightness'), 'max': number('/sys/class/backlight/' + node + '/max_brightness')} for name, node in [('bottom','ae94000.dsi.0'),('top','ae96000.dsi.0')]}
        self.cached_status = json.dumps(data)
        return self.cached_status

    @dbus.service.method(NAME, in_signature='', out_signature='s')
    def AndroidPartitions(self):
        return json.dumps(self.android())

    @dbus.service.method(NAME, in_signature='sas', out_signature='s', sender_keyword='sender', async_callbacks=('reply','error'))
    def Set(self, operation, values, sender=None, reply=None, error=None):
        self.authorize(sender)
        if not self.mutation_lock.acquire(blocking=False):
            error(dbus.exceptions.DBusException('Hardware is busy; retry the latest value', name=NAME+'.Busy'))
            return
        def execute():
            try:
                result = self.apply(operation,values)
                GLib.idle_add(lambda: (reply(result),False)[1])
            except Exception as exc:
                GLib.idle_add(lambda e=exc: (error(e),False)[1])
            finally:
                self.mutation_lock.release()
        threading.Thread(target=execute,daemon=True).start()

    def save_fan_curve(self, values):
        if len(values) != 14: raise ValueError('A custom fan curve requires seven temperatures and seven PWM values')
        numbers = list(map(int,values)); temps = numbers[:7]; speeds = numbers[7:]
        if not all(20000 <= t <= 95000 for t in temps) or any(a >= b for a,b in zip(temps,temps[1:])):
            raise ValueError('Fan temperatures must strictly increase within 20..95 °C')
        if not all(0 <= s <= 255 for s in speeds) or any(a > b for a,b in zip(speeds,speeds[1:])) or speeds[-1] != 255:
            raise ValueError('Fan PWM must increase within 0..255 and end at 255')
        config = Path('/etc/thorch/hardware.conf'); original = config.read_text()
        changes = dict(zip(['THORCH_FAN_T'+str(i) for i in range(1,7)]+['THORCH_FAN_MAX_TEMP']+['THORCH_FAN_CUSTOM_SPEED'+str(i) for i in range(1,7)]+['THORCH_FAN_CUSTOM_MAX_SPEED'],numbers))
        changes['THORCH_FAN_PROFILE'] = 'custom'
        text = original
        for key,value in changes.items():
            line = f'{key}={value}'
            if re.search(r'^'+key+r'=.*$',text,re.M): text = re.sub(r'^'+key+r'=.*$',line,text,flags=re.M)
            else: text += '\n'+line+'\n'
        stage = config.with_suffix('.new'); stage.write_text(text); stage.chmod(config.stat().st_mode & 0o777); stage.replace(config)
        try:
            run('systemctl','reset-failed','thorch-fancontrol.service')
            run('systemctl','start','thorch-fancontrol.service')
            run('systemctl','is-active','--quiet','thorch-fancontrol.service')
        except Exception:
            stage.write_text(original); stage.chmod(config.stat().st_mode & 0o777); stage.replace(config)
            run('systemctl','reset-failed','thorch-fancontrol.service')
            run('systemctl','start','thorch-fancontrol.service')
            raise

    def apply(self, operation, values):
        operation, values = str(operation), list(map(str, values))
        arities = {'scheduler': 1, 'cpu-boost': 1, 'cpu-governor': 1, 'gpu-governor': 1, 'governors': 2, 'fan-profile': 1, 'fan-sensor-mode': 1, 'fan-state': 2, 'rgb-mode': 1, 'rgb-brightness': 1, 'rgb-color': 3, 'rgb-state': 5}
        try:
            if operation == 'lighting-color' and len(values) == 4 and values[0] in ('left','right'):
                color = list(map(int,values[1:]))
                if any(not 0 <= v <= 255 for v in color): raise ValueError('RGB values must be 0..255')
                self.prefs.setdefault('lighting_colors',{})[values[0]] = color
            elif operation == 'lighting-mode' and values in (['audio'],['off'],['battery'],['static']):
                with self.led_lock:
                    self.prefs['lighting_mode'] = None
                    run(CTL,'set','rgb-mode','off' if values == ['audio'] else values[0])
                    self.prefs['lighting_mode'] = 'audio' if values == ['audio'] else None
                    self.led_last_frame = time.monotonic()
            elif operation == 'fan-curve':
                self.save_fan_curve(values)
            elif operation in arities and len(values) == arities[operation]:
                if any(len(v) > 32 for v in values):
                    raise ValueError('Value too long')
                run(CTL, 'set', operation, *values)
                if operation in ('rgb-mode','rgb-state'): self.prefs['lighting_mode'] = None
                if operation in ('cpu-governor','gpu-governor','governors'):
                    self.prefs['smart'] = False
            elif operation == 'performance' and len(values) == 1:
                modes = {'quiet': ('powersave', 'powersave', 'quiet', 'off'), 'standard': ('schedutil', 'simple_ondemand', 'moderate', 'on'), 'performance': ('performance', 'performance', 'aggressive', 'on')}
                cpu, gpu, fan, boost = modes[values[0]]
                run(CTL, 'set', 'governors', cpu, gpu)
                run(CTL, 'set', 'fan-profile', fan)
                run(CTL, 'set', 'cpu-boost', boost)
                self.prefs['performance'] = values[0]
                self.prefs['smart'] = False
            elif operation == 'smart' and values in (['on'], ['off']):
                if values == ['on']:
                    run(CTL, 'set', 'governors', 'schedutil', 'simple_ondemand')
                    run(CTL, 'set', 'fan-profile', 'moderate')
                self.prefs['smart'] = values == ['on']
                if values == ['on']:
                    self.prefs['performance'] = 'standard'
            elif operation == 'joystick' and values in (['gamepad'], ['mouse']):
                previous = self.prefs['joystick']
                self.prefs['joystick'] = values[0]
                try:
                    self.configure_input()
                except Exception:
                    self.prefs['joystick'] = previous
                    raise
            elif operation == 'vibration' and values in (['on'], ['off']):
                enabled = values == ['on']
                obj = self.composite()
                if not enabled: obj.Stop(dbus_interface=FF)
                obj.Set(FF, 'Enabled', dbus.Boolean(enabled,variant_level=1), dbus_interface='org.freedesktop.DBus.Properties')
                self.prefs['vibration'] = enabled
                if enabled:
                    obj.Rumble(dbus.Double(0.55), dbus_interface=FF)
                    time.sleep(0.16)
                    obj.Stop(dbus_interface=FF)
            elif operation == 'brightness' and len(values) == 2 and values[0] in ('top', 'bottom', 'both'):
                percent = int(values[1])
                if not 1 <= percent <= 100:
                    raise ValueError('Brightness must be 1..100')
                for target in (['top','bottom'] if values[0] == 'both' else [values[0]]):
                    node = 'ae94000.dsi.0' if target == 'bottom' else 'ae96000.dsi.0'
                    folder = Path('/sys/class/backlight')/node
                    maximum = int(read(folder/'max_brightness'))
                    (folder/'brightness').write_text(str(max(1,maximum*percent//100))+'\n')
            elif operation == 'key' and values in (['escape'], ['reload-mangohud']):
                keys = [ecodes.KEY_ESC] if values == ['escape'] else [ecodes.KEY_LEFTSHIFT, ecodes.KEY_F4]
                for key in keys:
                    self.keyboard.write(ecodes.EV_KEY, key, 1)
                self.keyboard.syn()
                for key in reversed(keys):
                    self.keyboard.write(ecodes.EV_KEY, key, 0)
                self.keyboard.syn()
            elif operation == 'clean-memory' and not values:
                # Dirty pages stay intact; avoid a global sync that stalls other controls.
                Path('/proc/sys/vm/drop_caches').write_text('1\n')
            elif operation in ('mount-android', 'unmount-android') and len(values) == 1:
                part = next((p for p in self.android() if p['label'] == values[0]), None)
                if not part or not part['mountable']:
                    raise ValueError((part or {}).get('reason', 'Android partition not found'))
                target = Path('/mnt/aynthor-android') / part['label']
                target.mkdir(parents=True, exist_ok=True)
                mounts = json.loads(run('findmnt', '-J', '-o', 'SOURCE,TARGET,OPTIONS'))['filesystems']
                def flatten(items):
                    for item in items:
                        yield item
                        yield from flatten(item.get('children', []))
                mounted = next((m for m in flatten(mounts) if m['target'] == str(target)), None)
                if operation == 'mount-android':
                    if mounted:
                        raise ValueError('Mountpoint is already in use')
                    loop = False
                    if 'table' in part:
                        if Path('/sys/module/dm_mod').exists():
                            if not Path(part['device']).exists():
                                run('dmsetup','create','aynthor-android-'+part['label'],'--readonly','--table',part['table'])
                        else:
                            # This Thor kernel has loop devices but CONFIG_BLK_DEV_DM is disabled.
                            folder = STATE.parent/'android'/f"{part['label']}-{time.time_ns()}"
                            folder.mkdir(parents=True,exist_ok=True)
                            if os.statvfs(folder).f_bavail * os.statvfs(folder).f_frsize < part['size'] + 256*1024*1024:
                                raise ValueError('Not enough space for Android read-only snapshot')
                            run('python','/usr/lib/aynthor/lpunpack.py','-p',part['label'],part['super_device'],str(folder),timeout=180)
                            part['device'] = str(folder/(part['label']+'.img'))
                            loop = True
                        part['filesystem'] = run('blkid','-p','-s','TYPE','-o','value',part['device'])
                    if part['filesystem'] not in ('ext4','f2fs','erofs'):
                        raise ValueError('Unsupported Android filesystem')
                    options = 'ro,nosuid,nodev,noexec' + (',noload' if part['filesystem'] == 'ext4' else ',norecovery' if part['filesystem'] == 'f2fs' else '')
                    if loop: options += ',loop'
                    run('mount', '-n', '-t', part['filesystem'], '-o', options, part['device'], str(target), timeout=60)
                else:
                    if not mounted:
                        raise ValueError('No daemon-owned Android mount at this path')
                    if mounted['source'] != part['device']:
                        if not mounted['source'].startswith('/dev/loop'):
                            raise ValueError('Mount source does not belong to this daemon')
                        backing = read('/sys/class/block/'+Path(mounted['source']).name+'/loop/backing_file','')
                        if not Path(backing).is_relative_to(STATE.parent/'android') or Path(backing).name != part['label']+'.img':
                            raise ValueError('Loop image does not belong to this daemon')
                    run('umount', str(target))
                    if 'table' in part and part['device'].startswith('/dev/mapper/') and Path(part['device']).exists():
                        run('dmsetup','remove','aynthor-android-'+part['label'])
            else:
                raise ValueError('Unknown operation or invalid arguments')
            if operation not in ('brightness','key','clean-memory'): atomic_json(STATE, self.prefs)
            return self.quick_status() if operation in ('brightness','key','clean-memory','vibration','joystick') else self.collect_status()
        except (RuntimeError, ValueError, KeyError, OSError, subprocess.SubprocessError, dbus.DBusException) as e:
            raise dbus.exceptions.DBusException(str(e), name=NAME + '.Failed')


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    DBusGMainLoop(set_as_default=True)
    hardware = Hardware(dbus.SystemBus())
    GLib.MainLoop().run()
