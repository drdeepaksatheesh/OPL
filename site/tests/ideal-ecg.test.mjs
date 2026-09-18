import test from "node:test";
import assert from "node:assert/strict";
import {generateIdealEcg, IDEAL_ECG_SPEC} from "../reference/ecg-id/ideal-ecg.mjs";

test("ideal ECG template is deterministic and uses declared sampling", () => {
  const a = generateIdealEcg();
  const b = generateIdealEcg();
  assert.equal(a.sampling_rate_hz, 500);
  assert.equal(a.sample_count, 3000);
  assert.deepEqual(a.signals.raw, b.signals.raw);
  assert.equal(a.provenance.teaching_only, true);
  assert.equal(a.provenance.validation_ground_truth, false);
});

test("ideal ECG exposes known PQRST landmarks and baseline", () => {
  const record = generateIdealEcg();
  assert.equal(IDEAL_ECG_SPEC.baseline_mV, 0);
  assert.equal(IDEAL_ECG_SPEC.horizontal_small_box_ms, 40);
  assert.equal(IDEAL_ECG_SPEC.vertical_small_box_mV, 0.1);
  assert.ok(record.beats.length >= 5);
  const beat = record.beats[0];
  assert.ok(beat.landmarks.p_peak < beat.landmarks.q);
  assert.ok(beat.landmarks.q < beat.landmarks.r);
  assert.ok(beat.landmarks.r < beat.landmarks.s);
  assert.ok(beat.landmarks.s < beat.landmarks.t_peak);
});

test("ideal teaching intervals are internally consistent", () => {
  const f = IDEAL_ECG_SPEC.fiducials;
  assert.equal(Math.round((f.qrs_onset_s - f.p_onset_s) * 1000), IDEAL_ECG_SPEC.teaching_measurements.pr_interval_ms);
  assert.equal(Math.round((f.qrs_end_s - f.qrs_onset_s) * 1000), IDEAL_ECG_SPEC.teaching_measurements.qrs_duration_ms);
  assert.equal(Math.round((f.t_end_s - f.qrs_onset_s) * 1000), IDEAL_ECG_SPEC.teaching_measurements.qt_interval_ms);
});
