from PySide6.QtWidgets import QFrame, QGridLayout, QLabel
from PySide6.QtGui import QColor, QPalette

class StatusPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        self.setFrameStyle(QFrame.Shape.Panel | QFrame.Shadow.Raised)
        layout = QGridLayout(self)
        self.status_label = QLabel("Status: Ready")
        layout.addWidget(self.status_label, 0, 0)

    def update_status(self, message, is_error=False):
        prefix = "Error: " if is_error else "Status: "
        self.status_label.setText(prefix + message)

        palette = self.palette()
        if is_error:
            bg_color = QColor(253, 231, 231)
            text_color = "rgb(211, 47, 47)"
        elif "successfully" in message.lower():
            bg_color = QColor(237, 255, 237)
            text_color = "rgb(46, 125, 50)"
        else:
            # Use parent's/system colors
            bg_color = self.parent().palette().color(QPalette.ColorRole.Window) if self.parent() else self.palette().color(QPalette.ColorRole.Window)
            text_color = self.palette().color(QPalette.ColorRole.WindowText).name()

        palette.setColor(QPalette.ColorRole.Window, bg_color)
        self.setPalette(palette)
        self.setAutoFillBackground(True)
        self.status_label.setStyleSheet(f"color: {text_color}")
