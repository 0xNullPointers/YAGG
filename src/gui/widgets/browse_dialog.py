import os, sqlite3
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLineEdit, QHBoxLayout, QListView, QAbstractItemView, QStyledItemDelegate, QStyle
from PySide6.QtCore import Qt, QByteArray, QAbstractListModel, QModelIndex, QThreadPool, QRunnable, Signal, QTimer, QSize, QPropertyAnimation, QEasingCurve, QAbstractAnimation, QRectF
from PySide6.QtGui import QPixmap, QImage, QPainter, QPainterPath
from src.core.network import create_session

CACHE_DIR = os.path.join(os.getcwd(), "assets", "cache", "posters")
os.makedirs(CACHE_DIR, exist_ok=True)
DB_PATH = os.path.join(os.getcwd(), "assets", "steam_data.db")

class GameItemDelegate(QStyledItemDelegate):
    """
    Highly optimized custom delegate to render posters and beautifully formatted text directly.
    Bypasses the need for heavy UI widgets per item.
    """
    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        rect = option.rect

        is_selected = option.state & QStyle.StateFlag.State_Selected
        is_hovered = option.state & QStyle.StateFlag.State_MouseOver

        # 4) Dynamic selection color that blends smoothly with the OS theme
        if is_selected or is_hovered:
            if is_selected:
                bg_color = option.palette.highlight().color()
                bg_color.setAlpha(50) # Soft, modern alpha blend
            else:
                bg_color = option.palette.text().color()
                bg_color.setAlpha(20) # Grayish opaque hover

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(bg_color)

            # Constrain the background box so it isn't too wide if grid expands
            box_w = 150
            box_x = rect.x() + (rect.width() - box_w) / 2
            selection_rect = QRectF(box_x, rect.y() + 2, box_w, rect.height() - 4)
            painter.drawRoundedRect(selection_rect, 10, 10)

        name, appid = index.data(Qt.ItemDataRole.UserRole)
        pixmap = index.data(Qt.ItemDataRole.DecorationRole)

        # 1) Image boundaries (Centered in the item)
        img_w, img_h = 120, 180
        img_x = rect.x() + (rect.width() - img_w) / 2
        img_y = rect.y() + 10
        img_rect = QRectF(img_x, img_y, img_w, img_h)

        if pixmap and not pixmap.isNull():
            # Round the poster corners
            path = QPainterPath()
            path.addRoundedRect(img_rect, 8, 8)
            painter.setClipPath(path)
            painter.drawPixmap(img_rect.toRect(), pixmap)
            painter.setClipping(False)

        # 2) Text boundaries (Bottom center)
        text_rect = QRectF(rect.x() + 5, img_rect.bottom() + 12, rect.width() - 10, 50)

        font = painter.font()

        # Game Name (Bold)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(option.palette.text().color())
        metrics = painter.fontMetrics()
        elided_name = metrics.elidedText(name, Qt.TextElideMode.ElideRight, int(text_rect.width()))
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, elided_name)

        # AppID (Lighter, subtle styling)
        font.setBold(False)
        painter.setFont(font)
        id_color = option.palette.text().color()
        id_color.setAlpha(150) # Subtly blend the ID color
        painter.setPen(id_color)
        id_rect = QRectF(text_rect.x(), text_rect.y() + 18, text_rect.width(), 20)
        painter.drawText(id_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, f"I.D. {appid}")

        painter.restore()

    def sizeHint(self, option, index):
        return QSize(160, 260)


