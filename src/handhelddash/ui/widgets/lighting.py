# SPDX-License-Identifier: LGPL-3.0-or-later
from handhelddash.ui.common import QBrush, QColor, QConicalGradient, QPainter, QPen, QPointF, QRectF, QWidget, Qt, math, pyqtSignal, theme_color, tr

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
