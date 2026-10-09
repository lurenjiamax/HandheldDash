#!/usr/bin/python
# SPDX-License-Identifier: LGPL-3.0-or-later
# Copyright (c) 2026 lurenjiamax
"""Unprivileged, touch-friendly Thor control panel and settings."""
import csv
from array import array
import math
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time

from PyQt6.QtCore import QObject, QProcess, QTimer, Qt, QSize, QRectF, QPointF, QLocale, QTranslator, QLibraryInfo, QStandardPaths, pyqtClassInfo, pyqtSlot, pyqtSignal
from PyQt6.QtDBus import QDBusAbstractAdaptor, QDBusConnection, QDBusInterface, QDBusPendingCallWatcher, QDBusPendingReply, QDBusMessage
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap, QPolygonF, QImage, QConicalGradient, QBrush
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton, QTabWidget, QProgressBar, QSlider, QStackedWidget, QFormLayout, QLineEdit, QColorDialog, QInputDialog, QMenu, QStyle, QStyleOptionSlider, QStyleOptionButton, QStylePainter, QScrollArea, QSpinBox)

sys.path.append('/usr/lib/aynthor')
from localization import Label as QLabel, Button as QPushButton, set_language, tr

NAME = 'org.aynthor.Hardware1'
PATH = '/org/aynthor/Hardware1'
APP = 'org.aynthor.Control'
CONFIG = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config'))) / 'aynthor'
DATA = Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share'))) / 'aynthor'
PREFS = CONFIG / 'settings.json'
ACTIONS = {'escape': 'Esc', 'desktop': '顯示桌面', 'overview': '工作概覽', 'panel': '中控台', 'screenshot': '截圖', 'swap': '移至另一螢幕', 'none': '停用', 'command': '自訂指令'}


def preferences():
    defaults = {'back': 'escape', 'home': 'desktop', 'back_command': '', 'home_command': '', 'fps_limit': 60, 'hud': True, 'autolock': False, 'language': 'system', 'launch_screen': '', 'app_screens': {}, 'screenshot_mode': 'top'}
    if PREFS.exists():
        try:
            defaults.update(json.loads(PREFS.read_text()))
        except (ValueError, OSError):
            pass
    return defaults


def save(data):
    CONFIG.mkdir(parents=True, exist_ok=True)
    stage = PREFS.with_suffix('.new')
    stage.write_text(json.dumps(data, indent=2))
    stage.replace(PREFS)


def mango_config(prefs):
    CONFIG.mkdir(parents=True, exist_ok=True)
    logs = DATA / 'fps'
    logs.mkdir(parents=True, exist_ok=True)
    file = CONFIG / 'MangoHud.conf'
    file.write_text(f"fps\nframetime\ncpu_stats\ngpu_stats\nfps_limit={prefs['fps_limit']}\nno_display={int(not prefs['hud'])}\noutput_folder={logs}\nautostart_log=1\nlog_interval=500\nlog_duration=3600\ncontrol=aynthor-mango-%p\n")
    return file


class MetricIcon(QWidget):
    """Draw the measured value; fan motion uses tachometer RPM."""
    def __init__(self, kind):
        super().__init__()
        self.kind = kind; self.fraction = 0; self.rpm = 0; self.angle = 0; self.charging = False
        self.setFixedSize(26,26)
        self.last_frame = time.monotonic()
        self.timer = QTimer(self); self.timer.timeout.connect(self.animate); self.timer.start(80)

    def animate(self):
        now = time.monotonic(); elapsed = now-self.last_frame; self.last_frame = now
        if self.isVisible() and self.kind == 'fan' and self.rpm:
            # Display rotation is scaled for legibility; its speed follows real RPM.
            self.angle = (self.angle+self.rpm*0.12*elapsed)%360; self.update()

    def reading(self, fraction, rpm=0, charging=False):
        self.fraction = max(0,min(1,fraction or 0)); self.rpm = rpm or 0; self.charging = charging; self.update()

    def paintEvent(self,event):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        name = {'temp':'thermometer','ram':'memory-stick','gpu':'activity'}.get(self.kind,self.kind)
        if self.kind == 'battery' and self.charging: name='battery-charging'
        if self.kind == 'fan': p.translate(13,13); p.rotate(self.angle); p.translate(-13,-13)
        control_icon(name).paint(p,0,0,26,26)


