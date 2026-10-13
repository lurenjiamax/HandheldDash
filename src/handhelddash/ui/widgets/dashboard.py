# SPDX-License-Identifier: LGPL-3.0-or-later
from handhelddash.ui.common import DASHBOARD_TILES, QApplication, QDrag, QLabel, QMimeData, QPainter, QSize, QSizePolicy, QTabBar, QTimer, QWidget, Qt, TILE_MIME, pyqtSignal, tr
from handhelddash.ui.widgets.buttons import QPushButton, paint_quick_tile

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
