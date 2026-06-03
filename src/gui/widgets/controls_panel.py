import os, configparser
from PySide6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QGridLayout, QCheckBox, QPushButton
from PySide6.QtCore import Qt, Signal

class ControlsPanel(QFrame):
    generate_clicked = Signal()

    def __init__(self, settings_path, parent=None):
        super().__init__(parent)
        self.settings_path = settings_path
        self.config = configparser.ConfigParser(comment_prefixes='/', allow_no_value=True)
        self.config.optionxform = str  # type: ignore
        self.load_settings()
        self.init_ui()

    def load_settings(self):
        if os.path.exists(self.settings_path):
            self.config.read(self.settings_path)
        if 'Settings' not in self.config:
            self.config['Settings'] = {}

    def init_ui(self):
        self.setFixedHeight(100)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 2, 5, 2)
        layout.setSpacing(10)

        # Checkbox Frame
        checkbox_frame = QFrame()
        checkbox_frame.setFixedWidth(270)
        checkbox_frame.setFixedHeight(80)
        checkbox_layout = QGridLayout(checkbox_frame)
        checkbox_layout.setContentsMargins(0, 0, 0, 0)

        # Helper to create checkbox
        def create_checkbox(name, label, tooltip):
            checkbox = QCheckBox(label)
            checkbox.setToolTip(tooltip)
            checkbox.setToolTipDuration(5000)
            checkbox.setChecked(self.config.getboolean('Settings', name, fallback=False))

            def on_change(state):
                self.config['Settings'][name] = str(bool(state))
                with open(self.settings_path, 'w') as f:
                    self.config.write(f)

            checkbox.stateChanged.connect(on_change)
            return checkbox

        self.use_steam = create_checkbox('use_steam', "Use Steam", "Use Steam Community to fetch achievements data")
        self.use_local_save = create_checkbox('use_local_save', "Local Save", "Save game data inside game folder")
        self.disable_lan_only = create_checkbox('disable_lan_only', "Disable LAN Only", "Allow connecting to online servers instead of LAN only")
        self.achievements_only = create_checkbox('achievements_only', "Achievements Only", "Only generate achievement files, skip other emulator files")
        self.disable_overlay = create_checkbox('disable_overlay', "Disable Overlay", "Disable the Experimental Steam overlay in-game (recommended)")
        self.auto_replace = create_checkbox('auto_replace', "Auto Replace", "Automatically replace GSE files in Game dir")

        checkbox_layout.addWidget(self.use_steam, 0, 0)
        checkbox_layout.addWidget(self.use_local_save, 1, 0)
        checkbox_layout.addWidget(self.disable_overlay, 2, 0)
        checkbox_layout.addWidget(self.disable_lan_only, 0, 1)
        checkbox_layout.addWidget(self.achievements_only, 1, 1)
        checkbox_layout.addWidget(self.auto_replace, 2, 1)

        layout.addWidget(checkbox_frame, stretch=1)

        # Button Frame
        button_frame = QFrame()
        button_layout = QVBoxLayout(button_frame)
        button_layout.setContentsMargins(0, 0, 0, 0)

        self.generate_btn = QPushButton("Generate")
        self.generate_btn.setMinimumHeight(35)
        self.generate_btn.setFixedWidth(90)
        self.generate_btn.clicked.connect(self.generate_clicked.emit)

        button_layout.addStretch(1)
        button_layout.addWidget(self.generate_btn, alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)

        layout.addWidget(button_frame)

    def is_checked(self, name):
        if name == 'use_steam': return self.use_steam.isChecked()
        if name == 'use_local_save': return self.use_local_save.isChecked()
        if name == 'disable_lan_only': return self.disable_lan_only.isChecked()
        if name == 'achievements_only': return self.achievements_only.isChecked()
        if name == 'disable_overlay': return self.disable_overlay.isChecked()
        if name == 'auto_replace': return self.auto_replace.isChecked()
        return False

    def set_generate_enabled(self, enabled):
        self.generate_btn.setEnabled(enabled)
