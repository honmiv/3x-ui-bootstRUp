#!/usr/bin/env bash
set -euo pipefail

ENV_DIR="./.python_env"
PORTABLE_PYTHON_RELEASE="20240224"
PYTHON_VERSION="3.12.2"

echo "========================================="
echo "   3x-ui-bootstRUp Local Web UI Launcher "
echo "========================================="

detect_platform() {
    OS="$(uname -s)"
    ARCH="$(uname -m)"
    case "$OS" in
        Linux)
            if [ "$ARCH" = "x86_64" ]; then
                PYTHON_URL="https://github.com/indygreg/python-build-standalone/releases/download/${PORTABLE_PYTHON_RELEASE}/cpython-${PYTHON_VERSION}+${PORTABLE_PYTHON_RELEASE}-x86_64-unknown-linux-gnu-install_only.tar.gz"
            elif [ "$ARCH" = "aarch64" ]; then
                PYTHON_URL="https://github.com/indygreg/python-build-standalone/releases/download/${PORTABLE_PYTHON_RELEASE}/cpython-${PYTHON_VERSION}+${PORTABLE_PYTHON_RELEASE}-aarch64-unknown-linux-gnu-install_only.tar.gz"
            else
                echo "[ERROR] Unsupported Linux architecture: $ARCH" >&2
                exit 1
            fi
            ;;
        Darwin)
            if [ "$ARCH" = "arm64" ]; then
                PYTHON_URL="https://github.com/indygreg/python-build-standalone/releases/download/${PORTABLE_PYTHON_RELEASE}/cpython-${PYTHON_VERSION}+${PORTABLE_PYTHON_RELEASE}-aarch64-apple-darwin-install_only.tar.gz"
            else
                PYTHON_URL="https://github.com/indygreg/python-build-standalone/releases/download/${PORTABLE_PYTHON_RELEASE}/cpython-${PYTHON_VERSION}+${PORTABLE_PYTHON_RELEASE}-x86_64-apple-darwin-install_only.tar.gz"
            fi
            ;;
        *)
            echo "[ERROR] Unsupported OS: $OS" >&2
            exit 1
            ;;
    esac
}

PYTHON_BIN=""

if [ -x "$ENV_DIR/bin/python3" ]; then
    PYTHON_BIN="$ENV_DIR/bin/python3"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
else
    echo "[..] Portable Python not found. Downloading isolated runtime..."
    detect_platform
    mkdir -p "$ENV_DIR"
    curl -fsSL "$PYTHON_URL" | tar -xz -C "$ENV_DIR" --strip-components=1
    PYTHON_BIN="$ENV_DIR/bin/python3"
    echo "[OK] Portable Python installed into $ENV_DIR"
fi

echo "[OK] Starting local Web UI application..."
exec "$PYTHON_BIN" main.py
