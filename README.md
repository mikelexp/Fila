# Fila

Fila is a desktop app for browsing folders, filtering media files, generating playlists, and playing content with `mpv`.

## Features

- Three-pane layout for folders, files, and preview
- Favorites with drag-and-drop ordering
- Media filtering by type
- Playlist generation and external playback
- Integrated preview player via `mpv`
- File duration detection with `ffprobe`
- System-level file actions like show in file manager and trash/delete

## Requirements

- Linux
- Python 3.13+
- `mpv`
- `ffmpeg` (`ffprobe`)
- `patchelf` for Nuitka builds

## Quick Start

```bash
make install-deps
make run
```

Or:

```bash
just install-deps
just run
```

If you prefer the legacy wrappers:

```bash
./setup.sh
./run.sh
```

## Build

```bash
make build-onefile
```

Or:

```bash
just build-onefile
```

This produces the app binary under `dist/`.

## Install Locally

```bash
make install
```

Or:

```bash
just install
```

Or, from a packaged release:

```bash
./install.sh
```

## Release Flow

GitHub Releases are published automatically from tags that start with `v`.

```bash
git tag v1.0.0
git push github master v1.0.0
```

The workflow builds a release tarball named like `fila-1.0.0-linux-x86_64.tar.gz`.

## AUR

The AUR package is `fila-bin`.

After the GitHub release is available:

```bash
make aur-update
```

Or:

```bash
just aur-update <version>
```

## Project Layout

- `fila.py`: main application
- `build_nuitka.py`: Nuitka build driver
- `scripts/`: build, install, release, and AUR helpers
- `.github/workflows/release.yml`: GitHub release pipeline

## License

See the repository metadata.
