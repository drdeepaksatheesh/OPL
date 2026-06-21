# app/recorder_panel.py

import csv
import json
import time
import shutil
import hashlib
from datetime import datetime
from pathlib import Path

import numpy as np

from PyQt5.QtWidgets import (
    QDialog, QDialogButtonBox,
    QApplication,
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QLineEdit, QTextEdit, QMessageBox,
    QFileDialog, QInputDialog,
    QCheckBox, QDoubleSpinBox, QSizePolicy, QFrame, QSlider, QGroupBox
)

from PyQt5.QtGui import QKeyEvent
from PyQt5.QtCore import QThread, pyqtSignal, QTimer, Qt

import pyqtgraph as pg
from app.theme import get_plot_palette

from acquisition.npg_lite import NPGLite
from acquisition.bandwidth import recommend_setup
from acquisition.transports.serial_transport import SerialTransport

from analysis.signal_filters import apply_bandpass_notch
from analysis.peak_detection import detect_general_peaks, detect_ecg_r_peaks
from analysis.selection_metrics import calculate_selection_metrics, format_selection_metrics_text
from app.machine_registry import (
    get_or_create_machine_profile_snapshot,
    get_latest_machine_evaluation_snapshot,
    build_session_machine_evaluation,
    save_machine_evaluation_report
)

try:
    from app.signals.ecg.ecg_protocols import build_ecg_electrode_pin_mapping
except Exception:
    build_ecg_electrode_pin_mapping = None


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RECORDINGS_DIR = PROJECT_ROOT / "recordings"

FIRMWARE_SOURCE_RELATIVE_PATH = Path(
    "OpenPhysio_NPG_Lite_FW_v0_1"
) / "OpenPhysio_NPG_Lite_FW_v0_1.ino"

FIRMWARE_SOURCE_FILE = "OpenPhysio_NPG_Lite_FW_v0_1.ino"
FIRMWARE_VERSION_EXPECTED_FROM_SOURCE = "0.1"

DEFAULT_PREVIEW_SECONDS = 60
TIMEBASE_OPTIONS = [2, 5, 10, 20, 30, 60]

DEFAULT_ADC_MIN = 0
DEFAULT_ADC_MAX = 4095


def build_electrode_pin_mapping(signal_type=None, protocol_name=None, electrode_placement=None):
    """
    Build explicit electrode-to-pin documentation.

    This is documentation metadata only.
    It does not modify raw ADC data.
    It does not modify display polarity.
    It does not modify machine evaluation.

    For ECG, the current local NPG Lite evidence supports:
    A0P -> RA/right wrist
    A0N -> LL/left leg
    REF -> RL/right leg

    This is described as Lead-II limb placement with NPG Lite practical polarity,
    not as textbook Lead II amplifier polarity.
    """

    signal = str(signal_type or "").upper()
    protocol = str(protocol_name or "")
    placement = str(electrode_placement or "")

    # Preferred path: use the modular ECG protocol/lead configuration registry.
    # This keeps lead naming future-proof: RA-LL practical, textbook Lead I/II/III,
    # chest-position-like configurations, etc.
    if signal == "ECG" or protocol.startswith("ECG"):
        if build_ecg_electrode_pin_mapping is not None:
            try:
                return build_ecg_electrode_pin_mapping(
                    protocol_name=protocol,
                    user_entered_placement=placement
                )
            except Exception:
                pass

        # Fallback for safety: old hard-coded ECG mapping.
        return {
            "schema_version": "0.1",
            "signal_type": "ECG",
            "configuration_label": "Lead-II limb placement, NPG Lite practical upright/non-clipping polarity configuration",
            "device_family": "NPG Lite / compatible",
            "pin_mapping": {
                "A0P": "Right wrist / RA",
                "A0N": "Left leg / LL",
                "REF": "Right leg / RL"
            },
            "body_mapping": {
                "Right wrist / RA": "A0P / CH input P",
                "Left leg / LL": "A0N / CH input N",
                "Right leg / RL": "REF / GND"
            },
            "textbook_lead_ii_note": (
                "Textbook Lead II polarity is LL positive and RA negative, with RL as ground/reference. "
                "In the current NPG Lite + OpenPhysiologyLab firmware/app chain, the tested practical mapping "
                "A0P->RA and A0N->LL produced upright ECG with better ADC headroom."
            ),
            "local_polarity_evidence": {
                "test_1": {
                    "mapping": "A0P->RA/right wrist, A0N->LL/left leg, REF->RL/right leg",
                    "display_polarity_without_app_inversion": "upright / positive R peaks",
                    "machine_status": "PASS",
                    "adc_result": "No low/high clipping in local test"
                },
                "test_2": {
                    "mapping": "A0P->LL/left leg, A0N->RA/right wrist, REF->RL/right leg",
                    "display_polarity_without_app_inversion": "inverted / negative R peaks",
                    "machine_status": "CAUTION",
                    "adc_result": "Low-rail clipping observed in local test"
                }
            },
            "raw_signal_policy": (
                "raw.csv stores original ADC values. Display inversion and review filtering are display/analysis operations "
                "and must not overwrite raw.csv."
            ),
            "user_entered_placement": placement
        }

    return {
        "schema_version": "0.1",
        "signal_type": signal if signal else "UNKNOWN",
        "configuration_label": "Generic electrode mapping not specified",
        "pin_mapping": {},
        "body_mapping": {},
        "textbook_note": None,
        "local_polarity_evidence": None,
        "raw_signal_policy": (
            "raw.csv stores original ADC values. Display inversion and review filtering should not overwrite raw.csv."
        ),
        "user_entered_placement": placement
    }




def calculate_file_sha256(file_path):
    """
    Calculate SHA256 hash of the firmware source file.

    This documents exactly which firmware source file was present
    when the recording was made.
    """

    path = Path(file_path)

    if not path.exists():
        return {
            "exists": False,
            "sha256": None,
            "error": f"File not found: {path}"
        }

    try:
        sha256 = hashlib.sha256()

        with open(path, "rb") as f:
            for block in iter(lambda: f.read(1024 * 1024), b""):
                sha256.update(block)

        return {
            "exists": True,
            "sha256": sha256.hexdigest(),
            "error": None
        }

    except Exception as e:
        return {
            "exists": False,
            "sha256": None,
            "error": str(e)
        }



class DurationInput(QLineEdit):
    """
    OTP-style duration input.

    Format:
    MM:SS:CC

    CC = centiseconds.

    Examples:
    05:00:00 = 5 minutes
    00:10:50 = 10.50 seconds
    --:--:-- = manual stop mode
    """

    def __init__(self):
        super().__init__()
        self.digits = []
        self.setText("--:--:--")
        self.setMaxLength(8)
        self.setPlaceholderText("--:--:--")
        self.setToolTip(
            "Enter duration as MM:SS:CC.\n"
            "Example: 05:00:00 = 5 minutes.\n"
            "Example: 00:10:50 = 10.50 seconds.\n"
            "Reset/blank means record until Stop Recording is pressed."
        )

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        text = event.text()

        if key in [Qt.Key_Backspace, Qt.Key_Delete]:
            if len(self.digits) > 0:
                self.digits.pop()
            self.update_display()
            return

        if key == Qt.Key_Escape:
            self.reset()
            return

        if text.isdigit():
            if len(self.digits) < 6:
                self.digits.append(text)
            self.update_display()
            return

        return

    def update_display(self):
        display_digits = self.digits + ["-"] * (6 - len(self.digits))
        text = (
            f"{display_digits[0]}{display_digits[1]}:"
            f"{display_digits[2]}{display_digits[3]}:"
            f"{display_digits[4]}{display_digits[5]}"
        )
        self.setText(text)

    def reset(self):
        self.digits = []
        self.setText("--:--:--")

    def is_blank(self):
        return len(self.digits) == 0

    def get_duration_seconds(self):
        if self.is_blank():
            return None, "--:--:--"

        if len(self.digits) < 6:
            raise ValueError("Complete duration as MM:SS:CC or press Reset Duration.")

        minutes = int(self.digits[0] + self.digits[1])
        seconds = int(self.digits[2] + self.digits[3])
        centiseconds = int(self.digits[4] + self.digits[5])

        if seconds > 59:
            raise ValueError("Seconds must be 00 to 59.")

        total_seconds = (minutes * 60) + seconds + (centiseconds / 100)

        if total_seconds <= 0:
            raise ValueError("Duration must be greater than zero, or reset for manual stop.")

        return total_seconds, self.text()


class TimeAxisItem(pg.AxisItem):
    """
    Bottom axis that displays seconds as MM:SS.
    Duplicate labels are suppressed.
    """

    def tickStrings(self, values, scale, spacing):
        labels = []
        previous_label = None

        for value in values:
            try:
                total_seconds = int(round(value))
                minutes = total_seconds // 60
                seconds = total_seconds % 60
                label = f"{minutes:02d}:{seconds:02d}"

                if label == previous_label:
                    labels.append("")
                else:
                    labels.append(label)
                    previous_label = label

            except Exception:
                labels.append("")

        return labels


class SelectionViewBox(pg.ViewBox):
    """
    ViewBox that allows stable absolute-time click-drag selection during review mode.

    Important:
    - The anchor time is stored at drag start.
    - It is not recalculated when the view scrolls.
    - Single click clears the active selection.
    """

    def __init__(self, plot_key, selection_callback, clear_callback=None):
        super().__init__(enableMenu=False)
        self.plot_key = plot_key
        self.selection_callback = selection_callback
        self.clear_callback = clear_callback
        self.drag_anchor_x = None

    def mouseDragEvent(self, event, axis=None):
        if event.button() == Qt.LeftButton and self.selection_callback is not None:
            event.accept()

            if event.isStart():
                start_point = self.mapSceneToView(event.buttonDownScenePos())
                self.drag_anchor_x = float(start_point.x())

            if self.drag_anchor_x is None:
                start_point = self.mapSceneToView(event.buttonDownScenePos())
                self.drag_anchor_x = float(start_point.x())

            current_point = self.mapSceneToView(event.scenePos())
            current_x = float(current_point.x())

            self.selection_callback(
                plot_key=self.plot_key,
                anchor_x=self.drag_anchor_x,
                current_x=current_x,
                finished=event.isFinish()
            )

            if event.isFinish():
                self.drag_anchor_x = None

            return

        super().mouseDragEvent(event, axis=axis)

    def mouseClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            event.accept()
            self.drag_anchor_x = None

            if self.clear_callback is not None:
                self.clear_callback()

            return

        super().mouseClickEvent(event)


class ScrubbablePreviewWidget(pg.GraphicsLayoutWidget):
    """
    GraphicsLayoutWidget that supports two-finger horizontal scroll
    during review mode.
    """

    def __init__(self):
        super().__init__()
        self.scrub_callback = None

    def set_scrub_callback(self, callback):
        self.scrub_callback = callback

    def wheelEvent(self, event):
        pixel_delta = event.pixelDelta()
        angle_delta = event.angleDelta()

        dx = pixel_delta.x() if pixel_delta.x() != 0 else angle_delta.x()
        dy = pixel_delta.y() if pixel_delta.y() != 0 else angle_delta.y()

        if abs(dx) > abs(dy) and dx != 0:
            if self.scrub_callback is not None:
                self.scrub_callback(dx)
                event.accept()
                return

        super().wheelEvent(event)


