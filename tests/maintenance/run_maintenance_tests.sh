#!/usr/bin/env bash
# ==============================================================================
# 3x-UI BootstRUp - Automated Maintenance Integration Tests Runner
# Runs maintenance tests (backup, recovery, update, restart, sub-server)
# across isolated Docker VPS containers.
#
# Usage:
#   ./tests/maintenance/run_maintenance_tests.sh            # Run all maintenance tests
#   ./tests/maintenance/run_maintenance_tests.sh backup     # Run Backup & Recovery test
#   ./tests/maintenance/run_maintenance_tests.sh update     # Run 3X-UI Version Update test
#   ./tests/maintenance/run_maintenance_tests.sh restart    # Run Panel Restart test
#   ./tests/maintenance/run_maintenance_tests.sh sub        # Run Sub-Server Maintenance test
#   ./tests/maintenance/run_maintenance_tests.sh --down     # Tear down test containers
# ==============================================================================

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/docker-compose.test.yml" ]; then
    TESTS_DIR="$SCRIPT_DIR"
    REPO_ROOT="$(dirname "$SCRIPT_DIR")"
    MAINT_DIR="$SCRIPT_DIR/maintenance"
elif [ -f "$SCRIPT_DIR/../docker-compose.test.yml" ]; then
    TESTS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
    REPO_ROOT="$(dirname "$TESTS_DIR")"
    MAINT_DIR="$SCRIPT_DIR"
else
    REPO_ROOT="$SCRIPT_DIR"
    TESTS_DIR="$SCRIPT_DIR/tests"
    MAINT_DIR="$TESTS_DIR/maintenance"
fi

COMPOSE_FILE="$TESTS_DIR/docker-compose.test.yml"

# Colors
NC='\033[0m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
BOLD='\033[1m'

# Find python binary
PYTHON_BIN="python3"
if [ -x "$REPO_ROOT/.python_env/bin/python3" ]; then
    PYTHON_BIN="$REPO_ROOT/.python_env/bin/python3"
fi

banner() {
    echo -e "${CYAN}${BOLD}"
    echo "=================================================================="
    echo "       3x-UI BootstRUp - Maintenance Integration Test Suite       "
    echo "=================================================================="
    echo -e "${NC}"
}

check_docker() {
    if ! docker info >/dev/null 2>&1; then
        echo -e "${RED}[ERROR] Docker daemon is not running. Please start Docker and try again.${NC}"
        exit 1
    fi
}

cleanup_containers() {
    echo -e "${CYAN}[..] Cleaning up test containers...${NC}"
    docker compose -f "$COMPOSE_FILE" down --remove-orphans >/dev/null 2>&1 || true
    echo -e "${GREEN}[OK] Test containers stopped and removed.${NC}"
}

for arg in "$@"; do
    if [[ "$arg" == "--default-workers" ]]; then
        exec "$PYTHON_BIN" "$MAINT_DIR/run_maintenance_parallel.py" --default-workers
    fi
done

if [[ "${1:-}" == "--down" || "${1:-}" == "down" || "${1:-}" == "clean" || "${1:-}" == "--clean" ]]; then
    cleanup_containers
    exit 0
fi

banner
check_docker

# Determine which test(s) to run
TARGET=""
WORKER_ARGS=()

for arg in "$@"; do
    if [[ "$arg" == --maint-workers=* || "$arg" == --workers=* ]]; then
        WORKER_ARGS+=("$arg")
    elif [[ -z "$TARGET" ]]; then
        TARGET="$arg"
    fi
done

[ -z "$TARGET" ] && TARGET="all"

case "$TARGET" in
    backup|recovery|backup_recovery)
        TEST_FILE="$MAINT_DIR/test_maint_panel_backup_recovery.py"
        ;;
    update|update_3xui)
        TEST_FILE="$MAINT_DIR/test_maint_panel_update.py"
        ;;
    restart|restart_panel)
        TEST_FILE="$MAINT_DIR/test_maint_panel_restart.py"
        ;;
    sub|sub_server|sub_ops)
        TEST_FILE="$MAINT_DIR/test_maint_sub_server.py"
        ;;
    all|--all|maintenance|maint|parallel|--parallel|-p|seq|sequential)
        "$PYTHON_BIN" "$MAINT_DIR/run_maintenance_parallel.py" "$TARGET" "${WORKER_ARGS[@]}"
        exit $?
        ;;
    *)
        echo -e "${RED}[ERROR] Unknown test target: '$TARGET'${NC}"
        echo "Valid options: all, backup, update, restart, sub, --down"
        exit 1
        ;;
esac

echo -e "${BOLD}${CYAN}▶ Running $(basename "$TEST_FILE")...${NC}"
START_TIME=$(date +%s)

if "$PYTHON_BIN" "$TEST_FILE"; then
    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))
    echo -e "\n${GREEN}${BOLD}✔ [PASS] $(basename "$TEST_FILE") (${DURATION}s)${NC}"
    exit 0
else
    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))
    echo -e "\n${RED}${BOLD}✘ [FAIL] $(basename "$TEST_FILE") (${DURATION}s)${NC}"
    exit 1
fi

