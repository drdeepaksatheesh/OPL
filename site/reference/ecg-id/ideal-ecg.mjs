export const IDEAL_ECG_SPEC = Object.freeze({
  schema: "org.openphysiologylab.ideal-ecg/v1",
  title: "OPL idealized ECG teaching template",
  purpose: "Pedagogical P-Q-R-S-T notation and caliper practice before viewing biological recordings.",
  warning: "Synthetic teaching model — not biological data, not a diagnostic reference, and not used as validation ground truth.",
  sampling_rate_hz: 500,
  heart_rate_bpm: 75,
  rr_seconds: 0.8,
  baseline_mV: 0,
  horizontal_small_box_ms: 40,
  vertical_small_box_mV: 0.1,
  morphology: {
    p: {offset_s: -0.16, amplitude_mV: 0.15, sigma_s: 0.028},
    q: {offset_s: -0.035, amplitude_mV: -0.12, sigma_s: 0.010},
    r: {offset_s: 0, amplitude_mV: 1.0, sigma_s: 0.012},
    s: {offset_s: 0.035, amplitude_mV: -0.25, sigma_s: 0.012},
    t: {offset_s: 0.25, amplitude_mV: 0.30, sigma_s: 0.055}
  },
  fiducials: {
    p_onset_s: -0.20,
    p_peak_s: -0.16,
    p_end_s: -0.12,
    qrs_onset_s: -0.045,
    q_s: -0.035,
    r_s: 0,
    s_s: 0.035,
    qrs_end_s: 0.045,
    t_onset_s: 0.18,
    t_peak_s: 0.25,
    t_end_s: 0.34
  },
  teaching_measurements: {
    p_wave_duration_ms: 80,
    pr_interval_ms: 155,
    pr_segment_ms: 75,
    qrs_duration_ms: 90,
    st_segment_ms: 135,
    qt_interval_ms: 385,
    t_wave_duration_ms: 160,
    rr_interval_ms: 800
  }
});

export function generateIdealEcg({durationSeconds = 6, samplingRateHz = IDEAL_ECG_SPEC.sampling_rate_hz} = {}) {
  const fs = Number(samplingRateHz);
  const count = Math.round(durationSeconds * fs);
  const values = new Array(count).fill(0);
  const rTimes = [];

  // Start after enough left margin for the P wave and continue while T fits.
  for (let rTime = 0.40; rTime < durationSeconds - 0.40; rTime += IDEAL_ECG_SPEC.rr_seconds) {
    rTimes.push(rTime);
    for (const component of Object.values(IDEAL_ECG_SPEC.morphology)) {
      addGaussian(values, fs, rTime + component.offset_s, component.amplitude_mV, component.sigma_s);
    }
  }

  const beats = rTimes.map((rTime, index) => ({
    index,
    r_time_s: rTime,
    landmarks: makeLandmarks(rTime, fs)
  }));

  return {
    schema: "org.openphysiologylab.reference-record/v1",
    record_id: "OPL-IDEAL/normal-sinus-template/v1",
    sampling_rate_hz: fs,
    duration_seconds: values.length / fs,
    sample_count: values.length,
    units: ["mV", "mV"],
    signal_names: ["Ideal ECG", "Ideal ECG"],
    adc: {
      storage_format: ["synthetic-float", "synthetic-float"],
      gain_counts_per_unit: [null, null],
      baseline: [0, 0],
      zero: [0, 0],
      resolution_bits: null,
      dataset_nominal_input_range_mV: null
    },
    signals: {
      raw: values,
      filtered: [...values]
    },
    annotations: beats.flatMap(beat => {
      const lm = beat.landmarks;
      return [
        {sample: lm.p_peak, symbol: "P", source: "ideal-model"},
        {sample: lm.q, symbol: "Q", source: "ideal-model"},
        {sample: lm.r, symbol: "R", source: "ideal-model"},
        {sample: lm.s, symbol: "S", source: "ideal-model"},
        {sample: lm.t_peak, symbol: "T", source: "ideal-model"}
      ];
    }),
    annotation_summary: {
      annotated_beats: beats.length,
      annotation_events: beats.length * 5
    },
    ideal_spec: IDEAL_ECG_SPEC,
    beats,
    source_files: {},
    provenance: {
      dataset: "OPL idealized teaching template",
      dataset_version: "v1",
      repository: "OpenPhysiologyLab",
      doi: null,
      license: "GPL-3.0 project code",
      contributor: "OpenPhysiologyLab",
      source_signal_0: "Synthetic idealized ECG",
      source_signal_1: "Same synthetic idealized ECG",
      known_preprocessing: "None. Generated deterministically in the browser from the declared model parameters.",
      annotation_status: "Landmarks are known by construction.",
      opl_transformations: ["Deterministic sum of declared Gaussian P/Q/R/S/T components"],
      teaching_only: true,
      validation_ground_truth: false
    }
  };
}

