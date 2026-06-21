# analysis/recording_loader.py

import csv
import json
from pathlib import Path

import numpy as np


def load_json_file(path):
    path = Path(path)

    if not path.exists():
        return None

    with open(path, "r") as f:
        return json.load(f)


def load_csv_rows(path):
    path = Path(path)

    if not path.exists():
        return []

    rows = []

    with open(path, "r", newline="") as f:
        reader = csv.DictReader(f)

        for row in reader:
            rows.append(row)

    return rows


def safe_float(value):
    if value is None:
        return None

    text = str(value).strip()

    if text == "":
        return None

    try:
        return float(text)
    except Exception:
        return None


def safe_int(value):
    if value is None:
        return None

    text = str(value).strip()

    if text == "":
        return None

    try:
        return int(float(text))
    except Exception:
        return None


def load_recording_folder(folder_path):
    """
    Load one OpenPhysiologyLab recording folder.

    Expected canonical files:
    raw.csv
    metadata.json
    markers.csv, optional

    Returns
    -------
    recording : dict
    """

    folder = Path(folder_path)

    if not folder.exists():
        raise FileNotFoundError(f"Recording folder not found: {folder}")

    raw_path = folder / "raw.csv"
    metadata_path = folder / "metadata.json"
    markers_path = folder / "markers.csv"

    if not raw_path.exists():
        raise FileNotFoundError(f"raw.csv not found in: {folder}")

    metadata = load_json_file(metadata_path)

    if metadata is None:
        metadata = {}

    raw_rows = load_csv_rows(raw_path)
    marker_rows = load_csv_rows(markers_path)

    if len(raw_rows) == 0:
        raise ValueError("raw.csv is empty or could not be read.")

    sample = []
    time_s = []
    segment_id = []

    channels = {
        "ch1": [],
        "ch2": [],
        "ch3": [],
        "ch4": [],
        "ch5": [],
        "ch6": []
    }

    for row in raw_rows:
        sample.append(safe_int(row.get("sample")))
        segment_id.append(safe_int(row.get("segment_id")))

        pc_time = safe_float(row.get("pc_time_s"))

        if pc_time is None:
            time_us = safe_float(row.get("time_us"))

            if time_us is not None:
                pc_time = time_us / 1_000_000.0
            else:
                pc_time = 0.0

        time_s.append(pc_time)

        for ch in channels:
            channels[ch].append(safe_float(row.get(ch)))

    sample = np.asarray(sample, dtype=float)
    time_s = np.asarray(time_s, dtype=float)
    segment_id = np.asarray(segment_id, dtype=float)

    channel_arrays = {}

    available_channels = []

    for ch, values in channels.items():
        arr = np.asarray(
            [np.nan if v is None else v for v in values],
            dtype=float
        )

        channel_arrays[ch] = arr

        if np.any(np.isfinite(arr)):
            available_channels.append(ch)

    markers = []

    for marker in marker_rows:
        markers.append({
            "marker_id": safe_int(marker.get("marker_id")),
            "time_s": safe_float(marker.get("time_s")),
            "label": marker.get("label", ""),
            "mode": marker.get("mode", ""),
            "created_datetime": marker.get("created_datetime", "")
        })

    fs = metadata.get("sample_rate_target_hz", None)

    if fs is None:
        fs = metadata.get("target_sample_rate_hz", None)

    if fs is None:
        fs = 500

    fs = float(fs)

    recording = {
        "folder": folder,
        "raw_path": raw_path,
        "metadata_path": metadata_path,
        "markers_path": markers_path if markers_path.exists() else None,

        "metadata": metadata,
        "markers": markers,

        "sample": sample,
        "time_s": time_s,
        "segment_id": segment_id,
        "channels": channel_arrays,
        "available_channels": available_channels,

        "sample_rate_hz": fs,
        "sample_count": len(raw_rows),
        "duration_sample_count_s": len(raw_rows) / fs if fs > 0 else None,
        "duration_time_axis_s": float(time_s[-1] - time_s[0]) if len(time_s) > 1 else 0.0
    }

    return recording


def summarize_recording(recording):
    metadata = recording.get("metadata", {})

    lines = []

    lines.append(f"Folder: {recording['folder']}")
    lines.append(f"Samples: {recording['sample_count']}")
    lines.append(f"Sample rate: {recording['sample_rate_hz']} Hz")
    lines.append(f"Sample-count duration: {recording['duration_sample_count_s']:.3f} s")
    lines.append(f"Time-axis span: {recording['duration_time_axis_s']:.3f} s")
    lines.append(f"Available channels: {', '.join(recording['available_channels'])}")

    lines.append("")
    lines.append("Metadata")

    important_keys = [
        "recording_mode",
        "device_id",
        "operator",
        "electrode_placement",
        "integrity_status",
        "missing_sample_count_estimate_segment_aware",
        "duration_mode",
        "duration_stop_rule",
        "sample_count_locked",
        "target_sample_count",
        "firmware_identity",
        "firmware_hash_sha256"
    ]

    for key in important_keys:
        if key in metadata:
            lines.append(f"{key}: {metadata.get(key)}")

    if recording.get("markers"):
        lines.append("")
        lines.append(f"Markers: {len(recording['markers'])}")

    return "\n".join(lines)