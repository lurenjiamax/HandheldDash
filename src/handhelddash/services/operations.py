# SPDX-License-Identifier: LGPL-3.0-or-later
from handhelddash.services.runtime import CTL, DEVICE, FF, NAME, Path, STATE, atomic_json, dbus, ecodes, json, logging, os, read, run, subprocess, time

class OperationService(dbus.service.Object):
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
            lines += [f'fps_limit={limit}',f'no_display={int(not hud)}','autostart_log=0']
            # Keep the inode for MangoHud's configuration hot reload.
            content='\n'.join(lines)+'\n'
            if not config.exists() or config.read_text(encoding='utf-8') != content:
                config.write_text(content,encoding='utf-8')
        self.prefs.update(mangohud_mode=mode,mangohud_limit=limit,mangohud_hud=hud)

    def apply(self, operation, values, uid=0):
        operation, values = str(operation), list(map(str, values))
        if operation == 'task-affinity':
            if len(values) != 3: raise ValueError('Invalid affinity arguments')
            self.set_task_affinity(int(values[0]),values[1],values[2],uid)
            return self.quick_status()
        if operation == 'kill-task':
            if len(values) != 2: raise ValueError('Invalid task arguments')
            self.kill_task(int(values[0]),values[1],uid)
            return self.quick_status()
        self.hardware_status = None
        if operation.startswith(('rgb-','lighting-')):
            with self.led_lock: self.led_written.clear()
        arities = {'scheduler': 1, 'cpu-boost': 1, 'cpu-governor': 1, 'gpu-governor': 1, 'governors': 2, 'fan-profile': 1, 'fan-sensor-mode': 1, 'fan-state': 2, 'rgb-mode': 1, 'rgb-brightness': 1, 'rgb-color': 3, 'rgb-state': 5}
        if operation in set(arities)|{'performance','smart','fan-curve','fan-follow-performance','lighting-mode'} and not self.backend.available:
            raise ValueError('Hardware control is not supported by the selected device adapter')
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
                    self.backend.set('rgb-mode','off' if values == ['audio'] else values[0])
                    self.prefs['lighting_mode'] = 'audio' if values == ['audio'] else None
                    self.led_last_frame = time.monotonic()
            elif operation == 'fan-curve':
                self.save_fan_curve(values)
                self.prefs['fan_follow_performance'] = False
            elif operation == 'fan-follow-performance' and values in (['on'],['off']):
                if values == ['on']:
                    profile = DEVICE.performance_modes.get(self.prefs['performance'],DEVICE.performance_modes['standard'])[2]
                    self.backend.set('fan-profile',profile)
                else:
                    self.backend.set('fan-profile','custom')
                self.prefs['fan_follow_performance'] = values == ['on']
            elif operation in arities and len(values) == arities[operation]:
                if any(len(v) > 32 for v in values):
                    raise ValueError('Value too long')
                self.backend.set(operation,*values)
                if operation in ('fan-profile','fan-state'): self.prefs['fan_follow_performance'] = False
                if operation in ('rgb-mode','rgb-state'): self.prefs['lighting_mode'] = None
                if operation in ('cpu-governor','gpu-governor','governors'):
                    self.prefs['smart'] = False
            elif operation == 'performance' and len(values) == 1:
                modes = DEVICE.performance_modes
                cpu, gpu, fan, boost = modes[values[0]]
                self.backend.set('governors',cpu,gpu)
                if self.prefs['fan_follow_performance']: self.backend.set('fan-profile',fan)
                self.backend.set('cpu-boost',boost)
                self.prefs['performance'] = values[0]
                self.prefs['smart'] = False
            elif operation == 'smart' and values in (['on'], ['off']):
                if values == ['on']:
                    cpu,gpu,fan,_=DEVICE.performance_modes['standard']
                    self.backend.set('governors',cpu,gpu)
                    if self.prefs['fan_follow_performance']: self.backend.set('fan-profile',fan)
                self.prefs['smart'] = values == ['on']
                if values == ['on']:
                    self.prefs['performance'] = 'standard'
            elif operation == 'controller-plan' and len(values) == 2:
                plans = self.controller_plans()
                if values[0] not in {item['id'] for item in plans['profiles']} or values[1] not in {item['id'] for item in plans['outputs']}:
                    raise ValueError('Unknown controller plan')
                previous = self.prefs['joystick'],self.prefs.get('controller_output','')
                self.prefs['joystick'],self.prefs['controller_output'] = values
                try:
                    self.configure_input()
                except Exception:
                    self.prefs['joystick'],self.prefs['controller_output'] = previous
                    self.ip_ready = False
                    raise
            elif operation == 'joystick' and len(values) == 1 and values[0] in {item['id'] for item in self.input_profiles()}:
                previous = self.prefs['joystick']
                self.prefs['joystick'] = values[0]
                try:
                    self.configure_input()
                except Exception:
                    self.prefs['joystick'] = previous
                    raise
            elif operation == 'vibration-gain' and len(values) == 1:
                percent = int(values[0])
                if not 0 <= percent <= 200:
                    raise ValueError('Vibration gain must be 0..200')
                if not self.ip_ready or not self.vibration_gain_supported:
                    raise ValueError('This InputPlumber version does not support RumbleGain')
                obj = self.composite()
                obj.Set(FF, 'RumbleGain', dbus.Double(percent/100,variant_level=1), dbus_interface='org.freedesktop.DBus.Properties')
                self.prefs['vibration_gain'] = percent
                if self.prefs['vibration'] and percent > 0:
                    # InputPlumber applies the new gain; do not scale twice here.
                    try:
                        try:
                            obj.Rumble(dbus.Double(0.55), dbus_interface=FF)
                            time.sleep(0.12)
                        finally:
                            obj.Stop(dbus_interface=FF)
                    except Exception:
                        logging.exception('Vibration gain preview failed')
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
                targets=['top','bottom'] if values[0]=='both' else [values[0]]
                if any(target not in DEVICE.backlights for target in targets): raise ValueError('Requested backlight is unavailable')
                with self.display_lock:
                    if any(target in self.screen_holds for target in targets): raise ValueError('Restore the screen before changing brightness')
                    for target in targets:
                        node = DEVICE.backlights.get(target)
                        if not node: raise ValueError('Backlight is unavailable for '+target)
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
            return self.quick_status() if operation in ('brightness','key','clean-memory','vibration','vibration-gain','joystick','controller-plan') else self.collect_status()
        except (RuntimeError, ValueError, KeyError, OSError, subprocess.SubprocessError, dbus.DBusException) as e:
            raise dbus.exceptions.DBusException(str(e), name=NAME + '.Failed')
