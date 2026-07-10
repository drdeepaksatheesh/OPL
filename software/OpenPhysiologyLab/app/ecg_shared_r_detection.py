
from __future__ import annotations

from typing import Optional, Tuple

import numpy as np


def safe_sampling_rate(time_s, default: float = 500.0) -> float:
    try:
        t = np.asarray(time_s, dtype=float)
        if len(t) < 3:
            return float(default)
        d = np.diff(t)
        d = d[np.isfinite(d) & (d > 0)]
        if len(d) == 0:
            return float(default)
        fs = float(1.0 / np.median(d))
        if not np.isfinite(fs) or fs < 50.0 or fs > 2000.0:
            return float(default)
        return fs
    except Exception:
        return float(default)


def ecg_review_filter(signal, time_s=None, fs: Optional[float] = None):
    """
    Calipers-compatible ECG review filter.

    This is the shared detection/filtering helper for ECG review tabs.
    It keeps the displayed raw waveform separate from the filtered copy used
    only for R-peak detection/navigation.
    """
    y = np.asarray(signal, dtype=float).copy()
    good = np.isfinite(y)
    if not good.all():
        y[~good] = np.nanmedian(y[good]) if good.any() else 0.0

    if fs is None:
        fs = safe_sampling_rate(time_s, default=500.0)

    try:
        from scipy.signal import butter, filtfilt

        nyq = fs / 2.0
        low = max(0.01, 0.5 / nyq)
        high = min(0.99, 40.0 / nyq)
        if low < high:
            b, a = butter(4, [low, high], btype="band")
            return filtfilt(b, a, y)
    except Exception:
        pass

    # Safe fallback if scipy is unavailable.
    win = int(max(5, min(len(y) // 10, fs * 0.8)))
    if win % 2 == 0:
        win += 1
    kernel = np.ones(win, dtype=float) / win
    baseline = np.convolve(y, kernel, mode="same")
    return y - baseline


def detect_r_peaks_calipers_style(signal, time_s=None, fs: Optional[float] = None):
    """
    Conservative ECG-Calipers-style R detection.

    The key design points are:
    - detect on a filtered copy, not on the displayed raw trace
    - tolerate inverted polarity
    - use a physiologic refractory window so T waves are less likely to be
      counted as R peaks
    """
    y = np.asarray(signal, dtype=float)
    if len(y) < 20:
        return np.array([], dtype=int)

    if fs is None:
        fs = safe_sampling_rate(time_s, default=500.0)

    # Conservative minimum RR. This is intentionally close to the ECG Calipers
    # navigation behaviour and avoids double-counting T waves.
    distance = int(max(1, 0.45 * fs))

    z_pos = y - np.nanmedian(y)
    z_neg = -z_pos
    z = z_neg if np.nanpercentile(z_neg, 99) > np.nanpercentile(z_pos, 99) else z_pos

    try:
        from scipy.signal import find_peaks

        robust = np.nanmedian(np.abs(z - np.nanmedian(z))) * 1.4826
        if not np.isfinite(robust) or robust <= 0:
            robust = np.nanstd(z)
        if not np.isfinite(robust) or robust <= 0:
            return np.array([], dtype=int)

        height = np.nanmedian(z) + robust * 1.0
        prominence = max(robust * 1.5, (np.nanpercentile(z, 98) - np.nanmedian(z)) * 0.35)
        peaks, _ = find_peaks(z, distance=distance, height=height, prominence=prominence)
        return peaks.astype(int)
    except Exception:
        robust = np.nanmedian(np.abs(z - np.nanmedian(z))) * 1.4826
        if not np.isfinite(robust) or robust <= 0:
            robust = np.nanstd(z)
        if not np.isfinite(robust) or robust <= 0:
            return np.array([], dtype=int)

        threshold = np.nanmedian(z) + robust * 1.5
        candidates = []
        last = -distance
        for i in range(1, len(z) - 1):
            if z[i] > threshold and z[i] >= z[i - 1] and z[i] >= z[i + 1] and (i - last) >= distance:
                candidates.append(i)
                last = i
        return np.asarray(candidates, dtype=int)


def complete_complex_peaks(peaks, time_s, pre_r_s: float = 0.25, post_r_s: float = 0.55):
    """
    Accept only R peaks whose surrounding PQRST window is complete.

    The first and last detected peaks are rejected automatically if they do
    not have enough pre-R or post-R signal.
    """
    if peaks is None or time_s is None:
        return np.array([], dtype=int)

    pks = np.asarray(peaks, dtype=int)
    t = np.asarray(time_s, dtype=float)
    if len(pks) == 0 or len(t) == 0:
        return np.array([], dtype=int)

    accepted = []
    for p in pks:
        if p < 0 or p >= len(t):
            continue
        rt = float(t[p])
        if rt - pre_r_s >= float(t[0]) and rt + post_r_s <= float(t[-1]):
            accepted.append(int(p))
    return np.asarray(accepted, dtype=int)


def detect_complete_ecg_complexes(raw_signal, time_s, pre_r_s: float = 0.25, post_r_s: float = 0.55):
    """
    Shared one-call helper.

    Returns:
        filtered_signal, all_r_peaks, complete_r_peaks
    """
    fs = safe_sampling_rate(time_s, default=500.0)
    filtered = ecg_review_filter(raw_signal, time_s=time_s, fs=fs)
    peaks = detect_r_peaks_calipers_style(filtered, time_s=time_s, fs=fs)
    complete = complete_complex_peaks(peaks, time_s, pre_r_s=pre_r_s, post_r_s=post_r_s)
    return filtered, peaks, complete
