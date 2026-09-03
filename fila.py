#!/usr/bin/env python3
"""Fila — browse folders, filter by type, sort, generate .m3u8, play."""

import locale
import os
import sys
import json
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

locale.setlocale(locale.LC_NUMERIC, "C")

import send2trash
import mpv

from PySide6.QtCore import (
    Qt, QObject, QThread, Signal, QModelIndex, QDir, QPoint, QTimer, QSize,
    QEvent, QLibraryInfo, QSettings, qVersion,
)
from PySide6.QtGui import QIcon, QPalette
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QSplitter, QTreeView, QComboBox, QLabel, QPushButton,
    QToolButton,
    QFileSystemModel, QHeaderView, QTableWidget, QTableWidgetItem,
    QAbstractItemView, QStatusBar, QLineEdit, QFrame, QMessageBox,
    QListWidget, QListWidgetItem, QMenu, QCheckBox, QSlider, QSpinBox, QStyle,
    QStyleOptionSlider, QInputDialog,
)

# ── File type definitions ─────────────────────────────────────────────────────

FILE_TYPES: dict[str, set[str]] = {
    "Videos": {
        # MPEG / H.26x
        ".mp4", ".m4v", ".m4p", ".mpg", ".mpeg", ".mpe", ".m1v", ".m2v",
        ".m2p", ".h264", ".264", ".h265", ".265", ".hevc",
        # Matroska
        ".mkv", ".mk3d", ".mks", ".webm",
        # AVI / DivX
        ".avi", ".divx",
        # QuickTime / Apple
        ".mov", ".qt",
        # Windows
        ".wmv", ".wm", ".asf",
        # Flash
        ".flv", ".f4v", ".f4p",
        # OGG
        ".ogv", ".ogg",
        # Transport streams
        ".ts", ".mts", ".m2ts", ".tp", ".trp",
        # DVD / Blu-ray
        ".vob", ".ifo",
        # Mobile / 3GPP
        ".3gp", ".3g2", ".3gpp",
        # RealMedia
        ".rm", ".rmvb", ".ram",
        # Misc
        ".dv", ".nsv", ".amv", ".mxf", ".roq", ".svi", ".mjpg", ".mjpeg",
        ".yuv", ".nut",
    },
    "Images": {
        ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif",
        ".webp", ".svg", ".ico", ".heic", ".heif", ".avif",
        ".jxl", ".psd", ".raw", ".cr2", ".cr3", ".nef", ".arw",
        ".dng", ".orf", ".rw2", ".pnm", ".pbm", ".pgm", ".ppm",
        ".xpm", ".tga", ".exr", ".hdr",
    },
    "Audio": {
        # Lossy
        ".mp3", ".mp2", ".mp1", ".aac", ".ogg", ".oga", ".opus",
        ".wma", ".ra", ".amr", ".3ga",
        # Lossless
        ".flac", ".wav", ".wave", ".aiff", ".aif", ".aifc",
        ".ape", ".wv", ".tta", ".tak",
        # Containers
        ".m4a", ".mka", ".caf",
        # Other
        ".mpc", ".spx", ".ac3", ".dts", ".au", ".snd",
        ".dsf", ".dff", ".ofr",
        # Tracker / MIDI
        ".mid", ".midi", ".mod", ".xm", ".it", ".s3m",
    },
    "All": set(),  # empty = no extension filter
}

# Role used to store the raw numeric/string sort key alongside display text
SORT_ROLE = Qt.ItemDataRole.UserRole + 1

# ── Config ────────────────────────────────────────────────────────────────────

CONFIG_PATH = Path.home() / ".config" / "fila" / "fila.json"


def _load_config() -> dict:
    try:
        data = json.loads(CONFIG_PATH.read_text())
        # Migrate old format: list of strings → list of dicts
        favs = data.get("favorites", [])
        if favs and isinstance(favs[0], str):
            data["favorites"] = [
                {"path": p, "name": Path(p).name or p} for p in favs
            ]
        return data
    except Exception:
        return {"favorites": []}


def _save_config(data: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(data, indent=2))


def _update_config(**kwargs) -> None:
    """Merge kwargs into the existing config and save."""
    data = _load_config()
    data.update(kwargs)
    _save_config(data)

# ── Sortable table item ───────────────────────────────────────────────────────

class NumericItem(QTableWidgetItem):
    """QTableWidgetItem that sorts by a stored numeric key instead of display text."""

    def __init__(self, display: str, sort_key: float):
        super().__init__(display)
        self.setData(SORT_ROLE, sort_key)

    def __lt__(self, other: QTableWidgetItem) -> bool:
        my_key    = self.data(SORT_ROLE)
        other_key = other.data(SORT_ROLE)
        if my_key is not None and other_key is not None:
            return my_key < other_key
        return super().__lt__(other)

# ── Background duration fetcher ───────────────────────────────────────────────

def _ffprobe_duration(path: str) -> float:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "json", path],
            capture_output=True, text=True, timeout=8,
        )
        return float(json.loads(out.stdout)["format"]["duration"])
    except Exception:
        return 0.0


class DurationWorker(QThread):
    result_ready = Signal(str, float)   # (path, seconds)

    def __init__(self, paths: list[str]):
        super().__init__()
        self.paths = paths
        self._stop = False

    def run(self):
        for p in self.paths:
            if self._stop:
                break
            self.result_ready.emit(p, _ffprobe_duration(p))

    def cancel(self):
        self._stop = True


# ── Helpers ───────────────────────────────────────────────────────────────────

def fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def fmt_duration(secs: float) -> str:
    if secs <= 0:
        return "—"
    s = int(secs)
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def vline() -> QFrame:
    ln = QFrame()
    ln.setFrameShape(QFrame.Shape.VLine)
    ln.setFrameShadow(QFrame.Shadow.Sunken)
    ln.setLineWidth(1)
    ln.setMidLineWidth(0)
    return ln


