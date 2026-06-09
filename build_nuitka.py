#!/usr/bin/env python3

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
MAIN_SCRIPT = PROJECT_ROOT / "fila.py"
ICON_FILE = PROJECT_ROOT / "icon.png"
BUILD_DIR = PROJECT_ROOT / "build"
DIST_DIR = PROJECT_ROOT / "dist"


def _git_version() -> str:
    try:
        result = subprocess.run(
            ["git", "describe", "--tags", "--abbrev=0", "--match", "v*"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        version = result.stdout.strip().removeprefix("v")
        if re.fullmatch(r"\d+\.\d+\.\d+", version):
            return version
    except Exception:
        pass
    return "0.1.0"


def build_command(onefile: bool) -> list[str]:
    version = _git_version()
    command = [
        sys.executable,
        "-m",
        "nuitka",
        "--assume-yes-for-downloads",
        "--standalone",
        "--enable-plugin=pyside6",
        "--include-qt-plugins=platforms,platformthemes,iconengines,imageformats,wayland-shell-integration,wayland-decoration-client,wayland-graphics-integration-client,xcbglintegrations",
        "--output-dir=" + str(DIST_DIR),
        "--output-filename=fila.bin",
        "--remove-output",
        "--show-progress",
        "--show-scons",
        "--follow-imports",
        "--python-flag=no_site",
        "--warn-unusual-code",
        "--company-name=Mikele",
        "--product-name=Fila",
        "--file-description=Browse folders, filter media, generate playlists, and play files",
        f"--file-version={version}.0",
        f"--product-version={version}.0",
        "--nofollow-import-to=tkinter,test,unittest,pydoc",
        f"--include-data-files={ICON_FILE}=icon.png",
        str(MAIN_SCRIPT),
    ]

    if onefile:
        command.append('--onefile-tempdir-spec={CACHE_DIR}/fila')
        command.append("--onefile")

    return command


def ensure_dirs() -> None:
    BUILD_DIR.mkdir(exist_ok=True)
    DIST_DIR.mkdir(exist_ok=True)
    (BUILD_DIR / ".cache").mkdir(exist_ok=True)


def clean() -> None:
    targets = [
        BUILD_DIR,
        DIST_DIR,
        PROJECT_ROOT / "__pycache__",
        PROJECT_ROOT / "fila.build",
        PROJECT_ROOT / "fila.dist",
        PROJECT_ROOT / "fila.onefile-build",
        PROJECT_ROOT / "fila.bin",
    ]
    for target in targets:
        if target.is_dir():
            shutil.rmtree(target)
        elif target.is_file():
            target.unlink()


def main() -> int:
    if sys.version_info[:2] > (3, 13):
        print(
            "Error: Nuitka 4.0.7 soporta hasta Python 3.13; usa python3.13 para construir.",
            file=sys.stderr,
        )
        return 1

    parser = argparse.ArgumentParser(description="Build Fila with Nuitka.")
    parser.add_argument("--onefile", action="store_true", help="Build a onefile binary instead of standalone.")
    parser.add_argument("--clean", action="store_true", help="Remove build artifacts before building.")
    parser.add_argument("--clean-only", action="store_true", help="Only remove build artifacts.")
    args = parser.parse_args()

    if args.clean or args.clean_only:
        clean()
    if args.clean_only:
        return 0

    ensure_dirs()
    command = build_command(onefile=args.onefile)
    print("Running:", " ".join(command))
    env = os.environ.copy()
    env["PATH"] = f"{Path.home() / '.local' / 'bin'}:{env.get('PATH', '')}"
    env["XDG_CACHE_HOME"] = str(BUILD_DIR / ".cache")
    completed = subprocess.run(command, cwd=PROJECT_ROOT, env=env)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
