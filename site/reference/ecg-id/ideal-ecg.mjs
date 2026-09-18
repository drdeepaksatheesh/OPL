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
    pr_interval_ms: 155,
    qrs_duration_ms: 90,
    qt_interval_ms: 385,
    pr_segment_ms: 75,
    st_segment_ms: 135,
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
