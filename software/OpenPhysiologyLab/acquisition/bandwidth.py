# acquisition/bandwidth.py

"""
Bandwidth and acquisition safety logic for OpenPhysiologyLab.

This module helps the acquisition GUI guide the user.

It does NOT permanently block experimental settings.
It classifies them as:
- Excellent
- Good
- Borderline
- Risky

Based on:
1. Estimated data load
2. Real NPG Lite test results
3. Transport method
"""

SUPPORTED_CHANNELS = [1, 2, 3, 4, 5, 6]
SUPPORTED_SAMPLE_RATES = [250, 500, 1000]
SUPPORTED_TRANSPORTS = ["USB_SERIAL", "BLE", "WIFI"]


def estimate_csv_bytes_per_sample(num_channels: int) -> int:
    """
    Estimate transmitted bytes per sample line for text CSV streaming.

    Format:
    sample,time_us,ch1,ch2,ch3,ch4,ch5,ch6

    This is approximate.
    """

    base_bytes = 20
    bytes_per_channel = 6

    return base_bytes + (num_channels * bytes_per_channel)


def estimate_data_rate_bytes_per_second(num_channels: int, sample_rate_hz: int) -> int:
    bytes_per_sample = estimate_csv_bytes_per_sample(num_channels)
    return bytes_per_sample * sample_rate_hz


def baud_to_bytes_per_second(baud_rate: int) -> float:
    """
    Serial baud to approximate usable bytes/s.

    Classic UART estimate:
    10 bits are used to transmit 1 byte.
    """

    return baud_rate / 10


def estimate_serial_load_percent(num_channels: int, sample_rate_hz: int, baud_rate: int) -> float:
    required = estimate_data_rate_bytes_per_second(num_channels, sample_rate_hz)
    available = baud_to_bytes_per_second(baud_rate)

    if available <= 0:
        return 999.0

    return (required / available) * 100


def classify_usb_serial_from_real_tests(num_channels: int, sample_rate_hz: int, duration_seconds: int = 300) -> tuple:
    """
    Real-world rule set from our NPG Lite USB serial tests.

    Observed:
    - 1 ch @ 500 Hz, 5 min: PASS
    - 6 ch @ 500 Hz, 5 min: PASS
    - 1 ch @ 1000 Hz, 1 min: PASS
    - 6 ch @ 1000 Hz, 1 min: PASS
    - 6 ch @ 1000 Hz, 5 min: FAIL/BORDERLINE with missing samples
    """

    # Very safe educational/research settings
    if sample_rate_hz in [250, 500]:
        if num_channels <= 6:
            return (
                "Good",
                "Tested logic suggests this is suitable. Still verify sample integrity after recording."
            )

    # 1000 Hz, low channel count
    if sample_rate_hz == 1000:
        if num_channels <= 2:
            return (
                "Good",
                "Likely suitable. Low channel count at 1000 Hz is expected to be stable, but verify integrity."
            )

        if num_channels == 3:
            return (
                "Borderline",
                "Likely usable, but not yet fully validated for long recordings. Run integrity check."
            )

        if num_channels in [4, 5]:
            return (
                "Borderline",
                "Higher channel count at 1000 Hz may stress the pipeline. Use for testing or short recordings first."
            )

        if num_channels == 6:
            if duration_seconds <= 60:
                return (
                    "Borderline",
                    "6 channels at 1000 Hz passed short testing, but use caution."
                )
            else:
                return (
                    "Risky",
                    "6 channels at 1000 Hz showed missing samples during 5-minute testing. Prefer 500 Hz."
                )

    return (
        "Risky",
        "This channel/rate combination is outside the recommended tested envelope."
    )


def classify_wireless(transport: str, num_channels: int, sample_rate_hz: int) -> tuple:
    transport = transport.upper()

    if transport == "BLE":
        if num_channels <= 2 and sample_rate_hz <= 500:
            return (
                "Good",
                "BLE may be usable for low-channel acquisition, but timing and packet integrity must be verified."
            )

        if num_channels <= 3 and sample_rate_hz <= 250:
            return (
                "Borderline",
                "BLE may work at low rates, but buffering and packet timing must be checked."
            )

        return (
            "Risky",
            "BLE is not recommended for high-channel raw acquisition."
        )

    if transport == "WIFI":
        if num_channels <= 6 and sample_rate_hz <= 500:
            return (
                "Good",
                "Wi-Fi is promising for multi-channel acquisition, but packet loss must be measured."
            )

        if num_channels <= 6 and sample_rate_hz <= 1000:
            return (
                "Borderline",
                "Possible with optimized firmware, but dropped packets must be checked carefully."
            )

        return (
            "Risky",
            "Too ambitious without optimized buffering or binary streaming."
        )

    return (
        "Risky",
        "Unknown wireless transport."
    )


def recommend_setup(
    num_channels: int,
    sample_rate_hz: int,
    baud_rate: int = 230400,
    transport: str = "USB_SERIAL",
    duration_seconds: int = 300
) -> dict:
    """
    Main function used by acquisition GUI.

    Returns a dictionary that can be displayed in the app.
    """

    transport = transport.upper()

    if num_channels not in SUPPORTED_CHANNELS:
        return {
            "status": "Invalid",
            "message": "Channel count must be 1 to 6."
        }

    if sample_rate_hz not in SUPPORTED_SAMPLE_RATES:
        return {
            "status": "Invalid",
            "message": "Sample rate must be 250, 500, or 1000 Hz."
        }

    if transport not in SUPPORTED_TRANSPORTS:
        return {
            "status": "Invalid",
            "message": "Transport must be USB_SERIAL, BLE, or WIFI."
        }

    if transport == "USB_SERIAL":
        load_percent = estimate_serial_load_percent(
            num_channels=num_channels,
            sample_rate_hz=sample_rate_hz,
            baud_rate=baud_rate
        )

        status, message = classify_usb_serial_from_real_tests(
            num_channels=num_channels,
            sample_rate_hz=sample_rate_hz,
            duration_seconds=duration_seconds
        )

        return {
            "transport": transport,
            "channels": num_channels,
            "sample_rate_hz": sample_rate_hz,
            "baud_rate": baud_rate,
            "duration_seconds": duration_seconds,
            "estimated_csv_load_percent": round(load_percent, 1),
            "status": status,
            "message": message
        }

    status, message = classify_wireless(
        transport=transport,
        num_channels=num_channels,
        sample_rate_hz=sample_rate_hz
    )

    return {
        "transport": transport,
        "channels": num_channels,
        "sample_rate_hz": sample_rate_hz,
        "baud_rate": None,
        "duration_seconds": duration_seconds,
        "estimated_csv_load_percent": None,
        "status": status,
        "message": message
    }


if __name__ == "__main__":
    test_cases = [
        ("USB_SERIAL", 1, 500, 230400, 300),
        ("USB_SERIAL", 6, 500, 230400, 300),
        ("USB_SERIAL", 1, 1000, 230400, 60),
        ("USB_SERIAL", 6, 1000, 230400, 60),
        ("USB_SERIAL", 6, 1000, 230400, 300),
        ("BLE", 2, 500, 0, 300),
        ("BLE", 6, 500, 0, 300),
        ("WIFI", 6, 500, 0, 300),
        ("WIFI", 6, 1000, 0, 300),
    ]

    for transport, channels, rate, baud, duration in test_cases:
        result = recommend_setup(
            num_channels=channels,
            sample_rate_hz=rate,
            baud_rate=baud,
            transport=transport,
            duration_seconds=duration
        )

        print(result)