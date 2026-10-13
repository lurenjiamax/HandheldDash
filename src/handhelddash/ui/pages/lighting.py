# SPDX-License-Identifier: LGPL-3.0-or-later
from handhelddash.ui.common import QColor, QColorDialog, QFormLayout, QHBoxLayout, QLabel, QProcess, QTimer, QVBoxLayout, Qt, array, math, sys, time, tr
from handhelddash.ui.widgets.buttons import StateButton
from handhelddash.ui.widgets.lighting import LightingPad
from handhelddash.ui.widgets.sliders import TouchSlider

class LightingPageMixin:
    @staticmethod
    def lighting_choices():
        return [('off','Lights off','lightbulb-off'),('battery','Battery lights','battery'),('static','Static lights','palette'),('audio','Audio reactive','volume-2')]

    def make_lighting(self):
        self.lighting_index = self.tabs.count()
        layout = self.page('Lighting')
        self.lighting_mode = StateButton('Lighting',self.lighting_choices(),self.set_rgb_mode); layout.addWidget(self.lighting_mode)
        form = QFormLayout(); layout.addLayout(form)
        self.lighting_brightness = TouchSlider(Qt.Orientation.Horizontal); self.lighting_brightness.setRange(0,255)
        self.lighting_brightness.edited.connect(lambda n:self.set('rgb-brightness',[str(n)]))
        dialog,box=self.adjustment_dialog('lighting','Lighting brightness'); box.insertWidget(1,self.lighting_brightness)
        form.addRow(QLabel('Lighting brightness'),self.button('Adjust',lambda:self.open_adjustment('lighting')))
        self.lighting_basic_form = form
        self.lighting_pads = []
        rings = QHBoxLayout(); layout.addLayout(rings)
        for side,title,default in [('left','Left stick light','#0080ff'),('right','Right stick light','#c050ff')]:
            column = QVBoxLayout(); rings.addLayout(column,1)
            label = QLabel(title); label.setAlignment(Qt.AlignmentFlag.AlignCenter); column.addWidget(label)
            self.prefs.setdefault('lighting_'+side,default)
            settings = self.prefs.get('lighting_range_'+side,{})
            pad = LightingPad(float(settings.get('minimum',0)),float(settings.get('maximum',self.state.get('rgb_brightness',255)/255)),float(settings.get('sensitivity',self.prefs.get('lighting_gain',4))))
            pad.edited.connect(lambda low,high,gain,k=side:self.set_pref('lighting_range_'+k,{'minimum':low,'maximum':high,'sensitivity':gain}))
            pad.colorChosen.connect(lambda color,k=side:self.set_ring_color(k,color))
            pad.detent.connect(lambda:self.call('Feedback',[],quiet=True))
            column.addWidget(pad); self.lighting_pads.append(pad)
        label = QLabel('X: minimum/maximum brightness; Y: sensitivity.'); label.setWordWrap(True); layout.addWidget(label)
        self.lighting_status = QLabel('—'); self.lighting_status.setWordWrap(True)
        layout.addStretch()
        self.capture = None; self.capture_buffer = b''; self.capture_source = None
        self.monitor_query = False; self.frame_pending = False; self.lighting_levels = [0.,0.]
        self.lighting_timer = QTimer(self); self.lighting_timer.setInterval(50); self.lighting_timer.timeout.connect(self.lighting_tick)

    def set_ring_color(self,side,value):
        color=QColor(value)
        if not color.isValid(): return
        self.set_pref('lighting_'+side,color.name())
        self.set('lighting-color',[side,*map(str,(color.red(),color.green(),color.blue()))])
        pad=self.lighting_pads[0 if side=='left' else 1]; pad.color=color; pad.update()

    def stop_lighting(self):
        self.lighting_timer.stop()
        process = self.capture; self.capture = None; self.capture_source = None; self.capture_buffer = b''
        if process:
            process.terminate()
            QTimer.singleShot(500,lambda:process.kill() if process.state()!=QProcess.ProcessState.NotRunning else None)
            QTimer.singleShot(700,process.deleteLater)
        self.lighting_levels = [0.,0.]; self.lighting_sent_colors = None
        for side,pad in zip(('left','right'),self.lighting_pads): pad.set_output(self.prefs['lighting_'+side],0)

    def sync_lighting(self,mode):
        self.lighting_basic_form.setRowVisible(0,mode != 'audio')
        for pad in self.lighting_pads: pad.controls_enabled = mode == 'audio'
        if mode != 'audio':
            if self.capture: self.stop_lighting()
            for side,pad in zip(('left','right'),self.lighting_pads):
                rgb=self.state.get('lighting_output',{}).get(side,[0,0,0]); peak=max(rgb)
                color=QColor.fromRgb(*[round(v*255/peak) if peak else 0 for v in rgb])
                if not pad.color_open: pad.set_output(color,peak/255)
            self.lighting_status.setText(tr('Audio reactive lighting is off')); return
        if self.monitor_query or time.monotonic()-getattr(self,'monitor_query_time',0) < 10: return
        self.monitor_query_time = time.monotonic()
        self.monitor_query = True
        query = QProcess(self)
        def done(code=1,*args):
            self.monitor_query = False
            source = bytes(query.readAllStandardOutput()).decode().strip()+'.monitor'
            query.deleteLater()
            if code or source == '.monitor':
                self.lighting_status.setText(tr('Cannot capture playback audio')); return
            if (self.state.get('lighting_mode') or self.state.get('rgb_mode')) != 'audio' or self.write_queue or self.write_active: return
            if self.capture and source == self.capture_source: return
            self.stop_lighting(); self.capture_source = source
            process = QProcess(self); self.capture = process
            def read_audio():
                data = bytes(process.readAllStandardOutput())
                if self.capture is process:
                    self.capture_buffer += data
                    excess = max(0,(len(self.capture_buffer)-6400)//8*8)
                    self.capture_buffer = self.capture_buffer[excess:]
            def ended(code=1,*args):
                if self.capture is process:
                    self.capture = None; self.capture_source = None; self.capture_buffer = b''
                    self.lighting_status.setText(tr('Cannot capture playback audio')+' · '+bytes(process.readAllStandardError()).decode(errors='replace'))
                    process.deleteLater()
            process.readyReadStandardOutput.connect(read_audio); process.finished.connect(ended)
            process.errorOccurred.connect(lambda e:ended() if e==QProcess.ProcessError.FailedToStart else None)
            process.start('parec',['--device='+source,'--raw','--format=float32le','--rate=8000','--channels=2','--channel-map=front-left,front-right','--latency-msec=50','--client-name=HandheldDash Lighting'])
            self.lighting_status.setText(tr('Playback source')+' · '+tr('Headphones' if 'headphone' in source.lower() else 'Speakers'))
            self.lighting_status.setToolTip(source); self.lighting_levels = [0.,0.]; self.lighting_targets = [0.,0.]; self.lighting_reference = .01; self.lighting_last_audio = self.lighting_last_tick = time.monotonic(); self.lighting_timer.start()
        query.finished.connect(done)
        query.errorOccurred.connect(lambda e:done() if e==QProcess.ProcessError.FailedToStart else None)
        query.start('pactl',['get-default-sink'])

    def lighting_tick(self):
        now = time.monotonic(); elapsed = max(0.,min(.25,now-getattr(self,'lighting_last_tick',now)))
        self.lighting_last_tick = now
        count = len(self.capture_buffer)//8*8
        data = self.capture_buffer[:count]; self.capture_buffer = self.capture_buffer[count:]
        samples = array('f'); samples.frombytes(data)
        if sys.byteorder != 'little': samples.byteswap()
        rms_channels=[]
        for channel in (0,1):
            values=samples[channel::2]
            rms=math.sqrt(sum(v*v for v in values)/len(values)) if values else 0.
            rms_channels.append(rms if math.isfinite(rms) else 0.)
        if samples:
            self.lighting_last_audio = now
            peak=max(rms_channels)
            # Shared peak reference preserves stereo balance; freeze gain during silence.
            if peak > .0008:
                self.lighting_reference=max(.001,peak,self.lighting_reference*math.exp(-elapsed/5.))
        colors = []
        for channel,side in enumerate(('left','right')):
            rms = rms_channels[channel]
            pad = self.lighting_pads[channel]
            sensitivity=math.log(pad.sensitivity)/math.log(20)
            threshold=.12-.10*sensitivity
            normalized=max(0.,min(1.,(rms/self.lighting_reference-threshold)/(1-threshold))) if rms > .0008 else 0.
            response=.9*normalized**(1.6-.8*sensitivity)
            if samples:
                self.lighting_targets[channel] = pad.minimum+(pad.maximum-pad.minimum)*response if response else 0.
            elif now-self.lighting_last_audio > .2: self.lighting_targets[channel] = 0.
            target = self.lighting_targets[channel]
            previous = self.lighting_levels[channel]
            tau = .09 if target > previous else .28
            level = previous+(target-previous)*(-math.expm1(-elapsed/tau))
            if target == 0 and level < .002: level=0.
            self.lighting_levels[channel] = level
            pad.set_output(self.prefs['lighting_'+side],level)
            color = QColor(self.prefs['lighting_'+side])
            scale = level
            colors.extend(round(v*scale) for v in (color.red(),color.green(),color.blue()))
        if not self.frame_pending and (colors != getattr(self,'lighting_sent_colors',None) or now-getattr(self,'lighting_sent_time',0) >= 1):
            self.frame_pending = True
            def sent(ok,busy):
                self.frame_pending = False
                if ok: self.lighting_sent_colors = colors; self.lighting_sent_time = now
            self.call('LightingFrame',colors,quiet=True,finished=sent)

    def set_rgb_mode(self,value):
        self.stop_lighting()
        self.set('lighting-mode',[value])

    def choose_color(self):
        color = QColorDialog.getColor(QColor(self.state.get('rgb_static_hex','#0080ff')),self,'Lighting color')
        if color.isValid(): self.set('rgb-color',list(map(str,[color.red(),color.green(),color.blue()])))

