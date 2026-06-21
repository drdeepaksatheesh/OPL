# analysis/selection_metrics.py

import numpy as np


def calculate_selection_metrics(x, y, peaks):
    """
    Calculate reusable selection metrics from signal and detected peaks.

    Parameters
    ----------
    x : array-like
        Time values in seconds.

    y : array-like
        Signal values. Usually raw ADC or filtered ADC values.

    peaks : array-like
        Indices of detected peaks in x/y arrays.

    Returns
    -------
    metrics : dict
        Dictionary containing signal metrics, peak metrics, HR metrics,
        and HRV-ready RR interval metrics.

    Notes
    -----
    This function does not detect peaks.
    Peak detection must be done separately by analysis/peak_detection.py.
    """

    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    peaks = np.asarray(peaks, dtype=int)

    metrics = {
        "duration_s": None,
        "sample_count": int(len(y)),
        "peak_count": int(len(peaks)),

        "hr_count_based_bpm": None,
        "hr_rr_based_bpm": None,

        "peak_times_s": [],
        "rr_intervals_s": [],
        "rr_intervals_ms": [],

        "rr_mean_ms": None,
        "rr_median_ms": None,
        "rr_min_ms": None,
        "rr_max_ms": None,

        "sdnn_ms": None,
        "rmssd_ms": None,
        "sdsd_ms": None,
        "nn50_count": None,
        "pnn50_percent": None,

        "signal_min": None,
        "signal_max": None,
        "signal_mean": None,
        "signal_median": None,
        "signal_std": None,
        "signal_peak_to_peak": None,

        "peak_amp_mean": None,
        "peak_amp_min": None,
        "peak_amp_max": None,

        "quality_flags": []
    }

    if len(x) == 0 or len(y) == 0:
        metrics["quality_flags"].append("empty_signal")
        return metrics

    if len(x) != len(y):
        metrics["quality_flags"].append("x_y_length_mismatch")
        return metrics

    duration_s = float(x[-1] - x[0]) if len(x) > 1 else 0.0
    metrics["duration_s"] = duration_s

    metrics["signal_min"] = float(np.min(y))
    metrics["signal_max"] = float(np.max(y))
    metrics["signal_mean"] = float(np.mean(y))
    metrics["signal_median"] = float(np.median(y))
    metrics["signal_std"] = float(np.std(y))
    metrics["signal_peak_to_peak"] = float(np.ptp(y))

    if duration_s <= 0:
        metrics["quality_flags"].append("zero_or_negative_duration")
        return metrics

    if len(peaks) > 0:
        valid_peaks = peaks[(peaks >= 0) & (peaks < len(x))]
        valid_peaks = np.asarray(valid_peaks, dtype=int)

        if len(valid_peaks) != len(peaks):
            metrics["quality_flags"].append("invalid_peak_indices_removed")

        peaks = valid_peaks
        metrics["peak_count"] = int(len(peaks))

    if len(peaks) == 0:
        metrics["quality_flags"].append("no_peaks_detected")
        return metrics

    peak_times_s = x[peaks]
    peak_values = y[peaks]

    metrics["peak_times_s"] = peak_times_s.tolist()

    metrics["peak_amp_mean"] = float(np.mean(peak_values))
    metrics["peak_amp_min"] = float(np.min(peak_values))
    metrics["peak_amp_max"] = float(np.max(peak_values))

    metrics["hr_count_based_bpm"] = float((len(peaks) / duration_s) * 60.0)

    if len(peaks) < 2:
        metrics["quality_flags"].append("less_than_two_peaks_no_rr_metrics")
        return metrics

    rr_intervals_s = np.diff(peak_times_s)
    rr_intervals_ms = rr_intervals_s * 1000.0

    metrics["rr_intervals_s"] = rr_intervals_s.tolist()
    metrics["rr_intervals_ms"] = rr_intervals_ms.tolist()

    if len(rr_intervals_s) == 0:
        metrics["quality_flags"].append("no_rr_intervals")
        return metrics

    rr_mean_s = float(np.mean(rr_intervals_s))

    if rr_mean_s > 0:
        metrics["hr_rr_based_bpm"] = float(60.0 / rr_mean_s)

    metrics["rr_mean_ms"] = float(np.mean(rr_intervals_ms))
    metrics["rr_median_ms"] = float(np.median(rr_intervals_ms))
    metrics["rr_min_ms"] = float(np.min(rr_intervals_ms))
    metrics["rr_max_ms"] = float(np.max(rr_intervals_ms))

    # SDNN requires at least 2 RR intervals because ddof=1 is used.
    if len(rr_intervals_ms) >= 2:
        metrics["sdnn_ms"] = float(np.std(rr_intervals_ms, ddof=1))
    else:
        metrics["quality_flags"].append("less_than_two_rr_intervals_no_sdnn")

    successive_differences_ms = np.diff(rr_intervals_ms)

    # RMSSD, NN50, pNN50 require at least 1 successive difference.
    if len(successive_differences_ms) >= 1:
        metrics["rmssd_ms"] = float(
            np.sqrt(np.mean(successive_differences_ms ** 2))
        )

        nn50 = int(np.sum(np.abs(successive_differences_ms) > 50.0))
        metrics["nn50_count"] = nn50

        metrics["pnn50_percent"] = float(
            (nn50 / len(successive_differences_ms)) * 100.0
        )
    else:
        metrics["quality_flags"].append("no_successive_differences_no_rmssd_nn50")

    # SDSD requires at least 2 successive differences because ddof=1 is used.
    if len(successive_differences_ms) >= 2:
        metrics["sdsd_ms"] = float(np.std(successive_differences_ms, ddof=1))
    else:
        metrics["quality_flags"].append("less_than_two_successive_differences_no_sdsd")

    return metrics


