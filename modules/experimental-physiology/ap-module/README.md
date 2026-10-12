# OPL Action Potential & Its Properties — Module 1 / v0.6 pilot

This is the first coherent teaching module of OpenPhysiologyLab Experimental Physiology. It is a **self-contained browser lesson** (HTML, CSS, JS without frameworks), with an authentic externally sourced figure track and a checksum-verified real two-channel squid axon excerpt. The reference single-spike curve and property-comparison curves are **teaching models, not recorded data**.

## Launch

From the extracted folder, run:

```bash
python -m http.server 8000
```

Open `http://localhost:8000/web/index.html` on desktop or phone on the same local network (use the host machine's address if needed). For source-file verification, `localhost` or a secure HTTPS origin is necessary for Web Crypto. Do **not** open via `file://` if testing the real waveform loader. No software installation is required for students.

## What ships and what does not

- Phase-by-phase illustrated isolated AP with true return-to-model baseline (explicit synthetic teaching model, not sampled ion-channel simulation).
- Six property comparisons: threshold/rheobase, all-or-none, refractory, strength-duration, propagation, accommodation/repetitive firing. Property plots are labelled illustrative.
- Two original published single-spike figure references, with source links and licence provenance; **not redistributed** as images or invented numeric data.
- Verified genuine squid giant axon recording `SGAMP a1t18`, 992–1030 ms, both Vm and stimulus-current channels; original 125 kHz sample rate, 4751 samples each; original-derived CSV SHA-256 checks enforced in browser. It is an ADVANCED repeating-spike demonstration, not the introductory isolated recording.
- Five formative assessment questions, source links, phases, mobile layout.
- Original binary master files and audit live in the earlier OPL v0.5 research package; not duplicated here. The excerpt files and manifest are the exact unchanged v0.5 artefacts.
- Search protocol for the first fully authentic digitized single AP is in `docs/ACQUISITION_PROTOCOL.md`.

## Explicit limitation

A genuine original *published image* showing an isolated spike and recovery exists. An original digital isolated AP sweep meeting the current-off before-and-after acceptance criteria is **still pending**. Until one passes source-integrity, calibration, licence and physiology review, the first phase-exploration plot remains a labelled teaching model. No property is claimed proved by one trial.

## Methodological design

1. Begin with recorded units (intracellular vs extracellular and injected stimulus).
2. Introduce shape and operational phase boundaries on a labelled model.
3. Practice original-source comparison and distinguish model versus measured waveform.
4. Use multiple original sweeps to verify all-or-none, threshold/rheobase and refractory response.
5. Do not infer conduction velocity from a single recording site.
6. Evaluate scientific reasoning rather than tracing recall.

## Local validation

- `python -m unittest discover -s tests -p 'test_*.py' -v` for data and source integrity.
- `python tests/test_browser_ui.py` for controlled offline desktop/mobile interaction; this uses a mock browser digest ONLY for UI exercise. Original data SHA-256 verification in Python is unmocked. Browser-native cryptography E2E remains a separate acceptance gate.
- `node --check web/app.js` for JavaScript parsing.

## Copyright

OPL module code is GPL-3.0 as inherited from OPL. Original SGAMP data have ODC-BY-1.0 terms and mandatory source credit. Published figures have their own separate licences. This module provides links, not copies, of those figures. Do not relicense third-party data under GPL simply because the reader is open-source.
