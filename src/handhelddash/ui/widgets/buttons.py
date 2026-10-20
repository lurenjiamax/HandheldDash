# SPDX-License-Identifier: LGPL-3.0-or-later
from handhelddash.ui.common import ICON_SIZE, LocalizedButton, QColor, QFont, QIcon, QMenu, QPainter, QPen, QRectF, QSize, QSizePolicy, QStyle, QStyleOptionButton, QStylePainter, QTimer, Qt, math, pyqtSignal, theme_color, time, tr
from handhelddash.ui.widgets.icons import control_icon

class QPushButton(LocalizedButton):
    """Give action/menu icons a short interaction pulse, not perpetual motion."""
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs); self.motion_started=0; self.motion_progress=1
        self.motion_timer=QTimer(self); self.motion_timer.setInterval(16); self.motion_timer.timeout.connect(self.animate_motion)
        self.pressed.connect(self.start_motion)

    def start_motion(self):
        return

    def animate_motion(self):
        self.motion_progress=min(1,(time.monotonic()-self.motion_started)/.2); self.update()
        if self.motion_progress>=1: self.motion_timer.stop()

    def paintEvent(self,event):
        if self.icon().isNull() or self.motion_progress>=1: return super().paintEvent(event)
        painter=QStylePainter(self); option=QStyleOptionButton(); self.initStyleOption(option)
        icon=option.icon; option.icon=QIcon(); painter.drawControl(QStyle.ControlElement.CE_PushButton,option)
        side=self.iconSize().width(); x=(self.width()-side)/2 if not self.text() else 12; y=(self.height()-side)/2
        scale=1-.14*math.sin(math.pi*self.motion_progress)
        painter.translate(x+side/2,y+side/2); painter.scale(scale,scale)
        icon.paint(painter,round(-side/2),round(-side/2),side,side)

class TaskButton(QPushButton):
    held = pyqtSignal()

    def __init__(self,*args):
        super().__init__(*args)
        self.holding = False
        self.hold_timer = QTimer(self); self.hold_timer.setSingleShot(True); self.hold_timer.setInterval(550)
        self.hold_timer.timeout.connect(self.on_hold)

    def on_hold(self):
        self.holding = True; self.setDown(False); self.held.emit()

    def mousePressEvent(self,event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.holding = False; self.hold_timer.start()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self,event):
        self.hold_timer.stop()
        if self.holding:
            self.setDown(False); event.accept(); return
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self,event):
        if not self.rect().contains(event.pos()): self.hold_timer.stop()
        super().mouseMoveEvent(event)

