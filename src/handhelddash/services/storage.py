# SPDX-License-Identifier: LGPL-3.0-or-later
from handhelddash.services.runtime import LpUnpack, NAME, Path, STATE, dbus, json, logging, os, re, run, subprocess, threading, time

class StorageService(dbus.service.Object):
    def logical_partitions(self, super_device):
        reader = LpUnpack(SUPER_IMAGE=super_device)
        try:
            # ponytail: pinned lpunpack has no public metadata API; review this call when updating it.
            metadata = reader._read_metadata()
        finally:
            reader._fd.close()
        limit = int(run('blockdev', '--getsz', super_device))
        result = []
        for p in metadata.partitions:
            if not re.fullmatch(r'(system|system_ext|system_dlkm|vendor|vendor_dlkm|product|odm)(_[ab])?', p.name) or not p.num_extents:
                continue
            table, start = [], 0
            for extent in metadata.extents[p.first_extent_index:p.first_extent_index+p.num_extents]:
                if extent.target_source != 0 or extent.target_type not in (0,1) or extent.num_sectors <= 0:
                    raise ValueError('Unsupported Android super extent')
                if extent.target_type == 0:
                    if extent.target_data + extent.num_sectors > limit:
                        raise ValueError('Android extent exceeds super partition')
                    table.append(f'{start} {extent.num_sectors} linear {super_device} {extent.target_data}')
                else:
                    table.append(f'{start} {extent.num_sectors} zero')
                start += extent.num_sectors
            mapper = '/dev/mapper/aynthor-android-' + p.name
            result.append({'label':p.name,'device':mapper,'filesystem':None,'mountable':True,'mountpoints':[], 'reason':'Android super logical partition; read-only access', 'super_device':super_device,'table':'\n'.join(table),'size':start*512})
        return result

    def userdata_view(self, uid):
        source=Path('/mnt/android-data/media/0'); target=Path('/mnt/aynthor-android/userdata')
        mount=subprocess.run(['findmnt','-rn','-M',str(target),'-o','FSTYPE'],capture_output=True,text=True)
        if mount.returncode == 0:
            if mount.stdout.strip() != 'fuse.bindfs': raise ValueError('Shared mountpoint is already in use')
            return
        if not source.is_dir(): raise ValueError('Android shared storage is not available')
        target.mkdir(parents=True,exist_ok=True)
        owner=source.stat()
        # Keep FUSE outside hardwared's cgroup: restarting the control service
        # must not kill an otherwise healthy Android storage view.
        run('systemd-run','--unit=aynthor-userdata-share','--collect',
            '--property=Type=exec','--property=Restart=on-failure',
            '/usr/bin/bindfs','-f','--mirror-only='+str(uid),'--perms=u+rwX',
            '--create-for-user='+str(owner.st_uid),'--create-for-group='+str(owner.st_gid),
            '--chown-ignore','--chgrp-ignore','--chmod-ignore','--xattr-ro',
            '-o','nosuid,nodev,noexec',str(source),str(target))
        for _ in range(30):
            view=subprocess.run(['findmnt','-rn','-M',str(target),'-o','FSTYPE'],capture_output=True,text=True)
            if view.returncode == 0 and view.stdout.strip() == 'fuse.bindfs': return
            time.sleep(0.1)
        raise ValueError('Android shared storage service did not establish its mount')

    def userdata_status(self, device):
        base = STATE.parent/'android'
        helper = Path('/usr/lib/aynthor/userdata-mount')
        release = os.uname().release
        ready = (helper.is_file() and Path('/usr/bin/modinfo').is_file()
                 and (base/'keymint-private/metadata.keyblob').is_file()
                 and all((base/'keymint-runtime'/name).is_file() for name in ('bin/linker64','bin/native-convert','lib64/conversion-compat.so','lib64/libaynthor-mink-bridge.so'))
                 and all(Path('/sys/module',name).is_dir() or (base/'tme-modules'/release/(name+'.ko')).is_file()
                         or subprocess.run(['modinfo','-n',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode == 0
                         for name in ('aynthor_qmp','tme_overlay_loader','aynthor_tme')))
        state = run('systemctl','show','aynthor-userdata-mount.service','-p','ActiveState','--value')
        mount = subprocess.run(['findmnt','-rn','-M','/mnt/android-data','-o','FSTYPE'],capture_output=True,text=True)
        return {'backend_ready':ready, 'service_state':state, 'mounted':mount.returncode == 0,
                'mountpoint':'/mnt/android-data', 'busy':self.android_lock.locked(),
                'error':self.android_error, 'mountable':ready}

    def userdata_action(self, operation, part, uid):
        if not self.android_lock.acquire(blocking=False):
            raise ValueError('Android mount operation is already running')
        self.android_error = ''
        def execute():
            try:
                device = part['device']
                status = self.userdata_status(device)
                if operation == 'mount-userdata':
                    if status['mounted'] or status['service_state'] in ('active','activating','deactivating'):
                        raise ValueError('Android userdata is already mounted or changing state')
                    if not status['backend_ready']:
                        raise ValueError('Matching kernel, private keys and userdata backend are required')
                    if subprocess.run(['pgrep','-x','fsck.f2fs'],stdout=subprocess.DEVNULL).returncode == 0:
                        raise ValueError('A filesystem check is running; cannot mount userdata')
                    run('blockdev','--setrw',device)
                    run('systemd-run','--unit=aynthor-userdata-mount','--collect',
                        '--property=TimeoutStopSec=90','--property=LimitCORE=0',
                        '/bin/bash','/usr/lib/aynthor/userdata-mount','--mount-user0-rw')
                    for _ in range(80):
                        if self.userdata_status(device)['mounted']: break
                        time.sleep(.5)
                    else:
                        details = run('journalctl','-u','aynthor-userdata-mount.service','-n','8','--no-pager','-o','cat')
                        raise ValueError('Userdata mount is not ready: '+details)
                    self.userdata_view(uid)
                else:
                    view=subprocess.run(['findmnt','-rn','-M','/mnt/aynthor-android/userdata','-o','FSTYPE'],capture_output=True,text=True)
                    if view.returncode == 0:
                        if view.stdout.strip() != 'fuse.bindfs': raise ValueError('Shared mountpoint is not owned by bindfs')
                        run('umount','/mnt/aynthor-android/userdata')
                    if subprocess.run(['systemctl','is-active','--quiet','aynthor-userdata-share.service']).returncode == 0:
                        run('systemctl','stop','aynthor-userdata-share.service')
                    if status['service_state'] != 'inactive':
                        run('systemctl','stop','aynthor-userdata-mount.service',timeout=95)
                    if self.userdata_status(device)['mounted']:
                        raise ValueError('Android userdata is still mounted; close applications using it')
                    if run('dmsetup','ls','--target','default-key') != 'No devices found':
                        raise ValueError('A default-key mapper remains; inspect cleanup before switching systems')
                    run('blockdev','--setro',device)
                    run('sync',timeout=60)
            except Exception as e:
                self.android_error = str(e)
                logging.warning('Android userdata operation failed: %s',e)
            finally:
                self.android_lock.release()
        threading.Thread(target=execute,daemon=True).start()

    def android(self):
        blocks = json.loads(run('lsblk','-J','-p','-o','NAME,FSTYPE,PARTLABEL,MOUNTPOINTS'))
        found = []
        for disk in blocks['blockdevices']:
            children = disk.get('children', [])
            if not any(p.get('partlabel') in ('super','userdata') for p in children):
                continue
            for item in children:
                label = item.get('partlabel')
                if label == 'super':
                    try:
                        found.extend(self.logical_partitions(item['name']))
                    except Exception as e:
                        found.append({'label':'super','device':item['name'],'filesystem':None,'mountable':False,'mountpoints':[], 'reason':'Super metadata unreadable: '+str(e)})
                elif label in ('userdata','system','vendor','product','system_a','system_b','vendor_a','vendor_b','product_a','product_b'):
                    fs=item.get('fstype')
                    found.append({'label':label,'device':item['name'],'filesystem':fs,'mountable':fs in ('ext4','f2fs','erofs'),'mountpoints':item.get('mountpoints'), 'reason':'' if fs in ('ext4','f2fs','erofs') else 'No readable filesystem; Android metadata encryption requires unlocked data exported from Android'})
        for part in found:
            if part['label'] == 'userdata':
                part.update(self.userdata_status(part['device']))
        return found

    @dbus.service.method(NAME, in_signature='', out_signature='s')
    def AndroidPartitions(self):
        return json.dumps(self.android())

