#!/usr/bin/env bash
# ==============================================================================
# 3x-UI BootstRUp - Automated VPN Traffic Integration Tests Runner
# Verifies real tunneling, XRay core connections, and IP egress via echo-server.
#
# Usage:
#   ./tests/vpn/run_vpn_tests.sh              # Run all VPN connectivity tests
#   ./tests/vpn/run_vpn_tests.sh freedom      # Test Freedom Node VPN egress only
#   ./tests/vpn/run_vpn_tests.sh --down       # Tear down and clean up test containers
# ==============================================================================

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/docker-compose.test.yml" ]; then
    TESTS_DIR="$SCRIPT_DIR"
    REPO_ROOT="$(dirname "$SCRIPT_DIR")"
    VPN_DIR="$SCRIPT_DIR/vpn"
elif [ -f "$SCRIPT_DIR/../docker-compose.test.yml" ]; then
    TESTS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
    REPO_ROOT="$(dirname "$TESTS_DIR")"
    VPN_DIR="$SCRIPT_DIR"
else
    REPO_ROOT="$SCRIPT_DIR"
    TESTS_DIR="$SCRIPT_DIR/tests"
    VPN_DIR="$TESTS_DIR/vpn"
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
    echo "         3x-UI BootstRUp - VPN E2E Traffic Test Suite            "
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
    docker rm -f vps-test-client-tcp vps-test-client-xhttp vps-test-client >/dev/null 2>&1 || true
    docker compose -f "$COMPOSE_FILE" down --remove-orphans >/dev/null 2>&1 || true
    echo -e "${GREEN}[OK] Test containers stopped and removed.${NC}"
}

if [[ "${1:-}" == "--down" || "${1:-}" == "down" || "${1:-}" == "clean" || "${1:-}" == "--clean" ]]; then
    cleanup_containers
    exit 0
fi

banner
check_docker

# Determine which test(s) to run
TARGET="${1:-all}"
declare -a TESTS_TO_RUN=()

case "$TARGET" in
    freedom|freedom_node|freedom_only)
        TESTS_TO_RUN=("$VPN_DIR/test_vpn_freedom_node.py")
        ;;
    proxy|proxy_node|proxy_only)
        TESTS_TO_RUN=("$VPN_DIR/test_vpn_proxy_node.py")
        ;;
    sub|sub_server|sub_only)
        TESTS_TO_RUN=("$VPN_DIR/test_vpn_sub_server.py")
        ;;
    cascade)
        TESTS_TO_RUN=("$VPN_DIR/test_vpn_cascade.py")
        ;;
    cascade_sub)
        TESTS_TO_RUN=("$VPN_DIR/test_vpn_cascade_sub.py")
        ;;
    sequential|seq)
        TESTS_TO_RUN=("$VPN_DIR"/test_*.py)
        ;;
    all|--all|vpn|vpn_all|parallel|--parallel|-p)
        "$PYTHON_BIN" "$VPN_DIR/run_vpn_parallel.py"
        exit $?
        ;;
    *)
        echo -e "${RED}[ERROR] Unknown VPN test target: '$TARGET'${NC}"
        echo "Valid options: all, freedom, proxy, sub, cascade, cascade_sub, --down"
        exit 1
        ;;
esac

echo -e "${CYAN}Selected ${#TESTS_TO_RUN[@]} VPN test suite(s) to execute.${NC}\n"

TOTAL_START=$(date +%s)
FAILED_COUNT=0
PASSED_COUNT=0
declare -a TEST_RESULTS=()

for test_file in "${TESTS_TO_RUN[@]}"; do
    test_name="$(basename "$test_file")"
    echo -e "${BOLD}${CYAN}▶ Running $test_name...${NC}"
    START_TIME=$(date +%s)

    if "$PYTHON_BIN" "$test_file"; then
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
    echo ""
done

TOTAL_END=$(date +%s)
TOTAL_DURATION=$((TOTAL_END - TOTAL_START))

echo -e "${BOLD}${CYAN}==================================================================${NC}"
echo -e "${BOLD}                     VPN TEST RUN SUMMARY                         ${NC}"
echo -e "${BOLD}${CYAN}==================================================================${NC}"
for res in "${TEST_RESULTS[@]}"; do
    echo -e "  $res"
done
echo -e "${BOLD}${CYAN}==================================================================${NC}"
echo -e "Total Duration: ${TOTAL_DURATION}s | Passed: ${GREEN}${PASSED_COUNT}${NC} | Failed: $([ $FAILED_COUNT -eq 0 ] && echo -e "${GREEN}0${NC}" || echo -e "${RED}${FAILED_COUNT}${NC}")\n"

if [ "$FAILED_COUNT" -gt 0 ]; then
    echo -e "${RED}${BOLD}❌ Some VPN tests failed! Please check logs above.${NC}"
    exit 1
else
    echo -e "${GREEN}${BOLD}🎉 ALL VPN CONNECTIVITY TESTS PASSED!${NC}"
    exit 0
fi
