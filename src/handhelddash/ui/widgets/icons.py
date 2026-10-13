# SPDX-License-Identifier: LGPL-3.0-or-later
from handhelddash.ui.assets import asset_path
from handhelddash.ui.common import ICON_SIZE, Path, QApplication, QIcon, QPainter, QPixmap, QProxyStyle, QRectF, QStyle, QTimer, QWidget, Qt, lru_cache, theme_color, time

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
    file = asset_path('icons/'+name+'.svg')
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
