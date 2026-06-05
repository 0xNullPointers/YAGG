import os, sqlite3, logging
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLineEdit, QHBoxLayout, QListView, QAbstractItemView, QStyledItemDelegate, QStyle
from PySide6.QtCore import Qt, QByteArray, QAbstractListModel, QModelIndex, QThreadPool, QRunnable, Signal, QObject, QTimer, QSize, QRectF
from PySide6.QtGui import QPixmap, QImage, QPainter, QPainterPath, QFont, QColor
from src.core.network import create_session

CACHE_DIR = os.path.join(os.getcwd(), "assets", "cache", "headers")
os.makedirs(CACHE_DIR, exist_ok=True)
DB_PATH = os.path.join(os.getcwd(), "assets", "steam_data.db")

log = logging.getLogger(__name__)


class _DBSignals(QObject):
    result_ready = Signal(list)


class DBWorker(QRunnable):
    BASE_EXCLUSIONS = (
        "name NOT LIKE '%DLC%' "
        "AND name NOT LIKE '%Soundtrack%' "
        "AND name NOT LIKE '%Artbook%' "
        "AND name NOT LIKE '%Dedicated Server%'"
    )

    def __init__(self, query: str, signals: _DBSignals):
        super().__init__()
        self._query = query
        self._signals = signals

    def run(self):
        if not os.path.exists(DB_PATH):
            self._signals.result_ready.emit([])
            return
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            if self._query:
                # Search: return all types
                cursor.execute(
                    f"SELECT appid, name, type FROM apps WHERE name LIKE ? AND {self.BASE_EXCLUSIONS} LIMIT 500",
                    (f"%{self._query}%",),
                )
            else:
                # Initial load: games only
                cursor.execute(
                    f"SELECT appid, name, type FROM apps WHERE type = 'game' AND {self.BASE_EXCLUSIONS} LIMIT 500"
                )
            games = cursor.fetchall()
            conn.close()
        except Exception as e:
            log.error("DBWorker query failed: %s", e)
            games = []
        self._signals.result_ready.emit(games)


class GameItemDelegate(QStyledItemDelegate):
    BOX_W = 250  # card width
    BOX_H = 171  # card height
    IMG_W = 230
    IMG_H = 107
    IMG_TOP = 10  # margin from top of box to image
    TEXT_GAP = 12  # gap between image bottom and name text
    ID_OFFSET_Y = 20  # vertical offset from name baseline to appid row

    # Badge colour map
    _BADGE_META = {
        "game": ("GAME", "#4CAF50"),
        "dlc": ("DLC", "#42A5F5"),
        "software": ("SOFT", "#AB47BC"),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        # Pre-built font objects
        base = QFont()
        self._font_bold = QFont(base)
        self._font_bold.setBold(True)
        self._font_normal = QFont(base)
        self._font_normal.setBold(False)

        # Badge font
        self._font_badge = QFont(base)
        self._font_badge.setBold(True)
        self._font_badge.setPointSize(7)

        # Pre-built QColor objects for each badge type
        self._badge_colors = {
            key: QColor(hex_) for key, (_, hex_) in self._BADGE_META.items()
        }

        self._img_clip_path = QPainterPath()
        self._img_clip_path.addRoundedRect(QRectF(0, 0, self.IMG_W, self.IMG_H), 8, 8)
        self._elided_cache: dict[int, str] = {}

    def invalidate_elided_cache(self):
        self._elided_cache.clear()

    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        rect = option.rect

        is_selected = option.state & QStyle.StateFlag.State_Selected
        is_hovered = option.state & QStyle.StateFlag.State_MouseOver

        # Box widget geometry
        box_x = rect.x() + (rect.width() - self.BOX_W) / 2
        box_y = rect.y() + (rect.height() - self.BOX_H) / 2
        box_rect = QRectF(box_x, box_y, self.BOX_W, self.BOX_H)

        # Dynamic selection color
        if is_selected:
            bg_color = option.palette.highlight().color()
            bg_color.setAlpha(50)
            border_color = option.palette.highlight().color()
            border_color.setAlpha(100)
        elif is_hovered:
            bg_color = option.palette.text().color()
            bg_color.setAlpha(20)
            border_color = option.palette.text().color()
            border_color.setAlpha(50)
        else:
            bg_color = option.palette.text().color()
            bg_color.setAlpha(8)
            border_color = option.palette.text().color()
            border_color.setAlpha(15)

        # Draw the "box widget" background
        painter.setBrush(bg_color)
        pen = painter.pen()
        pen.setColor(border_color)
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawRoundedRect(box_rect, 8, 8)

        name, appid, type_ = index.data(Qt.ItemDataRole.UserRole)
        pixmap = index.data(Qt.ItemDataRole.DecorationRole)

        # Image rect
        img_x = box_x + (self.BOX_W - self.IMG_W) / 2
        img_rect = QRectF(img_x, box_rect.y() + self.IMG_TOP, self.IMG_W, self.IMG_H)

        if pixmap and not pixmap.isNull():
            painter.save()
            painter.translate(img_rect.topLeft())
            painter.setClipPath(self._img_clip_path)
            painter.drawPixmap(0, 0, pixmap)
            painter.restore()

        # Badge
        badge_info = self._BADGE_META.get(type_ or "")
        if badge_info:
            badge_label, _ = badge_info
            badge_color = self._badge_colors[type_]

            painter.setFont(self._font_badge)
            fm = painter.fontMetrics()
            pad_x, pad_y = 5, 3
            badge_w = fm.horizontalAdvance(badge_label) + pad_x * 2
            badge_h = fm.height() + pad_y * 2
            badge_rect = QRectF(
                img_rect.right() - badge_w - 5,
                img_rect.top() + 5,
                badge_w,
                badge_h,
            )
            painter.setBrush(badge_color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(badge_rect, badge_h / 2, badge_h / 2)  # pill shape
            painter.setPen(Qt.GlobalColor.white)
            painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, badge_label)

        # Text rect
        text_rect = QRectF(
            box_x + 5, img_rect.bottom() + self.TEXT_GAP, self.BOX_W - 10, 50
        )

        # Game Name
        painter.setFont(self._font_bold)
        painter.setPen(option.palette.text().color())
        if appid not in self._elided_cache:
            self._elided_cache[appid] = painter.fontMetrics().elidedText(
                name, Qt.TextElideMode.ElideRight, int(text_rect.width())
            )
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            self._elided_cache[appid],
        )

        # AppID
        painter.setFont(self._font_normal)
        id_color = option.palette.text().color()
        id_color.setAlpha(150)
        painter.setPen(id_color)
        id_rect = QRectF(
            text_rect.x(), text_rect.y() + self.ID_OFFSET_Y, text_rect.width(), 20
        )
        painter.drawText(
            id_rect,
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            f"I.D. {appid}",
        )

        painter.restore()

    def sizeHint(self, option, index):
        return QSize(self.BOX_W + 20, self.BOX_H + 16)


