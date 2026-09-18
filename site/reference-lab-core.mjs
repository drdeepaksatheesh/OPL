export function sampleToMs(sample, fs) {
  assertFinite(sample, "sample");
  assertPositive(fs, "sampling rate");
  return (sample / fs) * 1000;
}

export function durationMs(sampleA, sampleB, fs) {
  return Math.abs(sampleB - sampleA) / fs * 1000;
}

export function deltaAdc(value, baseline) {
  assertFinite(value, "value");
  assertFinite(baseline, "baseline");
  return value - baseline;
}

export function median(values) {
  if (!Array.isArray(values) || values.length === 0) throw new Error("values are required");
  const sorted = values.map(Number).filter(Number.isFinite).sort((a, b) => a - b);
  if (!sorted.length) throw new Error("values contain no finite numbers");
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

export function validateReferenceRecord(record) {
  if (!record || typeof record !== "object") throw new Error("record must be an object");
  assertPositive(record.sampling_rate_hz, "sampling_rate_hz");
  if (!record.record_id) throw new Error("record_id is required");
  if (!record.provenance || !record.provenance.dataset) throw new Error("dataset provenance is required");
  if (!record.signals || !Array.isArray(record.signals.raw) || !Array.isArray(record.signals.filtered)) {
    throw new Error("raw and filtered signal arrays are required");
  }
  if (record.signals.raw.length !== record.signals.filtered.length) {
    throw new Error("raw and filtered signals must have equal length");
  }
  if (!record.signals.raw.length) throw new Error("signal cannot be empty");
  return true;
}

export function makeExportPackage({record, baseline, calipers, oplVersion, oplCommit}) {
  validateReferenceRecord(record);
  return {
    schema: "org.openphysiologylab.reference-package/v1",
    exported_at_utc: new Date().toISOString(),
    opl: {
      version: oplVersion || "unknown",
      commit: oplCommit || "unknown"
    },
    provenance: record.provenance,
    record: {
      record_id: record.record_id,
      sampling_rate_hz: record.sampling_rate_hz,
      duration_seconds: record.duration_seconds,
      units: record.units,
      adc: record.adc,
      source_files: record.source_files,
      signals: record.signals,
      annotations: record.annotations || []
    },
    session: {
      baseline_adc: Number(baseline),
      calipers: calipers || {a: null, b: null}
    }
  };
}

export function importExportPackage(value) {
  if (!value || value.schema !== "org.openphysiologylab.reference-package/v1") {
    throw new Error("not an OPL Reference Package v1");
  }
  const record = {
    ...value.record,
    provenance: value.provenance
  };
  validateReferenceRecord(record);
  return {
    record,
    session: value.session || {baseline_adc: 0, calipers: {a: null, b: null}},
    opl: value.opl || {}
  };
}

export function downloadJson(filename, value) {
  const blob = new Blob([JSON.stringify(value, null, 2)], {type: "application/json"});
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function assertPositive(value, label) {
  assertFinite(value, label);
  if (Number(value) <= 0) throw new Error(label + " must be > 0");
}

function assertFinite(value, label) {
  if (!Number.isFinite(Number(value))) throw new Error(label + " must be finite");
}
