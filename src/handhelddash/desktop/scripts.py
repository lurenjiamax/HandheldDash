"""Serialize KWin commands without routing them through global shortcuts."""
import json
from pathlib import Path
from PyQt6.QtCore import QObject, QTimer
from PyQt6.QtDBus import QDBusMessage, QDBusPendingCallWatcher, QDBusPendingReply


def script_path(name: str) -> Path:
    return Path(__file__).parent/'scripts'/name


class KWinScripts(QObject):
    name = 'handhelddash-runtime'
    legacy = ('aynthor-placement','aynthor-touchpad-focus','aynthor-tasks',
              'aynthor-move','aynthor-activate','handhelddash-swap')

    def __init__(self, session, notify, parent=None):
        super().__init__(parent)
        self.session, self.notify = session, notify
        self.parameters = {}; self.queue = {}; self.pending = set()
        self.ready = False; self.loading = False; self.active = None; self.serial = 0
        self.previous_window = ''; self.touchpad_active = False; self.panel_requested = False
        self.timeout = QTimer(self); self.timeout.setSingleShot(True)
        self.timeout.timeout.connect(self.failed)
        session.interface().serviceOwnerChanged.connect(self.owner_changed)

    def call(self, service, path, interface, method, args, callback):
        message = QDBusMessage.createMethodCall(service, path, interface, method)
        message.setArguments(args)
        watcher = QDBusPendingCallWatcher(self.session.asyncCall(message, 2000), self)
        self.pending.add(watcher)
        def done(w):
            reply = QDBusPendingReply(w).reply()
            self.pending.discard(w); w.deleteLater()
            if reply.type() == QDBusMessage.MessageType.ErrorMessage:
                self.failed(reply.errorMessage()); return
            callback(reply.arguments())
        watcher.finished.connect(done)

    def manager_call(self, method, args, callback):
        self.call('org.kde.KWin', '/Scripting', 'org.kde.kwin.Scripting', method, args, callback)

    def ensure_loaded(self):
        if self.loading or self.active is None: return
        self.loading = True
        names = iter((*self.legacy, self.name))
        def unload(_=None):
            name = next(names, None)
            if name is not None: self.manager_call('unloadScript', [name], unload)
            else: self.manager_call('loadScript', [str(script_path('kwin.js')), self.name], loaded)
        def loaded(args):
            if not args or int(args[0]) < 0:
                self.failed('Cannot load KWin runtime'); return
            self.call('org.kde.KWin', '/Scripting/Script'+str(int(args[0])),
                      'org.kde.kwin.Script', 'run', [], lambda _:None)
            self.timeout.start(4000)
        unload()

    def started(self):
        self.ready = True

    def failed(self, message='KWin command timed out'):
        self.timeout.stop(); self.loading = False; self.ready = False; self.active = None
        self.queue.clear()
        self.notify(str(message))

    def owner_changed(self, name, old, new):
        if name != 'org.kde.KWin': return
        self.timeout.stop(); self.ready = False; self.loading = False; self.active = None
        if new and self.parameters:
            for key, value in self.parameters.items(): self.queue[key] = value
            self.flush()

    def stop(self, name: str):
        self.manager_call('unloadScript', ['handhelddash-touchpad-escape'], lambda _:None)
        self.start(name, {'operation':'touchpad-stop'})

    def start(self, name: str, parameters: dict):
        if parameters['operation']=='touchpad':
            def loaded(args):
                if args and int(args[0])>=0:
                    self.call('org.kde.KWin','/Scripting/Script'+str(int(args[0])),
                              'org.kde.kwin.Script','run',[],lambda _:None)
            self.manager_call('unloadScript',['handhelddash-touchpad-escape'],
                lambda _:self.manager_call('loadScript',[str(script_path('touchpad.js')),'handhelddash-touchpad-escape'],loaded))
        self.parameters[name] = parameters
        self.queue[name] = parameters
        if parameters['operation'] in ('touchpad','touchpad-stop'):
            self.touchpad_active = parameters['operation'] == 'touchpad'
        if parameters['operation'] in ('panel-show','panel-hide'):
            self.panel_requested = parameters['operation'] == 'panel-show'
        self.flush()
        return True

    def flush(self):
        if self.loading or self.active is not None or not self.queue: return
        key = next(iter(self.queue)); parameters = self.queue.pop(key)
        placement = next((p for p in self.parameters.values() if p['operation']=='placement'), {})
        self.serial += 1
        self.active = dict(parameters, serial=self.serial, preferences=placement,
                           touchpadActive=self.touchpad_active, panelRequested=self.panel_requested,
                           previousWindow=self.previous_window)
        self.ensure_loaded()

    def command(self):
        return json.dumps(self.active or {})

    def completed(self, result):
        if self.active is None or self.active['serial'] != result.get('serial'): return
        self.previous_window = str(result.get('previousWindow') or '')
        self.timeout.stop(); self.loading = False; self.ready = True; self.active = None
        if result.get('error'): self.notify(str(result['error']))
        QTimer.singleShot(0, self.flush)
