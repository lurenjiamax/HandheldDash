#!/usr/bin/python
# SPDX-License-Identifier: LGPL-3.0-or-later
# Copyright (c) 2026 lurenjiamax
"""Unprivileged, touch-friendly Thor control panel and settings."""
import csv
from array import array
import math
from functools import lru_cache
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time

from PyQt6.QtCore import QObject, QMetaType, QProcess, QTimer, Qt, QEvent, QSize, QRectF, QPointF, QLocale, QTranslator, QLibraryInfo, QStandardPaths, QMimeData, pyqtClassInfo, pyqtSlot, pyqtSignal
from PyQt6.QtDBus import QDBus, QDBusArgument, QDBusAbstractAdaptor, QDBusConnection, QDBusInterface, QDBusPendingCallWatcher, QDBusPendingReply, QDBusMessage, QDBusVariant
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap, QPolygonF, QImage, QConicalGradient, QBrush, QPalette, QDrag
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton, QTabWidget, QTabBar, QProgressBar, QSlider, QStackedWidget, QFormLayout, QLineEdit, QColorDialog, QMenu, QStyle, QStyleOptionSlider, QStyleOptionButton, QStylePainter, QScrollArea, QSpinBox, QDialog, QProxyStyle, QSizePolicy)

sys.path.append('/usr/lib/aynthor')
from localization import Label as QLabel, Button as LocalizedButton, set_language, tr, CATALOG

NAME = 'org.aynthor.Hardware1'
PATH = '/org/aynthor/Hardware1'
APP = 'org.aynthor.Control'
ICON_SIZE = 24
VERSION_FILE = Path('/usr/share/aynthor/version')
VERSION = VERSION_FILE.read_text().strip() if VERSION_FILE.is_file() else '1.0.0-dev'
CONFIG = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config'))) / 'aynthor'
DATA = Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share'))) / 'aynthor'
PREFS = CONFIG / 'settings.json'
ACTIONS = {'escape': 'Esc', 'desktop': 'Show desktop', 'overview': 'Overview', 'panel': 'Control panel', 'screenshot': 'Screenshot', 'swap': 'Move to other display', 'none': 'Disabled', 'command': 'Custom command', 'reset-touchscreen':'Reset touchscreen driver'}

# Stable component IDs keep saved layouts independent of UI language.
DASHBOARD_COMPONENTS = {
    'controls': [('performance','Performance'),('fan_link','Fan linkage'),('input','Input mode'),('focus','Gamepad focus'),('caffeine','Caffine'),('vibration','Vibration'),('lighting','Lighting'),('bypass','Bypass charging')],
    'metrics': [('cpu','CPU'),('gpu','GPU'),('temp','Temperature'),('fan','Fan'),('ram','RAM'),('battery','Power')],
    'actions': [('screenshot','Screenshot'),('overview','Overview'),('hud','FPS overlay')],
}
DASHBOARD_SECTIONS = {'controls':'Quick controls','metrics':'Live metrics','actions':'Quick actions'}
DASHBOARD_TILES = {
    'performance': ('Performance mode','gauge'), 'fan_link': ('Fan mode','fan'),
    'input': ('Input mode','gamepad-2'), 'focus': ('Focus','monitor'),
    'caffeine': ('Caffine','coffee'), 'vibration': ('Vibration','vibrate'),
    'lighting': ('Lighting','palette'), 'screenshot': ('Screenshot','camera'),
    'overview': ('Overview','panels-top-left'), 'hud': ('FPS overlay','eye'),
    'brightness': ('Brightness','sun'), 'volume': ('Volume','volume-2'),
    'move_app': ('Move current app','arrow-left-right'),
}
CORE_TILES = ('performance','fan_link')
METRIC_TITLES = {'cpu':'CPU','gpu':'GPU','temperature':'Temperature','fan':'Fan','memory':'RAM','battery':'Power','load':'System load','network':'Network speed','disk_io':'Disk IO'}
METRIC_ICONS = {'cpu':'cpu','gpu':'gpu','temperature':'thermometer','fan':'fan','memory':'memory-stick','battery':'plug-zap','load':'activity','network':'network','disk_io':'disk'}
DEFAULT_TILES = ['performance','fan_link','input','focus','caffeine','vibration','lighting','screenshot','overview','hud','brightness','volume']
TILE_MIME = 'application/x-handhelddash-tile'


def dashboard_preset(name='default'):
    tiles = {
        'gaming': ['performance','fan_link','input','focus','vibration','screenshot','hud','volume'],
        'monitoring': ['performance','fan_link','caffeine','brightness','volume','screenshot'],
    }.get(name,DEFAULT_TILES)
    return {'version':3,'tiles':list(CORE_TILES)+[key for key in tiles if key not in CORE_TILES],'metrics':True}


def dashboard_layout(raw):
    """Validate tile IDs and migrate the original section-based layout."""
    defaults = dashboard_preset()
    if not isinstance(raw,dict): return defaults
    if 'tiles' in raw:
        if not isinstance(raw['tiles'],list): return defaults
        tiles = []
        for key in raw['tiles']:
            if isinstance(key,str) and key in DASHBOARD_TILES and key not in tiles: tiles.append(key)
        result={'version':4,'tiles':tiles[:12],'metrics':raw.get('metrics') if isinstance(raw.get('metrics'),bool) else True}
        for key in ('show_fps','show_cap'): result[key]=raw.get(key,True) is not False
        result['metric_mode']='percent' if raw.get('metric_mode') == 'percent' else 'mhz'
        modes=raw.get('metric_modes',{})
        result['metric_modes']={key:('percent' if isinstance(modes,dict) and modes.get(key,raw.get('metric_mode')) == 'percent' else 'mhz') for key in ('cpu','gpu')}
        sources=raw.get('metric_sources',{})
        result['metric_sources']={key:(sources[key][:100] if isinstance(sources,dict) and isinstance(sources.get(key),str) else 'all') for key in ('network','disk_io')}
        order=raw.get('metric_order',['cpu','gpu','temperature','fan','memory','battery'])
        result['metric_order']=list(dict.fromkeys(key for key in order if isinstance(key,str) and key in METRIC_TITLES))[:6] if isinstance(order,list) else ['cpu','gpu','temperature','fan','memory','battery']
        return result
    if not any(isinstance(raw.get(section),list) for section in ('controls','actions','metrics')): return defaults
    tiles = []
    for section in ('controls','actions'):
        values = raw.get(section)
        if not isinstance(values,list):
            tiles.extend(key for key in defaults['tiles'] if key in dict(DASHBOARD_COMPONENTS[section]) and key not in tiles)
            continue
        seen = set()
        for item in values:
            if not isinstance(item,dict): continue
            key = item.get('id')
            if not isinstance(key,str) or key not in dict(DASHBOARD_COMPONENTS[section]) or key in seen: continue
            seen.add(key)
            if key in DASHBOARD_TILES and item.get('visible',True) is not False: tiles.append(key)
        tiles.extend(key for key in defaults['tiles'] if key in dict(DASHBOARD_COMPONENTS[section]) and key not in seen)
    metrics = raw.get('metrics')
    visible_metrics = any(isinstance(item,dict) and item.get('visible',True) is not False for item in metrics) if isinstance(metrics,list) else True
    return {'version':3,'tiles':list(CORE_TILES)+[key for key in tiles if key not in CORE_TILES],'metrics':visible_metrics}


def preferences():
    defaults = {'back': 'escape', 'home': 'desktop', 'back_command': '', 'home_command': '', 'fps_limit': 60, 'hud': True, 'autolock': False, 'language': 'system', 'launch_screen': '', 'app_screens': {}, 'screenshot_mode': 'top', 'panel_cpu_affinity': 'little', 'mangohud_mode':'release', 'back-home':'reset-touchscreen', 'back-home_command':''}
    if PREFS.exists():
        try:
            defaults.update(json.loads(PREFS.read_text()))
        except (ValueError, OSError):
            pass
    if 'resident_tabs' in defaults:
        legacy = {value:key for key,values in CATALOG.items() for value in values.values()}
        defaults['resident_tabs'] = [legacy.get(title,title) for title in defaults['resident_tabs']]
    defaults.pop('mangohud_auto',None)
    return defaults


def save(data):
    CONFIG.mkdir(parents=True, exist_ok=True)
    stage = PREFS.with_suffix('.new')
    stage.write_text(json.dumps(data, indent=2))
    stage.replace(PREFS)


def mango_config(prefs):
    CONFIG.mkdir(parents=True, exist_ok=True)
    logs = Path('/var/cache/handhelddash/fps')
    if not logs.is_dir(): logs = DATA / 'fps'
    logs.mkdir(parents=True, exist_ok=True)
    file = CONFIG / 'MangoHud.conf'
    file.write_text(f"fps\nframetime\ncpu_stats\ngpu_stats\nfps_limit={prefs['fps_limit']}\nno_display={int(not prefs['hud'])}\noutput_folder={logs}\nautostart_log=1\nlog_interval=500\nlog_duration=0\ncontrol=aynthor-mango-%p\n")
    return file


THEME = {}

def theme_color(value):
    return QColor(THEME.get(value,value))


class MetricIcon(QWidget):
    """Draw the measured value; fan motion uses tachometer RPM."""
    def __init__(self, kind):
        super().__init__()
        self.kind = kind; self.fraction = 0; self.target_fraction=0; self.rpm = 0; self.angle = 0; self.charging = False; self.fast_charging = False
        self.setObjectName('MetricIcon'); self.setFixedSize(ICON_SIZE,ICON_SIZE)
        self.last_frame = time.monotonic()
        self.timer = QTimer(self); self.timer.timeout.connect(self.animate)
        if kind == 'fan': self.timer.start(50)

    def animate(self):
        now = time.monotonic(); elapsed = now-self.last_frame; self.last_frame = now
        if not self.isVisible() and not (getattr(self,'linked_tile',None) is not None and self.linked_tile.isVisible()): return
        self.fraction+=(self.target_fraction-self.fraction)*min(1,elapsed*8)
        if self.kind == 'fan' and self.rpm:
            # Display rotation is scaled for legibility; its speed follows real RPM.
            self.angle = (self.angle+min(120,self.rpm*.018)*min(elapsed,.1))%360; self.update()
        if abs(self.target_fraction-self.fraction)>.001 or self.charging: self.update()

    def reading(self, fraction, rpm=0, charging=False, fast_charging=False):
        self.target_fraction = max(0,min(1,fraction or 0)); self.fraction=self.target_fraction; self.rpm = rpm or 0; self.charging = charging; self.fast_charging = fast_charging; self.update()

    def paintEvent(self,event):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        name = {'temp':'thermometer','ram':'memory-stick','gpu':'gpu','load':'activity','disk_io':'disk'}.get(self.kind,self.kind)
        if self.kind == 'battery':
            name = ('battery-fast' if self.fast_charging else 'battery-charging') if self.charging else ('battery-low' if self.fraction <= .2 else 'battery-medium' if self.fraction <= .6 else 'battery-full')
        if self.kind == 'power': name='plug-zap' if self.charging else 'zap'
        if self.kind == 'fan': p.translate(ICON_SIZE/2,ICON_SIZE/2); p.rotate(self.angle); p.translate(-ICON_SIZE/2,-ICON_SIZE/2)
        control_icon(name,enabled=self.kind == 'battery' and self.fast_charging).paint(p,0,0,ICON_SIZE,ICON_SIZE)


@lru_cache(maxsize=128)
def control_icon(kind, enabled=False, color=None):
    names = {'speed': 'gauge',
             'smart': 'sparkles', 'memory': 'memory-stick', 'gamepad': 'gamepad-2',
             'rgb': 'palette'}
    name = names.get(kind, kind)
    local = Path(__file__).resolve().parent.parent / 'packaging/icons' / (name + '.svg')
    file = local if local.exists() else Path('/usr/share/aynthor/icons') / (name + '.svg')
    if not file.exists(): return QIcon.fromTheme(name)
    from PyQt6.QtSvg import QSvgRenderer
    ink = color or theme_color('#a68bff' if enabled else '#f2efff').name()
    svg = file.read_text().replace('#e5ddff',theme_color('#f2efff').name()).replace('#c4b5fd',theme_color('#f2efff').name()).replace('currentColor',ink)
    scale = QApplication.primaryScreen().devicePixelRatio()
    image = QPixmap(round(ICON_SIZE*scale),round(ICON_SIZE*scale)); image.setDevicePixelRatio(scale); image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image); QSvgRenderer(svg.encode()).render(painter,QRectF(0,0,ICON_SIZE,ICON_SIZE)); painter.end()
    return QIcon(image)


class ControlStyle(QProxyStyle):
    def pixelMetric(self,metric,option=None,widget=None):
        if metric == QStyle.PixelMetric.PM_SmallIconSize: return ICON_SIZE
        return super().pixelMetric(metric,option,widget)


class QPushButton(LocalizedButton):
    """Give action/menu icons a short interaction pulse, not perpetual motion."""
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs); self.motion_started=0; self.motion_progress=1
        self.motion_timer=QTimer(self); self.motion_timer.setInterval(16); self.motion_timer.timeout.connect(self.animate_motion)
        self.pressed.connect(self.start_motion)

    def start_motion(self):
        return

    def animate_motion(self):
        self.motion_progress=min(1,(time.monotonic()-self.motion_started)/.2); self.update()
        if self.motion_progress>=1: self.motion_timer.stop()

    def paintEvent(self,event):
        if self.icon().isNull() or self.motion_progress>=1: return super().paintEvent(event)
        painter=QStylePainter(self); option=QStyleOptionButton(); self.initStyleOption(option)
        icon=option.icon; option.icon=QIcon(); painter.drawControl(QStyle.ControlElement.CE_PushButton,option)
        side=self.iconSize().width(); x=(self.width()-side)/2 if not self.text() else 12; y=(self.height()-side)/2
        scale=1-.14*math.sin(math.pi*self.motion_progress)
        painter.translate(x+side/2,y+side/2); painter.scale(scale,scale)
        icon.paint(painter,round(-side/2),round(-side/2),side,side)


