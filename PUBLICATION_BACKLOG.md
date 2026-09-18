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

## Tier A — build first

### A1. OPL Calibration Bench / Recorder

**Minimum publishable unit:** reproducible low-cost acquisition and calibration workflow.

**Why first:** every later physiological measurement depends on knowing what the acquisition chain is actually doing.

**Abstract-ready evidence:**
- two NPG Lite units;
- known input signals;
- amplitude scaling;
- sampling/timing characterization;
- clipping/headroom behavior;
- within-device repeatability;
- between-device agreement;
- raw-data integrity.

**Full-paper expansion:**
- reference acquisition comparison;
- longer recordings;
- additional amplitudes/frequencies;
- ECG simulator or biological signal;
- inter-laboratory replication.

**Possible paper framing:**

> A reproducible calibration and quality-control workflow for low-cost physiological signal acquisition using NPG Lite and OpenPhysiologyLab

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

### A3. OPL Cardiac Chart

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

**measurement chain → calibration → recording → visual signal interpretation → beat-to-beat variability → HRV → integrated cardiac physiology → multimodal physiology**

Each paper should make sense alone.

Together, they should reveal the larger OpenPhysiologyLab system.
