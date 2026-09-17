#!/usr/bin/env python3
"""Unit test: _change_remote_ssh_port succeeds when probe and verification succeed."""

import asyncio
import os
import sys
import unittest
from unittest.mock import AsyncMock, patch

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from ssh_deployer import _change_remote_ssh_port


class TestChangeSshPortProbeSuccess(unittest.TestCase):
    def test_change_remote_ssh_port_probe_success(self):
        with (
            patch("ssh_deployer._probe_remote_http_port", new_callable=AsyncMock) as mock_probe,
            patch("ssh_deployer.SSHDeployer") as mock_deployer_cls,
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            mock_probe.return_value = (True, "")

            mock_instance = AsyncMock()
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.exec_command.return_value = (0, "ok")
            mock_instance.test_connection.return_value = (True, "Connection successful")
            mock_deployer_cls.return_value = mock_instance

            logs = []
            result = asyncio.run(_change_remote_ssh_port(
                "example.com", 22, 22222, "root", "pass", "", lambda m, lvl: logs.append((m, lvl))
            ))

            self.assertTrue(result)
            mock_probe.assert_awaited_once()
            self.assertTrue(any("успешно настроен" in m for m, _ in logs))


if __name__ == "__main__":
    unittest.main()
