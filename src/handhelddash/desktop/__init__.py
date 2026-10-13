"""Window-manager adapters."""
from .base import DesktopAdapter
from .kwin import KWinAdapter
from .kde import KDEAdapter
from .discovery import detect_desktop
