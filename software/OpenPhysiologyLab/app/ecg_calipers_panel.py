# app/ecg_calipers_panel.py

import csv
from pathlib import Path

import numpy as np
import pyqtgraph as pg

from analysis.peak_detection import detect_ecg_r_peaks

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout,
    QGroupBox, QTextEdit, QFileDialog, QComboBox, QCheckBox, QSplitter, QScrollBar
)
from PyQt5.QtCore import Qt, QTimer


class ECGCalipersPanel(QWidget):
    """
    ECG Calipers tab.

    Stage 2:
    - Load raw.csv directly
    - Choose channel
    - Show raw or filtered ECG view
    - Keep raw.csv untouched
    - No manual caliper markers yet
    """

    def __init__(self):
        super().__init__()

        self.setWindowTitle("OpenPhysiologyLab ECG Calipers")

        self.current_csv_path = None
        self.current_columns = []
        self.current_rows = []
        self.current_time_s = None
        self.current_channel_data = {}
        self.current_display_y = None
        self.current_display_label = "Raw"
        self.current_plot_t = None
        self.current_plot_y = None
        self.default_view_seconds = 5.0

        self.detected_r_peaks = np.array([], dtype=int)
        self.r_peak_detection_result = None
        self.selected_peak_number = None

        self.baseline_value = None
        self.baseline_set_mode = False
        self.baseline_line = None

        self.landmark_mode = None
        self.landmarks = {}

        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        title = QLabel("OpenPhysiologyLab ECG Calipers Panel")
        title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        title.setStyleSheet("font-size: 13px; font-weight: bold;")
        title.setMaximumHeight(22)
        layout.addWidget(title)

        subtitle = QLabel(
            "ECG Calipers tab = beat-wise waveform measurement. "
            "Load a recording, detect R peaks, set baseline, then place manual landmarks."
        )
        subtitle.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        subtitle.setWordWrap(True)
        subtitle.setMaximumHeight(24)
        layout.addWidget(subtitle)

        def make_caliper_group(title_text):
            group = QGroupBox(title_text)
            group.setMaximumHeight(72)
            group_layout = QHBoxLayout(group)
            group_layout.setContentsMargins(8, 4, 8, 4)
            group_layout.setSpacing(6)
            return group, group_layout

        # Ribbon row 1: source, display, and R reference.
        ribbon_row_1 = QHBoxLayout()
        ribbon_row_1.setSpacing(8)

        source_group, source_layout = make_caliper_group("Source")

        self.use_latest_btn = QPushButton("Use Latest")
        self.load_folder_btn = QPushButton("Load Folder")
        self.load_raw_btn = QPushButton("Load raw.csv")

        self.use_latest_btn.setToolTip("Planned: load the most recent recording from Recorder.")
        self.load_folder_btn.setToolTip("Planned: load a saved OPL recording folder.")
        self.load_raw_btn.setToolTip("Load a raw.csv file directly.")

        self.use_latest_btn.clicked.connect(self.show_planned_latest_recording)
        self.load_folder_btn.clicked.connect(self.show_planned_recording_folder)
        self.load_raw_btn.clicked.connect(self.load_raw_csv_clicked)

        source_layout.addWidget(self.use_latest_btn)
        source_layout.addWidget(self.load_folder_btn)
        source_layout.addWidget(self.load_raw_btn)

        view_group, controls_layout = make_caliper_group("Display")

        controls_layout.addWidget(QLabel("Ch"))
        self.channel_box = QComboBox()
        self.channel_box.setMinimumWidth(65)
        self.channel_box.currentIndexChanged.connect(self.refresh_plot)
        controls_layout.addWidget(self.channel_box)

        controls_layout.addWidget(QLabel("View"))
        self.view_box = QComboBox()
        self.view_box.setMinimumWidth(150)
        self.view_box.addItems(["Raw", "Filtered ECG 0.5-40 Hz"])
        self.view_box.currentIndexChanged.connect(self.refresh_plot)
        controls_layout.addWidget(self.view_box)

        self.notch_box = QCheckBox("50 Hz")
        self.notch_box.setChecked(True)
        self.notch_box.stateChanged.connect(self.refresh_plot)
        controls_layout.addWidget(self.notch_box)

        self.reset_view_btn = QPushButton("Reset")
        self.reset_view_btn.clicked.connect(self.reset_plot_view)
        controls_layout.addWidget(self.reset_view_btn)

        rpeak_group, rpeak_layout = make_caliper_group("R Reference")

        self.detect_r_btn = QPushButton("Detect R")
        self.detect_r_btn.setToolTip(
            "Use the same ECG R-peak detector used by Analysis as the internal beat reference."
        )
        self.detect_r_btn.clicked.connect(self.detect_r_peaks_clicked)

        self.prev_beat_btn = QPushButton("<")
        self.prev_beat_btn.setToolTip("Previous detected R peak")
        self.prev_beat_btn.clicked.connect(self.previous_beat_clicked)

        self.next_beat_btn = QPushButton(">")
        self.next_beat_btn.setToolTip("Next detected R peak")
        self.next_beat_btn.clicked.connect(self.next_beat_clicked)

        self.rpeak_status_label = QLabel("R: --")
        self.rpeak_status_label.setWordWrap(False)

        rpeak_layout.addWidget(self.detect_r_btn)
        rpeak_layout.addWidget(self.prev_beat_btn)
        rpeak_layout.addWidget(self.next_beat_btn)
        rpeak_layout.addWidget(self.rpeak_status_label, stretch=1)

        ribbon_row_1.addWidget(source_group, stretch=3)
        ribbon_row_1.addWidget(view_group, stretch=3)
        ribbon_row_1.addWidget(rpeak_group, stretch=3)

        layout.addLayout(ribbon_row_1)

        # Ribbon row 2: baseline and current manual landmarks.
        ribbon_row_2 = QHBoxLayout()
        ribbon_row_2.setSpacing(8)

        baseline_group, baseline_layout = make_caliper_group("Baseline")

        self.set_baseline_btn = QPushButton("Set")
        self.set_baseline_btn.setToolTip(
            "Click this, then click the isoelectric baseline on the ECG plot."
        )
        self.set_baseline_btn.clicked.connect(self.set_baseline_mode_clicked)

        self.clear_baseline_btn = QPushButton("Clear")
        self.clear_baseline_btn.clicked.connect(self.clear_baseline_clicked)

        self.baseline_status_label = QLabel("Baseline: --")
        self.baseline_status_label.setWordWrap(False)

        baseline_layout.addWidget(self.set_baseline_btn)
        baseline_layout.addWidget(self.clear_baseline_btn)
        baseline_layout.addWidget(self.baseline_status_label, stretch=1)

        landmark_group, landmark_layout = make_caliper_group("P Wave")

        self.p_onset_btn = QPushButton("P onset")
        self.p_peak_btn = QPushButton("P peak")
        self.p_offset_btn = QPushButton("P offset")
        self.clear_p_btn = QPushButton("Clear P")

        # New ECG Calipers controls use OPL green accents without changing the whole tab theme.
        green_button_style = (
            "QPushButton {"
            "border: 1px solid #00C853;"
            "color: #B9F6CA;"
            "padding: 4px 8px;"
            "}"
            "QPushButton:hover {"
            "background-color: rgba(0, 200, 83, 35);"
            "}"
        )
        for btn in [self.p_onset_btn, self.p_peak_btn, self.p_offset_btn, self.clear_p_btn]:
            btn.setStyleSheet(green_button_style)

        self.p_onset_btn.clicked.connect(lambda: self.set_landmark_mode("P onset"))
        self.p_peak_btn.clicked.connect(lambda: self.set_landmark_mode("P peak"))
        self.p_offset_btn.clicked.connect(lambda: self.set_landmark_mode("P offset"))
        self.clear_p_btn.clicked.connect(self.clear_p_landmarks)

        self.p_status_label = QLabel("P: --")
        self.p_status_label.setWordWrap(False)
        self.p_status_label.setStyleSheet("color: #B9F6CA;")

        landmark_layout.addWidget(self.p_onset_btn)
        landmark_layout.addWidget(self.p_peak_btn)
        landmark_layout.addWidget(self.p_offset_btn)
        landmark_layout.addWidget(self.clear_p_btn)
        landmark_layout.addWidget(self.p_status_label, stretch=1)

        ribbon_row_2.addWidget(baseline_group, stretch=3)
        ribbon_row_2.addWidget(landmark_group, stretch=6)

        layout.addLayout(ribbon_row_2)

        content_splitter = QSplitter(Qt.Horizontal)
        content_splitter.setChildrenCollapsible(False)

        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)

        view_group = QGroupBox("Signal View")
        view_layout = QVBoxLayout(view_group)
        view_layout.setContentsMargins(8, 8, 8, 8)

        self.plot = pg.PlotWidget()
        self.plot.setLabel("bottom", "Time", units="s")
        self.plot.setLabel("left", "Amplitude (raw ADC units; not mV)")
        self.plot.getAxis("left").enableAutoSIPrefix(False)
        self.plot.showGrid(x=True, y=True, alpha=0.25)
        self.plot.setBackground("#0B1020")
        self.plot.getPlotItem().setTitle("Load raw.csv to view ECG signal")

        # ECG Calipers navigation rule:
        # allow horizontal ECG browsing, but avoid accidental vertical/pinch runaway.
        self.plot.setMouseEnabled(x=True, y=False)
        self.plot.getPlotItem().getViewBox().setMenuEnabled(False)
        self.plot.scene().sigMouseClicked.connect(self.plot_clicked)

        view_layout.addWidget(self.plot, stretch=1)

        self.time_scroll = QScrollBar(Qt.Horizontal)
        self.time_scroll.setMinimum(0)
        self.time_scroll.setMaximum(10000)
        self.time_scroll.setSingleStep(20)
        self.time_scroll.setPageStep(500)
        self.time_scroll.valueChanged.connect(self.time_scroll_changed)
        self.time_scroll.setToolTip("Scroll through the recording while keeping the local morphology window.")
        view_layout.addWidget(self.time_scroll)

        left_layout.addWidget(view_group, stretch=1)

        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(4, 0, 0, 0)
        right_layout.setSpacing(6)

        summary_group = QGroupBox("Caliper Measurements")
        summary_layout = QVBoxLayout(summary_group)
        summary_layout.setContentsMargins(8, 6, 8, 6)

        self.summary_box = QTextEdit()
        self.summary_box.setReadOnly(True)
        self.summary_box.setMinimumWidth(320)
        self.summary_box.setText(
            "Caliper measurements will appear here.\n\n"
            "Load raw.csv, detect R peaks, set baseline, and place markers."
        )
        summary_layout.addWidget(self.summary_box)
        right_layout.addWidget(summary_group, stretch=2)

        info_group = QGroupBox("ECG Calipers Log")
        info_layout = QVBoxLayout(info_group)
        info_layout.setContentsMargins(8, 6, 8, 6)

        self.info_box = QTextEdit()
        self.info_box.setReadOnly(True)
        self.info_box.setMinimumHeight(90)
        self.info_box.setText(
            "ECG Calipers Stage 2\n\n"
            "Available now:\n"
            "1. Load raw.csv.\n"
            "2. Choose recorded channel.\n"
            "3. View raw ECG signal.\n"
            "4. View an in-memory filtered ECG signal.\n\n"
            "Not added yet:\n"
            "- selected beat context view\n"
            "- previous/selected/next PQRST display\n"
            "- manual QRS/T caliper markers\n"
            "- beat_measurements.csv export\n\n"
            "Safety: This is for education and experimentation, not diagnosis."
        )
        info_layout.addWidget(self.info_box)
        right_layout.addWidget(info_group, stretch=1)

        content_splitter.addWidget(left_container)
        content_splitter.addWidget(right_container)
        content_splitter.setSizes([1150, 360])

        layout.addWidget(content_splitter, stretch=10)

    def show_planned_latest_recording(self):
        self.info_box.setText(
            "Use Latest Recording is planned for the next workflow stage.\n\n"
            "For now, click Load raw.csv and choose a recorded OPL raw.csv file."
        )

    def show_planned_recording_folder(self):
        self.info_box.setText(
            "Load Recording Folder is planned for the next workflow stage.\n\n"
            "For now, click Load raw.csv and choose raw.csv inside a recording folder."
        )

    def load_raw_csv_clicked(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose raw.csv",
            "",
            "CSV files (*.csv);;All files (*.*)"
        )
        if not path:
            return

        try:
            self.load_raw_csv(path)
            self.refresh_plot()
        except Exception as e:
            self.info_box.setText(f"Could not load raw.csv:\n{e}")

    def load_raw_csv(self, path):
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(str(path))

        with path.open("r", newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            columns = reader.fieldnames or []

        if not rows:
            raise ValueError("CSV has no data rows.")

        self.current_csv_path = path
        self.current_columns = columns
        self.current_rows = rows

        self.current_time_s = self.extract_time_s(rows, columns)
        self.current_channel_data = self.extract_channels(rows, columns)
        self.detected_r_peaks = np.array([], dtype=int)
        self.r_peak_detection_result = None
        self.selected_peak_number = None
        self.rpeak_status_label.setText("R: --")

        self.baseline_value = None
        self.baseline_set_mode = False
        self.baseline_line = None
        self.baseline_status_label.setText(
            "Baseline: --"
        )

        self.landmark_mode = None
        self.landmarks = {}
        self.p_status_label.setText("P: --")

        if not self.current_channel_data:
            raise ValueError("No usable ch1/ch2/ch3/ch4/ch5/ch6 columns found.")

        self.channel_box.blockSignals(True)
        self.channel_box.clear()
        for ch in self.current_channel_data.keys():
            self.channel_box.addItem(ch)
        self.channel_box.blockSignals(False)

        duration = float(self.current_time_s[-1] - self.current_time_s[0])
        fs = self.estimate_fs(self.current_time_s)

        lines = [
            "raw.csv loaded successfully.",
            "",
            f"File: {path}",
            f"Rows: {len(rows)}",
            f"Channels detected: {', '.join(self.current_channel_data.keys())}",
            f"Duration: {duration:.3f} s",
            f"Estimated sampling rate: {fs:.2f} Hz",
            "",
            "The original raw.csv has not been modified.",
            "Filtered view is generated only in memory.",
            "",
            "Next development stage: selected beat context view with previous, selected, and next PQRST complexes."
        ]
        self.info_box.setText("\n".join(lines))
        self.update_measurement_summary()

    def extract_time_s(self, rows, columns):
        if "time_us" in columns:
            values = np.array([self.safe_float(row.get("time_us")) for row in rows], dtype=float)
            if np.isfinite(values).sum() > 2:
                start = values[np.isfinite(values)][0]
                return (values - start) / 1_000_000.0

        if "pc_time_s" in columns:
            values = np.array([self.safe_float(row.get("pc_time_s")) for row in rows], dtype=float)
            if np.isfinite(values).sum() > 2:
                start = values[np.isfinite(values)][0]
                return values - start

        if "sample" in columns:
            sample = np.array([self.safe_float(row.get("sample")) for row in rows], dtype=float)
            if np.isfinite(sample).sum() > 2:
                return sample - sample[0]

        return np.arange(len(rows), dtype=float)

    def extract_channels(self, rows, columns):
        channel_data = {}

        for ch in ["ch1", "ch2", "ch3", "ch4", "ch5", "ch6"]:
            if ch not in columns:
                continue

            values = np.array([self.safe_float(row.get(ch)) for row in rows], dtype=float)
            finite_count = int(np.isfinite(values).sum())

            if finite_count > 0:
                channel_data[ch] = values

        return channel_data

    def safe_float(self, value):
        try:
            if value is None:
                return np.nan
            value = str(value).strip()
            if value == "":
                return np.nan
            return float(value)
        except Exception:
            return np.nan

    def estimate_fs(self, t):
        t = np.asarray(t, dtype=float)
        t = t[np.isfinite(t)]
        if len(t) < 3:
            return 1.0

        dt = np.diff(t)
        dt = dt[np.isfinite(dt)]
        dt = dt[dt > 0]
        if len(dt) == 0:
            return 1.0

        median_dt = float(np.median(dt))

        if median_dt <= 0:
            return 1.0

        return 1.0 / median_dt





    def get_trace_color(self):
        label = str(getattr(self, "current_display_label", "")).lower()
        if label.startswith("raw"):
            return "#50C878"
        return "#FFC400"

    def get_y_axis_label(self):
        label = str(getattr(self, "current_display_label", "")).lower()
        if label.startswith("raw"):
            return "Amplitude (raw ADC units; not mV)"
        return "Filtered amplitude (ADC-count deviation; not mV)"

    def get_x_range_for_refresh(self):
        if self.current_plot_t is None:
            return None

        try:
            t = np.asarray(self.current_plot_t, dtype=float)
            t = t[np.isfinite(t)]
            if len(t) < 3:
                return None

            t_min = float(np.nanmin(t))
            t_max = float(np.nanmax(t))
            duration = max(t_max - t_min, 0.001)

            x_range, _ = self.plot.getPlotItem().getViewBox().viewRange()
            x0 = float(x_range[0])
            x1 = float(x_range[1])
            width = max(x1 - x0, 0.001)

            # If current view is near-full recording, switch back to morphology view.
            if width >= 0.85 * duration:
                return None

            if x1 < t_min or x0 > t_max:
                return None

            return [max(t_min, x0), min(t_max, x1)]

        except Exception:
            return None

    def set_view_window(self, center_time=None, window_s=None, update_scroll=True):
        if self.current_plot_t is None or self.current_plot_y is None:
            return

        t = np.asarray(self.current_plot_t, dtype=float)
        y = np.asarray(self.current_plot_y, dtype=float)

        valid = np.isfinite(t) & np.isfinite(y)
        if valid.sum() < 3:
            return

        t_valid = t[valid]
        y_valid = y[valid]

        t_min = float(np.nanmin(t_valid))
        t_max = float(np.nanmax(t_valid))
        duration = max(t_max - t_min, 0.001)

        if window_s is None:
            window_s = float(getattr(self, "current_window_seconds", getattr(self, "default_view_seconds", 5.0)))

        window_s = min(max(float(window_s), 0.2), duration)
        self.current_window_seconds = window_s

        if center_time is None:
            x0 = t_min
            x1 = min(t_max, t_min + window_s)
        else:
            center_time = float(center_time)
            x0 = center_time - window_s / 2.0
            x1 = center_time + window_s / 2.0

            if x0 < t_min:
                x1 += (t_min - x0)
                x0 = t_min
            if x1 > t_max:
                x0 -= (x1 - t_max)
                x1 = t_max

            x0 = max(t_min, x0)
            x1 = min(t_max, x1)

        visible = valid & (t >= x0) & (t <= x1)
        local_y = y[visible]
        local_y = local_y[np.isfinite(local_y)]

        if len(local_y) < 3:
            local_y = y_valid

        y_min = float(np.nanmin(local_y))
        y_max = float(np.nanmax(local_y))
        y_span = max(y_max - y_min, 1.0)
        y_pad = 0.10 * y_span

        self.plot.enableAutoRange(x=False, y=False)
        self.plot.setXRange(x0, x1, padding=0)
        self.plot.setYRange(y_min - y_pad, y_max + y_pad, padding=0)

        if update_scroll and hasattr(self, "time_scroll"):
            self.update_time_scrollbar(x0, x1)

    def update_time_scrollbar(self, x0, x1):
        if self.current_plot_t is None or not hasattr(self, "time_scroll"):
            return

        t = np.asarray(self.current_plot_t, dtype=float)
        t = t[np.isfinite(t)]
        if len(t) < 3:
            return

        t_min = float(np.nanmin(t))
        t_max = float(np.nanmax(t))
        duration = max(t_max - t_min, 0.001)
        window_s = max(float(x1) - float(x0), 0.001)
        max_start = max(duration - window_s, 0.001)

        value = int(round(((float(x0) - t_min) / max_start) * 10000.0))
        value = max(0, min(10000, value))

        self.updating_scrollbar = True
        try:
            self.time_scroll.setValue(value)
        finally:
            self.updating_scrollbar = False

    def time_scroll_changed(self, value):
        if getattr(self, "updating_scrollbar", False):
            return

        if self.current_plot_t is None:
            return

        t = np.asarray(self.current_plot_t, dtype=float)
        t = t[np.isfinite(t)]
        if len(t) < 3:
            return

        t_min = float(np.nanmin(t))
        t_max = float(np.nanmax(t))
        duration = max(t_max - t_min, 0.001)

        window_s = min(
            float(getattr(self, "current_window_seconds", getattr(self, "default_view_seconds", 5.0))),
            duration
        )
        max_start = max(duration - window_s, 0.001)

        x0 = t_min + (float(value) / 10000.0) * max_start
        center_time = x0 + window_s / 2.0
        self.set_view_window(center_time=center_time, window_s=window_s, update_scroll=False)

    def center_view_on_selected_peak(self):
        if self.current_plot_t is None or len(self.detected_r_peaks) == 0:
            return

        if self.selected_peak_number is None:
            return

        t = np.asarray(self.current_plot_t, dtype=float)
        peaks = np.asarray(self.detected_r_peaks, dtype=int)
        n = int(self.selected_peak_number)

        if n < 0 or n >= len(peaks):
            return

        idx = int(peaks[n])
        if idx < 0 or idx >= len(t):
            return

        self.set_view_window(
            center_time=float(t[idx]),
            window_s=getattr(self, "default_view_seconds", 5.0)
        )

    def apply_post_refresh_window(self, previous_x_range=None):
        if self.current_plot_t is None or self.current_plot_y is None:
            return

        try:
            self.plot.setLabel("left", self.get_y_axis_label())
            self.plot.enableAutoRange(x=False, y=False)

            if previous_x_range is not None:
                x0, x1 = previous_x_range
                center = (float(x0) + float(x1)) / 2.0
                window_s = max(float(x1) - float(x0), 0.2)
                self.set_view_window(center_time=center, window_s=window_s)
                QTimer.singleShot(0, lambda: self.set_view_window(center_time=center, window_s=window_s))
            else:
                self.set_view_window(center_time=None, window_s=getattr(self, "default_view_seconds", 5.0))
                QTimer.singleShot(0, lambda: self.set_view_window(center_time=None, window_s=getattr(self, "default_view_seconds", 5.0)))

        except Exception as e:
            try:
                self.info_box.setText(f"Could not apply local ECG view:\n{e}")
            except Exception:
                pass

    def refresh_plot(self):
        old_x_range = self.get_x_range_for_refresh()
        if self.current_time_s is None or not self.current_channel_data:
            return

        ch = self.channel_box.currentText()
        if not ch or ch not in self.current_channel_data:
            return

        t = np.asarray(self.current_time_s, dtype=float)
        y_raw = np.asarray(self.current_channel_data[ch], dtype=float)

        valid = np.isfinite(t) & np.isfinite(y_raw)
        if valid.sum() < 3:
            self.info_box.setText(f"No valid samples in {ch}.")
            return

        t = t[valid]
        y_raw = y_raw[valid]

        view = self.view_box.currentText()
        if view.startswith("Filtered"):
            y = self.make_filtered_ecg(t, y_raw, notch=self.notch_box.isChecked())
            self.current_display_label = view
        else:
            y = y_raw
            self.current_display_label = "Raw"

        self.current_display_y = y
        self.current_plot_t = t
        self.current_plot_y = y

        # Channel/filter changes invalidate previous peak indices and baseline until redetected/reset.
        self.detected_r_peaks = np.array([], dtype=int)
        self.r_peak_detection_result = None
        self.selected_peak_number = None
        self.rpeak_status_label.setText("R: --")

        self.baseline_value = None
        self.baseline_set_mode = False
        self.baseline_line = None
        self.baseline_status_label.setText(
            "Baseline: --"
        )

        self.landmark_mode = None
        self.landmarks = {}
        self.p_status_label.setText("P: --")

        self.plot.clear()
        self.plot.plot(t, y, pen=pg.mkPen(self.get_trace_color(), width=1))
        self.draw_baseline_line()
        self.draw_landmark_markers()
        self.plot.setLabel("bottom", "Time", units="s")
        self.plot.setLabel("left", "Amplitude (raw ADC units; not mV)")
        self.plot.getAxis("left").enableAutoSIPrefix(False)
        self.plot.getPlotItem().setTitle(f"ECG Calipers: {ch} | {self.current_display_label}")

        duration = float(t[-1] - t[0])
        fs = self.estimate_fs(t)
        y_min = float(np.nanmin(y))
        y_max = float(np.nanmax(y))

        self.apply_timebase_limits(t, y, set_full_view=False)


        self.info_box.setText(
            f"Displaying {ch} from:\n{self.current_csv_path}\n\n"
            f"View: {self.current_display_label}\n"
            f"50 Hz notch: {self.notch_box.isChecked()}\n"
            f"Samples displayed: {len(t)}\n"
            f"Duration: {duration:.3f} s\n"
            f"Estimated sampling rate: {fs:.2f} Hz\n"
            f"Displayed range: {y_min:.3f} to {y_max:.3f} raw units\n\n"
            "The original raw.csv has not been modified.\n\n"
            "Next development stage: selected beat context view with previous, selected, and next PQRST complexes."
        )
        self.apply_post_refresh_window(old_x_range)

    def detect_r_peaks_clicked(self):
        # Detect R peaks on the currently displayed signal using the shared
        # Analysis ECG detector. This gives ECG Calipers the same internal
        # R-peak reference as the Analysis/HRV workflow.
        if self.current_plot_t is None or self.current_plot_y is None:
            self.info_box.setText("Load raw.csv and display a channel before detecting R peaks.")
            return

        t = np.asarray(self.current_plot_t, dtype=float)
        y = np.asarray(self.current_plot_y, dtype=float)

        valid = np.isfinite(t) & np.isfinite(y)
        if valid.sum() < 10:
            self.info_box.setText("Not enough valid samples for R peak detection.")
            return

        t = t[valid]
        y = y[valid]

        fs = self.estimate_fs(t)

        try:
            result = detect_ecg_r_peaks(
                t,
                y,
                fs,
                forced_polarity="auto"
            )
        except Exception as e:
            self.info_box.setText(f"R peak detection failed:\n{e}")
            return

        peaks = np.asarray(result.get("peaks", []), dtype=int)

        self.r_peak_detection_result = result
        self.detected_r_peaks = peaks

        if len(peaks) == 0:
            warning = result.get("warning") or "No R peaks detected."
            self.rpeak_status_label.setText("R: 0")
            self.info_box.setText(
                "R peak detection completed, but no R peaks were found.\n\n"
                f"Polarity: {result.get('polarity')}\n"
                f"Polarity source: {result.get('polarity_source')}\n"
                f"Warning: {warning}"
            )
            self.redraw_plot_with_r_peaks()
            return

        self.selected_peak_number = 0
        self.redraw_plot_with_r_peaks(preserve_view=False)
        self.center_view_on_selected_peak()

        rr = np.diff(t[peaks]) if len(peaks) >= 2 else np.asarray([], dtype=float)
        mean_hr = 60.0 / float(np.nanmean(rr)) if len(rr) > 0 and np.nanmean(rr) > 0 else np.nan

        self.rpeak_status_label.setText(
            f"R: {len(peaks)} | beat 1/{len(peaks)}"
        )
        self.update_measurement_summary()

        self.info_box.setText(
            "R peaks detected using shared Analysis ECG detector.\n\n"
            f"Peaks detected: {len(peaks)}\n"
            f"Polarity: {result.get('polarity')}\n"
            f"Polarity source: {result.get('polarity_source')}\n"
            f"Estimated sampling rate: {fs:.2f} Hz\n"
            f"Mean HR from detected RR: {mean_hr:.1f} bpm\n\n"
            f"{self.selected_beat_context_text()}\n\n"
            "R peaks are the internal reference for ECG Calipers. "
            "Manual P/Q/S/J/T markers will be added later. You can click near any green R peak to select that beat."
        )

    def redraw_plot_with_r_peaks(self, preserve_view=True):
        if self.current_plot_t is None or self.current_plot_y is None:
            return

        t = np.asarray(self.current_plot_t, dtype=float)
        y = np.asarray(self.current_plot_y, dtype=float)

        view_box = self.plot.getPlotItem().getViewBox()
        old_x_range = None
        old_y_range = None

        if preserve_view:
            try:
                old_x_range, old_y_range = view_box.viewRange()
                old_x_range = [float(old_x_range[0]), float(old_x_range[1])]
                old_y_range = [float(old_y_range[0]), float(old_y_range[1])]
            except Exception:
                old_x_range = None
                old_y_range = None

        self.plot.clear()
        self.plot.plot(t, y, pen=pg.mkPen(self.get_trace_color(), width=1))
        self.draw_baseline_line()
        self.draw_landmark_markers()

        peaks = np.asarray(self.detected_r_peaks, dtype=int)
        valid_peaks = peaks[(peaks >= 0) & (peaks < len(t))]

        if len(valid_peaks) > 0:
            self.plot.plot(
                t[valid_peaks],
                y[valid_peaks],
                pen=None,
                symbol="o",
                symbolSize=7,
                symbolBrush=pg.mkBrush("#00E676"),
                symbolPen=pg.mkPen("#00E676"),
                name="R peaks"
            )

        if self.selected_peak_number is not None and len(valid_peaks) > 0:
            n = int(self.selected_peak_number)
            if 0 <= n < len(valid_peaks):
                idx = valid_peaks[n]
                self.plot.plot(
                    [t[idx]],
                    [y[idx]],
                    pen=None,
                    symbol="o",
                    symbolSize=13,
                    symbolBrush=pg.mkBrush("#B388FF"),
                    symbolPen=pg.mkPen("#E1BEE7", width=1),
                    name="Selected R"
                )

        self.plot.getPlotItem().setTitle(
            f"ECG Calipers: {self.channel_box.currentText()} | {self.current_display_label}"
        )

        # Keep hard navigation limits, but do not force full-recording view
        # when the user has already zoomed into a beat.
        self.apply_timebase_limits(t, y, set_full_view=False)

        if preserve_view and old_x_range is not None and old_y_range is not None:
            try:
                self.plot.setXRange(old_x_range[0], old_x_range[1], padding=0)
                self.plot.setYRange(old_y_range[0], old_y_range[1], padding=0)
            except Exception:
                pass

    def update_measurement_summary(self):
        if not hasattr(self, "summary_box"):
            return

        lines = ["ECG Calipers Measurements", ""]

        if self.current_csv_path is not None:
            lines.append(f"File: {self.current_csv_path.name}")
            lines.append(f"Channel: {self.channel_box.currentText()}")
            lines.append(f"View: {self.current_display_label}")
            lines.append("")

        if len(self.detected_r_peaks) > 0:
            lines.append(f"R peaks detected: {len(self.detected_r_peaks)}")
            if self.selected_peak_number is not None:
                lines.append(self.selected_beat_context_text())
            lines.append("")
        else:
            lines.append("R: --")
            lines.append("")

        if self.baseline_value is not None:
            lines.append(f"Baseline: {float(self.baseline_value):.4f} raw units")
        else:
            lines.append("Baseline: not set")
        lines.append("")

        onset = self.landmarks.get("P onset")
        peak = self.landmarks.get("P peak")
        offset = self.landmarks.get("P offset")

        lines.append("P-wave calipers")
        lines.append(f"P onset: {onset['time_s']:.4f} s" if onset else "P onset: --")
        lines.append(f"P peak: {peak['time_s']:.4f} s" if peak else "P peak: --")
        lines.append(f"P offset: {offset['time_s']:.4f} s" if offset else "P offset: --")

        if onset and offset:
            p_duration_ms = (float(offset["time_s"]) - float(onset["time_s"])) * 1000.0
            lines.append(f"P duration: {p_duration_ms:.1f} ms")

        if peak and self.baseline_value is not None:
            p_amp = float(peak["value"]) - float(self.baseline_value)
            lines.append(f"P amplitude from baseline: {p_amp:.4f} raw units")
        elif peak:
            lines.append("P amplitude: set baseline first")

        self.summary_box.setText("\n".join(lines))

    def set_landmark_mode(self, name):
        if self.current_plot_t is None or self.current_plot_y is None:
            self.info_box.setText("Load raw.csv and display a signal before placing landmarks.")
            return

        self.landmark_mode = name
        self.baseline_set_mode = False
        self.p_status_label.setText(f"{name}: click on the ECG trace")
        self.info_box.setText(
            f"{name} placement mode active.\n\n"
            "Click the appropriate point on the ECG trace.\n"
            "New P-wave caliper controls are shown in OPL green."
        )

    def clear_p_landmarks(self):
        for key in ["P onset", "P peak", "P offset"]:
            self.landmarks.pop(key, None)

        self.landmark_mode = None
        self.p_status_label.setText("P: cleared")

        if self.current_plot_t is not None and self.current_plot_y is not None:
            self.redraw_plot_with_r_peaks()

        self.info_box.setText("P-wave landmarks cleared.")

    def draw_landmark_markers(self):
        if not self.landmarks:
            return

        marker_items = [
            ("P onset", "t1"),
            ("P peak", "o"),
            ("P offset", "t1"),
        ]

        for name, symbol in marker_items:
            point = self.landmarks.get(name)
            if not point:
                continue

            try:
                x = float(point["time_s"])
                y = float(point["value"])
            except Exception:
                continue

            self.plot.plot(
                [x],
                [y],
                pen=None,
                symbol=symbol,
                symbolSize=12,
                symbolBrush=pg.mkBrush("#00C853"),
                symbolPen=pg.mkPen("#B9F6CA", width=1),
                name=name
            )

            label = pg.TextItem(
                text=name,
                color="#B9F6CA",
                anchor=(0.5, 1.2)
            )
            label.setPos(x, y)
            self.plot.addItem(label)

    def update_p_measurements_status(self):
        onset = self.landmarks.get("P onset")
        peak = self.landmarks.get("P peak")
        offset = self.landmarks.get("P offset")

        if onset and peak and offset:
            p_duration_ms = (float(offset["time_s"]) - float(onset["time_s"])) * 1000.0
            if self.baseline_value is not None:
                p_amp = float(peak["value"]) - float(self.baseline_value)
                self.p_status_label.setText(f"P: {p_duration_ms:.1f} ms | {p_amp:.3f} raw")
            else:
                self.p_status_label.setText(f"P: {p_duration_ms:.1f} ms | set baseline")
        else:
            count = sum(bool(self.landmarks.get(k)) for k in ["P onset", "P peak", "P offset"])
            if count == 0:
                self.p_status_label.setText("P: --")
            else:
                self.p_status_label.setText(f"P: {count}/3 set")

        self.update_measurement_summary()

    def set_baseline_mode_clicked(self):
        if self.current_plot_t is None or self.current_plot_y is None:
            self.info_box.setText("Load raw.csv and display a signal before setting baseline.")
            return

        self.baseline_set_mode = True
        self.baseline_status_label.setText(
            "Baseline: click trace"
        )
        self.info_box.setText(
            "Baseline set mode active.\n\n"
            "Click a flat isoelectric part of the ECG trace, preferably the TP segment or PR segment.\n\n"
            "This baseline will be used as the reference for future amplitude measurements."
        )

    def clear_baseline_clicked(self):
        self.baseline_value = None
        self.baseline_set_mode = False
        self.baseline_line = None
        self.baseline_status_label.setText(
            "Baseline: --"
        )

        if self.current_plot_t is not None and self.current_plot_y is not None:
            self.redraw_plot_with_r_peaks()

        self.info_box.setText(
            "Baseline reference cleared.\n\n"
            "Set a baseline before interpreting P, R, T amplitudes or ST level."
        )
        self.update_measurement_summary()

    def draw_baseline_line(self):
        if self.baseline_value is None:
            self.baseline_line = None
            return

        try:
            line = pg.InfiniteLine(
                pos=float(self.baseline_value),
                angle=0,
                movable=True,
                pen=pg.mkPen("#40C4FF", width=2, style=Qt.DashLine)
            )
            line.setZValue(20)
            line.sigPositionChanged.connect(self.baseline_line_moved)
            self.plot.addItem(line)
            self.baseline_line = line
        except Exception:
            self.baseline_line = None

    def baseline_line_moved(self):
        if self.baseline_line is None:
            return

        try:
            value = float(self.baseline_line.value())
        except Exception:
            return

        self.baseline_value = value
        self.baseline_status_label.setText(
            f"Baseline: {value:.4f} raw"
        )
        self.update_p_measurements_status()

    def plot_clicked(self, event):
        """
        Plot click behavior:
        - If baseline-set mode is active, click sets the isoelectric baseline.
        - Otherwise, click near any detected R peak to select the nearest beat.

        The automatic R peaks remain the internal reference; the click only
        chooses which detected beat is selected.
        """
        if self.current_plot_t is None or self.current_plot_y is None:
            return

        try:
            scene_pos = event.scenePos()
            view_box = self.plot.getPlotItem().getViewBox()

            if not view_box.sceneBoundingRect().contains(scene_pos):
                return

            mouse_point = view_box.mapSceneToView(scene_pos)
            clicked_time = float(mouse_point.x())
            clicked_y = float(mouse_point.y())

            if self.baseline_set_mode:
                self.baseline_value = clicked_y
                self.baseline_set_mode = False
                self.baseline_status_label.setText(
                    f"Baseline: {clicked_y:.4f} raw"
                )
                self.redraw_plot_with_r_peaks()
                self.info_box.setText(
                    "Baseline reference set.\n\n"
                    f"Baseline value: {clicked_y:.4f} raw units\n\n"
                    "Teaching note: ECG positivity is relative to this isoelectric baseline, not necessarily the plot's y-axis zero."
                )
                self.update_measurement_summary()
                event.accept()
                return

            if self.landmark_mode:
                self.landmarks[self.landmark_mode] = {
                    "time_s": clicked_time,
                    "value": clicked_y,
                }
                mode = self.landmark_mode
                self.landmark_mode = None

                self.redraw_plot_with_r_peaks()
                self.update_p_measurements_status()

                self.info_box.setText(
                    f"{mode} marker set.\n\n"
                    f"Time: {clicked_time:.4f} s\n"
                    f"Value: {clicked_y:.4f} raw units\n\n"
                    "P-wave measurements use the selected baseline for amplitude."
                )
                self.update_measurement_summary()
                event.accept()
                return

            if len(self.detected_r_peaks) == 0:
                return

            t = np.asarray(self.current_plot_t, dtype=float)
            peaks = np.asarray(self.detected_r_peaks, dtype=int)
            valid_peaks = peaks[(peaks >= 0) & (peaks < len(t))]

            if len(valid_peaks) == 0:
                return

            peak_times = t[valid_peaks]
            nearest = int(np.nanargmin(np.abs(peak_times - clicked_time)))

            # Store index in the same order used by detected_r_peaks.
            self.selected_peak_number = nearest

            self.redraw_plot_with_r_peaks(preserve_view=False)
            self.center_view_on_selected_peak()
            self.update_selected_beat_status()

            event.accept()

        except Exception as e:
            self.info_box.setText(f"Could not select nearest R peak:\n{e}")

    def previous_beat_clicked(self):
        if len(self.detected_r_peaks) == 0:
            self.info_box.setText("Detect R peaks first.")
            return

        if self.selected_peak_number is None:
            self.selected_peak_number = 0
        else:
            self.selected_peak_number = max(0, int(self.selected_peak_number) - 1)

        self.redraw_plot_with_r_peaks(preserve_view=False)
        self.center_view_on_selected_peak()
        self.update_selected_beat_status()

    def next_beat_clicked(self):
        if len(self.detected_r_peaks) == 0:
            self.info_box.setText("Detect R peaks first.")
            return

        if self.selected_peak_number is None:
            self.selected_peak_number = 0
        else:
            self.selected_peak_number = min(
                len(self.detected_r_peaks) - 1,
                int(self.selected_peak_number) + 1
            )

        self.redraw_plot_with_r_peaks(preserve_view=False)
        self.center_view_on_selected_peak()
        self.update_selected_beat_status()

    def update_selected_beat_status(self):
        if len(self.detected_r_peaks) == 0 or self.selected_peak_number is None:
            self.rpeak_status_label.setText("R: --")
            return

        self.rpeak_status_label.setText(
            f"R: {len(self.detected_r_peaks)} | "
            f"beat {int(self.selected_peak_number) + 1}/{len(self.detected_r_peaks)}"
        )

        self.info_box.setText(
            "Selected R peak updated.\n\n"
            f"{self.selected_beat_context_text()}\n\n"
            "Click near any green R peak to select it. Next stage: zoom the display to previous-selected-next ECG complexes."
        )
        self.update_measurement_summary()

    def selected_beat_context_text(self):
        if self.current_plot_t is None:
            return "No signal loaded."

        if len(self.detected_r_peaks) == 0 or self.selected_peak_number is None:
            return "No selected beat."

        t = np.asarray(self.current_plot_t, dtype=float)
        peaks = np.asarray(self.detected_r_peaks, dtype=int)
        n = int(self.selected_peak_number)

        if n < 0 or n >= len(peaks):
            return "Selected beat index is out of range."

        selected_idx = int(peaks[n])
        selected_t = float(t[selected_idx])

        lines = [
            f"Selected beat: {n + 1}/{len(peaks)}",
            f"Selected R time: {selected_t:.3f} s",
        ]

        if n > 0:
            prev_t = float(t[int(peaks[n - 1])])
            pre_rr_ms = (selected_t - prev_t) * 1000.0
            lines.append(f"Previous R time: {prev_t:.3f} s")
            lines.append(f"pre-RR interval: {pre_rr_ms:.1f} ms")
        else:
            lines.append("Previous R time: not available")
            lines.append("pre-RR interval: not available")

        if n < len(peaks) - 1:
            next_t = float(t[int(peaks[n + 1])])
            post_rr_ms = (next_t - selected_t) * 1000.0
            lines.append(f"Next R time: {next_t:.3f} s")
            lines.append(f"post-RR interval: {post_rr_ms:.1f} ms")
        else:
            lines.append("Next R time: not available")
            lines.append("post-RR interval: not available")

        return "\n".join(lines)

    def make_filtered_ecg(self, t, y, notch=True):
        try:
            from scipy.signal import butter, filtfilt, iirnotch
        except Exception:
            self.info_box.setText(
                "scipy is not available, so filtered view cannot be generated.\n"
                "Showing raw signal instead."
            )
            return y

        fs = self.estimate_fs(t)
        if fs < 100:
            return y

        y_work = np.asarray(y, dtype=float)

        finite = np.isfinite(y_work)
        if finite.sum() < 3:
            return y_work

        if not finite.all():
            x = np.arange(len(y_work))
            y_work = np.interp(x, x[finite], y_work[finite])

        y_work = y_work - np.nanmedian(y_work)

        nyq = fs / 2.0
        low = 0.5 / nyq
        high = 40.0 / nyq

        if not (0 < low < high < 1):
            return y_work

        b, a = butter(4, [low, high], btype="bandpass")
        y_filt = filtfilt(b, a, y_work)

        if notch and fs > 120:
            w0 = 50.0 / nyq
            if 0 < w0 < 1:
                b_notch, a_notch = iirnotch(w0, 30.0)
                y_filt = filtfilt(b_notch, a_notch, y_filt)

        return y_filt



    def apply_timebase_limits(self, t, y, set_full_view=True):
        t = np.asarray(t, dtype=float)
        y = np.asarray(y, dtype=float)

        valid = np.isfinite(t) & np.isfinite(y)
        if valid.sum() < 3:
            return

        t_valid = t[valid]
        y_valid = y[valid]

        t_min = float(np.nanmin(t_valid))
        t_max = float(np.nanmax(t_valid))
        y_min = float(np.nanmin(y_valid))
        y_max = float(np.nanmax(y_valid))
        y_span = max(y_max - y_min, 1.0)
        y_pad = 0.20 * y_span

        view_box = self.plot.getPlotItem().getViewBox()
        view_box.setLimits(
            xMin=t_min,
            xMax=t_max,
            minXRange=0.05,
            maxXRange=max(t_max - t_min, 0.05),
            yMin=y_min - y_pad,
            yMax=y_max + y_pad
        )

        if set_full_view:
            self.set_view_window(center_time=None, window_s=getattr(self, "default_view_seconds", 5.0))

    def reset_plot_view(self):
        if self.current_plot_t is not None and self.current_plot_y is not None:
            self.apply_timebase_limits(self.current_plot_t, self.current_plot_y, set_full_view=True)
        else:
            self.plot.enableAutoRange()
