# SPDX-License-Identifier: LGPL-3.0-or-later
from PyQt6.QtCore import QMetaType, QTimer, QVariant
from PyQt6.QtDBus import QDBusInterface
from PyQt6.QtDBus import QDBusMessage
from PyQt6.QtDBus import QDBusVariant
from handhelddash.desktop.base import DesktopAdapter
import configparser
from handhelddash.desktop.scripts import KWinScripts
from handhelddash.desktop.focus_rules import update_focus_rules
import math
import shutil

class KWinAdapter(DesktopAdapter):
    name = 'kwin'
    capabilities = frozenset(('placement','window_focus','pointer_configuration','shortcuts','panel_focus','window_list','screenshot'))

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        capabilities=set(type(self).capabilities)
        if not shutil.which('spectacle'): capabilities.discard('screenshot')
        self.capabilities=frozenset(capabilities)
        self.scripts=KWinScripts(self.session,self.notify,self)

    def install_placement(self, prefs, displays):
        return self.scripts.start('aynthor-placement', {'operation':'placement', 'rules':prefs.get('app_screens',{}), 'defaultScreen':prefs.get('launch_screen',''), 'gamepadFocus':prefs.get('gamepad_focus','auto'), 'displays':displays,
            'preventMinimize':bool(prefs.get('prevent_minimize',False)),
            'protectedOutput':displays.get(prefs.get('gamepad_focus') if prefs.get('gamepad_focus') in ('top','bottom') else 'top','')})

    def protect_windows(self,targets):
        update_focus_rules(self.config,self.session,targets)

    def focus_touchpad(self, output, active):
        return bool(output and active() and self.scripts.start('aynthor-touchpad-focus', {'operation':'touchpad','output':output}))

    def configure_pointer(self, output, source_name, prefs, save):
        manager=QDBusInterface('org.kde.KWin','/org/kde/KWin/InputDevice','org.kde.KWin.InputDeviceManager',self.session); manager.setTimeout(1000)
        reply=manager.call('ListPointers')
        if reply.type()==QDBusMessage.MessageType.ErrorMessage: return None
        names=list(reply.arguments()[0]); touches=manager.call('ListTouch')
        if touches.type()!=QDBusMessage.MessageType.ErrorMessage: names+=list(touches.arguments()[0])
        devices={}
        for name in dict.fromkeys(names):
            device=QDBusInterface('org.kde.KWin','/org/kde/KWin/InputDevice/'+name,'org.freedesktop.DBus.Properties',self.session); device.setTimeout(1000)
            result=device.call('Get','org.kde.KWin.InputDevice','name')
            if result.type()!=QDBusMessage.MessageType.ErrorMessage: devices[result.arguments()[0]]=device
        matrix=None; calibration=None; source=devices.get(source_name)
        if source:
            result=source.call('Get','org.kde.KWin.InputDevice','calibrationMatrix')
            if result.type()!=QDBusMessage.MessageType.ErrorMessage:
                matrix=result.arguments()[0]
                try:
                    values=[float(v) for v in matrix.split(',')]
                    if len(values)==16 and all(math.isfinite(v) and abs(v)<=4 for v in values): calibration=[values[i] for i in (0,1,2,4,5,6)]
                    else: matrix=None
                except (ValueError,AttributeError): matrix=None
        for name,device in devices.items():
            if name=='HandheldDash Pointer Placement':
                device.call('Set','org.kde.KWin.InputDevice','pointerAccelerationProfileFlat',QDBusVariant(True))
                device.call('Set','org.kde.KWin.InputDevice','pointerAcceleration',QDBusVariant(0.0))
            elif name=='HandheldDash Touchscreen Relay' and output:
                device.call('Set','org.kde.KWin.InputDevice','outputName',QDBusVariant(output))
                if matrix is not None: device.call('Set','org.kde.KWin.InputDevice','calibrationMatrix',QDBusVariant(matrix))
            elif name=='HandheldDash Virtual Touchpad' and not prefs.get('touchpad_raw_initialized'):
                result=device.call('Set','org.kde.KWin.InputDevice','tapToClick',QDBusVariant(True))
                device.call('Set','org.kde.KWin.InputDevice','tapAndDrag',QDBusVariant(False))
                device.call('Set','org.kde.KWin.InputDevice','tapDragLock',QDBusVariant(False))
                if result.type()!=QDBusMessage.MessageType.ErrorMessage: save('touchpad_raw_initialized',True)
        return calibration

    def configure_panel_focus(self):
        file=self.config.parent/'kwinrulesrc'; rules=configparser.ConfigParser(interpolation=None,strict=False); rules.optionxform=str
        if file.exists(): rules.read(file,encoding='utf-8')
        if not rules.has_section('General'): rules.add_section('General')
        ids=[value for value in rules.get('General','rules',fallback='').split(',') if value]; rule='handhelddash-panel'
        if rule not in ids: ids.append(rule)
        rules['General']['rules']=','.join(ids); rules['General']['count']=str(len(ids))
        rules[rule]={'Description':'HandheldDash panel activation','wmclass':'org.aynthor.Control','wmclassmatch':'1','title':'HandheldDash','titlematch':'1','acceptfocus':'true','acceptfocusrule':'2'}
        file.parent.mkdir(parents=True,exist_ok=True); stage=file.with_suffix('.handhelddash-new')
        with stage.open('w',encoding='utf-8') as stream: rules.write(stream,space_around_delimiters=False)
        stage.replace(file); QDBusInterface('org.kde.KWin','/KWin','org.kde.KWin',self.session).asyncCall('reconfigure')
        return True

    def show_panel(self):
        # A stale task-hover preview can hide even the active, keep-above panel.
        # Clear the preview without disabling or reloading the desktop effect.
        message=QDBusMessage.createMethodCall('org.kde.KWin','/org/kde/KWin/HighlightWindow',
                                              'org.kde.KWin.HighlightWindow','highlightWindows')
        windows=QVariant([]); windows.convert(QMetaType(QMetaType.Type.QStringList.value))
        message.setArguments([windows]); self.session.asyncCall(message,1000)
        return self.scripts.start('panel-visibility', {'operation':'panel-show'})

    def hide_panel(self):
        return self.scripts.start('panel-visibility', {'operation':'panel-hide'})

    def shortcut(self, name):
        QDBusInterface('org.kde.kglobalaccel','/component/kwin','org.kde.kglobalaccel.Component',self.session).asyncCall('invokeShortcut',name)

    def list_windows(self):
        return self.scripts.start('aynthor-tasks', {'operation':'list'})

    def move_window(self, identity, output):
        return self.scripts.start('aynthor-move', {'operation':'move','identity':identity,'output':output})

    def activate_window(self, identity):
        return self.scripts.start('aynthor-activate', {'operation':'activate','identity':identity})

    def stop_touchpad(self):
        self.scripts.stop('aynthor-touchpad-focus')

    def swap_active(self):
        return self.scripts.start('handhelddash-swap', {'operation':'swap'})

    def capture(self,process,mode,target):
        options=['--region'] if mode=='region' else ['--fullscreen','--scaled']
        QTimer.singleShot(300,lambda:process.start('spectacle',['--new-instance','--background',*options,'--output',str(target)]))
        return True