def format_selection_metrics_text(
    channel,
    trace_type,
    x1,
    x2,
    peak_method,
    peak_polarity,
    peak_warning,
    metrics
):
    """
    Format selection metrics for display in the acquisition review panel.
    """

    duration = metrics.get("duration_s")
    sample_count = metrics.get("sample_count")
    peak_count = metrics.get("peak_count")

    hr_count = metrics.get("hr_count_based_bpm")
    hr_rr = metrics.get("hr_rr_based_bpm")

    rr_mean = metrics.get("rr_mean_ms")
    rr_min = metrics.get("rr_min_ms")
    rr_max = metrics.get("rr_max_ms")

    sdnn = metrics.get("sdnn_ms")
    rmssd = metrics.get("rmssd_ms")
    sdsd = metrics.get("sdsd_ms")
    nn50 = metrics.get("nn50_count")
    pnn50 = metrics.get("pnn50_percent")

    signal_min = metrics.get("signal_min")
    signal_max = metrics.get("signal_max")
    signal_mean = metrics.get("signal_mean")
    signal_ptp = metrics.get("signal_peak_to_peak")

    peak_amp_mean = metrics.get("peak_amp_mean")
    peak_amp_max = metrics.get("peak_amp_max")

    quality_flags = metrics.get("quality_flags", [])

    def fmt(value, decimals=1):
        if value is None:
            return "--"
        return f"{value:.{decimals}f}"

    warning_text = f" | Warning: {peak_warning}" if peak_warning else ""

    if quality_flags:
        quality_text = ", ".join(quality_flags)
    else:
        quality_text = "none"

    text = (
        f"Selection Analysis\n"
        f"{channel} {trace_type} | {x1:.3f}–{x2:.3f} s | "
        f"duration: {fmt(duration, 3)} s | samples: {sample_count}\n"
        f"Peaks: {peak_count} | method: {peak_method} | polarity: {peak_polarity}{warning_text}\n"
        f"HR(count): {fmt(hr_count)} bpm | HR(RR): {fmt(hr_rr)} bpm | "
        f"RR mean: {fmt(rr_mean)} ms | RR min/max: {fmt(rr_min)}/{fmt(rr_max)} ms\n"
        f"SDNN: {fmt(sdnn)} ms | RMSSD: {fmt(rmssd)} ms | SDSD: {fmt(sdsd)} ms | "
        f"NN50: {nn50 if nn50 is not None else '--'} | pNN50: {fmt(pnn50)} %\n"
        f"Signal: min {fmt(signal_min)}, max {fmt(signal_max)}, mean {fmt(signal_mean)}, "
        f"peak-to-peak {fmt(signal_ptp)} ADC | "
        f"Peak amp mean/max: {fmt(peak_amp_mean)}/{fmt(peak_amp_max)} ADC\n"
        f"Quality flags: {quality_text}"
    )

    return text