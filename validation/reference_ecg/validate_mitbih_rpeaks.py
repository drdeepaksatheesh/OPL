#!/usr/bin/env python3
"""Benchmark OPL ECG R-peak detection against MIT-BIH reference annotations.

Scientific rules
----------------
- Dataset and record list are frozen in code.
- No record-specific threshold tuning.
- OPL detector parameters are left at their public defaults.
- Signal 0 is used because MIT-BIH reference beat annotation times generally
  coincide with the R-wave peak in signal 0.
- Reference beats are defined using official WFDB beat annotation symbols.
- Primary matching tolerance is +/-150 ms; a stricter +/-50 ms result is also
  reported.
- Performance is reported even if poor. The benchmark does not tune or hide
  failure cases.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import wfdb

ROOT = Path(__file__).resolve().parents[2]
SOFTWARE = ROOT / "software" / "OpenPhysiologyLab"
if str(SOFTWARE) not in sys.path:
    sys.path.insert(0, str(SOFTWARE))

from analysis.peak_detection import detect_ecg_r_peaks  # noqa: E402

MITBIH_VERSION = "1.0.0"
PN_DIR = f"mitdb/{MITBIH_VERSION}"
DOI = "10.13026/C2F305"
LICENSE = "Open Data Commons Attribution License v1.0"

RECORDS = [
    "100","101","102","103","104","105","106","107","108","109",
    "111","112","113","114","115","116","117","118","119","121",
    "122","123","124","200","201","202","203","205","207","208",
    "209","210","212","213","214","215","217","219","220","221",
    "222","223","228","230","231","232","233","234",
]

BEAT_SYMBOLS = {
    "N","L","R","B","A","a","J","S","V","r","F",
    "e","j","n","E","/","f","Q","?",
}


def fixed_quantile_records(count: int) -> list[str]:
    if count <= 0:
        raise ValueError("count must be positive")
    if count >= len(RECORDS):
        return list(RECORDS)
    if count == 1:
        return [RECORDS[0]]
    indices = [round(i * (len(RECORDS) - 1) / (count - 1)) for i in range(count)]
    # Guard against duplicate roundings if count changes.
    seen = set()
    selected = []
    for index in indices:
        record = RECORDS[index]
        if record not in seen:
            selected.append(record)
            seen.add(record)
    return selected


def match_sorted(reference: np.ndarray, detected: np.ndarray, tolerance_samples: int) -> dict:
    """One-to-one chronological matching for sorted beat locations."""
    reference = np.asarray(reference, dtype=int)
    detected = np.asarray(detected, dtype=int)

    i = 0
    j = 0
    matched_ref = []
    matched_det = []
    false_negatives = []
    false_positives = []

    while i < len(reference) and j < len(detected):
        delta = int(detected[j] - reference[i])

        if delta < -tolerance_samples:
            false_positives.append(int(detected[j]))
            j += 1
            continue

        if delta > tolerance_samples:
            false_negatives.append(int(reference[i]))
            i += 1
            continue

        # A candidate pair falls inside the tolerance window. If the next
        # detection is also inside this same reference window and is closer,
        # count the earlier detection as FP and use the closer one.
        if j + 1 < len(detected):
            next_delta = int(detected[j + 1] - reference[i])
            if abs(next_delta) <= tolerance_samples and abs(next_delta) < abs(delta):
                false_positives.append(int(detected[j]))
                j += 1
                continue

        # Likewise, if the next reference is closer to this same detection,
        # count the current reference as FN and let the detection match next.
        if i + 1 < len(reference):
            next_ref_delta = int(detected[j] - reference[i + 1])
            if abs(next_ref_delta) <= tolerance_samples and abs(next_ref_delta) < abs(delta):
                false_negatives.append(int(reference[i]))
                i += 1
                continue

        matched_ref.append(int(reference[i]))
        matched_det.append(int(detected[j]))
        i += 1
        j += 1

    if i < len(reference):
        false_negatives.extend(int(x) for x in reference[i:])
    if j < len(detected):
        false_positives.extend(int(x) for x in detected[j:])

    return {
        "matched_reference": np.asarray(matched_ref, dtype=int),
        "matched_detected": np.asarray(matched_det, dtype=int),
        "false_negative_samples": np.asarray(false_negatives, dtype=int),
        "false_positive_samples": np.asarray(false_positives, dtype=int),
    }


def metrics_for_match(match: dict, fs: float) -> dict:
    tp = int(len(match["matched_reference"]))
    fn = int(len(match["false_negative_samples"]))
    fp = int(len(match["false_positive_samples"]))

    sensitivity = tp / (tp + fn) if tp + fn else math.nan
    ppv = tp / (tp + fp) if tp + fp else math.nan
    f1 = 2 * sensitivity * ppv / (sensitivity + ppv) if (
        math.isfinite(sensitivity) and math.isfinite(ppv) and sensitivity + ppv
    ) else math.nan

    errors_ms = (
        (match["matched_detected"] - match["matched_reference"]) / fs * 1000.0
        if tp
        else np.asarray([], dtype=float)
    )
    abs_errors = np.abs(errors_ms)

    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "sensitivity": float(sensitivity),
        "positive_predictive_value": float(ppv),
        "f1": float(f1),
        "timing_error_ms": {
            "mean_signed": float(np.mean(errors_ms)) if tp else None,
            "median_signed": float(np.median(errors_ms)) if tp else None,
            "median_absolute": float(np.median(abs_errors)) if tp else None,
            "p95_absolute": float(np.percentile(abs_errors, 95)) if tp else None,
            "max_absolute": float(np.max(abs_errors)) if tp else None,
        },
        "false_positive_examples_s": [
            float(x / fs) for x in match["false_positive_samples"][:10]
        ],
        "false_negative_examples_s": [
            float(x / fs) for x in match["false_negative_samples"][:10]
        ],
    }


def evaluate_record(record_name: str) -> dict:
    record = wfdb.rdrecord(record_name, pn_dir=PN_DIR, physical=True)
    ann = wfdb.rdann(record_name, "atr", pn_dir=PN_DIR)

    fs = float(record.fs)
    signal = np.asarray(record.p_signal[:, 0], dtype=float)
    x = np.arange(signal.size, dtype=float) / fs

    reference_samples = np.asarray(
        [
            int(sample)
            for sample, symbol in zip(ann.sample, ann.symbol)
            if symbol in BEAT_SYMBOLS
        ],
        dtype=int,
    )

    result = detect_ecg_r_peaks(x, signal, fs)
    detected_samples = np.asarray(result.get("peaks", []), dtype=int)

    match_150 = match_sorted(reference_samples, detected_samples, int(round(0.150 * fs)))
    match_50 = match_sorted(reference_samples, detected_samples, int(round(0.050 * fs)))

    return {
        "record": record_name,
        "signal_0_name": str(record.sig_name[0]),
        "sampling_rate_hz": fs,
        "sample_count": int(signal.size),
        "duration_s": float(signal.size / fs),
        "reference_beat_count": int(reference_samples.size),
        "detected_peak_count": int(detected_samples.size),
        "detector_method": result.get("method"),
        "selected_polarity": result.get("polarity"),
        "polarity_source": result.get("polarity_source"),
        "detector_warning": result.get("warning"),
        "estimated_hr_count_bpm": result.get("estimated_hr_count_bpm"),
        "match_150_ms": metrics_for_match(match_150, fs),
        "match_50_ms": metrics_for_match(match_50, fs),
    }


def aggregate(records: list[dict], key: str) -> dict:
    tp = sum(int(r[key]["tp"]) for r in records)
    fp = sum(int(r[key]["fp"]) for r in records)
    fn = sum(int(r[key]["fn"]) for r in records)
    sensitivity = tp / (tp + fn) if tp + fn else math.nan
    ppv = tp / (tp + fp) if tp + fp else math.nan
    f1 = 2 * sensitivity * ppv / (sensitivity + ppv) if (
        sensitivity + ppv
    ) else math.nan

    per_record_sens = np.asarray([r[key]["sensitivity"] for r in records], dtype=float)
    per_record_ppv = np.asarray([r[key]["positive_predictive_value"] for r in records], dtype=float)

    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "sensitivity": float(sensitivity),
        "positive_predictive_value": float(ppv),
        "f1": float(f1),
        "per_record_sensitivity_median": float(np.nanmedian(per_record_sens)),
        "per_record_sensitivity_min": float(np.nanmin(per_record_sens)),
        "per_record_positive_predictive_value_median": float(np.nanmedian(per_record_ppv)),
        "per_record_positive_predictive_value_min": float(np.nanmin(per_record_ppv)),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--record-count",
        type=int,
        default=8,
        help="Fixed-quantile record count. Use 48 for the complete database.",
    )
    parser.add_argument(
        "--output",
        default="build/reference-validation/mitbih_rpeak_report.json",
    )
    args = parser.parse_args()

    selected = fixed_quantile_records(args.record_count)
    records = []

    for record_name in selected:
        print(f"Benchmarking MIT-BIH {record_name}...", flush=True)
        records.append(evaluate_record(record_name))

    report = {
        "schema": "org.openphysiologylab.mitbih-rpeak-validation/v1",
        "dataset": "MIT-BIH Arrhythmia Database",
        "dataset_version": MITBIH_VERSION,
        "doi": DOI,
        "license": LICENSE,
        "record_universe": RECORDS,
        "selection_rule": (
            "Fixed quantiles of the frozen sorted 48-record MIT-BIH record list. "
            "Selection is independent of waveform appearance and OPL output. "
            "Use --record-count 48 for the complete database."
        ),
        "selected_records": selected,
        "signal_rule": (
            "Use signal 0 without per-record lead selection because MIT-BIH "
            "reference beat times generally coincide with the R-wave peak in signal 0."
        ),
        "reference_rule": (
            "Include official WFDB beat annotation symbols only; exclude rhythm, "
            "noise, waveform-boundary and artifact annotations."
        ),
        "detector_rule": (
            "Run public OPL detect_ecg_r_peaks with default parameters and no "
            "record-specific threshold tuning."
        ),
        "matching": {
            "primary_tolerance_ms": 150,
            "strict_tolerance_ms": 50,
            "one_to_one": True,
        },
        "records": records,
        "aggregate_150_ms": aggregate(records, "match_150_ms"),
        "aggregate_50_ms": aggregate(records, "match_50_ms"),
        "claim_boundary": [
            "Benchmarks beat/R-peak timing only.",
            "Does not classify arrhythmia or beat type.",
            "Does not validate P/QRS/T delineation.",
            "Does not validate HRV until NN handling and HRV calculations are separately tested.",
            "Does not validate NPG Lite or analogue hardware.",
        ],
    }

    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({
        "selected_records": selected,
        "aggregate_150_ms": report["aggregate_150_ms"],
        "aggregate_50_ms": report["aggregate_50_ms"],
    }, indent=2))


if __name__ == "__main__":
    main()
