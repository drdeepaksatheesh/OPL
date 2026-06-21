# analysis/signal_quality.py

import numpy as np
from scipy.signal import welch


def _safe_array(values):
    arr = np.asarray(values, dtype=float)

    if arr.ndim != 1:
        arr = arr.ravel()

    return arr[np.isfinite(arr)]


def _safe_float(value):
    try:
        value = float(value)
    except Exception:
        return None

    if not np.isfinite(value):
        return None

    return value


def _basic_stats(signal):
    y = _safe_array(signal)

    if len(y) == 0:
        return {
            "samples": 0,
            "min": None,
            "max": None,
            "mean": None,
            "median": None,
            "std": None,
            "rms": None,
            "peak_to_peak": None
        }

    return {
        "samples": int(len(y)),
        "min": _safe_float(np.min(y)),
        "max": _safe_float(np.max(y)),
        "mean": _safe_float(np.mean(y)),
        "median": _safe_float(np.median(y)),
        "std": _safe_float(np.std(y)),
        "rms": _safe_float(np.sqrt(np.mean(y ** 2))),
        "peak_to_peak": _safe_float(np.ptp(y))
    }


def _band_power_welch(signal, fs, low_hz, high_hz):
    y = _safe_array(signal)

    if len(y) < max(16, int(fs)):
        return None

    try:
        nperseg = min(len(y), int(fs * 4))
        freqs, psd = welch(y, fs=fs, nperseg=nperseg)

        mask = (freqs >= low_hz) & (freqs <= high_hz)

        if not np.any(mask):
            return None

        return _safe_float(np.trapz(psd[mask], freqs[mask]))

    except Exception:
        return None


def _noise_report(signal, fs):
    y = _safe_array(signal)

    if len(y) < max(16, int(fs)):
        return {
            "baseline_drift_power_0_to_0_5_hz": None,
            "powerline_power_49_to_51_hz": None,
            "signal_band_power_0_5_to_40_hz": None,
            "powerline_to_signal_ratio": None,
            "baseline_to_signal_ratio": None
        }

    baseline_power = _band_power_welch(y, fs, 0.0, 0.5)
    powerline_power = _band_power_welch(y, fs, 49.0, 51.0)
    signal_power = _band_power_welch(y, fs, 0.5, 40.0)

    powerline_ratio = None
    baseline_ratio = None

    if signal_power is not None and signal_power > 0:
        if powerline_power is not None:
            powerline_ratio = _safe_float(powerline_power / signal_power)

        if baseline_power is not None:
            baseline_ratio = _safe_float(baseline_power / signal_power)

    return {
        "baseline_drift_power_0_to_0_5_hz": baseline_power,
        "powerline_power_49_to_51_hz": powerline_power,
        "signal_band_power_0_5_to_40_hz": signal_power,
        "powerline_to_signal_ratio": powerline_ratio,
        "baseline_to_signal_ratio": baseline_ratio
    }


def _artifact_flags(signal, fs, check_adc_clipping=True):
    y = _safe_array(signal)

    if len(y) < 2:
        return {
            "adc_clipping_checked": bool(check_adc_clipping),
            "possible_clipping_low_count": 0,
            "possible_clipping_high_count": 0,
            "possible_flatline_segments": 0,
            "large_jump_count": 0,
            "large_jump_threshold": None
        }

    if check_adc_clipping:
        # NPG-like 12-bit ADC range. Valid only for original non-inverted raw ADC values.
        possible_clipping_low_count = int(np.sum(y <= 1))
        possible_clipping_high_count = int(np.sum(y >= 4094))
    else:
        possible_clipping_low_count = None
        possible_clipping_high_count = None

    dy = np.diff(y)
    abs_dy = np.abs(dy)

    median_dy = np.median(abs_dy)
    mad_dy = np.median(np.abs(abs_dy - median_dy))

    threshold = max(
        float(median_dy + 10.0 * mad_dy),
        float(0.15 * np.ptp(y)),
        1.0
    )

    large_jump_count = int(np.sum(abs_dy > threshold))

    eps = max(1e-9, 0.001 * max(np.ptp(y), 1.0))
    flat = abs_dy <= eps

    min_run = max(2, int(0.5 * fs))
    flatline_segments = 0
    run = 0

    for item in flat:
        if item:
            run += 1
        else:
            if run >= min_run:
                flatline_segments += 1
            run = 0

    if run >= min_run:
        flatline_segments += 1

    return {
        "adc_clipping_checked": bool(check_adc_clipping),
        "possible_clipping_low_count": possible_clipping_low_count,
        "possible_clipping_high_count": possible_clipping_high_count,
        "possible_flatline_segments": int(flatline_segments),
        "large_jump_count": large_jump_count,
        "large_jump_threshold": _safe_float(threshold)
    }


