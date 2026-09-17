#!/usr/bin/env bash
# ==============================================================================
# 3x-UI BootstRUp - Master Test Runner
# Executes all test suites (Deployment tests + VPN E2E traffic tests)
#
# Usage:
#   ./tests/run_all_tests.sh              # Run ALL test suites (Unit + UI + Deploy + VPN + Maintenance)
#   ./tests/run_all_tests.sh deploy       # Run only Deploy test suite
#   ./tests/run_all_tests.sh vpn          # Run only VPN test suite
#   ./tests/run_all_tests.sh maintenance  # Run only Maintenance test suite
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

UNIT_RUNNER="$TESTS_DIR/unit/run_unit_tests.sh"
DEPLOY_RUNNER="$TESTS_DIR/deploy/run_deploy_tests.sh"
VPN_RUNNER="$TESTS_DIR/vpn/run_vpn_tests.sh"
UI_RUNNER="$TESTS_DIR/ui/run_ui_tests.sh"
MAINT_RUNNER="$TESTS_DIR/maintenance/run_maintenance_tests.sh"
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

PYTHON_BIN="python3"
if [ -x "$REPO_ROOT/.python_env/bin/python3" ]; then
    PYTHON_BIN="$REPO_ROOT/.python_env/bin/python3"
fi

# Query default workers from downstream runners (source of truth)
DEF_UNIT_WORKERS=$("$PYTHON_BIN" "$TESTS_DIR/unit/run_unit_parallel.py" --default-workers 2>/dev/null || echo 16)
DEF_UI_WORKERS=$("$PYTHON_BIN" "$TESTS_DIR/ui/run_ui_parallel.py" --default-workers 2>/dev/null || echo 16)
DEF_DEPLOY_WORKERS=$("$PYTHON_BIN" "$TESTS_DIR/deploy/run_deploy_parallel.py" --default-workers 2>/dev/null || echo 6)
DEF_VPN_WORKERS=$("$PYTHON_BIN" "$TESTS_DIR/vpn/run_vpn_parallel.py" --default-workers 2>/dev/null || echo 16)
DEF_MAINT_WORKERS=$("$PYTHON_BIN" "$TESTS_DIR/maintenance/run_maintenance_parallel.py" --default-workers 2>/dev/null || echo 1)

UNIT_WORKERS=""
UI_WORKERS=""
DEPLOY_WORKERS=""
VPN_WORKERS=""
MAINT_WORKERS=""
TARGET=""

for arg in "$@"; do
    case "$arg" in
        --unit-workers=*)
            UNIT_WORKERS="${arg#*=}"
            ;;
        --ui-workers=*)
            UI_WORKERS="${arg#*=}"
            ;;
        --deploy-workers=*)
            DEPLOY_WORKERS="${arg#*=}"
            ;;
        --vpn-workers=*)
            VPN_WORKERS="${arg#*=}"
            ;;
        --maint-workers=*)
            MAINT_WORKERS="${arg#*=}"
            ;;
        *)
            if [ -z "$TARGET" ]; then
                TARGET="$arg"
            fi
            ;;
    esac
done

[ -z "$TARGET" ] && TARGET="all"

ACTUAL_UNIT_WORKERS="${UNIT_WORKERS:-$DEF_UNIT_WORKERS}"
ACTUAL_UI_WORKERS="${UI_WORKERS:-$DEF_UI_WORKERS}"
ACTUAL_DEPLOY_WORKERS="${DEPLOY_WORKERS:-$DEF_DEPLOY_WORKERS}"
ACTUAL_VPN_WORKERS="${VPN_WORKERS:-$DEF_VPN_WORKERS}"
ACTUAL_MAINT_WORKERS="${MAINT_WORKERS:-$DEF_MAINT_WORKERS}"