class RecorderWorker(QThread):
    finished_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    log_signal = pyqtSignal(str)
    sample_batch_signal = pyqtSignal(object)
    integrity_signal = pyqtSignal(object)

    def __init__(
        self,
        port,
        baudrate,
        duration_seconds,
        duration_text,
        sample_rate_hz,
        channels,
        mode,
        device_id,
        operator,
        electrode_placement,
        protocol_name,
        review_filter_settings,
        project_name=None,
        subject_id=None,
        session_label=None,
        condition=None,
        posture=None,
        session_notes=None
    ):
        super().__init__()

        self.port = port
        self.baudrate = baudrate
        self.duration_seconds = duration_seconds
        self.duration_text = duration_text
        self.sample_rate_hz = sample_rate_hz
        self.channels = channels
        self.mode = mode
        self.device_id = device_id
        self.operator = operator
        self.electrode_placement = electrode_placement
        self.protocol_name = protocol_name
        self.review_filter_settings = review_filter_settings

        self.project_name = project_name or ""
        self.subject_id = subject_id or ""
        self.session_label = session_label or ""
        self.condition = condition or ""
        self.posture = posture or ""
        self.session_notes = session_notes or ""

        self.stop_requested = False
        self.pause_requested = False
        self.current_segment_id = 1
        self.stop_reason = "NOT_STOPPED"

    def request_stop(self):
        self.stop_requested = True
        self.stop_reason = "MANUAL_STOP"

    def request_pause(self):
        if not self.pause_requested:
            self.pause_requested = True
            self.log_signal.emit("Paused. Incoming samples are being ignored until Resume.")

    def request_resume(self):
        if self.pause_requested:
            self.pause_requested = False
            self.current_segment_id += 1
            self.log_signal.emit(f"Resumed. New segment started: segment {self.current_segment_id}")

    def create_session_folder(self):
        now = datetime.now()

        date_folder_name = now.strftime("%Y-%m-%d")
        timestamp = now.strftime("%Y-%m-%d_%H%M%S")

        folder_name = f"{timestamp}_{self.mode}_{self.device_id}"

        day_folder = RECORDINGS_DIR / date_folder_name
        session_folder = day_folder / folder_name

        session_folder.mkdir(parents=True, exist_ok=True)

        return session_folder

    def run(self):
        session_folder = self.create_session_folder()

        raw_csv_path = session_folder / "raw.csv"
        metadata_path = session_folder / "metadata.json"

        duration_for_bandwidth = self.duration_seconds if self.duration_seconds is not None else 300

        bandwidth_info = recommend_setup(
            num_channels=self.channels,
            sample_rate_hz=self.sample_rate_hz,
            baud_rate=self.baudrate,
            transport="USB_SERIAL",
            duration_seconds=int(duration_for_bandwidth)
        )

        duration_mode = "FIXED_DURATION" if self.duration_seconds is not None else "MANUAL_STOP"

        target_sample_count = None

        if self.duration_seconds is not None:
            target_sample_count = int(round(float(self.duration_seconds) * float(self.sample_rate_hz)))

            if target_sample_count < 1:
                target_sample_count = 1

        duration_stop_rule = "SAMPLE_COUNT_LOCKED" if target_sample_count is not None else "MANUAL_STOP"

        firmware_source_path = PROJECT_ROOT / FIRMWARE_SOURCE_RELATIVE_PATH
        firmware_hash_info = calculate_file_sha256(firmware_source_path)

        metadata = {
            "software": "OpenPhysiologyLab",
            "recording_mode": self.mode,
            "signal_type": self.mode,
            "protocol_name": self.protocol_name,
            "device_id": self.device_id,
            "operator": self.operator,
            "study_context": {
                "project_name": self.project_name,
                "subject_id": self.subject_id,
                "session_label": self.session_label,
                "condition": self.condition,
                "posture": self.posture,
                "session_notes": self.session_notes
            },
            "electrode_placement": self.electrode_placement,
            "electrode_pin_mapping": build_electrode_pin_mapping(
                signal_type=self.mode,
                protocol_name=self.protocol_name,
                electrode_placement=self.electrode_placement
            ),
            "transport": "USB_SERIAL",
            "port": self.port,
            "baudrate": self.baudrate,
            "sample_rate_target_hz": self.sample_rate_hz,
            "channels_requested": self.channels,
            "firmware_identity": None,
            "firmware_source_file": FIRMWARE_SOURCE_FILE,
            "firmware_source_relative_path": str(FIRMWARE_SOURCE_RELATIVE_PATH).replace("\\", "/"),
            "firmware_version_expected_from_source": FIRMWARE_VERSION_EXPECTED_FROM_SOURCE,
            "firmware_hash_method": "SHA256",
            "firmware_hash_sha256": firmware_hash_info["sha256"],
            "firmware_source_file_found": firmware_hash_info["exists"],
            "firmware_hash_error": firmware_hash_info["error"],
            "device_status_before_recording": None,
            "start_datetime": None,
            "end_datetime": None,
            "duration_mode": duration_mode,
            "duration_stop_rule": duration_stop_rule,
            "sample_count_locked": target_sample_count is not None,
            "target_sample_count": target_sample_count,
            "duration_requested_text": self.duration_text,
            "duration_requested_seconds": self.duration_seconds,
            "duration_measured_pc_seconds": None,
            "active_recording_duration_pc_seconds": None,
            "active_recording_duration_device_seconds": None,
            "stop_reason": None,
            "pause_resume_used": False,
            "segments_recorded": None,
            "samples_recorded": None,
            "first_sample_number": None,
            "last_sample_number": None,
            "missing_sample_count_estimate": None,
            "missing_sample_count_estimate_segment_aware": None,
            "measured_sample_rate_from_device_time_hz": None,
            "measured_sample_rate_from_pc_time_hz": None,
            "integrity_status": "NOT_CHECKED",
            "bandwidth_estimate": bandwidth_info,
            "review_filter_settings": self.review_filter_settings,
            "saved_files": {
                "raw_file": "raw.csv",
                "processed_file": None
            },
            "machine_profile": None,
            "latest_machine_evaluation_before_recording": None,
            "session_machine_evaluation": None,
            "session_machine_evaluation_report_path": None,
            "notes": (
                "Raw ADC values are saved in raw.csv. "
                "raw.csv includes segment_id. "
                "Pause/resume creates new segments. "
                "Missing sample count is calculated within segments, so paused gaps are not counted as data loss. "
                "Review filtering is display-only. Analysis software should use raw.csv only. "
                "Electrode pin mapping is stored separately in electrode_pin_mapping and is documentation metadata only."
            )
        }

        rows = []
        batch = []

        device = NPGLite(port=self.port, baudrate=self.baudrate)

        try:
            self.log_signal.emit("Connecting to NPG Lite...")
            device.connect()

            self.log_signal.emit("Identifying device...")
            identity = device.identify()
            metadata["firmware_identity"] = identity
            self.log_signal.emit(str(identity))

            self.log_signal.emit("Checking status...")
            status = device.status()
            metadata["device_status_before_recording"] = status
            self.log_signal.emit(str(status))

            try:
                machine_profile_snapshot = get_or_create_machine_profile_snapshot(
                    identity=identity,
                    status=status,
                    device_id=self.device_id,
                    port=self.port,
                    baudrate=self.baudrate,
                    sample_rate_hz=self.sample_rate_hz,
                    channels=self.channels
                )
                metadata["machine_profile"] = machine_profile_snapshot
                metadata["latest_machine_evaluation_before_recording"] = (
                    get_latest_machine_evaluation_snapshot(
                        machine_profile_snapshot.get("machine_uid")
                    )
                )
                self.log_signal.emit("Machine profile updated.")
                self.log_signal.emit(str(machine_profile_snapshot.get("machine_uid")))
            except Exception as e:
                metadata["machine_profile_error"] = str(e)
                self.log_signal.emit(f"Machine profile update failed: {e}")


            self.log_signal.emit(f"Setting sample rate: {self.sample_rate_hz} Hz")
            self.log_signal.emit(str(device.set_rate(self.sample_rate_hz)))

            self.log_signal.emit(f"Setting channels: {self.channels}")
            self.log_signal.emit(str(device.set_channels(self.channels)))

            self.log_signal.emit("Starting stream...")
            self.log_signal.emit(str(device.start_streaming()))

            metadata["start_datetime"] = datetime.now().isoformat(timespec="seconds")

            pc_start = time.time()

            if target_sample_count is None:
                pc_end_target = None
                self.log_signal.emit("Recording until Stop Recording is pressed...")
            else:
                pc_end_target = None
                self.log_signal.emit(
                    f"Recording sample-count locked duration: "
                    f"{self.duration_seconds:.3f} seconds at {self.sample_rate_hz} Hz "
                    f"= {target_sample_count} samples."
                )

            last_emit_time = time.time()

            while True:
                if self.stop_requested:
                    break

                if pc_end_target is not None and time.time() >= pc_end_target:
                    self.stop_reason = "DURATION_COMPLETE"
                    break

                line = device.read_sample_line()
                parsed = device.parse_sample_line(line)

                if parsed is None:
                    continue

                if self.pause_requested:
                    continue

                pc_time_s = time.time() - pc_start

                row = {
                    "segment_id": self.current_segment_id,
                    "sample": parsed["sample"],
                    "time_us": parsed["time_us"],
                    "pc_time_s": pc_time_s,
                    "ch1": parsed["ch1"],
                    "ch2": parsed["ch2"],
                    "ch3": parsed["ch3"],
                    "ch4": parsed["ch4"],
                    "ch5": parsed["ch5"],
                    "ch6": parsed["ch6"],
                }

                rows.append(row)
                batch.append(row)

                if target_sample_count is not None and len(rows) >= target_sample_count:
                    self.stop_reason = "DURATION_COMPLETE_SAMPLE_COUNT_LOCKED"
                    break

                now = time.time()

                if now - last_emit_time >= 0.05:
                    self.sample_batch_signal.emit(batch)
                    batch = []
                    last_emit_time = now

            if batch:
                self.sample_batch_signal.emit(batch)

            self.log_signal.emit("Stopping stream...")
            stop_response = device.stop_streaming()
            self.log_signal.emit(str(stop_response))

            metadata["end_datetime"] = datetime.now().isoformat(timespec="seconds")
            metadata["stop_reason"] = self.stop_reason

        except Exception as e:
            self.error_signal.emit(str(e))
            return

        finally:
            try:
                device.disconnect()
                self.log_signal.emit("Disconnected.")
            except Exception:
                pass

        fieldnames = [
            "segment_id",
            "sample",
            "time_us",
            "pc_time_s",
            "ch1",
            "ch2",
            "ch3",
            "ch4",
            "ch5",
            "ch6"
        ]

        with open(raw_csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for row in rows:
                writer.writerow(row)

        self.calculate_integrity(metadata, rows)

        try:
            machine_uid = None

            if isinstance(metadata.get("machine_profile"), dict):
                machine_uid = metadata["machine_profile"].get("machine_uid")

            session_eval = build_session_machine_evaluation(
                rows=rows,
                sample_rate_hz=metadata.get("sample_rate_target_hz", self.sample_rate_hz),
                channels=metadata.get("channels_requested", self.channels),
                machine_uid=machine_uid,
                signal_type=metadata.get("signal_type", metadata.get("recording_mode", self.mode)),
                protocol_name=metadata.get("protocol_name", metadata.get("recording_mode", self.mode)),
                source="recorder_session"
            )

            metadata["session_machine_evaluation"] = session_eval

            if machine_uid:
                eval_report_path = save_machine_evaluation_report(machine_uid, session_eval)

                if eval_report_path is not None:
                    metadata["session_machine_evaluation_report_path"] = str(eval_report_path)

            self.log_signal.emit("Session machine evaluation completed.")
            self.log_signal.emit(f"Machine evaluation status: {session_eval.get('overall_status')}")

        except Exception as e:
            metadata["session_machine_evaluation_error"] = str(e)
            self.log_signal.emit(f"Session machine evaluation failed: {e}")

        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=4)

        self.log_signal.emit("Recording complete.")
        self.log_signal.emit(f"Temporary session folder: {session_folder}")
        self.log_signal.emit(f"Raw CSV saved: {raw_csv_path}")
        self.log_signal.emit(f"Metadata saved: {metadata_path}")

        self.log_signal.emit("Integrity summary:")
        self.log_signal.emit(f"Status: {metadata['integrity_status']}")
        self.log_signal.emit(f"Stop reason: {metadata['stop_reason']}")
        self.log_signal.emit(f"Segments recorded: {metadata['segments_recorded']}")
        self.log_signal.emit(f"Samples recorded: {metadata['samples_recorded']}")
        self.log_signal.emit(f"Missing sample estimate: {metadata['missing_sample_count_estimate_segment_aware']}")
        self.log_signal.emit(
            f"Measured sample rate from device time: "
            f"{metadata['measured_sample_rate_from_device_time_hz']}"
        )

        self.integrity_signal.emit(metadata)
        self.finished_signal.emit(str(session_folder))

    def calculate_duration_accuracy(self, metadata, rows):
        """
        Add detailed duration/sample-count accuracy information to metadata.

        Important distinction:
        - device_sample_span_seconds = time between first and last recorded samples.
        - sample_count_duration_seconds = number of samples / target sample rate.

        For N samples at 500 Hz:
        - sample span is approximately (N - 1) / 500
        - sample-count duration is N / 500

        Both are useful and both are stored.
        """

        requested_duration = metadata.get("duration_requested_seconds")
        target_fs = metadata.get("sample_rate_target_hz")
        samples_recorded = metadata.get("samples_recorded")
        pc_span = metadata.get("active_recording_duration_pc_seconds")
        device_span = metadata.get("active_recording_duration_device_seconds")
        measured_fs_device = metadata.get("measured_sample_rate_from_device_time_hz")
        measured_fs_pc = metadata.get("measured_sample_rate_from_pc_time_hz")

        duration_accuracy = {
            "duration_mode": metadata.get("duration_mode"),
            "duration_stop_rule": metadata.get("duration_stop_rule"),
            "sample_count_locked": metadata.get("sample_count_locked"),
            "target_sample_count": metadata.get("target_sample_count"),
            "requested_duration_seconds": requested_duration,
            "target_sample_rate_hz": target_fs,

            "actual_samples_recorded": samples_recorded,

            "actual_pc_sample_span_seconds": pc_span,
            "actual_device_sample_span_seconds": device_span,

            "sample_count_duration_seconds": None,

            "expected_sample_count_from_requested_duration": None,
            "sample_count_error_vs_requested": None,

            "expected_sample_span_seconds_from_requested_duration": None,

            "pc_span_error_ms_vs_requested": None,
            "device_span_error_ms_vs_requested": None,
            "sample_count_duration_error_ms_vs_requested": None,

            "pc_minus_device_span_difference_ms": None,

            "measured_sample_rate_from_device_time_hz": measured_fs_device,
            "measured_sample_rate_from_pc_time_hz": measured_fs_pc,
            "device_sample_rate_error_hz_vs_target": None,
            "pc_sample_rate_error_hz_vs_target": None,

            "interpretation": None,
            "machine_profile": None,
            "latest_machine_evaluation_before_recording": None,
            "session_machine_evaluation": None,
            "session_machine_evaluation_report_path": None,
            "notes": (
                "device_sample_span_seconds is based on time_us difference between first and last samples. "
                "sample_count_duration_seconds is samples_recorded / target_sample_rate_hz. "
                "For a recording with N samples, the time span between first and last sample is approximately "
                "(N-1)/fs, while N/fs represents the duration occupied by N samples."
            )
        }

        try:
            if target_fs is not None and float(target_fs) > 0 and samples_recorded is not None:
                target_fs_float = float(target_fs)
                samples_float = float(samples_recorded)

                duration_accuracy["sample_count_duration_seconds"] = samples_float / target_fs_float

                if requested_duration is not None:
                    requested_float = float(requested_duration)

                    expected_sample_count = int(round(requested_float * target_fs_float))
                    duration_accuracy["expected_sample_count_from_requested_duration"] = expected_sample_count

                    duration_accuracy["sample_count_error_vs_requested"] = int(
                        int(samples_recorded) - expected_sample_count
                    )

                    if expected_sample_count > 1:
                        duration_accuracy["expected_sample_span_seconds_from_requested_duration"] = (
                            (expected_sample_count - 1) / target_fs_float
                        )

                    duration_accuracy["sample_count_duration_error_ms_vs_requested"] = (
                        (duration_accuracy["sample_count_duration_seconds"] - requested_float) * 1000.0
                    )

                if measured_fs_device is not None:
                    duration_accuracy["device_sample_rate_error_hz_vs_target"] = (
                        float(measured_fs_device) - target_fs_float
                    )

                if measured_fs_pc is not None:
                    duration_accuracy["pc_sample_rate_error_hz_vs_target"] = (
                        float(measured_fs_pc) - target_fs_float
                    )

        except Exception as e:
            duration_accuracy["calculation_warning"] = str(e)

        try:
            if requested_duration is not None and pc_span is not None:
                duration_accuracy["pc_span_error_ms_vs_requested"] = (
                    (float(pc_span) - float(requested_duration)) * 1000.0
                )
        except Exception:
            pass

        try:
            if requested_duration is not None and device_span is not None:
                duration_accuracy["device_span_error_ms_vs_requested"] = (
                    (float(device_span) - float(requested_duration)) * 1000.0
                )
        except Exception:
            pass

        try:
            if pc_span is not None and device_span is not None:
                duration_accuracy["pc_minus_device_span_difference_ms"] = (
                    (float(pc_span) - float(device_span)) * 1000.0
                )
        except Exception:
            pass

        if requested_duration is None:
            duration_accuracy["interpretation"] = (
                "Manual-stop recording. No requested duration was set, so duration error versus requested time is not applicable."
            )
        else:
            if metadata.get("sample_count_locked"):
                duration_accuracy["interpretation"] = (
                    "Fixed-duration sample-count locked recording. The recorder stops after the target number "
                    "of samples is stored. For analysis, sample_count_duration_seconds = samples_recorded / target_sample_rate_hz "
                    "is the primary duration. The first-to-last sample span is expected to be approximately (N-1)/fs."
                )
            else:
                duration_accuracy["interpretation"] = (
                    "Fixed-duration recording. Compare requested duration with PC sample span, device sample span, "
                    "sample-count duration, and expected sample count."
                )

        metadata["duration_accuracy"] = duration_accuracy

    def calculate_integrity(self, metadata, rows):
        metadata["samples_recorded"] = len(rows)

        if len(rows) == 0:
            metadata["integrity_status"] = "FAIL"
            metadata["segments_recorded"] = 0
            return

        metadata["first_sample_number"] = rows[0]["sample"]
        metadata["last_sample_number"] = rows[-1]["sample"]

        segment_ids = sorted(set(row["segment_id"] for row in rows))
        metadata["segments_recorded"] = len(segment_ids)
        metadata["pause_resume_used"] = len(segment_ids) > 1

        missing_total = 0
        active_pc_duration = 0
        active_device_duration = 0
        segment_details = []

        for segment_id in segment_ids:
            segment_rows = [row for row in rows if row["segment_id"] == segment_id]

            if len(segment_rows) == 0:
                continue

            first_sample = segment_rows[0]["sample"]
            last_sample = segment_rows[-1]["sample"]

            expected_count = last_sample - first_sample + 1
            missing = expected_count - len(segment_rows)
            missing_total += missing

            pc_duration = segment_rows[-1]["pc_time_s"] - segment_rows[0]["pc_time_s"]
            device_duration = (segment_rows[-1]["time_us"] - segment_rows[0]["time_us"]) / 1_000_000

            if pc_duration > 0:
                active_pc_duration += pc_duration

            if device_duration > 0:
                active_device_duration += device_duration

            segment_details.append({
                "segment_id": segment_id,
                "samples": len(segment_rows),
                "first_sample": first_sample,
                "last_sample": last_sample,
                "missing_estimate": missing,
                "pc_duration_seconds": pc_duration,
                "device_duration_seconds": device_duration
            })

        metadata["missing_sample_count_estimate"] = missing_total
        metadata["missing_sample_count_estimate_segment_aware"] = missing_total
        metadata["segment_details"] = segment_details

        total_pc_duration = rows[-1]["pc_time_s"] - rows[0]["pc_time_s"]
        metadata["duration_measured_pc_seconds"] = total_pc_duration

        metadata["active_recording_duration_pc_seconds"] = active_pc_duration
        metadata["active_recording_duration_device_seconds"] = active_device_duration

        if active_pc_duration > 0:
            metadata["measured_sample_rate_from_pc_time_hz"] = len(rows) / active_pc_duration

        if active_device_duration > 0:
            metadata["measured_sample_rate_from_device_time_hz"] = (
                (len(rows) - len(segment_ids)) / active_device_duration
            )

        self.calculate_duration_accuracy(metadata, rows)

        if missing_total == 0:
            metadata["integrity_status"] = "PASS"
        elif missing_total <= 10:
            metadata["integrity_status"] = "WARNING"
        else:
            metadata["integrity_status"] = "FAIL"


