import { chromium } from "playwright";
import assert from "node:assert/strict";
import fs from "node:fs/promises";

const base = process.env.OPL_TEST_URL || "http://127.0.0.1:8765";
const out = process.env.OPL_SCREENSHOT_DIR || "build/browser-smoke";
await fs.mkdir(out, {recursive: true});

const browser = await chromium.launch({headless: true});

try {
  {
    const page = await browser.newPage({
      viewport: {width: 390, height: 844},
      deviceScaleFactor: 2,
      isMobile: true,
      hasTouch: true
    });
    await page.goto(base + "/reference/ecg-id/index.html", {waitUntil: "networkidle"});
    await page.waitForSelector("#ecgCanvas");

    const bodyClass = await page.getAttribute("body", "class");
    assert.match(bodyClass || "", /mode-teaching/);

    assert.equal(await page.locator(".quick-toolbar").isVisible(), true);
    assert.equal(await page.locator(".controls").isVisible(), false);

    const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    const clientWidth = await page.evaluate(() => document.documentElement.clientWidth);
    assert.ok(scrollWidth <= clientWidth + 1, `mobile horizontal overflow: ${scrollWidth} > ${clientWidth}`);

    await page.locator('[data-quick-waveform="raw"]').tap();
    assert.equal(await page.locator('[data-quick-waveform="raw"]').getAttribute("class"), "active");

    await page.locator("#quickBaselineMedian").tap();

    const canvas = page.locator("#ecgCanvas");
    const box = await canvas.boundingBox();
    assert.ok(box && box.width > 250 && box.width <= 390);

    await canvas.tap({position: {x: box.width * 0.35, y: box.height * 0.5}});
    await canvas.tap({position: {x: box.width * 0.62, y: box.height * 0.5}});

    const measurementText = await page.locator("#measurementGrid").innerText();
    assert.match(measurementText, /Δt/);
    assert.doesNotMatch(measurementText, /Δt\s*—/);

    const firstQuizOption = page.locator(".quiz-option").first();
    await firstQuizOption.tap();
    const feedback = await page.locator("#quizFeedback").innerText();
    assert.ok(feedback.length > 10);

    await page.screenshot({path: out + "/mobile-teaching.png", fullPage: true});
    await page.close();
  }

  {
    const page = await browser.newPage({
      viewport: {width: 1440, height: 900},
      deviceScaleFactor: 1
    });
    await page.goto(base + "/reference/ecg-id/index.html", {waitUntil: "networkidle"});
    await page.waitForSelector("#ecgCanvas");

    const bodyClass = await page.getAttribute("body", "class");
    assert.match(bodyClass || "", /mode-advanced/);
    assert.equal(await page.locator(".controls").isVisible(), true);
    assert.equal(await page.locator(".quick-toolbar").isVisible(), false);

    const canvas = await page.locator("#ecgCanvas").boundingBox();
    assert.ok(canvas && canvas.width > 900);

    await page.screenshot({path: out + "/desktop-advanced.png", fullPage: true});
    await page.close();
  }

  console.log("Responsive browser smoke test passed.");
} finally {
  await browser.close();
}
