
from __future__ import annotations

from typing import Optional
import numpy as np

from .filters import safe_sampling_rate, ecg_review_filter


def detect_r_peaks_calipers_style(signal, time_s=None, fs: Optional[float] = None):
    y = np.asarray(signal, dtype=float)
    if len(y) < 20:
        return np.array([], dtype=int)

    if fs is None:
        fs = safe_sampling_rate(time_s, default=500.0)

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
    fs = safe_sampling_rate(time_s, default=500.0)
    filtered = ecg_review_filter(raw_signal, time_s=time_s, fs=fs)
    peaks = detect_r_peaks_calipers_style(filtered, time_s=time_s, fs=fs)
    complete = complete_complex_peaks(peaks, time_s, pre_r_s=pre_r_s, post_r_s=post_r_s)
    return filtered, peaks, complete
