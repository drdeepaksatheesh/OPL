# app/ecg_calipers_panel.py

import csv
from pathlib import Path

import numpy as np
import pyqtgraph as pg

from analysis.peak_detection import detect_ecg_r_peaks

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout,
    QGroupBox, QTextEdit, QFileDialog, QComboBox, QCheckBox
)
from PyQt5.QtCore import Qt


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

        self.detected_r_peaks = np.array([], dtype=int)
        self.r_peak_detection_result = None
        self.selected_peak_number = None

        self.baseline_value = None
        self.baseline_set_mode = False
        self.baseline_line = None

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        title = QLabel("OpenPhysiologyLab ECG Calipers")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(title)

        subtitle = QLabel(
            "Beat-wise ECG morphology measurement using manual calipers. "
            "Raw/filtered viewing first; PQRST calipers will be added next."
        )
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        source_group = QGroupBox("Recording Source")
        source_layout = QHBoxLayout(source_group)

        self.use_latest_btn = QPushButton("Use Latest Recording")
        self.load_folder_btn = QPushButton("Load Recording Folder")
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

        layout.addWidget(source_group)

        controls_group = QGroupBox("View Controls")
        controls_layout = QHBoxLayout(controls_group)

        controls_layout.addWidget(QLabel("Channel:"))
        self.channel_box = QComboBox()
        self.channel_box.currentIndexChanged.connect(self.refresh_plot)
        controls_layout.addWidget(self.channel_box)

        controls_layout.addWidget(QLabel("View:"))
        self.view_box = QComboBox()
        self.view_box.addItems(["Raw", "Filtered ECG 0.5-40 Hz"])
        self.view_box.currentIndexChanged.connect(self.refresh_plot)
        controls_layout.addWidget(self.view_box)

        self.notch_box = QCheckBox("50 Hz notch")
        self.notch_box.setChecked(True)
        self.notch_box.stateChanged.connect(self.refresh_plot)
        controls_layout.addWidget(self.notch_box)

        self.reset_view_btn = QPushButton("Reset View")
        self.reset_view_btn.clicked.connect(self.reset_plot_view)
        controls_layout.addWidget(self.reset_view_btn)

        controls_layout.addStretch(1)
        layout.addWidget(controls_group)

        rpeak_group = QGroupBox("R Peak Reference")
        rpeak_layout = QHBoxLayout(rpeak_group)

        self.detect_r_btn = QPushButton("Detect R Peaks")
        self.detect_r_btn.setToolTip(
            "Use the same ECG R-peak detector used by Analysis as the internal beat reference."
        )
        self.detect_r_btn.clicked.connect(self.detect_r_peaks_clicked)

        self.prev_beat_btn = QPushButton("< Previous Beat")
        self.prev_beat_btn.clicked.connect(self.previous_beat_clicked)

        self.next_beat_btn = QPushButton("Next Beat >")
        self.next_beat_btn.clicked.connect(self.next_beat_clicked)

        self.rpeak_status_label = QLabel("R peaks: not detected")
        self.rpeak_status_label.setWordWrap(True)

        rpeak_layout.addWidget(self.detect_r_btn)
        rpeak_layout.addWidget(self.prev_beat_btn)
        rpeak_layout.addWidget(self.next_beat_btn)
        rpeak_layout.addWidget(self.rpeak_status_label, stretch=1)

        layout.addWidget(rpeak_group)

        baseline_group = QGroupBox("Baseline Reference")
        baseline_layout = QHBoxLayout(baseline_group)

        self.set_baseline_btn = QPushButton("Set Baseline")
        self.set_baseline_btn.setToolTip(
            "Click this, then click the isoelectric baseline on the ECG plot."
        )
        self.set_baseline_btn.clicked.connect(self.set_baseline_mode_clicked)

        self.clear_baseline_btn = QPushButton("Clear Baseline")
        self.clear_baseline_btn.clicked.connect(self.clear_baseline_clicked)

        self.baseline_status_label = QLabel(
            "Baseline: not set. Amplitudes should be measured relative to the isoelectric baseline, not y-axis zero."
        )
        self.baseline_status_label.setWordWrap(True)

        baseline_layout.addWidget(self.set_baseline_btn)
        baseline_layout.addWidget(self.clear_baseline_btn)
        baseline_layout.addWidget(self.baseline_status_label, stretch=1)

        layout.addWidget(baseline_group)

        view_group = QGroupBox("Signal View")
        view_layout = QVBoxLayout(view_group)

        self.plot = pg.PlotWidget()
        self.plot.setLabel("bottom", "Time", units="s")
        self.plot.setLabel("left", "Amplitude", units="raw units")
        self.plot.showGrid(x=True, y=True, alpha=0.25)
        self.plot.setBackground("#0B1020")
        self.plot.getPlotItem().setTitle("Load raw.csv to view ECG signal")

        # ECG Calipers navigation rule:
        # allow horizontal ECG browsing, but avoid accidental vertical/pinch runaway.
        self.plot.setMouseEnabled(x=True, y=False)
        self.plot.getPlotItem().getViewBox().setMenuEnabled(False)
        self.plot.scene().sigMouseClicked.connect(self.plot_clicked)

        view_layout.addWidget(self.plot, stretch=1)

        layout.addWidget(view_group, stretch=1)

        info_group = QGroupBox("ECG Calipers Status")
        info_layout = QVBoxLayout(info_group)

        self.info_box = QTextEdit()
        self.info_box.setReadOnly(True)
        self.info_box.setMinimumHeight(150)
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
            "- manual PQRST caliper markers\n"
            "- RR before and RR after selected beat\n"
            "- beat_measurements.csv export\n\n"
            "Safety: This is for education and experimentation, not diagnosis."
        )
        info_layout.addWidget(self.info_box)

        layout.addWidget(info_group)

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
        self.rpeak_status_label.setText("R peaks: not detected")

        self.baseline_value = None
        self.baseline_set_mode = False
        self.baseline_line = None
        self.baseline_status_label.setText(
            "Baseline: not set. Amplitudes should be measured relative to the isoelectric baseline, not y-axis zero."
        )

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

    def refresh_plot(self):
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
        self.rpeak_status_label.setText("R peaks: not detected")

        self.baseline_value = None
        self.baseline_set_mode = False
        self.baseline_line = None
        self.baseline_status_label.setText(
            "Baseline: not set. Amplitudes should be measured relative to the isoelectric baseline, not y-axis zero."
        )

        self.plot.clear()
        self.plot.plot(t, y, pen=pg.mkPen("#FFC400", width=1))
        self.draw_baseline_line()
        self.plot.setLabel("bottom", "Time", units="s")
        self.plot.setLabel("left", "Amplitude", units="raw units")
        self.plot.getPlotItem().setTitle(f"ECG Calipers: {ch} | {self.current_display_label}")

        duration = float(t[-1] - t[0])
        fs = self.estimate_fs(t)
        y_min = float(np.nanmin(y))
        y_max = float(np.nanmax(y))

        self.apply_timebase_limits(t, y)


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
            self.rpeak_status_label.setText("R peaks: 0 detected")
            self.info_box.setText(
                "R peak detection completed, but no R peaks were found.\n\n"
                f"Polarity: {result.get('polarity')}\n"
                f"Polarity source: {result.get('polarity_source')}\n"
                f"Warning: {warning}"
            )
            self.redraw_plot_with_r_peaks()
            return

        self.selected_peak_number = 0
        self.redraw_plot_with_r_peaks()

        rr = np.diff(t[peaks]) if len(peaks) >= 2 else np.asarray([], dtype=float)
        mean_hr = 60.0 / float(np.nanmean(rr)) if len(rr) > 0 and np.nanmean(rr) > 0 else np.nan

        self.rpeak_status_label.setText(
            f"R peaks: {len(peaks)} | selected beat: 1/{len(peaks)}"
        )

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
        self.plot.plot(t, y, pen=pg.mkPen("#FFC400", width=1))
        self.draw_baseline_line()

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
                    symbolBrush=pg.mkBrush("#FF1744"),
                    symbolPen=pg.mkPen("#FFFFFF", width=1),
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

    def set_baseline_mode_clicked(self):
        if self.current_plot_t is None or self.current_plot_y is None:
            self.info_box.setText("Load raw.csv and display a signal before setting baseline.")
            return

        self.baseline_set_mode = True
        self.baseline_status_label.setText(
            "Baseline set mode: click the isoelectric baseline on the ECG plot."
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
            "Baseline: not set. Amplitudes should be measured relative to the isoelectric baseline, not y-axis zero."
        )

        if self.current_plot_t is not None and self.current_plot_y is not None:
            self.redraw_plot_with_r_peaks()

        self.info_box.setText(
            "Baseline reference cleared.\n\n"
            "Set a baseline before interpreting P, R, T amplitudes or ST level."
        )

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
            f"Baseline set at {value:.4f} raw units. Drag the blue dashed line for fine tuning."
        )

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
                    f"Baseline set at {clicked_y:.4f} raw units. Drag the blue dashed line for fine tuning."
                )
                self.redraw_plot_with_r_peaks()
                self.info_box.setText(
                    "Baseline reference set.\n\n"
                    f"Baseline value: {clicked_y:.4f} raw units\n\n"
                    "Teaching note: ECG positivity is relative to this isoelectric baseline, not necessarily the plot's y-axis zero."
                )
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

            self.redraw_plot_with_r_peaks()
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

        self.redraw_plot_with_r_peaks()
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

        self.redraw_plot_with_r_peaks()
        self.update_selected_beat_status()

    def update_selected_beat_status(self):
        if len(self.detected_r_peaks) == 0 or self.selected_peak_number is None:
            self.rpeak_status_label.setText("R peaks: not detected")
            return

        self.rpeak_status_label.setText(
            f"R peaks: {len(self.detected_r_peaks)} | "
            f"selected beat: {int(self.selected_peak_number) + 1}/{len(self.detected_r_peaks)}"
        )

        self.info_box.setText(
            "Selected R peak updated.\n\n"
            f"{self.selected_beat_context_text()}\n\n"
            "Click near any green R peak to select it. Next stage: zoom the display to previous-selected-next ECG complexes."
        )

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
        """
        Keep ECG Calipers plot navigation bounded to the recording timebase.

        If set_full_view is True, reset to the full recording.
        If False, only update limits and preserve the current zoom/pan.
        """
        if t is None or y is None:
            return

        t = np.asarray(t, dtype=float)
        y = np.asarray(y, dtype=float)

        valid = np.isfinite(t) & np.isfinite(y)
        if valid.sum() < 3:
            return

        t = t[valid]
        y = y[valid]

        t_min = float(np.nanmin(t))
        t_max = float(np.nanmax(t))
        y_min = float(np.nanmin(y))
        y_max = float(np.nanmax(y))

        duration = max(t_max - t_min, 0.001)
        y_span = max(y_max - y_min, 1.0)
        y_pad = 0.10 * y_span

        view_box = self.plot.getPlotItem().getViewBox()

        view_box.setLimits(
            xMin=t_min,
            xMax=t_max,
            yMin=y_min - y_pad,
            yMax=y_max + y_pad,
            minXRange=0.20,
            maxXRange=duration,
            minYRange=max(y_span * 0.05, 1.0),
            maxYRange=y_span + 2 * y_pad,
        )

        if set_full_view:
            # Full-recording view by default, using the same time base as Recorder/Analysis.
            self.plot.setXRange(t_min, t_max, padding=0)
            self.plot.setYRange(y_min - y_pad, y_max + y_pad, padding=0)

    def reset_plot_view(self):
        if self.current_plot_t is not None and self.current_plot_y is not None:
            self.apply_timebase_limits(self.current_plot_t, self.current_plot_y, set_full_view=True)
        else:
            self.plot.enableAutoRange()
