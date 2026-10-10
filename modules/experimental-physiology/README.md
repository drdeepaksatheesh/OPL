# OPL Experimental Physiology — pilot staging branch

**Status: initial source and governance records only.** The complete tested v0.1 local prototype (viewer, code, CSV ingestion, four teaching lesson files, plus tests) is being staged separately for review before the rest of the module is committed. **No third-party waveform data is hosted in this branch.**

## Mission

Build a reproducible, openly accessible laboratory in which any physiology student can locate an authentic recording, inspect its method and physical calibration, measure it, describe uncertainty and cite the original author. Historical AIIMS Delhi records are optional benchmarks, not a gatekeeper for an international source archive.

## Editorial rules

1. Keep raw master files unchanged; separately hash and document every derived display copy.
2. Distinguish `RAW`, `SCAN`, `FIGURE`, `SYNTHETIC`, and `LEAD`.
3. Unknown time bases, pressure/force units and cardiac tracing polarity stay **unknown**.
4. Free-to-read figures are not automatically cleared for adaptation or redistribution.
5. Author-facing peer review and correction notes are part of the dataset.
6. Teaching and analyses require no live-animal work; do not claim existing historical experiments are approved for replication.
7. Keep an open student-accessible browser viewer separate from source provenance and rights.

## First teaching modules

- Frog sciatic nerve and skeletal muscle: twitch, tetanus, fatigue.
- Frog heart: mechanical cardiogram, interventions and recording orientation.
- Isolated rabbit jejunum: spontaneous contractions, interventions and washout.
- Nerve action potentials: giant axon recordings with stimulus currents.
- Mammalian cardiovascular pressure: original telemetric pressure series.

## Real source references

See [SOURCE_STARTERS.md](SOURCE_STARTERS.md). They are discovery records, **not packaged datasets**.

## Release gate

A waveform becomes a public teaching record only with original file, source attribution and version, proper reuse permission, SHA-256 checksum, physical time/value calibration or explicit known limits, figure/caption context and scientific review.

Code inherits the parent OPL GPL-3.0 project licence; third-party data retain their own licences.
