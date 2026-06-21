# analysis/signal_filters.py

import numpy as np
from scipy.signal import butter, filtfilt, iirnotch


def apply_bandpass_notch(
    signal,
    fs,
    low_hz=0.5,
    high_hz=40.0,
    notch_hz=50.0,
    use_notch=True,
    filter_order=4,
    notch_quality=30.0
):
    """
    Apply bandpass filter and optional notch filter.

    Parameters
    ----------
    signal : array-like
        Input signal values. Usually raw ADC or voltage values.

    fs : float
        Sampling frequency in Hz.

    low_hz : float
        Lower cutoff frequency for bandpass filter.

    high_hz : float
        Upper cutoff frequency for bandpass filter.

    notch_hz : float
        Notch frequency. In India, usually 50 Hz mains noise.

    use_notch : bool
        Whether to apply notch filter.

    filter_order : int
        Butterworth bandpass filter order.

    notch_quality : float
        Q factor for notch filter. Higher = narrower notch.

    Returns
    -------
    filtered : numpy.ndarray
        Filtered signal.

    info : dict
        Information about what filtering was actually applied.
    """

    y = np.asarray(signal, dtype=float)

    info = {
        "bandpass_applied": False,
        "notch_applied": False,
        "fs_hz": fs,
        "low_hz": low_hz,
        "high_hz": high_hz,
        "notch_hz": notch_hz,
        "use_notch": use_notch,
        "filter_order": filter_order,
        "notch_quality": notch_quality,
        "warning": None
    }

    if y.size == 0:
        info["warning"] = "Empty signal."
        return y, info

    if fs is None or fs <= 0:
        info["warning"] = "Invalid sampling frequency."
        return y, info

    if y.size < 30:
        info["warning"] = "Signal too short for safe filtering."
        return y, info

    nyquist = fs / 2.0

    low = float(low_hz)
    high = float(high_hz)

    if low <= 0:
        low = 0.1

    if high >= nyquist:
        high = nyquist * 0.9

    if low >= high:
        info["warning"] = "Invalid bandpass range after Nyquist correction."
        return y, info

    filtered = y.copy()

    # Bandpass filter
    try:
        b, a = butter(
            filter_order,
            [low, high],
            btype="bandpass",
            fs=fs
        )

        padlen = 3 * max(len(a), len(b))

        if filtered.size > padlen:
            filtered = filtfilt(b, a, filtered)
            info["bandpass_applied"] = True
        else:
            info["warning"] = "Signal too short for bandpass filtfilt pad length."
            return y, info

    except Exception as e:
        info["warning"] = f"Bandpass filtering failed: {e}"
        return y, info

    # Notch filter
    if use_notch:
        try:
            if notch_hz < nyquist:
                b_notch, a_notch = iirnotch(
                    w0=notch_hz,
                    Q=notch_quality,
                    fs=fs
                )

                padlen = 3 * max(len(a_notch), len(b_notch))

                if filtered.size > padlen:
                    filtered = filtfilt(b_notch, a_notch, filtered)
                    info["notch_applied"] = True
                else:
                    info["warning"] = "Signal too short for notch filtfilt pad length."
            else:
                info["warning"] = "Notch frequency is above Nyquist frequency."

        except Exception as e:
            info["warning"] = f"Notch filtering failed: {e}"

    return filtered, info


def get_default_filter_settings(mode="ECG"):
    """
    Return sensible default filter settings for different recording modes.

    These are display/review defaults. Final analysis may use stricter settings.
    """

    mode = str(mode).upper()

    if mode == "ECG":
        return {
            "low_hz": 0.5,
            "high_hz": 40.0,
            "notch_hz": 50.0,
            "use_notch": True
        }

    if mode == "EMG":
        return {
            "low_hz": 20.0,
            "high_hz": 450.0,
            "notch_hz": 50.0,
            "use_notch": True
        }

    if mode == "EEG":
        return {
            "low_hz": 0.5,
            "high_hz": 40.0,
            "notch_hz": 50.0,
            "use_notch": True
        }

    if mode == "EOG":
        return {
            "low_hz": 0.1,
            "high_hz": 30.0,
            "notch_hz": 50.0,
            "use_notch": True
        }

    return {
        "low_hz": 0.5,
        "high_hz": 40.0,
        "notch_hz": 50.0,
        "use_notch": True
    }