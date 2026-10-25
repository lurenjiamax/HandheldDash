# SPDX-License-Identifier: LGPL-3.0-or-later
import json
from handhelddash.ui.common import AdjustmentRow, DEVICE, EmbeddedPopup, ICON_SIZE, POPUP_MARGIN, POPUP_WIDTH, QApplication, QHBoxLayout, QLabel, QProcess, QTimer, QVBoxLayout, QWidget, Qt, tr
from handhelddash.ui.widgets.buttons import StateButton
from handhelddash.ui.widgets.icons import control_icon
from handhelddash.ui.widgets.sliders import TouchSlider

class ScreensPageMixin:
    def make_screen(self):
        self.screen_sliders = {}
        self.adjustment_dialogs={}; self.brightness_buttons={}
        brightness_dialog,brightness_layout=self.adjustment_dialog('brightness','Brightness')
        volume_dialog,volume_layout=self.adjustment_dialog('volume','Volume')
        layout=brightness_layout
        row=QHBoxLayout(); self.screen_display_buttons={}
        for role,title in [('top','Top screen visible'),('bottom','Bottom screen visible')]:
            name=DEVICE.screen_name(role,QApplication.screens())
            if not name or name in self.screen_display_buttons: continue
            button=StateButton(title,[(True,title,'monitor'),(False,title.replace('visible','blanked'),'monitor-off')],lambda value,n=name:self.set_screen_display(n,value))
            button.setEnabled(role in DEVICE.touchscreens and role in DEVICE.backlights)
            button.show_value(True); self.screen_display_buttons[name]=button; row.addWidget(button,1)
        layout.addLayout(row)
        note=QLabel('Dark screen locks touch and preserves the desktop layout. Press the Dash key to restore.'); note.setWordWrap(True); layout.addWidget(note)
        brightness_row=QHBoxLayout()
        for key,title in [('both','Both'),('top','Top'),('bottom','Bottom')]:
            row=QHBoxLayout(); icon=QLabel(); icon.setPixmap(control_icon('sun').pixmap(ICON_SIZE,ICON_SIZE)); row.addWidget(icon)
            label=QLabel(title); label.setFixedWidth(46); row.addWidget(label)
            slider=TouchSlider(Qt.Orientation.Horizontal); slider.setRange(1,100); row.addWidget(slider,1)
            slider.setEnabled(len(DEVICE.backlights)>1 if key=='both' else key in DEVICE.backlights)
            value=QLabel('—%'); value.setFixedWidth(46); row.addWidget(value)
            button=self.button(title+' · —%',lambda checked=False:self.open_adjustment('brightness')); button.setIcon(control_icon('sun'))
            brightness_row.addWidget(button,1); self.brightness_buttons[key]=button
            slider.valueChanged.connect(lambda n,l=value,b=button,t=title:(l.setText(f'{n}%'),b.setText(t+f' · {n}%')))
            slider.edited.connect(lambda n,k=key:self.screen_brightness(k,n))
            brightness_layout.addLayout(row); self.screen_sliders[key]=slider
        self.audio_muted=False
        card=AdjustmentRow(self.button('',self.toggle_audio_mute),TouchSlider,100,ICON_SIZE)
        self.volume_icon=card.icon; self.volume=card.slider; self.volume_label=card.label
        self.volume_icon.setAccessibleName(tr('Volume'))
        self.volume_button=self.button('Volume · —%',lambda:self.open_adjustment('volume')); self.volume_button.hide()
        self.volume.edited.connect(lambda n:self.set_audio('set-volume',f'{n}%'))
        self.volume.valueChanged.connect(lambda n:self.update_volume_icon()); volume_layout.insertWidget(1,card)
        row=QHBoxLayout()
        screen_options=[('','Desktop default','panels-top-left')]+[(DEVICE.screen_name(role,QApplication.screens()),title,'monitor') for role,title in [('top','New apps: top'),('bottom','New apps: bottom')] if DEVICE.screen_name(role,QApplication.screens())]
        self.launch_screen=StateButton('New application screen',screen_options,self.set_launch_screen)
        self.launch_screen.setEnabled(self.desktop.supports('placement'))
        self.launch_screen.show_value(self.prefs.get('launch_screen','')); row.addWidget(self.launch_screen,1); layout.addLayout(row)

    def adjustment_dialog(self,key,title):
        dialog=EmbeddedPopup(self); dialog.setWindowTitle(tr(title)); dialog.setMinimumWidth(340)
        box=QVBoxLayout(dialog); heading=QLabel(title); heading.setObjectName('Title'); box.addWidget(heading)
        self.adjustment_dialogs[key]=dialog
        return dialog,box

    def open_vibration(self):
        self.vibration.show_value(bool(self.state.get('vibration')))
        if 'vibration' not in self.adjustment_dialogs:
            dialog,box=self.adjustment_dialog('vibration','Vibration')
            card=AdjustmentRow(self.button('',lambda:self.set('vibration',['off' if self.state.get('vibration') else 'on'])),TouchSlider,200,ICON_SIZE)
            self.vibration_icon=card.icon; self.vibration_gain_slider=card.slider; self.vibration_gain_label=card.label
            self.vibration_gain_slider.edited.connect(lambda value:self.set('vibration-gain',[str(value)]))
            box.addWidget(card)
            self.vibration_gain_slider.setToolTip(tr('Requires InputPlumber with RumbleGain support'))
        self.sync_vibration()
        self.open_adjustment('vibration')

    def sync_vibration(self):
        enabled=bool(self.state.get('vibration')); supported=bool(self.state.get('vibration_gain_supported'))
        gain=int(self.state.get('vibration_gain',100))
        self.vibration.set_display_state(f'{gain}%' if enabled and supported else 'On' if enabled else 'Off')
        if not hasattr(self,'vibration_gain_slider'): return
        self.vibration_icon.setIcon(control_icon('vibrate' if enabled else 'vibrate-off'))
        self.vibration_icon.setAccessibleName(tr('Rumble off' if enabled else 'Rumble on'))
        self.vibration_icon.setToolTip(tr('Rumble off' if enabled else 'Rumble on'))
        self.vibration_gain_slider.setEnabled(supported)
        if not self.vibration_gain_slider.isSliderDown(): self.vibration_gain_slider.setValue(gain)

    def open_adjustment(self,key):
        dialog=self.adjustment_dialogs.get(key)
        if dialog:
            dialog.setFixedSize(min(POPUP_WIDTH,self.width()-2*POPUP_MARGIN),min(self.height()-2*POPUP_MARGIN,dialog.sizeHint().height()))
            dialog.move(self.mapToGlobal(self.rect().center())-dialog.rect().center()); dialog.show(); dialog.raise_()

    def update_volume_icon(self):
        value=self.volume.value()
        icon='volume-x' if self.audio_muted or value == 0 else 'volume' if value < 20 else 'volume-1' if value < 60 else 'volume-2'
        self.volume_icon.setIcon(control_icon(icon)); self.volume_label.setText(f'{value}%')
        self.volume_button.setText(tr('Muted') if self.audio_muted else tr('Volume')+f' · {value}%')
        self.volume_icon.setToolTip(tr('Unmute' if self.audio_muted else 'Mute'))

    def toggle_audio_mute(self):
        self.audio_muted=not self.audio_muted
        self.set_audio('set-mute','1' if self.audio_muted else '0'); self.update_volume_icon()

    def set_launch_screen(self,name):
        self.set_pref('launch_screen',name); self.install_placement()

    def set_gamepad_focus(self,mode):
        if mode not in ('auto','top','bottom'): return
        self.set_pref('gamepad_focus',mode); self.install_placement()
        self.gamepad_focus.show_value(mode)
        for value,button in getattr(self,'focus_choices',{}).items(): button.setChecked(value==mode)
        QTimer.singleShot(1000,self.focus_gamepad)

    def focus_gamepad(self):
        if self.prefs.get('gamepad_focus','auto')!='auto':
            self.desktop.shortcut('HandheldDash Gamepad Focus')

    def open_window_focus(self):
        if 'focus' not in self.adjustment_dialogs:
            dialog,box=self.adjustment_dialog('focus','Window focus'); self.focus_choices={}
            for value,title in [('auto','Automatic'),('top','Lock top screen'),('bottom','Lock bottom screen')]:
                button=self.button(title,lambda checked=False,v=value:self.set_gamepad_focus(v),True)
                button.setMinimumHeight(44); self.focus_choices[value]=button; box.addWidget(button)
            note=QLabel('Lock top screen keeps Dash from taking keyboard focus and blocks touches on the other desktop background. Other applications can still take focus. Automatic restores normal desktop interaction.')
            note.setWordWrap(True); box.addWidget(note)
        for value,button in self.focus_choices.items(): button.setChecked(value==self.prefs.get('gamepad_focus','auto'))
        self.open_adjustment('focus')

    def set_screen_display(self,name,visible):
        role=next((role for role in DEVICE.backlights if DEVICE.screen_name(role,QApplication.screens())==name),None)
        if role is None: return
        button=self.screen_display_buttons[name]; button.setEnabled(False)
        if not visible and role=='bottom': self.exit_touchpad()
        def received(raw):
            self.screen_off=set(json.loads(raw))
            for target,widget in self.screen_display_buttons.items():
                target_role=next((r for r in DEVICE.backlights if DEVICE.screen_name(r,QApplication.screens())==target),None)
                widget.show_value(target_role not in self.screen_off)
            if not visible and role=='bottom': self.hide()
        def finished(success,busy):
            button.setEnabled(True)
            if not success: button.show_value(role not in self.screen_off)
        self.call('ScreenPower',[role,visible],received,finished=finished)

    def screen_brightness(self,key,value):
        self.set('brightness',[key,str(value)])
        if key == 'both':
            for target in ['top','bottom']: self.screen_sliders[target].setValue(value)

    def refresh_audio(self):
        if getattr(self,'audio_busy',False) or self.audio_active or self.audio_queue: return
        revision = self.audio_revision
        self.audio_busy=True
        process=QProcess(self)
        timeout=QTimer(process); timeout.setSingleShot(True); timeout.timeout.connect(process.kill); timeout.start(3000)
        completed=False
        def done():
            nonlocal completed
            if completed: return
            completed=True; timeout.stop()
            output=bytes(process.readAllStandardOutput()).decode().split()
            if process.exitCode()==0 and len(output)>=2:
                try:
                    if not self.volume.isSliderDown() and revision == self.audio_revision: self.volume.setValue(round(float(output[1])*100))
                    if revision == self.audio_revision: self.audio_muted='[MUTED]' in output; self.update_volume_icon()
                except ValueError: pass
            self.volume.setEnabled(process.exitCode()==0); self.volume_icon.setEnabled(process.exitCode()==0)
            self.audio_busy=False; process.deleteLater()
        process.finished.connect(done)
        process.errorOccurred.connect(lambda error:done())
        process.start('wpctl',['get-volume','@DEFAULT_AUDIO_SINK@'])

    def set_audio(self,operation,value):
        self.audio_revision += 1; self.audio_queue[operation] = value
        self.flush_audio()

    def flush_audio(self):
        if self.audio_active or not self.audio_queue: return
        operation = next(iter(self.audio_queue)); value = self.audio_queue.pop(operation)
        self.audio_active = True; process = QProcess(self)
        timeout=QTimer(process); timeout.setSingleShot(True); timeout.timeout.connect(process.kill); timeout.start(3000)
        completed=False
        def done(code=1,*args):
            nonlocal completed
            if completed: return
            completed=True; timeout.stop()
            self.audio_active = False
            if code: self.notify('Error: '+bytes(process.readAllStandardError()).decode())
            process.deleteLater(); self.flush_audio()
        process.finished.connect(done)
        process.errorOccurred.connect(lambda error:done() if error == QProcess.ProcessError.FailedToStart else None)
        process.start('wpctl',[operation,'@DEFAULT_AUDIO_SINK@',value])
