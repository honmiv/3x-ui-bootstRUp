#!/usr/bin/env python3
"""Unit test: _probe_remote_http_port connection refused path."""

import asyncio
import os
import sys
import unittest
from unittest.mock import AsyncMock, patch

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from ssh_deployer import _probe_remote_http_port


class TestProbeRemoteHttpPortConnectionRefused(unittest.TestCase):
    def test_probe_remote_http_port_connection_refused(self):
        with patch("ssh_deployer.SSHDeployer") as mock_deployer_cls, \
             patch("asyncio.open_connection") as mock_open_conn:

            mock_instance = AsyncMock()
            mock_instance.__aenter__.return_value = mock_instance

            async def fake_exec_cmd(cmd, callback=None):
                if callback:
                    callback("PROBE_HTTP_LISTENING")
                return 0, "PROBE_HTTP_DONE"

            mock_instance.exec_command.side_effect = fake_exec_cmd
            mock_deployer_cls.return_value = mock_instance

            mock_open_conn.side_effect = ConnectionRefusedError()

            logs = []
            ok, err = asyncio.run(_probe_remote_http_port(
                "example.com", 22222, 22, "root", "pass", "", lambda m, lvl: logs.append((m, lvl))
            ))

            self.assertFalse(ok)
            self.assertIn("Connection refused", err)


if __name__ == "__main__":
    unittest.main()
