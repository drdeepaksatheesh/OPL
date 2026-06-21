# app/analysis_panel.py

from pathlib import Path

import csv
import json
import shutil
from datetime import datetime

import numpy as np

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QTextEdit, QFileDialog, QCheckBox, QDoubleSpinBox,
    QSplitter, QFrame, QGroupBox, QMessageBox, QInputDialog
)

from PyQt5.QtCore import Qt, QTimer, pyqtSignal, pyqtSignal

import pyqtgraph as pg

from analysis.recording_loader import load_recording_folder, summarize_recording
from analysis.signal_filters import apply_bandpass_notch
from analysis.peak_detection import detect_ecg_r_peaks, detect_general_peaks
from analysis.signal_quality import assess_signal_quality, build_provenance_report
from analysis.selection_metrics import (
    calculate_selection_metrics,
    format_selection_metrics_text
)


TIME_WINDOWS = [2, 5, 10, 20, 30, 60]


class TimeAxisItem(pg.AxisItem):
    def tickStrings(self, values, scale, spacing):
        labels = []

        for value in values:
            try:
                seconds = float(value)
            except Exception:
                labels.append("")
                continue

            if seconds < 0:
                seconds = 0.0

            minutes = int(seconds // 60)
            whole_seconds = int(seconds % 60)

            labels.append(f"{minutes:02d}:{whole_seconds:02d}")

        return labels


class SelectionViewBox(pg.ViewBox):
    """
    ViewBox supporting:
    - click to set cursor
    - click-drag to create selection
    """

    def __init__(self, plot_name, click_callback=None, selection_callback=None):
        super().__init__(enableMenu=False)

        self.plot_name = plot_name
        self.click_callback = click_callback
        self.selection_callback = selection_callback
        self.drag_anchor_x = None
        self.drag_moved = False

    def mouseDragEvent(self, event, axis=None):
        if event.button() == Qt.LeftButton and self.selection_callback is not None:
            event.accept()

            if event.isStart():
                start_point = self.mapSceneToView(event.buttonDownScenePos())
                self.drag_anchor_x = float(start_point.x())
                self.drag_moved = False

            if self.drag_anchor_x is None:
                start_point = self.mapSceneToView(event.buttonDownScenePos())
                self.drag_anchor_x = float(start_point.x())

            current_point = self.mapSceneToView(event.scenePos())
            current_x = float(current_point.x())

            if abs(current_x - self.drag_anchor_x) > 0.005:
                self.drag_moved = True

            self.selection_callback(
                plot_name=self.plot_name,
                anchor_x=self.drag_anchor_x,
                current_x=current_x,
                finished=event.isFinish()
            )

            if event.isFinish():
                self.drag_anchor_x = None

            return

        super().mouseDragEvent(event, axis=axis)

    def mouseClickEvent(self, event):
        if event.button() == Qt.LeftButton and self.click_callback is not None:
            event.accept()

            point = self.mapSceneToView(event.scenePos())
            x = float(point.x())

            self.click_callback(x, self.plot_name)
            return

        super().mouseClickEvent(event)


class ScrubbablePlotWidget(pg.PlotWidget):
    """
    Locked plot widget with two-finger horizontal scrub.
    """

    def __init__(self, scrub_callback=None, click_callback=None, selection_callback=None, plot_name=None):
        self.view_box = SelectionViewBox(
            plot_name=plot_name,
            click_callback=click_callback,
            selection_callback=selection_callback
        )

        axis_items = {
            "bottom": TimeAxisItem(orientation="bottom")
        }

        super().__init__(viewBox=self.view_box, axisItems=axis_items)

        self.scrub_callback = scrub_callback
        self.plot_name = plot_name

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

        event.accept()


class AnalysisPanel(QWidget):
    open_results_requested = pyqtSignal(str)

    def __init__(self):
        super().__init__()

        self.recording = None
        self.recording_is_temporary = False
        self.latest_analysis_report_path = None

        self.current_raw_t = None
        self.current_raw_y = None
        self.current_analysis_y = None
        self.current_channel = None

        self.detected_peaks = None
        self.peak_result = None
        self.current_metrics = None

        self.cursor_time_s = None
        self.cursor_items = []

        self.active_selection = None
        self.selection_regions = {}

        self.edge_scroll_timer = QTimer()
        self.edge_scroll_timer.timeout.connect(self.perform_edge_scroll_selection)
        self.edge_scroll_active = False
        self.edge_scroll_direction = 0
        self.edge_scroll_anchor_x = None
        self.edge_scroll_current_x = None
        self.edge_scroll_plot_name = None
        self.edge_scroll_speed_factor = 1.0
        self.edge_scroll_speed_factor = 1.0

        self.current_filter_signature = None

        self.view_x_min = 0.0
        self.view_window_s = 60.0
        self.view_all = False
        self.all_mode_scrub_window_s = 60.0
        self.time_window_index = TIME_WINDOWS.index(60)

        self.y_ranges = {
            "raw": None,
            "analysis": None,
            "rr": None
        }

        self.setWindowTitle("OpenPhysiologyLab Analysis Panel")

        layout = QVBoxLayout()
        self.setLayout(layout)

        title = QLabel("OpenPhysiologyLab Analysis Panel")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #F2F2F4; padding: 2px;")
        layout.addWidget(title)

        self.recording_info_label = QLabel("No recording loaded | Load a recording folder to begin")
        self.recording_info_label.setStyleSheet("font-weight: bold; color: #D4AF37; padding: 5px; background-color: #0E1218; border: 1px solid #202630;")
        self.recording_info_label.setWordWrap(True)
        layout.addWidget(self.recording_info_label)

        # ------------------------------------------------------------
        # Prominent Results shortcut
        # ------------------------------------------------------------

        results_shortcut_row = QHBoxLayout()
        results_shortcut_row.setSpacing(8)

        self.top_results_btn = QPushButton("Go to Results / Update Report")
        self.top_results_btn.setObjectName("topResultsButton")
        self.top_results_btn.setMinimumHeight(30)
        self.top_results_btn.setMinimumWidth(230)
        self.top_results_btn.setToolTip(
            "Save or update the current analysis report, then open that exact report in the Results tab."
        )
        self.top_results_btn.clicked.connect(self.go_to_results_clicked)
        results_shortcut_row.addWidget(self.top_results_btn)

        self.results_hint_label = QLabel(
            "Use after Analyse. Results tab reads saved analysis_report.json; it does not recalculate."
        )
        self.results_hint_label.setWordWrap(True)
        self.results_hint_label.setStyleSheet(
            "color: #8F96A6; background-color: transparent; padding-left: 6px;"
        )
        results_shortcut_row.addWidget(self.results_hint_label, stretch=1)

        layout.addLayout(results_shortcut_row)

        # ------------------------------------------------------------
        # Grouped professional control ribbon
        # ------------------------------------------------------------

        def make_group(title):
            group = QGroupBox(title)
            group_layout = QHBoxLayout()
            group_layout.setContentsMargins(8, 12, 8, 8)
            group_layout.setSpacing(6)
            group.setLayout(group_layout)
            return group, group_layout

        ribbon_row_1 = QHBoxLayout()
        ribbon_row_1.setSpacing(8)

        # ----------------------------
        # File group
        # ----------------------------

        file_group, file_layout = make_group("File")

        self.load_btn = QPushButton("Load")
        self.load_btn.setMinimumWidth(95)
        self.load_btn.setToolTip("Load an existing OpenPhysioLab recording folder.")
        self.load_btn.clicked.connect(self.load_recording_clicked)
        file_layout.addWidget(self.load_btn)

        ribbon_row_1.addWidget(file_group)

        # ----------------------------
        # Signal group
        # ----------------------------

        signal_group, signal_layout = make_group("Signal")

        signal_layout.addWidget(QLabel("Ch"))

        self.channel_box = QComboBox()
        self.channel_box.setMinimumWidth(90)
        self.channel_box.currentIndexChanged.connect(self.channel_changed)
        signal_layout.addWidget(self.channel_box)

        signal_layout.addWidget(QLabel("Mode"))

        self.mode_box = QComboBox()
        self.mode_box.addItems(["ECG", "GENERAL"])
        self.mode_box.setMinimumWidth(95)
        signal_layout.addWidget(self.mode_box)

        signal_layout.addWidget(QLabel("Polarity"))

        self.peak_polarity_box = QComboBox()
        self.peak_polarity_box.addItems(["Auto", "Positive", "Negative"])
        self.peak_polarity_box.setMinimumWidth(95)
        self.peak_polarity_box.setToolTip(
            "Auto compares upward and downward QRS-like peak trains. "
            "Positive detects upward peaks. Negative detects downward peaks."
        )
        signal_layout.addWidget(self.peak_polarity_box)

        self.invert_checkbox = QCheckBox("Invert")
        self.invert_checkbox.setToolTip(
            "Invert display/analysis polarity. raw.csv remains unchanged."
        )
        self.invert_checkbox.stateChanged.connect(self.signal_display_setting_changed)
        signal_layout.addWidget(self.invert_checkbox)

        ribbon_row_1.addWidget(signal_group)

        # ----------------------------
        # Filter group
        # ----------------------------

        filter_group, filter_layout = make_group("Filter")

        self.apply_filter_btn = QPushButton("Apply")
        self.apply_filter_btn.setMinimumWidth(75)
        self.apply_filter_btn.setToolTip(
            "Apply current Low/High/50 Hz settings to raw.csv data and update the filtered monitor."
        )
        self.apply_filter_btn.clicked.connect(self.apply_filter_clicked)
        filter_layout.addWidget(self.apply_filter_btn)

        filter_layout.addWidget(QLabel("Lo"))

        self.low_spin = QDoubleSpinBox()
        self.low_spin.setRange(0.1, 500.0)
        self.low_spin.setValue(0.5)
        self.low_spin.setSingleStep(0.5)
        self.low_spin.setMinimumWidth(70)
        filter_layout.addWidget(self.low_spin)

        filter_layout.addWidget(QLabel("Hi"))

        self.high_spin = QDoubleSpinBox()
        self.high_spin.setRange(1.0, 1000.0)
        self.high_spin.setValue(40.0)
        self.high_spin.setSingleStep(5.0)
        self.high_spin.setMinimumWidth(75)
        filter_layout.addWidget(self.high_spin)

        self.notch_checkbox = QCheckBox("50 Hz")
        self.notch_checkbox.setChecked(True)
        self.notch_checkbox.setToolTip("Apply 50 Hz notch filter to filtered/analysis signal.")
        filter_layout.addWidget(self.notch_checkbox)

        ribbon_row_1.addWidget(filter_group)

        # ----------------------------
        # Peaks group
        # ----------------------------

        peaks_group, peaks_layout = make_group("Peaks")

        self.detect_btn = QPushButton("Detect R")
        self.detect_btn.setMinimumWidth(95)
        self.detect_btn.setToolTip(
            "Detect or remove R peaks. Detection is performed on filtered-from-raw signal."
        )
        self.detect_btn.clicked.connect(self.detect_r_peaks_clicked)
        peaks_layout.addWidget(self.detect_btn)

        self.add_peak_btn = QPushButton("Add")
        self.add_peak_btn.setMinimumWidth(70)
        self.add_peak_btn.setToolTip("Add the nearest local R peak around the blue cursor.")
        self.add_peak_btn.clicked.connect(self.add_peak_near_cursor)
        peaks_layout.addWidget(self.add_peak_btn)

        self.remove_peak_btn = QPushButton("Remove")
        self.remove_peak_btn.setMinimumWidth(85)
        self.remove_peak_btn.setToolTip("Remove the detected R peak nearest to the blue cursor.")
        self.remove_peak_btn.clicked.connect(self.remove_peak_near_cursor)
        peaks_layout.addWidget(self.remove_peak_btn)

        ribbon_row_1.addWidget(peaks_group)

        # ----------------------------
        # Analysis group
        # ----------------------------

        analysis_group, analysis_layout = make_group("Analysis")

        self.analyse_btn = QPushButton("Analyse")
        self.analyse_btn.setMinimumWidth(90)
        self.analyse_btn.setToolTip("Calculate HR, RR, and HRV-style metrics using the current peak list.")
        self.analyse_btn.clicked.connect(self.analyse_clicked)
        analysis_layout.addWidget(self.analyse_btn)

        self.quality_btn = QPushButton("Quality")
        self.quality_btn.setMinimumWidth(90)
        self.quality_btn.setToolTip("Show signal quality flags and analysis provenance.")
        self.quality_btn.clicked.connect(self.show_quality_provenance_clicked)
        analysis_layout.addWidget(self.quality_btn)

        ribbon_row_1.addWidget(analysis_group)

        # ----------------------------
        # Export group
        # ----------------------------

        export_group, export_layout = make_group("Export")

        self.save_analysis_btn = QPushButton("Save")
        self.save_analysis_btn.setMinimumWidth(80)
        self.save_analysis_btn.setToolTip("Save analysis outputs inside the recording folder.")
        self.save_analysis_btn.clicked.connect(self.save_analysis_clicked)
        export_layout.addWidget(self.save_analysis_btn)

        self.go_results_btn = QPushButton("Results")
        self.go_results_btn.setMinimumWidth(85)
        self.go_results_btn.setToolTip(
            "Save/update the current analysis report, then open it in the Results tab."
        )
        self.go_results_btn.clicked.connect(self.go_to_results_clicked)
        export_layout.addWidget(self.go_results_btn)

        ribbon_row_1.addWidget(export_group)

        ribbon_row_1.addStretch()
        layout.addLayout(ribbon_row_1)

        # ------------------------------------------------------------
        # Navigation / Selection / Amplitude ribbon
        # ------------------------------------------------------------

        ribbon_row_2 = QHBoxLayout()
        ribbon_row_2.setSpacing(8)

        nav_group, nav_layout = make_group("Navigation")

        nav_layout.addWidget(QLabel("Time"))

        self.time_window_btn = QPushButton("10s")
        self.time_window_btn.setMinimumWidth(55)
        self.time_window_btn.setToolTip(
            "Click to cycle time window: 2 s → 5 s → 10 s → 20 s → 30 s → 60 s"
        )
        self.time_window_btn.clicked.connect(self.cycle_time_window)
        nav_layout.addWidget(self.time_window_btn)

        self.btn_start = QPushButton("|◀")
        self.btn_start.setMinimumWidth(38)
        self.btn_start.setToolTip("Go to start")
        self.btn_start.clicked.connect(self.go_to_start)
        nav_layout.addWidget(self.btn_start)

        self.btn_back = QPushButton("◀")
        self.btn_back.setMinimumWidth(38)
        self.btn_back.setToolTip("Step backward")
        self.btn_back.clicked.connect(self.step_backward)
        nav_layout.addWidget(self.btn_back)

        self.btn_forward = QPushButton("▶")
        self.btn_forward.setMinimumWidth(38)
        self.btn_forward.setToolTip("Step forward")
        self.btn_forward.clicked.connect(self.step_forward)
        nav_layout.addWidget(self.btn_forward)

        self.btn_end = QPushButton("▶|")
        self.btn_end.setMinimumWidth(38)
        self.btn_end.setToolTip("Go to end")
        self.btn_end.clicked.connect(self.go_to_end)
        nav_layout.addWidget(self.btn_end)

        self.btn_all = QPushButton("A")
        self.btn_all.setMinimumWidth(35)
        self.btn_all.setToolTip("Show full recording overview")
        self.btn_all.clicked.connect(self.set_time_window_all)
        nav_layout.addWidget(self.btn_all)

        ribbon_row_2.addWidget(nav_group)

        selection_group, selection_layout = make_group("Selection")

        self.clear_selection_btn = QPushButton("Clear")
        self.clear_selection_btn.setMinimumWidth(75)
        self.clear_selection_btn.setToolTip("Clear the active selected time segment.")
        self.clear_selection_btn.clicked.connect(self.clear_active_selection)
        selection_layout.addWidget(self.clear_selection_btn)

        self.selection_hint_label = QLabel("drag trace")
        self.selection_hint_label.setToolTip(
            "Drag horizontally over raw or filtered trace to create analysis selection."
        )
        selection_layout.addWidget(self.selection_hint_label)

        ribbon_row_2.addWidget(selection_group)

        amp_group, amp_layout = make_group("Amplitude")

        amp_layout.addWidget(QLabel("Target"))

        self.amp_target_box = QComboBox()
        self.amp_target_box.addItems(["All", "Raw", "Analysis", "RR"])
        self.amp_target_box.setMinimumWidth(85)
        amp_layout.addWidget(self.amp_target_box)

        self.amp_plus_btn = QPushButton("+")
        self.amp_plus_btn.setMinimumWidth(35)
        self.amp_plus_btn.setToolTip("Enlarge selected monitor amplitude")
        self.amp_plus_btn.clicked.connect(self.amplitude_plus)
        amp_layout.addWidget(self.amp_plus_btn)

        self.amp_minus_btn = QPushButton("-")
        self.amp_minus_btn.setMinimumWidth(35)
        self.amp_minus_btn.setToolTip("Diminish selected monitor amplitude")
        self.amp_minus_btn.clicked.connect(self.amplitude_minus)
        amp_layout.addWidget(self.amp_minus_btn)

        self.amp_reset_btn = QPushButton("0")
        self.amp_reset_btn.setMinimumWidth(35)
        self.amp_reset_btn.setToolTip("Reset amplitude")
        self.amp_reset_btn.clicked.connect(self.reset_amplitude)
        amp_layout.addWidget(self.amp_reset_btn)

        ribbon_row_2.addWidget(amp_group)

        time_group, time_layout = make_group("View")

        self.time_label = QLabel("Time: --")
        self.time_label.setMinimumWidth(260)
        time_layout.addWidget(self.time_label)

        ribbon_row_2.addWidget(time_group)

        ribbon_row_2.addStretch()
        layout.addLayout(ribbon_row_2)

        # ------------------------------------------------------------
        # Splitter layout
        # ------------------------------------------------------------

        main_splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(main_splitter, stretch=1)

        self.plot_splitter = QSplitter(Qt.Vertical)

        self.raw_plot = ScrubbablePlotWidget(
            scrub_callback=self.scrub_view,
            click_callback=self.set_cursor_time,
            selection_callback=self.handle_plot_selection,
            plot_name="raw"
        )
        self.configure_plot(self.raw_plot, "Raw ADC")

        self.filtered_plot = ScrubbablePlotWidget(
            scrub_callback=self.scrub_view,
            click_callback=self.set_cursor_time,
            selection_callback=self.handle_plot_selection,
            plot_name="analysis"
        )
        self.configure_plot(self.filtered_plot, "Filtered / Analysis signal")

        self.rr_plot = ScrubbablePlotWidget(
            scrub_callback=self.scrub_view,
            click_callback=self.set_cursor_time,
            selection_callback=self.handle_plot_selection,
            plot_name="rr"
        )
        self.configure_plot(self.rr_plot, "RR interval (ms)")

        self.plot_splitter.addWidget(self.raw_plot)
        self.plot_splitter.addWidget(self.filtered_plot)
        self.plot_splitter.addWidget(self.rr_plot)
        self.plot_splitter.setSizes([380, 380, 190])

        main_splitter.addWidget(self.plot_splitter)

        right_panel = QFrame()
        right_layout = QVBoxLayout()
        right_panel.setLayout(right_layout)

        right_layout.addWidget(QLabel("Recording Summary"))

        self.summary_box = QTextEdit()
        self.summary_box.setReadOnly(True)
        self.summary_box.setMinimumWidth(300)
        right_layout.addWidget(self.summary_box, stretch=1)

        right_layout.addWidget(QLabel("Analysis Metrics"))

        self.metrics_box = QTextEdit()
        self.metrics_box.setReadOnly(True)
        self.metrics_box.setMinimumWidth(300)
        right_layout.addWidget(self.metrics_box, stretch=2)

        main_splitter.addWidget(right_panel)
        main_splitter.setSizes([1300, 330])

        self.apply_dark_style()

    # ------------------------------------------------------------
    # Style and config
    # ------------------------------------------------------------

    def apply_dark_style(self):
        """
        Black Opal theme for Analysis panel.

        This is UI-only.
        It does not change filtering, peak detection, analysis, saving,
        quality report, provenance, or raw.csv handling.
        """

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

            QPushButton#topResultsButton {
                background-color: #17140A;
                color: #F2F2F4;
                border: 1px solid #D4AF37;
                border-radius: 6px;
                padding: 6px 12px;
                font-weight: 600;
            }

            QPushButton#topResultsButton:hover {
                background-color: #211B0B;
                color: #D4AF37;
                border: 1px solid #D4AF37;
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

            QSplitter::handle {
                background-color: #2D333F;
            }

            QSplitter::handle:hover {
                background-color: #D4AF37;
            }

            QScrollBar:vertical {
                background: #101219;
                width: 12px;
                margin: 0px;
            }

            QScrollBar::handle:vertical {
                background: #2D333F;
                min-height: 25px;
                border-radius: 4px;
            }

            QScrollBar::handle:vertical:hover {
                background: #D4AF37;
            }
            """
        )

    def configure_plot(self, plot, y_label):
        """
        Black Opal plot styling.

        Plot colors:
        - background: deep black
        - grid: muted graphite
        - axes: silver-grey
        """

        plot.setBackground("#050609")
        plot.showGrid(x=True, y=True, alpha=0.32)
        plot.setLabel("left", y_label)
        plot.setLabel("bottom", "Time", units="s")
        plot.setMouseEnabled(x=False, y=False)
        plot.setMenuEnabled(False)

        try:
            plot.hideButtons()
        except Exception:
            pass

        try:
            for axis_name in ["left", "bottom"]:
                axis = plot.getAxis(axis_name)
                axis.setPen(pg.mkPen("#B8BBC6"))
                axis.setTextPen(pg.mkPen("#B8BBC6"))
        except Exception:
            pass

    # ------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------

    def load_recording_clicked(self):
        folder = QFileDialog.getExistingDirectory(
            self,
            "Choose OpenPhysiologyLab recording folder",
            str(Path.cwd() / "recordings")
        )

        if not folder:
            return

        self.load_recording_folder_path(folder, temporary=False)

    def load_recording_folder_path(self, folder_path, temporary=False):
        """
        Load an OpenPhysioLab recording folder programmatically.

        Parameters
        ----------
        folder_path : str or Path
            Folder containing raw.csv and metadata.json.
        temporary : bool
            True when opened directly from recorder before final save.
            Save Analysis will then force final recording save/rename first.
        """

        folder_path = Path(folder_path)

        try:
            self.recording = load_recording_folder(folder_path)
        except Exception as e:
            self.summary_box.setText(f"Could not load recording:\n{e}")
            return False

        self.recording_is_temporary = bool(temporary)

        self.channel_box.blockSignals(True)
        self.channel_box.clear()

        for ch in self.recording["available_channels"]:
            self.channel_box.addItem(ch)

        self.channel_box.blockSignals(False)

        self.summary_box.setText(summarize_recording(self.recording))
        self.metrics_box.setText(
            "Loaded.\n\n"
            "Workflow:\n"
            "1. Optional: drag over raw/filtered plot to select a time segment.\n"
            "2. Apply Filter.\n"
            "3. Detect R Peaks.\n"
            "4. Edit peaks if needed.\n"
            "5. Analyse.\n"
            "6. Save Analysis.\n\n"
            "If this came from the recorder before final save, Save Analysis will first ask for the final recording folder name."
        )

        self.update_recording_info_strip()

        self.view_x_min = 0.0
        self.view_window_s = 60.0
        self.view_all = False
        self.time_window_index = TIME_WINDOWS.index(60)
        self.time_window_btn.setText("60s")

        self.reset_all_y_ranges()
        self.clear_analysis_state()
        self.clear_active_selection()
        self.plot_raw_only()

        return True

    def update_recording_info_strip(self):
        if self.recording is None:
            self.recording_info_label.setText("No recording loaded | Load a recording folder to begin")
            return

        metadata = self.recording.get("metadata", {})

        folder_name = Path(self.recording.get("folder", "")).name
        mode = metadata.get("recording_mode", "--")
        device_id = metadata.get("device_id", "--")
        operator = metadata.get("operator", "--")
        placement = metadata.get("electrode_placement", "--")
        integrity = metadata.get("integrity_status", "--")

        fs = self.recording.get("sample_rate_hz", "--")
        samples = self.recording.get("sample_count", "--")
        duration = self.recording.get("duration_sample_count_s", None)

        duration_text = self.format_mmss(duration) if duration is not None else "--"
        marker_count = len(self.recording.get("markers", []))

        text = (
            f"{folder_name}  |  "
            f"Mode: {mode}  |  "
            f"Device: {device_id}  |  "
            f"Operator: {operator}  |  "
            f"Placement: {placement}  |  "
            f"Fs: {fs} Hz  |  "
            f"Samples: {samples}  |  "
            f"Duration: {duration_text}  |  "
            f"Integrity Status: {integrity}  |  "
            f"Markers: {marker_count}"
        )

        self.recording_info_label.setText(text)

    def get_original_raw_channel_data(self):
        """
        Return original non-inverted raw.csv channel data.

        Used for ADC clipping/saturation quality checks.
        Display/analysis inversion must not affect original raw ADC quality checks.
        """

        if self.recording is None:
            return None, None, None

        ch = self.channel_box.currentText()

        if not ch:
            return None, None, None

        t = self.recording["time_s"]
        y = self.recording["channels"][ch]

        mask = np.isfinite(t) & np.isfinite(y)

        return ch, t[mask], y[mask]

    def get_selected_channel_data(self):
        if self.recording is None:
            return None, None, None

        ch = self.channel_box.currentText()

        if not ch:
            return None, None, None

        t = self.recording["time_s"]
        y = self.recording["channels"][ch]

        mask = np.isfinite(t) & np.isfinite(y)

        t = t[mask]
        y = y[mask]

        if self.invert_checkbox.isChecked():
            y = -y

        return ch, t, y

    def get_total_duration(self):
        if self.recording is None:
            return 0.0

        duration = self.recording.get("duration_sample_count_s", None)

        if duration is not None:
            return float(duration)

        t = self.recording.get("time_s", [])

        if len(t) > 1:
            return float(t[-1] - t[0])

        return 0.0

    def clear_analysis_state(self):
        self.current_raw_t = None
        self.current_raw_y = None
        self.current_analysis_y = None
        self.current_channel = None

        self.detected_peaks = None
        self.peak_result = None
        self.current_metrics = None
        self.current_filter_signature = None

        self.cursor_time_s = None
        self.clear_cursor_lines()
        self.update_peak_button_text()

    # ------------------------------------------------------------
    # Selection
    # ------------------------------------------------------------

    def get_selection_text(self):
        if self.active_selection is None:
            return "Selection: full recording"

        x1 = self.active_selection["x1"]
        x2 = self.active_selection["x2"]

        return f"Selection: {x1:.3f}–{x2:.3f} s ({x2 - x1:.3f} s)"

    def handle_plot_selection(self, plot_name, anchor_x, current_x, finished=False):
        if self.recording is None:
            return

        total = self.get_total_duration()

        if total <= 0:
            return

        anchor_x = max(0.0, min(float(anchor_x), total))
        current_x = max(0.0, min(float(current_x), total))

        x1 = min(anchor_x, current_x)
        x2 = max(anchor_x, current_x)

        if x2 <= x1:
            return

        self.active_selection = {
            "x1": x1,
            "x2": x2
        }

        self.update_selection_regions()
        self.update_edge_scroll_state(plot_name, anchor_x, current_x)

        self.metrics_box.setText(
            f"{self.get_selection_text()}\n\n"
            f"All peak detection and analysis will use only this selected segment."
        )

        if finished:
            self.stop_edge_scroll_selection()

    def update_selection_regions(self):
        self.clear_selection_regions()

        if self.active_selection is None:
            return

        x1 = self.active_selection["x1"]
        x2 = self.active_selection["x2"]

        for key, plot in [
            ("raw", self.raw_plot),
            ("analysis", self.filtered_plot),
            ("rr", self.rr_plot)
        ]:
            try:
                visible_x1, visible_x2 = plot.viewRange()[0]
            except Exception:
                visible_x1 = self.view_x_min
                visible_x2 = self.view_x_min + self.view_window_s

            draw_x1 = max(x1, visible_x1)
            draw_x2 = min(x2, visible_x2)

            if draw_x2 <= draw_x1:
                continue

            region = pg.LinearRegionItem(
                values=[draw_x1, draw_x2],
                orientation=pg.LinearRegionItem.Vertical,
                brush=pg.mkBrush(245, 176, 0, 55),
                movable=False
            )

            try:
                for line in region.lines:
                    line.setPen(pg.mkPen('#D4AF37', width=2))
                    line.setHoverPen(pg.mkPen('#FFC400', width=4))
            except Exception:
                pass

            region.setZValue(20)
            plot.addItem(region)
            self.selection_regions[key] = region

    def clear_selection_regions(self):
        for key, region in list(self.selection_regions.items()):
            plot = self.get_plot_for_key(key)

            if plot is None:
                continue

            try:
                plot.removeItem(region)
            except Exception:
                pass

        self.selection_regions = {}

    def clear_active_selection(self):
        self.stop_edge_scroll_selection()
        self.active_selection = None
        self.clear_selection_regions()

        if self.recording is not None:
            self.metrics_box.setText("Selection cleared. Analysis will use full recording.")

    def update_edge_scroll_state(self, plot_name, anchor_x, current_x):
        """
        Start edge auto-scroll during drag selection.

        Edge zone begins at 20% from either side:
        - left 20% of monitor = scroll toward beginning
        - right 20% of monitor = scroll toward end

        Scroll speed accelerates closer to the edge.
        """

        plot = self.get_plot_for_key(plot_name)

        if plot is None:
            self.stop_edge_scroll_selection()
            return

        try:
            visible_x1, visible_x2 = plot.viewRange()[0]
        except Exception:
            self.stop_edge_scroll_selection()
            return

        width = visible_x2 - visible_x1

        if width <= 0:
            self.stop_edge_scroll_selection()
            return

        edge_zone = width * 0.20
        direction = 0
        intensity = 0.0

        left_boundary = visible_x1 + edge_zone
        right_boundary = visible_x2 - edge_zone

        if current_x >= right_boundary:
            direction = 1
            intensity = (current_x - right_boundary) / edge_zone

        elif current_x <= left_boundary:
            direction = -1
            intensity = (left_boundary - current_x) / edge_zone

        if direction == 0:
            self.stop_edge_scroll_selection()
            return

        intensity = max(0.0, min(float(intensity), 1.5))

        # Smooth acceleration: 1x near 80% boundary, up to ~7x near/beyond edge.
        speed_factor = 1.0 + (intensity ** 2) * 3.0 + intensity * 2.0

        self.edge_scroll_active = True
        self.edge_scroll_direction = direction
        self.edge_scroll_anchor_x = anchor_x
        self.edge_scroll_current_x = current_x
        self.edge_scroll_plot_name = plot_name
        self.edge_scroll_speed_factor = speed_factor

        if not self.edge_scroll_timer.isActive():
            self.edge_scroll_timer.start(50)

    def stop_edge_scroll_selection(self):
        self.edge_scroll_active = False
        self.edge_scroll_direction = 0
        self.edge_scroll_anchor_x = None
        self.edge_scroll_current_x = None
        self.edge_scroll_plot_name = None

        if self.edge_scroll_timer.isActive():
            self.edge_scroll_timer.stop()

    def perform_edge_scroll_selection(self):
        if not self.edge_scroll_active:
            self.stop_edge_scroll_selection()
            return

        if self.edge_scroll_anchor_x is None or self.edge_scroll_current_x is None:
            self.stop_edge_scroll_selection()
            return

        if self.view_all:
            self.view_all = False
            self.view_window_s = self.all_mode_scrub_window_s
            self.time_window_btn.setText("60s")

        speed_factor = getattr(self, "edge_scroll_speed_factor", 1.0)
        step = max(0.02, self.view_window_s * 0.025 * speed_factor)

        self.view_x_min += self.edge_scroll_direction * step
        self.edge_scroll_current_x += self.edge_scroll_direction * step

        self.clamp_view()

        total = self.get_total_duration()
        self.edge_scroll_current_x = max(0.0, min(self.edge_scroll_current_x, total))

        x1 = min(self.edge_scroll_anchor_x, self.edge_scroll_current_x)
        x2 = max(self.edge_scroll_anchor_x, self.edge_scroll_current_x)

        self.active_selection = {
            "x1": x1,
            "x2": x2
        }

        self.apply_view_range_to_plots()
        self.update_selection_regions()

        self.metrics_box.setText(
            f"{self.get_selection_text()}\n\n"
            f"All peak detection and analysis will use only this selected segment."
        )

    def get_selection_mask(self, t):
        t = np.asarray(t, dtype=float)

        if self.active_selection is None:
            return np.isfinite(t)

        x1 = self.active_selection["x1"]
        x2 = self.active_selection["x2"]

        return np.isfinite(t) & (t >= x1) & (t <= x2)

    def get_selected_indices(self, t):
        mask = self.get_selection_mask(t)
        return np.where(mask)[0]

    # ------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------

    def format_mmss(self, seconds):
        try:
            seconds = float(seconds)
        except Exception:
            seconds = 0.0

        if seconds < 0:
            seconds = 0.0

        minutes = int(seconds // 60)
        whole_seconds = int(seconds % 60)

        return f"{minutes:02d}:{whole_seconds:02d}"

    def cycle_time_window(self):
        if self.recording is None:
            return

        self.time_window_index = (self.time_window_index + 1) % len(TIME_WINDOWS)
        option = TIME_WINDOWS[self.time_window_index]

        self.set_time_window(float(option))
        self.time_window_btn.setText(f"{option}s")

    def set_time_window(self, seconds):
        if self.recording is None:
            return

        self.view_window_s = float(seconds)
        self.view_all = False
        self.clamp_view()
        self.apply_view_range_to_plots()

    def set_time_window_all(self):
        if self.recording is None:
            return

        total = self.get_total_duration()

        self.view_all = True
        self.time_window_btn.setText("All")
        self.all_mode_scrub_window_s = min(60.0, max(10.0, total))

        self.apply_view_range_to_plots()

    def go_to_start(self):
        if self.recording is None:
            return

        if self.view_all:
            self.view_window_s = self.all_mode_scrub_window_s
        elif self.view_window_s <= 0:
            self.view_window_s = 60.0

        self.view_all = False
        self.view_x_min = 0.0
        self.clamp_view()
        self.apply_view_range_to_plots()

    def go_to_end(self):
        if self.recording is None:
            return

        total = self.get_total_duration()

        if self.view_all:
            self.view_window_s = self.all_mode_scrub_window_s
        elif self.view_window_s <= 0:
            self.view_window_s = 60.0

        self.view_all = False
        self.view_x_min = max(0.0, total - self.view_window_s)
        self.clamp_view()
        self.apply_view_range_to_plots()

    def step_backward(self):
        if self.recording is None:
            return

        if self.view_all:
            self.view_window_s = self.all_mode_scrub_window_s
            self.view_all = False
            self.time_window_btn.setText("60s")

        if self.view_window_s <= 0:
            self.view_window_s = 60.0

        self.view_x_min -= self.view_window_s * 0.5
        self.clamp_view()
        self.apply_view_range_to_plots()

    def step_forward(self):
        if self.recording is None:
            return

        if self.view_all:
            self.view_window_s = self.all_mode_scrub_window_s
            self.view_all = False
            self.time_window_btn.setText("60s")

        if self.view_window_s <= 0:
            self.view_window_s = 60.0

        self.view_x_min += self.view_window_s * 0.5
        self.clamp_view()
        self.apply_view_range_to_plots()

    def scrub_view(self, dx):
        if self.recording is None:
            return

        if self.view_all:
            self.view_window_s = self.all_mode_scrub_window_s
            self.view_all = False

            if 60 in TIME_WINDOWS:
                self.time_window_index = TIME_WINDOWS.index(60)

            self.time_window_btn.setText("60s")

            if dx < 0:
                self.view_x_min = 0.0
            else:
                self.view_x_min = max(0.0, self.get_total_duration() - self.view_window_s)

        if self.view_window_s <= 0:
            self.view_window_s = 60.0

        step = self.view_window_s * 0.08

        if dx > 0:
            self.view_x_min -= step
        else:
            self.view_x_min += step

        self.clamp_view()
        self.apply_view_range_to_plots()

    def clamp_view(self):
        total = self.get_total_duration()

        if total <= 0:
            self.view_x_min = 0.0
            return

        if self.view_window_s <= 0:
            self.view_window_s = 60.0

        max_start = max(0.0, total - self.view_window_s)
        self.view_x_min = max(0.0, min(self.view_x_min, max_start))

    def update_time_axis_spacing(self, x1, x2):
        span = float(x2 - x1)

        if span <= 2:
            major = 0.5
            minor = 0.1
        elif span <= 5:
            major = 1.0
            minor = 0.2
        elif span <= 10:
            major = 2.0
            minor = 0.5
        elif span <= 30:
            major = 5.0
            minor = 1.0
        elif span <= 60:
            major = 10.0
            minor = 2.0
        elif span <= 120:
            major = 20.0
            minor = 5.0
        elif span <= 300:
            major = 60.0
            minor = 10.0
        else:
            major = 120.0
            minor = 30.0

        for plot in [self.raw_plot, self.filtered_plot, self.rr_plot]:
            try:
                axis = plot.getAxis("bottom")
                axis.setTickSpacing(major=major, minor=minor)
            except Exception:
                pass

    def apply_view_range_to_plots(self):
        if self.recording is None:
            return

        total = self.get_total_duration()

        if total <= 0:
            return

        if self.view_all:
            x1 = 0.0
            x2 = total
        else:
            self.clamp_view()
            x1 = self.view_x_min
            x2 = min(total, self.view_x_min + self.view_window_s)

        self.update_time_axis_spacing(x1, x2)

        for plot in [self.raw_plot, self.filtered_plot, self.rr_plot]:
            plot.setXRange(x1, x2, padding=0)

        self.apply_y_ranges()
        self.update_cursor_lines()
        self.update_selection_regions()

        self.time_label.setText(
            f"Time: {self.format_mmss(x1)}–{self.format_mmss(x2)} / {self.format_mmss(total)}"
        )

    # ------------------------------------------------------------
    # Amplitude controls
    # ------------------------------------------------------------

    def reset_all_y_ranges(self):
        self.y_ranges = {
            "raw": None,
            "analysis": None,
            "rr": None
        }

    def get_amp_targets(self):
        target = self.amp_target_box.currentText()

        if target == "All":
            return ["raw", "analysis", "rr"]

        if target == "Raw":
            return ["raw"]

        if target == "Analysis":
            return ["analysis"]

        if target == "RR":
            return ["rr"]

        return []

    def get_plot_for_key(self, key):
        if key == "raw":
            return self.raw_plot

        if key == "analysis":
            return self.filtered_plot

        if key == "rr":
            return self.rr_plot

        return None

    def amplitude_plus(self):
        self.change_amplitude(scale=0.80)

    def amplitude_minus(self):
        self.change_amplitude(scale=1.25)

    def change_amplitude(self, scale):
        for key in self.get_amp_targets():
            plot = self.get_plot_for_key(key)

            if plot is None:
                continue

            if self.y_ranges.get(key) is None:
                y_range = plot.viewRange()[1]
                self.y_ranges[key] = (float(y_range[0]), float(y_range[1]))

            y_min, y_max = self.y_ranges[key]

            center = (y_min + y_max) / 2.0
            half = (y_max - y_min) / 2.0

            if half <= 0:
                half = 1.0

            half = half * scale
            self.y_ranges[key] = (center - half, center + half)

        self.apply_y_ranges()

    def reset_amplitude(self):
        for key in self.get_amp_targets():
            self.y_ranges[key] = None

        self.auto_range_y_for_none()

    def apply_y_ranges(self):
        for key, yrange in self.y_ranges.items():
            if yrange is None:
                continue

            plot = self.get_plot_for_key(key)

            if plot is not None:
                plot.setYRange(yrange[0], yrange[1], padding=0)

    def auto_range_y_for_none(self):
        for key, yrange in self.y_ranges.items():
            if yrange is not None:
                continue

            plot = self.get_plot_for_key(key)

            if plot is None:
                continue

            try:
                data_items = plot.listDataItems()

                if len(data_items) == 0:
                    continue

                plot.enableAutoRange(axis="y", enable=True)
                plot.autoRange()
                plot.enableAutoRange(axis="y", enable=False)

            except Exception:
                pass

    # ------------------------------------------------------------
    # Cursor
    # ------------------------------------------------------------

    def set_cursor_time(self, time_s, plot_name=None):
        """
        Single click sets the blue cursor.

        If a selection exists, single click also clears the selection.
        This matches the requested behaviour:
        click elsewhere after selecting = unselect.
        """

        if self.recording is None:
            return

        total = self.get_total_duration()

        self.cursor_time_s = max(0.0, min(float(time_s), total))

        if self.active_selection is not None:
            self.active_selection = None
            self.clear_selection_regions()
            self.stop_edge_scroll_selection()
            selection_note = "Selection cleared. Analysis will use full recording."
        else:
            selection_note = self.get_selection_text()

        self.update_cursor_lines()

        self.metrics_box.setText(
            f"Cursor set at {self.cursor_time_s:.3f} s.\n\n"
            f"{selection_note}\n\n"
            f"Peak editing works inside the selected segment if a selection exists."
        )

    def clear_cursor_lines(self):
        for item in self.cursor_items:
            for plot in [self.raw_plot, self.filtered_plot, self.rr_plot]:
                try:
                    plot.removeItem(item)
                except Exception:
                    pass

        self.cursor_items = []

    def update_cursor_lines(self):
        self.clear_cursor_lines()

        if self.cursor_time_s is None:
            return

        plots = [self.raw_plot, self.filtered_plot]

        if self.current_metrics is not None:
            plots.append(self.rr_plot)

        for plot in plots:
            line = pg.InfiniteLine(
                pos=self.cursor_time_s,
                angle=90,
                movable=False,
                pen=pg.mkPen('#D4AF37', width=1)
            )

            line.setZValue(30)
            plot.addItem(line)
            self.cursor_items.append(line)

    # ------------------------------------------------------------
    # Signal preparation
    # ------------------------------------------------------------

    def channel_changed(self):
        if self.recording is None:
            return

        self.clear_analysis_state()
        self.reset_all_y_ranges()
        self.clear_active_selection()
        self.plot_raw_only()

    def signal_display_setting_changed(self):
        if self.recording is None:
            return

        had_analysis_signal = self.current_analysis_y is not None
        had_peaks = self.detected_peaks is not None and len(self.detected_peaks) > 0
        had_metrics = self.current_metrics is not None

        previous_cursor_time = self.cursor_time_s
        previous_selection = self.active_selection.copy() if self.active_selection is not None else None

        self.reset_all_y_ranges()

        self.current_raw_t = None
        self.current_raw_y = None
        self.current_analysis_y = None
        self.detected_peaks = None
        self.peak_result = None
        self.current_metrics = None
        self.current_filter_signature = None

        self.cursor_time_s = previous_cursor_time
        self.active_selection = previous_selection

        self.update_peak_button_text()

        if had_metrics:
            self.analyse_clicked()
        elif had_peaks:
            self.apply_filter_clicked()
            self.detect_r_peaks_clicked()
        elif had_analysis_signal:
            self.apply_filter_clicked()
        else:
            self.plot_raw_only()

        self.update_cursor_lines()
        self.update_selection_regions()

    def get_filter_signature(self):
        return {
            "low_hz": float(self.low_spin.value()),
            "high_hz": float(self.high_spin.value()),
            "notch_50hz": bool(self.notch_checkbox.isChecked()),
            "inverted": bool(self.invert_checkbox.isChecked())
        }

    def prepare_analysis_signal(self):
        ch, t, y = self.get_selected_channel_data()

        if ch is None:
            return None, None, None, None

        fs = float(self.recording["sample_rate_hz"])

        y_analysis, filter_info = apply_bandpass_notch(
            signal=y,
            fs=fs,
            low_hz=float(self.low_spin.value()),
            high_hz=float(self.high_spin.value()),
            notch_hz=50.0,
            use_notch=self.notch_checkbox.isChecked(),
            filter_order=4,
            notch_quality=30.0
        )

        self.current_channel = ch
        self.current_raw_t = t
        self.current_raw_y = y
        self.current_analysis_y = y_analysis
        self.current_filter_signature = self.get_filter_signature()

        return ch, t, y, filter_info

    # ------------------------------------------------------------
    # Peak state
    # ------------------------------------------------------------

    def update_peak_button_text(self):
        if self.detected_peaks is not None and len(self.detected_peaks) > 0:
            self.detect_btn.setText("Remove R")
        else:
            self.detect_btn.setText("Detect R")

    def clear_detected_peaks(self):
        self.detected_peaks = None
        self.peak_result = None
        self.current_metrics = None

        self.update_peak_button_text()

        if self.current_analysis_y is not None:
            self.plot_filtered_only(
                self.current_channel,
                self.current_raw_t,
                self.current_raw_y,
                self.current_analysis_y
            )
        else:
            self.plot_raw_only()

        self.metrics_box.setText(
            "R peaks removed.\n\n"
            f"{self.get_selection_text()}\n\n"
            "Filtered signal remains visible. RR interval plot remains empty until Analyse is clicked."
        )

    # ------------------------------------------------------------
    # Plotting and workflow
    # ------------------------------------------------------------

    def plot_raw_only(self):
        self.raw_plot.clear()
        self.filtered_plot.clear()
        self.rr_plot.clear()

        ch, t, y = self.get_selected_channel_data()

        if ch is None:
            return

        self.current_channel = ch
        self.current_raw_t = t
        self.current_raw_y = y

        self.raw_plot.plot(t, y, pen=pg.mkPen('#50C878', width=1))
        self.raw_plot.setTitle(f"{ch} RAW {'(inverted)' if self.invert_checkbox.isChecked() else ''}")
        self.add_marker_lines(self.raw_plot)

        self.filtered_plot.setTitle("Filtered signal: click Apply Filter")
        self.rr_plot.setTitle("RR intervals: click Analyse")

        self.auto_range_y_for_none()
        self.apply_view_range_to_plots()

    def apply_filter_clicked(self):
        if self.recording is None:
            self.metrics_box.setText("Load a recording folder first.")
            return

        self.detected_peaks = None
        self.peak_result = None
        self.current_metrics = None
        self.update_peak_button_text()

        self.rr_plot.clear()
        self.rr_plot.setTitle("RR intervals: click Analyse")
        self.rr_plot.setYRange(0, 1, padding=0)

        ch, t, y_raw, filter_info = self.prepare_analysis_signal()

        if ch is None:
            return

        self.plot_filtered_only(ch, t, y_raw, self.current_analysis_y)

        self.metrics_box.setText(
            "Filter applied to raw.csv data for visualization.\n\n"
            f"{self.get_selection_text()}\n\n"
            "No HR/RR/HRV analysis has been calculated yet.\n"
            "Detect R Peaks and Analyse will use the selected segment if one exists.\n\n"
            f"Filter info:\n{filter_info}"
        )

    def plot_filtered_only(self, ch, t, y_raw, y_analysis):
        self.raw_plot.clear()
        self.filtered_plot.clear()
        self.rr_plot.clear()

        self.raw_plot.plot(t, y_raw, pen=pg.mkPen('#50C878', width=1))
        self.raw_plot.setTitle(f"{ch} RAW {'(inverted)' if self.invert_checkbox.isChecked() else ''}")
        self.add_marker_lines(self.raw_plot)

        self.filtered_plot.plot(t, y_analysis, pen=pg.mkPen('#FFC400', width=1))
        self.filtered_plot.setTitle(
            f"{ch} Filtered signal from raw.csv "
            f"{'(inverted)' if self.invert_checkbox.isChecked() else ''}"
        )
        self.add_marker_lines(self.filtered_plot)

        self.rr_plot.setTitle("RR intervals: click Analyse")
        self.rr_plot.setYRange(0, 1, padding=0)

        self.reset_all_y_ranges()
        self.auto_range_y_for_none()
        self.apply_view_range_to_plots()

    def get_peak_polarity_setting(self):
        """
        Return selected R-peak polarity mode.
        """

        box = getattr(self, "peak_polarity_box", None)

        if box is None:
            return "auto"

        value = box.currentText().strip().lower()

        if value == "positive":
            return "positive"

        if value == "negative":
            return "negative"

        return "auto"

    def detect_r_peaks_clicked(self):
        """
        Toggle R-peak detection.

        Rule:
        R peaks are always detected on the filtered-from-raw analysis signal.
        If the filtered monitor has not been generated yet, this function
        automatically applies the current filter settings first.

        The same detected R-peak timings are displayed on both:
        - raw monitor
        - filtered monitor

        RR interval plot is generated only after Analyse is clicked.
        """

        if self.recording is None:
            self.metrics_box.setText("Load a recording folder first.")
            return

        # Toggle off if peaks already exist.
        if self.detected_peaks is not None and len(self.detected_peaks) > 0:
            self.clear_detected_peaks()
            return

        # Always create/recreate filtered-from-raw signal if needed.
        if self.current_analysis_y is None or self.current_filter_signature != self.get_filter_signature():
            ch, t, y_raw, filter_info = self.prepare_analysis_signal()
        else:
            ch = self.current_channel
            t = self.current_raw_t
            y_raw = self.current_raw_y
            filter_info = {
                "source_file": "raw.csv",
                "filter_application": "Existing current filter settings were used.",
                "low_hz": float(self.low_spin.value()),
                "high_hz": float(self.high_spin.value()),
                "notch_50hz": bool(self.notch_checkbox.isChecked())
            }

        if ch is None or t is None or self.current_analysis_y is None:
            return

        selected_indices = self.get_selected_indices(t)

        if len(selected_indices) < 5:
            self.metrics_box.setText("Selection is too short for R peak detection.")
            return

        t_selected = t[selected_indices]
        y_selected = self.current_analysis_y[selected_indices]

        fs = float(self.recording["sample_rate_hz"])
        mode = self.mode_box.currentText().upper()

        if mode == "ECG":
            peak_result = detect_ecg_r_peaks(
                x=t_selected,
                y=y_selected,
                fs=fs,
                forced_polarity=self.get_peak_polarity_setting()
            )
        else:
            peak_result = detect_general_peaks(
                x=t_selected,
                y=y_selected,
                fs=fs
            )

        local_peaks = np.asarray(peak_result["peaks"], dtype=int)
        global_peaks = selected_indices[local_peaks] if len(local_peaks) > 0 else np.asarray([], dtype=int)

        self.peak_result = peak_result
        self.detected_peaks = global_peaks
        self.current_metrics = None

        self.update_peak_button_text()
        self.plot_peaks_only(ch, t, y_raw, self.current_analysis_y)

        self.metrics_box.setText(
            f"R peaks detected on filtered-from-raw signal.\n\n"
            f"The same peak timings are shown on both raw and filtered monitors.\n\n"
            f"{self.get_selection_text()}\n\n"
            f"Method: {peak_result.get('method')}\n"
            f"Polarity: {peak_result.get('polarity')}\n"
            f"Polarity source: {peak_result.get('polarity_source', 'auto')}\n"
            f"Peak polarity setting: {self.get_peak_polarity_setting()}\n"
            f"Peaks in analysis scope: {len(self.detected_peaks)}\n"
            f"Warning: {peak_result.get('warning')}\n\n"
            f"Filter settings used for detection:\n"
            f"Low Hz: {float(self.low_spin.value())}\n"
            f"High Hz: {float(self.high_spin.value())}\n"
            f"50 Hz notch: {bool(self.notch_checkbox.isChecked())}\n\n"
            f"RR interval plot will be generated only after Analyse is clicked.\n\n"
            f"Filter info:\n{filter_info}"
        )

    def plot_peaks_only(self, ch, t, y_raw, y_analysis):
        """
        Plot editable R peaks on BOTH raw and filtered monitors.

        Peak detection happens on filtered-from-raw signal, but peak timing is
        shown on raw as well for teaching and verification.
        """

        self.raw_plot.clear()
        self.filtered_plot.clear()
        self.rr_plot.clear()

        valid = np.asarray([], dtype=int)

        if self.detected_peaks is not None and len(self.detected_peaks) > 0:
            valid = self.detected_peaks[
                (self.detected_peaks >= 0) & (self.detected_peaks < len(t))
            ]

        # Raw monitor with same R-peak timing markers
        self.raw_plot.plot(t, y_raw, pen=pg.mkPen('#50C878', width=1))

        if len(valid) > 0:
            self.raw_plot.plot(
                t[valid],
                y_raw[valid],
                pen=None,
                symbol="o",
                symbolSize=6,
                symbolBrush=pg.mkBrush('#9B6DFF'),
                symbolPen=pg.mkPen('#F2F2F4', width=1)
            )

        self.raw_plot.setTitle(
            f"{ch} RAW with detected R-peak timings "
            f"{'(inverted)' if self.invert_checkbox.isChecked() else ''}"
        )
        self.add_marker_lines(self.raw_plot)

        # Filtered monitor with R-peak markers
        self.filtered_plot.plot(t, y_analysis, pen=pg.mkPen('#FFC400', width=1))

        if len(valid) > 0:
            self.filtered_plot.plot(
                t[valid],
                y_analysis[valid],
                pen=None,
                symbol="o",
                symbolSize=6,
                symbolBrush=pg.mkBrush('#9B6DFF'),
                symbolPen=pg.mkPen('#F2F2F4', width=1)
            )

        self.filtered_plot.setTitle(
            f"{ch} Filtered signal used for R-peak detection "
            f"{'(inverted)' if self.invert_checkbox.isChecked() else ''}"
        )
        self.add_marker_lines(self.filtered_plot)

        self.rr_plot.setTitle("RR intervals: click Analyse")
        self.rr_plot.setYRange(0, 1, padding=0)

        self.auto_range_y_for_none()
        self.apply_view_range_to_plots()

    def add_peak_near_cursor(self):
        if self.recording is None:
            return

        if self.cursor_time_s is None:
            self.metrics_box.setText("Set cursor first by clicking near the missed R peak.")
            return

        if self.current_analysis_y is None:
            self.apply_filter_clicked()

        if self.current_raw_t is None or self.current_analysis_y is None:
            return

        t = self.current_raw_t
        y = self.current_analysis_y

        if self.active_selection is not None:
            if not (self.active_selection["x1"] <= self.cursor_time_s <= self.active_selection["x2"]):
                self.metrics_box.setText("Cursor is outside the active selection. Peak edit not applied.")
                return

        if self.detected_peaks is None:
            self.detect_r_peaks_clicked()

        window_s = 0.12

        mask = np.abs(t - self.cursor_time_s) <= window_s
        mask = mask & self.get_selection_mask(t)

        if not np.any(mask):
            idx = int(np.argmin(np.abs(t - self.cursor_time_s)))
        else:
            candidate_indices = np.where(mask)[0]
            local_y = y[candidate_indices]
            local_median = np.median(local_y)

            best_local = int(np.argmax(np.abs(local_y - local_median)))
            idx = int(candidate_indices[best_local])

        peaks = np.asarray([] if self.detected_peaks is None else self.detected_peaks, dtype=int)

        if idx not in peaks:
            peaks = np.append(peaks, idx)

        peaks = np.unique(peaks)
        peaks.sort()

        self.detected_peaks = peaks
        self.current_metrics = None
        self.update_peak_button_text()

        self.plot_peaks_only(self.current_channel, t, self.current_raw_y, y)

        self.metrics_box.setText(
            f"Peak added near cursor.\n\n"
            f"{self.get_selection_text()}\n\n"
            f"Cursor: {self.cursor_time_s:.3f} s\n"
            f"Added nearest local peak at: {t[idx]:.3f} s\n"
            f"Total peaks in current list: {len(self.detected_peaks)}\n\n"
            f"RR interval plot will update only after Analyse."
        )

    def remove_peak_near_cursor(self):
        if self.recording is None:
            return

        if self.cursor_time_s is None:
            self.metrics_box.setText("Set cursor first by clicking near a peak.")
            return

        if self.detected_peaks is None or len(self.detected_peaks) == 0:
            self.metrics_box.setText("No detected peaks available. Click Detect R Peaks first.")
            return

        t = self.current_raw_t

        if t is None:
            return

        if self.active_selection is not None:
            if not (self.active_selection["x1"] <= self.cursor_time_s <= self.active_selection["x2"]):
                self.metrics_box.setText("Cursor is outside the active selection. Peak edit not applied.")
                return

        peak_times = t[self.detected_peaks]
        nearest_i = int(np.argmin(np.abs(peak_times - self.cursor_time_s)))
        nearest_peak_index = int(self.detected_peaks[nearest_i])
        nearest_peak_time = float(t[nearest_peak_index])

        tolerance_s = 0.25

        if abs(nearest_peak_time - self.cursor_time_s) > tolerance_s:
            self.metrics_box.setText(
                f"No peak close enough to cursor.\n\n"
                f"Cursor: {self.cursor_time_s:.3f} s\n"
                f"Nearest peak: {nearest_peak_time:.3f} s\n"
                f"Tolerance: {tolerance_s:.3f} s"
            )
            return

        self.detected_peaks = np.delete(self.detected_peaks, nearest_i)
        self.current_metrics = None
        self.update_peak_button_text()

        self.plot_peaks_only(
            self.current_channel,
            self.current_raw_t,
            self.current_raw_y,
            self.current_analysis_y
        )

        self.metrics_box.setText(
            f"Peak removed near cursor.\n\n"
            f"{self.get_selection_text()}\n\n"
            f"Cursor: {self.cursor_time_s:.3f} s\n"
            f"Removed peak at: {nearest_peak_time:.3f} s\n"
            f"Total peaks in current list: {len(self.detected_peaks)}\n\n"
            f"RR interval plot will update only after Analyse."
        )

    def analyse_clicked(self):
        if self.recording is None:
            self.metrics_box.setText("Load a recording folder first.")
            return

        if self.current_analysis_y is None or self.current_filter_signature != self.get_filter_signature():
            ch, t, y_raw, filter_info = self.prepare_analysis_signal()
            self.detected_peaks = None
            self.peak_result = None
            self.update_peak_button_text()
        else:
            ch = self.current_channel
            t = self.current_raw_t
            y_raw = self.current_raw_y
            filter_info = {
                "source_file": "raw.csv",
                "filter_application": "Current filter settings were applied to raw.csv data.",
                "low_hz": float(self.low_spin.value()),
                "high_hz": float(self.high_spin.value()),
                "notch_50hz": bool(self.notch_checkbox.isChecked())
            }

        if ch is None or t is None or self.current_analysis_y is None:
            self.metrics_box.setText("No valid analysis signal.")
            return

        if self.detected_peaks is None:
            self.detect_r_peaks_clicked()

        selected_indices = self.get_selected_indices(t)

        if len(selected_indices) < 5:
            self.metrics_box.setText("Selection is too short for analysis.")
            return

        t_selected = t[selected_indices]
        y_selected = self.current_analysis_y[selected_indices]

        peaks_global = np.asarray([] if self.detected_peaks is None else self.detected_peaks, dtype=int)
        peaks_global = peaks_global[
            np.isin(peaks_global, selected_indices)
        ]

        selected_position_lookup = {int(global_idx): local_idx for local_idx, global_idx in enumerate(selected_indices)}
        peaks_local = np.asarray(
            [selected_position_lookup[int(idx)] for idx in peaks_global if int(idx) in selected_position_lookup],
            dtype=int
        )

        metrics = calculate_selection_metrics(
            x=t_selected,
            y=y_selected,
            peaks=peaks_local
        )

        self.current_metrics = metrics

        method = "manual_or_detected_peaks"
        polarity = "unknown"
        warning = None

        if self.peak_result is not None:
            method = self.peak_result.get("method", method)
            polarity = self.peak_result.get("polarity", polarity)
            warning = self.peak_result.get("warning", None)

        text = format_selection_metrics_text(
            channel=ch,
            trace_type="ANALYSIS",
            x1=float(t_selected[0]),
            x2=float(t_selected[-1]),
            peak_method=method,
            peak_polarity=polarity,
            peak_warning=warning,
            metrics=metrics
        )

        text += "\n\nAnalysis scope:\n"
        text += f"{self.get_selection_text()}\n"

        text += "\nAnalysis source:\n"
        text += "raw.csv was used as the source data.\n"
        text += "The current filter settings were applied to raw.csv for analysis.\n"
        text += "No processed/filtered saved file was used as source.\n"

        text += "\nFilter settings used:\n"
        text += f"Low Hz: {float(self.low_spin.value())}\n"
        text += f"High Hz: {float(self.high_spin.value())}\n"
        text += f"50 Hz notch: {bool(self.notch_checkbox.isChecked())}\n"

        text += "\nFilter info:\n"
        text += str(filter_info)

        if self.invert_checkbox.isChecked():
            text += "\n\nSignal display/analysis polarity: INVERTED"

        text += "\n\nPeak editing note:\n"
        text += "Metrics were calculated using the current editable peak list inside the analysis scope."

        self.metrics_box.setText(text)

        self.plot_analysis_result(ch, t, y_raw, self.current_analysis_y, peaks_global, metrics)

    def plot_analysis_result(self, ch, t, y_raw, y_analysis, peaks, metrics):
        """
        Plot final analysis result.

        R-peak timings are displayed on both raw and filtered monitors.
        RR intervals are displayed only after analysis.
        """

        self.raw_plot.clear()
        self.filtered_plot.clear()
        self.rr_plot.clear()

        valid = peaks[(peaks >= 0) & (peaks < len(t))]

        self.raw_plot.plot(t, y_raw, pen=pg.mkPen('#50C878', width=1))

        if len(valid) > 0:
            self.raw_plot.plot(
                t[valid],
                y_raw[valid],
                pen=None,
                symbol="o",
                symbolSize=6,
                symbolBrush=pg.mkBrush('#9B6DFF'),
                symbolPen=pg.mkPen('#F2F2F4', width=1)
            )

        self.raw_plot.setTitle(
            f"{ch} RAW with analysed R-peak timings "
            f"{'(inverted)' if self.invert_checkbox.isChecked() else ''}"
        )
        self.add_marker_lines(self.raw_plot)

        self.filtered_plot.plot(t, y_analysis, pen=pg.mkPen('#FFC400', width=1))

        if len(valid) > 0:
            self.filtered_plot.plot(
                t[valid],
                y_analysis[valid],
                pen=None,
                symbol="o",
                symbolSize=6,
                symbolBrush=pg.mkBrush('#9B6DFF'),
                symbolPen=pg.mkPen('#F2F2F4', width=1)
            )

        self.filtered_plot.setTitle(
            f"{ch} Filtered signal with analysed R peaks "
            f"{'(inverted)' if self.invert_checkbox.isChecked() else ''}"
        )
        self.add_marker_lines(self.filtered_plot)

        peak_times = np.asarray(metrics.get("peak_times_s", []), dtype=float)
        rr_ms = np.asarray(metrics.get("rr_intervals_ms", []), dtype=float)

        if len(peak_times) >= 2 and len(rr_ms) > 0:
            rr_times = peak_times[1:]

            self.rr_plot.plot(
                rr_times,
                rr_ms,
                pen=pg.mkPen('#D4AF37', width=1),
                symbol="o",
                symbolSize=5,
                symbolBrush=pg.mkBrush('#D4AF37')
            )

            self.rr_plot.setTitle("RR intervals")
        else:
            self.rr_plot.setTitle("RR intervals: insufficient peaks")
            self.rr_plot.setYRange(0, 1, padding=0)

        self.auto_range_y_for_none()
        self.apply_view_range_to_plots()

    def sanitize_folder_name_for_analysis(self, name):
        name = str(name).strip()

        if not name:
            return None

        invalid_chars = '<>:"/\\|?*'

        for ch in invalid_chars:
            name = name.replace(ch, "_")

        name = name.replace(" ", "_")

        while "__" in name:
            name = name.replace("__", "_")

        name = name.strip("_")

        return name if name else None

    def choose_final_recording_folder_for_analysis(self):
        """
        Ask for final recording folder if current recording was temporary.
        """

        if self.recording is None:
            return None

        current_folder = Path(self.recording["folder"])
        default_parent = current_folder.parent
        default_name = current_folder.name.replace("TEMP_", "")

        name, ok = QInputDialog.getText(
            self,
            "Save Recording Before Saving Analysis",
            (
                "This recording came directly from the Recorder and is still temporary.\n\n"
                "Enter the FINAL recording folder name.\n"
                "The analysis/ folder will be saved inside it:"
            ),
            text=default_name
        )

        if not ok:
            return None

        safe_name = self.sanitize_folder_name_for_analysis(name)

        if safe_name is None:
            QMessageBox.warning(
                self,
                "Invalid folder name",
                "Recording folder name cannot be empty."
            )
            return None

        final_folder = default_parent / safe_name

        if final_folder.exists() and final_folder.resolve() != current_folder.resolve():
            reply = QMessageBox.question(
                self,
                "Folder Already Exists",
                f"{final_folder}\n\nOverwrite this folder?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )

            if reply != QMessageBox.Yes:
                return None

            shutil.rmtree(final_folder)

        return final_folder

    def finalize_temporary_recording_if_needed(self):
        """
        If recording was opened directly from Recorder before final save,
        force final save/rename before analysis export.

        Important:
        Do NOT reload the recording here.
        Reloading clears current_analysis_y, detected_peaks, and current_metrics.
        We only move/rename the folder and update path references.
        """

        if self.recording is None:
            return None

        current_folder = Path(self.recording["folder"])

        if not self.recording_is_temporary:
            return current_folder

        final_folder = self.choose_final_recording_folder_for_analysis()

        if final_folder is None:
            return None

        try:
            if final_folder.resolve() != current_folder.resolve():
                shutil.move(str(current_folder), str(final_folder))

            self.recording_is_temporary = False

            # Update folder/path references without clearing analysis state.
            self.recording["folder"] = final_folder
            self.recording["raw_path"] = final_folder / "raw.csv"
            self.recording["metadata_path"] = final_folder / "metadata.json"

            markers_path = final_folder / "markers.csv"
            self.recording["markers_path"] = markers_path if markers_path.exists() else None

            self.update_recording_info_strip()

            self.summary_box.setText(summarize_recording(self.recording))

            return final_folder

        except Exception as e:
            QMessageBox.critical(
                self,
                "Save Failed",
                f"Could not finalize recording folder:\n{e}"
            )
            return None

    def get_provenance_report(self):
        """
        Return provenance report for current analysis settings.
        """

        return build_provenance_report(
            low_hz=float(self.low_spin.value()),
            high_hz=float(self.high_spin.value()),
            notch_50hz=bool(self.notch_checkbox.isChecked()),
            inverted=bool(self.invert_checkbox.isChecked()),
            selection=self.active_selection
        )

    def get_signal_quality_report(self, silent=False):
        """
        Return descriptive signal quality report.

        This does not modify raw data and does not correct artifacts.
        """

        if self.recording is None:
            if not silent:
                self.metrics_box.setText("No recording loaded.")
            return None

        if self.current_analysis_y is None or self.current_filter_signature != self.get_filter_signature():
            self.prepare_analysis_signal()

        if self.current_raw_t is None or self.current_raw_y is None or self.current_analysis_y is None:
            if not silent:
                self.metrics_box.setText("No signal available for quality report.")
            return None

        # For signal quality:
        # - original_raw is used for ADC clipping/saturation checks
        # - current_analysis_y is filtered-from-raw and may be inverted
        ch0, t0, original_raw = self.get_original_raw_channel_data()

        if t0 is None or original_raw is None:
            t = self.current_raw_t
            raw = self.current_raw_y
        else:
            t = t0
            raw = original_raw

        filtered = self.current_analysis_y

        selected_indices = self.get_selected_indices(t)

        if len(selected_indices) < 2:
            if not silent:
                self.metrics_box.setText("Selection too short for quality report.")
            return None

        peaks_for_scope = None

        if self.detected_peaks is not None:
            peaks = np.asarray(self.detected_peaks, dtype=int)
            peaks = peaks[np.isin(peaks, selected_indices)]

            lookup = {
                int(global_idx): local_idx
                for local_idx, global_idx in enumerate(selected_indices)
            }

            peaks_for_scope = np.asarray(
                [
                    lookup[int(idx)]
                    for idx in peaks
                    if int(idx) in lookup
                ],
                dtype=int
            )

        fs = float(self.recording.get("sample_rate_hz", 500.0))

        return assess_signal_quality(
            t=t[selected_indices],
            raw_signal=raw[selected_indices],
            filtered_signal=filtered[selected_indices],
            fs=fs,
            peak_indices=peaks_for_scope
        )

    def format_quality_provenance_text(self, quality, provenance):
        """
        Human-readable report for the right-side Analysis Metrics box.
        """

        lines = []

        lines.append("Signal Quality + Provenance Report")
        lines.append("=" * 42)
        lines.append("")

        lines.append("Provenance")
        lines.append("-" * 20)
        lines.append("Source data: raw.csv")
        lines.append("Raw data modified: No")
        lines.append("Filtering: applied in memory to raw.csv")
        lines.append("Peak detection: performed on filtered-from-raw signal")
        lines.append("Raw monitor markers: detected peak timings projected onto raw display")
        lines.append("Artifact correction applied: No")
        lines.append("RR correction applied: No")
        lines.append("")

        lines.append("Filter settings")
        lines.append("-" * 20)
        filt = provenance.get("filtering", {})
        lines.append(f"Low Hz: {filt.get('low_hz')}")
        lines.append(f"High Hz: {filt.get('high_hz')}")
        lines.append(f"50 Hz notch: {filt.get('notch_50hz')}")
        lines.append(f"Inverted display/analysis: {provenance.get('polarity', {}).get('display_or_analysis_inverted')}")
        lines.append("")

        if quality is None:
            lines.append("Quality report unavailable.")
            return "\n".join(lines)

        lines.append("Raw signal stats")
        lines.append("-" * 20)
        raw_stats = quality.get("raw_signal_stats", {})
        lines.append(f"Samples: {raw_stats.get('samples')}")
        lines.append(f"Mean: {raw_stats.get('mean')}")
        lines.append(f"SD: {raw_stats.get('std')}")
        lines.append(f"Peak-to-peak: {raw_stats.get('peak_to_peak')}")
        lines.append("")

        lines.append("Filtered signal stats")
        lines.append("-" * 20)
        filt_stats = quality.get("filtered_signal_stats", {})
        lines.append(f"Mean: {filt_stats.get('mean')}")
        lines.append(f"SD: {filt_stats.get('std')}")
        lines.append(f"Peak-to-peak: {filt_stats.get('peak_to_peak')}")
        lines.append(f"Filtered/raw RMS ratio: {quality.get('rms_ratio_filtered_to_raw')}")
        lines.append("")

        lines.append("Noise estimates")
        lines.append("-" * 20)
        raw_noise = quality.get("raw_noise_estimates", {})
        filt_noise = quality.get("filtered_noise_estimates", {})
        lines.append(f"Raw 50Hz/signal ratio: {raw_noise.get('powerline_to_signal_ratio')}")
        lines.append(f"Filtered 50Hz/signal ratio: {filt_noise.get('powerline_to_signal_ratio')}")
        lines.append(f"Raw baseline/signal ratio: {raw_noise.get('baseline_to_signal_ratio')}")
        lines.append(f"Filtered baseline/signal ratio: {filt_noise.get('baseline_to_signal_ratio')}")
        lines.append("")

        lines.append("Artifact flags")
        lines.append("-" * 20)
        raw_art = quality.get("raw_artifact_flags", {})
        low_clip = raw_art.get('possible_clipping_low_count')
        high_clip = raw_art.get('possible_clipping_high_count')
        samples = raw_stats.get('samples')

        lines.append(f"Possible clipping low count: {low_clip}")
        lines.append(f"Possible clipping high count: {high_clip}")

        try:
            samples_float = float(samples)
            low_float = float(low_clip)
            high_float = float(high_clip)

            if samples_float > 0:
                low_pct = (low_float / samples_float) * 100.0
                high_pct = (high_float / samples_float) * 100.0

                lines.append(f"Possible clipping low percent: {low_pct:.4f} %")
                lines.append(f"Possible clipping high percent: {high_pct:.4f} %")

                try:
                    fs = float(self.recording.get("sample_rate_hz", 500.0)) if self.recording is not None else 500.0
                    if fs > 0:
                        lines.append(f"Estimated low-clipped duration: {low_float / fs:.3f} s")
                        lines.append(f"Estimated high-clipped duration: {high_float / fs:.3f} s")
                except Exception:
                    pass

        except Exception:
            pass

        lines.append(f"Possible flatline segments: {raw_art.get('possible_flatline_segments')}")
        lines.append(f"Large jump count: {raw_art.get('large_jump_count')}")
        lines.append("")
        lines.append("Clipping interpretation")
        lines.append("-" * 20)
        lines.append("Clipping is checked on original raw ADC values, not on inverted display values.")
        lines.append("If display/analysis is inverted, LOW-rail clipping may visually look like an upper ceiling.")
        lines.append("Clipped waveform tips are not recoverable; timing may still be usable if R peaks are detectable.")
        lines.append("")

        lines.append("RR quality")
        lines.append("-" * 20)
        rrq = quality.get("rr_quality", {})
        lines.append(f"RR count: {rrq.get('rr_count')}")
        lines.append(f"RR median ms: {rrq.get('rr_median_ms')}")
        lines.append(f"RR outlier count: {rrq.get('rr_outlier_count')}")
        lines.append(f"Possible extra beat count: {rrq.get('possible_extra_beat_count')}")
        lines.append(f"Possible missed beat count: {rrq.get('possible_missed_beat_count')}")
        lines.append("")

        flags = quality.get("interpretation_flags", [])

        lines.append("Interpretation flags")
        lines.append("-" * 20)

        if len(flags) == 0:
            lines.append("None.")
        else:
            for flag in flags:
                lines.append(f"- {flag}")

        lines.append("")
        lines.append("Important note")
        lines.append("-" * 20)
        lines.append("This report is descriptive. It does not modify raw.csv.")
        lines.append("No artifact or RR correction has been applied.")

        return "\n".join(lines)

    def show_quality_provenance_clicked(self):
        """
        Display quality/provenance report in Analysis Metrics panel.
        """

        quality = self.get_signal_quality_report(silent=False)
        provenance = self.get_provenance_report()

        self.metrics_box.setText(
            self.format_quality_provenance_text(quality, provenance)
        )

    def go_to_results_clicked(self):
        """
        Save/update current analysis outputs, then open that exact
        analysis_report.json in the Results tab.

        Results tab is report-only. It does not recalculate.
        """

        if self.recording is None:
            self.metrics_box.setText("Load or analyse a recording first.")
            return

        # Save/update analysis_report.json using the existing save pipeline.
        self.save_analysis_clicked()

        report_path = getattr(self, "latest_analysis_report_path", None)

        # Fallback: infer report path from current recording folder.
        if report_path is None and self.recording is not None:
            try:
                candidate = Path(self.recording["folder"]) / "analysis" / "analysis_report.json"

                if candidate.exists():
                    report_path = candidate
            except Exception:
                report_path = None

        if report_path is None:
            self.metrics_box.append(
                "\n\nCould not open Results tab because no analysis_report.json was found."
            )
            return

        report_path = Path(report_path)

        if not report_path.exists():
            self.metrics_box.append(
                f"\n\nCould not open Results tab because report does not exist:\n{report_path}"
            )
            return

        # Emit exact report path. MainWindow will switch to Results.
        self.open_results_requested.emit(str(report_path))

        self.metrics_box.append(
            f"\n\nOpened Results tab with updated report:\n{report_path}"
        )


    def save_analysis_clicked(self):
        """
        Save current analysis into recording_folder/analysis/.
        """

        if self.recording is None:
            QMessageBox.warning(self, "No Recording", "Load or analyse a recording first.")
            return

        if self.current_metrics is None:
            reply = QMessageBox.question(
                self,
                "Run Analysis?",
                "No analysis result exists yet. Run Analyse now?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )

            if reply != QMessageBox.Yes:
                return

            self.analyse_clicked()

            if self.current_metrics is None:
                QMessageBox.warning(self, "No Analysis", "Analysis could not be completed.")
                return

        final_folder = self.finalize_temporary_recording_if_needed()

        if final_folder is None:
            self.metrics_box.append("\n\nSave Analysis cancelled.")
            return

        analysis_folder = final_folder / "analysis"
        analysis_folder.mkdir(exist_ok=True)

        try:
            # Safety net: if finalization or UI state somehow removed the analysis signal,
            # run Analyse again before exporting.
            if self.current_analysis_y is None or self.current_metrics is None:
                self.analyse_clicked()

            if self.current_analysis_y is None or self.current_metrics is None:
                raise RuntimeError(
                    "No analysis signal available. Click Apply Filter, Detect R Peaks, and Analyse first."
                )

            self.write_analysis_outputs(analysis_folder)

            QMessageBox.information(
                self,
                "Analysis Saved",
                f"Analysis saved in:\n{analysis_folder}"
            )

            self.metrics_box.append(f"\n\nAnalysis saved in:\n{analysis_folder}")

        except Exception as e:
            QMessageBox.critical(
                self,
                "Analysis Save Failed",
                str(e)
            )

    def make_json_safe(self, value):
        """
        Convert NumPy/Python objects into JSON-serializable objects.

        Needed because metrics and peak-detection results may contain:
        - np.ndarray
        - np.integer
        - np.floating
        - Path
        - nested dict/list structures
        """

        if isinstance(value, np.ndarray):
            return value.tolist()

        if isinstance(value, np.integer):
            return int(value)

        if isinstance(value, np.floating):
            return float(value)

        if isinstance(value, Path):
            return str(value)

        if isinstance(value, dict):
            return {
                str(k): self.make_json_safe(v)
                for k, v in value.items()
            }

        if isinstance(value, (list, tuple)):
            return [
                self.make_json_safe(v)
                for v in value
            ]

        return value

    def write_analysis_outputs(self, analysis_folder):
        """
        Export analysis report, R peaks, and RR intervals.
        """

        analysis_folder = Path(analysis_folder)
        analysis_folder.mkdir(exist_ok=True)

        if self.recording is None:
            raise RuntimeError("No recording loaded.")

        if self.current_raw_t is None or self.current_analysis_y is None:
            raise RuntimeError("No analysis signal available.")

        if self.current_metrics is None:
            raise RuntimeError("No analysis metrics available.")

        t = np.asarray(self.current_raw_t, dtype=float)
        y_raw = np.asarray(self.current_raw_y, dtype=float)
        y_analysis = np.asarray(self.current_analysis_y, dtype=float)

        peaks = np.asarray([] if self.detected_peaks is None else self.detected_peaks, dtype=int)
        valid = peaks[(peaks >= 0) & (peaks < len(t))]

        r_peaks_path = analysis_folder / "r_peaks.csv"

        with open(r_peaks_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "peak_number",
                "sample_index",
                "time_s",
                "raw_value",
                "filtered_analysis_value"
            ])

            for i, idx in enumerate(valid, start=1):
                writer.writerow([
                    i,
                    int(idx),
                    float(t[idx]),
                    float(y_raw[idx]),
                    float(y_analysis[idx])
                ])

        rr_path = analysis_folder / "rr_intervals.csv"

        peak_times = np.asarray(self.current_metrics.get("peak_times_s", []), dtype=float)
        rr_ms = np.asarray(self.current_metrics.get("rr_intervals_ms", []), dtype=float)

        with open(rr_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "rr_number",
                "beat_time_s",
                "rr_interval_ms"
            ])

            for i, rr in enumerate(rr_ms):
                beat_time = peak_times[i + 1] if i + 1 < len(peak_times) else ""
                writer.writerow([
                    i + 1,
                    float(beat_time) if beat_time != "" else "",
                    float(rr)
                ])

        metadata = self.recording.get("metadata", {}) if self.recording is not None else {}

        report = {
            "software": "OpenPhysiologyLab",
            "analysis_saved_datetime": datetime.now().isoformat(timespec="seconds"),
            "recording_folder": str(self.recording["folder"]),
            "source_files": {
                "raw": "raw.csv",
                "metadata": "metadata.json",
                "markers": "markers.csv"
            },
            "study_context": metadata.get("study_context", {}),
            "electrode_placement": metadata.get("electrode_placement"),
            "electrode_pin_mapping": metadata.get("electrode_pin_mapping"),
            "raw_signal_handling": {
                "raw_csv_contains": "Original ADC values from device stream",
                "raw_csv_modified_by_recorder_display_inversion": False,
                "raw_csv_modified_by_analysis_inversion": False,
                "raw_csv_modified_by_filtering": False,
                "filtering_location": "In-memory analysis signal generated from raw.csv",
                "peak_detection_source": "Filtered-from-raw analysis signal",
                "adc_headroom_source": "Original raw ADC values"
            },
            "machine_profile": metadata.get("machine_profile"),
            "latest_machine_evaluation_before_recording": metadata.get("latest_machine_evaluation_before_recording"),
            "session_machine_evaluation": metadata.get("session_machine_evaluation"),
            "session_machine_evaluation_report_path": metadata.get("session_machine_evaluation_report_path"),
            "provenance": self.get_provenance_report(),
            "signal_quality": self.get_signal_quality_report(silent=True),
            "analysis_rule": (
                "raw.csv was used as the source data. Current filter settings were applied "
                "to raw.csv to generate the analysis signal. No filtered saved file was used as source."
            ),
            "channel": self.current_channel,
            "filter_settings": {
                "low_hz": float(self.low_spin.value()),
                "high_hz": float(self.high_spin.value()),
                "notch_50hz": bool(self.notch_checkbox.isChecked()),
                "inverted": bool(self.invert_checkbox.isChecked())
            },
            "selection": self.active_selection,
            "peak_detection": self.peak_result if self.peak_result is not None else {},
            "metrics": self.current_metrics,
            "outputs": {
                "r_peaks_csv": "r_peaks.csv",
                "rr_intervals_csv": "rr_intervals.csv",
                "analysis_report_json": "analysis_report.json"
            }
        }

        report_path = analysis_folder / "analysis_report.json"

        with open(report_path, "w") as f:
            json.dump(self.make_json_safe(report), f, indent=4)

        self.latest_analysis_report_path = report_path

        summary_path = analysis_folder / "analysis_summary.csv"

        with open(summary_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["parameter", "value"])

            for key, value in self.current_metrics.items():
                if isinstance(value, (list, tuple, np.ndarray)):
                    continue

                value = self.make_json_safe(value)
                writer.writerow([key, value])

    def add_marker_lines(self, plot):
        if self.recording is None:
            return

        markers = self.recording.get("markers", [])

        for marker in markers:
            time_s = marker.get("time_s", None)

            if time_s is None:
                continue

            try:
                time_s = float(time_s)
            except Exception:
                continue

            label = marker.get("label", "")

            line = pg.InfiniteLine(
                pos=time_s,
                angle=90,
                movable=False,
                pen=pg.mkPen('#FF2BC2', width=1)
            )

            try:
                line.setToolTip(
                    f"Marker #{marker.get('marker_id')}\n"
                    f"Time: {time_s:.3f} s\n"
                    f"Label: {label}"
                )
            except Exception:
                pass

            plot.addItem(line)

    def showEvent(self, event):
        try:
            super().showEvent(event)
        except Exception:
            pass

        try:
            self.apply_analysis_emerald_accents()
        except Exception:
            pass

    def apply_analysis_emerald_accents(self):
        """
        Make Analysis page summary/metrics headings emerald.

        This only changes visual styling. It does not touch analysis logic.
        """

        try:
            from PyQt5.QtWidgets import QGroupBox, QLabel
        except Exception:
            return

        target_titles = {
            "record summary",
            "recording summary",
            "record summary / metadata",
            "analysis metrics",
            "metrics",
            "selection analysis",
        }

        group_style = """
            QGroupBox {
                background-color: #0E1218;
                border: 1px solid #2D333F;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 9px;
                color: #50C878;
                font-weight: 400;
            }

            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 9px;
                padding: 0px 6px;
                background-color: #0E1218;
                color: #50C878;
                font-weight: 400;
            }
        """

        label_style = """
            color: #50C878;
            font-weight: 400;
            background-color: transparent;
        """

        try:
            for box in self.findChildren(QGroupBox):
                title = str(box.title()).strip().lower()

                if title in target_titles:
                    box.setStyleSheet(group_style)
        except Exception:
            pass

        try:
            for label in self.findChildren(QLabel):
                txt = str(label.text()).strip().lower()

                if txt in target_titles:
                    label.setStyleSheet(label_style)
        except Exception:
            pass


