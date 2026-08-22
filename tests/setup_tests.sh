#!/usr/bin/env bash
# ==============================================================================
# 3x-UI BootstRUp - Test Environment Setup Script
# Prepares local environment for running test suites (UI E2E, Deploy, VPN).
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/docker-compose.test.yml" ]; then
    TESTS_DIR="$SCRIPT_DIR"
    REPO_ROOT="$(dirname "$SCRIPT_DIR")"
else
    TESTS_DIR="$SCRIPT_DIR/tests"
    REPO_ROOT="$SCRIPT_DIR"
fi

ENV_DIR="$REPO_ROOT/.python_env"

NC='\033[0m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
BOLD='\033[1m'

echo -e "${CYAN}${BOLD}"
echo "=================================================================="
echo "         3x-UI BootstRUp - Test Environment Setup                 "
echo "=================================================================="
echo -e "${NC}"

# 1. Resolve or bootstrap Python environment with pip
PYTHON_BIN=""

ensure_python_with_pip() {
    if [ -x "$ENV_DIR/bin/python3" ] && "$ENV_DIR/bin/python3" -m pip --version >/dev/null 2>&1; then
        PYTHON_BIN="$ENV_DIR/bin/python3"
        return 0
    fi

    if command -v python3 >/dev/null 2>&1 && python3 -m pip --version >/dev/null 2>&1; then
        PYTHON_BIN="$(command -v python3)"
        return 0
    fi

    echo -e "${YELLOW}[..] System python is missing pip. Provisioning isolated Python runtime in $ENV_DIR...${NC}"
    OS="$(uname -s)"
    ARCH="$(uname -m)"
    PORTABLE_PYTHON_RELEASE="20240224"
    PYTHON_VERSION="3.12.2"

    case "$OS" in
        Linux)
            if [ "$ARCH" = "x86_64" ]; then
                PYTHON_URL="https://github.com/indygreg/python-build-standalone/releases/download/${PORTABLE_PYTHON_RELEASE}/cpython-${PYTHON_VERSION}+${PORTABLE_PYTHON_RELEASE}-x86_64-unknown-linux-gnu-install_only.tar.gz"
            elif [ "$ARCH" = "aarch64" ]; then
                PYTHON_URL="https://github.com/indygreg/python-build-standalone/releases/download/${PORTABLE_PYTHON_RELEASE}/cpython-${PYTHON_VERSION}+${PORTABLE_PYTHON_RELEASE}-aarch64-unknown-linux-gnu-install_only.tar.gz"
            else
                echo -e "${RED}[ERROR] Unsupported Linux architecture: $ARCH${NC}"
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
            echo -e "${RED}[ERROR] Unsupported OS: $OS${NC}"
            exit 1
            ;;
    esac

    mkdir -p "$ENV_DIR"
    curl -fsSL "$PYTHON_URL" | tar -xz -C "$ENV_DIR" --strip-components=1
    PYTHON_BIN="$ENV_DIR/bin/python3"
    echo -e "${GREEN}[OK] Isolated Python with pip installed into $ENV_DIR${NC}"
}

ensure_python_with_pip
echo -e "${CYAN}[1/4] Using Python:${NC} $($PYTHON_BIN --version) ($PYTHON_BIN)"

# 2. Check Docker
echo -e "${CYAN}[2/4] Checking Docker status...${NC}"
if docker info >/dev/null 2>&1; then
    echo -e "${GREEN}[OK] Docker daemon is running and accessible.${NC}"
else
    echo -e "${YELLOW}[WARN] Docker daemon is not accessible without sudo or not running.${NC}"
    echo -e "       Ensure Docker is running and your user is in the docker group:"
    echo -e "       sudo usermod -aG docker \$USER && sudo service docker start"
fi

# 3. Install Python dependencies (Playwright, PyYAML)
echo -e "${CYAN}[3/6] Checking/Installing Python dependencies (playwright, pyyaml)...${NC}"
"$PYTHON_BIN" -m pip install playwright pyyaml --break-system-packages 2>/dev/null || \
"$PYTHON_BIN" -m pip install playwright pyyaml || {
    echo -e "${RED}[ERROR] Failed to install python dependencies via pip.${NC}"
    exit 1
}
echo -e "${GREEN}[OK] Python packages installed.${NC}"

# 4. Install Playwright browser binaries & system dependencies
echo -e "${CYAN}[4/6] Installing Chromium browser and system dependencies for Playwright...${NC}"
"$PYTHON_BIN" -m playwright install chromium
if command -v sudo >/dev/null 2>&1; then
    echo -e "${YELLOW}[..] Installing OS-level shared libraries (libnspr4, nss, etc.)...${NC}"
    sudo "$PYTHON_BIN" -m playwright install-deps chromium 2>/dev/null || \
    (sudo apt-get update -y && sudo apt-get install -y libnspr4 libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2t64 libasound2) || true
fi
echo -e "${GREEN}[OK] Chromium and system libraries installed.${NC}"

# 5. Fix permissions on tests/.cache directory
echo -e "${CYAN}[5/6] Checking tests/.cache sandbox directory permissions...${NC}"
CACHE_DIR="$TESTS_DIR/.cache"
if [ -d "$CACHE_DIR" ]; then
    if [ ! -w "$CACHE_DIR" ]; then
        echo -e "${YELLOW}[..] Fixing ownership/permissions on $CACHE_DIR...${NC}"
        sudo chown -R "$USER:$(id -gn)" "$CACHE_DIR" 2>/dev/null || chmod -R 777 "$CACHE_DIR" 2>/dev/null || true
    fi
else
    mkdir -p "$CACHE_DIR"
fi
echo -e "${GREEN}[OK] Cache directory ready.${NC}"

# 6. Build test-vps base Docker image & pre-cache test layers
echo -e "${CYAN}[6/6] Building test-vps Docker image & preparing cache...${NC}"
if docker info >/dev/null 2>&1; then
    docker build -t test-vps:latest -f "$TESTS_DIR/Dockerfile.vps" "$TESTS_DIR"
    echo -e "${GREEN}[OK] test-vps:latest image built successfully.${NC}"
else
    echo -e "${YELLOW}[WARN] Skipping Docker image build (daemon not accessible).${NC}"
fi

echo -e "\n${GREEN}${BOLD}==================================================================${NC}"
echo -e "${GREEN}${BOLD}✔ Test environment setup completed successfully!${NC}"
echo -e "${GREEN}${BOLD}==================================================================${NC}"
echo -e "You can now run tests with:"
echo -e "  ${BOLD}./tests/run_all_tests.sh${NC}          (All test suites)"
echo -e "  ${BOLD}./tests/ui/run_ui_tests.sh all${NC}    (UI E2E tests only)"
echo -e "  ${BOLD}./tests/deploy/run_deploy_tests.sh${NC} (Deploy tests only)"
echo -e "  ${BOLD}./tests/vpn/run_vpn_tests.sh${NC}       (VPN tests only)"
echo ""
