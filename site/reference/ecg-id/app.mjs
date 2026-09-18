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
import {ECG_TEACHING_QUESTIONS, evaluateAnswer, scoreQuiz} from "./teaching.mjs";

const BUNDLED_RECORD_URL = "./data/Person_01_rec_1.json";
const RECORD_ID = "ECG-ID/Person_01/rec_1";
const SESSION_KEY = "opl:ecg-reference:session:" + RECORD_ID;
const MODE_KEY = "opl:ecg-reference:mode";
const QUIZ_KEY = "opl:ecg-reference:quiz";

const state = {
  record: null,
  sourceManifest: null,
  buildInfo: null,
  baseline: 0,
  calipers: {a: null, b: null},
  nextCaliper: "a",
  mode: "overlay",
  measurementSignal: "raw",
  windowSeconds: 5,
  windowStartSeconds: 0,
  showAnnotations: true,
  verticalGridAdc: 50,
  interfaceMode: "advanced",
  quizIndex: 0,
  quizResponses: {}
};

const el = Object.fromEntries([
  "onlineState","provenanceGrid","waveformMode","measurementSignal","verticalGrid","gridScale","windowLength",
  "windowStart","windowStartLabel","showAnnotations","ecgCanvas","baselineOutput",
  "baselineInput","baselineZero","baselineMedian","baselineFromA","resetCalipers",
  "measurementGrid","saveOffline","exportPackage","importPackage","keepStatus",
  "quickMode","advancedMode","quickBaselineMedian","teachingHint","provenanceDetails","provenanceSummary",
  "quizScore","quizTotal","quizQuestion","quizOptions","quizFeedback","quizNext","quizReset"
].map(id => [id, document.getElementById(id)]));

const ctx = el.ecgCanvas.getContext("2d");

boot();

async function boot() {
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

  let record = null;
  try {
    record = await fetch(BUNDLED_RECORD_URL, {cache: "no-cache"}).then(requireOk).then(r => r.json());
    el.onlineState.textContent = navigator.onLine ? "Reference record loaded" : "Offline cache";
  } catch {
    record = await getRecord(RECORD_ID).catch(() => null);
    el.onlineState.textContent = record ? "Offline saved record" : "Reference record unavailable";
  }

  if (!record) {
    showStatus("The reference record is not bundled in this build and has not been saved offline yet. Use a built OPL package or import a previously exported OPL Reference Package.", true);
    renderProvenance();
    return;
  }

  loadRecord(record, restoreSession());
}

