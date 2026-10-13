# SPDX-License-Identifier: LGPL-3.0-or-later
from handhelddash.services.runtime import CI, DEVICE, FF, GLib, IP, NAME, Path, controller_category, dbus, json, logging, threading, time, yaml

class InputPlumberService(dbus.service.Object):
    def composite(self):
        manager = self.bus.get_object(IP, '/org/shadowblip/InputPlumber')
        objects = manager.GetManagedObjects(dbus_interface='org.freedesktop.DBus.ObjectManager')
        candidates=[path for path,interfaces in objects.items() if CI in interfaces and
                    (not DEVICE.composite_match or DEVICE.composite_match in str(interfaces[CI].get('Name','')))]
        if len(candidates)==1: return self.bus.get_object(IP,candidates[0])
        raise RuntimeError('InputPlumber controller is unavailable or ambiguous; configure composite_match')

    def configure_input(self):
        obj = self.composite()
        selected = next((item for item in self.input_profiles() if item['id'] == self.prefs['joystick']), None)
        if selected is None:
            raise ValueError('Selected InputPlumber profile is unavailable')
        base = selected['path']
        profile = yaml.safe_load(Path(base).read_text())
        self.controller_profile_name = selected['name']
        output = self.prefs.get('controller_output','')
        if output:
            plans = self.controller_plans(obj)
            choice = next((item for item in plans['outputs'] if item['id'] == output),None)
            if choice is None: raise ValueError('Selected output controller is unavailable')
            current = plans['target_types']
            # Keep auxiliary devices and replace only gamepad targets.
            gamepads = {item['id'] for item in plans['outputs']}
            targets = list(dict.fromkeys([output,*[kind for kind in current if kind not in gamepads],'mouse','keyboard']))
            profile.pop('target_devices',None)
            if set(targets) != set(current): profile['target_devices'] = targets
            self.controller_output_name = choice['name']
        profile['name'] = DEVICE.profile_prefix+' '+self.prefs['joystick']
        profile['mapping'] = [m for m in profile.get('mapping', []) if m.get('source_event', {}).get('gamepad', {}).get('button') not in ('Guide', 'QuickAccess2')]
        for button, event in [('Guide', 'ui_guide'), ('QuickAccess2', 'ui_back'), ('LeftStick','ui_left_stick'), ('RightStick','ui_right_stick')]:
            profile['mapping'].append({'name': button, 'source_event': {'gamepad': {'button': button}}, 'target_events': [{'dbus': event}]})
            if button in ('LeftStick','RightStick'): profile['mapping'][-1]['target_events'].append({'gamepad':{'button':button}})
        obj.LoadProfileFromYaml(yaml.safe_dump(profile), dbus_interface=CI)
        obj.Set(FF, 'Enabled', dbus.Boolean(self.prefs['vibration'],variant_level=1), dbus_interface='org.freedesktop.DBus.Properties')
        properties = obj.GetAll(FF, dbus_interface='org.freedesktop.DBus.Properties')
        self.vibration_gain_supported = 'RumbleGain' in properties
        if self.vibration_gain_supported:
            obj.Set(FF, 'RumbleGain', dbus.Double(self.prefs['vibration_gain']/100,variant_level=1), dbus_interface='org.freedesktop.DBus.Properties')
        self.ip_ready = True

    def input_profiles(self):
        profiles = []
        folder = Path('/usr/share/inputplumber/profiles')
        for path in sorted(folder.glob('*.yaml')):
            try:
                profile = yaml.safe_load(path.read_text())
                if not isinstance(profile, dict) or profile.get('kind') != 'DeviceProfile' or profile.get('version') != 1:
                    continue
                identity = {'default.yaml':'gamepad', 'mouse_keyboard_wasd.yaml':'mouse'}.get(path.name, 'profile:'+path.name)
                profiles.append({'id':identity, 'name':str(profile.get('name',path.stem)), 'description':str(profile.get('description','')), 'path':str(path)})
            except (OSError, ValueError, yaml.YAMLError):
                logging.warning('Skipping unreadable InputPlumber profile: %s',path)
        return profiles

    @dbus.service.method(NAME, in_signature='', out_signature='s')
    def InputProfiles(self):
        return json.dumps(self.input_profiles())

    def controller_plans(self,obj=None):
        obj = obj or self.composite()
        props = 'org.freedesktop.DBus.Properties'
        manager = self.bus.get_object(IP,'/org/shadowblip/InputPlumber/Manager',introspect=False)
        ids = manager.Get('org.shadowblip.InputManager','SupportedTargetDeviceIds',dbus_interface=props)
        names = manager.Get('org.shadowblip.InputManager','SupportedTargetDevices',dbus_interface=props)
        auxiliary = {'null','dbus','mouse','keyboard','touchpad','touchscreen','debug'}
        outputs = [{'id':str(identity),'name':str(name)} for identity,name in zip(ids,names) if str(identity) not in auxiliary]
        # Classification is metadata only; never replace the upstream name or ID.
        for item in outputs:
            item['category'] = controller_category(item['name'])
        target_types = []
        for path in obj.Get(CI,'TargetDevices',dbus_interface=props):
            target = self.bus.get_object(IP,path,introspect=False)
            target_types.append(str(target.Get('org.shadowblip.Input.Target','DeviceType',dbus_interface=props)))
        current = next((item for item in outputs if item['id'] in target_types),None)
        if current: self.controller_output_name = current['name']
        return {'profiles':self.input_profiles(),'outputs':outputs,'target_types':target_types,
                'profile':self.prefs['joystick'],'output':self.prefs.get('controller_output','') or (current['id'] if current else '')}

    @dbus.service.method(NAME, in_signature='', out_signature='s', async_callbacks=('reply','error'))
    def ControllerPlans(self,reply=None,error=None):
        def collect():
            try:
                result = json.dumps(self.controller_plans())
                GLib.idle_add(lambda: (reply(result),False)[1])
            except Exception as exc:
                GLib.idle_add(lambda e=exc: (error(dbus.exceptions.DBusException(str(e),name=NAME+'.Failed')),False)[1])
        threading.Thread(target=collect,daemon=True).start()

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

