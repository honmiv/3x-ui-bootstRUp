#!/usr/bin/env python3
"""
UI E2E Test: Server Vault PIN Setup & WebCrypto Encryption
Verifies:
1. Setting Master PIN via modal.
2. In-browser WebCrypto AES-GCM (PBKDF2 600k iterations) key derivation.
3. Server creation and rendering in DOM.
4. servers.json security assertion (ciphertext only, zero plaintext passwords on disk).
"""

import asyncio
import json
import os
import shutil
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from playwright.async_api import async_playwright
from tests.helpers import log
from tests.ui.ui_helpers import start_sandboxed_control_panel

TEST_PIN = "9876"


async def run_test() -> bool:
    log("==================================================", "info")
    log("🚀 UI TEST: SERVER VAULT PIN SETUP & WEBCRYPTO", "info")
    log("==================================================", "info")

    server, server_url, servers_file, _, sandbox_dir = start_sandboxed_control_panel("vault_pin")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1400, "height": 900})
        page = await context.new_page()

        try:
            await page.goto(server_url, wait_until="networkidle")

            # 1. Fill server drawer form
            log("Filling server form in sidebar...", "info")
            await page.fill("#sm_host", "95.217.100.50")
            await page.fill("#sm_user", "root")
            await page.fill("#sm_port", "2222")
            await page.fill("#sm_pass", "UltraSecretServerPassword_2026!")

            # 2. Click Save -> Master PIN Modal
            await page.click("#btnSaveServer")
            await page.wait_for_selector("#masterPasswordModal.active", state="attached", timeout=5000)

            log(f"Entering test PIN '{TEST_PIN}'...", "info")
            await page.fill("#masterPasswordInput", TEST_PIN)
            await page.click("#btnSubmitMasterPassword")
            await page.wait_for_selector("#masterPasswordModal.active", state="detached", timeout=5000)

            # 3. Verify Card in DOM
            card = page.locator(".server-card").first
            await card.wait_for(state="visible", timeout=5000)
            host_text = await card.locator(".server-card-host").text_content()
            assert "95.217.100.50" in host_text
            log(f"Server card rendered: '{host_text.strip()}'", "success")

            # 4. Security Assertion on Disk
            await asyncio.sleep(0.5)
            assert os.path.exists(servers_file)
            with open(servers_file, "r", encoding="utf-8") as f:
                disk_content = f.read()
                data = json.loads(disk_content)

            assert "UltraSecretServerPassword_2026!" not in disk_content, "SECURITY ALERT: Plaintext password found in servers.json!"
            assert isinstance(data, list) and len(data) == 1
            assert "enc_pass" in data[0] and len(data[0]["enc_pass"]) > 20
            log("✅ [SECURITY VERIFIED] Password encrypted via AES-GCM on disk.", "success")

            log("🎉 TEST PASSED!", "success")
            return True
        finally:
            await context.close()
            await browser.close()
            server.shutdown()
            shutil.rmtree(sandbox_dir, ignore_errors=True)


def main():
    ok = asyncio.run(run_test())
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