# ── Seek slider that jumps to click position ─────────────────────────────────

class SeekSlider(QSlider):
    def _value_from_position(self, x: int) -> int:
        opt = QStyleOptionSlider()
        self.initStyleOption(opt)
        groove = self.style().subControlRect(
            QStyle.ComplexControl.CC_Slider,
            opt,
            QStyle.SubControl.SC_SliderGroove,
            self,
        )
        position = max(0, min(groove.width(), x - groove.x()))
        return QStyle.sliderValueFromPosition(
            self.minimum(), self.maximum(), position, max(1, groove.width())
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # Start dragging from the clicked point, not only from the handle.
            self.sliderPressed.emit()
            self.setSliderDown(True)
            self.setSliderPosition(
                self._value_from_position(event.position().toPoint().x())
            )
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.isSliderDown() and (event.buttons() & Qt.MouseButton.LeftButton):
            self.setSliderPosition(
                self._value_from_position(event.position().toPoint().x())
            )
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.isSliderDown():
            self.setSliderDown(False)
            self.sliderReleased.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)


# ── Thread-safe bridge for mpv → Qt signals ──────────────────────────────────

class _MpvBridge(QObject):
    """Receives mpv property callbacks (called from mpv's thread) and re-emits
    them as Qt signals, which Qt queues onto the main thread automatically."""
    time_pos_changed   = Signal(float)   # current position in seconds
    duration_changed   = Signal(float)   # total duration in seconds
    pause_changed      = Signal(bool)    # True = paused
    mute_changed       = Signal(bool)    # True = muted
    volume_changed     = Signal(float)   # 0–100
    preview_dbl_clicked = Signal()       # MOUSE_BTN0_DBL inside the video area


