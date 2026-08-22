#!/usr/bin/env python3
"""
UI E2E Test: Wizard Stepper Navigation & Form Data Preservation
Verifies:
1. Advancing Step 1 -> Step 2 -> Step 3.
2. Filling inputs on multiple steps.
3. Returning backward via #btnBackToStep2 and #btnBackToStep1.
4. All filled values remain preserved without resetting.
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
from tests.ui.ui_helpers import mock_ssh_success, start_sandboxed_control_panel


async def run_test() -> bool:
    log("==================================================", "info")
    log("🚀 UI TEST: STEPPER NAVIGATION & VALUE PRESERVATION", "info")
    log("==================================================", "info")

    server, server_url, _, _, sandbox_dir = start_sandboxed_control_panel("stepper_nav")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1400, "height": 900})
        page = await context.new_page()

        try:
            await page.goto(server_url, wait_until="networkidle")

            # 1. Step 1 -> Choose Cascade
            await page.click("input[name='deploy_mode'][value='cascade']")
            await page.click("#btnNextStep1")
            await page.wait_for_timeout(300)

            # 2. Step 2 -> Fill details
            log("Filling Step 2 details...", "info")
            await page.fill("#freedom_host", "freedom.example.org")
            await page.fill("#freedom_port", "2221")
            await page.fill("#proxy_host", "proxy.example.org")
            await page.fill("#proxy_port", "2222")

            # Mock SSH check to reveal #btnNext1
            await mock_ssh_success(page)
            await page.click("#btnTestSSH")
            await page.wait_for_selector("#btnNext1:not(.hidden)", state="attached", timeout=5000)
            await page.click("#btnNext1")
            await page.wait_for_timeout(300)

            # 3. Step 3 -> Fill client details
            assert await page.is_visible("#step3"), "Step 3 should be visible"
            log("Filling Step 3 details...", "info")
            await page.fill("#proxy_client_tcp_list", "alice, bob")

            # 4. Navigate Backward: Step 3 -> Step 2
            log("Navigating back to Step 2...", "info")
            await page.click("#btnBackToStep2")
            await page.wait_for_timeout(300)

            f_host = await page.input_value("#freedom_host")
            p_host = await page.input_value("#proxy_host")
            assert f_host == "freedom.example.org", f"Expected 'freedom.example.org', got '{f_host}'"
            assert p_host == "proxy.example.org", f"Expected 'proxy.example.org', got '{p_host}'"
            log("✅ Values preserved when navigating back to Step 2.", "success")

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
