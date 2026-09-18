# OPL Reference-First Strategy

## Phase 1 identity

OpenPhysiologyLab should first mature as a **reference-data physiology visualization and interpretation platform**.

The immediate objective is not to prove a new acquisition device.

The immediate objective is to make trusted physiological datasets understandable, inspectable, measurable, and teachable.

## Core proposition

**Trusted open data → transparent visual analysis → understandable physiology → reproducible learning/research workflow**

A Reference Lab should let a user move from the waveform to the physiological concept without hiding the signal-processing chain.

## Why reference-first

Reference-first development has several advantages:

- does not depend on local recruitment or local data quality;
- can use datasets with international provenance and established citations;
- permits exact reproduction by reviewers, teachers, and laboratories worldwide;
- allows software validation before hardware validation;
- minimizes cost during early development;
- creates a strong case for later equipment funding;
- keeps OPL useful regardless of which acquisition system a laboratory owns.

## Phase 1 product

The public OPL should become a set of browser-facing **Reference Labs**.

Examples:

### ECG Reference Lab
raw/filtered signal → baseline → P/QRS/T geometry → intervals → R peaks → RR

### PPG & Pulse Transit Lab
raw PPG → artefact/contact effects → pulse morphology → foot/peak → PAT/PTT

### Visual HRV Lab
RR/NN → pairs/triplets → successive differences → RMSSD/SDNN → Poincaré

### Vascular Pulse Lab
central/peripheral pulse morphology → timing → propagation concepts

### Cerebral Doppler Lab
flow-velocity waveform → systolic/diastolic/mean velocity → pulsatility → autoregulation concepts

### Cardiac Mechanics Lab
ECG + pressure + volume + valves + heart sounds when suitable synchronized reference data are available

## Data-source rule

Every Reference Lab must identify:

- dataset name;
- source institution/repository;
- original publication(s);
- license/terms of use;
- signal units;
- sampling rate;
- known preprocessing;
- available annotations;
- exact records used in OPL examples/tests.

OPL must never imply that all "open" datasets have identical reuse terms.

## Reproduction rule

Where possible, a Reference Lab should reproduce a measurement or analysis from the source dataset/paper.

Use precise wording:

- reference-dataset benchmarked;
- annotation-validated;
- analysis reproduced from;
- numerically cross-checked against.

Avoid generic claims such as "validated against landmark papers" unless the actual published result was quantitatively reproduced.

## Hardware is Phase 2

Live acquisition remains part of the long-term architecture, but should not block Phase 1.

Later inputs may include:

- NPG Lite;
- PowerLab;
- BioAmp/BIOPAC or other systems;
- serial devices;
- uploaded CSV/WFDB;
- browser Web Serial devices.

The same Reference Lab interface should accept:

1. trusted reference data;
2. demo data;
3. uploaded local recordings;
4. live recordings.

## Funding narrative

Phase 1 provides a low-cost proof of value:

- internationally reproducible software;
- teaching adoption;
- publications/abstracts;
- usage metrics;
- open-source release history;
- benchmark results.

Hardware funding can then be justified as the next scientific step:

**reference-data physiology → acquisition validation → live experimental physiology**

## Publication model

Do not publish every module automatically.

A standalone paper requires:
- a distinct physiological or educational question;
- an independently useful tool;
- a distinct benchmark/validation/evaluation;
- a primary result not already reported elsewhere.

The integrated OPL platform paper should synthesize the matured Reference Labs rather than republish their individual results.

## Phase-1 success criterion

OPL succeeds before owning any new hardware if a student, teacher, or researcher anywhere can:

1. open a trusted physiological recording;
2. see what is raw and what is processed;
3. reproduce the key measurement;
4. understand why the measurement matters physiologically;
5. cite the original data and the OPL release used to analyze it.


## Open-source and visible-attribution rule

OPL Phase 1 is fully open-source.

Every public Reference Lab must visibly display, inside the application:

- dataset name;
- source repository/institution;
- original investigators or consortium where available;
- primary associated publication(s);
- dataset DOI or permanent identifier where available;
- license or reuse terms;
- exact record(s) or subset used;
- any transformations performed by OPL;
- OPL version used for the analysis.

Attribution must not be hidden only in a README or source-code comment.

A learner should be able to answer, from the tool itself:

> Where did this signal come from, who produced it, what am I allowed to do with it, and what did OPL change?

Where redistribution is not permitted, OPL should link to or fetch from the authoritative source rather than republishing the waveform.

Where redistribution is permitted, OPL may bundle selected examples while preserving the original license and attribution requirements.

The OPL source code for released Reference Labs should remain openly inspectable and versioned so that the visualization and analysis can be independently reproduced.
