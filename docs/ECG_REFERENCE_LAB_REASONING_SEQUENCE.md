# ECG Reference Lab — reasoning sequence

This document fixes the pedagogical and scientific order of the first OpenPhysiologyLab ECG instrument.

## Core principle

**Teach the model first, demonstrate the model in clean biology second, then introduce biological uncertainty. Never manufacture certainty to make an imperfect recording look like the model.**

The three waveform stages have deliberately different scientific roles.

## Stage 1 — Synthetic ideal ECG notation

Use a deterministic OPL-generated teaching waveform with declared:

- P, Q, R, S and T landmarks;
- isoelectric baseline;
- sampling rate;
- RR interval;
- PR interval;
- QRS duration;
- QT interval;
- ECG-style grid calibration.

The ideal waveform is explicitly synthetic.

It exists to teach:

- what P-Q-R-S-T notation means;
- what baseline-relative amplitude means;
- what a time interval means;
- how the ECG paper/grid ruler works;
- where caliper endpoints are intended to be placed in an unambiguous model.

It is **not** biological validation ground truth.

## Stage 2 — Clean real ECG

Move next to a genuine open biological ECG that closely resembles the ideal model.

The first OPL clean-real bridge is:

- LUDB v1.0.1 / PhysioNet;
- record 119;
- Lead II;
- 500 Hz;
- source amplitude in physical mV;
- P, QRS and T peaks/boundaries manually delineated by LUDB cardiologists.

The example is not selected merely because it looks attractive.

OPL first applies a predeclared metadata eligibility rule:

- sinus rhythm;
- no listed conduction abnormality;
- no listed extrasystole;
- no listed hypertrophy;
- no cardiac pacing;
- no listed ischemia;
- no nonspecific repolarization abnormality;
- no other listed state.

Eligible Lead-II records are then ranked by:

- stability of cardiologist-delineated PR/TP isoelectric segments;
- high-frequency noise;
- textbook-consistent polarity.

The frozen selection report is preserved with the build.

### Pedagogical purpose

This stage demonstrates that the textbook morphology is not merely an artificial drawing.

The learner uses the same conceptual ruler on real physiology:

- 40 ms horizontal small boxes;
- 0.1 mV vertical small boxes;
- real biological waveform;
- physical mV;
- cardiologist-delineated landmarks;
- a real isoelectric-reference estimate derived from annotated PR/TP regions.

The learner should understand the distinction:

> The synthetic trace defines the model.  
> The clean LUDB trace demonstrates that real biology can approximate the model.

## Stage 3 — Imperfect real ECG

Only after the learner has seen a clean real trace should OPL introduce a recording in which baseline and signal imperfections are more obvious.

The initial source is ECG-ID / PhysioNet.

Show:

- original digital recording;
- source-provided filtered recording;
- exact sampling information;
- source annotations with their documented limitations;
- dataset version, DOI, licence and record identity.

Do not force this recording to resemble the clean LUDB example.

## Stage 4 — Calipers and baseline uncertainty

Use the same sample-anchored time measurement system across all three stages.

### Synthetic ideal

Baseline is known by construction.

Report time and model mV.

### Clean real LUDB

Estimate the biological isoelectric reference from the cardiologist-delineated PR/TP regions.

Report time and physical mV relative to that reference.

### Imperfect real ECG

Use a local digital baseline only when it can be defended.

If the baseline is usable, report:

- time;
- relative digital amplitude from the selected baseline.

If the baseline is uncertain, report:

- time;
- explicit statement that vertical amplitude is withheld.

Do not silently invent, flatten or substitute a baseline merely to return a number.

## Stage 5 — Morphology uncertainty is not timing uncertainty

A wandering or uncertain baseline may make some morphology/amplitude measurements difficult while R/QRS timing remains identifiable.

Therefore OPL keeps separate questions separate:

1. Can I define the baseline?
2. Can I measure this wave amplitude?
3. Can I identify the beat fiducial reliably?
4. Can I derive an RR interval reliably?

Failure of question 1 does not automatically imply failure of questions 3–4.

## Stage 6 — Bridge to RR / HRV

Once R-peak detection is independently validated against suitable reference annotations:

ECG → R peaks → RR intervals → NN review → HRV.

The HRV module should explicitly demonstrate why slow baseline wander can coexist with usable RR timing when R detection remains reliable.

HRV correctness requires its own validation evidence. It does not inherit credibility automatically from the morphology/caliper module.

## Stage 7 — Later live acquisition

Only after the reference-data workflow is established should hardware recordings feed the same interface.

A later teaching/application example can include:

- resting supine/lying ECG;
- transition to standing;
- RR/HRV response;
- NPG Lite acquisition;
- OPL visualization and analysis.

This is a later acquisition/physiology application layer and is not part of the first reference-data validation claim.

## Visual identity

The browser Reference Lab uses the existing OPL Black Opal theme by default:

- black/charcoal surfaces;
- silver-white text;
- muted gold global accent;
- emerald for pass/ready and biological traces;
- cyan, magenta and violet for models/markers;
- red only for failure/error states.

Light mode remains optional.

## Paper 1 boundary

Paper 1 must distinguish three evidentiary roles:

### Teaching-model correctness
Parameters of the synthetic ECG are known by construction.

### Clean-real reference demonstration
The LUDB example is independent biological data in physical units with manual cardiologist delineation. Its selection method is reproducible and preserved.

### Reference-data validation
Quantitative validation claims are counter-verified against appropriate independent open physiological data, metadata and annotations.

The clean-real example is not called “normal ground truth” merely because it looks textbook-like. It is a reproducibly selected biological bridge between the model and messier recordings.
