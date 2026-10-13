"""Installed package provenance; development checkouts remain identifiable."""
import hashlib
import json
from pathlib import Path


def build_identity(entrypoint: str) -> str:
    manifest=Path('/usr/share/aynthor/build.json')
    if manifest.is_file() and Path(entrypoint).parent==Path('/usr/bin'):
        try:
            data=json.loads(manifest.read_text())
            modified=any(not Path('/'+name).is_file() or hashlib.sha256(Path('/'+name).read_bytes()).hexdigest()!=digest for name,digest in data['files'].items())
            return data['build']+(' · modified' if modified else '')
        except (OSError,ValueError,KeyError): pass
    digest=hashlib.sha256()
    package=Path(__file__).parents[1]
    sources=[Path(entrypoint),*sorted(package.rglob('*.py')),*sorted((package/'devices/profiles').glob('*.json'))]
    for source in sources: digest.update(source.name.encode()); digest.update(source.read_bytes())
    return 'dev · '+digest.hexdigest()[:12]
