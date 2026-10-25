# SPDX-License-Identifier: LGPL-3.0-or-later
from handhelddash.ui.common import APP, QApplication, QDBusAbstractAdaptor, QPointF, json, pyqtClassInfo, pyqtSlot

@pyqtClassInfo('D-Bus Interface', APP)
class ControlEndpoint(QDBusAbstractAdaptor):
    @pyqtSlot(str)
    def FocusTargets(self,raw):
        kwin=getattr(self.parent().desktop,'kwin',None)
        if not kwin: return
        try: targets=json.loads(raw)
        except ValueError: return
        if isinstance(targets,list) and all(isinstance(item,dict) for item in targets):
            kwin.protect_windows(targets if self.parent().prefs.get('prevent_minimize',False) else [])
    @pyqtSlot()
    def DesktopScriptReady(self):
        kwin = getattr(self.parent().desktop, 'kwin', None)
        if kwin: kwin.scripts.started()

    @pyqtSlot(result=str)
    def DesktopNextCommand(self):
        kwin = getattr(self.parent().desktop, 'kwin', None)
        return kwin.scripts.command() if kwin else '{}'

    @pyqtSlot(str)
    def DesktopCommandDone(self, serial):
        kwin = getattr(self.parent().desktop, 'kwin', None)
        if kwin: kwin.scripts.completed(int(serial))

    @pyqtSlot(str,result=str)
    def DesktopScriptParameters(self, operation):
        kwin = getattr(self.parent().desktop, 'kwin', None)
        if kwin:
            for parameters in kwin.scripts.parameters.values():
                if parameters.get('operation') == operation:
                    return json.dumps(parameters)
        return '{}'

    @pyqtSlot()
    def Screenshot(self): self.parent().screenshot()

    def configure_panel_focus(self):
        self.parent().desktop.configure_panel_focus()

    @pyqtSlot()
    def Toggle(self): self.parent().Toggle()

    @pyqtSlot()
    def Settings(self): self.parent().Settings()

    @pyqtSlot()
    def Customize(self):
        self.parent().Settings(); self.parent().open_dashboard_editor()

    @pyqtSlot()
    def ExitTouchpad(self): self.parent().exit_touchpad()

    @pyqtSlot(str,result=bool)
    def Snapshot(self,path): return self.parent().Snapshot(path)

    @pyqtSlot(str,result=bool)
    def SnapshotEnglish(self,path): return self.parent().snapshot_english(path)

    @pyqtSlot(str)
    def Adjustment(self,key):
        if key == 'focus': self.parent().open_window_focus()
        elif key in ('brightness','volume'): self.parent().open_adjustment(key)

    @pyqtSlot(str,result=bool)
    def PopupSnapshot(self,path):
        popup=QApplication.activePopupWidget()
        if popup is None: popup=next((dialog for dialog in self.parent().adjustment_dialogs.values() if dialog.isVisible()),None)
        return bool(popup and popup.grab().save(path))

    @pyqtSlot(str)
    def WindowList(self,raw): self.parent().WindowList(raw)

    @pyqtSlot(str)
    def CursorPosition(self,raw):
        try: x,y = json.loads(raw)
        except (ValueError,TypeError): return
        if not isinstance(x,(int,float)) or not isinstance(y,(int,float)): return
        self.parent().cursor_position = QPointF(x,y)
