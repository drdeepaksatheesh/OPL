import {
  sampleToMs,
  durationMs,
  deltaAdc,
  median,
  validateReferenceRecord,
  makeExportPackage,
  importExportPackage,
  downloadJson
} from "../../reference-lab-core.mjs";
import {saveRecord, getRecord} from "../../offline-store.mjs";
import {validateReferenceIntegrity, makeValidationReport} from "../../reference-validation.mjs";
import {generateIdealEcg, IDEAL_ECG_SPEC} from "./ideal-ecg.mjs";
import {ECG_TEACHING_QUESTIONS, evaluateAnswer, scoreQuiz} from "./teaching.mjs";

const IMPERFECT_RECORD_URL = "./data/Person_01_rec_1.json";
const CLEAN_RECORD_URL = "./data/LUDB_clean_LeadII.json";
const REAL_RECORD_ID = "ECG-ID/Person_01/rec_1";
const CLEAN_RECORD_ID_PREFIX = "LUDB/";
const SESSION_KEY_BASE = "opl:ecg-reference:session:";
const MODE_KEY = "opl:ecg-reference:mode";
const THEME_KEY = "opl:theme";
const QUIZ_KEY = "opl:ecg-reference:quiz";

const state = {
  record: null,
  realRecord: null,
  cleanRecord: null,
  idealRecord: generateIdealEcg(),
  sourceManifest: null,
  buildInfo: null,
  sourceMode: "ideal",
  baseline: 0,
  baselineStatus: "known",
  calipers: {a: null, b: null},
  nextCaliper: "a",
  mode: "raw",
  measurementSignal: "raw",
  windowSeconds: 2,
  windowStartSeconds: 0.1,
  showAnnotations: true,
  verticalGridAdc: 50,
  interfaceMode: "advanced",
  theme: "dark",
  quizIndex: 0,
  quizResponses: {}
};

const el = Object.fromEntries([
  "onlineState","provenanceGrid","provenanceDetails","provenanceSummary",
  "waveformMode","measurementSignal","verticalGrid","gridScale","windowLength",
  "windowStart","windowStartLabel","showAnnotations","ecgCanvas","baselineHeading",
  "baselineOutput","baselineInput","baselineZero","baselineMedian","baselineFromA",
  "baselineConfident","baselineUncertain","baselineRealityText","resetCalipers",
  "measurementGrid","saveOffline","exportPackage","importPackage","keepStatus",
  "quickMode","advancedMode","themeToggle","idealSource","cleanSource","realSource",
  "quizScore","quizTotal","quizQuestion","quizOptions","quizFeedback","quizNext","quizReset",
  "validationPassed","validationTotal","validationChecks","downloadValidation",
  "rrBridgeStats","cleanBaselineDetails","cleanSelectionSummary"
].map(id => [id, document.getElementById(id)]));

const ctx = el.ecgCanvas.getContext("2d");

boot();

async function boot() {
  initTheme();
  initInterfaceMode();
  restoreQuiz();
  bindEvents();
  renderQuiz();
  resizeCanvas();
  window.addEventListener("resize", () => { resizeCanvas(); draw(); });

  try {
    state.sourceManifest = await fetch("./manifest.json").then(requireOk).then(r => r.json());
  } catch {
    state.sourceManifest = null;
  }

  try {
    state.buildInfo = await fetch("../../build-info.json").then(requireOk).then(r => r.json());
  } catch {
    state.buildInfo = null;
  }

  try {
    state.cleanRecord = await fetch(CLEAN_RECORD_URL, {cache: "no-cache"}).then(requireOk).then(r => r.json());
  } catch {
    state.cleanRecord = null;
  }

  try {
    state.realRecord = await fetch(IMPERFECT_RECORD_URL, {cache: "no-cache"}).then(requireOk).then(r => r.json());
  } catch {
    state.realRecord = await getRecord(REAL_RECORD_ID).catch(() => null);
  }

  el.cleanSource.disabled = !state.cleanRecord;
  el.realSource.disabled = !state.realRecord;
  el.onlineState.textContent = state.cleanRecord && state.realRecord
    ? (navigator.onLine ? "Reference data ready" : "Offline reference data")
    : "Some reference data unavailable";

  switchSource("ideal", {restore:true});
}