function bindEvents() {
  el.quickMode.addEventListener("click", () => setInterfaceMode("teaching"));
  el.advancedMode.addEventListener("click", () => setInterfaceMode("advanced"));

  document.querySelectorAll("[data-quick-waveform]").forEach(button => {
    button.addEventListener("click", () => {
      const mode = button.dataset.quickWaveform;
      state.mode = mode;
      el.waveformMode.value = mode;
      syncQuickWaveformButtons();
      markLessonComplete(1);
      draw();
    });
  });

  el.waveformMode.addEventListener("change", () => {
    state.mode = el.waveformMode.value;
    syncQuickWaveformButtons();
    draw();
  });
  el.measurementSignal.addEventListener("change", () => { state.measurementSignal = el.measurementSignal.value; renderMeasurements(); draw(); scheduleClassroomViewEmit(); });
  el.verticalGrid.addEventListener("change", () => {
    state.verticalGridAdc = Number(el.verticalGrid.value);
    el.gridScale.textContent = "Small box: 40 ms × " + state.verticalGridAdc + " ΔADC";
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
  el.baselineInput.addEventListener("change", () => setBaseline(Number(el.baselineInput.value)));
  el.baselineZero.addEventListener("click", () => setBaseline(Number(state.record?.adc?.zero?.[signalIndex()] ?? 0)));
  el.baselineMedian.addEventListener("click", useVisibleMedianBaseline);
  el.quickBaselineMedian.addEventListener("click", () => {
    useVisibleMedianBaseline();
    markLessonComplete(2);
  });
  el.baselineFromA.addEventListener("click", () => {
    if (!state.record || state.calipers.a == null) return;
    setBaseline(activeSignal()[state.calipers.a]);
  });
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
    if (state.calipers.a != null && state.calipers.b != null) markLessonComplete(3);
    persistSession();
    renderMeasurements();
    draw();
  });

  el.saveOffline.addEventListener("click", async () => {
    if (!state.record) return;
    await saveRecord(state.record);
    persistSession();
    showStatus("Saved locally in this browser. The record can be reopened without downloading it again.");
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
    downloadJson("OPL_ECG-ID_Person_01_rec_1_reference-package.json", pkg);
    showStatus("Downloaded a self-contained OPL Reference Package with waveform, provenance and current measurements.");
  });

  el.importPackage.addEventListener("change", async event => {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      const value = JSON.parse(await file.text());
      const imported = importExportPackage(value);
      loadRecord(imported.record, imported.session);
      showStatus("Opened saved OPL Reference Package.");
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

function initInterfaceMode() {
  let saved = null;
  try { saved = localStorage.getItem(MODE_KEY); } catch {}
  const defaultMode = window.matchMedia("(max-width: 800px)").matches ? "teaching" : "advanced";
  setInterfaceMode(saved === "teaching" || saved === "advanced" ? saved : defaultMode, false);
}

function setInterfaceMode(mode, persist = true) {
  state.interfaceMode = mode === "teaching" ? "teaching" : "advanced";
  document.body.classList.toggle("mode-teaching", state.interfaceMode === "teaching");
  document.body.classList.toggle("mode-advanced", state.interfaceMode === "advanced");
  el.quickMode.setAttribute("aria-pressed", String(state.interfaceMode === "teaching"));
  el.advancedMode.setAttribute("aria-pressed", String(state.interfaceMode === "advanced"));
  if (el.provenanceDetails) el.provenanceDetails.open = state.interfaceMode === "advanced";
  if (persist) {
    try { localStorage.setItem(MODE_KEY, state.interfaceMode); } catch {}
  }
  requestAnimationFrame(() => {
    resizeCanvas();
    draw();
  });
}

function syncQuickWaveformButtons() {
  document.querySelectorAll("[data-quick-waveform]").forEach(button => {
    button.classList.toggle("active", button.dataset.quickWaveform === state.mode);
  });
}

function useVisibleMedianBaseline() {
  if (!state.record) return;
  const [start,end] = visibleSampleRange();
  setBaseline(median(activeSignal().slice(start, end)));
}

function markLessonComplete(step) {
  const dots = [...document.querySelectorAll("[data-lesson-dot]")];
  dots.forEach(dot => {
    const n = Number(dot.dataset.lessonDot);
    dot.classList.toggle("done", n <= step);
    dot.classList.toggle("active", n === Math.min(step + 1, 4));
  });
}

function restoreQuiz() {
  try {
    const saved = JSON.parse(localStorage.getItem(QUIZ_KEY));
    if (saved && typeof saved === "object") {
      state.quizIndex = Number.isInteger(saved.index) ? Math.max(0, Math.min(saved.index, ECG_TEACHING_QUESTIONS.length - 1)) : 0;
      state.quizResponses = saved.responses && typeof saved.responses === "object" ? saved.responses : {};
    }
  } catch {}
}

function persistQuiz() {
  try {
    localStorage.setItem(QUIZ_KEY, JSON.stringify({
      index: state.quizIndex,
      responses: state.quizResponses
    }));
  } catch {}
}

function renderQuiz() {
  const question = ECG_TEACHING_QUESTIONS[state.quizIndex];
  if (!question) return;

  const score = scoreQuiz(state.quizResponses);
  el.quizScore.textContent = String(score.correct);
  el.quizTotal.textContent = String(score.total);
  el.quizQuestion.textContent = question.prompt;
  el.quizOptions.innerHTML = "";

  const existing = state.quizResponses[question.id];
  question.options.forEach((option, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "quiz-option";
    button.textContent = option;

    if (Number.isInteger(existing)) {
      button.disabled = true;
      if (index === question.answer) button.classList.add("correct");
      else if (index === existing) button.classList.add("incorrect");
    } else {
      button.addEventListener("click", () => answerQuiz(question, index));
    }
    el.quizOptions.appendChild(button);
  });

  if (Number.isInteger(existing)) {
    const result = evaluateAnswer(question, existing);
    el.quizFeedback.textContent = (result.correct ? "Correct. " : "Not quite. ") + result.explanation;
  } else {
    el.quizFeedback.textContent = "Choose one answer.";
  }
  el.quizNext.textContent = state.quizIndex === ECG_TEACHING_QUESTIONS.length - 1 ? "Back to first" : "Next question";
}

function answerQuiz(question, optionIndex) {
  state.quizResponses[question.id] = optionIndex;
  persistQuiz();
  markLessonComplete(4);
  renderQuiz();
}

function loadRecord(record, session) {
  validateReferenceRecord(record);
  state.record = record;
  state.baseline = Number(session?.baseline_adc ?? record.adc?.zero?.[0] ?? 0);
  state.calipers = {
    a: integerOrNull(session?.calipers?.a),
    b: integerOrNull(session?.calipers?.b)
  };
  state.nextCaliper = state.calipers.a == null ? "a" : state.calipers.b == null ? "b" : "a";
  state.windowSeconds = Math.min(state.interfaceMode === "teaching" ? 5 : 5, record.duration_seconds);
  state.windowStartSeconds = 0;

  el.windowLength.value = String(state.windowSeconds);
  el.baselineInput.value = String(roundNumber(state.baseline, 3));
  clampWindowStart();
  syncWindowControls();
  renderProvenance();
  renderMeasurements();
  syncQuickWaveformButtons();
  draw();
}

function renderProvenance() {
  const p = state.record?.provenance || {};
  const m = state.sourceManifest || {};
  const values = [
    ["Dataset", p.dataset || m.title || "ECG-ID Database"],
    ["Repository", p.repository || m.repository || "PhysioNet"],
    ["Contributor", p.contributor || m.contributor || "Tatiana Lugovaya"],
    ["Version", p.dataset_version || m.version || "1.0.0"],
    ["DOI", p.doi || m.doi || "10.13026/C2J01F"],
    ["License", p.license || m.license || "ODC Attribution 1.0"],
    ["Record", state.record?.record_id || "Person_01 / rec_1"],
    ["Sampling", state.record ? state.record.sampling_rate_hz + " Hz" : "500 Hz"],
    ["Acquisition", state.record ? state.record.adc?.resolution_bits + "-bit" : "12-bit"],
    ["OPL processing", "None until a user-selected operation is applied"],
    ["OPL build", state.buildInfo?.git_sha ? state.buildInfo.git_sha.slice(0, 12) : "development source"]
  ];

  if (el.provenanceSummary) {
    const dataset = p.dataset || m.title || "ECG-ID";
    const repository = p.repository || m.repository || "PhysioNet";
    const sampling = state.record ? state.record.sampling_rate_hz + " Hz" : "500 Hz";
    const bits = state.record ? state.record.adc?.resolution_bits + "-bit" : "12-bit";
    el.provenanceSummary.textContent = dataset + " · " + repository + " · " + sampling + " · " + bits;
  }

  el.provenanceGrid.innerHTML = values.map(([label,value]) => {
    const content = label === "DOI" && value
      ? '<a href="https://doi.org/' + escapeHtml(String(value)) + '" target="_blank" rel="noopener">' + escapeHtml(String(value)) + "</a>"
      : "<strong>" + escapeHtml(String(value ?? "—")) + "</strong>";
    return '<div class="provenance-item"><span>' + escapeHtml(label) + "</span>" + content + "</div>";
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
    ["Signal", state.measurementSignal === "raw" ? "Raw ECG" : "Source filtered ECG"]
  ];
  el.measurementGrid.innerHTML = rows.map(([label,value]) =>
    "<div><span>" + escapeHtml(label) + "</span><strong>" + escapeHtml(value) + "</strong></div>"
  ).join("");
  el.baselineOutput.textContent = formatSigned(state.baseline) + " ADC";
  el.baselineInput.value = String(roundNumber(state.baseline, 3));
}

function cursorText(sample, value) {
  const time = sampleToMs(sample, state.record.sampling_rate_hz);
  const delta = deltaAdc(value, state.baseline);
  return roundNumber(time, 2) + " ms · " + formatSigned(delta) + " ΔADC";
}

function setBaseline(value) {
  if (!Number.isFinite(Number(value))) return;
  state.baseline = Number(value);
  persistSession();
  renderMeasurements();
  draw();
}

function activeSignal() {
  return state.record.signals[state.measurementSignal];
}

function signalIndex() {
  return state.measurementSignal === "raw" ? 0 : 1;
}

function visibleSampleRange() {
  const fs = state.record.sampling_rate_hz;
  const start = Math.floor(state.windowStartSeconds * fs);
  const end = Math.min(state.record.signals.raw.length, Math.ceil((state.windowStartSeconds + state.windowSeconds) * fs));
  return [start, Math.max(start + 1, end)];
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
  el.windowStart.value = String(Math.min(max, state.windowStartSeconds));
  el.windowStartLabel.textContent = roundNumber(state.windowStartSeconds, 2) + " s";
}

function resizeCanvas() {
  const rect = el.ecgCanvas.getBoundingClientRect();
  const dpr = Math.max(1, window.devicePixelRatio || 1);
  const width = Math.max(300, Math.round(rect.width * dpr));
  const height = Math.max(250, Math.round(rect.height * dpr));
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
  ctx.fillStyle = "#fbfcfd";
  ctx.fillRect(0,0,w,h);

  if (!state.record) {
    ctx.fillStyle = "#687985";
    ctx.font = Math.round(16 * (window.devicePixelRatio || 1)) + "px sans-serif";
    ctx.fillText("Reference record not loaded", 24, 40);
    return;
  }

  const [start,end] = visibleSampleRange();
  const raw = state.record.signals.raw.slice(start,end);
  const filtered = state.record.signals.filtered.slice(start,end);
  const displayed = state.mode === "raw" ? raw : state.mode === "filtered" ? filtered : raw.concat(filtered);
  const min = Math.min(...displayed, state.baseline);
  const max = Math.max(...displayed, state.baseline);
  const span = Math.max(1, max - min);
  const yMin = min - span * .12;
  const yMax = max + span * .12;
  const dpr = Math.max(1, window.devicePixelRatio || 1);

  drawGrid(start,end,yMin,yMax,dpr);

  const yBaseline = yFor(state.baseline,yMin,yMax,h);
  ctx.strokeStyle = "#5b6570";
  ctx.setLineDash([8*dpr,6*dpr]);
  ctx.lineWidth = 1*dpr;
  ctx.beginPath();ctx.moveTo(0,yBaseline);ctx.lineTo(w,yBaseline);ctx.stroke();
  ctx.setLineDash([]);

  if (state.mode === "raw" || state.mode === "overlay") drawSignal(state.record.signals.raw,start,end,yMin,yMax,"#18384d",1.35*dpr);
  if (state.mode === "filtered" || state.mode === "overlay") drawSignal(state.record.signals.filtered,start,end,yMin,yMax,"#b65e2e",1.15*dpr);

  if (state.showAnnotations) drawAnnotations(start,end,dpr);
  drawCaliper(state.calipers.a,"A","#2e7d4d",start,end,dpr);
  drawCaliper(state.calipers.b,"B","#7a3d8a",start,end,dpr);
}

function drawGrid(start,end,yMin,yMax,dpr) {
  const w=el.ecgCanvas.width,h=el.ecgCanvas.height,fs=state.record.sampling_rate_hz;
  const startTime=start/fs,endTime=end/fs;

  ctx.lineWidth=.55*dpr;
  ctx.strokeStyle="#e8edf1";
  const minor=.04;
  const first=Math.ceil(startTime/minor)*minor;
  for(let t=first;t<=endTime+1e-9;t+=minor){
    const x=(t-startTime)/(endTime-startTime)*w;
    ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,h);ctx.stroke();
  }

  ctx.strokeStyle="#d9e1e7";
  const major=.2;
  const firstMajor=Math.ceil(startTime/major)*major;
  for(let t=firstMajor;t<=endTime+1e-9;t+=major){
    const x=(t-startTime)/(endTime-startTime)*w;
    ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,h);ctx.stroke();
  }

  const step=state.verticalGridAdc;
  const lower=Math.floor((yMin-state.baseline)/step);
  const upper=Math.ceil((yMax-state.baseline)/step);
  for(let n=lower;n<=upper;n++){
    if(n===0) continue;
    const value=state.baseline+n*step;
    const y=yFor(value,yMin,yMax,h);
    ctx.strokeStyle=(Math.abs(n)%5===0)?"#d9e1e7":"#edf1f4";
    ctx.lineWidth=(Math.abs(n)%5===0?1:.55)*dpr;
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

function drawAnnotations(start,end,dpr) {
  const anns=state.record.annotations||[];
  const w=el.ecgCanvas.width,h=el.ecgCanvas.height;
  ctx.font=11*dpr+"px sans-serif";
  for(const ann of anns){
    if(ann.sample<start||ann.sample>=end)continue;
    const x=(ann.sample-start)/(end-start-1)*w;
    ctx.strokeStyle="rgba(119,76,32,.38)";
    ctx.lineWidth=.8*dpr;
    ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,h);ctx.stroke();
    ctx.fillStyle="#76522f";
    ctx.fillText(ann.symbol||"•",x+3*dpr,14*dpr);
  }
}

function drawCaliper(sample,label,color,start,end,dpr) {
  if(sample==null||sample<start||sample>=end)return;
  const w=el.ecgCanvas.width,h=el.ecgCanvas.height;
  const x=(sample-start)/(end-start-1)*w;
  ctx.strokeStyle=color;ctx.lineWidth=1.5*dpr;ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,h);ctx.stroke();
  ctx.fillStyle=color;ctx.font="bold "+12*dpr+"px sans-serif";ctx.fillText(label,x+4*dpr,h-8*dpr);
}

function yFor(value,min,max,height){return height-(value-min)/(max-min)*height}

function restoreSession() {
  try { return JSON.parse(localStorage.getItem(SESSION_KEY)) || null; } catch { return null; }
}

function persistSession() {
  try {
    localStorage.setItem(SESSION_KEY, JSON.stringify({
      baseline_adc: state.baseline,
      calipers: state.calipers
    }));
  } catch {}
}

function showStatus(message,isError=false) {
  el.keepStatus.textContent=message;
  el.keepStatus.style.color=isError?"#9a3412":"#365f4d";
}

function requireOk(response){if(!response.ok)throw new Error("HTTP "+response.status);return response}
function integerOrNull(value){return Number.isInteger(value)?value:null}
function roundNumber(value,places=0){const p=10**places;return Math.round(Number(value)*p)/p}
function formatSigned(value){const v=roundNumber(value,2);return (v>0?"+":"")+String(v)}
function escapeHtml(value){return String(value).replace(/[&<>"']/g,ch=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[ch]))}
