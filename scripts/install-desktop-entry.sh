#!/usr/bin/env sh
set -eu

APP_DIR="${HOME}/.local/share/applications"
ICON_DIR="${HOME}/.local/share/icons/hicolor/256x256/apps"
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_DIR=$(CDPATH= cd -- "${SCRIPT_DIR}/.." && pwd)

mkdir -p "${APP_DIR}" "${ICON_DIR}"

install -m 644 "${PROJECT_DIR}/klene.desktop" "${APP_DIR}/klene.desktop"
install -m 644 "${PROJECT_DIR}/src/klene/assets/klene_logo.png" "${ICON_DIR}/klene.png"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "${APP_DIR}" >/dev/null 2>&1 || true
fi

if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache "${HOME}/.local/share/icons/hicolor" >/dev/null 2>&1 || true
fi

printf '%s\n' "Installed klene.desktop and klene.png into your local desktop directories."
