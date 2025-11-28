import time
import ctypes
import winreg
from ctypes import wintypes
from DrissionPage import ChromiumPage, ChromiumOptions
from src.core.threadManager import ThreadManager

# Win32 Setup 
user32 = ctypes.WinDLL('user32', use_last_error=True)
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

EnumWindows = user32.EnumWindows
EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
GetWindowTextW = user32.GetWindowTextW
GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
GetClassNameW = user32.GetClassNameW
GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
IsWindowVisible = user32.IsWindowVisible
IsWindowVisible.argtypes = [wintypes.HWND]
ShowWindow = user32.ShowWindow
ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
SetWindowPos = user32.SetWindowPos
SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]

# Functions for modifying window styles
GetWindowLongW = user32.GetWindowLongW
GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
GetWindowLongW.restype = ctypes.c_long

SetWindowLongW = user32.SetWindowLongW
SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
SetWindowLongW.restype = ctypes.c_long

# Constants for SetWindowPos
HWND_BOTTOM = 1
SWP_NOACTIVATE = 0x0010
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_SHOWWINDOW = 0x0040

# Constants for window styles
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000
SW_HIDE = 0
SW_SHOW = 5

# Detect installed Chromium-based browsers from registry
def find_browsers():
    browsers = []
    
    # Registry paths to check
    registry_paths = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths"),
    ]
    
    browser_configs = [
        ("chrome.exe", "Google Chrome", "Chrome_WidgetWin_"),
        ("msedge.exe", "Microsoft Edge", "Chrome_WidgetWin_"),
        ("brave.exe", "Brave", "Chrome_WidgetWin_"),
        ("opera.exe", "Opera", "Chrome_WidgetWin_"),
        ("vivaldi.exe", "Vivaldi", "Chrome_WidgetWin_"),
    ]
    
    for hkey, base_path in registry_paths:
        for exe_name, display_name, window_class in browser_configs:
            try:
                key_path = f"{base_path}\\{exe_name}"
                with winreg.OpenKey(hkey, key_path) as key:
                    exe_path, _ = winreg.QueryValueEx(key, "")
                    if not any(b[0] == display_name for b in browsers):
                        browsers.append((display_name, exe_path, window_class))
            except FileNotFoundError:
                continue
            except Exception:
                continue
    
    return browsers

# Get all browser window handles for a specific browser
def get_browser_windows(window_class_prefix="Chrome_WidgetWin_"):
    windows = []
    @WNDENUMPROC
    def enum_proc(hwnd, _):
        if IsWindowVisible(hwnd):
            class_buf = ctypes.create_unicode_buffer(256)
            GetClassNameW(hwnd, class_buf, 256)
            if class_buf.value.startswith(window_class_prefix):
                title_buf = ctypes.create_unicode_buffer(256)
                GetWindowTextW(hwnd, title_buf, 256)
                if title_buf.value:
                    windows.append(hwnd)
        return True
    EnumWindows(enum_proc, 0)
    return windows

