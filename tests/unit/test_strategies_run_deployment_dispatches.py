#!/usr/bin/env python3
"""Unit test verifying run_deployment dispatches correctly for all registered modes."""

import asyncio
import os
import sys
import unittest
from unittest.mock import AsyncMock, patch

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from deployers.strategies import ModeStrategy, STRATEGIES
from ssh_deployer import run_deployment


class TestStrategiesRunDeploymentDispatches(unittest.TestCase):
    def test_run_deployment_dispatches_each_mode(self):
        for mode in STRATEGIES.keys():
            mock_run = AsyncMock(return_value=(True, {"ok": True, "mode": mode}))
            dummy_strategy = ModeStrategy(
                modes=(mode,),
                validate=lambda cfg: None,
                run=mock_run,
            )
            with patch.dict(STRATEGIES, {mode: dummy_strategy}), \
                 patch("ssh_deployer.validate_deployment_config", return_value=(True, "")):
                logs = []
                ok, result = asyncio.run(
                    run_deployment(
                        {"deploy_mode": mode},
                        lambda m, lvl: logs.append((m, lvl)),
                    )
                )
                self.assertTrue(ok)
                self.assertEqual(result.get("mode"), mode)
                mock_run.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
