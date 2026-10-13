# SPDX-License-Identifier: LGPL-3.0-or-later
from handhelddash.ui.common import DATA
from handhelddash.ui.common import DEVICE
from handhelddash.ui.common import Path
from handhelddash.ui.common import csv
from handhelddash.ui.common import dashboard_layout
from handhelddash.ui.common import json
from handhelddash.ui.common import time
from handhelddash.ui.common import tr

class StatusPresenterMixin:
    def call(self, method, args, callback=None, quiet=False, finished=None):
        if method not in ('Status','SetMonitoring','MonitoringDevices','LightingFrame','Feedback','Pointer'): self.error_text = None
        def done(success,busy):
            if method == 'Status': self.status_busy = False
            if success and not callback and not quiet: self.notify('Settings applied')
            if finished: finished(success,busy)
        self.client.request(method,args,callback,done)

    def hardware_error(self,text):
        self.error_text=text; self.notify(text)

    def receive_status(self,raw):
        try: self.update_state(raw)
        except (ValueError,KeyError,IndexError) as exc: self.hardware_error('Invalid response: '+str(exc))

    def set(self, operation, values, finished=None):
        self.client.set(operation,values,finished)

    @property
    def write_queue(self): return self.client.queue

    @property
    def write_active(self): return self.client.active

    @property
    def write_revision(self): return self.client.revision

    def mutation_finished(self,operation,values,success,busy):
        if success and operation=='fan-curve' and self.fan_graph.curve and values==list(map(str,self.fan_graph.curve['temperatures']+self.fan_graph.curve['pwm'])):
            self.fan_dirty=False; self.update_fan()
        if not self.write_queue and not success and not busy and self.state: self.update_state(json.dumps(self.state))

    def update_state(self, raw):
        self.state = json.loads(raw)
        supported=self.state.get('device',DEVICE.capabilities()).get('hardware_control',False)
        for widget in (self.performance,self.fan_link_control,self.rgb,self.lighting_mode): widget.setEnabled(supported)
        if not self.write_queue:
            self.prefs['mangohud_mode']=self.state.get('mangohud_mode','release')
            self.mango_mode.show_value(self.prefs['mangohud_mode'])
            controlled=self.prefs['mangohud_mode']=='takeover'
            self.fps_mode.setEnabled(controlled and not self.dashboard_editing); self.hud.setEnabled(controlled)
            self.fan_link_control.show_value(self.state.get('fan_follow_performance',True))
            self.ufs_irq.show_value(self.state.get('ufs_irq_mode','system'))
            self.vibration.show_value(bool(self.state.get('vibration')))
            self.sync_vibration()
            self.performance.show_value(self.state.get('performance','standard'))
            self.input_mode.show_value(self.state.get('joystick','gamepad'))
            self.input_mode.set_display_state(self.state.get('controller_profile_name') or ('Default' if self.state.get('joystick','gamepad')=='gamepad' else 'Mouse and keyboard'))
            mode = self.state.get('lighting_mode') or self.state.get('rgb_mode','off')
            self.rgb.show_value(mode); self.lighting_mode.show_value(mode)
            self.sync_lighting(mode)
        b = self.state.get('battery',{})
        self.battery_text.setText('—%' if b.get('capacity') is None else f"{b['capacity']:.0f}%")
        status = 'Fast charging' if b.get('fast_charging') and b.get('status') == 'Charging' else 'Slow charging' if b.get('status') == 'Charging' else 'Not charging'
        self.battery_icon.setToolTip(tr(status))
        self.battery_icon.reading((b.get('capacity') or 0)/100,charging=b.get('status') == 'Charging',fast_charging=b.get('fast_charging',False))
        def fmt(v,digits=0): return '—' if v is None else f'{v:.{digits}f}'
        def gauge(key,text,fraction):
            identity={'temp':'temperature','ram':'memory'}.get(key,key)
            if identity not in active: return
            value,bar=self.gauges[key]; value.setText(text); bar.setValue(max(0,min(1000,round((fraction or 0)*1000))))
            self.metric_icons[key].reading(fraction,rpm=self.state.get('fan_rpm') if key == 'fan' else 0,charging=key == 'battery' and b.get('status') == 'Charging')
        configuration=self.dashboard_draft if self.dashboard_editing else dashboard_layout(self.prefs.get('dashboard_layout'))
        active=set(configuration.get('metric_order',['cpu','gpu','temperature','fan','memory','battery'])) if self.dashboard_editing or configuration['metrics'] else set()
        for key in ('cpu','gpu'):
            current=self.state.get(key+'_mhz'); maximum=self.state.get(key+'_max_mhz'); fraction=(current or 0)/maximum if maximum else 0
            unit=configuration.get('metric_modes',{}).get(key,configuration.get('metric_mode','mhz'))
            text=key.upper()+' '+(fmt(self.state.get(key+'_percent'))+'%' if unit == 'percent' else fmt(current)+' / '+fmt(maximum)+' MHz')
            gauge(key,text,fraction); self.gauges[key][0].setToolTip(tr('Utilization unavailable') if unit == 'percent' and self.state.get(key+'_percent') is None else '')
        if 'temperature' in active: self.update_temperature()
        gauge('fan',f"{fmt(self.state.get('fan_rpm'))} RPM",(self.state.get('fan_percent') or 0)/100)
        gauge('ram',f"{fmt(self.state.get('ram_used_gb'),1)} / {fmt(self.state.get('ram_total_gb'),0)} GB",(self.state.get('ram_used_gb') or 0)/(self.state.get('ram_total_gb') or 1))
        load=self.state.get('load_average',[])
        gauge('load',' · '.join(fmt(value,2) for value in load) if len(load)==3 else '— · — · —',0)
        self.gauges['load'][0].setToolTip(tr('1 min · 5 min · 15 min'))
        def speed(value):
            if value is None: return '—'
            for unit in ('B','K','M','G'):
                if value<1024 or unit == 'G': return f'{value:.0f}{unit}/s' if unit == 'B' else f'{value:.1f}{unit}/s'
                value/=1024
        for key,prefixes in [('network',('↓','↑')),('disk_io',('R','W'))]:
            source=configuration.get('metric_sources',{}).get(key,'all'); rates=self.state.get(key,{}).get(source,[None,None])
            gauge(key,' '.join(prefix+speed(value) for prefix,value in zip(prefixes,rates)),0)
            self.gauges[key][0].setToolTip(source+' · '+tr('Bytes per second; K/M/G use powers of 1024'))
        charging=b.get('status') == 'Charging'
        self.power_temperature.setText(f"{fmt(b.get('temp'),1)} °C")
        suffix = ' · '+tr('Fast charging' if b.get('fast_charging') else 'Slow charging') if b.get('charger_connected') else ''
        watts=b.get('watts'); text='—' if watts is None else f'{watts:.1f}' if abs(watts)>=.05 else '0.0'
        gauge('battery',f"{text} W{suffix}",abs(watts or 0)/30)
        self.gauges['battery'][0].setToolTip(tr('Net battery power: negative means discharging; charging label describes the connected source.'))
        self.gauges['fan'][0].setToolTip(f"PWM {fmt(self.state.get('fan_percent'))}% · {self.state.get('fan_rpm_source')}")
        self.update_fan()
        irqs=self.state.get('ufs_irqs',[]); self.ufs_irq.setEnabled(bool(irqs))
        self.boost.show_value(bool(self.state.get('cpu_boost_enabled')))
        for key,widget in self.setting_widgets.items():
            if not self.write_queue and not widget.hasFocus(): widget.show_value(str(self.state.get(key,'')))
        for key,slider in self.sliders.items():
            if slider.isSliderDown() or self.write_queue: continue
            if key == 'both':
                value = sum(100*(v.get('value') or 0)/(v.get('max') or 1) for v in self.state.get('backlight',{}).values())/max(1,len(self.state.get('backlight',{})))
            elif key == 'rgb': value = self.state.get('rgb_brightness',0)
            else:
                item = self.state.get('backlight',{}).get(key,{})
                value = 100 * (item.get('value') or 0) / (item.get('max') or 1)
            slider.setValue(round(value))
        self.notify(self.error_text or '')

    def select_temperature(self,sensor):
        self.set_pref('temperature_sensor',sensor); self.update_temperature()

    def update_temperature(self):
        sensors=self.state.get('temperature_sensors',[])
        self.temperature_button.options=[(s['id'],s['name']+' · '+(f"{s['temperature']:.1f} °C" if s['temperature'] is not None else '— °C'),'thermometer') for s in sensors]
        selected=self.prefs.get('temperature_sensor','battery')
        self.temperature_button.show_value(selected)
        value=next((s['temperature'] for s in sensors if s['id']==selected),None)
        self.gauges['temp'][1].setValue(round(max(0,min(1,(value or 0)/80))*1000))

    def refresh(self):
        now = time.monotonic()
        if not self.isVisible() and now-getattr(self,'background_refresh_time',0) < 10: return
        self.background_refresh_time = now
        self.clock.setText(time.strftime('%H:%M'))
        if self.isVisible(): self.refresh_audio()
        if self.isVisible() and self.tabs.currentIndex() == self.tasks_index: self.refresh_tasks()
        if not self.status_busy and self.write_active is None and not self.write_queue:
            self.sync_monitoring()
            self.status_busy = True
            revision = self.write_revision
            self.call('Status',[],lambda raw:self.update_state(raw) if revision == self.write_revision else None,True)
        configuration=self.dashboard_draft if self.dashboard_editing else dashboard_layout(self.prefs.get('dashboard_layout'))
        files = [p for folder in (DATA/'fps',Path('/var/cache/handhelddash/fps')) if folder.is_dir() for p in folder.glob('*.csv')] if configuration.get('show_fps',True) else []
        files = [p for p in files if not p.name.endswith('_summary.csv') and time.time()-p.stat().st_mtime < 4]
        self.fps.setText('— FPS'); self.fps_source.setText('')
        if files:
            latest = max(files,key=lambda p:p.stat().st_mtime)
            try:
                with latest.open('rb') as f:
                    f.seek(max(0,latest.stat().st_size-8192))
                    lines = f.read().decode(errors='replace').splitlines()
                for line in reversed(lines):
                    columns = next(csv.reader([line]))
                    if len(columns) > 5 and columns[0].replace('.','',1).isdigit():
                        self.fps.setText(f'{float(columns[0]):.0f} FPS')
                        self.fps_source.setText(latest.name.split('_')[0]); break
            except (OSError,ValueError,IndexError): pass

