# analysis/peak_detection.py

import numpy as np
from scipy.signal import find_peaks


def _safe_float_array(values):
    """
    Convert input to clean float numpy array.
    """

    arr = np.asarray(values, dtype=float)

    if arr.ndim != 1:
        arr = arr.ravel()

    finite_mask = np.isfinite(arr)

    if not np.all(finite_mask):
        arr = arr[finite_mask]

    return arr


def _robust_mad(values):
    """
    Median absolute deviation based robust noise estimate.
    """

    values = np.asarray(values, dtype=float)

    if len(values) == 0:
        return 0.0

    median = np.median(values)
    mad = np.median(np.abs(values - median))

    return float(mad)


def _estimate_signal_polarity(y):
    """
    Decide whether dominant sharp ECG deflections are positive or negative.

    ECG R waves are brief. Percentiles can miss very narrow spikes,
    so this function uses extreme deflection from baseline first,
    then percentile deflection as a backup.
    """

    y = np.asarray(y, dtype=float)

    if len(y) == 0:
        return "positive"

    median = float(np.median(y))

    max_value = float(np.max(y))
    min_value = float(np.min(y))

    positive_extreme = max_value - median
    negative_extreme = median - min_value

    p99 = float(np.percentile(y, 99))
    p01 = float(np.percentile(y, 1))

    positive_percentile = p99 - median
    negative_percentile = median - p01

    positive_score = max(positive_extreme, positive_percentile)
    negative_score = max(negative_extreme, negative_percentile)

    if negative_score > positive_score:
        return "negative"

    return "positive"


def detect_general_peaks(x, y, fs, min_distance_seconds=0.25):
    """
    General adaptive peak detector.

    Useful for quick preview of ECG/EMG-like periodic peaks.
    Not a final diagnostic ECG algorithm.
    """

    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)

    if len(y) < max(10, int(fs * 0.5)):
        return {
            "peaks": np.array([], dtype=int),
            "polarity": "insufficient data",
            "method": "general",
            "warning": "Selection too short."
        }

    if len(x) != len(y):
        return {
            "peaks": np.array([], dtype=int),
            "polarity": "error",
            "method": "general",
            "warning": "x and y length mismatch."
        }

    y_centered = y - np.median(y)
    y_std = float(np.std(y_centered))

    if y_std <= 1e-9:
        return {
            "peaks": np.array([], dtype=int),
            "polarity": "flat",
            "method": "general",
            "warning": "Signal is flat."
        }

    min_distance = max(1, int(min_distance_seconds * fs))
    prominence = max(y_std * 0.8, 1.0)

    positive_peaks, positive_props = find_peaks(
        y_centered,
        distance=min_distance,
        prominence=prominence
    )

    negative_peaks, negative_props = find_peaks(
        -y_centered,
        distance=min_distance,
        prominence=prominence
    )

    positive_score = 0.0
    negative_score = 0.0

    if len(positive_peaks) > 0 and "prominences" in positive_props:
        positive_score = float(np.median(positive_props["prominences"])) * len(positive_peaks)

    if len(negative_peaks) > 0 and "prominences" in negative_props:
        negative_score = float(np.median(negative_props["prominences"])) * len(negative_peaks)

    if negative_score > positive_score:
        return {
            "peaks": negative_peaks,
            "polarity": "negative",
            "method": "general",
            "warning": None
        }

    return {
        "peaks": positive_peaks,
        "polarity": "positive",
        "method": "general",
        "warning": None
    }


