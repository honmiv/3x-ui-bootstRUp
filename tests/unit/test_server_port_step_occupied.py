#!/usr/bin/env python3
"""Unit test for server stepping to next port when current port is occupied by foreign process."""

import os
import socket
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import main as backend_main


class TestServerPortStepOccupied(unittest.TestCase):
    def test_step_to_next_port_when_foreign_process_occupies_port(self):
        foreign_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        foreign_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        foreign_sock.bind(("127.0.0.1", 8086))
        foreign_sock.listen(1)

        try:
            server, port = backend_main.bind_server(start_port=8086)
            try:
                self.assertEqual(port, 8087)
            finally:
                server.server_close()
        finally:
            foreign_sock.close()


if __name__ == "__main__":
    unittest.main()
