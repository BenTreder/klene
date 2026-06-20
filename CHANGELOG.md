# Changelog

## 0.2.0

- Added platform provider architecture and platform detection
- Added working Generic Linux cleanup support
- Added Debian and Ubuntu family cleanup support with APT cache and autoremove preview
- Added Fedora cleanup support with DNF cache and autoremove preview
- Added openSUSE cleanup support with zypper cache cleanup
- Added Windows safe cleanup support for temp files, Recycle Bin, thumbnail cache, and Windows error reports
- Preserved Arch Linux cleanup behavior for pacman cache, orphan packages, AUR cache, journal, user cache, trash, thumbnails, and Flatpak
- Improved GUI platform messaging and category filtering
- Improved CLI and doctor reporting with provider-aware output

## 0.1.0

Initial release.

- Preview-first Arch Linux cleanup workflow with safe defaults
- PySide6 GUI with branding, splash screen, and shared backend logic
- Typer CLI with scan, doctor, about, and cleanup commands
- Safety guards for protected paths and package removal confirmations
- Arch-focused cleanup categories for pacman cache, orphans, journal, trash, thumbnails, AUR cache, and Flatpak
