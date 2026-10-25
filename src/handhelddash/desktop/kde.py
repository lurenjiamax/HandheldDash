"""KDE desktop facade composed from independently detected services."""
from .base import DesktopAdapter
from .kwin import KWinAdapter
from .plasma import PlasmaComponent


class KDEAdapter(DesktopAdapter):
    name = 'kde'

    def __init__(self, session, config, run, notify, parent=None):
        super().__init__(session, config, run, notify, parent)
        bus = session.interface()
        self.kwin = KWinAdapter(session, config, run, notify, self) if bus.isServiceRegistered('org.kde.KWin').value() else None
        self.plasma = PlasmaComponent(session, config, run, notify, self) if bus.isServiceRegistered('org.kde.plasmashell').value() else None
        self.capabilities = frozenset().union(*(c.capabilities for c in (self.kwin, self.plasma) if c))

    def _window(self, operation, *args):
        if self.kwin: return getattr(self.kwin, operation)(*args)
        return getattr(super(), operation)(*args)

    def install_placement(self, prefs, displays):
        return self._window('install_placement', prefs, displays)

    def show_panel(self): return self._window('show_panel')

    def hide_panel(self): return self._window('hide_panel')

    def focus_touchpad(self, output, active):
        return self._window('focus_touchpad', output, active)

    def configure_pointer(self, output, source_name, prefs, save):
        return self._window('configure_pointer', output, source_name, prefs, save)

    def configure_panel_focus(self,mode='auto'):
        return self._window('configure_panel_focus',mode)

    def shortcut(self, name):
        return self._window('shortcut', name)

    def list_windows(self):
        return self._window('list_windows')

    def move_window(self, identity, output):
        return self._window('move_window', identity, output)

    def activate_window(self, identity):
        return self._window('activate_window', identity)

    def stop_touchpad(self):
        return self._window('stop_touchpad')

    def swap_active(self):
        return self._window('swap_active')

    def capture(self, process, mode, target):
        return self._window('capture', process, mode, target)

    def plasma_panels(self, rect, callback, failed):
        if self.plasma: return self.plasma.plasma_panels(rect, callback, failed)
        failed()

    def set_plasma_panel(self, rect, visible, geometry, callback, failed):
        if self.plasma: return self.plasma.set_plasma_panel(rect, visible, geometry, callback, failed)
        failed()

    def plasma_docked(self):
        return bool(self.plasma and self.plasma.plasma_docked())

    def set_plasma_docked(self, enabled):
        if self.plasma and self.plasma.supports('plasma_docked'):
            return self.plasma.set_plasma_docked(enabled)
