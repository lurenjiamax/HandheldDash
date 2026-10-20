# SPDX-License-Identifier: LGPL-3.0-or-later
from handhelddash.services.runtime import CTL, DEVICE, GLib, NAME, Path, dbus, json, number, os, re, read, run, threading, time

class TelemetryService(dbus.service.Object):
    def collect_status(self):
        try:
            monitoring=self.monitoring; active=set(monitoring['items']); modes=monitoring['modes']
            now = time.monotonic()
            config = Path(DEVICE.hardware_config) if DEVICE.hardware_config else None
            stamp = config.stat().st_mtime_ns if config and config.is_file() else 0
            if self.hardware_status is None or stamp != self.hardware_config_stamp or now-self.hardware_status_time >= 15:
                self.hardware_status = self.backend.status()
                self.cached_fan_status = self.backend.fan_status()
                self.hardware_status_time = now; self.hardware_config_stamp = stamp
            data = self.hardware_status.copy()
            data['device'] = DEVICE.capabilities()
            data['device']['hardware_control'] = self.backend.available
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
            battery = DEVICE.battery+'/' if DEVICE.battery else '/nonexistent/handhelddash/battery/'
            data['battery'] = {'capacity':number(battery+'capacity'),'temp':None,'current_now':None,'voltage_now':None}
            if 'battery' in active:
                data['battery'].update({key:number(battery+key,scale) for key,scale in [('temp',10),('current_now',1e6),('voltage_now',1e6)]})
            data['battery']['status'] = read(battery + 'status')
            data['battery']['charge_type'] = read(battery+'charge_type','Unknown')
            usb=Path(DEVICE.charger or '/nonexistent/handhelddash/charger')
            protocol=re.search(r'\[([^]]+)\]',read(usb/'usb_type',''))
            data['battery']['charging_protocol'] = protocol.group(1) if protocol else 'Unknown'
            data['battery']['charger_connected'] = bool(number(usb/'online'))
            data['battery']['fast_charging'] = data['battery']['charger_connected'] and (data['battery']['charging_protocol'] in ('PD','PD_PPS') or (number(usb/'voltage_now') or 0) > 5500000)
            data['temperature_sensors'] = [{'id':read(p/'type',p.name),'name':read(p/'type',p.name),'temperature':number(p/'temp',1000)} for p in sorted(Path('/sys/class/thermal').glob('thermal_zone*'),key=lambda p:int(p.name.removeprefix('thermal_zone')))] if 'temperature' in active else []
            # power_now is inconsistent on this BSP; derive watts from voltage and current.
            current = data['battery']['current_now']
            voltage = data['battery']['voltage_now']
            # This BSP reports battery current positive into, negative out of the battery.
            data['battery']['watts'] = current * voltage if current is not None and voltage is not None else None
            data['cpu_mhz'] = max((number(p, 1000) or 0 for p in Path('/sys/devices/system/cpu/cpufreq').glob('policy*/scaling_cur_freq')), default=0) if 'cpu' in active and modes.get('cpu') != 'percent' else None
            data['gpu_mhz'] = number(DEVICE.gpu_path('cur_freq'), 1e6) if 'gpu' in active and modes.get('gpu') != 'percent' else None
            now = time.monotonic()
            data['gpu_percent'] = self.gpu_utilization.read('gpu' in active and modes.get('gpu')=='percent')
            data['load_average'] = list(os.getloadavg()) if 'load' in active else []
            for section in ('network','disk_io'):
                if section not in active:
                    self.io_previous[section]={}; self.io_times[section]=0; self.io_rates[section]={}; continue
                if now-self.io_times[section]<1: continue
                counters={}; disks={}
                if section == 'network':
                    for line in Path('/proc/net/dev').read_text().splitlines()[2:]:
                        name,values=line.split(':',1); values=values.split(); counters[name.strip()]=(int(values[0]),int(values[8]))
                else:
                    disks={p.name:p for p in Path('/sys/block').iterdir() if not p.name.startswith(('loop','ram','zram'))}
                    for line in Path('/proc/diskstats').read_text().splitlines():
                        values=line.split()
                        if len(values)>=10 and values[2] in disks: counters[values[2]]=(int(values[5])*512,int(values[9])*512)
                elapsed=now-self.io_times[section]; rates={}
                for name,values in counters.items():
                    previous=self.io_previous[section].get(name)
                    rates[name]=[max(0,current-old)/elapsed for current,old in zip(values,previous)] if previous is not None and self.io_times[section] else [None,None]
                members=[name for name in rates if name != 'lo'] if section == 'network' else [name for name in rates if (disks[name]/'device').exists()]
                rates['all']=[sum(rates[name][index] for name in members if rates[name][index] is not None) if self.io_times[section] else None for index in (0,1)]
                self.io_rates[section]=rates; self.io_previous[section]=counters; self.io_times[section]=now
            data.update(self.io_rates)
            hwmon = [p for p in Path('/sys/class/hwmon').glob('*') if read(p / 'name') == DEVICE.fan_name] if 'fan' in active and DEVICE.fan_name else []
            data['fan_rpm'], data['fan_percent'], data['fan_rpm_source'] = self.fan_reading(hwmon[0]) if hwmon else (None,None,'unavailable')
            data['cpu_max_mhz'] = max((number(p,1000) or 0 for p in Path('/sys/devices/system/cpu/cpufreq').glob('policy*/cpuinfo_max_freq')),default=0) or None if 'cpu' in active and modes.get('cpu') != 'percent' else None
            data['gpu_max_mhz'] = number(DEVICE.gpu_path('max_freq'),1e6) if 'gpu' in active and modes.get('gpu') != 'percent' else None
            mode_governors = {mode:tuple(values[:2]) for mode,values in DEVICE.performance_modes.items()}
            if (data.get('cpu_governor'),data.get('gpu_governor')) != mode_governors.get(data['performance']):
                data['performance'] = 'custom'
            data['cpu_governor_actual'] = read('/sys/devices/system/cpu/cpufreq/policy0/scaling_governor')
            data['gpu_governor_actual'] = read(DEVICE.gpu_path('governor'))
            data['ram_used_gb']=None; data['ram_total_gb']=None; data['cpu_percent']=None
            if 'memory' in active:
                mem = {line.split(':')[0]: int(line.split()[1]) for line in Path('/proc/meminfo').read_text().splitlines() if len(line.split()) > 1 and line.split()[1].isdigit()}
                data['ram_used_gb'] = (mem['MemTotal'] - mem['MemAvailable']) / 1048576; data['ram_total_gb'] = mem['MemTotal'] / 1048576
            if 'cpu' in active and modes.get('cpu') == 'percent':
                fields = list(map(int, Path('/proc/stat').read_text().splitlines()[0].split()[1:9])); total, idle = sum(fields), fields[3] + fields[4]
                if self.cpu_previous is not None:
                    old_total,old_idle=self.cpu_previous; data['cpu_percent']=100*(1-(idle-old_idle)/(total-old_total)) if total>old_total else 0
                self.cpu_previous=total,idle
            else: self.cpu_previous=None
            data['backlight'] = {name: {'value': number('/sys/class/backlight/' + node + '/brightness'), 'max': number('/sys/class/backlight/' + node + '/max_brightness')} for name, node in DEVICE.backlights.items()}
            data['bypass_supported'] = False
            data['bypass_reason'] = 'No verified bypass charging backend for this device'
            data['fan_control'] = self.cached_fan_status
            data['ufs_irqs']=self.ufs_irqs()
            data['input_ready'] = self.ip_ready
            data['vibration_gain_supported'] = self.ip_ready and self.vibration_gain_supported
            data['controller_profile_name'] = self.controller_profile_name
            data['controller_output_name'] = self.controller_output_name
            data['layout_supported'] = False
            data['layout_reason'] = 'No controller layout backend for this device'
            self.cached_status = json.dumps(data)
            return self.cached_status
        except (RuntimeError, OSError, ValueError) as e:
            raise dbus.exceptions.DBusException(str(e), name=NAME + '.Failed')

    @dbus.service.method(NAME, in_signature='s', out_signature='')
    def SetMonitoring(self,raw):
        config=json.loads(raw); known={'cpu','gpu','temperature','fan','memory','battery','load','network','disk_io'}
        self.monitoring={'items':[key for key in config.get('items',[]) if isinstance(key,str) and key in known],'modes':{key:config.get('modes',{}).get(key,'mhz') for key in ('cpu','gpu')}}

    @dbus.service.method(NAME, in_signature='s', out_signature='s')
    def MonitoringDevices(self,kind):
        root=Path('/sys/class/net') if kind == 'network' else Path('/sys/block')
        return json.dumps(sorted(p.name for p in root.iterdir() if kind == 'network' or not p.name.startswith(('loop','ram','zram'))))

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
        data['vibration_gain_supported'] = self.ip_ready and self.vibration_gain_supported
        data['controller_profile_name'] = self.controller_profile_name
        data['controller_output_name'] = self.controller_output_name
        data['backlight'] = {name: {'value': number('/sys/class/backlight/' + node + '/brightness'), 'max': number('/sys/class/backlight/' + node + '/max_brightness')} for name, node in DEVICE.backlights.items()}
        self.cached_status = json.dumps(data)
        return self.cached_status