function bindEvents() {
  el.quickMode.addEventListener("click", () => setInterfaceMode("teaching"));
  el.advancedMode.addEventListener("click", () => setInterfaceMode("advanced"));
  el.themeToggle.addEventListener("click", () => setTheme(state.theme === "dark" ? "light" : "dark"));

  el.idealSource.addEventListener("click", () => switchSource("ideal", {restore:true}));
  el.nextToClean?.addEventListener("click", () => {
    switchSource("clean", {restore:true});
    scrollToLab();
  });
  el.nextToImperfect?.addEventListener("click", () => {
    switchSource("real", {restore:true});
    scrollToLab();
  });
  el.backToClean?.addEventListener("click", () => {
    switchSource("clean", {restore:true});
    scrollToLab();
  });
  el.cleanSource.addEventListener("click", () => {
    if (!state.cleanRecord) {
      showStatus("The clean LUDB reference is unavailable in this build.", true);
      return;
    }
    switchSource("clean", {restore:true});
  });
  el.realSource.addEventListener("click", () => {
    if (!state.realRecord) {
      showStatus("The real ECG-ID record is unavailable in this build/offline cache.", true);
      return;
    }
    switchSource("real", {restore:true});
  });

  document.querySelectorAll("[data-quick-waveform]").forEach(button => {
    button.addEventListener("click", () => {
      if (state.sourceMode !== "real") return;
      state.mode = button.dataset.quickWaveform;
      el.waveformMode.value = state.mode;
      syncQuickWaveformButtons();
      draw();
    });
  });

  el.waveformMode.addEventListener("change", () => {
    state.mode = el.waveformMode.value;
    syncQuickWaveformButtons();
    draw();
  });

  el.measurementSignal.addEventListener("change", () => {
    state.measurementSignal = el.measurementSignal.value;
    renderMeasurements();
    draw();
  });

  el.verticalGrid.addEventListener("change", () => {
    state.verticalGridAdc = Number(el.verticalGrid.value);
    updateGridLabel();
    draw();
  });

  el.windowLength.addEventListener("change", () => {
    state.windowSeconds = Number(el.windowLength.value);
    clampWindowStart();
    syncWindowControls();
    draw();
  });

  el.windowStart.addEventListener("input", () => {
    state.windowStartSeconds = Number(el.windowStart.value);
    syncWindowControls();
    draw();
  });

  el.showAnnotations.addEventListener("change", () => {
    state.showAnnotations = el.showAnnotations.checked;
    draw();
  });

  el.baselineInput.addEventListener("change", () => {
    if (state.sourceMode === "real") setBaseline(Number(el.baselineInput.value), "selected");
  });
  el.baselineZero.addEventListener("click", () => {
    if (state.sourceMode !== "real") return;
    setBaseline(Number(state.record?.adc?.zero?.[signalIndex()] ?? 0), "selected");
  });
  el.baselineMedian.addEventListener("click", useVisibleMedianBaseline);
  el.baselineFromA.addEventListener("click", () => {
    if (state.sourceMode !== "real" || state.calipers.a == null) return;
    setBaseline(activeSignal()[state.calipers.a], "selected");
  });
  el.baselineConfident.addEventListener("click", () => setBaselineStatus("selected"));
  el.baselineUncertain.addEventListener("click", () => setBaselineStatus("uncertain"));

  el.resetCalipers.addEventListener("click", () => {
    state.calipers = {a:null,b:null};
    state.nextCaliper = "a";
    persistSession();
    renderMeasurements();
    draw();
  });

  el.ecgCanvas.addEventListener("click", event => {
    if (!state.record) return;
    const rect = el.ecgCanvas.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const [start,end] = visibleSampleRange();
    const fraction = Math.max(0, Math.min(1, x / rect.width));
    const sample = Math.min(end - 1, Math.max(start, Math.round(start + fraction * (end - start - 1))));
    state.calipers[state.nextCaliper] = sample;
    state.nextCaliper = state.nextCaliper === "a" ? "b" : "a";
    persistSession();
    renderMeasurements();
    draw();
  });

  el.saveOffline.addEventListener("click", async () => {
    if (state.sourceMode === "ideal") {
      showStatus("The ideal trace is generated locally and does not need to be downloaded for offline use.");
      return;
    }
    await saveRecord(state.record);
    persistSession();
    showStatus(state.sourceMode === "clean"
      ? "Saved the clean LUDB reference locally in this browser."
      : "Saved the ECG-ID reference locally in this browser.");
  });

  el.downloadValidation.addEventListener("click", () => {
    if (state.sourceMode !== "real" || !state.realRecord) return;
    const report = makeValidationReport({
      record: state.realRecord,
      oplVersion: window.OPL_CONFIG?.version,
      oplCommit: state.buildInfo?.git_sha
    });
    downloadJson("OPL_ECG-ID_Person_01_rec_1_validation-report.json", report);
    showStatus("Downloaded the source-integrity validation report for this exact OPL build.");
  });

  el.exportPackage.addEventListener("click", () => {
    if (!state.record) return;
    const pkg = makeExportPackage({
      record: state.record,
      baseline: state.baseline,
      calipers: state.calipers,
      oplVersion: window.OPL_CONFIG?.version,
      oplCommit: state.buildInfo?.git_sha
    });
    pkg.session.baseline_status = state.baselineStatus;
    pkg.session.source_mode = state.sourceMode;
    const name = state.sourceMode === "ideal"
      ? "OPL_Ideal_ECG_teaching-package.json"
      : state.sourceMode === "clean"
        ? "OPL_LUDB_clean_LeadII_reference-package.json"
        : "OPL_ECG-ID_Person_01_rec_1_reference-package.json";
    downloadJson(name, pkg);
    showStatus("Downloaded the current OPL package with waveform, provenance, baseline state and calipers.");
  });

  el.importPackage.addEventListener("change", async event => {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      const value = JSON.parse(await file.text());
      const imported = importExportPackage(value);
      const importedId = String(imported.record?.record_id || "");
      const isIdeal = Boolean(imported.record?.provenance?.teaching_only) || importedId.startsWith("OPL-IDEAL/");
      const isClean = importedId.startsWith(CLEAN_RECORD_ID_PREFIX);
      if (isIdeal) {
        state.idealRecord = imported.record;
        switchSource("ideal", {session:imported.session});
      } else if (isClean) {
        state.cleanRecord = imported.record;
        switchSource("clean", {session:imported.session});
      } else {
        state.realRecord = imported.record;
        switchSource("real", {session:imported.session});
      }
      showStatus("Opened the saved OPL package.");
    } catch (error) {
      showStatus("Could not open package: " + error.message, true);
    } finally {
      event.target.value = "";
    }
  });

  el.quizNext.addEventListener("click", () => {
    state.quizIndex = (state.quizIndex + 1) % ECG_TEACHING_QUESTIONS.length;
    persistQuiz();
    renderQuiz();
  });

  el.quizReset.addEventListener("click", () => {
    state.quizIndex = 0;
    state.quizResponses = {};
    persistQuiz();
    renderQuiz();
  });

  window.addEventListener("online", () => { el.onlineState.textContent = "Online"; });
  window.addEventListener("offline", () => { el.onlineState.textContent = "Offline"; });
}

