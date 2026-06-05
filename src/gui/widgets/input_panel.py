from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QLineEdit, QPushButton, QSizePolicy
from PySide6.QtCore import Signal
from src.core.logger import log_operation

class InputPanel(QFrame):
    username_changed = Signal(str)
    game_name_changed = Signal(str)
    app_id_changed = Signal(str)
    browse_clicked = Signal()

    @log_operation()
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    @log_operation()
    def init_ui(self):
        # Prevent the frame itself from expanding vertically
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

        layout = QGridLayout(self)
        layout.setContentsMargins(8, 8, 8, 4)

        # We need a slight vertical spacing to calculate the button height correctly
        layout.setVerticalSpacing(6)

        # Account Name
        account_label = QLabel("Account Name:")
        self.user_account_entry = QLineEdit()
        self.user_account_entry.setMinimumHeight(28)
        self.user_account_entry.setPlaceholderText("e.g. gse orca")
        self.user_account_entry.textChanged.connect(self.username_changed.emit)
        layout.addWidget(account_label, 0, 0)
        layout.addWidget(self.user_account_entry, 0, 1, 1, 2)

        # Game Name
        game_label = QLabel("Game Name:")
        self.game_name_entry = QLineEdit()
        self.game_name_entry.setMinimumHeight(28)
        self.game_name_entry.setPlaceholderText("e.g. Counter-Strike 2")
        self.game_name_entry.textChanged.connect(self._on_game_name_change)
        layout.addWidget(game_label, 1, 0)
        layout.addWidget(self.game_name_entry, 1, 1)

        # AppID
        appid_label = QLabel("AppID:")
        self.app_id_entry = QLineEdit()
        self.app_id_entry.setMinimumHeight(28)
        self.app_id_entry.setPlaceholderText("e.g. 730")
        self.app_id_entry.textChanged.connect(self._on_app_id_change)
        layout.addWidget(appid_label, 2, 0)
        layout.addWidget(self.app_id_entry, 2, 1)

        # Browse Button
        self.browse_btn = QPushButton("Browse")
        # Ensure it spans both the Game Name and AppID rows
        # 28 (game name) + 28 (app id) + 6 (spacing) = 62
        self.browse_btn.setMinimumHeight(62)
        self.browse_btn.clicked.connect(self.browse_clicked.emit)
        layout.addWidget(self.browse_btn, 1, 2, 2, 1)

    @log_operation()
    def _on_game_name_change(self, text):
        self.app_id_entry.setReadOnly(bool(text.strip()))
        self.game_name_changed.emit(text)

    @log_operation()
    def _on_app_id_change(self, text):
        self.game_name_entry.setReadOnly(bool(text.strip()))
        self.app_id_changed.emit(text)

    @log_operation()
    def set_username(self, username):
        self.user_account_entry.setText(username)

    @log_operation()
    def get_username(self):
        return self.user_account_entry.text().strip()

    @log_operation()
    def get_game_name(self):
        return self.game_name_entry.text().strip()

    @log_operation()
    def get_app_id(self):
        return self.app_id_entry.text().strip()

    @log_operation()
    def set_game_info(self, app_id, game_name):
        self.app_id_entry.setText(app_id)
        self.game_name_entry.setText(game_name)
