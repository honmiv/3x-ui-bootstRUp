#!/usr/bin/env bash
# ==============================================================================
# 3x-UI BootstRUp - Master Test Runner
# Executes all test suites (Deployment tests + VPN E2E traffic tests)
#
# Usage:
#   ./tests/run_all_tests.sh              # Run ALL test suites (Deploy + VPN)
#   ./tests/run_all_tests.sh deploy       # Run only Deploy test suite
#   ./tests/run_all_tests.sh vpn          # Run only VPN test suite
#   ./tests/run_all_tests.sh --down       # Tear down and clean up test environment
# ==============================================================================

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/docker-compose.test.yml" ]; then
    TESTS_DIR="$SCRIPT_DIR"
    REPO_ROOT="$(dirname "$SCRIPT_DIR")"
else
    TESTS_DIR="$SCRIPT_DIR/tests"
    REPO_ROOT="$SCRIPT_DIR"
fi

DEPLOY_RUNNER="$TESTS_DIR/deploy/run_deploy_tests.sh"
VPN_RUNNER="$TESTS_DIR/vpn/run_vpn_tests.sh"
UI_RUNNER="$TESTS_DIR/ui/run_ui_tests.sh"
COMPOSE_FILE="$TESTS_DIR/docker-compose.test.yml"

# Colors
NC='\033[0m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
BOLD='\033[1m'

banner() {
    echo -e "${CYAN}${BOLD}"
    echo "=================================================================="
    echo "            3x-UI BootstRUp - Master Test Suite Runner            "
    echo "=================================================================="
    echo -e "${NC}"
}

check_docker() {
    if ! docker info >/dev/null 2>&1; then
        echo -e "${RED}[ERROR] Docker daemon is not running. Please start Docker and try again.${NC}"
        exit 1
    fi
}

TARGET="${1:-all}"

if [[ "$TARGET" == "--down" || "$TARGET" == "down" || "$TARGET" == "clean" ]]; then
    echo -e "${YELLOW}[..] Tearing down all test containers and networks...${NC}"
    docker compose -f "$COMPOSE_FILE" down -v --remove-orphans 2>/dev/null || true
    echo -e "${GREEN}[OK] All test containers stopped and removed.${NC}"
    exit 0
fi

if [[ "$TARGET" == "-h" || "$TARGET" == "--help" || "$TARGET" == "help" ]]; then
    banner
    echo "Usage: ./tests/run_all_tests.sh [target]"
    echo ""
    echo "Targets:"
    echo "  all (default)  Run all test suites (UI E2E + Deploy Integration + VPN E2E)"
    echo "  ui             Run only UI & Browser E2E tests"
    echo "  deploy         Run only Deploy Integration tests"
    echo "  vpn            Run only VPN E2E traffic tests"
    echo "  setup          Setup local dependencies (Playwright, browsers)"
    echo "  --down         Tear down test containers and volumes"
    echo ""
    exit 0
fi

if [[ "$TARGET" == "setup" || "$TARGET" == "--setup" ]]; then
    exec "$TESTS_DIR/setup_tests.sh"
fi

banner

ensure_environment() {
    local python_bin="python3"
    if [ -x "$REPO_ROOT/.python_env/bin/python3" ]; then
        python_bin="$REPO_ROOT/.python_env/bin/python3"
    fi

    local needs_setup=false

    if ! "$python_bin" -c "import yaml; from playwright.sync_api import sync_playwright; p = sync_playwright().start(); b = p.chromium.launch(headless=True); b.close(); p.stop()" >/dev/null 2>&1; then
        needs_setup=true
    fi

    if [[ "$TARGET" != "ui" && "$TARGET" != "ui_tests" ]]; then
        if ! docker image inspect test-vps:latest >/dev/null 2>&1; then
            needs_setup=true
        fi
    fi

    if [ "$needs_setup" = true ]; then
        echo -e "${YELLOW}[..] Test environment, dependencies or browser missing. Provisioning via setup_tests.sh...${NC}"
        "$TESTS_DIR/setup_tests.sh"
    fi
}

ensure_environment

echo -e "${YELLOW}[..] Ensuring clean slate: tearing down any leftover test containers...${NC}"
docker compose -f "$COMPOSE_FILE" down -v --remove-orphans 2>/dev/null || true