function switchSource(mode, {restore=false, session=null} = {}) {
  const next = mode === "clean" ? "clean" : mode === "real" ? "real" : "ideal";
  const record = next === "clean" ? state.cleanRecord : next === "real" ? state.realRecord : state.idealRecord;
  if (!record) return;

  validateReferenceRecord(record);
  state.sourceMode = next;
  state.record = record;
  document.body.classList.toggle("source-ideal", next === "ideal");
  document.body.classList.toggle("source-clean", next === "clean");
  document.body.classList.toggle("source-real", next === "real");
  el.idealSource.classList.toggle("active", next === "ideal");
  el.cleanSource.classList.toggle("active", next === "clean");
  el.realSource.classList.toggle("active", next === "real");

  const restored = session || (restore ? restoreSession(next) : null);
  state.calipers = {
    a: integerOrNull(restored?.calipers?.a),
    b: integerOrNull(restored?.calipers?.b)
  };
  state.nextCaliper = state.calipers.a == null ? "a" : state.calipers.b == null ? "b" : "a";

  if (next === "ideal") {
    state.baseline = 0;
    state.baselineStatus = "known";
    state.mode = "raw";
    state.measurementSignal = "raw";
    state.windowSeconds = 2;
    state.windowStartSeconds = 0.1;
    state.showAnnotations = true;
  } else if (next === "clean") {
    state.baseline = Number(restored?.baseline_adc ?? record.recommended_baseline_mV ?? 0);
    state.baselineStatus = "reference";
    state.mode = "raw";
    state.measurementSignal = "raw";
    state.windowSeconds = 5;
    state.windowStartSeconds = 0;
    state.showAnnotations = true;
  } else {
    state.baseline = Number(restored?.baseline_adc ?? record.adc?.zero?.[0] ?? 0);
    state.baselineStatus = restored?.baseline_status === "uncertain" ? "uncertain" : "selected";
    state.mode = "overlay";
    state.measurementSignal = "raw";
    state.windowSeconds = 5;
    state.windowStartSeconds = 0;
    state.showAnnotations = true;
  }

  syncControlsFromState();
  renderAll();
  persistSession();
}

function renderAll() {
  clampWindowStart();
  syncWindowControls();
  renderProvenance();
  renderMeasurements();
  renderBaselineReality();
  renderCleanSelection();
  renderRrBridge();
  renderValidation();
  syncQuickWaveformButtons();
  updateGridLabel();
  updateLogicPath();
  draw();
}

function syncControlsFromState() {
  el.waveformMode.value = state.mode;
  el.measurementSignal.value = state.measurementSignal;
  el.verticalGrid.value = String(state.verticalGridAdc);
  el.windowLength.value = String(state.windowSeconds);
  el.showAnnotations.checked = state.showAnnotations;
  el.baselineInput.value = String(roundNumber(state.baseline, 4));
  el.saveOffline.disabled = state.sourceMode === "ideal";
  el.downloadValidation.disabled = state.sourceMode !== "real";
  el.baselineHeading.textContent = state.sourceMode === "ideal"
    ? "Known baseline"
    : state.sourceMode === "clean"
      ? "Annotated isoelectric reference"
      : "Choose a local reference";
}

function initInterfaceMode() {
  let saved = null;
  try { saved = localStorage.getItem(MODE_KEY); } catch {}
  const defaultMode = "teaching";
  setInterfaceMode(saved === "teaching" || saved === "advanced" ? saved : defaultMode, false);
}

function setInterfaceMode(mode, persist=true) {
  state.interfaceMode = mode === "teaching" ? "teaching" : "advanced";
  document.body.classList.toggle("mode-teaching", state.interfaceMode === "teaching");
  document.body.classList.toggle("mode-advanced", state.interfaceMode === "advanced");
  el.quickMode.setAttribute("aria-pressed", String(state.interfaceMode === "teaching"));
  el.advancedMode.setAttribute("aria-pressed", String(state.interfaceMode === "advanced"));
  if (el.provenanceDetails) el.provenanceDetails.open = state.interfaceMode === "advanced";
  if (persist) {
    try { localStorage.setItem(MODE_KEY, state.interfaceMode); } catch {}
  }
  requestAnimationFrame(() => { resizeCanvas(); draw(); });
}

function initTheme() {
  let saved = null;
  try { saved = localStorage.getItem(THEME_KEY); } catch {}
  setTheme(saved === "light" ? "light" : "dark", false);
}

function setTheme(theme, persist=true) {
  state.theme = theme === "light" ? "light" : "dark";
  document.body.classList.toggle("theme-dark", state.theme === "dark");
  document.body.classList.toggle("theme-light", state.theme === "light");
  el.themeToggle.textContent = state.theme === "dark" ? "Light mode" : "Dark mode";
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", state.theme === "dark" ? "#050608" : "#F4F6F8");
  if (persist) {
    try { localStorage.setItem(THEME_KEY, state.theme); } catch {}
  }
  requestAnimationFrame(draw);
}

function syncQuickWaveformButtons() {
  document.querySelectorAll("[data-quick-waveform]").forEach(button => {
    button.classList.toggle("active", button.dataset.quickWaveform === state.mode);
  });
}

