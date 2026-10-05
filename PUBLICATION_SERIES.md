# OpenPhysiologyLab Publication Series

OpenPhysiologyLab (OPL) is an umbrella platform. Public outputs should be released as small, usable, versioned instruments that can stand alone for teaching, validation, or research and later interoperate inside the larger OPL ecosystem.

## Why this structure

A large development repository is useful to developers but is not automatically useful to students, teachers, laboratories, or reviewers. OPL therefore separates:

1. **development** — experimental code, prototypes, calibration work, failed approaches, unpublished methods;
2. **public instruments** — stable browser-facing tools that can be used without reading source code;
3. **validated releases** — frozen versions associated with abstracts, conference presentations, datasets, or papers.

The public trail should show a sequence of finished scientific contributions rather than one indefinitely unfinished application.

## Publication capsules

| Capsule | Public instrument | Minimum scientific contribution | Validation path | Integration target |
|---|---|---|---|---|
| ECG acquisition + calibration | OPL Recorder / Calibration Bench | low-cost acquisition workflow with transparent calibration | second NPG Lite, oscilloscope/function source, reference system where available | OPL Recorder |
| ECG waveform teaching | ECG Calipers / Cardiac Chart | visual measurement and conduction/morphology teaching workflow | agreement against manually measured reference tracings | ECG learning suite |
| RR pedagogy | RR Pairs + RR Triplets | visual bridge from beat-to-beat variability to descriptive statistics | deterministic test datasets + learner evaluation | HRV suite |
| Visual HRV | Visual HRV Explorer | animated and static teaching of NN intervals, RMSSD, SDNN, Poincaré geometry | reference datasets + numerical cross-checking against established software | HRV suite |
| Browser recorder | Recording Pad | low-friction acquisition interface with metadata and export | timing, sample-loss and file-integrity testing | OPL acquisition |
| Cardiac anatomy | Open Cardiac Anatomy | interactive anatomy/physiology teaching object | content validation + learner/usability study | cardiac teaching suite |
| Experimental cardiac physiology | Pig Heart Laboratory | standalone experimental-physiology workflow/simulation around real protocols | protocol/content validation; later experimental data linkage | experimental physiology suite |
| Multimodal expansion | ECG/EMG/EOG/EEG modules | reusable acquisition and visualization framework | signal-specific validation | full OPL |

## Publication ladder

A capsule may progress through:

**prototype → internal validation → public beta → abstract/demo → technical validation → teaching evaluation → paper release**

A capsule does not need to wait for the complete OPL platform.

## Public-release rule

A public module should satisfy all of the following:

- opens with minimal friction;
- teaches or measures one clearly defined thing;
- contains a visible version identifier;
- states what is and is not validated;
- includes example data where appropriate;
- exports results in an inspectable format where appropriate;
- has an independent citation target;
- can later be embedded into OPL without changing its scientific meaning.

## Paper-linked releases

Every paper should point to a frozen software version, not merely the moving default branch.

Recommended pattern:

- live tool: GitHub Pages;
- source snapshot: tagged GitHub release;
- archived snapshot: Zenodo DOI;
- validation data: versioned dataset;
- manuscript: cites the exact software version and commit.

## Naming

Use **OpenPhysiologyLab** as the umbrella identity and give individual public tools short functional names, for example:

- OPL Recorder
- OPL Calibration Bench
- OPL ECG Calipers
- OPL Cardiac Chart
- OPL RR Lab
- OPL Visual HRV
- Open Cardiac Anatomy
- OPL Experimental Heart Lab

The user should encounter the instrument first and the repository second.

## Development boundary

New experimental algorithms, unreleased calibration methods, unpublished study logic, and exploratory integrations should remain in the private development workspace until they meet the public release gate.

Public releases remain genuinely reproducible: once a capsule is published in an abstract or paper, the exact source necessary to reproduce that released capsule should be frozen and made public with its documentation and validation assets.
