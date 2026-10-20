# SPDX-License-Identifier: LGPL-3.0-or-later
from handhelddash.services.runtime import NAME, Path, dbus, os, signal, time

class SessionService(dbus.service.Object):
    def invalidate_sessions(self,*args):
        self.session_cache = None

    def sender_uid(self,sender):
        if sender not in self.sender_uids:
            self.sender_uids[sender] = int(self.bus.get_unix_user(sender))
        return self.sender_uids[sender]

    def sessions(self):
        now = time.monotonic()
        if self.session_cache is not None and now-self.session_cache_time < 1: return self.session_cache
        obj = self.bus.get_object('org.freedesktop.login1', '/org/freedesktop/login1')
        result = []
        for _, uid, _, seat, path in obj.ListSessions(dbus_interface='org.freedesktop.login1.Manager'):
            if seat:
                p = self.bus.get_object('org.freedesktop.login1', path)
                props = p.GetAll('org.freedesktop.login1.Session', dbus_interface='org.freedesktop.DBus.Properties')
                if props['Active'] and not props['Remote']:
                    result.append(int(uid))
        self.session_cache = result; self.session_cache_time = now
        return result

    def authorize(self, sender):
        uid = self.sender_uid(sender)
        if uid != 0 and uid not in self.sessions():
            raise dbus.exceptions.DBusException('An active local session is required', name=NAME + '.AccessDenied')
        return uid

    def kill_task(self,pid,started,uid):
        if pid <= 1 or pid == os.getpid(): raise ValueError('Invalid task')
        handle = os.pidfd_open(pid)
        try:
            process = Path('/proc')/str(pid)
            if process.joinpath('stat').read_text().rsplit(')',1)[1].split()[19] != started:
                raise ValueError('Task has already exited')
            owner = process.stat().st_uid
            if owner != uid:
                environment = process.joinpath('environ').read_bytes().split(b'\0')
                if owner != 0 or f'user-{uid}.slice' not in process.joinpath('cgroup').read_text() or not any(item.startswith((b'DISPLAY=',b'WAYLAND_DISPLAY=')) for item in environment):
                    raise ValueError('Task is outside your graphical session')
            signal.pidfd_send_signal(handle,signal.SIGKILL)
        finally:
            os.close(handle)

    def set_task_affinity(self,pid,started,cpu_list,uid):
        if pid <= 1 or pid == os.getpid(): raise ValueError('Invalid task')
        cpus = set()
        for part in cpu_list.split(','):
            bounds = part.strip().split('-')
            if len(bounds) not in (1,2): raise ValueError('Invalid CPU list')
            first,last = int(bounds[0]),int(bounds[-1])
            if first < 0 or last < first or last > 4095: raise ValueError('Invalid CPU range')
            cpus.update(range(first,last+1))
        online = {int(p.name[3:]) for p in Path('/sys/devices/system/cpu').glob('cpu[0-9]*')
                  if not (p/'online').exists() or (p/'online').read_text().strip() == '1'}
        if not cpus or not cpus <= online: raise ValueError('Select online CPUs only')
        handle = os.pidfd_open(pid)
        previous = {}
        try:
            process = Path('/proc')/str(pid)
            if process.stat().st_uid != uid: raise ValueError('Task is outside your user session')
            if process.joinpath('stat').read_text().rsplit(')',1)[1].split()[19] != started:
                raise ValueError('Task has already exited')
            for thread in process.joinpath('task').iterdir():
                tid = int(thread.name)
                try:
                    previous[tid] = os.sched_getaffinity(tid)
                    os.sched_setaffinity(tid,cpus)
                    if os.sched_getaffinity(tid) != cpus: raise ValueError('CPU selection restricted by process cgroup')
                except ProcessLookupError:
                    continue
        except Exception:
            for tid,mask in previous.items():
                try: os.sched_setaffinity(tid,mask)
                except OSError: pass
            raise
        finally:
            os.close(handle)
