#!/usr/bin/env python3
"""Unit test for server shutdown while serving."""

import os
import sys
import threading
import time
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import main as backend_main


class TestServerPortShutdown(unittest.TestCase):
    def test_server_shutdown_while_serving(self):
        server, port = backend_main.bind_server(start_port=8089)
        t = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.1})
        t.start()
        time.sleep(0.2)
        server.shutdown()
        server.server_close()
        t.join(timeout=2.0)
        self.assertFalse(t.is_alive())


if __name__ == "__main__":
    unittest.main()