function renderProvenance() {
  const p = state.record?.provenance || {};
  const m = state.sourceMode === "real" ? (state.sourceManifest || {}) : {};

  let values;
  let summary;

  if (state.sourceMode === "ideal") {
    values = [
      ["Source type", "Synthetic teaching model"],
      ["Generator", p.dataset || "OPL idealized teaching template"],
      ["Version", p.dataset_version || "v1"],
      ["Sampling", state.record.sampling_rate_hz + " Hz"],
      ["Baseline", "0 mV by construction"],
      ["Grid", "40 ms × 0.1 mV"],
      ["Validation role", "Teaching only — not ground truth"],
      ["Processing", p.known_preprocessing || "None"],
      ["License", p.license || "GPL-3.0 project code"],
      ["OPL build", buildLabel()]
    ];
    summary = "OPL idealized teaching template · synthetic · 500 Hz";
  } else if (state.sourceMode === "clean") {
    values = [
      ["Dataset", p.dataset || "Lobachevsky University ECG Database (LUDB)"],
      ["Repository", p.repository || "PhysioNet"],
      ["Version", p.dataset_version || "1.0.1"],
      ["DOI", p.doi || "10.13026/eegm-h675"],
      ["License", p.license || "ODC Attribution 1.0"],
      ["Record / lead", (p.record || state.record.record_id) + " · Lead " + (p.lead || "II")],
      ["Sampling", state.record.sampling_rate_hz + " Hz"],
      ["Amplitude", "Physical mV from source WFDB metadata"],
      ["Annotations", "Manual P / QRS / T peaks and boundaries by LUDB cardiologists"],
      ["Selection", "Metadata eligibility + objective Lead-II baseline/noise ranking"],
      ["OPL processing", "No filtering applied to displayed waveform"],
      ["OPL build", buildLabel()]
    ];
    summary = "LUDB " + (p.record || "119") + " · real Lead II · 500 Hz · physical mV";
  } else {
    const acquisition = state.record?.adc?.resolution_bits ? state.record.adc.resolution_bits + "-bit" : "—";
    values = [
      ["Dataset", p.dataset || m.title || "ECG-ID Database"],
      ["Repository", p.repository || m.repository || "PhysioNet"],
      ["Contributor", p.contributor || m.contributor || "Tatiana Lugovaya"],
      ["Version", p.dataset_version || m.version || "1.0.0"],
      ["DOI", p.doi || m.doi || "10.13026/C2J01F"],
      ["License", p.license || m.license || "ODC Attribution 1.0"],
      ["Record", state.record.record_id],
      ["Sampling", state.record.sampling_rate_hz + " Hz"],
      ["Acquisition", acquisition],
      ["OPL processing", "None unless explicitly selected"],
      ["OPL build", buildLabel()]
    ];
    summary = (p.dataset || "ECG-ID") + " · " + (p.repository || "PhysioNet") + " · " +
      state.record.sampling_rate_hz + " Hz · " + acquisition;
  }

  el.provenanceSummary.textContent = summary;
  el.provenanceGrid.innerHTML = values.map(([label,value]) => {
    const content = label === "DOI" && value && value !== "—"
      ? '<a href="https://doi.org/' + escapeHtml(String(value)) + '" target="_blank" rel="noopener">' +
        escapeHtml(String(value)) + "</a>"
      : "<strong>" + escapeHtml(String(value ?? "—")) + "</strong>";
    return '<div class="provenance-item"><span>' + escapeHtml(label) + "</span>" + content + "</div>";
  }).join("");
}

function renderValidation() {
  if (state.sourceMode !== "real" || !state.realRecord) {
    el.validationPassed.textContent = "—";
    el.validationTotal.textContent = "real record only";
    el.validationChecks.innerHTML = "";
    return;
  }
  const result = validateReferenceIntegrity(state.realRecord);
  el.validationPassed.textContent = result.passed + "/" + result.total;
  el.validationTotal.textContent = result.all_passed ? "checks passed" : "checks";

  el.validationChecks.innerHTML = result.checks.map(check => {
    const cls = check.pass ? "pass" : "fail";
    const status = check.pass ? "PASS" : "CHECK";
    return '<div class="validation-check ' + cls + '">' +
      '<div class="check-title"><span>' + escapeHtml(check.label) + '</span><span class="check-status">' + status + '</span></div>' +
      '<p><strong>Observed:</strong> ' + escapeHtml(formatValidationValue(check.observed)) +
      '<br><strong>Expected:</strong> ' + escapeHtml(formatValidationValue(check.expected)) + '</p>' +
      (check.note ? '<p>' + escapeHtml(check.note) + '</p>' : '') +
      '</div>';
  }).join("");
}

function renderMeasurements() {
  const signal = state.record ? activeSignal() : null;
  const fs = state.record?.sampling_rate_hz;
  const a = state.calipers.a;
  const b = state.calipers.b;

  const rows = [
    ["A", signal && a != null ? cursorText(a, signal[a]) : "—"],
    ["B", signal && b != null ? cursorText(b, signal[b]) : "—"],
    ["Δt", fs && a != null && b != null ? roundNumber(durationMs(a,b,fs), 2) + " ms" : "—"],
    ["Signal", signalLabel()]
  ];
  el.measurementGrid.innerHTML = rows.map(([label,value]) =>
    "<div><span>" + escapeHtml(label) + "</span><strong>" + escapeHtml(value) + "</strong></div>"
  ).join("");

  if (state.sourceMode === "ideal") {
    el.baselineOutput.textContent = "0 mV";
    el.baselineInput.value = "0";
  } else if (state.sourceMode === "clean") {
    el.baselineOutput.textContent = formatSigned(roundNumber(state.baseline, 4)) + " mV ref";
    el.baselineInput.value = String(roundNumber(state.baseline, 4));
  } else if (state.baselineStatus === "uncertain") {
    el.baselineOutput.textContent = "uncertain";
    el.baselineInput.value = String(roundNumber(state.baseline, 3));
  } else {
    el.baselineOutput.textContent = formatSigned(state.baseline) + " ADC";
    el.baselineInput.value = String(roundNumber(state.baseline, 3));
  }
}

function cursorText(sample, value) {
  const time = sampleToMs(sample, state.record.sampling_rate_hz);

  if (state.sourceMode === "ideal") {
    const delta = value - IDEAL_ECG_SPEC.baseline_mV;
    return roundNumber(time, 2) + " ms · " + formatSigned(roundNumber(delta, 3)) + " mV";
  }

  if (state.sourceMode === "clean") {
    const delta = value - state.baseline;
    return roundNumber(time, 2) + " ms · " + formatSigned(roundNumber(delta, 3)) + " mV";
  }

  if (state.baselineStatus === "uncertain") {
    return roundNumber(time, 2) + " ms · amplitude withheld";
  }

  const delta = deltaAdc(value, state.baseline);
  return roundNumber(time, 2) + " ms · " + formatSigned(roundNumber(delta, 2)) + " ΔADC";
}

