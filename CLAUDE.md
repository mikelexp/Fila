# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Initial setup (creates venv, installs deps)
./setup.sh

# Run in development (no compilation)
./run.sh

# Compile to a single binary with Nuitka
./build.sh

# Install compiled binary to ~/.local/bin/
./install.sh

# Create distributable tarball (requires build first)
./package.sh
```

System dependencies required: `mpv`, `libmpv` (for embedded preview), `ffmpeg`/`ffprobe` (for duration fetching), `patchelf` (for Nuitka build).

Python dependencies: `PySide6`, `python-mpv`, `send2trash` (see `requirements.txt`).

## Architecture

The entire application lives in a single file: `fila.py`.

### Layout

Three-pane layout managed by two nested `QSplitter`s:
- **Horizontal splitter**: left panel | right panel
- **Left panel** contains a vertical `QSplitter`: favorites list (top) | folder tree (bottom) — both sections are user-resizable
- **Right panel** contains a vertical `QSplitter`: file table (top) | preview panel (bottom)

### Threading model

- **Main thread**: all Qt UI
- **`DurationWorker(QThread)`**: runs `ffprobe` in the background for each visible file, emits `result_ready(path, seconds)` — updates only the affected table cell, never rebuilds the table
- **mpv thread**: mpv property observers (`time-pos`, `duration`, `pause`, `mute`, `volume`) fire from mpv's internal thread; `_MpvBridge(QObject)` re-emits them as Qt signals, which Qt auto-queues to the main thread

### mpv embedding

mpv is embedded via X11 window ID (`wid`). Critical constraints:
- `QT_QPA_PLATFORM=xcb` must be set before `QApplication` — forces XWayland so `winId()` returns a real XID (not a Wayland surface handle)
- `vo="x11"` required — `vo=gpu` ignores `wid` and opens a separate window
- `locale.setlocale(LC_NUMERIC, "C")` must be called after `QApplication.__init__` because Qt internally calls `setlocale(LC_ALL, "")`, resetting it; mpv segfaults on non-C locales
- mpv is initialized lazily in `_ensure_mpv()` on first preview, not at startup
- `MOUSE_BTN0_DBL` is registered as an mpv key binding (via `register_key_binding`) to detect double-click on the video — Qt event filters cannot intercept these events because mpv owns the X11 window's input

### Config persistence

Config is stored at `~/.config/fila/fila.json`. Use `_update_config(**kwargs)` to merge changes without clobbering other keys. Favorites are stored as `[{"path": str, "name": str}]` and persist drag-and-drop reorder order.

### Table sorting

`NumericItem(QTableWidgetItem)` stores a raw numeric sort key in `SORT_ROLE` and overrides `__lt__` to use it. `setSortingEnabled(False)` is used during table population and during duration cell updates to avoid O(n²) re-sorts.

### File operations

Right-click context menu on the file table provides:
- **Show in File Manager**: uses `org.freedesktop.FileManager1` D-Bus to highlight the file in the running file manager (Nautilus, Dolphin, Thunar, Nemo); falls back to `xdg-open` on the parent folder
- **Move to Trash**: uses `send2trash`
- **Delete Permanently**: prompts for confirmation, then `os.remove()`

All three operations remove the file from `_all_files` and the table without triggering a full folder rescan (`_remove_file_from_view`).

### Icon

`icon.png` lives in the project root and is embedded into the Nuitka onefile binary via `--include-data-files=icon.png=icon.png`. At runtime, `Path(__file__).parent / "icon.png"` resolves correctly both in dev mode and from the Nuitka extraction cache (`~/.cache/fila/`).
