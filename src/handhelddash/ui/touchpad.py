# SPDX-License-Identifier: LGPL-3.0-or-later
from handhelddash.ui.common import DEVICE, NAME, PATH, QApplication, QDBus, QDBusMessage, QPainter, QPen, QRectF, QTimer, QWidget, Qt, json, theme_color

class Touchpad(QWidget):
    def __init__(self, panel):
        super().__init__(); self.panel = panel
        self.setMinimumHeight(160)
        self.heartbeat = QTimer(self); self.heartbeat.timeout.connect(self.send_region); self.heartbeat.setInterval(250)

    def send_region(self, enabled=True):
        region = []
        if enabled and self.isVisible():
            screen = next((s for s in QApplication.screens() if s.name() == DEVICE.screen_name('bottom',QApplication.screens())),None)
            if screen:
                geometry = screen.geometry(); origin = self.mapToGlobal(self.rect().topLeft())-geometry.topLeft()
                region = [round(origin.x()*10000/geometry.width()),round(origin.y()*10000/geometry.height()),
                          round((origin.x()+self.width())*10000/geometry.width()),round((origin.y()+self.height())*10000/geometry.height())]
                region = [max(0,min(10000,v)) for v in region]
                if region[0] >= region[2] or region[1] >= region[3]: region = []
        message = QDBusMessage.createMethodCall(NAME,PATH,NAME,'TouchpadRegion')
        top = next((s for s in QApplication.screens() if s.name() == DEVICE.screen_name('top',QApplication.screens())),QApplication.primaryScreen())
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
        self.panel.desktop.stop_touchpad()
        super().hideEvent(event)

    def paintEvent(self,event):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(theme_color('#303144')); p.setPen(QPen(theme_color('#79718d'),1))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(1,1,-1,-1),18,18)