function setBaseline(value, status="selected") {
  if (state.sourceMode !== "real" || !Number.isFinite(Number(value))) return;
  state.baseline = Number(value);
  state.baselineStatus = status;
  persistSession();
  renderMeasurements();
  renderBaselineReality();
  draw();
}

function setBaselineStatus(status) {
  if (state.sourceMode !== "real") return;
  state.baselineStatus = status === "uncertain" ? "uncertain" : "selected";
  persistSession();
  renderMeasurements();
  renderBaselineReality();
  draw();
}

function useVisibleMedianBaseline() {
  if (state.sourceMode !== "real" || !state.record) return;
  const [start,end] = visibleSampleRange();
  setBaseline(median(activeSignal().slice(start,end)), "selected");
}

function renderBaselineReality() {
  if (state.sourceMode === "ideal") {
    el.baselineRealityText.textContent =
      "Known by construction: the synthetic isoelectric baseline is exactly 0 mV.";
    el.baselineConfident.classList.remove("active");
    el.baselineUncertain.classList.remove("active");
    return;
  }

  if (state.sourceMode === "clean") {
    el.baselineConfident.classList.remove("active");
    el.baselineUncertain.classList.remove("active");
    el.baselineRealityText.textContent =
      "Real biological reference: OPL estimates the local isoelectric level from the LUDB cardiologist-delineated PR and TP segments. " +
      "Amplitude is reported in physical mV relative to that reference.";
    return;
  }

  const uncertain = state.baselineStatus === "uncertain";
  el.baselineConfident.classList.toggle("active", !uncertain);
  el.baselineUncertain.classList.toggle("active", uncertain);
  el.baselineRealityText.textContent = uncertain
    ? "Baseline marked uncertain: vertical amplitude is deliberately withheld. Time measurements remain available."
    : "Local baseline accepted for this view: vertical values are reported relative to the selected ADC reference, not as calibrated input mV.";
}

function renderCleanSelection() {
  if (!el.cleanSelectionSummary || !el.cleanBaselineDetails) return;

  if (state.sourceMode !== "clean" || !state.cleanRecord) {
    el.cleanSelectionSummary.innerHTML = "";
    el.cleanBaselineDetails.innerHTML = "";
    return;
  }

  const selection = state.cleanRecord.selection || {};
  const source = selection.metadata || {};
  const selectionItems = [
    ["Eligible records", "23"],
    ["Selected record", selection.record_id || "119"],
    ["Rhythm", source.rhythm || "Sinus rhythm"],
    ["Electrical axis", source.electrical_axis || "Normal"],
    ["Baseline spread", Number.isFinite(Number(selection.baseline_segment_spread_mV))
      ? roundNumber(selection.baseline_segment_spread_mV, 4) + " mV"
      : "—"],
    ["HF noise MAD", Number.isFinite(Number(selection.high_frequency_noise_mad_mV))
      ? roundNumber(selection.high_frequency_noise_mad_mV, 5) + " mV"
      : "—"]
  ];

  el.cleanSelectionSummary.innerHTML = selectionItems.map(([label,value]) =>
    '<div><span>' + escapeHtml(label) + '</span><strong>' + escapeHtml(String(value)) + '</strong></div>'
  ).join("");

  const iso = state.cleanRecord.isoelectric_segments || [];
  const pr = iso.filter(segment => segment.type === "PR").length;
  const tp = iso.filter(segment => segment.type === "TP").length;
  const baselineItems = [
    ["Reference baseline", formatSigned(roundNumber(state.baseline, 4)) + " mV"],
    ["Isoelectric segments", iso.length],
    ["PR segments", pr],
    ["TP segments", tp]
  ];

  el.cleanBaselineDetails.innerHTML = baselineItems.map(([label,value]) =>
    '<div><span>' + escapeHtml(label) + '</span><strong>' + escapeHtml(String(value)) + '</strong></div>'
  ).join("");
}

function renderRrBridge() {
  if (!el.rrBridgeStats) return;

  if (state.sourceMode === "ideal" || !state.record) {
    el.rrBridgeStats.innerHTML = "";
    return;
  }

  const rSamples = (state.record.annotations || [])
    .filter(annotation => annotation.symbol === "N")
    .map(annotation => Number(annotation.sample))
    .filter(Number.isFinite)
    .sort((a,b) => a-b);

  const rr = [];
  for (let i=1; i<rSamples.length; i++) {
    rr.push((rSamples[i]-rSamples[i-1]) / state.record.sampling_rate_hz * 1000);
  }

  const mean = rr.length ? rr.reduce((a,b)=>a+b,0)/rr.length : NaN;
  const approxHr = Number.isFinite(mean) && mean > 0 ? 60000/mean : NaN;
  const markerLabel = state.sourceMode === "clean"
    ? "Manual QRS-peak markers"
    : "Source automated R markers";

  const items = [
    [markerLabel, rSamples.length],
    ["R–R intervals", rr.length],
    ["Mean RR", Number.isFinite(mean) ? roundNumber(mean,1) + " ms" : "—"],
    ["Approx. HR", Number.isFinite(approxHr) ? roundNumber(approxHr,1) + " bpm" : "—"]
  ];

  el.rrBridgeStats.innerHTML = items.map(([label,value]) =>
    '<div><span>' + escapeHtml(label) + '</span><strong>' + escapeHtml(String(value)) + '</strong></div>'
  ).join("");
}

function activeSignal() {
  if (state.sourceMode === "ideal" || state.sourceMode === "clean") {
    return state.record.signals.raw;
  }
  return state.record.signals[state.measurementSignal];
}

