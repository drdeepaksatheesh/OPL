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
    assert.match(bodyClass || "", /theme-dark/);
    assert.match(bodyClass || "", /source-ideal/);

    assert.equal(await page.locator("#idealGuide").isVisible(), true);
    assert.equal(await page.locator(".controls").isVisible(), false);
    assert.equal(await page.locator("#gridScale").innerText(), "Small box: 40 ms × 0.1 mV (synthetic)");

    const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    const clientWidth = await page.evaluate(() => document.documentElement.clientWidth);
    assert.ok(scrollWidth <= clientWidth + 1, `mobile horizontal overflow: ${scrollWidth} > ${clientWidth}`);

    const canvas = page.locator("#ecgCanvas");
    const box = await canvas.boundingBox();
    assert.ok(box && box.width > 250 && box.width <= 390);

    // Visible window is 0.1–2.1 s. Aim near P onset (~1.0 s) and QRS onset (~1.155 s)
    // of the second complete beat so the guided calipers should identify a PR interval.
    await canvas.tap({position: {x: box.width * 0.45, y: box.height * 0.5}});
    await canvas.tap({position: {x: box.width * 0.5275, y: box.height * 0.5}});
    const idealMeasurement = await page.locator("#measurementGrid").innerText();
    assert.match(idealMeasurement, /mV/);
    assert.match(idealMeasurement, /Δt/);
    const assist = await page.locator("#measurementAssist").innerText();
    assert.match(assist, /PR interval/);
    assert.match(assist, /model 155/);

    await page.screenshot({path: out + "/mobile-ideal.png", fullPage: true});

    await page.locator("#cleanSource").tap();
    await page.waitForTimeout(100);
    assert.match((await page.getAttribute("body","class")) || "", /source-clean/);
    const cleanPlotLegend = await page.locator(".plot-card .legend").innerText();
    assert.match(cleanPlotLegend, /Clean real Lead II/);
    const cleanBaseline = await page.locator("#baselineRealityText").innerText();
    assert.match(cleanBaseline, /cardiologist-delineated PR and TP segments/i);

    const expertTable = await page.locator("#ludbMeasurementTable").innerText();
    assert.match(expertTable, /QRS duration/i);
    assert.match(expertTable, /QT interval/i);

    const cleanRecord = await page.evaluate(async () => {
      const response = await fetch("./data/LUDB_clean_LeadII.json");
      return await response.json();
    });
    const qrsOnset = cleanRecord.annotations.find(a => a.symbol === "(" && a.wave === "QRS");
    const qrsEnd = cleanRecord.annotations.find(a => a.symbol === ")" && a.wave === "QRS" && a.sample > qrsOnset.sample);
    assert.ok(qrsOnset && qrsEnd);

    // Clean stage defaults to 0–5 s at 500 Hz. Place manual calipers exactly on
    // one cardiologist-delineated QRS pair and require reference agreement.
    const cleanCanvas = page.locator("#ecgCanvas");
    const cleanBox = await cleanCanvas.boundingBox();
    const cleanVisibleSamples = 5 * cleanRecord.sampling_rate_hz;
    await cleanCanvas.tap({position: {x: cleanBox.width * (qrsOnset.sample / cleanVisibleSamples), y: cleanBox.height * 0.5}});
    await cleanCanvas.tap({position: {x: cleanBox.width * (qrsEnd.sample / cleanVisibleSamples), y: cleanBox.height * 0.5}});
    const cleanAssist = await page.locator("#measurementAssist").innerText();
    assert.match(cleanAssist, /QRS duration/i);
    assert.match(cleanAssist, /cardiologist reference/i);

    await page.screenshot({path: out + "/mobile-clean.png", fullPage: true});

    await page.locator("#realSource").tap();
    await page.waitForTimeout(100);
    const realBodyClass = await page.getAttribute("body", "class");
    assert.match(realBodyClass || "", /source-real/);

    const validationText = await page.locator(".validation-section").innerText();
    assert.match(validationText, /8\/8/);
    assert.match(validationText, /Sampling rate/);

    await page.locator('[data-quick-waveform="raw"]').tap();
    assert.equal(await page.locator('[data-quick-waveform="raw"]').getAttribute("class"), "active");

    await page.locator("#baselineUncertain").tap();
    await canvas.tap({position: {x: box.width * 0.35, y: box.height * 0.5}});
    await canvas.tap({position: {x: box.width * 0.62, y: box.height * 0.5}});
    const uncertainMeasurement = await page.locator("#measurementGrid").innerText();
    assert.match(uncertainMeasurement, /amplitude withheld/);
    assert.match(uncertainMeasurement, /ms/);

    const rrText = await page.locator("#rrBridgeStats").innerText();
    assert.match(rrText, /R–R intervals/i);

    const firstQuizOption = page.locator(".quiz-option").first();
    await firstQuizOption.tap();
    const feedback = await page.locator("#quizFeedback").innerText();
    assert.ok(feedback.length > 10);

    await page.screenshot({path: out + "/mobile-real.png", fullPage: true});
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
    assert.match(bodyClass || "", /mode-teaching/);
    assert.match(bodyClass || "", /theme-dark/);
    assert.match(bodyClass || "", /source-ideal/);
    assert.equal(await page.locator(".controls").isVisible(), false);

    const canvas = await page.locator("#ecgCanvas").boundingBox();
    assert.ok(canvas && canvas.width > 900);
    assert.equal(await page.locator("#nextToClean").isVisible(), true);
    await page.screenshot({path: out + "/desktop-ideal.png", fullPage: true});

    await page.locator("#realSource").click();
    await page.waitForTimeout(100);
    const validationText = await page.locator(".validation-section").innerText();
    assert.match(validationText, /8\/8/);
    assert.equal(await page.locator("#downloadValidation").isVisible(), true);

    await page.locator("#themeToggle").click();
    assert.match((await page.getAttribute("body","class")) || "", /theme-light/);
    await page.locator("#themeToggle").click();
    assert.match((await page.getAttribute("body","class")) || "", /theme-dark/);

    await page.screenshot({path: out + "/desktop-real.png", fullPage: true});
    await page.close();
  }

  console.log("Ideal-to-real responsive browser smoke test passed.");
} finally {
  await browser.close();
}
