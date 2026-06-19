#!/usr/bin/env sh
set -eu

BIN_DIR="${HOME}/.local/bin"
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_DIR=$(CDPATH= cd -- "${SCRIPT_DIR}/.." && pwd)

mkdir -p "${BIN_DIR}"

cat > "${BIN_DIR}/klene" <<EOF
#!/usr/bin/env sh
set -eu
PROJECT_DIR="${PROJECT_DIR}"
if [ "\$#" -gt 0 ]; then
    printf '%s\n' "Use klene-cli for command-line actions." >&2
    exit 2
fi
cd "\${PROJECT_DIR}"
exec env PYTHONPATH="\${PROJECT_DIR}/src\${PYTHONPATH:+:\${PYTHONPATH}}" python -m klene gui
EOF

cat > "${BIN_DIR}/klene-cli" <<EOF
#!/usr/bin/env sh
set -eu
PROJECT_DIR="${PROJECT_DIR}"
cd "\${PROJECT_DIR}"
exec env PYTHONPATH="\${PROJECT_DIR}/src\${PYTHONPATH:+:\${PYTHONPATH}}" python -m klene "\$@"
EOF

chmod +x "${BIN_DIR}/klene" "${BIN_DIR}/klene-cli"

printf '%s\n' "Installed local shortcuts:"
printf '  %s\n' "${BIN_DIR}/klene"
printf '  %s\n' "${BIN_DIR}/klene-cli"
printf '%s\n' "Make sure ${BIN_DIR} is in your PATH before using them."
