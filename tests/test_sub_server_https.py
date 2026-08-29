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

    def test_subscription_forwards_routing_and_profile_headers(self):
        import email.message
        fake_headers = email.message.EmailMessage()
        fake_headers["Routing"] = "happ://routing/onadd/test12345"
        fake_headers["Routing-Enable"] = "true"
        fake_headers["Profile-Update-Interval"] = "12"
        fake_headers["Profile-Web-Page-Url"] = "https://example.com/subs/alice"
        fake_headers["Subscription-Userinfo"] = "upload=100; download=200; total=0; expire=0"
        fake_headers["Content-Type"] = "text/plain; charset=utf-8"
        fake_headers["Server"] = "upstream-caddy"
        fake_headers["Connection"] = "keep-alive"

        captured_args = {}

        def mock_fetch(url, user_agent=None, extra_headers=None):
            captured_args["url"] = url
            captured_args["user_agent"] = user_agent
            captured_args["extra_headers"] = extra_headers
            return b"vless://fake-config\n", fake_headers

        orig_fetch = self.sub_mod.fetch_subscription
        self.sub_mod.fetch_subscription = mock_fetch
        try:
            conn = http.client.HTTPConnection("127.0.0.1", self.port)
            conn.request(
                "GET",
                "/subs/alice",
                headers={
                    "Host": "sub.example.com",
                    "X-Forwarded-Proto": "https",
                    "User-Agent": "Happ/3.0.0",
                    "Accept": "*/*",
                },
            )
            resp = conn.getresponse()
            body = resp.read()
            self.assertEqual(resp.status, 200)
            self.assertEqual(body, b"vless://fake-config\n")
            self.assertEqual(resp.getheader("Routing"), "happ://routing/onadd/test12345")
            self.assertEqual(resp.getheader("Routing-Enable"), "true")
            self.assertEqual(resp.getheader("Profile-Update-Interval"), "12")
            self.assertEqual(resp.getheader("Profile-Web-Page-Url"), "https://example.com/subs/alice")
            self.assertEqual(resp.getheader("Subscription-Userinfo"), "upload=100; download=200; total=0; expire=0")
            self.assertEqual(resp.getheader("Content-Length"), str(len(b"vless://fake-config\n")))
            self.assertNotEqual(resp.getheader("Server"), "upstream-caddy")

            self.assertEqual(captured_args["url"], "https://example.com/subs/alice")
            self.assertEqual(captured_args["user_agent"], "Happ/3.0.0")
            self.assertEqual(captured_args["extra_headers"].get("Accept"), "*/*")
            conn.close()
        finally:
            self.sub_mod.fetch_subscription = orig_fetch

    def test_raw_subscription_list_formatting(self):
        self.sub_mod.NODES = [
            {
                "id": "node1",
                "name": "Node 1",
                "url": "https://node1.example.com/subs",
                "clients": ["alice", "bob"],
            },
            {
                "id": "node2",
                "name": "Node 2",
                "url": "https://node2.example.com/subs",
                "clients": ["charlie"],
            },
        ]
        import base64
        auth_header = "Basic " + base64.b64encode(b"admin:pass123").decode("ascii")
        conn = http.client.HTTPConnection("127.0.0.1", self.port)
        conn.request(
            "GET",
            "/subs?raw=1",
            headers={
                "Host": "sub.example.com",
                "X-Forwarded-Proto": "https",
                "Authorization": auth_header,
            },
        )
        resp = conn.getresponse()
        body = resp.read().decode("utf-8")
        self.assertEqual(resp.status, 200)
        expected = (
            "alice,bob\n"
            "https://node1.example.com/subs/alice\n"
            "https://node1.example.com/subs/bob\n"
            "========================\n"
            "charlie\n"
            "https://node2.example.com/subs/charlie\n"
        )
        self.assertEqual(body, expected)
        conn.close()


if __name__ == "__main__":
    unittest.main()
