from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from scipy.signal import find_peaks


@dataclass
class BeatMeasurement:
    beat_number: int
    r_index: int
    r_time_s: float
    r_value_raw: float
    baseline_raw: float
    r_amplitude_raw: float
    r_amplitude_abs_raw: float
    rr_interval_ms: Optional[float]
    heart_rate_bpm: Optional[float]


def estimate_sampling_rate_hz(time_s: Sequence[float]) -> float:
    """Estimate sampling rate from a time axis in seconds."""
    t = np.asarray(time_s, dtype=float)

    if t.ndim != 1 or t.size < 3:
        raise ValueError("time_s must be a 1D array with at least 3 samples.")

    dt = np.diff(t)

    if np.any(dt <= 0):
        raise ValueError("time_s must be strictly increasing.")

    median_dt = float(np.median(dt))

    if median_dt <= 0:
        raise ValueError("Could not estimate sampling rate.")

    return 1.0 / median_dt


def _robust_scale(x: np.ndarray) -> float:
    """Robust estimate of signal scale using median absolute deviation."""
    x = np.asarray(x, dtype=float)
    med = np.median(x)
    mad = np.median(np.abs(x - med))
    scale = 1.4826 * mad

    if not np.isfinite(scale) or scale <= 0:
        scale = float(np.std(x))

    if not np.isfinite(scale) or scale <= 0:
        scale = 1.0

    return float(scale)


def detect_r_peaks(
    time_s: Sequence[float],
    signal: Sequence[float],
    min_distance_s: float = 0.30,
    prominence: Optional[float] = None,
    polarity: str = "auto",
) -> Tuple[np.ndarray, str]:
    """
    Detect R peaks in an ECG-like signal.

    polarity can be "auto", "positive", or "negative".
    Use "negative" if the ECG is inverted and R peaks point downward.
    """
    t = np.asarray(time_s, dtype=float)
    x = np.asarray(signal, dtype=float)

    if t.ndim != 1 or x.ndim != 1:
        raise ValueError("time_s and signal must be 1D arrays.")

    if t.size != x.size:
        raise ValueError("time_s and signal must have the same length.")

    if t.size < 10:
        raise ValueError("Signal is too short for R peak detection.")

    fs = estimate_sampling_rate_hz(t)
    distance_samples = max(1, int(round(min_distance_s * fs)))

    x_centered = x - np.median(x)

    if polarity not in {"auto", "positive", "negative"}:
        raise ValueError("polarity must be 'auto', 'positive', or 'negative'.")

    if polarity == "auto":
        positive_strength = abs(float(np.max(x_centered)))
        negative_strength = abs(float(np.min(x_centered)))

        if negative_strength > positive_strength:
            y = -x_centered
            used_polarity = "negative"
        else:
            y = x_centered
            used_polarity = "positive"
    elif polarity == "negative":
        y = -x_centered
        used_polarity = "negative"
    else:
        y = x_centered
        used_polarity = "positive"

    if prominence is None:
        scale = _robust_scale(y)
        percentile_range = float(np.percentile(y, 95) - np.percentile(y, 5))
        prominence = max(0.6 * scale, 0.15 * percentile_range)

    trial_prominences = [prominence, prominence * 0.5, prominence * 0.25]
    best_peaks = np.array([], dtype=int)

    for prom in trial_prominences:
        peaks, _ = find_peaks(
            y,
            distance=distance_samples,
            prominence=prom,
        )

        if peaks.size >= 2:
            best_peaks = peaks.astype(int)
            break

        if peaks.size > best_peaks.size:
            best_peaks = peaks.astype(int)

    return best_peaks, used_polarity


def _local_baseline(
    time_s: np.ndarray,
    signal: np.ndarray,
    r_time_s: float,
    baseline_window_s: Tuple[float, float],
) -> float:
    """
    Estimate local ECG baseline before the R peak.

    Default window is usually before QRS and after much of the P wave:
    -180 ms to -80 ms from R peak.
    """
    start = r_time_s + baseline_window_s[0]
    end = r_time_s + baseline_window_s[1]

    mask = (time_s >= start) & (time_s <= end)

    if np.any(mask):
        return float(np.median(signal[mask]))

    return float(np.median(signal))


