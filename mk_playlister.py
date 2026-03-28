#!/usr/bin/env python3
"""MKVideoPlaylister — browse folders, filter by type, sort, generate .m3u8, play."""

import os
import sys
import json
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, QModelIndex, QDir, QPoint
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QSplitter, QTreeView, QComboBox, QLabel, QPushButton,
    QFileSystemModel, QHeaderView, QTableWidget, QTableWidgetItem,
    QAbstractItemView, QStatusBar, QLineEdit, QFrame, QMessageBox,
    QListWidget, QListWidgetItem, QMenu,
)

# ── File type definitions ─────────────────────────────────────────────────────

FILE_TYPES: dict[str, set[str]] = {
    "Videos": {
        ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm",
        ".m4v", ".mpg", ".mpeg", ".ts", ".mts", ".m2ts", ".vob",
        ".3gp", ".ogv", ".rm", ".rmvb",
    },
    "Images": {
        ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif",
        ".webp", ".svg", ".ico", ".heic", ".heif", ".avif",
    },
    "Audio": {
        ".mp3", ".flac", ".wav", ".aac", ".ogg", ".opus", ".m4a",
        ".wma", ".aiff", ".ape", ".mka",
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
        return json.loads(CONFIG_PATH.read_text())
    except Exception:
        return {"favorites": []}


def _save_config(data: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(data, indent=2))

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
        self.btn_add_fav.setToolTip("Add current folder to favorites")
        fav_header.addWidget(self.btn_add_fav)
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
        splitter.addWidget(self.table)

        splitter.setSizes([240, 860])
        layout.addWidget(splitter, 1)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

    # ── Connect signals ───────────────────────────────────────────────────────

    def _connect(self):
        self.btn_go.clicked.connect(lambda: self._navigate(self.path_edit.text().strip()))
        self.path_edit.returnPressed.connect(lambda: self._navigate(self.path_edit.text().strip()))
        self.tree.clicked.connect(self._on_tree_click)
        self.tree.customContextMenuRequested.connect(self._tree_context_menu)
        self.type_combo.currentTextChanged.connect(self._on_type_changed)
        self.play_btn.clicked.connect(self._play)
        self.table.cellDoubleClicked.connect(self._on_double_click)
        self.btn_add_fav.clicked.connect(lambda: self._add_favorite(self._current_folder))
        self.fav_list.itemClicked.connect(self._on_fav_click)
        self.fav_list.customContextMenuRequested.connect(self._fav_context_menu)

    # ── Navigation ────────────────────────────────────────────────────────────

    def _navigate(self, path: str):
        path = os.path.expanduser(path)
        if not os.path.isdir(path):
            self.status_bar.showMessage(f"Not a directory: {path}")
            return
        self._current_folder = path
        self.path_edit.setText(path)
        idx = self.fs_model.index(path)
        self.tree.setCurrentIndex(idx)
        self.tree.scrollTo(idx)
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
            start_name = ordered[start_row]["name"]
            self.status_bar.showMessage(
                f"Launched {player_bin} — {len(ordered)} file(s), starting at: {start_name}"
            )
        except FileNotFoundError:
            QMessageBox.critical(
                self, "Player not found",
                f"'{player_bin}' was not found. Is it installed and in PATH?",
            )

    # ── Favorites ─────────────────────────────────────────────────────────────

    def _populate_fav_list(self):
        self.fav_list.clear()
        for path in self._favorites:
            item = QListWidgetItem(Path(path).name or path)
            item.setData(Qt.ItemDataRole.UserRole, path)
            item.setToolTip(path)
            self.fav_list.addItem(item)

    def _add_favorite(self, path: str):
        if not path or not os.path.isdir(path):
            return
        if path in self._favorites:
            return
        self._favorites.append(path)
        _save_config({"favorites": self._favorites})
        self._populate_fav_list()

    def _remove_favorite(self, path: str):
        if path in self._favorites:
            self._favorites.remove(path)
            _save_config({"favorites": self._favorites})
            self._populate_fav_list()

    def _on_fav_click(self, item: QListWidgetItem):
        self._navigate(item.data(Qt.ItemDataRole.UserRole))

    def _fav_context_menu(self, pos: QPoint):
        item = self.fav_list.itemAt(pos)
        if not item:
            return
        menu = QMenu(self)
        remove_act = menu.addAction("Remove from Favorites")
        if menu.exec(self.fav_list.viewport().mapToGlobal(pos)) == remove_act:
            self._remove_favorite(item.data(Qt.ItemDataRole.UserRole))

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
        self._stop_worker()
        event.accept()


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
