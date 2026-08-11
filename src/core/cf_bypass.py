import ctypes
import json
import os
import sys
from PySide6.QtCore import QMutex, QWaitCondition, QRecursiveMutex
from src.core.logger import log_operation


class PySideLock:
    def __init__(self):
        self._mutex = QRecursiveMutex()

    def __enter__(self):
        self._mutex.lock()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._mutex.unlock()


class PySideEvent:
    def __init__(self):
        self._mutex = QMutex()
        self._cond = QWaitCondition()
        self._flag = False

    def set(self):
        self._mutex.lock()
        try:
            self._flag = True
            self._cond.wakeAll()
        finally:
            self._mutex.unlock()

    def wait(self, timeout: float = None) -> bool:
        self._mutex.lock()
        try:
            if self._flag:
                return True
            timeout_ms = int(timeout * 1000) if timeout is not None else 4294967295
            return self._cond.wait(self._mutex, timeout_ms)
        finally:
            self._mutex.unlock()


DLL_FILENAME = "cf_bypass.dll"

_lock = PySideLock()
_lib: ctypes.CDLL | None = None
_warmup_done = PySideEvent()
_warmup_started = False
_thread_manager = None


def _find_dll() -> str:
    """Locate cf_bypass.dll in assets folder beside the project, bundle, or exe."""
    try:
        base = sys._MEIPASS  # type: ignore
    except AttributeError:
        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    candidates = [
        os.path.join(base, "assets", DLL_FILENAME),
        os.path.join(os.path.dirname(sys.executable), "assets", DLL_FILENAME),
        os.path.join("assets", DLL_FILENAME),
        os.path.join(os.path.dirname(sys.executable), DLL_FILENAME),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return os.path.abspath(path)
    raise RuntimeError(f"{DLL_FILENAME} not found in assets folder.")


def _get_lib() -> ctypes.CDLL:
    global _lib
    if _lib is None:
        with _lock:
            if _lib is None:
                dll_path = _find_dll()
                _lib = ctypes.CDLL(dll_path)
                _lib.cf_solve_mode.restype = ctypes.c_void_p
                _lib.cf_solve_mode.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
                _lib.cf_free.restype = None
                _lib.cf_free.argtypes = [ctypes.c_void_p]
                _lib.cf_set_profile_path.restype = None
                _lib.cf_set_profile_path.argtypes = [ctypes.c_char_p]
                # Create profile folder in same asset directory and pass it to DLL
                profile_dir = os.path.join(os.path.dirname(dll_path), "webview_profile")
                os.makedirs(profile_dir, exist_ok=True)
                _lib.cf_set_profile_path(profile_dir.encode("utf-8"))
    return _lib


@log_operation()
def solve(url: str, mode: str = "both") -> dict:
    """Call cf_solve_mode on the native DLL, serialized against warm-up."""
    with _lock:
        return _solve_unlocked(url, mode)


def _solve_unlocked(url: str, mode: str) -> dict:
    lib = _get_lib()
    ptr = lib.cf_solve_mode(url.encode("utf-8"), mode.encode("utf-8"))
    if not ptr:
        return {"code": 0, "error": "null pointer returned"}
    try:
        raw = ctypes.string_at(ptr).decode("utf-8", errors="replace")
        return json.loads(raw)
    finally:
        lib.cf_free(ptr)


@log_operation()
def warm_up(url: str = "https://steamdb.info/") -> None:
    """Pre-create the WebView2 profile + cf_clearance cookie once, on a QThread."""
    global _warmup_started, _thread_manager
    with _lock:
        if _warmup_started:
            return
        _warmup_started = True
    from src.core.threadManager import ThreadManager
    _thread_manager = ThreadManager()
    _thread_manager.run_function(_warm_worker, url)


@log_operation()
def wait_for_warmup(timeout: float = 30.0) -> bool:
    """Block until the background warm-up finishes (or timeout), returns ready state."""
    if not _warmup_started:
        return True
    return _warmup_done.wait(timeout)


def _warm_worker(url: str) -> None:
    try:
        solve(url, "both")
    except Exception:
        pass
    finally:
        _warmup_done.set()


@log_operation()
class CF_Scraper:
    """
    Native WebView2-based Cloudflare bypass. Keeps the same interface the rest
    of the app expects: scrape(url) returns the final page HTML.
    """

    __slots__ = ()

    def __init__(self, hide_window: bool = True, browser_path: str | None = None) -> None:
        # Native DLL runs fully headless in its own worker thread — no browser,
        # no window, no hide tricks needed. Args kept for interface compatibility.
        pass

    def scrape(self, url: str, max_retries: int = 2, page_load_wait: float = 0) -> str:
        max_retries = max(max_retries, 0)
        for attempt in range(max_retries + 1):
            result = solve(url, "both")
            if result.get("code") == 200:
                body = result.get("body", "")
                if page_load_wait:
                    import time
                    time.sleep(page_load_wait)
                return body
            if attempt < max_retries:
                import time
                time.sleep(2 * (attempt + 1))
        return ""

    def cleanup(self) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.cleanup()