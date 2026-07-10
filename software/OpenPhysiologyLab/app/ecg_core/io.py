
from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import numpy as np


def read_numeric_csv(path: Path) -> Tuple[List[str], List[np.ndarray]]:
    path = Path(path)
    with path.open("r", newline="", encoding="utf-8-sig", errors="replace") as f:
        sample = f.read(4096)
        f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample)
        except Exception:
            dialect = csv.excel
        reader = csv.reader(f, dialect)
        rows = list(reader)

    if not rows:
        raise ValueError("CSV is empty.")

    header = rows[0]
    data_rows = rows[1:]

    first_numeric_count = 0
    for cell in header:
        try:
            float(cell)
            first_numeric_count += 1
        except Exception:
            pass

    if first_numeric_count >= max(1, len(header) // 2):
        data_rows = rows
        header = [f"col{i+1}" for i in range(len(rows[0]))]

    max_cols = max(len(r) for r in data_rows if r) if data_rows else len(header)
    header = header + [f"col{i+1}" for i in range(len(header), max_cols)]

    cols: List[List[float]] = [[] for _ in range(max_cols)]
    for row in data_rows:
        if not row:
            continue
        for i in range(max_cols):
            try:
                value = float(row[i]) if i < len(row) and row[i] != "" else np.nan
            except Exception:
                value = np.nan
            cols[i].append(value)

    arrays = [np.asarray(c, dtype=float) for c in cols]
    n = min(len(a) for a in arrays)
    arrays = [a[:n] for a in arrays]
    return header[:max_cols], arrays


def find_explicit_time_column(headers: List[str]) -> Optional[int]:
    for i, name in enumerate(headers):
        compact = str(name).lower().strip().replace(" ", "").replace("-", "_")
        if compact in ("time", "time_s", "time_sec", "seconds", "timestamp", "t"):
            return i
        if compact.startswith("time_") or compact.endswith("_time"):
            return i
    return None


def normalize_time_column(raw_time: np.ndarray) -> np.ndarray:
    t = np.asarray(raw_time, dtype=float)
    t = t - np.nanmin(t)
    finite = t[np.isfinite(t)]
    if len(finite) > 3:
        d = np.diff(finite)
        pos = d[d > 0]
        med_d = float(np.nanmedian(pos)) if len(pos) else 0.0
        if med_d > 100.0:
            t = t / 1000000.0
        elif med_d > 0.02:
            t = t / 1000.0
    return t


def default_time_vector(n: int, fs: float = 500.0) -> np.ndarray:
    return np.arange(int(n), dtype=float) / float(fs)


def is_probable_ecg_signal_column(name: str, col: np.ndarray) -> bool:
    lname = str(name).lower().strip()
    blocked = (
        "time", "timestamp", "segment", "seg", "sample", "index", "packet",
        "counter", "count", "marker", "event", "ms", "sec"
    )
    if any(word in lname for word in blocked):
        return False

    x = np.asarray(col, dtype=float)
    finite = x[np.isfinite(x)]
    if len(finite) < max(20, len(x) * 0.5):
        return False
    if np.nanstd(finite) <= 1e-9:
        return False

    try:
        unique_count = len(np.unique(finite[: min(len(finite), 5000)]))
        if unique_count < 10:
            return False
    except Exception:
        pass

    d = np.diff(finite[: min(len(finite), 5000)])
    if len(d):
        frac_pos = float(np.mean(d >= 0))
        frac_neg = float(np.mean(d <= 0))
        if frac_pos > 0.995 or frac_neg > 0.995:
            return False

    return True


def choose_default_channel_name(channels: Dict[str, np.ndarray]) -> Optional[str]:
    if not channels:
        return None

    names = list(channels.keys())
    compact_names = [(name, name.lower().replace(" ", "").replace("_", "")) for name in names]

    for token in ("ch1", "channel1", "a0", "ecg", "lead"):
        for name, compact in compact_names:
            if token in compact:
                return name

    best_name = names[0]
    best_score = -np.inf
    for name in names:
        x = np.asarray(channels[name], dtype=float)
        finite = x[np.isfinite(x)]
        if len(finite) < 20:
            continue
        score = float(np.nanpercentile(finite, 99) - np.nanpercentile(finite, 1))
        if score > best_score:
            best_score = score
            best_name = name
    return best_name


def load_ecg_csv(path: Path, default_fs: float = 500.0):
    headers, columns = read_numeric_csv(Path(path))
    time_idx = find_explicit_time_column(headers)

    if time_idx is not None:
        time_s = normalize_time_column(columns[time_idx])
    else:
        time_s = default_time_vector(len(columns[0]), fs=default_fs)

    channels: Dict[str, np.ndarray] = {}
    for i, (name, col) in enumerate(zip(headers, columns)):
        if time_idx is not None and i == time_idx:
            continue
        if is_probable_ecg_signal_column(name, col):
            channels[name] = np.asarray(col, dtype=float)

    if not channels:
        raise ValueError("No ECG-like signal channel found. Time/segment/sample columns were excluded.")

    return time_s, channels, headers, columns, time_idx
