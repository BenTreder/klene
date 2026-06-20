# Klene

Safe cleanup for Linux and Windows.

Klene is a cleanup utility with a modern desktop GUI and a fast CLI. It helps you review cleanup opportunities without guessing what is safe to remove.

## Hero

Klene helps you scan first, preview what can be cleaned, and only remove what you choose.

Made by Ben Treder  
BenTreder.com

GitHub: https://github.com/BenTreder/klene

## Why I Made Klene

Klene started as an Arch Linux cleanup app because that was the system I wanted to support deeply first. The app now expands carefully into other Linux distributions and Windows without losing its preview-first, confirmation-first safety model.

## What It Cleans

- Arch Linux and Arch-like: pacman cache, orphan packages, AUR cache, Flatpak, journal, trash, thumbnails, low-risk user cache
- Debian and Ubuntu family: apt cache, apt autoremove preview, Snap cache review, plus generic Linux cleanup
- Fedora: DNF cache, DNF autoremove preview, plus generic Linux cleanup
- openSUSE: zypper cache plus generic Linux cleanup
- Windows: user temp, Windows temp, Recycle Bin, thumbnail cache, and Windows error reports

## Safety-First Design

- It scans before it cleans
- Preview is non-destructive
- Real cleanup requires confirmation
- Package removal gets extra confirmation
- Protected paths are refused
- Browser data, registry cleanup, and arbitrary path cleanup stay blocked

## GUI And CLI

Klene includes a polished PySide6 desktop app and a Typer-powered command line interface. Both use the same provider-driven backend, so scan and cleanup behavior stay consistent per platform.

## Who It Is For

Klene is for people who want a cleaner system without relying on vague one-liners or risky cleanup habits. Arch remains the most complete platform, and the newer Linux and Windows providers stay deliberately conservative.

## Download On GitHub

https://github.com/BenTreder/klene

## Footer Credit

Made by Ben Treder  
BenTreder.com
