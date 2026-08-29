#!/usr/bin/env python3
"""
UI E2E Test: Server Vault Purge & Reset
Verifies:
1. Creating a server card.
2. Clicking «Сбросить все серверы» (#btnResetServers).
3. Modal confirmation in #customConfirmModal.
4. Server list cleared and servers.json removed from disk.
"""

import asyncio
import os
import shutil
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from playwright.async_api import async_playwright
from tests.helpers import log
from tests.ui.ui_helpers import start_sandboxed_control_panel


async def run_test() -> bool:
    log("==================================================", "info")
    log("🚀 UI TEST: SERVER VAULT PURGE & RESET", "info")
    log("==================================================", "info")

    server, server_url, servers_file, _, sandbox_dir = start_sandboxed_control_panel("vault_reset")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1400, "height": 900})
        page = await context.new_page()

        try:
            await page.goto(server_url, wait_until="networkidle")

            # 1. Add server
            await page.fill("#sm_host", "95.217.100.50")
            await page.fill("#sm_pass", "SecretPass123!")
            await page.click("#btnSaveServer")
            await page.wait_for_selector("#masterPasswordModal.active", state="attached", timeout=5000)
            await page.fill("#masterPasswordInput", "1234")
            await page.click("#btnSubmitMasterPassword")
            await page.wait_for_selector("#masterPasswordModal.active", state="detached", timeout=5000)

            card = page.locator(".server-card").first
            await card.wait_for(state="visible", timeout=5000)
            await asyncio.sleep(0.5)

            assert os.path.exists(servers_file), "servers.json should exist on disk"

            # 2. Click Reset
            log("Clicking '#btnResetServers'...", "info")
            await page.click("#btnResetServers")
            await page.wait_for_selector("#customConfirmModal.active", state="attached", timeout=3000)

            log("Confirming reset modal...", "info")
            await page.click("#customModalConfirmBtn")
            await page.wait_for_selector("#customConfirmModal.active", state="detached", timeout=5000)
            await page.wait_for_timeout(500)

            # 3. Assert cleared
            list_text = await page.locator("#savedServersList").text_content()
            assert "Нет сохраненных серверов" in list_text or "Загрузка" in list_text

            await asyncio.sleep(0.5)
            assert not os.path.exists(servers_file), "servers.json was not deleted after reset!"
            log("✅ [Vault Purge Verified] Storage cleared and file removed.", "success")

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
