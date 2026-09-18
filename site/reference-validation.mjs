export function validateReferenceIntegrity(record) {
  const checks = [];
  const push = (id, label, pass, observed, expected, note = "") => {
    checks.push({id, label, pass:Boolean(pass), observed, expected, note});
  };

  const fs = Number(record?.sampling_rate_hz);
  const raw = record?.signals?.raw;
  const filtered = record?.signals?.filtered;
  const sampleCount = Number(record?.sample_count);
  const duration = Number(record?.duration_seconds);
  const computedDuration = Array.isArray(raw) && Number.isFinite(fs) && fs > 0 ? raw.length / fs : NaN;

  push("sampling_rate", "Sampling rate", fs === 500, fs, 500, "ECG-ID Person_01/rec_1 source metadata");
  push("sample_count", "Raw sample count", Array.isArray(raw) && raw.length === sampleCount, Array.isArray(raw) ? raw.length : null, sampleCount, "Browser array must preserve the source record length");
  push("paired_channels", "Raw/filtered channel length", Array.isArray(raw) && Array.isArray(filtered) && raw.length === filtered.length, Array.isArray(filtered) ? filtered.length : null, Array.isArray(raw) ? raw.length : null, "Source raw and source-filtered channels remain aligned");
  push("duration", "Duration from samples", Number.isFinite(computedDuration) && Math.abs(computedDuration - duration) < 1e-12, computedDuration, duration, "sample_count / sampling_rate must reproduce duration");
  push("adc_resolution", "ADC resolution metadata", Number(record?.adc?.resolution_bits) === 12, Number(record?.adc?.resolution_bits), 12, "Source acquisition metadata");
  push("annotation_semantics", "Annotation event accounting",
    Number(record?.annotation_summary?.annotation_events) === (record?.annotations?.length ?? -1),
    record?.annotations?.length ?? null,
    record?.annotation_summary?.annotation_events ?? null,
    "Event count is preserved separately from annotated-beat count"
  );
  push("provenance_doi", "Source DOI", record?.provenance?.doi === "10.13026/C2J01F", record?.provenance?.doi ?? null, "10.13026/C2J01F", "Authoritative dataset identifier");
  const hashes = record?.source_files || {};
  const hashOk = ["hea","dat","atr"].every(ext => typeof hashes?.[ext]?.sha256 === "string" && hashes[ext].sha256.length === 64);
  push("source_hashes", "Source file hashes", hashOk,
    ["hea","dat","atr"].map(ext => hashes?.[ext]?.sha256 || null),
    "SHA-256 for .hea/.dat/.atr",
    "Exact downloaded source files are fingerprinted during the reproducible build"
  );

  return {
    schema:"org.openphysiologylab.reference-validation/v1",
    record_id:record?.record_id ?? null,
    dataset:record?.provenance?.dataset ?? null,
    dataset_version:record?.provenance?.dataset_version ?? null,
    checks,
    passed:checks.filter(c=>c.pass).length,
    total:checks.length,
    all_passed:checks.every(c=>c.pass)
  };
}

export function makeValidationReport({record, oplVersion, oplCommit}) {
  const integrity = validateReferenceIntegrity(record);
  return {
    ...integrity,
    generated_at_utc:new Date().toISOString(),
    opl:{
      version:oplVersion || "unknown",
      commit:oplCommit || "unknown"
    },
    source:{
      repository:record?.provenance?.repository ?? null,
      doi:record?.provenance?.doi ?? null,
      license:record?.provenance?.license ?? null,
      source_files:record?.source_files ?? {}
    },
    scope:{
      supports:[
        "source-data integrity verification",
        "sampling/time preservation",
        "raw versus source-filtered visualization",
        "baseline-relative digital amplitude measurement"
      ],
      does_not_support:[
        "diagnostic validation",
        "cardiologist gold-standard delineation",
        "NPG Lite physical voltage calibration"
      ]
    }
  };
}
