"""Check the graphical connection before Qt can abort on a missing compositor."""
import os
from pathlib import Path
import socket
import subprocess
import time


def refresh_display_environment() -> None:
    """The user manager receives display variables after early services start."""
    try:
        result=subprocess.run(['systemctl','--user','show-environment'],capture_output=True,
                              text=True,timeout=2,check=True)
    except (OSError,subprocess.SubprocessError):
        return
    keys={'WAYLAND_DISPLAY','DISPLAY','XAUTHORITY','XDG_SESSION_TYPE'}
    for line in result.stdout.splitlines():
        key,separator,value=line.partition('=')
        if separator and key in keys and value:
            os.environ[key]=value


def display_ready() -> bool:
    platform=os.environ.get('QT_QPA_PLATFORM','').split(';',1)[0].split(':',1)[0]
    wayland_platform=platform in ('wayland','wayland-egl')
    if platform and not wayland_platform:
        return True  # Explicit X11 and headless backends keep their own behavior.
    display=os.environ.get('WAYLAND_DISPLAY')
    wayland=wayland_platform or os.environ.get('XDG_SESSION_TYPE')=='wayland' or bool(display)
    if not wayland:
        return bool(os.environ.get('DISPLAY'))
    if os.environ.get('WAYLAND_SOCKET'):
        try:
            with socket.fromfd(int(os.environ['WAYLAND_SOCKET']),socket.AF_UNIX,socket.SOCK_STREAM) as client:
                client.getpeername()
            return True
        except (OSError,ValueError):
            return False
    if not display:
        return False
    path=Path(display)
    if not path.is_absolute():
        runtime=os.environ.get('XDG_RUNTIME_DIR')
        if not runtime: return False
        path=Path(runtime)/path
    try:
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
            client.settimeout(.25)
            client.connect(str(path))
        return True
    except OSError:
        return False


def wait_for_display(timeout: float = 30, refresh_environment: bool = False) -> bool:
    deadline=time.monotonic()+timeout
    waiting=False
    while True:
        if refresh_environment: refresh_display_environment()
        if display_ready(): return True
        remaining=deadline-time.monotonic()
        if remaining<=0: return False
        if not waiting:
            print('HandheldDash: waiting for the graphical display connection',flush=True)
            waiting=True
        time.sleep(min(.25,remaining))