function makeLandmarks(rTime, fs) {
  const f = IDEAL_ECG_SPEC.fiducials;
  const sample = offset => Math.round((rTime + offset) * fs);
  return {
    p_onset: sample(f.p_onset_s),
    p_peak: sample(f.p_peak_s),
    p_end: sample(f.p_end_s),
    qrs_onset: sample(f.qrs_onset_s),
    q: sample(f.q_s),
    r: sample(f.r_s),
    s: sample(f.s_s),
    qrs_end: sample(f.qrs_end_s),
    t_onset: sample(f.t_onset_s),
    t_peak: sample(f.t_peak_s),
    t_end: sample(f.t_end_s)
  };
}

function addGaussian(values, fs, centerSeconds, amplitude, sigmaSeconds) {
  const center = centerSeconds * fs;
  const sigma = sigmaSeconds * fs;
  const radius = Math.ceil(sigma * 4.5);
  const start = Math.max(0, Math.floor(center - radius));
  const end = Math.min(values.length - 1, Math.ceil(center + radius));
  for (let i = start; i <= end; i++) {
    const z = (i - center) / sigma;
    values[i] += amplitude * Math.exp(-0.5 * z * z);
  }
}


export const IDEAL_LANDMARK_LABELS = Object.freeze({
  p_onset: "P onset",
  p_peak: "P peak",
  p_end: "P end",
  qrs_onset: "QRS onset",
  q: "Q",
  r: "R",
  s: "S",
  qrs_end: "QRS end",
  t_onset: "T onset",
  t_peak: "T peak",
  t_end: "T end"
});

const IDEAL_INTERVALS = Object.freeze({
  "p_onset|p_end": ["P-wave duration", "p_wave_duration_ms"],
  "p_onset|qrs_onset": ["PR interval", "pr_interval_ms"],
  "p_end|qrs_onset": ["PR segment", "pr_segment_ms"],
  "qrs_onset|qrs_end": ["QRS duration", "qrs_duration_ms"],
  "qrs_end|t_onset": ["ST segment", "st_segment_ms"],
  "qrs_onset|t_end": ["QT interval", "qt_interval_ms"],
  "t_onset|t_end": ["T-wave duration", "t_wave_duration_ms"],
  "r|r": ["RR interval", "rr_interval_ms"]
});

export function nearestIdealLandmark(record, sample, toleranceMs = 30) {
  if (!record || !Number.isInteger(sample)) return null;
  const fs = Number(record.sampling_rate_hz);
  const toleranceSamples = Math.round((Number(toleranceMs) / 1000) * fs);
  let best = null;

  for (const beat of record.beats || []) {
    for (const [key, landmarkSample] of Object.entries(beat.landmarks || {})) {
      const distance = sample - Number(landmarkSample);
      const absDistance = Math.abs(distance);
      if (absDistance > toleranceSamples) continue;
      if (!best || absDistance < best.abs_distance_samples) {
        best = {
          key,
          label: IDEAL_LANDMARK_LABELS[key] || key,
          sample: Number(landmarkSample),
          beat_index: beat.index,
          distance_samples: distance,
          distance_ms: distance / fs * 1000,
          abs_distance_samples: absDistance
        };
      }
    }
  }
  return best;
}

export function interpretIdealCalipers(record, sampleA, sampleB, toleranceMs = 30) {
  if (!record || !Number.isInteger(sampleA) || !Number.isInteger(sampleB)) {
    return {a:null,b:null,measurement:null};
  }

  let a = nearestIdealLandmark(record, sampleA, toleranceMs);
  let b = nearestIdealLandmark(record, sampleB, toleranceMs);

  if (sampleA > sampleB) {
    [a,b] = [b,a];
    [sampleA,sampleB] = [sampleB,sampleA];
  }

  let measurement = null;
  if (a && b) {
    const sameBeat = a.beat_index === b.beat_index;
    const adjacentR = a.key === "r" && b.key === "r" && b.beat_index === a.beat_index + 1;
    const pairKey = a.key + "|" + b.key;
    const definition = IDEAL_INTERVALS[pairKey];

    if (definition && (sameBeat || adjacentR)) {
      const [label, expectedKey] = definition;
      const measuredMs = (sampleB - sampleA) / Number(record.sampling_rate_hz) * 1000;
      const expectedMs = Number(IDEAL_ECG_SPEC.teaching_measurements[expectedKey]);
      measurement = {
        label,
        expected_key: expectedKey,
        measured_ms: measuredMs,
        expected_ms: expectedMs,
        error_ms: measuredMs - expectedMs,
        endpoint_error_ms: Math.abs(a.distance_ms) + Math.abs(b.distance_ms)
      };
    }
  }

  return {a,b,measurement};
}