class TaskButton(QPushButton):
    held = pyqtSignal()

    def __init__(self,*args):
        super().__init__(*args)
        self.holding = False
        self.hold_timer = QTimer(self); self.hold_timer.setSingleShot(True); self.hold_timer.setInterval(550)
        self.hold_timer.timeout.connect(self.on_hold)

    def on_hold(self):
        self.holding = True; self.setDown(False); self.held.emit()

    def mousePressEvent(self,event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.holding = False; self.hold_timer.start()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self,event):
        self.hold_timer.stop()
        if self.holding:
            self.setDown(False); event.accept(); return
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self,event):
        if not self.rect().contains(event.pos()): self.hold_timer.stop()
        super().mouseMoveEvent(event)

class TouchSlider(QSlider):
    """Absolute tap/drag position, with user edits separate from device readings."""
    edited = pyqtSignal(int)

    def __init__(self, orientation):
        super().__init__(orientation)
        self.setMinimumHeight(38)
        self.commit_timer = QTimer(self); self.commit_timer.setSingleShot(True)
        self.commit_timer.setInterval(80)
        self.commit_timer.timeout.connect(lambda:self.edited.emit(self.value()))
        self.sliderReleased.connect(self.commit)

    def paintEvent(self,event):
        p=QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        box=QRectF(12,(self.height()-16)/2,max(1,self.width()-24),16)
        option=QStyleOptionSlider(); self.initStyleOption(option)
        fraction=(self.value()-self.minimum())/max(1,self.maximum()-self.minimum())
        x=box.right()-fraction*box.width() if option.upsideDown else box.left()+fraction*box.width()
        color=theme_color('#a68bff' if self.isEnabled() else '#666477')
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(theme_color('#303144')); p.drawRoundedRect(box,8,8)
        fill=QRectF(x if option.upsideDown else box.left(),box.top(),fraction*box.width(),box.height())
        p.setBrush(color); p.drawRoundedRect(fill,8,8); p.drawEllipse(QPointF(x,box.center().y()),10,10)

    def move_to(self, point):
        option = QStyleOptionSlider(); self.initStyleOption(option)
        value = QStyle.sliderValueFromPosition(self.minimum(),self.maximum(),round(point.x()-12),max(1,self.width()-24),option.upsideDown)
        if value != self.value():
            self.setValue(value)
            if not self.commit_timer.isActive(): self.commit_timer.start()

    def mousePressEvent(self,event):
        if event.button() != Qt.MouseButton.LeftButton: return super().mousePressEvent(event)
        self.setSliderDown(True); self.move_to(event.position()); event.accept()

    def mouseMoveEvent(self,event):
        if self.isSliderDown(): self.move_to(event.position()); event.accept()
        else: super().mouseMoveEvent(event)

    def mouseReleaseEvent(self,event):
        if event.button() == Qt.MouseButton.LeftButton and self.isSliderDown():
            self.move_to(event.position()); self.setSliderDown(False); event.accept()
        else: super().mouseReleaseEvent(event)

    def commit(self):
        self.commit_timer.stop(); self.edited.emit(self.value())

    def keyPressEvent(self,event):
        before = self.value(); super().keyPressEvent(event)
        if self.value() != before: self.commit()

    def wheelEvent(self,event):
        before = self.value(); super().wheelEvent(event)
        if self.value() != before: self.commit()


class StateButton(QPushButton):
    """Tap cycles values; a hold opens the same choices without cycling on release."""
    def __init__(self, title, options, callback, icon_only=False):
        super().__init__(title)
        self.icon_only=icon_only
        self.title = title; self.options = options; self.callback = callback
        self.current = options[0][0]; self.held = False; self.menu = None
        self.previous_icon=QIcon(); self.icon_kind=None; self.icon_transition=1; self.icon_started=0
        self.icon_timer=QTimer(self); self.icon_timer.setInterval(16); self.icon_timer.timeout.connect(self.animate_icon)
        self.setIconSize(QSize(ICON_SIZE,ICON_SIZE)); self.setMinimumHeight(32)
        self.hold_timer = QTimer(self); self.hold_timer.setSingleShot(True)
        self.hold_timer.setInterval(550); self.hold_timer.timeout.connect(self.open_options)
        self.pressed.connect(self.begin_hold); self.released.connect(self.hold_timer.stop)
        self.clicked.connect(self.cycle); self.render()

    def begin_hold(self):
        self.held = False; self.hold_timer.start()

    def cycle(self):
        if self.held: return
        values = [o[0] for o in self.options]
        index = values.index(self.current) if self.current in values else -1
        self.choose(self.options[(index+1)%len(values)][0])

    def choose(self,value):
        self.current=value; self.render(); self.callback(value)

    def show_value(self,value):
        self.current=value; self.render()

    def render(self):
        option = next((o for o in self.options if o[0] == self.current),None)
        label=option[1] if option else self.title
        self.setText('' if self.icon_only else label)
        kind=option[2] if option else 'gauge'
        self.icon_transition=1; self.icon_timer.stop()
        self.icon_kind=kind; self.setIcon(control_icon(kind))
        self.setAccessibleName(tr(self.title)+': '+tr(label))
        self.setToolTip(tr(self.title)+': '+tr(label) if self.icon_only or self.property('dashboard') else tr(self.title))

    def animate_icon(self):
        self.icon_transition=min(1,(time.monotonic()-self.icon_started)/.22); self.update()
        if self.icon_transition>=1: self.icon_timer.stop()

    def paint_icon(self,painter,kind,x,y,side,color=None):
        painter.save()
        if self.icon_transition<1:
            painter.setOpacity(1-self.icon_transition); self.previous_icon.paint(painter,x,y,side,side)
        painter.setOpacity(self.icon_transition); control_icon(kind,color=color).paint(painter,x,y,side,side)
        painter.restore()

    def open_options(self):
        if not self.isDown(): return
        self.held = True; self.setDown(False)
        self.menu = QMenu(self.window()); self.menu.setTitle(tr(self.title))
        self.menu.setMaximumHeight(max(120,self.screen().availableGeometry().height()-40))
        for value,title,icon in self.options:
            action = self.menu.addAction(control_icon(icon),tr(title))
            action.setCheckable(True); action.setChecked(value == self.current)
            action.triggered.connect(lambda checked=False,v=value:self.choose(v))
        self.menu.aboutToHide.connect(self.menu.deleteLater)
        self.menu.popup(self.mapToGlobal(self.rect().bottomLeft()))

    def mouseMoveEvent(self,event):
        if not self.rect().contains(event.position().toPoint()): self.hold_timer.stop()
        super().mouseMoveEvent(event)

    def sizeHint(self):
        hint=super().sizeHint()
        hint.setWidth(max(hint.width(),self.fontMetrics().horizontalAdvance(self.text())+ICON_SIZE+32))
        return hint

    def minimumSizeHint(self): return self.sizeHint()

    def paintEvent(self,event):
        painter = QStylePainter(self); option = QStyleOptionButton(); self.initStyleOption(option)
        painter.drawControl(QStyle.ControlElement.CE_PushButtonBevel,option)
        if self.objectName() == 'FpsLimit':
            painter.setPen(self.palette().buttonText().color())
            painter.drawText(self.rect(),Qt.AlignmentFlag.AlignCenter,'∞' if self.current == 0 else tr('Cap')+f' {self.current}')
            return
        side = ICON_SIZE; x = 0 if self.objectName() == 'MetricValue' else 12
        if isinstance(self,TemperatureButton): side=0; x=-8
        else: self.paint_icon(painter,self.icon_kind,x,(self.height()-side)//2,side)
        painter.setPen(self.palette().buttonText().color())
        rect = self.rect().adjusted(x+side+8,0,-12,0)
        text = self.fontMetrics().elidedText(self.text(),Qt.TextElideMode.ElideRight,max(0,rect.width())) if self.property('dashboard') else self.text()
        painter.drawText(rect,Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter,text)


class TemperatureButton(StateButton):
    def render(self):
        super().render()
        option=next((o for o in self.options if o[0] == self.current),None)
        self.setText(option[1].split(' · ')[-1] if option else '— °C')



class ScreenshotButton(StateButton):
    def __init__(self, options, callback, capture):
        super().__init__('Screenshot',options,callback); self.capture = capture

    def cycle(self):
        if not self.held: self.capture()


def paint_quick_tile(widget,painter,title,subtitle,kind,active=False,badge='',core=False,selected=False):
    """Center the complete content block inside either fixed card specification."""
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    background=theme_color('#303144'); accent=theme_color('#a68bff'); ink=theme_color('#f2efff'); muted=theme_color('#b8b5ca')
    if active:
        background=QColor.fromRgbF(background.redF()*.8+accent.redF()*.2,background.greenF()*.8+accent.greenF()*.2,background.blueF()*.8+accent.blueF()*.2)
    if not widget.isEnabled(): ink=muted
    border=accent if active or selected or widget.hasFocus() else theme_color('#45465e')
    pen=QPen(border,2 if selected else 1)
    if selected: pen.setStyle(Qt.PenStyle.DashLine)
    painter.setPen(pen); painter.setBrush(background); painter.drawRoundedRect(QRectF(widget.rect()).adjusted(1,1,-1,-1),10,10)
    if widget.isDown():
        pressed=QColor(accent); pressed.setAlpha(35); painter.setPen(Qt.PenStyle.NoPen); painter.setBrush(pressed)
        painter.drawRoundedRect(QRectF(widget.rect()).adjusted(2,2,-2,-2),10,10)
    title_font=QFont(widget.font()); title_font.setPixelSize(15 if core else 13); title_font.setBold(True)
    state_font=QFont(widget.font()); state_font.setPixelSize(13 if core else 12)
    painter.setFont(title_font); title_h=painter.fontMetrics().height(); title_w=painter.fontMetrics().horizontalAdvance(tr(title))
    painter.setFont(state_font); state_h=painter.fontMetrics().height() if subtitle else 0; state_w=painter.fontMetrics().horizontalAdvance(tr(subtitle))
    if core:
        side=28; available=max(0,widget.width()-side-10-24)
        text_w=min(max(title_w,state_w),available)
        def lines_for(text,font,limit):
            painter.setFont(font); metrics=painter.fontMetrics(); words=tr(text).split(); lines=[]; line=''
            for word in words:
                candidate=(line+' '+word).strip()
                if line and metrics.horizontalAdvance(candidate)>available:
                    lines.append(line); line=word
                else: line=candidate
            if line: lines.append(line)
            if len(lines)>limit: lines=lines[:limit-1]+[' '.join(lines[limit-1:])]
            return [metrics.elidedText(line,Qt.TextElideMode.ElideRight,max(0,round(available))) for line in lines]
        title_limit=2 if title_w>available and 2*title_h+state_h+2<=widget.height()-12 else 1
        state_limit=2 if subtitle and state_w>available and title_limit*title_h+2*state_h+2<=widget.height()-12 else 1
        title_lines=lines_for(title,title_font,title_limit); state_lines=lines_for(subtitle,state_font,state_limit)
        if title_w>available or state_w>available: text_w=available
        left=(widget.width()-side-10-text_w)/2
        if hasattr(widget,'paint_icon'): widget.paint_icon(painter,kind,round(left),round((widget.height()-side)/2),side,ink.name())
        else: control_icon(kind,color=ink.name()).paint(painter,round(left),round((widget.height()-side)/2),side,side)
        title_block=max(1,len(title_lines))*title_h; state_block=len(state_lines)*state_h
        top=(widget.height()-title_block-state_block-(2 if state_lines else 0))/2
        for lines,font,color,line_height,offset in [(title_lines,title_font,ink,title_h,0),(state_lines,state_font,muted,state_h,title_block+2)]:
            painter.setFont(font); painter.setPen(color)
            for index,line in enumerate(lines): painter.drawText(QRectF(left+side+10,top+offset+index*line_height,text_w,line_height),Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter,line)
        rects=[]
        alignment=Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter
    else:
        side=24; block_h=side+6+title_h+2+state_h; top=(widget.height()-block_h)/2
        if hasattr(widget,'paint_icon'): widget.paint_icon(painter,kind,round((widget.width()-side)/2),round(top),side,ink.name())
        else: control_icon(kind,color=ink.name()).paint(painter,round((widget.width()-side)/2),round(top),side,side)
        rects=[QRectF(5,top+side+6,widget.width()-10,title_h),QRectF(5,top+side+6+title_h+2,widget.width()-10,state_h)]
        alignment=Qt.AlignmentFlag.AlignCenter
    for text,font,color,rect in zip((title,subtitle),(title_font,state_font),(ink,muted),rects):
        painter.setFont(font); painter.setPen(color)
        painter.drawText(rect,alignment,painter.fontMetrics().elidedText(tr(text),Qt.TextElideMode.ElideRight,max(0,round(rect.width()))))
    if badge:
        if badge == 'locked':
            control_icon('lock',color=muted.name()).paint(painter,widget.width()-22,5,16,16); return
        font=QFont(widget.font()); font.setPixelSize(11); painter.setFont(font); painter.setPen(muted)
        painter.drawText(QRectF(widget.width()-24,4,20,16),Qt.AlignmentFlag.AlignCenter,badge)


class QuickTile(StateButton):
    def __init__(self,*args):
        super().__init__(*args); self.setMinimumHeight(66); self.core=False; self.editing=False; self.display_state=None
        self.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        self.setProperty('dashboard',True)

    def sizeHint(self): return QSize(104,96)
    def minimumSizeHint(self): return QSize(0,66)

    def presentation(self):
        option = next((value for value in self.options if value[0] == self.current),None)
        subtitle = option[1] if option else self.text()
        if isinstance(self.current,bool) and self.title not in ('Fan linkage','Fan mode'): subtitle = 'On' if self.current else 'Off'
        if self.display_state is not None: subtitle=self.display_state
        active=(isinstance(self.current,bool) and self.current and self.title not in ('Fan linkage','Fan mode')) or (self.title == 'Lighting' and self.current not in (None,'off','disabled',''))
        return subtitle,option[2] if option else 'gauge',active

    def set_display_state(self,value): self.display_state=value; self.update()

    def cycle(self):
        if not self.editing: super().cycle()

    def open_options(self):
        if not self.editing: super().open_options()

    def paintEvent(self,event):
        subtitle,kind,active=self.presentation()
        title='Focus' if self.title == 'Gamepad focus' else self.title
        paint_quick_tile(self,QPainter(self),title,subtitle,kind,active,'',self.core)


class ScreenshotTile(QuickTile):
    def __init__(self,options,callback,capture):
        super().__init__('Screenshot',options,callback); self.capture=capture

    def cycle(self):
        if not self.editing and not self.held: self.capture()


class EditTile(QPushButton):
    """Editor previews share the actual card appearance, without invoking hardware."""
    def __init__(self,editor,selected):
        super().__init__(); self.editor=editor; self.selected=selected; self.key=None; self.dragged=False; self.core=False
        self.context_held=False; self.context_timer=QTimer(self); self.context_timer.setSingleShot(True); self.context_timer.setInterval(550)
        self.context_timer.timeout.connect(self.open_context_menu)
        self.setMinimumHeight(66); self.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        self.setAcceptDrops(selected); self.clicked.connect(self.toggle)

    def set_tile(self,key):
        self.key=key; self.show()
        if key:
            title,kind=DASHBOARD_TILES[key]
            self.setAccessibleName(tr('Select tile' if self.selected else 'Add tile')+': '+tr(title))
            self.setToolTip(tr(title)); self.update()
        else:
            self.setAccessibleName(tr('Add tile')); self.setToolTip(tr('Add tile')); self.update()

    def toggle(self):
        if self.dragged or self.context_held: return
        if self.selected:
            if self.key: self.editor.select_dashboard_tile(self.key)
            else: self.editor.show_available_tiles()
        elif self.key: self.editor.toggle_dashboard_tile(self.key)

    def sizeHint(self): return QSize(104,96)
    def minimumSizeHint(self): return QSize(0,66)

    def paintEvent(self,event):
        if self.key:
            title,kind=DASHBOARD_TILES[self.key]
            subtitle='Add tile'; active=False
            if self.selected:
                subtitle,kind,active=self.editor.dashboard_tiles[self.key].presentation()
            chosen=self.editor.editor_selection == self.key
            paint_quick_tile(self,QPainter(self),title,subtitle,kind,active,'✓' if chosen and self.selected else '+' if not self.selected else '',core=self.core,selected=chosen and self.selected)
        else:
            paint_quick_tile(self,QPainter(self),'Add tile','','sliders-horizontal',badge='+')

    def mousePressEvent(self,event):
        self.dragged=False; self.context_held=False; self.origin=event.position().toPoint(); super().mousePressEvent(event)
        if self.selected and self.key: self.context_timer.start()

    def open_context_menu(self):
        if not self.isDown() or not self.key: return
        self.context_held=True; self.setDown(False); self.editor.open_tile_edit_menu(self.key)

    def mouseMoveEvent(self,event):
        if self.selected and self.key and event.buttons() & Qt.MouseButton.LeftButton and (event.position().toPoint()-self.origin).manhattanLength() >= QApplication.startDragDistance():
            self.context_timer.stop(); self.dragged=True; self.setDown(False)
            mime=QMimeData(); mime.setData(TILE_MIME,self.key.encode())
            drag=QDrag(self); drag.setMimeData(mime); drag.setPixmap(self.grab()); drag.exec(Qt.DropAction.MoveAction)
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self,event):
        self.context_timer.stop()
        if self.dragged or self.context_held: self.setDown(False); event.accept(); return
        super().mouseReleaseEvent(event)

    def dragEnterEvent(self,event):
        if event.mimeData().hasFormat(TILE_MIME): event.acceptProposedAction()

    def dropEvent(self,event):
        source=bytes(event.mimeData().data(TILE_MIME)).decode(errors='replace')
        if self.editor.reorder_dashboard_tile(source,self.key): event.acceptProposedAction()


