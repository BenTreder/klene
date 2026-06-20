# Klene

Klene is a safe cleanup utility for Linux and Windows with a modern GUI and CLI. It scans first, previews what can be cleaned, and only removes selected items after confirmation.

Klene started as an Arch Linux cleanup app. Arch Linux and Arch-like systems still have the deepest package-manager support, and the app now includes provider-based support for Debian-family systems, Fedora, openSUSE, Generic Linux, and conservative Windows cleanup.

![Klene logo](screenshots/Klene_Logo.png)

## Platform Support

| Platform | Status | Cleanup support |
| --- | --- | --- |
| Arch Linux | Full | pacman cache, orphans, journal, AUR cache, user cache, trash, thumbnails, Flatpak |
| Arch-like | Full when pacman tools are present | same as Arch where tools exist |
| Debian/Ubuntu/Mint | Working | apt cache, apt autoremove preview/cleanup, generic Linux cleanup, Flatpak, optional Snap cache |
| Fedora | Working | dnf cache, dnf autoremove, generic Linux cleanup, Flatpak |
| openSUSE | Working | zypper cache, generic Linux cleanup, Flatpak |
| Generic Linux | Working basic | trash, thumbnails, selected user cache, journal, Flatpak |
| Windows | Working safe cleanup | user temp, Windows temp, Recycle Bin, thumbnail cache, Windows error reports |

## Safety First

Klene stays conservative by design.

- Cleanup commands default to preview or dry-run behavior where possible
- Real cleanup requires confirmation in both the GUI and CLI
- Package removal is never selected by default and always requires extra confirmation
- Only strict allowlisted paths are cleaned
- Locked or inaccessible files are skipped where possible instead of forcing removal

Klene refuses to touch:

- Registry cleanup
- Browser passwords, cookies, sessions, or browser databases
- Whole home directories
- Whole AppData directories
- Whole `~/.cache` or arbitrary user-selected paths
- System roots such as `/`, `/usr`, `/etc`, `/var`, `C:\Windows`, `C:\Users`, `C:\Program Files`, or `C:\ProgramData`
- Package removal without preview and extra confirmation

## What Klene Cleans

Shared Linux cleanup areas:

- Trash
- Thumbnail cache
- Low-risk user cache:
  - `~/.cache/thumbnails`
  - `~/.cache/fontconfig`
  - `~/.cache/pip`
  - `~/.cache/go-build`
  - `~/.cache/npm`
  - `~/.cache/yarn`
- System journal when `journalctl` exists
- Flatpak unused data when `flatpak` exists

Windows cleanup areas:

- `%TEMP%`
- `%WINDIR%\Temp`
- Recycle Bin
- `%LOCALAPPDATA%\Microsoft\Windows\Explorer` thumbnail and icon cache files
- Windows Error Reporting cache folders under `%LOCALAPPDATA%` and `%ProgramData%`

## GUI Usage

```bash
klene
python -m klene gui
```

The GUI keeps the existing preview-first workflow, now with platform-aware cleanup cards and a platform badge in the header.

## CLI Usage

```bash
klene-cli scan
klene-cli scan --json
klene-cli platform
klene-cli doctor
klene-cli clean list
klene-cli clean user-cache --dry-run
klene-cli clean all --dry-run
```

Direct module-based CLI use still works:

```bash
PYTHONPATH=src python -m klene --help
```

## Install From Source

Linux:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

Future packaged Windows builds can use a PyInstaller workflow, but this repository does not build a Windows executable by default in this phase.

## Doctor Command

`klene-cli doctor` checks your local setup without cleaning anything.

It reports:

- Detected platform and selected provider
- Support level
- Relevant provider tools and cache paths
- GUI import health
- Packaged logo availability
- Current user

## Local Shortcuts

To make `klene` launch the GUI and `klene-cli` run CLI commands from this project:

```bash
./scripts/install-local-shortcuts.sh
```

## Testing

```bash
python -m compileall src tests
PYTHONPATH=src python -m pytest
PYTHONPATH=src python -m klene --help
PYTHONPATH=src python -m klene --version
PYTHONPATH=src python -m klene about
PYTHONPATH=src python -m klene platform
PYTHONPATH=src python -m klene doctor
PYTHONPATH=src python -m klene scan
PYTHONPATH=src python -m klene scan --json
```

## Release Notes

Current version: `0.2.0`

Arch remains the most complete package-manager integration. Other Linux distributions and Windows now have working, conservative cleanup support through platform-specific providers.

## Credits

Made by Ben Treder  
BenTreder.com
