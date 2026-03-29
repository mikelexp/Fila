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

## Architecture

The entire application lives in a single file: `fila.py`.

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

Config is stored at `~/.config/fila/fila.json`. Use `_update_config(**kwargs)` to merge changes without clobbering other keys. Favorites are stored as `[{"path": str, "name": str}]`.

### Table sorting

`NumericItem(QTableWidgetItem)` stores a raw numeric sort key in `SORT_ROLE` and overrides `__lt__` to use it. `setSortingEnabled(False)` is used during table population and during duration cell updates to avoid O(n²) re-sorts.
