#!/usr/bin/env python3
"""
Parallel Test Runner for VPN Connectivity E2E test suites.
Runs all 5 VPN test suites concurrently across worker processes.
Each test operates against its dedicated, isolated Docker VPS container and XRay test client.
"""

import concurrent.futures
import glob
import os
import subprocess
import sys
import time

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
VPN_DIR = os.path.join(REPO_ROOT, "tests", "vpn")

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


def main():
    tests_to_run = sorted(glob.glob(os.path.join(VPN_DIR, "test_*.py")))
    max_workers = min(len(tests_to_run), os.cpu_count() or 5)

    print("\033[0;36m\033[1m==================================================================")
    print("      3x-UI BootstRUp - PARALLEL VPN Connectivity Test Runner     ")
    print("==================================================================\033[0m")
    print(f"\033[0;36mRunning {len(tests_to_run)} VPN test suites concurrently across {max_workers} workers...\033[0m\n")

    suite_start = time.time()
    results = []

    with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
        future_map = {executor.submit(run_single_test, t): t for t in tests_to_run}
        for future in concurrent.futures.as_completed(future_map):
            res = future.result()
            results.append(res)
            status_tag = "\033[0;32m✔ [PASS]\033[0m" if res["returncode"] == 0 else "\033[0;31m✘ [FAIL]\033[0m"
            print(f"  {status_tag} {res['name']} ({res['duration']:.1f}s)")
            if res["returncode"] != 0:
                print(f"\n--- Output of {res['name']} ---\n{res['output']}\n------------------------\n")

    total_duration = time.time() - suite_start
    passed_count = sum(1 for r in results if r["returncode"] == 0)
    failed_count = sum(1 for r in results if r["returncode"] != 0)

    print("\n\033[0;36m\033[1m==================================================================")
    print("                 PARALLEL VPN TEST RUN SUMMARY                    ")
    print("==================================================================\033[0m")
    print(f"\033[1mTotal Time: {total_duration:.1f}s | Concurrency: {max_workers}x | Passed: {passed_count} | Failed: {failed_count}\033[0m\n")

    if failed_count > 0:
        print("\033[0;31m\033[1m❌ Some parallel VPN tests failed!\033[0m\n")
        sys.exit(1)
    else:
        print("\033[0;32m\033[1m🎉 ALL PARALLEL VPN TESTS PASSED! 🎉\033[0m\n")
        sys.exit(0)


if __name__ == "__main__":
    main()
