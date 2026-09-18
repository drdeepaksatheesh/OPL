import test from "node:test";
import assert from "node:assert/strict";
import {
  sampleToMs,
  durationMs,
  deltaAdc,
  median,
  validateReferenceRecord,
  makeExportPackage,
  importExportPackage
} from "../reference-lab-core.mjs";

const record = {
  record_id: "test/rec",
  sampling_rate_hz: 500,
  duration_seconds: 0.008,
  units: ["mV","mV"],
  adc: {resolution_bits: 12, zero: [0,0]},
  signals: {raw: [0,10,20,30], filtered: [0,8,18,28]},
  annotations: [],
  source_files: {},
  provenance: {dataset: "Test", doi: "test"}
};

test("500 Hz maps one sample to 2 ms", () => {
  assert.equal(sampleToMs(1, 500), 2);
  assert.equal(durationMs(10, 52, 500), 84);
});

test("baseline-relative amplitude preserves sign", () => {
  assert.equal(deltaAdc(1450, 0), 1450);
  assert.equal(deltaAdc(-250, 0), -250);
  assert.equal(deltaAdc(1800, 2050), -250);
});

test("median handles even and odd samples", () => {
  assert.equal(median([3,1,2]), 2);
  assert.equal(median([4,1,3,2]), 2.5);
});

test("reference record validation rejects mismatched channels", () => {
  assert.equal(validateReferenceRecord(record), true);
  assert.throws(() => validateReferenceRecord({...record, signals:{raw:[1],filtered:[1,2]}}));
});

test("export package round-trips record and session", () => {
  const pkg = makeExportPackage({
    record,
    baseline: 7,
    calipers: {a:1,b:3},
    oplVersion: "test",
    oplCommit: "abc123"
  });
  const restored = importExportPackage(pkg);
  assert.equal(pkg.opl.commit, "abc123");
  assert.equal(restored.record.record_id, record.record_id);
  assert.equal(restored.session.baseline_adc, 7);
  assert.deepEqual(restored.session.calipers, {a:1,b:3});
});
