import test from "node:test";
import assert from "node:assert/strict";
import {generateIdealEcg, IDEAL_ECG_SPEC, nearestIdealLandmark, interpretIdealCalipers} from "../reference/ecg-id/ideal-ecg.mjs";

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


test("manual calipers are interpreted against nearby declared landmarks without moving them", () => {
  const record = generateIdealEcg();
  const beat = record.beats[1];

  const a = beat.landmarks.p_onset - 5;   // 10 ms early at 500 Hz
  const b = beat.landmarks.qrs_onset + 4; // 8 ms late
  const result = interpretIdealCalipers(record, a, b, 30);

  assert.equal(result.a.label, "P onset");
  assert.equal(result.b.label, "QRS onset");
  assert.equal(result.measurement.label, "PR interval");
  assert.equal(result.measurement.expected_ms, 155);
  assert.equal(result.measurement.measured_ms, 173);
  assert.equal(result.measurement.error_ms, 18);
});

test("landmark assist declines to invent an interval for unrelated points", () => {
  const record = generateIdealEcg();
  const beat = record.beats[1];

  const pPeak = beat.landmarks.p_peak;
  const tPeak = beat.landmarks.t_peak;
  const result = interpretIdealCalipers(record, pPeak, tPeak, 30);

  assert.equal(result.a.label, "P peak");
  assert.equal(result.b.label, "T peak");
  assert.equal(result.measurement, null);
});

test("nearest landmark reports placement error in milliseconds", () => {
  const record = generateIdealEcg();
  const beat = record.beats[1];
  const sample = beat.landmarks.r + 6; // 12 ms late at 500 Hz
  const hit = nearestIdealLandmark(record, sample, 30);

  assert.equal(hit.label, "R");
  assert.equal(hit.distance_ms, 12);
});
