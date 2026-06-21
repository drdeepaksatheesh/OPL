import json
import base64
import html
from pathlib import Path
from datetime import datetime

import numpy as np
import pyqtgraph as pg

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QFileDialog, QGroupBox, QSplitter,
    QTableWidget, QTableWidgetItem, QHeaderView
)
from PyQt5.QtCore import Qt


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ComparePanel(QWidget):
    """
    OpenPhysiologyLab Compare panel.

    This tab compares saved analysis_report.json files.

    It does not recalculate:
    - filtering
    - peak detection
    - HRV metrics
    - machine evaluation

    It only compares saved reports and visualizes selected saved parameters.
    """

    def __init__(self):
        super().__init__()

        self.report_a_path = None
        self.report_b_path = None
        self.report_a = None
        self.report_b = None

        self.available_reports = []

        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        self.setLayout(layout)

        title = QLabel("OpenPhysiologyLab Compare Panel")
        title.setStyleSheet(
            "font-size: 18px; font-weight: bold; color: #F2F2F4; padding: 2px;"
        )
        layout.addWidget(title)

        info = QLabel(
            "Compare tab = validation workbench. Load two saved analysis_report.json files "
            "and compare protocol, study context, electrode mapping, machine/session status, "
            "ADC headroom, peak detection, and HR/RR/HRV metrics."
        )
        info.setWordWrap(True)
        info.setStyleSheet(
            "font-weight: 400; color: #D4AF37; padding: 6px; "
            "background-color: #0E1218; border: 1px solid #202630; border-radius: 6px;"
        )
        layout.addWidget(info)

        controls_group = QGroupBox("Comparison Source")
        controls_layout = QHBoxLayout()
        controls_layout.setContentsMargins(8, 12, 8, 8)
        controls_layout.setSpacing(8)
        controls_group.setLayout(controls_layout)

        self.load_a_btn = QPushButton("Load Report A")
        self.load_a_btn.clicked.connect(self.load_report_a)
        controls_layout.addWidget(self.load_a_btn)

        self.load_b_btn = QPushButton("Load Report B")
        self.load_b_btn.clicked.connect(self.load_report_b)
        controls_layout.addWidget(self.load_b_btn)

        self.compare_btn = QPushButton("Compare")
        self.compare_btn.clicked.connect(self.compare_loaded_reports)
        controls_layout.addWidget(self.compare_btn)

        self.export_compare_btn = QPushButton("Export Compare Report")
        self.export_compare_btn.setToolTip(
            "Export current comparison table and graphs as HTML plus PNG images."
        )
        self.export_compare_btn.clicked.connect(self.export_compare_report)
        controls_layout.addWidget(self.export_compare_btn)

        self.clear_btn = QPushButton("Clear")
        self.clear_btn.clicked.connect(self.clear_reports)
        controls_layout.addWidget(self.clear_btn)

        self.refresh_reports_btn = QPushButton("Refresh Reports")
        self.refresh_reports_btn.setToolTip("Scan recordings folder for saved analysis_report.json files.")
        self.refresh_reports_btn.clicked.connect(self.refresh_report_browser)
        controls_layout.addWidget(self.refresh_reports_btn)

        self.set_a_btn = QPushButton("Set Selected as A")
        self.set_a_btn.setToolTip("Use selected report from the browser as Report A.")
        self.set_a_btn.clicked.connect(self.set_selected_report_a)
        controls_layout.addWidget(self.set_a_btn)

        self.set_b_btn = QPushButton("Set Selected as B")
        self.set_b_btn.setToolTip("Use selected report from the browser as Report B.")
        self.set_b_btn.clicked.connect(self.set_selected_report_b)
        controls_layout.addWidget(self.set_b_btn)

        self.status_label = QLabel("No reports loaded")
        self.status_label.setWordWrap(True)
        controls_layout.addWidget(self.status_label, stretch=1)

        layout.addWidget(controls_group)

        # Main layout:
        # left: loaded report cards
        # right: comparison table + graphs
        main_splitter = QSplitter(Qt.Horizontal)

        left_group = QGroupBox("Loaded Reports")
        left_layout = QVBoxLayout()
        left_group.setLayout(left_layout)

        browser_label = QLabel("Saved Analysis Reports")
        browser_label.setStyleSheet("color: #D4AF37; font-weight: 600;")
        left_layout.addWidget(browser_label)

        self.report_table = QTableWidget()
        self.report_table.setColumnCount(8)
        self.report_table.setHorizontalHeaderLabels([
            "Saved",
            "Project",
            "Subject",
            "Session",
            "Protocol",
            "Status",
            "HR",
            "Folder",
        ])
        self.report_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.report_table.setSelectionMode(QTableWidget.SingleSelection)
        self.report_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.report_table.doubleClicked.connect(self.set_selected_report_a)
        self.report_table.setMinimumHeight(260)

        try:
            header = self.report_table.horizontalHeader()
            header.setSectionResizeMode(QHeaderView.ResizeToContents)
            header.setStretchLastSection(True)
        except Exception:
            pass

        left_layout.addWidget(self.report_table, stretch=1)

        self.loaded_box = QTextEdit()
        self.loaded_box.setReadOnly(True)
        left_layout.addWidget(self.loaded_box, stretch=1)

        right_group = QGroupBox("Comparison Workbench")
        right_layout = QVBoxLayout()
        right_group.setLayout(right_layout)

        right_splitter = QSplitter(Qt.Vertical)

        self.compare_box = QTextEdit()
        self.compare_box.setReadOnly(True)
        right_splitter.addWidget(self.compare_box)

        plots_group = QGroupBox("Graphical Comparison")
        plots_layout = QVBoxLayout()
        plots_group.setLayout(plots_layout)

        self.protocol_strip = QLabel("Graphs will appear after loading two reports.")
        self.protocol_strip.setWordWrap(True)
        self.protocol_strip.setStyleSheet(
            "color: #D4AF37; background-color: #080B10; "
            "border: 1px solid #2D333F; border-radius: 6px; padding: 6px;"
        )
        plots_layout.addWidget(self.protocol_strip)

        plot_row_1 = QSplitter(Qt.Horizontal)
        plot_row_2 = QSplitter(Qt.Horizontal)

        self.plot_hr_rr = pg.PlotWidget()
        self.configure_bar_plot(self.plot_hr_rr, "Heart rate and RR", "Metric", "Value")

        self.plot_hrv = pg.PlotWidget()
        self.configure_bar_plot(self.plot_hrv, "HRV metrics", "Metric", "ms / %")

        self.plot_adc = pg.PlotWidget()
        self.configure_bar_plot(self.plot_adc, "ADC headroom and range", "Metric", "ADC counts")

        self.plot_artifacts = pg.PlotWidget()
        self.configure_bar_plot(self.plot_artifacts, "Artifacts and clipping", "Metric", "Count")

        plot_row_1.addWidget(self.plot_hr_rr)
        plot_row_1.addWidget(self.plot_hrv)
        plot_row_1.setSizes([700, 700])

        plot_row_2.addWidget(self.plot_adc)
        plot_row_2.addWidget(self.plot_artifacts)
        plot_row_2.setSizes([700, 700])

        plots_layout.addWidget(plot_row_1, stretch=1)
        plots_layout.addWidget(plot_row_2, stretch=1)

        right_splitter.addWidget(plots_group)
        right_splitter.setSizes([520, 520])

        right_layout.addWidget(right_splitter)

        main_splitter.addWidget(left_group)
        main_splitter.addWidget(right_group)
        main_splitter.setSizes([420, 1080])

        layout.addWidget(main_splitter, stretch=1)

        self.apply_dark_style()
        self.update_loaded_box()
        self.show_empty_comparison()
        self.clear_plots()
        self.refresh_report_browser()

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

            QTableWidget {
                background-color: #080B10;
                color: #F2F2F4;
                border: 1px solid #2D333F;
                border-radius: 6px;
                gridline-color: #2D333F;
                selection-background-color: #17140A;
                selection-color: #D4AF37;
            }

            QHeaderView::section {
                background-color: #10141B;
                color: #D4AF37;
                border: 1px solid #2D333F;
                padding: 4px;
                font-weight: 600;
            }

            QTableCornerButton::section {
                background-color: #10141B;
                border: 1px solid #2D333F;
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

            table {
                border-collapse: collapse;
                width: 100%;
            }

            td {
                padding: 4px 14px 4px 0px;
                vertical-align: top;
                border-bottom: 1px solid rgba(45, 51, 63, 90);
            }
        </style>
        """

    def configure_bar_plot(self, plot, title, x_label, y_label):
        plot.setBackground("#020304")
        plot.setTitle(title, color="#D4AF37", size="10pt")
        plot.setLabel("bottom", x_label)
        plot.setLabel("left", y_label)
        plot.showGrid(x=True, y=True, alpha=0.25)
        plot.setMenuEnabled(False)
        plot.setMouseEnabled(x=False, y=False)

        try:
            plot.hideButtons()
        except Exception:
            pass

        try:
            vb = plot.getViewBox()
            vb.setMenuEnabled(False)
            vb.setMouseEnabled(x=False, y=False)
        except Exception:
            pass

        for axis_name in ["left", "bottom"]:
            try:
                axis = plot.getAxis(axis_name)
                axis.setPen(pg.mkPen("#C6CBD5"))
                axis.setTextPen(pg.mkPen("#C6CBD5"))
            except Exception:
                pass

    def esc(self, value):
        return html.escape(str(value), quote=True)

    # ------------------------------------------------------------
    # Report Browser
    # ------------------------------------------------------------

    def refresh_report_browser(self):
        """
        Scan recordings folder for analysis_report.json files and display
        them in the browser table.
        """

        self.available_reports = []

        recordings = PROJECT_ROOT / "recordings"

        if not recordings.exists():
            self.status_label.setText("No recordings folder found.")
            self.report_table.setRowCount(0)
            return

        candidates = sorted(
            recordings.glob("**/analysis/analysis_report.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )

        for report_path in candidates:
            try:
                with open(report_path, "r", encoding="utf-8") as f:
                    report = json.load(f)
            except Exception:
                continue

            study = report.get("study_context", {}) or {}
            session_eval = report.get("session_machine_evaluation", {}) or {}
            metrics = report.get("metrics", {}) or {}

            protocol = report.get("protocol_name", "")
            if not protocol:
                protocol = session_eval.get("protocol_name", "")

            folder_name = Path(str(report.get("recording_folder", ""))).name

            row = {
                "path": report_path,
                "report": report,
                "saved": report.get("analysis_saved_datetime", ""),
                "project": study.get("project_name", ""),
                "subject": study.get("subject_id", ""),
                "session": study.get("session_label", ""),
                "protocol": protocol,
                "status": session_eval.get("overall_status", ""),
                "hr": metrics.get("hr_rr_based_bpm", metrics.get("hr_count_based_bpm", "")),
                "folder": folder_name,
            }

            self.available_reports.append(row)

        self.populate_report_table()

        self.status_label.setText(
            f"Found {len(self.available_reports)} saved analysis reports."
        )

    def populate_report_table(self):
        self.report_table.setRowCount(len(self.available_reports))

        for row_index, item in enumerate(self.available_reports):
            values = [
                item.get("saved", ""),
                item.get("project", ""),
                item.get("subject", ""),
                item.get("session", ""),
                item.get("protocol", ""),
                item.get("status", ""),
                self.format_table_number(item.get("hr", "")),
                item.get("folder", ""),
            ]

            for col, value in enumerate(values):
                cell = QTableWidgetItem(str(value))
                self.report_table.setItem(row_index, col, cell)

        try:
            self.report_table.resizeColumnsToContents()
            self.report_table.horizontalHeader().setStretchLastSection(True)
        except Exception:
            pass

    def format_table_number(self, value):
        try:
            return f"{float(value):.2f}"
        except Exception:
            return str(value)

    def get_selected_browser_report(self):
        row = self.report_table.currentRow()

        if row < 0 or row >= len(self.available_reports):
            self.status_label.setText("Select a report row first.")
            return None, None

        item = self.available_reports[row]
        return item.get("path"), item.get("report")

    def set_selected_report_a(self):
        path, report = self.get_selected_browser_report()

        if path is None:
            return

        self.report_a_path = Path(path)
        self.report_a = report
        self.update_loaded_box()

        self.status_label.setText(f"Set Report A: {self.report_a_path.parent.parent.name}")

        if self.report_b is not None:
            self.compare_loaded_reports()

    def set_selected_report_b(self):
        path, report = self.get_selected_browser_report()

        if path is None:
            return

        self.report_b_path = Path(path)
        self.report_b = report
        self.update_loaded_box()

        self.status_label.setText(f"Set Report B: {self.report_b_path.parent.parent.name}")

        if self.report_a is not None:
            self.compare_loaded_reports()



    # ------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------

    def choose_report_file(self, title):
        start_dir = PROJECT_ROOT / "recordings"

        try:
            selected_path, _selected_report = self.get_selected_browser_report()
            if selected_path is not None:
                start_dir = Path(selected_path).parent
        except Exception:
            pass

        path, _ = QFileDialog.getOpenFileName(
            self,
            title,
            str(start_dir),
            "JSON Files (*.json);;All Files (*.*)"
        )

        if not path:
            return None, None

        path = Path(path)

        try:
            with open(path, "r", encoding="utf-8") as f:
                report = json.load(f)
        except Exception as e:
            self.compare_box.setHtml(
                f"""
                <html>
                <head>{self.html_style()}</head>
                <body>
                    <div class='title'>Load Failed</div>
                    <div class='failbox'>Could not load report:<br>{self.esc(path)}<br><br>{self.esc(e)}</div>
                </body>
                </html>
                """
            )
            return None, None

        return path, report

    def load_report_a(self):
        path, report = self.choose_report_file("Choose Report A: analysis_report.json")

        if path is None:
            return

        self.report_a_path = path
        self.report_a = report
        self.update_loaded_box()

        if self.report_b is not None:
            self.compare_loaded_reports()

    def load_report_b(self):
        path, report = self.choose_report_file("Choose Report B: analysis_report.json")

        if path is None:
            return

        self.report_b_path = path
        self.report_b = report
        self.update_loaded_box()

        if self.report_a is not None:
            self.compare_loaded_reports()

    def clear_reports(self):
        self.report_a_path = None
        self.report_b_path = None
        self.report_a = None
        self.report_b = None
        self.status_label.setText("No reports loaded")
        self.update_loaded_box()
        self.show_empty_comparison()
        self.clear_plots()

    def update_loaded_box(self):
        a_name = self.report_label(self.report_a, self.report_a_path)
        b_name = self.report_label(self.report_b, self.report_b_path)

        self.loaded_box.setHtml(
            f"""
            <html>
            <head>{self.html_style()}</head>
            <body>
                <div class='title'>Loaded Reports</div>

                <div class='section'>Report A</div>
                <div class='note'>{self.esc(a_name)}</div>

                <div class='section'>Report B</div>
                <div class='note'>{self.esc(b_name)}</div>

                <div class='section'>Workflow</div>
                <div class='note'>
                    1. Load Report A<br>
                    2. Load Report B<br>
                    3. Click Compare<br><br>
                    Reports should be saved analysis_report.json files.
                </div>
            </body>
            </html>
            """
        )

    def report_label(self, report, path):
        if report is None or path is None:
            return "Not loaded"

        folder = Path(str(report.get("recording_folder", ""))).name
        study = report.get("study_context", {}) or {}
        session = study.get("session_label", "")
        subject = study.get("subject_id", "")
        protocol = report.get("protocol_name", "")
        if not protocol:
            protocol = self.nested_get(report, "session_machine_evaluation.protocol_name", "")
        status = self.nested_get(report, "session_machine_evaluation.overall_status", "")

        return f"{folder} | Subject: {subject} | Session: {session} | Protocol: {protocol} | Status: {status}"

    def show_empty_comparison(self):
        self.compare_box.setHtml(
            f"""
            <html>
            <head>{self.html_style()}</head>
            <body>
                <div class='title'>No Comparison Loaded</div>
                <div class='note'>
                    Load two analysis_report.json files to compare protocol,
                    recording quality, machine status, ADC headroom, peak detection,
                    and HRV metrics.
                </div>
            </body>
            </html>
            """
        )
        self.protocol_strip.setText("Graphs will appear after loading two reports.")

    # ------------------------------------------------------------
    # Comparison helpers
    # ------------------------------------------------------------

    def nested_get(self, data, path, default=""):
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

    def first_available(self, report, paths, default=""):
        for path in paths:
            value = self.nested_get(report, path, None)
            if value not in [None, ""]:
                return value
        return default

    def compare_fmt(self, value, digits=3):
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

    def status_class(self, value):
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

        a_class = self.status_class(a_text) if status else "value"
        b_class = self.status_class(b_text) if status else "value"

        return (
            f"<tr>"
            f"<td class='label'>{self.esc(label)}</td>"
            f"<td class='{a_class}'>{self.esc(a_text)}</td>"
            f"<td class='{b_class}'>{self.esc(b_text)}</td>"
            f"</tr>"
        )

    def comparison_section(self, title, rows):
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

    def get_protocol_name(self, report):
        return self.first_available(
            report,
            [
                "protocol_name",
                "session_machine_evaluation.protocol_name",
                "latest_machine_evaluation_before_recording.protocol_name",
            ],
            default=""
        )

    def get_recording_mode(self, report):
        return self.first_available(
            report,
            [
                "recording_mode",
                "signal_type",
                "session_machine_evaluation.signal_type",
                "electrode_pin_mapping.signal_type",
            ],
            default=""
        )

    def compare_loaded_reports(self):
        if self.report_a is None or self.report_b is None:
            self.compare_box.setHtml(
                f"""
                <html>
                <head>{self.html_style()}</head>
                <body>
                    <div class='title'>Compare Reports</div>
                    <div class='warnbox'>Load both Report A and Report B first.</div>
                </body>
                </html>
                """
            )
            return

        self.compare_box.setHtml(
            self.format_comparison_report(
                self.report_a,
                self.report_b,
                self.report_a_path,
                self.report_b_path
            )
        )

        self.update_comparison_plots(self.report_a, self.report_b)

        self.status_label.setText(
            f"Comparison loaded: {Path(self.report_a_path).parent.parent.name} vs {Path(self.report_b_path).parent.parent.name}"
        )

    def percent_difference(self, a, b):
        """
        Percent difference = ((B - A) / A) * 100.
        Returns None if A is zero or invalid.
        """

        try:
            a = float(a)
            b = float(b)

            if abs(a) < 1e-12:
                return None

            return ((b - a) / a) * 100.0

        except Exception:
            return None

    def difference_row(self, label, a, b, unit="", digits=3, show_percent=True):
        """
        Difference row for numeric comparison.

        Difference = Report B - Report A.
        """

        try:
            a_float = float(a)
            b_float = float(b)
            diff = b_float - a_float

            a_text = f"{a_float:.{digits}f}"
            b_text = f"{b_float:.{digits}f}"
            diff_text = f"{diff:+.{digits}f}"

            pct = self.percent_difference(a_float, b_float)

            if pct is None or not show_percent:
                pct_text = "—"
            else:
                pct_text = f"{pct:+.2f}%"

        except Exception:
            a_text = self.compare_fmt(a, digits=digits)
            b_text = self.compare_fmt(b, digits=digits)
            diff_text = "—"
            pct_text = "—"

        if unit:
            a_text = f"{a_text} {unit}"
            b_text = f"{b_text} {unit}"
            if diff_text != "—":
                diff_text = f"{diff_text} {unit}"

        return (
            f"<tr>"
            f"<td class='label'>{self.esc(label)}</td>"
            f"<td class='value'>{self.esc(a_text)}</td>"
            f"<td class='value'>{self.esc(b_text)}</td>"
            f"<td class='value'>{self.esc(diff_text)}</td>"
            f"<td class='value'>{self.esc(pct_text)}</td>"
            f"</tr>"
        )

    def format_difference_summary(self, report_a, report_b):
        """
        Show Report B - Report A difference summary.
        """

        rows = []

        rows.append(self.difference_row(
            "HR count-based",
            self.nested_get(report_a, "metrics.hr_count_based_bpm"),
            self.nested_get(report_b, "metrics.hr_count_based_bpm"),
            unit="bpm"
        ))

        rows.append(self.difference_row(
            "HR RR-based",
            self.nested_get(report_a, "metrics.hr_rr_based_bpm"),
            self.nested_get(report_b, "metrics.hr_rr_based_bpm"),
            unit="bpm"
        ))

        rows.append(self.difference_row(
            "RR mean",
            self.nested_get(report_a, "metrics.rr_mean_ms"),
            self.nested_get(report_b, "metrics.rr_mean_ms"),
            unit="ms"
        ))

        rows.append(self.difference_row(
            "RR median",
            self.nested_get(report_a, "metrics.rr_median_ms"),
            self.nested_get(report_b, "metrics.rr_median_ms"),
            unit="ms"
        ))

        rows.append(self.difference_row(
            "SDNN",
            self.nested_get(report_a, "metrics.sdnn_ms"),
            self.nested_get(report_b, "metrics.sdnn_ms"),
            unit="ms"
        ))

        rows.append(self.difference_row(
            "RMSSD",
            self.nested_get(report_a, "metrics.rmssd_ms"),
            self.nested_get(report_b, "metrics.rmssd_ms"),
            unit="ms"
        ))

        rows.append(self.difference_row(
            "pNN50",
            self.nested_get(report_a, "metrics.pnn50_percent"),
            self.nested_get(report_b, "metrics.pnn50_percent"),
            unit="%"
        ))

        rows.append(self.difference_row(
            "Raw peak-to-peak",
            self.nested_get(report_a, "signal_quality.raw_signal_stats.peak_to_peak"),
            self.nested_get(report_b, "signal_quality.raw_signal_stats.peak_to_peak"),
            unit="ADC"
        ))

        rows.append(self.difference_row(
            "Low clipping count",
            self.nested_get(report_a, "signal_quality.raw_artifact_flags.possible_clipping_low_count"),
            self.nested_get(report_b, "signal_quality.raw_artifact_flags.possible_clipping_low_count"),
            unit="",
            digits=0,
            show_percent=False
        ))

        rows.append(self.difference_row(
            "High clipping count",
            self.nested_get(report_a, "signal_quality.raw_artifact_flags.possible_clipping_high_count"),
            self.nested_get(report_b, "signal_quality.raw_artifact_flags.possible_clipping_high_count"),
            unit="",
            digits=0,
            show_percent=False
        ))

        rows.append(self.difference_row(
            "Large jumps",
            self.nested_get(report_a, "signal_quality.raw_artifact_flags.large_jump_count"),
            self.nested_get(report_b, "signal_quality.raw_artifact_flags.large_jump_count"),
            unit="",
            digits=0,
            show_percent=False
        ))

        rows.append(self.difference_row(
            "RR outliers",
            self.nested_get(report_a, "signal_quality.rr_quality.rr_outlier_count"),
            self.nested_get(report_b, "signal_quality.rr_quality.rr_outlier_count"),
            unit="",
            digits=0,
            show_percent=False
        ))

        return f"""
        <div class='section'>Difference summary</div>
        <div class='smallnote'>
            Difference is calculated as <b>Report B − Report A</b>.
            Percent difference is calculated relative to Report A where meaningful.
        </div>
        <table>
            <tr>
                <td class='label'>Metric</td>
                <td class='label'>Report A</td>
                <td class='label'>Report B</td>
                <td class='label'>Difference</td>
                <td class='label'>% Difference</td>
            </tr>
            {''.join(rows)}
        </table>
        """

    def score_machine_quality(self, report):
        """
        Simple quality score for practical comparison.
        Lower score is better.
        """

        score = 0

        status = str(self.nested_get(report, "session_machine_evaluation.overall_status", "")).upper()

        if status == "PASS":
            score += 0
        elif status == "CAUTION":
            score += 10
        elif status == "FAIL":
            score += 100
        else:
            score += 25

        try:
            low_clip = float(self.nested_get(report, "signal_quality.raw_artifact_flags.possible_clipping_low_count", 0))
            high_clip = float(self.nested_get(report, "signal_quality.raw_artifact_flags.possible_clipping_high_count", 0))
            jumps = float(self.nested_get(report, "signal_quality.raw_artifact_flags.large_jump_count", 0))
            rr_out = float(self.nested_get(report, "signal_quality.rr_quality.rr_outlier_count", 0))
        except Exception:
            low_clip = high_clip = jumps = rr_out = 0

        score += low_clip * 2
        score += high_clip * 2
        score += jumps * 0.05
        score += rr_out * 2

        return score

    def better_report_text(self, score_a, score_b):
        """
        Convert two quality scores into a readable statement.
        """

        try:
            score_a = float(score_a)
            score_b = float(score_b)
        except Exception:
            return "Unable to judge from available fields."

        if abs(score_a - score_b) < 1.0:
            return "Report A and Report B are broadly similar by this simple quality score."

        if score_a < score_b:
            return "Report A looks cleaner by this simple machine/signal quality score."

        return "Report B looks cleaner by this simple machine/signal quality score."

    def format_validation_interpretation(self, report_a, report_b):
        """
        Practical interpretation for validation use.
        """

        status_a = str(self.nested_get(report_a, "session_machine_evaluation.overall_status", "UNKNOWN")).upper()
        status_b = str(self.nested_get(report_b, "session_machine_evaluation.overall_status", "UNKNOWN")).upper()

        timing_a = str(self.nested_get(report_a, "session_machine_evaluation.usability.timing", "UNKNOWN")).upper()
        timing_b = str(self.nested_get(report_b, "session_machine_evaluation.usability.timing", "UNKNOWN")).upper()

        amp_a = str(self.nested_get(report_a, "session_machine_evaluation.usability.amplitude", "UNKNOWN")).upper()
        amp_b = str(self.nested_get(report_b, "session_machine_evaluation.usability.amplitude", "UNKNOWN")).upper()

        morph_a = str(self.nested_get(report_a, "session_machine_evaluation.usability.morphology", "UNKNOWN")).upper()
        morph_b = str(self.nested_get(report_b, "session_machine_evaluation.usability.morphology", "UNKNOWN")).upper()

        protocol_a = self.get_protocol_name(report_a)
        protocol_b = self.get_protocol_name(report_b)

        score_a = self.score_machine_quality(report_a)
        score_b = self.score_machine_quality(report_b)

        protocol_note = ""

        if protocol_a != protocol_b:
            protocol_note = (
                "Protocols are different. Direct numerical comparison should be treated cautiously. "
                "Use this mainly for exploratory or validation context."
            )
        else:
            protocol_note = "Protocols match, so direct comparison is more defensible."

        if status_a == "PASS" and status_b != "PASS":
            machine_note = "Report A has better machine/session status."
        elif status_b == "PASS" and status_a != "PASS":
            machine_note = "Report B has better machine/session status."
        elif status_a == status_b:
            machine_note = f"Both reports have the same machine/session status: {status_a}."
        else:
            machine_note = f"Machine/session status differs: A={status_a}, B={status_b}."

        if timing_a == "PASS" and timing_b == "PASS":
            timing_note = "Timing is marked PASS in both reports. HR/RR comparison is reasonable after visual peak verification."
        else:
            timing_note = f"Timing usability differs or is not fully PASS: A={timing_a}, B={timing_b}. HRV comparison should be cautious."

        if amp_a == "PASS" and amp_b == "PASS" and morph_a == "PASS" and morph_b == "PASS":
            morphology_note = "Amplitude and morphology are marked PASS in both reports."
        else:
            morphology_note = (
                f"Amplitude/morphology caution: A amplitude={amp_a}, A morphology={morph_a}; "
                f"B amplitude={amp_b}, B morphology={morph_b}. Avoid strong morphology/amplitude conclusions "
                "from any CAUTION/FAIL recording."
            )

        quality_note = self.better_report_text(score_a, score_b)

        return f"""
        <div class='section'>Validation interpretation</div>
        <table>
            <tr><td class='label'>Protocol comparison</td><td class='value'>{self.esc(protocol_note)}</td></tr>
            <tr><td class='label'>Machine quality</td><td class='value'>{self.esc(machine_note)}</td></tr>
            <tr><td class='label'>Simple quality score</td><td class='value'>A={score_a:.2f}, B={score_b:.2f}. {self.esc(quality_note)}</td></tr>
            <tr><td class='label'>Timing / HRV</td><td class='value'>{self.esc(timing_note)}</td></tr>
            <tr><td class='label'>Amplitude / morphology</td><td class='value'>{self.esc(morphology_note)}</td></tr>
        </table>

        <div class='smallnote'>
            This interpretation is rule-based and descriptive. It does not replace visual inspection of the ECG,
            R-peak markers, and raw ADC trace.
        </div>
        """


    def format_comparison_report(self, report_a, report_b, path_a, path_b):
        rows_protocol = [
            self.comparison_row("Protocol followed", self.get_protocol_name(report_a), self.get_protocol_name(report_b)),
            self.comparison_row("Recording mode / signal type", self.get_recording_mode(report_a), self.get_recording_mode(report_b)),
            self.comparison_row("Electrode placement", report_a.get("electrode_placement", ""), report_b.get("electrode_placement", "")),
            self.comparison_row("Filter low cut", self.nested_get(report_a, "filter_settings.low_hz"), self.nested_get(report_b, "filter_settings.low_hz")),
            self.comparison_row("Filter high cut", self.nested_get(report_a, "filter_settings.high_hz"), self.nested_get(report_b, "filter_settings.high_hz")),
            self.comparison_row("50 Hz notch", self.nested_get(report_a, "filter_settings.notch_50hz"), self.nested_get(report_b, "filter_settings.notch_50hz")),
            self.comparison_row("Analysis inverted", self.nested_get(report_a, "filter_settings.inverted"), self.nested_get(report_b, "filter_settings.inverted")),
        ]

        rows_study = [
            self.comparison_row("Project", self.nested_get(report_a, "study_context.project_name"), self.nested_get(report_b, "study_context.project_name")),
            self.comparison_row("Subject ID", self.nested_get(report_a, "study_context.subject_id"), self.nested_get(report_b, "study_context.subject_id")),
            self.comparison_row("Session label", self.nested_get(report_a, "study_context.session_label"), self.nested_get(report_b, "study_context.session_label")),
            self.comparison_row("Condition", self.nested_get(report_a, "study_context.condition"), self.nested_get(report_b, "study_context.condition")),
            self.comparison_row("Posture", self.nested_get(report_a, "study_context.posture"), self.nested_get(report_b, "study_context.posture")),
            self.comparison_row("Notes", self.nested_get(report_a, "study_context.session_notes"), self.nested_get(report_b, "study_context.session_notes")),
        ]

        rows_recording = [
            self.comparison_row("Recording folder", Path(str(report_a.get("recording_folder", ""))).name, Path(str(report_b.get("recording_folder", ""))).name),
            self.comparison_row("Saved datetime", report_a.get("analysis_saved_datetime", ""), report_b.get("analysis_saved_datetime", "")),
            self.comparison_row("Electrode configuration", self.nested_get(report_a, "electrode_pin_mapping.configuration_label"), self.nested_get(report_b, "electrode_pin_mapping.configuration_label")),
            self.comparison_row("A0P", self.nested_get(report_a, "electrode_pin_mapping.pin_mapping.A0P"), self.nested_get(report_b, "electrode_pin_mapping.pin_mapping.A0P")),
            self.comparison_row("A0N", self.nested_get(report_a, "electrode_pin_mapping.pin_mapping.A0N"), self.nested_get(report_b, "electrode_pin_mapping.pin_mapping.A0N")),
            self.comparison_row("REF", self.nested_get(report_a, "electrode_pin_mapping.pin_mapping.REF"), self.nested_get(report_b, "electrode_pin_mapping.pin_mapping.REF")),
        ]

        rows_machine = [
            self.comparison_row("Machine UID", self.nested_get(report_a, "machine_profile.machine_uid"), self.nested_get(report_b, "machine_profile.machine_uid")),
            self.comparison_row("Machine status", self.nested_get(report_a, "session_machine_evaluation.overall_status"), self.nested_get(report_b, "session_machine_evaluation.overall_status"), status=True),
            self.comparison_row("Timing usability", self.nested_get(report_a, "session_machine_evaluation.usability.timing"), self.nested_get(report_b, "session_machine_evaluation.usability.timing"), status=True),
            self.comparison_row("Amplitude usability", self.nested_get(report_a, "session_machine_evaluation.usability.amplitude"), self.nested_get(report_b, "session_machine_evaluation.usability.amplitude"), status=True),
            self.comparison_row("Morphology usability", self.nested_get(report_a, "session_machine_evaluation.usability.morphology"), self.nested_get(report_b, "session_machine_evaluation.usability.morphology"), status=True),
            self.comparison_row("Teaching demo usability", self.nested_get(report_a, "session_machine_evaluation.usability.teaching_demo"), self.nested_get(report_b, "session_machine_evaluation.usability.teaching_demo"), status=True),
        ]

        rows_adc = [
            self.comparison_row("Raw min ADC", self.nested_get(report_a, "signal_quality.raw_signal_stats.min"), self.nested_get(report_b, "signal_quality.raw_signal_stats.min")),
            self.comparison_row("Raw max ADC", self.nested_get(report_a, "signal_quality.raw_signal_stats.max"), self.nested_get(report_b, "signal_quality.raw_signal_stats.max")),
            self.comparison_row("Raw peak-to-peak ADC", self.nested_get(report_a, "signal_quality.raw_signal_stats.peak_to_peak"), self.nested_get(report_b, "signal_quality.raw_signal_stats.peak_to_peak")),
            self.comparison_row("Median baseline ADC", self.nested_get(report_a, "signal_quality.raw_signal_stats.median"), self.nested_get(report_b, "signal_quality.raw_signal_stats.median")),
            self.comparison_row("Low clipping count", self.nested_get(report_a, "signal_quality.raw_artifact_flags.possible_clipping_low_count"), self.nested_get(report_b, "signal_quality.raw_artifact_flags.possible_clipping_low_count"), digits=0),
            self.comparison_row("High clipping count", self.nested_get(report_a, "signal_quality.raw_artifact_flags.possible_clipping_high_count"), self.nested_get(report_b, "signal_quality.raw_artifact_flags.possible_clipping_high_count"), digits=0),
            self.comparison_row("Large jumps", self.nested_get(report_a, "signal_quality.raw_artifact_flags.large_jump_count"), self.nested_get(report_b, "signal_quality.raw_artifact_flags.large_jump_count"), digits=0),
            self.comparison_row("Filtered 50 Hz ratio", self.nested_get(report_a, "signal_quality.filtered_noise_estimates.powerline_to_signal_ratio"), self.nested_get(report_b, "signal_quality.filtered_noise_estimates.powerline_to_signal_ratio"), digits=6),
        ]

        rows_peaks = [
            self.comparison_row("Peak detection method", self.nested_get(report_a, "peak_detection.method"), self.nested_get(report_b, "peak_detection.method")),
            self.comparison_row("Peak polarity", self.nested_get(report_a, "peak_detection.polarity"), self.nested_get(report_b, "peak_detection.polarity")),
            self.comparison_row("Polarity source", self.nested_get(report_a, "peak_detection.polarity_source"), self.nested_get(report_b, "peak_detection.polarity_source")),
            self.comparison_row("Peak count", self.nested_get(report_a, "metrics.peak_count"), self.nested_get(report_b, "metrics.peak_count"), digits=0),
            self.comparison_row("RR count", self.nested_get(report_a, "signal_quality.rr_quality.rr_count"), self.nested_get(report_b, "signal_quality.rr_quality.rr_count"), digits=0),
            self.comparison_row("RR outliers", self.nested_get(report_a, "signal_quality.rr_quality.rr_outlier_count"), self.nested_get(report_b, "signal_quality.rr_quality.rr_outlier_count"), digits=0),
        ]

        rows_metrics = [
            self.comparison_row("HR count-based bpm", self.nested_get(report_a, "metrics.hr_count_based_bpm"), self.nested_get(report_b, "metrics.hr_count_based_bpm")),
            self.comparison_row("HR RR-based bpm", self.nested_get(report_a, "metrics.hr_rr_based_bpm"), self.nested_get(report_b, "metrics.hr_rr_based_bpm")),
            self.comparison_row("RR mean ms", self.nested_get(report_a, "metrics.rr_mean_ms"), self.nested_get(report_b, "metrics.rr_mean_ms")),
            self.comparison_row("RR median ms", self.nested_get(report_a, "metrics.rr_median_ms"), self.nested_get(report_b, "metrics.rr_median_ms")),
            self.comparison_row("RR min ms", self.nested_get(report_a, "metrics.rr_min_ms"), self.nested_get(report_b, "metrics.rr_min_ms")),
            self.comparison_row("RR max ms", self.nested_get(report_a, "metrics.rr_max_ms"), self.nested_get(report_b, "metrics.rr_max_ms")),
            self.comparison_row("SDNN ms", self.nested_get(report_a, "metrics.sdnn_ms"), self.nested_get(report_b, "metrics.sdnn_ms")),
            self.comparison_row("RMSSD ms", self.nested_get(report_a, "metrics.rmssd_ms"), self.nested_get(report_b, "metrics.rmssd_ms")),
            self.comparison_row("pNN50 %", self.nested_get(report_a, "metrics.pnn50_percent"), self.nested_get(report_b, "metrics.pnn50_percent")),
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

            {self.comparison_section("Protocol followed", rows_protocol)}
            {self.comparison_section("Project / subject / session", rows_study)}
            {self.comparison_section("Recording and electrode configuration", rows_recording)}
            {self.comparison_section("Machine / session evaluation", rows_machine)}
            {self.comparison_section("ADC headroom and signal quality", rows_adc)}
            {self.comparison_section("Peak detection", rows_peaks)}
            {self.comparison_section("HR / RR / HRV metrics", rows_metrics)}
            {self.format_difference_summary(report_a, report_b)}
            {flags_html}
            {self.format_validation_interpretation(report_a, report_b)}
        </body>
        </html>
        """

        return html_text

    # ------------------------------------------------------------
    # Export comparison
    # ------------------------------------------------------------

    def export_compare_report(self):
        """
        Export current comparison as:
        - comparison_report.html
        - hr_rr_comparison.png
        - hrv_comparison.png
        - adc_comparison.png
        - artifact_comparison.png

        This does not recalculate anything.
        """

        if self.report_a is None or self.report_b is None:
            self.compare_box.setHtml(
                f"""
                <html>
                <head>{self.html_style()}</head>
                <body>
                    <div class='title'>Export Compare Report</div>
                    <div class='warnbox'>
                        Load Report A and Report B, then compare before exporting.
                    </div>
                </body>
                </html>
                """
            )
            return

        try:
            base_folder = Path(self.report_a_path).parent / "comparison_export"
            base_folder.mkdir(parents=True, exist_ok=True)

            hr_rr_path = base_folder / "hr_rr_comparison.png"
            hrv_path = base_folder / "hrv_comparison.png"
            adc_path = base_folder / "adc_comparison.png"
            artifact_path = base_folder / "artifact_comparison.png"
            html_path = base_folder / "comparison_report.html"

            self.export_plot_png(self.plot_hr_rr, hr_rr_path)
            self.export_plot_png(self.plot_hrv, hrv_path)
            self.export_plot_png(self.plot_adc, adc_path)
            self.export_plot_png(self.plot_artifacts, artifact_path)

            html_text = self.build_compare_export_html(
                hr_rr_path=hr_rr_path,
                hrv_path=hrv_path,
                adc_path=adc_path,
                artifact_path=artifact_path
            )

            html_path.write_text(html_text, encoding="utf-8")

            self.status_label.setText(f"Exported comparison: {html_path}")

            self.compare_box.append(
                f"<br><br><b>Exported comparison report:</b><br>{self.esc(html_path)}"
            )

        except Exception as e:
            self.compare_box.append(
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
            pixmap = plot_widget.grab()
            pixmap.save(str(output_path), "PNG")

    def image_to_base64_data_uri(self, image_path):
        image_path = Path(image_path)

        if not image_path.exists():
            return ""

        data = image_path.read_bytes()
        encoded = base64.b64encode(data).decode("ascii")
        return f"data:image/png;base64,{encoded}"

    def build_compare_export_html(self, hr_rr_path, hrv_path, adc_path, artifact_path):
        """
        Build standalone exported comparison HTML.
        """

        comparison_html = self.format_comparison_report(
            self.report_a,
            self.report_b,
            self.report_a_path,
            self.report_b_path
        )

        hr_rr_uri = self.image_to_base64_data_uri(hr_rr_path)
        hrv_uri = self.image_to_base64_data_uri(hrv_path)
        adc_uri = self.image_to_base64_data_uri(adc_path)
        artifact_uri = self.image_to_base64_data_uri(artifact_path)

        exported_at = datetime.now().isoformat(timespec="seconds")

        return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>OpenPhysiologyLab Comparison Report</title>
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
        width: 100%;
    }}

    td {{
        padding: 4px 14px 4px 0;
        vertical-align: top;
        border-bottom: 1px solid rgba(45, 51, 63, 90);
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
    <h1>OpenPhysiologyLab Comparison Report</h1>
    <div class="subtle">Exported: {self.esc(exported_at)}</div>
    <div class="subtle">Report A: {self.esc(self.report_a_path)}</div>
    <div class="subtle">Report B: {self.esc(self.report_b_path)}</div>
</div>

<div class="report-box">
    {comparison_html}
</div>

<h2>Graphical Comparison</h2>

<div class="plots">
    <div class="plot-card">
        <h2>Heart rate and RR</h2>
        <img src="{hr_rr_uri}" alt="Heart rate and RR comparison">
    </div>

    <div class="plot-card">
        <h2>HRV metrics</h2>
        <img src="{hrv_uri}" alt="HRV comparison">
    </div>

    <div class="plot-card">
        <h2>ADC headroom and range</h2>
        <img src="{adc_uri}" alt="ADC comparison">
    </div>

    <div class="plot-card">
        <h2>Artifacts and clipping</h2>
        <img src="{artifact_uri}" alt="Artifact comparison">
    </div>
</div>

<div class="footer">
    OpenPhysiologyLab comparison export. This file compares saved analysis_report.json files.
    It does not recalculate filtering, peak detection, HRV metrics, or machine/session evaluation.
</div>

</body>
</html>
"""


    # ------------------------------------------------------------
    # Graphical comparison
    # ------------------------------------------------------------

    def clear_plots(self):
        for plot in [
            self.plot_hr_rr,
            self.plot_hrv,
            self.plot_adc,
            self.plot_artifacts,
        ]:
            try:
                plot.clear()
            except Exception:
                pass

    def as_float(self, value, default=np.nan):
        try:
            return float(value)
        except Exception:
            return default

    def get_numeric(self, report, path, default=np.nan):
        return self.as_float(self.nested_get(report, path, default), default=default)

    def plot_grouped_bars(self, plot, title, labels, values_a, values_b, y_label):
        plot.clear()
        plot.setTitle(title, color="#D4AF37", size="10pt")
        plot.setLabel("left", y_label)

        x = np.arange(len(labels), dtype=float)
        width = 0.32

        values_a = np.asarray(values_a, dtype=float)
        values_b = np.asarray(values_b, dtype=float)

        valid_values = np.concatenate([
            values_a[np.isfinite(values_a)],
            values_b[np.isfinite(values_b)]
        ])

        bar_a = pg.BarGraphItem(
            x=x - width / 2.0,
            height=np.nan_to_num(values_a, nan=0.0),
            width=width,
            brush=pg.mkBrush(212, 175, 55, 180),
            pen=pg.mkPen("#D4AF37")
        )

        bar_b = pg.BarGraphItem(
            x=x + width / 2.0,
            height=np.nan_to_num(values_b, nan=0.0),
            width=width,
            brush=pg.mkBrush(80, 200, 120, 170),
            pen=pg.mkPen("#50C878")
        )

        plot.addItem(bar_a)
        plot.addItem(bar_b)

        try:
            axis = plot.getAxis("bottom")
            axis.setTicks([[(i, labels[i]) for i in range(len(labels))]])
        except Exception:
            pass

        try:
            if valid_values.size > 0:
                ymin = min(0.0, float(np.min(valid_values)))
                ymax = float(np.max(valid_values))

                if ymax <= ymin:
                    ymax = ymin + 1.0

                pad = max((ymax - ymin) * 0.15, 1.0)
                plot.setYRange(ymin, ymax + pad, padding=0)
                plot.setXRange(-0.75, len(labels) - 0.25, padding=0)
        except Exception:
            pass

        try:
            plot.setMouseEnabled(x=False, y=False)
            plot.setMenuEnabled(False)
            plot.hideButtons()
        except Exception:
            pass

    def update_comparison_plots(self, report_a, report_b):
        protocol_a = self.get_protocol_name(report_a) or "--"
        protocol_b = self.get_protocol_name(report_b) or "--"
        session_a = self.nested_get(report_a, "study_context.session_label", "--")
        session_b = self.nested_get(report_b, "study_context.session_label", "--")

        self.protocol_strip.setText(
            f"Report A: {session_a} | Protocol: {protocol_a}    "
            f"Report B: {session_b} | Protocol: {protocol_b}    "
            "Bar colour: gold = Report A, emerald = Report B"
        )

        self.plot_grouped_bars(
            self.plot_hr_rr,
            "Heart rate and RR",
            ["HR count", "HR RR", "RR mean", "RR median"],
            [
                self.get_numeric(report_a, "metrics.hr_count_based_bpm"),
                self.get_numeric(report_a, "metrics.hr_rr_based_bpm"),
                self.get_numeric(report_a, "metrics.rr_mean_ms"),
                self.get_numeric(report_a, "metrics.rr_median_ms"),
            ],
            [
                self.get_numeric(report_b, "metrics.hr_count_based_bpm"),
                self.get_numeric(report_b, "metrics.hr_rr_based_bpm"),
                self.get_numeric(report_b, "metrics.rr_mean_ms"),
                self.get_numeric(report_b, "metrics.rr_median_ms"),
            ],
            "bpm / ms"
        )

        self.plot_grouped_bars(
            self.plot_hrv,
            "HRV metrics",
            ["SDNN", "RMSSD", "pNN50", "RR out"],
            [
                self.get_numeric(report_a, "metrics.sdnn_ms"),
                self.get_numeric(report_a, "metrics.rmssd_ms"),
                self.get_numeric(report_a, "metrics.pnn50_percent"),
                self.get_numeric(report_a, "signal_quality.rr_quality.rr_outlier_count"),
            ],
            [
                self.get_numeric(report_b, "metrics.sdnn_ms"),
                self.get_numeric(report_b, "metrics.rmssd_ms"),
                self.get_numeric(report_b, "metrics.pnn50_percent"),
                self.get_numeric(report_b, "signal_quality.rr_quality.rr_outlier_count"),
            ],
            "ms / % / count"
        )

        self.plot_grouped_bars(
            self.plot_adc,
            "ADC headroom and range",
            ["Raw min", "Raw max", "Median", "P-P"],
            [
                self.get_numeric(report_a, "signal_quality.raw_signal_stats.min"),
                self.get_numeric(report_a, "signal_quality.raw_signal_stats.max"),
                self.get_numeric(report_a, "signal_quality.raw_signal_stats.median"),
                self.get_numeric(report_a, "signal_quality.raw_signal_stats.peak_to_peak"),
            ],
            [
                self.get_numeric(report_b, "signal_quality.raw_signal_stats.min"),
                self.get_numeric(report_b, "signal_quality.raw_signal_stats.max"),
                self.get_numeric(report_b, "signal_quality.raw_signal_stats.median"),
                self.get_numeric(report_b, "signal_quality.raw_signal_stats.peak_to_peak"),
            ],
            "ADC counts"
        )

        self.plot_grouped_bars(
            self.plot_artifacts,
            "Artifacts and clipping",
            ["Low clip", "High clip", "Jumps", "RR out"],
            [
                self.get_numeric(report_a, "signal_quality.raw_artifact_flags.possible_clipping_low_count"),
                self.get_numeric(report_a, "signal_quality.raw_artifact_flags.possible_clipping_high_count"),
                self.get_numeric(report_a, "signal_quality.raw_artifact_flags.large_jump_count"),
                self.get_numeric(report_a, "signal_quality.rr_quality.rr_outlier_count"),
            ],
            [
                self.get_numeric(report_b, "signal_quality.raw_artifact_flags.possible_clipping_low_count"),
                self.get_numeric(report_b, "signal_quality.raw_artifact_flags.possible_clipping_high_count"),
                self.get_numeric(report_b, "signal_quality.raw_artifact_flags.large_jump_count"),
                self.get_numeric(report_b, "signal_quality.rr_quality.rr_outlier_count"),
            ],
            "Count"
        )