class SmoothScrollListView(QListView):
    """
    Industrial-standard smooth scrolling using Qt's internal C++ animation engine.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)

        self._v_anim = QPropertyAnimation(self.verticalScrollBar(), b"value", self)
        self._v_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._v_anim.setDuration(400)
        self._scroll_target = 0

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if not delta:
            return super().wheelEvent(event)

        bar = self.verticalScrollBar()

        if self._v_anim.state() == QAbstractAnimation.State.Running:
            current_target = self._scroll_target
        else:
            current_target = bar.value()

        step_size = 200
        direction = -1 if delta > 0 else 1

        new_target = current_target + (direction * step_size)
        new_target = max(bar.minimum(), min(new_target, bar.maximum()))
        self._scroll_target = new_target

        self._v_anim.stop()
        self._v_anim.setStartValue(bar.value())
        self._v_anim.setEndValue(new_target)
        self._v_anim.start()

        event.accept()


class ImageLoader(QRunnable):
    def __init__(self, appid, finished_signal):
        super().__init__()
        self.appid = appid
        self.finished_signal = finished_signal

    def run(self):
        cache_path = os.path.join(CACHE_DIR, f"{self.appid}.jpg")
        image = QImage()

        # Check cache first
        if os.path.exists(cache_path):
            if os.path.getsize(cache_path) > 0:
                image.load(cache_path)
            # If size is 0, it's a known missing image, image remains null
        else:
            # Download from Steam using custom network manager
            url = f"https://cdn.cloudflare.steamstatic.com/steam/apps/{self.appid}/library_600x900.jpg"
            try:
                with create_session(timeout=5) as session:
                    response = session.get(url)
                    if response.status_code == 200:
                        with open(cache_path, 'wb') as f:
                            f.write(response.content)
                        image.loadFromData(response.content)
                    else:
                        # Cache the 404 state as an empty file to save future requests
                        with open(cache_path, 'wb') as f:
                            f.write(b'')
            except Exception:
                pass

        # Generate placeholder or scale down actual image
        if image.isNull():
            image = QImage(120, 180, QImage.Format.Format_RGB32)
            image.fill(Qt.GlobalColor.darkGray)
        else:
            image = image.scaled(120, 180, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)

        # Emit through the shared signal on the model to ensure lifetime safety
        try:
            self.finished_signal.emit(self.appid, image)
        except RuntimeError:
            # Signal source has been deleted (dialog closed)
            pass


class GameListModel(QAbstractListModel):
    image_loaded = Signal(int, QImage)

    def __init__(self, games, parent=None):
        super().__init__(parent)
        self.games = games
        self.pixmaps = {}
        self.loading = set()
        self.thread_pool = QThreadPool.globalInstance()
        self.image_loaded.connect(self.on_image_loaded)

    def rowCount(self, parent=QModelIndex()):
        return len(self.games)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None

        appid, name = self.games[index.row()]

        # Supply raw data to the custom delegate
        if role == Qt.ItemDataRole.UserRole:
            return (name, appid)

        elif role == Qt.ItemDataRole.DecorationRole:
            if appid in self.pixmaps:
                return self.pixmaps[appid]

            # Trigger lazy load
            if appid not in self.loading:
                self.loading.add(appid)
                worker = ImageLoader(appid, self.image_loaded)
                self.thread_pool.start(worker)

            # Return placeholder while loading
            placeholder = QPixmap(120, 180)
            placeholder.fill(Qt.GlobalColor.darkGray)
            return placeholder

        return None

    def on_image_loaded(self, appid, image):
        self.pixmaps[appid] = QPixmap.fromImage(image)
        if appid in self.loading:
            self.loading.remove(appid)

        # Emit dataChanged for the specific row
        for row, (a_id, name) in enumerate(self.games):
            if a_id == appid:
                idx = self.index(row, 0)
                self.dataChanged.emit(idx, idx, [Qt.ItemDataRole.DecorationRole])
                break

    def update_data(self, new_games):
        self.beginResetModel()
        self.games = new_games
        # Prevent memory leak by clearing massive pixmap caches across major search changes
        if len(self.pixmaps) > 2000:
            self.pixmaps.clear()
        self.endResetModel()

    def get_game(self, row):
        if 0 <= row < len(self.games):
            return self.games[row]
        return None, None


class BrowseDialog(QDialog):
    game_selected = Signal(str, str)

    def __init__(self, config, settings_path, parent=None):
        super().__init__(parent)
        self.config = config
        self.settings_path = settings_path

        self.setWindowTitle("Search Games")
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowCloseButtonHint)
        self.setModal(True)
        self.resize(800, 600) # Slightly larger default to see more posters

        self.init_ui()
        self.load_geometry()

        # Debounce timer for search
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.timeout.connect(self.perform_search)

        self.load_initial_games()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setContentsMargins(10, 20, 10, 10)

        # Search Bar
        self.search_bar = QLineEdit()
        self.search_bar.setMinimumHeight(45)
        self.search_bar.setFixedWidth(400)
        self.search_bar.setPlaceholderText("Search for a game...")
        self.search_bar.setStyleSheet("""
            QLineEdit {
                border: 1px solid #777;
                border-radius: 22px;
                padding: 0 15px;
                font-size: 14px;
            }
        """)
        self.search_bar.textChanged.connect(self.on_search_text_changed)

        search_layout = QHBoxLayout()
        search_layout.addStretch(1)
        search_layout.addWidget(self.search_bar)
        search_layout.addStretch(1)

        layout.addLayout(search_layout)

        # 5) Add spacing below the search bar to prevent it from being too narrow
        layout.addSpacing(20)

        # Lazy Loading Game List View
        self.list_view = SmoothScrollListView()
        self.list_view.setMouseTracking(True) # Enable hover states
        self.list_view.setViewMode(QListView.ViewMode.IconMode)
        self.list_view.setResizeMode(QListView.ResizeMode.Adjust)
        self.list_view.setSpacing(15) # Revert to Qt's native spacing handler
        self.list_view.setGridSize(QSize(160, 260))
        self.list_view.setUniformItemSizes(True)

        # Assign our performant custom painter delegate
        self.list_view.setItemDelegate(GameItemDelegate(self.list_view))

        self.list_view.setStyleSheet("""
            QListView {
                border: none;
                background-color: transparent;
                outline: 0;
            }
        """)

        self.model = GameListModel([])
        self.list_view.setModel(self.model)
        self.list_view.doubleClicked.connect(self.on_item_double_clicked)

        layout.addWidget(self.list_view)

    def on_search_text_changed(self, text):
        # Debounce the search input to avoid database lockups on fast typing
        self.search_timer.start(400)

    def load_initial_games(self):
        self.fetch_games("")

    def perform_search(self):
        query = self.search_bar.text().strip()
        self.fetch_games(query)

    def fetch_games(self, query):
        if not os.path.exists(DB_PATH):
            return

        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()

            # Base exclusions to filter out common non-game apps
            exclusions = "name NOT LIKE '%DLC%' AND name NOT LIKE '%Soundtrack%' AND name NOT LIKE '%Artbook%' AND name NOT LIKE '%Dedicated Server%'"

            # Limit to 500 to keep the UI perfectly smooth and fast
            if query:
                cursor.execute(f"SELECT appid, name FROM apps WHERE name LIKE ? AND {exclusions} LIMIT 500", (f"%{query}%",))
            else:
                cursor.execute(f"SELECT appid, name FROM apps WHERE {exclusions} LIMIT 500")

            games = cursor.fetchall()
            self.model.update_data(games)
            conn.close()
        except Exception as e:
            print(f"Database error: {e}")

    def on_item_double_clicked(self, index):
        appid, name = self.model.get_game(index.row())
        if appid and name:
            self.game_selected.emit(str(appid), name)
            self.accept()

    def load_geometry(self):
        try:
            geom = self.config.get('Window', 'browse_geometry', fallback=None)
            if geom:
                self.restoreGeometry(QByteArray.fromHex(geom.encode()))
        except Exception:
            pass

    def closeEvent(self, event):
        try:
            if not self.config.has_section('Window'):
                self.config.add_section('Window')
            self.config.set('Window', 'browse_geometry', self.saveGeometry().toHex().data().decode())
            with open(self.settings_path, 'w') as f:
                self.config.write(f)
        except Exception:
            pass
        super().closeEvent(event)