if [[ "$TARGET" == "--down" || "$TARGET" == "down" || "$TARGET" == "clean" ]]; then
    echo -e "${YELLOW}[..] Tearing down all test containers and networks...${NC}"
    docker compose -f "$COMPOSE_FILE" down -v --remove-orphans 2>/dev/null || true
    echo -e "${GREEN}[OK] All test containers stopped and removed.${NC}"
    echo -e "${YELLOW}[..] Cleaning up tests/working/ temp directories...${NC}"
    find "$TESTS_DIR/working" -maxdepth 1 -name "3xui-test-*" -type d -exec rm -rf {} + 2>/dev/null || true
    echo -e "${GREEN}[OK] tests/working/ cleaned.${NC}"
    exit 0
fi

if [[ "$TARGET" == "-h" || "$TARGET" == "--help" || "$TARGET" == "help" ]]; then
    banner
    echo "Usage: ./tests/run_all_tests.sh [target] [options]"
    echo ""
    echo "Targets:"
    echo "  all (default)  Run all test suites (Unit + UI E2E + Deploy Integration + VPN E2E + Maintenance)"
    echo "  unit           Run fast Python unit tests (tests/unit)"
    echo "  ui             Run only UI & Browser E2E tests"
    echo "  deploy         Run only Deploy Integration tests"
    echo "  vpn            Run only VPN E2E traffic tests"
    echo "  maintenance    Run Maintenance E2E tests (backup, recovery, update, restart, sub)"
    echo "  sequential     Run all test suites sequentially (1 worker per suite)"
    echo "  setup          Setup local dependencies (Playwright, browsers)"
    echo "  --down         Tear down test containers and volumes"
    echo ""
    echo "Parallelism Options (defaults queried from downstream runners):"
    echo "  --unit-workers=N    Concurrency for unit tests (default: $DEF_UNIT_WORKERS)"
    echo "  --ui-workers=N      Concurrency for UI tests (default: $DEF_UI_WORKERS)"
    echo "  --deploy-workers=N  Concurrency for deploy tests (default: $DEF_DEPLOY_WORKERS)"
    echo "  --vpn-workers=N     Concurrency for VPN tests (default: $DEF_VPN_WORKERS)"
    echo "  --maint-workers=N   Concurrency for maintenance tests (default: $DEF_MAINT_WORKERS)"
    echo ""
    exit 0
fi

if [[ "$TARGET" == "setup" || "$TARGET" == "--setup" ]]; then
    exec "$TESTS_DIR/setup_tests.sh"
fi

banner

if [ -z "$UNIT_WORKERS" ] && [ -z "$UI_WORKERS" ] && [ -z "$DEPLOY_WORKERS" ] && [ -z "$VPN_WORKERS" ] && [ -z "$MAINT_WORKERS" ]; then
    echo -e "${YELLOW}Running with default parallelism: --unit-workers=${DEF_UNIT_WORKERS} --ui-workers=${DEF_UI_WORKERS} --deploy-workers=${DEF_DEPLOY_WORKERS} --vpn-workers=${DEF_VPN_WORKERS} --maint-workers=${DEF_MAINT_WORKERS}${NC}"
    echo -e "${YELLOW}You can override any with the arguments listed above (e.g. $0 --unit-workers=4)${NC}\n"
else
    echo -e "${CYAN}Running with parallelism: --unit-workers=${ACTUAL_UNIT_WORKERS} --ui-workers=${ACTUAL_UI_WORKERS} --deploy-workers=${ACTUAL_DEPLOY_WORKERS} --vpn-workers=${ACTUAL_VPN_WORKERS} --maint-workers=${ACTUAL_MAINT_WORKERS}${NC}"
    echo -e "${CYAN}You can override any with: --unit-workers=N --ui-workers=N --deploy-workers=N --vpn-workers=N --maint-workers=N${NC}\n"
fi

