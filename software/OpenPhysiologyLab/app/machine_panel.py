import json
import html

from PyQt5.QtCore import Qt

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QComboBox, QGroupBox, QMessageBox, QSplitter
)

from app.machine_registry import (
    list_machine_profiles,
    build_manual_machine_evaluation,
    save_machine_evaluation_report,
    get_latest_machine_evaluation_snapshot
)


class MachinePanel(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("OpenPhysiologyLab Machine Panel")

        layout = QVBoxLayout()
        self.setLayout(layout)

        title = QLabel("OpenPhysiologyLab Machine Panel")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #F2F2F4; padding: 2px;")
        layout.addWidget(title)

        info = QLabel(
            "Machine tab = instrument record room. Refresh reloads saved machine profiles/reports. "
            "Run Machine Evaluation creates a profile-level check. The most important evaluation is "
            "session-level evaluation after each recording, which should travel with Analysis metadata."
        )
        info.setWordWrap(True)
        info.setStyleSheet(
            "font-weight: bold; color: #D4AF37; padding: 5px; "
            "background-color: #0E1218; border: 1px solid #202630;"
        )
        layout.addWidget(info)

        top_group = QGroupBox("Machine Profile")
        top_row = QHBoxLayout()
        top_group.setLayout(top_row)

        top_row.addWidget(QLabel("Machine"))

        self.profile_box = QComboBox()
        self.profile_box.setMinimumWidth(350)
        self.profile_box.currentIndexChanged.connect(self.show_selected_profile)
        top_row.addWidget(self.profile_box, stretch=1)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh_profiles)
        top_row.addWidget(self.refresh_btn)

        self.run_eval_btn = QPushButton("Run Machine Evaluation")
        self.run_eval_btn.setToolTip(
            "Creates a profile-level machine_evaluation_report.json. "
            "Use this to document the selected device/profile. "
            "It does not replace session-level evaluation after real recordings. "
            "Full electronic self-test will need later firmware support."
        )
        self.run_eval_btn.clicked.connect(self.run_machine_evaluation)
        top_row.addWidget(self.run_eval_btn)

        layout.addWidget(top_group)

        # ------------------------------------------------------------
        # Side-by-side machine information panes
        # ------------------------------------------------------------

        self.machine_splitter = QSplitter(Qt.Horizontal)

        self.profile_group = QGroupBox("Machine Profile")
        self.profile_group.setObjectName("greenAccentBox")
        profile_layout = QVBoxLayout()
        self.profile_group.setLayout(profile_layout)

        self.profile_text = QTextEdit()
        self.profile_text.setReadOnly(True)
        self.profile_text.setObjectName("greenAccentText")
        profile_layout.addWidget(self.profile_text)

        self.eval_group = QGroupBox("Latest Machine Evaluation")
        self.eval_group.setObjectName("greenAccentBox")
        eval_layout = QVBoxLayout()
        self.eval_group.setLayout(eval_layout)

        self.eval_text = QTextEdit()
        self.eval_text.setReadOnly(True)
        self.eval_text.setObjectName("greenAccentText")
        eval_layout.addWidget(self.eval_text)

        self.machine_splitter.addWidget(self.profile_group)
        self.machine_splitter.addWidget(self.eval_group)
        self.machine_splitter.setSizes([700, 700])

        layout.addWidget(self.machine_splitter, stretch=1)

        self.apply_dark_style()
        self.refresh_profiles()

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

            QGroupBox#greenAccentBox {
                background-color: #0E1218;
                border: 1px solid #50C878;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 9px;
                color: #50C878;
                font-weight: 400;
            }

            QGroupBox#greenAccentBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 9px;
                padding: 0px 6px;
                background-color: #0E1218;
                color: #50C878;
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

            QComboBox {
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

            QTextEdit#greenAccentText {
                background-color: #080B10;
                color: #F2F2F4;
                border: 1px solid #202630;
                border-radius: 6px;
                padding: 8px;
                selection-background-color: #50C878;
                selection-color: #000000;
            }

            QSplitter::handle {
                background-color: #2D333F;
            }

            QSplitter::handle:hover {
                background-color: #50C878;
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
                background: #50C878;
            }
            """
        )


    def showEvent(self, event):
        try:
            super().showEvent(event)
        except Exception:
            pass

        try:
            # When the Machine tab is opened, show latest machine/session by default.
            self.refresh_profiles(preserve_selected=False)
        except Exception:
            pass


    def set_external_theme(self, light_mode):
        self.apply_dark_style()

    def profile_sort_key(self, profile):
        """
        Sort profiles by most recent useful timestamp.

        Priority:
        1. latest evaluation datetime
        2. latest connection datetime
        3. updated datetime
        4. created datetime
        """

        latest_eval = profile.get("latest_evaluation_report", {}) or {}
        latest_connection = profile.get("latest_connection", {}) or {}

        return (
            str(latest_eval.get("evaluation_datetime", "")),
            str(latest_connection.get("datetime", "")),
            str(profile.get("updated_datetime", "")),
            str(profile.get("created_datetime", "")),
        )

    def refresh_profiles(self, *args, preserve_selected=False, select_uid=None):
        """
        Reload machine profiles from disk.

        Default behaviour:
        - sort newest profile first
        - select newest profile

        If preserve_selected=True:
        - keep currently selected UID if it still exists
        """

        previous_uid = self.get_selected_machine_uid() if preserve_selected else None

        self.profiles = list_machine_profiles()
        self.profiles = sorted(
            self.profiles,
            key=self.profile_sort_key,
            reverse=True
        )

        self.profile_box.blockSignals(True)
        self.profile_box.clear()

        if not self.profiles:
            self.profile_box.addItem("No machine profiles yet")
            self.profile_box.blockSignals(False)
            self.show_selected_profile()
            return

        for profile in self.profiles:
            uid = profile.get("machine_uid", "unknown")
            label = profile.get("device_id_user_label", "unknown")

            latest_eval = profile.get("latest_evaluation_report", {}) or {}
            eval_status = latest_eval.get("overall_status", "--")
            eval_time = latest_eval.get("evaluation_datetime", "--")

            self.profile_box.addItem(
                f"{label} | {uid} | {eval_status} | {eval_time}",
                uid
            )

        target_uid = select_uid or previous_uid

        if target_uid is None:
            # newest profile is first after sorting
            self.profile_box.setCurrentIndex(0)
        else:
            found_index = -1

            for i in range(self.profile_box.count()):
                if self.profile_box.itemData(i) == target_uid:
                    found_index = i
                    break

            if found_index >= 0:
                self.profile_box.setCurrentIndex(found_index)
            else:
                self.profile_box.setCurrentIndex(0)

        self.profile_box.blockSignals(False)
        self.show_selected_profile()


    def get_selected_machine_uid(self):
        if not getattr(self, "profiles", None):
            return None

        index = self.profile_box.currentIndex()

        if index < 0:
            return None

        return self.profile_box.itemData(index)

    def get_selected_profile(self):
        uid = self.get_selected_machine_uid()

        if uid is None:
            return None

        for profile in self.profiles:
            if profile.get("machine_uid") == uid:
                return profile

        return None

    def show_selected_profile(self):
        profile = self.get_selected_profile()

        if profile is None:
            self.profile_text.setText(
                "No machine profile yet.\n\n"
                "Connect and record from a device in the Recorder tab. "
                "The software will create/update machine_profiles automatically."
            )
            self.eval_text.setHtml(
                f"<html><head>{self.html_style()}</head><body>"
                "<div class='title'>Latest Machine Evaluation</div>"
                "<div class='note'>No evaluation available.</div>"
                "</body></html>"
            )
            return

        self.profile_text.setHtml(self.format_machine_profile_summary(profile))

        uid = profile.get("machine_uid")
        latest = get_latest_machine_evaluation_snapshot(uid)

        if latest is None:
            self.eval_text.setHtml(
                f"<html><head>{self.html_style()}</head><body>"
                "<div class='title'>Latest Machine Evaluation</div>"
                "<div class='note'>No machine evaluation report yet.</div>"
                "<div class='section'>What to do</div>"
                "<div class='note'>Record a session to generate a session-level evaluation, "
                "or click Run Machine Evaluation for a profile-level check.</div>"
                "</body></html>"
            )
        else:
            self.eval_text.setHtml(self.format_latest_evaluation_summary(latest))

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
                font-size: 10.5pt;
                font-weight: 800;
                margin-top: 0px;
                margin-bottom: 9px;
            }

            .section {
                color: #D4AF37;
                font-size: 10pt;
                font-weight: 800;
                margin-top: 13px;
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
                font-weight: 800;
            }

            .warning {
                color: #D4AF37;
                font-weight: 800;
            }

            .fail {
                color: #FF5C5C;
                font-weight: 800;
            }

            .note {
                color: #F2F2F4;
                font-weight: 400;
                line-height: 1.35;
            }

            .smallnote {
                color: #8F96A6;
                font-size: 9pt;
                font-weight: 400;
                line-height: 1.25;
            }

            .goodbox {
                color: #F2F2F4;
                background-color: rgba(80, 200, 120, 24);
                border-left: 3px solid #50C878;
                padding: 7px 9px;
                margin-top: 8px;
                margin-bottom: 8px;
                line-height: 1.35;
            }

            .warnbox {
                color: #F2F2F4;
                background-color: rgba(212, 175, 55, 28);
                border-left: 3px solid #D4AF37;
                padding: 7px 9px;
                margin-top: 8px;
                margin-bottom: 8px;
                line-height: 1.35;
            }

            table {
                border-collapse: collapse;
            }

            td {
                padding: 3px 12px 3px 0px;
                vertical-align: top;
            }
        </style>
        """

    def escape_html(self, value):
        return html.escape(str(value), quote=True)

    def looks_like_raw_sample_line(self, value):
        """
        Detect serial streaming rows such as:
        216,59082775,1297,...
        These should not be displayed as device identity/status.
        """

        s = str(value).strip().strip("'").strip('"')

        if not s:
            return False

        parts = [p.strip().strip("'").strip('"') for p in s.split(",")]

        if len(parts) < 3:
            return False

        numeric_count = 0

        for p in parts[:6]:
            try:
                float(p)
                numeric_count += 1
            except Exception:
                pass

        return numeric_count >= 2

    def clean_device_line_for_display(self, value):
        """
        Keep only real device identity/status information.

        Accepted examples:
        DEVICE,OpenPhysio_NPG_Lite_FW,0.1
        STATUS,streaming=0,sample_rate=500,...
        OpenPhysio NPG Lite Firmware Ready

        Rejected examples:
        raw streaming sample rows
        timestamp,adc,adc...
        """

        s = str(value).strip()

        if not s:
            return None

        # If a real identity/status token is embedded after raw garbage,
        # cut from the meaningful token onward.
        for token in ["DEVICE,", "STATUS,"]:
            idx = s.find(token)

            if idx >= 0:
                return s[idx:].strip()

        lower = s.lower()

        useful_keywords = [
            "openphysio",
            "firmware",
            "fw",
            "device",
            "status",
            "ready",
            "sample_rate",
            "channels",
            "baud",
            "streaming",
        ]

        if any(k in lower for k in useful_keywords):
            return s

        if self.looks_like_raw_sample_line(s):
            return None

        # Unknown serial chatter is not useful for Machine Profile identity.
        return None

    def format_device_lines_html(self, value, empty_text):
        """
        Convert latest_identity/latest_status into clean HTML.
        Filters raw sample rows before display.
        """

        if value is None:
            return f"<div class='note'>{self.escape_html(empty_text)}</div>"

        if isinstance(value, (list, tuple)):
            items = value
        else:
            items = [value]

        cleaned = []

        for item in items:
            clean = self.clean_device_line_for_display(item)

            if clean is not None:
                cleaned.append(self.escape_html(clean))

        if not cleaned:
            return (
                f"<div class='note'>{self.escape_html(empty_text)}</div>"
                "<div class='smallnote'>Raw streaming sample rows were hidden from this display.</div>"
            )

        return "<div class='note'>" + "<br>".join(cleaned) + "</div>"

    def evaluation_context_html(self, latest):
        """
        Explain what kind of machine evaluation this is.
        """

        eval_type = str(latest.get("evaluation_type", "unknown")).upper()

        if "SESSION" in eval_type:
            return """
            <div class='goodbox'>
                This is a session-level machine evaluation from an actual recording.
                Use this when interpreting Analysis results from that recording.
            </div>
            """

        if "MANUAL" in eval_type or "PROFILE" in eval_type:
            return """
            <div class='warnbox'>
                This is a profile-level manual machine evaluation.
                It documents the selected machine/profile, but it does not replace
                the session-level evaluation generated after a real recording.
            </div>
            """

        return """
        <div class='warnbox'>
            Evaluation type is not clearly classified. Treat it as contextual machine information,
            not as a substitute for session-level signal quality.
        </div>
        """


    def format_machine_profile_summary(self, profile):
        uid = profile.get("machine_uid", "unknown")
        label = profile.get("device_id_user_label", "unknown")
        family = profile.get("device_family", "unknown")
        created = profile.get("created_datetime", "unknown")
        updated = profile.get("updated_datetime", "unknown")
        latest_connection = profile.get("latest_connection", {}) or {}
        latest_identity = profile.get("latest_identity", None)
        latest_status = profile.get("latest_status", None)
        latest_eval = profile.get("latest_evaluation_report", None)

        connection_rows = ""

        if latest_connection:
            connection_rows = f"""
            <tr><td class='label'>Port</td><td class='value'>{self.escape_html(latest_connection.get('port', 'unknown'))}</td></tr>
            <tr><td class='label'>Baudrate</td><td class='value'>{self.escape_html(latest_connection.get('baudrate', 'unknown'))}</td></tr>
            <tr><td class='label'>Sample rate</td><td class='value'>{self.escape_html(latest_connection.get('sample_rate_hz', 'unknown'))} Hz</td></tr>
            <tr><td class='label'>Channels</td><td class='value'>{self.escape_html(latest_connection.get('channels', 'unknown'))}</td></tr>
            <tr><td class='label'>Datetime</td><td class='value'>{self.escape_html(latest_connection.get('datetime', 'unknown'))}</td></tr>
            """
        else:
            connection_rows = "<tr><td class='value'>No connection recorded yet.</td></tr>"

        identity_html = self.format_device_lines_html(
            latest_identity,
            "No clean identity line captured yet."
        )

        status_html = self.format_device_lines_html(
            latest_status,
            "No clean device status captured yet."
        )

        eval_html = ""

        if latest_eval:
            eval_status = latest_eval.get("overall_status", "unknown")
            eval_html = f"""
            <table>
                <tr><td class='label'>Status</td><td class='value'>{self.escape_html(eval_status)}</td></tr>
                <tr><td class='label'>Type</td><td class='value'>{self.escape_html(latest_eval.get('evaluation_type', 'unknown'))}</td></tr>
                <tr><td class='label'>Time</td><td class='value'>{self.escape_html(latest_eval.get('evaluation_datetime', 'unknown'))}</td></tr>
                <tr><td class='label'>Report</td><td class='value'>{self.escape_html(latest_eval.get('report_path', 'unknown'))}</td></tr>
            </table>
            """
        else:
            eval_html = "<div class='note'>No evaluation report saved yet.</div>"

        html_text = f"""
        <html>
        <head>{self.html_style()}</head>
        <body>
            <div class='title'>Machine Profile</div>

            <table>
                <tr><td class='label'>Machine UID</td><td class='value'>{self.escape_html(uid)}</td></tr>
                <tr><td class='label'>User label</td><td class='value'>{self.escape_html(label)}</td></tr>
                <tr><td class='label'>Device family</td><td class='value'>{self.escape_html(family)}</td></tr>
                <tr><td class='label'>Created</td><td class='value'>{self.escape_html(created)}</td></tr>
                <tr><td class='label'>Updated</td><td class='value'>{self.escape_html(updated)}</td></tr>
            </table>

            <div class='section'>Latest connection</div>
            <table>{connection_rows}</table>

            <div class='section'>Latest identity</div>
            {identity_html}

            <div class='section'>Latest device status</div>
            {status_html}

            <div class='section'>Latest evaluation link</div>
            {eval_html}

            <div class='section'>How to use this tab</div>
            <div class='note'>
                <span class='label'>Refresh</span> reloads saved machine_profiles and reports from disk.
                It does not create a new evaluation.
                <br><br>
                <span class='label'>Run Machine Evaluation</span> creates a profile-level report for this selected device.
                It is useful for documentation, but real signal trust is decided by the session-level evaluation after recording.
            </div>

            <div class='section'>Important</div>
            <div class='warnbox'>
                Machine Profile describes the instrument. Session Machine Evaluation describes a specific recording.
                Analysis should carry the session evaluation as a warning/context block.
            </div>
        </body>
        </html>
        """

        return html_text


    def format_latest_evaluation_summary(self, latest):
        status = latest.get("overall_status", "unknown")

        status_class = "warning"
        if str(status).upper() == "PASS":
            status_class = "good"
        elif str(status).upper() == "FAIL":
            status_class = "fail"
        elif str(status).upper() == "CAUTION":
            status_class = "warning"

        usability = latest.get("usability", None)
        channel_summary = latest.get("channel_summary", {}) or {}
        recommendations = latest.get("recommendations", []) or []

        usability_html = "<div class='note'>No usability summary available.</div>"

        if isinstance(usability, dict) and usability:
            usability_html = f"""
            <table>
                <tr><td class='label'>Timing</td><td class='value'>{usability.get('timing', 'unknown')}</td></tr>
                <tr><td class='label'>Amplitude</td><td class='value'>{usability.get('amplitude', 'unknown')}</td></tr>
                <tr><td class='label'>Morphology</td><td class='value'>{usability.get('morphology', 'unknown')}</td></tr>
                <tr><td class='label'>Teaching demo</td><td class='value'>{usability.get('teaching_demo', 'unknown')}</td></tr>
                <tr><td class='label'>Interpretation</td><td class='value'>{usability.get('interpretation', '')}</td></tr>
            </table>
            """

        channel_html = ""

        if isinstance(channel_summary, dict) and channel_summary:
            for ch_name, ch in channel_summary.items():
                if not isinstance(ch, dict):
                    continue

                channel_html += f"""
                <div class='section'>{ch_name} ADC headroom</div>
                <table>
                    <tr><td class='label'>Status</td><td class='value'>{ch.get('status', 'unknown')}</td></tr>
                    <tr><td class='label'>Samples</td><td class='value'>{ch.get('samples', 'unknown')}</td></tr>
                    <tr><td class='label'>Median baseline</td><td class='value'>{self.fmt(ch.get('median_baseline'))} ADC</td></tr>
                    <tr><td class='label'>Min / Max</td><td class='value'>{self.fmt(ch.get('min'))} / {self.fmt(ch.get('max'))} ADC</td></tr>
                    <tr><td class='label'>Peak-to-peak</td><td class='value'>{self.fmt(ch.get('peak_to_peak'))} ADC</td></tr>
                    <tr><td class='label'>Lower headroom</td><td class='value'>{self.fmt(ch.get('lower_headroom_adc'))} ADC</td></tr>
                    <tr><td class='label'>Upper headroom</td><td class='value'>{self.fmt(ch.get('upper_headroom_adc'))} ADC</td></tr>
                    <tr><td class='label'>Low clipping</td><td class='value'>{ch.get('low_clip_count', 'unknown')} ({self.fmt(ch.get('low_clip_percent'))}%)</td></tr>
                    <tr><td class='label'>High clipping</td><td class='value'>{ch.get('high_clip_count', 'unknown')} ({self.fmt(ch.get('high_clip_percent'))}%)</td></tr>
                </table>
                """
        else:
            channel_html = "<div class='note'>No channel ADC summary available.</div>"

        rec_html = ""

        if recommendations:
            for rec in recommendations:
                rec_html += f"<div class='note'>• {rec}</div>"
        else:
            rec_html = "<div class='note'>No recommendations available.</div>"

        html = f"""
        <html>
        <head>{self.html_style()}</head>
        <body>
            <div class='title'>Latest Machine Evaluation</div>

            {self.evaluation_context_html(latest)}

            <table>
                <tr><td class='label'>Status</td><td class='{status_class}'>{status}</td></tr>
                <tr><td class='label'>Evaluation type</td><td class='value'>{latest.get('evaluation_type', 'unknown')}</td></tr>
                <tr><td class='label'>Signal type</td><td class='value'>{latest.get('signal_type', 'unknown')}</td></tr>
                <tr><td class='label'>Protocol</td><td class='value'>{latest.get('protocol_name', 'unknown')}</td></tr>
                <tr><td class='label'>Time</td><td class='value'>{latest.get('evaluation_datetime', 'unknown')}</td></tr>
                <tr><td class='label'>Report path</td><td class='value'>{latest.get('report_path', 'unknown')}</td></tr>
            </table>

            <div class='section'>Summary</div>
            <div class='note'>{latest.get('summary', '')}</div>

            <div class='section'>Usability</div>
            {usability_html}

            {channel_html}

            <div class='section'>Recommendations</div>
            {rec_html}

            <div class='section'>Important interpretation</div>
            <div class='note'>
                PASS / CAUTION / FAIL describes machine-session ADC behaviour.
                A CAUTION ECG may still be usable for RR timing if R-peaks are correct,
                but clipped morphology or amplitude should not be trusted.
            </div>
        </body>
        </html>
        """

        return html


    def fmt(self, value, digits=3):
        try:
            return f"{float(value):.{digits}f}"
        except Exception:
            return "unknown"

    def run_machine_evaluation(self):
        uid = self.get_selected_machine_uid()

        if uid is None:
            QMessageBox.warning(
                self,
                "No Machine",
                "No machine profile is available yet. Connect and record from a device first."
            )
            return

        report = build_manual_machine_evaluation(machine_uid=uid)
        path = save_machine_evaluation_report(uid, report)

        QMessageBox.information(
            self,
            "Machine Evaluation Saved",
            f"Machine evaluation saved:\n{path}"
        )

        self.refresh_profiles(select_uid=uid)
