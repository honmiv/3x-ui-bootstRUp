#!/usr/bin/env python3
"""Unit test: _change_remote_ssh_port aborts when remote probe fails."""

import asyncio
import os
import sys
import unittest
from unittest.mock import AsyncMock, patch

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from ssh_deployer import _change_remote_ssh_port


class TestChangeSshPortProbeFailure(unittest.TestCase):
    def test_change_remote_ssh_port_probe_failure_aborts(self):
        with patch("ssh_deployer._probe_remote_http_port", new_callable=AsyncMock) as mock_probe, \
             patch("ssh_deployer.SSHDeployer") as mock_deployer_cls:
            mock_probe.return_value = (False, "Connection timed out")

            logs = []
            result = asyncio.run(_change_remote_ssh_port(
                "example.com", 22, 22222, "root", "pass", "", lambda m, lvl: logs.append((m, lvl))
            ))

            self.assertFalse(result)
            mock_probe.assert_awaited_once()
            mock_deployer_cls.assert_not_called()
            self.assertTrue(any("не удалась" in m for m, _ in logs))
            self.assertTrue(any("НЕ была изменена" in m for m, _ in logs))


if __name__ == "__main__":
    unittest.main()
