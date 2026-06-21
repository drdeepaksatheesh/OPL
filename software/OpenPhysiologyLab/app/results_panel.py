import json
import base64
import html
from pathlib import Path

import numpy as np
import pyqtgraph as pg

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QFileDialog, QGroupBox, QSplitter
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ResultsPanel(QWidget):
    """
    OpenPhysiologyLab Results panel.

    Report-only scientific dashboard.

    It reads saved analysis_report.json and displays:
    - recording summary
    - machine/session evaluation
    - signal quality
    - peak detection
    - HR/RR/HRV metrics
    - RR tachogram
    - RR histogram
    - Poincare plot

    It does not recalculate analysis.
    """

    def __init__(self):
        super().__init__()

        self.current_report_path = None
        self.current_report = None

        self.setWindowTitle("OpenPhysiologyLab Results Panel")

        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        self.setLayout(layout)

        title = QLabel("OpenPhysiologyLab Results Panel")
        title.setStyleSheet(
            "font-size: 18px; font-weight: bold; color: #F2F2F4; padding: 2px;"
        )
        layout.addWidget(title)

        info = QLabel(
            "Results tab = final report dashboard. It reads saved analysis_report.json "
            "and shows machine status, signal quality, HR/RR/HRV metrics, and scientific plots."
        )
        info.setWordWrap(True)
        info.setStyleSheet(
            "font-weight: 400; color: #D4AF37; padding: 6px; "
            "background-color: #0E1218; border: 1px solid #202630; border-radius: 6px;"
        )
        layout.addWidget(info)

        controls = QGroupBox("Results Source")
        controls_layout = QHBoxLayout()
        controls_layout.setContentsMargins(8, 12, 8, 8)
        controls_layout.setSpacing(8)
        controls.setLayout(controls_layout)

        self.load_btn = QPushButton("Load Analysis Report")
        self.load_btn.clicked.connect(self.load_report_clicked)
        controls_layout.addWidget(self.load_btn)

        self.latest_btn = QPushButton("Load Latest Saved Analysis")
        self.latest_btn.clicked.connect(self.load_latest_report)
        controls_layout.addWidget(self.latest_btn)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh_current_report)
        controls_layout.addWidget(self.refresh_btn)

        self.export_btn = QPushButton("Export Results Report")
        self.export_btn.setToolTip(
            "Export current Results dashboard as HTML and save plot images."
        )
        self.export_btn.clicked.connect(self.export_results_report)
        controls_layout.addWidget(self.export_btn)

        self.path_label = QLabel("No report loaded")
        self.path_label.setWordWrap(True)
        controls_layout.addWidget(self.path_label, stretch=1)

        layout.addWidget(controls)

        # ------------------------------------------------------------
        # Main scientific dashboard
        # ------------------------------------------------------------

        self.main_splitter = QSplitter(Qt.Horizontal)

        left_group = QGroupBox("Scientific Report")
        left_layout = QVBoxLayout()
        left_group.setLayout(left_layout)

        self.report_box = QTextEdit()
        self.report_box.setReadOnly(True)
        self.report_box.setObjectName("resultsReportBox")
        left_layout.addWidget(self.report_box)

        right_group = QGroupBox("Plots")
        right_layout = QVBoxLayout()
        right_group.setLayout(right_layout)

        self.rr_tachogram = pg.PlotWidget()
        self.configure_plot(self.rr_tachogram, "RR Tachogram", "Time", "RR interval (ms)")
        right_layout.addWidget(self.rr_tachogram, stretch=1)

        self.rr_histogram = pg.PlotWidget()
        self.configure_plot(self.rr_histogram, "RR Histogram", "RR interval (ms)", "Count")
        right_layout.addWidget(self.rr_histogram, stretch=1)

        self.poincare_plot = pg.PlotWidget()
        self.configure_plot(self.poincare_plot, "Poincaré Plot", "RR n (ms)", "RR n+1 (ms)")
        right_layout.addWidget(self.poincare_plot, stretch=1)

        self.main_splitter.addWidget(left_group)
        self.main_splitter.addWidget(right_group)
        self.main_splitter.setSizes([720, 680])

        layout.addWidget(self.main_splitter, stretch=1)

        self.apply_dark_style()
        self.show_empty_message()

    # ------------------------------------------------------------
    # Styling
    # ------------------------------------------------------------

    def apply_dark_style(self):
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

            QGroupBox {
                background-color: #0E1218;
                border: 1px solid #2D333F;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 9px;
                color: #D4AF37;
                font-weight: 400;
            }

            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 9px;
                padding: 0px 6px;
                background-color: #0E1218;
                color: #D4AF37;
                font-weight: 400;
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

            QTextEdit {
                background-color: #080B10;
                color: #F2F2F4;
                border: 1px solid #2D333F;
                border-radius: 6px;
                padding: 8px;
                selection-background-color: #D4AF37;
                selection-color: #000000;
            }

            QTextEdit#resultsReportBox {
                background-color: #080B10;
                color: #F2F2F4;
                border: 1px solid #2D333F;
                border-radius: 8px;
                padding: 10px;
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

    def configure_plot(self, plot, title, x_label, y_label):
        """
        Configure Results plots as locked scientific monitors.

        Same philosophy as Recorder/Analysis:
        - no accidental zoom/pan
        - no right-click menu
        - no pyqtgraph auto buttons
        - stable display
        """

        plot.setBackground("#020304")
        plot.setTitle(title, color="#D4AF37", size="10pt")
        plot.setLabel("bottom", x_label)
        plot.setLabel("left", y_label)
        plot.showGrid(x=True, y=True, alpha=0.28)

        # Lock interactive behaviour.
        plot.setMouseEnabled(x=False, y=False)
        plot.setMenuEnabled(False)

        try:
            plot.hideButtons()
        except Exception:
            pass

        try:
            vb = plot.getViewBox()
            vb.setMenuEnabled(False)
            vb.setMouseEnabled(x=False, y=False)
            vb.disableAutoRange()
        except Exception:
            pass

        try:
            for axis_name in ["left", "bottom"]:
                axis = plot.getAxis(axis_name)
                axis.setPen(pg.mkPen("#C6CBD5"))
                axis.setTextPen(pg.mkPen("#C6CBD5"))
        except Exception:
            pass

    def lock_plot_view(self, plot):
        """
        Re-lock monitor after plotting/autorange.
        """

        try:
            plot.setMouseEnabled(x=False, y=False)
            plot.setMenuEnabled(False)
            plot.hideButtons()
        except Exception:
            pass

        try:
            vb = plot.getViewBox()
            vb.setMenuEnabled(False)
            vb.setMouseEnabled(x=False, y=False)
        except Exception:
            pass

    def safe_set_plot_range(self, plot, x_values=None, y_values=None, pad_fraction=0.08):
        """
        Apply a sensible fixed range after plotting.

        This avoids wild auto-zoom behaviour and keeps the Results plots
        looking like instrument monitors.
        """

        try:
            if x_values is not None:
                x = np.asarray(x_values, dtype=float)
                x = x[np.isfinite(x)]

                if len(x) > 0:
                    x_min = float(np.min(x))
                    x_max = float(np.max(x))

                    if x_max <= x_min:
                        x_max = x_min + 1.0

                    x_pad = max((x_max - x_min) * pad_fraction, 0.5)
                    plot.setXRange(x_min - x_pad, x_max + x_pad, padding=0)

            if y_values is not None:
                y = np.asarray(y_values, dtype=float)
                y = y[np.isfinite(y)]

                if len(y) > 0:
                    y_min = float(np.min(y))
                    y_max = float(np.max(y))

                    if y_max <= y_min:
                        y_max = y_min + 1.0

                    y_pad = max((y_max - y_min) * pad_fraction, 5.0)
                    plot.setYRange(y_min - y_pad, y_max + y_pad, padding=0)

            self.lock_plot_view(plot)

        except Exception:
            pass


    def set_external_theme(self, light_mode):
        self.apply_dark_style()

    def html_style(self):
        return """
        <style>
            body {
                color: #F2F2F4;
                font-family: Segoe UI, Arial;
                font-size: 10pt;
                line-height: 1.35;
            }

            .title {
                color: #D4AF37;
                font-size: 12pt;
                font-weight: 600;
                margin-bottom: 8px;
            }

            .section {
                color: #D4AF37;
                font-size: 10.5pt;
                font-weight: 500;
                margin-top: 14px;
                margin-bottom: 5px;
            }

            .label {
                color: #C6CBD5;
                font-weight: 400;
            }

            .value {
                color: #F2F2F4;
                font-weight: 400;
            }

            .good {
                color: #50C878;
                font-weight: 700;
            }

            .warning {
                color: #D4AF37;
                font-weight: 700;
            }

            .fail {
                color: #FF5C5C;
                font-weight: 700;
            }

            .note {
                color: #F2F2F4;
                font-weight: 400;
                line-height: 1.35;
            }

            .smallnote {
                color: #8F96A6;
                font-size: 9pt;
            }

            .goodbox {
                color: #F2F2F4;
                background-color: rgba(80, 200, 120, 24);
                border-left: 3px solid #50C878;
                padding: 8px 10px;
                margin-top: 8px;
                margin-bottom: 8px;
            }

            .warnbox {
                color: #F2F2F4;
                background-color: rgba(212, 175, 55, 28);
                border-left: 3px solid #D4AF37;
                padding: 8px 10px;
                margin-top: 8px;
                margin-bottom: 8px;
            }

            .failbox {
                color: #F2F2F4;
                background-color: rgba(255, 92, 92, 28);
                border-left: 3px solid #FF5C5C;
                padding: 8px 10px;
                margin-top: 8px;
                margin-bottom: 8px;
            }

            .metric-card {
                background-color: rgba(14, 18, 24, 150);
                border: 1px solid #2D333F;
                padding: 6px;
            }

            table {
                border-collapse: collapse;
            }

            td {
                padding: 3px 14px 3px 0px;
                vertical-align: top;
            }
        </style>
        """

    # ------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------

    def show_empty_message(self):
        self.report_box.setHtml(
            f"""
            <html>
            <head>{self.html_style()}</head>
            <body>
                <div class='title'>No Results Loaded</div>
                <div class='note'>
                    Save an analysis from the Analysis tab, then click
                    <span class='label'>Load Latest Saved Analysis</span>.
                    You can also manually load an analysis_report.json file.
                </div>
            </body>
            </html>
            """
        )
        self.clear_plots()

    def showEvent(self, event):
        try:
            super().showEvent(event)
        except Exception:
            pass

        if self.current_report_path is None:
            try:
                self.load_latest_report(silent=True)
            except Exception:
                pass

    def load_report_clicked(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose analysis_report.json",
            str(PROJECT_ROOT / "recordings"),
            "Analysis Report (analysis_report.json);;JSON Files (*.json);;All Files (*.*)"
        )

        if not path:
            return

        self.load_report_path(Path(path))

    def find_latest_analysis_report(self):
        recordings = PROJECT_ROOT / "recordings"

        if not recordings.exists():
            return None

        candidates = list(recordings.glob("**/analysis/analysis_report.json"))

        if not candidates:
            return None

        candidates = sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)
        return candidates[0]

    def load_latest_report(self, silent=False):
        report_path = self.find_latest_analysis_report()

        if report_path is None:
            if not silent:
                self.path_label.setText("No saved analysis_report.json found.")
                self.show_empty_message()
            return False

        return self.load_report_path(report_path)

    def refresh_current_report(self):
        if self.current_report_path is None:
            self.load_latest_report()
            return

        self.load_report_path(self.current_report_path)

    def load_report_path(self, report_path):
        report_path = Path(report_path)

        try:
            with open(report_path, "r", encoding="utf-8") as f:
                report = json.load(f)
        except Exception as e:
            self.path_label.setText(f"Could not load report: {report_path}")
            self.report_box.setText(f"Could not load analysis report:\n{e}")
            self.clear_plots()
            return False

        self.current_report_path = report_path
        self.current_report = report

        self.path_label.setText(str(report_path))
        self.report_box.setHtml(self.format_results_report(report, report_path))
        self.update_plots(report)

        return True

    # ------------------------------------------------------------
    # Formatting helpers
    # ------------------------------------------------------------

    def esc(self, value):
        return html.escape(str(value), quote=True)

    def fmt(self, value, digits=3):
        try:
            return f"{float(value):.{digits}f}"
        except Exception:
            return "unknown"

    def status_class(self, status):
        s = str(status).upper()

        if s == "PASS":
            return "good"

        if s == "FAIL":
            return "fail"

        if s == "CAUTION":
            return "warning"

        return "value"

    def machine_warning_box(self, session_eval):
        if not isinstance(session_eval, dict) or not session_eval:
            return """
            <div class='warnbox'>
                No session machine evaluation found in this analysis report.
                Interpret results with caution.
            </div>
            """

        status = str(session_eval.get("overall_status", "unknown")).upper()
        usability = session_eval.get("usability", {}) or {}
        interpretation = usability.get("interpretation", session_eval.get("summary", ""))

        if status == "PASS":
            return f"""
            <div class='goodbox'>
                <span class='good'>Machine/session status: PASS.</span>
                ADC headroom was acceptable for this recording.
                <br>{self.esc(interpretation)}
            </div>
            """

        if status == "FAIL":
            return f"""
            <div class='failbox'>
                <span class='fail'>Machine/session status: FAIL.</span>
                ADC/headroom or channel-quality problems were detected.
                RR timing may still be usable only if R peaks are visually correct.
                Do not trust amplitude or morphology from this recording.
                <br>{self.esc(interpretation)}
            </div>
            """

        return f"""
        <div class='warnbox'>
            <span class='warning'>Machine/session status: {self.esc(status)}.</span>
            Use timing/amplitude/morphology according to the usability fields below.
            <br>{self.esc(interpretation)}
        </div>
        """

    def format_study_context_html(self, study_context):
        """
        Render project/subject/session metadata.
        """

        if not isinstance(study_context, dict) or not study_context:
            return """
            <div class='section'>Project / subject / session</div>
            <div class='warnbox'>
                No study_context metadata found in this report.
            </div>
            """

        return f"""
        <div class='section'>Project / subject / session</div>
        <table>
            <tr><td class='label'>Project</td><td class='value'>{self.esc(study_context.get('project_name', ''))}</td></tr>
            <tr><td class='label'>Subject ID</td><td class='value'>{self.esc(study_context.get('subject_id', ''))}</td></tr>
            <tr><td class='label'>Session label</td><td class='value'>{self.esc(study_context.get('session_label', ''))}</td></tr>
            <tr><td class='label'>Condition</td><td class='value'>{self.esc(study_context.get('condition', ''))}</td></tr>
            <tr><td class='label'>Posture</td><td class='value'>{self.esc(study_context.get('posture', ''))}</td></tr>
            <tr><td class='label'>Notes</td><td class='value'>{self.esc(study_context.get('session_notes', ''))}</td></tr>
        </table>
        """


    def format_electrode_mapping_html(self, mapping):
        """
        Render electrode-to-pin mapping from analysis_report.json.
        """

        if not isinstance(mapping, dict) or not mapping:
            return """
            <div class='section'>Electrode / pin mapping</div>
            <div class='warnbox'>
                No explicit electrode_pin_mapping found in this report.
                Older recordings may only contain a free-text electrode placement field.
            </div>
            """

        pin_mapping = mapping.get("pin_mapping", {}) or {}
        body_mapping = mapping.get("body_mapping", {}) or {}

        rows = ""

        if pin_mapping:
            for pin, body in pin_mapping.items():
                rows += (
                    f"<tr><td class='label'>{self.esc(pin)}</td>"
                    f"<td class='value'>{self.esc(body)}</td></tr>"
                )
        elif body_mapping:
            for body, pin in body_mapping.items():
                rows += (
                    f"<tr><td class='label'>{self.esc(body)}</td>"
                    f"<td class='value'>{self.esc(pin)}</td></tr>"
                )
        else:
            rows = "<tr><td class='value'>No pin mapping details available.</td></tr>"

        return f"""
        <div class='section'>Electrode / pin mapping</div>
        <table>
            <tr><td class='label'>Configuration</td><td class='value'>{self.esc(mapping.get('configuration_label', 'unknown'))}</td></tr>
            {rows}
        </table>

        <div class='note'>
            {self.esc(mapping.get('textbook_lead_ii_note', mapping.get('textbook_note', '')))}
        </div>

        <div class='smallnote'>
            {self.esc(mapping.get('raw_signal_policy', ''))}
        </div>
        """

    def format_raw_signal_handling_html(self, handling):
        """
        Render raw-signal provenance.
        """

        if not isinstance(handling, dict) or not handling:
            return ""

        return f"""
        <div class='section'>Raw signal handling</div>
        <table>
            <tr><td class='label'>raw.csv contains</td><td class='value'>{self.esc(handling.get('raw_csv_contains', 'unknown'))}</td></tr>
            <tr><td class='label'>Recorder display inversion modified raw.csv</td><td class='value'>{self.esc(handling.get('raw_csv_modified_by_recorder_display_inversion', 'unknown'))}</td></tr>
            <tr><td class='label'>Analysis inversion modified raw.csv</td><td class='value'>{self.esc(handling.get('raw_csv_modified_by_analysis_inversion', 'unknown'))}</td></tr>
            <tr><td class='label'>Filtering modified raw.csv</td><td class='value'>{self.esc(handling.get('raw_csv_modified_by_filtering', 'unknown'))}</td></tr>
            <tr><td class='label'>Filtering location</td><td class='value'>{self.esc(handling.get('filtering_location', 'unknown'))}</td></tr>
            <tr><td class='label'>ADC headroom source</td><td class='value'>{self.esc(handling.get('adc_headroom_source', 'unknown'))}</td></tr>
        </table>
        """


    def format_results_report(self, report, report_path):
        metadata_machine = report.get("machine_profile", {}) or {}
        session_eval = report.get("session_machine_evaluation", {}) or {}
        signal_quality = report.get("signal_quality", {}) or {}
        peak_detection = report.get("peak_detection", {}) or {}
        metrics = report.get("metrics", {}) or {}
        provenance = report.get("provenance", {}) or {}
        filter_settings = report.get("filter_settings", {}) or {}
        study_context = report.get("study_context", {}) or {}
        electrode_mapping = report.get("electrode_pin_mapping", {}) or {}
        raw_signal_handling = report.get("raw_signal_handling", {}) or {}

        recording_folder = report.get("recording_folder", "unknown")
        channel = report.get("channel", "unknown")

        machine_uid = metadata_machine.get("machine_uid", "unknown")
        device_label = metadata_machine.get("device_id_user_label", "unknown")

        session_status = session_eval.get("overall_status", "unknown")
        usability = session_eval.get("usability", {}) or {}

        raw_stats = signal_quality.get("raw_signal_stats", {}) or {}
        filt_noise = signal_quality.get("filtered_noise_estimates", {}) or {}
        raw_art = signal_quality.get("raw_artifact_flags", {}) or {}
        rr_quality = signal_quality.get("rr_quality", {}) or {}
        flags = signal_quality.get("interpretation_flags", []) or []

        flags_html = ""
        if flags:
            flags_html = "".join([f"<div class='note'>• {self.esc(flag)}</div>" for flag in flags])
        else:
            flags_html = "<div class='note'>No signal-quality interpretation flags.</div>"

        html_text = f"""
        <html>
        <head>{self.html_style()}</head>
        <body>
            <div class='title'>OpenPhysiologyLab Results Summary</div>

            {self.machine_warning_box(session_eval)}

            <div class='section'>Key metrics</div>
            <table>
                <tr>
                    <td class='label'>HR count-based</td><td class='value'>{self.fmt(metrics.get('hr_count_based_bpm'))} bpm</td>
                    <td class='label'>HR RR-based</td><td class='value'>{self.fmt(metrics.get('hr_rr_based_bpm'))} bpm</td>
                </tr>
                <tr>
                    <td class='label'>RR mean</td><td class='value'>{self.fmt(metrics.get('rr_mean_ms'))} ms</td>
                    <td class='label'>RR median</td><td class='value'>{self.fmt(metrics.get('rr_median_ms'))} ms</td>
                </tr>
                <tr>
                    <td class='label'>SDNN</td><td class='value'>{self.fmt(metrics.get('sdnn_ms'))} ms</td>
                    <td class='label'>RMSSD</td><td class='value'>{self.fmt(metrics.get('rmssd_ms'))} ms</td>
                </tr>
                <tr>
                    <td class='label'>pNN50</td><td class='value'>{self.fmt(metrics.get('pnn50_percent'))} %</td>
                    <td class='label'>Peak count</td><td class='value'>{self.esc(metrics.get('peak_count', 'unknown'))}</td>
                </tr>
            </table>

            {self.format_study_context_html(study_context)}

            <div class='section'>Recording summary</div>
            <table>
                <tr><td class='label'>Report path</td><td class='value'>{self.esc(report_path)}</td></tr>
                <tr><td class='label'>Recording folder</td><td class='value'>{self.esc(recording_folder)}</td></tr>
                <tr><td class='label'>Saved datetime</td><td class='value'>{self.esc(report.get('analysis_saved_datetime', 'unknown'))}</td></tr>
                <tr><td class='label'>Channel</td><td class='value'>{self.esc(channel)}</td></tr>
                <tr><td class='label'>Source data</td><td class='value'>{self.esc(provenance.get('source_data', 'raw.csv'))}</td></tr>
                <tr><td class='label'>Raw modified</td><td class='value'>{self.esc(provenance.get('raw_data_modified', False))}</td></tr>
            </table>

            {self.format_electrode_mapping_html(electrode_mapping)}

            {self.format_raw_signal_handling_html(raw_signal_handling)}

            <div class='section'>Machine / session status</div>
            <table>
                <tr><td class='label'>Machine UID</td><td class='value'>{self.esc(machine_uid)}</td></tr>
                <tr><td class='label'>Device label</td><td class='value'>{self.esc(device_label)}</td></tr>
                <tr><td class='label'>Evaluation type</td><td class='value'>{self.esc(session_eval.get('evaluation_type', 'unknown'))}</td></tr>
                <tr><td class='label'>Protocol</td><td class='value'>{self.esc(session_eval.get('protocol_name', 'unknown'))}</td></tr>
                <tr><td class='label'>Status</td><td class='{self.status_class(session_status)}'>{self.esc(session_status)}</td></tr>
                <tr><td class='label'>Timing</td><td class='value'>{self.esc(usability.get('timing', 'unknown'))}</td></tr>
                <tr><td class='label'>Amplitude</td><td class='value'>{self.esc(usability.get('amplitude', 'unknown'))}</td></tr>
                <tr><td class='label'>Morphology</td><td class='value'>{self.esc(usability.get('morphology', 'unknown'))}</td></tr>
                <tr><td class='label'>Teaching demo</td><td class='value'>{self.esc(usability.get('teaching_demo', 'unknown'))}</td></tr>
            </table>

            <div class='section'>Signal quality</div>
            <table>
                <tr><td class='label'>Duration</td><td class='value'>{self.fmt(signal_quality.get('duration_s'))} s</td></tr>
                <tr><td class='label'>Sampling rate</td><td class='value'>{self.fmt(signal_quality.get('sampling_rate_hz'))} Hz</td></tr>
                <tr><td class='label'>Raw min / max</td><td class='value'>{self.fmt(raw_stats.get('min'))} / {self.fmt(raw_stats.get('max'))}</td></tr>
                <tr><td class='label'>Raw peak-to-peak</td><td class='value'>{self.fmt(raw_stats.get('peak_to_peak'))}</td></tr>
                <tr><td class='label'>Low clipping</td><td class='value'>{self.esc(raw_art.get('possible_clipping_low_count', 'unknown'))}</td></tr>
                <tr><td class='label'>High clipping</td><td class='value'>{self.esc(raw_art.get('possible_clipping_high_count', 'unknown'))}</td></tr>
                <tr><td class='label'>Large jumps</td><td class='value'>{self.esc(raw_art.get('large_jump_count', 'unknown'))}</td></tr>
                <tr><td class='label'>Filtered 50 Hz ratio</td><td class='value'>{self.fmt(filt_noise.get('powerline_to_signal_ratio'), 6)}</td></tr>
            </table>

            <div class='section'>Signal-quality flags</div>
            {flags_html}

            <div class='section'>Peak detection</div>
            <table>
                <tr><td class='label'>Method</td><td class='value'>{self.esc(peak_detection.get('method', 'unknown'))}</td></tr>
                <tr><td class='label'>Polarity</td><td class='value'>{self.esc(peak_detection.get('polarity', 'unknown'))}</td></tr>
                <tr><td class='label'>Polarity source</td><td class='value'>{self.esc(peak_detection.get('polarity_source', 'unknown'))}</td></tr>
                <tr><td class='label'>RR count</td><td class='value'>{self.esc(rr_quality.get('rr_count', 'unknown'))}</td></tr>
                <tr><td class='label'>RR outliers</td><td class='value'>{self.esc(rr_quality.get('rr_outlier_count', 'unknown'))}</td></tr>
                <tr><td class='label'>Detection warning</td><td class='value'>{self.esc(peak_detection.get('warning', None))}</td></tr>
            </table>

            <div class='section'>Filter and provenance</div>
            <table>
                <tr><td class='label'>Low Hz</td><td class='value'>{self.esc(filter_settings.get('low_hz', 'unknown'))}</td></tr>
                <tr><td class='label'>High Hz</td><td class='value'>{self.esc(filter_settings.get('high_hz', 'unknown'))}</td></tr>
                <tr><td class='label'>50 Hz notch</td><td class='value'>{self.esc(filter_settings.get('notch_50hz', 'unknown'))}</td></tr>
                <tr><td class='label'>Inverted</td><td class='value'>{self.esc(filter_settings.get('inverted', 'unknown'))}</td></tr>
            </table>

            <div class='section'>Interpretation note</div>
            <div class='note'>
                Results shown here are read from saved analysis_report.json.
                This tab does not recalculate peaks or metrics.
                If you edit peaks or rerun analysis, save again and refresh this tab.
            </div>
        </body>
        </html>
        """

        return html_text

    # ------------------------------------------------------------
    # Compare Reports
    # ------------------------------------------------------------

    def compare_reports_clicked(self):
        """
        Compare two analysis_report.json files.

        User-friendly two-step selection:
        1. choose Report A
        2. choose Report B

        This is report-only. It does not recalculate peaks, filters,
        HRV, or machine evaluation.
        """

        default_dir = PROJECT_ROOT / "recordings"

        # If a report is already loaded, start near that report.
        try:
            if self.current_report_path is not None:
                default_dir = Path(self.current_report_path).parent
        except Exception:
            pass

        path_a, _ = QFileDialog.getOpenFileName(
            self,
            "Choose Report A: analysis_report.json",
            str(default_dir),
            "JSON Files (*.json);;All Files (*.*)"
        )

        if not path_a:
            return

        path_a = Path(path_a)

        path_b, _ = QFileDialog.getOpenFileName(
            self,
            "Choose Report B: analysis_report.json",
            str(PROJECT_ROOT / "recordings"),
            "JSON Files (*.json);;All Files (*.*)"
        )

        if not path_b:
            self.report_box.setHtml(
                f"""
                <html>
                <head>{self.html_style()}</head>
                <body>
                    <div class='title'>Compare Reports</div>
                    <div class='warnbox'>
                        Report A was selected, but Report B was not selected.
                        Click Compare Reports again and choose two reports.
                    </div>
                    <div class='section'>Selected Report A</div>
                    <div class='note'>{self.esc(path_a)}</div>
                </body>
                </html>
                """
            )
            self.path_label.setText(f"Compare waiting for Report B. Report A: {path_a.name}")
            return

        path_b = Path(path_b)

        try:
            with open(path_a, "r", encoding="utf-8") as f:
                report_a = json.load(f)

            with open(path_b, "r", encoding="utf-8") as f:
                report_b = json.load(f)

        except Exception as e:
            self.report_box.setHtml(
                f"""
                <html>
                <head>{self.html_style()}</head>
                <body>
                    <div class='title'>Compare Reports</div>
                    <div class='failbox'>
                        Could not load comparison reports.<br>{self.esc(e)}
                    </div>
                </body>
                </html>
                """
            )
            return

        self.current_comparison = {
            "path_a": path_a,
            "path_b": path_b,
            "report_a": report_a,
            "report_b": report_b,
        }

        self.report_box.setHtml(
            self.format_comparison_report(
                report_a=report_a,
                report_b=report_b,
                path_a=path_a,
                path_b=path_b
            )
        )

        self.path_label.setText(
            f"Comparison loaded: {path_a.parent.parent.name} vs {path_b.parent.parent.name}"
        )


    def nested_get(self, data, path, default=""):
        """
        Safe nested dictionary read.
        path example: "metrics.rr_mean_ms"
        """

        try:
            current = data

            for part in path.split("."):
                if isinstance(current, dict):
                    current = current.get(part, default)
                else:
                    return default

            if current is None:
                return default

            return current

        except Exception:
            return default

    def compare_fmt(self, value, digits=3):
        """
        Format comparison values.
        """

        if value is None:
            return ""

        if isinstance(value, bool):
            return str(value)

        try:
            if isinstance(value, (int, float)):
                return f"{float(value):.{digits}f}"
        except Exception:
            pass

        return str(value)

    def comparison_status_class(self, value):
        s = str(value).upper()

        if s == "PASS":
            return "good"

        if s in ["CAUTION", "WARNING"]:
            return "warning"

        if s == "FAIL":
            return "fail"

        return "value"

    def comparison_row(self, label, a, b, digits=3, status=False):
        a_text = self.compare_fmt(a, digits=digits)
        b_text = self.compare_fmt(b, digits=digits)

        if status:
            a_class = self.comparison_status_class(a_text)
            b_class = self.comparison_status_class(b_text)
        else:
            a_class = "value"
            b_class = "value"

        return (
            f"<tr>"
            f"<td class='label'>{self.esc(label)}</td>"
            f"<td class='{a_class}'>{self.esc(a_text)}</td>"
            f"<td class='{b_class}'>{self.esc(b_text)}</td>"
            f"</tr>"
        )

    def format_comparison_section(self, title, rows):
        return f"""
        <div class='section'>{self.esc(title)}</div>
        <table>
            <tr>
                <td class='label'></td>
                <td class='label'>Report A</td>
                <td class='label'>Report B</td>
            </tr>
            {''.join(rows)}
        </table>
        """

    def format_comparison_report(self, report_a, report_b, path_a, path_b):
        """
        Format side-by-side comparison of two analysis reports.
        """

        rows_study = [
            self.comparison_row(
                "Project",
                self.nested_get(report_a, "study_context.project_name"),
                self.nested_get(report_b, "study_context.project_name")
            ),
            self.comparison_row(
                "Subject ID",
                self.nested_get(report_a, "study_context.subject_id"),
                self.nested_get(report_b, "study_context.subject_id")
            ),
            self.comparison_row(
                "Session label",
                self.nested_get(report_a, "study_context.session_label"),
                self.nested_get(report_b, "study_context.session_label")
            ),
            self.comparison_row(
                "Condition",
                self.nested_get(report_a, "study_context.condition"),
                self.nested_get(report_b, "study_context.condition")
            ),
            self.comparison_row(
                "Posture",
                self.nested_get(report_a, "study_context.posture"),
                self.nested_get(report_b, "study_context.posture")
            ),
            self.comparison_row(
                "Notes",
                self.nested_get(report_a, "study_context.session_notes"),
                self.nested_get(report_b, "study_context.session_notes")
            ),
        ]

        rows_recording = [
            self.comparison_row(
                "Recording folder",
                Path(str(report_a.get("recording_folder", ""))).name,
                Path(str(report_b.get("recording_folder", ""))).name
            ),
            self.comparison_row(
                "Saved datetime",
                report_a.get("analysis_saved_datetime", ""),
                report_b.get("analysis_saved_datetime", "")
            ),
            self.comparison_row(
                "Signal type",
                self.nested_get(report_a, "electrode_pin_mapping.signal_type"),
                self.nested_get(report_b, "electrode_pin_mapping.signal_type")
            ),
            self.comparison_row(
                "Electrode configuration",
                self.nested_get(report_a, "electrode_pin_mapping.configuration_label"),
                self.nested_get(report_b, "electrode_pin_mapping.configuration_label")
            ),
            self.comparison_row(
                "A0P",
                self.nested_get(report_a, "electrode_pin_mapping.pin_mapping.A0P"),
                self.nested_get(report_b, "electrode_pin_mapping.pin_mapping.A0P")
            ),
            self.comparison_row(
                "A0N",
                self.nested_get(report_a, "electrode_pin_mapping.pin_mapping.A0N"),
                self.nested_get(report_b, "electrode_pin_mapping.pin_mapping.A0N")
            ),
            self.comparison_row(
                "REF",
                self.nested_get(report_a, "electrode_pin_mapping.pin_mapping.REF"),
                self.nested_get(report_b, "electrode_pin_mapping.pin_mapping.REF")
            ),
        ]

        rows_machine = [
            self.comparison_row(
                "Machine UID",
                self.nested_get(report_a, "machine_profile.machine_uid"),
                self.nested_get(report_b, "machine_profile.machine_uid")
            ),
            self.comparison_row(
                "Machine status",
                self.nested_get(report_a, "session_machine_evaluation.overall_status"),
                self.nested_get(report_b, "session_machine_evaluation.overall_status"),
                status=True
            ),
            self.comparison_row(
                "Timing usability",
                self.nested_get(report_a, "session_machine_evaluation.usability.timing"),
                self.nested_get(report_b, "session_machine_evaluation.usability.timing"),
                status=True
            ),
            self.comparison_row(
                "Amplitude usability",
                self.nested_get(report_a, "session_machine_evaluation.usability.amplitude"),
                self.nested_get(report_b, "session_machine_evaluation.usability.amplitude"),
                status=True
            ),
            self.comparison_row(
                "Morphology usability",
                self.nested_get(report_a, "session_machine_evaluation.usability.morphology"),
                self.nested_get(report_b, "session_machine_evaluation.usability.morphology"),
                status=True
            ),
            self.comparison_row(
                "Teaching demo usability",
                self.nested_get(report_a, "session_machine_evaluation.usability.teaching_demo"),
                self.nested_get(report_b, "session_machine_evaluation.usability.teaching_demo"),
                status=True
            ),
        ]

        rows_adc = [
            self.comparison_row(
                "Raw min ADC",
                self.nested_get(report_a, "signal_quality.raw_signal_stats.min"),
                self.nested_get(report_b, "signal_quality.raw_signal_stats.min")
            ),
            self.comparison_row(
                "Raw max ADC",
                self.nested_get(report_a, "signal_quality.raw_signal_stats.max"),
                self.nested_get(report_b, "signal_quality.raw_signal_stats.max")
            ),
            self.comparison_row(
                "Raw peak-to-peak ADC",
                self.nested_get(report_a, "signal_quality.raw_signal_stats.peak_to_peak"),
                self.nested_get(report_b, "signal_quality.raw_signal_stats.peak_to_peak")
            ),
            self.comparison_row(
                "Median baseline ADC",
                self.nested_get(report_a, "signal_quality.raw_signal_stats.median"),
                self.nested_get(report_b, "signal_quality.raw_signal_stats.median")
            ),
            self.comparison_row(
                "Low clipping count",
                self.nested_get(report_a, "signal_quality.raw_artifact_flags.possible_clipping_low_count"),
                self.nested_get(report_b, "signal_quality.raw_artifact_flags.possible_clipping_low_count"),
                digits=0
            ),
            self.comparison_row(
                "High clipping count",
                self.nested_get(report_a, "signal_quality.raw_artifact_flags.possible_clipping_high_count"),
                self.nested_get(report_b, "signal_quality.raw_artifact_flags.possible_clipping_high_count"),
                digits=0
            ),
            self.comparison_row(
                "Large jumps",
                self.nested_get(report_a, "signal_quality.raw_artifact_flags.large_jump_count"),
                self.nested_get(report_b, "signal_quality.raw_artifact_flags.large_jump_count"),
                digits=0
            ),
            self.comparison_row(
                "Filtered 50 Hz ratio",
                self.nested_get(report_a, "signal_quality.filtered_noise_estimates.powerline_to_signal_ratio"),
                self.nested_get(report_b, "signal_quality.filtered_noise_estimates.powerline_to_signal_ratio"),
                digits=6
            ),
        ]

        rows_peaks = [
            self.comparison_row(
                "Peak detection method",
                self.nested_get(report_a, "peak_detection.method"),
                self.nested_get(report_b, "peak_detection.method")
            ),
            self.comparison_row(
                "Peak polarity",
                self.nested_get(report_a, "peak_detection.polarity"),
                self.nested_get(report_b, "peak_detection.polarity")
            ),
            self.comparison_row(
                "Polarity source",
                self.nested_get(report_a, "peak_detection.polarity_source"),
                self.nested_get(report_b, "peak_detection.polarity_source")
            ),
            self.comparison_row(
                "Peak count",
                self.nested_get(report_a, "metrics.peak_count"),
                self.nested_get(report_b, "metrics.peak_count"),
                digits=0
            ),
            self.comparison_row(
                "RR count",
                self.nested_get(report_a, "signal_quality.rr_quality.rr_count"),
                self.nested_get(report_b, "signal_quality.rr_quality.rr_count"),
                digits=0
            ),
            self.comparison_row(
                "RR outliers",
                self.nested_get(report_a, "signal_quality.rr_quality.rr_outlier_count"),
                self.nested_get(report_b, "signal_quality.rr_quality.rr_outlier_count"),
                digits=0
            ),
        ]

        rows_metrics = [
            self.comparison_row(
                "HR count-based bpm",
                self.nested_get(report_a, "metrics.hr_count_based_bpm"),
                self.nested_get(report_b, "metrics.hr_count_based_bpm")
            ),
            self.comparison_row(
                "HR RR-based bpm",
                self.nested_get(report_a, "metrics.hr_rr_based_bpm"),
                self.nested_get(report_b, "metrics.hr_rr_based_bpm")
            ),
            self.comparison_row(
                "RR mean ms",
                self.nested_get(report_a, "metrics.rr_mean_ms"),
                self.nested_get(report_b, "metrics.rr_mean_ms")
            ),
            self.comparison_row(
                "RR median ms",
                self.nested_get(report_a, "metrics.rr_median_ms"),
                self.nested_get(report_b, "metrics.rr_median_ms")
            ),
            self.comparison_row(
                "RR min ms",
                self.nested_get(report_a, "metrics.rr_min_ms"),
                self.nested_get(report_b, "metrics.rr_min_ms")
            ),
            self.comparison_row(
                "RR max ms",
                self.nested_get(report_a, "metrics.rr_max_ms"),
                self.nested_get(report_b, "metrics.rr_max_ms")
            ),
            self.comparison_row(
                "SDNN ms",
                self.nested_get(report_a, "metrics.sdnn_ms"),
                self.nested_get(report_b, "metrics.sdnn_ms")
            ),
            self.comparison_row(
                "RMSSD ms",
                self.nested_get(report_a, "metrics.rmssd_ms"),
                self.nested_get(report_b, "metrics.rmssd_ms")
            ),
            self.comparison_row(
                "pNN50 %",
                self.nested_get(report_a, "metrics.pnn50_percent"),
                self.nested_get(report_b, "metrics.pnn50_percent")
            ),
        ]

        flags_a = self.nested_get(report_a, "signal_quality.interpretation_flags", [])
        flags_b = self.nested_get(report_b, "signal_quality.interpretation_flags", [])

        if not isinstance(flags_a, list):
            flags_a = []

        if not isinstance(flags_b, list):
            flags_b = []

        flags_html = f"""
        <div class='section'>Signal-quality flags</div>
        <table>
            <tr>
                <td class='label'>Report A</td>
                <td class='value'>{''.join(['• ' + self.esc(x) + '<br>' for x in flags_a]) or 'None'}</td>
            </tr>
            <tr>
                <td class='label'>Report B</td>
                <td class='value'>{''.join(['• ' + self.esc(x) + '<br>' for x in flags_b]) or 'None'}</td>
            </tr>
        </table>
        """

        html_text = f"""
        <html>
        <head>{self.html_style()}</head>
        <body>
            <div class='title'>OpenPhysiologyLab Report Comparison</div>

            <div class='warnbox'>
                Comparison is generated from saved analysis_report.json files.
                No filtering, peak detection, HRV calculation, or machine evaluation is recalculated here.
            </div>

            <div class='section'>Compared files</div>
            <table>
                <tr><td class='label'>Report A</td><td class='value'>{self.esc(path_a)}</td></tr>
                <tr><td class='label'>Report B</td><td class='value'>{self.esc(path_b)}</td></tr>
            </table>

            {self.format_comparison_section("Project / subject / session", rows_study)}
            {self.format_comparison_section("Recording and electrode configuration", rows_recording)}
            {self.format_comparison_section("Machine / session evaluation", rows_machine)}
            {self.format_comparison_section("ADC headroom and signal quality", rows_adc)}
            {self.format_comparison_section("Peak detection", rows_peaks)}
            {self.format_comparison_section("HR / RR / HRV metrics", rows_metrics)}
            {flags_html}

            <div class='section'>Interpretation</div>
            <div class='note'>
                Prefer the report with better machine/session status, lower clipping, fewer large jumps,
                correct peak polarity, and cleaner RR quality. For morphology/amplitude work, PASS headroom
                is important. For HRV timing, RR quality and visual peak verification remain essential.
            </div>
        </body>
        </html>
        """

        return html_text


    # ------------------------------------------------------------
    # Export Results Report
    # ------------------------------------------------------------

    def export_results_report(self):
        """
        Export the current Results tab to:
        - results_report.html
        - rr_tachogram.png
        - rr_histogram.png
        - poincare_plot.png

        This does not recalculate analysis.
        It exports the current loaded analysis_report.json view.
        """

        if self.current_report_path is None or self.current_report is None:
            self.report_box.append(
                "<br><br><b>No report loaded.</b> Load an analysis report first."
            )
            return

        try:
            analysis_folder = Path(self.current_report_path).parent
            export_folder = analysis_folder / "results_export"
            export_folder.mkdir(parents=True, exist_ok=True)

            tachogram_path = export_folder / "rr_tachogram.png"
            histogram_path = export_folder / "rr_histogram.png"
            poincare_path = export_folder / "poincare_plot.png"
            html_path = export_folder / "results_report.html"

            self.export_plot_png(self.rr_tachogram, tachogram_path)
            self.export_plot_png(self.rr_histogram, histogram_path)
            self.export_plot_png(self.poincare_plot, poincare_path)

            html_text = self.build_export_html(
                report=self.current_report,
                report_path=self.current_report_path,
                tachogram_path=tachogram_path,
                histogram_path=histogram_path,
                poincare_path=poincare_path
            )

            html_path.write_text(html_text, encoding="utf-8")

            self.path_label.setText(f"Exported: {html_path}")
            self.report_box.append(
                f"<br><br><b>Exported Results Report:</b><br>{self.esc(html_path)}"
            )

        except Exception as e:
            self.report_box.append(
                f"<br><br><b>Export failed:</b><br>{self.esc(e)}"
            )

    def export_plot_png(self, plot_widget, output_path):
        """
        Export a pyqtgraph PlotWidget to PNG.
        """

        try:
            from pyqtgraph.exporters import ImageExporter

            exporter = ImageExporter(plot_widget.plotItem)
            exporter.parameters()["width"] = 1400
            exporter.export(str(output_path))

        except Exception:
            # Fallback screenshot export if ImageExporter fails.
            pixmap = plot_widget.grab()
            pixmap.save(str(output_path), "PNG")

    def image_to_base64_data_uri(self, image_path):
        """
        Embed image into HTML so the report is portable.
        """

        image_path = Path(image_path)

        if not image_path.exists():
            return ""

        data = image_path.read_bytes()
        encoded = base64.b64encode(data).decode("ascii")

        return f"data:image/png;base64,{encoded}"

    def build_export_html(self, report, report_path, tachogram_path, histogram_path, poincare_path):
        """
        Build standalone HTML report with embedded plots.
        """

        dashboard_html = self.format_results_report(report, report_path)

        # Strip outer html/head/body lightly by embedding as-is inside a container.
        tachogram_uri = self.image_to_base64_data_uri(tachogram_path)
        histogram_uri = self.image_to_base64_data_uri(histogram_path)
        poincare_uri = self.image_to_base64_data_uri(poincare_path)

        exported_at = datetime.now().isoformat(timespec="seconds")

        return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>OpenPhysiologyLab Results Report</title>
