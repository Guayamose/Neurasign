"""Exercise real saved-model inference through the local browser/API stack."""

import asyncio
import json
import os
from pathlib import Path

from playwright.async_api import async_playwright, expect


ROOT = Path(__file__).resolve().parents[1]
WEB = os.getenv("NEURASIGN_WEB_URL", "http://localhost:3000")
EXPECTED = {"stress": 86, "readiness": 684, "fatigue": 96, "workload": 167}


async def main():
    artifacts = ROOT / "artifacts"
    artifacts.mkdir(exist_ok=True)
    errors = []
    predictions = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            channel="chrome", headless=True, args=["--no-sandbox"]
        )
        page = await browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda error: errors.append(str(error)))
        await page.goto(WEB + "/models", wait_until="domcontentloaded")
        await expect(page.locator("html")).to_have_attribute("lang", "en")
        await expect(page.get_by_test_id("run-model")).to_be_enabled(timeout=60000)
        await expect(page.get_by_text("Bundle verified", exact=True)).to_have_count(1)

        for model_id, count in EXPECTED.items():
            await page.get_by_test_id("model-" + model_id).click()
            await expect(page.get_by_test_id("model-prediction")).to_have_count(0)
            await expect(page.locator("#model-record option")).to_have_count(count)
            await expect(page.get_by_test_id("run-model")).to_be_enabled()
            record_id = await page.locator("#model-record").input_value()
            async with page.expect_response(
                lambda response: response.url.endswith(f"/models/{model_id}/predict")
            ) as response_info:
                await page.get_by_test_id("run-model").click()
            response = await response_info.value
            assert response.ok, (model_id, response.status, await response.text())
            result = await response.json()
            assert result["model_id"] == model_id
            assert result["record_id"] == record_id
            assert result["scope"] == "anonymous_research"
            assert result["production_enabled"] is False
            assert result["confidence"] is None
            assert len(result["provenance"]["artifact_sha256"]) == 64
            output = page.get_by_test_id("model-prediction")
            await expect(output).to_be_visible()
            await expect(output).to_contain_text("MODEL PREDICTION", ignore_case=True)
            await expect(output).to_contain_text("RECORDED REFERENCE", ignore_case=True)
            await output.get_by_text("Prediction provenance", exact=True).click()
            await expect(output).to_contain_text(result["provenance"]["artifact_sha256"])
            predictions.append({
                "model": model_id,
                "records": count,
                "prediction": result["prediction"],
                "reference": result["reference"],
            })
            await page.screenshot(path=str(artifacts / f"model-engine-{model_id}.png"), full_page=True)
            await page.locator("#model-record").select_option(index=1)
            await expect(output).to_have_count(0)

        # Invalid employee input is rejected at the same-origin boundary.
        rejected = await page.request.post(
            WEB + "/api/model-engine/models/stress/predict",
            data={"record_id": "stress-0001", "employee_id": "employee-1"},
        )
        assert rejected.status == 422

        # A real service failure clears the old result; it cannot show a fallback score.
        await page.route("**/api/model-engine/models/workload/predict", lambda route: route.fulfill(
            status=503, content_type="application/json",
            body=json.dumps({"detail": "Model service is unavailable."}),
        ))
        await page.get_by_test_id("run-model").click()
        await expect(page.get_by_role("alert").filter(has_text="Prediction unavailable")).to_be_visible()
        await expect(page.get_by_test_id("model-prediction")).to_have_count(0)
        await page.unroute("**/api/model-engine/models/workload/predict")

        await page.set_viewport_size({"width": 390, "height": 844})
        await page.get_by_test_id("model-readiness").click()
        await expect(page.get_by_test_id("run-model")).to_be_enabled()
        await page.get_by_test_id("run-model").click()
        await expect(page.get_by_test_id("model-prediction")).to_be_visible(timeout=60000)
        assert await page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), "Mobile horizontal overflow"
        await page.screenshot(path=str(artifacts / "model-engine-mobile.png"), full_page=True)

        await page.set_viewport_size({"width": 1440, "height": 1000})
        await page.goto(WEB + "/demo", wait_until="domcontentloaded")
        await expect(page.get_by_test_id("monitoring-dashboard")).to_be_visible(timeout=30000)
        await page.get_by_role("link", name="Model engine", exact=True).click()
        await expect(page).to_have_url(WEB + "/models")
        await expect(page.get_by_test_id("run-model")).to_be_enabled(timeout=60000)

        await page.goto(WEB + "/", wait_until="domcontentloaded")
        await page.get_by_role("button", name="Sign in with test account").click()
        await expect(page.get_by_test_id("company-workspace")).to_be_visible(timeout=30000)
        await page.locator(".co-research-nav > summary").click()
        await page.get_by_role("link", name="Model engine", exact=True).click()
        await expect(page).to_have_url(WEB + "/models")
        await expect(page.get_by_test_id("run-model")).to_be_enabled(timeout=60000)

        await page.route("**/api/model-engine/catalog", lambda route: route.fulfill(
            status=503, content_type="application/json",
            body=json.dumps({"detail": "Model service is unavailable."}),
        ))
        await page.reload(wait_until="domcontentloaded")
        await expect(page.get_by_role("alert").filter(has_text="Model engine unavailable")).to_be_visible()
        await expect(page.get_by_test_id("model-prediction")).to_have_count(0)
        await page.unroute("**/api/model-engine/catalog")
        await page.get_by_role("button", name="Retry connection").click()
        await expect(page.get_by_test_id("run-model")).to_be_enabled(timeout=60000)
        assert not errors, json.dumps(errors)
        await browser.close()
    print(json.dumps(predictions, indent=2))
    print("PASS: four real model executions, recorded references and hashes, strict inputs, stale-result clearing, service failures/recovery, company/demo navigation and mobile layout.")


if __name__ == "__main__":
    asyncio.run(main())