def _rr_quality_report(peak_times_s):
    peak_times = _safe_array(peak_times_s)

    if len(peak_times) < 2:
        return {
            "rr_count": 0,
            "rr_mean_ms": None,
            "rr_median_ms": None,
            "rr_min_ms": None,
            "rr_max_ms": None,
            "rr_outlier_count": 0,
            "possible_extra_beat_count": 0,
            "possible_missed_beat_count": 0
        }

    rr_ms = np.diff(peak_times) * 1000.0

    median_rr = float(np.median(rr_ms))

    if median_rr <= 0:
        outlier_count = 0
        extra_count = 0
        missed_count = 0
    else:
        lower = 0.80 * median_rr
        upper = 1.20 * median_rr

        outlier_count = int(np.sum((rr_ms < lower) | (rr_ms > upper)))
        extra_count = int(np.sum(rr_ms < 0.70 * median_rr))
        missed_count = int(np.sum(rr_ms > 1.30 * median_rr))

    return {
        "rr_count": int(len(rr_ms)),
        "rr_mean_ms": _safe_float(np.mean(rr_ms)),
        "rr_median_ms": _safe_float(np.median(rr_ms)),
        "rr_min_ms": _safe_float(np.min(rr_ms)),
        "rr_max_ms": _safe_float(np.max(rr_ms)),
        "rr_outlier_count": outlier_count,
        "possible_extra_beat_count": extra_count,
        "possible_missed_beat_count": missed_count
    }


def assess_signal_quality(
    t,
    raw_signal,
    filtered_signal,
    fs,
    peak_indices=None
):
    """
    Descriptive signal quality report.

    This does NOT modify raw data.
    This does NOT correct artifacts.
    It only reports possible quality issues.
    """

    t = np.asarray(t, dtype=float)
    raw = np.asarray(raw_signal, dtype=float)
    filtered = np.asarray(filtered_signal, dtype=float)

    finite_mask = np.isfinite(t) & np.isfinite(raw) & np.isfinite(filtered)

    t = t[finite_mask]
    raw = raw[finite_mask]
    filtered = filtered[finite_mask]

    duration_s = None

    if len(t) >= 2:
        duration_s = _safe_float(t[-1] - t[0])

    raw_stats = _basic_stats(raw)
    filtered_stats = _basic_stats(filtered)

    raw_noise = _noise_report(raw, fs)
    filtered_noise = _noise_report(filtered, fs)

    raw_artifacts = _artifact_flags(raw, fs, check_adc_clipping=True)
    filtered_artifacts = _artifact_flags(filtered, fs, check_adc_clipping=False)

    rms_ratio_filtered_to_raw = None

    raw_rms = raw_stats.get("rms")
    filtered_rms = filtered_stats.get("rms")

    if raw_rms is not None and raw_rms > 0 and filtered_rms is not None:
        rms_ratio_filtered_to_raw = _safe_float(filtered_rms / raw_rms)

    peak_times = []

    if peak_indices is not None:
        peak_indices = np.asarray(peak_indices, dtype=int)
        peak_indices = peak_indices[(peak_indices >= 0) & (peak_indices < len(t))]

        if len(peak_indices) > 0:
            peak_times = t[peak_indices].tolist()

    rr_quality = _rr_quality_report(peak_times)

    interpretation_flags = []

    low_clip = raw_artifacts.get("possible_clipping_low_count")
    high_clip = raw_artifacts.get("possible_clipping_high_count")

    if low_clip is not None and high_clip is not None:
        if low_clip > 0 or high_clip > 0:
            interpretation_flags.append("Possible ADC clipping/saturation detected in original raw ADC signal.")

    if raw_artifacts["large_jump_count"] > 0:
        interpretation_flags.append("Large sudden jumps detected in raw signal; possible motion/electrode artifact.")

    if raw_artifacts["possible_flatline_segments"] > 0:
        interpretation_flags.append("Possible flatline segment detected in raw signal.")

    if filtered_noise["powerline_to_signal_ratio"] is not None:
        if filtered_noise["powerline_to_signal_ratio"] > 0.10:
            interpretation_flags.append("Residual 50 Hz component may still be prominent after filtering.")

    if rr_quality["rr_outlier_count"] > 0:
        interpretation_flags.append("RR outliers detected; inspect peaks manually before HRV interpretation.")

    return {
        "report_type": "descriptive_signal_quality",
        "modifies_raw_data": False,
        "artifact_correction_applied": False,
        "duration_s": duration_s,
        "sampling_rate_hz": _safe_float(fs),
        "raw_signal_stats": raw_stats,
        "filtered_signal_stats": filtered_stats,
        "raw_noise_estimates": raw_noise,
        "filtered_noise_estimates": filtered_noise,
        "raw_artifact_flags": raw_artifacts,
        "filtered_artifact_flags": filtered_artifacts,
        "rms_ratio_filtered_to_raw": rms_ratio_filtered_to_raw,
        "rr_quality": rr_quality,
        "interpretation_flags": interpretation_flags
    }


def build_provenance_report(
    low_hz,
    high_hz,
    notch_50hz,
    inverted,
    selection
):
    return {
        "source_data": "raw.csv",
        "raw_data_modified": False,
        "processing_location": "in_memory_only",
        "filtering": {
            "applied_to": "raw.csv loaded signal",
            "low_hz": float(low_hz),
            "high_hz": float(high_hz),
            "notch_50hz": bool(notch_50hz),
            "saved_as_processed_file": False
        },
        "polarity": {
            "display_or_analysis_inverted": bool(inverted),
            "raw_file_changed_by_inversion": False
        },
        "peak_detection": {
            "performed_on": "filtered_from_raw_signal",
            "raw_monitor_peak_markers": "detected peak timings projected back onto raw signal display",
            "filtered_monitor_peak_markers": "detected peak locations on filtered signal"
        },
        "selection": selection,
        "correction_policy": {
            "artifact_detection": "descriptive flags only",
            "artifact_correction": "not applied",
            "rr_correction": "not applied"
        }
    }