"""Driver-specific monitoring services."""
import os
import time
from pathlib import Path


class GPUUtilization:
    def __init__(self, sampler: str):
        self.sampler=sampler; self.reset()

    def reset(self):
        self.previous={}; self.sample_time=0; self.value=None

    def read(self, enabled: bool):
        if not enabled or self.sampler!='msm-drm':
            self.reset(); return None
        now=time.monotonic()
        if now-self.sample_time<1: return self.value
        clients={}
        for fd in Path('/proc').glob('[0-9]*/fd/*'):
            try:
                if not os.readlink(fd).startswith('/dev/dri/'): continue
                fields=dict(line.split(':',1) for line in (fd.parent.parent/'fdinfo'/fd.name).read_text().splitlines() if ':' in line)
                if fields.get('drm-driver','').strip()!='msm' or 'drm-engine-gpu' not in fields: continue
                client=fields['drm-client-id'].strip(); busy=int(fields['drm-engine-gpu'].split()[0])
                clients[client]=max(clients.get(client,0),busy)
            except (OSError,ValueError,KeyError): continue
        elapsed=now-self.sample_time
        delta=sum(max(0,value-self.previous[key]) for key,value in clients.items() if key in self.previous)
        self.value=max(0,min(100,100*delta/(elapsed*1e9))) if self.sample_time and clients else None
        self.previous=clients; self.sample_time=now
        return self.value
