# SPDX-License-Identifier: LGPL-3.0-or-later
from handhelddash.ui.common import QPainter, QPointF, QRectF, QSlider, QStyle, QStyleOptionSlider, QTimer, Qt, pyqtSignal, theme_color

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
