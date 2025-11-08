import time
import ctypes
from ctypes import wintypes
from DrissionPage import ChromiumPage, ChromiumOptions
from src.core.threadManager import ThreadManager

# ========== Win32 Setup ==========
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

# Get all visible Chrome window handles
def get_chrome_windows():
    windows = []
    @WNDENUMPROC
    def enum_proc(hwnd, _):
        if IsWindowVisible(hwnd):
            class_buf = ctypes.create_unicode_buffer(256)
            GetClassNameW(hwnd, class_buf, 256)
            if class_buf.value.startswith("Chrome_WidgetWin_"):
                title_buf = ctypes.create_unicode_buffer(256)
                GetWindowTextW(hwnd, title_buf, 256)
                if title_buf.value:
                    windows.append(hwnd)
        return True
    EnumWindows(enum_proc, 0)
    return windows

# Monitor for new Chrome windows and hide them
def monitor_and_hide(existing_set, duration=3):
    start = time.time()
    while time.time() - start < duration:
        for hwnd in get_chrome_windows():
            if hwnd not in existing_set:
                ShowWindow(hwnd, 0)
                return hwnd
        time.sleep(0.05)
    return None

# ========== CloudflareBypasser ==========
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
            # Fast path: look for turnstile input
            for ele in self.driver.eles("tag:input"):
                attrs = ele.attrs
                if attrs.get("type") == "hidden" and "turnstile" in attrs.get("name", ""):
                    parent_shadow = ele.parent().shadow_root
                    if parent_shadow:
                        body = parent_shadow.child()("tag:body")
                        if body:
                            return body.shadow_root("tag:input")
            
            # Fallback: search through iframe
            body = self.driver.ele("tag:body")
            iframe = self._search_iframe(body)
            if iframe:
                iframe_body = iframe("tag:body")
                if iframe_body:
                    return self._search_input(iframe_body)
            return None
        except Exception as e:
            print(f"Error locating button: {e}")
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

# ========== Main Scraper Class ==========
# Main Scraper class
class CF_Scraper:
    
    __slots__ = ('hide_window', 'driver', 'thread_mgr', '_window_monitor_signals')
    
    def __init__(self, hide_window=True):
        self.hide_window = hide_window
        self.driver = None
        self.thread_mgr = ThreadManager()
        self._window_monitor_signals = None
    
    # Set up window hiding monitoring in background thread
    def _setup_hidden_window(self):
        existing_windows = set(get_chrome_windows())
        self._window_monitor_signals = self.thread_mgr.run_function(
            monitor_and_hide, 
            existing_windows
        )
        return self._window_monitor_signals
    
    # Create and configure ChromiumPage driver
    def _create_driver(self):
        co = ChromiumOptions()
        if self.hide_window:
            co.set_argument('--window-position=-2400,-2400')
        else:
            co.set_argument('--window-position=100,100')
        return ChromiumPage(addr_or_opts=co)
    
    def scrape(self, url, output_file=None, max_retries=-1, page_load_wait=0):
        '''
        Scrape a URL with Cloudflare bypass and optional hidden browser window.
        
        Args:
            url (str): The URL to scrape
            output_file (str, optional): File path to save HTML. If None, returns HTML string
            max_retries (int): Max Cloudflare bypass retries (-1 for infinite)
            page_load_wait (int/float): Seconds to wait after page loads before retrieving HTML
        
        Returns:
            str: HTML content if output_file is None, otherwise None
        '''
        try:
            # Start window monitoring if hiding enabled
            if self.hide_window:
                self._setup_hidden_window()
            
            # Create driver with small delay for window monitor
            if self.hide_window:
                time.sleep(0.1)
            self.driver = self._create_driver()
            
            # Wait for window monitor to complete
            if self.hide_window:
                time.sleep(0.5)
            
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
            print(f"Scraping error: {e}")
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