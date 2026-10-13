# SPDX-License-Identifier: LGPL-3.0-or-later
from PyQt6.QtCore import QObject
from pathlib import Path

class DesktopAdapter(QObject):
    name = 'generic'
    capabilities = frozenset()

    def __init__(self, session, config: Path, run, notify, parent=None):
        super().__init__(parent)
        self.session=session; self.config=config; self.run=run; self.notify=notify

    def supports(self, feature: str) -> bool:
        return feature in self.capabilities

    def install_placement(self, prefs: dict, displays: dict):
        return False

    def focus_touchpad(self, output: str, active):
        return False

    def configure_pointer(self, output: str, source_name: str, prefs: dict, save):
        return None

    def configure_panel_focus(self):
        return False

    def shortcut(self, name: str):
        self.notify('Desktop action is not supported by '+self.name)

    def plasma_docked(self):
        return False

    def list_windows(self):
        return False

    def move_window(self, identity: str, output: str):
        return False

    def activate_window(self, identity: str):
        return False

    def stop_touchpad(self):
        return False

    def swap_active(self):
        self.notify('Window movement is not supported by '+self.name)

    def capture(self,process,mode,target):
        return False
