#!/usr/bin/python
"""Generate a reproducible manifest from the actual packaged runtime files."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

p=argparse.ArgumentParser(); p.add_argument('root',type=Path); p.add_argument('source',type=Path); p.add_argument('version'); args=p.parse_args()
files=[args.root/'usr/bin/aynthor-control',args.root/'usr/bin/aynthor-hardwared',args.root/'usr/share/aynthor/translations.json']
files+=sorted((args.root/'usr/lib/aynthor').rglob('*.py'))
files+=sorted((args.root/'usr/lib/aynthor').rglob('*.js'))
files+=sorted((args.root/'usr/lib/aynthor/handhelddash/devices').rglob('*.json'))
digests={str(path.relative_to(args.root)):hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(files)}
git=subprocess.run(['git','rev-parse','HEAD'],cwd=args.source,capture_output=True,text=True)
state=subprocess.run(['git','status','--porcelain'],cwd=args.source,capture_output=True,text=True)
build=hashlib.sha256(json.dumps(digests,sort_keys=True).encode()).hexdigest()[:12]
manifest={'version':args.version,'build':build,'commit':git.stdout.strip() if git.returncode==0 else '',
          'dirty':bool(state.stdout.strip()),'files':digests}
(args.root/'usr/share/aynthor/build.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
