"""Verify individual manager presentation, not production authorization or GDPR compliance."""
import asyncio
import copy
import json
import os
from pathlib import Path
import re

from playwright.async_api import async_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
WEB = os.getenv("NEURASIGN_WEB_URL", "http://localhost:3000")
API = os.getenv("NEURASIGN_API_URL", "http://localhost:8000")


async def main():
    artifacts = ROOT / "artifacts"
    artifacts.mkdir(exist_ok=True)
    errors, writes = [], []
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome", headless=True, args=["--no-sandbox"])
        page = await browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("request", lambda request: writes.append(request.url) if request.method not in ("GET", "HEAD", "OPTIONS") else None)
        await page.goto(WEB + "/demo#manager", wait_until="domcontentloaded")
        view = page.get_by_test_id("manager-overview")
        await expect(view).to_be_visible(timeout=30000)
        await expect(page.get_by_test_id("manager-person-alex")).to_be_visible()
        await expect(page.get_by_test_id("manager-person-aoi")).to_contain_text("Sam")
        await expect(page.get_by_test_id("tab-manager")).to_have_attribute("aria-current", "page")
        await expect(view).to_contain_text("Experimental interpretations")
        await expect(page.get_by_test_id("manager-detail")).to_have_count(0)
        await expect(page.get_by_test_id("manager-trend")).to_have_count(0)
        await expect(page.get_by_test_id("demo-source-context")).to_be_visible()
        await expect(page.get_by_test_id("monitoring-dashboard")).to_have_count(0)
        assert not re.search(r"\bbpm\b|µS|°C|\bHRV\b|\bEDA\b", await view.inner_text()), "Raw physiological units or controls rendered in manager preview"
        await page.screenshot(path=str(artifacts / "manager-desktop.png"), full_page=True)

        await view.get_by_role("button", name="View details for Sam", exact=True).click()
        await expect(page.get_by_test_id("manager-detail")).to_have_attribute("aria-label", "Interpretation details for Sam")
        await page.get_by_role("button", name="Back to team", exact=True).click()
        await expect(page.get_by_test_id("manager-detail")).to_have_count(0)
        await expect(view.get_by_role("button", name="View details for Sam", exact=True)).to_be_focused()
        search = view.get_by_role("textbox", name="Search employees")
        await search.fill("not-a-team-member")
        await expect(page.get_by_test_id("manager-empty")).to_be_visible()
        await expect(page.get_by_test_id("manager-detail")).to_have_count(0)
        await view.get_by_role("button", name="Clear filters").click()
        await expect(page.get_by_test_id("manager-person-alex")).to_be_visible()
        await search.fill("Sam")
        await expect(page.get_by_test_id("manager-person-alex")).to_have_count(0)
        await expect(page.get_by_test_id("manager-person-aoi")).to_be_visible()
        await search.fill("")

        for width in (1440, 1024, 768, 390, 320):
            await page.set_viewport_size({"width": width, "height": 900})
            assert await page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), f"Overflow at {width}px"
            for tab in ("monitoring", "manager", "examples"):
                bounds = await page.get_by_test_id("tab-" + tab).bounding_box()
                assert bounds and bounds["x"] >= 0 and bounds["x"] + bounds["width"] <= width + 1, f"Hidden navigation: {tab} at {width}px"
        await page.set_viewport_size({"width": 390, "height": 844})
        await page.screenshot(path=str(artifacts / "manager-mobile.png"), full_page=True)
        await page.get_by_test_id("tab-monitoring").click()
        await expect(page.get_by_test_id("monitoring-dashboard")).to_be_visible()
        assert await page.evaluate("location.hash") == ""
        await page.get_by_test_id("tab-manager").click()
        assert await page.evaluate("location.hash") == "#manager"
        await page.reload(wait_until="domcontentloaded")
        await expect(view).to_be_visible()
        await page.get_by_role("link", name="Back to login").click()
        await expect(page.get_by_role("heading", name="Sign in.")).to_be_visible(timeout=15000)

        # Controlled browser inputs only. No demo controls or employee data are written.
        response = await page.request.get(API + "/api/state")
        assert response.ok
        fixture = copy.deepcopy(await response.json())
        fixture["mode"] = "replay"
        fixture["source"]["kind"] = "universe"
        for worker in fixture["workers"]:
            worker["cognitive_state"].update(cognitive_load=35, readiness=80, fatigue=20, confidence=.8)
        for signal in fixture["monitoring"]["workers"]:
            signal["status"] = "recorded"
            signal["history"] = [
                dict(time=time, cognitive_load=load, readiness=80, fatigue=20,
                     heart_rate=777, hrv=888, eda=999, temperature=444, movement=333)
                for time, load in [(0, 30), (60, 35)]
            ]
        fixture["workers"][0]["cognitive_state"]["fatigue"] = 65
        sockets = []
        isolated = await browser.new_page(viewport={"width": 1440, "height": 1000})
        isolated.on("pageerror", lambda error: errors.append(str(error)))
        isolated.on("request", lambda request: writes.append(request.url) if request.method not in ("GET", "HEAD", "OPTIONS") else None)

        async def state_route(route):
            await route.fulfill(json=fixture, headers={"access-control-allow-origin": "*"})

        async def socket_route(socket):
            sockets.append(socket)
            socket.send(json.dumps({"type": "snapshot", "data": fixture}))

        await isolated.route("**/api/state", state_route)
        await isolated.route_web_socket(re.compile(r"/ws(?:\?|$)"), socket_route)
        await isolated.goto(WEB + "/demo#manager", wait_until="domcontentloaded")
        controlled = isolated.get_by_test_id("manager-overview")
        alex = isolated.get_by_test_id("manager-person-alex")
        await expect(alex).to_contain_text("Review suggested")
        await expect(isolated.get_by_test_id("demo-source-context")).to_contain_text("UNIVERSE recordings")
        await expect(isolated.get_by_test_id("manager-detail")).to_have_count(0)
        await controlled.get_by_role("button", name="View details for Alex", exact=True).click()
        await expect(isolated.get_by_test_id("manager-trend")).to_be_visible()
        await expect(isolated.get_by_test_id("manager-estimates-alex")).to_contain_text("65")
        assert not re.search(r"777|888|999|444|333", await controlled.inner_text()), "Private source values leaked into rendered manager view"
        await controlled.get_by_role("button", name="Review suggested 1", exact=True).click()
        await expect(controlled.get_by_role("combobox", name="Filter by status")).to_have_value("review")
        await expect(isolated.get_by_test_id("manager-detail")).to_have_count(0)
        await expect(alex).to_be_visible()
        await expect(isolated.get_by_test_id("manager-person-aoi")).to_have_count(0)
        await controlled.get_by_role("combobox", name="Filter by status").select_option("all")

        # Navigation preserves the same source values; detail requires explicit selection.
        await isolated.get_by_test_id("tab-monitoring").click()
        await expect(isolated.get_by_test_id("monitor-worker-alex")).to_be_visible()
        await isolated.get_by_test_id("tab-manager").click()
        await expect(isolated.get_by_test_id("manager-detail")).to_have_count(0)
        await controlled.get_by_role("button", name="View details for Alex", exact=True).click()
        await expect(isolated.get_by_test_id("manager-estimates-alex")).to_contain_text("65")

        fixture["revision"] += 1
        next(signal for signal in fixture["monitoring"]["workers"] if signal["worker_id"] == "alex")["status"] = "stale"
        for socket in sockets:
            socket.send(json.dumps({"type": "snapshot", "data": fixture}))
        await expect(alex).to_contain_text("Unavailable")
        await expect(isolated.get_by_test_id("manager-estimates-alex")).to_have_count(0)
        await expect(isolated.get_by_test_id("manager-trend")).to_have_count(0)
        await expect(isolated.get_by_test_id("manager-detail")).to_contain_text("No interpreted trend available")
        await isolated.screenshot(path=str(artifacts / "manager-unavailable.png"), full_page=True)
        await controlled.get_by_role("combobox", name="Filter by status").select_option("unavailable")
        await expect(alex).to_be_visible()
        await expect(isolated.get_by_test_id("manager-person-aoi")).to_have_count(0)

        assert not writes, f"Manager interaction unexpectedly sent writes: {writes}"
        assert not errors, errors
        await browser.close()
    print("PASS: named employee interpretations, shared demo source, individual history, search/status filters, unavailable-state suppression, responsive navigation, deep link, return to login; no application writes or browser errors.")


if __name__ == "__main__":
    asyncio.run(main())
