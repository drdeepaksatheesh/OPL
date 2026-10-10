# OPL Experimental Physiology — pilot staging branch

**Status: pilot in review.** [Launch the standalone, dependency-free lab](lab.html) by downloading the HTML file, or view its source. The review branch includes a linked historical image viewer, an explicitly synthetic interactive demo, local CSV import, two cursors and source attribution. The more complete v0.2 local development bundle also contains teaching specifications, a metadata validator, a CSV ingestion script and tests. **No third-party raw waveform data are hosted here yet.**

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


## First usable entry point — authentic source scans

Open [the browser lab](lab.html). Choose one of the frog-heart scans (2013, 2017) or the historical Marey frog-muscle figure (1892); select "View original image". These images are displayed from Wikimedia Commons with inline attribution. The physical force and time calibration of these scans is **unverified**; zoom is display magnification only. The numerical caliper demonstration is labelled **synthetic**; imported CSV is labelled **unverified**.

## v0.2 review milestones

- Standalone HTML learner on the review branch with no third-party code dependency or telemetry.
- Detailed local build has 8 source records and 5 mapped exercises, 5 passing ingestion tests, a verified desktop/mobile layout under controlled headless-browser testing, and image-linked sources.
- Remaining: acquire independently verified original binary master(s) and prove gain, scale, polarity and sample rate; complete rights review and reproducible acquisition; then commit accepted data.

Do not merge on the strength of a browser screenshot alone. Scientific and code review remain separate.