# ── Main window ───────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Fila")
        self.resize(1100, 680)

        self._all_files: list[dict] = []
        self._dur_cache: dict[str, float] = {}
        self._worker: DurationWorker | None = None
        self._current_folder: str = ""
        config = _load_config()
        self._favorites: list[str] = config.get("favorites", [])
        self._scan_subfolders: bool = bool(config.get("scan_subfolders", False))
        try:
            self._max_depth: int = max(1, int(config.get("max_depth", 1)))
        except (TypeError, ValueError):
            self._max_depth = 1
        self._mpv: mpv.MPV | None = None
        self._mpv_bridge = _MpvBridge()
        self._mpv_duration: float = 0.0
        self._mpv_pos: float = 0.0           # current playback position in preview
        self._mpv_muted: bool = True         # mirrors mpv mute state (starts muted)
        self._preview_path: str = ""         # file currently loaded in preview
        self._seeking: bool = False          # True while user drags the slider
        self._preview_timer = QTimer(singleShot=True, interval=250)
        self._preview_timer.timeout.connect(self._do_preview)

        self._build_ui()
        self._connect()
        self._populate_fav_list()
        self._navigate(str(Path.home()))

    def _set_play_pause_icon(self, paused: bool) -> None:
        icon = self.style().standardIcon(
            QStyle.StandardPixmap.SP_MediaPlay if paused else QStyle.StandardPixmap.SP_MediaPause
        )
        self.btn_play_pause.setIcon(icon)

    def _set_mute_icon(self, muted: bool) -> None:
        icon = self.style().standardIcon(
            QStyle.StandardPixmap.SP_MediaVolumeMuted if muted else QStyle.StandardPixmap.SP_MediaVolume
        )
        self.btn_mute.setIcon(icon)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.MouseButtonPress and self._is_descendant(obj, self.preview_panel):
            self.preview_panel.setFocus()

        if event.type() == QEvent.Type.KeyPress and event.modifiers() == Qt.KeyboardModifier.NoModifier:
            key = event.key()
            focus = QApplication.focusWidget()
            if focus is not None:
                in_preview = self._is_descendant(focus, self.preview_panel)
                in_table = self._is_descendant(focus, self.table)

                if key in (Qt.Key.Key_Left, Qt.Key.Key_Right) and (in_preview or in_table):
                    self._seek_relative(-15 if key == Qt.Key.Key_Left else 15)
                    return True

        return super().eventFilter(obj, event)

    def _is_descendant(self, widget, ancestor) -> bool:
        current = widget
        while current is not None:
            if current is ancestor:
                return True
            parent = getattr(current, "parentWidget", None)
            current = parent() if callable(parent) else None
        return False

    def _seek_relative(self, delta: float) -> None:
        if self._mpv is None:
            return
        try:
            if self._mpv_duration > 0:
                target = max(0.0, min(self._mpv_pos + delta, self._mpv_duration))
                self._mpv_pos = target
                self.lbl_pos.setText(fmt_duration(target))
                self._mpv.seek(target, "absolute")
            else:
                self._mpv.seek(delta, "relative")
        except Exception:
            pass

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        self.setStyleSheet(
            """
            QWidget#topBar,
            QWidget#previewPane,
            QTreeView#folderTree,
            QListWidget#favoritesList,
            QTableWidget#fileTable {
                background: palette(window);
                border: 1px solid palette(mid);
                border-radius: 7px;
            }

            QTableWidget#fileTable,
            QTreeView#folderTree,
            QListWidget#favoritesList {
                background-color: palette(base);
            }

            QSplitter::handle {
                background: palette(mid);
            }

            QSplitter::handle:hover {
                background: palette(highlight);
            }

            """
        )

        # Toolbar
        top_bar = QWidget()
        top_bar.setObjectName("topBar")
        tb = QHBoxLayout(top_bar)
        tb.setContentsMargins(6, 6, 6, 6)
        tb.setSpacing(6)

        tb.addWidget(QLabel("Path:"))
        self.path_edit = QLineEdit()
        self.path_edit.setMinimumHeight(30)
        self.path_edit.setPlaceholderText("Folder path…")
        tb.addWidget(self.path_edit, 1)

        self.btn_go = QPushButton("Go")
        self.btn_go.setObjectName("topActionButton")
        self.btn_go.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowRight))
        self.btn_go.setIconSize(QSize(16, 16))
        self.btn_go.setFixedWidth(64)
        self.btn_go.setFixedHeight(30)
        tb.addWidget(self.btn_go)

        tb.addWidget(vline())

        tb.addWidget(QLabel("Type:"))
        self.type_combo = QComboBox()
        self.type_combo.addItems(FILE_TYPES.keys())
        self.type_combo.setCurrentText("Videos")
        self.type_combo.setMinimumWidth(90)
        self.type_combo.setMinimumHeight(30)
        tb.addWidget(self.type_combo)

        tb.addWidget(vline())

        tb.addWidget(QLabel("Filter:"))
        self.filter_edit = QLineEdit()
        self.filter_edit.setMinimumHeight(30)
        self.filter_edit.setPlaceholderText("Search files…")
        self.filter_edit.setFixedWidth(160)
        self.filter_edit.setClearButtonEnabled(True)
        tb.addWidget(self.filter_edit)

        tb.addWidget(vline())

        self.scan_subfolders_check = QCheckBox("Scan subfolders")
        self.scan_subfolders_check.setChecked(self._scan_subfolders)
        self.scan_subfolders_check.setMinimumHeight(30)
        self.scan_subfolders_check.setToolTip("Include files in subfolders")
        tb.addWidget(self.scan_subfolders_check)

        tb.addWidget(QLabel("Max depth:"))
        self.max_depth_spin = QSpinBox()
        self.max_depth_spin.setRange(1, 1000)
        self.max_depth_spin.setValue(self._max_depth)
        self.max_depth_spin.setMinimumHeight(30)
        self.max_depth_spin.setEnabled(self._scan_subfolders)
        self.max_depth_spin.setToolTip("Maximum subfolder depth to scan")
        tb.addWidget(self.max_depth_spin)

        tb.addWidget(vline())

        self.preview_check = QCheckBox("Preview")
        self.preview_check.setChecked(True)
        self.preview_check.setMinimumHeight(30)
        tb.addWidget(self.preview_check)

        tb.addWidget(vline())

        self.play_btn = QPushButton("Play")
        self.play_btn.setObjectName("playButton")
        self.play_btn.setFixedHeight(30)
        self.play_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self.play_btn.setIconSize(QSize(16, 16))
        f = self.play_btn.font()
        self.play_btn.setFont(f)
        tb.addWidget(self.play_btn)

        layout.addWidget(top_bar)

        # Splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(7)

        # ── Left panel: favorites + folder tree ──────────────────────────────
        left = QWidget()
        left.setObjectName("leftPane")
        left.setMinimumWidth(200)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        left_splitter = QSplitter(Qt.Orientation.Vertical)
        left_splitter.setHandleWidth(7)

        # Favorites section
        fav_widget = QWidget()
        fav_widget_layout = QVBoxLayout(fav_widget)
        fav_widget_layout.setContentsMargins(0, 0, 0, 0)
        fav_widget_layout.setSpacing(4)

        fav_header = QHBoxLayout()
        fav_lbl = QLabel("Favorites")
        fav_lbl_font = fav_lbl.font()
        fav_lbl_font.setBold(True)
        fav_lbl.setFont(fav_lbl_font)
        fav_header.addWidget(fav_lbl)
        fav_header.addStretch()
        self.btn_add_fav = QPushButton("Add")
        self.btn_add_fav.setIcon(QIcon.fromTheme("list-add"))
        self.btn_add_fav.setIconSize(QSize(16, 16))
        self.btn_add_fav.setToolTip("Add current folder to bookmarks")
        fav_header.addWidget(self.btn_add_fav)

        self.btn_rename_fav = QPushButton("Rename")
        self.btn_rename_fav.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView))
        self.btn_rename_fav.setIconSize(QSize(16, 16))
        self.btn_rename_fav.setToolTip("Rename selected bookmark")
        self.btn_rename_fav.setEnabled(False)
        fav_header.addWidget(self.btn_rename_fav)

        fav_widget_layout.addLayout(fav_header)

        self.fav_list = QListWidget()
        self.fav_list.setObjectName("favoritesList")
        self.fav_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.fav_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.fav_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        fav_widget_layout.addWidget(self.fav_list)

        left_splitter.addWidget(fav_widget)

        # Folder tree
        self.fs_model = QFileSystemModel()
        self.fs_model.setFilter(QDir.Filter.AllDirs | QDir.Filter.NoDotAndDotDot)
        self.fs_model.setRootPath("")

        self.tree = QTreeView()
        self.tree.setObjectName("folderTree")
        self.tree.setModel(self.fs_model)
        self.tree.setHeaderHidden(True)
        for col in range(1, self.fs_model.columnCount()):
            self.tree.hideColumn(col)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        left_splitter.addWidget(self.tree)

        left_splitter.setSizes([160, 400])
        left_layout.addWidget(left_splitter)

        splitter.addWidget(left)

        self.table = QTableWidget()
        self.table.setObjectName("fileTable")
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Name", "Size", "Duration", "Date Created"])
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for c in (1, 2, 3):
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSortIndicatorShown(True)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        # ── Preview panel (video area + seek bar) ────────────────────────────
        self.preview_panel = QWidget()
        self.preview_panel.setObjectName("previewPane")
        self.preview_panel.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        pp_layout = QVBoxLayout(self.preview_panel)
        pp_layout.setContentsMargins(6, 6, 6, 6)
        pp_layout.setSpacing(8)

        # Video area — mpv embeds here via XID
        self.preview_container = QWidget()
        self.preview_container.setMinimumHeight(60)
        self.preview_container.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
        self.preview_container.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.preview_container.setStyleSheet("background: black;")
        pp_layout.addWidget(self.preview_container, 1)

        # Seek bar row
        seek_row = QHBoxLayout()
        seek_row.setContentsMargins(2, 2, 2, 2)
        seek_row.setSpacing(6)

        self.btn_play_pause = QToolButton()
        self.btn_play_pause.setObjectName("previewControlButton")
        self.btn_play_pause.setFixedSize(34, 34)
        self.btn_play_pause.setIconSize(QSize(18, 18))
        self.btn_play_pause.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.btn_play_pause.setAutoRaise(False)
        self.btn_play_pause.setToolTip("Play / Pause")
        seek_row.addWidget(self.btn_play_pause)

        self.btn_mute = QToolButton()
        self.btn_mute.setObjectName("previewControlButton")
        self.btn_mute.setFixedSize(34, 34)
        self.btn_mute.setIconSize(QSize(18, 18))
        self.btn_mute.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.btn_mute.setAutoRaise(False)
        self.btn_mute.setToolTip("Mute / Unmute")
        seek_row.addWidget(self.btn_mute)

        self._set_play_pause_icon(True)
        self._set_mute_icon(True)

        self.vol_slider = QSlider(Qt.Orientation.Horizontal)
        self.vol_slider.setObjectName("volumeSlider")
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(100)
        self.vol_slider.setFixedWidth(96)
        self.vol_slider.setToolTip("Volume")
        seek_row.addWidget(self.vol_slider)

        self.lbl_pos = QLabel("0:00")
        self.lbl_pos.setFixedWidth(46)
        self.lbl_pos.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        seek_row.addWidget(self.lbl_pos)

        self.seek_slider = SeekSlider(Qt.Orientation.Horizontal)
        self.seek_slider.setObjectName("seekSlider")
        self.seek_slider.setRange(0, 10000)
        self.seek_slider.setValue(0)
        seek_row.addWidget(self.seek_slider, 1)

        self.lbl_dur = QLabel("0:00")
        self.lbl_dur.setFixedWidth(46)
        self.lbl_dur.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        seek_row.addWidget(self.lbl_dur)

        pp_layout.addLayout(seek_row)

        right_splitter = QSplitter(Qt.Orientation.Vertical)
        right_splitter.setHandleWidth(7)
        right_splitter.addWidget(self.table)
        right_splitter.addWidget(self.preview_panel)
        right_splitter.setSizes([420, 220])
        splitter.addWidget(right_splitter)

        splitter.setSizes([240, 860])
        layout.addWidget(splitter, 1)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

    # ── Connect signals ───────────────────────────────────────────────────────

    def _connect(self):
        self.btn_go.clicked.connect(lambda: self._navigate(self.path_edit.text().strip(), scroll=True))
        self.path_edit.returnPressed.connect(lambda: self._navigate(self.path_edit.text().strip(), scroll=True))
        self.tree.clicked.connect(self._on_tree_click)
        self.tree.customContextMenuRequested.connect(self._tree_context_menu)
        self.type_combo.currentTextChanged.connect(self._on_type_changed)
        self.filter_edit.textChanged.connect(self._on_filter_changed)
        self.scan_subfolders_check.toggled.connect(self._on_scan_subfolders_changed)
        self.max_depth_spin.valueChanged.connect(self._on_max_depth_changed)
        self.play_btn.clicked.connect(self._play)
        self.table.cellDoubleClicked.connect(self._on_double_click)
        self.table.customContextMenuRequested.connect(self._table_context_menu)
        self.btn_add_fav.clicked.connect(lambda: self._add_favorite(self._current_folder))
        self.btn_rename_fav.clicked.connect(self._rename_selected_fav)
        self.fav_list.itemClicked.connect(self._on_fav_click)
        self.fav_list.currentItemChanged.connect(self._on_fav_selection_changed)
        self.fav_list.customContextMenuRequested.connect(self._fav_context_menu)
        self.fav_list.model().rowsMoved.connect(self._on_fav_reordered)
        self.preview_check.toggled.connect(self._on_preview_toggle)
        self.table.selectionModel().currentRowChanged.connect(self._on_selection_changed)
        self.seek_slider.sliderPressed.connect(self._on_seek_pressed)
        self.seek_slider.sliderMoved.connect(self._on_seek_moved)
        self.seek_slider.sliderReleased.connect(self._on_seek_released)
        self.btn_play_pause.clicked.connect(self._on_play_pause_clicked)
        self.btn_mute.clicked.connect(self._on_mute_clicked)
        self.vol_slider.valueChanged.connect(self._on_vol_slider_changed)
        self._mpv_bridge.time_pos_changed.connect(self._on_mpv_time_pos)
        self._mpv_bridge.duration_changed.connect(self._on_mpv_duration)
        self._mpv_bridge.pause_changed.connect(self._on_mpv_pause)
        self._mpv_bridge.mute_changed.connect(self._on_mpv_mute)
        self._mpv_bridge.volume_changed.connect(self._on_mpv_volume)
        self._mpv_bridge.preview_dbl_clicked.connect(self._open_preview_in_player)

    # ── Navigation ────────────────────────────────────────────────────────────

    def _navigate(self, path: str, scroll: bool = False):
        path = os.path.expanduser(path)
        if not os.path.isdir(path):
            self.status_bar.showMessage(f"Not a directory: {path}")
            return
        self._current_folder = path
        self.path_edit.setText(path)
        idx = self.fs_model.index(path)
        self.tree.setCurrentIndex(idx)
        if scroll:
            self.tree.scrollTo(idx, QAbstractItemView.ScrollHint.PositionAtCenter)
        self._stop_preview()
        self._preview_path = ""
        self.seek_slider.setValue(0)
        self.lbl_pos.setText("0:00")
        self.lbl_dur.setText("0:00")
        self._set_play_pause_icon(True)
        self._scan_folder()

    def _on_tree_click(self, idx: QModelIndex):
        self._navigate(self.fs_model.filePath(idx))

    # ── Scanning ──────────────────────────────────────────────────────────────

    def _scan_folder(self):
        self._stop_worker()
        files = []
        folders = [(self._current_folder, 0)]
        max_depth = self._max_depth if self._scan_subfolders else 0

        while folders:
            folder, depth = folders.pop()
            try:
                entries = list(os.scandir(folder))
            except PermissionError:
                if folder == self._current_folder:
                    self.status_bar.showMessage(f"Permission denied: {self._current_folder}")
                    return
                continue

            for entry in entries:
                try:
                    if entry.is_file(follow_symlinks=True):
                        stat = entry.stat()
                        files.append({
                            "path":     entry.path,
                            "name":     entry.name,
                            "ext":      Path(entry.name).suffix.lower(),
                            "size":     stat.st_size,
                            "ctime":    stat.st_ctime,
                            "duration": self._dur_cache.get(entry.path, -1),
                        })
                    elif depth < max_depth and entry.is_dir(follow_symlinks=False):
                        folders.append((entry.path, depth + 1))
                except OSError:
                    continue

        self._all_files = files
        self._render_table()
        self._maybe_fetch_durations()
        self.table.clearSelection()
        self.table.setCurrentIndex(self.table.model().index(-1, -1))

    def _on_scan_subfolders_changed(self, checked: bool):
        self._scan_subfolders = checked
        self.max_depth_spin.setEnabled(checked)
        _update_config(scan_subfolders=checked)
        self._scan_folder()

    def _on_max_depth_changed(self, depth: int):
        self._max_depth = depth
        _update_config(max_depth=depth)
        if self._scan_subfolders:
            self._scan_folder()

    def _on_type_changed(self):
        self._render_table()
        self._maybe_fetch_durations()

    def _on_filter_changed(self):
        self._render_table()
        self._maybe_fetch_durations()

    # ── Rendering ─────────────────────────────────────────────────────────────

    def _visible_files(self) -> list[dict]:
        exts = FILE_TYPES[self.type_combo.currentText()]
        needle = self.filter_edit.text().lower()
        files = self._all_files if not exts else [f for f in self._all_files if f["ext"] in exts]
        if needle:
            files = [f for f in files if needle in f["name"].lower()]
        return files

    def _render_table(self):
        files = self._visible_files()

        # Disable sorting while populating to avoid O(n²) re-sorts per insertion
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(files))

        for row, f in enumerate(files):
            name_item = QTableWidgetItem(f["name"])
            name_item.setData(Qt.ItemDataRole.UserRole, f["path"])
            name_item.setToolTip(f["path"])

            size_item = NumericItem(fmt_size(f["size"]), float(f["size"]))
            size_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            dur_text = "…" if f["duration"] < 0 else fmt_duration(f["duration"])
            dur_item = NumericItem(dur_text, f["duration"])
            dur_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            date_item = NumericItem(
                datetime.fromtimestamp(f["ctime"]).strftime("%Y-%m-%d %H:%M"),
                f["ctime"],
            )
            date_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            self.table.setItem(row, 0, name_item)
            self.table.setItem(row, 1, size_item)
            self.table.setItem(row, 2, dur_item)
            self.table.setItem(row, 3, date_item)

        self.table.setSortingEnabled(True)
        self.status_bar.showMessage(f"{len(files)} file(s)  •  {self._current_folder}")

    # ── Duration fetching ─────────────────────────────────────────────────────

    def _maybe_fetch_durations(self):
        if self.type_combo.currentText() not in ("Videos", "Audio"):
            return
        need = [f["path"] for f in self._visible_files() if f["duration"] < 0]
        if not need:
            return
        self._stop_worker()
        self._worker = DurationWorker(need)
        self._worker.result_ready.connect(self._on_duration)
        self._worker.start()

    def _on_duration(self, path: str, secs: float):
        self._dur_cache[path] = secs
        for f in self._all_files:
            if f["path"] == path:
                f["duration"] = secs
                break

        # Update only the duration cell for this path
        for row in range(self.table.rowCount()):
            name_item = self.table.item(row, 0)
            if name_item and name_item.data(Qt.ItemDataRole.UserRole) == path:
                dur_item = self.table.item(row, 2)
                if dur_item:
                    # Disable sorting to update without triggering a re-sort per cell
                    self.table.setSortingEnabled(False)
                    dur_item.setText(fmt_duration(secs))
                    dur_item.setData(SORT_ROLE, secs)
                    self.table.setSortingEnabled(True)
                break

    def _stop_worker(self):
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait()
        self._worker = None

    # ── Playback ──────────────────────────────────────────────────────────────

    def _table_ordered_files(self) -> list[dict]:
        """Return files in the exact visual order of the table."""
        path_to_file = {f["path"]: f for f in self._all_files}
        result = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item:
                f = path_to_file.get(item.data(Qt.ItemDataRole.UserRole))
                if f:
                    result.append(f)
        return result

    def _on_double_click(self, row: int, _col: int):
        self._play(start_row=row)

    def _table_context_menu(self, pos: QPoint):
        item = self.table.itemAt(pos)
        if not item:
            return
        row = self.table.rowAt(pos.y())
        path = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        if not path:
            return
        menu = QMenu(self)
        open_act = menu.addAction("Show in File Manager")
        menu.addSeparator()
        trash_act = menu.addAction("Move to Trash")
        delete_act = menu.addAction("Delete Permanently")
        chosen = menu.exec(self.table.viewport().mapToGlobal(pos))
        if chosen == open_act:
            self._show_in_file_manager(path)
        elif chosen == trash_act:
            self._trash_file(path)
        elif chosen == delete_act:
            self._delete_file(path)

    def _show_in_file_manager(self, path: str):
        uri = Path(path).as_uri()
        try:
            subprocess.Popen([
                "dbus-send", "--session",
                "--dest=org.freedesktop.FileManager1",
                "--type=method_call",
                "/org/freedesktop/FileManager1",
                "org.freedesktop.FileManager1.ShowItems",
                f"array:string:{uri}", "string:",
            ])
        except FileNotFoundError:
            subprocess.Popen(["xdg-open", str(Path(path).parent)])

    def _trash_file(self, path: str):
        try:
            send2trash.send2trash(path)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not move to trash:\n{e}")
            return
        self._remove_file_from_view(path)

    def _delete_file(self, path: str):
        name = Path(path).name
        reply = QMessageBox.question(
            self, "Delete Permanently",
            f"Permanently delete '{name}'?\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            os.remove(path)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not delete file:\n{e}")
            return
        self._remove_file_from_view(path)

    def _remove_file_from_view(self, path: str):
        self._all_files = [f for f in self._all_files if f["path"] != path]
        self._dur_cache.pop(path, None)
        for row in range(self.table.rowCount()):
            if self.table.item(row, 0).data(Qt.ItemDataRole.UserRole) == path:
                self.table.removeRow(row)
                break
        self.status_bar.showMessage(
            f"{self.table.rowCount()} file(s)  •  {self._current_folder}"
        )

    def _play(self, start_row: int = 0):
        ordered = self._table_ordered_files()
        if not ordered:
            QMessageBox.information(self, "Nothing to play", "No files match the current filter.")
            return

        # Clamp start index
        start_row = max(0, min(start_row, len(ordered) - 1))

        playlist = os.path.join(tempfile.gettempdir(), "fila.m3u8")
        with open(playlist, "w", encoding="utf-8") as fh:
            fh.write("#EXTM3U\n")
            for f in ordered:
                dur = int(f["duration"]) if f["duration"] > 0 else -1
                fh.write(f"#EXTINF:{dur},{f['name']}\n")
                fh.write(f"{f['path']}\n")

        cmd = ["mpv", f"--playlist-start={start_row}", playlist]

        try:
            subprocess.Popen(cmd)
            self._stop_preview()
            self.seek_slider.setValue(0)
            self.lbl_pos.setText("0:00")
            start_name = ordered[start_row]["name"]
            self.status_bar.showMessage(
                f"Launched mpv — {len(ordered)} file(s), starting at: {start_name}"
            )
        except FileNotFoundError:
            QMessageBox.critical(
                self, "Player not found",
                "mpv was not found. Is it installed and in PATH?",
            )

    # ── Preview player ────────────────────────────────────────────────────────

    def _on_preview_toggle(self, checked: bool):
        self.preview_panel.setVisible(checked)
        if not checked:
            self._stop_preview()

    def _on_selection_changed(self, _current, _previous):
        if self.preview_check.isChecked():
            self._preview_timer.start()

    def _do_preview(self):
        row = self.table.currentRow()
        if row < 0:
            return
        item = self.table.item(row, 0)
        if item:
            self._preview_file(item.data(Qt.ItemDataRole.UserRole))

    def _ensure_mpv(self):
        if self._mpv is not None:
            return
        locale.setlocale(locale.LC_NUMERIC, "C")  # guard: Qt may have reset it
        wid = int(self.preview_container.winId())
        self._mpv = mpv.MPV(
            wid=str(wid),
            vo="x11",
            mute=True,
            keep_open="yes",
            keep_open_pause=False,
            input_default_bindings=False,
            input_vo_keyboard=False,
            osc=False,
        )

        bridge = self._mpv_bridge

        # Double-click in the video area → open in external player.
        # mpv owns the X11 mouse events, so we hook into its input system directly.
        self._mpv.register_key_binding('MOUSE_BTN0_DBL',
                                       lambda *_: bridge.preview_dbl_clicked.emit())

        @self._mpv.property_observer("time-pos")
        def _on_pos(name, val):
            if val is not None:
                bridge.time_pos_changed.emit(float(val))

        @self._mpv.property_observer("duration")
        def _on_dur(name, val):
            if val is not None:
                bridge.duration_changed.emit(float(val))

        @self._mpv.property_observer("pause")
        def _on_pause(name, val):
            if val is not None:
                bridge.pause_changed.emit(bool(val))

        @self._mpv.property_observer("mute")
        def _on_mute(name, val):
            if val is not None:
                bridge.mute_changed.emit(bool(val))

        @self._mpv.property_observer("volume")
        def _on_vol(name, val):
            if val is not None:
                bridge.volume_changed.emit(float(val))

    def _preview_file(self, path: str):
        try:
            self._ensure_mpv()
            self._preview_path = path
            self._mpv_duration = 0.0
            self._mpv_pos = 0.0
            self.seek_slider.setValue(0)
            self.lbl_pos.setText("0:00")
            self.lbl_dur.setText("0:00")
            self._mpv.loadfile(path, mode="replace")
        except Exception as e:
            self.status_bar.showMessage(f"Preview error: {e}")

    def _stop_preview(self):
        if self._mpv is not None:
            try:
                self._mpv.stop()
            except Exception:
                pass
        self._set_play_pause_icon(True)

    # ── Seek bar ──────────────────────────────────────────────────────────────

    def _on_mpv_time_pos(self, secs: float):
        self._mpv_pos = secs
        if self._seeking or self._mpv_duration <= 0:
            return
        val = int(secs / self._mpv_duration * 10000)
        self.seek_slider.setValue(val)
        self.lbl_pos.setText(fmt_duration(secs))

    def _on_mpv_duration(self, secs: float):
        self._mpv_duration = secs
        self.lbl_dur.setText(fmt_duration(secs))

    def _on_seek_pressed(self):
        self._seeking = True

    def _seek_to_slider_value(self) -> None:
        if self._mpv is None or self._mpv_duration <= 0:
            return
        target = self.seek_slider.value() / 10000 * self._mpv_duration
        self._mpv_pos = target
        self.lbl_pos.setText(fmt_duration(target))
        try:
            self._mpv.seek(target, "absolute")
        except Exception:
            pass

    def _on_seek_moved(self, _value: int):
        if self._seeking:
            self._seek_to_slider_value()

    def _on_seek_released(self):
        self._seeking = False
        self._seek_to_slider_value()

    def _on_play_pause_clicked(self):
        if self._mpv is not None:
            try:
                # Let mpv toggle its own state; reading pause here can be stale
                # while the previous command is still being processed.
                self._mpv.command("cycle", "pause")
            except Exception:
                pass

    def _on_mute_clicked(self):
        if self._mpv is not None:
            try:
                self._mpv.mute = not self._mpv.mute
            except Exception:
                pass

    def _on_mpv_pause(self, paused: bool):
        self._set_play_pause_icon(paused)

    def _on_mpv_mute(self, muted: bool):
        self._mpv_muted = muted
        self._set_mute_icon(muted)

    def _on_vol_slider_changed(self, value: int):
        if self._mpv is not None:
            try:
                self._mpv.volume = float(value)
            except Exception:
                pass

    def _on_mpv_volume(self, value: float):
        # Block signals to avoid feedback loop back to _on_vol_slider_changed
        self.vol_slider.blockSignals(True)
        self.vol_slider.setValue(int(value))
        self.vol_slider.blockSignals(False)

    def _open_preview_in_player(self):
        if not self._preview_path:
            return
        pos = self._mpv_pos
        cmd = ["mpv", f"--start={pos:.3f}"]
        if self._mpv_muted:
            cmd.append("--mute=yes")
        cmd.append(self._preview_path)

        try:
            subprocess.Popen(cmd)
            self._stop_preview()
            self.seek_slider.setValue(0)
            self.lbl_pos.setText("0:00")
            self.status_bar.showMessage(
                f"Opened in mpv at {fmt_duration(pos)}: {Path(self._preview_path).name}"
            )
        except FileNotFoundError:
            QMessageBox.critical(self, "Player not found",
                                 "mpv was not found. Is it installed and in PATH?")

    # ── Favorites ─────────────────────────────────────────────────────────────

    def _populate_fav_list(self):
        current_path = None
        cur = self.fav_list.currentItem()
        if cur:
            current_path = cur.data(Qt.ItemDataRole.UserRole)
        self.fav_list.clear()
        for bm in self._favorites:
            item = QListWidgetItem(bm["name"])
            item.setData(Qt.ItemDataRole.UserRole, bm["path"])
            item.setToolTip(bm["path"])
            self.fav_list.addItem(item)
            if bm["path"] == current_path:
                self.fav_list.setCurrentItem(item)

    def _add_favorite(self, path: str):
        if not path or not os.path.isdir(path):
            return
        if any(bm["path"] == path for bm in self._favorites):
            return
        self._favorites.append({"path": path, "name": Path(path).name or path})
        _update_config(favorites=self._favorites)
        self._populate_fav_list()

    def _remove_favorite(self, path: str):
        self._favorites = [bm for bm in self._favorites if bm["path"] != path]
        _update_config(favorites=self._favorites)
        self._populate_fav_list()

    def _rename_favorite(self, path: str):
        bm = next((b for b in self._favorites if b["path"] == path), None)
        if bm is None:
            return
        name, ok = QInputDialog.getText(
            self, "Rename Bookmark", "Name:", text=bm["name"]
        )
        if ok and name.strip():
            bm["name"] = name.strip()
            _update_config(favorites=self._favorites)
            self._populate_fav_list()

    def _rename_selected_fav(self):
        item = self.fav_list.currentItem()
        if item:
            self._rename_favorite(item.data(Qt.ItemDataRole.UserRole))

    def _on_fav_reordered(self):
        self._favorites = [
            {"path": self.fav_list.item(i).data(Qt.ItemDataRole.UserRole),
             "name": self.fav_list.item(i).text()}
            for i in range(self.fav_list.count())
        ]
        _update_config(favorites=self._favorites)

    def _on_fav_selection_changed(self, current, _previous):
        self.btn_rename_fav.setEnabled(current is not None)

    def _on_fav_click(self, item: QListWidgetItem):
        self._navigate(item.data(Qt.ItemDataRole.UserRole), scroll=True)

    def _fav_context_menu(self, pos: QPoint):
        item = self.fav_list.itemAt(pos)
        if not item:
            return
        path = item.data(Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        rename_act = menu.addAction("Rename")
        remove_act = menu.addAction("Remove")
        chosen = menu.exec(self.fav_list.viewport().mapToGlobal(pos))
        if chosen == rename_act:
            self._rename_favorite(path)
        elif chosen == remove_act:
            self._remove_favorite(path)

    def _tree_context_menu(self, pos: QPoint):
        idx = self.tree.indexAt(pos)
        path = self.fs_model.filePath(idx) if idx.isValid() else self._current_folder
        if not path:
            return
        menu = QMenu(self)
        add_act = menu.addAction("Add to Favorites")
        if menu.exec(self.tree.viewport().mapToGlobal(pos)) == add_act:
            self._add_favorite(path)

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def closeEvent(self, event):
        _update_config(maximized=self.isMaximized())
        self._preview_timer.stop()
        self._stop_worker()
        if self._mpv is not None:
            try:
                self._mpv.terminate()
            except Exception:
                pass
            self._mpv = None
        event.accept()


# ── Qt/desktop integration ─────────────────────────────────────────────────────

APP_NAME = "Fila"
_SYSTEM_QT_PLUGIN_PATHS = (
    "/usr/lib/qt6/plugins",
    "/usr/lib64/qt6/plugins",
    "/usr/lib/x86_64-linux-gnu/qt6/plugins",
)


def _running_on_kde() -> bool:
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "")
    session = os.environ.get("DESKTOP_SESSION", "")
    return "kde" in f"{desktop}:{session}".lower() or bool(os.environ.get("KDE_FULL_SESSION"))


