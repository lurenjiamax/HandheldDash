# SPDX-License-Identifier: LGPL-3.0-or-later
from handhelddash.ui.common import CORE_TILES, DASHBOARD_TILES, EmbeddedPopup, METRIC_ICONS, METRIC_TITLES, QApplication, QDrag, QEvent, QGridLayout, QHBoxLayout, QLabel, QMimeData, QProgressBar, QScrollArea, QSizePolicy, QStackedWidget, QTimer, QVBoxLayout, QWidget, Qt, TILE_MIME, dashboard_layout, dashboard_preset, json, math, theme_color, time, tr
from handhelddash.ui.widgets.buttons import QuickTile, ScreenshotTile, StateButton, TemperatureButton
from handhelddash.ui.widgets.dashboard import DashboardPage, EditTile, FpsMeter
from handhelddash.ui.widgets.icons import MetricIcon, control_icon

class DashboardPageMixin:
    def make_control(self):
        self.dashboard_page_widget=DashboardPage(self); layout = self.page('Control',self.dashboard_page_widget)
        layout.setContentsMargins(0,0,0,8); layout.setSpacing(8)
        self.dashboard_editing=False; self.editor_selection=None; self.dashboard_draft=dashboard_layout(self.prefs.get('dashboard_layout'))
        self.metric_hold_timer=QTimer(self); self.metric_hold_timer.setSingleShot(True); self.metric_hold_timer.setInterval(550); self.metric_hold_timer.timeout.connect(self.open_metric_context)
        self.metric_press_key=None; self.metric_dragged=False; self.metric_held=False
        self.fps = FpsMeter('— FPS'); self.fps.setObjectName('Fps'); self.fps.setFixedWidth(70); self.header.insertWidget(1,self.fps); self.fps.clicked.connect(self.open_fps_menu)
        self.fps_source = QLabel('',self.dashboard_page_widget); self.fps_source.hide()
        self.fps_mode = StateButton('FPS',[(0,'Unlimited','infinity'),(30,'30 FPS','fps-30'),(60,'60 FPS','fps-60'),(120,'120 FPS','fps-120')],self.set_fps_limit,icon_only=True)
        self.fps_mode.setObjectName('FpsLimit'); self.fps_mode.setStyleSheet('padding:0; min-height:0; border-radius:10px; font-size:12px;')
        self.fps_mode.setFixedSize(64,44); self.fps_mode.show_value(self.prefs['fps_limit']); self.fps_mode.setParent(self); self.fps_mode.hide()
        edit = self.button('',self.dashboard_edit_tap); edit.setIcon(control_icon('pencil'))
        edit.setFixedSize(44,44); edit.setStyleSheet('padding:0; min-height:0; border-radius:10px;')
        edit.setAccessibleName(tr('Customize dashboard')); edit.setToolTip(tr('Customize dashboard')); self.header.insertWidget(self.header.count()-1,edit)
        self.dashboard_edit_button=edit
        self.dashboard_widgets = {}; self.dashboard_tiles = {}
        self.dashboard_info=QStackedWidget(); self.dashboard_info.setFixedHeight(94)
        self.dashboard_metrics = QWidget(); metrics_box=QVBoxLayout(self.dashboard_metrics); metrics_box.setContentsMargins(0,0,0,0)
        metrics_grid=QGridLayout(); self.dashboard_metrics_grid=metrics_grid; metrics_grid.setSpacing(6); metrics_box.addLayout(metrics_grid)
        for column in range(3): metrics_grid.setColumnStretch(column,1)
        self.dashboard_info.addWidget(self.dashboard_metrics); self.make_editor_toolbar(); layout.addWidget(self.dashboard_info)
        self.dashboard_tile_area=QWidget(); tile_box=QVBoxLayout(self.dashboard_tile_area); tile_box.setContentsMargins(0,0,0,0); tile_box.setSpacing(8)
        self.dashboard_core_area=QWidget(); self.dashboard_core_area.setFixedHeight(72)
        self.dashboard_core_grid=QGridLayout(self.dashboard_core_area); self.dashboard_core_grid.setContentsMargins(0,0,0,0); self.dashboard_core_grid.setSpacing(8)
        for column in range(2): self.dashboard_core_grid.setColumnStretch(column,1)
        tile_box.addWidget(self.dashboard_core_area)
        self.dashboard_shortcut_area=QWidget(); self.dashboard_grid=QGridLayout(self.dashboard_shortcut_area)
        self.dashboard_grid.setContentsMargins(0,0,0,0); self.dashboard_grid.setSpacing(8)
        for column in range(5): self.dashboard_grid.setColumnStretch(column,1)
        for row in range(2): self.dashboard_grid.setRowStretch(row,1)
        tile_box.addWidget(self.dashboard_shortcut_area,1); layout.addWidget(self.dashboard_tile_area); layout.addStretch(1)
        self.editor_selected_tiles=[]
        for index in range(12):
            tile=EditTile(self,True); tile.setParent(self.dashboard_shortcut_area); tile.hide(); self.editor_selected_tiles.append(tile)
        self.caffeine_cookies = []
        self.autolock = QuickTile('Caffine',[(False,'Caffine Off','coffee-off'),(True,'Caffine On','coffee')],self.set_autolock)
        self.autolock.show_value(False)
        QTimer.singleShot(0,lambda:self.set_autolock(self.prefs.get('caffeine_enabled',False)))
        self.performance = QuickTile('Performance mode', [('quiet','Quiet','leaf'),('standard','Balanced','gauge'),('performance','Performance','zap')], lambda v:self.set('performance',[v]))
        self.fan_link_control = QuickTile('Fan mode',self.fan_link_choices(),self.set_fan_follow)
        self.input_mode = QuickTile('Controller plan',[('gamepad','Default','gamepad'),('mouse','Mouse and keyboard','mouse')],lambda v:self.open_input_profiles())
        self.gamepad_focus = QuickTile('Gamepad focus',[('auto','Automatic','gamepad'),('top','Lock top screen','monitor'),('bottom','Lock bottom screen','monitor')],self.set_gamepad_focus)
        self.gamepad_focus.show_value(self.prefs.get('gamepad_focus','auto'))
        self.gamepad_focus.setToolTip(tr('Controls desktop focus; apps reading gamepad devices directly are not isolated.'))
        self.vibration = QuickTile('Vibration',[(False,'Rumble off','vibrate-off'),(True,'Rumble on','vibrate')],lambda v:self.open_vibration())
        self.rgb = QuickTile('Lighting',self.lighting_choices(),self.set_rgb_mode)
        for key,button in [('caffeine',self.autolock),('performance',self.performance),('fan_link',self.fan_link_control),('input',self.input_mode),('focus',self.gamepad_focus),('vibration',self.vibration),('lighting',self.rgb)]:
            self.dashboard_widgets[('controls',key)] = button; self.dashboard_tiles[key]=button
            if key in CORE_TILES:
                button.core=True; button.setMinimumHeight(72); self.dashboard_core_grid.addWidget(button,0,CORE_TILES.index(key))
        self.gauges = {}; self.metric_icons = {}
        for i,(key,title,icon) in enumerate([('cpu','CPU','cpu'),('gpu','GPU','video-display'),('temp','Temperature','temperature-normal'),('fan','Fan','fan'),('ram','RAM','memory'),('battery','Power','zap'),('load','System load','activity'),('network','Network speed','network'),('disk_io','Disk IO','disk')]):
            card = QWidget(); card.setObjectName('Gauge'); card.setFixedHeight(44); card.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed); box = QVBoxLayout(card); box.setContentsMargins(8,5,8,5); box.setSpacing(0)
            row = QHBoxLayout(); row.setSpacing(8); image = MetricIcon('power' if key == 'battery' else key); self.metric_icons[key] = image
            if key == 'temp':
                row.addWidget(image)
                value=TemperatureButton('Temperature',[('battery','Battery · — °C','thermometer')],lambda v:self.select_temperature(v)); self.temperature_button=value
                value.setObjectName('MetricValue'); value.setMinimumHeight(24); value.setMaximumHeight(28)
                value.show_value(self.prefs.get('temperature_sensor','battery'))
            else:
                row.addWidget(image); value = QLabel(title); value.setObjectName('MetricReading')
                if key == 'battery':
                    self.power_temperature = QLabel('— °C'); self.power_temperature.setObjectName('MetricReading'); row.addWidget(self.power_temperature)
                    value.setWordWrap(True)
                    value.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter)
            row.addWidget(value,1); box.addLayout(row)
            if key in ('load','network','disk_io'): value.setStyleSheet('font-size:11px;')
            bar = QProgressBar(card); bar.setRange(0,1000); bar.hide()
            metrics_grid.addWidget(card,i//3,i%3); self.dashboard_widgets[('metrics',key)] = card; self.gauges[key]=(value,bar)
            metric_key={'temp':'temperature','ram':'memory'}.get(key,key); card.setProperty('metric_key',metric_key); card.setAcceptDrops(True)
            card.installEventFilter(self)
            for child in card.findChildren(QWidget): child.setProperty('metric_key',metric_key); child.setAcceptDrops(True); child.installEventFilter(self)
        self.metric_add_slots=[]
        for index in range(6):
            button=self.button('',self.show_available_metrics); button.setIcon(control_icon('plus')); button.setObjectName('Gauge'); button.setAccessibleName(tr('Add metric')); button.hide(); button.setParent(self.dashboard_metrics); self.metric_add_slots.append(button)
        self.shot = ScreenshotTile(self.screenshot_choices(),self.set_screenshot_mode,self.screenshot)
        self.shot.show_value(self.prefs.get('screenshot_mode','top')); self.shot.setToolTip(tr('Tap to capture, hold to change mode'))
        overview = QuickTile('Overview',[(None,'Open overview','panels-top-left')],lambda v:self.action('overview'))
        self.hud = QuickTile('FPS overlay',[(False,'Overlay off','eye-off'),(True,'Overlay on','eye')],self.set_hud)
        self.hud.show_value(self.prefs['hud'])
        for key,button in [('screenshot',self.shot),('overview',overview),('hud',self.hud)]:
            self.dashboard_widgets[('actions',key)] = button; self.dashboard_tiles[key]=button
        for key,title,icon in [('brightness','Brightness','sun'),('volume','Volume','volume-2')]:
            self.dashboard_tiles[key]=QuickTile(title,[(None,'Adjust','sun' if key == 'brightness' else 'volume-2')],lambda value,k=key:self.open_adjustment(k))
        self.dashboard_tiles['move_app']=QuickTile('Move current app',[(None,'Move current app','arrow-left-right')],lambda value:self.action('swap'))
        self.apply_dashboard_layout()

    def apply_dashboard_layout(self):
        configuration = self.dashboard_draft if self.dashboard_editing else dashboard_layout(self.prefs.get('dashboard_layout'))
        self.fps.setVisible(configuration.get('show_fps',True)); self.fps_mode.hide()
        self.header_title.setFixedWidth(90 if self.dashboard_editing else 110)
        self.clock.setVisible(not self.dashboard_editing)
        for button in self.editor_header_actions: button.setVisible(self.dashboard_editing)
        self.dashboard_edit_button.setVisible(not self.dashboard_editing)
        self.fps_mode.setEnabled(not self.dashboard_editing and self.prefs.get('mangohud_mode') == 'takeover')
        while self.dashboard_metrics_grid.count(): self.dashboard_metrics_grid.takeAt(0)
        for button in self.metric_add_slots: button.hide()
        for key in ('cpu','gpu','temp','fan','ram','battery','load','network','disk_io'): self.dashboard_widgets[('metrics',key)].hide()
        for index,key in enumerate(configuration.get('metric_order',['cpu','gpu','temperature','fan','memory','battery'])):
            card=self.dashboard_widgets[('metrics',{'temperature':'temp','memory':'ram'}.get(key,key))]; self.dashboard_metrics_grid.addWidget(card,index//3,index%3); card.show()
            card.setStyleSheet('QWidget#Gauge { border:1px dashed '+theme_color('#a68bff').name()+'; }' if self.editor_selection == 'metric:'+key else '')
        if self.dashboard_editing:
            for index in range(len(configuration.get('metric_order',[])),6):
                button=self.metric_add_slots[index]; self.dashboard_metrics_grid.addWidget(button,index//3,index%3); button.show()
        self.dashboard_info.setVisible(self.dashboard_editing or (configuration['metrics'] and bool(configuration.get('metric_order',['cpu','gpu','temperature','fan','memory','battery']))))
        self.dashboard_info.setCurrentIndex(0); self.layout_dashboard_regions()
        tiles=configuration['tiles']
        while self.dashboard_grid.count(): self.dashboard_grid.takeAt(0)
        while self.dashboard_core_grid.count(): self.dashboard_core_grid.takeAt(0)
        for key,widget in self.dashboard_tiles.items():
            widget.editing=self.dashboard_editing
            widget.core=key in tiles[:2]
            if widget.parentWidget() is not self.dashboard_shortcut_area: widget.setParent(self.dashboard_shortcut_area)
            widget.hide()
        for index,tile in enumerate(self.editor_selected_tiles):
            tile.hide()
            core=index<2; grid=self.dashboard_core_grid if core else self.dashboard_grid
            row=0 if core else (index-2)//5; column=index if core else (index-2)%5
            if self.dashboard_editing:
                tile.core=core; grid.addWidget(tile,row,column); tile.set_tile(tiles[index] if index<len(tiles) else None)
            elif index<len(tiles):
                widget=self.dashboard_tiles[tiles[index]]; grid.addWidget(widget,row,column); widget.show()
        self.editor_add.setEnabled(True)
        self.sync_monitoring()

    def sync_monitoring(self):
        configuration=self.dashboard_draft if self.dashboard_editing else dashboard_layout(self.prefs.get('dashboard_layout'))
        items=configuration.get('metric_order',['cpu','gpu','temperature','fan','memory','battery']) if self.dashboard_editing or configuration['metrics'] else []
        payload=json.dumps({'items':items,'modes':configuration.get('metric_modes',{})})
        self.call('SetMonitoring',[payload],quiet=True)
        timer=self.metric_icons['fan'].timer
        if 'fan' in items:
            if not timer.isActive(): self.metric_icons['fan'].last_frame=time.monotonic(); timer.start(50)
        else: timer.stop()

    def open_dashboard_editor(self):
        visible=self.isVisible()
        self.setWindowTitle('HandheldDash Settings')
        self.setWindowFlag(Qt.WindowType.WindowDoesNotAcceptFocus,False)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating,False)
        self.dashboard_draft = dashboard_layout(self.prefs.get('dashboard_layout'))
        self.dashboard_editing=True; self.editor_selection=None; self.header_title.setText('Edit dashboard')
        self.open_tab(0); self.refresh_dashboard_editor()
        if visible: self.showFullScreen(); self.raise_(); self.activateWindow()

    def layout_dashboard_regions(self):
        height=max(300,self.dashboard_page_widget.height()); metrics=max(80,round(height*.23))
        self.dashboard_info.setFixedHeight(metrics)
        for key in ('cpu','gpu','temp','fan','ram','battery','load','network','disk_io'): self.dashboard_widgets.get(('metrics',key),self.dashboard_metrics).setFixedHeight(max(36,(metrics-6)//2))
        for button in self.metric_add_slots: button.setFixedHeight(max(36,(metrics-6)//2))
        area=max(220,height-(metrics if not self.dashboard_info.isHidden() else 0)-16)
        self.dashboard_tile_area.setFixedHeight(area); self.dashboard_core_area.setFixedHeight(max(66,round(area*.23)))

    def eventFilter(self,watched,event):
        key=watched.property('metric_key')
        if self.dashboard_editing and key:
            kind=event.type()
            if kind == QEvent.Type.MouseButtonPress:
                self.metric_press_key=key; self.metric_origin=event.globalPosition().toPoint(); self.metric_dragged=False; self.metric_held=False; self.metric_hold_timer.start(); return True
            if kind == QEvent.Type.MouseMove and event.buttons() & Qt.MouseButton.LeftButton and self.metric_press_key:
                if not self.metric_dragged and (event.globalPosition().toPoint()-self.metric_origin).manhattanLength() >= QApplication.startDragDistance():
                    self.metric_hold_timer.stop(); self.metric_dragged=True; mime=QMimeData(); mime.setData(TILE_MIME,('metric:'+self.metric_press_key).encode()); drag=QDrag(watched); drag.setMimeData(mime); drag.setPixmap(watched.grab()); drag.exec(Qt.DropAction.MoveAction)
                return True
            if kind == QEvent.Type.MouseButtonRelease:
                self.metric_hold_timer.stop()
                if not self.metric_dragged and not self.metric_held: self.select_dashboard_tile('metric:'+key)
                self.metric_press_key=None; return True
            if kind == QEvent.Type.DragEnter and event.mimeData().hasFormat(TILE_MIME): event.acceptProposedAction(); return True
            if kind == QEvent.Type.Drop:
                source=bytes(event.mimeData().data(TILE_MIME)).decode(errors='replace')
                if self.reorder_dashboard_tile(source,'metric:'+key): event.acceptProposedAction()
                return True
        return super().eventFilter(watched,event)

    def open_metric_context(self):
        if self.metric_press_key:
            self.metric_held=True; self.open_tile_edit_menu('metric:'+self.metric_press_key)

    def open_fps_menu(self):
        if self.dashboard_editing:
            self.open_tile_edit_menu('fps'); return
        popup=EmbeddedPopup(self); box=QVBoxLayout(popup); box.addWidget(QLabel('FPS limit'))
        for value,title,icon in self.fps_mode.options:
            button=self.button(title,lambda checked=False,v=value:self.set_fps_limit(v),True); button.setChecked(value == self.prefs['fps_limit']); button.setEnabled(self.prefs.get('mangohud_mode') == 'takeover'); button.clicked.connect(popup.hide); box.addWidget(button)
        popup.setFixedSize(260,280); self.fps_popup=popup; popup.show()

    def dashboard_edit_tap(self):
        if not self.dashboard_editing: self.open_dashboard_editor()

    def make_editor_toolbar(self):
        toolbar=QWidget(); layout=QVBoxLayout(toolbar); layout.setContentsMargins(0,0,0,0); layout.setSpacing(6)
        help_text=QLabel('Tap two tiles to swap, or drag to reorder. All tiles can be removed.'); help_text.setObjectName('Notice'); help_text.setWordWrap(True)
        layout.addWidget(help_text,1)
        layout.addWidget(QLabel('Hold a tile to edit it.'))
        self.editor_header_actions=[]
        for title,icon,callback in [('Add tile','plus',self.open_add_menu),('Cancel','corner-up-left',self.cancel_dashboard_layout),('Done','check',self.save_dashboard_layout)]:
            button=self.button(title,callback,title == 'Show metrics')
            label=button.text(); button.setAccessibleName(label); button.setToolTip(label); button.setText(''); button.setIcon(control_icon(icon))
            button.setFixedSize(44,44); button.setStyleSheet('padding:0; min-height:0; border-radius:10px; font-size:12px;'); self.header.insertWidget(self.header.count()-1,button)
            self.editor_header_actions.append(button); button.hide()
        self.editor_add=self.editor_header_actions[0]
        self.dashboard_info.addWidget(toolbar)

    def open_tile_edit_menu(self,key):
        if not self.dashboard_editing: return
        metric=key.startswith('metric:'); identity=key.split(':',1)[1] if metric else key
        if key != 'fps' and identity not in (self.dashboard_draft.get('metric_order',[]) if metric else self.dashboard_draft['tiles']): return
        if hasattr(self,'tile_edit_popup'): self.tile_edit_popup.hide(); self.tile_edit_popup.deleteLater()
        titles=METRIC_TITLES
        popup=EmbeddedPopup(self); box=QVBoxLayout(popup); box.addWidget(QLabel(titles.get(identity,'FPS') if metric or key == 'fps' else DASHBOARD_TILES[key][0]))
        row=QHBoxLayout(); box.addLayout(row)
        delete=lambda:self.set_dashboard_metric(identity,False) if metric else self.set_dashboard_display('show_fps',False) if key == 'fps' else self.toggle_dashboard_tile(key)
        add=self.show_available_metrics if metric or key == 'fps' else self.show_available_tiles
        for title,icon,callback in [('Add tile','plus',add),('Remove tile','trash',delete)]:
            button=self.button('',lambda checked=False,action=callback:action()); button.setIcon(control_icon(icon)); button.setAccessibleName(tr(title)); button.setToolTip(tr(title)); button.setFixedSize(44,44); button.clicked.connect(popup.hide); row.addWidget(button)
        if metric and identity in ('cpu','gpu'):
            units=QHBoxLayout(); box.addLayout(units)
            mode=self.dashboard_draft.get('metric_modes',{}).get(identity,self.dashboard_draft.get('metric_mode','mhz'))
            for value,title in [('percent','%'),('mhz','MHz')]:
                button=self.button(title,lambda checked=False,v=value,k=identity:self.set_metric_unit(k,v),True); button.setChecked(mode == value); button.clicked.connect(popup.hide); units.addWidget(button)
        if metric and identity in ('network','disk_io'):
            source=self.dashboard_draft.get('metric_sources',{}).get(identity,'all')
            button=self.button(('Interface' if identity == 'network' else 'Disk')+' · '+source,lambda checked=False,k=identity:self.choose_metric_source(k)); button.clicked.connect(popup.hide); box.addWidget(button)
        if metric and identity == 'load': box.addWidget(QLabel('1 min · 5 min · 15 min'))
        popup.setFixedSize(260,170 if metric and identity in ('cpu','gpu','network','disk_io','load') else 110); self.tile_edit_popup=popup; popup.show()

    def choose_metric_source(self,key):
        self.call('MonitoringDevices',[key],lambda raw:self.show_metric_sources(key,json.loads(raw)),quiet=True)

    def show_metric_sources(self,key,names):
        popup=EmbeddedPopup(self); box=QVBoxLayout(popup); area=QScrollArea(); area.setWidgetResizable(True); content=QWidget(); choices=QVBoxLayout(content)
        selected=self.dashboard_draft.get('metric_sources',{}).get(key,'all')
        for name in ['all']+sorted(name for name in names if name != 'all'):
            button=self.button(name,lambda checked=False,n=name,k=key:self.set_metric_source(k,n),True); button.setChecked(name == selected); button.clicked.connect(popup.hide); choices.addWidget(button)
        area.setWidget(content); box.addWidget(area); popup.setFixedSize(300,320); self.metric_source_popup=popup; popup.show()

    def set_metric_source(self,key,value):
        self.dashboard_draft.setdefault('metric_sources',{})[key]=value; self.refresh_dashboard_editor()

    def set_metric_unit(self,key,value):
        self.dashboard_draft.setdefault('metric_modes',{})[key]=value; self.refresh_dashboard_editor()

    def open_add_menu(self):
        popup=EmbeddedPopup(self); row=QHBoxLayout(popup)
        for title,icon,callback in [('Add control','plus',self.show_available_tiles),('Add metric','activity',self.show_available_metrics)]:
            button=self.button(title,callback); button.setIcon(control_icon(icon)); button.clicked.connect(popup.hide); row.addWidget(button)
        popup.setFixedSize(360,80); self.add_kind_popup=popup; popup.show()

    def show_available_metrics(self):
        titles=dict(METRIC_TITLES); icons=dict(METRIC_ICONS)
        order=self.dashboard_draft.get('metric_order',[]); available=[key for key in titles if key not in order]
        if not self.dashboard_draft.get('show_fps',True): available.append('fps'); titles['fps']='FPS'; icons['fps']='gauge'
        if not available: return
        popup=EmbeddedPopup(self); grid=QGridLayout(popup); columns=min(2,len(available))
        for index,key in enumerate(available):
            action=lambda checked=False,k=key:self.set_dashboard_display('show_fps',True) if k == 'fps' else self.set_dashboard_metric(k,True)
            reading=self.fps.text() if key == 'fps' else self.gauges[{'temperature':'temp','memory':'ram'}.get(key,key)][0].text()
            button=self.button(reading,action); button.setIcon(control_icon(icons[key])); button.setFixedSize(180,44); button.setStyleSheet('border:0; border-radius:12px; padding:8px; text-align:left; background:'+theme_color('#303144').name()+';'); button.clicked.connect(popup.hide); grid.addWidget(button,index//columns,index%columns)
            button.setEnabled(key == 'fps' or len(order)<6)
            if key != 'fps' and len(order)>=6: button.setToolTip(tr('Remove a metric before adding another.'))
        popup.setFixedSize(columns*180+24+(columns-1)*6,math.ceil(len(available)/columns)*50+24); self.metric_add_popup=popup; popup.show()

    def set_dashboard_display(self,key,value):
        self.dashboard_draft[key]=value; self.refresh_dashboard_editor()

    def set_dashboard_metric(self,key,value):
        order=self.dashboard_draft.setdefault('metric_order',['cpu','gpu','temperature','fan','memory','battery'])
        if value and key not in order and len(order)<6: order.append(key)
        elif not value and key in order: order.remove(key)
        self.dashboard_draft['metrics']=True; self.editor_selection=None
        self.refresh_dashboard_editor()

    def make_dashboard_editor(self,layout):
        help_text=QLabel('Edit all tiles directly on the dashboard.'); help_text.setWordWrap(True); layout.addWidget(help_text)
        layout.addWidget(self.button('Customize dashboard',self.open_dashboard_editor)); layout.addStretch(1)

    def refresh_dashboard_editor(self):
        if not hasattr(self,'editor_selected_tiles'): return
        self.apply_dashboard_layout()

    def select_dashboard_tile(self,key):
        metric=key.startswith('metric:'); identity=key.split(':',1)[1] if metric else key
        tiles=self.dashboard_draft.get('metric_order',[]) if metric else self.dashboard_draft['tiles']
        if identity not in tiles: return
        if self.editor_selection is None: self.editor_selection=key
        elif self.editor_selection == key: self.editor_selection=None
        elif self.editor_selection.startswith('metric:') != metric: self.editor_selection=key
        else:
            source=tiles.index(self.editor_selection.split(':',1)[1] if metric else self.editor_selection); target=tiles.index(identity)
            tiles[source],tiles[target]=tiles[target],tiles[source]; self.editor_selection=None
        self.refresh_dashboard_editor()

    def remove_selected_tile(self):
        if self.editor_selection: self.toggle_dashboard_tile(self.editor_selection)

    def show_available_tiles(self):
        available=[key for key in DASHBOARD_TILES if key not in self.dashboard_draft['tiles']]
        if not available: return
        if hasattr(self,'dashboard_add_dialog'): self.dashboard_add_dialog.close(); self.dashboard_add_dialog.deleteLater()
        dialog=EmbeddedPopup(self); dialog.setWindowTitle(tr('Add tile')); box=QVBoxLayout(dialog); box.addWidget(QLabel('Add tiles'))
        grid=QGridLayout(); grid.setSpacing(8); box.addLayout(grid)
        columns=min(4,len(available)); rows=math.ceil(len(available)/columns); size=self.editor_selected_tiles[2].size()
        card_width=max(90,min(size.width(),(self.width()-48)//4)); card_height=max(80,min(size.height(),(self.height()-120)//rows))
        for index,key in enumerate(available):
            tile=EditTile(self,False); tile.set_tile(key); grid.addWidget(tile,index//columns,index%columns); tile.setFixedSize(card_width,card_height)
        dialog.setFixedSize(columns*card_width+(columns-1)*8+24,min(self.height()-24,rows*card_height+48))
        self.dashboard_add_dialog=dialog; dialog.show(); dialog.raise_(); dialog.activateWindow()

    def toggle_dashboard_tile(self,key):
        if key not in DASHBOARD_TILES: return
        tiles=self.dashboard_draft['tiles']
        if key in tiles: tiles.remove(key)
        elif len(tiles)<12: tiles.append(key)
        self.editor_selection=None
        if hasattr(self,'dashboard_add_dialog'): self.dashboard_add_dialog.accept()
        self.refresh_dashboard_editor()

    def reorder_dashboard_tile(self,source,target):
        metric=source.startswith('metric:')
        if target is not None and metric != target.startswith('metric:'): return False
        if metric:
            source=source.split(':',1)[1]; target=target.split(':',1)[1] if target is not None else None
        tiles=self.dashboard_draft.get('metric_order',[]) if metric else self.dashboard_draft['tiles']
        if source not in tiles or source == target: return False
        if target is not None and target not in tiles: return False
        index=tiles.index(target) if target is not None else len(tiles)-1
        tiles.remove(source); tiles.insert(index,source); self.editor_selection=None; self.refresh_dashboard_editor(); return True

    def toggle_dashboard_metrics(self,checked): self.dashboard_draft['metrics']=checked

    def reset_dashboard_draft(self):
        self.dashboard_draft=dashboard_preset(); self.editor_selection=None; self.refresh_dashboard_editor()

    def save_dashboard_layout(self):
        self.set_pref('dashboard_layout',dashboard_layout(self.dashboard_draft)); self.leave_dashboard_editor()

    def cancel_dashboard_layout(self):
        self.dashboard_draft = dashboard_layout(self.prefs.get('dashboard_layout')); self.refresh_dashboard_editor(); self.leave_dashboard_editor()

    def leave_dashboard_editor(self):
        self.dashboard_editing=False; self.editor_selection=None; self.header_title.setText('HandheldDash'); self.apply_dashboard_layout()
        if hasattr(self,'dashboard_add_dialog'): self.dashboard_add_dialog.hide()
        self.open_tab(0)
        if hasattr(self,'settings_stack'):
            self.settings_stack.setCurrentIndex(0); self.change_group(0)
        visible=self.isVisible(); self.setWindowTitle('HandheldDash')
        self.setWindowFlag(Qt.WindowType.WindowDoesNotAcceptFocus,True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating,True)
        if visible: self.showFullScreen(); self.raise_()

