"""Packaged scripts and ordered KWin D-Bus lifecycle."""
import json
from pathlib import Path
from PyQt6.QtCore import QObject, QSettings
from PyQt6.QtDBus import QDBusInterface, QDBusMessage


def script_path(name: str) -> Path:
    return Path(__file__).parent/'scripts'/name


class KWinScripts(QObject):
    def __init__(self, session, notify, parent=None):
        super().__init__(parent)
        self.session, self.notify = session, notify
        self.parameters = {}
        self.manager = QDBusInterface('org.kde.KWin', '/Scripting', 'org.kde.kwin.Scripting', session)
        self.manager.setTimeout(1500)

    def stop(self, name: str):
        self.manager.call('unloadScript', name)
        self.parameters.pop(name, None)

    def start(self, name: str, parameters: dict):
        self.stop(name)
        self.parameters[name] = parameters
        settings = QSettings(str(Path(self.parent().config).parent/'kwinrc'), QSettings.Format.IniFormat)
        settings.remove('Script-'+name+'/parameters')
        settings.setValue('Script-'+name+'/operation', parameters['operation'])
        settings.sync()
        QDBusInterface('org.kde.KWin', '/KWin', 'org.kde.KWin', self.session).call('reconfigure')
        reply = self.manager.call('loadScript', str(script_path('kwin.js')), name)
        if reply.type() == QDBusMessage.MessageType.ErrorMessage or not reply.arguments() or int(reply.arguments()[0]) < 0:
            self.notify('Cannot load KWin script: '+name)
            return False
        identity = int(reply.arguments()[0])
        script = QDBusInterface('org.kde.KWin', '/Scripting/Script'+str(identity), 'org.kde.kwin.Script', self.session)
        reply = script.call('run')
        if reply.type() == QDBusMessage.MessageType.ErrorMessage:
            self.notify(reply.errorMessage())
            return False
        return True

    def payload(self, name: str) -> str:
        return json.dumps(self.parameters.get(name, {}))
