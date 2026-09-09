#!/usr/bin/env python3
"""Unit test verifying bind_server kills stale local instances and rebinds the same port."""

import os
import socket
import subprocess
import sys
import time
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import main as backend_main


def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((host, port))
            return False
        except OSError:
            return True


class TestServerPortKillsStale(unittest.TestCase):
    def test_kills_stale_instance_and_rebinds_same_port(self):
        old_proc = subprocess.Popen(
            [sys.executable, "main.py"],
            cwd=backend_main.APP_DIR,
            env={**os.environ, "PORT": "8088"},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        for _ in range(50):
            if is_port_in_use(8088):
                break
            time.sleep(0.1)

        self.assertTrue(is_port_in_use(8088))

        try:
            server, port = backend_main.bind_server(start_port=8088)
            try:
                self.assertEqual(port, 8088)
            finally:
                server.server_close()
        finally:
            if old_proc.poll() is None:
                old_proc.kill()


if __name__ == "__main__":
    unittest.main()