function signalLabel() {
  if (state.sourceMode === "ideal") return "Ideal synthetic ECG";
  if (state.sourceMode === "clean") return "LUDB real Lead II · physical mV";
  return state.measurementSignal === "raw" ? "Raw ECG" : "Source filtered ECG";
}

function signalIndex() {
  return state.measurementSignal === "raw" ? 0 : 1;
}

function visibleSampleRange() {
  const fs = state.record.sampling_rate_hz;
  const start = Math.floor(state.windowStartSeconds * fs);
  const end = Math.min(state.record.signals.raw.length, Math.ceil((state.windowStartSeconds + state.windowSeconds) * fs));
  return [start, Math.max(start + 1,end)];
}

function clampWindowStart() {
  if (!state.record) return;
  const max = Math.max(0, state.record.duration_seconds - state.windowSeconds);
  state.windowStartSeconds = Math.min(max, Math.max(0, state.windowStartSeconds));
}

function syncWindowControls() {
  if (!state.record) return;
  const max = Math.max(0, state.record.duration_seconds - state.windowSeconds);
  el.windowStart.max = String(max);
  el.windowStart.step = String(1 / state.record.sampling_rate_hz);
  el.windowStart.value = String(Math.min(max,state.windowStartSeconds));
  el.windowStartLabel.textContent = roundNumber(state.windowStartSeconds,3) + " s";
  el.windowLength.value = String(state.windowSeconds);
}

function updateGridLabel() {
  if (state.sourceMode === "ideal") {
    el.gridScale.textContent = "Small box: 40 ms × 0.1 mV (synthetic)";
  } else if (state.sourceMode === "clean") {
    el.gridScale.textContent = "Small box: 40 ms × 0.1 mV (real source units)";
  } else {
    el.gridScale.textContent = "Small box: 40 ms × " + state.verticalGridAdc + " ΔADC";
  }
}

function resizeCanvas() {
  const rect = el.ecgCanvas.getBoundingClientRect();
  const dpr = Math.max(1, window.devicePixelRatio || 1);
  const width = Math.max(300, Math.round(rect.width*dpr));
  const height = Math.max(250, Math.round(rect.height*dpr));
  if (el.ecgCanvas.width !== width || el.ecgCanvas.height !== height) {
    el.ecgCanvas.width = width;
    el.ecgCanvas.height = height;
  }
}

function draw() {
  resizeCanvas();
  const w = el.ecgCanvas.width;
  const h = el.ecgCanvas.height;
  ctx.clearRect(0,0,w,h);
  ctx.fillStyle = cssColor("--plot-bg");
  ctx.fillRect(0,0,w,h);

  if (!state.record) {
    ctx.fillStyle = cssColor("--text-muted");
    ctx.font = Math.round(16*(window.devicePixelRatio||1)) + "px sans-serif";
    ctx.fillText("Reference record not loaded",24,40);
    return;
  }

  const [start,end] = visibleSampleRange();
  const raw = state.record.signals.raw.slice(start,end);
  const filtered = state.record.signals.filtered.slice(start,end);

  let displayed;
  if (state.sourceMode === "ideal" || state.sourceMode === "clean") {
    displayed = raw;
  } else {
    displayed = state.mode === "raw" ? raw : state.mode === "filtered" ? filtered : raw.concat(filtered);
  }

  let yMin;
  let yMax;
  if (state.sourceMode === "ideal") {
    yMin = -0.4;
    yMax = 1.2;
  } else if (state.sourceMode === "clean") {
    const min = Math.min(...displayed,state.baseline);
    const max = Math.max(...displayed,state.baseline);
    const span = Math.max(0.2,max-min);
    yMin = Math.floor((min-span*.10)/0.1)*0.1;
    yMax = Math.ceil((max+span*.10)/0.1)*0.1;
  } else {
    const min = Math.min(...displayed,state.baseline);
    const max = Math.max(...displayed,state.baseline);
    const span = Math.max(1,max-min);
    yMin = min - span*.12;
    yMax = max + span*.12;
  }

  const dpr = Math.max(1,window.devicePixelRatio||1);
  drawGrid(start,end,yMin,yMax,dpr);

  const yBaseline = yFor(state.baseline,yMin,yMax,h);
  ctx.strokeStyle = cssColor("--silver");
  ctx.globalAlpha = .75;
  ctx.setLineDash([8*dpr,6*dpr]);
  ctx.lineWidth = 1*dpr;
  ctx.beginPath();ctx.moveTo(0,yBaseline);ctx.lineTo(w,yBaseline);ctx.stroke();
  ctx.setLineDash([]);
  ctx.globalAlpha = 1;

  if (state.sourceMode === "ideal") {
    drawSignal(state.record.signals.raw,start,end,yMin,yMax,cssColor("--cyan"),1.7*dpr);
  } else if (state.sourceMode === "clean") {
    drawSignal(state.record.signals.raw,start,end,yMin,yMax,cssColor("--emerald"),1.55*dpr);
  } else {
    if (state.mode === "raw" || state.mode === "overlay") {
      drawSignal(state.record.signals.raw,start,end,yMin,yMax,cssColor("--emerald"),1.35*dpr);
    }
    if (state.mode === "filtered" || state.mode === "overlay") {
      drawSignal(state.record.signals.filtered,start,end,yMin,yMax,cssColor("--gold"),1.25*dpr);
    }
  }

  if (state.showAnnotations) {
    if (state.sourceMode === "ideal") {
      drawIdealNotation(start,end,yMin,yMax,dpr);
    } else if (state.sourceMode === "clean") {
      drawCleanAnnotations(start,end,yMin,yMax,dpr);
    } else {
      drawRealAnnotations(start,end,dpr);
    }
  }

  drawCaliper(state.calipers.a,"A",cssColor("--cyan"),start,end,dpr);
  drawCaliper(state.calipers.b,"B",cssColor("--violet"),start,end,dpr);
}