declare -a SUITES_TO_RUN=()

case "$TARGET" in
    ui|ui_tests)
        SUITES_TO_RUN=("$UI_RUNNER parallel:Frontend & UI E2E Tests (Parallel)")
        ;;
    deploy|deploy_tests)
        check_docker
        SUITES_TO_RUN=("$DEPLOY_RUNNER parallel:Deployment Integration Tests (Parallel)")
        ;;
    vpn|vpn_tests)
        check_docker
        SUITES_TO_RUN=("$VPN_RUNNER parallel:VPN E2E Traffic Tests (Parallel)")
        ;;
    all|--all|parallel|--parallel)
        check_docker
        SUITES_TO_RUN=(
            "$UI_RUNNER parallel:Frontend & UI E2E Tests (Parallel)"
            "$DEPLOY_RUNNER parallel:Deployment Integration Tests (Parallel)"
            "$VPN_RUNNER parallel:VPN E2E Traffic Tests (Parallel)"
        )
        ;;
    sequential)
        check_docker
        SUITES_TO_RUN=(
            "$UI_RUNNER sequential:Frontend & UI E2E Tests (Sequential)"
            "$DEPLOY_RUNNER sequential:Deployment Integration Tests (Sequential)"
            "$VPN_RUNNER sequential:VPN E2E Traffic Tests (Sequential)"
        )
        ;;
    *)
        echo -e "${RED}[ERROR] Unknown test suite target: '$TARGET'${NC}"
        echo "Valid options: all, ui, deploy, vpn, parallel, sequential, --down, --help"
        exit 1
        ;;
esac

echo -e "${CYAN}Selected ${#SUITES_TO_RUN[@]} master test suite(s) to execute.${NC}\n"

TOTAL_START=$(date +%s)
FAILED_SUITES=0
PASSED_SUITES=0
declare -a MASTER_RESULTS=()

for item in "${SUITES_TO_RUN[@]}"; do
    runner_full="${item%%:*}"
    title="${item#*:}"

    cmd=$(echo "$runner_full" | awk '{print $1}')
    arg=$(echo "$runner_full" | awk '{print $2}')
    [ -z "$arg" ] && arg="all"

    if [ ! -x "$cmd" ]; then
        chmod +x "$cmd" 2>/dev/null || true
    fi

    echo -e "\n${BOLD}${CYAN}>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>${NC}"
    echo -e "${BOLD}${CYAN}▶ STARTING: $title${NC}"
    echo -e "${BOLD}${CYAN}>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>${NC}\n"

    SUITE_START=$(date +%s)
    
    if "$cmd" "$arg"; then
        SUITE_END=$(date +%s)
        SUITE_DUR=$((SUITE_END - SUITE_START))
        PASSED_SUITES=$((PASSED_SUITES + 1))
        MASTER_RESULTS+=("${GREEN}✔ [PASS]${NC} $title (${SUITE_DUR}s)")
    else
        SUITE_END=$(date +%s)
        SUITE_DUR=$((SUITE_END - SUITE_START))
        FAILED_SUITES=$((FAILED_SUITES + 1))
        MASTER_RESULTS+=("${RED}✘ [FAIL]${NC} $title (${SUITE_DUR}s)")
    fi
done

TOTAL_END=$(date +%s)
TOTAL_DURATION=$((TOTAL_END - TOTAL_START))

echo -e "\n${CYAN}${BOLD}"
echo "=================================================================="
echo "                   MASTER TEST RUN SUMMARY                        "
echo "=================================================================="
echo -e "${NC}"

for res in "${MASTER_RESULTS[@]}"; do
    echo -e "  $res"
done

echo -e "${CYAN}==================================================================${NC}"
echo -e "${BOLD}Total Duration: ${TOTAL_DURATION}s | Passed Suites: ${PASSED_SUITES} | Failed Suites: ${FAILED_SUITES}${NC}\n"

if [ "$FAILED_SUITES" -gt 0 ]; then
    echo -e "${RED}${BOLD}❌ Some test suites failed! Please check logs above.${NC}\n"
    exit 1
else
    echo -e "${GREEN}${BOLD}🎉 ALL MASTER TEST SUITES PASSED! 🎉${NC}\n"
    exit 0
fi
