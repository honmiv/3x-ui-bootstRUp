#!/usr/bin/env python3
"""Unit test for server port binding on a free port."""

import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import main as backend_main


class TestServerPortBindFree(unittest.TestCase):
    def test_bind_server_on_free_port(self):
        server, port = backend_main.bind_server(start_port=8085)
        try:
            self.assertEqual(port, 8085)
            self.assertIsNotNone(server)
        finally:
            server.server_close()


if __name__ == "__main__":
    unittest.main()
