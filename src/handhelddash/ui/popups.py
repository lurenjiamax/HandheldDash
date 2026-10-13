"""Reusable in-panel dialogs and paged selectors; no hardware/WM access."""
from PyQt6.QtCore import QEvent, QRect, QSize, Qt, QTimer
from PyQt6.QtGui import QFontMetrics
from PyQt6.QtWidgets import (QAbstractItemView, QDialog, QGridLayout, QHBoxLayout,
                            QListWidget, QListWidgetItem, QSizePolicy, QVBoxLayout, QWidget)
from localization import Label as QLabel, tr
from handhelddash.integrations.inputplumber.catalog import CATEGORIES
from .design import TOUCH_SIZE, ROW_HEIGHT, SPACING
from .theme import theme_color


class EmbeddedPopup(QDialog):
    """Panel-local standard dialog, independent of native Wayland activation."""
    def __init__(self,panel):
        self.scrim=QWidget(panel); self.scrim.setObjectName('PopupScrim')
        self.scrim.setStyleSheet('QWidget#PopupScrim { background:rgba(0,0,0,110); }'); self.scrim.hide()
        super().__init__(self.scrim)
        self.setWindowFlags(Qt.WindowType.Widget)
        self.setObjectName('EmbeddedPopup'); self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground,True)
        self.update_theme(); self.panel=panel; self.scrim.installEventFilter(self)

    def update_theme(self):
        self.setStyleSheet('QWidget#EmbeddedPopup { background:'+theme_color('#222331').name()+'; border:1px solid '+theme_color('#45465e').name()+'; border-radius:12px; }')

    def showEvent(self,event):
        self.scrim.setGeometry(self.panel.rect()); self.scrim.show(); self.scrim.raise_()
        self.move(self.scrim.rect().center()-self.rect().center()); self.raise_()
        super().showEvent(event)

    def show(self):
        self.scrim.setGeometry(self.panel.rect()); self.scrim.show(); self.scrim.raise_(); super().show()

    def hideEvent(self,event):
        self.scrim.hide(); super().hideEvent(event)

    def reject(self):
        if not self.property('applying'): super().reject()

    def eventFilter(self,watched,event):
        if watched is self.scrim and event.type()==QEvent.Type.MouseButtonPress:
            if not self.geometry().contains(event.position().toPoint()): self.reject()
            return True
        return super().eventFilter(watched,event)


class ControllerChoicePage(QWidget):
    """Upstream names, category navigation and height-aware pages."""
    def __init__(self,panel,items,selected,changed,categorized=False):
        super().__init__()
        self.panel=panel; self.items=items; self.selected=selected; self.changed=changed
        self.categorized=categorized; self.category=''; self.page_index=0; self.chunks=[]; self.visible_buttons={}; self.rebuilding=False
        self.setMinimumSize(0,0); box=QVBoxLayout(self); box.setContentsMargins(8,8,8,8); box.setSpacing(SPACING)
        if categorized:
            categories=tuple(dict.fromkeys((*CATEGORIES,*(item.get('category',CATEGORIES[-1]) for item in items))))
            current=next((item for item in items if item['id']==selected),None)
            self.category=current.get('category',CATEGORIES[-1]) if current else next((category for category in categories if any(item.get('category')==category for item in items)),CATEGORIES[-1])
            grid=QGridLayout(); grid.setSpacing(SPACING); self.category_buttons={}
            for index,category in enumerate(categories):
                count=sum(item.get('category',CATEGORIES[-1])==category for item in items)
                button=panel.button(tr(category)+f' · {count}',lambda checked=False,value=category:self.set_category(value))
                button.setCheckable(True); button.setChecked(category==self.category); button.setEnabled(count>0); button.setFixedHeight(TOUCH_SIZE)
                button.setMinimumWidth(0); button.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed)
                grid.addWidget(button,index//2,index%2); self.category_buttons[category]=button
            box.addLayout(grid)
        self.rows=QListWidget(); self.rows.setMinimumSize(0,0); self.rows.setWordWrap(True)
        self.rows.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.rows.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.rows.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff); self.rows.setSpacing(4)
        self.rows.setStyleSheet('QListWidget { background:transparent; border:0; }'
            'QListWidget::item { padding:8px; border:1px solid '+theme_color('#45465e').name()+'; border-radius:6px; background:'+theme_color('#222331').name()+'; }'
            'QListWidget::item:selected { border:2px solid '+theme_color('#8ab4f8').name()+'; background:'+theme_color('#343b54').name()+'; }')
        self.rows.itemClicked.connect(lambda item:self.choose(item.data(Qt.ItemDataRole.UserRole))); box.addWidget(self.rows,1)
        self.navigation=QWidget(); row=QHBoxLayout(self.navigation); row.setContentsMargins(0,0,0,0)
        self.previous=panel.button('Previous',lambda:self.show_page(self.page_index-1)); self.next=panel.button('Next',lambda:self.show_page(self.page_index+1))
        self.counter=QLabel(); self.counter.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(self.previous,1); row.addWidget(self.counter,1); row.addWidget(self.next,1); box.addWidget(self.navigation)
        self.initial_selection=True

    def set_category(self,category):
        self.category=category; self.page_index=0
        for value,button in self.category_buttons.items(): button.setChecked(value==category)
        self.rebuild()

    def resizeEvent(self,event):
        super().resizeEvent(event); QTimer.singleShot(0,self.rebuild)

    def showEvent(self,event):
        super().showEvent(event); QTimer.singleShot(0,self.rebuild)

    def rebuild(self):
        if self.rebuilding or not self.isVisible(): return
        self.rebuilding=True
        try:
            items=[item for item in self.items if not self.categorized or item.get('category',CATEGORIES[-1])==self.category]
            width=max(100,self.rows.viewport().width()-24); available=max(ROW_HEIGHT,self.rows.viewport().height())
            metrics=QFontMetrics(self.rows.font()); chunks=[]; chunk=[]; used=0
            for item in items:
                name_height=metrics.boundingRect(QRect(0,0,width,10000),Qt.TextFlag.TextWordWrap,item['name']+'\n'+item['id']).height()
                height=max(ROW_HEIGHT,name_height+24)
                if chunk and used+height+8>available: chunks.append(chunk); chunk=[]; used=0
                chunk.append((item,height)); used+=height+8
            if chunk: chunks.append(chunk)
            self.chunks=chunks
            if self.initial_selection:
                self.page_index=next((index for index,chunk in enumerate(chunks) if any(item['id']==self.selected for item,height in chunk)),0); self.initial_selection=False
            self.show_page(self.page_index)
        finally: self.rebuilding=False

    def show_page(self,index):
        self.page_index=max(0,min(index,len(self.chunks)-1)); self.visible_buttons={}; self.rows.clear()
        if self.chunks:
            for item,height in self.chunks[self.page_index]:
                choice=QListWidgetItem(item['name']+'\n'+item['id']); choice.setData(Qt.ItemDataRole.UserRole,item['id'])
                choice.setSizeHint(QSize(0,height)); choice.setToolTip(item.get('description') or item['name'])
                self.rows.addItem(choice); choice.setSelected(item['id']==self.selected); self.visible_buttons[item['id']]=choice
        total=max(1,len(self.chunks)); self.counter.setText(f'{self.page_index+1} / {total}')
        self.previous.setEnabled(self.page_index>0); self.next.setEnabled(self.page_index+1<len(self.chunks)); self.navigation.show()

    def choose(self,identity):
        self.selected=identity
        for value,item in self.visible_buttons.items(): item.setSelected(value==identity)
        self.changed(identity)