def detect_ecg_r_peaks(
    x,
    y,
    fs,
    max_hr_bpm=220,
    min_hr_bpm=30,
    preferred_min_rr_seconds=0.30,
    forced_polarity="auto",
    min_qrs_height_fraction=0.20,
    min_qrs_prominence_fraction=0.15,
    min_qrs_noise_multiple=3.0
):
    """
    ECG-oriented R-peak detector for review/analysis preview.

    Auto polarity logic:
    - Test positive and negative candidate QRS peak trains.
    - Apply QRS-like thresholds to both:
        1. repeated peak height
        2. repeated peak prominence
        3. physiologic peak count / HR
        4. RR regularity
    - Choose the polarity with stronger repeated QRS-like peaks.

    Manual override:
    - forced_polarity="positive" detects upward QRS peaks.
    - forced_polarity="negative" detects downward QRS peaks.
    - forced_polarity="auto" compares both.

    This is not a clinical-grade ECG detector yet.
    It is a transparent review/teaching detector.
    """

    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)

    warnings = []

    if len(x) == 0 or len(y) == 0:
        return {
            "peaks": np.array([], dtype=int),
            "polarity": "empty",
            "polarity_source": "none",
            "method": "ecg_r_peak_adaptive_v4_qrs_threshold",
            "warning": "Empty signal."
        }

    if len(x) != len(y):
        return {
            "peaks": np.array([], dtype=int),
            "polarity": "error",
            "polarity_source": "none",
            "method": "ecg_r_peak_adaptive_v4_qrs_threshold",
            "warning": "x and y length mismatch."
        }

    if fs <= 0:
        return {
            "peaks": np.array([], dtype=int),
            "polarity": "error",
            "polarity_source": "none",
            "method": "ecg_r_peak_adaptive_v4_qrs_threshold",
            "warning": "Invalid sampling rate."
        }

    min_required_samples = max(10, int(fs * 1.0))

    if len(y) < min_required_samples:
        return {
            "peaks": np.array([], dtype=int),
            "polarity": "insufficient data",
            "polarity_source": "none",
            "method": "ecg_r_peak_adaptive_v4_qrs_threshold",
            "warning": "Selection too short for ECG R-peak detection."
        }

    duration_s = float(x[-1] - x[0])

    if duration_s <= 0:
        return {
            "peaks": np.array([], dtype=int),
            "polarity": "error",
            "polarity_source": "none",
            "method": "ecg_r_peak_adaptive_v4_qrs_threshold",
            "warning": "Zero or negative duration."
        }

    y_centered = y - np.median(y)

    y_ptp = float(np.ptp(y_centered))
    y_std = float(np.std(y_centered))
    y_mad = _robust_mad(y_centered)

    if y_ptp <= 1e-9 or y_std <= 1e-9:
        return {
            "peaks": np.array([], dtype=int),
            "polarity": "flat",
            "polarity_source": "none",
            "method": "ecg_r_peak_adaptive_v4_qrs_threshold",
            "warning": "Signal is flat or near-flat."
        }

    # Refractory period / minimum RR.
    min_rr_from_max_hr = 60.0 / float(max_hr_bpm)
    min_distance_seconds = max(min_rr_from_max_hr, preferred_min_rr_seconds)
    min_distance_samples = max(1, int(round(min_distance_seconds * fs)))

    # Robust noise estimate.
    robust_noise = max(y_mad * 1.4826, y_std * 0.35, 1.0)

    # Explicit QRS thresholds.
    minimum_height_threshold = max(
        float(min_qrs_height_fraction) * y_ptp,
        min_qrs_noise_multiple * robust_noise
    )

    minimum_prominence_threshold = max(
        float(min_qrs_prominence_fraction) * y_ptp,
        min_qrs_noise_multiple * robust_noise
    )

    # Try several thresholds, strict first, relaxed later.
    candidate_prominence_thresholds = [
        max(0.35 * y_ptp, 5.0 * robust_noise, minimum_prominence_threshold),
        max(0.30 * y_ptp, 4.5 * robust_noise, minimum_prominence_threshold),
        max(0.25 * y_ptp, 4.0 * robust_noise, minimum_prominence_threshold),
        max(0.20 * y_ptp, 3.5 * robust_noise, minimum_prominence_threshold),
        max(0.15 * y_ptp, 3.0 * robust_noise, minimum_prominence_threshold),
    ]

    def evaluate_peak_train(peaks, props, polarity, prominence_threshold):
        """
        Evaluate one polarity candidate peak train.

        Returns a score dictionary or None.
        Higher quality score is better.
        """

        if peaks is None or len(peaks) == 0:
            return None

        peaks = np.asarray(peaks, dtype=int)

        if polarity == "negative":
            detection_heights = -y_centered[peaks]
        else:
            detection_heights = y_centered[peaks]

        # Keep only peaks tall enough to be QRS-like.
        height_mask = detection_heights >= minimum_height_threshold

        if not np.any(height_mask):
            return None

        peaks = peaks[height_mask]
        detection_heights = detection_heights[height_mask]

        if props is not None and "prominences" in props:
            prominences = np.asarray(props["prominences"], dtype=float)
            prominences = prominences[height_mask]
        else:
            prominences = np.zeros(len(peaks), dtype=float)

        # Keep only peaks with enough local prominence.
        prominence_mask = prominences >= minimum_prominence_threshold

        if np.any(prominence_mask):
            peaks = peaks[prominence_mask]
            detection_heights = detection_heights[prominence_mask]
            prominences = prominences[prominence_mask]

        if len(peaks) == 0:
            return None

        hr_count = (len(peaks) / duration_s) * 60.0

        rr_s = np.diff(x[peaks]) if len(peaks) >= 2 else np.asarray([], dtype=float)

        rr_median = None
        rr_cv = 999.0
        rr_outlier_fraction = 1.0

        if len(rr_s) >= 2:
            rr_median = float(np.median(rr_s))

            if rr_median > 0:
                rr_cv = float(np.std(rr_s) / rr_median)

                lower = 0.70 * rr_median
                upper = 1.30 * rr_median
                rr_outlier_fraction = float(np.mean((rr_s < lower) | (rr_s > upper)))

        median_height = float(np.median(detection_heights))
        median_prominence = float(np.median(prominences)) if len(prominences) > 0 else 0.0

        height_ratio = float(median_height / max(y_ptp, 1.0))
        prominence_ratio = float(median_prominence / max(y_ptp, 1.0))

        # Physiological plausibility.
        hr_plausible = min_hr_bpm <= hr_count <= max_hr_bpm
        enough_peaks = len(peaks) >= max(3, int(duration_s * min_hr_bpm / 60.0 * 0.4))

        # Penalise detections dominated by trace edges.
        edge_s = min(1.0, max(0.25, 0.05 * duration_s))
        edge_count = int(np.sum((x[peaks] - x[0] < edge_s) | (x[-1] - x[peaks] < edge_s)))
        edge_fraction = edge_count / max(len(peaks), 1)

        # Quality components.
        hr_score = 1.0 if hr_plausible else 0.0
        peak_count_score = min(len(peaks) / max(duration_s * 0.8, 1.0), 2.0) / 2.0
        rr_score = max(0.0, 1.0 - min(rr_cv, 1.0))
        rr_outlier_score = max(0.0, 1.0 - min(rr_outlier_fraction, 1.0))
        height_score = min(max(height_ratio / max(min_qrs_height_fraction, 1e-9), 0.0), 2.0) / 2.0
        prominence_score = min(max(prominence_ratio / max(min_qrs_prominence_fraction, 1e-9), 0.0), 2.0) / 2.0
        edge_score = max(0.0, 1.0 - edge_fraction)

        quality_score = (
            height_score * 3.0
            + prominence_score * 2.0
            + rr_score * 2.0
            + rr_outlier_score * 1.5
            + hr_score * 1.0
            + peak_count_score * 0.5
            + edge_score * 0.5
        )

        if not enough_peaks:
            quality_score -= 2.0

        if not hr_plausible:
            quality_score -= 2.0

        return {
            "peaks": peaks,
            "polarity": polarity,
            "prominence_threshold": float(prominence_threshold),
            "minimum_height_threshold": float(minimum_height_threshold),
            "minimum_prominence_threshold": float(minimum_prominence_threshold),
            "hr_count": float(hr_count),
            "rr_cv": float(rr_cv),
            "rr_outlier_fraction": float(rr_outlier_fraction),
            "median_peak_height": float(median_height),
            "median_prominence": float(median_prominence),
            "height_ratio": float(height_ratio),
            "prominence_ratio": float(prominence_ratio),
            "edge_fraction": float(edge_fraction),
            "quality_score": float(quality_score),
            "hr_plausible": bool(hr_plausible),
            "enough_peaks": bool(enough_peaks)
        }

    def detect_for_polarity(polarity):
        """
        Detect candidate QRS peaks for a single polarity.
        """

        if polarity == "negative":
            detection_signal = -y_centered
        else:
            detection_signal = y_centered

        best = None

        for prominence in candidate_prominence_thresholds:
            peaks, props = find_peaks(
                detection_signal,
                distance=min_distance_samples,
                prominence=prominence
            )

            candidate = evaluate_peak_train(peaks, props, polarity, prominence)

            if candidate is None:
                continue

            if best is None or candidate["quality_score"] > best["quality_score"]:
                best = candidate

            # If it is already strong and regular, stop early.
            if (
                candidate["hr_plausible"]
                and candidate["enough_peaks"]
                and candidate["height_ratio"] >= min_qrs_height_fraction
                and candidate["prominence_ratio"] >= min_qrs_prominence_fraction
                and candidate["rr_cv"] < 0.20
                and candidate["rr_outlier_fraction"] < 0.20
            ):
                best = candidate
                break

        return best

    forced_polarity = str(forced_polarity).lower().strip()

    positive_best = None
    negative_best = None

    if forced_polarity in ["positive", "up", "upward"]:
        polarity_source = "forced"
        best = detect_for_polarity("positive")

    elif forced_polarity in ["negative", "down", "downward"]:
        polarity_source = "forced"
        best = detect_for_polarity("negative")

    else:
        polarity_source = "auto_qrs_threshold_compare_both"

        positive_best = detect_for_polarity("positive")
        negative_best = detect_for_polarity("negative")

        if positive_best is None and negative_best is None:
            # Fallback: extreme deflection, but still transparent.
            estimated = _estimate_signal_polarity(y_centered)
            best = detect_for_polarity(estimated)
            polarity_source = "auto_fallback_extreme"

        elif positive_best is None:
            best = negative_best

        elif negative_best is None:
            best = positive_best

        else:
            pos_q = positive_best["quality_score"]
            neg_q = negative_best["quality_score"]

            pos_h = positive_best["median_peak_height"]
            neg_h = negative_best["median_peak_height"]

            # If one polarity has clearly stronger repeated QRS height, prefer it.
            if pos_h >= 1.20 * max(neg_h, 1e-9):
                best = positive_best
            elif neg_h >= 1.20 * max(pos_h, 1e-9):
                best = negative_best
            else:
                best = positive_best if pos_q >= neg_q else negative_best

    if best is None or len(best["peaks"]) == 0:
        return {
            "peaks": np.array([], dtype=int),
            "polarity": str(forced_polarity),
            "polarity_source": polarity_source,
            "method": "ecg_r_peak_adaptive_v4_qrs_threshold",
            "warning": "No ECG R peaks detected.",
            "qrs_thresholds": {
                "minimum_height_threshold": float(minimum_height_threshold),
                "minimum_prominence_threshold": float(minimum_prominence_threshold),
                "min_qrs_height_fraction": float(min_qrs_height_fraction),
                "min_qrs_prominence_fraction": float(min_qrs_prominence_fraction)
            }
        }

    best_peaks = np.asarray(best["peaks"], dtype=int)
    best_hr = float(best["hr_count"])

    if best_hr > max_hr_bpm:
        warnings.append(f"Detected HR above max_hr_bpm ({best_hr:.1f} bpm). Possible over-detection.")
    elif best_hr < min_hr_bpm:
        warnings.append(f"Detected HR below min_hr_bpm ({best_hr:.1f} bpm). Possible under-detection.")

    if len(best_peaks) >= 2:
        rr_s = np.diff(x[best_peaks])

        if len(rr_s) > 0:
            rr_min = float(np.min(rr_s))
            rr_median = float(np.median(rr_s))

            if rr_min < min_distance_seconds * 0.95:
                warnings.append("Very short RR interval detected despite refractory rule.")

            if rr_median > 0:
                rr_based_hr = 60.0 / rr_median

                if rr_based_hr > max_hr_bpm:
                    warnings.append("RR-based HR is unusually high.")
                elif rr_based_hr < min_hr_bpm:
                    warnings.append("RR-based HR is unusually low.")

            if best["rr_outlier_fraction"] > 0.20:
                warnings.append("RR train is irregular; inspect peaks manually.")

    if len(best_peaks) < 2:
        warnings.append("Less than two R peaks detected; RR metrics limited.")

    warning_text = "; ".join(warnings) if warnings else None

    diagnostics = {
        "selected_quality_score": float(best["quality_score"]),
        "selected_median_peak_height": float(best["median_peak_height"]),
        "selected_median_prominence": float(best["median_prominence"]),
        "selected_height_ratio": float(best["height_ratio"]),
        "selected_prominence_ratio": float(best["prominence_ratio"]),
        "selected_rr_cv": float(best["rr_cv"]),
        "selected_rr_outlier_fraction": float(best["rr_outlier_fraction"]),
        "selected_edge_fraction": float(best["edge_fraction"])
    }

    if positive_best is not None:
        diagnostics["positive_quality_score"] = float(positive_best["quality_score"])
        diagnostics["positive_median_peak_height"] = float(positive_best["median_peak_height"])
        diagnostics["positive_height_ratio"] = float(positive_best["height_ratio"])

    if negative_best is not None:
        diagnostics["negative_quality_score"] = float(negative_best["quality_score"])
        diagnostics["negative_median_peak_height"] = float(negative_best["median_peak_height"])
        diagnostics["negative_height_ratio"] = float(negative_best["height_ratio"])

    return {
        "peaks": best_peaks,
        "polarity": best["polarity"],
        "polarity_source": polarity_source,
        "method": "ecg_r_peak_adaptive_v4_qrs_threshold",
        "warning": warning_text,
        "prominence_used": float(best["prominence_threshold"]),
        "min_distance_seconds": float(min_distance_seconds),
        "estimated_hr_count_bpm": float(best_hr),
        "qrs_thresholds": {
            "minimum_height_threshold": float(minimum_height_threshold),
            "minimum_prominence_threshold": float(minimum_prominence_threshold),
            "min_qrs_height_fraction": float(min_qrs_height_fraction),
            "min_qrs_prominence_fraction": float(min_qrs_prominence_fraction),
            "min_qrs_noise_multiple": float(min_qrs_noise_multiple)
        },
        "auto_polarity_diagnostics": diagnostics
    }

