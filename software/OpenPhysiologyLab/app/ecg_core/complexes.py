
from __future__ import annotations

import numpy as np


def pair_count_from_complete_peaks(complete_peaks) -> int:
    return max(0, len(complete_peaks) - 1)


def pair_indices(pair_index: int, complete_peaks):
    peaks = np.asarray(complete_peaks, dtype=int)
    if len(peaks) < 2:
        raise ValueError("Need at least two complete complexes.")
    i = int(max(0, min(int(pair_index), len(peaks) - 2)))
    return int(peaks[i]), int(peaks[i + 1])


def pair_time_window(time_s, r1_index: int, r2_index: int, pre_r_s: float, post_r_s: float):
    t = np.asarray(time_s, dtype=float)
    r1_t = float(t[int(r1_index)])
    r2_t = float(t[int(r2_index)])
    start_t = max(float(t[0]), r1_t - float(pre_r_s))
    end_t = min(float(t[-1]), r2_t + float(post_r_s))
    return start_t, end_t