def _qt_version_compatible() -> bool:
    """Avoid loading a system style built for a different Qt ABI."""
    commands = (("qtpaths6", "--qt-version"), ("qmake6", "-query", "QT_VERSION"))
    for command in commands:
        try:
            result = subprocess.run(
                command, capture_output=True, text=True, timeout=1, check=False
            )
        except (OSError, subprocess.SubprocessError):
            continue
        system_version = result.stdout.strip()
        if system_version:
            # Qt plugins can depend on patch-level private ABI details.  A
            # matching major/minor version is not sufficient for a bundled
            # PySide6 installation.
            return system_version == qVersion()
    return False


def _plasma_widget_style() -> str:
    settings_path = Path.home() / ".config" / "kdeglobals"
    if settings_path.is_file():
        style = QSettings(
            str(settings_path), QSettings.Format.IniFormat
        ).value("KDE/widgetStyle", "", type=str).strip()
        if style:
            return style
    try:
        result = subprocess.run(
            ["kreadconfig6", "--group", "KDE", "--key", "widgetStyle"],
            capture_output=True, text=True, timeout=1, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip()


def _configure_plugin_path() -> tuple[bool, bool]:
    bundled = str(QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath))
    configured = [bundled]
    configured.extend(os.environ.get("QT_PLUGIN_PATH", "").split(os.pathsep))
    has_kde_theme = False
    has_gtk3_theme = False

    for candidate in _SYSTEM_QT_PLUGIN_PATHS:
        system_path = Path(candidate)
        if not system_path.is_dir() or not _qt_version_compatible():
            continue
        platformthemes = system_path / "platformthemes"
        styles = system_path / "styles"
        has_kde_theme = any(
            "kde" in plugin.name.lower() and plugin.suffix == ".so"
            for plugin in platformthemes.glob("*")
        )
        has_gtk3_theme = (platformthemes / "libqgtk3.so").is_file()
        has_style_plugin = (styles / "breeze6.so").is_file()
        if has_kde_theme or has_gtk3_theme or has_style_plugin:
            configured.append(candidate)
            break

    paths = []
    for path in configured:
        if path and path not in paths:
            paths.append(path)
    os.environ["QT_PLUGIN_PATH"] = os.pathsep.join(paths)
    return has_kde_theme, has_gtk3_theme


