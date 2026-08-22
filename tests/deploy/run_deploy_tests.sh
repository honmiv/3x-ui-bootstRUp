#!/usr/bin/env bash
# ==============================================================================
# 3x-UI BootstRUp - Automated Deployment Integration Tests Runner
# Runs deployment tests across isolated Docker VPS containers.
#
# Usage:
#   ./tests/deploy/run_deploy_tests.sh              # Run all 5 deployment tests
#   ./tests/deploy/run_deploy_tests.sh freedom      # Test Freedom Node deployment only
#   ./tests/deploy/run_deploy_tests.sh proxy        # Test Proxy Node deployment only
#   ./tests/deploy/run_deploy_tests.sh sub          # Test Sub-Server deployment only
#   ./tests/deploy/run_deploy_tests.sh cascade      # Test 2-Stage Cascade (Freedom + Proxy)
#   ./tests/deploy/run_deploy_tests.sh cascade_sub  # Test 3-Stage Cascade (Freedom + Proxy + Sub)
#   ./tests/deploy/run_deploy_tests.sh --down       # Tear down and clean up test containers
# ==============================================================================

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/docker-compose.test.yml" ]; then
    TESTS_DIR="$SCRIPT_DIR"
    REPO_ROOT="$(dirname "$SCRIPT_DIR")"
    DEPLOY_DIR="$SCRIPT_DIR/deploy"
elif [ -f "$SCRIPT_DIR/../docker-compose.test.yml" ]; then
    TESTS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
    REPO_ROOT="$(dirname "$TESTS_DIR")"
    DEPLOY_DIR="$SCRIPT_DIR"
else
    REPO_ROOT="$SCRIPT_DIR"
    TESTS_DIR="$SCRIPT_DIR/tests"
    DEPLOY_DIR="$TESTS_DIR/deploy"
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
    echo "       3x-UI BootstRUp - Deployment Integration Test Suite        "
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
    freedom|freedom_only)
        TESTS_TO_RUN=("$DEPLOY_DIR/test_deploy_freedom_node.py")
        ;;
    proxy|proxy_only)
        TESTS_TO_RUN=("$DEPLOY_DIR/test_deploy_proxy_node.py")
        ;;
    sub|sub_only|sub_server)
        TESTS_TO_RUN=("$DEPLOY_DIR/test_deploy_sub_server.py")
        ;;
    cascade)
        TESTS_TO_RUN=("$DEPLOY_DIR/test_deploy_cascade.py")
        ;;
    cascade_sub)
        TESTS_TO_RUN=("$DEPLOY_DIR/test_deploy_cascade_sub.py")
        ;;
    sequential|seq)
        TESTS_TO_RUN=("$DEPLOY_DIR"/test_*.py)
        ;;
    all|--all|deploy|deploy_all|parallel|--parallel|-p)
        "$PYTHON_BIN" "$DEPLOY_DIR/run_deploy_parallel.py"
        exit $?
        ;;
    *)
        echo -e "${RED}[ERROR] Unknown test target: '$TARGET'${NC}"
        echo "Valid options: all, freedom, proxy, sub, cascade, cascade_sub, --down"
        exit 1
        ;;
esac

echo -e "${CYAN}Selected ${#TESTS_TO_RUN[@]} deployment test suite(s) to execute.${NC}\n"

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
echo -e "${BOLD}                   DEPLOYMENT TEST RUN SUMMARY                    ${NC}"
echo -e "${BOLD}${CYAN}==================================================================${NC}"
for res in "${TEST_RESULTS[@]}"; do
    echo -e "  $res"
done
echo -e "${BOLD}${CYAN}==================================================================${NC}"
echo -e "Total Duration: ${TOTAL_DURATION}s | Passed: ${GREEN}${PASSED_COUNT}${NC} | Failed: $([ $FAILED_COUNT -eq 0 ] && echo -e "${GREEN}0${NC}" || echo -e "${RED}${FAILED_COUNT}${NC}")\n"

if [ "$FAILED_COUNT" -gt 0 ]; then
    echo -e "${RED}${BOLD}❌ Some deployment tests failed! Please check logs above.${NC}"
    exit 1
else
    echo -e "${GREEN}${BOLD}🎉 ALL DEPLOYMENT TESTS PASSED! Ready for push.${NC}"
    exit 0
fi
