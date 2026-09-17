#!/usr/bin/env python3
"""
Parallel Test Runner for Unit tests.
Runs all isolated unit test suites concurrently using ProcessPoolExecutor.
Output matches the clean, formatted output of UI and deployment tests:
  ✔ [PASS] test_name.py (0.1s)
"""

import concurrent.futures
import glob
import os
import subprocess
import sys
import time

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
UNIT_DIR = os.path.join(REPO_ROOT, "tests", "unit")

PYTHON_BIN = sys.executable
if os.path.exists(os.path.join(REPO_ROOT, ".python_env", "bin", "python3")):
    PYTHON_BIN = os.path.join(REPO_ROOT, ".python_env", "bin", "python3")


def run_single_test(test_path: str):
    """Executes a single test script in an isolated subprocess."""
    test_name = os.path.basename(test_path)
    start_time = time.time()

    proc = subprocess.run(
        [PYTHON_BIN, test_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=REPO_ROOT
    )
    duration = time.time() - start_time
    return {
        "name": test_name,
        "returncode": proc.returncode,
        "duration": duration,
        "output": proc.stdout
    }


DEFAULT_WORKERS = os.cpu_count() or 4


def parse_args():
    if "--default-workers" in sys.argv:
        print(DEFAULT_WORKERS)
        sys.exit(0)

    workers = DEFAULT_WORKERS
    target = "all"

    for arg in sys.argv[1:]:
        if arg.startswith("--unit-workers="):
            try:
                workers = int(arg.split("=", 1)[1])
            except ValueError:
                pass
        elif arg.startswith("--workers="):
            try:
                workers = int(arg.split("=", 1)[1])
            except ValueError:
                pass
        elif not arg.startswith("-") and target == "all":
            target = arg

    return target, workers


def main():
    target, req_workers = parse_args()

    if target in ("all", "--all", "parallel", "--parallel", "-p", ""):
        tests_to_run = sorted(glob.glob(os.path.join(UNIT_DIR, "test_*.py")))
    else:
        # Filter by pattern
        pattern = target if target.endswith(".py") else f"*{target}*.py"
        tests_to_run = sorted(glob.glob(os.path.join(UNIT_DIR, pattern)))
        if not tests_to_run:
            # Try exact test_ prefix
            tests_to_run = sorted(glob.glob(os.path.join(UNIT_DIR, f"test_{target}*.py")))

    if not tests_to_run:
        print(f"\033[0;31m[ERROR] No unit tests found matching: '{target}'\033[0m")
        sys.exit(1)

    max_workers = max(1, min(len(tests_to_run), req_workers))

    print("\033[0;36m\033[1m==================================================================")
    print("      3x-UI BootstRUp - PARALLEL Isolated Unit Test Runner        ")
    print("==================================================================\033[0m")
    print(f"\033[0;36mRunning {len(tests_to_run)} test suites concurrently across {max_workers} worker processes...\033[0m\n")

    suite_start = time.time()
    results = []

    with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
        future_map = {executor.submit(run_single_test, t): t for t in tests_to_run}
        for future in concurrent.futures.as_completed(future_map):
            res = future.result()
            results.append(res)
            status_tag = "\033[0;32m✔ [PASS]\033[0m" if res["returncode"] == 0 else "\033[0;31m✘ [FAIL]\033[0m"
            print(f"  {status_tag} {res['name']} ({res['duration']:.1f}s)", flush=True)
            if res["returncode"] != 0:
                print(f"\n--- Output of {res['name']} ---\n{res['output']}\n------------------------\n", flush=True)

    total_duration = time.time() - suite_start
    passed_count = sum(1 for r in results if r["returncode"] == 0)
    failed_count = sum(1 for r in results if r["returncode"] != 0)

    print("\n\033[0;36m\033[1m==================================================================")
    print("                PARALLEL UNIT TEST RUN SUMMARY                    ")
    print("==================================================================\033[0m")
    print(f"\033[1mTotal Time: {total_duration:.1f}s | Concurrency: {max_workers}x | Passed: {passed_count} | Failed: {failed_count}\033[0m\n")

    if failed_count > 0:
        print("\033[0;31m\033[1m❌ Some unit tests failed!\033[0m\n")
        sys.exit(1)
    else:
        print("\033[0;32m\033[1m🎉 ALL PARALLEL UNIT TESTS PASSED IN RECORD TIME! 🎉\033[0m\n")
        sys.exit(0)


if __name__ == "__main__":
    main()