def configure_qt_theme() -> str:
    """Configure Qt before QApplication while respecting explicit user choices."""
    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
    user_style = "QT_STYLE_OVERRIDE" in os.environ
    user_platform_theme = "QT_QPA_PLATFORMTHEME" in os.environ
    kde = _running_on_kde()

    has_kde_theme, has_gtk3_theme = _configure_plugin_path()

    if not user_platform_theme and ((kde and has_kde_theme) or (not kde and has_gtk3_theme)):
        os.environ["QT_QPA_PLATFORMTHEME"] = "kde" if kde else "gtk3"
    if kde and has_kde_theme and not user_style:
        style = _plasma_widget_style()
        if style:
            os.environ["QT_STYLE_OVERRIDE"] = style

    if user_style or user_platform_theme:
        return "user override"
    if kde and "QT_STYLE_OVERRIDE" in os.environ:
        return f"kde/{os.environ['QT_STYLE_OVERRIDE']}"
    return os.environ.get("QT_QPA_PLATFORMTHEME", "built-in")


def ensure_placeholder_text_contrast(app: QApplication) -> None:
    palette = app.palette()
    base = palette.color(QPalette.ColorRole.Base)
    placeholder = palette.color(QPalette.ColorRole.PlaceholderText)
    text = palette.color(QPalette.ColorRole.Text)
    distance = sum(
        abs(a - b)
        for a, b in zip(base.getRgb()[:3], placeholder.getRgb()[:3])
    )
    if distance < 45:
        placeholder = text
        placeholder.setAlpha(160)
        palette.setColor(
            QPalette.ColorGroup.Active,
            QPalette.ColorRole.PlaceholderText,
            placeholder,
        )
        palette.setColor(
            QPalette.ColorGroup.Inactive,
            QPalette.ColorRole.PlaceholderText,
            placeholder,
        )
        app.setPalette(palette)


