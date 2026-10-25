"""Screen dimming with exclusive touch inhibition and disconnect recovery."""
import threading
from handhelddash.services.runtime import DEVICE, NAME, STATE, InputDevice, Path, atomic_json, dbus, json, list_devices, logging


class DisplayService(dbus.service.Object):
    def initialize_displays(self):
        self.display_lock = threading.RLock()
        self.screen_holds = {}
        self.screen_state_file = STATE.parent/'screen-restore.json'
        if self.screen_state_file.exists():
            saved = json.loads(self.screen_state_file.read_text())
            for role,value in saved.items():
                if role in DEVICE.backlights:
                    folder = Path('/sys/class/backlight')/DEVICE.backlights[role]
                    maximum = int((folder/'max_brightness').read_text())
                    (folder/'brightness').write_text(str(max(0,min(maximum,int(value)))))
            atomic_json(self.screen_state_file,{})
        self.bus.add_signal_receiver(self.screen_owner_changed,signal_name='NameOwnerChanged',
                                    dbus_interface='org.freedesktop.DBus',bus_name='org.freedesktop.DBus')

    def save_screen_restore(self):
        atomic_json(self.screen_state_file,{role:hold['brightness'] for role,hold in self.screen_holds.items()})

    @dbus.service.method(NAME,in_signature='sb',out_signature='s',sender_keyword='sender')
    def ScreenPower(self,role,visible,sender=None):
        self.authorize(sender)
        role = str(role)
        if role not in DEVICE.backlights or role not in DEVICE.touchscreens:
            raise ValueError('Screen and touchscreen mapping is unavailable')
        with self.display_lock:
            if visible:
                self.restore_screen(role)
            elif role not in self.screen_holds:
                folder = Path('/sys/class/backlight')/DEVICE.backlights[role]
                original = int((folder/'brightness').read_text())
                device = None
                try:
                    with self.touch_lock:
                        if DEVICE.touchscreens[role] == DEVICE.touchscreen: self.stop_touchpad()
                        for path in list_devices():
                            candidate = InputDevice(path)
                            if candidate.name == DEVICE.touchscreens[role]:
                                device = candidate; break
                            candidate.close()
                        if device is None: raise ValueError('Touchscreen is unavailable')
                        device.grab()
                    self.screen_holds[role] = {'owner':str(sender),'device':device,'brightness':original}
                    self.save_screen_restore()
                    (folder/'brightness').write_text('0\n')
                    if int((folder/'brightness').read_text()) != 0: raise ValueError('Screen rejected zero brightness')
                except Exception:
                    if role in self.screen_holds: self.restore_screen(role)
                    elif device is not None: device.close()
                    raise
            return json.dumps(list(self.screen_holds))

    def restore_screen(self,role):
        with self.display_lock:
            hold = self.screen_holds.get(role)
            if hold is None: return
            folder = Path('/sys/class/backlight')/DEVICE.backlights[role]
            (folder/'brightness').write_text(str(hold['brightness'])+'\n')
            hold['device'].close()  # Closing releases the exclusive evdev grab.
            del self.screen_holds[role]
            self.save_screen_restore()

    def restore_screens(self):
        with self.display_lock:
            for role in list(self.screen_holds):
                try: self.restore_screen(role)
                except OSError: logging.exception('Restore screen %s failed',role)

    def screen_owner_changed(self,name,previous,current):
        if current: return
        with self.display_lock:
            for role,hold in list(self.screen_holds.items()):
                if hold['owner'] == str(name):
                    try: self.restore_screen(role)
                    except OSError: logging.exception('Restore disconnected screen owner failed')
