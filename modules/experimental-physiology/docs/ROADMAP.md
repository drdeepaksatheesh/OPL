# Roadmap and acceptance tests

## First scientific release (v0.2)

1. **Frog gastrocnemius:** acquire an appropriately licensed real record; preserve master; verify time marks, stimulus marks, preparation, length/force units and recording direction.
2. **Frog heart:** obtain a calibrated real recording (or restrict to faithful image interpretation when scale is unknown); check that printed 'inverted' cardiogram is explicitly contextualized by lever/transducer geometry.
3. **Isolated intestine:** find actual rabbit intestinal spontaneous and agonist-response records with a permissive reuse licence and documented organ-bath method; do not substitute generic sigmoid cartoon.
4. **Squid axon:** reproduce one action-potential record from SGAMP at 125 kHz; verify WFDB headers and physical-unit conversions before teaching.
5. Recruit physiological domain experts to annotate one original recording each; record disagreements and correction history.
6. Add an evaluation pilot: pre/post interpretation competence, time-to-interpret, scale literacy, ability to identify artifacts and cite provenance. Pre-register if comparative effectiveness is studied.

## Dataset admission gates

`accessible -> licence_approved -> original_downloaded -> SHA256 -> sampling_and_calibration_verified -> annotated -> scientific_reviewed -> student_release`.

Missing gates must remain visible in the repository UI. An image with an unknown time axis cannot support millisecond-caliper answers. A sample simulated trace is useful for testing controls, not evidence of physiology.

## Development

- v0.1: verified source links, reproducible manifests, local CSV import, two-cursor viewer and demo waveform (done).
- v0.2: authentic waveform(s), channel overlays, independent analysis validation, timestamps/marks, waveform export.
- v0.3: interactive practical worksheets and answer rubric.
- v1.0: peer-reviewed educational validation, dataset DOI/archive, sustainable contributors and preservation strategy.
