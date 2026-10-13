# SPDX-License-Identifier: LGPL-3.0-or-later
from PyQt6.QtCore import QSettings
from PyQt6.QtDBus import QDBusInterface
from PyQt6.QtDBus import QDBusMessage
from PyQt6.QtDBus import QDBusPendingCallWatcher
from PyQt6.QtDBus import QDBusPendingReply
from handhelddash.desktop.base import DesktopAdapter
from handhelddash.desktop.scripts import script_path
import shutil
import json

class PlasmaComponent(DesktopAdapter):
    capabilities = frozenset(('plasma_panel','plasma_docked'))

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        if not shutil.which('kwriteconfig6'): self.capabilities=frozenset(('plasma_panel',))

    @staticmethod
    def target(rect):
        return {'x':rect.x(),'y':rect.y(),'width':rect.width(),'height':rect.height()}

    def panel_script(self, parameters):
        # Plasma exposes only evaluateScript; serialize a single data argument.
        return script_path('plasma.js').read_text()+'\nhandhelddashPanel('+json.dumps(parameters)+');'

    def evaluate(self,script,callback=None,failed=None):
        interface=QDBusInterface('org.kde.plasmashell','/PlasmaShell','org.kde.PlasmaShell',self.session)
        watcher=QDBusPendingCallWatcher(interface.asyncCall('evaluateScript',script),self)
        def done(w):
            reply=QDBusPendingReply(w).reply()
            if reply.type()==QDBusMessage.MessageType.ErrorMessage:
                self.notify('Error: '+reply.errorMessage())
                if failed: failed()
            elif callback and reply.arguments(): callback(str(reply.arguments()[0]).strip())
            w.deleteLater()
        watcher.finished.connect(done)

    def plasma_panels(self,rect,callback,failed):
        self.evaluate(self.panel_script({'operation':'list','target':self.target(rect)}),callback,failed)

    def set_plasma_panel(self,rect,visible,geometry,callback,failed):
        self.evaluate(self.panel_script({'operation':'set','target':self.target(rect),'visible':bool(visible),'location':geometry.get('location','top'),'height':int(geometry.get('height',30))}),callback,failed)

    def plasma_docked(self):
        settings=QSettings(str(self.config.parent/'plasmamobilerc'),QSettings.Format.IniFormat)
        return settings.value('General/convergenceModeEnabled',False,type=bool)

    def set_plasma_docked(self,enabled):
        self.run('kwriteconfig6','--file','plasmamobilerc','--group','General','--key','convergenceModeEnabled','--type','bool','--notify','true' if enabled else 'false')
