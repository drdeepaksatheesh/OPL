# OPL Publication Backlog

This backlog treats OpenPhysiologyLab as a **series of independently useful scientific instruments** rather than a single all-or-nothing software paper.

The aim is to create a visible scholarly trail while the larger platform continues to evolve.

## Priority principle

Prefer work that:

1. can be used by another laboratory quickly;
2. has a narrow and defensible claim;
3. can be validated with equipment already available or inexpensive to obtain;
4. creates infrastructure for later OPL studies;
5. can produce an abstract before it produces a full paper.

---

## Tier A — build first: reference physiology

### A1. OPL ECG Reference Lab

**Minimum publishable unit:** a browser-accessible ECG teaching and analysis workflow benchmarked against trusted public reference datasets.

**Why first:** ECG provides unusually strong open datasets with calibrated waveforms, expert beat annotations, raw-versus-filtered examples, and waveform delineation. It allows OPL to establish its software, visualization, measurement, and provenance model without requiring new subject recruitment or new hardware.

**Core evidence:**
- ECG-ID for raw-versus-filtered understanding;
- PTB-XL for physical-unit and multilead handling;
- MIT-BIH for R-peak/RR benchmarking;
- LUDB later for waveform delineation;
- fixed analysis version and predeclared benchmark rules;
- transparent reporting of failures as well as successes.

**Possible paper framing:**

> OpenPhysiologyLab ECG: design and reference-dataset validation of a transparent, baseline-relative ECG teaching and analysis workflow

---

### A2. OPL Visual HRV

**Minimum publishable unit:** browser tool that converts RR/NN data into visible, stepwise HRV concepts.

**Independent of acquisition hardware:** yes.

**Abstract-ready evidence:**
- numerical agreement with reference calculations;
- expert content validation;
- small learner usability pilot.

**Full-paper expansion:**
- randomized or crossover teaching comparison;
- pre/post conceptual assessment;
- cognitive-load/usability measures.

**Possible paper framing:**

> From RR intervals to Poincaré geometry: a visual interactive approach to teaching heart-rate variability

---

### A3. OPL PPG & Pulse Transit Lab

**Minimum publishable unit:** transparent visual analysis of trusted ECG + PPG reference recordings from pulse morphology through pulse-arrival/transit timing.

**Independent value:** introduces vascular timing and optical pulse physiology rather than extending ECG morphology.

**Potential evidence:**
- raw multi-site PPG;
- synchronized ECG;
- motion/contact-pressure context;
- reference timing/annotations where available;
- numerical cross-checks against published definitions.

**Possible paper framing:**

> A visual reference-data laboratory for teaching photoplethysmography and cardiovascular pulse timing

---

### A4. OPL Cardiac Chart

**Minimum publishable unit:** synchronized interactive cardiac-cycle timeline.

**Abstract-ready evidence:**
- expert validation of phase relationships;
- deterministic timing model;
- usability demonstration.

**Full-paper expansion:**
- student learning study;
- comparison with conventional Wiggers-diagram teaching.

**Possible paper framing:**

> An interactive time-linked cardiac-cycle chart for integrating electrical and mechanical physiology

---

## Tier B — independent teaching objects

### B1. Open Cardiac Anatomy

Structure-function teaching object that can later link directly to ECG, vectors, conduction and cardiac-cycle modules.

Potential outputs:
- educational software abstract;
- expert-validated digital learning resource;
- student learning/usability paper.

### B2. OPL RR Lab

RR pairs and RR triplets as a focused visual-statistics tool.

Potential outputs:
- small physiology-education abstract;
- methods/teaching note;
- later bundled into Visual HRV.

This is deliberately allowed to exist both independently and as a component of Visual HRV.

### B3. ECG Calipers

Interactive measurement and morphology/conduction learning from real or demonstration ECG.

Potential outputs:
- teaching-tool abstract;
- measurement-agreement study;
- later ECG morphology/conduction teaching paper.

---

## Tier C — hardware acquisition and experimental physiology

### C0. OPL Calibration Bench / Recorder

**Deferred until the reference-data platform is mature enough to justify hardware funding and acquisition studies.**

Scientific contribution:
- low-cost acquisition;
- sampling/timing integrity;
- clipping/headroom;
- device-to-device repeatability;
- optional physical calibration;
- integration of live recordings into already validated Reference Labs.

This becomes a stronger paper because it plugs hardware into an established analysis environment rather than trying to validate hardware and software simultaneously.

Possible framing:

> Low-cost ECG acquisition with NPG Lite and OpenPhysiologyLab: device characterization, reproducibility and implementation for physiology education

---

## Tier C — experimental physiology

### C1. Experimental Heart Lab

Standalone experimental-cardiac-physiology teaching instrument.

Start with:
- preparation;
- recording chain;
- baseline trace;
- intervention;
- predicted/observed response;
- interpretation.

Later connect real recordings.

### C2. Skeletal Muscle Laboratory

Candidate modules:
- simple muscle twitch;
- stimulus-strength relationship;
- paired stimuli;
- summation;
- tetanus;
- fatigue;
- length-tension.

### C3. Autonomic / vascular experimental modules

Add only when the underlying protocol and data pathway are mature.

---

## Tier D — integrated platform papers

These should come **after** the smaller trail exists.

### D1. OpenPhysiologyLab platform paper

Integrate validated acquisition, visualization, analysis and teaching modules.

Possible framing:

> OpenPhysiologyLab: an open, modular platform for physiological signal acquisition, analysis and education

### D2. ECG technical-validation paper

Use the established Calibration Bench + Recorder + ECG analysis chain.

### D3. Multimodal OPL paper

ECG + EMG + EOG + EEG only after channel timing, bandwidth and acquisition behavior are validated.

---

## Abstract-first workflow

For every capsule:

1. freeze a narrow question;
2. build the minimum usable instrument;
3. generate a small validation dataset;
4. submit an abstract/demo;
5. collect user feedback;
6. improve;
7. perform the stronger validation;
8. publish the full paper;
9. archive the exact paper version;
10. integrate the mature capsule back into OPL.

The abstract is not the end product. It is a timestamped scholarly waypoint.

---

## What not to do

- wait for the whole OPL ecosystem to be complete;
- bundle unrelated innovations merely because they share code;
- make validation claims broader than the experiment;
- expose unreleased research logic just to appear "open";
- confuse a GitHub repository with an accessible teaching product;
- change the software used in a paper without preserving the exact published version.

---

## Long-term scholarly narrative

The intended sequence should become visible in the literature:

**trusted reference data → transparent visual analysis → reproducible physiology → independent Reference Labs → integrated OPL → acquisition validation → live experimental physiology**

Each paper should make sense alone.

Together, they should reveal the larger OpenPhysiologyLab system.