def report_qt_theme(app: QApplication, configured_mode: str) -> None:
    """Report configured and effective Qt integration without masking failures."""
    runtime_style = app.style().objectName()
    expected_style = os.environ.get("QT_STYLE_OVERRIDE", "")
    if expected_style and runtime_style.lower() in {"fusion", "windows"}:
        print(
            f"Fila Qt warning: requested style {expected_style!r} was not loaded; "
            f"using {runtime_style!r}",
            file=sys.stderr,
        )
    print(
        f"Fila Qt theme: {configured_mode}; "
        f"platform={os.environ.get('QT_QPA_PLATFORMTHEME', '')}; "
        f"style={expected_style}; runtime={runtime_style}"
    )


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    # mpv wid embedding needs X11 window IDs; force XCB so winId() returns a
    # real XID even under Wayland (runs via XWayland transparently).
    theme_mode = configure_qt_theme()
    QApplication.setApplicationName(APP_NAME)
    app = QApplication(sys.argv)
    ensure_placeholder_text_contrast(app)
    # QApplication resets LC_NUMERIC via setlocale(LC_ALL,""); restore for mpv.
    locale.setlocale(locale.LC_NUMERIC, "C")
    _icon = Path(__file__).parent / "icon.png"
    if _icon.exists():
        app.setWindowIcon(QIcon(str(_icon)))
    report_qt_theme(app, theme_mode)
    win = MainWindow()
    app.installEventFilter(win)
    if _load_config().get("maximized", False):
        win.showMaximized()
    else:
        win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
