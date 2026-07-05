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
        self.current_template_overlay_y = None
        self.default_view_seconds = 5.0

        self.detected_r_peaks = np.array([], dtype=int)
        self.r_peak_detection_result = None
        self.selected_peak_number = None

        self.baseline_value = None
        self.save_current_baseline_to_view()
        self.baseline_set_mode = False
        self.baseline_line = None

        self.landmark_mode = None
        self.landmarks = {}

        # Marker/baseline sets are independent per view.
        # The teaching template is deliberately separate from raw/filtered measurements.
        self.marker_sets = {
            "raw": {},
            "filtered": {},
            "template": {},
        }
        self.baseline_sets = {
            "raw": None,
            "filtered": None,
            "template": 0.0,
        }

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
        self.view_box.addItems(["Raw", "Filtered ECG 0.5-40 Hz", "Teaching Template ECG"])
        self.view_box.currentIndexChanged.connect(self.refresh_plot)
        controls_layout.addWidget(self.view_box)

        self.notch_box = QCheckBox("50 Hz")
        self.notch_box.setChecked(True)
        self.notch_box.stateChanged.connect(self.refresh_plot)
        controls_layout.addWidget(self.notch_box)

        self.template_overlay_box = QCheckBox("Overlay filtered")
        self.template_overlay_box.setChecked(False)
        self.template_overlay_box.setToolTip(
            "In Teaching Template ECG view, overlay the filtered ECG behind the template."
        )
        self.template_overlay_box.stateChanged.connect(self.refresh_plot)
        controls_layout.addWidget(self.template_overlay_box)

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

        qrs_group, qrs_layout = make_caliper_group("QRS / ST")

        self.qrs_onset_btn = QPushButton("QRS onset")
        self.q_nadir_btn = QPushButton("Q nadir")
        self.s_nadir_btn = QPushButton("S nadir")
        self.j_point_btn = QPushButton("J point")
        self.clear_qrs_btn = QPushButton("Clear QRS")

        qrs_button_style = (
            "QPushButton {"
            "border: 1px solid #00C853;"
            "color: #B9F6CA;"
            "padding: 4px 8px;"
            "}"
            "QPushButton:hover {"
            "background-color: rgba(0, 200, 83, 35);"
            "}"
        )
        for btn in [self.qrs_onset_btn, self.q_nadir_btn, self.s_nadir_btn, self.j_point_btn, self.clear_qrs_btn]:
            btn.setStyleSheet(qrs_button_style)

        self.qrs_onset_btn.clicked.connect(lambda: self.set_landmark_mode("QRS onset"))
        self.q_nadir_btn.clicked.connect(lambda: self.set_landmark_mode("Q nadir"))
        self.s_nadir_btn.clicked.connect(lambda: self.set_landmark_mode("S nadir"))
        self.j_point_btn.clicked.connect(lambda: self.set_landmark_mode("J point"))
        self.clear_qrs_btn.clicked.connect(self.clear_qrs_landmarks)

        self.qrs_status_label = QLabel("QRS: --")
        self.qrs_status_label.setWordWrap(False)
        self.qrs_status_label.setStyleSheet("color: #B9F6CA;")

        qrs_layout.addWidget(self.qrs_onset_btn)
        qrs_layout.addWidget(self.q_nadir_btn)
        qrs_layout.addWidget(self.s_nadir_btn)
        qrs_layout.addWidget(self.j_point_btn)
        qrs_layout.addWidget(self.clear_qrs_btn)
        qrs_layout.addWidget(self.qrs_status_label, stretch=1)

        ribbon_row_2.addWidget(baseline_group, stretch=2)
        ribbon_row_2.addWidget(landmark_group, stretch=4)
        ribbon_row_2.addWidget(qrs_group, stretch=5)

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
        self.reset_all_view_measurements()
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
            return "#50C878"  # emerald green for raw ADC
        if label.startswith("teaching"):
            return "#B9F6CA"  # pale OPL green for teaching template
        return "#FFC400"      # gold for filtered ECG


    def get_y_axis_label(self):
        label = str(getattr(self, "current_display_label", "")).lower()
        if label.startswith("raw"):
            return "Amplitude (raw ADC units; not mV)"
        if label.startswith("teaching"):
            return "Derived teaching template (filtered ADC-count deviation; not mV)"
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

        key = self.get_active_view_key()
        if key == "template" and hasattr(self, "template_overlay_box") and self.template_overlay_box.isChecked():
            overlay_y = getattr(self, "current_template_overlay_y", None)
            if overlay_y is not None:
                try:
                    overlay_y = np.asarray(overlay_y, dtype=float)
                    if len(overlay_y) == len(y):
                        overlay_local = overlay_y[visible]
                        overlay_local = overlay_local[np.isfinite(overlay_local)]
                        if len(overlay_local) > 0:
                            local_y = np.concatenate([local_y, overlay_local])
                except Exception:
                    pass

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

    def get_active_view_key(self):
        label = str(getattr(self, "current_display_label", "")).lower()
        if label.startswith("raw"):
            return "raw"
        if label.startswith("teaching"):
            return "template"
        return "filtered"

    def reset_all_view_measurements(self):
        self.marker_sets = {
            "raw": {},
            "filtered": {},
            "template": {},
        }
        self.baseline_sets = {
            "raw": None,
            "filtered": None,
            "template": 0.0,
        }
        self.landmarks = self.marker_sets["raw"]
        self.baseline_value = None
        self.baseline_line = None
        self.landmark_mode = None

    def activate_view_measurements(self):
        key = self.get_active_view_key()

        if not hasattr(self, "marker_sets"):
            self.marker_sets = {"raw": {}, "filtered": {}, "template": {}}
        if not hasattr(self, "baseline_sets"):
            self.baseline_sets = {"raw": None, "filtered": None, "template": 0.0}

        self.landmarks = self.marker_sets.setdefault(key, {})

        if key == "template":
            self.baseline_value = 0.0
            self.baseline_sets["template"] = 0.0
        else:
            self.baseline_value = self.baseline_sets.get(key)

        self.baseline_line = None

        if hasattr(self, "set_baseline_btn") and hasattr(self, "clear_baseline_btn"):
            is_template = key == "template"
            self.set_baseline_btn.setEnabled(not is_template)
            self.clear_baseline_btn.setEnabled(not is_template)

        if hasattr(self, "baseline_status_label"):
            if key == "template":
                self.baseline_status_label.setText("Baseline: 0 template fixed")
            elif self.baseline_value is None:
                self.baseline_status_label.setText("Baseline: --")
            else:
                self.baseline_status_label.setText(f"Baseline: {float(self.baseline_value):.4f} raw")

        if hasattr(self, "p_status_label"):
            self.update_p_measurements_status()


    def save_current_baseline_to_view(self):
        key = self.get_active_view_key()
        if not hasattr(self, "baseline_sets"):
            self.baseline_sets = {"raw": None, "filtered": None, "template": 0.0}

        if key == "template":
            self.baseline_value = 0.0
            self.baseline_sets["template"] = 0.0
            return

        self.baseline_sets[key] = self.baseline_value


    def make_teaching_template_ecg(self, t):
        # Derived teaching template ECG.
        #
        # This is NOT a freehand cartoon and NOT a smoothed ECG.
        # It is a teaching-only schematic generated from the filtered ECG:
        # - R timing comes from detected R peaks.
        # - Q/R/S/P/T peak times are estimated from filtered-signal windows.
        # - Relative wave amplitudes are taken from the filtered signal, with
        #   gentle guardrails so one noise spike does not dominate.
        # - The drawn waves are clean finite teaching shapes.
        #
        # Therefore it remains related to the recording, while becoming easier
        # to use for explaining PQRST waves, intervals, and segments.
        t = np.asarray(t, dtype=float)
        template = np.zeros_like(t, dtype=float)

        if len(t) < 3:
            return template

        ch = self.channel_box.currentText() if hasattr(self, "channel_box") else "ch1"
        raw = None

        try:
            raw = np.asarray(self.current_channel_data.get(ch, None), dtype=float)
        except Exception:
            raw = None

        if raw is None or len(raw) != len(t):
            return template

        try:
            filtered = self.make_filtered_ecg(
                t,
                raw,
                notch=self.notch_box.isChecked() if hasattr(self, "notch_box") else True
            )
        except Exception:
            filtered = raw - np.nanmedian(raw)

        filtered = np.asarray(filtered, dtype=float)
        finite = np.isfinite(t) & np.isfinite(filtered)

        if finite.sum() < 10:
            return template

        t_min = float(np.nanmin(t[finite]))
        t_max = float(np.nanmax(t[finite]))

        try:
            peaks = np.asarray(self.detected_r_peaks, dtype=int)
            r_indices = peaks[(peaks >= 0) & (peaks < len(t))]
        except Exception:
            r_indices = np.asarray([], dtype=int)

        if len(r_indices) == 0:
            # If the user has not detected R peaks yet, fall back to a simple
            # default rhythm so the view is not blank. The log/right panel still
            # tells the user that R has not been detected.
            fs = self.estimate_fs(t)
            rr_s = 0.8
            r_times = []
            r = t_min + 0.45
            while r <= t_max + rr_s:
                r_times.append(r)
                r += rr_s
            r_indices = np.asarray([int(np.nanargmin(np.abs(t - rt))) for rt in r_times], dtype=int)

        r_indices = np.asarray(sorted(set(int(x) for x in r_indices)), dtype=int)
        r_indices = r_indices[(r_indices >= 0) & (r_indices < len(t))]

        if len(r_indices) == 0:
            return template

        r_times = t[r_indices]

        if len(r_times) >= 2:
            rr_values = np.diff(r_times)
            rr_values = rr_values[np.isfinite(rr_values) & (rr_values > 0.25) & (rr_values < 2.5)]
            rr_default = float(np.nanmedian(rr_values)) if len(rr_values) else 0.8
        else:
            rr_default = 0.8

        def clip_amp(value, low, high):
            value = float(value)
            sign = 1.0 if value >= 0 else -1.0
            mag = abs(value)
            mag = min(max(mag, low), high)
            return sign * mag

        def window_indices(a, b):
            mask = finite & (t >= a) & (t <= b)
            idx = np.where(mask)[0]
            return idx

        def local_max(a, b):
            idx = window_indices(a, b)
            if len(idx) == 0:
                return None, None
            local = filtered[idx]
            j = int(np.nanargmax(local))
            return int(idx[j]), float(local[j])

        def local_min(a, b):
            idx = window_indices(a, b)
            if len(idx) == 0:
                return None, None
            local = filtered[idx]
            j = int(np.nanargmin(local))
            return int(idx[j]), float(local[j])

        def add_cosine_bump(center, half_width, amp):
            half_width = max(float(half_width), 0.001)
            mask = np.abs(t - center) <= half_width
            if not np.any(mask):
                return
            phase = (t[mask] - center) / half_width
            template[mask] += amp * 0.5 * (1.0 + np.cos(np.pi * phase))

        def add_triangle(center, half_width, amp):
            half_width = max(float(half_width), 0.001)
            mask = np.abs(t - center) <= half_width
            if not np.any(mask):
                return
            phase = np.abs((t[mask] - center) / half_width)
            template[mask] += amp * np.maximum(0.0, 1.0 - phase)

        for i, r_idx in enumerate(r_indices):
            r_time = float(t[r_idx])

            if i > 0:
                pre_rr = r_time - float(t[r_indices[i - 1]])
            else:
                pre_rr = rr_default

            if i < len(r_indices) - 1:
                post_rr = float(t[r_indices[i + 1]]) - r_time
            else:
                post_rr = rr_default

            if not np.isfinite(pre_rr) or pre_rr <= 0.25 or pre_rr > 2.5:
                pre_rr = rr_default
            if not np.isfinite(post_rr) or post_rr <= 0.25 or post_rr > 2.5:
                post_rr = rr_default

            # Local baseline from pre-QRS segment.
            base_idx = window_indices(r_time - min(0.30, 0.45 * pre_rr), r_time - 0.09)
            if len(base_idx) >= 5:
                baseline = float(np.nanmedian(filtered[base_idx]))
            else:
                baseline = 0.0

            # R peak: use local max close to detected R.
            r_peak_idx, r_value = local_max(r_time - 0.030, r_time + 0.030)
            if r_peak_idx is None:
                r_peak_idx = int(r_idx)
                r_value = float(filtered[r_idx])

            r_amp = float(r_value - baseline)
            if abs(r_amp) < 1e-6:
                r_amp = 1.0

            # Use sign of R. Most ECG teaching examples are positive R.
            r_sign = 1.0 if r_amp >= 0 else -1.0
            r_mag = abs(r_amp)

            # Q and S: local minima around R.
            q_idx, q_val = local_min(r_time - 0.070, r_time - 0.010)
            s_idx, s_val = local_min(r_time + 0.010, r_time + 0.090)

            if q_idx is None:
                q_time = r_time - 0.035
                q_amp = -0.15 * r_mag * r_sign
            else:
                q_time = float(t[q_idx])
                q_amp = clip_amp(q_val - baseline, 0.05 * r_mag, 0.35 * r_mag)

            if s_idx is None:
                s_time = r_time + 0.040
                s_amp = -0.25 * r_mag * r_sign
            else:
                s_time = float(t[s_idx])
                s_amp = clip_amp(s_val - baseline, 0.08 * r_mag, 0.45 * r_mag)

            # P peak: search the real filtered signal before QRS.
            p_start = r_time - min(0.36, 0.55 * pre_rr)
            p_end = r_time - 0.085
            p_idx, p_val = local_max(p_start, p_end)

            if p_idx is None:
                p_time = r_time - min(0.20, 0.28 * pre_rr)
                p_amp = 0.12 * r_mag * r_sign
            else:
                p_time = float(t[p_idx])
                p_amp = p_val - baseline
                # Guardrails: preserve relation but keep teaching shape readable.
                if abs(p_amp) < 0.03 * r_mag:
                    p_amp = 0.08 * r_mag * r_sign
                else:
                    p_amp = clip_amp(p_amp, 0.04 * r_mag, 0.25 * r_mag)

            # T peak: search after QRS and before next P.
            t_start = r_time + 0.10
            t_end = r_time + min(0.52, 0.68 * post_rr)
            t_idx, t_val = local_max(t_start, t_end)

            if t_idx is None:
                t_time = r_time + min(0.28, 0.36 * post_rr)
                t_amp = 0.28 * r_mag * r_sign
            else:
                t_time = float(t[t_idx])
                t_amp = t_val - baseline
                if abs(t_amp) < 0.05 * r_mag:
                    t_amp = 0.25 * r_mag * r_sign
                else:
                    t_amp = clip_amp(t_amp, 0.08 * r_mag, 0.45 * r_mag)

            # Finite didactic widths. These are narrower at faster rates.
            p_half = min(0.060, max(0.035, 0.075 * pre_rr))
            t_half = min(0.120, max(0.065, 0.145 * post_rr))

            # Avoid overlap with QRS and next P.
            qrs_left_guard = r_time - 0.075
            if p_time + p_half > qrs_left_guard:
                p_half = max(0.025, qrs_left_guard - p_time)

            if i < len(r_indices) - 1:
                next_r_time = float(t[r_indices[i + 1]])
                next_p_start = next_r_time - min(0.36, 0.55 * post_rr)
                allowed_t_half = next_p_start - t_time - 0.025
                if allowed_t_half < t_half:
                    t_half = max(0.050, allowed_t_half)

            # Draw template in filtered ADC-count deviation units.
            add_cosine_bump(p_time, p_half, p_amp)
            add_triangle(q_time, 0.018, q_amp)
            add_triangle(r_time, 0.022, r_mag * r_sign)
            add_triangle(s_time, 0.024, s_amp)
            add_cosine_bump(t_time, t_half, t_amp)

        return template


    def plot_current_ecg_trace(self, t, y):
        key = self.get_active_view_key()

        if key == "template":
            show_overlay = False
            if hasattr(self, "template_overlay_box"):
                show_overlay = self.template_overlay_box.isChecked()

            overlay_y = getattr(self, "current_template_overlay_y", None)
            if show_overlay and overlay_y is not None:
                try:
                    overlay_y = np.asarray(overlay_y, dtype=float)
                    if len(overlay_y) == len(t):
                        self.plot.plot(
                            t,
                            overlay_y,
                            pen=pg.mkPen((255, 196, 0, 110), width=1),
                            name="Filtered ECG overlay"
                        )
                except Exception:
                    pass

            self.plot.plot(
                t,
                y,
                pen=pg.mkPen(self.get_trace_color(), width=2),
                name="Teaching Template ECG"
            )
            return

        self.plot.plot(
            t,
            y,
            pen=pg.mkPen(self.get_trace_color(), width=1),
            name=getattr(self, "current_display_label", "ECG")
        )


    def ensure_r_peaks_for_template(self, t, filtered):
        # Teaching Template ECG needs R peaks as anchors.
        # If the user has not pressed Detect R yet, detect R peaks silently from
        # the filtered ECG so the template remains related to the loaded recording.
        try:
            existing = np.asarray(getattr(self, "detected_r_peaks", []), dtype=int)
            existing = existing[(existing >= 0) & (existing < len(t))]
            if len(existing) > 0:
                return
        except Exception:
            pass

        try:
            fs = self.estimate_fs(np.asarray(t, dtype=float))
            result = detect_ecg_r_peaks(
                np.asarray(t, dtype=float),
                np.asarray(filtered, dtype=float),
                fs=fs,
                forced_polarity="auto"
            )

            peaks = result.get("peaks", None)
            if peaks is None:
                peaks = result.get("r_peaks", None)
            if peaks is None:
                peaks = result.get("peak_indices", None)
            if peaks is None:
                peaks = []

            peaks = np.asarray(peaks, dtype=int)
            peaks = peaks[(peaks >= 0) & (peaks < len(t))]

            self.detected_r_peaks = peaks

            if len(peaks) > 0:
                self.selected_peak_number = 0
                if hasattr(self, "rpeak_status_label"):
                    self.rpeak_status_label.setText(f"R: {len(peaks)} | beat 1/{len(peaks)}")
            else:
                if hasattr(self, "rpeak_status_label"):
                    self.rpeak_status_label.setText("R: --")

        except Exception as e:
            if hasattr(self, "rpeak_status_label"):
                self.rpeak_status_label.setText("R: autodetect failed")
            try:
                self.log_message(f"Teaching Template ECG could not auto-detect R peaks: {e}")
            except Exception:
                pass



    def remove_template_vertical_guides(self):
        # The shared R-marker code may draw a vertical selected-R guide line.
        # In Teaching Template ECG this distracts from morphology, so remove
        # vertical InfiniteLine objects after all normal drawing is done.
        try:
            if self.get_active_view_key() != "template":
                return
        except Exception:
            return

        try:
            plot_item = self.plot.getPlotItem()
            for item in list(plot_item.items):
                if isinstance(item, pg.InfiniteLine):
                    angle = getattr(item, "angle", None)
                    try:
                        angle_value = float(angle)
                    except Exception:
                        angle_value = None

                    # Remove only vertical guide lines. Keep horizontal baseline
                    # lines in other views untouched.
                    if angle_value == 90.0:
                        plot_item.removeItem(item)
        except Exception:
            pass


    def extract_landmark_xy(self, value):
        # Robust extraction of a plotted landmark coordinate.
        # Accepts:
        # - tuple/list: (time, value)
        # - dict: time/x/t/time_s and value/y/y_raw/amplitude
        # - pyqtgraph items with pos()
        try:
            if value is None:
                return None

            if isinstance(value, dict):
                time_keys = ["time", "time_s", "t", "x", "x_s"]
                value_keys = ["value", "y", "y_raw", "amplitude", "amp"]

                x = None
                y = None

                for k in time_keys:
                    if k in value:
                        x = value.get(k)
                        break

                for k in value_keys:
                    if k in value:
                        y = value.get(k)
                        break

                if x is not None and y is not None:
                    return float(x), float(y)

            if isinstance(value, (list, tuple)) and len(value) >= 2:
                return float(value[0]), float(value[1])

            # Some pyqtgraph objects have pos() returning QPointF.
            if hasattr(value, "pos"):
                p = value.pos()
                if hasattr(p, "x") and hasattr(p, "y"):
                    return float(p.x()), float(p.y())

        except Exception:
            return None

        return None

    def find_template_p_landmark_xy(self, kind):
        # Find P landmarks regardless of how the current panel stores them.
        # kind: "onset", "peak", or "offset".
        #
        # The shared P-marker code already knows the points, but earlier template
        # overlay code did not always find them because the internal key names can
        # differ. This scanner searches common dicts and attributes.
        kind = str(kind).lower()

        key_variants = {
            "onset": ["ponset", "p_onset", "p onset", "pstart", "p_start", "pbegin", "p_begin"],
            "peak": ["ppeak", "p_peak", "p peak", "pmax", "p_max"],
            "offset": ["poffset", "p_offset", "p offset", "pend", "p_end", "pstop", "p_stop"],
        }.get(kind, [])

        def normalized(s):
            return str(s).lower().replace(" ", "").replace("_", "").replace("-", "")

        normalized_variants = [normalized(x) for x in key_variants]

        def key_matches(k):
            nk = normalized(k)
            return any(v in nk for v in normalized_variants)

        # 1. Search likely dictionaries first.
        likely_dict_names = [
            "landmarks",
            "marker_sets",
            "p_landmarks",
            "p_markers",
            "p_wave_markers",
            "p_calipers",
            "manual_markers",
        ]

        for name in likely_dict_names:
            try:
                obj = getattr(self, name, None)
            except Exception:
                obj = None

            if isinstance(obj, dict):
                # marker_sets is nested by view name.
                dicts_to_scan = [obj]
                try:
                    if self.get_active_view_key() in obj and isinstance(obj[self.get_active_view_key()], dict):
                        dicts_to_scan.insert(0, obj[self.get_active_view_key()])
                except Exception:
                    pass

                for d in dicts_to_scan:
                    for k, v in d.items():
                        if key_matches(k):
                            xy = self.extract_landmark_xy(v)
                            if xy is not None:
                                return xy

        # 2. Search every dictionary in self.__dict__.
        try:
            for attr_name, obj in vars(self).items():
                if not isinstance(obj, dict):
                    continue

                for k, v in obj.items():
                    if key_matches(k):
                        xy = self.extract_landmark_xy(v)
                        if xy is not None:
                            return xy

                # Nested dictionaries.
                for outer_k, outer_v in obj.items():
                    if isinstance(outer_v, dict):
                        for k, v in outer_v.items():
                            if key_matches(k):
                                xy = self.extract_landmark_xy(v)
                                if xy is not None:
                                    return xy
        except Exception:
            pass

        # 3. Search direct attributes such as p_onset_time + p_onset_value.
        try:
            time_candidates = []
            value_candidates = []

            for attr_name, obj in vars(self).items():
                n = normalized(attr_name)
                if not any(v in n for v in normalized_variants):
                    continue

                if "time" in n or n.endswith("x") or "times" in n:
                    time_candidates.append((attr_name, obj))
                if "value" in n or "raw" in n or "amp" in n or n.endswith("y"):
                    value_candidates.append((attr_name, obj))

                xy = self.extract_landmark_xy(obj)
                if xy is not None:
                    return xy

            for _, tx in time_candidates:
                for _, vy in value_candidates:
                    try:
                        return float(tx), float(vy)
                    except Exception:
                        continue
        except Exception:
            pass

        return None

    def remove_template_shared_p_labels(self):
        # Shared P-marker drawing already adds green labels. In Teaching Template
        # ECG we draw gold P labels instead, so remove the shared green P labels
        # first to avoid duplicated green+gold text.
        try:
            if self.get_active_view_key() != "template":
                return
        except Exception:
            return

        try:
            plot_item = self.plot.getPlotItem()
            for item in list(plot_item.items):
                if not isinstance(item, pg.TextItem):
                    continue

                label = ""
                try:
                    if hasattr(item, "textItem"):
                        label = item.textItem.toPlainText()
                    elif hasattr(item, "toPlainText"):
                        label = item.toPlainText()
                except Exception:
                    label = ""

                label_norm = str(label).strip().lower()
                if label_norm in {
                    "p onset", "p peak", "p offset",
                    "ponset", "ppeak", "poffset",
                    "p on", "p off", "p"
                }:
                    plot_item.removeItem(item)
        except Exception:
            pass

    def draw_template_opal_markers(self):
        # Teaching Template ECG marker overlay.
        # Keep it simple and readable:
        # - R peaks remain cyan diamonds.
        # - Selected R remains a subtle lavender ring.
        # - P-wave markers are gold in template view, with labels outside the icon.
        # Raw and Filtered ECG marker styling is left unchanged.
        try:
            if self.get_active_view_key() != "template":
                return
        except Exception:
            return

        if self.current_plot_t is None or self.current_plot_y is None:
            return

        try:
            t = np.asarray(self.current_plot_t, dtype=float)
            y = np.asarray(self.current_plot_y, dtype=float)
        except Exception:
            return

        if len(t) == 0 or len(y) == 0:
            return

        self.remove_template_vertical_guides()
        self.remove_template_shared_p_labels()

        # R peak markers.
        try:
            peaks = np.asarray(getattr(self, "detected_r_peaks", []), dtype=int)
            peaks = peaks[(peaks >= 0) & (peaks < len(t))]

            if len(peaks) > 0:
                item = self.plot.plot(
                    t[peaks],
                    y[peaks],
                    pen=None,
                    symbol="d",
                    symbolSize=15,
                    symbolBrush=pg.mkBrush("#00E5FF"),
                    symbolPen=pg.mkPen("#00131A", width=2),
                    name="Template R peaks"
                )
                try:
                    item.setZValue(75)
                except Exception:
                    pass

            n = getattr(self, "selected_peak_number", None)
            if n is not None and len(peaks) > 0:
                n = int(n)
                if 0 <= n < len(peaks):
                    idx = int(peaks[n])
                    item = self.plot.plot(
                        [float(t[idx])],
                        [float(y[idx])],
                        pen=None,
                        symbol="o",
                        symbolSize=14,
                        symbolBrush=pg.mkBrush(179, 136, 255, 80),
                        symbolPen=pg.mkPen("#EDE7FF", width=2),
                        name="Selected template R"
                    )
                    try:
                        item.setZValue(85)
                    except Exception:
                        pass
        except Exception:
            pass

        # P-wave landmarks in Teaching Template ECG:
        # Use one simple gold scheme for all P markers so it is not visually busy.
        # The label is placed above the marker, not inside it.
        gold_brush = pg.mkBrush("#FFD54F")
        gold_pen = pg.mkPen("#111111", width=2)
        gold_text = "#FFE082"

        p_styles = {
            "onset": {"label": "P onset",  "symbol": "t",  "size": 15, "dy": 46},
            "peak":  {"label": "P peak",   "symbol": "o",  "size": 15, "dy": 58},
            "offset":{"label": "P offset", "symbol": "t1", "size": 15, "dy": 46},
        }

        try:
            for kind, style in p_styles.items():
                xy = self.find_template_p_landmark_xy(kind)
                if xy is None:
                    continue

                x0, y0 = xy

                item = self.plot.plot(
                    [x0],
                    [y0],
                    pen=None,
                    symbol=style["symbol"],
                    symbolSize=style["size"],
                    symbolBrush=gold_brush,
                    symbolPen=gold_pen,
                    name=f"Template P {kind}"
                )
                try:
                    item.setZValue(90)
                except Exception:
                    pass

                # Put label outside/above the marker, similar to the filtered view.
                label_y = float(y0) + float(style["dy"])
                label = pg.TextItem(style["label"], color=gold_text, anchor=(0.5, 1.0))
                label.setPos(float(x0), label_y)
                label.setZValue(95)
                self.plot.addItem(label)

        except Exception:
            pass

        self.remove_template_vertical_guides()


    def ensure_p_marker_drag_signals(self):
        # Connect once. This gives P markers hover + drag repositioning.
        if getattr(self, "_p_marker_drag_connected", False):
            return

        try:
            self.plot.scene().sigMouseMoved.connect(self.handle_p_marker_hover_drag)
            self._p_marker_drag_connected = True
        except Exception:
            self._p_marker_drag_connected = False

        if not hasattr(self, "hovered_p_marker"):
            self.hovered_p_marker = None
        if not hasattr(self, "dragging_p_marker"):
            self.dragging_p_marker = None
        if not hasattr(self, "selected_p_marker"):
            self.selected_p_marker = None

    def map_scene_pos_to_data(self, scene_pos):
        try:
            vb = self.plot.getViewBox()
            mapped = vb.mapSceneToView(scene_pos)
            return float(mapped.x()), float(mapped.y())
        except Exception:
            return None

    def trace_xy_at_time(self, x_time):
        # Keep moved markers on the currently displayed trace.
        if self.current_plot_t is None or self.current_plot_y is None:
            return None

        try:
            t = np.asarray(self.current_plot_t, dtype=float)
            y = np.asarray(self.current_plot_y, dtype=float)
            finite = np.isfinite(t) & np.isfinite(y)

            if finite.sum() < 2:
                return None

            valid_idx = np.where(finite)[0]
            nearest_local = int(np.nanargmin(np.abs(t[valid_idx] - float(x_time))))
            idx = int(valid_idx[nearest_local])
            return float(t[idx]), float(y[idx])
        except Exception:
            return None

    def find_any_p_landmark_xy(self, kind):
        # Find P landmarks across the different storage forms used while this
        # panel has evolved. This is intentionally broad so P onset, peak, and
        # offset can all be dragged.
        kind = str(kind).lower()

        variants = {
            "onset": ["p_onset", "ponset", "p_start", "pstart", "p_begin", "pbegin"],
            "peak": ["p_peak", "ppeak", "p_max", "pmax"],
            "offset": ["p_offset", "poffset", "p_end", "pend", "p_stop", "pstop"],
        }.get(kind, [])

        def norm(s):
            return str(s).lower().replace(" ", "").replace("_", "").replace("-", "")

        variant_norms = [norm(v) for v in variants]

        def key_matches(k):
            nk = norm(k)
            return any(v in nk for v in variant_norms)

        def xy_from_obj(obj):
            try:
                xy = self.extract_landmark_xy(obj)
                if xy is not None:
                    return xy
            except Exception:
                pass
            return None

        # 1. First scan the active per-view marker set.
        try:
            view_key = self.get_active_view_key()
            if hasattr(self, "marker_sets"):
                d = self.marker_sets.get(view_key, None)
                if isinstance(d, dict):
                    for k, v in d.items():
                        if key_matches(k):
                            xy = xy_from_obj(v)
                            if xy is not None:
                                return xy
        except Exception:
            pass

        # 2. Scan current landmarks dictionary.
        try:
            if hasattr(self, "landmarks") and isinstance(self.landmarks, dict):
                for k, v in self.landmarks.items():
                    if key_matches(k):
                        xy = xy_from_obj(v)
                        if xy is not None:
                            return xy
        except Exception:
            pass

        # 3. Scan all dictionaries and nested dictionaries in self.
        try:
            for attr_name, obj in vars(self).items():
                if not isinstance(obj, dict):
                    continue

                for k, v in obj.items():
                    if key_matches(k):
                        xy = xy_from_obj(v)
                        if xy is not None:
                            return xy

                for outer_k, outer_v in obj.items():
                    if isinstance(outer_v, dict):
                        for k, v in outer_v.items():
                            if key_matches(k):
                                xy = xy_from_obj(v)
                                if xy is not None:
                                    return xy
        except Exception:
            pass

        # 4. Scan direct attributes. This catches forms like p_peak_time_s and
        # p_peak_value if they exist.
        try:
            candidate_times = []
            candidate_values = []

            for attr_name, obj in vars(self).items():
                n = norm(attr_name)
                if not any(v in n for v in variant_norms):
                    continue

                xy = xy_from_obj(obj)
                if xy is not None:
                    return xy

                if "time" in n or n.endswith("x") or "times" in n:
                    candidate_times.append(obj)

                if "value" in n or "raw" in n or "amp" in n or n.endswith("y"):
                    candidate_values.append(obj)

            for tx in candidate_times:
                for vy in candidate_values:
                    try:
                        return float(tx), float(vy)
                    except Exception:
                        continue
        except Exception:
            pass

        return None


    def nearest_p_marker_kind(self, scene_pos):
        # Return nearest P marker if the mouse is close enough in screen pixels.
        # Use a generous tolerance because the label may overlap the marker and
        # trackpad clicks move a few pixels during mouse-down.
        mapped = self.map_scene_pos_to_data(scene_pos)
        if mapped is None:
            return None

        try:
            vb = self.plot.getViewBox()
            candidates = []

            for kind in ["onset", "peak", "offset"]:
                xy = self.find_any_p_landmark_xy(kind)
                if xy is None:
                    continue

                marker_scene = vb.mapViewToScene(pg.Point(float(xy[0]), float(xy[1])))
                dx = float(marker_scene.x() - scene_pos.x())
                dy = float(marker_scene.y() - scene_pos.y())
                dist = (dx * dx + dy * dy) ** 0.5
                candidates.append((dist, kind))

            if not candidates:
                return None

            candidates.sort(key=lambda x: x[0])
            best_dist, best_kind = candidates[0]

            # Larger tolerance than before. This fixes cases where P peak/offset
            # did not start dragging although hover labels were visible.
            if best_dist <= 45:
                return best_kind
        except Exception:
            return None

        return None


    def set_p_landmark_position(self, kind, x, y):
        # Store using standard keys and also update any existing matching keys.
        # This prevents only one marker moving when different parts of the panel
        # use different historical names for P onset/peak/offset.
        kind = str(kind).lower()
        standard_key = {
            "onset": "p_onset",
            "peak": "p_peak",
            "offset": "p_offset",
        }.get(kind)

        if standard_key is None:
            return

        x = float(x)
        y = float(y)
        value = (x, y)

        if not hasattr(self, "landmarks") or self.landmarks is None:
            self.landmarks = {}

        self.landmarks[standard_key] = value

        # Keep per-view marker_sets synchronized.
        try:
            view_key = self.get_active_view_key()
            if hasattr(self, "marker_sets"):
                if view_key not in self.marker_sets or not isinstance(self.marker_sets[view_key], dict):
                    self.marker_sets[view_key] = {}
                self.marker_sets[view_key][standard_key] = value
        except Exception:
            pass

        # Update common alternate key names in existing dicts.
        variants = {
            "onset": ["p_onset", "ponset", "p_start", "pstart", "p_begin", "pbegin"],
            "peak": ["p_peak", "ppeak", "p_max", "pmax"],
            "offset": ["p_offset", "poffset", "p_end", "pend", "p_stop", "pstop"],
        }.get(kind, [])

        def norm(s):
            return str(s).lower().replace(" ", "").replace("_", "").replace("-", "")

        variant_norms = [norm(v) for v in variants]

        def key_matches(k):
            nk = norm(k)
            return any(v in nk for v in variant_norms)

        try:
            for attr_name, obj in vars(self).items():
                if isinstance(obj, dict):
                    for k in list(obj.keys()):
                        if key_matches(k):
                            obj[k] = value

                    for outer_k, outer_v in list(obj.items()):
                        if isinstance(outer_v, dict):
                            for k in list(outer_v.keys()):
                                if key_matches(k):
                                    outer_v[k] = value
        except Exception:
            pass

        # Update common direct attributes if present.
        try:
            for attr_name in list(vars(self).keys()):
                n = norm(attr_name)
                if not any(v in n for v in variant_norms):
                    continue

                if "time" in n or n.endswith("x"):
                    setattr(self, attr_name, x)
                elif "value" in n or "raw" in n or n.endswith("y"):
                    setattr(self, attr_name, y)
        except Exception:
            pass

        self.selected_p_marker = kind
        self.hovered_p_marker = kind

        try:
            self.update_p_measurements_status()
        except Exception:
            pass

        try:
            self.update_measurements_panel()
        except Exception:
            pass


    def ecg_drag_marker_specs(self):
        return [
            ("p:onset", "P onset"),
            ("p:peak", "P peak"),
            ("p:offset", "P offset"),
            ("qrs:qrs_onset", "QRS onset"),
            ("qrs:q_nadir", "Q nadir"),
            ("qrs:s_nadir", "S nadir"),
            ("qrs:j_point", "J point"),
        ]

    def ecg_drag_marker_label(self, marker_id):
        labels = dict(self.ecg_drag_marker_specs())
        return labels.get(marker_id, str(marker_id))

    def find_ecg_drag_marker_xy(self, marker_id):
        marker_id = str(marker_id)

        if marker_id.startswith("p:"):
            kind = marker_id.split(":", 1)[1]
            try:
                return self.find_any_p_landmark_xy(kind)
            except Exception:
                return None

        if marker_id.startswith("qrs:"):
            kind = marker_id.split(":", 1)[1]
            try:
                return self.get_qrs_landmark_xy(kind)
            except Exception:
                return None

        return None

    def nearest_ecg_drag_marker(self, scene_pos):
        # Return nearest draggable ECG landmark if close enough in screen pixels.
        try:
            vb = self.plot.getViewBox()
            candidates = []

            for marker_id, label in self.ecg_drag_marker_specs():
                xy = self.find_ecg_drag_marker_xy(marker_id)
                if xy is None:
                    continue

                marker_scene = vb.mapViewToScene(pg.Point(float(xy[0]), float(xy[1])))
                dx = float(marker_scene.x() - scene_pos.x())
                dy = float(marker_scene.y() - scene_pos.y())
                dist = (dx * dx + dy * dy) ** 0.5
                candidates.append((dist, marker_id))

            if not candidates:
                return None

            candidates.sort(key=lambda item: item[0])
            best_dist, best_marker = candidates[0]

            # Generous enough for trackpads and labels, but still local.
            if best_dist <= 45:
                return best_marker
        except Exception:
            return None

        return None

    def set_ecg_drag_marker_position(self, marker_id, x, y):
        marker_id = str(marker_id)

        if marker_id.startswith("p:"):
            kind = marker_id.split(":", 1)[1]
            self.set_p_landmark_position(kind, float(x), float(y))
            try:
                self.rebuild_caliper_measurements_panel()
            except Exception:
                pass
            return

        if marker_id.startswith("qrs:"):
            kind = marker_id.split(":", 1)[1]
            self.store_qrs_landmark(kind, float(x), float(y))
            self.selected_ecg_marker = marker_id
            self.hovered_ecg_marker = marker_id

            try:
                self.rebuild_caliper_measurements_panel()
            except Exception:
                pass

            return


    def handle_p_marker_hover_drag(self, scene_pos):
        # Hover/select and reposition ECG caliper landmarks.
        #
        # Clean interaction rule:
        # - Normal mouse drag = plot navigation/pan
        # - Mouse wheel = zoom
        # - Ctrl + left-drag on a marker = move marker
        #
        # This prevents marker editing from fighting with navigation.
        self.ensure_p_marker_drag_signals()

        try:
            from PyQt5.QtWidgets import QApplication
            from PyQt5.QtCore import Qt as _Qt
        except Exception:
            return

        try:
            inside_plot = self.plot.sceneBoundingRect().contains(scene_pos)
        except Exception:
            inside_plot = True

        if not inside_plot:
            self.dragging_ecg_marker = None
            self.dragging_p_marker = None
            self.hovered_ecg_marker = None
            self.hovered_p_marker = None
            try:
                self.plot.getViewBox().setMouseEnabled(x=True, y=True)
                self.plot.unsetCursor()
            except Exception:
                pass
            return

        try:
            left_down = bool(QApplication.mouseButtons() & _Qt.LeftButton)
            ctrl_down = bool(QApplication.keyboardModifiers() & _Qt.ControlModifier)
        except Exception:
            left_down = False
            ctrl_down = False

        if not ctrl_down:
            self.dragging_ecg_marker = None
            self.dragging_p_marker = None

            near_marker = self.nearest_ecg_drag_marker(scene_pos)
            self.hovered_ecg_marker = near_marker

            if near_marker and near_marker.startswith("p:"):
                self.hovered_p_marker = near_marker.split(":", 1)[1]
            else:
                self.hovered_p_marker = None

            try:
                self.plot.getViewBox().setMouseEnabled(x=True, y=True)

                if near_marker is not None:
                    self.plot.setCursor(_Qt.OpenHandCursor)
                    label = self.ecg_drag_marker_label(near_marker)
                    if near_marker.startswith("p:") and hasattr(self, "p_status_label"):
                        self.p_status_label.setText(f"{label}: Ctrl + drag to move")
                    elif near_marker.startswith("qrs:") and hasattr(self, "qrs_status_label"):
                        self.qrs_status_label.setText(f"{label}: Ctrl + drag to move")
                else:
                    self.plot.unsetCursor()
            except Exception:
                pass

            return

        current_drag = getattr(self, "dragging_ecg_marker", None)

        if left_down and current_drag is not None:
            mapped = self.map_scene_pos_to_data(scene_pos)
            if mapped is None:
                return

            snapped = self.trace_xy_at_time(mapped[0])
            if snapped is None:
                return

            self.set_ecg_drag_marker_position(current_drag, snapped[0], snapped[1])
            self.refresh_all_caliper_measurements()

            try:
                self.refresh_plot()
            except Exception:
                try:
                    self.redraw_plot_with_r_peaks()
                except Exception:
                    pass

            try:
                self.plot.getViewBox().setMouseEnabled(x=False, y=False)
                self.plot.setCursor(_Qt.ClosedHandCursor)
            except Exception:
                pass

            return

        if left_down:
            near_marker = self.nearest_ecg_drag_marker(scene_pos)

            if near_marker is not None:
                self.dragging_ecg_marker = near_marker
                self.selected_ecg_marker = near_marker

                if near_marker.startswith("p:"):
                    self.dragging_p_marker = near_marker.split(":", 1)[1]
                    self.selected_p_marker = near_marker.split(":", 1)[1]

                mapped = self.map_scene_pos_to_data(scene_pos)
                if mapped is None:
                    return

                snapped = self.trace_xy_at_time(mapped[0])
                if snapped is None:
                    return

                self.set_ecg_drag_marker_position(near_marker, snapped[0], snapped[1])
                self.refresh_all_caliper_measurements()

                try:
                    self.refresh_plot()
                except Exception:
                    try:
                        self.redraw_plot_with_r_peaks()
                    except Exception:
                        pass

                try:
                    self.plot.getViewBox().setMouseEnabled(x=False, y=False)
                    self.plot.setCursor(_Qt.ClosedHandCursor)
                except Exception:
                    pass

                return

        self.dragging_ecg_marker = None
        self.dragging_p_marker = None
        near_marker = self.nearest_ecg_drag_marker(scene_pos)
        self.hovered_ecg_marker = near_marker

        if near_marker and near_marker.startswith("p:"):
            self.hovered_p_marker = near_marker.split(":", 1)[1]
        else:
            self.hovered_p_marker = None

        try:
            if near_marker is not None:
                self.plot.getViewBox().setMouseEnabled(x=False, y=False)
                self.plot.setCursor(_Qt.OpenHandCursor)
                label = self.ecg_drag_marker_label(near_marker)
                if near_marker.startswith("p:") and hasattr(self, "p_status_label"):
                    self.p_status_label.setText(f"{label}: release after moving")
                elif near_marker.startswith("qrs:") and hasattr(self, "qrs_status_label"):
                    self.qrs_status_label.setText(f"{label}: release after moving")
            else:
                self.plot.getViewBox().setMouseEnabled(x=True, y=True)
                self.plot.unsetCursor()
        except Exception:
            pass


    def refresh_plot(self):
        self.ensure_p_marker_drag_signals()
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

        self.current_template_overlay_y = None
        view_name = self.view_box.currentText() if hasattr(self, "view_box") else ""
        if str(view_name).startswith("Teaching"):
            raw_for_template = np.asarray(self.current_channel_data.get(ch, y), dtype=float)
            filtered_for_template = self.make_filtered_ecg(
                t,
                raw_for_template,
                notch=self.notch_box.isChecked() if hasattr(self, "notch_box") else True
            )
            self.current_template_overlay_y = filtered_for_template
            self.ensure_r_peaks_for_template(t, filtered_for_template)
            y = self.make_teaching_template_ecg(t)
            self.current_display_label = "Teaching Template ECG"

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

        self.activate_view_measurements()
        self.activate_view_measurements()
        self.plot.clear()
        self.plot_current_ecg_trace(t, y)
        self.draw_baseline_line()
        self.draw_landmark_markers()
        self.draw_qrs_markers()
        try:
            self.rebuild_caliper_measurements_panel()
        except Exception:
            pass
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
        self.draw_template_opal_markers()

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
        self.ensure_p_marker_drag_signals()
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
        self.plot_current_ecg_trace(t, y)
        self.draw_baseline_line()
        self.draw_landmark_markers()
        self.draw_qrs_markers()
        try:
            self.rebuild_caliper_measurements_panel()
        except Exception:
            pass

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
        self.draw_template_opal_markers()

    def update_measurement_summary(self):
        if not hasattr(self, "summary_box"):
            return

        lines = ["ECG Calipers Measurements", ""]

        if self.current_csv_path is not None:
            lines.append(f"File: {self.current_csv_path.name}")
            lines.append(f"Channel: {self.channel_box.currentText()}")
            lines.append(f"View: {self.current_display_label}")
            lines.append(f"Active marker set: {self.get_active_view_key()}")
            if self.get_active_view_key() == "template":
                lines.append("Teaching-only template; not for diagnosis/research.")
                lines.append("")
                lines.append("Template method:")
                lines.append("1. Filtered ECG is used as the source signal.")
                lines.append("2. R peaks are auto-detected if needed.")
                lines.append("3. R timing = detected R-peak times.")
                lines.append("4. R amplitude = local filtered R peak minus pre-QRS median baseline.")
                lines.append("5. P/Q/S/T are finite teaching shapes placed relative to R and RR.")
                lines.append("6. Relative amplitudes: P≈0.12R, Q≈-0.12R, S≈-0.25R, T≈0.30R.")
                lines.append("7. Baseline is fixed at 0 template units.")
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

        self.append_qrs_summary_lines(lines)
        self.summary_box.setText("\n".join(lines))

    def normalize_marker_key(self, key):
        return str(key).lower().replace(" ", "").replace("_", "").replace("-", "")

    def get_landmark_xy_by_variants(self, variants):
        # Exact normalized lookup only.
        # This prevents short names like "S" from accidentally matching keys
        # such as "p_onset".
        variants_norm = {self.normalize_marker_key(v) for v in variants}

        def key_matches(k):
            return self.normalize_marker_key(k) in variants_norm

        def xy_from_obj(obj):
            try:
                xy = self.extract_landmark_xy(obj)
                if xy is not None:
                    return xy
            except Exception:
                pass

            try:
                if isinstance(obj, dict):
                    x = obj.get("time_s", obj.get("time", obj.get("x", None)))
                    y = obj.get("value", obj.get("y", obj.get("raw", None)))
                    if x is not None and y is not None:
                        return float(x), float(y)
            except Exception:
                pass

            try:
                if isinstance(obj, (list, tuple)) and len(obj) >= 2:
                    return float(obj[0]), float(obj[1])
            except Exception:
                pass

            return None

        try:
            view_key = self.get_active_view_key()
            if hasattr(self, "marker_sets"):
                d = self.marker_sets.get(view_key, None)
                if isinstance(d, dict):
                    for k, v in d.items():
                        if key_matches(k):
                            xy = xy_from_obj(v)
                            if xy is not None:
                                return xy
        except Exception:
            pass

        try:
            if hasattr(self, "landmarks") and isinstance(self.landmarks, dict):
                for k, v in self.landmarks.items():
                    if key_matches(k):
                        xy = xy_from_obj(v)
                        if xy is not None:
                            return xy
        except Exception:
            pass

        try:
            for attr_name, obj in vars(self).items():
                if not isinstance(obj, dict):
                    continue

                for k, v in obj.items():
                    if key_matches(k):
                        xy = xy_from_obj(v)
                        if xy is not None:
                            return xy

                for outer_k, outer_v in obj.items():
                    if isinstance(outer_v, dict):
                        for k, v in outer_v.items():
                            if key_matches(k):
                                xy = xy_from_obj(v)
                                if xy is not None:
                                    return xy
        except Exception:
            pass

        return None


    def sync_qrs_landmarks_from_all_storage(self):
        # Normalize QRS/ST marker names from any internal storage used by the
        # generic caliper placement code. This keeps the right panel and marker
        # dragging in sync.
        key_groups = {
            "qrs_onset": ["qrs_onset", "qrs onset", "QRS onset", "q_onset", "q onset", "Q onset", "qrs_start", "QRS start"],
            "q_nadir": ["q_nadir", "q nadir", "Q nadir", "q_point", "q point", "Q point", "Q"],
            "s_nadir": ["s_nadir", "s nadir", "S nadir", "s_point", "s point", "S point", "S"],
            "j_point": ["j_point", "j point", "J point", "qrs_offset", "qrs offset", "QRS offset", "qrs_end", "QRS end", "J"],
        }

        def norm(s):
            return str(s).lower().replace(" ", "").replace("_", "").replace("-", "")

        normalized = {std: {norm(k) for k in keys} for std, keys in key_groups.items()}

        def xy_from_obj(obj):
            try:
                xy = self.extract_landmark_xy(obj)
                if xy is not None:
                    return xy
            except Exception:
                pass

            try:
                if isinstance(obj, dict):
                    x = obj.get("time_s", obj.get("time", obj.get("x", obj.get("t", None))))
                    y = obj.get("value", obj.get("y", obj.get("y_raw", obj.get("raw", obj.get("amplitude", None)))))
                    if x is not None and y is not None:
                        return float(x), float(y)
            except Exception:
                pass

            try:
                if isinstance(obj, (list, tuple)):
                    nums = []
                    for item in obj:
                        try:
                            nums.append(float(item))
                        except Exception:
                            pass
                    if len(nums) >= 2:
                        return nums[0], nums[1]
            except Exception:
                pass

            return None

        found = {}

        def scan_dict(d):
            if not isinstance(d, dict):
                return

            for k, v in d.items():
                nk = norm(k)
                for std, variants in normalized.items():
                    if nk in variants:
                        xy = xy_from_obj(v)
                        if xy is not None:
                            found[std] = xy

            for outer_k, outer_v in d.items():
                if isinstance(outer_v, dict):
                    scan_dict(outer_v)

        try:
            if hasattr(self, "marker_sets") and isinstance(self.marker_sets, dict):
                try:
                    view_key = self.get_active_view_key()
                    scan_dict(self.marker_sets.get(view_key, {}))
                except Exception:
                    pass
                scan_dict(self.marker_sets)
        except Exception:
            pass

        try:
            if hasattr(self, "landmarks") and isinstance(self.landmarks, dict):
                scan_dict(self.landmarks)
        except Exception:
            pass

        try:
            for attr_name, obj in vars(self).items():
                if isinstance(obj, dict):
                    scan_dict(obj)
        except Exception:
            pass

        if not found:
            return

        if not hasattr(self, "landmarks") or self.landmarks is None:
            self.landmarks = {}

        try:
            view_key = self.get_active_view_key()
            if hasattr(self, "marker_sets"):
                if view_key not in self.marker_sets or not isinstance(self.marker_sets[view_key], dict):
                    self.marker_sets[view_key] = {}
        except Exception:
            view_key = None

        for std, xy in found.items():
            value = (float(xy[0]), float(xy[1]))
            self.landmarks[std] = value
            try:
                if hasattr(self, "marker_sets") and view_key is not None:
                    self.marker_sets[view_key][std] = value
            except Exception:
                pass

    def refresh_all_caliper_measurements(self):
        # One safe refresh point after any marker placement/move.
        try:
            self.sync_qrs_landmarks_from_all_storage()
        except Exception:
            pass

        try:
            self.update_p_measurements_status()
        except Exception:
            pass

        try:
            self.update_qrs_measurements_status()
        except Exception:
            pass

        for method_name in [
            "update_measurements_panel",
            "update_measurement_summary",
            "update_summary_panel",
        ]:
            try:
                method = getattr(self, method_name, None)
                if callable(method):
                    method()
            except Exception:
                pass

    def get_current_measurement_view_name(self):
        try:
            view_key = self.get_active_view_key()
        except Exception:
            view_key = ""

        if view_key == "template":
            return "Teaching Template ECG"
        if view_key == "filtered":
            return "Filtered ECG 0.5-40 Hz"
        if view_key == "raw":
            return "Raw"
        return str(view_key) if view_key else "--"

    def set_caliper_measurements_text_direct(self, text):
        # The right-side measurement box has changed names during development.
        # Update whichever widget is actually present, but only if it looks like
        # the caliper measurement panel.
        candidate_names = [
            "summary_box",
            "measurements_box",
            "measurement_box",
            "measurements_text",
            "measurement_text",
            "caliper_measurements_box",
            "caliper_measurements_text",
            "results_box",
        ]

        for name in candidate_names:
            widget = getattr(self, name, None)
            if widget is None:
                continue

            try:
                old_text = ""
                if hasattr(widget, "toPlainText"):
                    old_text = widget.toPlainText()
                elif hasattr(widget, "text"):
                    old_text = widget.text()

                # Avoid accidentally changing the log panel.
                if old_text and "ECG Calipers Measurements" not in old_text and "Template method" not in old_text:
                    continue

                if hasattr(widget, "setPlainText"):
                    widget.setPlainText(text)
                    return True

                if hasattr(widget, "setText"):
                    widget.setText(text)
                    return True
            except Exception:
                pass

        # Fallback: scan object attributes for a text widget containing the
        # measurement title.
        try:
            for name, widget in vars(self).items():
                if widget is None:
                    continue

                old_text = ""
                try:
                    if hasattr(widget, "toPlainText"):
                        old_text = widget.toPlainText()
                    elif hasattr(widget, "text"):
                        old_text = widget.text()
                except Exception:
                    continue

                if "ECG Calipers Measurements" not in old_text:
                    continue

                if hasattr(widget, "setPlainText"):
                    widget.setPlainText(text)
                    return True

                if hasattr(widget, "setText"):
                    widget.setText(text)
                    return True
        except Exception:
            pass

        return False

    def rebuild_caliper_measurements_panel(self):
        # Directly rebuild the right-side measurements box from the current
        # marker coordinates. This is intentionally independent of older summary
        # methods, so the box updates after both placement and Ctrl-drag.
        try:
            self.sync_qrs_landmarks_from_all_storage()
        except Exception:
            pass

        lines = []
        lines.append("ECG Calipers Measurements")
        lines.append("")

        try:
            file_name = getattr(self, "current_file_name", None) or getattr(self, "loaded_file_name", None) or "raw.csv"
        except Exception:
            file_name = "raw.csv"

        try:
            channel = getattr(self, "current_channel", None) or getattr(self, "channel_name", None) or "ch1"
        except Exception:
            channel = "ch1"

        lines.append(f"File: {file_name}")
        lines.append(f"Channel: {channel}")
        lines.append(f"View: {self.get_current_measurement_view_name()}")

        try:
            marker_set_name = self.get_active_view_key()
        except Exception:
            marker_set_name = "--"
        lines.append(f"Active marker set: {marker_set_name}")

        try:
            if self.get_active_view_key() == "template":
                lines.append("Teaching-only template; not for diagnosis/research.")
                lines.append("")
                lines.append("Template method:")
                lines.append("1. Filtered ECG is used as the source signal.")
                lines.append("2. R peaks are auto-detected if needed.")
                lines.append("3. R timing = detected R-peak times.")
                lines.append("4. R amplitude = local filtered R peak minus pre-QRS median baseline.")
                lines.append("5. P/Q/S/T are finite teaching shapes placed relative to R and RR.")
                lines.append("6. Relative amplitudes: P≈0.12R, Q≈-0.12R, S≈-0.25R, T≈0.30R.")
                lines.append("7. Baseline is fixed at 0 template units.")
                lines.append("")
        except Exception:
            pass

        try:
            r_count = len(getattr(self, "r_peak_indices", [])) or len(getattr(self, "detected_r_peaks", []))
            if r_count:
                lines.append(f"R peaks detected: {r_count}")
            else:
                lines.append("R: --")
        except Exception:
            lines.append("R: --")

        try:
            baseline = getattr(self, "baseline_value", None)
            if baseline is None:
                lines.append("")
                lines.append("Baseline: not set")
            else:
                lines.append("")
                lines.append(f"Baseline: {float(baseline):.4f} raw units")
        except Exception:
            lines.append("")
            lines.append("Baseline: --")

        # P wave
        try:
            p_on = self.find_any_p_landmark_xy("onset")
        except Exception:
            p_on = None
        try:
            p_pk = self.find_any_p_landmark_xy("peak")
        except Exception:
            p_pk = None
        try:
            p_off = self.find_any_p_landmark_xy("offset")
        except Exception:
            p_off = None

        lines.append("")
        lines.append("P-wave calipers")
        lines.append(f"P onset: {p_on[0]:.4f} s" if p_on else "P onset: --")
        lines.append(f"P peak: {p_pk[0]:.4f} s" if p_pk else "P peak: --")
        lines.append(f"P offset: {p_off[0]:.4f} s" if p_off else "P offset: --")

        if p_on and p_off:
            try:
                lines.append(f"P duration: {(float(p_off[0]) - float(p_on[0])) * 1000.0:.1f} ms")
            except Exception:
                pass

        try:
            baseline = getattr(self, "baseline_value", None)
            if baseline is not None and p_pk:
                lines.append(f"P amplitude: {float(p_pk[1]) - float(baseline):.4f}")
        except Exception:
            pass

        # QRS / ST
        try:
            qrs_on = self.get_qrs_landmark_xy("qrs_onset")
        except Exception:
            qrs_on = None
        try:
            q_nadir = self.get_qrs_landmark_xy("q_nadir")
        except Exception:
            q_nadir = None
        try:
            s_nadir = self.get_qrs_landmark_xy("s_nadir")
        except Exception:
            s_nadir = None
        try:
            j_point = self.get_qrs_landmark_xy("j_point")
        except Exception:
            j_point = None

        lines.append("")
        lines.append("QRS / ST calipers")
        lines.append(f"QRS onset: {qrs_on[0]:.4f} s" if qrs_on else "QRS onset: --")
        lines.append(f"Q nadir: {q_nadir[0]:.4f} s" if q_nadir else "Q nadir: --")
        lines.append(f"S nadir: {s_nadir[0]:.4f} s" if s_nadir else "S nadir: --")
        lines.append(f"J point: {j_point[0]:.4f} s" if j_point else "J point: --")

        if qrs_on and j_point:
            try:
                lines.append(f"QRS duration: {(float(j_point[0]) - float(qrs_on[0])) * 1000.0:.1f} ms")
            except Exception:
                pass

        if p_on and qrs_on:
            try:
                lines.append(f"PR interval: {(float(qrs_on[0]) - float(p_on[0])) * 1000.0:.1f} ms")
            except Exception:
                pass

        if p_off and qrs_on:
            try:
                lines.append(f"PR segment: {(float(qrs_on[0]) - float(p_off[0])) * 1000.0:.1f} ms")
            except Exception:
                pass

        try:
            baseline = getattr(self, "baseline_value", None)
            if baseline is not None:
                if q_nadir:
                    lines.append(f"Q deflection: {float(q_nadir[1]) - float(baseline):.4f}")
                if s_nadir:
                    lines.append(f"S deflection: {float(s_nadir[1]) - float(baseline):.4f}")
        except Exception:
            pass

        text = "\n".join(lines)
        self.set_caliper_measurements_text_direct(text)

    def refresh_all_caliper_measurements(self):
        # One safe refresh point after marker placement/movement.
        try:
            self.sync_qrs_landmarks_from_all_storage()
        except Exception:
            pass

        try:
            self.update_p_measurements_status()
        except Exception:
            pass

        try:
            self.update_qrs_measurements_status()
        except Exception:
            pass

        try:
            self.rebuild_caliper_measurements_panel()
        except Exception:
            pass

    def get_qrs_landmark_xy(self, kind):
        try:
            if not getattr(self, "_syncing_qrs_landmarks", False):
                self._syncing_qrs_landmarks = True
                try:
                    self.sync_qrs_landmarks_from_all_storage()
                finally:
                    self._syncing_qrs_landmarks = False
        except Exception:
            self._syncing_qrs_landmarks = False

        kind = str(kind).lower()

        variants = {
            "qrs_onset": [
                "qrs_onset", "qrs onset", "QRS onset",
                "q_onset", "q onset", "Q onset",
                "qrs_start", "qrs start", "QRS start",
            ],
            "q_nadir": [
                "q_nadir", "q nadir", "Q nadir",
                "q_point", "q point", "Q point", "Q",
            ],
            "s_nadir": [
                "s_nadir", "s nadir", "S nadir",
                "s_point", "s point", "S point", "S",
            ],
            "j_point": [
                "j_point", "j point", "J point", "J",
                "qrs_offset", "qrs offset", "QRS offset",
                "qrs_end", "qrs end", "QRS end",
            ],
        }.get(kind, [])

        return self.get_landmark_xy_by_variants(variants)


    def store_qrs_landmark(self, kind, x, y):
        # Store QRS/ST caliper positions in the same per-view structure used by
        # the other ECG calipers. This is required for click-drag repositioning.
        kind = str(kind).lower()

        standard_key = {
            "qrs_onset": "qrs_onset",
            "q_nadir": "q_nadir",
            "s_nadir": "s_nadir",
            "j_point": "j_point",
        }.get(kind)

        if standard_key is None:
            return

        value = (float(x), float(y))

        if not hasattr(self, "landmarks") or self.landmarks is None:
            self.landmarks = {}

        self.landmarks[standard_key] = value

        try:
            view_key = self.get_active_view_key()
            if hasattr(self, "marker_sets"):
                if view_key not in self.marker_sets or not isinstance(self.marker_sets[view_key], dict):
                    self.marker_sets[view_key] = {}
                self.marker_sets[view_key][standard_key] = value
        except Exception:
            pass

        # Also update common display-name keys if they already exist.
        alternate_keys = {
            "qrs_onset": ["QRS onset", "qrs onset", "q_onset", "Q onset", "q onset"],
            "q_nadir": ["Q nadir", "q nadir", "Q point", "q point"],
            "s_nadir": ["S nadir", "s nadir", "S point", "s point"],
            "j_point": ["J point", "j point", "QRS offset", "qrs_offset", "qrs offset"],
        }.get(kind, [])

        try:
            for key in alternate_keys:
                if key in self.landmarks:
                    self.landmarks[key] = value

            view_key = self.get_active_view_key()
            if hasattr(self, "marker_sets") and isinstance(self.marker_sets, dict):
                d = self.marker_sets.get(view_key, None)
                if isinstance(d, dict):
                    for key in alternate_keys:
                        if key in d:
                            d[key] = value
        except Exception:
            pass

    def clear_qrs_landmarks(self):
        keys_to_remove = [
            "qrs_onset", "QRS onset", "q onset", "Q onset",
            "q_nadir", "Q nadir", "q point", "Q point",
            "s_nadir", "S nadir", "s point", "S point",
            "j_point", "J point", "qrs_offset", "QRS offset",
        ]

        try:
            for key in keys_to_remove:
                if hasattr(self, "landmarks") and isinstance(self.landmarks, dict):
                    self.landmarks.pop(key, None)

            view_key = self.get_active_view_key()
            if hasattr(self, "marker_sets") and isinstance(self.marker_sets, dict):
                d = self.marker_sets.get(view_key, None)
                if isinstance(d, dict):
                    for key in keys_to_remove:
                        d.pop(key, None)
        except Exception:
            pass

        if hasattr(self, "qrs_status_label"):
            self.qrs_status_label.setText("QRS: cleared")

        try:
            self.redraw_plot_with_r_peaks()
        except Exception:
            try:
                self.refresh_plot()
            except Exception:
                pass

        self.update_qrs_measurements_status()

    def qrs_marker_style(self, name):
        try:
            is_template = self.get_active_view_key() == "template"
        except Exception:
            is_template = False

        if is_template:
            return {
                "brush": "#FFD54F",
                "pen": "#111111",
                "text": "#FFE082",
            }

        styles = {
            "QRS onset": {"brush": "#00E5FF", "pen": "#00131A", "text": "#B2EBF2"},
            "Q nadir": {"brush": "#7C4DFF", "pen": "#FFFFFF", "text": "#D1C4E9"},
            "S nadir": {"brush": "#FF4FD8", "pen": "#FFFFFF", "text": "#F8BBD0"},
            "J point": {"brush": "#00C853", "pen": "#FFFFFF", "text": "#B9F6CA"},
        }
        return styles.get(name, {"brush": "#00C853", "pen": "#FFFFFF", "text": "#B9F6CA"})

    def draw_qrs_markers(self):
        marker_defs = [
            ("qrs_onset", "QRS onset", "t"),
            ("q_nadir", "Q", "o"),
            ("s_nadir", "S", "o"),
            ("j_point", "J", "t1"),
        ]

        full_names = {
            "qrs_onset": "QRS onset",
            "q_nadir": "Q nadir",
            "s_nadir": "S nadir",
            "j_point": "J point",
        }

        for kind, label, symbol in marker_defs:
            xy = self.get_qrs_landmark_xy(kind)
            if xy is None:
                continue

            x0, y0 = xy
            style = self.qrs_marker_style(full_names.get(kind, label))

            try:
                item = self.plot.plot(
                    [float(x0)],
                    [float(y0)],
                    pen=None,
                    symbol=symbol,
                    symbolSize=15,
                    symbolBrush=pg.mkBrush(style["brush"]),
                    symbolPen=pg.mkPen(style["pen"], width=2),
                    name=f"QRS marker {label}"
                )
                try:
                    item.setZValue(70)
                except Exception:
                    pass

                txt = pg.TextItem(label, color=style["text"], anchor=(0.5, 1.35))
                txt.setPos(float(x0), float(y0))
                txt.setZValue(75)
                self.plot.addItem(txt)
            except Exception:
                pass

    def update_qrs_measurements_status(self):
        onset = self.get_qrs_landmark_xy("qrs_onset")
        q = self.get_qrs_landmark_xy("q_nadir")
        s = self.get_qrs_landmark_xy("s_nadir")
        j = self.get_qrs_landmark_xy("j_point")

        parts = []

        if onset and j:
            qrs_ms = (float(j[0]) - float(onset[0])) * 1000.0
            parts.append(f"QRS {qrs_ms:.1f} ms")
        else:
            count = sum(x is not None for x in [onset, q, s, j])
            parts.append(f"QRS: {count}/4 set" if count else "QRS: --")

        if self.baseline_value is not None:
            try:
                baseline = float(self.baseline_value)
                if q:
                    parts.append(f"Q {float(q[1]) - baseline:.3f}")
                if s:
                    parts.append(f"S {float(s[1]) - baseline:.3f}")
            except Exception:
                pass

        if hasattr(self, "qrs_status_label"):
            self.qrs_status_label.setText(" | ".join(parts))

        try:
            self.update_measurement_summary()
        except Exception:
            pass

    def append_qrs_summary_lines(self, lines):
        onset = self.get_qrs_landmark_xy("qrs_onset")
        q = self.get_qrs_landmark_xy("q_nadir")
        s = self.get_qrs_landmark_xy("s_nadir")
        j = self.get_qrs_landmark_xy("j_point")

        lines.append("")
        lines.append("QRS / ST calipers")
        lines.append(f"QRS onset: {onset[0]:.4f} s" if onset else "QRS onset: --")
        lines.append(f"Q nadir: {q[0]:.4f} s" if q else "Q nadir: --")
        lines.append(f"S nadir: {s[0]:.4f} s" if s else "S nadir: --")
        lines.append(f"J point: {j[0]:.4f} s" if j else "J point: --")

        if onset and j:
            qrs_ms = (float(j[0]) - float(onset[0])) * 1000.0
            lines.append(f"QRS duration: {qrs_ms:.1f} ms")

        p_onset = None
        p_offset = None
        try:
            p_onset = self.find_any_p_landmark_xy("onset")
            p_offset = self.find_any_p_landmark_xy("offset")
        except Exception:
            pass

        if p_onset and onset:
            pr_ms = (float(onset[0]) - float(p_onset[0])) * 1000.0
            lines.append(f"PR interval: {pr_ms:.1f} ms")

        if p_offset and onset:
            pr_seg_ms = (float(onset[0]) - float(p_offset[0])) * 1000.0
            lines.append(f"PR segment: {pr_seg_ms:.1f} ms")

        if self.baseline_value is not None:
            try:
                baseline = float(self.baseline_value)
                if q:
                    lines.append(f"Q deflection from baseline: {float(q[1]) - baseline:.4f}")
                if s:
                    lines.append(f"S deflection from baseline: {float(s[1]) - baseline:.4f}")
            except Exception:
                pass

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

        # Teaching Template ECG already has an inherent straight baseline at 0.
        # Do not draw the blue draggable/reference baseline line in this mode.
        try:
            if self.get_active_view_key() == "template":
                self.baseline_line = None
                return
        except Exception:
            pass

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
        self.save_current_baseline_to_view()
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
                self.save_current_baseline_to_view()
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