<style>
    body {{
        background: #050608;
        color: #F2F2F4;
        font-family: Segoe UI, Arial, sans-serif;
        margin: 24px;
        line-height: 1.4;
    }}

    .header {{
        border: 1px solid #2D333F;
        border-left: 4px solid #D4AF37;
        background: #0E1218;
        padding: 14px 18px;
        border-radius: 8px;
        margin-bottom: 18px;
    }}

    h1 {{
        color: #D4AF37;
        margin: 0 0 6px 0;
        font-size: 24px;
    }}

    h2 {{
        color: #D4AF37;
        margin-top: 28px;
        border-bottom: 1px solid #2D333F;
        padding-bottom: 5px;
    }}

    .subtle {{
        color: #8F96A6;
        font-size: 13px;
    }}

    .report-box {{
        background: #080B10;
        border: 1px solid #2D333F;
        border-radius: 8px;
        padding: 14px;
        margin-bottom: 20px;
    }}

    .plots {{
        display: grid;
        grid-template-columns: 1fr;
        gap: 18px;
    }}

    .plot-card {{
        background: #080B10;
        border: 1px solid #2D333F;
        border-radius: 8px;
        padding: 12px;
    }}

    .plot-card img {{
        width: 100%;
        max-width: 1100px;
        display: block;
        margin: auto;
        border: 1px solid #202630;
        border-radius: 6px;
    }}

    table {{
        border-collapse: collapse;
    }}

    td {{
        padding: 3px 14px 3px 0;
        vertical-align: top;
    }}

    .footer {{
        margin-top: 28px;
        color: #8F96A6;
        font-size: 12px;
        border-top: 1px solid #2D333F;
        padding-top: 10px;
    }}
