# Paper 1 validation results — working ledger

This file records quantitative results that have already been produced by the frozen OpenPhysiologyLab Paper 1 validation workflow.

It distinguishes measured software/reference-data results from later planned validation.

## 1. PTB-XL physical-unit and timing round trip

Dataset: **PTB-XL v1.0.3**  
DOI: **10.13026/kfzx-aw45**  
Lead: **II**  
High-resolution sampling: **500 Hz**  
Benchmark selection: five records chosen at fixed quantiles of the sorted PTB-XL `ecg_id` table, independent of waveform appearance or OPL output.

Frozen records:

- ECG 1
- ECG 5470
- ECG 10926
- ECG 16386
- ECG 21837

For every benchmark record:

- 12 source leads were present;
- Lead II contained 5000 samples over 10 s;
- source physical unit was mV;
- WFDB gain was 1000 counts/mV;
- WFDB baseline was 0 counts;
- imported sample indices matched the source exactly;
- imported Lead-II physical samples matched the source exactly at the precision tested;
- the OPL time axis matched `sample / 500 Hz` exactly at the precision tested;
- exported OPL metadata retained 500 Hz, 5000 samples and mV.

Aggregate result:

- **5/5 records passed**
- maximum Lead-II sample absolute error: **0.0 mV**
- maximum time-axis absolute error: **0.0 s**
- maximum WFDB digital→physical conversion error: **0.0 mV**

### Claim supported

For the frozen five-record PTB-XL benchmark, the OPL reference-data import path preserved Lead-II sample values, sample order, 500-Hz timing and source physical mV conversion without measurable error at the benchmark precision.

### Claims not supported by this result

This result does **not** establish:

- diagnostic accuracy;
- ECG morphology/delineation accuracy;
- R-peak detection accuracy;
- NPG Lite calibration;
- analogue acquisition accuracy;
- clinical-grade performance.

## 2. LUDB clean-real teaching/reference layer

Dataset: **Lobachevsky University ECG Database (LUDB) v1.0.1**  
DOI: **10.13026/eegm-h675**  
Current frozen teaching/reference record: **LUDB 119, Lead II**

Selection is not based on visual preference alone.

Current pipeline:

1. retain records labelled sinus rhythm in LUDB metadata;
2. exclude records with listed conduction abnormalities, extrasystoles, hypertrophy, cardiac pacing, ischemia, non-specific repolarization abnormalities or other states;
3. rank eligible Lead-II recordings by annotated isoelectric-baseline stability, high-frequency noise and Lead-II orientation;
4. freeze the selected record and the complete ranked selection report.

The current selection process identified **23 eligible records** and selected record 119.

For the selected record, OPL reconstructs reference intervals directly from LUDB manual cardiologist P/QRS/T onset, peak and end sample positions.

The current interface compares unsnapped learner/manual A/B calipers against those expert reference boundaries.

### Claim supported

OPL can reproducibly expose and reconstruct LUDB cardiologist annotation geometry for a real Lead-II ECG and compare manual caliper placement with the independent reference without moving the learner's endpoints.

### Claim not supported

This is not yet a validation of an OPL automated P/QRS/T delineation algorithm.

## 3. ECG-ID imperfect-real/reference-integrity layer

Dataset: **ECG-ID Database, PhysioNet**  
Current frozen record: **Person_01 / rec_1**

The browser validation panel currently counter-checks:

- sampling rate;
- raw sample count;
- raw/source-filtered channel lengths;
- duration reconstructed from samples;
- ADC-resolution metadata;
- annotation event count;
- source DOI;
- source file hashes.

Current browser/source-integrity result: **8/8 checks passed** for the frozen record.

This stage also implements the explicit measurement rule:

- defensible local baseline → time + relative amplitude;
- baseline uncertain → retain time, withhold vertical amplitude.

### Claim supported

The frozen ECG-ID record, provenance metadata and paired source channels are internally traceable through the OPL browser package, and the interface preserves explicit uncertainty rather than forcing a vertical amplitude result.

## 4. Synthetic teaching model

The idealized OPL trace is a teaching scaffold, not validation ground truth.

At 500 Hz it uses sample-compatible declared values:

- rate: 75 bpm;
- RR: 800 ms;
- PR: 160 ms;
- QRS: 90 ms;
- QT: 400 ms;
- baseline: 0 mV;
- grid: 40 ms × 0.1 mV.

Manual calipers are not snapped. OPL interprets nearby interval boundaries and reports manual placement against the known model.

## 5. Next quantitative result required

The next independent benchmark should be a frozen **MIT-BIH Arrhythmia Database R-peak / beat-timing benchmark**.

Required outputs:

- predeclared record selection;
- no per-record threshold tuning;
- expert reference beat annotations;
- matching tolerance declared before running;
- sensitivity;
- positive predictive value;
- timing-error distribution;
- false-positive and false-negative counts;
- failure examples preserved;
- algorithm and OPL commit frozen with the result.

That benchmark is the evidence bridge required before RR/NN/HRV becomes a validated OPL analysis layer.