# Hide icon from taskbar
def hide_from_taskbar(hwnd):
    try:
        ex_style = GetWindowLongW(hwnd, GWL_EXSTYLE)
        new_style = (ex_style | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW
        ShowWindow(hwnd, SW_HIDE)
        SetWindowLongW(hwnd, GWL_EXSTYLE, new_style)
        ShowWindow(hwnd, SW_SHOW)
        ShowWindow(hwnd, SW_HIDE)
        
        return True
    except Exception:
        return False

# Monitor for browser windows and hide them with proper sequence
def monitor_and_hide(existing_set, window_class_prefix, duration=1.5):
    start = time.time()
    while time.time() - start < duration:
        for hwnd in get_browser_windows(window_class_prefix):
            if hwnd not in existing_set:
                if hide_from_taskbar(hwnd):
                    return hwnd
        time.sleep(0.01)
    return None

# CloudflareBypasser
# Courtesy: https://github.com/sarperavci/CloudflareBypassForScraping
# Handles Cloudflare challenge bypass
class CloudflareBypasser:
    __slots__ = ('driver', 'max_retries')
    def __init__(self, driver: ChromiumPage, max_retries=-1):
        self.driver = driver
        self.max_retries = max_retries

    # Recursively search for Cloudflare iframe in shadow DOM
    def _search_iframe(self, ele):
        if ele.shadow_root:
            child = ele.shadow_root.child()
            if child and child.tag == "iframe":
                return child
        for child in ele.children():
            result = self._search_iframe(child)
            if result:
                return result
        return None

    # Recursively search for challenge input in shadow DOM
    def _search_input(self, ele):
        if ele.shadow_root:
            input_ele = ele.shadow_root.ele("tag:input")
            if input_ele:
                return input_ele
        for child in ele.children():
            result = self._search_input(child)
            if result:
                return result
        return None
    
    # Locate Cloudflare challenge button
    def _locate_button(self):
        try:
            for ele in self.driver.eles("tag:input"):
                attrs = ele.attrs
                if attrs.get("type") == "hidden" and "turnstile" in attrs.get("name", ""):
                    parent_shadow = ele.parent().shadow_root
                    if parent_shadow:
                        body = parent_shadow.child()("tag:body")
                        if body:
                            return body.shadow_root("tag:input")
            
            body = self.driver.ele("tag:body")
            iframe = self._search_iframe(body)
            if iframe:
                iframe_body = iframe("tag:body")
                if iframe_body:
                    return self._search_input(iframe_body)
            return None
        except Exception as e:
            return None

    # Execute Cloudflare bypass
    def bypass(self):
        tries = 0
        while "just a moment" in self.driver.title.lower():
            if 0 < self.max_retries < tries:
                break
            
            try:
                button = self._locate_button()
                if button:
                    button.click()
                    time.sleep(2)
                else:
                    time.sleep(1)
            except Exception as e:
                print(f"Bypass attempt {tries + 1} failed: {e}")
                time.sleep(2)
            
            tries += 1

# Main class
class CF_Scraper:
    __slots__ = ('hide_window', 'driver', 'thread_mgr', '_window_monitor_signals', 'browser_name', 'browser_path', 'window_class_prefix')
    
    def __init__(self, hide_window=True, browser_path=None):
        self.hide_window = hide_window
        self.driver = None
        self.thread_mgr = ThreadManager()
        self._window_monitor_signals = None
        
        # Detect browser
        if browser_path:
            self.browser_path = browser_path
            self.browser_name = "Custom Browser"
            self.window_class_prefix = "Chrome_WidgetWin_"
        else:
            browsers = find_browsers()
            if not browsers:
                raise RuntimeError("No compatible Chromium-based browsers found in registry")
            
            self.browser_name, self.browser_path, self.window_class_prefix = browsers[0]
            print(f"Using: {self.browser_name}")
    
    def _setup_hidden_window(self):
        existing_windows = set(get_browser_windows(self.window_class_prefix))
        self._window_monitor_signals = self.thread_mgr.run_function(
            monitor_and_hide,
            existing_windows,
            self.window_class_prefix
        )
        return self._window_monitor_signals
    
    def _create_driver(self):
        co = ChromiumOptions()
        co.set_browser_path(self.browser_path)
        
        if self.hide_window:
            co.set_argument('--window-position=-3000,-3000')
            co.set_argument('--start-minimized')
            co.set_argument('--disable-gpu')
        else:
            co.set_argument('--window-position=100,100')
            
        return ChromiumPage(addr_or_opts=co)
    
    def scrape(self, url, output_file=None, max_retries=-1, page_load_wait=0):
        try:
            if self.hide_window:
                self._setup_hidden_window()
                time.sleep(0.05)

            self.driver = self._create_driver()
            if self.hide_window:
                time.sleep(0.15)
            
            # Navigate and bypass Cloudflare
            self.driver.get(url)
            CloudflareBypasser(self.driver, max_retries=max_retries).bypass()
            
            # Wait for additional page content if requested
            if page_load_wait > 0:
                time.sleep(page_load_wait)
            
            # Get HTML content
            html_content = self.driver.html
            
            # Save to file or return content
            if output_file:
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(html_content)
                return None
            return html_content
                
        except Exception as e:
            print(f"Fetching error: {e}")
            raise
        finally:
            self.cleanup()
    
    # Clean up browser and background threads
    def cleanup(self):
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None
        
        self.thread_mgr.cleanup()
        self._window_monitor_signals = None
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()
        return False