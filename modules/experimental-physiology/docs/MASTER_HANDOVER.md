# MASTER HANDOVER — OPL Experimental Physiology

**Date:** 2026-10-11  
**Review branch:** `feature/experimental-physiology-v0.1`  
**Draft PR:** https://github.com/drdeepaksatheesh/OPL/pull/16  
**CI:** `.github/workflows/experimental-physiology-ci.yml`

## Goal
An independently inspectable, freely accessible and reusable experimental-physiology library for MBBS students. Distinguish discovery, authentic experimental image, truly raw numerical records and synthetic teaching controls. This initiative is not an audit of a single institution.

## Current source of truth
`modules/experimental-physiology/`: `web/` dependency-free reference viewer, `data/sources.json` international source references (8), `experiments/` five structured student exercises, `scripts/` checked CSV ingest plus registry verification, and `tests/` Python unit tests. `lab.html` is a convenient **standalone** browser experience (linked historical images and CSV measurement). `examples/` contains exactly one synthetic demo, never a biological claim.

## Verified tests, local development
5 Python unit tests pass, metadata validator passes, Node browser-script syntax passes. A controlled Chromium test using injected local HTML/CSS/JS rather than an HTTP server confirms source selection, correct image URL, two digital cursors measuring 116 ms on synthetic data, zero JavaScript exceptions, and no horizontal mobile overflow at 390 pixels. Network fetching external image bytes was **not tested** due container network restrictions. CI is configured but its remote result must be checked before merge.

## Evidence/rights boundaries
- Marey/McKendrick 1892 frog fatigue: historical image, Wikimedia public domain. 100-Hz chronograph in caption, force uncalibrated.
- Sachinthonakkara 2013 and 2017 frog-heart kymographs: original scans, CC BY-SA 4.0. Do not infer drug timing, heart-lever sign convention, force scale or timebase from scan pixels.
- PhysioNet SGAMP v1.0.0: 170 real squid giant axon trials across 8 axons, 125-kHz nominal sampling; original WFDB records **not acquired**. Source describes gain removal and stimulus conversion. No normalized trial approved for numerical teaching yet.
- PhysioNet Dahl rat BP: data access confirmed but apparent licensing ambiguity requires clarification before mirroring.
- DANDI macaque dataset: open source link, specific NWB not acquired/inspected.
- Rabbit jejunum published figure: rights/calibration pending.
- Virtual Frog: lead only; original files and rights unknown.

## Scientific admission checklist
1. Retain original source bytes and SHA-256; record upstream identity and version.
2. Independently verify physical units, sampling rate, channel order/gain, specimen/preparation and instrument polarity.
3. Track intervention and stimulus markers; distinguish artifact from biology.
4. Attach source citation, licence and any figure-level exceptions.
5. Keep transformations reproducible and reversible, with hashes.
6. Conduct independent scientific review before marking original waveform accepted.

## Next numbered GitHub tasks
- #17: ingest one calibrated original PhysioNet squid-axon WFDB trial.
- #18: figure-level image/rights/calibration QA.
- #19: find genuinely reusable original frog skeletal-muscle and isolated-gut recordings.

## Rejected shortcuts
Do not present a digitized scan as an acquisition waveform, invent y-axis calibration or repeat an inverted cardiogram without apparatus evidence. Do not assume free PDF means an open licence. Do not use synthetic demonstration data to support biological conclusions.

## Publication / institutional use
Educational access requires no animals or proprietary devices. The parent OPL licence is GPL-3.0; third-party images/data retain source-specific terms. No user/student telemetry or cloud data upload in the module.
