import json
import os
import re
import unittest
from http.server import HTTPServer
import threading
import http.client

import main as backend_main

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestButtonNotificationsStructure(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(REPO_ROOT, "panel", "static", "index.html"), "r", encoding="utf-8") as f:
            cls.index_html = f.read()
        with open(os.path.join(REPO_ROOT, "panel", "static", "app.js"), "r", encoding="utf-8") as f:
            cls.app_js = f.read()

    def test_custom_confirm_modal_present_in_index_html(self):
        self.assertIn('id="customConfirmModal"', self.index_html)
        self.assertIn('id="customModalTitle"', self.index_html)
        self.assertIn('id="customModalMessage"', self.index_html)
        self.assertIn('id="customModalIconWrapper"', self.index_html)
        self.assertIn('id="customModalIcon"', self.index_html)
        self.assertIn('id="customModalConfirmBtn"', self.index_html)
        self.assertIn('id="customModalCancelBtn"', self.index_html)

    def test_toast_container_present_in_index_html(self):
        self.assertIn('id="toastContainer"', self.index_html)

    def test_action_buttons_present_in_index_html(self):
        self.assertIn('id="btnUpdateSources"', self.index_html)
        self.assertIn('id="btnRestart"', self.index_html)
        self.assertIn('id="btnShutdown"', self.index_html)

    def test_btn_update_sources_uses_custom_confirm_and_alert(self):
        self.assertIn("btnUpdateSources.addEventListener('click'", self.app_js)
        self.assertIn("showConfirm(", self.app_js)
        self.assertIn("Обновление деплоера", self.app_js)
        self.assertIn("showAlert(", self.app_js)

    def test_btn_restart_uses_custom_confirm(self):
        self.assertIn("btnRestart.addEventListener('click'", self.app_js)
        self.assertIn("Перезапуск сервера", self.app_js)

    def test_btn_shutdown_uses_custom_confirm_with_danger(self):
        self.assertIn("btnShutdown.addEventListener('click'", self.app_js)
        self.assertIn("Выключение сервера", self.app_js)
        self.assertIn("danger: true", self.app_js)

    def test_no_native_confirm_fallback_in_show_confirm(self):
        show_confirm_match = re.search(r"function showConfirm\s*\(.*?\)\s*\{(.*?)\n\}", self.app_js, re.DOTALL)
        self.assertIsNotNone(show_confirm_match)
        body = show_confirm_match.group(1)
        self.assertNotIn("window.nativeConfirm", body)
        self.assertNotIn("nativeAlert", self.app_js)


class TestButtonEndpointsResponses(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        backend_main.is_deploying = False
        cls.server = HTTPServer(("127.0.0.1", 0), backend_main.WebUIHandler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2.0)

    def _post(self, path):
        conn = http.client.HTTPConnection("127.0.0.1", self.port)
        conn.request("POST", path)
        resp = conn.getresponse()
        data = json.loads(resp.read().decode("utf-8"))
        conn.close()
        return resp.status, data

    def test_update_sources_endpoint_responds_json(self):
        status, data = self._post("/api/update_sources")
        self.assertEqual(status, 200)
        self.assertIn("ok", data)

    def test_restart_endpoint_responds_json(self):
        status, data = self._post("/api/restart")
        self.assertEqual(status, 200)
        self.assertIn("ok", data)

    def test_shutdown_endpoint_responds_json(self):
        status, data = self._post("/api/shutdown")
        self.assertEqual(status, 200)
        self.assertIn("ok", data)


if __name__ == "__main__":
    unittest.main()
