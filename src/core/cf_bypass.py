import time, ctypes, winreg, sys, os, shutil, tempfile, threading
from ctypes import wintypes
from DrissionPage import ChromiumPage, ChromiumOptions
from src.core.logger import log_operation

if sys.platform == "win32":
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    # Constants
    EVENT_OBJECT_CREATE = 0x8000
    WINEVENT_OUTOFCONTEXT = 0x0000
    SW_HIDE = 0
    HWND_MESSAGE = -3
    GWL_EXSTYLE = -20
    WS_EX_TOOLWINDOW = 0x00000080
    WS_EX_APPWINDOW = 0x00040000
    WS_EX_NOACTIVATE = 0x08000000
    WM_QUIT = 0x0012

    # API prototypes
    WinEventProcType = ctypes.WINFUNCTYPE(
        None,
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.HWND,
        wintypes.LONG,
        wintypes.LONG,
        wintypes.DWORD,
        wintypes.DWORD,
    )

    _GetWindowThreadProcessId = user32.GetWindowThreadProcessId
    _GetWindowThreadProcessId.restype = wintypes.DWORD
    _GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]

    _AttachThreadInput = user32.AttachThreadInput
    _SetWinEventHook = user32.SetWinEventHook
    _UnhookWinEvent = user32.UnhookWinEvent
    _SetParent = user32.SetParent
    _ShowWindow = user32.ShowWindow
    _SetWindowLongW = user32.SetWindowLongW
    _GetWindowLongW = user32.GetWindowLongW
    _GetForegroundWindow = user32.GetForegroundWindow
    _SetForegroundWindow = user32.SetForegroundWindow
    _GetCurrentThreadId = kernel32.GetCurrentThreadId
    _PostThreadMessage = user32.PostThreadMessageW
    _PeekMessageW = user32.PeekMessageW
    _WaitMessage = user32.WaitMessage
    _TranslateMessage = user32.TranslateMessage
    _DispatchMessageW = user32.DispatchMessageW

# Shared PID with a proper lock
_target_pid_lock = threading.Lock()
_TARGET_PID: int | None = None

class StealthShield(threading.Thread):
    """
    Background thread that intercepts every new window belonging to the
    browser process and immediately hides it, reparenting it to the
    HWND_MESSAGE plane so it never appears in Alt-Tab or the taskbar,
    and never steals keyboard focus from the caller's window.
    """

    @log_operation()
    def __init__(self) -> None:
        super().__init__(daemon=True)
        self._stop_event = threading.Event()
        self._tid: int = 0
        self._orig_hwnd: int = 0  # set before hook fires
        self._orig_tid: int = 0
        # Keep a strong reference to the ctypes callback so it isn't GC'd
        self._cb: ctypes.CFUNCTYPE | None = None  # type: ignore[type-arg]

    # Internal helpers
    @log_operation(mute=True)
    def _hide_window(self, hwnd: int) -> None:
        """Reparent to the message-only plane and strip all visibility styles."""
        _SetParent(hwnd, HWND_MESSAGE)
        ex = _GetWindowLongW(hwnd, GWL_EXSTYLE)
        _SetWindowLongW(
            hwnd,
            GWL_EXSTYLE,
            (ex | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE) & ~WS_EX_APPWINDOW,
        )
        _ShowWindow(hwnd, SW_HIDE)

    @log_operation(mute=True)
    def _restore_focus(self) -> None:
        """Give focus back to whoever had it before we launched the browser."""
        if self._orig_hwnd and _GetForegroundWindow() != self._orig_hwnd:
            _SetForegroundWindow(self._orig_hwnd)

    # WinEvent callback
    @log_operation(mute=True)
    def _on_window_created(self, _hHook, _event, hwnd, _idObj, _idChild, _dwTid, _dwTime) -> None:
        with _target_pid_lock:
            target = _TARGET_PID
        if not target:
            return

        lp_pid = wintypes.DWORD()
        _GetWindowThreadProcessId(hwnd, ctypes.byref(lp_pid))
        if lp_pid.value != target:
            return

        self._hide_window(hwnd)
        self._restore_focus()

    # Thread entry point
    @log_operation()
    def run(self) -> None:
        self._tid = _GetCurrentThreadId()
        self._orig_hwnd = _GetForegroundWindow()

        # Capture the TID of the foreground window's thread
        # to get the authority to call SetForegroundWindow().
        lp_pid = wintypes.DWORD()
        self._orig_tid = _GetWindowThreadProcessId(
            self._orig_hwnd, ctypes.byref(lp_pid)
        )
        if self._orig_tid and self._orig_tid != self._tid:
            _AttachThreadInput(self._tid, self._orig_tid, True)

        # Keep cb alive as an instance attribute - ctypes won't GC it.
        self._cb = WinEventProcType(self._on_window_created)
        h_hook = _SetWinEventHook(
            EVENT_OBJECT_CREATE,
            EVENT_OBJECT_CREATE,
            0,
            self._cb,
            0,
            0,
            WINEVENT_OUTOFCONTEXT,
        )

        msg = wintypes.MSG()
        while not self._stop_event.is_set():
            if _PeekMessageW(ctypes.byref(msg), 0, 0, 0, 1):  # PM_REMOVE = 1
                if msg.message == WM_QUIT:
                    break
                _TranslateMessage(ctypes.byref(msg))
                _DispatchMessageW(ctypes.byref(msg))
            else:
                _WaitMessage()  # block until any message arrives

        _UnhookWinEvent(h_hook)
        if self._orig_tid and self._orig_tid != self._tid:
            _AttachThreadInput(self._tid, self._orig_tid, False)

    @log_operation()
    def stop(self) -> None:
        self._stop_event.set()
        if self._tid:
            _PostThreadMessage(self._tid, WM_QUIT, 0, 0)

