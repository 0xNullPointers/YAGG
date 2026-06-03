import os, sys, shutil
from PySide6.QtWidgets import QMainWindow, QWidget, QGridLayout, QFileDialog
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QIcon
from .utils import get_resource_path, RedirectText
from .widgets.input_panel import InputPanel
from .widgets.controls_panel import ControlsPanel
from .widgets.output_panel import OutputPanel
from .widgets.status_panel import StatusPanel
from src.core.logger import log_operation

class AchievementFetcherGUI(QMainWindow):
    status_update = Signal(str, bool)
    message_received = Signal(str)
    request_dll_selection = Signal()

    @log_operation()
    def __init__(self):
        super().__init__()

        # Initialize basic attributes
        self.assets_dir = os.path.join(os.getcwd(), "assets")
        os.makedirs(self.assets_dir, exist_ok=True)
        self.settings_path = os.path.join(self.assets_dir, 'settings.ini')

        # Lazy initialize thread manager
        self._thread_manager = None

        # Setup UI
        self.init_ui()
        self.setup_window()
        self.setup_signals()
        self.load_saved_username()

    @log_operation(mute=True)
    def setup_window(self):
        self.setWindowTitle("YAGG - GSE Generator")
        self.resize(700, 500)
        self.setMinimumSize(500, 500)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowMinimizeButtonHint | Qt.WindowType.WindowCloseButtonHint)
        icon_path = get_resource_path('icon.ico')
        self.setWindowIcon(QIcon(icon_path))

    @log_operation(mute=True)
    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QGridLayout(central_widget)

        self.input_panel = InputPanel()
        self.controls_panel = ControlsPanel(self.settings_path)
        self.output_panel = OutputPanel()
        self.status_panel = StatusPanel()

        # Place input panel and its sub-widgets
        main_layout.addWidget(self.input_panel, 0, 0)
        # Nest controls_panel inside input_panel's layout for consistent UI look
        self.input_panel.layout().addWidget(self.controls_panel, 3, 0, 1, 2)

        main_layout.addWidget(self.output_panel, 1, 0)
        main_layout.addWidget(self.status_panel, 2, 0)

    @log_operation()
    def setup_signals(self):
        self.status_update.connect(self.status_panel.update_status)
        self.message_received.connect(self.output_panel.append_message)
        self.request_dll_selection.connect(self.select_dll)

        self.input_panel.username_changed.connect(self.save_username)
        self.controls_panel.generate_clicked.connect(self.start_generate)

    @property
    def thread_manager(self):
        if self._thread_manager is None:
            from src.core.threadManager import ThreadManager
            self._thread_manager = ThreadManager()
        return self._thread_manager

    @log_operation(mute=True)
    def write_output(self, message):
        self.message_received.emit(message + '\n')

    @log_operation()
    def set_status(self, message, is_error=False):
        self.status_update.emit(message, is_error)

    @log_operation()
    def save_username(self, username):
        try:
            config = self.controls_panel.config
            if 'Settings' not in config:
                config['Settings'] = {}
            config['Settings']['username'] = username.strip()
            with open(self.settings_path, 'w') as f:
                config.write(f)
        except Exception as e:
            self.write_output(f"Failed to save username: {str(e)}")

    @log_operation()
    def load_saved_username(self):
        try:
            username = self.controls_panel.config.get('Settings', 'username', fallback='')
            if username:
                self.input_panel.set_username(username)
        except Exception as e:
            self.write_output(f"Failed to load username: {str(e)}")

    @log_operation()
    def create_user_config(self, settings_dir: str):
        user_account = self.input_panel.get_username()
        use_local_save = self.controls_panel.is_checked('use_local_save')

        if self.controls_panel.is_checked('disable_lan_only') and not self.controls_panel.is_checked('achievements_only'):
            config_main_path = os.path.join(settings_dir, "configs.main.ini")
            with open(config_main_path, "w", encoding="utf-8") as f:
                f.write("[main::connectivity]\ndisable_lan_only=1\n")

        if not user_account and not use_local_save:
            return

        config_content = ""
        if user_account:
            config_content += f"[user::general]\naccount_name={user_account}\nlanguage=english\n"
        if use_local_save:
            config_content += "[user::saves]\nlocal_save_path=./GSE Saves\n"

        if config_content and not self.controls_panel.is_checked('achievements_only'):
            config_path = os.path.join(settings_dir, "configs.user.ini")
            with open(config_path, "w", encoding="utf-8") as f:
                f.write(config_content)

    @log_operation()
    def select_dll(self):
        self.write_output("Select Original Game folder...")
        try:
            dialog = QFileDialog(self)
            dialog.setWindowTitle("Select original Game folder")
            dialog.setFileMode(QFileDialog.FileMode.Directory)
            dialog.setViewMode(QFileDialog.ViewMode.Detail)

            if dialog.exec() == QFileDialog.DialogCode.Accepted:
                selected_files = dialog.selectedFiles()
                if selected_files:
                    folder_path = os.path.normpath(selected_files[0])
                    if os.access(folder_path, os.R_OK):
                        self.selected_dll_path = folder_path
                        self.continue_generation()
                    else:
                        self.write_output(f"Permission denied - {folder_path}")
                        self.set_status("Permission denied", True)
                        self.controls_panel.set_generate_enabled(True)
                else:
                    self.write_output("No folder selected")
                    self.set_status("No folder selected", True)
                    self.controls_panel.set_generate_enabled(True)
            else:
                self.write_output("No folder selected")
                self.set_status("No folder selected", True)
                self.controls_panel.set_generate_enabled(True)

        except Exception as e:
            self.write_output(f"Error selecting folder: {str(e)}")
            self.set_status("Error in folder selection", True)
            self.controls_panel.set_generate_enabled(True)

    @log_operation()
    def process_input(self, app_id, game_name):
        from src.core.appID_finder import get_steam_app_by_id, get_steam_app_by_name
        result = {}
        if app_id:
            self.write_output("Parsing AppID...")
            app_index = get_steam_app_by_id(app_id)
            if not app_index or 'name' not in app_index:
                raise Exception(f"Could not find game name for AppID '{app_id}'")
            result = {'game_name': app_index['name'], 'app_id': app_id}
        elif game_name:
            self.write_output("Parsing game name...")
            app_info = get_steam_app_by_name(game_name)
            if not app_info or 'appid' not in app_info:
                raise Exception(f"Could not find AppID for '{game_name}'")
            result = {'game_name': game_name, 'app_id': str(app_info['appid'])}
        return result

    @log_operation()
    def setup_emu(self):
        from src.core.setupEmu import download_goldberg, extract_archive
        EMU_FOLDER = os.path.join("assets", "goldberg_emu")
        if os.path.exists(EMU_FOLDER):
            return True
        self.write_output("Setting up GBE(Detanup01 fork)...")
        try:
            archive_path = download_goldberg()
            extract_archive(archive_path)
            self.write_output("GBE setup successfully.")
            return True
        except Exception as e:
            raise Exception(f"Failed to setup GBE: {str(e)}")

    @log_operation()
    def generate_files(self, app_id, file_path, use_steam):
        from src.core.appID_finder import get_steam_app_by_id
        app_index = get_steam_app_by_id(app_id)
        if not app_index or 'name' not in app_index:
            raise Exception(f"Could not find game info for AppID '{app_id}'")

        game_name = "".join(c if c not in '<>:"/\\|?*' else '_' for c in app_index['name'])
        game_dir = f"{game_name} ({app_id})"
        settings_dir = os.path.join(game_dir, "steam_settings")

        try:
            os.makedirs(game_dir, exist_ok=True)
            os.makedirs(settings_dir, exist_ok=True)

            dll_path = None
            if not self.controls_panel.is_checked('achievements_only'):
                dll_path = self._generate_core_files(game_dir, app_id, file_path)

            self._generate_achievements(settings_dir, app_id, use_steam)
            self.create_user_config(settings_dir)

            if self.controls_panel.is_checked('auto_replace') and dll_path:
                self._auto_replace_files(game_dir, dll_path)

            return game_dir
        except Exception as e:
            raise Exception(f"Failed to generate files: {str(e)}")

    @log_operation()
    def _generate_core_files(self, game_dir, app_id, file_path):
        from src.core.goldberg_gen import generate_emu
        from src.core.dlc_gen import fetch_dlc, create_dlc_config

        self.write_output("Generating GSE...")
        file_path = os.path.abspath(file_path)
        dll_path = self._find_dll(file_path)

        if not dll_path:
            raise Exception("Could not find steam_api.dll or steam_api64.dll")

        if not generate_emu(game_dir, app_id, dll_path, self.controls_panel.is_checked('disable_overlay')):
            raise Exception("Failed to generate Goldberg emu files")

        self.write_output("Fetching DLCs...")
        dlc_details = fetch_dlc(app_id)
        create_dlc_config(game_dir, dlc_details)
        return dll_path

    @log_operation()
    def _find_dll(self, file_path):
        ignore_folders = [f.lower() for f in ['gse', 'crack']]
        for root, dirs, files in os.walk(file_path, topdown=True):
            dirs[:] = [d for d in dirs if d.lower() not in ignore_folders]
            if 'steam_api.dll' in files:
                return os.path.join(root, 'steam_api.dll')
            if 'steam_api64.dll' in files:
                return os.path.join(root, 'steam_api64.dll')
        return None

    @log_operation()
    def _auto_replace_files(self, game_dir, dll_path):
        target_dir = os.path.dirname(dll_path)
        for root, dirs, files in os.walk(game_dir):
            rel_path = os.path.relpath(root, game_dir)
            for dir_name in dirs:
                os.makedirs(os.path.join(target_dir, rel_path, dir_name), exist_ok=True)
            for file_name in files:
                source_file = os.path.join(root, file_name)
                target_file = os.path.join(target_dir, rel_path, file_name)
                try:
                    if os.path.exists(target_file):
                        os.remove(target_file)
                    shutil.copy2(source_file, target_file)
                except PermissionError:
                    continue
        self.write_output("Files copied to Game dir successfully!")

    @log_operation()
    def _generate_achievements(self, settings_dir, app_id, use_steam):
        self.write_output("Fetching Achievements...")
        from src.core.achievements import fetch_from_steamcommunity, fetch_from_steamdb
        achievements = None
        if use_steam:
            try: achievements = fetch_from_steamcommunity(app_id, settings_dir, silent=False)
            except: pass
        else:
            try: achievements = fetch_from_steamdb(app_id, settings_dir, silent=False) or fetch_from_steamcommunity(app_id, settings_dir, silent=False)
            except: pass
        if not achievements:
            self.write_output("No achievements found.")

    @log_operation()
    def start_generate(self):
        game_name = self.input_panel.get_game_name()
        app_id = self.input_panel.get_app_id()

        if not (game_name or app_id):
            self.set_status("Enter GameName or AppID to continue", True)
            return

        self.set_status("Generating GSE...")
        self.controls_panel.set_generate_enabled(False)
        self.output_panel.clear_for_generation()
        sys.stdout = RedirectText(self.write_output)

        signals = self.thread_manager.run_function(self.process_input, app_id, game_name)
        signals.result.connect(self.on_input_processed)
        signals.error.connect(self.on_error)

    @log_operation()
    def on_input_processed(self, result):
        self.input_panel.set_game_info(result['app_id'], result['game_name'])

        if not self.controls_panel.is_checked('achievements_only'):
            signals = self.thread_manager.run_function(self.setup_emu)
            signals.result.connect(lambda _: self.request_dll_selection.emit())
            signals.error.connect(self.on_error)
        else:
            self.continue_generation(skip_dll=True)

    @log_operation()
    def continue_generation(self, skip_dll=False):
        signals = self.thread_manager.run_function(
            self.generate_files,
            self.input_panel.get_app_id(),
            getattr(self, 'selected_dll_path', None) if not skip_dll else None,
            self.controls_panel.is_checked('use_steam')
        )
        signals.result.connect(self.on_generation_complete)
        signals.error.connect(self.on_error)

    @log_operation()
    def on_generation_complete(self, game_dir):
        self.write_output("Files generated successfully!")
        self.write_output(f"Location: {game_dir}")
        self.set_status("GSE generated successfully")
        self.controls_panel.set_generate_enabled(True)
        sys.stdout = sys.__stdout__

    @log_operation()
    def on_error(self, error):
        self.write_output(str(error))
        self.controls_panel.set_generate_enabled(True)
        sys.stdout = sys.__stdout__

    @log_operation()
    def closeEvent(self, event):
        self.hide()
        event.accept()
        if self._thread_manager is not None:
            QTimer.singleShot(0, self._thread_manager.cleanup)
