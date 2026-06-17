#!/usr/bin/env bash
set -euo pipefail

readonly REPO="${REPO:-honmiv/3x-ui-bootstRUp}"
readonly BRANCH="${BRANCH:-master}"
readonly INSTALL_DIR="${INSTALL_DIR:-3x-ui-bootstRUp}"
readonly ARCHIVE_URL="${ARCHIVE_URL:-https://github.com/${REPO}/archive/refs/heads/${BRANCH}.tar.gz}"

die() {
    echo "[ERROR] $*" >&2
    exit 1
}

require_cmd() {
    command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

require_cmd curl
require_cmd tar

[[ -r /dev/tty ]] || die "Interactive terminal is required."

cd ~

mkdir -p "$INSTALL_DIR"

echo "[..] Downloading ${ARCHIVE_URL}"
curl -fsSL "$ARCHIVE_URL" | tar -xz -C "$INSTALL_DIR" --strip-components=1

cd "$INSTALL_DIR"
chmod +x setup.sh

echo "[..] Starting setup.sh"
if [[ $EUID -eq 0 ]]; then
    exec ./setup.sh </dev/tty
fi

require_cmd sudo
exec sudo ./setup.sh </dev/tty
