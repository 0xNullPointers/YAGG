import ctypes
import json
import os
import sys

DLL_FILENAME = "cf_bypass.dll"


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


_lib: ctypes.CDLL | None = None


def _get_lib() -> ctypes.CDLL:
    global _lib
    if _lib is None:
        _lib = ctypes.CDLL(_find_dll())
        _lib.cf_solve_mode.restype = ctypes.c_void_p
        _lib.cf_solve_mode.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
        _lib.cf_free.restype = None
        _lib.cf_free.argtypes = [ctypes.c_void_p]
    return _lib


def solve(url: str, mode: str = "both") -> dict:
    """Call cf_solve_mode on the native DLL, return parsed JSON."""
    lib = _get_lib()
    ptr = lib.cf_solve_mode(url.encode("utf-8"), mode.encode("utf-8"))
    if not ptr:
        return {"code": 0, "error": "null pointer returned"}
    try:
        raw = ctypes.string_at(ptr).decode("utf-8", errors="replace")
        return json.loads(raw)
    finally:
        lib.cf_free(ptr)


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

    def scrape(self, url: str, max_retries: int = -1, page_load_wait: float = 0) -> str:
        result = solve(url, "both")
        if result.get("code") == 200:
            import time
            body = result.get("body", "")
            if page_load_wait:
                time.sleep(page_load_wait)
            return body
        return ""

    def cleanup(self) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.cleanup()