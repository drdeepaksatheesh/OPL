# First authentic digital animal-physiology recording: SGAMP a1t18

**Status:** Original record **source-identified** and header/hash publication verified. Full biological waveform conversion is **not claimed successful** until the automated acquisition workflow downloads and validates the original master bytes. Until then, only tested importer code exists locally.

## Actual original source

Paydarfar D, Forger DB, Clay JR. *Noisy Inputs and the Induction of On–Off Switching Behavior in a Neuronal Pacemaker.* Journal of Neurophysiology. 2006;96:3338–3348. Record hosted by PhysioNet: SGAMP v1.0.0 (2016), DOI https://doi.org/10.13026/C25C73. Dataset: https://physionet.org/content/sgamp/1.0.0/. Licence: Open Data Commons Attribution 1.0 (ODC-BY 1.0). Credit both investigators and PhysioNet and retain ODC-BY attribution on redistributed datasets.

Record path `raw/a1t18`; upstream `Irms.txt` labels trial 1.18 as **PULSE**. Original is a two-channel, 125 kHz, 250,001-sample WFDB format 16 record. The exact file-level checksums published in upstream SHA256SUMS.txt are fixed in `scripts/ingest_sgamp.py`.

### Raw upstream header as published (for verification, NOT a downloaded original)

```
a1t18 2 125000 250001
a1t18.dat 16 64082.904(4205)/V 0 0 -22187 18729 0 Vmembrane
a1t18.dat 16 64915.9042(-32450)/V 0 0 -32292 22585 0 Istim
```

Expected original SHA-256:

- `a1t18.hea`: `9dd10bf0703219b08be82f69444d25ae9e4c81f5f419f998b422c9ab72f66e0c`
- `a1t18.dat`: `d74534b5d67d7f582694e597e4d4c86adccfdb1f4597379af45323059cafffb9`

Both source hashes must match **actual downloaded bytes**. The published header above is reference text, not a substitute for the authentic 141-byte `.hea` master.

## Conversion, without invented units

WFDB format 16 uses little-endian signed 16-bit interleaved samples. For each channel, raw instrument volts = `(signed_ADC_count - ADC_baseline) / ADC_gain_per_V`.

- Membrane potential mV = `raw_instrument_volts * 0.1 * 1000` (the source states an amplifier gain of 10).
- Injected stimulus current in µA/cm² = `raw_instrument_volts * 5` (the source's current conversion).
- Time in milliseconds = `sample_index * 1000 / 125000`; last time point = **2000.0 ms**.
- Stimulus-channel DC instrumentation offset is **not automatically corrected**. A meaningful current zero must be located from the original stimulation-off segment and protocol; never silently zero the first sample or subtract its median.
- Do not silently filter, interpolate, denoise, reshape, normalize amplitude or change trace polarity.

The two derived single-channel CSVs use exactly `time_ms,value` for the current single-channel browser viewer. The manifest documents synchronous origin; a proper synchronized multi-channel viewer is still a future feature. CSV output uses decimal rounding to 8 places; use original integer ADC master for precision-critical work.

## Reproduce the acquisition (network required)

From the root of OPL:

```bash
python -m unittest discover -s modules/experimental-physiology/tests -p 'test_sgamp.py' -v
python modules/experimental-physiology/scripts/ingest_sgamp.py --record a1t18 --output /tmp/sgamp_a1t18_verified
```

For independently downloaded originals, run offline:

```bash
python modules/experimental-physiology/scripts/ingest_sgamp.py --record a1t18 --source-dir /path/to/original/SGAMP/raw --output /tmp/sgamp_a1t18_verified
```

If any file hash, header layout, sample count, first sample or channel checksum disagrees, conversion **must reject the record**. Never use the sample-size or header values in this document to fabricate original data.

## Student exercise once a verified artifact is produced

1. View the membrane potential `Vmembrane_mV.csv` at 125 kHz. Identify baseline level and membrane excursions (a spike requires scrutiny; do not pre-label without signal review).
2. View the separate stimulus current CSV and identify the stimulation interval, while explicitly noting possible DC offset.
3. Measure peak-to-peak membrane potential and latency from independently marked stimulus features, using a carefully zoomed view; avoid concluding cause solely from one trial.
4. Record the original DOI, file hashes and conversion procedure alongside any derived measurement.
5. Write a short explanation of ADC calibration, baseline and why invented normalization would be scientifically unacceptable.

**Not completed:** independent visual examination of biological waveform, cross-check against published figures, peer-reviewed answer key and third-party data publication/long-term archival. The workflow produces a 30-day CI artifact, not a permanent dataset repository. Keep a separate immutable archive with hashes once acquisition succeeds.
