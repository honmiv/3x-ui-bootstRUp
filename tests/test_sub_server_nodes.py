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


class TestSubServerNodes(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_sub_nodes_")
        self.nodes_file = os.path.join(self.temp_dir, "nodes.json")
        self.force_file = os.path.join(self.temp_dir, "force-subs.yml")
        self.log_file = os.path.join(self.temp_dir, "sub-server.log")

        os.environ["NODES_FILE"] = self.nodes_file
        os.environ["FORCE_FILE"] = self.force_file
        os.environ["LOG_FILE"] = self.log_file
        os.environ["SECRET_SUB_PATH"] = "subs"
        os.environ["ADMIN_USER"] = "admin"
        os.environ["ADMIN_PASSWORD"] = "pass123"
        os.environ["PROXY_DOMAIN"] = "proxy.example.com"
        os.environ["FREEDOM_DOMAIN"] = "freedom.example.com"

        spec = importlib.util.spec_from_file_location(
            "sub_server_mod_nodes", os.path.join(REPO_ROOT, "sub-server", "server.py")
        )
        self.sub_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.sub_mod)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_legacy_nodes_backward_compatibility(self):
        with open(self.nodes_file, "w", encoding="utf-8") as f:
            json.dump([
                {"id": "proxy", "name": "Proxy (РФ)", "url": "https://ru-node.example.org/subs", "clients": ["alice"]},
                {"id": "freedom", "name": "Freedom (зарубежье)", "url": "https://eu-node.example.org/subs", "clients": ["bob"]},
            ], f)

        nodes = self.sub_mod.load_nodes(self.nodes_file)
        self.assertEqual(len(nodes), 2)
        self.assertEqual(nodes[0]["type"], "proxy")
        self.assertEqual(nodes[0]["name"], "ru-node.example.org")
        self.assertEqual(nodes[1]["type"], "freedom")
        self.assertEqual(nodes[1]["name"], "eu-node.example.org")

    def test_default_nodes_env_domain(self):
        os.environ["RUSSIAN_SUB_URL"] = "https://proxy.example.com/subs"
        os.environ["FOREIGN_SUB_URL"] = "https://freedom.example.com/subs"
        self.sub_mod.RUSSIAN_SUB_URL = "https://proxy.example.com/subs"
        self.sub_mod.FOREIGN_SUB_URL = "https://freedom.example.com/subs"

        nodes = self.sub_mod.default_nodes()
        self.assertEqual(len(nodes), 2)
        self.assertEqual(nodes[0]["type"], "proxy")
        self.assertEqual(nodes[0]["name"], "proxy.example.com")
        self.assertEqual(nodes[1]["type"], "freedom")
        self.assertEqual(nodes[1]["name"], "freedom.example.com")

    def test_add_and_edit_node_api(self):
        with open(self.nodes_file, "w", encoding="utf-8") as f:
            json.dump([
                {"id": "node-1", "type": "proxy", "name": "proxy.initial.org", "url": "https://proxy.initial.org/subs", "clients": []}
            ], f)

        self.sub_mod.NODES = self.sub_mod.load_nodes(self.nodes_file)
        server = ThreadingHTTPServer(("127.0.0.1", 0), self.sub_mod.Handler)
        port = server.server_address[1]
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()

        try:
            conn = http.client.HTTPConnection("127.0.0.1", port)
            login_payload = "user=admin&password=pass123"
            conn.request("POST", "/subs/login", body=login_payload, headers={"Content-Type": "application/x-www-form-urlencoded"})
            resp = conn.getresponse()
            resp.read()
            cookie = resp.getheader("Set-Cookie", "").split(";")[0]

            add_payload = json.dumps({
                "action": "add",
                "type": "freedom",
                "domain": "eu.exit.org",
                "url": "my-secret-subs"
            })
            conn.request("POST", "/subs/api/node", body=add_payload, headers={
                "Content-Type": "application/json",
                "Cookie": cookie
            })
            resp = conn.getresponse()
            res_data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(res_data.get("ok"))

            added_node = next((n for n in self.sub_mod.NODES if n["name"] == "eu.exit.org"), None)
            self.assertIsNotNone(added_node)
            self.assertEqual(added_node["type"], "freedom")
            self.assertEqual(added_node["url"], "https://eu.exit.org/my-secret-subs")

            edit_payload = json.dumps({
                "action": "edit",
                "node": added_node["id"],
                "type": "proxy",
                "domain": "proxy-updated.exit.org",
                "url": "https://proxy-updated.exit.org/subs"
            })
            conn.request("POST", "/subs/api/node", body=edit_payload, headers={
                "Content-Type": "application/json",
                "Cookie": cookie
            })
            resp = conn.getresponse()
            res_data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(res_data.get("ok"))

            edited_node = next((n for n in self.sub_mod.NODES if n["id"] == added_node["id"]), None)
            self.assertIsNotNone(edited_node)
            self.assertEqual(edited_node["type"], "proxy")
            self.assertEqual(edited_node["name"], "proxy-updated.exit.org")

            conn.request("GET", "/subs", headers={"Cookie": cookie, "Accept": "text/html"})
            resp = conn.getresponse()
            html_body = resp.read().decode("utf-8")
            self.assertIn("node-type-badge proxy", html_body)
            self.assertIn("proxy.initial.org", html_body)
            self.assertIn("proxy-updated.exit.org", html_body)
            self.assertIn("new-node-type-select", html_body)

        finally:
            server.shutdown()
            server.server_close()
            t.join(timeout=2.0)


if __name__ == "__main__":
    unittest.main()
