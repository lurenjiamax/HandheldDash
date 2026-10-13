# SPDX-License-Identifier: LGPL-3.0-or-later
from handhelddash.services.runtime import CTL, DEVICE, NAME, Path, cpu_set, dbus, format_cpu_set, logging, number, re, read, run, struct, time

class ThorchService(dbus.service.Object):
    def initialize_fan(self):
        if not DEVICE.fan_reset_workaround: return
        for hwmon in Path('/sys/class/hwmon').glob('*'):
            if read(hwmon/'name') != DEVICE.fan_name: continue
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
        if not CTL: raise ValueError('UFS IRQ policy is unavailable on this device')
        if mode not in ('system','powersave','performance'): raise ValueError('Invalid UFS IRQ mode')
        irqs=self.ufs_irqs()
        if not irqs: raise RuntimeError('No ufshcd interrupt found')
        if any(not irq['requested'] or not irq['effective'] for irq in irqs): raise RuntimeError('UFS IRQ affinity is unavailable')
        online=cpu_set(read('/sys/devices/system/cpu/online'))
        selected=set(DEVICE.irq_cpu_sets.get(mode,[])) & online
        target=format_cpu_set(selected)
        if mode!='system' and not target: raise RuntimeError('Selected UFS CPUs are offline')
        originals=self.prefs.setdefault('ufs_irq_original',{})
        previous=[]
        try:
            for irq in irqs:
                node=Path('/proc/irq')/str(irq['irq'])
                originals.setdefault(irq['name'],irq['requested'])
                desired=originals[irq['name']] if mode=='system' else target
                if irq['requested']==desired:
                    if mode=='system' or (cpu_set(irq['effective']) and cpu_set(irq['effective'])<=selected): continue
                previous.append((node,irq['requested']))
                (node/'smp_affinity_list').write_text(desired+'\n')
                effective=read(node/'effective_affinity_list')
                if mode!='system' and (not effective or not cpu_set(effective)<=selected):
                    raise RuntimeError('UFS IRQ did not move to configured CPUs '+target)
        except Exception:
            for node,old in reversed(previous):
                try: (node/'smp_affinity_list').write_text(old+'\n')
                except OSError: logging.exception('Restore UFS IRQ affinity failed')
            raise

    def maintain_ufs_irq(self):
        if not CTL: return True
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

    def save_fan_curve(self, values):
        if len(values) != 14: raise ValueError('A custom fan curve requires seven temperatures and seven PWM values')
        numbers = list(map(int,values)); temps = numbers[:7]; speeds = numbers[7:]
        if not all(20000 <= t <= 95000 for t in temps) or any(a >= b for a,b in zip(temps,temps[1:])):
            raise ValueError('Fan temperatures must strictly increase within 20..95 °C')
        if not all(0 <= s <= 255 for s in speeds) or any(a > b for a,b in zip(speeds,speeds[1:])) or speeds[-1] != 255:
            raise ValueError('Fan PWM must increase within 0..255 and end at 255')
        if not DEVICE.hardware_config or not DEVICE.fan_service: raise ValueError('Fan curve backend is unavailable')
        config = Path(DEVICE.hardware_config); original = config.read_text()
        changes = dict(zip(['THORCH_FAN_T'+str(i) for i in range(1,7)]+['THORCH_FAN_MAX_TEMP']+['THORCH_FAN_CUSTOM_SPEED'+str(i) for i in range(1,7)]+['THORCH_FAN_CUSTOM_MAX_SPEED'],numbers))
        changes['THORCH_FAN_PROFILE'] = 'custom'
        text = original
        for key,value in changes.items():
            line = f'{key}={value}'
            if re.search(r'^'+key+r'=.*$',text,re.M): text = re.sub(r'^'+key+r'=.*$',line,text,flags=re.M)
            else: text += '\n'+line+'\n'
        stage = config.with_suffix('.new'); stage.write_text(text); stage.chmod(config.stat().st_mode & 0o777); stage.replace(config)
        try:
            run('systemctl','reset-failed',DEVICE.fan_service)
            run('systemctl','start',DEVICE.fan_service)
            run('systemctl','is-active','--quiet',DEVICE.fan_service)
        except Exception:
            stage.write_text(original); stage.chmod(config.stat().st_mode & 0o777); stage.replace(config)
            run('systemctl','reset-failed',DEVICE.fan_service)
            run('systemctl','start',DEVICE.fan_service)
            raise

