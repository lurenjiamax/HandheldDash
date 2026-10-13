"""Shared adjustment presentation, with callbacks supplied by the application."""
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtWidgets import QWidget, QHBoxLayout
from localization import Label as QLabel
from .design import TOUCH_SIZE


class AdjustmentRow(QWidget):
    def __init__(self,button,slider_factory,maximum,icon_size,parent=None):
        super().__init__(parent); self.setObjectName('Gauge'); row=QHBoxLayout(self)
        self.icon=button; self.icon.setIconSize(QSize(icon_size,icon_size)); self.icon.setFixedWidth(TOUCH_SIZE)
        self.icon.setStyleSheet('border:0; background:transparent; padding:0; min-height:'+str(TOUCH_SIZE)+'px;')
        row.addWidget(self.icon)
        self.slider=slider_factory(Qt.Orientation.Horizontal); self.slider.setRange(0,maximum); row.addWidget(self.slider,1)
        self.label=QLabel('—%'); row.addWidget(self.label)
        self.slider.valueChanged.connect(lambda value:self.label.setText(f'{value}%'))
