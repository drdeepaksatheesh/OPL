const PEAK_SYMBOL = Object.freeze({P:"p", QRS:"N", T:"t"});

export function parseLudbWaves(record) {
  const annotations = [...(record?.annotations || [])]
    .filter(a => Number.isInteger(Number(a.sample)))
    .sort((a,b)=>Number(a.sample)-Number(b.sample));

  const waves = [];
  for (let i=0;i<annotations.length;i++) {
    const onset = annotations[i];
    if (onset.symbol !== "(" || !["P","QRS","T"].includes(onset.wave)) continue;

    let peak = null;
    let end = null;
    for (let j=i+1;j<annotations.length;j++) {
      const event = annotations[j];
      if (event.symbol === ")" && event.wave === onset.wave) {
        end = event;
        break;
      }
      if (event.symbol === PEAK_SYMBOL[onset.wave] && event.wave === onset.wave) {
        peak = event;
      }
      if (event.symbol === "(" && event.wave === onset.wave) break;
    }
    if (!end) continue;

    waves.push({
      wave:onset.wave,
      onset_sample:Number(onset.sample),
      peak_sample:peak ? Number(peak.sample) : null,
      end_sample:Number(end.sample),
      onset_source:onset.source || null,
      peak_source:peak?.source || null,
      end_source:end.source || null
    });
  }
  return waves;
}

export function buildLudbReferenceIntervals(record) {
  const fs = Number(record?.sampling_rate_hz);
  if (!Number.isFinite(fs) || fs <= 0) return [];

  const waves = parseLudbWaves(record);
  const pWaves = waves.filter(w=>w.wave==="P");
  const qrsWaves = waves.filter(w=>w.wave==="QRS");
  const tWaves = waves.filter(w=>w.wave==="T");

  const beats = qrsWaves.map((qrs,index)=>{
    const p = [...pWaves]
      .filter(w=>w.end_sample < qrs.onset_sample && qrs.onset_sample - w.end_sample <= fs*0.5)
      .sort((a,b)=>b.end_sample-a.end_sample)[0] || null;
    const t = [...tWaves]
      .filter(w=>w.onset_sample > qrs.end_sample && w.onset_sample - qrs.end_sample <= fs*0.7)
      .sort((a,b)=>a.onset_sample-b.onset_sample)[0] || null;
    return {index,p,qrs,t};
  });

  const intervals = [];
  const add=(beatIndex,key,label,startSample,endSample)=>{
    if (!Number.isInteger(startSample) || !Number.isInteger(endSample) || endSample<=startSample) return;
    intervals.push({
      beat_index:beatIndex,
      key,label,
      start_sample:startSample,
      end_sample:endSample,
      reference_ms:(endSample-startSample)/fs*1000
    });
  };

  for (const beat of beats) {
    if (beat.p) {
      add(beat.index,"p_wave","P-wave duration",beat.p.onset_sample,beat.p.end_sample);
      add(beat.index,"pr_interval","PR interval",beat.p.onset_sample,beat.qrs.onset_sample);
      add(beat.index,"pr_segment","PR segment",beat.p.end_sample,beat.qrs.onset_sample);
    }
    add(beat.index,"qrs_duration","QRS duration",beat.qrs.onset_sample,beat.qrs.end_sample);
    if (beat.t) {
      add(beat.index,"st_segment","ST segment",beat.qrs.end_sample,beat.t.onset_sample);
      add(beat.index,"qt_interval","QT interval",beat.qrs.onset_sample,beat.t.end_sample);
      add(beat.index,"t_wave","T-wave duration",beat.t.onset_sample,beat.t.end_sample);
    }
  }

  for (let i=0;i<beats.length-1;i++) {
    const a=beats[i].qrs.peak_sample;
    const b=beats[i+1].qrs.peak_sample;
    add(i,"rr_interval","R–R interval",a,b);
  }

  return intervals;
}

export function interpretLudbCalipers(record, sampleA, sampleB, toleranceMs=40) {
  if (!record || !Number.isInteger(sampleA) || !Number.isInteger(sampleB)) {
    return {measurement:null};
  }
  if (sampleA>sampleB) [sampleA,sampleB]=[sampleB,sampleA];

  const fs=Number(record.sampling_rate_hz);
  const toleranceSamples=Math.round(toleranceMs/1000*fs);
  const intervals=buildLudbReferenceIntervals(record);

  let best=null;
  for (const interval of intervals) {
    const startError=sampleA-interval.start_sample;
    const endError=sampleB-interval.end_sample;
    if (Math.abs(startError)>toleranceSamples || Math.abs(endError)>toleranceSamples) continue;
    const score=Math.abs(startError)+Math.abs(endError);
    if (!best || score<best.score) {
      best={
        ...interval,
        score,
        measured_ms:(sampleB-sampleA)/fs*1000,
        error_ms:(sampleB-sampleA)/fs*1000-interval.reference_ms,
        start_error_ms:startError/fs*1000,
        end_error_ms:endError/fs*1000
      };
    }
  }

  return {measurement:best};
}

export function summarizeLudbReferenceIntervals(record) {
  const intervals=buildLudbReferenceIntervals(record);
  const groups={};
  for (const item of intervals) {
    if (!groups[item.key]) groups[item.key]=[];
    groups[item.key].push(item.reference_ms);
  }

  const rows=[];
  const order=[
    ["p_wave","P-wave duration"],
    ["pr_interval","PR interval"],
    ["pr_segment","PR segment"],
    ["qrs_duration","QRS duration"],
    ["st_segment","ST segment"],
    ["qt_interval","QT interval"],
    ["t_wave","T-wave duration"],
    ["rr_interval","R–R interval"]
  ];

  for (const [key,label] of order) {
    const values=groups[key] || [];
    if (!values.length) continue;
    const sorted=[...values].sort((a,b)=>a-b);
    rows.push({
      key,label,
      n:values.length,
      median_ms:median(sorted),
      min_ms:sorted[0],
      max_ms:sorted[sorted.length-1]
    });
  }
  return rows;
}

export function makeLudbReferenceMeasurementReport(record) {
  return {
    schema:"org.openphysiologylab.ludb-reference-measurements/v1",
    record_id:record?.record_id ?? null,
    dataset:record?.provenance?.dataset ?? null,
    dataset_version:record?.provenance?.dataset_version ?? null,
    doi:record?.provenance?.doi ?? null,
    lead:record?.provenance?.lead ?? "II",
    sampling_rate_hz:record?.sampling_rate_hz ?? null,
    annotation_status:record?.provenance?.annotation_status ?? null,
    intervals:buildLudbReferenceIntervals(record),
    summary:summarizeLudbReferenceIntervals(record),
    note:"Durations are derived directly from LUDB cardiologist annotation sample positions. They are expert-reference measurements, not OPL automated delineation outputs."
  };
}

function median(values){
  if(!values.length)return null;
  const mid=Math.floor(values.length/2);
  return values.length%2?values[mid]:(values[mid-1]+values[mid])/2;
}