def make_beat_table(
    time_s: Sequence[float],
    signal: Sequence[float],
    r_peaks: Sequence[int],
    baseline_window_s: Tuple[float, float] = (-0.18, -0.08),
) -> List[BeatMeasurement]:
    """
    Create beat-by-beat ECG measurements from detected R peaks.

    First reliable measurements:
    - R time
    - RR interval
    - heart rate
    - R value
    - R amplitude from local baseline
    """
    t = np.asarray(time_s, dtype=float)
    x = np.asarray(signal, dtype=float)
    peaks = np.asarray(r_peaks, dtype=int)

    if t.ndim != 1 or x.ndim != 1:
        raise ValueError("time_s and signal must be 1D arrays.")

    if t.size != x.size:
        raise ValueError("time_s and signal must have the same length.")

    if np.any(peaks < 0) or np.any(peaks >= t.size):
        raise ValueError("r_peaks contains indices outside the signal length.")

    rows: List[BeatMeasurement] = []
    previous_r_time: Optional[float] = None

    for i, idx in enumerate(peaks, start=1):
        r_time = float(t[idx])
        r_value = float(x[idx])

        baseline = _local_baseline(t, x, r_time, baseline_window_s)
        r_amp = r_value - baseline

        if previous_r_time is None:
            rr_ms = None
            hr_bpm = None
        else:
            rr_ms = (r_time - previous_r_time) * 1000.0
            hr_bpm = 60000.0 / rr_ms if rr_ms > 0 else None

        rows.append(
            BeatMeasurement(
                beat_number=i,
                r_index=int(idx),
                r_time_s=r_time,
                r_value_raw=r_value,
                baseline_raw=baseline,
                r_amplitude_raw=float(r_amp),
                r_amplitude_abs_raw=float(abs(r_amp)),
                rr_interval_ms=None if rr_ms is None else float(rr_ms),
                heart_rate_bpm=None if hr_bpm is None else float(hr_bpm),
            )
        )

        previous_r_time = r_time

    return rows


def beat_table_as_dicts(rows: Sequence[BeatMeasurement]) -> List[Dict[str, Any]]:
    """Convert BeatMeasurement rows into dictionaries for CSV export or GUI tables."""
    return [asdict(row) for row in rows]


def manual_time_measurement(t1_s: float, t2_s: float) -> Dict[str, float]:
    """Measure duration or interval between two manually selected time points."""
    delta_s = float(t2_s) - float(t1_s)

    return {
        "t1_s": float(t1_s),
        "t2_s": float(t2_s),
        "delta_s": delta_s,
        "delta_ms": delta_s * 1000.0,
        "absolute_delta_ms": abs(delta_s) * 1000.0,
    }


def manual_amplitude_measurement(
    y1: float,
    y2: float,
    scale_mV_per_unit: Optional[float] = None,
) -> Dict[str, Optional[float]]:
    """
    Measure amplitude difference between two manually selected signal values.

    y1 may be baseline.
    y2 may be peak.

    If scale_mV_per_unit is given, mV output is also calculated.
    """
    delta_raw = float(y2) - float(y1)
    abs_delta_raw = abs(delta_raw)

    if scale_mV_per_unit is None:
        delta_mV = None
        abs_delta_mV = None
    else:
        delta_mV = delta_raw * float(scale_mV_per_unit)
        abs_delta_mV = abs_delta_raw * float(scale_mV_per_unit)

    return {
        "y1_raw": float(y1),
        "y2_raw": float(y2),
        "delta_raw": delta_raw,
        "absolute_delta_raw": abs_delta_raw,
        "delta_mV": delta_mV,
        "absolute_delta_mV": abs_delta_mV,
    }
