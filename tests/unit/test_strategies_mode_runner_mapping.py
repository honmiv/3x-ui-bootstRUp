#!/usr/bin/env python3
"""Unit test verifying each mode in STRATEGIES maps to the expected runner callback."""

import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from deployers.strategies import (
    STRATEGIES,
    _run_single,
    _run_freedom_sub,
    _run_cascade,
    _run_sub_only,
    _run_backup,
    _run_recovery,
    _run_update,
    _run_restart,
    _run_sub_ops,
)


class TestStrategiesModeRunnerMapping(unittest.TestCase):
    EXPECTED_RUNNERS = {
        "single": _run_single,
        "proxy_only": _run_single,
        "freedom_only": _run_single,
        "freedom_component": _run_single,
        "freedom_sub": _run_freedom_sub,
        "cascade": _run_cascade,
        "cascade_sub": _run_cascade,
        "sub_only": _run_sub_only,
        "backup": _run_backup,
        "recovery": _run_recovery,
        "update_3xui": _run_update,
        "restart_panel": _run_restart,
        "restart_server": _run_restart,
        "restart_sub": _run_sub_ops,
        "update_sub": _run_sub_ops,
        "backup_sub": _run_sub_ops,
        "rollback_sub": _run_sub_ops,
    }

    def test_mode_runner_mapping(self):
        for mode, expected_runner in self.EXPECTED_RUNNERS.items():
            strategy = STRATEGIES.get(mode)
            self.assertIsNotNone(strategy, f"Mode {mode} not found in STRATEGIES")
            self.assertIs(
                strategy.run,
                expected_runner,
                f"Mode '{mode}' mapped to {strategy.run.__name__}, expected {expected_runner.__name__}",
            )


if __name__ == "__main__":
    unittest.main()
