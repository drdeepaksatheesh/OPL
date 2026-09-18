# ECG Reference Lab — reasoning sequence

This document fixes the pedagogical and scientific order of the first OpenPhysiologyLab ECG instrument.

## Core principle

**Teach certainty first. Introduce biological uncertainty second. Never manufacture certainty to make a real recording look like the ideal model.**

The ideal and real traces have different scientific roles.

## Stage 1 — Ideal ECG notation

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

- what the symbols mean;
- what a baseline-relative amplitude means;
- what a time interval means;
- how ECG paper/grid notation works;
- where caliper endpoints are intended to be placed in an unambiguous teaching example.

It is **not** validation ground truth and is not presented as biological data.

## Stage 2 — Calipers on the ideal waveform

The learner measures the known model.

Because the baseline and landmarks are known by construction, OPL can show:

- 40 ms horizontal small boxes;
- 0.1 mV vertical small boxes;
- sample-anchored calipers;
- direct comparison of caliper measurements with the declared model values.

This establishes the ruler before biological ambiguity is introduced.

## Stage 3 — Real open ECG

Switch to a trustworthy open physiological recording with visible provenance.

The current first real source is ECG-ID / PhysioNet.

Show:

- raw digital recording;
- source-provided filtered recording;
- exact sampling information;
- source annotations with their limitations;
- dataset version, DOI, licence and record identity.

Do not force the real recording to resemble the ideal waveform.

## Stage 4 — Calipers on real data

Use the same sample-anchored time measurement system.

For vertical measurements, the user chooses a defensible local baseline when possible.

The software should distinguish:

### Baseline usable

Report:

- time;
- relative digital amplitude from the selected baseline.

### Baseline uncertain

Report:

- time;
- explicit statement that vertical amplitude is withheld because the reference baseline cannot be defended.

Do not silently invent, flatten or substitute a baseline merely to return a number.

## Stage 5 — Morphology uncertainty is not timing uncertainty

A wandering or uncertain baseline may make some morphology/amplitude measurements difficult while R peaks remain clearly identifiable.

Therefore OPL must keep separate questions separate:

1. Can I define the baseline?
2. Can I measure this wave amplitude?
3. Can I identify the R peak reliably?
4. Can I derive an RR interval reliably?

Failure of question 1 does not automatically imply failure of questions 3–4.

## Stage 6 — Bridge to RR / HRV

Once R-peak detection is validated against suitable reference annotations:

ECG → R peaks → RR intervals → NN review → HRV.

The HRV module should explicitly show why slow baseline wander can coexist with usable RR timing when R detection remains reliable.

HRV correctness requires its own validation evidence. It should not inherit credibility automatically from the morphology/caliper module.

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

The browser Reference Lab should use the existing OPL Black Opal theme by default:

- black/charcoal surfaces;
- silver-white text;
- muted gold global accent;
- emerald for pass/ready/raw;
- cyan, magenta and violet for plots/markers;
- red only for failure/error states.

Light mode remains optional.

## Paper 1 boundary

Paper 1 should use the ideal waveform only as a transparent teaching scaffold.

Scientific validation claims must be based on appropriate real/open reference sources.

The manuscript should therefore distinguish:

**Teaching-model correctness** — parameters known by construction.

from

**Reference-data validation** — OPL outputs counter-verified against independent open physiological data and annotations.
