"""Shared palette substitutions; updated by the Qt application theme owner."""
from PyQt6.QtGui import QColor

THEME = {}


def theme_color(value: str) -> QColor:
    return QColor(THEME.get(value,value))