# Patch DrissionPage to capture PID and suppress the startup window
try:
    import DrissionPage._functions.browser as _dp_browser

    @log_operation()
    def _patched_run_browser(port, path, args):
        global _TARGET_PID
        from subprocess import Popen, DEVNULL, STARTUPINFO, STARTF_USESHOWWINDOW
        from pathlib import Path

        si = STARTUPINFO()
        if sys.platform == "win32":
            si.dwFlags |= STARTF_USESHOWWINDOW
            si.wShowWindow = SW_HIDE

        exe = str(Path(path) / "chrome") if Path(path).is_dir() else path
        cmd = [exe, f"--remote-debugging-port={port}", *args]

        proc = Popen(
            cmd,
            shell=False,
            stdout=DEVNULL,
            stderr=DEVNULL,
            creationflags=0x08000000,  # CREATE_NO_WINDOW
            startupinfo=si,
        )
        with _target_pid_lock:
            _TARGET_PID = proc.pid
        return proc

    _dp_browser._run_browser = _patched_run_browser

except ImportError:
    pass

# Browser discovery
@log_operation()
def find_browsers() -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    reg_bases = [
        (
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths",
        ),
        (
            winreg.HKEY_CURRENT_USER,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths",
        ),
    ]
    for hkey, base in reg_bases:
        for exe in ("chrome.exe", "msedge.exe", "brave.exe"):
            try:
                with winreg.OpenKey(hkey, rf"{base}\{exe}") as k:
                    path = winreg.QueryValueEx(k, "")[0]
                    if not any(p == path for _, p in found):
                        found.append((exe, path))
            except OSError:
                continue
    return found


# Cloudflare Turnstile bypasser
class CloudflareBypasser:
    __slots__ = ("driver", "max_retries")
    @log_operation()
    def __init__(self, driver: ChromiumPage, max_retries: int = -1) -> None:
        self.driver = driver
        self.max_retries = max_retries

    @log_operation()
    def _find_turnstile_input(self):
        # Form-field variant
        for ele in self.driver.eles("tag:input"):
            if "turnstile" in ele.attrs.get("name", ""):
                return (
                    ele.parent()
                    .shadow_root.child()("tag:body")
                    .shadow_root("tag:input")
                )
        # Iframe variant
        ifr = self.driver.ele("tag:body").shadow_root.ele("tag:iframe")
        if ifr:
            return ifr.content_frame.ele("tag:body").shadow_root.ele("tag:input")
        return None

    @log_operation()
    def bypass(self) -> None:
        tries = 0
        while "just a moment" in self.driver.title.lower():
            if 0 <= self.max_retries <= tries:
                break
            try:
                target = self._find_turnstile_input()
                if target:
                    target.click()
                    time.sleep(2)
                else:
                    time.sleep(1)
            except Exception:  # noqa: BLE001 - CF DOM can be volatile
                time.sleep(1)
            tries += 1

# Main class
class CF_Scraper:
    """
    Launch a Chromium browser invisibly, bypass Cloudflare Turnstile, and
    return the final page HTML.  The browser is always torn down after scrape().
    """

    __slots__ = ("_hide", "_browser_path", "driver", "_tmp_dir", "_shield")

    @log_operation()
    def __init__(self, hide_window: bool = True, browser_path: str | None = None) -> None:
        self._hide = hide_window
        self.driver: ChromiumPage | None = None
        self._tmp_dir: str | None = None
        self._shield: StealthShield | None = None

        if browser_path:
            self._browser_path = browser_path
        else:
            browsers = find_browsers()
            if not browsers:
                raise RuntimeError("No compatible Chromium-family browser found.")
            self._browser_path = browsers[0][1]

    @log_operation()
    def scrape(self, url: str, max_retries: int = -1, page_load_wait: float = 0) -> str:
        try:
            co = ChromiumOptions().set_browser_path(self._browser_path)

            if self._hide:
                self._tmp_dir = tempfile.mkdtemp(prefix="cf_scraper_")
                co.set_user_data_path(self._tmp_dir)
                for arg in (
                    "--window-position=-32000,-32000",
                    "--window-size=1,1",
                    "--start-minimized",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--mute-audio",
                ):
                    co.set_argument(arg)

                if sys.platform == "win32":
                    self._shield = StealthShield()
                    self._shield.start()

            self.driver = ChromiumPage(addr_or_opts=co)
            self.driver.get(url)
            CloudflareBypasser(self.driver, max_retries).bypass()

            if page_load_wait:
                time.sleep(page_load_wait)

            return self.driver.html

        finally:
            self.cleanup()

    @log_operation()
    def cleanup(self) -> None:
        if self._shield:
            self._shield.stop()
            self._shield = None

        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None

        if self._tmp_dir and os.path.exists(self._tmp_dir):
            time.sleep(0.1)
            shutil.rmtree(self._tmp_dir, ignore_errors=True)
            self._tmp_dir = None

    @log_operation()
    def __enter__(self):
        return self

    @log_operation()
    def __exit__(self, *_):
        self.cleanup()
