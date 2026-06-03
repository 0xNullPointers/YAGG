from PySide6.QtWidgets import QPlainTextEdit
from PySide6.QtCore import Qt
from src.core.logger import log_operation

class OutputPanel(QPlainTextEdit):
    @log_operation()
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    @log_operation()
    def init_ui(self):
        self.setReadOnly(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.show_help_text()

    @log_operation()
    def show_help_text(self):
        help_text = """YAGG - GSE Generator: Quick Guide

  • Account Name: Optional (default used if empty)
  • Game Name: Full game name (e.g. "Counter-Strike 2")
  • AppID: Steam AppID number (e.g. 730)

REQUIRED: Either Game Name OR AppID must be provided — not both.
TIPS: Hover over the options for more info

Click Generate to start the process."""

        self.setPlainText(help_text)
        self.setStyleSheet("""QPlainTextEdit { font-family: 'Consolas', 'Monaco', 'Courier New', monospace; font-size: 14px; padding: 10px; color: #888888; }""")

    @log_operation()
    def clear_for_generation(self):
        self.clear()
        self.setStyleSheet("""QPlainTextEdit { font-family: 'Consolas', 'Monaco', 'Courier New', monospace; font-size: 14px; padding: 10px; }""")

    @log_operation(mute=True)
    def append_message(self, message):
        self.appendPlainText(message.rstrip())