function drawGrid(start,end,yMin,yMax,dpr) {
  const w=el.ecgCanvas.width,h=el.ecgCanvas.height,fs=state.record.sampling_rate_hz;
  const startTime=start/fs,endTime=end/fs;

  const first=Math.ceil(startTime/.04)*.04;
  for(let t=first;t<=endTime+1e-9;t+=.04){
    const major=Math.abs((t/.2)-Math.round(t/.2))<1e-7;
    ctx.strokeStyle=major?cssColor("--grid-major"):cssColor("--grid-minor");
    ctx.lineWidth=(major?1:.55)*dpr;
    const x=(t-startTime)/(endTime-startTime)*w;
    ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,h);ctx.stroke();
  }

  const step=(state.sourceMode==="ideal" || state.sourceMode==="clean")
    ? 0.1
    : state.verticalGridAdc;
  const lower=Math.floor((yMin-state.baseline)/step);
  const upper=Math.ceil((yMax-state.baseline)/step);

  for(let n=lower;n<=upper;n++){
    if(n===0)continue;
    const value=state.baseline+n*step;
    const y=yFor(value,yMin,yMax,h);
    const major=Math.abs(n)%5===0;
    ctx.strokeStyle=major?cssColor("--grid-major"):cssColor("--grid-minor");
    ctx.lineWidth=(major?1:.55)*dpr;
    ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(w,y);ctx.stroke();
  }
}

function drawSignal(signal,start,end,yMin,yMax,color,lineWidth) {
  const w=el.ecgCanvas.width,h=el.ecgCanvas.height,n=end-start;
  ctx.strokeStyle=color;ctx.lineWidth=lineWidth;ctx.beginPath();
  for(let i=0;i<n;i++){
    const x=n===1?0:i/(n-1)*w;
    const y=yFor(signal[start+i],yMin,yMax,h);
    if(i===0)ctx.moveTo(x,y);else ctx.lineTo(x,y);
  }
  ctx.stroke();
}

function drawIdealNotation(start,end,yMin,yMax,dpr) {
  const beats=(state.record.beats||[]).filter(b=>b.landmarks.r>=start&&b.landmarks.r<end);
  if(!beats.length)return;
  const center=(start+end)/2;
  const beat=beats.slice().sort((a,b)=>Math.abs(a.landmarks.r-center)-Math.abs(b.landmarks.r-center))[0];
  const lm=beat.landmarks;
  const labels=[
    ["P",lm.p_peak],["Q",lm.q],["R",lm.r],["S",lm.s],["T",lm.t_peak]
  ];
  const signal=state.record.signals.raw;
  ctx.font="bold "+12*dpr+"px sans-serif";
  ctx.textAlign="center";
  for(const [label,sample] of labels){
    if(sample<start||sample>=end)continue;
    const x=xFor(sample,start,end);
    const y=yFor(signal[sample],yMin,yMax,el.ecgCanvas.height);
    ctx.fillStyle=cssColor("--gold");
    const offset=label==="Q"||label==="S" ? 18*dpr : -12*dpr;
    ctx.fillText(label,x,y+offset);
  }
  ctx.textAlign="left";

  drawBracket(lm.p_onset,lm.qrs_onset,"PR",el.ecgCanvas.height-68*dpr,start,end,dpr);
  drawBracket(lm.qrs_onset,lm.qrs_end,"QRS",el.ecgCanvas.height-46*dpr,start,end,dpr);
  drawBracket(lm.qrs_onset,lm.t_end,"QT",el.ecgCanvas.height-24*dpr,start,end,dpr);
}

function drawBracket(sampleA,sampleB,label,y,start,end,dpr){
  if(sampleB<start||sampleA>=end)return;
  const a=Math.max(sampleA,start),b=Math.min(sampleB,end-1);
  const x1=xFor(a,start,end),x2=xFor(b,start,end);
  ctx.strokeStyle=cssColor("--magenta");ctx.fillStyle=cssColor("--magenta");
  ctx.lineWidth=1*dpr;
  ctx.beginPath();ctx.moveTo(x1,y-4*dpr);ctx.lineTo(x1,y+4*dpr);ctx.moveTo(x1,y);ctx.lineTo(x2,y);ctx.moveTo(x2,y-4*dpr);ctx.lineTo(x2,y+4*dpr);ctx.stroke();
  ctx.font=10*dpr+"px sans-serif";ctx.textAlign="center";ctx.fillText(label,(x1+x2)/2,y-4*dpr);ctx.textAlign="left";
}


function drawCleanAnnotations(start,end,yMin,yMax,dpr) {
  const annotations=(state.record.annotations||[])
    .filter(annotation => annotation.sample>=start && annotation.sample<end);
  const signal=state.record.signals.raw;
  const h=el.ecgCanvas.height;

  ctx.font="bold "+10*dpr+"px sans-serif";
  ctx.textAlign="center";

  for(const annotation of annotations){
    if(!["p","N","t"].includes(annotation.symbol))continue;
    const x=xFor(annotation.sample,start,end);
    const y=yFor(signal[annotation.sample],yMin,yMax,h);
    const label=annotation.symbol==="p" ? "P" : annotation.symbol==="N" ? "QRS" : "T";
    ctx.fillStyle=cssColor("--gold");
    ctx.fillText(label,x,y-10*dpr);
  }
  ctx.textAlign="left";

  const boundaries=annotations.filter(annotation =>
    (annotation.symbol==="(" || annotation.symbol===")") &&
    ["P","QRS","T"].includes(annotation.wave)
  );
  const rows={P:h-68*dpr,QRS:h-46*dpr,T:h-24*dpr};

  for(let i=0;i<boundaries.length;i++){
    const onset=boundaries[i];
    if(onset.symbol!=="(")continue;
    const endBoundary=boundaries.slice(i+1).find(annotation =>
      annotation.symbol===")" && annotation.wave===onset.wave
    );
    if(!endBoundary)continue;
    drawBracket(onset.sample,endBoundary.sample,onset.wave,rows[onset.wave],start,end,dpr);
  }
}

