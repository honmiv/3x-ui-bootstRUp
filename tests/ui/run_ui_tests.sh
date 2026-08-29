#!/usr/bin/env bash
# ==============================================================================
# 3x-UI BootstRUp - Granular Frontend & UI Automated Test Runner
# Runs Playwright E2E browser tests and UI API integration tests.
#
# Usage:
#   ./tests/ui/run_ui_tests.sh [target]
# ==============================================================================

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/docker-compose.test.yml" ]; then
    TESTS_DIR="$SCRIPT_DIR"
    REPO_ROOT="$(dirname "$SCRIPT_DIR")"
    UI_DIR="$SCRIPT_DIR/ui"
elif [ -f "$SCRIPT_DIR/../docker-compose.test.yml" ]; then
    TESTS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
    REPO_ROOT="$(dirname "$TESTS_DIR")"
    UI_DIR="$SCRIPT_DIR"
else
    REPO_ROOT="$SCRIPT_DIR"
    TESTS_DIR="$SCRIPT_DIR/tests"
    UI_DIR="$TESTS_DIR/ui"
fi

# Colors
NC='\033[0m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
BOLD='\033[1m'

PYTHON_BIN="python3"
if [ -x "$REPO_ROOT/.python_env/bin/python3" ]; then
    PYTHON_BIN="$REPO_ROOT/.python_env/bin/python3"
fi

banner() {
    echo -e "${CYAN}${BOLD}"
    echo "=================================================================="
    echo "         3x-UI BootstRUp - Frontend & UI Test Suite               "
    echo "=================================================================="
    echo -e "${NC}"
}

ensure_environment() {
    if ! "$PYTHON_BIN" -c "import yaml; from playwright.sync_api import sync_playwright; p = sync_playwright().start(); b = p.chromium.launch(headless=True); b.close(); p.stop()" >/dev/null 2>&1; then
        echo -e "${YELLOW}[..] Playwright, dependencies or Chromium missing. Provisioning environment via setup_tests.sh...${NC}"
        "$TESTS_DIR/setup_tests.sh"
        if [ -x "$REPO_ROOT/.python_env/bin/python3" ]; then
            PYTHON_BIN="$REPO_ROOT/.python_env/bin/python3"
        fi
    fi
}

banner
ensure_environment

TARGET="${1:-all}"
declare -a TESTS_TO_RUN=()

