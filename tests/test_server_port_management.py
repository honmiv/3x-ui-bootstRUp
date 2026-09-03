import os
import signal
import socket
import subprocess
import sys
import time
import unittest
from http.server import HTTPServer

import main as backend_main

def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((host, port))
            return False
        except OSError:
            return True




class TestServerPortManagement(unittest.TestCase):
    def test_bind_server_on_free_port(self):
        server, port = backend_main.bind_server(start_port=8085)
        try:
            self.assertEqual(port, 8085)
            self.assertIsNotNone(server)
        finally:
            server.server_close()

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

    def test_kills_stale_instance_and_rebinds_same_port(self):
        old_proc = subprocess.Popen(
            [sys.executable, "main.py"],
            cwd=backend_main.APP_DIR,
            env={**os.environ, "PORT": "8088"}
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

    def test_server_shutdown_while_serving(self):
        import threading
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
