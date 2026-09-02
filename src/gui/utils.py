import os, sys
from src.core.logger import log_operation

@log_operation()
def get_resource_path(filename):
    try:
        base_path = sys._MEIPASS  # type: ignore
    except AttributeError:
        base_path = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    return os.path.join(base_path, filename)

class RedirectText:
    @log_operation()
    def __init__(self, output_callback):
        self.output_callback = output_callback
        self.last_line = ""

    @log_operation(mute=True)
    def write(self, string):
        cleaned_string = string.replace('\r', '').replace('\n', '').strip()
        if cleaned_string:
            self.output_callback(cleaned_string + '\n')

    @log_operation()
    def flush(self):
        pass


@log_operation()
def bring_to_foreground(widget):
    """Ensure the top-level window is raised, activated, and given foreground focus."""
    widget.raise_()
    widget.activateWindow()
    if sys.platform == "win32":
        try:
            import ctypes
            hwnd = int(widget.winId())
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            from PySide6.QtCore import QTimer
            QTimer.singleShot(50, lambda: ctypes.windll.user32.SetForegroundWindow(hwnd))
        except Exception:
            pass
