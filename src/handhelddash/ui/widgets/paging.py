"""Bounded dashboard pages with swipe navigation and compact page dots."""
from PyQt6.QtCore import QObject, QEvent, Qt, pyqtSignal, QTimer, QPoint, QPropertyAnimation, QParallelAnimationGroup, QEasingCurve
from PyQt6.QtWidgets import QApplication, QHBoxLayout, QPushButton, QWidget, QLabel


class RegionPager(QObject):
    changed = pyqtSignal()

    def __init__(self, region, parent):
        super().__init__(parent)
        self.region=region; self.index=0; self.count=1; self.enabled=True
        self.origin=None; self.pressed=None; self.swiped=False
        self.animating=False
        self.indicator=QWidget(region)
        self.dots=QHBoxLayout(self.indicator); self.dots.setContentsMargins(0,0,0,0); self.dots.setSpacing(4)
        QApplication.instance().installEventFilter(self)
        QApplication.instance().aboutToQuit.connect(self.detach)
        region.destroyed.connect(self.detach)

    def detach(self):
        application=QApplication.instance()
        if application is not None: application.removeEventFilter(self)

    def configure(self, count, enabled):
        count=max(1,count)
        changed=count!=self.count or enabled!=self.enabled
        self.count=count; self.enabled=enabled; self.index=min(self.index,count-1)
        if changed:
            while self.dots.count():
                item=self.dots.takeAt(0)
                if item.widget(): item.widget().deleteLater()
            self.dots.addStretch()
            for index in range(count):
                dot=QPushButton('●' if index==self.index else '○',self.indicator)
                dot.setFixedSize(24,20); dot.setAccessibleName(f'{index+1} / {count}')
                dot.setStyleSheet('background:transparent; border:0; padding:0; min-height:0; font-size:10px;')
                dot.clicked.connect(lambda checked=False,i=index:self.select(i)); self.dots.addWidget(dot)
            self.dots.addStretch()
        else:
            for index,dot in enumerate(self.indicator.findChildren(QPushButton)):
                dot.setText('●' if index==self.index else '○')
        self.indicator.setVisible(count>1 and getattr(self.parent(),'dashboard_editing',False))

    def select(self,index):
        index=max(0,min(self.count-1,index))
        if index==self.index or self.animating: return
        direction=1 if index>self.index else -1
        before=self.region.grab(); self.index=index; self.changed.emit()
        if not self.region.isVisible(): return
        self.animating=True
        def animate():
            after=self.region.grab(); width=self.region.width(); height=self.region.height()
            old=QLabel(self.region); old.setPixmap(before); old.resize(width,height)
            new=QLabel(self.region); new.setPixmap(after); new.resize(width,height)
            for label in (old,new): label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents); label.show(); label.raise_()
            group=QParallelAnimationGroup(self.region); self.animation=group
            for label,start,end in [(old,QPoint(0,0),QPoint(-direction*width,0)),(new,QPoint(direction*width,0),QPoint(0,0))]:
                animation=QPropertyAnimation(label,b'pos',group); animation.setDuration(180)
                animation.setStartValue(start); animation.setEndValue(end); animation.setEasingCurve(QEasingCurve.Type.OutCubic); group.addAnimation(animation)
            def finish():
                old.deleteLater(); new.deleteLater(); self.animating=False; group.deleteLater()
            group.finished.connect(finish); group.start()
        QTimer.singleShot(0,animate)

    def eventFilter(self,watched,event):
        if event.type() not in (QEvent.Type.MouseButtonPress,QEvent.Type.MouseMove,QEvent.Type.MouseButtonRelease): return False
        if self.animating: return False
        if not self.enabled or self.count<2 or not self.region.isVisible(): return False
        if not isinstance(watched,QWidget) or not (watched is self.region or self.region.isAncestorOf(watched)): return False
        if watched is self.indicator or self.indicator.isAncestorOf(watched): return False
        # Editing keeps horizontal drag-and-drop; page dots remain available.
        if getattr(self.parent(),'dashboard_editing',False): return False
        kind=event.type()
        if kind==QEvent.Type.MouseButtonPress and event.button()==Qt.MouseButton.LeftButton:
            self.origin=event.globalPosition(); self.pressed=watched; self.swiped=False
        elif kind==QEvent.Type.MouseMove and self.origin is not None:
            delta=event.globalPosition()-self.origin
            if abs(delta.x())>45 and abs(delta.x())>abs(delta.y())*1.5:
                self.swiped=True
                button=self.pressed
                while button is not None and button is not self.region:
                    if hasattr(button,'setDown'): button.setDown(False)
                    for name in ('hold_timer','context_timer'):
                        if hasattr(button,name): getattr(button,name).stop()
                    button=button.parentWidget()
                return True
        elif kind==QEvent.Type.MouseButtonRelease and self.origin is not None:
            delta=event.globalPosition()-self.origin; swipe=self.swiped
            self.origin=None; self.pressed=None; self.swiped=False
            if swipe:
                self.select(self.index+(1 if delta.x()<0 else -1)); return True
        return False
