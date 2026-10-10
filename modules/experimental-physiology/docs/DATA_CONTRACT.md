# Data contract and provenance

A source record (in `data/sources.json`) is a **bibliographic discovery item**, not automatically an accepted dataset. Source record attributes must have explicit `signal_class`, `access_status`, `record_in_repository`, licence and `reuse_review`.

## Minimum metadata for an accepted recording

- Source ID, DOI/URL, creator and source version.
- Organism (taxon as stated), specimen/preparation, experimental setting, anesthesia and conditions where relevant.
- Original physical recording / file, source checksum SHA-256, date of retrieval, upstream licence evidence and attribution.
- Independent and dependent physical units, sampling frequency / historical time ruler, device/gain/transducer, polarity and display direction, calibration method and uncertainties.
- Intervention markers, details of concentrations/stimulus, preprocessing (if any), transformation provenance.
- Biological artifacts vs equipment artifacts explicitly separated.
- Review by a discipline-competent annotator; unknown values remain `null` / `unknown`.

## Browser-ready CSV

One sample per row, **CSV with header `time_ms,value`**. `time_ms` strictly increases and values are finite. `value` is already in the documented *channel unit*. For multi-channel acquisition, make a file per channel for v0.1 and retain channel synchronization metadata. No guessing what units mean from magnitude. Reversed-sign renderings are display transformations, never redefined as data.

Associated manifest example:

```json
{
  "record_id": "unique-stable-id",
  "source_id": "source-registry-id",
  "data_class": "UNVERIFIED_IMPORT",
  "species": "as reported",
  "time_unit": "ms",
  "y_unit": "mV",
  "signal_polarity": "as_recorded",
  "original_sha256": "64-character digest of ORIGINAL source file",
  "derived_sha256": "64-character digest of converted CSV",
  "calibration": "conversion procedure with reference",
  "processing": ["none"],
  "limitations": []
}
```

Do not fill illustrative placeholder entries into the released genuine-signal catalogue. Any dataset added from scans requires a separate image master and tracing extraction uncertainty; not equivalent to waveform sampling by an ADC.
