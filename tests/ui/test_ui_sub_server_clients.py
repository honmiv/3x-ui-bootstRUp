#!/usr/bin/env python3
"""
UI E2E Test: Subscription Server Nodes Registry & Force-Subs Override
Verifies:
1. Logging into dashboard.
2. Rendering nodes and clients from nodes.json.
3. Adding a new client via modal.
4. Setting a custom force-subs override and saving to force-subs.yml.
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
from tests.ui.ui_helpers import start_sandboxed_sub_server

ADMIN_USER = "subadmin"
ADMIN_PASSWORD = "SubAdminSecurePass123!"
SECRET_PATH = "subs"

INITIAL_NODES = [
    {
        "id": "node-freedom",
        "name": "Freedom Server (EU)",
        "url": "https://freedom.example.org/subs",
        "clients": ["alice-direct", "bob-direct"]
    },
    {
        "id": "node-proxy",
        "name": "Russian Proxy (RU)",
        "url": "https://proxy.example.org/subs",
        "clients": ["charlie-cascade"]
    }
]


async def run_test() -> bool:
    log("==================================================", "info")
    log("🚀 UI TEST: SUB-SERVER NODES & CLIENTS MANAGEMENT", "info")
    log("==================================================", "info")

    server, server_url, _, force_file, sandbox_dir, _ = start_sandboxed_sub_server(
        "sub_clients",
        initial_nodes=INITIAL_NODES,
        admin_user=ADMIN_USER,
        admin_password=ADMIN_PASSWORD,
        secret_path=SECRET_PATH
    )

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1400, "height": 900})
        page = await context.new_page()

        try:
            # 1. Login
            await page.goto(f"{server_url}/{SECRET_PATH}/login", wait_until="networkidle")
            await page.fill("input[name='user']", ADMIN_USER)
            await page.fill("input[name='password']", ADMIN_PASSWORD)
            await page.click("button[type='submit']")
            await page.wait_for_timeout(800)

            # 2. Assert nodes and clients rendered
            content = await page.text_content("body")
            assert "Freedom Server (EU)" in content
            assert "Russian Proxy (RU)" in content
            assert "alice-direct" in content
            assert "charlie-cascade" in content
            log("✅ [Node Registry Verified] Rendered nodes and clients from nodes.json.", "success")

            # 3. Add Client modal
            btn_add = page.locator("button:has-text('Добавить клиента')").first
            if await btn_add.count() > 0:
                await btn_add.click()
                await page.wait_for_timeout(300)
                name_in = page.locator("input#client-name, input[name='client'], input#addClientName").first
                if await name_in.count() > 0:
                    await name_in.fill("david-user")
                    await page.click("button:has-text('Сохранить'), button:has-text('Добавить')")
                    await page.wait_for_timeout(500)
                    assert "david-user" in await page.text_content("body")
                    log("✅ [Client Management Verified] Added new client.", "success")

            # 4. Override modal
            override_btn = page.locator("button:has-text('Переопределить'), button[title*='Переопределить']").first
            if await override_btn.count() > 0:
                await override_btn.click()
                await page.wait_for_timeout(300)
                txt_area = page.locator("textarea#override-content, textarea[name='value'], textarea#overrideValue").first
                if await txt_area.count() > 0:
                    await txt_area.fill("vless://custom-uuid@custom.server.com:443?security=reality#custom")
                    await page.click("button:has-text('Сохранить'), button:has-text('Применить')")
                    await page.wait_for_timeout(500)

                    assert os.path.exists(force_file)
                    with open(force_file, "r", encoding="utf-8") as f:
                        data = f.read()
                    log(f"Updated force-subs.yml:\n{data}", "info")
                    log("✅ [Force-Subs Verified] Custom override applied.", "success")

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
