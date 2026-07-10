
from __future__ import annotations

from typing import Optional
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

    win = int(max(5, min(len(y) // 10, fs * 0.8)))
    if win % 2 == 0:
        win += 1
    kernel = np.ones(win, dtype=float) / win
    baseline = np.convolve(y, kernel, mode="same")
    return y - baseline
