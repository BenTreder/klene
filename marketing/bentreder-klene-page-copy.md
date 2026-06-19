# Klene

Safe cleanup for Arch Linux.

Klene is a cleanup utility for Arch Linux with a modern desktop GUI and a fast CLI. It was built to help you review cleanup opportunities without guessing what is safe to remove.

## Hero

Klene helps you scan first, preview what can be cleaned, and only remove what you choose.

Made by Ben Treder  
BenTreder.com

GitHub: https://github.com/bdtreder/klene

## Why I Made Klene

I wanted a cleanup tool for Arch Linux that felt clear, safe, and pleasant to use. A lot of cleanup advice online jumps straight to destructive commands. Klene takes the opposite approach. It shows you what it found, explains what each category means, and keeps cleanup behind explicit confirmation.

## What It Cleans

- Pacman cache
- Orphan packages
- System journal logs
- Low-risk user cache folders
- Trash
- Thumbnail cache
- yay and paru cache
- Unused Flatpak data when available

## Safety-First Design

Klene is safe by default.

- It scans before it cleans
- Preview is non-destructive
- Real cleanup requires confirmation
- Orphan package removal gets extra confirmation
- Protected paths are refused

## GUI And CLI

Klene includes a polished PySide6 desktop app and a Typer-powered command line interface. Both use the same backend, so the scan and cleanup behavior stays consistent.

## Who It Is For

Klene is for Arch Linux users who want a cleaner system without relying on vague one-liners or risky cleanup habits.

## Download On GitHub

GitHub placeholder link:

https://github.com/bdtreder/klene

## Footer Credit

Made by Ben Treder  
BenTreder.com