class EmbeddedPopup(QWidget):
    """Panel-local popup: independent of Wayland activation/fullscreen rules."""
    def __init__(self,panel):
        self.scrim=QWidget(panel); self.scrim.setObjectName('PopupScrim'); self.scrim.setStyleSheet('QWidget#PopupScrim { background:rgba(0,0,0,110); }'); self.scrim.hide()
        super().__init__(self.scrim)
        self.setObjectName('EmbeddedPopup'); self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground,True)
        self.update_theme()
        self.panel=panel; self.scrim.installEventFilter(self)

    def update_theme(self):
        self.setStyleSheet('QWidget#EmbeddedPopup { background:'+theme_color('#222331').name()+'; border:1px solid '+theme_color('#45465e').name()+'; border-radius:12px; }')

    def showEvent(self,event):
        self.scrim.setGeometry(self.panel.rect()); self.scrim.show(); self.scrim.raise_()
        self.move(self.scrim.rect().center()-self.rect().center()); self.raise_()
        super().showEvent(event)

    def show(self):
        self.scrim.setGeometry(self.panel.rect()); self.scrim.show(); self.scrim.raise_()
        super().show()

    def hideEvent(self,event):
        self.scrim.hide(); super().hideEvent(event)

    def accept(self): self.hide()
    def reject(self): self.hide()

    def eventFilter(self,watched,event):
        if watched is self.scrim and event.type() == QEvent.Type.MouseButtonPress:
            self.reject(); return True
        return super().eventFilter(watched,event)


class DashboardPage(QWidget):
    def __init__(self,panel): super().__init__(); self.panel=panel

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self.panel,'dashboard_tile_area'):
            self.panel.layout_dashboard_regions()


class FpsMeter(QLabel):
    clicked=pyqtSignal()
    def mouseReleaseEvent(self,event):
        if event.button() == Qt.MouseButton.LeftButton: self.clicked.emit(); event.accept()
        else: super().mouseReleaseEvent(event)


