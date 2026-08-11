#!/usr/bin/env bash
set -euo pipefail

readonly REPO="${REPO:-honmiv/3x-ui-bootstRUp}"
readonly BRANCH="${BRANCH:-master}"
readonly ARCHIVE_URL="${ARCHIVE_URL:-https://github.com/${REPO}/archive/refs/heads/${BRANCH}.tar.gz}"

# Resolve target directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd || echo ".")"
readonly TARGET_DIR="${TARGET_DIR:-${INSTALL_DIR:-$SCRIPT_DIR}}"

die() {
    echo "[ERROR] $*" >&2
    exit 1
}

require_cmd() {
    command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

main() {
    require_cmd curl
    require_cmd tar
    require_cmd mktemp

    tmp_dir="$(mktemp -d)"
    trap 'rm -rf "$tmp_dir"' EXIT

    echo "[..] Downloading latest sources from ${ARCHIVE_URL}..."
    curl -fsSL "$ARCHIVE_URL" | tar -xz -C "$tmp_dir"

    src_dir="$(find "$tmp_dir" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
    [[ -n "$src_dir" && -d "$src_dir" ]] || die "Downloaded archive is empty or invalid."

    mkdir -p "$TARGET_DIR"
    cd "$TARGET_DIR"
    TARGET_DIR_ABS="$PWD"

    echo "[..] Cleaning working directory at ${TARGET_DIR_ABS}..."
    echo "[..] Preserving 'backups' folder, 'setup_backup.yml' file, and '.git' repository."

    shopt -s dotglob nullglob
    for item in *; do
        name="$(basename "$item")"
        if [[ "$name" == "." || "$name" == ".." ]]; then
            continue
        fi
        if [[ "$name" == "backups" || "$name" == "backup" || "$name" == "setup_backup.yml" || "$name" == "setup_backup.yaml" || "$name" == ".git" ]]; then
            echo "[KEEP] $name"
            continue
        fi
        rm -rf "$item"
    done
    shopt -u dotglob nullglob

    echo "[..] Extracting updated files..."
    cp -a "$src_dir"/. "$TARGET_DIR_ABS"/

    echo "[..] Setting script execution permissions..."
    for script in setup.sh update.sh rollback_update.sh install.sh update_sources.sh backup.sh; do
        [[ -f "$script" ]] && chmod +x "$script"
    done

    echo "[OK] Project files updated successfully."

    # Kill any leftover main.py process if running to free port 8000
    if command -v pkill >/dev/null 2>&1; then
        pkill -f "python.*main\.py" >/dev/null 2>&1 || true
    fi

    if [[ -f "./install.sh" ]]; then
        echo "[..] Starting local Web UI application..."
        exec ./install.sh
    fi
}

main "$@"