</style>
</head>
<body>

<div class="header">
    <h1>OpenPhysiologyLab Results Report</h1>
    <div class="subtle">Exported: {self.esc(exported_at)}</div>
    <div class="subtle">Source report: {self.esc(report_path)}</div>
</div>

<div class="report-box">
    {dashboard_html}
</div>

<h2>Scientific Plots</h2>

<div class="plots">
    <div class="plot-card">
        <h2>RR Tachogram</h2>
        <img src="{tachogram_uri}" alt="RR Tachogram">
    </div>

    <div class="plot-card">
        <h2>RR Histogram</h2>
        <img src="{histogram_uri}" alt="RR Histogram">
    </div>

    <div class="plot-card">
        <h2>Poincaré Plot</h2>
        <img src="{poincare_uri}" alt="Poincare Plot">
    </div>
</div>

<div class="footer">
    OpenPhysiologyLab report export. Results are generated from saved analysis_report.json.
    This export does not recalculate peaks, filters, HRV metrics, or machine evaluation.
</div>

</body>
</html>
"""


    # ------------------------------------------------------------
    # Scientific plots
    # ------------------------------------------------------------

    def clear_plots(self):
        for plot in [self.rr_tachogram, self.rr_histogram, self.poincare_plot]:
            plot.clear()
            self.lock_plot_view(plot)

    def update_plots(self, report):
        self.clear_plots()

        metrics = report.get("metrics", {}) or {}

        rr_ms = np.asarray(metrics.get("rr_intervals_ms", []), dtype=float)
        peak_times = np.asarray(metrics.get("peak_times_s", []), dtype=float)

        rr_ms = rr_ms[np.isfinite(rr_ms)]

        if len(rr_ms) == 0:
            self.rr_tachogram.setTitle("RR Tachogram: no RR data", color="#D4AF37")
            self.rr_histogram.setTitle("RR Histogram: no RR data", color="#D4AF37")
            self.poincare_plot.setTitle("Poincaré Plot: no RR data", color="#D4AF37")
            return

        # RR tachogram
        if len(peak_times) >= len(rr_ms) + 1:
            rr_x = peak_times[1:len(rr_ms) + 1]
        else:
            rr_x = np.arange(len(rr_ms))

        self.rr_tachogram.plot(
            rr_x,
            rr_ms,
            pen=pg.mkPen("#50C878", width=1.4),
            symbol="o",
            symbolSize=5,
            symbolBrush=pg.mkBrush("#50C878"),
            symbolPen=pg.mkPen("#F2F2F4", width=0.7)
        )

        mean_rr = float(np.mean(rr_ms))
        mean_line = pg.InfiniteLine(
            pos=mean_rr,
            angle=0,
            movable=False,
            pen=pg.mkPen("#D4AF37", width=1, style=Qt.DashLine)
        )
        self.rr_tachogram.addItem(mean_line)

        self.safe_set_plot_range(
            self.rr_tachogram,
            x_values=rr_x,
            y_values=rr_ms,
            pad_fraction=0.08
        )

        self.rr_tachogram.setTitle("RR Tachogram", color="#D4AF37")

        # RR histogram
        try:
            counts, edges = np.histogram(rr_ms, bins="auto")
        except Exception:
            counts, edges = np.histogram(rr_ms, bins=min(12, max(3, len(rr_ms))))

        if len(edges) > 1:
            centers = (edges[:-1] + edges[1:]) / 2.0
            widths = np.diff(edges)

            bar = pg.BarGraphItem(
                x=centers,
                height=counts,
                width=widths * 0.85,
                brush=pg.mkBrush(212, 175, 55, 180),
                pen=pg.mkPen("#D4AF37")
            )
            self.rr_histogram.addItem(bar)

            self.safe_set_plot_range(
                self.rr_histogram,
                x_values=centers,
                y_values=counts,
                pad_fraction=0.10
            )

        self.rr_histogram.setTitle("RR Histogram", color="#D4AF37")

        # Poincare plot
        if len(rr_ms) >= 2:
            rr_n = rr_ms[:-1]
            rr_next = rr_ms[1:]

            self.poincare_plot.plot(
                rr_n,
                rr_next,
                pen=None,
                symbol="o",
                symbolSize=6,
                symbolBrush=pg.mkBrush(155, 109, 255, 180),
                symbolPen=pg.mkPen("#F2F2F4", width=0.6)
            )

            min_rr = float(min(np.min(rr_n), np.min(rr_next)))
            max_rr = float(max(np.max(rr_n), np.max(rr_next)))

            self.poincare_plot.plot(
                [min_rr, max_rr],
                [min_rr, max_rr],
                pen=pg.mkPen("#D4AF37", width=1, style=Qt.DashLine)
            )

            self.safe_set_plot_range(
                self.poincare_plot,
                x_values=np.concatenate([rr_n, rr_next]),
                y_values=np.concatenate([rr_n, rr_next]),
                pad_fraction=0.08
            )

            self.poincare_plot.setTitle("Poincaré Plot", color="#D4AF37")
        else:
            self.poincare_plot.setTitle("Poincaré Plot: insufficient RR data", color="#D4AF37")
