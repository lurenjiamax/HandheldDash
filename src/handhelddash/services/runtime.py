# SPDX-License-Identifier: LGPL-3.0-or-later

"""AYN Thor hardware service. Fixed operations only; never executes client commands."""

import json

import fcntl

import logging

import math

import os

import re

import select

import signal

import struct

import sys

import threading

from pathlib import Path

import subprocess

import time

import dbus

import dbus.service

from dbus.mainloop.glib import DBusGMainLoop

from gi.repository import GLib

from evdev import AbsInfo, InputDevice, UInput, ecodes, list_devices

import yaml

sys.path.insert(0, '/usr/lib/aynthor')

from lpunpack import LpUnpack

from handhelddash.devices import DEVICE, cpu_set, format_cpu_set

from handhelddash.integrations.inputplumber.catalog import category as controller_category

from handhelddash.services.monitoring import GPUUtilization

from handhelddash.protocol import (HARDWARE_SERVICE as NAME, HARDWARE_PATH as PATH,
                                   INPUT_SERVICE as IP, COMPOSITE_INTERFACE as CI,
                                   FEEDBACK_INTERFACE as FF)

STATE = Path('/var/lib/aynthor/preferences.json')

CTL = DEVICE.hardware_control

def run(*args, timeout=25):
    p = subprocess.run(args, text=True, capture_output=True, timeout=timeout)
    if p.returncode:
        raise RuntimeError(p.stderr.strip() or p.stdout.strip() or f'{args[0]} failed')
    return p.stdout.strip()

def read(path, default=None):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return default

def number(path, scale=1):
    try:
        return float(read(path)) / scale
    except (TypeError, ValueError):
        return None

def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    stage = path.with_suffix('.new')
    with stage.open('w') as f:
        json.dump(data, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    stage.replace(path)
