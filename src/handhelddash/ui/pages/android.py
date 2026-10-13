# SPDX-License-Identifier: LGPL-3.0-or-later
from handhelddash.ui.common import json, tr

class AndroidPageMixin:
    def refresh_android(self):
        def update(raw):
            selected=self.android_combo.currentData(); self.android_parts=sorted(json.loads(raw),key=lambda p:p['label']!='userdata'); self.android_combo.blockSignals(True); self.android_combo.clear()
            for p in self.android_parts: self.android_combo.addItem(p['label'],p['label'])
            index=max(0,self.android_combo.findData(selected)); self.android_combo.setCurrentIndex(index); self.android_combo.blockSignals(False); self.describe_android(index)
        self.call('AndroidPartitions',[],update)

    def describe_android(self,index):
        if not self.android_parts: self.android_label.setText('No Android partitions found'); return
        if not 0 <= index < len(self.android_parts): return
        p=self.android_parts[index]
        self.android_mount.setText(tr('Mount read/write' if p['label'] == 'userdata' else 'Mount read-only'))
        self.android_mount.setEnabled(p['mountable'] and not p.get('busy') and not p.get('mounted'))
        if p['label'] == 'userdata':
            state = tr('Mounted' if p.get('mounted') else 'Not mounted')
            backend = tr('Unlock backend ready' if p.get('backend_ready') else 'Matching kernel, original keys and unlock backend required')
            self.android_label.setText('/sdcard → /mnt/android-data/media/0\n'+state+' · '+p.get('service_state','')+'\n'+backend+('\n'+p['error'] if p.get('error') else ''))
            return
        self.android_label.setText(f"{index+1} / {len(self.android_parts)} · {p.get('filesystem') or 'super logical partition'}\n"+(p['reason'] or 'Read-only mounting available'))

    def android_action(self,operation):
        label = self.android_combo.currentData()
        if label:
            if label == 'userdata': operation='mount-userdata' if operation == 'mount-android' else 'unmount-userdata'
            self.set(operation,[label])
        else: self.refresh_android()

    def open_android(self):
        if self.android_combo.currentData() == 'userdata':
            part=next((p for p in self.android_parts if p['label'] == 'userdata'),{})
            if not part.get('mounted'): self.notify(tr('Not mounted')); return
            self.call('Set',['userdata-share',['userdata']],lambda _:self.start('xdg-open','/mnt/aynthor-android/userdata'))
        else:
            self.start('xdg-open','/mnt/aynthor-android/'+str(self.android_combo.currentData() or ''))