class SmoothScrollListView(QListView):
    MOUSE_STEP = 120

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setGridSize(QSize(GameItemDelegate.BOX_W + 20, GameItemDelegate.BOX_H + 16))

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._update_grid_layout)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_grid_layout()

    def _update_grid_layout(self):
        box_w = GameItemDelegate.BOX_W
        cell_h = GameItemDelegate.BOX_H + 16
        min_gap = 20
        base_item_w = box_w + min_gap

        scroll_w = self.verticalScrollBar().sizeHint().width()
        available_w = self.width() - scroll_w

        if available_w < base_item_w:
            self.setGridSize(QSize(base_item_w, cell_h))
            self.setViewportMargins(0, 0, 0, 0)
            return

        columns = max(1, (available_w - min_gap) // base_item_w)
        gap = (available_w - columns * box_w) // (columns + 1)
        self.setGridSize(QSize(box_w + gap, cell_h))
        self.setViewportMargins(gap // 2, 0, 0, 0)

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if not delta:
            return super().wheelEvent(event)
        bar = self.verticalScrollBar()
        pixels = round(-delta * self.MOUSE_STEP / 120)
        bar.setValue(bar.value() + pixels)
        event.accept()


class ImageLoader(QRunnable):
    CDN_URLS = [
        "https://cdn.akamai.steamstatic.com/steam/apps/{appid}/header.jpg",
        "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{appid}/header.jpg",
        "https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/header.jpg",
    ]

    def __init__(self, appid, session, finished_signal):
        super().__init__()
        self.appid = appid
        self.session = session
        self.finished_signal = finished_signal

    def run(self):
        cache_path = os.path.join(CACHE_DIR, f"{self.appid}.jpg")
        image = QImage()

        if os.path.exists(cache_path):
            if os.path.getsize(cache_path) > 0:
                image.load(cache_path)
        else:
            content = None

            for url_template in self.CDN_URLS:
                url = url_template.format(appid=self.appid)
                try:
                    response = self.session.get(url)
                    if response.status_code == 200:
                        content = response.content
                        break
                    elif response.status_code == 404:
                        content = b""
                        break
                except Exception as e:
                    log.warning("Image fetch failed: appid=%s cdn=%s error=%s", self.appid, url, e)
                    break

            if content:
                with open(cache_path, "wb") as f:
                    f.write(content)
                image.loadFromData(content)
            elif content == b"":
                with open(cache_path, "wb") as f:
                    f.write(b"")

        img_w = GameItemDelegate.IMG_W
        img_h = GameItemDelegate.IMG_H
        if image.isNull():
            image = QImage(img_w, img_h, QImage.Format.Format_RGB32)
            image.fill(Qt.GlobalColor.darkGray)
        else:
            image = image.scaled(img_w, img_h, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)

        try:
            self.finished_signal.emit(self.appid, image)
        except RuntimeError:
            pass


class GameListModel(QAbstractListModel):
    image_loaded = Signal(int, QImage)

    def __init__(self, games, session, parent=None):
        super().__init__(parent)
        self.games = games  # list of (appid, name, type)
        self._appid_to_row: dict[int, int] = {
            appid: row for row, (appid, *_) in enumerate(games)
        }
        self.pixmaps = {}
        self.loading = set()
        self.thread_pool = QThreadPool.globalInstance()
        self._session = session
        # Single shared placeholder
        self._placeholder = QPixmap(GameItemDelegate.IMG_W, GameItemDelegate.IMG_H)
        self._placeholder.fill(Qt.GlobalColor.darkGray)
        self.image_loaded.connect(
            self.on_image_loaded, Qt.ConnectionType.QueuedConnection
        )

    def rowCount(self, parent=QModelIndex()):
        return len(self.games)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None

        appid, name, type_ = self.games[index.row()]

        if role == Qt.ItemDataRole.UserRole:
            return (name, appid, type_)

        elif role == Qt.ItemDataRole.DecorationRole:
            if appid in self.pixmaps:
                return self.pixmaps[appid]
            if appid not in self.loading:
                self.loading.add(appid)
                worker = ImageLoader(appid, self._session, self.image_loaded)
                self.thread_pool.start(worker)
            return self._placeholder

        return None

    def on_image_loaded(self, appid, image):
        self.pixmaps[appid] = QPixmap.fromImage(image)
        self.loading.discard(appid)
        row = self._appid_to_row.get(appid)
        if row is not None:
            idx = self.index(row, 0)
            self.dataChanged.emit(idx, idx, [Qt.ItemDataRole.DecorationRole])

    def update_data(self, new_games):
        self.beginResetModel()
        self.games = new_games
        self._appid_to_row = {appid: row for row, (appid, *_) in enumerate(new_games)}
        if len(self.pixmaps) > 2000:
            self.pixmaps.clear()
        self.endResetModel()

    def get_game(self, row):
        if 0 <= row < len(self.games):
            return self.games[row]
        return None, None, None


class BrowseDialog(QDialog):
    game_selected = Signal(str, str)

    def __init__(self, config, settings_path, parent=None):
        super().__init__(parent)
        self.config = config
        self.settings_path = settings_path
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle("Search Games")
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowCloseButtonHint)
        self.setModal(True)
        self.resize(800, 600)
        self._http_session = create_session(timeout=10)
        self._db_signals = _DBSignals(self)
        self._db_signals.result_ready.connect(
            self.model_update_from_db, Qt.ConnectionType.QueuedConnection
        )

        self.init_ui()
        self.load_geometry()

        # Debounce timer
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.timeout.connect(self.perform_search)

        self.load_initial_games()

    def init_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 20, 0, 0)
        self.main_layout.setSpacing(20)

        # UPPER ROW
        self.upper_row = QHBoxLayout()
        self.upper_row.setAlignment(Qt.AlignmentFlag.AlignCenter)

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

        self.upper_row.addWidget(self.search_bar)
        self.main_layout.addLayout(self.upper_row)

        # BOTTOM ROW
        self.list_view = SmoothScrollListView(self)
        self.list_view.setMouseTracking(True)
        self.list_view.setViewMode(QListView.ViewMode.IconMode)
        self.list_view.setResizeMode(QListView.ResizeMode.Adjust)
        self.list_view.setSpacing(0)
        self.list_view.setUniformItemSizes(True)
        self.list_view.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.list_view.setItemDelegate(GameItemDelegate(self.list_view))
        self.list_view.setStyleSheet("""
            QListView {
                border: none;
                background-color: transparent;
                outline: 0;
            }
        """)

        self.model = GameListModel([], self._http_session)
        self.list_view.setModel(self.model)
        self.list_view.doubleClicked.connect(self.on_item_double_clicked)

        self.main_layout.addWidget(self.list_view, 1)

    # Search / DB
    def on_search_text_changed(self, text):
        self.search_timer.start(400)

    def load_initial_games(self):
        self.fetch_games("")

    def perform_search(self):
        self.fetch_games(self.search_bar.text().strip())

    def fetch_games(self, query: str):
        worker = DBWorker(query, self._db_signals)
        QThreadPool.globalInstance().start(worker)

    def model_update_from_db(self, games: list):
        self.model.update_data(games)
        delegate = self.list_view.itemDelegate()
        if isinstance(delegate, GameItemDelegate):
            delegate.invalidate_elided_cache()

    # Selection
    def on_item_double_clicked(self, index):
        appid, name, _type = self.model.get_game(index.row())
        if appid and name:
            self.game_selected.emit(str(appid), name)
            self.accept()

    # Geometry persistence
    def load_geometry(self):
        try:
            geom = self.config.get("Window", "browse_geometry", fallback=None)
            if geom:
                self.restoreGeometry(QByteArray.fromHex(geom.encode()))
        except Exception:
            log.warning("Failed to restore browse dialog geometry", exc_info=True)

    def closeEvent(self, event):
        log.debug("BrowseDialog.closeEvent - closing HTTP session")
        self._http_session.close()

        try:
            if not self.config.has_section("Window"):
                self.config.add_section("Window")
            self.config.set(
                "Window", "browse_geometry", self.saveGeometry().toHex().data().decode()
            )
            with open(self.settings_path, "w") as f:
                self.config.write(f)
        except Exception:
            log.warning("Failed to save browse dialog geometry", exc_info=True)
        super().closeEvent(event)
