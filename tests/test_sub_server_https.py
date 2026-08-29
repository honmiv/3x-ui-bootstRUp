import http.client
import importlib.util
import json
import os
import shutil
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestSubServerHttps(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_sub_https_")
        self.nodes_file = os.path.join(self.temp_dir, "nodes.json")
        self.force_file = os.path.join(self.temp_dir, "force-subs.yml")
        self.log_file = os.path.join(self.temp_dir, "sub-server.log")

        os.environ["NODES_FILE"] = self.nodes_file
        os.environ["FORCE_FILE"] = self.force_file
        os.environ["LOG_FILE"] = self.log_file
        os.environ["SECRET_SUB_PATH"] = "subs"
        os.environ["ADMIN_USER"] = "admin"
        os.environ["ADMIN_PASSWORD"] = "pass123"

        with open(self.nodes_file, "w", encoding="utf-8") as f:
            json.dump([
                {"id": "proxy", "name": "Proxy", "url": "https://example.com/subs", "clients": ["alice"]}
            ], f)

        spec = importlib.util.spec_from_file_location(
            "sub_server_mod", os.path.join(REPO_ROOT, "sub-server", "server.py")
        )
        self.sub_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.sub_mod)
        self.sub_mod.NODES = self.sub_mod.load_nodes(self.nodes_file)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self.sub_mod.Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2.0)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_http_request_with_x_forwarded_proto_redirects_to_https(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port)
        conn.request(
            "GET",
            "/subs/alice",
            headers={
                "Host": "sub.example.com",
                "X-Forwarded-Proto": "http",
                "X-Forwarded-Host": "sub.example.com",
            },
        )
        resp = conn.getresponse()
        self.assertEqual(resp.status, 301)
        self.assertEqual(resp.getheader("Location"), "https://sub.example.com/subs/alice")
        conn.close()

    def test_http_post_with_x_forwarded_proto_redirects_to_https(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port)
        conn.request(
            "POST",
            "/subs/login",
            headers={
                "Host": "sub.example.com",
                "X-Forwarded-Proto": "http",
                "X-Forwarded-Host": "sub.example.com",
            },
        )
        resp = conn.getresponse()
        self.assertEqual(resp.status, 301)
        self.assertEqual(resp.getheader("Location"), "https://sub.example.com/subs/login")
        conn.close()

    def test_https_request_passes_through(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port)
        conn.request(
            "GET",
            "/subs/login",
            headers={
                "Host": "sub.example.com",
                "X-Forwarded-Proto": "https",
            },
        )
        resp = conn.getresponse()
        self.assertEqual(resp.status, 200)
        conn.close()

    def test_public_base_defaults_to_https(self):
        handler = self.sub_mod.Handler.__new__(self.sub_mod.Handler)
        handler.headers = {"Host": "sub.example.com"}
        self.assertEqual(handler._public_base(), "https://sub.example.com")


if __name__ == "__main__":
    unittest.main()
