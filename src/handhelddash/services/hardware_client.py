"""Asynchronous transport; presentation and state policy stay with callers."""
from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtDBus import QDBusMessage, QDBusPendingCallWatcher, QDBusPendingReply
from handhelddash.protocol import HARDWARE_SERVICE


class HardwareClient(QObject):
    error = pyqtSignal(str)
    status = pyqtSignal(str)
    mutation = pyqtSignal(str,object,bool,bool)

    def __init__(self, interface, parent=None):
        super().__init__(parent); self.interface=interface; self.pending=set()
        self.queue={}; self.callbacks={}; self.active=None; self.revision=0
        self.timer=QTimer(self); self.timer.setSingleShot(True); self.timer.timeout.connect(self.flush)

    def set(self,operation,values,finished=None):
        key=('brightness',values[0]) if operation=='brightness' else ('lighting-color',values[0]) if operation=='lighting-color' else ('performance' if operation in ('performance','smart','governors') else 'rgb-mode' if operation in ('rgb-mode','rgb-state','lighting-mode') else operation)
        if operation=='brightness':
            if values[0]=='both':
                for target in ('top','bottom'): self.queue.pop(('brightness',target),None)
            elif ('brightness','both') in self.queue:
                _,both=self.queue.pop(('brightness','both')); other='bottom' if values[0]=='top' else 'top'
                self.queue[('brightness',other)]=('brightness',[other,both[1]])
        self.queue[key]=(operation,values); self.revision+=1
        if finished: self.callbacks[key]=finished
        self.timer.start(60)

    def flush(self):
        if self.active is not None or not self.queue: return
        key=next(iter(self.queue)); operation,values=self.queue.pop(key); callback=self.callbacks.pop(key,None)
        self.active=(key,operation,values)
        def completed(success,busy):
            self.active=None
            if busy and key not in self.queue:
                self.queue[key]=(operation,values)
                if callback: self.callbacks[key]=callback
            elif callback: callback(success,busy)
            self.revision+=1; self.mutation.emit(operation,values,success,busy)
            self.timer.start(100 if busy else 0)
        self.request('Set',[operation,values],self.status.emit,completed)

    def request(self, method, args, callback=None, finished=None):
        watcher=QDBusPendingCallWatcher(self.interface.asyncCall(method,*args),self); self.pending.add(watcher)
        def done(w):
            reply=QDBusPendingReply(w).reply(); self.pending.discard(w)
            success=reply.type()!=QDBusMessage.MessageType.ErrorMessage
            busy=not success and reply.errorName()==HARDWARE_SERVICE+'.Busy'
            if not success and not busy: self.error.emit('Error: '+reply.errorMessage())
            elif success and callback:
                try: callback(str(reply.arguments()[0]))
                except (ValueError,KeyError,IndexError) as exc:
                    self.error.emit('Invalid response: '+str(exc)); success=False
            if finished: finished(success,busy)
            w.deleteLater()
        watcher.finished.connect(done)