class RecorderPanel(QWidget):
    analyse_recording_requested = pyqtSignal(str)

    recording_finished = pyqtSignal(str)

    def __init__(self):
        super().__init__()

        self.worker = None

        self.preview_rows = []
        self.all_recorded_rows = []

        self.preview_seconds = DEFAULT_PREVIEW_SECONDS
        self.timebase_index = TIMEBASE_OPTIONS.index(DEFAULT_PREVIEW_SECONDS)

        self.review_mode = False
        self.review_session_folder = None
        self.review_x_min = 0
        self.saved_review_visible = False

        self.recording_start_wall_time = None
        self.recording_elapsed_final = 0

        self.is_recording = False
        self.is_paused = False
        self.is_light_theme = False

        self.preview_widget = None
        self.preview_plots = {}
        self.preview_curves = {}
        self.selection_regions = {}

        # Absolute-time active selection.
        # Example:
        # {"plot_key": "ch1_raw", "x1": 12.3, "x2": 118.7}
        self.active_selection = None

        self.y_ranges = {}

        self.edge_scroll_timer = QTimer(self)
        self.edge_scroll_timer.setInterval(40)
        self.edge_scroll_timer.timeout.connect(self.perform_edge_scroll_selection)

        self.edge_scroll_active = False
        self.edge_scroll_direction = 0
        self.edge_scroll_strength = 0.0
        self.edge_scroll_plot_key = None
        self.edge_scroll_anchor_x = None
        self.edge_scroll_current_x = None

        # Marker state.
        # Each marker:
        # {
        #   "marker_id": 1,
        #   "time_s": 12.345,
        #   "label": "deep breath",
        #   "mode": "recording/review/saved",
        #   "created_datetime": "..."
        # }
        self.markers = []
        self.marker_items = {}

        # Shared scrub bar state.
        # The scrub bar controls the visible time window during review/saved mode.
        self.updating_scrub_slider = False

        layout = QVBoxLayout()
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)
        self.setLayout(layout)

        def make_recorder_group(title_text):
            group = QGroupBox(title_text)
            group_layout = QHBoxLayout()
            group_layout.setContentsMargins(8, 12, 8, 8)
            group_layout.setSpacing(6)
            group.setLayout(group_layout)
            return group, group_layout

        title = QLabel("OpenPhysiologyLab Recorder Panel")
        title.setStyleSheet("font-size: 15px; font-weight: bold;")
        layout.addWidget(title)

        compact_row = QHBoxLayout()

        self.settings_toggle_btn = QPushButton("⚙ Settings")
        self.settings_toggle_btn.setToolTip("Show/hide acquisition settings")
        self.settings_toggle_btn.clicked.connect(self.toggle_settings_panel)
        compact_row.addWidget(self.settings_toggle_btn)

        self.settings_summary_label = QLabel("Settings: --")
        self.settings_summary_label.setStyleSheet("font-weight: bold;")
        compact_row.addWidget(self.settings_summary_label)

        compact_row.addStretch()
        layout.addLayout(compact_row)

        self.settings_panel = QFrame()
        self.settings_panel.setFrameShape(QFrame.StyledPanel)
        self.settings_panel.setVisible(False)

        settings_layout = QVBoxLayout()
        self.settings_panel.setLayout(settings_layout)

        row1 = QHBoxLayout()

        row1.addWidget(QLabel("Port"))
        self.port_box = QComboBox()
        self.port_box.currentTextChanged.connect(self.update_settings_summary)
        row1.addWidget(self.port_box)

        self.refresh_btn = QPushButton("↻")
        self.refresh_btn.setToolTip("Refresh serial ports")
        self.refresh_btn.clicked.connect(self.refresh_ports)
        row1.addWidget(self.refresh_btn)

        row1.addWidget(QLabel("Baud"))
        self.baud_box = QComboBox()
        self.baud_box.addItems(["230400", "460800", "921600"])
        self.baud_box.setCurrentText("230400")
        self.baud_box.currentTextChanged.connect(self.update_recommendation)
        self.baud_box.currentTextChanged.connect(self.update_settings_summary)
        row1.addWidget(self.baud_box)

        self.theme_checkbox = QCheckBox("Light")
        self.theme_checkbox.setToolTip("Toggle light/dark theme")
        self.theme_checkbox.stateChanged.connect(self.toggle_theme)
        self.theme_checkbox.setVisible(False)  # v0.1-alpha: dark-only UI

        settings_layout.addLayout(row1)

        row2 = QHBoxLayout()

        row2.addWidget(QLabel("Mode"))
        self.mode_box = QComboBox()
        self.mode_box.addItems(["ECG"])
        self.mode_box.currentTextChanged.connect(self.update_settings_summary)
        row2.addWidget(self.mode_box)

        row2.addWidget(QLabel("Protocol"))
        self.protocol_box = QComboBox()
        self.protocol_box.addItems([
    "ECG_HEADROOM_60S",
    "ECG_RESTING_5MIN"
])
        self.protocol_box.setMinimumWidth(190)
        self.protocol_box.setToolTip(
            "Protocol label saved into metadata and machine evaluation. "
            "It helps interpret ECG, EMG, EOG, and EEG recordings differently."
        )
        self.protocol_box.currentTextChanged.connect(self.update_settings_summary)
        row2.addWidget(self.protocol_box)

        row2.addWidget(QLabel("Ch"))
        self.channels_box = QComboBox()
        self.channels_box.addItems(["1"])
        self.channels_box.setCurrentText("1")
        self.channels_box.currentTextChanged.connect(self.update_recommendation)
        self.channels_box.currentTextChanged.connect(self.rebuild_preview_plots)
        self.channels_box.currentTextChanged.connect(self.update_settings_summary)
        row2.addWidget(self.channels_box)

        row2.addWidget(QLabel("Hz"))
        self.rate_box = QComboBox()
        self.rate_box.addItems(["250", "500", "1000"])
        self.rate_box.setCurrentText("500")
        self.rate_box.currentTextChanged.connect(self.update_recommendation)
        self.rate_box.currentTextChanged.connect(self.update_settings_summary)
        row2.addWidget(self.rate_box)

        row2.addWidget(QLabel("Dur"))
        self.duration_edit = DurationInput()
        self.duration_edit.textChanged.connect(self.update_recommendation)
        self.duration_edit.textChanged.connect(self.update_settings_summary)
        row2.addWidget(self.duration_edit)

        self.reset_duration_btn = QPushButton("⟲")
        self.reset_duration_btn.setToolTip("Reset duration to manual stop")
        self.reset_duration_btn.clicked.connect(self.reset_duration)
        row2.addWidget(self.reset_duration_btn)

        settings_layout.addLayout(row2)

        row3 = QHBoxLayout()

        row3.addWidget(QLabel("ID"))
        self.device_id_edit = QLineEdit("NPG_TEST")
        self.device_id_edit.textChanged.connect(self.update_settings_summary)
        row3.addWidget(self.device_id_edit)

        row3.addWidget(QLabel("Op"))
        self.operator_edit = QLineEdit("Deepak")
        row3.addWidget(self.operator_edit)

        row3.addWidget(QLabel("Placement"))
        self.placement_edit = QLineEdit("RA-LL limb ECG / Lead-II-like")
        self.placement_edit.setToolTip("Electrode placement, e.g. Lead II, Fp1-Fp2, biceps belly, etc.")
        self.placement_edit.textChanged.connect(self.update_settings_summary)
        row3.addWidget(self.placement_edit)

        settings_layout.addLayout(row3)

        # ------------------------------------------------------------
        # Study / subject / session metadata
        # ------------------------------------------------------------

        row4 = QHBoxLayout()

        row4.addWidget(QLabel("Project"))
        self.project_name_edit = QLineEdit("NPG Lite ECG Validation")
        self.project_name_edit.setToolTip("Project or study name saved into metadata and reports.")
        self.project_name_edit.textChanged.connect(self.update_settings_summary)
        row4.addWidget(self.project_name_edit)

        row4.addWidget(QLabel("Subject"))
        self.subject_id_edit = QLineEdit("S001")
        self.subject_id_edit.setToolTip("De-identified subject ID. Avoid real names.")
        self.subject_id_edit.textChanged.connect(self.update_settings_summary)
        row4.addWidget(self.subject_id_edit)

        row4.addWidget(QLabel("Session"))
        self.session_label_edit = QLineEdit("ECG headroom test")
        self.session_label_edit.setToolTip("Short session label, e.g. polarity test, resting ECG, pre/post exercise.")
        self.session_label_edit.textChanged.connect(self.update_settings_summary)
        row4.addWidget(self.session_label_edit)

        settings_layout.addLayout(row4)

        row5 = QHBoxLayout()

        row5.addWidget(QLabel("Condition"))
        self.condition_edit = QLineEdit("Resting")
        self.condition_edit.setToolTip("Condition, e.g. resting, post-exercise, eyes closed, contraction.")
        self.condition_edit.textChanged.connect(self.update_settings_summary)
        row5.addWidget(self.condition_edit)

        row5.addWidget(QLabel("Posture"))
        self.posture_edit = QLineEdit("Sitting")
        self.posture_edit.setToolTip("Posture, e.g. supine, sitting, standing.")
        self.posture_edit.textChanged.connect(self.update_settings_summary)
        row5.addWidget(self.posture_edit)

        row5.addWidget(QLabel("Notes"))
        self.session_notes_edit = QLineEdit("")
        self.session_notes_edit.setPlaceholderText("Optional protocol/session note")
        self.session_notes_edit.setToolTip("Free-text note saved into metadata and reports.")
        self.session_notes_edit.textChanged.connect(self.update_settings_summary)
        row5.addWidget(self.session_notes_edit, stretch=1)

        settings_layout.addLayout(row5)

        layout.addWidget(self.settings_panel)

        # ------------------------------------------------------------
        # Recorder control ribbon, matched to Analysis panel style
        # ------------------------------------------------------------

        ribbon_row_1 = QHBoxLayout()
        ribbon_row_1.setSpacing(8)

        ribbon_row_2 = QHBoxLayout()
        ribbon_row_2.setSpacing(8)

        # ------------------------------------------------------------
        # Display / Filter group
        # Analysis-panel style: natural sizing, no cramped fixed-width labels.
        # ------------------------------------------------------------

        display_group, row_filter = make_recorder_group("Display / Filter")

        self.show_raw_checkbox = QCheckBox("Raw")
        self.show_raw_checkbox.setChecked(True)
        self.show_raw_checkbox.stateChanged.connect(self.rebuild_preview_plots)
        row_filter.addWidget(self.show_raw_checkbox)

        self.show_review_filtered_checkbox = QCheckBox("Filtered")
        self.show_review_filtered_checkbox.setChecked(False)
        self.show_review_filtered_checkbox.setToolTip("Show filtered review trace after recording.")
        self.show_review_filtered_checkbox.stateChanged.connect(self.review_filter_changed)
        row_filter.addWidget(self.show_review_filtered_checkbox)

        row_filter.addWidget(QLabel("Low"))

        self.bp_low_spin = QDoubleSpinBox()
        self.bp_low_spin.setRange(0.1, 500.0)
        self.bp_low_spin.setValue(0.5)
        self.bp_low_spin.setSingleStep(0.5)
        self.bp_low_spin.setDecimals(2)
        self.bp_low_spin.setMinimumWidth(75)
        row_filter.addWidget(self.bp_low_spin)

        row_filter.addWidget(QLabel("High"))

        self.bp_high_spin = QDoubleSpinBox()
        self.bp_high_spin.setRange(1.0, 1000.0)
        self.bp_high_spin.setValue(40.0)
        self.bp_high_spin.setSingleStep(5.0)
        self.bp_high_spin.setDecimals(2)
        self.bp_high_spin.setMinimumWidth(80)
        row_filter.addWidget(self.bp_high_spin)

        self.notch_checkbox = QCheckBox("50 Hz")
        self.notch_checkbox.setChecked(True)
        row_filter.addWidget(self.notch_checkbox)

        self.invert_display_checkbox = QCheckBox("Invert")
        self.invert_display_checkbox.setToolTip("Display-only inversion. raw.csv remains unchanged.")
        self.invert_display_checkbox.setChecked(False)
        self.invert_display_checkbox.stateChanged.connect(self.on_invert_display_changed)
        row_filter.addWidget(self.invert_display_checkbox)

        self.apply_review_filter_btn = QPushButton("Apply")
        self.apply_review_filter_btn.setMinimumWidth(75)
        self.apply_review_filter_btn.setToolTip("Apply review filter")
        self.apply_review_filter_btn.clicked.connect(self.apply_review_filter)
        self.apply_review_filter_btn.setEnabled(False)
        row_filter.addWidget(self.apply_review_filter_btn)

        ribbon_row_1.addWidget(display_group, stretch=4)

        # ------------------------------------------------------------
        # Status group
        # Two-line layout to prevent cramped clipping/recommendation text.
        # Line 1: Mode | Recorded | ADC
        # Line 2: Recommendation
        # ------------------------------------------------------------

        status_group = QGroupBox("Status")
        status_outer_layout = QVBoxLayout()
        status_outer_layout.setContentsMargins(8, 12, 8, 8)
        status_outer_layout.setSpacing(5)
        status_group.setLayout(status_outer_layout)

        status_top_row = QHBoxLayout()
        status_top_row.setSpacing(8)

        self.review_label = QLabel("Mode: Idle")
        self.review_label.setMinimumWidth(300)
        self.review_label.setStyleSheet("font-weight: bold;")
        status_top_row.addWidget(self.review_label, stretch=2)

        self.elapsed_label = QLabel("Elapsed: 00:00")
        self.elapsed_label.setMinimumWidth(190)
        self.elapsed_label.setStyleSheet("font-weight: bold;")
        status_top_row.addWidget(self.elapsed_label, stretch=1)

        self.adc_status_label = QLabel("ADC: --")
        self.adc_status_label.setMinimumWidth(360)
        self.adc_status_label.setWordWrap(False)
        self.adc_status_label.setToolTip(
            "Live ADC headroom status from original raw values. "
            "Display inversion does not affect this check."
        )
        status_top_row.addWidget(self.adc_status_label, stretch=2)

        status_outer_layout.addLayout(status_top_row)

        self.recommendation_label = QLabel("Recommendation: --")
        self.recommendation_label.setWordWrap(False)
        self.recommendation_label.setMinimumWidth(500)
        status_outer_layout.addWidget(self.recommendation_label)

        ribbon_row_1.addWidget(status_group, stretch=5)

        marker_row = QHBoxLayout()

        marker_row.addWidget(QLabel("Marker"))

        self.marker_edit = QLineEdit()
        self.marker_edit.setPlaceholderText("Type marker label and press Enter")
        self.marker_edit.returnPressed.connect(self.add_marker_from_entry)
        marker_row.addWidget(self.marker_edit, stretch=1)

        self.add_marker_btn = QPushButton("＋M")
        self.add_marker_btn.setToolTip("Add marker at current recorded/review time")
        self.add_marker_btn.clicked.connect(self.add_marker_from_entry)
        marker_row.addWidget(self.add_marker_btn)

        self.clear_markers_btn = QPushButton("Clear M")
        self.clear_markers_btn.setToolTip("Clear markers from current unsaved/review session")
        self.clear_markers_btn.clicked.connect(self.clear_markers)
        marker_row.addWidget(self.clear_markers_btn)

        marker_group = QGroupBox("Markers")
        marker_group.setLayout(marker_row)
        ribbon_row_2.addWidget(marker_group, stretch=5)

        row_control = QHBoxLayout()

        row_control.addWidget(QLabel("Timebase"))
        self.timebase_btn = QPushButton(f"{self.preview_seconds}s")
        self.timebase_btn.setToolTip("Click to cycle 2s → 5s → 10s → 20s → 30s → 60s")
        self.timebase_btn.clicked.connect(self.cycle_timebase)
        row_control.addWidget(self.timebase_btn)

        self.review_start_btn = QPushButton("|◀")
        self.review_start_btn.setToolTip("Review start")
        self.review_start_btn.clicked.connect(self.review_go_start)
        row_control.addWidget(self.review_start_btn)

        self.review_end_btn = QPushButton("▶|")
        self.review_end_btn.setToolTip("Review end")
        self.review_end_btn.clicked.connect(self.review_go_end)
        row_control.addWidget(self.review_end_btn)

        row_control.addSpacing(20)

        row_control.addWidget(QLabel("Amp"))
        self.amp_target_box = QComboBox()
        self.amp_target_box.addItems(["All", "ch1"])
        self.amp_target_box.setToolTip("v0.1-alpha: only one ECG channel is exposed.")
        row_control.addWidget(self.amp_target_box)

        self.gain_up_btn = QPushButton("+")
        self.gain_up_btn.setToolTip("Increase displayed amplitude")
        self.gain_up_btn.clicked.connect(self.gain_up)
        row_control.addWidget(self.gain_up_btn)

        self.gain_down_btn = QPushButton("-")
        self.gain_down_btn.setToolTip("Decrease displayed amplitude")
        self.gain_down_btn.clicked.connect(self.gain_down)
        row_control.addWidget(self.gain_down_btn)

        self.reset_amp_btn = QPushButton("0")
        self.reset_amp_btn.setToolTip("Reset amplitude")
        self.reset_amp_btn.clicked.connect(self.reset_amplitude)
        row_control.addWidget(self.reset_amp_btn)

        self.auto_expand_checkbox = QCheckBox("AutoY")
        self.auto_expand_checkbox.setChecked(True)
        row_control.addWidget(self.auto_expand_checkbox)

        nav_group = QGroupBox("Navigation / Amplitude")
        nav_group.setLayout(row_control)
        ribbon_row_2.addWidget(nav_group, stretch=4)

        row_buttons = QHBoxLayout()

        self.play_btn = QPushButton("▶")
        self.play_btn.setToolTip("Start recording")
        self.play_btn.clicked.connect(self.play_pause_clicked)
        row_buttons.addWidget(self.play_btn)

        self.stop_btn = QPushButton("■")
        self.stop_btn.setToolTip("Stop recording")
        self.stop_btn.clicked.connect(self.stop_recording)
        self.stop_btn.setEnabled(False)
        row_buttons.addWidget(self.stop_btn)

        self.keep_btn = QPushButton("✓")
        self.keep_btn.setToolTip("Keep recording")
        self.keep_btn.clicked.connect(self.keep_recording)
        self.keep_btn.setEnabled(False)
        getattr(self, "analyse_recording_btn", None) and self.analyse_recording_btn.setEnabled(False)
        row_buttons.addWidget(self.keep_btn)

        self.discard_btn = QPushButton("✕")
        self.discard_btn.setToolTip("Discard recording")
        self.discard_btn.clicked.connect(self.discard_recording)

        self.analyse_recording_btn = QPushButton("Analyse")
        self.analyse_recording_btn.setToolTip("Open this reviewed recording directly in the Analysis tab.")
        self.analyse_recording_btn.clicked.connect(self.send_recording_to_analysis)
        getattr(self, "analyse_recording_btn", None) and self.analyse_recording_btn.setEnabled(False)
        self.discard_btn.setEnabled(False)
        getattr(self, "analyse_recording_btn", None) and self.analyse_recording_btn.setEnabled(False)
        row_buttons.addWidget(self.discard_btn)
        row_buttons.addWidget(self.analyse_recording_btn)

        actions_group = QGroupBox("Actions")
        actions_group.setLayout(row_buttons)
        ribbon_row_2.addWidget(actions_group, stretch=3)

        ribbon_row_1.addStretch()
        layout.addLayout(ribbon_row_1)

        ribbon_row_2.addStretch()
        layout.addLayout(ribbon_row_2)

        self.preview_widget = ScrubbablePreviewWidget()
        self.preview_widget.setBackground((5, 6, 9))
        self.preview_widget.set_scrub_callback(self.scrub_review_window)

        self.preview_widget.setMinimumHeight(300)
        self.preview_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.preview_widget, stretch=1)

        scrub_row = QHBoxLayout()

        self.scrub_label = QLabel("Time: --")
        self.scrub_label.setMinimumWidth(230)
        scrub_row.addWidget(self.scrub_label)

        self.scrub_slider = QSlider(Qt.Horizontal)
        self.scrub_slider.setMinimum(0)
        self.scrub_slider.setMaximum(0)
        self.scrub_slider.setValue(0)
        self.scrub_slider.setEnabled(False)
        self.scrub_slider.setToolTip(
            "Review scrub bar: drag to move the visible time window through the recording."
        )
        self.scrub_slider.valueChanged.connect(self.scrub_slider_changed)
        scrub_row.addWidget(self.scrub_slider, stretch=1)

        layout.addLayout(scrub_row)

        layout.addSpacing(2)

        bottom_info_row = QHBoxLayout()
        bottom_info_row.setSpacing(6)

        self.selection_box = QTextEdit()
        self.selection_box.setReadOnly(True)
        self.selection_box.setMaximumHeight(64)
        self.selection_box.setMinimumWidth(360)
        self.selection_box.setText(
            "Selection Analysis: Drag over a raw or filtered trace during review. "
            "Hold at left/right edge to accelerate through the recording."
        )
        bottom_info_row.addWidget(self.selection_box, stretch=2)

        self.integrity_box = QTextEdit()
        self.integrity_box.setReadOnly(True)
        self.integrity_box.setMaximumHeight(64)
        self.integrity_box.setMinimumWidth(300)
        self.integrity_box.setText("Integrity Summary: Not recorded yet.")
        bottom_info_row.addWidget(self.integrity_box, stretch=2)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setMaximumHeight(64)
        self.log_box.setMinimumWidth(320)
        bottom_info_row.addWidget(self.log_box, stretch=2)

        bottom_group = QGroupBox("Review / Integrity / Log")
        bottom_group.setLayout(bottom_info_row)
        layout.addWidget(bottom_group)

        self.plot_timer = QTimer(self)
        self.plot_timer.setInterval(100)
        self.plot_timer.timeout.connect(self.update_preview_plot)
        self.plot_timer.start()

        self.elapsed_timer = QTimer(self)
        self.elapsed_timer.setInterval(250)
        self.elapsed_timer.timeout.connect(self.update_elapsed_timer)
        self.elapsed_timer.start()

        self.apply_theme()
        self.refresh_ports()
        self.rebuild_preview_plots()
        self.update_recommendation()
        self.update_settings_summary()
        self.make_buttons_non_focusable()

    def apply_protocol_config(self, config):
        """
        Apply Setup tab protocol configuration to Recorder.

        This changes UI settings only. It does not start recording.
        Recorder remains editable after setup is applied.
        """

        if config is None:
            return

        signal_type = str(config.get("signal_type", "ECG")).upper()
        protocol_name = str(config.get("protocol_name", signal_type))

        try:
            if hasattr(self, "mode_box"):
                index = self.mode_box.findText(signal_type)
                if index >= 0:
                    self.mode_box.setCurrentIndex(index)
        except Exception:
            pass

        try:
            if hasattr(self, "protocol_box"):
                index = self.protocol_box.findText(protocol_name)
                if index >= 0:
                    self.protocol_box.setCurrentIndex(index)
                else:
                    self.protocol_box.addItem(protocol_name)
                    self.protocol_box.setCurrentText(protocol_name)
        except Exception:
            pass

        try:
            channels = str(int(config.get("recommended_channels", 1)))
            if hasattr(self, "channels_box"):
                index = self.channels_box.findText(channels)
                if index >= 0:
                    self.channels_box.setCurrentIndex(index)
        except Exception:
            pass

        try:
            rate = str(int(config.get("recommended_sample_rate_hz", 500)))
            if hasattr(self, "rate_box"):
                index = self.rate_box.findText(rate)
                if index >= 0:
                    self.rate_box.setCurrentIndex(index)
        except Exception:
            pass

        try:
            duration_text = str(config.get("recommended_duration_text", "--:--:--"))
            if hasattr(self, "duration_edit"):
                if duration_text == "--:--:--":
                    self.duration_edit.reset()
                else:
                    clean = duration_text.replace(":", "")
                    digits = [ch for ch in clean if ch.isdigit()]

                    if len(digits) == 6:
                        self.duration_edit.digits = digits
                        self.duration_edit.update_display()
        except Exception:
            pass

        try:
            placement = str(config.get("electrode_placement", "")).strip()
            if placement and hasattr(self, "placement_edit"):
                self.placement_edit.setText(placement)
        except Exception:
            pass

        try:
            filt = config.get("filter", {}) or {}

            if hasattr(self, "bp_low_spin") and filt.get("low_hz") is not None:
                self.bp_low_spin.setValue(float(filt.get("low_hz")))

            if hasattr(self, "bp_high_spin") and filt.get("high_hz") is not None:
                self.bp_high_spin.setValue(float(filt.get("high_hz")))

            if hasattr(self, "notch_checkbox") and filt.get("notch_50hz") is not None:
                self.notch_checkbox.setChecked(bool(filt.get("notch_50hz")))
        except Exception:
            pass

        try:
            self.update_recommendation()
        except Exception:
            pass

        try:
            self.update_settings_summary()
        except Exception:
            pass

        try:
            self.log("Setup protocol applied:")
            self.log(f"Signal type: {signal_type}")
            self.log(f"Protocol: {protocol_name}")
            self.log(f"Suggested placement: {config.get('electrode_placement', '')}")
        except Exception:
            pass


    def apply_theme(self):
        if self.is_light_theme:
            pg.setConfigOption("background", "w")
            pg.setConfigOption("foreground", "k")

            self.setStyleSheet(
                """
                QWidget {
                    background-color: #f4f4f4;
                    color: #111111;
                }
                QLabel {
                    color: #111111;
                }
                QFrame {
                    border: 1px solid #999999;
                    border-radius: 4px;
                    padding: 4px;
                }
                QGroupBox {
                background-color: #0E1218;
                border: 1px solid #2D333F;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 9px;
                font-weight: bold;
                color: #D4AF37;
            }
                QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 9px;
                padding: 0px 6px;
                background-color: #0E1218;
                color: #D4AF37;
                font-weight: bold;
            }
                QPushButton {
                background-color: #10141B;
                color: #F2F2F4;
                border: 1px solid #2D333F;
                border-radius: 5px;
                padding: 5px 10px;
                min-height: 22px;
            }
                QPushButton:hover {
                background-color: #0E1218;
                border: 1px solid #D4AF37;
                color: #D4AF37;
            }
                QPushButton:disabled {
                    background-color: #eeeeee;
                    color: #999999;
                }
                QComboBox, QDoubleSpinBox, QLineEdit {
                background-color: #030406;
                color: #F2F2F4;
                border: 1px solid #2D333F;
                border-radius: 4px;
                padding: 4px 6px;
                min-height: 22px;
            }
                QTextEdit {
                background-color: #080B10;
                color: #F2F2F4;
                border: 1px solid #2D333F;
                border-radius: 5px;
                padding: 6px;
                selection-background-color: #D4AF37;
                selection-color: #000000;
            }
                QCheckBox {
                    color: #111111;
                }
                """
            )

            if self.preview_widget is not None:
                self.preview_widget.setBackground((250, 250, 250))

        else:
            pg.setConfigOption("background", "k")
            pg.setConfigOption("foreground", "w")

            self.setStyleSheet(
                """
                QWidget {
                    background-color: #050608;
                    color: #F2F2F4;
                    font-family: Segoe UI, Arial;
                    font-size: 10pt;
                }
                QLabel {
                    color: #F2F2F4;
                    background-color: transparent;
                }
                QFrame {
                    background-color: #101219;
                    border: 1px solid #202630;
                    border-radius: 5px;
                    padding: 4px;
                }
                QGroupBox {
                background-color: #0E1218;
                border: 1px solid #2D333F;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 9px;
                font-weight: bold;
                color: #D4AF37;
            }
                QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 9px;
                padding: 0px 6px;
                background-color: #0E1218;
                color: #D4AF37;
                font-weight: bold;
            }
                QPushButton {
                background-color: #10141B;
                color: #F2F2F4;
                border: 1px solid #2D333F;
                border-radius: 5px;
                padding: 5px 10px;
                min-height: 22px;
            }
                QPushButton:hover {
                background-color: #0E1218;
                border: 1px solid #D4AF37;
                color: #D4AF37;
            }
                QPushButton:pressed {
                background-color: #050608;
                border: 1px solid #D4AF37;
                color: #F2F2F4;
            }
                QPushButton:disabled {
                    background-color: #101219;
                    color: #686D7A;
                    border: 1px solid #262A34;
                }
                QComboBox, QDoubleSpinBox, QLineEdit {
                background-color: #030406;
                color: #F2F2F4;
                border: 1px solid #2D333F;
                border-radius: 4px;
                padding: 4px 6px;
                min-height: 22px;
            }
                QComboBox:hover, QDoubleSpinBox:hover, QLineEdit:hover {
                    border: 1px solid #D4AF37;
                }
                QTextEdit {
                background-color: #080B10;
                color: #F2F2F4;
                border: 1px solid #2D333F;
                border-radius: 5px;
                padding: 6px;
                selection-background-color: #D4AF37;
                selection-color: #000000;
            }
                QCheckBox {
                    color: #F2F2F4;
                    spacing: 6px;
                    background-color: transparent;
                }
                QCheckBox::indicator {
                    width: 14px;
                    height: 14px;
                    border-radius: 2px;
                    border: 1px solid #4A4F5C;
                    background-color: #08090D;
                }
                QCheckBox::indicator:checked {
                    background-color: #D4AF37;
                    border: 1px solid #D4AF37;
                }
                QSlider::groove:horizontal {
                    border: 1px solid #202630;
                    height: 6px;
                    background: #0E1218;
                    border-radius: 3px;
                }
                QSlider::handle:horizontal {
                    background: #D4AF37;
                    border: 1px solid #D4AF37;
                    width: 14px;
                    margin: -5px 0;
                    border-radius: 7px;
                }
                """
            )

            if self.preview_widget is not None:
                self.preview_widget.setBackground((5, 6, 9))

        self.update_mode_label_style()
        self.update_recommendation()

    def toggle_theme(self):
        self.is_light_theme = self.theme_checkbox.isChecked()
        self.apply_theme()
        self.rebuild_preview_plots()
        self.update_preview_plot()

    def set_external_theme(self, light_mode):
        """
        Called by the main OpenPhysiologyLab theme toggle.

        Keeps recorder plot background and trace colors in sync with the global app theme.
        """

        self.is_light_theme = bool(light_mode)

        if hasattr(self, "theme_checkbox"):
            old_state = self.theme_checkbox.blockSignals(True)
            self.theme_checkbox.setChecked(self.is_light_theme)
            self.theme_checkbox.blockSignals(old_state)

        self.apply_theme()
        self.rebuild_preview_plots()
        self.update_preview_plot()

    def make_buttons_non_focusable(self):
        for button in self.findChildren(QPushButton):
            button.setFocusPolicy(Qt.NoFocus)

            try:
                button.setAutoDefault(False)
                button.setDefault(False)
            except Exception:
                pass

    def toggle_settings_panel(self):
        self.settings_panel.setVisible(not self.settings_panel.isVisible())

    def update_settings_summary(self):
        try:
            port = self.port_box.currentText()
            mode = self.mode_box.currentText()

            if hasattr(self, "protocol_box"):
                protocol = self.protocol_box.currentText()
            else:
                protocol = "--"

            ch = self.channels_box.currentText()
            hz = self.rate_box.currentText()
            dur = self.duration_edit.text()
            placement = self.placement_edit.text().strip()

            if self.duration_edit.is_blank():
                dur_text = "manual"
            else:
                dur_text = dur

            self.settings_summary_label.setText(
                f"{port} | {mode} | {protocol} | ch{ch} | {hz} Hz | {dur_text} | {placement}"
            )
        except Exception:
            self.settings_summary_label.setText("Settings: --")

    def log(self, text):
        self.log_box.append(str(text))

    def update_mode_label_style(self):
        text = self.review_label.text()

        if "Recording" in text or "Paused" in text:
            color = "#b8860b" if self.is_light_theme else "#ffd966"
        elif "Review" in text:
            color = "#008000" if self.is_light_theme else "#80ff80"
        elif "Saved" in text:
            color = "#0066aa" if self.is_light_theme else "#80dfff"
        elif "Error" in text:
            color = "#aa0000" if self.is_light_theme else "#ff8080"
        else:
            color = "#111111" if self.is_light_theme else "#dddddd"

        self.review_label.setStyleSheet(f"color: {color}; font-weight: bold;")
        self.elapsed_label.setStyleSheet(
            f"color: {'#0066aa' if self.is_light_theme else '#80dfff'}; font-weight: bold;"
        )

    def set_mode_label(self, text):
        self.review_label.setText(text)
        self.update_mode_label_style()

    def format_elapsed_time_ms(self, seconds):
        """
        Format seconds as MM:SS.mmm.
        """

        try:
            seconds = float(seconds)
        except Exception:
            seconds = 0.0

        if seconds < 0:
            seconds = 0.0

        minutes = int(seconds // 60)
        whole_seconds = int(seconds % 60)
        milliseconds = int(round((seconds - int(seconds)) * 1000))

        if milliseconds >= 1000:
            milliseconds = 0
            whole_seconds += 1

        if whole_seconds >= 60:
            whole_seconds = 0
            minutes += 1

        return f"{minutes:02d}:{whole_seconds:02d}.{milliseconds:03d}"

    def get_recorded_elapsed_seconds_for_display(self):
        """
        Return best current recorded elapsed time for display.

        Priority:
        1. sample-count based time during active recording
        2. latest recorded pc_time_s during manual/review mode
        3. final stored elapsed time
        """

        try:
            rows_count = len(self.all_recorded_rows)
        except Exception:
            rows_count = 0

        if rows_count > 0:
            try:
                fs = float(self.rate_box.currentText())
            except Exception:
                fs = None

            # During recording, sample-count based time is best for analysis-facing display.
            # For N recorded samples, acquisition duration represented by samples is N/fs.
            if self.is_recording and fs is not None and fs > 0:
                return rows_count / fs

            # During review, use the final sample-count duration if possible.
            if (self.review_mode or self.saved_review_visible) and fs is not None and fs > 0:
                return rows_count / fs

            # Fallback: latest recorded PC-relative sample time.
            try:
                return float(self.all_recorded_rows[-1].get("pc_time_s", 0.0))
            except Exception:
                return 0.0

        return float(self.recording_elapsed_final)

    def update_elapsed_timer(self):
        """
        Show actual recorded elapsed time.

        This avoids the misleading delay between pressing Start and first acquired sample.
        It is especially useful in sample-count locked recordings.
        """

        elapsed = self.get_recorded_elapsed_seconds_for_display()

        self.elapsed_label.setText(
            f"Recorded: {self.format_elapsed_time_ms(elapsed)}"
        )

    def parse_duration_text(self):
        return self.duration_edit.get_duration_seconds()

    def reset_duration(self):
        self.duration_edit.reset()
        self.update_recommendation()
        self.update_settings_summary()

    def get_duration_for_recommendation(self):
        try:
            duration_seconds, _ = self.parse_duration_text()

            if duration_seconds is None:
                return 300

            return int(max(1, duration_seconds))

        except Exception:
            return 300

    def refresh_ports(self):
        self.port_box.clear()

        ports = SerialTransport.list_ports()

        if len(ports) == 0:
            self.port_box.addItem("No ports")
            self.log("No serial ports found.")
            self.update_settings_summary()
            return

        for port in ports:
            self.port_box.addItem(port["device"])

        self.log("Ports refreshed.")
        self.update_settings_summary()

    def update_recommendation(self):
        try:
            channels = int(self.channels_box.currentText())
            rate = int(self.rate_box.currentText())
            baud = int(self.baud_box.currentText())
            duration = self.get_duration_for_recommendation()

            result = recommend_setup(
                num_channels=channels,
                sample_rate_hz=rate,
                baud_rate=baud,
                transport="USB_SERIAL",
                duration_seconds=duration
            )

            status = result.get("status", "Unknown")
            message = result.get("message", "")
            load = result.get("estimated_csv_load_percent", None)

            if self.duration_edit.is_blank():
                duration_note = "Manual stop"
            else:
                duration_note = f"Timed: {self.duration_edit.text()}"

            if load is not None:
                text = (
                    f"Recommendation: {status} | Load: {load}% | "
                    f"{duration_note} | {message}"
                )
            else:
                text = f"Recommendation: {status} | {duration_note} | {message}"

            self.recommendation_label.setText(text)

            if status == "Good":
                color = "#008000" if self.is_light_theme else "#80ff80"
            elif status == "Borderline":
                color = "#aa7700" if self.is_light_theme else "#ffd966"
            elif status == "Risky":
                color = "#aa0000" if self.is_light_theme else "#ff8080"
            else:
                color = "#111111" if self.is_light_theme else "#dddddd"

            self.recommendation_label.setStyleSheet(f"color: {color};")

        except Exception as e:
            self.recommendation_label.setText(f"Recommendation error: {e}")

    def cycle_timebase(self):
        self.timebase_index = (self.timebase_index + 1) % len(TIMEBASE_OPTIONS)
        seconds = TIMEBASE_OPTIONS[self.timebase_index]
        self.preview_seconds = seconds
        self.timebase_btn.setText(f"{seconds}s")

        if self.review_mode:
            self.clamp_review_window()

        self.update_empty_plot_ranges()
        self.update_preview_plot()

    def update_empty_plot_ranges(self):
        for plot in self.preview_plots.values():
            plot.setXRange(0, self.preview_seconds, padding=0)
            plot.setYRange(DEFAULT_ADC_MIN, DEFAULT_ADC_MAX, padding=0)

    def review_go_start(self):
        if not self.review_mode and not self.saved_review_visible:
            return

        self.review_x_min = 0
        self.update_preview_plot()

    def review_go_end(self):
        if not self.review_mode and not self.saved_review_visible:
            return

        total_duration = self.get_recorded_duration()
        self.review_x_min = max(0, total_duration - self.preview_seconds)
        self.update_preview_plot()

    def scrub_review_window(self, dx):
        if not self.review_mode and not self.saved_review_visible:
            return

        step = self.preview_seconds * 0.08

        if dx > 0:
            self.review_x_min -= step
        else:
            self.review_x_min += step

        self.clamp_review_window()
        self.update_preview_plot()

    def clamp_review_window(self):
        total_duration = self.get_recorded_duration()

        if total_duration <= 0:
            self.review_x_min = 0
            return

        max_start = max(0, total_duration - self.preview_seconds)

        if self.review_x_min < 0:
            self.review_x_min = 0

        if self.review_x_min > max_start:
            self.review_x_min = max_start

    def get_recorded_duration(self):
        if len(self.all_recorded_rows) == 0:
            return 0

        return float(self.all_recorded_rows[-1]["pc_time_s"])

    def get_target_plot_keys(self):
        target = self.amp_target_box.currentText()

        if target == "All":
            return list(self.preview_plots.keys())

        keys = []

        for key in self.preview_plots.keys():
            if key.startswith(target + "_"):
                keys.append(key)

        return keys

    def gain_up(self):
        self.change_amplitude(scale=0.80)

    def gain_down(self):
        self.change_amplitude(scale=1.25)

    def change_amplitude(self, scale):
        keys = self.get_target_plot_keys()

        for key in keys:
            if key not in self.y_ranges:
                continue

            y_min, y_max = self.y_ranges[key]

            center = (y_min + y_max) / 2
            half_range = (y_max - y_min) / 2

            if half_range <= 0:
                half_range = 1

            new_half_range = half_range * scale

            self.y_ranges[key] = (
                center - new_half_range,
                center + new_half_range
            )

        self.update_preview_plot()

    def reset_amplitude(self):
        keys = self.get_target_plot_keys()

        for key in keys:
            if key in self.y_ranges:
                del self.y_ranges[key]

        self.update_empty_plot_ranges()
        self.update_preview_plot()

    def update_stable_y_range(self, plot_key, y_values):
        if len(y_values) < 2:
            return None

        y_min = float(np.min(y_values))
        y_max = float(np.max(y_values))

        if y_max == y_min:
            y_min -= 1
            y_max += 1

        margin = (y_max - y_min) * 0.20
        proposed_min = y_min - margin
        proposed_max = y_max + margin

        if plot_key not in self.y_ranges:
            self.y_ranges[plot_key] = (proposed_min, proposed_max)
            return self.y_ranges[plot_key]

        current_min, current_max = self.y_ranges[plot_key]

        if self.auto_expand_checkbox.isChecked():
            expanded_min = min(current_min, proposed_min)
            expanded_max = max(current_max, proposed_max)

            self.y_ranges[plot_key] = (expanded_min, expanded_max)

        return self.y_ranges[plot_key]

    def get_review_filter_settings(self):
        return {
            "display_only": True,
            "show_raw_signal": self.show_raw_checkbox.isChecked(),
            "show_filtered_signal_in_review": self.show_review_filtered_checkbox.isChecked(),
            "bandpass_low_hz": float(self.bp_low_spin.value()),
            "bandpass_high_hz": float(self.bp_high_spin.value()),
            "notch_50hz": self.notch_checkbox.isChecked(),
            "processed_data_saved": False,
            "analysis_rule": "Analysis must load raw.csv only.",
            "note": "Review filter only. raw.csv remains unfiltered raw ADC."
        }

    def filter_review_signal(self, y, fs):
        filtered, info = apply_bandpass_notch(
            signal=y,
            fs=fs,
            low_hz=float(self.bp_low_spin.value()),
            high_hz=float(self.bp_high_spin.value()),
            notch_hz=50.0,
            use_notch=self.notch_checkbox.isChecked(),
            filter_order=4,
            notch_quality=30.0
        )

        return filtered

    def review_filter_changed(self):
        if not self.review_mode and not self.saved_review_visible:
            return

        self.rebuild_preview_plots()
        self.update_preview_plot()

    def apply_review_filter(self):
        if not self.review_mode and not self.saved_review_visible:
            self.log("Review filter can be applied only after recording is stopped.")
            return

        self.y_ranges = {}
        self.rebuild_preview_plots()
        self.update_preview_plot()

        self.log("Review filter applied to display.")
        self.log(str(self.get_review_filter_settings()))

    def apply_plot_theme(self, mode="dark"):
        self.plot_theme_mode = mode
        palette = get_plot_palette(mode)

        for attr in ["raw_plot", "filtered_plot", "preview_plot", "plot_widget"]:
            plot = getattr(self, attr, None)
            if plot is None:
                continue
            try:
                plot.setBackground(palette['background'])
                plot.showGrid(x=True, y=True, alpha=0.32)
                for axis_name in ["left", "bottom"]:
                    axis = plot.getAxis(axis_name)
                    axis.setPen(palette['axis'])
                    axis.setTextPen(palette['axis'])
            except Exception:
                pass

    def get_plot_palette_current(self):
        return get_plot_palette(getattr(self, "plot_theme_mode", "dark"))

    def configure_plot(self, plot, show_time_axis=False):
        plot.hideButtons()
        plot.enableAutoRange(axis="x", enable=False)
        plot.enableAutoRange(axis="y", enable=False)

        bottom_axis = plot.getAxis("bottom")
        left_axis = plot.getAxis("left")

        if show_time_axis:
            bottom_axis.setHeight(36)
            bottom_axis.setStyle(showValues=True)
        else:
            bottom_axis.setHeight(4)
            bottom_axis.setStyle(showValues=False)

        left_axis.setWidth(42)

        plot.showGrid(x=True, y=True, alpha=0.45)
        plot.setMouseEnabled(x=False, y=False)
        plot.setMenuEnabled(False)

        plot.setXRange(0, self.preview_seconds, padding=0)
        plot.setYRange(DEFAULT_ADC_MIN, DEFAULT_ADC_MAX, padding=0)

    def make_plot(self, plot_key, row, show_time_axis):
        view_box = SelectionViewBox(
            plot_key=plot_key,
            selection_callback=self.handle_plot_selection,
            clear_callback=self.clear_active_selection
        )

        plot = pg.PlotItem(
            viewBox=view_box,
            axisItems={"bottom": TimeAxisItem(orientation="bottom")}
        )

        self.preview_widget.addItem(plot, row=row, col=0)
        self.configure_plot(plot, show_time_axis=show_time_axis)

        return plot

    def get_trace_pen(self, filtered=False):
        if filtered:
            return pg.mkPen(self.get_plot_palette_current()["filtered"], width=1)

        if self.is_light_theme:
            return pg.mkPen((0, 90, 180), width=1)

        return pg.mkPen(self.get_plot_palette_current()["raw"], width=1)

    def get_selection_brush(self):
        if self.is_light_theme:
            return pg.mkBrush(0, 100, 255, 45)
        return pg.mkBrush(245, 176, 0, 55)

    def rebuild_preview_plots(self):
        if self.preview_widget is None:
            return

        self.stop_edge_scroll_selection()

        self.preview_widget.clear()
        self.preview_plots = {}
        self.preview_curves = {}
        self.selection_regions = {}
        self.y_ranges = {}

        try:
            channels = int(self.channels_box.currentText())
        except Exception:
            channels = 1

        show_raw = self.show_raw_checkbox.isChecked()
        show_filtered = (
            (self.review_mode or self.saved_review_visible)
            and self.show_review_filtered_checkbox.isChecked()
        )

        row = 0

        for i in range(1, channels + 1):
            ch_name = f"ch{i}"

            if show_raw:
                plot_key = f"{ch_name}_raw"
                show_time_axis = (not show_filtered and i == channels)

                plot = self.make_plot(
                    plot_key=plot_key,
                    row=row,
                    show_time_axis=show_time_axis
                )

                plot.setLabel("left", ch_name)

                if show_time_axis:
                    plot.setLabel("bottom", "Time", units="MM:SS")
                else:
                    plot.setLabel("bottom", "")

                curve = plot.plot([], [], pen=self.get_trace_pen(filtered=False))

                self.preview_plots[plot_key] = plot
                self.preview_curves[plot_key] = curve

                row += 1

            if show_filtered:
                plot_key = f"{ch_name}_filtered"
                show_time_axis = (i == channels)

                plot = self.make_plot(
                    plot_key=plot_key,
                    row=row,
                    show_time_axis=show_time_axis
                )

                plot.setLabel("left", f"{ch_name}F")

                if show_time_axis:
                    plot.setLabel("bottom", "Time", units="MM:SS")
                else:
                    plot.setLabel("bottom", "")

                curve = plot.plot([], [], pen=self.get_trace_pen(filtered=True))

                self.preview_plots[plot_key] = plot
                self.preview_curves[plot_key] = curve

                row += 1

        self.update_empty_plot_ranges()
        self.update_all_selection_regions()

        self.log(
            f"Preview rebuilt for {channels} channel(s). "
            f"Raw: {show_raw}, Filtered review: {show_filtered}"
        )

    def receive_sample_batch(self, batch):
        self.all_recorded_rows.extend(batch)

        if self.review_mode or self.saved_review_visible:
            return

        return

    def format_time_mmss_ms(self, seconds):
        """
        Format seconds as MM:SS.mmm.
        """

        try:
            seconds = float(seconds)
        except Exception:
            seconds = 0.0

        if seconds < 0:
            seconds = 0.0

        minutes = int(seconds // 60)
        whole_seconds = int(seconds % 60)
        milliseconds = int(round((seconds - int(seconds)) * 1000))

        if milliseconds >= 1000:
            milliseconds = 0
            whole_seconds += 1

        if whole_seconds >= 60:
            whole_seconds = 0
            minutes += 1

        return f"{minutes:02d}:{whole_seconds:02d}.{milliseconds:03d}"

    def scrub_slider_changed(self, value):
        """
        Move review window using the shared scrub bar.

        Slider value is stored in milliseconds.
        """

        if self.updating_scrub_slider:
            return

        if not self.review_mode and not self.saved_review_visible:
            return

        self.review_x_min = float(value) / 1000.0
        self.clamp_review_window()
        self.update_preview_plot()

    def update_scrub_controls(self, x_min=None, x_max=None):
        """
        Update scrub bar range, value, label, and enabled state.

        The scrub bar is enabled only during review/saved mode.
        It controls the visible review window.
        """

        if not hasattr(self, "scrub_slider"):
            return

        total_duration = self.get_recorded_duration()

        review_available = (
            (self.review_mode or self.saved_review_visible)
            and total_duration > 0
        )

        if x_min is None:
            x_min = self.review_x_min

        if x_max is None:
            x_max = x_min + self.preview_seconds

        x_min = max(0.0, float(x_min))
        x_max = max(x_min, float(x_max))

        visible_end = min(x_max, total_duration)

        max_start = max(0.0, total_duration - self.preview_seconds)
        max_slider_value = int(round(max_start * 1000))
        current_slider_value = int(round(min(x_min, max_start) * 1000))

        self.updating_scrub_slider = True

        try:
            self.scrub_slider.setEnabled(review_available and max_slider_value > 0)
            self.scrub_slider.setMinimum(0)
            self.scrub_slider.setMaximum(max_slider_value)
            self.scrub_slider.setSingleStep(10)
            self.scrub_slider.setPageStep(max(10, int(round(self.preview_seconds * 1000))))

            if current_slider_value < 0:
                current_slider_value = 0

            if current_slider_value > max_slider_value:
                current_slider_value = max_slider_value

            self.scrub_slider.setValue(current_slider_value)

        finally:
            self.updating_scrub_slider = False

        if review_available:
            self.scrub_label.setText(
                "Time: "
                f"{self.format_time_mmss_ms(x_min)}–"
                f"{self.format_time_mmss_ms(visible_end)} / "
                f"{self.format_time_mmss_ms(total_duration)}"
            )
        else:
            self.scrub_label.setText("Time: --")

    def get_current_marker_time_s(self):
        """
        Decide where to place a marker.

        Recording/paused:
            latest acquired sample time.

        Review/saved:
            center of visible review window.

        Fallback:
            0 seconds.
        """

        total_duration = self.get_recorded_duration()

        if total_duration <= 0:
            return 0.0

        if self.is_recording or self.is_paused:
            if len(self.all_recorded_rows) > 0:
                try:
                    fs = float(self.rate_box.currentText())

                    if fs > 0:
                        return len(self.all_recorded_rows) / fs

                except Exception:
                    pass

                try:
                    return float(self.all_recorded_rows[-1].get("pc_time_s", 0.0))
                except Exception:
                    return 0.0

        if self.review_mode or self.saved_review_visible:
            marker_time = self.review_x_min + (self.preview_seconds / 2.0)
            marker_time = max(0.0, min(marker_time, total_duration))
            return marker_time

        return total_duration

    def add_marker_from_entry(self):
        """
        Add marker from UI entry box.
        """

        label = self.marker_edit.text().strip()

        if not label:
            label = f"Marker {len(self.markers) + 1}"

        marker_time = self.get_current_marker_time_s()

        if len(self.all_recorded_rows) == 0:
            self.log("Cannot add marker: no recording data available yet.")
            return

        if self.is_recording:
            mode = "recording"
        elif self.is_paused:
            mode = "paused"
        elif self.review_mode:
            mode = "review"
        elif self.saved_review_visible:
            mode = "saved_review"
        else:
            mode = "idle"

        marker = {
            "marker_id": len(self.markers) + 1,
            "time_s": float(marker_time),
            "label": label,
            "mode": mode,
            "created_datetime": datetime.now().isoformat(timespec="seconds")
        }

        self.markers.append(marker)
        self.marker_edit.clear()

        self.log(
            f"Marker added: #{marker['marker_id']} "
            f"at {marker['time_s']:.3f} s | {marker['label']}"
        )

        self.update_marker_lines()

        if self.review_session_folder is not None:
            self.write_markers_to_session(self.review_session_folder)

    def clear_markers(self):
        """
        Clear markers for the current session.
        """

        reply = QMessageBox.question(
            self,
            "Clear Markers?",
            "Clear all markers from the current recording/review?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        self.markers = []
        self.clear_marker_lines()

        if self.review_session_folder is not None:
            self.write_markers_to_session(self.review_session_folder)

        self.log("Markers cleared.")

    def clear_marker_lines(self):
        """
        Remove visible marker lines from all plots.
        """

        for plot_key, items in list(self.marker_items.items()):
            plot = self.preview_plots.get(plot_key)

            if plot is None:
                continue

            for item in items:
                try:
                    plot.removeItem(item)
                except Exception:
                    pass

        self.marker_items = {}

    def update_marker_lines(self):
        """
        Draw markers as vertical lines on currently visible plots.

        Markers are stored in absolute recording time.
        Only visible markers are drawn in the current time window.
        """

        if not hasattr(self, "preview_plots"):
            return

        self.clear_marker_lines()

        if len(self.markers) == 0:
            return

        if len(self.preview_plots) == 0:
            return

        rows, x_min, x_max = self.get_rows_for_current_view()

        if len(rows) == 0:
            return

        visible_markers = []

        for marker in self.markers:
            try:
                t = float(marker.get("time_s", 0.0))
            except Exception:
                continue

            if x_min <= t <= x_max:
                visible_markers.append(marker)

        if len(visible_markers) == 0:
            return

        for plot_key, plot in self.preview_plots.items():
            self.marker_items[plot_key] = []

            for marker in visible_markers:
                t = float(marker["time_s"])
                label = str(marker.get("label", ""))

                line = pg.InfiniteLine(
                    pos=t,
                    angle=90,
                    movable=False,
                    pen=pg.mkPen(self.get_plot_palette_current()["marker"], width=1)
                )

                line.setZValue(15)

                try:
                    line.setToolTip(
                        f"Marker #{marker['marker_id']}\n"
                        f"Time: {t:.3f} s\n"
                        f"Label: {label}"
                    )
                except Exception:
                    pass

                plot.addItem(line)
                self.marker_items[plot_key].append(line)

    def write_markers_to_session(self, session_folder):
        """
        Save markers.csv and update metadata.json with marker summary.
        """

        try:
            session_path = Path(session_folder)
        except Exception:
            return

        if not session_path.exists():
            return

        markers_csv_path = session_path / "markers.csv"
        metadata_path = session_path / "metadata.json"

        fieldnames = [
            "marker_id",
            "time_s",
            "label",
            "mode",
            "created_datetime"
        ]

        try:
            with open(markers_csv_path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()

                for marker in self.markers:
                    writer.writerow(marker)

        except Exception as e:
            self.log("Could not write markers.csv:")
            self.log(str(e))
            return

        if metadata_path.exists():
            try:
                with open(metadata_path, "r") as f:
                    metadata = json.load(f)

                metadata["markers"] = {
                    "marker_count": len(self.markers),
                    "marker_file": "markers.csv",
                    "marker_time_unit": "seconds",
                    "marker_reference": (
                        "Marker time is stored in seconds relative to the start of the recorded sample stream."
                    ),
                    "items": self.markers
                }

                saved_files = metadata.get("saved_files", {})

                if isinstance(saved_files, dict):
                    saved_files["marker_file"] = "markers.csv"
                    metadata["saved_files"] = saved_files

                with open(metadata_path, "w") as f:
                    json.dump(metadata, f, indent=4)

            except Exception as e:
                self.log("Could not update metadata.json with markers:")
                self.log(str(e))

    def get_rows_for_current_view(self):
        rows = self.all_recorded_rows

        if len(rows) == 0:
            return [], 0, self.preview_seconds

        if self.review_mode or self.saved_review_visible:
            x_min = self.review_x_min
            x_max = self.review_x_min + self.preview_seconds
            return rows, x_min, x_max

        latest_time = rows[-1]["pc_time_s"]

        trigger_fraction = 0.80
        trigger_time = self.preview_seconds * trigger_fraction

        if latest_time <= trigger_time:
            x_min = 0
            x_max = self.preview_seconds
        else:
            x_min = latest_time - trigger_time
            x_max = x_min + self.preview_seconds

        return rows, x_min, x_max

    def is_display_inverted(self):
        """
        Return whether display inversion is active.

        Display inversion affects only plotting in live/review monitors.
        It must not change raw.csv or stored raw ADC values.
        """

        checkbox = getattr(self, "invert_display_checkbox", None)

        if checkbox is None:
            return False

        try:
            return bool(checkbox.isChecked())
        except Exception:
            return False

    def on_invert_display_changed(self):
        """
        Replot signal after display polarity is toggled.

        Also clears stored stable Y ranges so the inverted trace is not hidden
        outside the previous Y-axis limits.
        """

        for attr in [
            "stable_y_ranges",
            "preview_y_ranges",
            "plot_y_ranges",
            "y_ranges"
        ]:
            obj = getattr(self, attr, None)

            if isinstance(obj, dict):
                obj.clear()

        self.update_preview_plot()

    def baseline_centered_invert_for_display(self, values):
        """
        Display-only polarity inversion for ADC biosignals.

        Do NOT invert ADC traces as -y. Raw ADC data live in a positive
        range, usually 0-4095. Inverting as -y flips around zero and makes
        the live monitor look wrong.

        Correct display inversion reflects the visible signal around its
        local baseline/median:

            y_display = 2 * median(y) - y

        This changes only plotting. It does not change raw.csv, metadata,
        saved samples, or the true ADC clipping status.
        """

        y = np.asarray(values, dtype=float)

        if y.size == 0:
            return y

        finite = np.isfinite(y)

        if not np.any(finite):
            return y

        baseline = float(np.median(y[finite]))
        return (2.0 * baseline) - y

    def update_live_adc_headroom_status(self, visible_values):
        """
        Descriptive live ADC headroom/clipping status for original raw ADC values.

        This checks the real incoming ADC values, not the inverted display values.
        Therefore if display inversion makes low-rail clipping look like an
        upper ceiling, this status still correctly reports LOW-rail clipping.
        """

        label = getattr(self, "adc_status_label", None)

        if label is None:
            return

        try:
            y = np.asarray(visible_values, dtype=float)
        except Exception:
            label.setText("ADC: --")
            return

        if y.size == 0:
            label.setText("ADC: --")
            return

        finite = np.isfinite(y)

        if not np.any(finite):
            label.setText("ADC: --")
            return

        y = y[finite]
        low_count = int(np.sum(y <= DEFAULT_ADC_MIN + 1))
        high_count = int(np.sum(y >= DEFAULT_ADC_MAX - 1))
        y_min = float(np.min(y))
        y_max = float(np.max(y))
        baseline = float(np.median(y))
        low_headroom = baseline - DEFAULT_ADC_MIN
        high_headroom = DEFAULT_ADC_MAX - baseline
        total = int(y.size)
        low_pct = (low_count / total) * 100.0 if total else 0.0
        high_pct = (high_count / total) * 100.0 if total else 0.0

        detail = (
            f"ADC live headroom from original raw values\n"
            f"Low clipping: {low_count} samples ({low_pct:.3f}%)\n"
            f"High clipping: {high_count} samples ({high_pct:.3f}%)\n"
            f"Raw range: {y_min:.0f}–{y_max:.0f} ADC\n"
            f"Baseline/median: {baseline:.0f} ADC\n"
            f"Headroom low: {low_headroom:.0f} ADC\n"
            f"Headroom high: {high_headroom:.0f} ADC\n\n"
            f"Note: display inversion does not affect this check."
        )

        if low_count > 0 or high_count > 0:
            clip_parts = []

            if low_count > 0:
                clip_parts.append(f"LOW {low_count} ({low_pct:.2f}%)")

            if high_count > 0:
                clip_parts.append(f"HIGH {high_count} ({high_pct:.2f}%)")

            text = f"ADC: CLIP {' | '.join(clip_parts)}"
            color = "#aa0000" if self.is_light_theme else "#ff8080"

        elif low_headroom < 250 or high_headroom < 250:
            text = f"ADC: CAUTION | base {baseline:.0f} | L {low_headroom:.0f} H {high_headroom:.0f}"
            color = "#aa7700" if self.is_light_theme else "#ffd966"

        else:
            text = f"ADC: OK | base {baseline:.0f} | L {low_headroom:.0f} H {high_headroom:.0f}"
            color = "#008000" if self.is_light_theme else "#80ff80"

        label.setText(text)
        label.setToolTip(detail)
        label.setStyleSheet(f"color: {color}; font-weight: bold;")

    def update_preview_plot(self):
        rows, x_min, x_max = self.get_rows_for_current_view()

        if len(rows) == 0:
            self.update_empty_plot_ranges()
            self.update_scrub_controls(0, self.preview_seconds)
            return

        try:
            channels = int(self.channels_box.currentText())
            fs = int(self.rate_box.currentText())
        except Exception:
            channels = 1
            fs = 500

        invert_display = self.is_display_inverted()

        for i in range(1, channels + 1):
            ch_name = f"ch{i}"

            x = []
            y_raw = []

            for row in rows:
                value = row.get(ch_name)

                if value is None:
                    continue

                if row["pc_time_s"] < x_min:
                    continue

                if row["pc_time_s"] > x_max:
                    continue

                x.append(row["pc_time_s"])
                y_raw.append(value)

            if len(x) == 0:
                continue

            # Raw monitor displays original raw ADC values unless display inversion is enabled.
            # Inversion is baseline-centered, not zero-centered. raw.csv remains unchanged.
            if invert_display:
                y_display = self.baseline_centered_invert_for_display(y_raw)
            else:
                y_display = np.asarray(y_raw, dtype=float)

            # Live ADC status must always use original raw ADC values.
            # Do this for ch1 only to avoid status flicker in multi-channel mode.
            if i == 1:
                self.update_live_adc_headroom_status(y_raw)

            raw_key = f"{ch_name}_raw"

            if raw_key in self.preview_curves:
                self.preview_curves[raw_key].setData(x, y_display)

                plot = self.preview_plots[raw_key]
                plot.setXRange(x_min, x_max, padding=0)

                y_range = self.update_stable_y_range(raw_key, y_display)

                if y_range is not None:
                    plot.setYRange(y_range[0], y_range[1], padding=0)

            filtered_key = f"{ch_name}_filtered"

            if filtered_key in self.preview_curves:
                # Filter is calculated from the original raw ADC values.
                # Inversion is applied only after filtering, for display.
                y_filtered = self.filter_review_signal(y_raw, fs)

                if invert_display:
                    y_filtered = self.baseline_centered_invert_for_display(y_filtered)

                self.preview_curves[filtered_key].setData(x, y_filtered)

                plot = self.preview_plots[filtered_key]
                plot.setXRange(x_min, x_max, padding=0)

                y_range = self.update_stable_y_range(filtered_key, y_filtered)

                if y_range is not None:
                    plot.setYRange(y_range[0], y_range[1], padding=0)

        self.update_all_selection_regions()
        self.update_marker_lines()
        self.update_scrub_controls(x_min, x_max)

    # ========================================================
    # SELECTION + EDGE AUTOSCROLL
    # ========================================================

    def clear_active_selection(self):
        """
        Clear any active selection from all plots.
        """

        self.stop_edge_scroll_selection()
        self.active_selection = None

        for plot_key, region in list(self.selection_regions.items()):
            plot = self.preview_plots.get(plot_key)

            if plot is not None:
                try:
                    plot.removeItem(region)
                except Exception:
                    pass

        self.selection_regions = {}
        self.selection_box.setText(
            "Selection Analysis: No active selection. Drag over a trace during review."
        )

    def handle_plot_selection(self, plot_key, anchor_x, current_x, finished=False):
        if not self.review_mode and not self.saved_review_visible:
            return

        if plot_key not in self.preview_plots:
            return

        total_duration = self.get_recorded_duration()

        if total_duration <= 0:
            return

        anchor_x = max(0.0, min(float(anchor_x), total_duration))
        current_x = max(0.0, min(float(current_x), total_duration))

        x1 = min(anchor_x, current_x)
        x2 = max(anchor_x, current_x)

        if x2 <= x1:
            return

        # Store absolute-time selection.
        # This is independent of the currently visible timebase window.
        self.active_selection = {
            "plot_key": plot_key,
            "x1": x1,
            "x2": x2
        }

        self.update_all_selection_regions()
        self.analyse_selection(plot_key, x1, x2)

        self.update_edge_scroll_state(plot_key, anchor_x, current_x)

        if finished and not (QApplication.mouseButtons() & Qt.LeftButton):
            self.stop_edge_scroll_selection()

    def update_all_selection_regions(self):
        """
        Draw the active selection only on the active plot.

        The stored selection is absolute time.
        The visible selection is clipped to the currently displayed window.
        """

        # Remove all old visual regions first.
        for plot_key, region in list(self.selection_regions.items()):
            plot = self.preview_plots.get(plot_key)

            if plot is not None:
                try:
                    plot.removeItem(region)
                except Exception:
                    pass

        self.selection_regions = {}

        if self.active_selection is None:
            return

        plot_key = self.active_selection.get("plot_key")

        if plot_key not in self.preview_plots:
            return

        plot = self.preview_plots[plot_key]

        x1 = float(self.active_selection.get("x1", 0))
        x2 = float(self.active_selection.get("x2", 0))

        if x2 <= x1:
            return

        try:
            visible_x1, visible_x2 = plot.viewRange()[0]
        except Exception:
            visible_x1 = self.review_x_min
            visible_x2 = self.review_x_min + self.preview_seconds

        draw_x1 = max(x1, visible_x1)
        draw_x2 = min(x2, visible_x2)

        # If selection is outside the visible frame, keep it stored but do not draw it.
        if draw_x2 <= draw_x1:
            return

        region = pg.LinearRegionItem(
            values=[draw_x1, draw_x2],
            orientation=pg.LinearRegionItem.Vertical,
            brush=self.get_selection_brush(),
            movable=False
        )

        plot.addItem(region)
        self.selection_regions[plot_key] = region

    def update_selection_region(self, plot_key, x1, x2):
        """
        Backward-compatible helper.

        Updates the absolute active selection and redraws it.
        """

        self.active_selection = {
            "plot_key": plot_key,
            "x1": float(min(x1, x2)),
            "x2": float(max(x1, x2))
        }

        self.update_all_selection_regions()

    def update_edge_scroll_state(self, plot_key, anchor_x, current_x):
        if not self.review_mode and not self.saved_review_visible:
            self.stop_edge_scroll_selection()
            return

        x_min = self.review_x_min
        x_max = self.review_x_min + self.preview_seconds
        edge_zone = max(self.preview_seconds * 0.12, 0.25)

        distance_to_left = current_x - x_min
        distance_to_right = x_max - current_x

        direction = 0
        strength = 0.0

        if distance_to_left <= edge_zone:
            direction = -1
            strength = (edge_zone - max(distance_to_left, 0.0)) / edge_zone

        elif distance_to_right <= edge_zone:
            direction = 1
            strength = (edge_zone - max(distance_to_right, 0.0)) / edge_zone

        if direction == 0:
            self.stop_edge_scroll_selection()
            return

        total_duration = self.get_recorded_duration()
        max_start = max(0.0, total_duration - self.preview_seconds)

        if direction < 0 and self.review_x_min <= 0:
            self.stop_edge_scroll_selection()
            return

        if direction > 0 and self.review_x_min >= max_start:
            self.stop_edge_scroll_selection()
            return

        self.edge_scroll_active = True
        self.edge_scroll_direction = direction
        self.edge_scroll_strength = max(0.15, min(float(strength), 1.0))
        self.edge_scroll_plot_key = plot_key
        self.edge_scroll_anchor_x = float(anchor_x)
        self.edge_scroll_current_x = float(current_x)

        if not self.edge_scroll_timer.isActive():
            self.edge_scroll_timer.start()

    def stop_edge_scroll_selection(self):
        self.edge_scroll_active = False
        self.edge_scroll_direction = 0
        self.edge_scroll_strength = 0.0
        self.edge_scroll_plot_key = None
        self.edge_scroll_anchor_x = None
        self.edge_scroll_current_x = None

        if self.edge_scroll_timer.isActive():
            self.edge_scroll_timer.stop()

    def perform_edge_scroll_selection(self):
        if not self.edge_scroll_active:
            self.stop_edge_scroll_selection()
            return

        # Stop automatic edge scrolling when the user releases the mouse/trackpad.
        if not (QApplication.mouseButtons() & Qt.LeftButton):
            self.stop_edge_scroll_selection()
            return

        if not self.review_mode and not self.saved_review_visible:
            self.stop_edge_scroll_selection()
            return

        if self.edge_scroll_plot_key not in self.preview_plots:
            self.stop_edge_scroll_selection()
            return

        total_duration = self.get_recorded_duration()

        if total_duration <= 0:
            self.stop_edge_scroll_selection()
            return

        max_start = max(0.0, total_duration - self.preview_seconds)

        if max_start <= 0:
            self.stop_edge_scroll_selection()
            return

        base_step = self.preview_seconds * 0.025
        accelerated_step = base_step * (1.0 + 7.0 * self.edge_scroll_strength)
        delta = accelerated_step * self.edge_scroll_direction

        old_x_min = self.review_x_min
        new_x_min = old_x_min + delta

        if new_x_min < 0:
            new_x_min = 0

        if new_x_min > max_start:
            new_x_min = max_start

        if abs(new_x_min - old_x_min) < 1e-9:
            self.stop_edge_scroll_selection()
            return

        self.review_x_min = new_x_min
        self.clamp_review_window()

        if self.edge_scroll_direction > 0:
            self.edge_scroll_current_x = min(
                total_duration,
                self.review_x_min + self.preview_seconds
            )
        else:
            self.edge_scroll_current_x = max(
                0.0,
                self.review_x_min
            )

        x1 = min(self.edge_scroll_anchor_x, self.edge_scroll_current_x)
        x2 = max(self.edge_scroll_anchor_x, self.edge_scroll_current_x)

        self.active_selection = {
            "plot_key": self.edge_scroll_plot_key,
            "x1": float(x1),
            "x2": float(x2)
        }

        self.update_preview_plot()
        self.update_all_selection_regions()
        self.analyse_selection(self.edge_scroll_plot_key, x1, x2)

    def handle_region_moved(self, plot_key, region):
        if not self.review_mode and not self.saved_review_visible:
            return

        self.stop_edge_scroll_selection()

        x1, x2 = region.getRegion()

        if x2 <= x1:
            return

        self.analyse_selection(plot_key, x1, x2)

    def get_selection_data(self, plot_key, x1, x2):
        if "_raw" in plot_key:
            channel_name = plot_key.replace("_raw", "")
            trace_type = "RAW"
            use_filter = False
        elif "_filtered" in plot_key:
            channel_name = plot_key.replace("_filtered", "")
            trace_type = "FILTERED"
            use_filter = True
        else:
            return None

        x = []
        y = []

        for row in self.all_recorded_rows:
            t = float(row["pc_time_s"])

            if t < x1 or t > x2:
                continue

            value = row.get(channel_name)

            if value is None:
                continue

            x.append(t)
            y.append(value)

        if len(x) == 0:
            return None

        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)

        try:
            fs = int(self.rate_box.currentText())
        except Exception:
            fs = 500

        if use_filter:
            y = self.filter_review_signal(y, fs)

        return {
            "channel": channel_name,
            "trace_type": trace_type,
            "x": x,
            "y": y,
            "fs": fs
        }

    def detect_peaks_in_selection(self, x, y, fs):
        mode = self.mode_box.currentText().upper()

        if mode == "ECG":
            return detect_ecg_r_peaks(x=x, y=y, fs=fs)

        return detect_general_peaks(x=x, y=y, fs=fs)

    def analyse_selection(self, plot_key, x1, x2):
        data = self.get_selection_data(plot_key, x1, x2)

        if data is None:
            self.selection_box.setText("Selection Analysis: No data in selected region.")
            return

        channel = data["channel"]
        trace_type = data["trace_type"]
        x = data["x"]
        y = data["y"]
        fs = data["fs"]

        peak_result = self.detect_peaks_in_selection(x, y, fs)
        peaks = peak_result["peaks"]

        metrics = calculate_selection_metrics(
            x=x,
            y=y,
            peaks=peaks
        )

        text = format_selection_metrics_text(
            channel=channel,
            trace_type=trace_type,
            x1=x1,
            x2=x2,
            peak_method=peak_result.get("method", "unknown"),
            peak_polarity=peak_result.get("polarity", "unknown"),
            peak_warning=peak_result.get("warning", None),
            metrics=metrics
        )

        self.selection_box.setText(text)

    # ========================================================
    # RECORDING CONTROLS
    # ========================================================

    def play_pause_clicked(self):
        if not self.is_recording:
            self.start_recording()
            return

        if self.worker is None:
            return

        if not self.is_paused:
            self.worker.request_pause()
            self.is_paused = True
            self.play_btn.setText("▶")
            self.play_btn.setToolTip("Resume recording")
            self.set_mode_label("Mode: Paused")
            self.log("Pause requested.")
        else:
            self.worker.request_resume()
            self.is_paused = False
            self.play_btn.setText("⏸")
            self.play_btn.setToolTip("Pause recording")
            self.set_mode_label("Mode: Recording")
            self.log("Resume requested.")

    def start_recording(self):
        port = self.port_box.currentText()

        if port == "No ports":
            self.log("No COM port selected.")
            return

        try:
            duration_seconds, duration_text = self.parse_duration_text()
        except Exception as e:
            QMessageBox.warning(self, "Invalid Duration", str(e))
            return

        self.stop_edge_scroll_selection()

        self.review_mode = False
        self.saved_review_visible = False
        self.review_session_folder = None
        self.review_x_min = 0
        self.preview_rows = []
        self.all_recorded_rows = []
        self.y_ranges = {}
        self.selection_regions = {}
        self.active_selection = None
        self.markers = []
        self.clear_marker_lines()
        self.active_selection = None
        self.is_paused = False
        self.is_recording = True

        self.recording_start_wall_time = time.time()
        self.recording_elapsed_final = 0
        self.elapsed_label.setText("Elapsed: 00:00")

        self.set_mode_label("Mode: Recording")

        self.selection_box.setText("Selection Analysis: Available after recording is stopped.")
        self.integrity_box.setText("Integrity Summary: Recording in progress...")

        self.apply_review_filter_btn.setEnabled(False)

        self.rebuild_preview_plots()

        for curve in self.preview_curves.values():
            curve.setData([], [])

        baud = int(self.baud_box.currentText())
        channels = int(self.channels_box.currentText())
        rate = int(self.rate_box.currentText())
        mode = self.mode_box.currentText()

        if hasattr(self, "protocol_box"):
            protocol_name = self.protocol_box.currentText()
        else:
            protocol_name = mode

        device_id = self.device_id_edit.text().strip()
        operator = self.operator_edit.text().strip()
        placement = self.placement_edit.text().strip()

        review_filter_settings = self.get_review_filter_settings()

        self.play_btn.setText("⏸")
        self.play_btn.setToolTip("Pause recording")
        self.stop_btn.setEnabled(True)
        self.keep_btn.setEnabled(False)
        self.discard_btn.setEnabled(False)

        self.log("Starting recording with settings:")
        self.log(f"Port: {port}")
        self.log(f"Baud: {baud}")
        self.log(f"Channels: {channels}")
        self.log(f"Rate: {rate} Hz")
        self.log(f"Mode: {mode}")
        self.log(f"Protocol: {protocol_name}")

        if duration_seconds is None:
            self.log("Duration: manual stop mode")
        else:
            self.log(f"Duration: {duration_text} = {duration_seconds:.3f} s")

        self.worker = RecorderWorker(
            port=port,
            baudrate=baud,
            duration_seconds=duration_seconds,
            duration_text=duration_text,
            sample_rate_hz=rate,
            channels=channels,
            mode=mode,
            device_id=device_id,
            operator=operator,
            electrode_placement=placement,
            protocol_name=protocol_name,
            review_filter_settings=review_filter_settings,
            project_name=self.project_name_edit.text().strip() if hasattr(self, "project_name_edit") else "",
            subject_id=self.subject_id_edit.text().strip() if hasattr(self, "subject_id_edit") else "",
            session_label=self.session_label_edit.text().strip() if hasattr(self, "session_label_edit") else "",
            condition=self.condition_edit.text().strip() if hasattr(self, "condition_edit") else "",
            posture=self.posture_edit.text().strip() if hasattr(self, "posture_edit") else "",
            session_notes=self.session_notes_edit.text().strip() if hasattr(self, "session_notes_edit") else ""
        )

        self.worker.log_signal.connect(self.log)
        self.worker.sample_batch_signal.connect(self.receive_sample_batch)
        self.worker.integrity_signal.connect(self.show_integrity_summary)
        self.worker.finished_signal.connect(self.recording_finished_handler)
        self.worker.error_signal.connect(self.recording_error_handler)

        self.worker.start()

    def stop_recording(self):
        if self.worker is not None:
            self.log("Stop requested.")
            self.worker.request_stop()

        self.stop_btn.setEnabled(False)
        self.play_btn.setEnabled(False)

    def show_integrity_summary(self, metadata):
        status = metadata.get("integrity_status", "UNKNOWN")
        samples = metadata.get("samples_recorded")
        missing = metadata.get("missing_sample_count_estimate_segment_aware")
        rate_device = metadata.get("measured_sample_rate_from_device_time_hz")
        rate_pc = metadata.get("measured_sample_rate_from_pc_time_hz")
        target = metadata.get("sample_rate_target_hz")
        duration_mode = metadata.get("duration_mode")
        requested_text = metadata.get("duration_requested_text")
        stop_reason = metadata.get("stop_reason")
        measured_duration = metadata.get("duration_measured_pc_seconds")
        segments = metadata.get("segments_recorded")
        pause_used = metadata.get("pause_resume_used")

        text = (
            f"Integrity Summary\n"
            f"Status: {status}\n"
            f"Duration mode: {duration_mode}\n"
            f"Requested duration: {requested_text}\n"
            f"Stop reason: {stop_reason}\n"
            f"Measured duration: {measured_duration}\n"
            f"Target sample rate: {target} Hz\n"
            f"Samples recorded: {samples}\n"
            f"Segments: {segments}\n"
            f"Pause/resume used: {pause_used}\n"
            f"Missing sample estimate: {missing}\n"
            f"Measured device-time sample rate: {rate_device}\n"
            f"Measured PC-time sample rate: {rate_pc}\n"
        )

        self.integrity_box.setText(text)

        if status == "PASS":
            color = "#008000" if self.is_light_theme else "#80ff80"
        elif status == "WARNING":
            color = "#aa7700" if self.is_light_theme else "#ffd966"
        else:
            color = "#aa0000" if self.is_light_theme else "#ff8080"

        bg = "#ffffff" if self.is_light_theme else "#1e1e1e"
        self.integrity_box.setStyleSheet(f"background-color: {bg}; color: {color};")

    def recording_finished_handler(self, session_folder):
        self.is_recording = False
        self.is_paused = False

        self.play_btn.setEnabled(True)
        self.play_btn.setText("▶")
        self.play_btn.setToolTip("Start new recording")
        self.stop_btn.setEnabled(False)

        self.review_mode = True
        self.saved_review_visible = False
        self.review_session_folder = session_folder
        self.review_x_min = 0

        if len(self.all_recorded_rows) > 0:
            self.recording_elapsed_final = float(self.all_recorded_rows[-1]["pc_time_s"])
        else:
            self.recording_elapsed_final = 0

        self.recording_start_wall_time = None
        self.update_elapsed_timer()

        self.preview_rows = list(self.all_recorded_rows)

        self.keep_btn.setEnabled(True)
        getattr(self, "analyse_recording_btn", None) and self.analyse_recording_btn.setEnabled(True)
        self.discard_btn.setEnabled(True)
        self.apply_review_filter_btn.setEnabled(True)

        self.set_mode_label(
            "Mode: Review before save | Drag over trace; hold at edge to extend selection"
        )

        self.selection_box.setText(
            "Selection Analysis: Drag horizontally over any raw or filtered trace. "
            "Hold at the left/right edge to accelerate toward start/end."
        )

        self.write_markers_to_session(session_folder)

        self.log("Recording finished.")
        self.log("Review mode enabled.")
        self.log(f"Temporary session folder: {session_folder}")
        self.log("Drag over trace to analyse. Hold at edge to extend selection. Click ✓ to keep, ✕ to discard.")

        self.rebuild_preview_plots()
        self.update_preview_plot()

    def sanitize_session_folder_name(self, name):
        """
        Convert user-entered session name into a safe folder name.
        """

        name = str(name).strip()

        if not name:
            return None

        invalid_chars = '<>:"/\\|?*'

        for ch in invalid_chars:
            name = name.replace(ch, "_")

        name = name.replace(" ", "_")

        while "__" in name:
            name = name.replace("__", "_")

        return name.strip("_")

    def update_metadata_after_save(self, session_folder, save_mode, original_session_folder=None):
        """
        Add final save information into metadata.json after user keeps the recording.
        """

        session_path = Path(session_folder)
        metadata_path = session_path / "metadata.json"

        if not metadata_path.exists():
            return

        try:
            with open(metadata_path, "r") as f:
                metadata = json.load(f)

            metadata["save_action"] = {
                "save_mode": save_mode,
                "saved_datetime": datetime.now().isoformat(timespec="seconds"),
                "final_session_folder": str(session_path),
                "original_session_folder": str(original_session_folder) if original_session_folder else str(session_path)
            }

            saved_files = metadata.get("saved_files", {})

            if not isinstance(saved_files, dict):
                saved_files = {}

            saved_files["raw_file"] = "raw.csv"
            saved_files["metadata_file"] = "metadata.json"

            if (session_path / "markers.csv").exists():
                saved_files["marker_file"] = "markers.csv"

            if "processed_file" not in saved_files:
                saved_files["processed_file"] = None

            metadata["saved_files"] = saved_files

            with open(metadata_path, "w") as f:
                json.dump(metadata, f, indent=4)

        except Exception as e:
            self.log("Could not update metadata after save:")
            self.log(str(e))

    def choose_save_as_folder(self, current_session_folder):
        """
        Ask user for custom save parent folder and session folder name.

        Returns destination folder Path or None.
        """

        current_path = Path(current_session_folder)
        default_parent = current_path.parent
        default_name = current_path.name

        parent_folder = QFileDialog.getExistingDirectory(
            self,
            "Choose parent folder for saved recording",
            str(default_parent)
        )

        if not parent_folder:
            return None

        name, ok = QInputDialog.getText(
            self,
            "Recording folder name",
            "Enter recording folder name:",
            text=default_name
        )

        if not ok:
            return None

        safe_name = self.sanitize_session_folder_name(name)

        if safe_name is None:
            QMessageBox.warning(
                self,
                "Invalid Name",
                "Recording folder name cannot be empty."
            )
            return None

        destination = Path(parent_folder) / safe_name

        if destination.exists():
            QMessageBox.warning(
                self,
                "Folder Already Exists",
                (
                    "A folder with this name already exists.\n\n"
                    f"{destination}\n\n"
                    "Choose another name."
                )
            )
            return None

        return destination

    def send_recording_to_analysis(self):
        """
        Send the current reviewed recording folder to the analysis workflow.

        This does not require final saving first.
        The Analysis Panel will treat it as temporary and force final save
        when Save Analysis is clicked.
        """

        folder = getattr(self, "review_session_folder", None)

        if folder is None:
            QMessageBox.warning(
                self,
                "No Recording",
                "No reviewed recording folder is available yet."
            )
            return

        folder_path = Path(folder)

        if not folder_path.exists():
            QMessageBox.warning(
                self,
                "Folder Missing",
                f"Recording folder not found:\n{folder_path}"
            )
            return

        self.analyse_recording_requested.emit(str(folder_path))


    def choose_final_recording_folder_with_save_dialog(self, current_session_folder):
        """
        Choose final recording FOLDER name.

        This intentionally does NOT use a file-save dialog, because one recording
        is a folder containing raw.csv, metadata.json, and markers.csv.

        Workflow:
        - Show current date/parent folder.
        - Show current recording folder name.
        - User edits only the final folder name.
        - Optional: choose another parent/date folder.
        """

        current_path = Path(current_session_folder)
        default_parent = current_path.parent
        default_name = current_path.name

        dialog = QDialog(self)
        dialog.setWindowTitle("Save Recording Folder")
        dialog.setMinimumWidth(700)

        main_layout = QVBoxLayout(dialog)

        info_label = QLabel(
            "Rename the final recording folder. The files inside will remain as "
            "raw.csv, metadata.json, and markers.csv for analysis compatibility."
        )
        info_label.setWordWrap(True)
        main_layout.addWidget(info_label)

        parent_row = QHBoxLayout()
        parent_row.addWidget(QLabel("Save inside"))

        parent_edit = QLineEdit(str(default_parent))
        parent_edit.setReadOnly(True)
        parent_row.addWidget(parent_edit, stretch=1)

        browse_btn = QPushButton("Browse")
        parent_row.addWidget(browse_btn)

        main_layout.addLayout(parent_row)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Recording folder name"))

        name_edit = QLineEdit(default_name)
        name_edit.selectAll()
        name_row.addWidget(name_edit, stretch=1)

        main_layout.addLayout(name_row)

        if hasattr(self, "human_copy_checkbox"):
            try:
                self.human_copy_checkbox.setParent(None)
            except Exception:
                pass

        self.human_copy_checkbox = QCheckBox(
            "Also create human-friendly renamed copies of raw, metadata, and marker files"
        )
        self.human_copy_checkbox.setChecked(False)
        self.human_copy_checkbox.setToolTip(
            "Usually keep this unchecked. Analysis software will use raw.csv, metadata.json, and markers.csv."
        )
        main_layout.addWidget(self.human_copy_checkbox)

        preview_label = QLabel("")
        preview_label.setWordWrap(True)
        main_layout.addWidget(preview_label)

        button_box = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        main_layout.addWidget(button_box)

        selected_parent = {"path": default_parent}

        def update_preview():
            safe_name = self.sanitize_session_folder_name(name_edit.text())

            if safe_name is None:
                preview_label.setText("Final recording folder: <invalid name>")
                return

            final_path = selected_parent["path"] / safe_name
            preview_label.setText(f"Final recording folder: {final_path}")

        def browse_parent():
            folder = QFileDialog.getExistingDirectory(
                self,
                "Choose date/parent folder",
                str(selected_parent["path"])
            )

            if folder:
                selected_parent["path"] = Path(folder)
                parent_edit.setText(str(selected_parent["path"]))
                update_preview()

        def accept_dialog():
            safe_name = self.sanitize_session_folder_name(name_edit.text())

            if safe_name is None:
                QMessageBox.warning(
                    self,
                    "Invalid folder name",
                    "Recording folder name cannot be empty."
                )
                return

            try:
                self.create_human_friendly_copies_on_save = self.human_copy_checkbox.isChecked()
            except Exception:
                self.create_human_friendly_copies_on_save = False

            dialog.accept()

        browse_btn.clicked.connect(browse_parent)
        name_edit.textChanged.connect(update_preview)
        button_box.accepted.connect(accept_dialog)
        button_box.rejected.connect(dialog.reject)

        update_preview()

        result = dialog.exec_()

        if result != QDialog.Accepted:
            return None

        safe_name = self.sanitize_session_folder_name(name_edit.text())

        if safe_name is None:
            return None

        final_path = selected_parent["path"] / safe_name

        return final_path

    def keep_recording(self):
        """
        Keep recording using direct native Save dialog.

        The dialog opens in the default date folder with the default session name.
        User can simply press Save, or rename the final recording folder.
        """

        if self.review_session_folder is None:
            return

        self.stop_edge_scroll_selection()

        current_path = Path(self.review_session_folder)
        original_session_folder = current_path

        final_path = self.choose_final_recording_folder_with_save_dialog(current_path)

        if final_path is None:
            self.log("Save cancelled. Review remains active.")
            return

        save_mode = "default"

        try:
            # Save markers before any move/rename.
            if hasattr(self, "write_markers_to_session"):
                self.write_markers_to_session(current_path)

            # If the user chose the same folder, just keep it.
            if final_path.resolve() == current_path.resolve():
                self.log("Recording saved using default location.")
                self.log(f"Saved session folder: {current_path}")

            else:
                save_mode = "save_as"

                if final_path.exists():
                    reply = QMessageBox.question(
                        self,
                        "Folder Already Exists",
                        (
                            "A recording folder with this name already exists.\n\n"
                            f"{final_path}\n\n"
                            "Overwrite it?"
                        ),
                        QMessageBox.Yes | QMessageBox.No,
                        QMessageBox.No
                    )

                    if reply != QMessageBox.Yes:
                        self.log("Save cancelled because destination exists.")
                        return

                    shutil.rmtree(final_path)

                shutil.copytree(current_path, final_path)
                shutil.rmtree(current_path)

                self.review_session_folder = str(final_path)
                current_path = final_path

                self.log("Recording saved using Save As.")
                self.log(f"New session folder: {current_path}")

            # Save/update markers and metadata at final path.
            if hasattr(self, "write_markers_to_session"):
                self.write_markers_to_session(current_path)

            if hasattr(self, "update_metadata_after_save"):
                self.update_metadata_after_save(
                    session_folder=current_path,
                    save_mode=save_mode,
                    original_session_folder=original_session_folder
                )

        except Exception as e:
            QMessageBox.critical(
                self,
                "Save Failed",
                str(e)
            )
            self.log("Save failed:")
            self.log(str(e))
            return

        self.recording_finished.emit(str(current_path))

        self.review_mode = False
        self.saved_review_visible = True

        self.keep_btn.setEnabled(False)
        self.discard_btn.setEnabled(False)
        self.apply_review_filter_btn.setEnabled(True)

        self.set_mode_label("Mode: Saved | Review remains visible")

        self.update_preview_plot()

    def discard_recording(self):
        if self.review_session_folder is None:
            return

        self.stop_edge_scroll_selection()

        reply = QMessageBox.question(
            self,
            "Discard Recording?",
            (
                "Are you sure you want to delete this recording?\n\n"
                f"{self.review_session_folder}"
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        try:
            shutil.rmtree(self.review_session_folder)
            self.log("Recording discarded and deleted.")
        except Exception as e:
            self.log("Could not delete recording folder:")
            self.log(str(e))

        self.review_mode = False
        self.saved_review_visible = False
        self.review_session_folder = None
        self.keep_btn.setEnabled(False)
        self.discard_btn.setEnabled(False)
        self.apply_review_filter_btn.setEnabled(False)
        self.preview_rows = []
        self.all_recorded_rows = []
        self.y_ranges = {}
        self.selection_regions = {}

        self.recording_start_wall_time = None
        self.recording_elapsed_final = 0
        self.update_elapsed_timer()

        for curve in self.preview_curves.values():
            curve.setData([], [])

        self.update_empty_plot_ranges()

        self.selection_box.setText("Selection Analysis: Recording discarded.")
        self.integrity_box.setText("Integrity Summary: Recording discarded.")

        self.set_mode_label("Mode: Idle")

    def recording_error_handler(self, error):
        self.stop_edge_scroll_selection()

        self.is_recording = False
        self.is_paused = False

        self.play_btn.setEnabled(True)
        self.play_btn.setText("▶")
        self.play_btn.setToolTip("Start recording")
        self.stop_btn.setEnabled(False)
        self.keep_btn.setEnabled(False)
        self.discard_btn.setEnabled(False)
        self.apply_review_filter_btn.setEnabled(False)

        self.review_mode = False
        self.saved_review_visible = False
        self.recording_start_wall_time = None

        self.log("Recording error:")
        self.log(error)

        self.selection_box.setText("Selection Analysis: Not available because recording failed.")
        self.integrity_box.setText(
            "Integrity Summary\n"
            "Status: ERROR\n"
            f"Error: {error}"
        )

        bg = "#ffffff" if self.is_light_theme else "#1e1e1e"
        color = "#aa0000" if self.is_light_theme else "#ff8080"
        self.integrity_box.setStyleSheet(f"background-color: {bg}; color: {color};")

        self.set_mode_label("Mode: Error")
