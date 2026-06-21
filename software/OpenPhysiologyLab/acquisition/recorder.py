# acquisition/recorder.py

import csv
import json
import time
from datetime import datetime
from pathlib import Path

from acquisition.npg_lite import NPGLite
from acquisition.bandwidth import recommend_setup


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RECORDINGS_DIR = PROJECT_ROOT / "recordings"


def create_session_folder(mode="ECG", device_id="NPG_UNKNOWN"):
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    folder_name = f"{timestamp}_{mode}_{device_id}"

    session_folder = RECORDINGS_DIR / folder_name
    session_folder.mkdir(parents=True, exist_ok=True)

    return session_folder


def record_npg_lite(
    port="COM3",
    baudrate=230400,
    duration_seconds=10,
    sample_rate_hz=500,
    channels=1,
    mode="ECG",
    device_id="NPG_UNKNOWN",
    operator="Deepak",
    electrode_placement="Lead II",
):
    session_folder = create_session_folder(mode=mode, device_id=device_id)

    raw_csv_path = session_folder / "raw.csv"
    metadata_path = session_folder / "metadata.json"

    bandwidth_info = recommend_setup(
        num_channels=channels,
        sample_rate_hz=sample_rate_hz,
        baud_rate=baudrate,
        transport="USB_SERIAL"
    )

    device = NPGLite(port=port, baudrate=baudrate)

    rows = []

    metadata = {
        "software": "OpenPhysiologyLab",
        "recording_mode": mode,
        "device_id": device_id,
        "operator": operator,
        "electrode_placement": electrode_placement,
        "transport": "USB_SERIAL",
        "port": port,
        "baudrate": baudrate,
        "sample_rate_target_hz": sample_rate_hz,
        "channels_requested": channels,
        "firmware_identity": None,
        "device_status_before_recording": None,
        "start_datetime": None,
        "end_datetime": None,
        "duration_requested_seconds": duration_seconds,
        "duration_measured_pc_seconds": None,
        "samples_recorded": None,
        "first_sample_number": None,
        "last_sample_number": None,
        "missing_sample_count_estimate": None,
        "measured_sample_rate_from_device_time_hz": None,
        "measured_sample_rate_from_pc_time_hz": None,
        "bandwidth_estimate": bandwidth_info,
        "raw_file": "raw.csv",
        "notes": "Raw ADC values. Blank inactive channels saved as empty cells."
    }

    try:
        print("Connecting to NPG Lite...")
        device.connect()

        print("Identifying device...")
        identity = device.identify()
        print(identity)
        metadata["firmware_identity"] = identity

        print("Checking status...")
        status = device.status()
        print(status)
        metadata["device_status_before_recording"] = status

        print(f"Setting sample rate: {sample_rate_hz} Hz")
        print(device.set_rate(sample_rate_hz))

        print(f"Setting channels: {channels}")
        print(device.set_channels(channels))

        print("Starting stream...")
        print(device.start_streaming())

        metadata["start_datetime"] = datetime.now().isoformat(timespec="seconds")

        pc_start = time.time()
        pc_end_target = pc_start + duration_seconds

        print(f"Recording for {duration_seconds} seconds...")

        while time.time() < pc_end_target:
            line = device.read_sample_line()
            parsed = device.parse_sample_line(line)

            if parsed is None:
                continue

            pc_time_s = time.time() - pc_start

            rows.append({
                "sample": parsed["sample"],
                "time_us": parsed["time_us"],
                "pc_time_s": pc_time_s,
                "ch1": parsed["ch1"],
                "ch2": parsed["ch2"],
                "ch3": parsed["ch3"],
                "ch4": parsed["ch4"],
                "ch5": parsed["ch5"],
                "ch6": parsed["ch6"],
            })

        print("Stopping stream...")
        stop_response = device.stop_streaming()
        print(stop_response)

        metadata["end_datetime"] = datetime.now().isoformat(timespec="seconds")

    finally:
        device.disconnect()
        print("Disconnected.")

    # -----------------------------
    # Save raw CSV
    # -----------------------------

    fieldnames = [
        "sample",
        "time_us",
        "pc_time_s",
        "ch1",
        "ch2",
        "ch3",
        "ch4",
        "ch5",
        "ch6",
    ]

    with open(raw_csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for row in rows:
            writer.writerow(row)

    # -----------------------------
    # Calculate integrity metadata
    # -----------------------------

    metadata["samples_recorded"] = len(rows)

    if len(rows) > 0:
        first_sample = rows[0]["sample"]
        last_sample = rows[-1]["sample"]

        metadata["first_sample_number"] = first_sample
        metadata["last_sample_number"] = last_sample

        expected_count_from_sample_numbers = last_sample - first_sample + 1
        missing_estimate = expected_count_from_sample_numbers - len(rows)

        metadata["missing_sample_count_estimate"] = missing_estimate

        pc_duration = rows[-1]["pc_time_s"] - rows[0]["pc_time_s"]
        metadata["duration_measured_pc_seconds"] = pc_duration

        if pc_duration > 0:
            metadata["measured_sample_rate_from_pc_time_hz"] = len(rows) / pc_duration

        device_time_duration_s = (rows[-1]["time_us"] - rows[0]["time_us"]) / 1_000_000

        if device_time_duration_s > 0:
            metadata["measured_sample_rate_from_device_time_hz"] = (
                (len(rows) - 1) / device_time_duration_s
            )

    # -----------------------------
    # Save metadata JSON
    # -----------------------------

    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=4)

    print("\nRecording complete.")
    print(f"Session folder: {session_folder}")
    print(f"Raw CSV saved: {raw_csv_path}")
    print(f"Metadata saved: {metadata_path}")

    print("\nIntegrity summary:")
    print(f"Samples recorded: {metadata['samples_recorded']}")
    print(f"Missing sample estimate: {metadata['missing_sample_count_estimate']}")
    print(f"Measured sample rate from device time: {metadata['measured_sample_rate_from_device_time_hz']}")
    print(f"Measured sample rate from PC time: {metadata['measured_sample_rate_from_pc_time_hz']}")

    return session_folder


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Record raw data from NPG Lite using OpenPhysio firmware."
    )

    parser.add_argument("--port", default="COM3")
    parser.add_argument("--baud", type=int, default=230400)
    parser.add_argument("--duration", type=int, default=10)
    parser.add_argument("--rate", type=int, default=500)
    parser.add_argument("--channels", type=int, default=1)
    parser.add_argument("--mode", default="ECG")
    parser.add_argument("--device-id", default="NPG_TEST")
    parser.add_argument("--operator", default="Deepak")
    parser.add_argument("--placement", default="Lead II")

    args = parser.parse_args()

    record_npg_lite(
        port=args.port,
        baudrate=args.baud,
        duration_seconds=args.duration,
        sample_rate_hz=args.rate,
        channels=args.channels,
        mode=args.mode,
        device_id=args.device_id,
        operator=args.operator,
        electrode_placement=args.placement
    )