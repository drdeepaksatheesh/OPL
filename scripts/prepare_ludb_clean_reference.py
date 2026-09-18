#!/usr/bin/env python3
"""Select and prepare a clean real Lead-II ECG teaching reference from LUDB.

Selection is reproducible and deliberately separates:
1. clinical-metadata eligibility; and
2. signal-quality ranking.

The script does not choose a record by visual preference.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import urllib.request
from pathlib import Path

import numpy as np
import wfdb
from scipy.signal import butter, sosfiltfilt

LUDB_VERSION = "1.0.1"
PN_DIR = f"ludb/{LUDB_VERSION}/data"
CSV_URL = f"https://physionet.org/files/ludb/{LUDB_VERSION}/ludb.csv"
FILE_BASE = f"https://physionet.org/files/ludb/{LUDB_VERSION}/data"
DOI = "10.13026/eegm-h675"
LICENSE = "Open Data Commons Attribution License v1.0"

EXCLUSION_COLUMNS = [
    "Conduction abnormalities",
    "Extrasystolies",
    "Hypertrophies",
    "Cardiac pacing",
    "Ischemia",
    "Non-specific repolarization abnormalities",
    "Other states",
]


def fetch_csv() -> list[dict[str, str]]:
    with urllib.request.urlopen(CSV_URL, timeout=60) as response:
        text = response.read().decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text)))


def eligible_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    out = []
    for row in rows:
        if row.get("Rhythms", "").strip().lower() != "sinus rhythm":
            continue
        if any(row.get(column, "").strip() for column in EXCLUSION_COLUMNS):
            continue
        out.append(row)
    return out


def robust_mad(values: np.ndarray) -> float:
    if values.size == 0:
        return math.nan
    med = np.median(values)
    return float(1.4826 * np.median(np.abs(values - med)))


def interior_segment(a: int, b: int) -> tuple[int, int] | None:
    if b - a < 8:
        return None
    left = int(round(a + 0.25 * (b - a)))
    right = int(round(a + 0.75 * (b - a)))
    if right <= left:
        return None
    return left, right


def annotation_events(ann) -> list[dict]:
    return [
        {
            "sample": int(sample),
            "symbol": str(symbol),
            "num": int(num),
        }
        for sample, symbol, num in zip(ann.sample, ann.symbol, ann.num)
    ]


def isoelectric_samples(events: list[dict], signal: np.ndarray) -> tuple[np.ndarray, list[dict]]:
    """Use cardiologist wave boundaries to sample PR and TP isoelectric regions."""
    chunks: list[np.ndarray] = []
    segments: list[dict] = []

    for idx, event in enumerate(events):
        # P-wave end -> next QRS onset (PR segment)
        if event["symbol"] == ")" and event["num"] == 0:
            for nxt in events[idx + 1 :]:
                if nxt["sample"] - event["sample"] > 250:
                    break
                if nxt["symbol"] == "(" and nxt["num"] == 1:
                    bounds = interior_segment(event["sample"], nxt["sample"])
                    if bounds:
                        a, b = bounds
                        chunk = signal[a:b]
                        if chunk.size:
                            chunks.append(chunk)
                            segments.append(
                                {
                                    "type": "PR",
                                    "start_sample": a,
                                    "end_sample": b,
                                    "median_mV": float(np.median(chunk)),
                                }
                            )
                    break

        # T-wave end -> next P-wave onset (TP segment)
        if event["symbol"] == ")" and event["num"] == 2:
            for nxt in events[idx + 1 :]:
                if nxt["sample"] - event["sample"] > 700:
                    break
                if nxt["symbol"] == "(" and nxt["num"] == 0:
                    bounds = interior_segment(event["sample"], nxt["sample"])
                    if bounds:
                        a, b = bounds
                        chunk = signal[a:b]
                        if chunk.size:
                            chunks.append(chunk)
                            segments.append(
                                {
                                    "type": "TP",
                                    "start_sample": a,
                                    "end_sample": b,
                                    "median_mV": float(np.median(chunk)),
                                }
                            )
                    break

    if not chunks:
        return np.array([], dtype=float), []
    return np.concatenate(chunks), segments


def peak_amplitudes(events: list[dict], signal: np.ndarray, baseline: np.ndarray) -> dict:
    groups = {"p": [], "N": [], "t": []}
    for event in events:
        symbol = event["symbol"]
        if symbol not in groups:
            continue
        sample = event["sample"]
        if 0 <= sample < signal.size:
            groups[symbol].append(float(signal[sample] - baseline[sample]))

    result = {}
    for symbol, values in groups.items():
        arr = np.asarray(values, dtype=float)
        result[symbol] = {
            "count": int(arr.size),
            "median_mV": float(np.median(arr)) if arr.size else None,
            "positive_fraction": float(np.mean(arr > 0)) if arr.size else None,
        }
    return result


def evaluate_record(record_id: str) -> tuple[dict, np.ndarray, object, list[dict]]:
    record = wfdb.rdrecord(record_id, pn_dir=PN_DIR, physical=True)
    signal_names = [str(name).lower() for name in record.sig_name]
    try:
        lead_index = signal_names.index("ii")
    except ValueError as exc:
        raise RuntimeError(f"Lead II not found in LUDB record {record_id}") from exc

    signal = np.asarray(record.p_signal[:, lead_index], dtype=float)
    fs = float(record.fs)
    ann = wfdb.rdann(record_id, "ii", pn_dir=PN_DIR)
    events = annotation_events(ann)

    baseline_sos = butter(4, 0.5, btype="lowpass", fs=fs, output="sos")
    baseline_curve = sosfiltfilt(baseline_sos, signal)

    iso_values, iso_segments = isoelectric_samples(events, signal)
    segment_medians = np.asarray([seg["median_mV"] for seg in iso_segments], dtype=float)

    recommended_baseline = (
        float(np.median(iso_values)) if iso_values.size else float(np.median(baseline_curve))
    )
    baseline_segment_spread = (
        float(np.percentile(segment_medians, 95) - np.percentile(segment_medians, 5))
        if segment_medians.size >= 2
        else math.inf
    )
    baseline_noise = robust_mad(iso_values - recommended_baseline) if iso_values.size else math.inf

    ecg_component = signal - baseline_curve
    robust_range = float(np.percentile(ecg_component, 99.5) - np.percentile(ecg_component, 0.5))
    robust_range = max(robust_range, np.finfo(float).eps)

    clean_sos = butter(4, [0.5, 40.0], btype="bandpass", fs=fs, output="sos")
    bandpassed = sosfiltfilt(clean_sos, signal)
    residual = signal - baseline_curve - bandpassed
    hf_noise = robust_mad(residual)

    peaks = peak_amplitudes(events, signal, baseline_curve)

    orientation_penalty = 0.0
    for symbol, weight in (("p", 0.25), ("N", 1.0), ("t", 0.5)):
        info = peaks[symbol]
        if not info["count"]:
            orientation_penalty += weight
            continue
        if info["median_mV"] is None or info["median_mV"] <= 0:
            orientation_penalty += weight
        if info["positive_fraction"] is not None and info["positive_fraction"] < 0.8:
            orientation_penalty += weight * 0.5

    baseline_ratio = baseline_segment_spread / robust_range
    noise_ratio = hf_noise / robust_range
    score = baseline_ratio + 2.0 * noise_ratio + orientation_penalty

    metrics = {
        "record_id": record_id,
        "sampling_rate_hz": fs,
        "duration_seconds": signal.size / fs,
        "lead": "II",
        "isoelectric_segment_count": len(iso_segments),
        "recommended_baseline_mV": recommended_baseline,
        "baseline_segment_spread_mV": baseline_segment_spread,
        "baseline_noise_mad_mV": baseline_noise,
        "robust_ecg_range_mV": robust_range,
        "high_frequency_noise_mad_mV": hf_noise,
        "baseline_ratio": baseline_ratio,
        "noise_ratio": noise_ratio,
        "orientation_penalty": orientation_penalty,
        "selection_score": score,
        "peak_summary": peaks,
    }
    return metrics, signal, ann, iso_segments


def download_bytes(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        default="site/reference/ecg-id/data/LUDB_clean_LeadII.json",
    )
    parser.add_argument(
        "--report",
        default="site/reference/ecg-id/data/LUDB_clean_selection.json",
    )
    args = parser.parse_args()

    rows = fetch_csv()
    eligible = eligible_rows(rows)
    if not eligible:
        raise RuntimeError("No LUDB records met the predeclared clinical-metadata criteria.")

    results = []
    cache = {}
    for row in eligible:
        record_id = str(row["ID"]).strip()
        metrics, signal, ann, iso_segments = evaluate_record(record_id)
        metrics["metadata"] = {
            "sex": row.get("Sex", ""),
            "age": row.get("Age", ""),
            "rhythm": row.get("Rhythms", ""),
            "electrical_axis": row.get("Electric axis of the heart", ""),
        }
        results.append(metrics)
        cache[record_id] = (signal, ann, iso_segments, row)

    results.sort(key=lambda item: (item["selection_score"], item["record_id"]))
    selected_metrics = results[0]
    selected_id = selected_metrics["record_id"]
    signal, ann, iso_segments, row = cache[selected_id]

    source_files = {}
    for ext in ("hea", "dat", "ii"):
        data = download_bytes(f"{FILE_BASE}/{selected_id}.{ext}")
        source_files[ext] = {
            "url": f"{FILE_BASE}/{selected_id}.{ext}",
            "bytes": len(data),
            "sha256": sha256_bytes(data),
        }

    events = annotation_events(ann)
    annotations = [
        {
            "sample": event["sample"],
            "symbol": event["symbol"],
            "num": event["num"],
            "source": "LUDB cardiologist manual delineation",
        }
        for event in events
    ]

    out_record = {
        "schema": "org.openphysiologylab.reference-record/v1",
        "record_id": f"LUDB/{selected_id}/LeadII",
        "sampling_rate_hz": selected_metrics["sampling_rate_hz"],
        "duration_seconds": selected_metrics["duration_seconds"],
        "sample_count": int(signal.size),
        "units": ["mV"],
        "signal_names": ["II"],
        "signals": {
            "raw": signal.tolist(),
            # Compatibility alias for the current OPL v1 record package schema.
            # It is not a second filtered source channel.
            "filtered": signal.tolist(),
        },
        "signal_semantics": {
            "raw": "LUDB physical Lead II waveform",
            "filtered": "Schema compatibility alias of raw; LUDB does not provide a paired filtered channel here.",
        },
        "recommended_baseline_mV": selected_metrics["recommended_baseline_mV"],
        "isoelectric_segments": iso_segments,
        "annotations": annotations,
        "annotation_summary": {
            "annotation_events": len(annotations),
            "p_peaks": sum(1 for e in events if e["symbol"] == "p"),
            "qrs_peaks": sum(1 for e in events if e["symbol"] == "N"),
            "t_peaks": sum(1 for e in events if e["symbol"] == "t"),
            "manual_delineation": True,
        },
        "source_files": source_files,
        "selection": selected_metrics,
        "provenance": {
            "dataset": "Lobachevsky University Electrocardiography Database (LUDB)",
            "dataset_version": LUDB_VERSION,
            "repository": "PhysioNet",
            "doi": DOI,
            "license": LICENSE,
            "record": selected_id,
            "lead": "II",
            "sampling_rate_hz": selected_metrics["sampling_rate_hz"],
            "known_preprocessing": "No OPL filtering applied; physical waveform read from the source WFDB record.",
            "annotation_status": "P/T/QRS peaks and boundaries manually annotated by cardiologists in LUDB.",
            "selection_method": "Predeclared clinical-metadata eligibility followed by objective Lead-II baseline/noise ranking.",
            "teaching_role": "Clean real ECG bridge between the synthetic teaching model and a more imperfect real-world recording.",
            "validation_ground_truth": "Manual LUDB waveform delineations are reference annotations for waveform boundaries/peaks; the clean-example selection itself is a teaching choice, not a diagnostic claim.",
        },
    }

    report = {
        "schema": "org.openphysiologylab.clean-reference-selection/v1",
        "dataset": "LUDB",
        "dataset_version": LUDB_VERSION,
        "doi": DOI,
        "eligibility_rule": {
            "rhythm": "Sinus rhythm",
            "required_empty_columns": EXCLUSION_COLUMNS,
            "electrical_axis": "not used as an exclusion criterion",
        },
        "ranking_rule": {
            "lead": "II",
            "baseline": "Cardiologist-delineated PR/TP isoelectric segments when available",
            "score": "baseline_ratio + 2*noise_ratio + orientation_penalty",
            "orientation_preference": "predominantly positive P, QRS peak and T in Lead II",
        },
        "eligible_record_count": len(eligible),
        "selected_record_id": selected_id,
        "selected_metrics": selected_metrics,
        "ranked_candidates": results,
    }

    output = Path(args.output)
    report_path = Path(args.report)
    output.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(out_record, indent=2) + "\n", encoding="utf-8")
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({
        "eligible_record_count": len(eligible),
        "selected_record_id": selected_id,
        "selection_score": selected_metrics["selection_score"],
        "baseline_segment_spread_mV": selected_metrics["baseline_segment_spread_mV"],
        "high_frequency_noise_mad_mV": selected_metrics["high_frequency_noise_mad_mV"],
    }, indent=2))


if __name__ == "__main__":
    main()
