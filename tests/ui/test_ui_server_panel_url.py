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

            # 6. Test Update 3X-UI mode auto-updating server port in server card
            log("6. Testing Update 3X-UI mode auto-updating server port in server card...", "info")
            await page.fill("#sm_host", "update.example.com")
            await page.fill("#sm_port", "22")
            await page.fill("#sm_pass", "UpdateSecret123!")
            await page.click("#btnSaveServer")
            await page.wait_for_timeout(300)

            cards = page.locator(".server-card")
            assert await cards.count() == 3, "Should have 3 servers now"
            update_card = cards.nth(2)
            update_text_before = await update_card.inner_text()
            assert ":22" in update_text_before or " 22" in update_text_before, f"Expected initial port 22 in update.example.com card, got:\n{update_text_before}"

            # Step 1: select update_3xui mode
            await page.click(".step[data-step='1']")
            await page.click("input[name='deploy_mode'][value='update_3xui']")
            await page.click("#btnNextStep1")
            await page.wait_for_timeout(300)

            # Step 2: fill update_vps_host
            await page.fill("#update_vps_host", "update.example.com")
            await page.fill("#update_vps_password", "UpdateSecret123!")
            await page.click("#btnTestSSH")
            await page.wait_for_selector("#btnNext1:not(.hidden)", state="attached", timeout=5000)
            await page.click("#btnNext1")
            await page.wait_for_timeout(300)

            # Step 3: check opt_update_change_ssh_port
            update_ssh_cb = page.locator("#opt_update_change_ssh_port")
            assert await update_ssh_cb.count() == 1, "SSH port change checkbox should exist in Step 3 for update_3xui"
            await page.click("label[for='opt_update_change_ssh_port']")
            assert await update_ssh_cb.is_checked(), "SSH port change checkbox should be checked"
            await page.fill("#custom_update_ssh_port", "22222")

            # Step 3 -> Step 4
            await page.click("#btnNextStep3")
            await page.wait_for_timeout(300)

            # Step 4: Deploy update_3xui
            await page.route("**/api/status", lambda route: route.fulfill(
                status=200,
                json={
                    "deploying": False,
                    "status": "completed",
                    "logs_count": 5,
                    "result": {
                        "deploy_mode": "update_3xui",
                        "update_host": "update.example.com",
                        "xui_version": "1.7.5",
                        "xui_url": "https://update.example.com/secret_path/",
                        "new_ssh_port": 22222,
                        "updated_ssh_ports": {
                            "update.example.com": 22222
                        }
                    }
                }
            ))
            await page.click("#btnStartDeploy")
            await page.wait_for_timeout(1000)

            # Verify update_card now has port 22222
            update_text_after = await update_card.inner_text()
            assert "22222" in update_text_after, f"Expected port 22222 in update server card, got:\n{update_text_after}"
            log("✅ [Update 3X-UI Auto-Port Verified] Server card for update_3xui automatically updated to 22222!", "success")

            # 7. Test Sub-Server Only mode auto-updating server port
            log("7. Testing Sub-Server Only mode auto-updating server port in server card...", "info")
            await page.fill("#sm_host", "subonly.example.com")
            await page.fill("#sm_port", "22")
            await page.fill("#sm_pass", "SubOnlyPass123!")
            await page.click("#btnSaveServer")
            await page.wait_for_timeout(300)

            cards = page.locator(".server-card")
            subonly_card = cards.nth(3)
            subonly_text_before = await subonly_card.inner_text()
            assert "subonly.example.com" in subonly_text_before and ("22" in subonly_text_before)

            # Select sub_only
            await page.click(".step[data-step='1']")
            await page.click("input[name='deploy_mode'][value='sub_only']")
            await page.click("#btnNextStep1")
            await page.wait_for_timeout(300)

            # Step 2: fill sub_vps_host
            await page.fill("#sub_vps_host", "subonly.example.com")
            await page.fill("#sub_vps_password", "SubOnlyPass123!")
            await page.click("#btnTestSSH")
            await page.wait_for_selector("#btnNext1:not(.hidden)", state="attached", timeout=5000)
            await page.click("#btnNext1")
            await page.wait_for_timeout(300)

            # Step 3: check opt_change_ssh_port
            sub_ssh_cb = page.locator("#opt_change_ssh_port")
            assert await sub_ssh_cb.count() == 1
            await page.fill("#sub_russian_url", "https://proxy.example.com/subs/client1")
            await page.fill("#sub_secret_path", "secret123")
            await page.fill("#sub_admin_user", "admin")
            await page.fill("#sub_admin_password", "AdminPass123!")
            await page.click("label[for='opt_change_ssh_port']")
            await page.fill("#custom_ssh_port", "22222")
            await page.click("#btnNextStep3")
            await page.wait_for_timeout(300)

            # Step 4: Deploy
            await page.route("**/api/status", lambda route: route.fulfill(
                status=200,
                json={
                    "deploying": False,
                    "status": "completed",
                    "logs_count": 5,
                    "result": {
                        "deploy_mode": "sub_only",
                        "sub_domain": "subonly.example.com",
                        "sub_base_url": "https://subonly.example.com/subs",
                        "new_ssh_port": 22222,
                        "updated_ssh_ports": {
                            "subonly.example.com": 22222
                        }
                    }
                }
            ))
            await page.click("#btnStartDeploy")
            await page.wait_for_timeout(1000)

            subonly_text_after = await subonly_card.inner_text()
            assert "22222" in subonly_text_after, f"Expected port 22222 in subonly card, got:\n{subonly_text_after}"
            sub_port_val = await page.input_value("#sub_vps_port")
            assert sub_port_val == "22222", f"Expected #sub_vps_port to be 22222, got {sub_port_val}"
            log("✅ [Sub Only Auto-Port Verified] Server card and #sub_vps_port updated to 22222!", "success")

            # 8. Test Update Sub-Server mode auto-updating server port
            log("8. Testing Update Sub-Server mode auto-updating server port in server card...", "info")
            await page.fill("#sm_host", "updatesub.example.com")
            await page.fill("#sm_port", "22")
            await page.fill("#sm_pass", "UpdateSubPass123!")
            await page.click("#btnSaveServer")
            await page.wait_for_timeout(300)

            cards = page.locator(".server-card")
            updatesub_card = cards.nth(4)
            updatesub_text_before = await updatesub_card.inner_text()
            assert "updatesub.example.com" in updatesub_text_before

            # Select update_sub
            await page.click(".step[data-step='1']")
            await page.click("input[name='deploy_mode'][value='update_sub']")
            await page.click("#btnNextStep1")
            await page.wait_for_timeout(300)

            # Step 2: fill sub_vps_host
            await page.fill("#sub_vps_host", "updatesub.example.com")
            await page.fill("#sub_vps_password", "UpdateSubPass123!")
            await page.click("#btnTestSSH")
            await page.wait_for_selector("#btnNext1:not(.hidden)", state="attached", timeout=5000)
            await page.click("#btnNext1")
            await page.wait_for_timeout(300)

            # Step 3: check opt_update_sub_change_ssh_port
            updatesub_ssh_cb = page.locator("#opt_update_sub_change_ssh_port")
            assert await updatesub_ssh_cb.count() == 1
            await page.click("label[for='opt_update_sub_change_ssh_port']")
            await page.fill("#custom_update_sub_ssh_port", "22222")
            await page.click("#btnNextStep3")
            await page.wait_for_timeout(300)

            # Step 4: Deploy
            await page.route("**/api/status", lambda route: route.fulfill(
                status=200,
                json={
                    "deploying": False,
                    "status": "completed",
                    "logs_count": 5,
                    "result": {
                        "deploy_mode": "update_sub",
                        "sub_host": "updatesub.example.com",
                        "new_ssh_port": 22222,
                        "updated_ssh_ports": {
                            "updatesub.example.com": 22222
                        }
                    }
                }
            ))
            await page.click("#btnStartDeploy")
            await page.wait_for_timeout(1000)

            updatesub_text_after = await updatesub_card.inner_text()
            assert "22222" in updatesub_text_after, f"Expected port 22222 in updatesub card, got:\n{updatesub_text_after}"
            updatesub_port_val = await page.input_value("#sub_vps_port")
            assert updatesub_port_val == "22222", f"Expected #sub_vps_port to be 22222, got {updatesub_port_val}"
            log("✅ [Update Sub Auto-Port Verified] Server card and #sub_vps_port updated to 22222!", "success")

            # 9. Test Single (Freedom Only) mode auto-updating server port
            log("9. Testing Single Node mode auto-updating server port in server card...", "info")
            await page.fill("#sm_host", "singlenode.example.com")
            await page.fill("#sm_port", "22")
            await page.fill("#sm_pass", "SingleSecret123!")
            await page.click("#btnSaveServer")
            await page.wait_for_timeout(300)

            cards = page.locator(".server-card")
            single_card = cards.nth(5)
            single_text_before = await single_card.inner_text()
            assert "singlenode.example.com" in single_text_before

            # Select freedom_only mode
            await page.click(".step[data-step='1']")
            await page.click("input[name='deploy_mode'][value='freedom_only']")
            await page.click("#btnNextStep1")
            await page.wait_for_timeout(300)

            # Step 2: fill vps_host
            await page.fill("#vps_host", "singlenode.example.com")
            await page.fill("#vps_password", "SingleSecret123!")
            await page.click("#btnTestSSH")
            await page.wait_for_selector("#btnNext1:not(.hidden)", state="attached", timeout=5000)
            await page.click("#btnNext1")
            await page.wait_for_timeout(300)

            # Step 3: check opt_change_ssh_port
            single_ssh_cb = page.locator("#opt_change_ssh_port")
            assert await single_ssh_cb.count() == 1
            await page.fill("#xui_username", "admin")
            await page.fill("#xui_password", "AdminPass123!")
            await page.fill("#sub_secret", "secret123")
            await page.fill("#client_tcp_list", "client1")
            await page.click("label[for='opt_change_ssh_port']")
            await page.fill("#custom_ssh_port", "22222")
            await page.click("#btnNextStep3")
            await page.wait_for_timeout(300)

            # Step 4: Deploy
            await page.route("**/api/status", lambda route: route.fulfill(
                status=200,
                json={
                    "deploying": False,
                    "status": "completed",
                    "logs_count": 5,
                    "result": {
                        "deploy_mode": "freedom_only",
                        "domain": "singlenode.example.com",
                        "xui_url": "https://singlenode.example.com/panel/",
                        "new_ssh_port": 22222,
                        "updated_ssh_ports": {
                            "singlenode.example.com": 22222
                        }
                    }
                }
            ))
            await page.click("#btnStartDeploy")
            await page.wait_for_timeout(1000)

            single_text_after = await single_card.inner_text()
            assert "22222" in single_text_after, f"Expected port 22222 in single card, got:\n{single_text_after}"
            vps_port_val = await page.input_value("#vps_port")
            assert vps_port_val == "22222", f"Expected #vps_port to be 22222, got {vps_port_val}"
            log("✅ [Single Node Auto-Port Verified] Server card and #vps_port updated to 22222!", "success")

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
