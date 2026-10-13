# SPDX-License-Identifier: LGPL-3.0-or-later
from handhelddash.ui.common import QHBoxLayout, QLabel, QWidget, Qt, pyqtSignal
from handhelddash.ui.widgets.buttons import QPushButton

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
