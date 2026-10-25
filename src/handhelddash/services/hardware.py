# SPDX-License-Identifier: LGPL-3.0-or-later
from handhelddash.services.runtime import AbsInfo, CTL, DEVICE, GLib, GPUUtilization, IP, NAME, PATH, Path, STATE, UInput, atomic_json, dbus, ecodes, json, logging, read, run, subprocess, threading
from handhelddash.integrations.thorch.control import ThorchService
from handhelddash.integrations.inputplumber.controller import InputPlumberService
from handhelddash.services.touch import TouchService
from handhelddash.services.sessions import SessionService
from handhelddash.services.input_events import InputEventsService
from handhelddash.services.storage import StorageService
from handhelddash.services.telemetry import TelemetryService
from handhelddash.services.operations import OperationService
from handhelddash.services.displays import DisplayService
from handhelddash.services.backend_factory import hardware_backend

class Hardware(ThorchService, InputPlumberService, TouchService, SessionService, InputEventsService, StorageService, TelemetryService, OperationService, DisplayService, dbus.service.Object):
    def __init__(self, bus):
        self.backend=hardware_backend(DEVICE)
        self.bus = bus
        # Recover dark panels before advertising the D-Bus service as ready.
        self.initialize_displays()
        self.name = dbus.service.BusName(NAME, bus, do_not_queue=True)
        super().__init__(self.name, PATH)
        self.prefs = {'performance': 'standard', 'smart': False, 'joystick': 'gamepad', 'controller_output': '', 'vibration': True, 'vibration_gain': 100, 'fan_follow_performance': True}
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
        self.cpu_previous = None
        self.gpu_utilization=GPUUtilization(DEVICE.gpu_utilization)
        self.io_previous = {'network':{},'disk_io':{}}; self.io_times = {'network':0,'disk_io':0}; self.io_rates = {'network':{},'disk_io':{}}
        self.monitoring = {'items':[],'modes':{}}
        self.tach_previous = None
        self.tach_rpm = None
        self.mutation_lock = threading.Lock()
        self.android_lock = threading.Lock()
        self.android_error = ""
        self.cached_status = None
        self.led_lock = threading.Lock()
        self.led_last_frame = 0
        self.led_dirs = {side: list(Path('/sys/class/leds').glob(DEVICE.led_patterns[side])) if side in DEVICE.led_patterns else [] for side in ('l','r')}
        self.led_metadata = {node: (read(node/'multi_index','').split(),read(node/'max_brightness','255')+'\n') for nodes in self.led_dirs.values() for node in nodes}
        self.led_written = {}
        GLib.timeout_add_seconds(1, self.lighting_watchdog)
        self.last_button = {}
        self.navigation_down = set(); self.navigation_chord = False
        self.ip_ready = False
        self.vibration_gain_supported = False
        self.controller_profile_name = ''
        self.controller_output_name = ''
        self.initialize_fan()
        if self.backend.available and not self.prefs.get('fan_follow_performance',True):
            try: self.backend.set('fan-profile','custom')
            except (RuntimeError,subprocess.SubprocessError) as e: logging.warning('Custom fan profile could not be restored: %s',e)
        bus.add_signal_receiver(self.resume, signal_name='PrepareForSleep', dbus_interface='org.freedesktop.login1.Manager',bus_name='org.freedesktop.login1')
        bus.add_signal_receiver(self.ip_event, signal_name='InputEvent', dbus_interface='org.shadowblip.Input.DBusDevice', bus_name=IP)
        GLib.timeout_add_seconds(2, self.discover_inputs)
        self.discover_inputs()
        self.maintain_ufs_irq()
        GLib.timeout_add_seconds(5,self.maintain_ufs_irq)

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
