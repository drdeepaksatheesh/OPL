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

    assert.equal(await page.locator("#stageSelect").inputValue(), "ideal");
    assert.equal(await page.locator("#controlsDrawer").evaluate(el => el.open), false);
    assert.equal(await page.locator("#gridScale").innerText(), "ECG paper: square boxes · 40 ms × 0.1 mV (synthetic)");

    const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    const clientWidth = await page.evaluate(() => document.documentElement.clientWidth);
    assert.ok(scrollWidth <= clientWidth + 1, `mobile horizontal overflow: ${scrollWidth} > ${clientWidth}`);

    const canvas = page.locator("#ecgCanvas");
    const box = await canvas.boundingBox();
    assert.ok(box && box.width > 250 && box.width <= 390);

    // Visible window is 0.1–2.1 s. Aim near P onset (~1.0 s) and QRS onset (~1.160 s)
    // of the second complete beat so the guided calipers should identify a PR interval.
    await canvas.tap({position: {x: box.width * 0.45, y: box.height * 0.5}});
    await canvas.tap({position: {x: box.width * 0.53, y: box.height * 0.5}});
    const idealMeasurement = await page.locator("#measurementGrid").innerText();
    assert.match(idealMeasurement, /mV/);
    assert.match(idealMeasurement, /Δt/);
    assert.match(idealMeasurement, /small boxes/);
    const assist = await page.locator("#measurementAssist").innerText();
    assert.match(assist, /PR interval/);
    assert.match(assist, /model 160/);

    await page.screenshot({path: out + "/mobile-ideal.png", fullPage: true});

    await page.locator("#nextToClean").tap();
    await page.waitForTimeout(100);
    assert.equal(await page.locator("#stageSelect").inputValue(), "clean");
    assert.match((await page.getAttribute("body","class")) || "", /source-clean/);
    assert.equal(await page.locator("#windowLength").inputValue(), "2");
    const cleanPlotLegend = await page.locator(".plot-card .legend").innerText();
    assert.match(cleanPlotLegend, /Clean real Lead II/);
    const cleanBaseline = await page.locator("#baselineRealityText").innerText();
    assert.match(cleanBaseline, /cardiologist-delineated PR and TP segments/i);

    await page.locator("#evidenceDrawer").evaluate(el => { el.open = true; });
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

    // Clean stage now uses the same 0–2 s teaching window as the ideal trace.
    // Place manual calipers exactly on one cardiologist-delineated QRS pair.
    const cleanCanvas = page.locator("#ecgCanvas");
    const cleanBox = await cleanCanvas.boundingBox();
    const cleanEndSample = 2 * cleanRecord.sampling_rate_hz - 1;
    await cleanCanvas.tap({position: {x: cleanBox.width * (qrsOnset.sample / cleanEndSample), y: cleanBox.height * 0.5}});
    await cleanCanvas.tap({position: {x: cleanBox.width * (qrsEnd.sample / cleanEndSample), y: cleanBox.height * 0.5}});
    const cleanAssist = await page.locator("#measurementAssist").innerText();
    assert.match(cleanAssist, /QRS duration/i);
    assert.match(cleanAssist, /cardiologist reference/i);

    await page.screenshot({path: out + "/mobile-clean.png", fullPage: true});

    await page.locator("#nextToImperfect").tap();
    await page.waitForTimeout(100);
    assert.equal(await page.locator("#stageSelect").inputValue(), "real");
    assert.equal(await page.locator("#windowLength").inputValue(), "2");
    const realBodyClass = await page.getAttribute("body", "class");
    assert.match(realBodyClass || "", /source-real/);
    assert.match(await page.locator("#rulerSmallBox").innerText(), /40 ms × 0.1 mV/);
    assert.match(await page.locator("#gridScale").innerText(), /ADC→mV conversion/);

    await page.locator("#evidenceDrawer").evaluate(el => { el.open = true; });
    const validationText = await page.locator(".validation-section").innerText();
    assert.match(validationText, /8\/8/);
    assert.match(validationText, /Sampling rate/);

    await page.locator('[data-quick-waveform="raw"]').tap();
    assert.equal(await page.locator('[data-quick-waveform="raw"]').getAttribute("class"), "active");

    await page.locator("#baselineUncertain").tap();
    await canvas.tap({position: {x: box.width * 0.35, y: box.height * 0.5}});
    await canvas.tap({position: {x: box.width * 0.62, y: box.height * 0.5}});
    const uncertainMeasurement = await page.locator("#measurementGrid").innerText();
    assert.match(uncertainMeasurement, /withheld/);
    assert.match(uncertainMeasurement, /small boxes/);

    await page.locator("#nextToAdc").tap();
    await page.waitForTimeout(100);
    assert.equal(await page.locator("#stageSelect").inputValue(), "adc");
    assert.match((await page.getAttribute("body","class")) || "", /source-machine/);
    assert.match(await page.locator("#rulerSmallBox").innerText(), /40 ms × 20 ADC/);
    assert.match(await page.locator("#gridScale").innerText(), /~0.1 mV/);

    await page.locator("#practiceJump").tap();
    await page.waitForTimeout(100);
    assert.equal(await page.locator("#stageSelect").inputValue(), "practice");
    assert.match((await page.getAttribute("body","class")) || "", /source-practice/);
    assert.equal(await page.locator(".practice-record-button").count(), 6);
    await page.locator(".practice-record-button").nth(1).tap();
    await page.locator("#practiceTask").selectOption("qrs_duration");
    await page.locator("#baselineMedian").tap();

    const practiceRecord = await page.evaluate(async () => {
      const response = await fetch("./practice/records/LUDB_58_LeadII.json");
      return await response.json();
    });
    const pOn = practiceRecord.annotations.find(a => a.symbol === "(" && a.wave === "QRS" && a.sample < 1000);
    const pEnd = practiceRecord.annotations.find(a => a.symbol === ")" && a.wave === "QRS" && a.sample > pOn.sample && a.sample < 1000);
    const practiceCanvas = page.locator("#ecgCanvas");
    const practiceBox = await practiceCanvas.boundingBox();
    const practiceEnd = 2 * practiceRecord.sampling_rate_hz - 1;
    await practiceCanvas.tap({position:{x:practiceBox.width*(pOn.sample/practiceEnd),y:practiceBox.height*0.5}});
    await practiceCanvas.tap({position:{x:practiceBox.width*(pEnd.sample/practiceEnd),y:practiceBox.height*0.5}});
    const practiceMeasurement = await page.locator("#measurementGrid").innerText();
    assert.match(practiceMeasurement,/small boxes/);
    assert.match(practiceMeasurement,/mV/);
    await page.locator("#practiceReveal").tap();
    assert.match(await page.locator("#practiceReview").innerText(),/Expert revealed/);
    assert.match(await page.locator("#practiceReview").innerText(),/record 58/);
    assert.match(await page.locator("#measurementAssist").innerText(),/QRS duration/i);

    await page.locator("details.dock-card.biological-only").evaluate(el => { el.open = true; });
    const rrText = await page.locator("#rrBridgeStats").innerText();
    assert.match(rrText, /R–R intervals/i);

    await page.locator("#learningDrawer").evaluate(el => { el.open = true; });
    const firstQuizOption = page.locator(".quiz-option").first();
    await firstQuizOption.tap();
    const feedback = await page.locator("#quizFeedback").innerText();
    assert.ok(feedback.length > 10);

    await page.screenshot({path: out + "/mobile-practice.png", fullPage: true});
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
    assert.equal(await page.locator("#controlsDrawer").evaluate(el => el.open), false);

    const canvas = await page.locator("#ecgCanvas").boundingBox();
    assert.ok(canvas && canvas.width > 900);
    assert.equal(await page.locator("#nextToClean").isVisible(), true);

    // Drag exactly from source-sample P onset (500) to QRS onset (580).
    // Visible samples are 50..1049, so use source-sample geometry rather than
    // approximate percentages of the nominal 0.1–2.1 s window.
    const dragY = canvas.y + canvas.height * 0.5;
    const idealStartSample = 50;
    const idealEndSample = 1049;
    const pOnsetFraction = (500 - idealStartSample) / (idealEndSample - idealStartSample);
    const qrsOnsetFraction = (580 - idealStartSample) / (idealEndSample - idealStartSample);
    await page.mouse.move(canvas.x + canvas.width * pOnsetFraction, dragY);
    await page.mouse.down();
    await page.mouse.move(canvas.x + canvas.width * qrsOnsetFraction, dragY, {steps: 8});
    await page.mouse.up();

    const dragAssist = await page.locator("#measurementAssist").innerText();
    assert.match(dragAssist, /PR interval/);
    assert.match(dragAssist, /model 160/);
    const dragMeasurement = await page.locator("#measurementGrid").innerText();
    assert.match(dragMeasurement, /160 ms/);

    await page.screenshot({path: out + "/desktop-ideal.png", fullPage: true});

    await page.locator("#nextToClean").click();
    await page.waitForTimeout(100);
    assert.equal(await page.locator("#stageSelect").inputValue(), "clean");
    assert.equal(await page.locator("#windowLength").inputValue(), "2");

    await page.locator("#nextToImperfect").click();
    await page.waitForTimeout(100);
    assert.equal(await page.locator("#stageSelect").inputValue(), "real");
    assert.match(await page.locator("#gridScale").innerText(),/0.1 mV/);
    await page.locator("#evidenceDrawer").evaluate(el => { el.open = true; });
    const validationText = await page.locator(".validation-section").innerText();
    assert.match(validationText, /8\/8/);
    assert.equal(await page.locator("#downloadValidation").isVisible(), true);

    await page.locator("#nextToAdc").click();
    await page.waitForTimeout(100);
    assert.equal(await page.locator("#stageSelect").inputValue(), "adc");
    assert.match(await page.locator("#gridScale").innerText(),/20 ADC/);

    await page.locator("#practiceJump").click();
    await page.waitForTimeout(100);
    assert.equal(await page.locator("#stageSelect").inputValue(), "practice");
    assert.equal(await page.locator(".practice-record-button").count(),6);

    await page.locator("#themeToggle").click();
    assert.match((await page.getAttribute("body","class")) || "", /theme-light/);
    await page.locator("#themeToggle").click();
    assert.match((await page.getAttribute("body","class")) || "", /theme-dark/);

    await page.screenshot({path: out + "/desktop-practice.png", fullPage: true});
    await page.close();
  }

  console.log("Four-stage ECG story + real-ECG practice responsive browser smoke test passed.");
} finally {
  await browser.close();
}
