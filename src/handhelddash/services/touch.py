# SPDX-License-Identifier: LGPL-3.0-or-later
from handhelddash.services.runtime import DEVICE, NAME, Path, dbus, ecodes, fcntl, json, logging, math, os, select, struct, threading, time

class TouchService(dbus.service.Object):
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
            if region and 'bottom' in self.screen_holds:
                raise ValueError('Screen touch is locked')
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

    def request_touch_reset(self):
        if not self.touch_resetting:
            self.touch_resetting=True
            threading.Thread(target=self.reset_touchscreen,daemon=True).start()

    def reset_touchscreen(self):
        try:
            if not DEVICE.touchscreen_reset: raise ValueError('Touchscreen reset is not supported on this device')
            driver = (Path('/sys/bus/i2c/devices')/DEVICE.touchscreen_reset/'driver').resolve(strict=True)
            with self.touch_lock: self.stop_touchpad()
            (driver/'unbind').write_text(DEVICE.touchscreen_reset)
            try:
                (driver/'bind').write_text(DEVICE.touchscreen_reset)
            except OSError:
                # Retry binding so a transient probe failure does not leave the screen detached.
                (driver/'bind').write_text(DEVICE.touchscreen_reset)
            logging.info('HOME+BACK: bottom touchscreen driver rebound')
        except OSError:
            logging.exception('HOME+BACK: touchscreen recovery failed')
        finally:
            self.touch_resetting = False
