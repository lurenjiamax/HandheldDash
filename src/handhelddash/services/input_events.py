# SPDX-License-Identifier: LGPL-3.0-or-later
from handhelddash.services.runtime import CI, DEVICE, GLib, IP, InputDevice, NAME, UInput, dbus, ecodes, fcntl, list_devices, logging, struct, threading, time

class InputEventsService(dbus.service.Object):
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
                if DEVICE.touchscreen and dev.name == DEVICE.touchscreen:
                    if self.touch_resetting:
                        dev.close(); continue
                    fcntl.ioctl(dev.fd,0x400445a0,struct.pack('i',time.CLOCK_MONOTONIC))  # EVIOCSCLOCKID
                    self.touch_axes = (dev.absinfo(ecodes.ABS_MT_POSITION_X),dev.absinfo(ecodes.ABS_MT_POSITION_Y))
                    self.touch_source = dev
                    if self.touch_relay is None:
                        self.touch_relay = UInput.from_device(dev,name='HandheldDash Touchscreen Relay',input_props=[ecodes.INPUT_PROP_DIRECT])
                    self.inputs[path] = (dev,None)
                    threading.Thread(target=self.read_touchscreen,args=(dev,path),daemon=True).start()
                elif dev.name in DEVICE.hotkey_devices:
                    watch = GLib.io_add_watch(dev.fd, GLib.IO_IN | GLib.IO_HUP, self.input_event, path)
                    self.inputs[path] = (dev, watch)
                else:
                    dev.close()
            except OSError as e:
                logging.warning('Input discovery: %s', e)
        try:
            if not self.bus.name_has_owner(IP):
                self.ip_ready=False; return True
            if not self.ip_ready:
                self.configure_input()
            else:
                profile = self.composite().Get(CI, 'ProfileName', dbus_interface='org.freedesktop.DBus.Properties')
                if str(profile) != DEVICE.profile_prefix+' '+self.prefs['joystick']:
                    self.configure_input()
        except (dbus.DBusException, RuntimeError, OSError, ValueError) as e:
            self.ip_ready = False
            logging.warning('InputPlumber: %s', e)
        return True

