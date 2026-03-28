#!/usr/bin/env python3
"""MKVideoPlaylister — browse folders, filter by type, sort, generate .m3u8, play."""

import locale
import os
import sys
import json
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

locale.setlocale(locale.LC_NUMERIC, "C")

import mpv

from PySide6.QtCore import Qt, QObject, QEvent, QThread, Signal, QModelIndex, QDir, QPoint, QTimer
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QSplitter, QTreeView, QComboBox, QLabel, QPushButton,
    QFileSystemModel, QHeaderView, QTableWidget, QTableWidgetItem,
    QAbstractItemView, QStatusBar, QLineEdit, QFrame, QMessageBox,
    QListWidget, QListWidgetItem, QMenu, QCheckBox, QSlider, QStyle,
    QInputDialog,
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

PLAYERS: dict[str, str] = {
    "mpv":             "mpv",
    "vlc":             "vlc",
    "mplayer":         "mplayer",
    "cvlc (headless)": "cvlc",
}

# Role used to store the raw numeric/string sort key alongside display text
SORT_ROLE = Qt.ItemDataRole.UserRole + 1

# ── Config ────────────────────────────────────────────────────────────────────

CONFIG_PATH = Path.home() / ".config" / "mkplaylister" / "mkplaylister.json"


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
    return ln


# ── Seek slider that jumps to click position ─────────────────────────────────

class SeekSlider(QSlider):
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            val = QStyle.sliderValueFromPosition(
                self.minimum(), self.maximum(),
                event.position().toPoint().x(), self.width(),
            )
            self.setValue(val)
        super().mousePressEvent(event)


# ── Thread-safe bridge for mpv → Qt signals ──────────────────────────────────

class _MpvBridge(QObject):
    """Receives mpv property callbacks (called from mpv's thread) and re-emits
    them as Qt signals, which Qt queues onto the main thread automatically."""
    time_pos_changed  = Signal(float)   # current position in seconds
    duration_changed  = Signal(float)   # total duration in seconds
    pause_changed     = Signal(bool)    # True = paused
    mute_changed      = Signal(bool)    # True = muted
    volume_changed    = Signal(float)   # 0–100


