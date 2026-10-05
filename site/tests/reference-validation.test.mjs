import test from "node:test";
import assert from "node:assert/strict";
import {validateReferenceIntegrity, makeValidationReport} from "../reference-validation.mjs";

const record = {
  record_id:"ECG-ID/Person_01/rec_1",
  sampling_rate_hz:500,
  duration_seconds:20,
  sample_count:10000,
  adc:{resolution_bits:12},
  signals:{
    raw:Array.from({length:10000},(_,i)=>i%4096),
    filtered:Array.from({length:10000},(_,i)=>(i+1)%4096)
  },
  annotations:Array.from({length:20},(_,i)=>({sample:i*400,symbol:i%2===0?"N":"t"})),
  annotation_summary:{annotated_beats:10,annotation_events:20},
  provenance:{
    dataset:"ECG-ID Database",
    dataset_version:"1.0.0",
    repository:"PhysioNet",
    doi:"10.13026/C2J01F",
    license:"Open Data Commons Attribution License v1.0"
  },
  source_files:{
    hea:{sha256:"a".repeat(64)},
    dat:{sha256:"b".repeat(64)},
    atr:{sha256:"c".repeat(64)}
  }
};

test("ECG-ID integrity checks pass for expected reference structure",()=>{
  const result=validateReferenceIntegrity(record);
  assert.equal(result.total,8);
  assert.equal(result.passed,8);
  assert.equal(result.all_passed,true);
});

test("integrity checks fail visibly when source representation changes",()=>{
  const broken={
    ...record,
    sampling_rate_hz:250,
    signals:{...record.signals,filtered:record.signals.filtered.slice(1)}
  };
  const result=validateReferenceIntegrity(broken);
  assert.equal(result.all_passed,false);
  assert.ok(result.checks.some(c=>c.id==="sampling_rate"&&!c.pass));
  assert.ok(result.checks.some(c=>c.id==="paired_channels"&&!c.pass));
});

test("validation report preserves OPL and source provenance",()=>{
  const report=makeValidationReport({record,oplVersion:"0.1",oplCommit:"abc123"});
  assert.equal(report.opl.version,"0.1");
  assert.equal(report.opl.commit,"abc123");
  assert.equal(report.source.doi,"10.13026/C2J01F");
  assert.equal(report.source.source_files.dat.sha256,"b".repeat(64));
  assert.equal(report.scope.does_not_support.includes("diagnostic validation"),true);
});