ensure_environment() {
    local python_bin="python3"
    if [ -x "$REPO_ROOT/.python_env/bin/python3" ]; then
        python_bin="$REPO_ROOT/.python_env/bin/python3"
    fi

    local needs_setup=false

    if ! "$python_bin" -c "from playwright.sync_api import sync_playwright; p = sync_playwright().start(); b = p.chromium.launch(headless=True); b.close(); p.stop()" >/dev/null 2>&1; then
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

if [[ "$TARGET" != "unit" && "$TARGET" != "unit_tests" ]]; then
    ensure_environment
    echo -e "${YELLOW}[..] Ensuring clean slate: tearing down any leftover test containers...${NC}"
    docker compose -f "$COMPOSE_FILE" down -v --remove-orphans 2>/dev/null || true
    echo -e "${YELLOW}[..] Cleaning up stale tests/working/ temp directories...${NC}"
    find "$TESTS_DIR/working" -maxdepth 1 -name "3xui-test-*" -type d -exec rm -rf {} + 2>/dev/null || true
fi

declare -a SUITES_TO_RUN=()

case "$TARGET" in
    unit|unit_tests)
        SUITES_TO_RUN=("$UNIT_RUNNER all --unit-workers=$ACTUAL_UNIT_WORKERS:Fast Python Unit Tests")
        ;;
    ui|ui_tests)
        SUITES_TO_RUN=("$UI_RUNNER parallel --ui-workers=$ACTUAL_UI_WORKERS:Frontend & UI E2E Tests (Parallel)")
        ;;
    deploy|deploy_tests)
        check_docker
        SUITES_TO_RUN=("$DEPLOY_RUNNER parallel --deploy-workers=$ACTUAL_DEPLOY_WORKERS:Deployment Integration Tests (Parallel)")
        ;;
    vpn|vpn_tests)
        check_docker
        SUITES_TO_RUN=("$VPN_RUNNER parallel --vpn-workers=$ACTUAL_VPN_WORKERS:VPN E2E Traffic Tests (Parallel)")
        ;;
    maintenance|maint|maintenance_tests)
        check_docker
        SUITES_TO_RUN=("$MAINT_RUNNER all --maint-workers=$ACTUAL_MAINT_WORKERS:Maintenance E2E Tests")
        ;;
    all|--all|parallel|--parallel)
        check_docker
        SUITES_TO_RUN=(
            "$UNIT_RUNNER all --unit-workers=$ACTUAL_UNIT_WORKERS:Fast Python Unit Tests"
            "$UI_RUNNER parallel --ui-workers=$ACTUAL_UI_WORKERS:Frontend & UI E2E Tests (Parallel)"
            "$DEPLOY_RUNNER parallel --deploy-workers=$ACTUAL_DEPLOY_WORKERS:Deployment Integration Tests (Parallel)"
            "$VPN_RUNNER parallel --vpn-workers=$ACTUAL_VPN_WORKERS:VPN E2E Traffic Tests (Parallel)"
            "$MAINT_RUNNER all --maint-workers=$ACTUAL_MAINT_WORKERS:Maintenance E2E Tests"
        )
        ;;
    sequential)
        check_docker
        SUITES_TO_RUN=(
            "$UNIT_RUNNER all --unit-workers=1:Fast Python Unit Tests (Sequential)"
            "$UI_RUNNER sequential:Frontend & UI E2E Tests (Sequential)"
            "$DEPLOY_RUNNER sequential:Deployment Integration Tests (Sequential)"
            "$VPN_RUNNER sequential:VPN E2E Traffic Tests (Sequential)"
            "$MAINT_RUNNER all --maint-workers=1:Maintenance E2E Tests (Sequential)"
        )
        ;;
    *)
        echo -e "${RED}[ERROR] Unknown test suite target: '$TARGET'${NC}"
        echo "Valid options: all, unit, ui, deploy, vpn, maintenance, parallel, sequential, --down, --help"
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

    read -r -a cmd_parts <<< "$runner_full"
    cmd="${cmd_parts[0]}"
    args=("${cmd_parts[@]:1}")
    [ ${#args[@]} -eq 0 ] && args=("all")

    if [ ! -x "$cmd" ]; then
        chmod +x "$cmd" 2>/dev/null || true
    fi

    echo -e "\n${BOLD}${CYAN}>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>${NC}"
    echo -e "${BOLD}${CYAN}▶ STARTING: $title${NC}"
    echo -e "${BOLD}${CYAN}>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>${NC}\n"

    SUITE_START=$(date +%s)
    
    if "$cmd" "${args[@]}"; then
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
