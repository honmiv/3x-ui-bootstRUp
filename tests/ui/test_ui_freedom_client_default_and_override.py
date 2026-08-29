#!/usr/bin/env python3
"""
UI E2E Test: Freedom Client Default Name and Override
Verifies:
1. When freedom_client_name is cleared in UI, deploy payload defaults to 'local-proxy-node-client'.
2. When freedom_client_name is overridden in UI (e.g. 'custom-cascade-client'), deploy payload contains the custom value.
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
from tests.ui.ui_helpers import mock_ssh_success, start_sandboxed_control_panel


async def run_test() -> bool:
    log("==================================================", "info")
    log("🚀 UI TEST: FREEDOM CLIENT DEFAULT & OVERRIDE", "info")
    log("==================================================", "info")

    server, server_url, _, _, sandbox_dir = start_sandboxed_control_panel("freedom_client_test")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1400, "height": 900})
        page = await context.new_page()

        try:
            await page.goto(server_url, wait_until="networkidle")

            captured_payloads = []

            async def handle_deploy_route(route):
                request = route.request
                post_data = request.post_data
                if post_data:
                    try:
                        captured_payloads.append(json.loads(post_data))
                    except Exception:
                        pass
                # Respond with error to keep btnStartDeploy visible without waiting for SSE logs
                await route.fulfill(status=200, content_type="application/json", json={"ok": False, "message": "Dry-run validation mock"})

            await page.route("**/api/deploy", handle_deploy_route)

            # Step 1 -> Step 2
            await page.click("input[name='deploy_mode'][value='cascade']")
            await page.click("#btnNextStep1")
            await page.wait_for_timeout(300)

            # Step 2: Fill SSH fields
            await page.fill("#freedom_host", "freedom.example.com")
            await page.fill("#freedom_password", "pass123")
            await page.fill("#proxy_host", "proxy.example.com")
            await page.fill("#proxy_password", "pass123")
            await mock_ssh_success(page)
            await page.click("#btnTestSSH")
            await page.wait_for_selector("#btnNext1:not(.hidden)", state="attached", timeout=5000)
            await page.click("#btnNext1")
            await page.wait_for_timeout(300)

            # Step 3: Fill required panel credentials and test freedom_client_name
            await page.fill("#freedom_xui_username", "admin")
            await page.fill("#freedom_xui_password", "admin_pass")
            await page.fill("#freedom_sub_secret", "freedom_secret")
            await page.fill("#proxy_xui_username", "admin")
            await page.fill("#proxy_xui_password", "proxy_pass")
            await page.fill("#proxy_sub_secret", "proxy_secret")

            # 1. Test Default Value when input is cleared on Step 3
            log("1. Testing empty input fallback to default on deploy...", "info")
            await page.fill("#freedom_client_name", "")
            
            # Step 3 -> Step 4
            await page.click("#btnNextStep3")
            await page.wait_for_timeout(300)

            captured_payloads.clear()
            await page.click("#btnStartDeploy")
            await page.wait_for_timeout(300)

            assert len(captured_payloads) > 0, "No /api/deploy request intercepted for default test"
            actual_default = captured_payloads[-1].get("freedom_client_name")
            assert actual_default == "local-proxy-node-client", f"Expected 'local-proxy-node-client', got '{actual_default}'"
            log(f"✅ Empty field fallback verified: '{actual_default}'", "success")

            # Go back Step 4 -> Step 3
            await page.click("#btnBackToStep3")
            await page.wait_for_timeout(300)

            # 2. Test Override Value
            log("2. Testing custom override value on deploy...", "info")
            custom_name = "my-custom-cascade-link"
            await page.fill("#freedom_client_name", custom_name)

            # Step 3 -> Step 4
            await page.click("#btnNextStep3")
            await page.wait_for_timeout(300)

            captured_payloads.clear()
            await page.click("#btnStartDeploy")
            await page.wait_for_timeout(300)

            assert len(captured_payloads) > 0, "No /api/deploy request intercepted for override test"
            actual_override = captured_payloads[-1].get("freedom_client_name")
            assert actual_override == custom_name, f"Expected '{custom_name}', got '{actual_override}'"
            log(f"✅ Override value verified: '{actual_override}'", "success")

            log("🎉 ALL FREEDOM CLIENT UI TESTS PASSED!", "success")
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
