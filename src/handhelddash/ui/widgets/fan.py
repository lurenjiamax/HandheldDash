# SPDX-License-Identifier: LGPL-3.0-or-later
from handhelddash.ui.common import QPainter, QPen, QPointF, QPolygonF, QRectF, QWidget, Qt, math, pyqtSignal, theme_color

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