function drawRealAnnotations(start,end,dpr){
  const anns=state.record.annotations||[];
  const w=el.ecgCanvas.width;
  ctx.font=10*dpr+"px sans-serif";
  for(const ann of anns){
    if(ann.sample<start||ann.sample>=end)continue;
    const x=(ann.sample-start)/(end-start-1)*w;
    const label=ann.symbol==="N"?"R":ann.symbol==="t"?"T":ann.symbol||"•";
    ctx.strokeStyle=cssColor("--magenta");ctx.fillStyle=cssColor("--magenta");
    ctx.globalAlpha=.72;ctx.lineWidth=.8*dpr;
    ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,15*dpr);ctx.stroke();
    ctx.fillText(label,x+2*dpr,13*dpr);
    ctx.globalAlpha=1;
  }
}

function drawCaliper(sample,label,color,start,end,dpr){
  if(sample==null||sample<start||sample>=end)return;
  const w=el.ecgCanvas.width,h=el.ecgCanvas.height;
  const x=(sample-start)/(end-start-1)*w;
  ctx.strokeStyle=color;ctx.lineWidth=1.5*dpr;
  ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,h);ctx.stroke();
  ctx.fillStyle=color;ctx.font="bold "+12*dpr+"px sans-serif";ctx.fillText(label,x+4*dpr,h-8*dpr);
}

function xFor(sample,start,end){
  return (sample-start)/(end-start-1)*el.ecgCanvas.width;
}

function yFor(value,min,max,height){
  return height-(value-min)/(max-min)*height;
}

function restoreSession(mode=state.sourceMode) {
  try { return JSON.parse(localStorage.getItem(sessionKey(mode))) || null; } catch { return null; }
}

function persistSession() {
  try {
    localStorage.setItem(sessionKey(),JSON.stringify({
      baseline_adc:state.baseline,
      baseline_status:state.baselineStatus,
      calipers:state.calipers,
      source_mode:state.sourceMode
    }));
  } catch {}
}

function sessionKey(mode=state.sourceMode){
  return SESSION_KEY_BASE + mode;
}

function restoreQuiz(){
  try{
    const saved=JSON.parse(localStorage.getItem(QUIZ_KEY));
    if(saved&&typeof saved==="object"){
      state.quizIndex=Number.isInteger(saved.index)?Math.max(0,Math.min(saved.index,ECG_TEACHING_QUESTIONS.length-1)):0;
      state.quizResponses=saved.responses&&typeof saved.responses==="object"?saved.responses:{};
    }
  }catch{}
}

function persistQuiz(){
  try{localStorage.setItem(QUIZ_KEY,JSON.stringify({index:state.quizIndex,responses:state.quizResponses}))}catch{}
}

function renderQuiz(){
  const question=ECG_TEACHING_QUESTIONS[state.quizIndex];
  if(!question)return;
  const score=scoreQuiz(state.quizResponses);
  el.quizScore.textContent=String(score.correct);
  el.quizTotal.textContent=String(score.total);
  el.quizQuestion.textContent=question.prompt;
  el.quizOptions.innerHTML="";
  const existing=state.quizResponses[question.id];

  question.options.forEach((option,index)=>{
    const button=document.createElement("button");
    button.type="button";
    button.className="quiz-option";
    button.textContent=option;
    if(Number.isInteger(existing)){
      button.disabled=true;
      if(index===question.answer)button.classList.add("correct");
      else if(index===existing)button.classList.add("incorrect");
    }else{
      button.addEventListener("click",()=>answerQuiz(question,index));
    }
    el.quizOptions.appendChild(button);
  });

  if(Number.isInteger(existing)){
    const result=evaluateAnswer(question,existing);
    el.quizFeedback.textContent=(result.correct?"Correct. ":"Not quite. ")+result.explanation;
  }else{
    el.quizFeedback.textContent="Choose one answer.";
  }
  el.quizNext.textContent=state.quizIndex===ECG_TEACHING_QUESTIONS.length-1?"Back to first":"Next question";
}

function answerQuiz(question,index){
  state.quizResponses[question.id]=index;
  persistQuiz();
  renderQuiz();
}

function showStatus(message,isError=false){
  el.keepStatus.textContent=message;
  el.keepStatus.style.color=isError?cssColor("--fail"):cssColor("--emerald");
}

function updateLogicPath(){
  const steps=[...document.querySelectorAll(".logic-step")];
  const activeIndex = state.sourceMode === "ideal" ? 0 : state.sourceMode === "clean" ? 1 : 2;
  steps.forEach((node,index)=>{
    node.classList.toggle("active", index===activeIndex);
  });
}

function scrollToLab(){
  document.querySelector(".workspace")?.scrollIntoView({behavior:"smooth", block:"start"});
}

function buildLabel(){
  return state.buildInfo?.git_sha ? state.buildInfo.git_sha.slice(0,12) : "development source";
}

function formatValidationValue(value){
  if(Array.isArray(value))return value.map(v=>v==null?"—":String(v)).join(", ");
  if(value==null)return "—";
  if(typeof value==="number"&&Number.isFinite(value))return String(roundNumber(value,6));
  return String(value);
}

function cssColor(name){
  return getComputedStyle(document.body).getPropertyValue(name).trim() || "#FFFFFF";
}

function requireOk(response){if(!response.ok)throw new Error("HTTP "+response.status);return response}
function integerOrNull(value){return Number.isInteger(value)?value:null}
function roundNumber(value,places=0){const p=10**places;return Math.round(Number(value)*p)/p}
function formatSigned(value){const v=Number(value);return(v>0?"+":"")+String(v)}
function escapeHtml(value){return String(value).replace(/[&<>"']/g,ch=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[ch]))}
