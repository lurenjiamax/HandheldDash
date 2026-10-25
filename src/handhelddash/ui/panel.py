# SPDX-License-Identifier: LGPL-3.0-or-later
from handhelddash.ui.common import APP
from handhelddash.ui.common import CONFIG
from handhelddash.ui.common import DEVICE
from handhelddash.ui.common import EmbeddedPopup
from handhelddash.ui.common import HardwareClient
from handhelddash.ui.common import ICON_SIZE
from handhelddash.ui.common import NAME
from handhelddash.ui.common import PATH
from handhelddash.ui.common import Path
from handhelddash.ui.common import QApplication
from handhelddash.ui.common import QColor
from handhelddash.ui.common import QDBusConnection
from handhelddash.ui.common import QDBusInterface
from handhelddash.ui.common import QHBoxLayout
from handhelddash.ui.common import QLabel
from handhelddash.ui.common import QPalette
from handhelddash.ui.common import QPointF
from handhelddash.ui.common import QProcess
from handhelddash.ui.common import QSize
from handhelddash.ui.common import QSizePolicy
from handhelddash.ui.common import QTabWidget
from handhelddash.ui.common import QTimer
from handhelddash.ui.common import QTranslator
from handhelddash.ui.common import QVBoxLayout
from handhelddash.ui.common import QWidget
from handhelddash.ui.common import Qt
from handhelddash.ui.common import THEME
from handhelddash.ui.common import detect_desktop
from handhelddash.ui.common import json
from handhelddash.ui.common import os
from handhelddash.ui.common import preferences
from handhelddash.ui.common import pyqtSlot
from handhelddash.ui.common import set_language
from handhelddash.ui.common import shlex
from handhelddash.ui.common import sys
from handhelddash.ui.common import tr
from handhelddash.ui.endpoint import ControlEndpoint
from handhelddash.ui.pages.android import AndroidPageMixin
from handhelddash.ui.pages.capture import CapturePageMixin
from handhelddash.ui.pages.controller import ControllerPageMixin
from handhelddash.ui.pages.dashboard import DashboardPageMixin
from handhelddash.ui.pages.fan import FanPageMixin
from handhelddash.ui.pages.lighting import LightingPageMixin
from handhelddash.ui.pages.screens import ScreensPageMixin
from handhelddash.ui.pages.settings import SettingsPageMixin
from handhelddash.ui.pages.tasks import TasksPageMixin
from handhelddash.ui.touchpad import Touchpad
from handhelddash.ui.widgets.buttons import QPushButton
from handhelddash.ui.widgets.buttons import StateButton
from handhelddash.ui.widgets.dashboard import ControlTabBar
from handhelddash.ui.widgets.icons import MetricIcon
from handhelddash.ui.widgets.icons import control_icon

from handhelddash.ui.presenter import StatusPresenterMixin
from localization import CATALOG
from handhelddash.services.preferences import mango_config
from PyQt6.QtCore import QFileSystemWatcher

