# SPDX-License-Identifier: LGPL-3.0-or-later
from handhelddash.services.hardware import Hardware
from handhelddash.services.runtime import DBusGMainLoop, GLib, dbus, logging, os

def main():
    logging.basicConfig(level=logging.DEBUG if os.environ.get('HANDHELDDASH_TOUCH_TRACE') == '1' else logging.INFO)
    DBusGMainLoop(set_as_default=True)
    hardware = Hardware(dbus.SystemBus())
    GLib.MainLoop().run()