case "$TARGET" in
    pin|vault_pin|test_ui_server_vault_pin.py)
        TESTS_TO_RUN=("$UI_DIR/test_ui_server_vault_pin.py")
        ;;
    lock|drawer_lock|test_ui_server_drawer_lock.py)
        TESTS_TO_RUN=("$UI_DIR/test_ui_server_drawer_lock.py")
        ;;
    autofill|fill|test_ui_server_autofill.py)
        TESTS_TO_RUN=("$UI_DIR/test_ui_server_autofill.py")
        ;;
    reset|vault_reset|test_ui_server_vault_reset.py)
        TESTS_TO_RUN=("$UI_DIR/test_ui_server_vault_reset.py")
        ;;
    modes|sections|test_ui_wizard_mode_sections.py)
        TESTS_TO_RUN=("$UI_DIR/test_ui_wizard_mode_sections.py")
        ;;
    stepper|nav|test_ui_stepper_navigation.py)
        TESTS_TO_RUN=("$UI_DIR/test_ui_stepper_navigation.py")
        ;;
    session|persistence|test_ui_session_persistence.py)
        TESTS_TO_RUN=("$UI_DIR/test_ui_session_persistence.py")
        ;;
    validation|test_ui_client_validation.py)
        TESTS_TO_RUN=("$UI_DIR/test_ui_client_validation.py")
        ;;
    sse|logs|terminal|test_ui_terminal_sse_logs.py)
        TESTS_TO_RUN=("$UI_DIR/test_ui_terminal_sse_logs.py")
        ;;
    stop|cancel|test_ui_deploy_cancellation.py)
        TESTS_TO_RUN=("$UI_DIR/test_ui_deploy_cancellation.py")
        ;;
    notifications|buttons|test_ui_button_notifications.py)
        TESTS_TO_RUN=("$UI_DIR/test_ui_button_notifications.py")
        ;;
    versions|test_ui_xui_versions_dropdown.py)
        TESTS_TO_RUN=("$UI_DIR/test_ui_xui_versions_dropdown.py")
        ;;
    freedom_client|freedom_default|test_ui_freedom_client_default_and_override.py)
        TESTS_TO_RUN=("$UI_DIR/test_ui_freedom_client_default_and_override.py")
        ;;
    sub_auth|test_ui_sub_server_auth.py)
        TESTS_TO_RUN=("$UI_DIR/test_ui_sub_server_auth.py")
        ;;
    sub_clients|test_ui_sub_server_clients.py)
        TESTS_TO_RUN=("$UI_DIR/test_ui_sub_server_clients.py")
        ;;
    panel_url|test_ui_server_panel_url.py)
        TESTS_TO_RUN=("$UI_DIR/test_ui_server_panel_url.py")
        ;;
    reorder|drag|test_ui_server_reorder.py)
        TESTS_TO_RUN=("$UI_DIR/test_ui_server_reorder.py")
        ;;
    servers|server_vault)
        TESTS_TO_RUN=(
            "$UI_DIR/test_ui_server_vault_pin.py"
            "$UI_DIR/test_ui_server_drawer_lock.py"
            "$UI_DIR/test_ui_server_panel_url.py"
            "$UI_DIR/test_ui_server_autofill.py"
            "$UI_DIR/test_ui_server_reorder.py"
            "$UI_DIR/test_ui_server_vault_reset.py"
        )
        ;;
    wizard)
        TESTS_TO_RUN=(
            "$UI_DIR/test_ui_wizard_mode_sections.py"
            "$UI_DIR/test_ui_stepper_navigation.py"
            "$UI_DIR/test_ui_session_persistence.py"
            "$UI_DIR/test_ui_client_validation.py"
        )
        ;;
    sub|sub_server)
        TESTS_TO_RUN=(
            "$UI_DIR/test_ui_sub_server_auth.py"
            "$UI_DIR/test_ui_sub_server_clients.py"
        )
        ;;
    sequential|seq)
        TESTS_TO_RUN=("$UI_DIR"/test_*.py)
        ;;
    all|--all|ui|ui_all|parallel|--parallel|-p)
        "$PYTHON_BIN" "$UI_DIR/run_ui_parallel.py"
        exit $?
        ;;
    *)
        echo -e "${RED}[ERROR] Unknown UI test target: '$TARGET'${NC}"
        echo "Valid targets: all, servers, wizard, sub, pin, lock, autofill, reset, modes, stepper, session, validation, sse, stop, versions, sub_auth, sub_clients"
        exit 1
        ;;
esac

echo -e "${CYAN}Selected ${#TESTS_TO_RUN[@]} UI test suite(s) to execute.${NC}\n"

TOTAL_START=$(date +%s)
FAILED_COUNT=0
PASSED_COUNT=0
declare -a TEST_RESULTS=()

for test_script in "${TESTS_TO_RUN[@]}"; do
    test_name="$(basename "$test_script")"
    echo -e "\n${BOLD}${CYAN}▶ Running $test_name...${NC}"
    START_TIME=$(date +%s)

    if "$PYTHON_BIN" "$test_script"; then
        END_TIME=$(date +%s)
        DURATION=$((END_TIME - START_TIME))
        PASSED_COUNT=$((PASSED_COUNT + 1))
        TEST_RESULTS+=("${GREEN}✔ [PASS]${NC} $test_name (${DURATION}s)")
    else
        END_TIME=$(date +%s)
        DURATION=$((END_TIME - START_TIME))
        FAILED_COUNT=$((FAILED_COUNT + 1))
        TEST_RESULTS+=("${RED}✘ [FAIL]${NC} $test_name (${DURATION}s)")
    fi
done

TOTAL_END=$(date +%s)
TOTAL_DURATION=$((TOTAL_END - TOTAL_START))

echo -e "\n${CYAN}${BOLD}"
echo "=================================================================="
echo "                     UI TEST RUN SUMMARY                          "
echo "=================================================================="
echo -e "${NC}"

for result in "${TEST_RESULTS[@]}"; do
    echo -e "  $result"
done

echo -e "${CYAN}==================================================================${NC}"
echo -e "${BOLD}Total Duration: ${TOTAL_DURATION}s | Passed: ${PASSED_COUNT} | Failed: ${FAILED_COUNT}${NC}\n"

if [ "$FAILED_COUNT" -gt 0 ]; then
    echo -e "${RED}${BOLD}❌ Some UI tests failed! Please check logs above.${NC}\n"
    exit 1
else
    echo -e "${GREEN}${BOLD}🎉 ALL UI TESTS PASSED! 🎉${NC}\n"
    exit 0
fi
