#!/usr/bin/python
# SPDX-License-Identifier: LGPL-3.0-or-later
# Copyright (c) 2026 lurenjiamax
"""AYN Thor hardware service. Fixed operations only; never executes client commands."""
import json
import fcntl
import logging
import math
import os
import re
import select
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
from evdev import AbsInfo, InputDevice, UInput, ecodes, list_devices
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
        self.prefs = {'performance': 'standard', 'smart': False, 'joystick': 'gamepad', 'vibration': True, 'fan_follow_performance': True}
        if STATE.exists():
            self.prefs.update(json.loads(STATE.read_text()))
        self.prefs.pop('mangohud_auto',None)
        self.configure_mangohud(self.prefs.get('mangohud_mode','release'),
                                self.prefs.get('mangohud_limit',60),self.prefs.get('mangohud_hud',True))
        atomic_json(STATE,self.prefs)
        self.session_cache = None; self.session_cache_time = 0; self.sender_uids = {}
        bus.add_signal_receiver(self.invalidate_sessions, signal_name='PropertiesChanged', dbus_interface='org.freedesktop.DBus.Properties', bus_name='org.freedesktop.login1')
        bus.add_signal_receiver(self.invalidate_sessions, dbus_interface='org.freedesktop.login1.Manager', bus_name='org.freedesktop.login1')
        self.hardware_status = None; self.hardware_status_time = 0; self.hardware_config_stamp = None
        self.inputs = {}
        self.stick_axes = {}
        self.stick_sent = {}
        self.feedback_busy = False
        self.keyboard = UInput({ecodes.EV_KEY: [ecodes.KEY_ESC, ecodes.KEY_LEFTSHIFT, ecodes.KEY_F4]}, name='AYN Thor Action Keyboard')
        self.pointer = UInput({ecodes.EV_KEY: [ecodes.BTN_LEFT, ecodes.BTN_RIGHT],
                              ecodes.EV_REL: [ecodes.REL_X, ecodes.REL_Y, ecodes.REL_WHEEL]}, name='HandheldDash Pointer Placement')
        self.touchpad = UInput({ecodes.EV_KEY: [ecodes.BTN_LEFT, ecodes.BTN_TOUCH, ecodes.BTN_TOOL_FINGER,
            ecodes.BTN_TOOL_DOUBLETAP, ecodes.BTN_TOOL_TRIPLETAP, ecodes.BTN_TOOL_QUADTAP, ecodes.BTN_TOOL_QUINTTAP],
            ecodes.EV_ABS: [(code,AbsInfo(0,0,limit,0,0,resolution)) for code,limit,resolution in
                [(ecodes.ABS_X,1000,10),(ecodes.ABS_Y,600,10),(ecodes.ABS_MT_POSITION_X,1000,10),
                 (ecodes.ABS_MT_POSITION_Y,600,10),(ecodes.ABS_MT_SLOT,4,0),(ecodes.ABS_MT_TRACKING_ID,65535,0)]]},
            name='HandheldDash Virtual Touchpad', input_props=[ecodes.INPUT_PROP_POINTER,ecodes.INPUT_PROP_BUTTONPAD])
        self.touch_slots = {}; self.touch_tracking = 0; self.touch_owner = None
        self.touch_last = 0; self.touch_authorized = 0
        self.touch_region = None; self.raw_touches = {}; self.raw_slot = 0; self.raw_dropped = False
        self.touch_source = None; self.touch_grabbed = False; self.touch_relay = None; self.relay_slots = {}
        self.touch_rotation = 0; self.touch_calibration = (1,0,0,0,1,0)
        self.touch_lock = threading.RLock()
        self.touch_resetting = False
        GLib.timeout_add_seconds(2,self.touchpad_watchdog)
        bus.add_signal_receiver(self.touchpad_owner_changed,signal_name='NameOwnerChanged',
                                dbus_interface='org.freedesktop.DBus',bus_name='org.freedesktop.DBus')
        self.cpu_previous = (0, 0)
        self.tach_previous = None
        self.tach_rpm = None
        self.mutation_lock = threading.Lock()
        self.android_lock = threading.Lock()
        self.android_error = ""
        self.cached_status = None
        self.led_lock = threading.Lock()
        self.led_last_frame = 0
        self.led_dirs = {side: list(Path('/sys/class/leds').glob('rgb:'+side+'[0-9]*')) for side in ('l','r')}
        self.led_metadata = {node: (read(node/'multi_index','').split(),read(node/'max_brightness','255')+'\n') for nodes in self.led_dirs.values() for node in nodes}
        self.led_written = {}
        GLib.timeout_add_seconds(1, self.lighting_watchdog)
        self.last_button = {}
        self.navigation_down = set(); self.navigation_chord = False
        self.ip_ready = False
        self.initialize_fan()
        if not self.prefs.get('fan_follow_performance',True):
            try: run(CTL,'set','fan-profile','custom')
            except (RuntimeError,subprocess.SubprocessError) as e: logging.warning('Custom fan profile could not be restored: %s',e)
        bus.add_signal_receiver(self.resume, signal_name='PrepareForSleep', dbus_interface='org.freedesktop.login1.Manager',bus_name='org.freedesktop.login1')
        bus.add_signal_receiver(self.ip_event, signal_name='InputEvent', dbus_interface='org.shadowblip.Input.DBusDevice', bus_name=IP)
        GLib.timeout_add_seconds(2, self.discover_inputs)
        self.discover_inputs()
        self.maintain_ufs_irq()
        GLib.timeout_add_seconds(5,self.maintain_ufs_irq)

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
        if not sleeping:
            self.initialize_fan(); self.maintain_ufs_irq()
            self.hardware_status = None
            with self.led_lock: self.led_written.clear()

    def ufs_irqs(self):
        result=[]
        for line in Path('/proc/interrupts').read_text().splitlines():
            if 'ufshcd' not in line: continue
            number=line.split(':',1)[0].strip()
            if not number.isdigit(): continue
            node=Path('/proc/irq')/number
            result.append({'irq':int(number),'name':line[line.index('ufshcd'):].strip(),
                           'requested':read(node/'smp_affinity_list'),
                           'effective':read(node/'effective_affinity_list')})
        return result

    def apply_ufs_irq(self,mode):
        if mode not in ('system','powersave','performance'): raise ValueError('Invalid UFS IRQ mode')
        irqs=self.ufs_irqs()
        if not irqs: raise RuntimeError('No ufshcd interrupt found')
        if any(not irq['requested'] or not irq['effective'] for irq in irqs): raise RuntimeError('UFS IRQ affinity is unavailable')
        online=set()
        for part in read('/sys/devices/system/cpu/online').split(','):
            ends=list(map(int,part.split('-'))); online.update(range(ends[0],ends[-1]+1))
        target=','.join(str(cpu) for cpu in (range(3) if mode=='powersave' else [7]) if cpu in online)
        if target=='0,1,2': target='0-2'
        if mode!='system' and not target: raise RuntimeError('Selected UFS CPUs are offline')
        originals=self.prefs.setdefault('ufs_irq_original',{})
        previous=[]
        try:
            for irq in irqs:
                node=Path('/proc/irq')/str(irq['irq'])
                originals.setdefault(irq['name'],irq['requested'])
                desired=originals[irq['name']] if mode=='system' else target
                if irq['requested']==desired:
                    if mode=='system' or (mode=='performance' and irq['effective']=='7'): continue
                    if mode=='powersave' and irq['effective'] and all(int(cpu)<=2 for cpu in re.findall(r'\d+',irq['effective'])): continue
                previous.append((node,irq['requested']))
                (node/'smp_affinity_list').write_text(desired+'\n')
                effective=read(node/'effective_affinity_list')
                if mode=='performance' and effective!='7': raise RuntimeError('UFS IRQ did not move to CPU7')
                if mode=='powersave' and (not effective or any(int(cpu)>2 for cpu in re.findall(r'\d+',effective))):
                    raise RuntimeError('UFS IRQ did not move to CPU0–2')
        except Exception:
            for node,old in reversed(previous):
                try: (node/'smp_affinity_list').write_text(old+'\n')
                except OSError: logging.exception('Restore UFS IRQ affinity failed')
            raise

    def maintain_ufs_irq(self):
        mode=self.prefs.get('ufs_irq_mode','system')
        if mode!='system':
            try: self.apply_ufs_irq(mode)
            except (OSError,ValueError,RuntimeError): logging.exception('Apply UFS IRQ policy failed')
        return True

    def write_lighting(self, colors):
        for side,color in zip(('l','r'),colors):
            channels = dict(zip(('red','green','blue'),color))
            for node in self.led_dirs[side]:
                if self.led_written.get(node) == tuple(color): continue
                order,maximum = self.led_metadata[node]
                (node/'multi_intensity').write_text(' '.join(str(channels.get(c,0)) for c in order)+'\n')
                (node/'brightness').write_text(maximum)
                self.led_written[node] = tuple(color)

    @dbus.service.method(NAME, in_signature='iiiiii', out_signature='', sender_keyword='sender')
    def LightingFrame(self, lr, lg, lb, rr, rg, rb, sender=None):
        if self.sender_uid(sender) not in self.sessions():
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

    def invalidate_sessions(self,*args):
        self.session_cache = None

    def sender_uid(self,sender):
        if sender not in self.sender_uids:
            self.sender_uids[sender] = int(self.bus.get_unix_user(sender))
        return self.sender_uids[sender]

    def sessions(self):
        now = time.monotonic()
        if self.session_cache is not None and now-self.session_cache_time < 1: return self.session_cache
        obj = self.bus.get_object('org.freedesktop.login1', '/org/freedesktop/login1')
        result = []
        for _, uid, _, seat, path in obj.ListSessions(dbus_interface='org.freedesktop.login1.Manager'):
            if seat:
                p = self.bus.get_object('org.freedesktop.login1', path)
                props = p.GetAll('org.freedesktop.login1.Session', dbus_interface='org.freedesktop.DBus.Properties')
                if props['Active'] and not props['Remote']:
                    result.append(int(uid))
        self.session_cache = result; self.session_cache_time = now
        return result

    def authorize(self, sender):
        uid = self.sender_uid(sender)
        if uid != 0 and uid not in self.sessions():
            raise dbus.exceptions.DBusException('An active local session is required', name=NAME + '.AccessDenied')
        return uid

    @dbus.service.method(NAME, in_signature='iiii', out_signature='', sender_keyword='sender')
    def Pointer(self, dx, dy, wheel, button, sender=None):
        self.authorize(sender)
        if abs(dx) > 32767 or abs(dy) > 32767 or abs(wheel) > 10 or button not in (0, 1, 2):
            raise dbus.exceptions.DBusException('Invalid pointer frame', name=NAME + '.InvalidArgument')
        for code, value in ((ecodes.REL_X, dx), (ecodes.REL_Y, dy), (ecodes.REL_WHEEL, wheel)):
            if value: self.pointer.write(ecodes.EV_REL, code, value)
        self.pointer.syn()
        if button:
            code = ecodes.BTN_LEFT if button == 1 else ecodes.BTN_RIGHT
            self.pointer.write(ecodes.EV_KEY, code, 1); self.pointer.syn()
            self.pointer.write(ecodes.EV_KEY, code, 0); self.pointer.syn()

    @dbus.service.method(NAME, in_signature='s', out_signature='', sender_keyword='sender')
    def TouchpadRegion(self, raw, sender=None):
        if self.touch_resetting: return
        now = time.monotonic()
        if sender != self.touch_owner or now-self.touch_authorized > 1:
            self.authorize(sender); self.touch_authorized = now
        if self.touch_region and sender != self.touch_owner:
            raise dbus.exceptions.DBusException('Touchpad is in use', name=NAME + '.Busy')
        try:
            if len(raw) > 1024: raise ValueError()
            config = json.loads(raw)
            if not isinstance(config,dict): raise ValueError()
            region = config.get('region')
            rotation = config.get('rotation')
            calibration = config.get('calibration')
            if type(rotation) is not int or rotation not in (0,90,180,270): raise ValueError()
            if not isinstance(calibration,list) or len(calibration) != 6 or any(
                type(v) not in (int,float) or not math.isfinite(v) or abs(v)>4 for v in calibration): raise ValueError()
            if region and (not isinstance(region,list) or len(region) != 4 or
                           any(type(v) is not int or not 0 <= v <= 10000 for v in region) or
                           region[0] >= region[2] or region[1] >= region[3]): raise ValueError()
            if region != [] and not region: raise ValueError()
        except (ValueError,TypeError):
            raise dbus.exceptions.DBusException('Invalid touchpad region', name=NAME + '.InvalidArgument')
        with self.touch_lock:
            self.touch_rotation = rotation; self.touch_calibration = tuple(calibration)
            region = tuple(region) if region else None
            if region is None and self.touch_region is not None:
                self.write_touchpad([])
                for point in self.raw_touches.values(): point['admitted'] = False
            self.touch_region = region; self.touch_owner = sender; self.touch_last = now
            if region is None: self.stop_touchpad()
            else: self.grab_touchscreen()

    def grab_touchscreen(self):
        if self.touch_grabbed or self.touch_source is None or self.touch_region is None: return
        # Finish the physical touch selecting this tab before taking exclusive ownership.
        if ecodes.BTN_TOUCH not in self.touch_source.active_keys():
            self.touch_source.grab(); self.touch_grabbed = True
            for point in self.raw_touches.values(): point['admitted'] = None

    def read_touchscreen(self, device, path):
        # Hardware and D-Bus calls must not delay touch frames in the GLib main loop.
        while self.touch_source is device:
            ready,_,_ = select.select([device.fd],[],[],1)
            if ready:
                with self.touch_lock:
                    if not self.raw_touch_event(path): return

    def raw_touch_event(self, path):
        device = self.inputs[path][0]
        try:
            for event in device.read():
                if event.type == ecodes.EV_SYN and event.code == ecodes.SYN_DROPPED:
                    logging.warning('Touchscreen input buffer overflow')
                    self.raw_dropped = True
                    continue
                if self.raw_dropped: continue
                if event.type == ecodes.EV_ABS:
                    if event.code == ecodes.ABS_MT_SLOT: self.raw_slot = event.value
                    elif event.code == ecodes.ABS_MT_TRACKING_ID:
                        previous = self.raw_touches.get(self.raw_slot,{'x':0,'y':0})
                        self.raw_touches[self.raw_slot] = {'id':event.value,'x':previous['x'],'y':previous['y'],
                                                           'admitted':None if event.value >= 0 else False}
                    elif event.code in (ecodes.ABS_MT_POSITION_X,ecodes.ABS_MT_POSITION_Y):
                        point = self.raw_touches.get(self.raw_slot)
                        if point is not None: point['x' if event.code == ecodes.ABS_MT_POSITION_X else 'y'] = event.value
                elif event.type == ecodes.EV_SYN and event.code == ecodes.SYN_REPORT and self.touch_region:
                    if not self.touch_grabbed:
                        self.grab_touchscreen(); continue
                    self.forward_touch_frame(event)
            if self.raw_dropped:
                try:
                    while True: list(device.read())
                except BlockingIOError: pass
                self.resync_touchscreen(device)
                self.raw_dropped = False
                if self.touch_region and self.touch_grabbed: self.forward_touch_frame()
        except BlockingIOError: pass
        except OSError as error:
            logging.warning('Touchscreen: %s',error)
            self.stop_touchpad(); self.raw_touches.clear(); device.close(); self.inputs.pop(path,None)
            self.touch_source = None
            return False
        return True

    def resync_touchscreen(self, device):
        count = device.absinfo(ecodes.ABS_MT_SLOT).max+1
        values = []
        for code in (ecodes.ABS_MT_TRACKING_ID,ecodes.ABS_MT_POSITION_X,ecodes.ABS_MT_POSITION_Y):
            buffer = bytearray(struct.pack('i',code)+bytes(count*4))
            request = (2 << 30) | (len(buffer) << 16) | (ord('E') << 8) | 0x0a  # EVIOCGMTSLOTS
            fcntl.ioctl(device.fd,request,buffer,True)
            values.append(struct.unpack('i'*(count+1),buffer)[1:])
        recovered = {}
        for slot,(identity,x,y) in enumerate(zip(*values)):
            previous = self.raw_touches.get(slot,{})
            point = dict(previous) if previous.get('id') == identity else {'admitted':None}
            point.update(id=identity,x=x,y=y)
            recovered[slot] = point
        self.raw_touches = recovered
        self.raw_slot = device.absinfo(ecodes.ABS_MT_SLOT).value

    def forward_touch_frame(self, event=None):
        xaxis,yaxis = self.touch_axes
        left,top,right,bottom = [v/10000 for v in self.touch_region]
        points = []; relay = []
        for point in self.raw_touches.values():
            if point['id'] < 0: continue
            x = (point['x']-xaxis.min)/(xaxis.max-xaxis.min)
            y = (point['y']-yaxis.min)/(yaxis.max-yaxis.min)
            a,b,c,d,e,f = self.touch_calibration
            hit_x,hit_y = a*x+b*y+c,d*x+e*y+f
            if point['admitted'] is None:
                point['admitted'] = left <= hit_x < right and top <= hit_y < bottom
                # Freeze orientation for this contact to avoid a jump during screen rotation.
                point['rotation'] = self.touch_rotation
            if point['admitted']:
                rotation = point['rotation']
                if rotation == 90: x,y = 1-y,x
                elif rotation == 180: x,y = 1-x,1-y
                elif rotation == 270: x,y = y,1-x
                points.append([point['id'],max(0,min(1000,round(x*1000))),max(0,min(600,round(y*600)))])
            else: relay.append([point['id'],point['x'],point['y']])
        if points or self.touch_slots: self.write_touchpad(points,event)
        if relay or self.relay_slots: self.write_relay(relay,event)
        logging.debug('Touch frame source=%s processed=%s raw=%s pad=%s relay=%s',
                      (event.sec+event.usec/1e6) if event else time.monotonic(),time.monotonic(),self.raw_touches,points,relay)

    def write_touchpad(self, points, timestamp=None):
        self.write_contacts(self.touchpad,self.touch_slots,points,timestamp,tools=True)

    def write_relay(self, points, timestamp=None):
        if self.touch_relay is not None: self.write_contacts(self.touch_relay,self.relay_slots,points,timestamp)

    def write_contacts(self, device, slots, points, timestamp=None, tools=False):
        events = []
        def write(etype,code,value): events.append((etype,code,value))
        write(ecodes.EV_KEY,ecodes.BTN_TOUCH,int(bool(points)))
        identities = {p[0] for p in points}
        for identity,slot in list(slots.items()):
            if identity not in identities:
                write(ecodes.EV_ABS,ecodes.ABS_MT_SLOT,slot)
                write(ecodes.EV_ABS,ecodes.ABS_MT_TRACKING_ID,-1)
                del slots[identity]
        for identity,x,y in points:
            if identity not in slots:
                slot = next(s for s in range(5) if s not in slots.values())
                slots[identity] = slot
                self.touch_tracking = (self.touch_tracking+1)%65536
                write(ecodes.EV_ABS,ecodes.ABS_MT_SLOT,slot)
                write(ecodes.EV_ABS,ecodes.ABS_MT_TRACKING_ID,self.touch_tracking)
            else: write(ecodes.EV_ABS,ecodes.ABS_MT_SLOT,slots[identity])
            write(ecodes.EV_ABS,ecodes.ABS_MT_POSITION_X,x)
            write(ecodes.EV_ABS,ecodes.ABS_MT_POSITION_Y,y)
        if points:
            write(ecodes.EV_ABS,ecodes.ABS_X,points[0][1])
            write(ecodes.EV_ABS,ecodes.ABS_Y,points[0][2])
        if tools:
            for count,code in enumerate([ecodes.BTN_TOOL_FINGER,ecodes.BTN_TOOL_DOUBLETAP,ecodes.BTN_TOOL_TRIPLETAP,
                                         ecodes.BTN_TOOL_QUADTAP,ecodes.BTN_TOOL_QUINTTAP],1):
                write(ecodes.EV_KEY,code,int(len(points) == count))
        write(ecodes.EV_SYN,ecodes.SYN_REPORT,0)
        micros = time.monotonic_ns()//1000 if timestamp is None else timestamp.sec*1000000+timestamp.usec
        seconds,micros = divmod(micros,1000000)
        # Preserve source frame timing when the main loop reads several frames together.
        packet = b''.join(struct.pack('llHHi',seconds,micros,*event) for event in events)
        if os.write(device.fd,packet) != len(packet): raise OSError('Incomplete touchpad frame')

    def stop_touchpad(self):
        with self.touch_lock:
            self.write_touchpad([]); self.write_relay([])
            if self.touch_grabbed and self.touch_source is not None:
                try: self.touch_source.ungrab()
                except OSError as error: logging.warning('Release touchscreen: %s',error)
            self.touch_grabbed = False; self.touch_owner = None; self.touch_region = None
            for point in self.raw_touches.values(): point['admitted'] = False

    def touchpad_owner_changed(self, name, previous, current):
        if not current: self.sender_uids.pop(str(name),None)
        if name == self.touch_owner and not current: self.stop_touchpad()

    def touchpad_watchdog(self):
        if self.touch_region:
            try: self.authorize(self.touch_owner)
            except dbus.DBusException: self.stop_touchpad()
        return True

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
        if str(event) in ('ui_guide','ui_back'):
            action = 'home' if str(event) == 'ui_guide' else 'back'
            if value == 1:
                if action in self.navigation_down: return
                self.navigation_down.add(action)
                if len(self.navigation_down) == 2 and not self.navigation_chord:
                    self.navigation_chord = True
                    if self.prefs.get('navigation_chord','reset-touchscreen') == 'reset-touchscreen':
                        self.request_touch_reset()
                    else: self.emit_button('back-home')
            elif value == 0 and action in self.navigation_down:
                self.navigation_down.remove(action)
                if not self.navigation_chord: self.emit_button(action)
                if not self.navigation_down: self.navigation_chord = False

    def request_touch_reset(self):
        if not self.touch_resetting:
            self.touch_resetting=True
            threading.Thread(target=self.reset_touchscreen,daemon=True).start()

    def reset_touchscreen(self):
        try:
            driver = Path('/sys/bus/i2c/devices/1-0038/driver').resolve(strict=True)
            with self.touch_lock: self.stop_touchpad()
            (driver/'unbind').write_text('1-0038')
            try:
                (driver/'bind').write_text('1-0038')
            except OSError:
                # Retry binding so a transient probe failure does not leave the screen detached.
                (driver/'bind').write_text('1-0038')
            logging.info('HOME+BACK: bottom touchscreen driver rebound')
        except OSError:
            logging.exception('HOME+BACK: touchscreen recovery failed')
        finally:
            self.touch_resetting = False

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
                        self.emit_button('gamepad-focus')
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
                if dev.name == 'bottom_touchscreen':
                    if self.touch_resetting:
                        dev.close(); continue
                    fcntl.ioctl(dev.fd,0x400445a0,struct.pack('i',time.CLOCK_MONOTONIC))  # EVIOCSCLOCKID
                    self.touch_axes = (dev.absinfo(ecodes.ABS_MT_POSITION_X),dev.absinfo(ecodes.ABS_MT_POSITION_Y))
                    self.touch_source = dev
                    if self.touch_relay is None:
                        self.touch_relay = UInput.from_device(dev,name='HandheldDash Touchscreen Relay',input_props=[ecodes.INPUT_PROP_DIRECT])
                    self.inputs[path] = (dev,None)
                    threading.Thread(target=self.read_touchscreen,args=(dev,path),daemon=True).start()
                elif dev.name in ('Thorch Hardware Keys','Microsoft Xbox Series S|X Controller'):
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

    def userdata_view(self, uid):
        source=Path('/mnt/android-data/media/0'); target=Path('/mnt/aynthor-android/userdata')
        mount=subprocess.run(['findmnt','-rn','-M',str(target),'-o','FSTYPE'],capture_output=True,text=True)
        if mount.returncode == 0:
            if mount.stdout.strip() != 'fuse.bindfs': raise ValueError('Shared mountpoint is already in use')
            return
        if not source.is_dir(): raise ValueError('Android shared storage is not available')
        target.mkdir(parents=True,exist_ok=True)
        owner=source.stat()
        run('bindfs','--mirror-only='+str(uid),'--perms=u+rwX',
            '--create-for-user='+str(owner.st_uid),'--create-for-group='+str(owner.st_gid),
            '--chown-ignore','--chgrp-ignore','--chmod-ignore','--xattr-ro',
            '-o','nosuid,nodev,noexec',str(source),str(target))

    def userdata_status(self, device):
        base = STATE.parent/'android'
        helper = base/'test-thor-metadata-unlock.sh'
        release = os.uname().release
        ready = (release == '7.1.2-thorch19' and helper.is_file()
                 and (base/'keymint-private/metadata.keyblob').is_file()
                 and all((base/'keymint-runtime'/name).is_file() for name in ('bin/linker64','bin/native-convert','lib64/conversion-compat.so','lib64/libaynthor-mink-bridge.so'))
                 and all((base/'tme-modules'/release/(name+'.ko')).is_file()
                         for name in ('aynthor_qmp','tme_overlay_loader','aynthor_tme')))
        state = run('systemctl','show','aynthor-userdata-mount.service','-p','ActiveState','--value')
        mount = subprocess.run(['findmnt','-rn','-M','/mnt/android-data','-o','FSTYPE'],capture_output=True,text=True)
        return {'backend_ready':ready, 'service_state':state, 'mounted':mount.returncode == 0,
                'mountpoint':'/mnt/android-data', 'busy':self.android_lock.locked(),
                'error':self.android_error, 'mountable':ready}

    def userdata_action(self, operation, part, uid):
        if not self.android_lock.acquire(blocking=False):
            raise ValueError('Android mount operation is already running')
        self.android_error = ''
        def execute():
            try:
                device = part['device']
                status = self.userdata_status(device)
                if operation == 'mount-userdata':
                    if status['mounted'] or status['service_state'] in ('active','activating','deactivating'):
                        raise ValueError('Android userdata is already mounted or changing state')
                    if not status['backend_ready']:
                        raise ValueError('Matching kernel, private keys and userdata backend are required')
                    if subprocess.run(['pgrep','-x','fsck.f2fs'],stdout=subprocess.DEVNULL).returncode == 0:
                        raise ValueError('A filesystem check is running; cannot mount userdata')
                    run('blockdev','--setrw',device)
                    run('systemd-run','--unit=aynthor-userdata-mount','--collect',
                        '--property=TimeoutStopSec=90','--property=LimitCORE=0',
                        '/bin/bash',str(STATE.parent/'android/test-thor-metadata-unlock.sh'),'--mount-user0-rw')
                    for _ in range(80):
                        if self.userdata_status(device)['mounted']: break
                        time.sleep(.5)
                    else: raise ValueError('Userdata mount is not ready; inspect backend service state')
                    self.userdata_view(uid)
                else:
                    view=subprocess.run(['findmnt','-rn','-M','/mnt/aynthor-android/userdata','-o','FSTYPE'],capture_output=True,text=True)
                    if view.returncode == 0:
                        if view.stdout.strip() != 'fuse.bindfs': raise ValueError('Shared mountpoint is not owned by bindfs')
                        run('umount','/mnt/aynthor-android/userdata')
                    if status['service_state'] != 'inactive':
                        run('systemctl','stop','aynthor-userdata-mount.service',timeout=95)
                    if self.userdata_status(device)['mounted']:
                        raise ValueError('Android userdata is still mounted; close applications using it')
                    if run('dmsetup','ls','--target','default-key') != 'No devices found':
                        raise ValueError('A default-key mapper remains; inspect cleanup before switching systems')
                    run('blockdev','--setro',device)
                    run('sync',timeout=60)
            except Exception as e:
                self.android_error = str(e)
                logging.warning('Android userdata operation failed: %s',e)
            finally:
                self.android_lock.release()
        threading.Thread(target=execute,daemon=True).start()

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
        for part in found:
            if part['label'] == 'userdata':
                part.update(self.userdata_status(part['device']))
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
            now = time.monotonic()
            stamp = Path('/etc/thorch/hardware.conf').stat().st_mtime_ns
            if self.hardware_status is None or stamp != self.hardware_config_stamp or now-self.hardware_status_time >= 15:
                self.hardware_status = json.loads(run(CTL, 'status-json'))
                self.hardware_status_time = now; self.hardware_config_stamp = stamp
            data = self.hardware_status.copy()
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
            data['battery']['charge_type'] = read(battery+'charge_type','Unknown')
            usb=Path('/sys/class/power_supply/qcom-battmgr-usb')
            protocol=re.search(r'\[([^]]+)\]',read(usb/'usb_type',''))
            data['battery']['charging_protocol'] = protocol.group(1) if protocol else 'Unknown'
            data['battery']['fast_charging'] = data['battery']['status'] == 'Charging' and (data['battery']['charging_protocol'] in ('PD','PD_PPS') or (number(usb/'voltage_now') or 0) > 5500000)
            data['temperature_sensors'] = [{'id':read(p/'type',p.name),'name':read(p/'type',p.name),'temperature':number(p/'temp',1000)} for p in sorted(Path('/sys/class/thermal').glob('thermal_zone*'),key=lambda p:int(p.name.removeprefix('thermal_zone')))]
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
            data['ufs_irqs']=self.ufs_irqs()
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
        uid = self.authorize(sender)
        if not self.mutation_lock.acquire(blocking=False):
            error(dbus.exceptions.DBusException('Hardware is busy; retry the latest value', name=NAME+'.Busy'))
            return
        def execute():
            try:
                result = self.apply(operation,values,uid)
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

    def configure_mangohud(self,mode,limit,hud):
        config=Path('/etc/MangoHud.conf')
        active=self.prefs.get('mangohud_mode') == 'takeover'
        if mode == 'release':
            if active:
                original=json.loads(Path(self.prefs['mangohud_backup']).read_text(encoding='utf-8'))
                if original['exists']: config.write_text(original['content'],encoding='utf-8')
                else: config.unlink(missing_ok=True)
        else:
            if not active:
                backup=STATE.parent/f'MangoHud-original-{time.time_ns()}.json'
                atomic_json(backup,{'exists':config.exists(),'content':config.read_text(encoding='utf-8') if config.exists() else ''})
                self.prefs['mangohud_backup']=str(backup)
                # Persist the backup before modifying the live configuration.
                self.prefs['mangohud_mode']='takeover'
                atomic_json(STATE,self.prefs)
            lines=config.read_text(encoding='utf-8').splitlines() if config.exists() else []
            managed={'fps_limit','no_display','output_folder','autostart_log','log_interval','log_duration'}
            lines=[line for line in lines if line.partition('=')[0].strip() not in managed]
            lines += [f'fps_limit={limit}',f'no_display={int(not hud)}','output_folder=/var/cache/handhelddash/fps','autostart_log=1','log_interval=500','log_duration=0']
            # Keep the inode for MangoHud's configuration hot reload.
            content='\n'.join(lines)+'\n'
            if not config.exists() or config.read_text(encoding='utf-8') != content:
                config.write_text(content,encoding='utf-8')
        self.prefs.update(mangohud_mode=mode,mangohud_limit=limit,mangohud_hud=hud)

    def apply(self, operation, values, uid=0):
        operation, values = str(operation), list(map(str, values))
        self.hardware_status = None
        if operation.startswith(('rgb-','lighting-')):
            with self.led_lock: self.led_written.clear()
        arities = {'scheduler': 1, 'cpu-boost': 1, 'cpu-governor': 1, 'gpu-governor': 1, 'governors': 2, 'fan-profile': 1, 'fan-sensor-mode': 1, 'fan-state': 2, 'rgb-mode': 1, 'rgb-brightness': 1, 'rgb-color': 3, 'rgb-state': 5}
        try:
            if operation == 'mangohud' and len(values) == 3:
                mode,limit,hud = values
                if mode not in ('release','takeover') or int(limit) not in (0,30,60,120) or hud not in ('on','off'):
                    raise ValueError('Invalid MangoHud settings')
                self.configure_mangohud(mode,int(limit),hud == 'on')
            elif operation == 'navigation-chord' and len(values) == 1 and values[0] in ('escape','desktop','overview','panel','screenshot','swap','none','command','reset-touchscreen'):
                self.prefs['navigation_chord']=values[0]
            elif operation == 'reset-touchscreen' and not values:
                self.request_touch_reset()
            elif operation == 'ufs-irq' and len(values)==1:
                self.apply_ufs_irq(values[0]); self.prefs['ufs_irq_mode']=values[0]
            elif operation == 'lighting-color' and len(values) == 4 and values[0] in ('left','right'):
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
                self.prefs['fan_follow_performance'] = False
            elif operation == 'fan-follow-performance' and values in (['on'],['off']):
                if values == ['on']:
                    profile = {'quiet':'quiet','standard':'moderate','performance':'aggressive'}.get(self.prefs['performance'],'moderate')
                    run(CTL,'set','fan-profile',profile)
                else:
                    run(CTL,'set','fan-profile','custom')
                self.prefs['fan_follow_performance'] = values == ['on']
            elif operation in arities and len(values) == arities[operation]:
                if any(len(v) > 32 for v in values):
                    raise ValueError('Value too long')
                run(CTL, 'set', operation, *values)
                if operation in ('fan-profile','fan-state'): self.prefs['fan_follow_performance'] = False
                if operation in ('rgb-mode','rgb-state'): self.prefs['lighting_mode'] = None
                if operation in ('cpu-governor','gpu-governor','governors'):
                    self.prefs['smart'] = False
            elif operation == 'performance' and len(values) == 1:
                modes = {'quiet': ('powersave', 'powersave', 'quiet', 'off'), 'standard': ('schedutil', 'simple_ondemand', 'moderate', 'on'), 'performance': ('performance', 'performance', 'aggressive', 'on')}
                cpu, gpu, fan, boost = modes[values[0]]
                run(CTL, 'set', 'governors', cpu, gpu)
                if self.prefs['fan_follow_performance']: run(CTL, 'set', 'fan-profile', fan)
                run(CTL, 'set', 'cpu-boost', boost)
                self.prefs['performance'] = values[0]
                self.prefs['smart'] = False
            elif operation == 'smart' and values in (['on'], ['off']):
                if values == ['on']:
                    run(CTL, 'set', 'governors', 'schedutil', 'simple_ondemand')
                    if self.prefs['fan_follow_performance']: run(CTL, 'set', 'fan-profile', 'moderate')
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
            elif operation == 'userdata-share' and values == ['userdata']:
                if not self.android_lock.acquire(blocking=False): raise ValueError('Android mount operation is running')
                try:
                    if subprocess.run(['findmnt','-rn','-M','/mnt/android-data'],stdout=subprocess.DEVNULL).returncode:
                        raise ValueError('Android userdata is not mounted')
                    self.userdata_view(uid)
                finally: self.android_lock.release()
            elif operation in ('mount-userdata','unmount-userdata') and values == ['userdata']:
                part = next((p for p in self.android() if p['label'] == 'userdata'),None)
                if not part: raise ValueError('Android userdata partition not found')
                self.userdata_action(operation,part,uid)
            elif operation in ('mount-android', 'unmount-android') and len(values) == 1:
                part = next((p for p in self.android() if p['label'] == values[0]), None)
                if part and part['label'] == 'userdata':
                    raise ValueError('Use the dedicated userdata backend')
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
    logging.basicConfig(level=logging.DEBUG if os.environ.get('HANDHELDDASH_TOUCH_TRACE') == '1' else logging.INFO)
    DBusGMainLoop(set_as_default=True)
    hardware = Hardware(dbus.SystemBus())
    GLib.MainLoop().run()
