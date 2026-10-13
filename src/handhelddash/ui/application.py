# SPDX-License-Identifier: LGPL-3.0-or-later
from handhelddash.ui.common import APP, QApplication, QDBusConnection, QDBusInterface, Qt, os, sys
from handhelddash.ui.panel import Panel
from handhelddash.ui.widgets.icons import ControlStyle

def main():
    if '--run' in sys.argv:
        args = sys.argv[sys.argv.index('--run')+1:]
        if not args: raise SystemExit('Usage: aynthor-control --run PROGRAM [ARGS]')
        env = os.environ.copy()
        os.execvpe('mangohud',['mangohud',*args],env)
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_CompressHighFrequencyEvents,False)
    app = QApplication(sys.argv); app.setStyle(ControlStyle(app.style().objectName())); app.setQuitOnLastWindowClosed(False); app.setDesktopFileName('org.aynthor.Control')
    bus = QDBusConnection.sessionBus()
    if bus.interface().isServiceRegistered(APP).value():
        if '--background' in sys.argv: return
        interface = QDBusInterface(APP,'/Control',APP,bus)
        if '--snapshot' in sys.argv: interface.call('Snapshot',sys.argv[sys.argv.index('--snapshot')+1])
        else: interface.call('Customize' if '--customize' in sys.argv else 'Settings' if '--settings' in sys.argv else 'Toggle')
        return
    panel = Panel()
    if '--customize' in sys.argv: panel.Settings(); panel.open_dashboard_editor()
    elif '--settings' in sys.argv: panel.Settings()
    elif '--background' not in sys.argv: panel.Toggle()
    sys.exit(app.exec())
