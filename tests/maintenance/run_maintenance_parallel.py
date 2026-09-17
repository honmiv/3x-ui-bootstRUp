#!/usr/bin/env python3
"""
Maintenance Test Suite Runner.
Executes maintenance automated test suites.
"""

import concurrent.futures
import glob
import os
import subprocess
import sys
import time

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MAINT_DIR = os.path.join(REPO_ROOT, "tests", "maintenance")

PYTHON_BIN = sys.executable
if os.path.exists(os.path.join(REPO_ROOT, ".python_env", "bin", "python3")):
    PYTHON_BIN = os.path.join(REPO_ROOT, ".python_env", "bin", "python3")


def run_single_test(test_path: str):
    test_name = os.path.basename(test_path)
    start_time = time.time()

    proc = subprocess.run(
        [PYTHON_BIN, test_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=REPO_ROOT,
    )
    duration = time.time() - start_time
    return {
        "name": test_name,
        "returncode": proc.returncode,
        "duration": duration,
        "output": proc.stdout,
    }


try:
    DEFAULT_WORKERS = int(os.environ.get("MAINT_TEST_WORKERS", "1"))
except ValueError:
    DEFAULT_WORKERS = 1


def parse_args():
    if "--default-workers" in sys.argv:
        print(DEFAULT_WORKERS)
        sys.exit(0)

    workers = DEFAULT_WORKERS
    target = "all"

    for arg in sys.argv[1:]:
        if arg.startswith("--maint-workers=") or arg.startswith("--workers="):
            try:
                workers = int(arg.split("=", 1)[1])
            except ValueError:
                pass
        elif not arg.startswith("-") and target == "all":
            target = arg

    return target, workers


def main():
    target, req_workers = parse_args()

    all_tests = sorted(glob.glob(os.path.join(MAINT_DIR, "test_*.py")))

    if target in ["all", "parallel", "seq", "sequential"]:
        tests_to_run = all_tests
    elif target in ["backup", "recovery", "backup_recovery"]:
        tests_to_run = [t for t in all_tests if "backup_recovery" in t]
    elif target in ["update", "update_3xui"]:
        tests_to_run = [t for t in all_tests if "update" in t]
    elif target in ["restart", "restart_panel"]:
        tests_to_run = [t for t in all_tests if "restart" in t]
    elif target in ["sub", "sub_server"]:
        tests_to_run = [t for t in all_tests if "sub_server" in t]
    else:
        matched = [t for t in all_tests if target in os.path.basename(t)]
        if matched:
            tests_to_run = matched
        else:
            print(f"\033[0;31m[ERROR] No test found matching target: {target}\033[0m")
    panel_tests = [t for t in tests_to_run if "test_maint_panel_" in os.path.basename(t)]
    if len(panel_tests) > 1 and req_workers > 1:
        print("\033[0;33m[WARN] Multiple panel maintenance tests share 'vps-maint-panel' container.")
        print("       Enforcing sequential execution (max_workers=1) to prevent state collision.\033[0m\n")
        max_workers = 1
    else:
        max_workers = max(1, min(len(tests_to_run), req_workers))

    print("\033[0;36m\033[1m==================================================================")
    print("        3x-UI BootstRUp - Maintenance Test Suite Runner          ")
    print("==================================================================\033[0m")
    print(f"\033[0;36mRunning {len(tests_to_run)} maintenance test suite(s) across {max_workers} worker(s)...\033[0m\n")

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
                print(f"\n--- Output of failed {res['name']} ---")
                print(res["output"])
                print("--------------------------------------\n")

    total_duration = time.time() - suite_start
    failed_count = sum(1 for r in results if r["returncode"] != 0)
    passed_count = len(results) - failed_count

    print(f"\n\033[1mFinished in {total_duration:.1f}s. Passed: {passed_count}, Failed: {failed_count}\033[0m")
    sys.exit(1 if failed_count > 0 else 0)


if __name__ == "__main__":
    main()

