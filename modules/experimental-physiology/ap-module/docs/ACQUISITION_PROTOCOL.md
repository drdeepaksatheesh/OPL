# Acceptance gate: first authentic isolated AP numerical sweep

## Why SGAMP a1t18 does not qualify

Its first pulse elicits prolonged firing. The membrane does not recover to a stable resting potential between the spikes in the displayed portion. Use the file as a source-verified advanced **bistability/persistent firing** exercise, not as a purported clean isolated AP.

## First candidate collection

[Allen Cell Types Database](https://brain-map.org/support/documentation/documentation-cell-types-database) publishes in-situ/whole-cell current-clamp sweeps, especially **Short Square** (3-ms injections) and **Short Square – Triple**, from mouse and human neurons. Short Square is appropriate for one spike followed by a quiet interval; Triple can later address paired/rapid stimuli. The documentation explicitly describes single AP thumbnails and lists recorded stimulus, Vm and spikes.

[AllenSDK example](https://allensdk.readthedocs.io/en/latest/_static/examples/nb/cell_types.html) demonstrates specimen ID `464212183`, sweep `30` but these are only example access instructions; neither their single-spike status nor suitability for a full stable-return lesson has been established.

[DANDI 000148](https://dandiarchive.org/dandiset/000148) is another candidate, with genuine adult mouse spinal-cord whole-cell NWB recordings and CC BY 4.0, but the draft dataset needs stable version/archive review before public mirroring.

## Qualifying trial — objective criteria determined before inspection

1. Original intracellular **current-clamp** Vm paired with full injected-current I time series; no extracellular compound signal substituted.
2. Full original NWB/WFDB master retained immutably; SHA-256, URL, upstream version, specimen ID, sweep ID, preparation, licence terms documented.
3. Native sampling rate, unit/gain/conversion, gain stages, sign conventions and stimulus alignment verified from metadata.
4. **Exactly one** spike in a ≥50 ms display interval extending before and after the event, and no additional spikes in a sufficiently long recovery window.
5. At least 20 ms of no-stimulus pre-window and 30 ms (preferably 100 ms) no-stimulus post-window; voltage not artificially recentered or detrended.
6. Default comparison: absolute difference between medians of 20-ms pre-window and late 30-ms post-window ≤3 mV, and stable baseline (slope/variance checked). This is a *screening* heuristic, not an experimental law, and the selected windows must be specified and checked by the reviewer.
7. AP peak reaches at least 30 mV above baseline; quality-controlled cell type and overshoot, when applicable, disclosed. Operational onset specified (e.g., first pre-peak positive dV/dt >10 mV/ms after a stimulus), not mislabelled as an unambiguous physiological instant.
8. Mark AP duration at an explicit voltage criterion (e.g., half-height); AHP deepest point must be below genuine pre-stimulus rest if labelled AHP.
9. Independent numerical and visual check of samples and axes; record noise, compensation/transient artifacts, and whether stimulus current is off during AHP and late recovery.
10. Verify reproducibility and redistribution permissions for that **particular data source**, beyond the ability to download it.

## Later properties need original SERIES, not isolated traces

- **All-or-none/threshold:** escalating current pulses from same cell at stable holding conditions, before/at/above rheobase; report any changes in AP height near threshold.
- **Refractoriness:** paired pulses with varied ISI and strength. Explain that a standard Triple series alone may not provide full absolute/relative refractory characterization.
- **Strength-duration/chronaxie:** record actual current threshold versus different pulse durations; never infer from fixed 3-ms Short Square series.
- **Propagation and nondecrement:** simultaneous or time-aligned recordings at two known distances, with validated latency and temperature; no pseudo-velocity from a single intracellular site.

## Operational note

An openly accessible webpage or PDF is not automatically a reusable raw dataset. Until this selected sweep and licence pass the checklist, leave the numerical introductory waveform in OPL explicitly **MODEL** status. Preserve the full source and original authorship when it becomes authentic.
