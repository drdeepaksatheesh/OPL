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
import {
  generateIdealEcg,
  IDEAL_ECG_SPEC,
  nearestIdealLandmark,
  nearestIdealIntervalEndpoint,
  interpretIdealCalipers
} from "./ideal-ecg.mjs";
import {
  interpretLudbCalipers,
  summarizeLudbReferenceIntervals,
  makeLudbReferenceMeasurementReport
} from "./ludb-calipers.mjs";
import {ECG_TEACHING_QUESTIONS, evaluateAnswer, scoreQuiz} from "./teaching.mjs";
import {
  ECG_PAPER_TIME_SMALL_BOX_S,
  computeSquarePaperRange
} from "./ecg-paper.mjs";

const IMPERFECT_RECORD_URL = "./data/Person_01_rec_1.json";
const CLEAN_RECORD_URL = "./data/LUDB_clean_LeadII.json";
const PRACTICE_MANIFEST_URL = "./practice/practice_manifest.json";
const REAL_RECORD_ID = "ECG-ID/Person_01/rec_1";
const REAL_MV_RECORD_ID = "ECG-ID/Person_01/rec_1-derived-mV";
const CLEAN_RECORD_ID_PREFIX = "LUDB/";
const SESSION_KEY_BASE = "opl:ecg-reference:session:";
const MODE_KEY = "opl:ecg-reference:mode";
const THEME_KEY = "opl:theme";
const QUIZ_KEY = "opl:ecg-reference:quiz";

const state = {
  record: null,
  realRecord: null,
  realMvRecord: null,
  cleanRecord: null,
  idealRecord: generateIdealEcg(),
  practiceManifest: null,
  practiceRecords: new Map(),
  practiceRecord: null,
  practiceRecordId: null,
  practiceReveal: false,
  practiceTask: "pr_interval",
  storyReturnMode: "adc",
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
  verticalGridAdc: 20,
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
  "quickMode","advancedMode","themeToggle","stageSelect","dockDelta",
  "nextToClean","nextToImperfect","backToClean","rulerSmallBox","rulerLargeBox",
  "quizScore","quizTotal","quizQuestion","quizOptions","quizFeedback","quizNext","quizReset",
  "validationPassed","validationTotal","validationChecks","downloadValidation",
  "rrBridgeStats","cleanBaselineDetails","cleanSelectionSummary","measurementAssist",
  "ludbMeasurementTable","downloadLudbMeasurements","nextToAdc","backToReal","baselineInputLabel",
  "practiceJump","practiceRecordList","practiceTask","practiceReveal","practiceNewAttempt","practiceStatus","practiceReview","exitPractice"
].map(id => [id, document.getElementById(id)]));

const ctx = el.ecgCanvas.getContext("2d");

const caliperPointer = {
  active: false,
  pointerId: null,
  mode: "range",
  endpoint: null,
  startSample: null,
  startClientX: 0,
  moved: false,
  original: {a:null,b:null}
};
const CALIPER_DRAG_THRESHOLD_PX = 5;
const CALIPER_HIT_RADIUS_PX = 12;

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
  state.realMvRecord = state.realRecord ? convertRecordToPhysicalMv(state.realRecord) : null;

  try {
    state.practiceManifest = await fetch(PRACTICE_MANIFEST_URL, {cache:"no-cache"}).then(requireOk).then(r => r.json());
    const loaded = await Promise.all((state.practiceManifest.records || []).map(async item => {
      const record = await fetch("./practice/" + item.file, {cache:"no-cache"}).then(requireOk).then(r => r.json());
      validateReferenceRecord(record);
      return [item.id, record];
    }));
    state.practiceRecords = new Map(loaded);
    const first = state.practiceManifest.records?.[0];
    if (first) {
      state.practiceRecordId = first.id;
      state.practiceRecord = state.practiceRecords.get(first.id) || null;
    }
  } catch {
    state.practiceManifest = null;
    state.practiceRecords = new Map();
    state.practiceRecord = null;
  }

  if (el.stageSelect) {
    const cleanOption = el.stageSelect.querySelector('option[value="clean"]');
    const realOption = el.stageSelect.querySelector('option[value="real"]');
    const adcOption = el.stageSelect.querySelector('option[value="adc"]');
    const practiceOption = el.stageSelect.querySelector('option[value="practice"]');
    if (cleanOption) cleanOption.disabled = !state.cleanRecord;
    if (realOption) realOption.disabled = !state.realMvRecord;
    if (adcOption) adcOption.disabled = !state.realRecord;
    if (practiceOption) practiceOption.disabled = !state.practiceRecord;
  }
  if (el.nextToClean) el.nextToClean.disabled = !state.cleanRecord;
  if (el.nextToImperfect) el.nextToImperfect.disabled = !state.realMvRecord;
  if (el.nextToAdc) el.nextToAdc.disabled = !state.realRecord;
  if (el.backToClean) el.backToClean.disabled = !state.cleanRecord;
  if (el.backToReal) el.backToReal.disabled = !state.realMvRecord;
  if (el.practiceJump) el.practiceJump.disabled = !state.practiceRecord;
  renderPracticePicker();
  el.onlineState.textContent = state.cleanRecord && state.realRecord
    ? (navigator.onLine ? "Reference data ready" : "Offline reference data")
    : "Some reference data unavailable";

  switchSource("ideal", {restore:true});
}

