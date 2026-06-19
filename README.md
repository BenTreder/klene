# Klene

Klene is a safe cleanup utility for Arch Linux with a modern GUI and a fast CLI.

## Features

- Safe-by-default cleanup workflow with scan, preview, and explicit confirmation before deletion.
- Typer-based CLI with Rich tables and JSON output for scripting.
- PySide6 desktop app with a responsive dark interface and shared backend logic.
- Arch-focused cleanup actions for pacman cache, orphan packages, journal logs, trash, thumbnails, AUR cache, and optional Flatpak unused data.
- Hardcoded path safety rules to avoid deleting critical system or personal directories.

## Screenshots

Add screenshots to the `screenshots/` directory and reference them here once available.

## Install From Source

Arch package dependencies:

```bash
sudo pacman -S python python-pyside6 python-typer python-rich python-pytest pacman-contrib
```

`paccache` is provided by `pacman-contrib`:

```bash
sudo pacman -S pacman-contrib
```

Local development install:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Run CLI

```bash
klene scan
klene scan --json
klene clean pacman-cache --dry-run
klene clean pacman-cache --keep 3 --execute
klene clean all --dry-run
```

## Run GUI

```bash
klene gui
python -m klene gui
```

## Safety Philosophy

Klene scans first and previews what it can clean. Nothing destructive runs automatically.

- Cleanup commands default to dry-run mode.
- `--execute` is required for real cleanup.
- Confirmation is required before cleanup runs.
- Orphan package removal requires an extra confirmation step.
- Klene avoids broad destructive commands such as `pacman -Scc` as a default.

## What Klene Cleans

- Pacman package cache using `paccache` when available.
- Orphan packages detected with `pacman -Qdtq`.
- Systemd journal usage and optional vacuum cleanup.
- User cache reporting plus targeted low-risk cache cleanup for:
  - `~/.cache/thumbnails`
  - `~/.cache/fontconfig`
  - `~/.cache/pip`
  - `~/.cache/go-build`
  - `~/.cache/npm`
  - `~/.cache/yarn`
- Trash data under `~/.local/share/Trash`.
- Thumbnail cache.
- AUR helper cache for `yay` and `paru` when present.
- Optional Flatpak unused data preview if `flatpak` is installed.

## What Klene Refuses To Touch

Klene will refuse unsafe cleanup targets including:

- `/`
- `/home`
- `~`
- `/usr`
- `/etc`
- `/var`
- `/var/cache`
- `~/.config`
- `~/.ssh`
- `~/Documents`
- `~/Downloads`
- `~/Desktop`
- `~/Pictures`
- `~/Videos`

## Development

Useful commands:

```bash
python -m compileall src
pytest
python -m klene --help
python -m klene scan --json
```

Project layout uses a `src/` package structure and keeps GUI and CLI logic on top of the same scanner and cleaner services.

## GitHub Release Checklist

- Review README examples and screenshots.
- Run `python -m compileall src`.
- Run `pytest`.
- Run `python -m klene --help`.
- Run `python -m klene scan --json` on an Arch system.
- Confirm `klene.desktop` launches the GUI.
- Tag a release after verifying behavior on a real Arch install.
