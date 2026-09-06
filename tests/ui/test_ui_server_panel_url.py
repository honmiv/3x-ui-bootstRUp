#!/usr/bin/env python3
"""
UI E2E Test: Server Panel URL and Open Button
Verifies:
1. Adding a server with panel_url in the server manager.
2. The card renders the open panel button (btn-open-panel-card) next to the SSH test button.
3. Clicking the open panel button links to the saved panel URL.
4. Auto-updating panel_url in existing saved server upon successful deploy.
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
from tests.ui.ui_helpers import start_sandboxed_control_panel, mock_ssh_success


async def run_test() -> bool:
    log("==================================================", "info")
    log("🚀 UI TEST: SERVER PANEL URL & OPEN PANEL BUTTON", "info")
    log("==================================================", "info")

    server, server_url, _, _, sandbox_dir = start_sandboxed_control_panel("panel_url")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1400, "height": 900})
        page = await context.new_page()

        try:
            await page.goto(server_url, wait_until="networkidle")

            # 1. Add server with panel_url
            log("1. Adding server with explicit panel_url...", "info")
            await page.fill("#sm_host", "freedom.example.com")
            await page.fill("#sm_pass", "SecretPass123!")
            await page.fill("#sm_panel_url", "https://freedom.example.com/admin123/")
            await page.click("#btnSaveServer")

            await page.wait_for_selector("#masterPasswordModal.active", state="attached", timeout=5000)
            await page.fill("#masterPasswordInput", "1234")
            await page.click("#btnSubmitMasterPassword")
            await page.wait_for_selector("#masterPasswordModal.active", state="detached", timeout=5000)

            card = page.locator(".server-card").first
            await card.wait_for(state="visible", timeout=5000)

            # 2. Check open panel button exists
            log("2. Checking open panel button in server card...", "info")
            panel_btn = card.locator(".btn-open-panel-card")
            assert await panel_btn.count() == 1, "Open panel button should be rendered!"
            href = await panel_btn.get_attribute("href")
            assert href == "https://freedom.example.com/admin123/", f"Expected href https://freedom.example.com/admin123/, got {href}"
            log("✅ [Button Verified] Open panel button present with correct URL.", "success")

            # 3. Add second server without panel_url
            log("3. Adding second server without panel_url...", "info")
            await page.fill("#sm_host", "proxy.example.com")
            await page.fill("#sm_pass", "ProxySecret123!")
            await page.click("#btnSaveServer")
            await page.wait_for_timeout(300)

            cards = page.locator(".server-card")
            assert await cards.count() == 2, "Should have 2 servers now"
            proxy_card = cards.nth(1)
            proxy_panel_btn = proxy_card.locator(".btn-open-panel-card")
            assert await proxy_panel_btn.count() == 0, "Server without panel_url should not have open panel button initially"

            # 4. Trigger mock deploy completion that auto-updates proxy.example.com panel_url
            log("4. Simulating deploy completion for proxy.example.com...", "info")
            await page.route("**/api/status", lambda route: route.fulfill(
                status=200,
                json={
                    "deploying": False,
                    "status": "completed",
                    "logs_count": 5,
                    "result": {
                        "deploy_mode": "cascade",
                        "freedom_domain": "freedom.example.com",
                        "freedom_xui_url": "https://freedom.example.com/admin123/",
                        "domain": "proxy.example.com",
                        "xui_url": "https://proxy.example.com/new_secret_panel/",
                        "xui_username": "admin",
                        "xui_password": "pass",
                        "new_ssh_port": 22222,
                        "updated_ssh_ports": {
                            "freedom.example.com": 22222,
                            "proxy.example.com": 22222
                        }
                    }
                }
            ))

            # Step 1 -> Step 2
            await page.click("input[name='deploy_mode'][value='cascade']")
            await page.click("#btnNextStep1")
            await page.wait_for_timeout(300)

            # Step 2: Fill SSH
            await page.fill("#freedom_host", "freedom.example.com")
            await page.fill("#freedom_password", "pass")
            await page.fill("#proxy_host", "proxy.example.com")
            await page.fill("#proxy_password", "pass")
            await mock_ssh_success(page)
            await page.click("#btnTestSSH")
            await page.wait_for_selector("#btnNext1:not(.hidden)", state="attached", timeout=5000)
            await page.click("#btnNext1")
            await page.wait_for_timeout(300)

            # Step 3: Fill required panel credentials
            await page.fill("#freedom_xui_username", "admin")
            await page.fill("#freedom_xui_password", "admin_pass")
            await page.fill("#freedom_sub_secret", "freedom_secret")
            await page.fill("#proxy_xui_username", "admin")
            await page.fill("#proxy_xui_password", "proxy_pass")
            await page.fill("#proxy_sub_secret", "proxy_secret")

            # Verify SSH port change option in Step 3
            change_ssh_cb = page.locator("#opt_change_ssh_port")
            assert await change_ssh_cb.count() == 1, "SSH port change checkbox should exist in Step 3"
            await page.click("label[for='opt_change_ssh_port']")
            assert await change_ssh_cb.is_checked(), "SSH port change checkbox should be checked"
            ssh_row = page.locator("#sshPortConfigRow")
            await ssh_row.wait_for(state="visible", timeout=3000)
            custom_port_val = await page.input_value("#custom_ssh_port")
            assert custom_port_val == "22222", f"Default custom SSH port should be 22222, got {custom_port_val}"

            # Step 3 -> Step 4
            await page.click("#btnNextStep3")
            await page.wait_for_timeout(300)

            # Step 4: Deploy
            await page.route("**/api/deploy", lambda route: route.fulfill(
                status=200,
                json={"ok": True, "message": "Deployment started"}
            ))
            await page.click("#btnStartDeploy")

            await page.wait_for_timeout(1000)

            # Check that proxy_card now has the updated panel button
            proxy_panel_btn_after = proxy_card.locator(".btn-open-panel-card")
            await proxy_panel_btn_after.wait_for(state="attached", timeout=5000)
            updated_href = await proxy_panel_btn_after.get_attribute("href")
            assert updated_href == "https://proxy.example.com/new_secret_panel/", f"Expected updated href https://proxy.example.com/new_secret_panel/, got {updated_href}"
            log("✅ [Auto-Save Verified] Server card automatically updated with new panel URL after deployment!", "success")

            # Check that server cards now have the updated SSH port
            log("5. Checking server card SSH ports after deploy...", "info")
            freedom_text = await card.inner_text()
            assert "22222" in freedom_text, f"Expected port 22222 in freedom server card, got:\n{freedom_text}"
            proxy_text = await proxy_card.inner_text()
            assert "22222" in proxy_text, f"Expected port 22222 in proxy server card, got:\n{proxy_text}"
            log("✅ [Auto-Port Verified] Server cards automatically updated with new SSH port 22222!", "success")

            # Check that form inputs are updated with new SSH port
            freedom_port_val = await page.input_value("#freedom_port")
            proxy_port_val = await page.input_value("#proxy_port")
            assert freedom_port_val == "22222", f"Expected #freedom_port to be 22222, got {freedom_port_val}"
            assert proxy_port_val == "22222", f"Expected #proxy_port to be 22222, got {proxy_port_val}"
            log("✅ [Form Port Verified] Form inputs #freedom_port and #proxy_port updated to 22222!", "success")

            log("🎉 ALL TESTS PASSED!", "success")
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
