"""Resolve resources from a source checkout or installed package."""
from pathlib import Path


def asset_path(relative: str) -> Path:
    source=Path(__file__).resolve().parents[3]/'packaging'/relative
    return source if source.is_file() else Path('/usr/share/aynthor')/relative