# ── Main window ───────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MK Video Playlister")
        self.resize(1100, 680)

        self._all_files: list[dict] = []
        self._dur_cache: dict[str, float] = {}
        self._worker: DurationWorker | None = None
        self._current_folder: str = ""
        self._favorites: list[str] = _load_config().get("favorites", [])
        self._mpv: mpv.MPV | None = None
        self._mpv_bridge = _MpvBridge()
        self._mpv_duration: float = 0.0
        self._mpv_pos: float = 0.0           # current playback position in preview
        self._preview_path: str = ""         # file currently loaded in preview
        self._seeking: bool = False          # True while user drags the slider
        self._preview_timer = QTimer(singleShot=True, interval=250)
        self._preview_timer.timeout.connect(self._do_preview)

        self._build_ui()
        self._connect()
        self._populate_fav_list()
        self._navigate(str(Path.home()))

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(6, 6, 6, 4)
        layout.setSpacing(4)

        # Toolbar
        tb = QHBoxLayout()
        tb.setSpacing(6)

        tb.addWidget(QLabel("Path:"))
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("Folder path…")
        tb.addWidget(self.path_edit, 1)

        self.btn_go = QPushButton("Go")
        self.btn_go.setFixedWidth(40)
        tb.addWidget(self.btn_go)

        tb.addWidget(vline())

        tb.addWidget(QLabel("Type:"))
        self.type_combo = QComboBox()
        self.type_combo.addItems(FILE_TYPES.keys())
        self.type_combo.setCurrentText("Videos")
        self.type_combo.setMinimumWidth(90)
        tb.addWidget(self.type_combo)

        tb.addWidget(vline())

        self.preview_check = QCheckBox("Preview")
        self.preview_check.setChecked(True)
        tb.addWidget(self.preview_check)

        tb.addWidget(vline())

        tb.addWidget(QLabel("Player:"))
        self.player_combo = QComboBox()
        self.player_combo.addItems(PLAYERS.keys())
        self.player_combo.setCurrentText("mpv")
        self.player_combo.setMinimumWidth(130)
        tb.addWidget(self.player_combo)

        tb.addWidget(vline())

        self.play_btn = QPushButton("▶  Play")
        self.play_btn.setFixedHeight(30)
        f = self.play_btn.font()
        f.setBold(True)
        self.play_btn.setFont(f)
        self.play_btn.setStyleSheet(
            "QPushButton{background:#2d7d46;color:white;border-radius:4px;padding:0 14px}"
            "QPushButton:hover{background:#3a9e5a}"
            "QPushButton:pressed{background:#1f5c32}"
        )
        tb.addWidget(self.play_btn)

        layout.addLayout(tb)

        # Splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ── Left panel: favorites + folder tree ──────────────────────────────
        left = QWidget()
        left.setMinimumWidth(200)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(2)

        # Favorites header row
        fav_header = QHBoxLayout()
        fav_lbl = QLabel("Favorites")
        fav_lbl_font = fav_lbl.font()
        fav_lbl_font.setBold(True)
        fav_lbl.setFont(fav_lbl_font)
        fav_header.addWidget(fav_lbl)
        fav_header.addStretch()
        self.btn_add_fav = QPushButton("+ Add")
        self.btn_add_fav.setFixedHeight(22)
        self.btn_add_fav.setToolTip("Add current folder to bookmarks")
        fav_header.addWidget(self.btn_add_fav)

        self.btn_rename_fav = QPushButton("Rename")
        self.btn_rename_fav.setFixedHeight(22)
        self.btn_rename_fav.setToolTip("Rename selected bookmark")
        self.btn_rename_fav.setEnabled(False)
        fav_header.addWidget(self.btn_rename_fav)

        left_layout.addLayout(fav_header)

        self.fav_list = QListWidget()
        self.fav_list.setMaximumHeight(160)
        self.fav_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        left_layout.addWidget(self.fav_list)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        left_layout.addWidget(sep)

        # Folder tree
        self.fs_model = QFileSystemModel()
        self.fs_model.setFilter(QDir.Filter.AllDirs | QDir.Filter.NoDotAndDotDot)
        self.fs_model.setRootPath("")

        self.tree = QTreeView()
        self.tree.setModel(self.fs_model)
        self.tree.setHeaderHidden(True)
        for col in range(1, self.fs_model.columnCount()):
            self.tree.hideColumn(col)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        left_layout.addWidget(self.tree, 1)

        splitter.addWidget(left)

        self.table = QTableWidget()
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

        # ── Preview panel (video area + seek bar) ────────────────────────────
        self.preview_panel = QWidget()
        pp_layout = QVBoxLayout(self.preview_panel)
        pp_layout.setContentsMargins(0, 0, 0, 0)
        pp_layout.setSpacing(2)

        # Video area — mpv embeds here via XID
        self.preview_container = QWidget()
        self.preview_container.setMinimumHeight(60)
        self.preview_container.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
        self.preview_container.setStyleSheet("background: black;")
        self.preview_container.installEventFilter(self)
        pp_layout.addWidget(self.preview_container, 1)

        # Seek bar row
        seek_row = QHBoxLayout()
        seek_row.setContentsMargins(4, 0, 4, 2)
        seek_row.setSpacing(4)

        self.btn_play_pause = QPushButton("▶")
        self.btn_play_pause.setFixedSize(28, 22)
        self.btn_play_pause.setToolTip("Play / Pause")
        seek_row.addWidget(self.btn_play_pause)

        self.btn_mute = QPushButton("🔇")
        self.btn_mute.setFixedSize(28, 22)
        self.btn_mute.setToolTip("Mute / Unmute")
        seek_row.addWidget(self.btn_mute)

        self.vol_slider = QSlider(Qt.Orientation.Horizontal)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(100)
        self.vol_slider.setFixedWidth(80)
        self.vol_slider.setToolTip("Volume")
        seek_row.addWidget(self.vol_slider)

        self.lbl_pos = QLabel("0:00")
        self.lbl_pos.setFixedWidth(42)
        self.lbl_pos.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        seek_row.addWidget(self.lbl_pos)

        self.seek_slider = SeekSlider(Qt.Orientation.Horizontal)
        self.seek_slider.setRange(0, 10000)
        self.seek_slider.setValue(0)
        seek_row.addWidget(self.seek_slider, 1)

        self.lbl_dur = QLabel("0:00")
        self.lbl_dur.setFixedWidth(42)
        self.lbl_dur.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        seek_row.addWidget(self.lbl_dur)

        pp_layout.addLayout(seek_row)

        right_splitter = QSplitter(Qt.Orientation.Vertical)
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
        self.play_btn.clicked.connect(self._play)
        self.table.cellDoubleClicked.connect(self._on_double_click)
        self.btn_add_fav.clicked.connect(lambda: self._add_favorite(self._current_folder))
        self.btn_rename_fav.clicked.connect(self._rename_selected_fav)
        self.fav_list.itemClicked.connect(self._on_fav_click)
        self.fav_list.currentItemChanged.connect(self._on_fav_selection_changed)
        self.fav_list.customContextMenuRequested.connect(self._fav_context_menu)
        self.preview_check.toggled.connect(self._on_preview_toggle)
        self.table.selectionModel().currentRowChanged.connect(self._on_selection_changed)
        self.seek_slider.sliderPressed.connect(self._on_seek_pressed)
        self.seek_slider.sliderReleased.connect(self._on_seek_released)
        self.btn_play_pause.clicked.connect(self._on_play_pause_clicked)
        self.btn_mute.clicked.connect(self._on_mute_clicked)
        self.vol_slider.valueChanged.connect(self._on_vol_slider_changed)
        self._mpv_bridge.time_pos_changed.connect(self._on_mpv_time_pos)
        self._mpv_bridge.duration_changed.connect(self._on_mpv_duration)
        self._mpv_bridge.pause_changed.connect(self._on_mpv_pause)
        self._mpv_bridge.mute_changed.connect(self._on_mpv_mute)
        self._mpv_bridge.volume_changed.connect(self._on_mpv_volume)

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
        self.btn_play_pause.setText("▶")
        self._scan_folder()

    def _on_tree_click(self, idx: QModelIndex):
        self._navigate(self.fs_model.filePath(idx))

    # ── Scanning ──────────────────────────────────────────────────────────────

    def _scan_folder(self):
        self._stop_worker()
        files = []
        try:
            for entry in os.scandir(self._current_folder):
                if not entry.is_file(follow_symlinks=True):
                    continue
                stat = entry.stat()
                files.append({
                    "path":     entry.path,
                    "name":     entry.name,
                    "ext":      Path(entry.name).suffix.lower(),
                    "size":     stat.st_size,
                    "ctime":    stat.st_ctime,
                    "duration": self._dur_cache.get(entry.path, -1),
                })
        except PermissionError:
            self.status_bar.showMessage(f"Permission denied: {self._current_folder}")
            return

        self._all_files = files
        self._render_table()
        self._maybe_fetch_durations()

    def _on_type_changed(self):
        self._render_table()
        self._maybe_fetch_durations()

    # ── Rendering ─────────────────────────────────────────────────────────────

    def _visible_files(self) -> list[dict]:
        exts = FILE_TYPES[self.type_combo.currentText()]
        if exts:
            return [f for f in self._all_files if f["ext"] in exts]
        return list(self._all_files)

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

    def _play(self, start_row: int = 0):
        ordered = self._table_ordered_files()
        if not ordered:
            QMessageBox.information(self, "Nothing to play", "No files match the current filter.")
            return

        # Clamp start index
        start_row = max(0, min(start_row, len(ordered) - 1))

        playlist = os.path.join(tempfile.gettempdir(), "mk_playlister.m3u8")
        with open(playlist, "w", encoding="utf-8") as fh:
            fh.write("#EXTM3U\n")
            for f in ordered:
                dur = int(f["duration"]) if f["duration"] > 0 else -1
                fh.write(f"#EXTINF:{dur},{f['name']}\n")
                fh.write(f"{f['path']}\n")

        player_label = self.player_combo.currentText()
        player_bin   = PLAYERS[player_label]

        # Build the launch command depending on player capabilities
        if player_bin == "mpv":
            cmd = [player_bin, f"--playlist-start={start_row}", playlist]
        elif player_bin in ("vlc", "cvlc"):
            # VLC has no playlist-start flag for m3u files; reorder instead
            rotated = ordered[start_row:] + ordered[:start_row]
            with open(playlist, "w", encoding="utf-8") as fh:
                fh.write("#EXTM3U\n")
                for f in rotated:
                    dur = int(f["duration"]) if f["duration"] > 0 else -1
                    fh.write(f"#EXTINF:{dur},{f['name']}\n")
                    fh.write(f"{f['path']}\n")
            cmd = [player_bin, playlist]
        else:
            cmd = [player_bin, playlist]

        try:
            subprocess.Popen(cmd)
            self._stop_preview()
            self.seek_slider.setValue(0)
            self.lbl_pos.setText("0:00")
            start_name = ordered[start_row]["name"]
            self.status_bar.showMessage(
                f"Launched {player_bin} — {len(ordered)} file(s), starting at: {start_name}"
            )
        except FileNotFoundError:
            QMessageBox.critical(
                self, "Player not found",
                f"'{player_bin}' was not found. Is it installed and in PATH?",
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
            self.btn_play_pause.setText("⏸")
            self._mpv.loadfile(path, mode="replace")
        except Exception as e:
            self.status_bar.showMessage(f"Preview error: {e}")

    def _stop_preview(self):
        if self._mpv is not None:
            try:
                self._mpv.stop()
            except Exception:
                pass

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

    def _on_seek_released(self):
        self._seeking = False
        if self._mpv is not None and self._mpv_duration > 0:
            target = self.seek_slider.value() / 10000 * self._mpv_duration
            try:
                self._mpv.seek(target, "absolute")
            except Exception:
                pass

    def _on_play_pause_clicked(self):
        if self._mpv is not None:
            try:
                self._mpv.pause = not self._mpv.pause
            except Exception:
                pass

    def _on_mute_clicked(self):
        if self._mpv is not None:
            try:
                self._mpv.mute = not self._mpv.mute
            except Exception:
                pass

    def _on_mpv_pause(self, paused: bool):
        self.btn_play_pause.setText("▶" if paused else "⏸")

    def _on_mpv_mute(self, muted: bool):
        self.btn_mute.setText("🔇" if muted else "🔊")

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

    def eventFilter(self, obj, event):
        if (obj is self.preview_container
                and event.type() == QEvent.Type.MouseButtonDblClick
                and event.button() == Qt.MouseButton.LeftButton):
            self._open_preview_in_player()
            return True
        return super().eventFilter(obj, event)

    def _open_preview_in_player(self):
        if not self._preview_path:
            return
        player_bin = PLAYERS[self.player_combo.currentText()]
        pos = self._mpv_pos

        if player_bin == "mpv":
            cmd = [player_bin, f"--start={pos:.3f}", self._preview_path]
        elif player_bin in ("vlc", "cvlc"):
            cmd = [player_bin, f"--start-time={pos:.3f}", self._preview_path]
        elif player_bin == "mplayer":
            cmd = [player_bin, "-ss", f"{pos:.3f}", self._preview_path]
        else:
            cmd = [player_bin, self._preview_path]

        try:
            subprocess.Popen(cmd)
            self._stop_preview()
            self.seek_slider.setValue(0)
            self.lbl_pos.setText("0:00")
            self.status_bar.showMessage(
                f"Opened in {player_bin} at {fmt_duration(pos)}: {Path(self._preview_path).name}"
            )
        except FileNotFoundError:
            QMessageBox.critical(self, "Player not found",
                                 f"'{player_bin}' was not found.")

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


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    # mpv wid embedding needs X11 window IDs; force XCB so winId() returns a
    # real XID even under Wayland (runs via XWayland transparently).
    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")

    app = QApplication(sys.argv)
    # QApplication resets LC_NUMERIC via setlocale(LC_ALL,""); restore for mpv.
    locale.setlocale(locale.LC_NUMERIC, "C")
    app.setStyle("Fusion")
    win = MainWindow()
    if _load_config().get("maximized", False):
        win.showMaximized()
    else:
        win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
