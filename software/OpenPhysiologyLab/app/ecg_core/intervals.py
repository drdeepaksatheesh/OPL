
from __future__ import annotations

from typing import Dict, Optional, Tuple

import numpy as np


def r_peak_times_s(time_s, r_peaks) -> np.ndarray:
    """Return R peak times in seconds from sample indices."""
    t = np.asarray(time_s, dtype=float)
    peaks = np.asarray(r_peaks, dtype=int)
    if len(t) == 0 or len(peaks) == 0:
        return np.array([], dtype=float)
    good = (peaks >= 0) & (peaks < len(t))
    return t[peaks[good]].astype(float)


def rr_intervals_ms(time_s, r_peaks) -> np.ndarray:
    """Return consecutive RR intervals in milliseconds."""
    rt = r_peak_times_s(time_s, r_peaks)
    if len(rt) < 2:
        return np.array([], dtype=float)
    return np.diff(rt) * 1000.0


def rr_interval_mid_times_s(time_s, r_peaks) -> np.ndarray:
    """Return time position of each RR interval as midpoint between adjacent R peaks."""
    rt = r_peak_times_s(time_s, r_peaks)
    if len(rt) < 2:
        return np.array([], dtype=float)
    return (rt[:-1] + rt[1:]) / 2.0


def instant_hr_bpm_from_rr_ms(rr_ms) -> np.ndarray:
    """Convert RR intervals in ms to instantaneous heart rate in beats/min."""
    rr = np.asarray(rr_ms, dtype=float)
    out = np.full_like(rr, np.nan, dtype=float)
    good = np.isfinite(rr) & (rr > 0)
    out[good] = 60000.0 / rr[good]
    return out


def basic_nn_mask(
    rr_ms,
    min_rr_ms: float = 300.0,
    max_rr_ms: float = 2000.0,
    max_successive_change_ms: Optional[float] = None,
    max_successive_change_fraction: Optional[float] = None,
) -> np.ndarray:
    """
    Basic transparent NN candidate mask.

    This is deliberately conservative and visual-audit friendly.
    By default it only rejects non-finite and physiologically impossible /
    very unlikely RR intervals. More advanced ectopic/artifact correction
    should be added later as a visible, user-controlled step.
    """
    rr = np.asarray(rr_ms, dtype=float)
    mask = np.isfinite(rr) & (rr >= float(min_rr_ms)) & (rr <= float(max_rr_ms))

    if max_successive_change_ms is not None and len(rr) >= 2:
        d = np.abs(np.diff(rr))
        bad_jump = d > float(max_successive_change_ms)
        if len(bad_jump):
            # A large jump makes both adjacent intervals suspicious.
            suspicious = np.zeros(len(rr), dtype=bool)
            suspicious[:-1] |= bad_jump
            suspicious[1:] |= bad_jump
            mask &= ~suspicious

    if max_successive_change_fraction is not None and len(rr) >= 2:
        prev = rr[:-1]
        d = np.abs(np.diff(rr))
        frac = np.full_like(d, np.inf, dtype=float)
        good_prev = np.isfinite(prev) & (prev > 0)
        frac[good_prev] = d[good_prev] / prev[good_prev]
        bad_jump = frac > float(max_successive_change_fraction)
        if len(bad_jump):
            suspicious = np.zeros(len(rr), dtype=bool)
            suspicious[:-1] |= bad_jump
            suspicious[1:] |= bad_jump
            mask &= ~suspicious

    return mask.astype(bool)


def nn_intervals_ms(
    rr_ms,
    min_rr_ms: float = 300.0,
    max_rr_ms: float = 2000.0,
    max_successive_change_ms: Optional[float] = None,
    max_successive_change_fraction: Optional[float] = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """Return accepted NN intervals and the boolean mask used."""
    rr = np.asarray(rr_ms, dtype=float)
    mask = basic_nn_mask(
        rr,
        min_rr_ms=min_rr_ms,
        max_rr_ms=max_rr_ms,
        max_successive_change_ms=max_successive_change_ms,
        max_successive_change_fraction=max_successive_change_fraction,
    )
    return rr[mask], mask


def successive_differences_ms(nn_ms) -> np.ndarray:
    """Return NN(n+1)-NN(n) in milliseconds."""
    nn = np.asarray(nn_ms, dtype=float)
    nn = nn[np.isfinite(nn)]
    if len(nn) < 2:
        return np.array([], dtype=float)
    return np.diff(nn)


def time_domain_stats(nn_ms) -> Dict[str, float]:
    """
    Standard time-domain HRV statistics from NN intervals in ms.

    Returns NaN for metrics that need more intervals than available.
    SDNN/SDSD use sample standard deviation, ddof=1.
    """
    nn = np.asarray(nn_ms, dtype=float)
    nn = nn[np.isfinite(nn)]
    n = int(len(nn))

    stats: Dict[str, float] = {
        "n_nn": float(n),
        "mean_nn_ms": np.nan,
        "mean_hr_bpm": np.nan,
        "sdnn_ms": np.nan,
        "rmssd_ms": np.nan,
        "sdsd_ms": np.nan,
        "pnn50_percent": np.nan,
        "min_nn_ms": np.nan,
        "max_nn_ms": np.nan,
    }

    if n == 0:
        return stats

    mean_nn = float(np.mean(nn))
    stats["mean_nn_ms"] = mean_nn
    stats["mean_hr_bpm"] = float(60000.0 / mean_nn) if mean_nn > 0 else np.nan
    stats["min_nn_ms"] = float(np.min(nn))
    stats["max_nn_ms"] = float(np.max(nn))

    if n >= 2:
        stats["sdnn_ms"] = float(np.std(nn, ddof=1))
        d = np.diff(nn)
        stats["rmssd_ms"] = float(np.sqrt(np.mean(d ** 2))) if len(d) else np.nan
        stats["pnn50_percent"] = float(100.0 * np.mean(np.abs(d) > 50.0)) if len(d) else np.nan
        if len(d) >= 2:
            stats["sdsd_ms"] = float(np.std(d, ddof=1))

    return stats


def build_rr_nn_series(time_s, r_peaks, use_complete_peaks: bool = True):
    """
    Build core RR/NN arrays for future visual HRV tabs.

    Returns a dictionary:
        r_times_s
        rr_ms
        rr_mid_times_s
        instant_hr_bpm
        nn_ms
        nn_mask
        nn_mid_times_s
        stats
    """
    peaks = np.asarray(r_peaks, dtype=int)
    rt = r_peak_times_s(time_s, peaks)
    rr = rr_intervals_ms(time_s, peaks)
    mid = rr_interval_mid_times_s(time_s, peaks)
    hr = instant_hr_bpm_from_rr_ms(rr)
    nn, mask = nn_intervals_ms(rr)
    nn_mid = mid[mask] if len(mid) == len(mask) else np.array([], dtype=float)
    stats = time_domain_stats(nn)

    return {
        "r_times_s": rt,
        "rr_ms": rr,
        "rr_mid_times_s": mid,
        "instant_hr_bpm": hr,
        "nn_ms": nn,
        "nn_mask": mask,
        "nn_mid_times_s": nn_mid,
        "stats": stats,
    }