function bindEvents() {
  el.quickMode.addEventListener("click", () => setInterfaceMode("teaching"));
  el.advancedMode.addEventListener("click", () => setInterfaceMode("advanced"));
  el.themeToggle.addEventListener("click", () => setTheme(state.theme === "dark" ? "light" : "dark"));

  el.stageSelect?.addEventListener("change", () => {
    const next = el.stageSelect.value;
    if (next === "clean" && !state.cleanRecord) {
      showStatus("The clean LUDB reference is unavailable in this build.", true);
      el.stageSelect.value = state.sourceMode;
      return;
    }
    if (next === "real" && !state.realMvRecord) {
      showStatus("The imperfect ECG mV reference is unavailable in this build/offline cache.", true);
      el.stageSelect.value = state.sourceMode;
      return;
    }
    if (next === "adc" && !state.realRecord) {
      showStatus("The ECG-ID machine-view reference is unavailable in this build/offline cache.", true);
      el.stageSelect.value = state.sourceMode;
      return;
    }
    if (next === "practice" && !state.practiceRecord) {
      showStatus("The bundled LUDB practice bank is unavailable in this build.", true);
      el.stageSelect.value = state.sourceMode;
      return;
    }
    if (next === "practice") state.storyReturnMode = state.sourceMode === "practice" ? state.storyReturnMode : state.sourceMode;
    switchSource(next, {restore:true});
  });

  el.nextToClean?.addEventListener("click", () => {
    if (!state.cleanRecord) {
      showStatus("The clean LUDB reference is unavailable in this build.", true);
      return;
    }
    switchSource("clean", {restore:true});
    scrollToLab();
  });
  el.nextToImperfect?.addEventListener("click", () => {
    if (!state.realMvRecord) {
      showStatus("The imperfect ECG mV reference is unavailable in this build.", true);
      return;
    }
    switchSource("real", {restore:true});
    scrollToLab();
  });
  el.nextToAdc?.addEventListener("click", () => {
    if (!state.realRecord) {
      showStatus("The ECG-ID machine-view reference is unavailable in this build.", true);
      return;
    }
    switchSource("adc", {restore:true});
    scrollToLab();
  });
  el.backToClean?.addEventListener("click", () => {
    switchSource("clean", {restore:true});
    scrollToLab();
  });
  el.backToReal?.addEventListener("click", () => {
    switchSource("real", {restore:true});
    scrollToLab();
  });
  el.practiceJump?.addEventListener("click", () => {
    if (!state.practiceRecord) return;
    if (state.sourceMode !== "practice") state.storyReturnMode = state.sourceMode;
    switchSource("practice", {restore:true});
    scrollToLab();
  });
  el.exitPractice?.addEventListener("click", () => {
    switchSource(state.storyReturnMode || "adc", {restore:true});
    scrollToLab();
  });
  el.practiceTask?.addEventListener("change", () => {
    state.practiceTask = el.practiceTask.value;
    state.practiceReveal = false;
    renderPracticeReview();
    renderMeasurementAssist();
    draw();
  });
  el.practiceReveal?.addEventListener("click", () => {
    state.practiceReveal = !state.practiceReveal;
    state.showAnnotations = state.practiceReveal;
    syncControlsFromState();
    renderProvenance();
    renderPracticeReview();
    renderMeasurementAssist();
    renderBaselineReality();
    draw();
  });
  el.practiceNewAttempt?.addEventListener("click", () => resetPracticeAttempt());

  document.querySelectorAll("[data-drawer-target]").forEach(button => {
    button.addEventListener("click", () => {
      const drawer = document.getElementById(button.dataset.drawerTarget);
      if (!drawer) return;
      drawer.open = true;
      drawer.scrollIntoView({behavior:"smooth", block:"start"});
    });
  });

  document.querySelectorAll("[data-quick-waveform]").forEach(button => {
    button.addEventListener("click", () => {
      if (!(state.sourceMode === "real" || state.sourceMode === "adc" || state.sourceMode === "practice")) return;
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
    updateRuler();
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
    if (state.sourceMode === "real" || state.sourceMode === "adc" || state.sourceMode === "practice") setBaseline(Number(el.baselineInput.value), "selected");
  });
  el.baselineZero.addEventListener("click", () => {
    if (!(state.sourceMode === "real" || state.sourceMode === "adc" || state.sourceMode === "practice")) return;
    const zero = Number(state.record?.adc?.zero?.[signalIndex()] ?? 0);
    const gain = derivedCountsPerMv(state.record) || 1;
    setBaseline(state.sourceMode === "real" ? zero / gain : zero, "selected");
  });
  el.baselineMedian.addEventListener("click", useVisibleMedianBaseline);
  el.baselineFromA.addEventListener("click", () => {
    if (!((state.sourceMode === "real" || state.sourceMode === "adc" || state.sourceMode === "practice") && state.calipers.a != null)) return;
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

  el.ecgCanvas.addEventListener("pointerdown", event => {
    if (!state.record) return;
    event.preventDefault();

    const sample = sampleFromPointerEvent(event);
    const endpoint = caliperEndpointNearPointer(event);

    caliperPointer.active = true;
    caliperPointer.pointerId = event.pointerId;
    caliperPointer.mode = endpoint ? "endpoint" : "range";
    caliperPointer.endpoint = endpoint;
    caliperPointer.startSample = sample;
    caliperPointer.startClientX = event.clientX;
    caliperPointer.moved = false;
    caliperPointer.original = {...state.calipers};

    try { el.ecgCanvas.setPointerCapture(event.pointerId); } catch {}

    if (endpoint) {
      state.calipers[endpoint] = sample;
      renderMeasurements();
      draw();
    }
  });

  el.ecgCanvas.addEventListener("pointermove", event => {
    if (!state.record) return;

    if (!caliperPointer.active || event.pointerId !== caliperPointer.pointerId) {
      updateCaliperHoverCursor(event);
      return;
    }

    event.preventDefault();
    const sample = sampleFromPointerEvent(event);
    if (Math.abs(event.clientX - caliperPointer.startClientX) >= CALIPER_DRAG_THRESHOLD_PX) {
      caliperPointer.moved = true;
    }

    if (caliperPointer.mode === "endpoint") {
      state.calipers[caliperPointer.endpoint] = sample;
    } else if (caliperPointer.moved) {
      const a = Math.min(caliperPointer.startSample, sample);
      const b = Math.max(caliperPointer.startSample, sample);
      state.calipers = {a,b};
    }

    renderMeasurements();
    draw();
  });

  el.ecgCanvas.addEventListener("pointerup", event => finishCaliperPointer(event, false));
  el.ecgCanvas.addEventListener("pointercancel", event => finishCaliperPointer(event, true));
  el.ecgCanvas.addEventListener("pointerleave", event => {
    if (!caliperPointer.active) updateCaliperHoverCursor(event, true);
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
      : state.sourceMode === "practice"
        ? "Saved this LUDB practice ECG locally in this browser."
        : "Saved the ECG-ID reference locally in this browser.");
  });

  el.downloadLudbMeasurements?.addEventListener("click", () => {
    if (!state.cleanRecord) return;
    const report = makeLudbReferenceMeasurementReport(state.cleanRecord);
    report.opl = {
      version: window.OPL_CONFIG?.version || "unknown",
      commit: state.buildInfo?.git_sha || "unknown"
    };
    downloadJson("OPL_LUDB_clean_LeadII_expert-reference-measurements.json", report);
    showStatus("Downloaded LUDB cardiologist-derived interval measurements for this exact reference record.");
  });

  el.downloadValidation.addEventListener("click", () => {
    if (!((state.sourceMode === "real" || state.sourceMode === "adc") && state.realRecord)) return;
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
    pkg.session.practice_task = state.practiceTask;
    pkg.session.practice_record_id = state.practiceRecordId;
    const name = state.sourceMode === "ideal"
      ? "OPL_Ideal_ECG_teaching-package.json"
      : state.sourceMode === "clean"
        ? "OPL_LUDB_clean_LeadII_reference-package.json"
        : state.sourceMode === "real"
          ? "OPL_ECG-ID_Person_01_rec_1_physical_mV_reference-package.json"
          : state.sourceMode === "practice"
            ? "OPL_" + (practiceManifestItem()?.label || "Practice_ECG").replaceAll(" ","_") + "_attempt.json"
            : "OPL_ECG-ID_Person_01_rec_1_ADC_reference-package.json";
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
      const isPractice = imported.session?.source_mode === "practice";
      const isClean = importedId.startsWith(CLEAN_RECORD_ID_PREFIX);
      if (isIdeal) {
        state.idealRecord = imported.record;
        switchSource("ideal", {session:imported.session});
      } else if (isPractice) {
        state.practiceRecord = imported.record;
        state.practiceRecordId = imported.session?.practice_record_id || importedId;
        state.practiceRecords.set(state.practiceRecordId, imported.record);
        state.practiceTask = imported.session?.practice_task || "free";
        switchSource("practice", {session:imported.session});
      } else if (isClean) {
        state.cleanRecord = imported.record;
        switchSource("clean", {session:imported.session});
      } else if (importedId === REAL_MV_RECORD_ID) {
        state.realMvRecord = imported.record;
        switchSource("real", {session:imported.session});
      } else {
        state.realRecord = imported.record;
        state.realMvRecord = convertRecordToPhysicalMv(imported.record);
        switchSource(imported.session?.source_mode === "adc" ? "adc" : "real", {session:imported.session});
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

function sampleFromPointerEvent(event) {
  const rect = el.ecgCanvas.getBoundingClientRect();
  const [start,end] = visibleSampleRange();
  const x = Math.max(0, Math.min(rect.width, event.clientX - rect.left));
  const fraction = rect.width > 0 ? x / rect.width : 0;
  return Math.min(
    end - 1,
    Math.max(start, Math.round(start + fraction * (end - start - 1)))
  );
}

function caliperEndpointNearPointer(event) {
  // Do not let a lone A caliper steal the second tap on short intervals.
  // Endpoint dragging becomes available once a complete A/B pair exists.
  if (!Number.isInteger(state.calipers.a) || !Number.isInteger(state.calipers.b)) {
    return null;
  }

  const rect = el.ecgCanvas.getBoundingClientRect();
  const [start,end] = visibleSampleRange();
  const pointerX = event.clientX - rect.left;
  let best = null;

  for (const endpoint of ["a","b"]) {
    const sample = state.calipers[endpoint];
    if (!Number.isInteger(sample) || sample < start || sample >= end) continue;
    const x = (sample - start) / Math.max(1,end - start - 1) * rect.width;
    const distance = Math.abs(pointerX - x);
    if (distance <= CALIPER_HIT_RADIUS_PX && (!best || distance < best.distance)) {
      best = {endpoint,distance};
    }
  }
  return best?.endpoint || null;
}

function normalizeCalipers() {
  const {a,b} = state.calipers;
  if (Number.isInteger(a) && Number.isInteger(b) && a > b) {
    state.calipers = {a:b,b:a};
  }
}

function finishCaliperPointer(event, cancelled) {
  if (!caliperPointer.active || event.pointerId !== caliperPointer.pointerId) return;
  event.preventDefault();

  if (cancelled) {
    state.calipers = {...caliperPointer.original};
  } else {
    const sample = sampleFromPointerEvent(event);

    if (caliperPointer.mode === "endpoint") {
      state.calipers[caliperPointer.endpoint] = sample;
      normalizeCalipers();
      state.nextCaliper = "a";
    } else if (caliperPointer.moved) {
      state.calipers = {
        a: Math.min(caliperPointer.startSample, sample),
        b: Math.max(caliperPointer.startSample, sample)
      };
      state.nextCaliper = "a";
    } else {
      const endpoint = state.nextCaliper;
      state.calipers[endpoint] = sample;
      if (endpoint === "a") {
        state.nextCaliper = "b";
      } else {
        normalizeCalipers();
        state.nextCaliper = "a";
      }
    }
  }

  try { el.ecgCanvas.releasePointerCapture(event.pointerId); } catch {}
  caliperPointer.active = false;
  caliperPointer.pointerId = null;
  caliperPointer.endpoint = null;
  caliperPointer.startSample = null;
  caliperPointer.moved = false;

  persistSession();
  renderMeasurements();
  draw();
  updateCaliperHoverCursor(event);
}

function updateCaliperHoverCursor(event, leaving=false) {
  if (leaving) {
    el.ecgCanvas.style.cursor = "crosshair";
    return;
  }
  el.ecgCanvas.style.cursor = caliperEndpointNearPointer(event) ? "ew-resize" : "crosshair";
}

function switchSource(mode, {restore=false, session=null} = {}) {
  const next = mode === "clean" ? "clean" : mode === "real" ? "real" : mode === "adc" ? "adc" : mode === "practice" ? "practice" : "ideal";
  const record = next === "clean"
    ? state.cleanRecord
    : next === "real"
      ? state.realMvRecord
      : next === "adc"
        ? state.realRecord
        : next === "practice"
          ? state.practiceRecord
          : state.idealRecord;
  if (!record) return;

  validateReferenceRecord(record);
  state.sourceMode = next;
  state.record = record;
  document.body.classList.toggle("source-ideal", next === "ideal");
  document.body.classList.toggle("source-clean", next === "clean");
  document.body.classList.toggle("source-real", next === "real");
  document.body.classList.toggle("source-machine", next === "adc");
  document.body.classList.toggle("source-practice", next === "practice");
  if (el.stageSelect) el.stageSelect.value = next;

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
    state.verticalGridAdc = 20;
  } else if (next === "clean") {
    state.baseline = Number(restored?.baseline_value ?? record.recommended_baseline_mV ?? 0);
    state.baselineStatus = "reference";
    state.mode = "raw";
    state.measurementSignal = "raw";
    state.windowSeconds = 2;
    state.windowStartSeconds = 0;
    state.showAnnotations = true;
    state.verticalGridAdc = 20;
  } else if (next === "real") {
    state.baseline = Number(restored?.baseline_value ?? record.recommended_baseline_mV ?? 0);
    state.baselineStatus = restored?.baseline_status === "uncertain" ? "uncertain" : "selected";
    state.mode = "overlay";
    state.measurementSignal = restored?.measurement_signal || "raw";
    state.windowSeconds = 2;
    state.windowStartSeconds = Number(restored?.window_start_seconds ?? 0);
    state.showAnnotations = true;
    state.verticalGridAdc = 20;
  } else if (next === "adc") {
    state.baseline = Number(restored?.baseline_value ?? record.adc?.zero?.[0] ?? 0);
    state.baselineStatus = restored?.baseline_status === "uncertain" ? "uncertain" : "selected";
    state.mode = restored?.display_mode || "overlay";
    state.measurementSignal = restored?.measurement_signal || "raw";
    state.windowSeconds = 2;
    state.windowStartSeconds = Number(restored?.window_start_seconds ?? 0);
    state.showAnnotations = true;
    state.verticalGridAdc = Number(restored?.vertical_grid_adc ?? 20);
  } else {
    state.baseline = Number(restored?.baseline_value ?? 0);
    state.baselineStatus = ["selected","uncertain"].includes(restored?.baseline_status) ? restored.baseline_status : "unselected";
    state.mode = "raw";
    state.measurementSignal = "raw";
    state.windowSeconds = Number(restored?.window_seconds ?? 2);
    state.windowStartSeconds = Number(restored?.window_start_seconds ?? 0);
    state.showAnnotations = false;
    state.practiceReveal = false;
    state.practiceTask = restored?.practice_task || state.practiceTask || "pr_interval";
    state.verticalGridAdc = 20;
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
  renderLudbReferenceTable();
  renderRrBridge();
  renderValidation();
  renderPracticePicker();
  renderPracticeReview();
  syncQuickWaveformButtons();
  updateGridLabel();
  updateRuler();
  updateLogicPath();
  draw();
}

function syncControlsFromState() {
  el.waveformMode.value = state.mode;
  el.measurementSignal.value = state.measurementSignal;
  el.verticalGrid.value = String(state.verticalGridAdc);
  el.windowLength.value = String(state.windowSeconds);
  el.showAnnotations.checked = state.showAnnotations;
  el.showAnnotations.disabled = state.sourceMode === "practice" && !state.practiceReveal;
  el.baselineInput.value = String(roundNumber(state.baseline, 4));
  el.saveOffline.disabled = state.sourceMode === "ideal";
  el.downloadValidation.disabled = !(state.sourceMode === "real" || state.sourceMode === "adc");
  if (el.practiceTask) el.practiceTask.value = state.practiceTask;
  if (el.baselineInputLabel) {
    el.baselineInputLabel.textContent = state.sourceMode === "adc"
      ? "Selected baseline (ADC)"
      : "Selected baseline (mV)";
  }
  el.baselineInput.step = state.sourceMode === "adc" ? "1" : "0.001";
  el.baselineHeading.textContent = state.sourceMode === "ideal"
    ? "Known baseline"
    : state.sourceMode === "clean"
      ? "Annotated isoelectric reference"
      : state.sourceMode === "practice"
        ? "Your baseline"
        : "Choose a local reference";
  if (el.baselineZero) el.baselineZero.textContent = state.sourceMode === "adc" ? "ADC zero" : "0 mV";
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
  const controlsDrawer = document.getElementById("controlsDrawer");
  const evidenceDrawer = document.getElementById("evidenceDrawer");
  if (state.interfaceMode === "advanced") {
    if (controlsDrawer) controlsDrawer.open = true;
    if (evidenceDrawer) evidenceDrawer.open = true;
    if (el.provenanceDetails) el.provenanceDetails.open = true;
  } else if (persist) {
    if (controlsDrawer) controlsDrawer.open = false;
    if (evidenceDrawer) evidenceDrawer.open = false;
  }
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
  const m = (state.sourceMode === "real" || state.sourceMode === "adc") ? (state.sourceManifest || {}) : {};

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
  } else if (state.sourceMode === "practice") {
    const item = practiceManifestItem();
    const recordLabel = state.practiceReveal ? (p.record || item?.source_record || state.record.record_id) : "hidden until review";
    values = [
      ["Dataset", p.dataset || "Lobachevsky University ECG Database (LUDB)"],
      ["Repository", p.repository || "PhysioNet"],
      ["Version", p.dataset_version || "1.0.1"],
      ["DOI", p.doi || "10.13026/eegm-h675"],
      ["License", p.license || "ODC Attribution 1.0"],
      ["Exercise", item?.label || "Practice ECG"],
      ["Source record", recordLabel],
      ["Lead", p.lead || "II"],
      ["Sampling", state.record.sampling_rate_hz + " Hz"],
      ["Amplitude", "Physical mV from source WFDB metadata"],
      ["Expert reference", state.practiceReveal ? "Cardiologist delineations revealed" : "Hidden until learner review"],
      ["OPL processing", "No filtering applied to displayed practice waveform"],
      ["OPL build", buildLabel()]
    ];
    summary = (item?.label || "Practice ECG") + " · LUDB Lead II · physical mV · expert hidden";
  } else if (state.sourceMode === "real") {
    const acquisition = state.record?.adc?.resolution_bits ? state.record.adc.resolution_bits + "-bit" : "—";
    const gain = derivedCountsPerMv(state.record);
    values = [
      ["Dataset", p.dataset || m.title || "ECG-ID Database"],
      ["Repository", p.repository || m.repository || "PhysioNet"],
      ["Contributor", p.contributor || m.contributor || "Tatiana Lugovaya"],
      ["Version", p.dataset_version || m.version || "1.0.0"],
      ["DOI", p.doi || m.doi || "10.13026/C2J01F"],
      ["License", p.license || m.license || "ODC Attribution 1.0"],
      ["Record", state.record.record_id],
      ["Sampling", state.record.sampling_rate_hz + " Hz"],
      ["Amplitude", gain ? "Physical mV derived from known source gain (" + gain + " ADC per mV)" : "Physical mV derived from source metadata"],
      ["Acquisition", acquisition],
      ["OPL processing", "Raw and source-filtered views available; no hidden OPL filtering"],
      ["OPL build", buildLabel()]
    ];
    summary = (p.dataset || "ECG-ID") + " · imperfect real ECG · physical mV · derived from source ADC";
  } else {
    const acquisition = state.record?.adc?.resolution_bits ? state.record.adc.resolution_bits + "-bit" : "—";
    const gain = derivedCountsPerMv(state.record);
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
      ["Amplitude", gain ? "Source ADC counts · known conversion " + gain + " ADC per mV (1 ADC = " + roundNumber(1/gain, 4) + " mV)" : "Source ADC counts"],
      ["OPL processing", "Raw and source-filtered views available; machine-scale learning"],
      ["OPL build", buildLabel()]
    ];
    summary = (p.dataset || "ECG-ID") + " · machine view · ADC counts · " + state.record.sampling_rate_hz + " Hz";
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
  if (!((state.sourceMode === "real" || state.sourceMode === "adc") && state.realRecord)) {
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

  let aText = signal && a != null ? cursorText(a, signal[a]) : "—";
  let bText = signal && b != null ? cursorText(b, signal[b]) : "—";

  if (state.sourceMode === "ideal") {
    if (a != null) aText = idealCursorText(a, signal[a]);
    if (b != null) bText = idealCursorText(b, signal[b]);
  }

  const rows = [
    ["A", aText],
    ["B", bText],
    ["Δt", fs && a != null && b != null ? formatTimeMeasurement(a,b,fs) : "—"],
    ["ΔV", signal && a != null && b != null ? formatVoltageMeasurement(signal[a],signal[b]) : "—"],
    ["Signal", signalLabel()]
  ];
  el.measurementGrid.innerHTML = rows.map(([label,value]) =>
    "<div><span>" + escapeHtml(label) + "</span><strong>" + escapeHtml(value) + "</strong></div>"
  ).join("");

  if (el.dockDelta) {
    el.dockDelta.textContent = fs && a != null && b != null
      ? "Δt " + roundNumber(durationMs(a,b,fs), 1) + " ms · " + roundNumber(Math.abs(durationMs(a,b,fs))/40,2) + " boxes"
      : "Δt —";
  }

  renderMeasurementAssist();
  renderPracticeReview();

  if (state.sourceMode === "ideal") {
    el.baselineOutput.textContent = "0 mV";
    el.baselineInput.value = "0";
  } else if (state.sourceMode === "clean") {
    el.baselineOutput.textContent = formatSigned(roundNumber(state.baseline, 4)) + " mV ref";
    el.baselineInput.value = String(roundNumber(state.baseline, 4));
  } else if (state.baselineStatus === "uncertain") {
    el.baselineOutput.textContent = "uncertain";
    el.baselineInput.value = String(roundNumber(state.baseline, 4));
  } else if (state.sourceMode === "real") {
    el.baselineOutput.textContent = formatSigned(roundNumber(state.baseline, 4)) + " mV ref";
    el.baselineInput.value = String(roundNumber(state.baseline, 4));
  } else if (state.sourceMode === "practice") {
    el.baselineOutput.textContent = state.baselineStatus === "unselected"
      ? "choose baseline"
      : formatSigned(roundNumber(state.baseline, 4)) + " mV";
    el.baselineInput.value = String(roundNumber(state.baseline, 4));
  } else {
    el.baselineOutput.textContent = formatSigned(state.baseline) + " ADC";
    el.baselineInput.value = String(roundNumber(state.baseline, 3));
  }
}

function idealCursorText(sample, value) {
  const landmark =
    nearestIdealIntervalEndpoint(state.record, sample, 30) ||
    nearestIdealLandmark(state.record, sample, 30);
  const delta = value - IDEAL_ECG_SPEC.baseline_mV;
  if (!landmark) {
    return roundNumber(sampleToMs(sample, state.record.sampling_rate_hz), 2) +
      " ms · " + formatSigned(roundNumber(delta, 3)) + " mV · " + formatSigned(roundNumber(delta/0.1,2)) + " vertical boxes";
  }
  const offset = roundNumber(landmark.distance_ms, 1);
  const offsetText = offset === 0 ? "on landmark" : (offset > 0 ? "+" : "") + offset + " ms";
  return "near " + landmark.label + " · " + offsetText + " · " + formatSigned(roundNumber(delta, 3)) + " mV · " + formatSigned(roundNumber(delta/0.1,2)) + " vertical boxes";
}

function renderMeasurementAssist() {
  if (!el.measurementAssist) return;

  const a = state.calipers.a;
  const b = state.calipers.b;

  if (state.sourceMode === "ideal") {
    if (a == null && b == null) {
      el.measurementAssist.innerHTML =
        "<strong>Landmark assist:</strong> place A and B near the boundaries of a P wave, PR interval, QRS complex, QT interval, or successive R peaks.";
      return;
    }

    if (a == null || b == null) {
      const sample = a ?? b;
      const landmark = nearestIdealLandmark(state.record, sample, 30);
      el.measurementAssist.innerHTML = landmark
        ? "<strong>Landmark assist:</strong> first caliper is near " + escapeHtml(landmark.label) + ". Place the second boundary."
        : "<strong>Landmark assist:</strong> first caliper is not within 30 ms of a declared landmark.";
      return;
    }

    const interpretation = interpretIdealCalipers(state.record, a, b, 30);
    if (!interpretation.measurement) {
      const aLabel = interpretation.a?.label || "an unlabeled boundary";
      const bLabel = interpretation.b?.label || "an unlabeled boundary";
      el.measurementAssist.innerHTML =
        "<strong>Landmark assist:</strong> A is near " + escapeHtml(aLabel) +
        " and B is near " + escapeHtml(bLabel) +
        ". OPL does not recognize that pair as one of the declared teaching intervals.";
      return;
    }

    const m = interpretation.measurement;
    const error = roundNumber(m.error_ms, 1);
    const absError = Math.abs(error);
    const cls = absError <= 10 ? "good" : "warn";
    const difference = error === 0 ? "exactly matches" :
      (error > 0 ? "+" : "") + error + " ms from";

    el.measurementAssist.innerHTML =
      "<strong>" + escapeHtml(m.label) + "</strong> · measured " +
      escapeHtml(String(roundNumber(m.measured_ms, 1))) + " ms (" +
      escapeHtml(String(roundNumber(m.measured_ms/40, 2))) + " small boxes) · model " +
      escapeHtml(String(roundNumber(m.expected_ms, 1))) + " ms (" +
      escapeHtml(String(roundNumber(m.expected_ms/40, 2))) + " boxes) · <span class=\"" + cls + "\">" +
      escapeHtml(difference) + " model</span>. " +
      "This is manual placement feedback; OPL has not moved your calipers.";
    return;
  }

  if (state.sourceMode === "clean") {
    if (a == null && b == null) {
      el.measurementAssist.innerHTML =
        "<strong>Expert-reference assist:</strong> place A and B on a real P/QRS/T boundary. OPL will compare your manual placement with the LUDB cardiologist delineation.";
      return;
    }
    if (a == null || b == null) {
      el.measurementAssist.innerHTML =
        "<strong>Expert-reference assist:</strong> first caliper placed. Select the second boundary; OPL will not snap either cursor.";
      return;
    }

    const result = interpretLudbCalipers(state.record, a, b, 40);
    const m = result.measurement;
    if (!m) {
      el.measurementAssist.innerHTML =
        "<strong>Expert-reference assist:</strong> this A/B pair is not within 40 ms of both endpoints of a recognized LUDB reference interval. Keep the manual measurement, or reposition the boundaries.";
      return;
    }

    const error = roundNumber(m.error_ms, 1);
    const cls = Math.abs(error) <= 10 ? "good" : "warn";
    const errorText = error === 0 ? "matches the reference" :
      (error > 0 ? "+" : "") + error + " ms vs reference";

    el.measurementAssist.innerHTML =
      "<strong>" + escapeHtml(m.label) + "</strong> · your calipers " +
      escapeHtml(String(roundNumber(m.measured_ms,1))) + " ms (" +
      escapeHtml(String(roundNumber(m.measured_ms/40,2))) + " small boxes) · cardiologist reference " +
      escapeHtml(String(roundNumber(m.reference_ms,1))) + " ms (" +
      escapeHtml(String(roundNumber(m.reference_ms/40,2))) + " boxes) · <span class=\"" + cls + "\">" +
      escapeHtml(errorText) + "</span>. " +
      "Endpoint differences: A " + escapeHtml(formatSigned(roundNumber(m.start_error_ms,1))) +
      " ms, B " + escapeHtml(formatSigned(roundNumber(m.end_error_ms,1))) + " ms.";
    return;
  }

  if (state.sourceMode === "practice") {
    const item = practiceManifestItem();
    if (!state.practiceReveal) {
      if (a == null && b == null) {
        el.measurementAssist.innerHTML =
          "<strong>Practice:</strong> choose a defensible baseline, then drag A→B around the interval you want to measure. Time is shown in ms and 40-ms small boxes; amplitude is shown in mV and 0.1-mV vertical boxes after baseline selection.";
      } else if (a == null || b == null) {
        el.measurementAssist.innerHTML =
          "<strong>Practice:</strong> first caliper placed. Complete A→B before revealing the cardiologist reference.";
      } else {
        el.measurementAssist.innerHTML =
          "<strong>Practice:</strong> measurement recorded on " + escapeHtml(item?.label || "this ECG") +
          ". Decide whether the boundaries and baseline are defensible, then reveal the expert reference when ready.";
      }
      return;
    }

    if (a == null || b == null) {
      el.measurementAssist.innerHTML =
        "<strong>Expert revealed:</strong> cardiologist boundaries are now visible. Place A and B to compare your measurement.";
      return;
    }
    const m = interpretLudbCalipers(state.record, a, b, 40).measurement;
    if (!m) {
      el.measurementAssist.innerHTML =
        "<strong>Expert revealed:</strong> this A/B pair does not fall within 40 ms of both endpoints of a recognized LUDB interval.";
      return;
    }
    const targetMismatch = state.practiceTask !== "free" && m.key !== state.practiceTask;
    el.measurementAssist.innerHTML =
      "<strong>" + escapeHtml(m.label) + "</strong> · your calipers " +
      escapeHtml(String(roundNumber(m.measured_ms,1))) + " ms (" + escapeHtml(String(roundNumber(m.measured_ms/40,2))) +
      " small boxes) · expert " + escapeHtml(String(roundNumber(m.reference_ms,1))) + " ms · error " +
      escapeHtml(formatSigned(roundNumber(m.error_ms,1))) + " ms" +
      (targetMismatch ? ' · <span class="warn">this is not the selected practice target</span>' : "") + ".";
    return;
  }

  el.measurementAssist.innerHTML = "";
}

function practiceManifestItem() {
  return (state.practiceManifest?.records || []).find(item => item.id === state.practiceRecordId) || null;
}

function renderPracticePicker() {
  if (!el.practiceRecordList) return;
  const items = state.practiceManifest?.records || [];
  if (!items.length) {
    el.practiceRecordList.innerHTML = '<p class="muted">Practice bank unavailable in this build.</p>';
    return;
  }
  el.practiceRecordList.innerHTML = items.map(item =>
    '<button type="button" class="practice-record-button ' + (item.id === state.practiceRecordId ? 'active' : '') + '" data-practice-id="' +
    escapeHtml(item.id) + '"><strong>' + escapeHtml(item.label) + '</strong><small>' +
    escapeHtml(item.difficulty) + ' · Lead II · 10 s · 500 Hz</small></button>'
  ).join('');
  el.practiceRecordList.querySelectorAll('[data-practice-id]').forEach(button => {
    button.addEventListener('click', () => loadPracticeRecord(button.dataset.practiceId));
  });
}

function loadPracticeRecord(id) {
  const record = state.practiceRecords.get(id);
  if (!record) return;
  if (state.sourceMode !== 'practice') state.storyReturnMode = state.sourceMode;
  state.practiceRecordId = id;
  state.practiceRecord = record;
  state.practiceReveal = false;
  switchSource('practice', {restore:false});
  scrollToLab();
}

function resetPracticeAttempt() {
  if (state.sourceMode !== 'practice') return;
  state.calipers = {a:null,b:null};
  state.nextCaliper = 'a';
  state.baseline = 0;
  state.baselineStatus = 'unselected';
  state.practiceReveal = false;
  state.showAnnotations = false;
  syncControlsFromState();
  renderAll();
  persistSession();
}

function renderPracticeReview() {
  if (!el.practiceReview || !el.practiceStatus || !el.practiceReveal) return;
  if (state.sourceMode !== 'practice' || !state.practiceRecord) {
    el.practiceReview.hidden = true;
    el.practiceStatus.textContent = 'Choose Practice to work through unfamiliar real ECGs.';
    return;
  }

  const item = practiceManifestItem();
  const taskLabel = el.practiceTask?.selectedOptions?.[0]?.textContent || 'Free measurement';
  const baselineState = state.baselineStatus === 'unselected'
    ? 'baseline not assigned'
    : state.baselineStatus === 'uncertain'
      ? 'baseline marked uncertain'
      : 'baseline ' + formatSigned(roundNumber(state.baseline,3)) + ' mV';

  if (!state.practiceReveal) {
    el.practiceReveal.textContent = 'Reveal expert';
    el.practiceReview.hidden = true;
    el.practiceStatus.innerHTML = '<strong>' + escapeHtml(item?.label || 'Practice ECG') + '</strong> · ' +
      escapeHtml(item?.difficulty || '') + ' · target: ' + escapeHtml(taskLabel) + ' · ' + escapeHtml(baselineState) +
      '. Expert annotations and source record ID are hidden.';
    return;
  }

  el.practiceReveal.textContent = 'Hide expert';
  el.practiceReview.hidden = false;
  const expertBaseline = Number(state.practiceRecord.recommended_baseline_mV);
  const baselineError = state.baselineStatus === 'selected'
    ? state.baseline - expertBaseline
    : null;
  const summaries = summarizeLudbReferenceIntervals(state.practiceRecord);
  const target = state.practiceTask === 'free' ? null : summaries.find(row => row.key === state.practiceTask);
  const interpreted = (state.calipers.a != null && state.calipers.b != null)
    ? interpretLudbCalipers(state.practiceRecord, state.calipers.a, state.calipers.b, 40).measurement
    : null;

  let measurementHtml = '<span class="warn">No recognized expert interval at the current A/B pair.</span>';
  if (interpreted) {
    const boxes = interpreted.measured_ms / 40;
    measurementHtml = '<strong>' + escapeHtml(interpreted.label) + '</strong>: your calipers ' +
      escapeHtml(String(roundNumber(interpreted.measured_ms,1))) + ' ms (' + escapeHtml(String(roundNumber(boxes,2))) +
      ' small boxes) · expert ' + escapeHtml(String(roundNumber(interpreted.reference_ms,1))) + ' ms · error ' +
      escapeHtml(formatSigned(roundNumber(interpreted.error_ms,1))) + ' ms.';
  }

  el.practiceReview.innerHTML =
    '<strong>Expert revealed</strong> · LUDB record ' + escapeHtml(item?.source_record || state.practiceRecord.provenance?.record || '—') +
    ' · Lead II.<br>' +
    'Cardiologist-derived PR/TP baseline: ' + escapeHtml(formatSigned(roundNumber(expertBaseline,4))) + ' mV' +
    (baselineError == null ? ' · your baseline was not finalized.' : ' · your baseline error ' + escapeHtml(formatSigned(roundNumber(baselineError,4))) + ' mV (' + escapeHtml(formatSigned(roundNumber(baselineError/0.1,2))) + ' vertical boxes).') +
    (target ? '<br>Target reference across beats: median ' + escapeHtml(String(roundNumber(target.median_ms,1))) + ' ms (' + escapeHtml(String(roundNumber(target.median_ms/40,2))) + ' small boxes), range ' + escapeHtml(String(roundNumber(target.min_ms,1))) + '–' + escapeHtml(String(roundNumber(target.max_ms,1))) + ' ms.' : '') +
    '<br>' + measurementHtml;
  el.practiceStatus.textContent = 'Expert reference is visible. Hide it or reset the attempt to practice again without annotations.';
}

function renderLudbReferenceTable() {
  if (!el.ludbMeasurementTable) return;
  if (state.sourceMode !== "clean" || !state.cleanRecord) {
    el.ludbMeasurementTable.innerHTML = "";
    return;
  }

  const rows = summarizeLudbReferenceIntervals(state.cleanRecord);
  el.ludbMeasurementTable.innerHTML = rows.map(row =>
    '<div class="reference-measurement-row">' +
      '<span>' + escapeHtml(row.label) + '</span>' +
      '<strong>' + escapeHtml(String(roundNumber(row.median_ms,1))) + ' ms median</strong>' +
      '<small>n=' + escapeHtml(String(row.n)) + ' · range ' +
      escapeHtml(String(roundNumber(row.min_ms,1))) + '–' +
      escapeHtml(String(roundNumber(row.max_ms,1))) + ' ms</small>' +
    '</div>'
  ).join("");
}

function cursorText(sample, value) {
  const time = sampleToMs(sample, state.record.sampling_rate_hz);

  if (state.sourceMode === "ideal") {
    const delta = value - IDEAL_ECG_SPEC.baseline_mV;
    return roundNumber(time, 2) + " ms · " + formatSigned(roundNumber(delta, 3)) + " mV · " + formatSigned(roundNumber(delta/0.1,2)) + " vertical boxes";
  }

  if (state.sourceMode === "clean" || state.sourceMode === "real" || state.sourceMode === "practice") {
    if (state.baselineStatus === "uncertain" || state.baselineStatus === "unselected") {
      return roundNumber(time, 2) + " ms · amplitude withheld until baseline is chosen";
    }
    const delta = value - state.baseline;
    return roundNumber(time, 2) + " ms · " + formatSigned(roundNumber(delta, 3)) + " mV · " +
      formatSigned(roundNumber(delta/0.1, 2)) + " vertical boxes";
  }

  if (state.baselineStatus === "uncertain") {
    return roundNumber(time, 2) + " ms · amplitude withheld";
  }

  const delta = deltaAdc(value, state.baseline);
  const gain = derivedCountsPerMv(state.record);
  const mv = gain ? delta / gain : null;
  return roundNumber(time, 2) + " ms · " + formatSigned(roundNumber(delta, 2)) + " ADC" +
    (mv == null ? "" : " · " + formatSigned(roundNumber(mv, 3)) + " mV · " + formatSigned(roundNumber(mv/0.1,2)) + " vertical boxes");
}

function formatTimeMeasurement(sampleA,sampleB,fs) {
  const ms = Math.abs(durationMs(sampleA,sampleB,fs));
  const boxes = ms / 40;
  return roundNumber(ms,2) + " ms · " + roundNumber(boxes,2) + " small boxes";
}

function formatVoltageMeasurement(valueA,valueB) {
  if (state.baselineStatus === "uncertain" || state.baselineStatus === "unselected") {
    return "withheld until baseline is usable";
  }
  if (state.sourceMode === "adc") {
    const adc = Number(valueB) - Number(valueA);
    const gain = derivedCountsPerMv(state.record);
    if (!gain) return formatSigned(roundNumber(adc,2)) + " ADC";
    const mv = adc / gain;
    return formatSigned(roundNumber(adc,2)) + " ADC · " + formatSigned(roundNumber(mv,3)) + " mV · " +
      formatSigned(roundNumber(mv/0.1,2)) + " small boxes";
  }
  const mv = Number(valueB) - Number(valueA);
  return formatSigned(roundNumber(mv,3)) + " mV · " + formatSigned(roundNumber(mv/0.1,2)) + " small boxes";
}

function setBaseline(value, status="selected") {
  if (!(state.sourceMode === "real" || state.sourceMode === "adc" || state.sourceMode === "practice") || !Number.isFinite(Number(value))) return;
  state.baseline = Number(value);
  state.baselineStatus = status;
  persistSession();
  renderMeasurements();
  renderBaselineReality();
  draw();
}

function setBaselineStatus(status) {
  if (!(state.sourceMode === "real" || state.sourceMode === "adc" || state.sourceMode === "practice")) return;
  state.baselineStatus = status === "uncertain" ? "uncertain" : "selected";
  persistSession();
  renderMeasurements();
  renderBaselineReality();
  draw();
}

function useVisibleMedianBaseline() {
  if (!(state.sourceMode === "real" || state.sourceMode === "adc" || state.sourceMode === "practice") || !state.record) return;
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
  const unselected = state.baselineStatus === "unselected";
  el.baselineConfident.classList.toggle("active", !uncertain && !unselected);
  el.baselineUncertain.classList.toggle("active", uncertain);
  if (state.sourceMode === "practice") {
    el.baselineRealityText.textContent = unselected
      ? "Baseline not yet assigned. Time measurements work now; choose a baseline before interpreting amplitude in mV or vertical boxes."
      : uncertain
        ? "You marked the baseline uncertain: vertical amplitude is deliberately withheld. Time and horizontal box measurements remain available."
        : state.practiceReveal
          ? "Your baseline is shown against the hidden cardiologist-derived PR/TP reference in the Practice review above."
          : "Your baseline is active. Amplitudes are now reported in mV and 0.1-mV vertical-box units; expert reference remains hidden.";
  } else if (state.sourceMode === "real") {
    el.baselineRealityText.textContent = uncertain
      ? "Baseline marked uncertain: vertical amplitude is deliberately withheld. Time measurements remain available."
      : "Local baseline accepted for this view: vertical values are reported in physical mV, derived from the known ECG-ID ADC→mV conversion.";
  } else {
    el.baselineRealityText.textContent = uncertain
      ? "Baseline marked uncertain: vertical amplitude is deliberately withheld. Time measurements remain available."
      : "Local baseline accepted for this view: vertical values are reported relative to the selected ADC reference, not as calibrated input mV.";
  }
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
  const markerLabel = (state.sourceMode === "clean" || state.sourceMode === "practice")
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
  if (state.sourceMode === "practice") return "Practice real Lead II · physical mV";
  if (state.sourceMode === "real") {
    return state.measurementSignal === "raw"
      ? "Imperfect real ECG · physical mV"
      : "Source filtered ECG · physical mV";
  }
  return state.measurementSignal === "raw" ? "Raw ECG · ADC" : "Source filtered ECG · ADC";
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

function updateRuler() {
  if (!el.rulerSmallBox || !el.rulerLargeBox) return;
  if (state.sourceMode === "adc") {
    const small = Number(state.verticalGridAdc);
    el.rulerSmallBox.textContent = "40 ms × " + small + " ADC";
    el.rulerLargeBox.textContent = "200 ms × " + (small * 5) + " ADC";
  } else {
    el.rulerSmallBox.textContent = "40 ms × 0.1 mV";
    el.rulerLargeBox.textContent = "200 ms × 0.5 mV";
  }
}

function verticalSmallBoxValue() {
  return state.sourceMode === "adc" ? state.verticalGridAdc : 0.1;
}

function updateGridLabel() {
  if (state.sourceMode === "ideal") {
    el.gridScale.textContent = "ECG paper: square boxes · 40 ms × 0.1 mV (synthetic)";
  } else if (state.sourceMode === "clean") {
    el.gridScale.textContent = "ECG paper: square boxes · 40 ms × 0.1 mV";
  } else if (state.sourceMode === "real") {
    el.gridScale.textContent = "ECG paper: square boxes · 40 ms × 0.1 mV (derived from known ADC→mV conversion)";
  } else if (state.sourceMode === "practice") {
    el.gridScale.textContent = "Practice ECG paper: square boxes · 40 ms × 0.1 mV";
  } else {
    const gain = derivedCountsPerMv(state.record);
    const approxMv = gain ? roundNumber(state.verticalGridAdc / gain, 3) : null;
    el.gridScale.textContent = "Machine view: square boxes · 40 ms × " + state.verticalGridAdc + " ADC" + (approxMv != null ? " (~" + approxMv + " mV)" : "");
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

  const fs = Number(state.record.sampling_rate_hz);
  const visibleDurationSeconds = Math.max(
    1 / fs,
    (end - start - 1) / fs
  );
  const verticalSmallBox = verticalSmallBoxValue();
  const dataMin = Math.min(...displayed,state.baseline);
  const dataMax = Math.max(...displayed,state.baseline);
  const paperRange = computeSquarePaperRange({
    widthPx:w,
    heightPx:h,
    visibleDurationSeconds,
    verticalSmallBox,
    baseline:state.baseline,
    dataMin,
    dataMax,
    marginBoxes:1
  });
  const yMin = paperRange.yMin;
  const yMax = paperRange.yMax;

  const dpr = Math.max(1,window.devicePixelRatio||1);
  drawGrid(start,end,yMin,yMax,dpr);
  drawCaliperSpan(state.calipers.a,state.calipers.b,start,end,dpr);

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
  const startTime=start/fs;
  const endTime=(end-1)/fs;
  const duration=Math.max(1/fs,endTime-startTime);

  const first=Math.ceil((startTime-1e-12)/ECG_PAPER_TIME_SMALL_BOX_S)*ECG_PAPER_TIME_SMALL_BOX_S;
  for(let t=first;t<=endTime+1e-9;t+=ECG_PAPER_TIME_SMALL_BOX_S){
    const major=Math.abs((t/.2)-Math.round(t/.2))<1e-7;
    ctx.strokeStyle=major?cssColor("--grid-major"):cssColor("--grid-minor");
    ctx.lineWidth=(major?1:.55)*dpr;
    const x=(t-startTime)/duration*w;
    ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,h);ctx.stroke();
  }

  const step=verticalSmallBoxValue();
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

  drawBracket(
    lm.p_onset,lm.qrs_onset,
    "PR · " + IDEAL_ECG_SPEC.teaching_measurements.pr_interval_ms + " ms",
    el.ecgCanvas.height-68*dpr,start,end,dpr
  );
  drawBracket(
    lm.qrs_onset,lm.qrs_end,
    "QRS · " + IDEAL_ECG_SPEC.teaching_measurements.qrs_duration_ms + " ms",
    el.ecgCanvas.height-46*dpr,start,end,dpr
  );
  drawBracket(
    lm.qrs_onset,lm.t_end,
    "QT · " + IDEAL_ECG_SPEC.teaching_measurements.qt_interval_ms + " ms",
    el.ecgCanvas.height-24*dpr,start,end,dpr
  );
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

function drawCaliperSpan(sampleA,sampleB,start,end,dpr){
  if(!Number.isInteger(sampleA)||!Number.isInteger(sampleB))return;
  const left=Math.max(start,Math.min(sampleA,sampleB));
  const right=Math.min(end-1,Math.max(sampleA,sampleB));
  if(right<start||left>=end||right<=left)return;

  const x1=xFor(left,start,end);
  const x2=xFor(right,start,end);
  ctx.fillStyle=cssColor("--cyan");
  ctx.globalAlpha=.055;
  ctx.fillRect(x1,0,x2-x1,el.ecgCanvas.height);
  ctx.globalAlpha=1;

  const duration=durationMs(left,right,state.record.sampling_rate_hz);
  ctx.fillStyle=cssColor("--text-secondary");
  ctx.font="bold "+10*dpr+"px sans-serif";
  ctx.textAlign="center";
  ctx.fillText(roundNumber(duration,1)+" ms",(x1+x2)/2,14*dpr);
  ctx.textAlign="left";
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
  if (el.stageSelect) el.stageSelect.value = state.sourceMode;
}

function scrollToLab(){
  document.querySelector(".core-workspace")?.scrollIntoView({behavior:"smooth", block:"start"});
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
