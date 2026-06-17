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
require_cmd mktemp

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

echo "[..] Downloading ${ARCHIVE_URL}"
curl -fsSL "$ARCHIVE_URL" | tar -xz -C "$tmp_dir"

src_dir="$(find "$tmp_dir" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
[[ -n "$src_dir" ]] || die "Downloaded archive is empty."

mkdir -p "$INSTALL_DIR"
echo "[..] Updating files in ${INSTALL_DIR}"
tar -C "$src_dir" -cf - . | tar -C "$INSTALL_DIR" -xf -


cd "$INSTALL_DIR"

for script in setup.sh update.sh rollback_update.sh install.sh update_sources.sh; do
    [[ -f "$script" ]] && chmod +x "$script"
done

echo "[OK] Project files updated."
