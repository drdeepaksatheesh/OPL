import test from "node:test";
import assert from "node:assert/strict";
import {
  parseLudbWaves,
  buildLudbReferenceIntervals,
  interpretLudbCalipers,
  summarizeLudbReferenceIntervals,
  makeLudbReferenceMeasurementReport
} from "../reference/ecg-id/ludb-calipers.mjs";

const record = {
  record_id:"LUDB/mock/LeadII",
  sampling_rate_hz:500,
  provenance:{
    dataset:"LUDB",
    dataset_version:"1.0.1",
    doi:"10.13026/eegm-h675",
    lead:"II",
    annotation_status:"manual cardiologist delineation"
  },
  annotations:[
    {sample:100,symbol:"(",wave:"P"},{sample:120,symbol:"p",wave:"P"},{sample:140,symbol:")",wave:"P"},
    {sample:180,symbol:"(",wave:"QRS"},{sample:200,symbol:"N",wave:"QRS"},{sample:225,symbol:")",wave:"QRS"},
    {sample:300,symbol:"(",wave:"T"},{sample:340,symbol:"t",wave:"T"},{sample:390,symbol:")",wave:"T"},
    {sample:500,symbol:"(",wave:"P"},{sample:520,symbol:"p",wave:"P"},{sample:540,symbol:")",wave:"P"},
    {sample:580,symbol:"(",wave:"QRS"},{sample:600,symbol:"N",wave:"QRS"},{sample:625,symbol:")",wave:"QRS"},
    {sample:700,symbol:"(",wave:"T"},{sample:740,symbol:"t",wave:"T"},{sample:790,symbol:")",wave:"T"}
  ]
};

test("LUDB waves reconstruct from manual onset/peak/end annotations",()=>{
  const waves=parseLudbWaves(record);
  assert.equal(waves.length,6);
  assert.deepEqual(waves[0],{
    wave:"P",onset_sample:100,peak_sample:120,end_sample:140,
    onset_source:null,peak_source:null,end_source:null
  });
});

test("LUDB reference intervals derive directly from annotation samples",()=>{
  const intervals=buildLudbReferenceIntervals(record);
  const byKey=Object.fromEntries(intervals.map(x=>[x.key,x]));
  assert.equal(byKey.p_wave.reference_ms,80);
  assert.equal(byKey.pr_interval.reference_ms,160);
  assert.equal(byKey.pr_segment.reference_ms,80);
  assert.equal(byKey.qrs_duration.reference_ms,90);
  assert.equal(byKey.st_segment.reference_ms,150);
  assert.equal(byKey.qt_interval.reference_ms,420);
  assert.equal(byKey.t_wave.reference_ms,180);
  assert.equal(byKey.rr_interval.reference_ms,800);
});

test("manual LUDB calipers compare with expert reference without snapping",()=>{
  // 10 ms early at onset, 8 ms late at end.
  const result=interpretLudbCalipers(record,175,229,40);
  assert.equal(result.measurement.label,"QRS duration");
  assert.equal(result.measurement.reference_ms,90);
  assert.equal(result.measurement.measured_ms,108);
  assert.equal(result.measurement.error_ms,18);
  assert.equal(result.measurement.start_error_ms,-10);
  assert.equal(result.measurement.end_error_ms,8);
});

test("LUDB summary and report remain provenance-linked",()=>{
  const summary=summarizeLudbReferenceIntervals(record);
  const qrs=summary.find(x=>x.key==="qrs_duration");
  assert.equal(qrs.n,2);
  assert.equal(qrs.median_ms,90);

  const report=makeLudbReferenceMeasurementReport(record);
  assert.equal(report.doi,"10.13026/eegm-h675");
  assert.equal(report.intervals.length,15);
  assert.match(report.note,/cardiologist annotation sample positions/i);
});
