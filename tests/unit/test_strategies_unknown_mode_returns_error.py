#!/usr/bin/env python3
"""Unit test verifying run_deployment returns error for unknown modes."""

import asyncio
import os
import sys
import unittest
from unittest.mock import patch

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from ssh_deployer import run_deployment


class TestStrategiesUnknownModeReturnsError(unittest.TestCase):
    def test_unknown_mode_returns_error(self):
        logs = []
        with patch("ssh_deployer.validate_deployment_config", return_value=(True, "")):
            ok, result = asyncio.run(
                run_deployment(
                    {"deploy_mode": "non_existent_mode_xyz"},
                    lambda m, lvl: logs.append((m, lvl)),
                )
            )
            self.assertFalse(ok)
            self.assertIn("error", result)
            self.assertIn("Неизвестный режим", result["error"])


if __name__ == "__main__":
    unittest.main()