def control_icon(kind, enabled=False, color='#a68bff'):
    names = {'lock': 'lock' if enabled else 'lock-open', 'speed': 'gauge',
             'smart': 'sparkles', 'memory': 'memory-stick', 'gamepad': 'gamepad-2',
             'rgb': 'palette', 'battery': 'battery-charging'}
    name = names.get(kind, kind)
    local = Path(__file__).resolve().parent.parent / 'packaging/icons' / (name + '.svg')
    return QIcon(str(local if local.exists() else Path('/usr/share/aynthor/icons') / (name + '.svg')))


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

    def move_to(self, point):
        option = QStyleOptionSlider(); self.initStyleOption(option)
        groove = self.style().subControlRect(QStyle.ComplexControl.CC_Slider,option,QStyle.SubControl.SC_SliderGroove,self)
        handle = self.style().subControlRect(QStyle.ComplexControl.CC_Slider,option,QStyle.SubControl.SC_SliderHandle,self)
        value = QStyle.sliderValueFromPosition(self.minimum(),self.maximum(),round(point.x()-groove.x()-handle.width()/2),max(1,groove.width()-handle.width()),option.upsideDown)
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
    def __init__(self, title, options, callback):
        super().__init__(title)
        self.title = title; self.options = options; self.callback = callback
        self.current = options[0][0]; self.held = False; self.menu = None
        self.setIconSize(QSize(22,22)); self.setMinimumHeight(32)
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
        self.setText(option[1] if option else self.title)
        self.setIcon(control_icon(option[2] if option else 'gauge'))
        self.setAccessibleName(tr(self.title)+': '+self.text())
        self.setToolTip(tr(self.title))

    def open_options(self):
        if not self.isDown(): return
        self.held = True; self.setDown(False)
        self.menu = QMenu(self); self.menu.setTitle(tr(self.title))
        for value,title,icon in self.options:
            action = self.menu.addAction(control_icon(icon),tr(title))
            action.setCheckable(True); action.setChecked(value == self.current)
            action.triggered.connect(lambda checked=False,v=value:self.choose(v))
        self.menu.aboutToHide.connect(self.menu.deleteLater)
        self.menu.popup(self.mapToGlobal(self.rect().bottomLeft()))

    def mouseMoveEvent(self,event):
        if not self.rect().contains(event.position().toPoint()): self.hold_timer.stop()
        super().mouseMoveEvent(event)

    def paintEvent(self,event):
        painter = QStylePainter(self); option = QStyleOptionButton(); self.initStyleOption(option)
        painter.drawControl(QStyle.ControlElement.CE_PushButtonBevel,option)
        side = self.iconSize().width(); x = 14
        self.icon().paint(painter,x,(self.height()-side)//2,side,side,mode=QIcon.Mode.Normal if self.isEnabled() else QIcon.Mode.Disabled)
        painter.setPen(self.palette().buttonText().color())
        painter.drawText(self.rect().adjusted(x+side+10,0,-10,0),Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter,self.text())


class ScreenshotButton(StateButton):
    def __init__(self, options, callback, capture):
        super().__init__('截圖',options,callback); self.capture = capture

    def cycle(self):
        if not self.held: self.capture()


class LightingPad(QWidget):
    edited = pyqtSignal(float,float,float)
    colorChosen = pyqtSignal(str)
    detent = pyqtSignal()

    def __init__(self, minimum=0., maximum=1., sensitivity=4.):
        super().__init__()
        self.minimum = max(0.,min(1.,minimum)); self.maximum = max(self.minimum,min(1.,maximum))
        self.sensitivity = max(1.,min(20.,sensitivity)); self.level = 0.; self.color = QColor('#0080ff')
        self.handle = 1; self.dragging = False; self.color_open = False; self.color_dragging = False; self.controls_enabled = True; self.stick_angle = None; self.stick_remainder = 0.
        self.setMinimumSize(190,220); self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(tr('亮度與靈敏度'))
        self.setToolTip(tr('拖動兩個點：橫向調整最低／最高亮度，縱向調整靈敏度。'))

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
            p.setBrush(QColor('#303144')); p.setPen(QPen(QColor('#bca6ff'),2))
            p.drawRoundedRect(QRectF(self.rect()).adjusted(3,3,-3,-3),18,18)
            gradient=QConicalGradient(center,0)
            for i in range(7): gradient.setColorAt(i/6,QColor.fromHsvF((i%6)/6,1,1))
            p.setBrush(Qt.BrushStyle.NoBrush); p.setPen(QPen(QBrush(gradient),18)); p.drawEllipse(center,radius,radius)
            selected=round(max(0.,self.color.hueF())*12)%12
            for i in range(12):
                angle=i*math.pi/6; direction=QPointF(math.cos(angle),-math.sin(angle))
                p.setPen(QPen(QColor('#ffffff') if i==selected else QColor('#79798f'),4 if i==selected else 2))
                p.drawLine(center+direction*(radius-13),center+direction*(radius+11))
            p.setBrush(self.color); p.setPen(Qt.PenStyle.NoPen); p.drawEllipse(center,15,15)
            names=('紅色','橙色','黃色','黃綠色','綠色','薄荷綠','青色','天藍色','藍色','紫色','洋紅色','玫紅色')
            p.setPen(QColor('#f2efff')); p.drawText(QRectF(center.x()-radius+20,center.y()+20,2*radius-40,45),Qt.AlignmentFlag.AlignCenter,tr(names[selected])+'\n'+self.color.name().upper())
            return
        center = QPointF(self.width()/2,42)
        p.setBrush(QColor('#303144')); p.setPen(Qt.PenStyle.NoPen); p.drawEllipse(center,34,34)
        ring = QColor(self.color); ring.setAlphaF(.12+.88*self.level)
        if self.color_open:
            ring = QConicalGradient(center,0)
            for i in range(7): ring.setColorAt(i/6,QColor.fromHsvF((i%6)/6,1,1))
        p.setBrush(Qt.BrushStyle.NoBrush); p.setPen(QPen(QBrush(ring),7)); p.drawEllipse(center,29,29)
        p.setBrush(QColor('#45465e')); p.setPen(QPen(QColor('#79798f'),1)); p.drawEllipse(center,20,20)
        p.setPen(QColor('#f2efff'))
        p.drawText(QRectF(0,79,self.width(),25),Qt.AlignmentFlag.AlignCenter,f'{round(self.minimum*100)}–{round(self.maximum*100)}% · S {round(math.log(self.sensitivity)/math.log(20)*100)}% · {round(self.level*100)}%')
        box = self.plot(); p.setPen(QPen(QColor('#45465e'),1))
        for fraction in (0.,.5,1.):
            x=box.left()+fraction*box.width(); y=box.top()+fraction*box.height()
            p.drawLine(QPointF(x,box.top()),QPointF(x,box.bottom())); p.drawLine(QPointF(box.left(),y),QPointF(box.right(),y))
        p.setPen(QColor('#b8b5ca')); p.drawText(QRectF(0,box.top()-3,24,20),Qt.AlignmentFlag.AlignCenter,tr('高'))
        p.drawText(QRectF(0,box.bottom()-17,24,20),Qt.AlignmentFlag.AlignCenter,tr('低'))
        p.drawText(QRectF(0,box.bottom()+6,self.width(),22),Qt.AlignmentFlag.AlignCenter,tr('亮度')+' 0 → 100%')
        p.setPen(QPen(self.color,3)); p.drawLine(self.point(0),self.point(1))
        for handle in (0,1):
            p.setBrush(QColor('#f2efff') if handle == self.handle else self.color)
            p.setPen(QPen(self.color,2)); p.drawEllipse(self.point(handle),10,10)
            p.setPen(QColor('#222331')); p.drawText(QRectF(self.point(handle).x()-10,self.point(handle).y()-10,20,20),Qt.AlignmentFlag.AlignCenter,'−' if handle == 0 else '+')

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
    def __init__(self):
        super().__init__(); self.curve=None; self.temperature=None
        self.setMinimumHeight(128)

    def paintEvent(self,event):
        if not self.curve: return
        p=QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        box=QRectF(42,14,self.width()-58,self.height()-42)
        def point(temp,pwm): return QPointF(box.left()+(temp-20)/80*box.width(),box.bottom()-pwm/255*box.height())
        p.setPen(QPen(QColor('#45465e'),1))
        for temp in (20,40,60,80,100):
            x=point(temp,0).x(); p.drawLine(QPointF(x,box.top()),QPointF(x,box.bottom()))
            p.setPen(QColor('#b8b5ca')); p.drawText(QRectF(x-20,box.bottom()+4,40,20),Qt.AlignmentFlag.AlignCenter,f'{temp}°'); p.setPen(QPen(QColor('#45465e'),1))
        for percent in (0,50,100):
            y=point(20,percent*2.55).y(); p.drawLine(QPointF(box.left(),y),QPointF(box.right(),y))
            p.setPen(QColor('#b8b5ca')); p.drawText(QRectF(0,y-10,37,20),Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter,f'{percent}%'); p.setPen(QPen(QColor('#45465e'),1))
        points=[point(20,0)]; previous=0
        for temp,pwm in zip(self.curve['temperatures'],self.curve['pwm']):
            points.extend([point(temp/1000,previous),point(temp/1000,pwm)]); previous=pwm
        points.append(point(100,previous))
        p.setPen(QPen(QColor('#bca6ff'),2.5)); p.drawPolyline(QPolygonF(points))
        if self.temperature is not None:
            x=point(max(20,min(100,self.temperature)),0).x()
            p.setPen(QPen(QColor('#7de2ad'),1.5,Qt.PenStyle.DashLine)); p.drawLine(QPointF(x,box.top()),QPointF(x,box.bottom()))


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

    @pyqtSlot()
    def Toggle(self): self.parent().Toggle()

    @pyqtSlot()
    def Settings(self): self.parent().Settings()

    @pyqtSlot(str,result=bool)
    def Snapshot(self,path): return self.parent().Snapshot(path)

    @pyqtSlot(str)
    def WindowList(self,raw): self.parent().WindowList(raw)


class Panel(QWidget):
    def __init__(self):
        super().__init__()
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
        self.error_text = None
        self.setWindowTitle(tr('AYN Thor 中控台'))
        self.setObjectName('ThorPanel')
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setMinimumSize(470, 420)
        self.resize(604, 520)
        self.bus = QDBusConnection.systemBus()
        self.hardware = QDBusInterface(NAME, PATH, NAME, self.bus)
        self.hardware.setTimeout(200000)
        self.bus.connect(NAME,PATH,NAME,'Stick',self.on_stick)
        if not self.bus.connect(NAME, PATH, NAME, 'Button', self.on_button):
            raise RuntimeError('Cannot subscribe to hardware button events')
        self.session = QDBusConnection.sessionBus()
        self.session.registerService(APP)
        self.endpoint = ControlEndpoint(self)
        self.session.registerObject('/Control', self, QDBusConnection.RegisterOption.ExportAdaptors)
        self.setStyleSheet('''
            QWidget { background:#222331; color:#f2efff; font-size:14px; }
            QWidget#ThorPanel { background:#222331; }
            QLabel#Title { font-size:22px; font-weight:700; }
            QLabel#Fps { font-size:36px; font-weight:800; color:#bca6ff; }
            QWidget#Gauge { background:#303144; border-radius:12px; }
            QWidget#Gauge QWidget { background:transparent; }
            QProgressBar { background:#45465e; border:0; border-radius:3px; height:6px; }
            QProgressBar::chunk { background:#a68bff; border-radius:3px; }
            QPushButton { background:#36374a; border:1px solid #45465e; border-radius:13px; padding:10px; min-height:24px; }
            QPushButton:pressed { background:#4c4268; }
            QPushButton:checked { background:#7755d9; border-color:#a58cf8; }
            QPushButton:disabled { color:#79798f; }
            QMenu { background:#303144; border:1px solid #79718d; padding:6px; }
            QMenu::item { padding:12px 20px; } QMenu::item:selected { background:#7755d9; }
            QTabWidget::pane { border:0; } QTabBar::tab { padding:10px 18px; background:#303144; }
            QTabBar::tab:selected { background:#7755d9; }
            QLineEdit { background:#303144; border:1px solid #45465e; border-radius:8px; padding:7px; }
            QSlider::groove:horizontal { height:12px; background:#45465e; border-radius:6px; }
            QSlider::handle:horizontal { width:26px; margin:-7px 0; border-radius:13px; background:#a68bff; }
            QTabWidget::tab-bar { alignment:center; } QLabel#Notice { color:#b8b5ca; font-size:12px; }
        ''')
        root = QVBoxLayout(self)
        header = QHBoxLayout()
        title = QLabel('AYN / THOR'); title.setObjectName('Title')
        header.addWidget(title); header.addStretch()
        self.battery_icon = MetricIcon('battery'); header.addWidget(self.battery_icon)
        self.battery_text = QLabel('—%'); header.addWidget(self.battery_text)
        self.clock = QLabel(); header.addWidget(self.clock)
        close = QPushButton('×'); close.setFixedWidth(44); close.clicked.connect(self.hide); header.addWidget(close)
        root.addLayout(header)
        self.tabs = QTabWidget(); self.tabs.setTabPosition(QTabWidget.TabPosition.South); root.addWidget(self.tabs)
        self.make_control(); self.make_modes(); self.make_tasks(); self.make_screen(); self.make_fan(); self.make_lighting(); self.make_settings()
        self.notices = []
        for i in range(self.tabs.count()):
            label = QLabel('連線到硬體服務…'); label.setObjectName('Notice'); label.setWordWrap(True)
            self.tabs.widget(i).layout().addWidget(label); self.notices.append(label)
        self.timer = QTimer(self); self.timer.timeout.connect(self.refresh); self.timer.start(2000)
        self.desktop_visible = False
        self.install_placement()
        self.refresh()

    def install_placement(self):
        CONFIG.mkdir(parents=True, exist_ok=True)
        script = CONFIG / 'placement.js'
        rules = json.dumps(self.prefs.get('app_screens',{})); default = json.dumps(self.prefs.get('launch_screen',''))
        script.write_text('const rules = '+rules+'; const defaultScreen = '+default+';'+'''
function place(w, existing) {
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
''')
        self.start('qdbus6','org.kde.KWin','/Scripting','org.kde.kwin.Scripting.unloadScript','aynthor-placement')
        QTimer.singleShot(300, lambda: self.start('qdbus6','org.kde.KWin','/Scripting','org.kde.kwin.Scripting.loadScript',str(script),'aynthor-placement'))
        QTimer.singleShot(600, lambda: self.start('qdbus6','org.kde.KWin','/Scripting','org.kde.kwin.Scripting.start'))

    def notify(self,text):
        for label in self.notices: label.setText(text)

    def page(self, title):
        widget = QWidget(); layout = QVBoxLayout(widget)
        self.tabs.addTab(widget, tr(title))
        return layout

    def button(self, text, callback, checkable=False):
        button = QPushButton(text); button.setCheckable(checkable); button.clicked.connect(callback)
        return button

    def make_control(self):
        layout = self.page('中控')
        top = QHBoxLayout()
        self.fps = QLabel('— FPS'); self.fps.setObjectName('Fps'); top.addWidget(self.fps)
        right = QVBoxLayout()
        self.fps_mode = StateButton('FPS',[(0,'不限幀','infinity'),(30,'30 FPS','gauge'),(60,'60 FPS','activity'),(120,'120 FPS','zap')],self.set_fps_limit)
        self.fps_mode.show_value(self.prefs['fps_limit']); right.addWidget(self.fps_mode)
        self.fps_source = QLabel('等待遊戲'); self.fps_source.setObjectName('Notice'); self.fps_source.setWordWrap(True); right.addWidget(self.fps_source)
        top.addLayout(right); layout.addLayout(top)
        grid = QGridLayout(); grid.setVerticalSpacing(6); layout.addLayout(grid)
        self.autolock = StateButton('自動鎖定',[(False,'鎖定停用','lock-open'),(True,'自動鎖定','lock')],self.set_autolock)
        try:
            self.prefs['autolock'] = subprocess.check_output(['kreadconfig6','--file','kscreenlockerrc','--group','Daemon','--key','Autolock','--default','true'],text=True,timeout=5).strip() == 'true'
        except (OSError,subprocess.SubprocessError): pass
        self.autolock.show_value(self.prefs['autolock'])
        self.performance = StateButton('效能', [('quiet','安靜','leaf'),('standard','標準','gauge'),('performance','高效能','zap')], lambda v:self.set('performance',[v]))
        self.smart = StateButton('智慧模式',[(False,'手動調節','sliders-horizontal'),(True,'智慧調節','sparkles')],lambda v:self.set('smart',['on' if v else 'off']))
        self.input_mode = StateButton('輸入模式',[('gamepad','手柄模式','gamepad'),('mouse','鼠標模式','mouse')],lambda v:self.set('joystick',[v]))
        self.joystick = StateButton('手柄布局',[(None,'布局不支援','gamepad')],lambda v:None)
        self.joystick.setEnabled(False)
        bypass = StateButton('旁路供電',[(None,'旁路不支援','battery')],lambda v:None); bypass.setEnabled(False)
        self.vibration = StateButton('震動',[(False,'震動關閉','bell-off'),(True,'震動開啟','vibration')],lambda v:self.set('vibration',['on' if v else 'off']))
        self.rgb = StateButton('氛圍燈',self.lighting_choices(),self.set_rgb_mode)
        for i, button in enumerate([self.autolock,self.performance,self.smart,self.input_mode,self.joystick,bypass,self.vibration,self.rgb]):
            button.setStyleSheet('padding:5px 10px; min-height:22px;'); grid.addWidget(button,i//2,i%2)
        gauges = QGridLayout(); self.gauges = {}; self.metric_icons = {}
        for i,(key,title,icon) in enumerate([('cpu','CPU','cpu'),('gpu','GPU','video-display'),('temp','溫度','temperature-normal'),('fan','風扇','fan'),('ram','RAM','memory'),('battery','電池','battery')]):
            card = QWidget(); card.setObjectName('Gauge'); box = QVBoxLayout(card); box.setContentsMargins(9,7,9,7); box.setSpacing(4)
            row = QHBoxLayout(); image = MetricIcon(key); self.metric_icons[key] = image; row.addWidget(image)
            value = QLabel(title); row.addWidget(value,1); box.addLayout(row)
            bar = QProgressBar(); bar.setRange(0,1000); bar.setTextVisible(False); bar.setFixedHeight(6); box.addWidget(bar)
            gauges.addWidget(card,i//3,i%3); self.gauges[key]=(value,bar)
        layout.addLayout(gauges)
        bottom = QHBoxLayout()
        self.shot = ScreenshotButton(self.screenshot_choices(),self.set_screenshot_mode,self.screenshot)
        self.shot.show_value(self.prefs.get('screenshot_mode','top')); self.shot.setToolTip(tr('點擊截圖，長按切換模式')); bottom.addWidget(self.shot)
        overview = StateButton('工作概覽',[(None,'工作概覽','panels-top-left')],lambda v:self.action('overview')); bottom.addWidget(overview)
        self.hud = StateButton('FPS 浮層',[(False,'浮層關閉','eye-off'),(True,'浮層開啟','activity')],self.set_hud)
        self.hud.show_value(self.prefs['hud']); bottom.addWidget(self.hud); layout.addLayout(bottom)

    def make_modes(self):
        layout = self.page('模式')
        for name, title, description in [('quiet','安靜','省電 CPU／GPU，較晚的風扇升速'),('standard','標準','依負載調節 CPU／GPU，平衡風扇'),('performance','高效能','最大 CPU／GPU 時脈，積極散熱')]:
            layout.addWidget(self.button(title + ' · ' + description, lambda checked=False, mode=name: self.set('performance', [mode])))
        layout.addWidget(self.button('智慧模式', lambda: self.set('smart', ['on'])))
        layout.addWidget(self.button('啟動遊戲…', self.choose_game))
        info = QLabel('FPS 限制與浮層適用於 MangoHud 包裝的 OpenGL／Vulkan 遊戲。\n命令列：aynthor-control --run 遊戲程式 [參數]\n執行中設定會由 MangoHud 自動重新載入。'); info.setWordWrap(True); info.setObjectName('Notice'); layout.addWidget(info)
        layout.addStretch()

    def make_tasks(self):
        layout = self.page('工作')
        self.task_page = 0; self.task_records = []; self.selected_task = None
        self.task_buttons = []
        grid = QGridLayout(); layout.addLayout(grid)
        for i in range(6):
            button = TaskButton('—'); button.clicked.connect(lambda checked=False,index=i:self.select_task(index))
            button.held.connect(lambda index=i:self.task_menu(index))
            button.setMinimumHeight(62); button.setIconSize(QSize(28,28)); grid.addWidget(button,i//2,i%2); self.task_buttons.append(button)
        row = QHBoxLayout()
        row.addWidget(self.button('上一頁',lambda:self.change_task_page(-1)))
        self.task_count = QLabel('0 / 0'); self.task_count.setAlignment(Qt.AlignmentFlag.AlignCenter); row.addWidget(self.task_count,1)
        row.addWidget(self.button('下一頁',lambda:self.change_task_page(1))); layout.addLayout(row)
        row = QHBoxLayout(); row.addWidget(self.button('重新整理',self.refresh_tasks));  layout.addLayout(row)
        layout.addStretch()
        self.tabs.currentChanged.connect(lambda i:self.refresh_tasks() if i==2 else None)

    def make_screen(self):
        layout = self.page('屏幕控制'); self.screen_sliders = {}
        card = QWidget(); card.setObjectName('Gauge'); form = QFormLayout(card)
        for key, title in [('both','雙屏亮度'),('top','主螢幕亮度'),('bottom','副螢幕亮度')]:
            row = QHBoxLayout(); icon = QLabel(); icon.setPixmap(control_icon('sun').pixmap(22,22)); row.addWidget(icon)
            slider = TouchSlider(Qt.Orientation.Horizontal); slider.setRange(1,100); row.addWidget(slider,1)
            value = QLabel('—%'); value.setFixedWidth(48); row.addWidget(value)
            slider.valueChanged.connect(lambda n,l=value:l.setText(f'{n}%'))
            slider.edited.connect(lambda n,k=key:self.screen_brightness(k,n))
            form.addRow(QLabel(title),row); self.screen_sliders[key]=slider
        layout.addWidget(card)
        card = QWidget(); card.setObjectName('Gauge'); form = QFormLayout(card)
        self.volume = TouchSlider(Qt.Orientation.Horizontal); self.volume.setRange(0,100)
        self.volume.edited.connect(lambda n:self.set_audio('set-volume',f'{n}%'))
        row = QHBoxLayout(); row.addWidget(self.volume,1); self.volume_label = QLabel('—%'); row.addWidget(self.volume_label)
        self.volume.valueChanged.connect(lambda n:self.volume_label.setText(f'{n}%'))
        form.addRow(QLabel('音量'),row)
        self.mute = self.button('靜音',lambda:self.set_audio('set-mute','1' if self.mute.isChecked() else '0'),True)
        self.mute.setIcon(control_icon('volume-x')); form.addRow(self.mute); layout.addWidget(card)
        move = self.button('移動目前應用到另一螢幕',lambda:self.action('swap')); move.setIcon(control_icon('arrow-left-right')); layout.addWidget(move)
        form = QFormLayout(); layout.addLayout(form)
        self.launch_screen = Choice()
        for title,name in [('跟隨桌面',''),('上屏','DSI-2'),('下屏','DSI-1')]: self.launch_screen.addItem(title,name)
        self.launch_screen.setCurrentIndex(self.launch_screen.findData(self.prefs.get('launch_screen','')))
        self.launch_screen.activated.connect(lambda i:self.set_launch_screen(self.launch_screen.currentData()))
        form.addRow(QLabel('新應用預設屏幕'),self.launch_screen)
        self.screenshot_mode = StateButton('截圖模式',self.screenshot_choices(),self.set_screenshot_mode)
        self.screenshot_mode.show_value(self.prefs.get('screenshot_mode','top')); form.addRow(QLabel('截圖模式'),self.screenshot_mode)
        label = QLabel('工作頁顯示應用所在屏幕；長按可移動並記住啟動屏幕。'); label.setWordWrap(True); layout.addWidget(label)
        label = QLabel('音量控制共用揚聲器，與上下屏無關。'); label.setWordWrap(True); layout.addWidget(label)
        layout.addStretch()

    def set_launch_screen(self,name):
        self.set_pref('launch_screen',name); self.install_placement()

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
                    if revision == self.audio_revision: self.mute.setChecked('[MUTED]' in output)
                except ValueError: pass
            self.volume.setEnabled(process.exitCode()==0); self.mute.setEnabled(process.exitCode()==0)
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
            if code: self.notify('錯誤：'+bytes(process.readAllStandardError()).decode())
            process.deleteLater(); self.flush_audio()
        process.finished.connect(done)
        process.errorOccurred.connect(lambda error:done() if error == QProcess.ProcessError.FailedToStart else None)
        process.start('wpctl',[operation,'@DEFAULT_AUDIO_SINK@',value])

    def combo(self, form, label, items, operation, key):
        combo = Choice(); combo.addItems(items)
        combo.activated.connect(lambda i: self.set(operation, [combo.currentText()]))
        form.addRow(QLabel(label), combo)
        self.setting_widgets[key] = combo
        return combo

    def make_fan(self):
        layout=self.page('風扇管理'); self.fan_dirty=False; self.fan_loading=False
        row=QHBoxLayout()
        self.fan_profile=StateButton('風扇策略',[('quiet','安靜','leaf'),('moderate','標準','gauge'),('aggressive','強散熱','fan'),('custom','自訂','sliders-horizontal')],self.select_fan_profile)
        self.fan_sensor=StateButton('風扇感測',[('max','最熱感測器','thermometer'),('average','平均感測器','activity')],lambda v:self.set('fan-sensor-mode',[v]))
        row.addWidget(self.fan_profile,1); row.addWidget(self.fan_sensor,1); layout.addLayout(row)
        self.fan_graph=FanCurve(); layout.addWidget(self.fan_graph)
        self.fan_reading=QLabel('—'); layout.addWidget(self.fan_reading)
        scroll=QScrollArea(); scroll.setWidgetResizable(True); scroll.setMinimumHeight(110)
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
        scroll.setWidget(editor); layout.addWidget(scroll,1)
        row=QHBoxLayout(); row.addWidget(self.button('複製為自訂',self.copy_fan_curve))
        self.fan_apply=self.button('套用自訂曲線',self.apply_fan_curve); row.addWidget(self.fan_apply); layout.addLayout(row)

    def load_fan_curve(self,curve,editable=False):
        self.fan_loading=True
        self.fan_graph.curve=curve; self.fan_graph.update()
        for i,(temp,speed) in enumerate(self.fan_points):
            temp.setValue(round(curve['temperatures'][i]/1000)); speed.setValue(round(curve['pwm'][i]/2.55))
            temp.setEnabled(editable); speed.setEnabled(editable and i<6)
        self.fan_apply.setEnabled(editable)
        self.fan_loading=False

    def select_fan_profile(self,value):
        self.fan_dirty=False
        curves=self.state.get('fan_control',{}).get('curves',{})
        if value in curves: self.load_fan_curve(curves[value],value=='custom')
        self.set('fan-profile',[value])

    def copy_fan_curve(self):
        if self.fan_graph.curve:
            self.load_fan_curve(self.fan_graph.curve,True)
            self.fan_points[-1][1].setValue(100)
            self.fan_profile.show_value('custom'); self.edit_fan_curve()

    def edit_fan_curve(self,*args):
        if self.fan_loading: return
        self.fan_dirty=True
        self.fan_graph.curve={'temperatures':[temp.value()*1000 for temp,speed in self.fan_points],'pwm':[round(speed.value()*2.55) for temp,speed in self.fan_points]}
        self.fan_graph.update(); self.fan_reading.setText('未套用的曲線')

    def apply_fan_curve(self):
        curve=self.fan_graph.curve
        if not curve: return
        temps=curve['temperatures']; speeds=curve['pwm']
        if any(a>=b for a,b in zip(temps,temps[1:])) or any(a>b for a,b in zip(speeds,speeds[1:])) or speeds[-1]!=255:
            self.notify('溫度須遞增，轉速不可遞減，最後一點須為 100%'); return
        self.set('fan-curve',list(map(str,temps+speeds)))

    def update_fan(self):
        control=self.state.get('fan_control',{})
        self.fan_graph.temperature=control.get('temperature',0)/1000
        self.fan_graph.update()
        if self.fan_dirty or self.write_queue: return
        profile=self.state.get('fan_profile','moderate')
        if profile=='auto': profile='moderate'
        self.fan_profile.show_value(profile); self.fan_sensor.show_value(self.state.get('fan_sensor_mode','max'))
        curve=control.get('curves',{}).get(profile)
        if curve: self.load_fan_curve(curve,profile=='custom')
        self.fan_reading.setText(f"{self.fan_graph.temperature:.1f} °C · {self.state.get('fan_rpm') or 0:.0f} RPM · PWM {self.state.get('fan_percent') or 0:.0f}%")

    @staticmethod
    def lighting_choices():
        return [('off','燈光關閉','lightbulb-off'),('battery','電量燈光','battery'),('static','固定燈光','palette'),('audio','音頻律動','volume-2')]

    def make_lighting(self):
        layout = self.page('燈光管理')
        self.lighting_mode = StateButton('氛圍燈',self.lighting_choices(),self.set_rgb_mode); layout.addWidget(self.lighting_mode)
        form = QFormLayout(); layout.addLayout(form)
        self.lighting_brightness = TouchSlider(Qt.Orientation.Horizontal); self.lighting_brightness.setRange(0,255)
        self.lighting_brightness.edited.connect(lambda n:self.set('rgb-brightness',[str(n)]))
        form.addRow(QLabel('氛圍燈亮度'),self.lighting_brightness)
        self.lighting_basic_form = form
        self.lighting_pads = []
        rings = QHBoxLayout(); layout.addLayout(rings)
        for side,title,default in [('left','左搖杆燈','#0080ff'),('right','右搖杆燈','#c050ff')]:
            column = QVBoxLayout(); rings.addLayout(column,1)
            label = QLabel(title); label.setAlignment(Qt.AlignmentFlag.AlignCenter); column.addWidget(label)
            self.prefs.setdefault('lighting_'+side,default)
            settings = self.prefs.get('lighting_range_'+side,{})
            pad = LightingPad(float(settings.get('minimum',0)),float(settings.get('maximum',self.state.get('rgb_brightness',255)/255)),float(settings.get('sensitivity',self.prefs.get('lighting_gain',4))))
            pad.edited.connect(lambda low,high,gain,k=side:self.set_pref('lighting_range_'+k,{'minimum':low,'maximum':high,'sensitivity':gain}))
            pad.colorChosen.connect(lambda color,k=side:self.set_ring_color(k,color))
            pad.detent.connect(lambda:self.call('Feedback',[],quiet=True))
            column.addWidget(pad); self.lighting_pads.append(pad)
        label = QLabel('點擊預覽或按 L3／R3 開啟色環，轉動對應搖杆逐格選色，再按一次關閉。'); label.setWordWrap(True); layout.addWidget(label)
        label = QLabel('X：最低／最高亮度；Y：響應靈敏度（S）。音量自動歸一化，保留左右聲道差異。'); label.setWordWrap(True); layout.addWidget(label)
        label = QLabel('內錄播放音頻；左右聲道分別控制左右搖杆燈。靜音時燈光熄滅。'); label.setWordWrap(True); layout.addWidget(label)
        self.lighting_status = QLabel('—'); self.lighting_status.setWordWrap(True); layout.addWidget(self.lighting_status)
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
        self.lighting_levels = [0.,0.]
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
            self.lighting_status.setText(tr('音頻律動未啟用')); return
        if self.monitor_query: return
        self.monitor_query = True
        query = QProcess(self)
        def done(code=1,*args):
            self.monitor_query = False
            source = bytes(query.readAllStandardOutput()).decode().strip()+'.monitor'
            query.deleteLater()
            if code or source == '.monitor':
                self.lighting_status.setText(tr('無法讀取播放音頻')); return
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
                    self.lighting_status.setText(tr('無法讀取播放音頻')+' · '+bytes(process.readAllStandardError()).decode(errors='replace'))
                    process.deleteLater()
            process.readyReadStandardOutput.connect(read_audio); process.finished.connect(ended)
            process.errorOccurred.connect(lambda e:ended() if e==QProcess.ProcessError.FailedToStart else None)
            process.start('parec',['--device='+source,'--raw','--format=float32le','--rate=8000','--channels=2','--channel-map=front-left,front-right','--latency-msec=50','--client-name=AYN Thor Lighting'])
            self.lighting_status.setText(tr('內錄來源')+' · '+tr('耳機' if 'headphone' in source.lower() else '揚聲器'))
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
            values = samples[channel::2]
            rms = rms_channels[channel]
            pad = self.lighting_pads[channel]
            sensitivity=math.log(pad.sensitivity)/math.log(20)
            threshold=.12-.10*sensitivity
            normalized=max(0.,min(1.,(rms/self.lighting_reference-threshold)/(1-threshold))) if rms > .0008 else 0.
            response=.9*normalized**(1.6-.8*sensitivity)
            if values:
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
        if not self.frame_pending:
            self.frame_pending = True
            self.call('LightingFrame',colors,quiet=True,finished=lambda ok,busy:setattr(self,'frame_pending',False))

    def make_settings(self):
        self.settings_index=self.tabs.count()
        layout = self.page('設定')
        self.settings_stack = QStackedWidget(); layout.addWidget(self.settings_stack)
        self.setting_widgets = {}; self.sliders = self.screen_sliders.copy(); self.group_names = []
        def group(title):
            self.group_names.append(title)
            page = QWidget(); box = QVBoxLayout(page); form = QFormLayout(); box.addLayout(form); box.addStretch()
            self.settings_stack.addWidget(page)
            return form
        form = group('效能')
        self.combo(form,'CPU governor',['performance','schedutil','ondemand','powersave','auto'],'cpu-governor','cpu_governor')
        self.combo(form,'GPU governor',['performance','simple_ondemand','powersave','userspace','auto'],'gpu-governor','gpu_governor')
        self.combo(form,'排程器',['regular','lavd'],'scheduler','scheduler')
        self.boost = self.button('CPU boost',lambda:self.set('cpu-boost',['on' if self.boost.isChecked() else 'off']),True); form.addRow(self.boost)
        self.sliders['rgb'] = self.lighting_brightness
        form = group('按鍵')
        for key,label in [('back','返回鍵'),('home','首頁鍵')]:
            combo = Choice()
            for value,text in ACTIONS.items(): combo.addItem(text,value)
            combo.setCurrentIndex(combo.findData(self.prefs[key])); combo.activated.connect(lambda i,k=key,c=combo:self.set_pref(k,c.currentData())); form.addRow(QLabel(label),combo)
            command = QLineEdit(self.prefs[key+'_command']); command.setPlaceholderText('自訂指令，例如 konsole')
            command.editingFinished.connect(lambda k=key,c=command:self.set_pref(k+'_command',c.text())); form.addRow(QLabel(label+'指令'),command)
        form = group('Android')
        warning = QLabel('極端實驗性功能：可能完全無法工作，甚至可能導致 Android 分區無法啟動。'); warning.setWordWrap(True); warning.setStyleSheet('color:#ffb176; font-weight:600;'); form.addRow(warning)
        self.android_parts = []
        self.android_combo = Choice(); self.android_combo.currentIndexChanged.connect(self.describe_android); form.addRow(QLabel('分區'),self.android_combo)
        self.android_label = QLabel('按查詢讀取 Android 分區'); self.android_label.setWordWrap(True); form.addRow(self.android_label)
        row = QHBoxLayout(); row.addWidget(self.button('查詢',self.refresh_android)); row.addWidget(self.button('唯讀掛載',lambda:self.android_action('mount-android'))); row.addWidget(self.button('卸載',lambda:self.android_action('unmount-android'))); form.addRow(row)
        form.addRow(self.button('開啟 Android 目錄',lambda:self.start('xdg-open','/mnt/aynthor-android')))
        form = group('語言')
        language = Choice()
        for text,value in [('跟隨系統','system'),('English','en'),('简体中文','zh_CN'),('繁體中文','zh_TW')]: language.addItem(text,value)
        language.setCurrentIndex(language.findData(self.prefs['language']))
        language.activated.connect(lambda i:self.change_language(language.currentData()))
        form.addRow(QLabel('語言'),language)
        row = QHBoxLayout(); row.addWidget(self.button('上一組',lambda:self.change_group(-1)))
        self.group_title = QLabel(); self.group_title.setAlignment(Qt.AlignmentFlag.AlignCenter); row.addWidget(self.group_title,1)
        row.addWidget(self.button('下一組',lambda:self.change_group(1))); layout.addLayout(row); self.change_group(0)

    def change_language(self,value):
        self.set_pref('language',value); set_language(value)
        self.translate_dialogs()
        for widget in self.findChildren(QWidget):
            if hasattr(widget,'retranslate'): widget.retranslate()
        for i,title in enumerate(['中控','模式','工作','屏幕控制','風扇管理','燈光管理','設定']): self.tabs.setTabText(i,tr(title))
        self.setWindowTitle(tr('AYN Thor 中控台'))

    def translate_dialogs(self):
        app = QApplication.instance(); app.removeTranslator(self.qt_translator)
        if self.qt_translator.load(QLocale(),'qtbase','_',QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
            app.installTranslator(self.qt_translator)

    def change_group(self,delta):
        index=(self.settings_stack.currentIndex()+delta)%self.settings_stack.count(); self.settings_stack.setCurrentIndex(index)
        self.group_title.setText(f'{self.group_names[index]} · {index+1} / {self.settings_stack.count()}')

    def call(self, method, args, callback=None, quiet=False, finished=None):
        if method not in ('Status','LightingFrame','Feedback'): self.error_text = None
        watcher = QDBusPendingCallWatcher(self.hardware.asyncCall(method,*args),self)
        self.pending.add(watcher)
        def done(w):
            reply = QDBusPendingReply(w).reply()
            self.pending.discard(w)
            if method == 'Status': self.status_busy = False
            busy = reply.type() == QDBusMessage.MessageType.ErrorMessage and reply.errorName() == NAME+'.Busy'
            if busy: pass
            elif reply.type() == QDBusMessage.MessageType.ErrorMessage:
                self.error_text = '錯誤：' + reply.errorMessage()
                self.notify(self.error_text)
            elif callback:
                try: callback(str(reply.arguments()[0]))
                except (ValueError,KeyError,IndexError) as e: self.notify('回覆格式錯誤：'+str(e))
            elif not quiet: self.notify('已套用設定')
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
        self.notify('正在套用…'); self.write_timer.start(60)

    def flush_writes(self):
        if self.write_active is not None or not self.write_queue: return
        key = next(iter(self.write_queue)); operation,values = self.write_queue.pop(key)
        self.write_active = (key,operation,values)
        def completed(success,busy):
            self.write_active = None
            if success and operation == 'fan-curve':
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
            self.smart.show_value(bool(self.state.get('smart')))
            self.vibration.show_value(bool(self.state.get('vibration')))
            self.performance.show_value(self.state.get('performance','standard'))
            self.input_mode.show_value(self.state.get('joystick','gamepad'))
            mode = self.state.get('lighting_mode') or self.state.get('rgb_mode','off')
            self.rgb.show_value(mode); self.lighting_mode.show_value(mode)
            self.sync_lighting(mode)
        self.joystick.setEnabled(False)
        self.joystick.setToolTip(tr('手柄布局')+' · '+self.state.get('layout_reason',''))
        b = self.state.get('battery',{})
        self.battery_text.setText('—%' if b.get('capacity') is None else f"{b['capacity']:.0f}%")
        self.battery_icon.reading((b.get('capacity') or 0)/100,charging=b.get('status') == 'Charging')
        def fmt(v,digits=0): return '—' if v is None else f'{v:.{digits}f}'
        def gauge(key,text,fraction):
            value,bar=self.gauges[key]; value.setText(text); bar.setValue(max(0,min(1000,round((fraction or 0)*1000))))
            self.metric_icons[key].reading(fraction,rpm=self.state.get('fan_rpm') if key == 'fan' else 0,charging=b.get('status') == 'Charging')
        gauge('cpu',f"CPU {fmt(self.state.get('cpu_mhz'))} MHz",(self.state.get('cpu_mhz') or 0)/(self.state.get('cpu_max_mhz') or 3200))
        gauge('gpu',f"GPU {fmt(self.state.get('gpu_mhz'))} MHz",(self.state.get('gpu_mhz') or 0)/(self.state.get('gpu_max_mhz') or 680))
        gauge('temp',f"{fmt(b.get('temp'),1)} °C",(b.get('temp') or 0)/80)
        gauge('fan',f"{fmt(self.state.get('fan_rpm'))} RPM",(self.state.get('fan_percent') or 0)/100)
        gauge('ram',f"{fmt(self.state.get('ram_used_gb'),1)} / {fmt(self.state.get('ram_total_gb'),0)} GB",(self.state.get('ram_used_gb') or 0)/(self.state.get('ram_total_gb') or 1))
        gauge('battery',f"{fmt(b.get('capacity'))}% · {fmt(b.get('watts'),1)} W",(b.get('capacity') or 0)/100)
        self.gauges['temp'][0].setToolTip('電池溫度')
        self.gauges['fan'][0].setToolTip(f"PWM {fmt(self.state.get('fan_percent'))}% · {self.state.get('fan_rpm_source')}")
        self.update_fan()
        self.boost.setChecked(bool(self.state.get('cpu_boost_enabled')))
        for key,widget in self.setting_widgets.items():
            if not self.write_queue and not widget.hasFocus(): widget.setCurrentText(str(self.state.get(key,'')))
        for key,slider in self.sliders.items():
            if slider.isSliderDown() or self.write_queue: continue
            if key == 'both':
                value = sum(100*(v.get('value') or 0)/(v.get('max') or 1) for v in self.state.get('backlight',{}).values())/max(1,len(self.state.get('backlight',{})))
            elif key == 'rgb': value = self.state.get('rgb_brightness',0)
            else:
                item = self.state.get('backlight',{}).get(key,{})
                value = 100 * (item.get('value') or 0) / (item.get('max') or 1)
            slider.setValue(round(value))
        self.notify(self.error_text or ('服務已連線 · AYN 鍵切換中控' if self.state.get('input_ready') else '服務已連線 · 手柄服務尚未就緒'))

    def refresh(self):
        self.clock.setText(time.strftime('%H:%M'))
        self.refresh_audio()
        if self.isVisible() and self.tabs.currentIndex() == 2: self.refresh_tasks()
        if not self.status_busy and self.write_active is None and not self.write_queue:
            self.status_busy = True
            revision = self.write_revision
            self.call('Status',[],lambda raw:self.update_state(raw) if revision == self.write_revision else None,True)
        files = list((DATA/'fps').glob('*.csv')) if (DATA/'fps').exists() else []
        files = [p for p in files if not p.name.endswith('_summary.csv') and time.time()-p.stat().st_mtime < 4]
        self.fps.setText('— FPS')
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
        else: self.fps_source.setText('等待遊戲')

    def set_pref(self, key, value):
        self.prefs[key] = value; save(self.prefs)

    def set_fps_limit(self,value):
        self.set_pref('fps_limit',value); mango_config(self.prefs)

    def set_hud(self,value):
        self.set_pref('hud',value); mango_config(self.prefs)

    def set_autolock(self,value):
        self.set_pref('autolock',value)
        self.start('kwriteconfig6','--file','kscreenlockerrc','--group','Daemon','--key','Autolock','true' if value else 'false')
        QTimer.singleShot(150,lambda:self.session_call('org.kde.screensaver','/ScreenSaver','org.kde.screensaver','configure',[]))

    def set_rgb_mode(self,value):
        self.stop_lighting()
        self.set('lighting-mode',[value])

    def choose_color(self):
        color = QColorDialog.getColor(QColor(self.state.get('rgb_static_hex','#0080ff')),self,'氛圍燈顏色')
        if color.isValid(): self.set('rgb-color',list(map(str,[color.red(),color.green(),color.blue()])))

    def start(self,*args):
        process = QProcess(self); self.processes.add(process)
        process.errorOccurred.connect(lambda error: self.notify('無法啟動：'+args[0]+' · '+process.errorString()))
        def finished(code,status):
            if code: self.notify(process.readAllStandardError().data().decode(errors='replace') or f'{args[0]} 結束碼 {code}')
            self.processes.discard(process); process.deleteLater()
        process.finished.connect(finished); process.start(args[0],list(args[1:]))

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
        if action in ('lighting-left','lighting-right'):
            if self.isVisible() and self.tabs.currentIndex() == 5: self.lighting_pads[0 if action=='lighting-left' else 1].toggle_color()
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
        return [('region','區域截圖','camera'),('top','上屏截圖','monitor'),('bottom','下屏截圖','monitor')]

    def set_screenshot_mode(self,value):
        if value not in ('region','top','bottom'): return
        self.set_pref('screenshot_mode',value)
        self.shot.show_value(value); self.screenshot_mode.show_value(value)

    def screenshot(self):
        if getattr(self,'screenshot_process',None): return
        mode = self.prefs.get('screenshot_mode','top')
        if mode not in ('region','top','bottom'): mode='top'
        geometries = {screen.name():screen.geometry() for screen in QApplication.screens()}
        name = 'DSI-2' if mode == 'top' else 'DSI-1'
        if mode != 'region' and name not in geometries:
            self.error_text = tr('找不到截圖屏幕'); self.notify(self.error_text); return
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
                    success = False; error = tr('截圖尺寸與屏幕配置不符')
                else:
                    g = geometries[name]
                    x = round((g.x()-bounds.x())*sx); y = round((g.y()-bounds.y())*sy)
                    right = round((g.x()+g.width()-bounds.x())*sx); bottom = round((g.y()+g.height()-bounds.y())*sy)
                    success = image.copy(x,y,right-x,bottom-y).save(str(target))
            if success: self.start('notify-send',tr('截圖'),str(target))
            elif mode == 'region' and code == 0 and not target.exists(): self.showFullScreen()
            else:
                self.error_text = tr('截圖失敗')+' · '+error
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
        if uid != os.getuid() or not self.isVisible() or self.tabs.currentIndex()!=5: return
        self.lighting_pads[0 if side=='left' else 1].rotate_stick(x,y)

    @pyqtSlot('uint',str)
    def on_button(self, uid, action):
        if uid != os.getuid(): return
        if action in ('lighting-left','lighting-right'): self.action(action); return
        if action == 'panel': self.Toggle(); return
        configured = self.prefs.get(action,'none')
        if configured == 'command':
            try:
                argv = shlex.split(self.prefs.get(action+'_command',''))
                if argv: self.start(*argv)
            except ValueError as e: self.notify(str(e))
        else: self.action(configured)

    @pyqtSlot()
    def Toggle(self):
        if self.isVisible(): self.hide()
        else:
            if self.tabs.currentIndex()==2: self.refresh_tasks()
            self.place(); self.showFullScreen(); self.raise_(); self.activateWindow()

    @pyqtSlot()
    def Settings(self):
        self.tabs.setCurrentIndex(self.settings_index); self.place(); self.showFullScreen(); self.raise_(); self.activateWindow()

    @pyqtSlot(str, result=bool)
    def Snapshot(self,path):
        return self.grab().save(path)

    def place(self):
        screen = next((s for s in QApplication.screens() if s.name() == 'DSI-1'),QApplication.primaryScreen())
        self.winId(); self.windowHandle().setScreen(screen)
        self.resize(min(604,screen.availableGeometry().width()-12),min(520,screen.availableGeometry().height()-12))
        self.move(screen.availableGeometry().center()-self.rect().center())

    def closeEvent(self,event):
        event.ignore(); self.hide()

    def refresh_android(self):
        def update(raw):
            self.android_parts=sorted(json.loads(raw),key=lambda p:p['label']!='userdata'); self.android_combo.clear()
            for p in self.android_parts: self.android_combo.addItem(p['label'],p['label'])
            self.describe_android(0)
        self.call('AndroidPartitions',[],update)

    def describe_android(self,index):
        if not self.android_parts: self.android_label.setText('未找到 Android 分區'); return
        p=self.android_parts[index]
        if p['label'] == 'userdata' and not p['mountable']:
            self.android_label.setText('/sdcard → /data/media/0\n'+tr('Android 使用硬體封裝加密；Linux 尚未支援解鎖。'))
            return
        self.android_label.setText(f"{index+1} / {len(self.android_parts)} · {p.get('filesystem') or 'super 邏輯分區'}\n"+(p['reason'] or '可唯讀掛載'))

    def android_action(self,operation):
        label = self.android_combo.currentData()
        if label: self.set(operation,[label])
        else: self.refresh_android()

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
                if path.stat().st_uid != os.getuid(): continue
                record['starttime']=(path/'stat').read_text().rsplit(')',1)[1].split()[19]
                self.task_records.append(record)
            self.change_task_page(0)
        except (OSError,ValueError,KeyError,IndexError) as e: self.notify(str(e))

    def change_task_page(self,delta):
        count=max(1,(len(self.task_records)+5)//6); self.task_page=max(0,min(count-1,self.task_page+delta)); self.selected_task=None
        self.task_count.setText(f'{self.task_page+1} / {count}')
        for i,button in enumerate(self.task_buttons):
            index=self.task_page*6+i; button.setChecked(False); button.setEnabled(index<len(self.task_records))
            record=self.task_records[index] if index<len(self.task_records) else None
            text=(record['caption'][:24]+' · '+tr('上屏' if record.get('screen')=='DSI-2' else '下屏' if record.get('screen')=='DSI-1' else '其他屏幕')) if record else '—'
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
                    parser.read(file)
                    name = parser.get('Desktop Entry','Icon',fallback='application-x-executable')
                    return QIcon(name) if name.startswith('/') else QIcon.fromTheme(name,control_icon('monitor'))
                except configparser.Error:
                    pass
        return QIcon.fromTheme(desktop,control_icon('monitor'))

    def task_menu(self,index):
        offset = self.task_page*6+index
        if offset >= len(self.task_records): return
        record = dict(self.task_records[offset]); menu = QMenu(self)
        for name,title in [('DSI-2','移到上屏'),('DSI-1','移到下屏')]:
            action = menu.addAction(control_icon('monitor'),tr(title))
            action.triggered.connect(lambda checked=False,n=name:self.move_task(record,n))
        menu.addSeparator()
        saved = self.prefs.get('app_screens',{}).get(record['app'].lower(),'')
        for name,title in [('DSI-2','總是在上屏開啟'),('DSI-1','總是在下屏開啟'),('','跟隨預設屏幕')]:
            action = menu.addAction(tr(title)); action.setCheckable(True); action.setChecked(name==saved)
            action.triggered.connect(lambda checked=False,n=name:self.remember_task_screen(record,n))
        menu.exec(self.task_buttons[index].mapToGlobal(self.task_buttons[index].rect().center()))

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
        self.hide()
        self.start('qdbus6','org.kde.KWin','/Scripting','org.kde.kwin.Scripting.unloadScript','aynthor-activate')
        QTimer.singleShot(150,lambda:self.start('qdbus6','org.kde.KWin','/Scripting','org.kde.kwin.Scripting.loadScript',str(script),'aynthor-activate'))
        QTimer.singleShot(300,lambda:self.start('qdbus6','org.kde.KWin','/Scripting','org.kde.kwin.Scripting.start'))

    def choose_game(self):
        command,ok = QInputDialog.getText(self,tr('啟動遊戲'),tr('程式與參數'),text=self.prefs.get('game_command',''))
        if ok:
            try:
                args=shlex.split(command)
                if args:
                    self.set_pref('game_command',command)
                    self.start('/usr/bin/aynthor-control','--run',*args)
            except ValueError as e:self.notify(str(e))


def main():
    if '--run' in sys.argv:
        args = sys.argv[sys.argv.index('--run')+1:]
        if not args: raise SystemExit('Usage: aynthor-control --run PROGRAM [ARGS]')
        env = os.environ.copy(); env['MANGOHUD_CONFIGFILE'] = str(mango_config(preferences()))
        os.execvpe('mangohud',['mangohud',*args],env)
    app = QApplication(sys.argv); app.setQuitOnLastWindowClosed(False); app.setDesktopFileName('org.aynthor.Control')
    bus = QDBusConnection.sessionBus()
    if bus.interface().isServiceRegistered(APP).value():
        if '--background' in sys.argv: return
        interface = QDBusInterface(APP,'/Control',APP,bus)
        if '--snapshot' in sys.argv: interface.call('Snapshot',sys.argv[sys.argv.index('--snapshot')+1])
        else: interface.call('Settings' if '--settings' in sys.argv else 'Toggle')
        return
    panel = Panel()
    if '--settings' in sys.argv: panel.Settings()
    elif '--background' not in sys.argv: panel.Toggle()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
