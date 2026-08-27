#!/usr/bin/env python3
"""
UI E2E Test: Saved Server Cards Drag-and-Drop Reordering
Verifies:
1. Adding multiple servers to the vault.
2. Initial order in DOM and servers.json on disk.
3. Drag & drop reordering of server cards.
4. Immediate DOM update and persistence to servers.json on disk.
5. Page reload & unlock preserves reordered positions.
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

TEST_PIN = "1234"


async def run_test() -> bool:
    log("==================================================", "info")
    log("🚀 UI TEST: SERVER CARDS DRAG & DROP REORDERING", "info")
    log("==================================================", "info")

    server, server_url, servers_file, _, sandbox_dir = start_sandboxed_control_panel("server_reorder")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1400, "height": 900})
        page = await context.new_page()

        try:
            await page.goto(server_url, wait_until="networkidle")

            servers = [
                {"host": "alpha.example.com", "pass": "PassAlpha1!"},
                {"host": "beta.example.com", "pass": "PassBeta2!"},
                {"host": "gamma.example.com", "pass": "PassGamma3!"},
            ]

            for idx, s in enumerate(servers):
                await page.fill("#sm_host", s["host"])
                await page.fill("#sm_user", "root")
                await page.fill("#sm_port", "22")
                await page.fill("#sm_pass", s["pass"])
                await page.click("#btnSaveServer")

                if idx == 0:
                    await page.wait_for_selector("#masterPasswordModal.active", state="attached", timeout=5000)
                    await page.fill("#masterPasswordInput", TEST_PIN)
                    await page.click("#btnSubmitMasterPassword")
                    await page.wait_for_selector("#masterPasswordModal.active", state="detached", timeout=5000)

                await page.wait_for_timeout(200)

            # Wait until 3 cards are rendered
            await page.wait_for_selector(".server-card:nth-child(3)", state="visible", timeout=5000)

            cards = page.locator(".server-card")
            count = await cards.count()
            assert count == 3, f"Expected 3 server cards, got {count}"

            initial_hosts = [h.strip() for h in await page.locator(".server-card-host").all_text_contents()]
            log(f"Initial server card order: {initial_hosts}", "info")
            assert initial_hosts == ["alpha.example.com", "beta.example.com", "gamma.example.com"]

            # Perform Drag and Drop: move gamma (index 2) to top (before alpha, index 0)
            log("Dragging 'gamma.example.com' to the top (position 0)...", "info")
            card_gamma = cards.nth(2)
            card_alpha = cards.nth(0)

            # Trigger drag and drop
            await card_gamma.drag_to(card_alpha, target_position={"x": 50, "y": 5})
            await page.wait_for_timeout(400)

            reordered_hosts = [h.strip() for h in await page.locator(".server-card-host").all_text_contents()]
            log(f"DOM order after drag: {reordered_hosts}", "info")
            assert reordered_hosts == ["gamma.example.com", "alpha.example.com", "beta.example.com"], (
                f"Unexpected DOM order after drag: {reordered_hosts}"
            )

            # Verify persistence on disk (servers.json)
            assert os.path.exists(servers_file), "servers.json must exist on disk"
            with open(servers_file, "r", encoding="utf-8") as f:
                disk_data = json.load(f)

            disk_hosts = [s.get("host") for s in disk_data]
            log(f"Disk servers.json order: {disk_hosts}", "info")
            assert disk_hosts == ["gamma.example.com", "alpha.example.com", "beta.example.com"], (
                f"Unexpected servers.json disk order: {disk_hosts}"
            )
            log("✅ [Disk Persistence Verified] servers.json reflects reordered items.", "success")

            # Reload page and verify order is preserved after unlocking
            log("Reloading page to verify order persistence...", "info")
            await page.reload(wait_until="networkidle")

            # Unlock vault
            unlock_btn = page.locator("#btnUnlockStorage")
            if await unlock_btn.is_visible():
                await unlock_btn.click()
                await page.wait_for_selector("#masterPasswordModal.active", state="attached", timeout=5000)
                await page.fill("#masterPasswordInput", TEST_PIN)
                await page.click("#btnSubmitMasterPassword")
                await page.wait_for_selector("#masterPasswordModal.active", state="detached", timeout=5000)

            await page.wait_for_selector(".server-card:nth-child(3)", state="visible", timeout=5000)
            persisted_hosts = [h.strip() for h in await page.locator(".server-card-host").all_text_contents()]
            log(f"Hosts after page reload & unlock: {persisted_hosts}", "info")
            assert persisted_hosts == ["gamma.example.com", "alpha.example.com", "beta.example.com"], (
                f"Order was not persisted across page reload: {persisted_hosts}"
            )

            log("🎉 DRAG & DROP REORDER TEST PASSED!", "success")
            return True
        finally:
            await context.close()
            await browser.close()
            server.shutdown()
            shutil.rmtree(sandbox_dir, ignore_errors=True)


if __name__ == "__main__":
    success = asyncio.run(run_test())
    sys.exit(0 if success else 1)