class StateButton(QPushButton):
    """Tap cycles values; a hold opens the same choices without cycling on release."""
    def __init__(self, title, options, callback, icon_only=False):
        super().__init__(title)
        self.icon_only=icon_only
        self.title = title; self.options = options; self.callback = callback
        self.current = options[0][0]; self.held = False; self.menu = None
        self.previous_icon=QIcon(); self.icon_kind=None; self.icon_transition=1; self.icon_started=0
        self.icon_timer=QTimer(self); self.icon_timer.setInterval(16); self.icon_timer.timeout.connect(self.animate_icon)
        self.setIconSize(QSize(ICON_SIZE,ICON_SIZE)); self.setMinimumHeight(32)
        self.hold_timer = QTimer(self); self.hold_timer.setSingleShot(True)
        self.hold_timer.setInterval(550); self.hold_timer.timeout.connect(self.open_options)
        self.pressed.connect(self.begin_hold); self.released.connect(self.hold_timer.stop)
        self.clicked.connect(self.cycle); self.render()

    def begin_hold(self):
        self.held = False; self.hold_timer.start()

    def cycle(self):
        if self.held: return
        values = [o[0] for o in self.options]
        index = values.index(self.current) if self.current in values else -1
        self.choose(self.options[(index+1)%len(values)][0])

    def choose(self,value):
        self.current=value; self.render(); self.callback(value)

    def show_value(self,value):
        self.current=value; self.render()

    def render(self):
        option = next((o for o in self.options if o[0] == self.current),None)
        label=option[1] if option else self.title
        self.setText('' if self.icon_only else label)
        kind=option[2] if option else 'gauge'
        self.icon_transition=1; self.icon_timer.stop()
        self.icon_kind=kind; self.setIcon(control_icon(kind))
        self.setAccessibleName(tr(self.title)+': '+tr(label))
        self.setToolTip(tr(self.title)+': '+tr(label) if self.icon_only or self.property('dashboard') else tr(self.title))

    def animate_icon(self):
        self.icon_transition=min(1,(time.monotonic()-self.icon_started)/.22); self.update()
        if self.icon_transition>=1: self.icon_timer.stop()

    def paint_icon(self,painter,kind,x,y,side,color=None):
        painter.save()
        if self.icon_transition<1:
            painter.setOpacity(1-self.icon_transition); self.previous_icon.paint(painter,x,y,side,side)
        painter.setOpacity(self.icon_transition); control_icon(kind,color=color).paint(painter,x,y,side,side)
        painter.restore()

    def open_options(self):
        if not self.isDown(): return
        self.held = True; self.setDown(False)
        self.menu = QMenu(self.window()); self.menu.setTitle(tr(self.title))
        self.menu.setMaximumHeight(max(120,self.screen().availableGeometry().height()-40))
        for value,title,icon in self.options:
            action = self.menu.addAction(control_icon(icon),tr(title))
            action.setCheckable(True); action.setChecked(value == self.current)
            action.triggered.connect(lambda checked=False,v=value:self.choose(v))
        self.menu.aboutToHide.connect(self.menu.deleteLater)
        self.menu.popup(self.mapToGlobal(self.rect().bottomLeft()))

    def mouseMoveEvent(self,event):
        if not self.rect().contains(event.position().toPoint()): self.hold_timer.stop()
        super().mouseMoveEvent(event)

    def sizeHint(self):
        hint=super().sizeHint()
        hint.setWidth(max(hint.width(),self.fontMetrics().horizontalAdvance(self.text())+ICON_SIZE+32))
        return hint

    def minimumSizeHint(self): return self.sizeHint()

    def paintEvent(self,event):
        painter = QStylePainter(self); option = QStyleOptionButton(); self.initStyleOption(option)
        painter.drawControl(QStyle.ControlElement.CE_PushButtonBevel,option)
        if self.objectName() == 'FpsLimit':
            painter.setPen(self.palette().buttonText().color())
            painter.drawText(self.rect(),Qt.AlignmentFlag.AlignCenter,'∞' if self.current == 0 else tr('Cap')+f' {self.current}')
            return
        side = ICON_SIZE; x = 0 if self.objectName() == 'MetricValue' else 12
        if isinstance(self,TemperatureButton): side=0; x=-8
        else: self.paint_icon(painter,self.icon_kind,x,(self.height()-side)//2,side)
        painter.setPen(self.palette().buttonText().color())
        rect = self.rect().adjusted(x+side+8,0,-12,0)
        text = self.fontMetrics().elidedText(self.text(),Qt.TextElideMode.ElideRight,max(0,rect.width())) if self.property('dashboard') else self.text()
        painter.drawText(rect,Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter,text)

class TemperatureButton(StateButton):
    def render(self):
        super().render()
        option=next((o for o in self.options if o[0] == self.current),None)
        self.setText(option[1].split(' · ')[-1] if option else '— °C')

class ScreenshotButton(StateButton):
    def __init__(self, options, callback, capture):
        super().__init__('Screenshot',options,callback); self.capture = capture

    def cycle(self):
        if not self.held: self.capture()

def paint_quick_tile(widget,painter,title,subtitle,kind,active=False,badge='',core=False,selected=False):
    """Center the complete content block inside either fixed card specification."""
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    background=theme_color('#303144'); accent=theme_color('#a68bff'); ink=theme_color('#f2efff'); muted=theme_color('#b8b5ca')
    if active:
        background=QColor.fromRgbF(background.redF()*.8+accent.redF()*.2,background.greenF()*.8+accent.greenF()*.2,background.blueF()*.8+accent.blueF()*.2)
    if not widget.isEnabled(): ink=muted
    navigation_focus=widget.hasFocus() and getattr(widget,'navigation_focus',widget.window().testAttribute(Qt.WidgetAttribute.WA_KeyboardFocusChange))
    border=accent if active or selected or navigation_focus else theme_color('#45465e')
    pen=QPen(border,2 if selected else 1)
    if selected: pen.setStyle(Qt.PenStyle.DashLine)
    painter.setPen(pen); painter.setBrush(background); painter.drawRoundedRect(QRectF(widget.rect()).adjusted(1,1,-1,-1),10,10)
    if widget.isDown():
        pressed=QColor(accent); pressed.setAlpha(35); painter.setPen(Qt.PenStyle.NoPen); painter.setBrush(pressed)
        painter.drawRoundedRect(QRectF(widget.rect()).adjusted(2,2,-2,-2),10,10)
    title_font=QFont(widget.font()); title_font.setPixelSize(15 if core else 13); title_font.setBold(True)
    state_font=QFont(widget.font()); state_font.setPixelSize(13 if core else 12)
    painter.setFont(title_font); title_h=painter.fontMetrics().height(); title_w=painter.fontMetrics().horizontalAdvance(tr(title))
    painter.setFont(state_font); state_h=painter.fontMetrics().height() if subtitle else 0; state_w=painter.fontMetrics().horizontalAdvance(tr(subtitle))
    if core:
        side=28; available=max(0,widget.width()-side-10-24)
        text_w=min(max(title_w,state_w),available)
        def lines_for(text,font,limit):
            painter.setFont(font); metrics=painter.fontMetrics(); words=tr(text).split(); lines=[]; line=''
            for word in words:
                candidate=(line+' '+word).strip()
                if line and metrics.horizontalAdvance(candidate)>available:
                    lines.append(line); line=word
                else: line=candidate
            if line: lines.append(line)
            if len(lines)>limit: lines=lines[:limit-1]+[' '.join(lines[limit-1:])]
            return [metrics.elidedText(line,Qt.TextElideMode.ElideRight,max(0,round(available))) for line in lines]
        title_limit=2 if title_w>available and 2*title_h+state_h+2<=widget.height()-12 else 1
        state_limit=2 if subtitle and state_w>available and title_limit*title_h+2*state_h+2<=widget.height()-12 else 1
        title_lines=lines_for(title,title_font,title_limit); state_lines=lines_for(subtitle,state_font,state_limit)
        if title_w>available or state_w>available: text_w=available
        left=(widget.width()-side-10-text_w)/2
        if hasattr(widget,'paint_icon'): widget.paint_icon(painter,kind,round(left),round((widget.height()-side)/2),side,ink.name())
        else: control_icon(kind,color=ink.name()).paint(painter,round(left),round((widget.height()-side)/2),side,side)
        title_block=max(1,len(title_lines))*title_h; state_block=len(state_lines)*state_h
        top=(widget.height()-title_block-state_block-(2 if state_lines else 0))/2
        for lines,font,color,line_height,offset in [(title_lines,title_font,ink,title_h,0),(state_lines,state_font,muted,state_h,title_block+2)]:
            painter.setFont(font); painter.setPen(color)
            for index,line in enumerate(lines): painter.drawText(QRectF(left+side+10,top+offset+index*line_height,text_w,line_height),Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter,line)
        rects=[]
        alignment=Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter
    else:
        side=24; block_h=side+6+title_h+2+state_h; top=(widget.height()-block_h)/2
        if hasattr(widget,'paint_icon'): widget.paint_icon(painter,kind,round((widget.width()-side)/2),round(top),side,ink.name())
        else: control_icon(kind,color=ink.name()).paint(painter,round((widget.width()-side)/2),round(top),side,side)
        rects=[QRectF(5,top+side+6,widget.width()-10,title_h),QRectF(5,top+side+6+title_h+2,widget.width()-10,state_h)]
        alignment=Qt.AlignmentFlag.AlignCenter
    for text,font,color,rect in zip((title,subtitle),(title_font,state_font),(ink,muted),rects):
        painter.setFont(font); painter.setPen(color)
        painter.drawText(rect,alignment,painter.fontMetrics().elidedText(tr(text),Qt.TextElideMode.ElideRight,max(0,round(rect.width()))))
    if badge:
        if badge == 'locked':
            control_icon('lock',color=muted.name()).paint(painter,widget.width()-22,5,16,16); return
        font=QFont(widget.font()); font.setPixelSize(11); painter.setFont(font); painter.setPen(muted)
        painter.drawText(QRectF(widget.width()-24,4,20,16),Qt.AlignmentFlag.AlignCenter,badge)

class QuickTile(StateButton):
    def __init__(self,*args):
        super().__init__(*args); self.setMinimumHeight(66); self.core=False; self.editing=False; self.display_state=None
        self.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        self.setProperty('dashboard',True)

    def sizeHint(self): return QSize(104,96)
    def minimumSizeHint(self): return QSize(0,66)

    def focusInEvent(self,event):
        self.navigation_focus=event.reason() in (Qt.FocusReason.TabFocusReason,Qt.FocusReason.BacktabFocusReason,Qt.FocusReason.ShortcutFocusReason,Qt.FocusReason.OtherFocusReason)
        super().focusInEvent(event); self.update()

    def mousePressEvent(self,event):
        self.navigation_focus=False
        super().mousePressEvent(event); self.update()

    def presentation(self):
        option = next((value for value in self.options if value[0] == self.current),None)
        subtitle = option[1] if option else self.text()
        if isinstance(self.current,bool) and self.title not in ('Fan linkage','Fan mode'): subtitle = 'On' if self.current else 'Off'
        if self.display_state is not None: subtitle=self.display_state
        active=(isinstance(self.current,bool) and self.current and self.title not in ('Fan linkage','Fan mode')) or (self.title == 'Lighting' and self.current not in (None,'off','disabled',''))
        return subtitle,option[2] if option else 'gauge',active

    def set_display_state(self,value): self.display_state=value; self.update()

    def cycle(self):
        if not self.editing: super().cycle()

    def open_options(self):
        if not self.editing: super().open_options()

    def paintEvent(self,event):
        subtitle,kind,active=self.presentation()
        title='Focus' if self.title == 'Gamepad focus' else self.title
        paint_quick_tile(self,QPainter(self),title,subtitle,kind,active,'',self.core)

class ScreenshotTile(QuickTile):
    def __init__(self,options,callback,capture):
        super().__init__('Screenshot',options,callback); self.capture=capture

    def cycle(self):
        if not self.editing and not self.held: self.capture()
