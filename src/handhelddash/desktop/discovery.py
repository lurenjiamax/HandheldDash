# SPDX-License-Identifier: LGPL-3.0-or-later
from handhelddash.desktop.base import DesktopAdapter
from handhelddash.desktop.kwin import KWinAdapter
from handhelddash.desktop.kde import KDEAdapter
from pathlib import Path

def detect_desktop(session, config: Path, run, notify, parent=None):
    interface=session.interface()
    kwin=bool(interface and interface.isServiceRegistered('org.kde.KWin').value())
    plasma=bool(interface and interface.isServiceRegistered('org.kde.plasmashell').value())
    adapter=KDEAdapter if kwin or plasma else DesktopAdapter
    return adapter(session,config,run,notify,parent)
