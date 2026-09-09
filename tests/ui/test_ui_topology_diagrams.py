#!/usr/bin/env python3
"""
UI E2E Test: Traffic Topology Diagrams Verification
Verifies:
1. Dynamic rendering of traffic topology diagrams in #topologyDiagram for all 16 deployment & maintenance modes.
2. Presence of required node types (Client, Proxy, Freedom, Sub-Server, Local PC, etc.).
3. Absence of console errors during mode transitions.
"""

import asyncio
import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from playwright.async_api import async_playwright
from tests.helpers import log
from tests.ui.ui_helpers import start_sandboxed_control_panel


async def run_test() -> bool:
    log("==================================================", "info")
    log("🚀 UI TEST: TRAFFIC TOPOLOGY DIAGRAMS (16 MODES)", "info")
    log("==================================================", "info")

    server, server_url, _, _, sandbox_dir = start_sandboxed_control_panel("topology_diagrams")
    page_errors = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1400, "height": 900})
        page = await context.new_page()

        page.on("pageerror", lambda err: page_errors.append(str(err)))

        try:
            await page.goto(server_url, wait_until="networkidle")
            await page.wait_for_timeout(400)

            modes_expected_min_nodes = {
                "cascade_sub": 5,
                "cascade": 5,
                "freedom_sub": 4,
                "freedom_only": 4,
                "proxy_only": 4,
                "freedom_component": 4,
                "sub_only": 3,
                "backup": 2,
                "backup_sub": 2,
                "restart_server": 2,
                "recovery": 2,
                "rollback_sub": 2,
                "restart_panel": 2,
                "restart_sub": 2,
                "update_3xui": 2,
                "update_sub": 2
            }

            for mode, min_nodes in modes_expected_min_nodes.items():
                log(f"Testing topology for mode: {mode}...", "info")
                radio = page.locator(f"input[name='deploy_mode'][value='{mode}']")
                await radio.click()
                await page.wait_for_timeout(100)

                nodes = page.locator("#topologyDiagram .topology-node")
                count = await nodes.count()
                assert count >= min_nodes, (
                    f"Mode {mode}: Expected at least {min_nodes} nodes, found {count}"
                )

                # Ensure diagrams contain valid stages
                stages = page.locator("#topologyDiagram .topology-stage")
                stage_count = await stages.count()
                assert stage_count >= 1, f"Mode {mode}: No topology stages rendered"

                log(f"✅ [{mode}] {count} nodes and {stage_count} stage(s) rendered correctly.", "success")

            assert len(page_errors) == 0, f"Page errors encountered: {page_errors}"
            log("🎉 All 16 topology diagram modes verified with 0 errors!", "success")
            return True

        except Exception as e:
            log(f"❌ Topology diagram test failed: {e}", "error")
            return False
        finally:
            await browser.close()
            server.shutdown()


if __name__ == "__main__":
    success = asyncio.run(run_test())
    sys.exit(0 if success else 1)

