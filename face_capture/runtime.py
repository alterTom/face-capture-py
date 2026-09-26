import ctypes
import logging
import os
import sys
import time
from ctypes import wintypes
from logging.handlers import RotatingFileHandler
from .paths import data_dir

MUTEX = 'FaceCaptureAgent'
STOP_EVENT = 'FaceCaptureAgentStop'
SHOW_EVENT = 'FaceCaptureAgentShow'


def kernel32():
    dll = ctypes.WinDLL('kernel32', use_last_error=True)
    dll.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    dll.CreateMutexW.restype = wintypes.HANDLE
    dll.OpenMutexW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    dll.OpenMutexW.restype = wintypes.HANDLE
    dll.ReleaseMutex.argtypes = [wintypes.HANDLE]
    dll.CloseHandle.argtypes = [wintypes.HANDLE]
    dll.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
    dll.CreateEventW.restype = wintypes.HANDLE
    dll.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    dll.OpenEventW.restype = wintypes.HANDLE
    dll.SetEvent.argtypes = [wintypes.HANDLE]
    dll.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    return dll


class InstanceGuard:
    def __init__(self, name=MUTEX):
        self.dll = kernel32()
        self.handle = self.dll.CreateMutexW(None, True, name)
        error = ctypes.get_last_error()
        if not self.handle: raise ctypes.WinError(error)
        self.acquired = error != 183  # ERROR_ALREADY_EXISTS

    def __enter__(self): return self

    def __exit__(self, *args):
        if self.acquired: self.dll.ReleaseMutex(self.handle)
        self.dll.CloseHandle(self.handle)


class ControlEvents:
    def __init__(self, stop_name=STOP_EVENT, show_name=SHOW_EVENT):
        self.dll = kernel32()
        self.stop = self.dll.CreateEventW(None, True, False, stop_name)
        self.show = self.dll.CreateEventW(None, False, False, show_name)
        if not self.stop or not self.show:
            error = ctypes.get_last_error()
            if self.stop: self.dll.CloseHandle(self.stop)
            if self.show: self.dll.CloseHandle(self.show)
            raise ctypes.WinError(error)

    def __enter__(self): return self

    def poll(self):
        return (self.dll.WaitForSingleObject(self.stop, 0) == 0,
                self.dll.WaitForSingleObject(self.show, 0) == 0)

    def __exit__(self, *args):
        self.dll.CloseHandle(self.stop)
        self.dll.CloseHandle(self.show)


def signal_event(name, timeout=1.5):
    dll = kernel32()
    deadline = time.monotonic() + timeout
    while True:
        event = dll.OpenEventW(2, False, name)
        if event:
            try: return bool(dll.SetEvent(event))
            finally: dll.CloseHandle(event)
        if time.monotonic() >= deadline: return False
        time.sleep(.05)


def stop_running():
    dll = kernel32()
    event = dll.OpenEventW(2, False, STOP_EVENT)
    if not event: return 0
    try: dll.SetEvent(event)
    finally: dll.CloseHandle(event)
    mutex = dll.OpenMutexW(0x00100000, False, MUTEX)
    if not mutex: return 0
    try:
        return 0 if dll.WaitForSingleObject(mutex, 20000) in (0, 128) else 1
    finally: dll.CloseHandle(mutex)


def clear_previous_logs(logs):
    """Remove only application-owned logs before the main process starts logging."""
    for component in ('capture', 'camera'):
        for name in (f'{component}.log', f'{component}-native.log',
                     f'{component}-native.previous.log'):
            (logs / name).unlink(missing_ok=True)
        for backup in logs.glob(f'{component}.log.*'):
            if backup.name.removeprefix(f'{component}.log.').isdigit():
                backup.unlink()


def configure_mpl_cache(cache):
    # PyInstaller's runtime hook assigns a fresh temporary directory in every
    # spawned process. This onedir application can reuse its stable cache.
    if getattr(sys, 'frozen', False):
        os.environ['MPLCONFIGDIR'] = str(cache)
    else:
        os.environ.setdefault('MPLCONFIGDIR', str(cache))


def configure_logging(component='capture', *, new_session=False):
    root = data_dir()
    logs = root / 'logs'
    logs.mkdir(exist_ok=True)
    if new_session:
        clear_previous_logs(logs)
    cache = root / 'cache'
    cache.mkdir(exist_ok=True)
    configure_mpl_cache(cache)
    os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '2')
    handler = RotatingFileHandler(logs / f'{component}.log', maxBytes=2 * 1024 * 1024,
                                  backupCount=5, encoding='utf-8')
    logging.basicConfig(level=logging.INFO, handlers=[handler],
                        format='%(asctime)s %(levelname)s %(name)s %(message)s', force=True)
    native_path = logs / f'{component}-native.log'
    if native_path.exists() and native_path.stat().st_size > 2 * 1024 * 1024:
        native_path.replace(logs / f'{component}-native.previous.log')
    native = open(native_path, 'a', encoding='utf-8', buffering=1)
    # windowed PyInstaller has no stdout/stderr; provide valid streams for dependencies.
    sys.stdout = sys.stderr = native
    for fd in (1, 2):
        try: os.dup2(native.fileno(), fd)
        except OSError: pass
    return root
