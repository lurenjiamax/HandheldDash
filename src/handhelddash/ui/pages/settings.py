# SPDX-License-Identifier: LGPL-3.0-or-later
from handhelddash.ui.common import ACTIONS, BUILD, DEVICE, Path, PlainLabel, QApplication, QDBusArgument, QDBusInterface, QDBusMessage, QFormLayout, QHBoxLayout, QLabel, QLibraryInfo, QLineEdit, QLocale, QMetaType, QScrollArea, QStackedWidget, QTimer, QVBoxLayout, QWidget, Qt, VERSION, json, mango_config, os, save, set_language, tr
from handhelddash.ui.widgets.buttons import QPushButton, StateButton
from handhelddash.ui.widgets.choice import Choice

class SettingsPageMixin:
    def make_settings(self):
        self.settings_index=self.tabs.count()
        layout = self.page('Settings')
        self.settings_stack = QStackedWidget(); layout.addWidget(self.settings_stack)
        self.setting_widgets = {}; self.sliders = self.screen_sliders.copy(); self.group_names = []
        def group(title,scrollable=False):
            self.group_names.append(title)
            page = QWidget(); box = QVBoxLayout(page)
            if scrollable:
                scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
                content = QWidget(); scroll.setWidget(content); box.addWidget(scroll); box = QVBoxLayout(content)
                scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            form = QFormLayout(); form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow); form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows); box.addLayout(form); box.addStretch()
            self.settings_stack.addWidget(page)
            return form
        form = group('Tab management')
        help_text = QLabel('Pin your tabs. Open other pages here; they close when you leave. Settings always remains available.'); help_text.setWordWrap(True); form.addRow(help_text)
        list_widget = QWidget(); list_layout = QVBoxLayout(list_widget)
        for i,title in enumerate(self.page_titles[:-1]):
            row = QHBoxLayout(); row.addWidget(QLabel(title),1)
            pin = self.button('Pinned',lambda checked,t=title:self.pin_tab(t,checked),True)
            pin.setChecked(title in self.prefs.get('resident_tabs',self.page_titles))
            row.addWidget(pin); row.addWidget(self.button('Open',lambda checked=False,index=i:self.open_tab(index)))
            list_layout.addLayout(row)
        list_layout.setContentsMargins(0,0,0,0)
        for button in list_widget.findChildren(QPushButton): button.setStyleSheet('padding:4px 8px; min-height:24px;')
        form.addRow(list_widget)
        self.dashboard_settings_index = self.settings_stack.count()
        self.group_names.append('Customize dashboard')
        editor = QWidget(); editor_layout = QVBoxLayout(editor); self.settings_stack.addWidget(editor)
        self.make_dashboard_editor(editor_layout)
        form = group('Performance')
        self.mango_mode=StateButton('MangoHud',[('release','Release configuration','sliders-horizontal'),('takeover','Take over configuration','gauge')],lambda value:self.set_mangohud_mode(value))
        form.addRow(QLabel('MangoHud'),self.mango_mode)
        self.panel_affinity = StateButton('Panel CPU', [('system','System language','sliders-horizontal'),('little','Little cores only','leaf')],self.set_cpu_affinity)
        self.panel_affinity.show_value(self.prefs['panel_cpu_affinity'])
        self.panel_affinity.setToolTip(tr('Limits only the panel; externally launched apps are unrestricted.')+' CPU '+','.join(map(str,sorted(self.little_cpus))))
        form.addRow(QLabel('Panel CPU'),self.panel_affinity)
        row=QHBoxLayout()
        cpu=StateButton('CPU governor',[(v,v,'zap' if v=='performance' else 'leaf' if v=='powersave' else 'sliders-horizontal') for v in ['performance','schedutil','ondemand','powersave','auto']],lambda v:self.set('cpu-governor',[v]))
        self.setting_widgets['cpu_governor']=cpu; row.addWidget(cpu,1)
        self.boost=StateButton('CPU boost',[(False,'Boost off','sliders-horizontal'),(True,'Boost on','zap')],lambda v:self.set('cpu-boost',['on' if v else 'off'])); row.addWidget(self.boost,1)
        form.addRow(QLabel('CPU governor'),row)
        self.combo(form,'GPU governor',['performance','simple_ondemand','powersave','userspace','auto'],'gpu-governor','gpu_governor')
        self.combo(form,'Scheduler',['regular','lavd'],'scheduler','scheduler')
        self.ufs_irq=StateButton('UFS interrupt affinity',[('system','Restore original','sliders-horizontal'),('powersave','Power saving CPU0–2','leaf'),('performance','Performance CPU7','zap')],lambda value:self.set('ufs-irq',[value]))
        self.ufs_irq.setToolTip(tr('CPU7 may increase power use; performance depends on the workload.'))
        form.addRow(QLabel('UFS interrupt affinity'),self.ufs_irq)
        self.sliders['rgb'] = self.lighting_brightness
        form=group('Plasma')
        self.plasma_status_bar=StateButton('Bottom-screen status bar',[(False,'Hidden','eye-off'),(True,'Visible','eye')],self.set_plasma_status_bar)
        self.plasma_docked=StateButton('Plasma Docked Mode',[(False,'Off','monitor'),(True,'On','panels-top-left')],self.set_plasma_docked)
        form.addRow(QLabel('Bottom-screen status bar'),self.plasma_status_bar); form.addRow(QLabel('Plasma Docked Mode'),self.plasma_docked)
        note=QLabel('Docked Mode is a global Plasma Mobile setting. Only the bottom screen uses its Mobile panel here.'); note.setWordWrap(True); form.addRow(note)
        self.refresh_plasma_settings()
        form = group('Buttons',True)
        for key,label in [('back','Back button'),('home','Home button'),('back-home','Back button + Home button')]:
            combo = Choice()
            for value,text in ACTIONS.items(): combo.addItem(text,value)
            combo.setCurrentIndex(combo.findData(self.prefs[key])); combo.activated.connect(lambda i,k=key,c=combo:self.set_button_action(k,c.currentData())); form.addRow(QLabel(label),combo)
            command = QLineEdit(self.prefs[key+'_command']); command.setPlaceholderText('Custom command, e.g. konsole')
            command.editingFinished.connect(lambda k=key,c=command:self.set_pref(k+'_command',c.text())); form.addRow(QLabel(label+' command'),command)
        form = group('Android'); self.android_settings_index=self.settings_stack.count()-1
        warning = QLabel('Extremely experimental: this may not work at all and may even prevent the Android partition from booting.'); warning.setWordWrap(True); warning.setStyleSheet('color:#ffb176; font-weight:600;'); form.addRow(warning)
        self.android_parts = []
        self.android_combo = Choice(); self.android_combo.currentIndexChanged.connect(self.describe_android); form.addRow(QLabel('Partition'),self.android_combo)
        self.android_label = QLabel('Query Android partitions'); self.android_label.setWordWrap(True); form.addRow(self.android_label)
        row = QHBoxLayout(); row.addWidget(self.button('Query',self.refresh_android)); self.android_mount=self.button('Mount read-only',lambda:self.android_action('mount-android')); row.addWidget(self.android_mount); row.addWidget(self.button('Unmount',lambda:self.android_action('unmount-android'))); form.addRow(row)
        form.addRow(self.button('Open Android folder',self.open_android))
        self.android_timer=QTimer(self); self.android_timer.setInterval(10000)
        self.android_timer.timeout.connect(lambda:self.refresh_android() if self.isVisible() and self.tabs.currentIndex()==self.settings_index and self.settings_stack.currentIndex()==self.android_settings_index else None)
        self.android_timer.start()
        form = group('Language')
        language = Choice()
        for text,value in [('System language','system'),('English','en'),('Simplified Chinese','zh_CN'),('Traditional Chinese','zh_TW')]: language.addItem(text,value)
        language.setCurrentIndex(language.findData(self.prefs['language']))
        language.activated.connect(lambda i:self.change_language(language.currentData()))
        form.addRow(QLabel('Language'),language)
        form = group('About')
        form.addRow(QLabel('HandheldDash'))
        form.addRow(QLabel('Version'),QLabel(VERSION))
        form.addRow(QLabel('Build'),PlainLabel(BUILD))
        source=QLabel('<a style="color:#bca6ff" href="https://github.com/lurenjiamax/HandheldDash">github.com/lurenjiamax/HandheldDash</a>')
        source.setOpenExternalLinks(True); source.setWordWrap(True); form.addRow(QLabel('Source code'),source)
        for text in ['Currently supported and tested only on AYN Thor with the Thorch BSP; other handhelds are planned.','Original code: LGPL-3.0-or-later. Third-party components retain their licenses; Lucide icons use ISC and PyQt6 uses GPL/commercial licensing.','© 2026 lurenjiamax. Provided as-is, without warranty.']:
            label=QLabel(text); label.setWordWrap(True); form.addRow(label)
        self.settings_navigation=QWidget(); row = QHBoxLayout(self.settings_navigation); row.setContentsMargins(0,0,0,0)
        row.addWidget(self.button('Previous group',lambda:self.change_group(-1)))
        self.group_title = QLabel(); self.group_title.setAlignment(Qt.AlignmentFlag.AlignCenter); row.addWidget(self.group_title,1)
        row.addWidget(self.button('Next group',lambda:self.change_group(1))); layout.addWidget(self.settings_navigation); self.change_group(0)

    def plasma_target_screen(self):
        screen=next((screen for screen in QApplication.screens() if screen.name() == DEVICE.screen_name('bottom',QApplication.screens())),None)
        return screen

    def refresh_plasma_settings(self):
        self.plasma_docked.setEnabled(self.desktop.supports('plasma_docked'))
        self.plasma_docked.show_value(self.desktop.plasma_docked())
        screen=self.plasma_target_screen()
        if screen is None or not self.desktop.supports('plasma_panel'):
            self.plasma_status_bar.setEnabled(False); return
        def loaded(raw):
            try: panels=json.loads(raw)
            except ValueError: return
            self.plasma_status_bar.setEnabled(True)
            self.plasma_status_bar.show_value(bool(panels))
            if panels: self.plasma_status_geometry=panels[0]
        self.desktop.plasma_panels(screen.geometry(),loaded,lambda:self.plasma_status_bar.setEnabled(False))

    def set_plasma_status_bar(self,visible):
        screen=self.plasma_target_screen()
        if screen is None or not self.desktop.supports('plasma_panel'):
            self.plasma_status_bar.setEnabled(False); self.notify('Error: configured display is unavailable'); return
        geometry=getattr(self,'plasma_status_geometry',self.prefs.get('plasma_status_geometry',{'height':30,'location':'top'}))
        self.set_pref('plasma_status_geometry',geometry)
        self.desktop.set_plasma_panel(screen.geometry(),visible,geometry,lambda raw:self.refresh_plasma_settings(),self.refresh_plasma_settings)

    def set_plasma_docked(self,enabled):
        if not self.desktop.supports('plasma_docked'): return
        self.desktop.set_plasma_docked(enabled)
        QTimer.singleShot(300,self.refresh_plasma_settings)

    def change_language(self,value):
        self.set_pref('language',value); set_language(value)
        self.translate_dialogs()
        for widget in self.findChildren(QWidget):
            if hasattr(widget,'retranslate'): widget.retranslate()
        for i,title in enumerate(self.page_titles): self.tabs.setTabText(i,tr(title))
        self.refresh_dashboard_editor()
        self.setWindowTitle('HandheldDash')

    def translate_dialogs(self):
        app = QApplication.instance(); app.removeTranslator(self.qt_translator)
        if self.qt_translator.load(QLocale(),'qtbase','_',QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
            app.installTranslator(self.qt_translator)

    def change_group(self,delta):
        index=(self.settings_stack.currentIndex()+delta)%self.settings_stack.count(); self.settings_stack.setCurrentIndex(index)
        self.settings_navigation.setVisible(True)
        self.group_title.setText(f'{self.group_names[index]} · {index+1} / {self.settings_stack.count()}')

    def combo(self, form, label, items, operation, key):
        options=[(value,value,'zap' if value=='performance' else 'leaf' if value=='powersave' else 'sliders-horizontal') for value in items]
        button=StateButton(label,options,lambda value:self.set(operation,[value]))
        form.addRow(QLabel(label),button); self.setting_widgets[key]=button
        return button

    def set_cpu_affinity(self,mode,persist=True):
        if mode not in ('system','little'): return
        target = self.little_cpus if mode == 'little' else self.system_cpus
        previous = {}
        try:
            for task in sorted(Path('/proc/self/task').iterdir(),key=lambda p:int(p.name) != os.getpid()):
                tid = int(task.name)
                try:
                    previous[tid] = os.sched_getaffinity(tid)
                    os.sched_setaffinity(tid,target)
                except ProcessLookupError: continue
        except OSError as error:
            for tid,cpus in previous.items():
                try: os.sched_setaffinity(tid,cpus)
                except ProcessLookupError: pass
            self.panel_affinity.show_value(self.prefs['panel_cpu_affinity']); self.notify(str(error)); return
        if persist: self.set_pref('panel_cpu_affinity',mode)
        self.panel_affinity.show_value(mode)

    def set_pref(self, key, value):
        self.prefs[key] = value; save(self.prefs)

    def update_mangohud(self):
        if self.prefs['mangohud_mode'] == 'takeover': mango_config(self.prefs)
        self.set('mangohud',[self.prefs['mangohud_mode'],self.prefs['fps_limit'],'on' if self.prefs['hud'] else 'off'])

    def set_mangohud_mode(self,value):
        self.set_pref('mangohud_mode',value)
        self.update_mangohud()

    def set_button_action(self,key,value):
        self.set_pref(key,value)
        if key == 'back-home': self.set('navigation-chord',[value])

    def set_fps_limit(self,value):
        self.set_pref('fps_limit',value); self.fps_mode.show_value(value); self.update_mangohud()

    def set_hud(self,value):
        self.set_pref('hud',value); self.update_mangohud()

    def set_autolock(self,value):
        for interface,cookie in self.caffeine_cookies:
            interface.call('UnInhibit',QDBusArgument(cookie,QMetaType.Type.UInt.value))
        self.caffeine_cookies = []
        if value:
            for service,path,api in [('org.freedesktop.PowerManagement','/org/freedesktop/PowerManagement/Inhibit','org.freedesktop.PowerManagement.Inhibit'),('org.freedesktop.ScreenSaver','/ScreenSaver','org.freedesktop.ScreenSaver')]:
                interface = QDBusInterface(service,path,api,self.session)
                reply = interface.call('Inhibit','HandheldDash','Manually block sleep and screen locking')
                if reply.type() == QDBusMessage.MessageType.ErrorMessage:
                    self.notify(reply.errorMessage()); self.set_autolock(False); return
                self.caffeine_cookies.append((interface,reply.arguments()[0]))
        self.set_pref('caffeine_enabled',bool(value)); self.autolock.show_value(bool(value))
