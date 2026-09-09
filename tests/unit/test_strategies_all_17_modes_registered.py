#!/usr/bin/env python3
"""Unit test verifying all 17 deployment modes are registered in STRATEGIES."""

import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from deployers.strategies import STRATEGIES


class TestStrategiesAll17ModesRegistered(unittest.TestCase):
    EXPECTED_MODES = {
        "single", "proxy_only", "freedom_only", "freedom_component",
        "freedom_sub", "cascade", "cascade_sub", "sub_only",
        "backup", "recovery", "update_3xui", "restart_panel",
        "restart_server", "restart_sub", "update_sub",
        "backup_sub", "rollback_sub",
    }

    def test_all_17_modes_registered(self):
        registered_modes = set(STRATEGIES.keys())
        self.assertEqual(
            registered_modes,
            self.EXPECTED_MODES,
            f"STRATEGIES keys mismatch: missing={self.EXPECTED_MODES - registered_modes}, extra={registered_modes - self.EXPECTED_MODES}",
        )
        self.assertEqual(len(registered_modes), 17)


if __name__ == "__main__":
    unittest.main()