class ControlTabBar(QTabBar):
    def __init__(self):
        super().__init__(); self.setExpanding(True); self.setUsesScrollButtons(False); self.setElideMode(Qt.TextElideMode.ElideRight)

    def tabSizeHint(self,index):
        count=max(1,sum(self.isTabVisible(i) for i in range(self.count())))
        return QSize(max(44,self.parentWidget().width()//count),44)


class LightingPad(QWidget):
    edited = pyqtSignal(float,float,float)
    colorChosen = pyqtSignal(str)
    detent = pyqtSignal()

    def __init__(self, minimum=0., maximum=1., sensitivity=4.):
        super().__init__()
        self.minimum = max(0.,min(1.,minimum)); self.maximum = max(self.minimum,min(1.,maximum))
        self.sensitivity = max(1.,min(20.,sensitivity)); self.level = 0.; self.color = theme_color('#0080ff')
        self.handle = 1; self.dragging = False; self.color_open = False; self.color_dragging = False; self.controls_enabled = True; self.stick_angle = None; self.stick_remainder = 0.
        self.setMinimumSize(190,220); self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(tr('Brightness and sensitivity'))
        self.setToolTip(tr('Drag the two points: X sets minimum/maximum brightness, Y sets sensitivity.'))

    def plot(self): return QRectF(24,112,self.width()-48,max(60,self.height()-140))

    def point(self,handle):
        box = self.plot(); value = self.minimum if handle == 0 else self.maximum
        return QPointF(box.left()+value*box.width(),box.bottom()-math.log(self.sensitivity)/math.log(20)*box.height())

    def set_output(self,color,level):
        self.color = QColor(color); self.level = max(0.,min(1.,level)); self.update()

    def dial_center(self): return QPointF(self.width()/2,self.height()/2)

    def dial_radius(self): return max(35.,min(self.width()/2-22,self.height()/2-22))

    def color_step(self,index):
        index %= 12
        current=round(max(0.,self.color.hueF())*12)%12
        if index == current: return
        self.color=QColor.fromHsvF(index/12,1,1)
        self.colorChosen.emit(self.color.name()); self.detent.emit(); self.update()

    def rotate_stick(self,x,y):
        if not self.color_open: return
        if math.hypot(x,y) < .5: self.stick_angle=None; return
        angle=math.atan2(-y,x)
        if self.stick_angle is not None:
            self.stick_remainder += (angle-self.stick_angle+math.pi)%(2*math.pi)-math.pi
            steps=math.trunc(self.stick_remainder/(math.pi/6))
            if steps:
                self.stick_remainder -= steps*math.pi/6
                self.color_step(round(max(0.,self.color.hueF())*12)+steps)
        self.stick_angle=angle

    def paintEvent(self,event):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.color_open:
            center=self.dial_center(); radius=self.dial_radius()
            p.setBrush(theme_color('#303144')); p.setPen(QPen(theme_color('#bca6ff'),2))
            p.drawRoundedRect(QRectF(self.rect()).adjusted(3,3,-3,-3),18,18)
            gradient=QConicalGradient(center,0)
            for i in range(7): gradient.setColorAt(i/6,QColor.fromHsvF((i%6)/6,1,1))
            p.setBrush(Qt.BrushStyle.NoBrush); p.setPen(QPen(QBrush(gradient),18)); p.drawEllipse(center,radius,radius)
            selected=round(max(0.,self.color.hueF())*12)%12
            for i in range(12):
                angle=i*math.pi/6; direction=QPointF(math.cos(angle),-math.sin(angle))
                p.setPen(QPen(theme_color('#ffffff') if i==selected else theme_color('#79798f'),4 if i==selected else 2))
                p.drawLine(center+direction*(radius-13),center+direction*(radius+11))
            p.setBrush(self.color); p.setPen(Qt.PenStyle.NoPen); p.drawEllipse(center,15,15)
            names=('Red','Orange','Yellow','Lime','Green','Mint','Cyan','Sky blue','Blue','Purple','Magenta','Rose')
            p.setPen(theme_color('#f2efff')); p.drawText(QRectF(center.x()-radius+20,center.y()+20,2*radius-40,45),Qt.AlignmentFlag.AlignCenter,tr(names[selected])+'\n'+self.color.name().upper())
            return
        center = QPointF(self.width()/2,42)
        p.setBrush(theme_color('#303144')); p.setPen(Qt.PenStyle.NoPen); p.drawEllipse(center,34,34)
        ring = QColor(self.color); ring.setAlphaF(.12+.88*self.level)
        if self.color_open:
            ring = QConicalGradient(center,0)
            for i in range(7): ring.setColorAt(i/6,QColor.fromHsvF((i%6)/6,1,1))
        p.setBrush(Qt.BrushStyle.NoBrush); p.setPen(QPen(QBrush(ring),7)); p.drawEllipse(center,29,29)
        p.setBrush(theme_color('#45465e')); p.setPen(QPen(theme_color('#79798f'),1)); p.drawEllipse(center,20,20)
        p.setPen(theme_color('#f2efff'))
        p.drawText(QRectF(0,79,self.width(),25),Qt.AlignmentFlag.AlignCenter,f'{round(self.minimum*100)}–{round(self.maximum*100)}% · S {round(math.log(self.sensitivity)/math.log(20)*100)}% · {round(self.level*100)}%')
        box = self.plot(); p.setPen(QPen(theme_color('#45465e'),1))
        for fraction in (0.,.5,1.):
            x=box.left()+fraction*box.width(); y=box.top()+fraction*box.height()
            p.drawLine(QPointF(x,box.top()),QPointF(x,box.bottom())); p.drawLine(QPointF(box.left(),y),QPointF(box.right(),y))
        p.setPen(theme_color('#b8b5ca')); p.drawText(QRectF(0,box.top()-3,24,20),Qt.AlignmentFlag.AlignCenter,tr('High'))
        p.drawText(QRectF(0,box.bottom()-17,24,20),Qt.AlignmentFlag.AlignCenter,tr('Low'))
        p.drawText(QRectF(0,box.bottom()+6,self.width(),22),Qt.AlignmentFlag.AlignCenter,tr('Brightness')+' 0 → 100%')
        p.setPen(QPen(self.color,3)); p.drawLine(self.point(0),self.point(1))
        for handle in (0,1):
            p.setBrush(theme_color('#f2efff') if handle == self.handle else self.color)
            p.setPen(QPen(self.color,2)); p.drawEllipse(self.point(handle),10,10)
            p.setPen(theme_color('#222331')); p.drawText(QRectF(self.point(handle).x()-10,self.point(handle).y()-10,20,20),Qt.AlignmentFlag.AlignCenter,'−' if handle == 0 else '+')

    def adjust(self,position):
        box=self.plot(); value=max(0.,min(1.,(position.x()-box.left())/box.width()))
        if self.handle == 0: self.minimum=min(value,self.maximum)
        else: self.maximum=max(value,self.minimum)
        self.sensitivity=20**max(0.,min(1.,(box.bottom()-position.y())/box.height()))
        self.update()

    def toggle_color(self):
        self.color_open = not self.color_open; self.stick_angle=None; self.stick_remainder=0.; self.update()

    def pick_color(self,position):
        center=self.dial_center()
        hue=(math.atan2(center.y()-position.y(),position.x()-center.x())/(2*math.pi))%1
        self.color_step(round(hue*12))

    def mousePressEvent(self,event):
        center=self.dial_center() if self.color_open else QPointF(self.width()/2,42)
        distance=math.hypot(event.position().x()-center.x(),event.position().y()-center.y())
        if event.button() == Qt.MouseButton.LeftButton and (self.color_open or distance <= 38):
            if self.color_open and distance >= self.dial_radius()-24:
                self.color_dragging=True; self.pick_color(event.position())
            else: self.toggle_color()
            event.accept(); return
        if not self.controls_enabled: event.accept(); return
        if event.button() != Qt.MouseButton.LeftButton or not self.plot().adjusted(-12,-12,12,12).contains(event.position()):
            super().mousePressEvent(event); return
        self.setFocus(); self.dragging=True
        self.handle=min((0,1),key=lambda h:abs(self.point(h).x()-event.position().x()))
        self.adjust(event.position()); event.accept()

    def mouseMoveEvent(self,event):
        if self.color_dragging: self.pick_color(event.position()); event.accept(); return
        if self.dragging: self.adjust(event.position()); event.accept()
        else: super().mouseMoveEvent(event)

    def mouseReleaseEvent(self,event):
        if self.color_dragging:
            self.pick_color(event.position()); self.color_dragging=False; event.accept(); return
        if self.dragging and event.button() == Qt.MouseButton.LeftButton:
            self.adjust(event.position()); self.dragging=False
            self.edited.emit(self.minimum,self.maximum,self.sensitivity); event.accept()
        else: super().mouseReleaseEvent(event)

    def keyPressEvent(self,event):
        if event.key() in (Qt.Key.Key_Return,Qt.Key.Key_Space): self.toggle_color(); event.accept(); return
        if self.color_open and event.key() in (Qt.Key.Key_Left,Qt.Key.Key_Right):
            self.color_step(round(max(0.,self.color.hueF())*12)+(1 if event.key()==Qt.Key.Key_Right else -1)); return
        if not self.controls_enabled: super().keyPressEvent(event); return
        key=event.key()
        if key in (Qt.Key.Key_Home,Qt.Key.Key_End): self.handle=0 if key == Qt.Key.Key_Home else 1; self.update(); return
        if key not in (Qt.Key.Key_Left,Qt.Key.Key_Right,Qt.Key.Key_Up,Qt.Key.Key_Down): super().keyPressEvent(event); return
        position=self.point(self.handle); box=self.plot()
        dx=(1 if key == Qt.Key.Key_Right else -1 if key == Qt.Key.Key_Left else 0)*box.width()/100
        dy=(1 if key == Qt.Key.Key_Down else -1 if key == Qt.Key.Key_Up else 0)*box.height()/100
        self.adjust(position+QPointF(dx,dy)); self.edited.emit(self.minimum,self.maximum,self.sensitivity)


class FanCurve(QWidget):
    pointChanged = pyqtSignal(int,int,int)
    def __init__(self):
        super().__init__(); self.curve=None; self.temperature=None
        self.editable=False; self.selected=None; self.dragging=False
        self.setMinimumHeight(200); self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def plot_box(self): return QRectF(42,14,self.width()-58,self.height()-42)

    def move_point(self,temp,percent):
        if not self.editable or self.selected is None: return
        i=self.selected; temps=self.curve['temperatures']; speeds=self.curve['pwm']
        temp=max(20 if i==0 else temps[i-1]//1000+1,min(95 if i==6 else temps[i+1]//1000-1,round(temp)))
        percent=100 if i==6 else max(round(speeds[i-1]/2.55) if i else 0,min(round(speeds[i+1]/2.55),round(percent)))
        self.pointChanged.emit(i,temp,percent)

    def mousePressEvent(self,event):
        if event.button()!=Qt.MouseButton.LeftButton or not self.editable or not self.curve:
            super().mousePressEvent(event); return
        box=self.plot_box(); pos=event.position()
        distances=[math.hypot(pos.x()-(box.left()+(t/1000-20)/80*box.width()),pos.y()-(box.bottom()-v/255*box.height()))
                   for t,v in zip(self.curve['temperatures'],self.curve['pwm'])]
        i=min(range(len(distances)),key=distances.__getitem__)
        if distances[i]<=30:
            self.selected=i; self.dragging=True; self.setFocus(); self.update(); event.accept()

    def mouseMoveEvent(self,event):
        if not self.dragging: super().mouseMoveEvent(event); return
        box=self.plot_box(); pos=event.position()
        self.move_point(20+(pos.x()-box.left())/box.width()*80,(box.bottom()-pos.y())/box.height()*100)
        event.accept()

    def mouseReleaseEvent(self,event):
        self.dragging=False; super().mouseReleaseEvent(event)

    def keyPressEvent(self,event):
        if self.editable and self.selected is not None and event.key() in (Qt.Key.Key_Left,Qt.Key.Key_Right,Qt.Key.Key_Up,Qt.Key.Key_Down):
            i=self.selected; temp=self.curve['temperatures'][i]/1000; percent=self.curve['pwm'][i]/2.55
            self.move_point(temp+(1 if event.key()==Qt.Key.Key_Right else -1 if event.key()==Qt.Key.Key_Left else 0),
                            percent+(1 if event.key()==Qt.Key.Key_Up else -1 if event.key()==Qt.Key.Key_Down else 0))
            event.accept(); return
        super().keyPressEvent(event)

    def paintEvent(self,event):
        if not self.curve: return
        p=QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        box=self.plot_box()
        def point(temp,pwm): return QPointF(box.left()+(temp-20)/80*box.width(),box.bottom()-pwm/255*box.height())
        p.setPen(QPen(theme_color('#45465e'),1))
        for temp in (20,40,60,80,100):
            x=point(temp,0).x(); p.drawLine(QPointF(x,box.top()),QPointF(x,box.bottom()))
            p.setPen(theme_color('#b8b5ca')); p.drawText(QRectF(x-20,box.bottom()+4,40,20),Qt.AlignmentFlag.AlignCenter,f'{temp}°'); p.setPen(QPen(theme_color('#45465e'),1))
        for percent in (0,50,100):
            y=point(20,percent*2.55).y(); p.drawLine(QPointF(box.left(),y),QPointF(box.right(),y))
            p.setPen(theme_color('#b8b5ca')); p.drawText(QRectF(0,y-10,37,20),Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter,f'{percent}%'); p.setPen(QPen(theme_color('#45465e'),1))
        points=[point(min(20,self.curve['temperatures'][0]/1000-5),0),point(self.curve['temperatures'][0]/1000-5,0)]
        for temp,pwm in zip(self.curve['temperatures'],self.curve['pwm']):
            points.append(point(temp/1000,pwm))
        points.append(point(100,255))
        p.save(); p.setClipRect(box)
        p.setPen(QPen(theme_color('#bca6ff'),2.5)); p.drawPolyline(QPolygonF(points)); p.restore()
        for i,(temp,pwm) in enumerate(zip(self.curve['temperatures'],self.curve['pwm'])):
            pos=point(temp/1000,pwm)
            p.setPen(QPen(theme_color('#bca6ff'),2)); p.setBrush(theme_color('#bca6ff' if self.editable else '#303144'))
            p.drawEllipse(pos,8 if i==self.selected else 6,8 if i==self.selected else 6)
            if i==self.selected:
                p.setPen(theme_color('#ffffff'))
                p.drawText(QRectF(max(box.left(),min(pos.x()-65,box.right()-130)),max(box.top(),pos.y()-32),130,22),Qt.AlignmentFlag.AlignCenter,f'{temp/1000:.0f} °C · {pwm/2.55:.0f}%')
        if self.temperature is not None:
            x=point(max(20,min(100,self.temperature)),0).x()
            p.setPen(QPen(theme_color('#7de2ad'),1.5,Qt.PenStyle.DashLine)); p.drawLine(QPointF(x,box.top()),QPointF(x,box.bottom()))


class Choice(QWidget):
    """One value per page; arrows replace dropdown lists."""
    activated = pyqtSignal(int)
    currentIndexChanged = pyqtSignal(int)

    def __init__(self):
        super().__init__()
        self.items = []
        self.index = 0
        row = QHBoxLayout(self); row.setContentsMargins(0,0,0,0)
        prev = QPushButton('‹'); prev.setFixedWidth(38); prev.clicked.connect(lambda: self.step(-1))
        self.label = QLabel('—'); self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nxt = QPushButton('›'); nxt.setFixedWidth(38); nxt.clicked.connect(lambda: self.step(1))
        row.addWidget(prev); row.addWidget(self.label,1); row.addWidget(nxt)

    def addItem(self, text, value=None):
        self.items.append((text,text if value is None else value)); self.draw()

    def addItems(self,items):
        for text in items: self.addItem(text)

    def clear(self):
        self.items.clear(); self.index = 0; self.draw()

    def draw(self):
        self.label.setText(self.currentText())

    def setCurrentIndex(self,index):
        if not self.items or index < 0: return
        changed = self.index != index
        self.index = index % len(self.items); self.draw()
        if changed: self.currentIndexChanged.emit(self.index)

    def step(self,delta):
        if self.items:
            self.setCurrentIndex((self.index+delta)%len(self.items)); self.activated.emit(self.index)

    def currentText(self):
        return self.items[self.index][0] if self.items else '—'

    def currentData(self):
        return self.items[self.index][1] if self.items else None

    def findData(self,value):
        return next((i for i,item in enumerate(self.items) if item[1] == value),-1)

    def setCurrentText(self,text):
        self.setCurrentIndex(next((i for i,item in enumerate(self.items) if item[0] == text),-1))


@pyqtClassInfo('D-Bus Interface', APP)
class ControlEndpoint(QDBusAbstractAdaptor):
    @pyqtSlot()
    def Screenshot(self): self.parent().screenshot()

    def configure_panel_focus(self):
        import configparser
        file=CONFIG.parent/'kwinrulesrc'
        rules=configparser.ConfigParser(interpolation=None,strict=False)
        rules.optionxform=str
        if file.exists(): rules.read(file,encoding='utf-8')
        if not rules.has_section('General'): rules.add_section('General')
        ids=[value for value in rules.get('General','rules',fallback='').split(',') if value]
        rule='handhelddash-panel'
        if rule not in ids: ids.append(rule)
        rules['General']['rules']=','.join(ids)
        rules['General']['count']=str(len(ids))
        rules[rule]={'Description':'HandheldDash panel preserves game focus',
                     'wmclass':'org.aynthor.Control','wmclassmatch':'1',
                     'title':'HandheldDash','titlematch':'1',
                     'acceptfocus':'false','acceptfocusrule':'2'}
        file.parent.mkdir(parents=True,exist_ok=True)
        stage=file.with_suffix('.handhelddash-new')
        with stage.open('w',encoding='utf-8') as stream: rules.write(stream,space_around_delimiters=False)
        stage.replace(file)
        QDBusInterface('org.kde.KWin','/KWin','org.kde.KWin',self.session).call('reconfigure')

    @pyqtSlot()
    def Toggle(self): self.parent().Toggle()

    @pyqtSlot()
    def Settings(self): self.parent().Settings()

    @pyqtSlot()
    def Customize(self):
        self.parent().Settings(); self.parent().open_dashboard_editor()

    @pyqtSlot()
    def ExitTouchpad(self): self.parent().exit_touchpad()

    @pyqtSlot(str,result=bool)
    def Snapshot(self,path): return self.parent().Snapshot(path)

    @pyqtSlot(str,result=bool)
    def SnapshotEnglish(self,path): return self.parent().snapshot_english(path)

    @pyqtSlot(str)
    def Adjustment(self,key):
        if key in ('brightness','volume'): self.parent().open_adjustment(key)

    @pyqtSlot(str,result=bool)
    def PopupSnapshot(self,path):
        popup=QApplication.activePopupWidget()
        if popup is None: popup=next((dialog for dialog in self.parent().adjustment_dialogs.values() if dialog.isVisible()),None)
        return bool(popup and popup.grab().save(path))

    @pyqtSlot(str)
    def WindowList(self,raw): self.parent().WindowList(raw)

    @pyqtSlot(str)
    def CursorPosition(self,raw):
        try: x,y = json.loads(raw)
        except (ValueError,TypeError): return
        if not isinstance(x,(int,float)) or not isinstance(y,(int,float)): return
        self.parent().cursor_position = QPointF(x,y)


class Touchpad(QWidget):
    def __init__(self, panel):
        super().__init__(); self.panel = panel
        self.setMinimumHeight(160)
        self.heartbeat = QTimer(self); self.heartbeat.timeout.connect(self.send_region); self.heartbeat.setInterval(250)

    def send_region(self, enabled=True):
        region = []
        if enabled and self.isVisible():
            screen = next((s for s in QApplication.screens() if s.name() == 'DSI-1'),None)
            if screen:
                geometry = screen.geometry(); origin = self.mapToGlobal(self.rect().topLeft())-geometry.topLeft()
                region = [round(origin.x()*10000/geometry.width()),round(origin.y()*10000/geometry.height()),
                          round((origin.x()+self.width())*10000/geometry.width()),round((origin.y()+self.height())*10000/geometry.height())]
                region = [max(0,min(10000,v)) for v in region]
                if region[0] >= region[2] or region[1] >= region[3]: region = []
        message = QDBusMessage.createMethodCall(NAME,PATH,NAME,'TouchpadRegion')
        top = next((s for s in QApplication.screens() if s.name() == 'DSI-2'),QApplication.primaryScreen())
        rotation = top.angleBetween(Qt.ScreenOrientation.LandscapeOrientation,top.orientation()) if top else 0
        message.setArguments([json.dumps({'region':region,'rotation':rotation,'calibration':self.panel.touch_calibration},separators=(',',':'))])
        self.panel.bus.call(message,QDBus.CallMode.NoBlock)

    def showEvent(self,event):
        super().showEvent(event)
        self.panel.focus_upper(); self.panel.center_pointer(); self.send_region(); self.heartbeat.start()

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if self.isVisible(): self.send_region()

    def hideEvent(self,event):
        self.heartbeat.stop(); self.send_region(False)
        self.panel.start('qdbus6','org.kde.KWin','/Scripting','org.kde.kwin.Scripting.unloadScript','aynthor-touchpad-focus')
        super().hideEvent(event)

    def paintEvent(self,event):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(theme_color('#303144')); p.setPen(QPen(theme_color('#79718d'),1))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(1,1,-1,-1),18,18)


class Panel(QWidget):
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
        self.prefs = preferences()
        set_language(self.prefs['language'])
        self.qt_translator = QTranslator(self); self.translate_dialogs()
        self.state = {}
        self.pending = set()
        self.processes = set()
        self.status_busy = False
        self.write_queue = {}; self.write_active = None; self.write_revision = 0
        self.write_timer = QTimer(self); self.write_timer.setSingleShot(True); self.write_timer.timeout.connect(self.flush_writes)
        self.audio_queue = {}; self.audio_active = False; self.audio_revision = 0
        self.cursor_position = None
        self.touch_calibration = [1,0,0,0,1,0]
        self.screen_blanks = {}
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
        self.bus.connect(NAME,PATH,NAME,'Stick',self.on_stick)
        if not self.bus.connect(NAME, PATH, NAME, 'Button', self.on_button):
            raise RuntimeError('Cannot subscribe to hardware button events')
        self.session = QDBusConnection.sessionBus()
        self.configure_panel_focus()
        self.session.registerService(APP)
        self.endpoint = ControlEndpoint(self)
        self.session.registerObject('/Control', self, QDBusConnection.RegisterOption.ExportAdaptors)
        self.theme_css = '''
            QWidget { background:#222331; color:#f2efff; font-size:14px; }
            QWidget#ThorPanel { background:#222331; }
            QLabel#Title { font-size:22px; font-weight:700; }
            QLabel#HeaderTitle { font-size:14px; font-weight:600; }
            QLabel#Fps { font-size:18px; font-weight:700; color:#bca6ff; }
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
        self.theme_timer = QTimer(self); self.theme_timer.timeout.connect(self.apply_theme); self.theme_timer.start(3000)
        self.menu_timer = QTimer(self); self.menu_timer.timeout.connect(self.sync_desktop_actions); self.menu_timer.start(60000)
        QTimer.singleShot(1000,self.sync_desktop_actions)
        self.make_shell()
        self.make_control(); self.make_tasks(); self.make_screen(); self.make_fan(); self.make_lighting(); self.make_touchpad(); self.make_settings()
        resident = self.prefs.get('resident_tabs',self.page_titles)
        self.tabs.setCurrentIndex(next((i for i,title in enumerate(self.page_titles) if title in resident),self.settings_index))
        self.tabs.currentChanged.connect(self.update_tabs)
        self.update_tabs()
        self.notices = []
        for i in range(self.tabs.count()):
            if i == self.touchpad_index: continue
            label = QLabel(''); label.setObjectName('Notice'); label.setWordWrap(True); label.hide()
            self.tabs.widget(i).layout().addWidget(label); self.notices.append(label)
        self.timer = QTimer(self); self.timer.timeout.connect(self.refresh); self.timer.start(2000)
        self.desktop_visible = False
        self.install_placement()
        QTimer.singleShot(1000,self.configure_pointer)
        for screen in QApplication.screens():
            screen.orientationChanged.connect(lambda orientation:self.configure_pointer())
        self.refresh()
        QTimer.singleShot(0,lambda:self.set_cpu_affinity(self.prefs['panel_cpu_affinity'],False))

    def sync_desktop_actions(self):
        helper = Path(__file__).resolve().parent/'desktop_launch.py'
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
        CONFIG.mkdir(parents=True, exist_ok=True)
        script = CONFIG / 'placement.js'
        rules = json.dumps(self.prefs.get('app_screens',{})); default = json.dumps(self.prefs.get('launch_screen',''))
        focus = json.dumps(self.prefs.get('gamepad_focus','auto'))
        script.write_text('const rules = '+rules+'; const defaultScreen = '+default+'; const gamepadFocus = '+focus+';'+'''
registerShortcut('HandheldDash Gamepad Focus','Focus selected gamepad screen','',function() {
    if (gamepadFocus === 'auto') return;
    const output = gamepadFocus === 'top' ? 'DSI-2' : 'DSI-1';
    const target = workspace.stackingOrder.slice().reverse().find(w => w.normalWindow && !w.minimized && w.output && w.output.name === output && String(w.resourceClass).toLowerCase().indexOf('org.aynthor.control') < 0);
    if (target && workspace.activeWindow !== target) workspace.activeWindow = target;
});
function place(w, existing) {
    const blank = /^HandheldDash Blank (DSI-[12])$/.exec(w.caption);
    if (blank) {
        const output = workspace.screens.find(s => s.name === blank[1]);
        if (output) { workspace.sendClientToScreen(w,output); w.keepAbove=true; w.fullScreen=true; }
        return;
    }
    const app = String(w.resourceClass).toLowerCase();
    if (app.indexOf('org.aynthor.control') < 0) {
        if (existing || !w.normalWindow || w.skipTaskbar) return;
        const name = rules[app] || defaultScreen;
        const target = workspace.screens.find(s => s.name === name);
        if (target) workspace.sendClientToScreen(w,target);
        return;
    }
    const screen = workspace.screens.find(s => s.name === 'DSI-1');
    if (!screen) return;
    workspace.sendClientToScreen(w, screen);
    w.keepAbove = true;
    w.fullScreen = true;
    const g = screen.geometry, f = w.frameGeometry;
    w.frameGeometry = {x:g.x+(g.width-f.width)/2, y:g.y+(g.height-f.height)/2, width:f.width,height:f.height};
}
workspace.windowAdded.connect(w => place(w,false));
workspace.windowList().forEach(w => place(w,true));
function reportCursor() {
    callDBus('org.aynthor.Control','/Control','org.aynthor.Control','CursorPosition',JSON.stringify([workspace.cursorPos.x,workspace.cursorPos.y]));
}
workspace.cursorPosChanged.connect(reportCursor);
reportCursor();
''')
        self.start('qdbus6','org.kde.KWin','/Scripting','org.kde.kwin.Scripting.unloadScript','aynthor-placement')
        QTimer.singleShot(300, lambda: self.start('qdbus6','org.kde.KWin','/Scripting','org.kde.kwin.Scripting.loadScript',str(script),'aynthor-placement'))
        QTimer.singleShot(600, lambda: self.start('qdbus6','org.kde.KWin','/Scripting','org.kde.kwin.Scripting.start'))

    def notify(self,text):
        for label in self.notices:
            label.setText(text); label.setVisible(bool(text))

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
        name = 'aynthor-touchpad-focus'
        script = CONFIG/(name+'.js')
        script.write_text("""
const target = workspace.stackingOrder.slice().reverse().find(w => w.normalWindow && !w.minimized && w.output && w.output.name === 'DSI-2' && String(w.resourceClass).toLowerCase().indexOf('org.aynthor.control') < 0);
if (target) workspace.activeWindow = target;
registerShortcut('HandheldDash Exit Touchpad','Exit HandheldDash touchpad mode','Esc',function() {
    callDBus('org.aynthor.Control','/Control','org.aynthor.Control','ExitTouchpad');
});
""")
        self.start('qdbus6','org.kde.KWin','/Scripting','org.kde.kwin.Scripting.unloadScript',name)
        QTimer.singleShot(150,lambda:self.touchpad.isVisible() and self.start('qdbus6','org.kde.KWin','/Scripting','org.kde.kwin.Scripting.loadScript',str(script),name))
        QTimer.singleShot(300,lambda:self.touchpad.isVisible() and self.start('qdbus6','org.kde.KWin','/Scripting','org.kde.kwin.Scripting.start'))

    def configure_pointer(self):
        manager = QDBusInterface('org.kde.KWin','/org/kde/KWin/InputDevice','org.kde.KWin.InputDeviceManager',self.session)
        manager.setTimeout(1000)
        reply = manager.call('ListPointers')
        if reply.type() == QDBusMessage.MessageType.ErrorMessage: return
        names = list(reply.arguments()[0])
        touches = manager.call('ListTouch')
        if touches.type() != QDBusMessage.MessageType.ErrorMessage: names += list(touches.arguments()[0])
        devices = {}
        for name in dict.fromkeys(names):
            device = QDBusInterface('org.kde.KWin','/org/kde/KWin/InputDevice/'+name,'org.freedesktop.DBus.Properties',self.session)
            device.setTimeout(1000)
            result = device.call('Get','org.kde.KWin.InputDevice','name')
            if result.type() != QDBusMessage.MessageType.ErrorMessage: devices[result.arguments()[0]] = device
        source = devices.get('bottom_touchscreen')
        matrix = None
        if source:
            result = source.call('Get','org.kde.KWin.InputDevice','calibrationMatrix')
            if result.type() != QDBusMessage.MessageType.ErrorMessage:
                matrix = result.arguments()[0]
                try:
                    values = [float(v) for v in matrix.split(',')]
                    if len(values) == 16 and all(math.isfinite(v) and abs(v)<=4 for v in values):
                        self.touch_calibration = [values[i] for i in (0,1,2,4,5,6)]
                    else: matrix = None
                except (ValueError,AttributeError): matrix = None
        for name,device in devices.items():
            if name == 'HandheldDash Pointer Placement':
                device.call('Set','org.kde.KWin.InputDevice','pointerAccelerationProfileFlat',QDBusVariant(True))
                device.call('Set','org.kde.KWin.InputDevice','pointerAcceleration',QDBusVariant(0.0))
            elif name == 'HandheldDash Touchscreen Relay':
                device.call('Set','org.kde.KWin.InputDevice','outputName',QDBusVariant('DSI-1'))
                if matrix is not None: device.call('Set','org.kde.KWin.InputDevice','calibrationMatrix',QDBusVariant(matrix))
            elif name == 'HandheldDash Virtual Touchpad' and not self.prefs.get('touchpad_raw_initialized'):
                result = device.call('Set','org.kde.KWin.InputDevice','tapToClick',QDBusVariant(True))
                device.call('Set','org.kde.KWin.InputDevice','tapAndDrag',QDBusVariant(False))
                device.call('Set','org.kde.KWin.InputDevice','tapDragLock',QDBusVariant(False))
                if result.type() != QDBusMessage.MessageType.ErrorMessage: self.set_pref('touchpad_raw_initialized',True)

    def center_pointer(self):
        screen = next((s for s in QApplication.screens() if s.name() == 'DSI-2'),None)
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
        self.input_mode = QuickTile('Input mode',[('gamepad','Gamepad mode','gamepad'),('mouse','Mouse mode','mouse')],lambda v:self.set('joystick',[v]))
        self.gamepad_focus = QuickTile('Gamepad focus',[('auto','Automatic','gamepad'),('top','Lock top screen','monitor'),('bottom','Lock bottom screen','monitor')],self.set_gamepad_focus)
        self.gamepad_focus.show_value(self.prefs.get('gamepad_focus','auto'))
        self.gamepad_focus.setToolTip(tr('Controls desktop focus; apps reading gamepad devices directly are not isolated.'))
        self.vibration = QuickTile('Vibration',[(False,'Rumble off','vibrate-off'),(True,'Rumble on','vibrate')],lambda v:self.set('vibration',['on' if v else 'off']))
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
        box.addWidget(self.button('Cancel',dialog.reject)); dialog.setFixedSize(columns*card_width+(columns-1)*8+24,min(self.height()-24,rows*card_height+80)); dialog.move(self.mapToGlobal(self.rect().center())-dialog.rect().center())
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

    def make_tasks(self):
        self.tasks_index = self.tabs.count()
        layout = self.page('Tasks')
        self.task_page = 0; self.task_records = []; self.selected_task = None
        self.task_buttons = []
        grid = QGridLayout(); layout.addLayout(grid)
        for i in range(6):
            button = TaskButton('—'); button.clicked.connect(lambda checked=False,index=i:self.select_task(index))
            button.held.connect(lambda index=i:self.task_menu(index))
            button.setMinimumHeight(62); button.setIconSize(QSize(ICON_SIZE,ICON_SIZE)); grid.addWidget(button,i//2,i%2); self.task_buttons.append(button)
        row = QHBoxLayout()
        row.addWidget(self.button('Previous',lambda:self.change_task_page(-1)))
        self.task_count = QLabel('0 / 0'); self.task_count.setAlignment(Qt.AlignmentFlag.AlignCenter); row.addWidget(self.task_count,1)
        row.addWidget(self.button('Next',lambda:self.change_task_page(1))); layout.addLayout(row)
        row = QHBoxLayout(); row.addWidget(self.button('Refresh',self.refresh_tasks));  layout.addLayout(row)
        layout.addStretch()
        self.tabs.currentChanged.connect(lambda i:self.refresh_tasks() if i==self.tasks_index else None)

    def make_screen(self):
        self.screen_sliders = {}
        self.adjustment_dialogs={}; self.brightness_buttons={}
        brightness_dialog,brightness_layout=self.adjustment_dialog('brightness','Brightness')
        volume_dialog,volume_layout=self.adjustment_dialog('volume','Volume')
        layout=brightness_layout
        row=QHBoxLayout(); self.screen_display_buttons={}
        for name,title in [('DSI-2','Top screen visible'),('DSI-1','Bottom screen visible')]:
            button=StateButton(title,[(True,title,'monitor'),(False,title.replace('visible','blanked'),'monitor-off')],lambda value,n=name:self.set_screen_display(n,value))
            button.show_value(True); self.screen_display_buttons[name]=button; row.addWidget(button,1)
        layout.addLayout(row)
        brightness_row=QHBoxLayout()
        for key,title in [('both','Both'),('top','Top'),('bottom','Bottom')]:
            row=QHBoxLayout(); icon=QLabel(); icon.setPixmap(control_icon('sun').pixmap(ICON_SIZE,ICON_SIZE)); row.addWidget(icon)
            label=QLabel(title); label.setFixedWidth(46); row.addWidget(label)
            slider=TouchSlider(Qt.Orientation.Horizontal); slider.setRange(1,100); row.addWidget(slider,1)
            value=QLabel('—%'); value.setFixedWidth(46); row.addWidget(value)
            button=self.button(title+' · —%',lambda checked=False:self.open_adjustment('brightness')); button.setIcon(control_icon('sun'))
            brightness_row.addWidget(button,1); self.brightness_buttons[key]=button
            slider.valueChanged.connect(lambda n,l=value,b=button,t=title:(l.setText(f'{n}%'),b.setText(t+f' · {n}%')))
            slider.edited.connect(lambda n,k=key:self.screen_brightness(k,n))
            brightness_layout.insertLayout(brightness_layout.count()-1,row); self.screen_sliders[key]=slider
        card=QWidget(); card.setObjectName('Gauge'); row=QHBoxLayout(card)
        self.audio_muted=False
        self.volume_icon=self.button('',self.toggle_audio_mute); self.volume_icon.setIconSize(QSize(ICON_SIZE,ICON_SIZE)); self.volume_icon.setFixedWidth(44)
        self.volume_icon.setStyleSheet('border:0; background:transparent; padding:0; min-height:44px;')
        self.volume_icon.setAccessibleName(tr('Volume')); row.addWidget(self.volume_icon)
        self.volume_button=self.button('Volume · —%',lambda:self.open_adjustment('volume')); self.volume_button.hide()
        self.volume=TouchSlider(Qt.Orientation.Horizontal); self.volume.setRange(0,100); row.addWidget(self.volume,1)
        self.volume_label=QLabel('—%'); row.addWidget(self.volume_label)
        self.volume.edited.connect(lambda n:self.set_audio('set-volume',f'{n}%'))
        self.volume.valueChanged.connect(lambda n:self.update_volume_icon()); volume_layout.insertWidget(1,card)
        row=QHBoxLayout()
        self.launch_screen=StateButton('New application screen',[('','Desktop default','panels-top-left'),('DSI-2','New apps: top','monitor'),('DSI-1','New apps: bottom','monitor')],self.set_launch_screen)
        self.launch_screen.show_value(self.prefs.get('launch_screen','')); row.addWidget(self.launch_screen,1); layout.addLayout(row)
        done=layout.takeAt(1).widget(); layout.addWidget(done)

    def adjustment_dialog(self,key,title):
        dialog=EmbeddedPopup(self); dialog.setWindowTitle(tr(title)); dialog.setMinimumWidth(340)
        box=QVBoxLayout(dialog); heading=QLabel(title); heading.setObjectName('Title'); box.addWidget(heading)
        box.addWidget(self.button('Done',dialog.accept)); self.adjustment_dialogs[key]=dialog
        return dialog,box

    def open_adjustment(self,key):
        dialog=self.adjustment_dialogs.get(key)
        if dialog:
            dialog.setFixedSize(min(420,self.width()-24),min(self.height()-24,dialog.sizeHint().height()))
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
        QTimer.singleShot(1000,self.focus_gamepad)

    def focus_gamepad(self):
        if self.prefs.get('gamepad_focus','auto')!='auto':
            self.session_call('org.kde.kglobalaccel','/component/kwin','org.kde.kglobalaccel.Component','invokeShortcut',['HandheldDash Gamepad Focus'])

    def set_screen_display(self,name,visible):
        if visible:
            if name in self.screen_blanks: self.screen_blanks[name].hide()
            return
        screen=next((s for s in QApplication.screens() if s.name()==name),None)
        if not screen:
            self.screen_display_buttons[name].show_value(True); self.notify('Capture screen is unavailable'); return
        if name not in self.screen_blanks:
            blank=QWidget(None,Qt.WindowType.Tool|Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint|Qt.WindowType.WindowDoesNotAcceptFocus)
            blank.setWindowTitle('HandheldDash Blank '+name)
            blank.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
            blank.setFocusPolicy(Qt.FocusPolicy.NoFocus); blank.setStyleSheet('background:black;')
            self.screen_blanks[name]=blank
        blank=self.screen_blanks[name]; blank.winId(); blank.windowHandle().setScreen(screen)
        blank.setGeometry(screen.geometry()); blank.showFullScreen()
        if name=='DSI-1': self.hide()

    def screen_brightness(self,key,value):
        self.set('brightness',[key,str(value)])
        if key == 'both':
            for target in ['top','bottom']: self.screen_sliders[target].setValue(value)

    def refresh_audio(self):
        if getattr(self,'audio_busy',False) or self.audio_active or self.audio_queue: return
        revision = self.audio_revision
        self.audio_busy=True
        process=QProcess(self)
        def done():
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
        def done(code=1,*args):
            self.audio_active = False
            if code: self.notify('Error: '+bytes(process.readAllStandardError()).decode())
            process.deleteLater(); self.flush_audio()
        process.finished.connect(done)
        process.errorOccurred.connect(lambda error:done() if error == QProcess.ProcessError.FailedToStart else None)
        process.start('wpctl',[operation,'@DEFAULT_AUDIO_SINK@',value])

    def combo(self, form, label, items, operation, key):
        options=[(value,value,'zap' if value=='performance' else 'leaf' if value=='powersave' else 'sliders-horizontal') for value in items]
        button=StateButton(label,options,lambda value:self.set(operation,[value]))
        form.addRow(QLabel(label),button); self.setting_widgets[key]=button
        return button

    @staticmethod
    def fan_link_choices():
        return [(True,'Default','fan'),(False,'Manual','fan')]

    def set_fan_follow(self,value):
        self.fan_edit_timer.stop(); self.write_queue.pop('fan-curve',None); self.fan_dirty=False
        self.fan_graph.dragging=False
        if value:
            if self.fan_graph.curve: self.load_fan_curve(self.fan_graph.curve,False)
        else:
            curve=self.state.get('fan_control',{}).get('curves',{}).get('custom')
            if curve: self.load_fan_curve(curve,True)
        self.set('fan-follow-performance',['on' if value else 'off'])

    def make_fan(self):
        layout=self.page('Fan'); self.fan_dirty=False; self.fan_loading=False
        self.fan_performance=QLabel('—'); layout.addWidget(self.fan_performance)
        row=QHBoxLayout()
        self.fan_profile=QLabel('—')
        self.fan_sensor=StateButton('Fan sensor',[('max','Hottest sensor','thermometer'),('average','Average sensors','activity')],lambda v:self.set('fan-sensor-mode',[v]))
        self.fan_follow=StateButton('Fan linkage',self.fan_link_choices(),self.set_fan_follow)
        row.addWidget(self.fan_follow,1)
        row.addWidget(self.fan_profile,1); row.addWidget(self.fan_sensor,1); layout.addLayout(row)
        self.fan_graph=FanCurve(); self.fan_graph.pointChanged.connect(self.edit_fan_point); layout.addWidget(self.fan_graph,1)
        self.fan_reading=QLabel('—'); layout.addWidget(self.fan_reading)
        self.fan_edit_timer=QTimer(self); self.fan_edit_timer.setSingleShot(True); self.fan_edit_timer.setInterval(120); self.fan_edit_timer.timeout.connect(self.apply_fan_curve)
        self.fan_dialog=QDialog(self); self.fan_dialog.setWindowTitle(tr('Advanced values')); dialog_layout=QVBoxLayout(self.fan_dialog)
        advanced=self.button('Advanced values',self.fan_dialog.show); layout.addWidget(advanced)
        scroll=QScrollArea(); scroll.setWidgetResizable(True); scroll.setMinimumHeight(250)
        editor=QWidget(); grid=QGridLayout(editor); grid.setContentsMargins(8,4,8,4)
        self.fan_points=[]
        for i in range(7):
            temp=QSpinBox(); temp.setRange(20,95); temp.setSuffix(' °C'); temp.setFixedWidth(90)
            speed=TouchSlider(Qt.Orientation.Horizontal); speed.setRange(0,100)
            value=QLabel('—%'); value.setFixedWidth(45)
            speed.valueChanged.connect(lambda n,l=value:l.setText(f'{n}%'))
            speed.valueChanged.connect(self.edit_fan_curve); temp.valueChanged.connect(self.edit_fan_curve)
            grid.addWidget(temp,i,0); grid.addWidget(speed,i,1); grid.addWidget(value,i,2)
            self.fan_points.append((temp,speed))
        scroll.setWidget(editor); dialog_layout.addWidget(scroll); dialog_layout.addWidget(self.button('Close',self.fan_dialog.close)); self.fan_dialog.resize(510,370)

    def load_fan_curve(self,curve,editable=False):
        self.fan_loading=True
        self.fan_graph.editable=editable
        if not editable: self.fan_graph.selected=None; self.fan_graph.dragging=False
        self.fan_graph.curve=curve; self.fan_graph.update()
        for i,(temp,speed) in enumerate(self.fan_points):
            temp.setRange(20,95); temp.setValue(round(curve['temperatures'][i]/1000)); speed.setValue(round(curve['pwm'][i]/2.55))
            temp.setEnabled(editable); speed.setEnabled(editable and i<6)
        self.fan_loading=False

    def edit_fan_curve(self,*args):
        if self.fan_loading: return
        self.fan_dirty=True
        self.fan_loading=True
        for i,(temp,speed) in enumerate(self.fan_points):
            low=self.fan_points[i-1][0].value()+1 if i else 20
            high=self.fan_points[i+1][0].value()-1 if i<6 else 95
            temp.setRange(low,high)
            speed.setValue(100 if i==6 else max(self.fan_points[i-1][1].value() if i else 0,min(self.fan_points[i+1][1].value(),speed.value())))
        self.fan_loading=False
        self.fan_graph.curve={'temperatures':[temp.value()*1000 for temp,speed in self.fan_points],'pwm':[round(speed.value()*2.55) for temp,speed in self.fan_points]}
        self.fan_graph.update()
        if not self.fan_edit_timer.isActive(): self.fan_edit_timer.start()

    def edit_fan_point(self,index,temp,percent):
        self.fan_loading=True
        temperature,speed=self.fan_points[index]
        temperature.setValue(temp); speed.setValue(percent)
        self.fan_loading=False; self.edit_fan_curve()

    def apply_fan_curve(self):
        curve=self.fan_graph.curve
        if not curve: return
        temps=curve['temperatures']; speeds=curve['pwm']
        if any(a>=b for a,b in zip(temps,temps[1:])) or any(a>b for a,b in zip(speeds,speeds[1:])) or speeds[-1]!=255:
            self.notify('Temperatures must rise, speeds must not fall, final speed must be 100%'); return
        self.set('fan-curve',list(map(str,temps+speeds)))

    def update_fan(self):
        performance=self.state.get('performance','standard')
        self.fan_performance.setText(tr({'quiet':'Quiet','standard':'Balanced','performance':'Performance','custom':'Custom'}.get(performance,performance)))
        self.fan_follow.show_value(self.state.get('fan_follow_performance',True))
        control=self.state.get('fan_control',{})
        self.fan_graph.temperature=control.get('temperature',0)/1000
        self.fan_graph.update()
        if self.fan_dirty or self.write_queue or self.fan_graph.dragging: return
        profile=self.state.get('fan_profile','moderate')
        if profile=='auto': profile='moderate'
        self.fan_profile.setText(tr({'quiet':'Quiet','moderate':'Balanced','aggressive':'Active cooling','custom':'Custom'}.get(profile,profile))); self.fan_sensor.show_value(self.state.get('fan_sensor_mode','max'))
        curve=control.get('curves',{}).get(profile)
        if curve: self.load_fan_curve(curve,profile=='custom')
        self.fan_reading.setText(f"{self.fan_graph.temperature:.1f} °C · {self.state.get('fan_rpm') or 0:.0f} RPM · PWM {self.state.get('fan_percent') or 0:.0f}%")

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
        form = group('Android')
        warning = QLabel('Extremely experimental: this may not work at all and may even prevent the Android partition from booting.'); warning.setWordWrap(True); warning.setStyleSheet('color:#ffb176; font-weight:600;'); form.addRow(warning)
        self.android_parts = []
        self.android_combo = Choice(); self.android_combo.currentIndexChanged.connect(self.describe_android); form.addRow(QLabel('Partition'),self.android_combo)
        self.android_label = QLabel('Query Android partitions'); self.android_label.setWordWrap(True); form.addRow(self.android_label)
        row = QHBoxLayout(); row.addWidget(self.button('Query',self.refresh_android)); self.android_mount=self.button('Mount read-only',lambda:self.android_action('mount-android')); row.addWidget(self.android_mount); row.addWidget(self.button('Unmount',lambda:self.android_action('unmount-android'))); form.addRow(row)
        form.addRow(self.button('Open Android folder',self.open_android))
        self.android_timer=QTimer(self); self.android_timer.setInterval(2000); self.android_timer.timeout.connect(lambda:self.refresh_android() if self.isVisible() else None); self.android_timer.start()
        form = group('Language')
        language = Choice()
        for text,value in [('System language','system'),('English','en'),('Simplified Chinese','zh_CN'),('Traditional Chinese','zh_TW')]: language.addItem(text,value)
        language.setCurrentIndex(language.findData(self.prefs['language']))
        language.activated.connect(lambda i:self.change_language(language.currentData()))
        form.addRow(QLabel('Language'),language)
        form = group('About')
        form.addRow(QLabel('HandheldDash'))
        form.addRow(QLabel('Version'),QLabel(VERSION))
        source=QLabel('<a style="color:#bca6ff" href="https://github.com/lurenjiamax/HandheldDash">github.com/lurenjiamax/HandheldDash</a>')
        source.setOpenExternalLinks(True); source.setWordWrap(True); form.addRow(QLabel('Source code'),source)
        for text in ['Currently supported and tested only on AYN Thor with the Thorch BSP; other handhelds are planned.','Original code: LGPL-3.0-or-later. Third-party components retain their licenses; Lucide icons use ISC and PyQt6 uses GPL/commercial licensing.','© 2026 lurenjiamax. Provided as-is, without warranty.']:
            label=QLabel(text); label.setWordWrap(True); form.addRow(label)
        self.settings_navigation=QWidget(); row = QHBoxLayout(self.settings_navigation); row.setContentsMargins(0,0,0,0)
        row.addWidget(self.button('Previous group',lambda:self.change_group(-1)))
        self.group_title = QLabel(); self.group_title.setAlignment(Qt.AlignmentFlag.AlignCenter); row.addWidget(self.group_title,1)
        row.addWidget(self.button('Next group',lambda:self.change_group(1))); layout.addWidget(self.settings_navigation); self.change_group(0)

    def plasma_target_script(self):
        screen=next((screen for screen in QApplication.screens() if screen.name() == 'DSI-1'),None)
        if screen is None: return None
        rect=screen.geometry(); target={'x':rect.x(),'y':rect.y(),'width':rect.width(),'height':rect.height()}
        return ('var target='+json.dumps(target)+'; var ids=[]; '
                'desktops().concat(panels()).forEach(function(item){if(item.screen>=0 && ids.indexOf(item.screen)<0) ids.push(item.screen);}); '
                'var matches=ids.filter(function(id){var r=screenGeometry(id); return r.x===target.x && r.y===target.y && r.width===target.width && r.height===target.height;}); '
                'if(matches.length!==1) throw new Error("Cannot uniquely resolve DSI-1 in Plasma"); var targetScreen=matches[0]; ')

    def plasma_script(self,script,callback=None,failed=None):
        interface=QDBusInterface('org.kde.plasmashell','/PlasmaShell','org.kde.PlasmaShell',self.session)
        watcher=QDBusPendingCallWatcher(interface.asyncCall('evaluateScript',script),self); self.pending.add(watcher)
        def done(w):
            reply=QDBusPendingReply(w).reply(); self.pending.discard(w)
            if reply.type() == QDBusMessage.MessageType.ErrorMessage:
                self.notify('Error: '+reply.errorMessage())
                if failed: failed()
            elif callback and reply.arguments(): callback(str(reply.arguments()[0]).strip())
            w.deleteLater()
        watcher.finished.connect(done)

    def refresh_plasma_settings(self):
        from PyQt6.QtCore import QSettings
        settings=QSettings(str(CONFIG.parent/'plasmamobilerc'),QSettings.Format.IniFormat)
        self.plasma_docked.show_value(settings.value('General/convergenceModeEnabled',False,type=bool))
        target=self.plasma_target_script()
        if target is None:
            self.plasma_status_bar.setEnabled(False); return
        script=target+'print(JSON.stringify(panels().filter(function(p){return p.type === "org.kde.plasma.mobile.panel" && p.screen === targetScreen;}).map(function(p){return {height:p.height,location:p.location};})));'
        def loaded(raw):
            try: panels=json.loads(raw)
            except ValueError: return
            self.plasma_status_bar.setEnabled(True)
            self.plasma_status_bar.show_value(bool(panels))
            if panels: self.plasma_status_geometry=panels[0]
        self.plasma_script(script,loaded,lambda:self.plasma_status_bar.setEnabled(False))

    def set_plasma_status_bar(self,visible):
        target=self.plasma_target_script()
        if target is None:
            self.plasma_status_bar.setEnabled(False); self.notify('Error: DSI-1 is unavailable'); return
        geometry=getattr(self,'plasma_status_geometry',self.prefs.get('plasma_status_geometry',{'height':30,'location':'top'}))
        self.set_pref('plasma_status_geometry',geometry)
        script=target+'var matching=panels().filter(function(p){return p.type === "org.kde.plasma.mobile.panel" && p.screen === targetScreen;});'
        if visible:
            script+='if (!matching.length) { var p=new Panel("org.kde.plasma.mobile.panel"); p.screen=targetScreen; p.location='+json.dumps(geometry.get('location','top'))+'; p.height='+str(int(geometry.get('height',30)))+'; }'
        else: script+='matching.forEach(function(p){p.remove();});'
        self.plasma_script(script+'print("ok");',lambda raw:self.refresh_plasma_settings(),self.refresh_plasma_settings)

    def set_plasma_docked(self,enabled):
        process=QProcess(self); self.processes.add(process)
        def finished(code,status):
            self.processes.discard(process)
            if code: self.notify('Error: '+bytes(process.readAllStandardError()).decode(errors='replace'))
            self.refresh_plasma_settings(); process.deleteLater()
        process.finished.connect(finished)
        process.start('kwriteconfig6',['--file','plasmamobilerc','--group','General','--key','convergenceModeEnabled','--type','bool','--notify','true' if enabled else 'false'])

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

    def call(self, method, args, callback=None, quiet=False, finished=None):
        if method not in ('Status','SetMonitoring','MonitoringDevices','LightingFrame','Feedback','Pointer'): self.error_text = None
        watcher = QDBusPendingCallWatcher(self.hardware.asyncCall(method,*args),self)
        self.pending.add(watcher)
        def done(w):
            reply = QDBusPendingReply(w).reply()
            self.pending.discard(w)
            if method == 'Status': self.status_busy = False
            busy = reply.type() == QDBusMessage.MessageType.ErrorMessage and reply.errorName() == NAME+'.Busy'
            if busy: pass
            elif reply.type() == QDBusMessage.MessageType.ErrorMessage:
                self.error_text = 'Error: ' + reply.errorMessage()
                self.notify(self.error_text)
            elif callback:
                try: callback(str(reply.arguments()[0]))
                except (ValueError,KeyError,IndexError) as e: self.notify('Invalid response: '+str(e))
            elif not quiet: self.notify('Settings applied')
            if finished: finished(reply.type() != QDBusMessage.MessageType.ErrorMessage,busy)
            w.deleteLater()
        watcher.finished.connect(done)

    def set(self, operation, values):
        key = ('brightness',values[0]) if operation == 'brightness' else ('lighting-color',values[0]) if operation == 'lighting-color' else ('performance' if operation in ('performance','smart','governors') else 'rgb-mode' if operation in ('rgb-mode','rgb-state','lighting-mode') else operation)
        if operation == 'brightness':
            if values[0] == 'both':
                for target in ['top','bottom']: self.write_queue.pop(('brightness',target),None)
            elif ('brightness','both') in self.write_queue:
                _,both = self.write_queue.pop(('brightness','both'))
                other = 'bottom' if values[0] == 'top' else 'top'
                self.write_queue[('brightness',other)] = ('brightness',[other,both[1]])
        self.write_queue[key]=(operation,values); self.write_revision += 1
        self.write_timer.start(60)

    def flush_writes(self):
        if self.write_active is not None or not self.write_queue: return
        key = next(iter(self.write_queue)); operation,values = self.write_queue.pop(key)
        self.write_active = (key,operation,values)
        def completed(success,busy):
            self.write_active = None
            if success and operation == 'fan-curve' and self.fan_graph.curve and values == list(map(str,self.fan_graph.curve['temperatures']+self.fan_graph.curve['pwm'])):
                self.fan_dirty=False; self.update_fan()
            if busy and key not in self.write_queue: self.write_queue[key]=(operation,values)
            self.write_revision += 1
            if not self.write_queue and not success and not busy:
                self.update_state(json.dumps(self.state))
            self.write_timer.start(100 if busy else 0)
        self.call('Set',[operation,values],self.update_state,finished=completed)

    def update_state(self, raw):
        self.state = json.loads(raw)
        if not self.write_queue:
            self.prefs['mangohud_mode']=self.state.get('mangohud_mode','release')
            self.mango_mode.show_value(self.prefs['mangohud_mode'])
            controlled=self.prefs['mangohud_mode']=='takeover'
            self.fps_mode.setEnabled(controlled and not self.dashboard_editing); self.hud.setEnabled(controlled)
            self.fan_link_control.show_value(self.state.get('fan_follow_performance',True))
            self.ufs_irq.show_value(self.state.get('ufs_irq_mode','system'))
            self.vibration.show_value(bool(self.state.get('vibration')))
            self.performance.show_value(self.state.get('performance','standard'))
            self.input_mode.show_value(self.state.get('joystick','gamepad'))
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
        for key,fallback in [('cpu',3200),('gpu',680)]:
            current=self.state.get(key+'_mhz'); maximum=self.state.get(key+'_max_mhz'); fraction=(current or 0)/(maximum or fallback)
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
        self.set_pref('fps_limit',value); self.update_mangohud()

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

    def set_rgb_mode(self,value):
        self.stop_lighting()
        self.set('lighting-mode',[value])

    def choose_color(self):
        color = QColorDialog.getColor(QColor(self.state.get('rgb_static_hex','#0080ff')),self,'Lighting color')
        if color.isValid(): self.set('rgb-color',list(map(str,[color.red(),color.green(),color.blue()])))

    def start(self,*args):
        process = QProcess(self); self.processes.add(process)
        process.errorOccurred.connect(lambda error: self.notify('Cannot start: '+args[0]+' · '+process.errorString()))
        def finished(code,status):
            if code: self.notify(process.readAllStandardError().data().decode(errors='replace') or f'{args[0]} exit code {code}')
            self.processes.discard(process); process.deleteLater()
        process.finished.connect(finished); process.start('taskset',['--cpu-list',','.join(map(str,sorted(self.system_cpus))),*args])

    def session_call(self,service,path,interface,method,args):
        msg = QDBusMessage.createMethodCall(service,path,interface,method); msg.setArguments(args)
        watcher = QDBusPendingCallWatcher(self.session.asyncCall(msg),self); self.pending.add(watcher)
        def done(w):
            reply = QDBusPendingReply(w).reply()
            if reply.type() == QDBusMessage.MessageType.ErrorMessage: self.notify(reply.errorMessage())
            self.pending.discard(w); w.deleteLater()
        watcher.finished.connect(done)

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
            elif action == 'desktop':
                self.session_call('org.kde.kglobalaccel','/component/kwin','org.kde.kglobalaccel.Component','invokeShortcut',['Show Desktop'])
            elif action == 'overview': self.session_call('org.kde.kglobalaccel','/component/kwin','org.kde.kglobalaccel.Component','invokeShortcut',['Overview'])
            elif action == 'swap': self.start('/usr/bin/thorch-windowctl','swap-active')
        QTimer.singleShot(180,perform)

    @staticmethod
    def screenshot_choices():
        return [('region','Region capture','camera'),('top','Top screen capture','monitor'),('bottom','Bottom screen capture','monitor')]

    def set_screenshot_mode(self,value):
        if value not in ('region','top','bottom'): return
        self.set_pref('screenshot_mode',value)
        self.shot.show_value(value)

    def screenshot(self):
        if getattr(self,'screenshot_process',None): return
        mode = self.prefs.get('screenshot_mode','top')
        if mode not in ('region','top','bottom'): mode='top'
        geometries = {screen.name():screen.geometry() for screen in QApplication.screens()}
        name = 'DSI-2' if mode == 'top' else 'DSI-1'
        if mode != 'region' and name not in geometries:
            self.error_text = tr('Capture screen is unavailable'); self.notify(self.error_text); return
        folder = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.PicturesLocation))/'AYN Thor'
        try: folder.mkdir(parents=True,exist_ok=True)
        except OSError as exc: self.error_text=str(exc); self.notify(self.error_text); return
        target = folder/(time.strftime('%Y%m%d-%H%M%S')+f'-{mode}-{time.time_ns()%1000000000:09d}.png')
        process = QProcess(self); self.screenshot_process = process
        def done(code=1,*args):
            if self.screenshot_process is not process: return
            self.screenshot_process = None
            error = bytes(process.readAllStandardError()).decode(errors='replace')
            success = code == 0 and target.is_file() and target.stat().st_size
            if success and mode != 'region':
                image = QImage(str(target)); bounds = next(iter(geometries.values()))
                for geometry in geometries.values(): bounds = bounds.united(geometry)
                sx = image.width()/bounds.width(); sy = image.height()/bounds.height()
                if image.isNull() or abs(sx-sy)*max(bounds.width(),bounds.height()) > 2:
                    success = False; error = tr('Capture size does not match screen layout')
                else:
                    g = geometries[name]
                    x = round((g.x()-bounds.x())*sx); y = round((g.y()-bounds.y())*sy)
                    right = round((g.x()+g.width()-bounds.x())*sx); bottom = round((g.y()+g.height()-bounds.y())*sy)
                    success = image.copy(x,y,right-x,bottom-y).save(str(target))
            if success: self.start('notify-send',tr('Screenshot'),str(target))
            elif mode == 'region' and code == 0 and not target.exists(): self.showFullScreen()
            else:
                self.error_text = tr('Screenshot failed')+' · '+error
                self.showFullScreen(); self.notify(self.error_text)
            process.deleteLater()
        process.finished.connect(done)
        process.errorOccurred.connect(lambda e:done() if e == QProcess.ProcessError.FailedToStart else None)
        self.hide()
        options = ['--region'] if mode == 'region' else ['--fullscreen','--scaled']
        # A fresh instance avoids an existing Spectacle process swallowing capture options.
        QTimer.singleShot(300,lambda:process.start('spectacle',['--new-instance','--background',*options,'--output',str(target)]))

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
        import configparser
        file=CONFIG.parent/'kwinrulesrc'
        rules=configparser.ConfigParser(interpolation=None,strict=False)
        rules.optionxform=str
        if file.exists(): rules.read(file,encoding='utf-8')
        if not rules.has_section('General'): rules.add_section('General')
        ids=[value for value in rules.get('General','rules',fallback='').split(',') if value]
        rule='handhelddash-panel'
        if rule not in ids: ids.append(rule)
        rules['General']['rules']=','.join(ids)
        rules['General']['count']=str(len(ids))
        rules[rule]={'Description':'HandheldDash panel preserves game focus',
                     'wmclass':'org.aynthor.Control','wmclassmatch':'1',
                     'title':'HandheldDash','titlematch':'1',
                     'acceptfocus':'false','acceptfocusrule':'2'}
        file.parent.mkdir(parents=True,exist_ok=True)
        stage=file.with_suffix('.handhelddash-new')
        with stage.open('w',encoding='utf-8') as stream: rules.write(stream,space_around_delimiters=False)
        stage.replace(file)
        QDBusInterface('org.kde.KWin','/KWin','org.kde.KWin',self.session).call('reconfigure')

    @pyqtSlot()
    def Toggle(self):
        if any(blank.isVisible() for blank in self.screen_blanks.values()):
            for name,blank in self.screen_blanks.items():
                blank.hide(); self.screen_display_buttons[name].show_value(True)
            if self.isVisible(): return
        if self.isVisible(): self.hide()
        else:
            if self.tabs.currentIndex()==self.tasks_index: self.refresh_tasks()
            self.setWindowTitle('HandheldDash')
            self.setWindowFlag(Qt.WindowType.WindowDoesNotAcceptFocus,True)
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating,True)
            self.place(); self.showFullScreen(); self.raise_(); self.refresh()

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
            screen=next((screen for screen in QApplication.screens() if screen.name() == 'DSI-1'),None)
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
        screen = next((s for s in QApplication.screens() if s.name() == 'DSI-1'),QApplication.primaryScreen())
        self.winId(); self.windowHandle().setScreen(screen)
        self.resize(min(604,screen.availableGeometry().width()-12),min(520,screen.availableGeometry().height()-12))
        self.move(screen.availableGeometry().center()-self.rect().center())

    def closeEvent(self,event):
        event.ignore(); self.hide()

    def refresh_android(self):
        def update(raw):
            selected=self.android_combo.currentData(); self.android_parts=sorted(json.loads(raw),key=lambda p:p['label']!='userdata'); self.android_combo.blockSignals(True); self.android_combo.clear()
            for p in self.android_parts: self.android_combo.addItem(p['label'],p['label'])
            index=max(0,self.android_combo.findData(selected)); self.android_combo.setCurrentIndex(index); self.android_combo.blockSignals(False); self.describe_android(index)
        self.call('AndroidPartitions',[],update)

    def describe_android(self,index):
        if not self.android_parts: self.android_label.setText('No Android partitions found'); return
        if not 0 <= index < len(self.android_parts): return
        p=self.android_parts[index]
        self.android_mount.setText(tr('Mount read/write' if p['label'] == 'userdata' else 'Mount read-only'))
        self.android_mount.setEnabled(p['mountable'] and not p.get('busy') and not p.get('mounted'))
        if p['label'] == 'userdata':
            state = tr('Mounted' if p.get('mounted') else 'Not mounted')
            backend = tr('Unlock backend ready' if p.get('backend_ready') else 'Matching kernel, original keys and unlock backend required')
            self.android_label.setText('/sdcard → /mnt/android-data/media/0\n'+state+' · '+p.get('service_state','')+'\n'+backend+('\n'+p['error'] if p.get('error') else ''))
            return
        self.android_label.setText(f"{index+1} / {len(self.android_parts)} · {p.get('filesystem') or 'super logical partition'}\n"+(p['reason'] or 'Read-only mounting available'))

    def android_action(self,operation):
        label = self.android_combo.currentData()
        if label:
            if label == 'userdata': operation='mount-userdata' if operation == 'mount-android' else 'unmount-userdata'
            self.set(operation,[label])
        else: self.refresh_android()

    def open_android(self):
        if self.android_combo.currentData() == 'userdata':
            part=next((p for p in self.android_parts if p['label'] == 'userdata'),{})
            if not part.get('mounted'): self.notify(tr('Not mounted')); return
            self.call('Set',['userdata-share',['userdata']],lambda _:self.start('xdg-open','/mnt/aynthor-android/userdata'))
        else:
            self.start('xdg-open','/mnt/aynthor-android/'+str(self.android_combo.currentData() or ''))

    def refresh_tasks(self):
        script = CONFIG/'tasks.js'
        script.write_text("""
const windows = workspace.windowList().filter(w => w.normalWindow && !w.skipTaskbar && w.pid > 0 && String(w.resourceClass).toLowerCase().indexOf('org.aynthor.control') < 0);
callDBus('org.aynthor.Control','/Control','org.aynthor.Control','WindowList',JSON.stringify(windows.map(w => ({pid:w.pid,id:String(w.internalId),active:w.active,desktop:String(w.desktopFileName),caption:String(w.caption),app:String(w.resourceClass),screen:String(w.output ? w.output.name : '')}))));
""")
        self.start('qdbus6','org.kde.KWin','/Scripting','org.kde.kwin.Scripting.unloadScript','aynthor-tasks')
        QTimer.singleShot(150,lambda:self.start('qdbus6','org.kde.KWin','/Scripting','org.kde.kwin.Scripting.loadScript',str(script),'aynthor-tasks'))
        QTimer.singleShot(300,lambda:self.start('qdbus6','org.kde.KWin','/Scripting','org.kde.kwin.Scripting.start'))

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

    def change_task_page(self,delta):
        count=max(1,(len(self.task_records)+5)//6); self.task_page=max(0,min(count-1,self.task_page+delta)); self.selected_task=None
        self.task_count.setText(f'{self.task_page+1} / {count}')
        for i,button in enumerate(self.task_buttons):
            index=self.task_page*6+i; button.setChecked(False); button.setEnabled(index<len(self.task_records))
            record=self.task_records[index] if index<len(self.task_records) else None
            text=(record['caption'][:24]+' · '+tr('Top screen' if record.get('screen')=='DSI-2' else 'Bottom screen' if record.get('screen')=='DSI-1' else 'Other screen')) if record else '—'
            button.setIcon(self.app_icon(record) if record else QIcon())
            button.setToolTip(record['caption'] if record else '')
            button.setText(text); button.setVisible(record is not None)

    def app_icon(self, record):
        import configparser
        desktop = record.get('desktop') or record['app']
        for folder in [Path.home()/'.local/share/applications', Path('/usr/local/share/applications'), Path('/usr/share/applications')]:
            file = folder / (desktop if desktop.endswith('.desktop') else desktop+'.desktop')
            if file.is_file():
                parser = configparser.ConfigParser(interpolation=None, strict=False)
                try:
                    parser.read(file,encoding='utf-8')
                    name = parser.get('Desktop Entry','Icon',fallback='application-x-executable')
                    return QIcon(name) if name.startswith('/') else QIcon.fromTheme(name,control_icon('monitor'))
                except (configparser.Error,UnicodeError,OSError):
                    pass
        return QIcon.fromTheme(desktop,control_icon('monitor'))

    def task_menu(self,index):
        offset = self.task_page*6+index
        if offset >= len(self.task_records): return
        record = dict(self.task_records[offset]); menu = QMenu(self)
        for name,title in [('DSI-2','Move to top screen'),('DSI-1','Move to bottom screen')]:
            action = menu.addAction(control_icon('monitor'),tr(title))
            action.triggered.connect(lambda checked=False,n=name:self.move_task(record,n))
        menu.addSeparator()
        saved = self.prefs.get('app_screens',{}).get(record['app'].lower(),'')
        for name,title in [('DSI-2','Always open on top screen'),('DSI-1','Always open on bottom screen'),('','Use default screen')]:
            action = menu.addAction(tr(title)); action.setCheckable(True); action.setChecked(name==saved)
            action.triggered.connect(lambda checked=False,n=name:self.remember_task_screen(record,n))
        menu.addSeparator()
        action = menu.addAction(control_icon('circle-x'),tr('Force close'))
        pid = int(record.get('pid') or 0)
        try: started = Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()[19]
        except (OSError,IndexError): started = ''
        action.setEnabled(pid > 1 and bool(started))
        action.triggered.connect(lambda:self.force_close_task(pid,started))
        menu.exec(self.task_buttons[index].mapToGlobal(self.task_buttons[index].rect().center()))

    def force_close_task(self,pid,started):
        self.call('Set',['kill-task',[str(pid),started]],lambda _:self.refresh_tasks())

    def remember_task_screen(self,record,name):
        rules = dict(self.prefs.get('app_screens',{})); key = record['app'].lower()
        if name: rules[key] = name
        else: rules.pop(key,None)
        self.set_pref('app_screens',rules); self.install_placement()
        if name: self.move_task(record,name)

    def move_task(self,record,name):
        script = CONFIG/'move-task.js'
        script.write_text('const w=workspace.windowList().find(w=>String(w.internalId)==='+json.dumps(record['id'])+'); const s=workspace.screens.find(s=>s.name==='+json.dumps(name)+'); if(w && s) workspace.sendClientToScreen(w,s);')
        self.start('qdbus6','org.kde.KWin','/Scripting','org.kde.kwin.Scripting.unloadScript','aynthor-move')
        QTimer.singleShot(150,lambda:self.start('qdbus6','org.kde.KWin','/Scripting','org.kde.kwin.Scripting.loadScript',str(script),'aynthor-move'))
        QTimer.singleShot(300,lambda:self.start('qdbus6','org.kde.KWin','/Scripting','org.kde.kwin.Scripting.start'))
        QTimer.singleShot(550,self.refresh_tasks)

    def select_task(self,index):
        record=self.task_records[self.task_page*6+index]
        script=CONFIG/'activate-task.js'
        script.write_text("const w=workspace.windowList().find(w=>String(w.internalId)==="+json.dumps(record['id'])+"); if(w){w.minimized=false; workspace.activeWindow=w;}")
        self.start('qdbus6','org.kde.KWin','/Scripting','org.kde.kwin.Scripting.unloadScript','aynthor-activate')
        QTimer.singleShot(150,lambda:self.start('qdbus6','org.kde.KWin','/Scripting','org.kde.kwin.Scripting.loadScript',str(script),'aynthor-activate'))
        QTimer.singleShot(300,lambda:self.start('qdbus6','org.kde.KWin','/Scripting','org.kde.kwin.Scripting.start'))



def main():
    if '--run' in sys.argv:
        args = sys.argv[sys.argv.index('--run')+1:]
        if not args: raise SystemExit('Usage: aynthor-control --run PROGRAM [ARGS]')
        env = os.environ.copy()
        os.execvpe('mangohud',['mangohud',*args],env)
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_CompressHighFrequencyEvents,False)
    app = QApplication(sys.argv); app.setStyle(ControlStyle(app.style().objectName())); app.setQuitOnLastWindowClosed(False); app.setDesktopFileName('org.aynthor.Control')
    bus = QDBusConnection.sessionBus()
    if bus.interface().isServiceRegistered(APP).value():
        if '--background' in sys.argv: return
        interface = QDBusInterface(APP,'/Control',APP,bus)
        if '--snapshot' in sys.argv: interface.call('Snapshot',sys.argv[sys.argv.index('--snapshot')+1])
        else: interface.call('Customize' if '--customize' in sys.argv else 'Settings' if '--settings' in sys.argv else 'Toggle')
        return
    panel = Panel()
    if '--customize' in sys.argv: panel.Settings(); panel.open_dashboard_editor()
    elif '--settings' in sys.argv: panel.Settings()
    elif '--background' not in sys.argv: panel.Toggle()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