class Panel(StatusPresenterMixin, DashboardPageMixin, ScreensPageMixin, ControllerPageMixin, FanPageMixin, LightingPageMixin, SettingsPageMixin, AndroidPageMixin, TasksPageMixin, CapturePageMixin, QWidget):
    def __init__(self):
        super().__init__()
        self.system_cpus = os.sched_getaffinity(0)
        capacities = {}
        for cpu in self.system_cpus:
            node = Path(f'/sys/devices/system/cpu/cpu{cpu}')
            try:
                capacity = node/'cpu_capacity'
                capacities[cpu] = int((capacity if capacity.exists() else node/'cpufreq/cpuinfo_max_freq').read_text())
            except (OSError,ValueError):
                capacities = {}; break
        self.little_cpus = {cpu for cpu,value in capacities.items() if value == min(capacities.values())} if capacities else self.system_cpus.copy()
        self.prefs = preferences(CATALOG)
        if self.prefs.get('mangohud_mode') == 'takeover': mango_config(self.prefs)
        set_language(self.prefs['language'])
        self.qt_translator = QTranslator(self); self.translate_dialogs()
        self.state = {}
        self.processes = set()
        self.status_busy = False
        self.audio_queue = {}; self.audio_active = False; self.audio_revision = 0
        self.cursor_position = None
        self.touch_calibration = [1,0,0,0,1,0]
        self.screen_off = set()
        self.error_text = None
        self.setWindowTitle('HandheldDash')
        self.setObjectName('ThorPanel')
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setWindowFlag(Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setMinimumSize(470, 420)
        self.resize(604, 520)
        self.bus = QDBusConnection.systemBus()
        self.hardware = QDBusInterface(NAME, PATH, NAME, self.bus)
        self.hardware.setTimeout(200000)
        self.client=HardwareClient(self.hardware,self)
        self.client.error.connect(self.hardware_error)
        self.client.status.connect(self.receive_status)
        self.client.mutation.connect(self.mutation_finished)
        self.bus.connect(NAME,PATH,NAME,'Stick',self.on_stick)
        if not self.bus.connect(NAME, PATH, NAME, 'Button', self.on_button):
            raise RuntimeError('Cannot subscribe to hardware button events')
        self.session = QDBusConnection.sessionBus()
        self.desktop = detect_desktop(self.session,CONFIG,self.start,self.notify,self)
        self.configure_panel_focus()
        self.session.registerService(APP)
        self.endpoint = ControlEndpoint(self)
        self.session.registerObject('/Control', self, QDBusConnection.RegisterOption.ExportAdaptors)
        self.theme_css = '''
            QWidget { background:#222331; color:#f2efff; font-size:14px; }
            QWidget#ThorPanel { background:#222331; }
            QLabel#Title { font-size:22px; font-weight:700; }
            QLabel#HeaderTitle { font-size:14px; font-weight:600; }
            QWidget#Gauge { background:#303144; border-radius:12px; }
            QWidget#Gauge QWidget { background:transparent; }
            QWidget#MetricIcon { background:transparent; }
            QLabel#SectionTitle { background:transparent; color:#b8b5ca; font-size:12px; font-weight:600; }
            QPushButton#MetricValue { background:transparent; border:0; border-radius:0; padding:0; min-height:0; }
            QLabel#MetricReading { font-size:12px; }
            QWidget#Gauge QProgressBar { background:#45465e; }
            QProgressBar { background:#45465e; border:0; border-radius:3px; height:6px; }
            QProgressBar::chunk { background:#a68bff; border-radius:3px; }
            QPushButton { background:#36374a; border:1px solid #45465e; border-radius:13px; padding:10px; min-height:24px; }
            QPushButton:pressed { background:#4c4268; }
            QPushButton:checked { background:#7755d9; border-color:#a58cf8; }
            QPushButton:disabled { color:#79798f; }
            QMenu { background:#303144; color:#f2efff; border:1px solid #45465e; border-radius:8px; padding:6px; menu-scrollable:1; }
            QMenu::item { padding:10px 16px; min-height:24px; border-radius:6px; } QMenu::item:selected { background:#7755d9; }
            QMenu::item:disabled { color:#79798f; } QMenu::separator { height:1px; background:#45465e; margin:5px; }
            QTabWidget::pane { border:0; } QTabBar::tab { padding:6px 8px; background:#303144; }
            QTabBar::tab:selected { background:#7755d9; }
            QLineEdit { background:#303144; border:1px solid #45465e; border-radius:8px; padding:7px; }
            QTabWidget::tab-bar { alignment:left; } QLabel#Notice { color:#b8b5ca; font-size:12px; }
        '''
        self.apply_theme()
        self.theme_watcher=QFileSystemWatcher(self)
        self.theme_watcher.addPath(str(CONFIG.parent))
        self.theme_watcher.directoryChanged.connect(self.apply_theme)
        theme_file=CONFIG.parent/'kdeglobals'
        if theme_file.is_file(): self.theme_watcher.addPath(str(theme_file))
        self.theme_watcher.fileChanged.connect(self.apply_theme)
        self.menu_watcher=QFileSystemWatcher(self)
        for folder in (Path.home()/'.local/share/applications',Path('/usr/local/share/applications'),Path('/usr/share/applications')):
            if folder.is_dir(): self.menu_watcher.addPath(str(folder))
        self.menu_debounce=QTimer(self); self.menu_debounce.setSingleShot(True); self.menu_debounce.setInterval(1000)
        self.menu_debounce.timeout.connect(self.sync_desktop_actions)
        self.menu_watcher.directoryChanged.connect(lambda _:self.menu_debounce.start())
        QTimer.singleShot(1000,self.sync_desktop_actions)
        self.make_shell()
        self.make_control(); self.make_tasks(); self.make_screen(); self.make_fan(); self.make_lighting(); self.make_touchpad(); self.make_settings()
        self.tabs.setTabEnabled(self.touchpad_index,self.desktop.supports('window_focus'))
        self.gamepad_focus.setEnabled(self.desktop.supports('window_focus'))
        self.shot.setEnabled(self.desktop.supports('screenshot'))
        resident = self.prefs.get('resident_tabs',self.page_titles)
        self.tabs.setCurrentIndex(next((i for i,title in enumerate(self.page_titles) if title in resident),self.settings_index))
        self.tabs.currentChanged.connect(self.update_tabs)
        self.update_tabs()
        self.notices = []
        self.notice_text = ''
        self.notice_timer = QTimer(self); self.notice_timer.setSingleShot(True)
        self.notice_timer.setInterval(5000); self.notice_timer.timeout.connect(self.clear_notice)
        for i in range(self.tabs.count()):
            if i == self.touchpad_index: continue
            label = QLabel(''); label.setObjectName('Notice'); label.setWordWrap(True); label.hide()
            self.tabs.widget(i).layout().addWidget(label); self.notices.append(label)
        self.timer = QTimer(self); self.timer.timeout.connect(self.refresh)
        self.desktop_visible = False
        self.install_placement()
        QTimer.singleShot(1000,self.configure_pointer)
        for screen in QApplication.screens():
            screen.orientationChanged.connect(lambda orientation:self.configure_pointer())
        self.refresh()
        QTimer.singleShot(0,lambda:self.set_cpu_affinity(self.prefs['panel_cpu_affinity'],False))

    def sync_desktop_actions(self):
        if not self.desktop.supports('placement'): return
        helper = Path(__file__).resolve().parents[2]/'desktop_launch.py'
        if not helper.exists(): helper = Path('/usr/lib/aynthor/desktop_launch.py')
        self.start(sys.executable,str(helper),'--sync')

    def make_shell(self):
        root = QVBoxLayout(self); root.setContentsMargins(12,12,12,12); root.setSpacing(8)
        header_widget=QWidget(); header_widget.setFixedHeight(44)
        self.header=QHBoxLayout(header_widget); self.header.setContentsMargins(0,0,0,0); self.header.setSpacing(6)
        self.header_title=QLabel('HandheldDash'); self.header_title.setObjectName('HeaderTitle'); self.header_title.setFixedWidth(110)
        self.header.addWidget(self.header_title); self.header.addStretch()
        self.battery_icon = MetricIcon('battery'); self.header.addWidget(self.battery_icon)
        self.battery_text = QLabel('—%'); self.battery_text.setFixedWidth(34); self.battery_text.setStyleSheet('font-size:12px;'); self.header.addWidget(self.battery_text)
        self.clock = QLabel(); self.clock.setFixedWidth(40); self.clock.setStyleSheet('font-size:12px;'); self.header.addWidget(self.clock)
        close = QPushButton('×'); close.setFixedSize(44,44); close.setStyleSheet('padding:0; min-height:0; border-radius:10px;'); close.clicked.connect(self.hide); self.header.addWidget(close); close.hide()
        root.addWidget(header_widget)
        self.tabs = QTabWidget(); self.tabs.setTabBar(ControlTabBar()); self.tabs.setTabPosition(QTabWidget.TabPosition.South)
        self.tabs.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Ignored); root.addWidget(self.tabs,1)
        self.page_titles = []

    def apply_theme(self):
        from PyQt6.QtCore import QSettings
        file = CONFIG.parent/'kdeglobals'
        stamp = file.stat().st_mtime_ns if file.exists() else 0
        if getattr(self,'theme_stamp',None) == stamp: return
        self.theme_stamp = stamp
        settings = QSettings(str(file),QSettings.Format.IniFormat)
        palette = QApplication.instance().palette()
        def color(group,key,role):
            value = settings.value(group+'/'+key)
            if isinstance(value,list): value = ','.join(value)
            if value:
                try: return QColor(*map(int,str(value).split(',')[:3])).name()
                except (TypeError,ValueError): pass
            return palette.color(role).name()
        window = color('Colors:Window','BackgroundNormal',QPalette.ColorRole.Window)
        text = color('Colors:Window','ForegroundNormal',QPalette.ColorRole.WindowText)
        button = color('Colors:Button','BackgroundNormal',QPalette.ColorRole.Button)
        accent = color('Colors:Selection','BackgroundNormal',QPalette.ColorRole.Highlight)
        muted = color('Colors:Window','ForegroundInactive',QPalette.ColorRole.PlaceholderText)
        THEME.update({key:value for keys,value in [(['#222331'],window),(['#f2efff','#ffffff','#e5ddff'],text),(['#303144','#36374a'],button),(['#a68bff','#bca6ff','#7755d9','#a58cf8','#4c4268'],accent),(['#45465e','#79798f','#b8b5ca','#79718d'],muted)] for key in keys})
        css = self.theme_css
        for old,new in THEME.items(): css = css.replace(old,new)
        selected_text = color('Colors:Selection','ForegroundNormal',QPalette.ColorRole.HighlightedText)
        css += 'QPushButton:checked, QMenu::item:selected, QTabBar::tab:selected { color:'+selected_text+'; }'
        QApplication.instance().setStyleSheet(css)
        control_icon.cache_clear()
        for widget in self.findChildren(StateButton): widget.render()
        for widget in self.findChildren(EmbeddedPopup): widget.update_theme()
        self.update()

    def install_placement(self):
        self.desktop.install_placement(self.prefs,{role:DEVICE.screen_name(role,QApplication.screens()) for role in ('top','bottom')})

    def notify(self,text):
        if not text:
            self.notice_text = ''; self.clear_notice(); return
        if text == self.notice_text: return
        self.notice_text = text
        for label in self.notices:
            label.setText(text); label.setVisible(bool(text))
        self.notice_timer.start()

    def clear_notice(self):
        self.notice_timer.stop(); self.error_text = None
        for label in self.notices:
            label.setText(''); label.hide()

    def page(self, title, widget=None):
        widget = widget if widget is not None else QWidget(); layout = QVBoxLayout(widget)
        self.page_titles.append(title)
        self.tabs.addTab(widget, tr(title))
        return layout

    def update_tabs(self, index=None):
        resident = self.prefs.get('resident_tabs',self.page_titles)
        current = self.tabs.currentIndex()
        for i,title in enumerate(self.page_titles):
            self.tabs.setTabVisible(i,title in resident or i == self.settings_index or i == current)

    def pin_tab(self, title, pinned):
        resident = set(self.prefs.get('resident_tabs',self.page_titles))
        if pinned: resident.add(title)
        else: resident.discard(title)
        self.set_pref('resident_tabs',[t for t in self.page_titles if t in resident])
        self.update_tabs()

    def open_tab(self, index):
        self.tabs.setTabVisible(index,True); self.tabs.setCurrentIndex(index)

    def make_touchpad(self):
        self.touchpad_index = self.tabs.count()
        layout = self.page('Touchpad')
        layout.setContentsMargins(0,0,0,0)
        self.touchpad = Touchpad(self); layout.addWidget(self.touchpad,1)

    def exit_touchpad(self):
        if self.touchpad.isVisible():
            self.touchpad.heartbeat.stop(); self.touchpad.send_region(False)
            self.open_tab(0)

    def keyPressEvent(self,event):
        if event.key() == Qt.Key.Key_Escape:
            if self.touchpad.isVisible(): self.exit_touchpad()
            event.accept(); return
        super().keyPressEvent(event)

    def focus_upper(self):
        self.desktop.focus_touchpad(DEVICE.screen_name('top',QApplication.screens()),lambda:self.touchpad.isVisible())

    def configure_pointer(self):
        calibration=self.desktop.configure_pointer(DEVICE.screen_name('bottom',QApplication.screens()),DEVICE.touchscreen,self.prefs,self.set_pref)
        if calibration is not None: self.touch_calibration=calibration

    def center_pointer(self):
        screen = next((s for s in QApplication.screens() if s.name() == DEVICE.screen_name('top',QApplication.screens())),None)
        if screen is None or self.cursor_position is None:
            self.notify(tr('Top-screen pointer interface is unavailable')); return
        rect = screen.geometry(); dx=dy=0
        if not rect.contains(self.cursor_position.toPoint()):
            delta = QPointF(rect.center())-self.cursor_position
            dx,dy = int(delta.x()),int(delta.y())
        if dx or dy: self.call('Pointer',[max(-32767,min(32767,dx)),max(-32767,min(32767,dy)),0,0],quiet=True)

    def button(self, text, callback, checkable=False):
        button = QPushButton(text); button.setIconSize(QSize(ICON_SIZE,ICON_SIZE)); button.setCheckable(checkable); button.clicked.connect(callback)
        return button

    def start(self,*args):
        process = QProcess(self); self.processes.add(process)
        process.errorOccurred.connect(lambda error: self.notify('Cannot start: '+args[0]+' · '+process.errorString()))
        def finished(code,status):
            if code: self.notify(process.readAllStandardError().data().decode(errors='replace') or f'{args[0]} exit code {code}')
            self.processes.discard(process); process.deleteLater()
        process.finished.connect(finished); process.start('taskset',['--cpu-list',','.join(map(str,sorted(self.system_cpus))),*args])

    def action(self, action):
        if action == 'none': return
        if action == 'reset-touchscreen': self.set('reset-touchscreen',[]); return
        if action == 'escape' and self.isVisible():
            if self.touchpad.isVisible(): self.exit_touchpad()
            return
        if action in ('lighting-left','lighting-right'):
            if self.isVisible() and self.tabs.currentIndex() == self.lighting_index: self.lighting_pads[0 if action=='lighting-left' else 1].toggle_color()
            return
        if action == 'panel': self.Toggle(); return
        if action == 'screenshot': self.screenshot(); return
        self.hide()
        def perform():
            if action == 'escape': self.set('key',['escape'])
            elif action == 'desktop': self.desktop.shortcut('Show Desktop')
            elif action == 'overview': self.desktop.shortcut('Overview')
            elif action == 'swap': self.desktop.swap_active()
        QTimer.singleShot(180,perform)

    @pyqtSlot('uint',str,float,float)
    def on_stick(self,uid,side,x,y):
        if uid != os.getuid() or not self.isVisible() or self.tabs.currentIndex()!=self.lighting_index: return
        self.lighting_pads[0 if side=='left' else 1].rotate_stick(x,y)

    @pyqtSlot('uint',str)
    def on_button(self, uid, action):
        if uid != os.getuid(): return
        if action=='gamepad-focus': self.focus_gamepad(); return
        if action in ('lighting-left','lighting-right'): self.action(action); return
        if action == 'panel': self.Toggle(); return
        configured = self.prefs.get(action,'none')
        if configured == 'command':
            try:
                argv = shlex.split(self.prefs.get(action+'_command',''))
                if argv: self.start(*argv)
            except ValueError as e: self.notify(str(e))
        else: self.action(configured)

    def configure_panel_focus(self):
        self.desktop.configure_panel_focus()

    @pyqtSlot()
    def Toggle(self):
        if self.screen_off:
            for role in list(self.screen_off):
                name=DEVICE.screen_name(role,QApplication.screens())
                if name: self.set_screen_display(name,True)
            if self.isVisible(): return
        if self.isVisible(): self.hide()
        else:
            if self.tabs.currentIndex()==self.tasks_index: self.refresh_tasks()
            self.setWindowTitle('HandheldDash')
            self.setWindowFlag(Qt.WindowType.WindowDoesNotAcceptFocus,False)
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating,True)
            self.place(); self.showFullScreen(); self.raise_(); self.refresh()

    def showEvent(self,event):
        super().showEvent(event)
        if hasattr(self,'timer'):
            self.timer.start(2000); self.sync_monitoring()
            self.desktop.show_panel()

    def hideEvent(self,event):
        super().hideEvent(event)
        if hasattr(self,'timer'):
            self.timer.stop(); self.sync_monitoring(); self.desktop.hide_panel()

    @pyqtSlot()
    def Settings(self):
        self.setWindowTitle('HandheldDash Settings')
        self.setWindowFlag(Qt.WindowType.WindowDoesNotAcceptFocus,False)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating,False)
        self.tabs.setCurrentIndex(self.settings_index); self.place(); self.showFullScreen(); self.raise_(); self.activateWindow(); self.refresh()

    @pyqtSlot(str, result=bool)
    def Snapshot(self,path):
        return self.grab().save(path)

    def snapshot_english(self,path):
        language=self.prefs.get('language','system'); tab=self.tabs.currentIndex(); editing=self.dashboard_editing; size=self.size()
        title=self.header_title.source_text; popups=[popup for popup in self.findChildren(EmbeddedPopup) if not popup.isHidden()]
        def translate(language):
            set_language(language); self.translate_dialogs()
            for widget in self.findChildren(QWidget):
                if hasattr(widget,'retranslate'): widget.retranslate()
                if isinstance(widget,StateButton): widget.render()
            for index,name in enumerate(self.page_titles): self.tabs.setTabText(index,tr(name))
            if self.state: self.update_state(json.dumps(self.state))
        try:
            for popup in popups: popup.hide()
            screen=next((screen for screen in QApplication.screens() if screen.name() == DEVICE.screen_name('bottom',QApplication.screens())),None)
            if not self.isVisible() and screen is not None: self.resize(screen.geometry().size())
            self.dashboard_editing=False; self.header_title.setText('HandheldDash'); self.open_tab(0)
            translate('en'); self.apply_dashboard_layout(); QApplication.processEvents()
            return self.grab().save(path)
        finally:
            self.dashboard_editing=editing; self.header_title.setText(title); translate(language)
            self.apply_dashboard_layout(); self.tabs.setCurrentIndex(tab)
            if not self.isVisible(): self.resize(size)
            for popup in popups: popup.show()

    def place(self):
        screen = next((s for s in QApplication.screens() if s.name() == DEVICE.screen_name('bottom',QApplication.screens())),QApplication.primaryScreen())
        self.winId(); self.windowHandle().setScreen(screen)
        self.resize(min(604,screen.availableGeometry().width()-12),min(520,screen.availableGeometry().height()-12))
        self.move(screen.availableGeometry().center()-self.rect().center())

    def closeEvent(self,event):
        event.ignore(); self.hide()

    @pyqtSlot(str)
    def WindowList(self,raw):
        try:
            records=json.loads(raw); self.task_records=[]
            for record in records:
                if record['pid'] == os.getpid(): continue
                path=Path('/proc')/str(record['pid'])
                try:
                    record['starttime']=(path/'stat').read_text(encoding='utf-8',errors='replace').rsplit(')',1)[1].split()[19]
                except (OSError,ValueError,IndexError):
                    continue
                self.task_records.append(record)
            self.change_task_page(0)
        except (OSError,ValueError,KeyError,IndexError) as e: self.notify(str(e))
