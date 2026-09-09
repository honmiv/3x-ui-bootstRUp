#!/usr/bin/env python3
"""
UI E2E Test: Deployment Result Cards (summaryCard / panelsContainer)
Covers EVERY maintenance deployment mode plus a positive panel control,
asserting:
- maintenance modes render their own success block and NEVER a fake
  "Панель управления 3X-UI" card with placeholder URL https://Server/
- panel modes (freedom_only/...) still render a real panel card

Regression target: app.js fallthrough where maintenance modes hit the
generic panel-card `else` branch (was rendering "https://Server/" after
update_sub deployments).
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

BACKUP_API_MOCK = [
    {
        "name": "backup_20260906.tar.gz",
        "size": "1.2 MB",
        "mtime": "2026-09-06 12:00:00",
        "mtime_ts": 0,
    }
]

FORBIDDEN_PANEL_TITLES = [
    "Панель управления 3X-UI",
    "Панель управления Freedom Node",
    "Панель управления Proxy Node",
]


async def set_hidden_select(page, select_id: str, option_value: str) -> None:
    """Populate a hidden backup-file <select> and fire change so validation reads the value."""
    await page.evaluate(
        """([selId, val]) => {
            const sel = document.getElementById(selId);
            sel.innerHTML = '<option value="' + val + '">' + val + '</option>';
            sel.value = val;
            sel.dispatchEvent(new Event('change'));
        }""",
        [select_id, option_value],
    )


async def run_test() -> bool:
    log("==================================================", "info")
    log("🚀 UI TEST: DEPLOYMENT RESULT CARDS (all maintenance modes)", "info")
    log("==================================================", "info")

    server, server_url, _, _, sandbox_dir = start_sandboxed_control_panel("result_cards")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1400, "height": 900})
        page = await context.new_page()

        try:
            await page.goto(server_url, wait_until="networkidle")

            # Backup-list mock for recovery / rollback_sub selects
            await page.route("**/api/backups*", lambda route: route.fulfill(
                status=200, json=BACKUP_API_MOCK
            ))

            async def panels_text() -> str:
                el = page.locator("#panelsContainer")
                await el.wait_for(state="attached", timeout=5000)
                return await el.inner_text()

            async def navigate_and_deploy(
                mode: str,
                result: dict,
                step2: dict,
                step3_inputs: dict | None = None,
                step3_selects: dict | None = None,
            ):
                step3_inputs = step3_inputs or {}
                step3_selects = step3_selects or {}

                # Step 1: pick mode
                await page.click(".step[data-step='1']")
                await page.click(f"input[name='deploy_mode'][value='{mode}']")
                await page.click("#btnNextStep1")
                await page.wait_for_timeout(300)

                # Step 2: SSH fields
                for fid, val in step2.items():
                    await page.fill(f"#{fid}", val)
                await mock_ssh_success(page)
                await page.click("#btnTestSSH")
                await page.wait_for_selector("#btnNext1:not(.hidden)", state="attached", timeout=5000)
                await page.click("#btnNext1")
                await page.wait_for_timeout(300)

                # Step 3: fill inputs (plain text) and hidden selects
                for fid, val in step3_inputs.items():
                    await page.fill(f"#{fid}", val)
                for fid, val in step3_selects.items():
                    await set_hidden_select(page, fid, val)

                # Step 3 → Step 4
                await page.click("#btnNextStep3")
                await page.wait_for_timeout(300)

                # Mock final /api/status and /api/deploy BEFORE clicking deploy
                await page.route("**/api/status", lambda route: route.fulfill(
                    status=200,
                    json={
                        "deploying": False,
                        "status": "completed",
                        "logs_count": 3,
                        "result": result,
                    }
                ))
                await page.route("**/api/deploy", lambda route: route.fulfill(
                    status=200,
                    json={"ok": True, "message": "Deployment started"}
                ))

                # Step 4: deploy
                await page.click("#btnStartDeploy")
                await page.wait_for_selector(
                    "#summaryCard:not(.hidden)", state="attached", timeout=5000
                )

            async def assert_maintenance_block(
                mode: str,
                expected: str,
                result: dict,
                step2: dict,
                step3_inputs: dict | None = None,
                step3_selects: dict | None = None,
            ):
                log(f"{mode} result card...", "info")
                await navigate_and_deploy(mode, result, step2, step3_inputs, step3_selects)
                txt = await panels_text()
                assert expected in txt, (
                    f"{mode}: missing success block {expected!r}, got:\n{txt}"
                )
                for bad in FORBIDDEN_PANEL_TITLES:
                    assert bad not in txt, (
                        f"{mode}: leaked panel card ({bad}), got:\n{txt}"
                    )
                assert "https://Server/" not in txt, (
                    f"{mode}: placeholder URL leaked, got:\n{txt}"
                )
                log(f"✅ [{mode}] correct block, no fake panel card.", "success")

            # ================================================================
            # Maintenance: sub-server family (sub_vps_* SSH fields)
            # ================================================================
            await assert_maintenance_block(
                "update_sub",
                "Сервер подписок обновлён, клиенты и ноды сохранены!",
                {"deploy_mode": "update_sub",
                 "sub_host": "updatesub.example.com",
                 "pre_update_backup": "./backups_sub_server/updatesub.example.com_pre-update_2026-09-06_211607.tar.gz"},
                {"sub_vps_host": "updatesub.example.com", "sub_vps_password": "SubPass123!"},
            )
            await assert_maintenance_block(
                "restart_sub",
                "Сервер подписок перезапущен, всё готово!",
                {"deploy_mode": "restart_sub", "sub_host": "updatesub.example.com"},
                {"sub_vps_host": "updatesub.example.com", "sub_vps_password": "SubPass123!"},
            )
            await assert_maintenance_block(
                "backup_sub",
                "Бэкап Сервера подписок успешно создан!",
                {"deploy_mode": "backup_sub",
                 "sub_host": "updatesub.example.com",
                 "backup_name": "updatesub.example.com_sub_20260906.tar.gz",
                 "file_size": "0.01 MB"},
                {"sub_vps_host": "updatesub.example.com", "sub_vps_password": "SubPass123!"},
            )
            await assert_maintenance_block(
                "rollback_sub",
                "Сервер подписок восстановлен из бэкапа!",
                {"deploy_mode": "rollback_sub",
                 "sub_host": "updatesub.example.com",
                 "backup_file": "backup_20260906.tar.gz",
                 "sub_base_url": "https://updatesub.example.com/a1b2c3d4"},
                {"sub_vps_host": "updatesub.example.com", "sub_vps_password": "SubPass123!"},
                step3_selects={"rollback_sub_backup_file": "backup_20260906.tar.gz"},
            )

            # ================================================================
            # Maintenance: panel family (backup_vps_*/update_vps_*/recovery_vps_*)
            # ================================================================
            await assert_maintenance_block(
                "backup",
                "Архив бэкапа успешно создан!",
                {"deploy_mode": "backup",
                 "backup_host": "panel.example.com",
                 "backup_name": "panel.example.com_20260906.tar.gz",
                 "file_size": "2.5 MB"},
                {"backup_vps_host": "panel.example.com", "backup_vps_password": "BackupPass123!"},
            )
            await assert_maintenance_block(
                "recovery",
                "Сервер успешно восстановлен из бэкапа!",
                {"deploy_mode": "recovery",
                 "recovery_host": "new-panel.example.com",
                 "backup_file": "backup_20260906.tar.gz",
                 "xui_url": "https://new-panel.example.com/"},
                {"recovery_vps_host": "new-panel.example.com", "recovery_vps_password": "RecoveryPass123!"},
                step3_inputs={"recovery_xui_username": "admin", "recovery_xui_password": "OldAdminPass"},
            )
            await assert_maintenance_block(
                "restart_panel",
                "Панель 3X-UI перезапущена, всё готово!",
                {"deploy_mode": "restart_panel", "update_host": "panel.example.com"},
                {"update_vps_host": "panel.example.com", "update_vps_password": "RestartPass123!"},
            )
            await assert_maintenance_block(
                "restart_server",
                "Сервер перезагружается, всё готово!",
                {"deploy_mode": "restart_server", "update_host": "panel.example.com"},
                {"update_vps_host": "panel.example.com", "update_vps_password": "RebootPass123!"},
            )
            await assert_maintenance_block(
                "update_3xui",
                "Панель 3X-UI успешно обновлена!",
                {"deploy_mode": "update_3xui",
                 "update_host": "panel.example.com",
                 "xui_version": "1.7.5",
                 "xui_url": "https://panel.example.com/abc123/"},
                {"update_vps_host": "panel.example.com", "update_vps_password": "UpdatePass123!"},
            )

            # ================================================================
            # Positive control: REAL panel card must still render
            # ================================================================
            log("freedom_only result card (positive control)...", "info")
            await navigate_and_deploy(
                "freedom_only",
                {"deploy_mode": "freedom_only",
                 "domain": "singlenode.example.com",
                 "xui_url": "https://singlenode.example.com/panel/",
                 "xui_username": "admin",
                 "xui_password": "pass"},
                {"vps_host": "singlenode.example.com", "vps_password": "SingleSecret123!"},
                step3_inputs={
                    "xui_username": "admin",
                    "xui_password": "AdminPass123!",
                    "sub_secret": "secret123",
                    "client_tcp_list": "client1",
                },
            )
            txt = await panels_text()
            assert "Панель управления Freedom Node" in txt, (
                f"freedom_only: panel card missing, got:\n{txt}"
            )
            assert "https://singlenode.example.com/panel/" in txt, (
                f"freedom_only: xui_url missing, got:\n{txt}"
            )
            log("✅ [freedom_only] real panel card still renders.", "success")

            log("🎉 ALL RESULT-CARD TESTS PASSED!", "success")
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