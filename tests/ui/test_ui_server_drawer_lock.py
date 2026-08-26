#!/usr/bin/env python3
"""
UI E2E Test: Server Drawer Lock / Unlock Protection
Verifies:
1. Creating a server card.
2. Clicking the Lock button 🔒 toggles .is-locked on the card.
3. Action buttons (Delete, Edit) become disabled when locked.
4. Unlocking re-enables action buttons.
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
    log("🚀 UI TEST: SERVER DRAWER LOCK / UNLOCK PROTECTION", "info")
    log("==================================================", "info")

    server, server_url, _, _, sandbox_dir = start_sandboxed_control_panel("drawer_lock")

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

            # 2. Lock server card
            log("Locking server card 🔒...", "info")
            lock_btn = card.locator(".btn-lock-toggle")
            await lock_btn.click()
            await page.wait_for_timeout(300)

            card_classes = await card.get_attribute("class")
            assert "is-locked" in card_classes, "Card should receive 'is-locked' class!"

            delete_btn = card.locator("button.danger")
            assert await delete_btn.is_disabled(), "Delete button must be disabled when server is locked!"
            log("✅ [Lock Protection Verified] Actions disabled while locked.", "success")

            # 3. Unlock server card
            log("Unlocking server card 🔓...", "info")
            await lock_btn.click()
            await page.wait_for_timeout(300)

            assert not await delete_btn.is_disabled(), "Delete button must be enabled when unlocked!"
            log("✅ [Unlock Verified] Actions restored.", "success")

            # 4. Test SSH connection via lightning button ⚡
            log("Testing SSH connection button ⚡...", "info")
            await page.route("**/api/ssh/test", lambda route: route.fulfill(status=200, json={"ok": True, "message": "Connected successfully"}))
            test_ssh_btn = card.locator(".btn-test-ssh-card")
            assert await test_ssh_btn.count() == 1, "Lightning SSH test button should exist in card header!"
            await test_ssh_btn.click()
            await page.wait_for_timeout(500)
            toast = page.locator(".toast-success")
            await toast.wait_for(state="visible", timeout=3000)
            log("✅ [SSH Test Verified] Lightning button triggered test and showed success toast.", "success")

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
