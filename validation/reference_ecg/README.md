# Reference ECG validation for OPL

This directory defines a reproducible way to test OpenPhysiologyLab against trusted open ECG data before using NPG Lite recordings to make physical-unit claims.

## What this does — and does not — validate

A digital reference ECG can validate:

- file ingestion;
- time axis and sampling-rate handling;
- preservation of physical amplitude units;
- filtering behavior;
- R-peak detection;
- RR/HR/HRV calculations;
- ECG-wave delineation where expert annotations are available;
- numerical scale invariance of analysis code.

A digital reference ECG **cannot by itself calibrate the NPG Lite analogue front end** because it bypasses the electrodes, analogue amplifier, ADC and device-specific gain.

That distinction creates two useful OPL validation levels.

### Level 1 — Reference-dataset verified

For medical-education and research-prototyping users who want a low-friction workflow.

Run trusted open ECGs with known physical units and/or expert annotations through OPL without tuning the algorithm to individual records.

Recommended references:

1. **PTB-XL** — primary amplitude/time reference
   - 12-lead clinical ECG
   - 500 Hz high-resolution records
   - 16-bit waveform data
   - 1 microvolt/LSB
   - Lead II available directly
   - useful for testing mV handling, plotting, filtering and 12-lead compatibility

2. **MIT-BIH Arrhythmia Database** — primary beat-detection reference
   - 48 half-hour two-channel records
   - 360 Hz
   - 11-bit over a 10 mV range
   - expert-resolved beat annotations
   - useful for R-peak / RR detection benchmarking

3. **LUDB v1.0.1** — primary ECG-delineation reference
   - 200 10-second 12-lead ECGs
   - 500 Hz
   - cardiologist-marked P, QRS and T boundaries/peaks
   - useful later for ECG Calipers and morphology/delineation validation

The first OPL reference panel should use PTB-XL Lead II because its 500 Hz sampling rate matches the current OPL/NPG workflow and its physical scaling is explicitly documented.

### Level 2 — End-to-end electrically calibrated

For laboratories that want stronger acquisition validation.

Replay a known ECG waveform or calibrated test waveform through a DAC/arbitrary-waveform generator/ECG simulator into NPG Lite, then compare:

known source voltage -> NPG Lite ADC -> OPL -> reconstructed voltage

This tests the complete hardware + software chain.

An oscilloscope may be used to independently verify the applied waveform but is not required for ordinary educational use once a device/firmware calibration profile has been adequately characterized.

## Proposed user-facing claim

A normal user should not need an oscilloscope.

OPL can expose a simple status such as:

- **Reference-dataset verified** — OPL software calculations passed the bundled reference suite.
- **Device profile calibrated** — this NPG Lite hardware/firmware profile has a documented ADC-to-voltage conversion and tolerance.
- **Locally calibrated** — the laboratory performed its own end-to-end electrical calibration.

None of these statuses imply diagnostic medical-device approval.

## Blind-test rule

For benchmark datasets:

1. freeze the OPL algorithm/version;
2. select records using a predeclared rule;
3. do not tune thresholds per record;
4. run the complete set;
5. compare outputs to reference annotations/physical values;
6. report failures as well as successes;
7. only then revise the algorithm;
8. preserve the original result in Git history.

This prevents the reference dataset from becoming a training set by accident.

## First experiment

### PTB-XL smoke test

Use the high-resolution 500 Hz records.

- select Lead II;
- preserve physical values in mV;
- export to OPL canonical recording format;
- run plotting, filtering and peak detection;
- confirm that amplitude before/after import is numerically identical within floating-point tolerance;
- check that filtering does not silently change units;
- compare results after multiplying the entire trace by 0.001, 1 and 1000 to expose hidden unit assumptions.

### MIT-BIH beat test

- run fixed OPL R-peak detection;
- compare detected peaks with reference beat annotations using a predeclared matching tolerance;
- report sensitivity, positive predictive value and timing error;
- stratify later by rhythm/noise rather than tuning record-by-record.

### LUDB delineation test

Reserved for ECG Calipers / P-QRS-T delineation work.
