"""Intercept bare-desktop touches without taking keyboard focus."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QWidget


class DesktopTouchGuard(QWidget):
    def __init__(self):
        super().__init__(None,Qt.WindowType.Tool|Qt.WindowType.FramelessWindowHint|
                         Qt.WindowType.WindowDoesNotAcceptFocus|Qt.WindowType.WindowStaysOnBottomHint)
        self.setWindowTitle('HandheldDash Desktop Touch Guard')
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        QApplication.instance().aboutToQuit.connect(self.close)

    def follow(self,output: str) -> None:
        if not output:
            self.hide(); return
        screen=next((s for s in QApplication.screens() if s.name()==output),None)
        if screen is None:
            self.hide(); return
        self.winId(); self.windowHandle().setScreen(screen)
        self.setGeometry(screen.geometry()); self.showFullScreen()
