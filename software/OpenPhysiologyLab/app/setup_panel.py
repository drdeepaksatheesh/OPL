from pathlib import Path

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QTextEdit, QGroupBox, QFrame, QGraphicsOpacityEffect
)
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtGui import QPixmap

from app.protocol_registry import (
    get_signal_types,
    get_protocols_for_signal,
    build_recorder_config
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class SetupPanel(QWidget):
    protocol_selected = pyqtSignal(dict)

    def __init__(self):
        super().__init__()

        self.setWindowTitle("OpenPhysiologyLab Setup")

        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        self.setLayout(layout)

        # ------------------------------------------------------------
        # Branded hero header
        # ------------------------------------------------------------

        hero = QFrame()
        hero.setObjectName("heroFrame")
        hero_layout = QHBoxLayout()
        hero_layout.setContentsMargins(14, 14, 14, 14)
        hero_layout.setSpacing(14)
        hero.setLayout(hero_layout)

        self.logo_label = QLabel()
        self.logo_label.setFixedSize(96, 96)
        self.logo_label.setAlignment(Qt.AlignCenter)
        self.load_logo()
        hero_layout.addWidget(self.logo_label)

        title_col = QVBoxLayout()
        title_col.setSpacing(4)

        title = QLabel("OpenPhysiologyLab")
        title.setObjectName("heroTitle")
        title_col.addWidget(title)

        tagline = QLabel("Record. Analyze. Understand.")
        tagline.setObjectName("heroTagline")
        title_col.addWidget(tagline)

        mission = QLabel("Accessible physiology for everyone")
        mission.setObjectName("heroMission")
        mission.setWordWrap(True)
        title_col.addWidget(mission)

        helper = QLabel("Start with ECG acquisition, then move through calipers, RR intervals, NN decisions, and visual HRV.")
        helper.setObjectName("heroHelper")
        helper.setWordWrap(True)
        title_col.addWidget(helper)

        hero_layout.addLayout(title_col, stretch=1)

        layout.addWidget(hero)

        # ------------------------------------------------------------
        # Protocol selector card
        # ------------------------------------------------------------

        group = QGroupBox("ECG → HRV workflow setup")
        row = QHBoxLayout()
        row.setContentsMargins(10, 14, 10, 10)
        row.setSpacing(10)
        group.setLayout(row)

        row.addWidget(QLabel("Signal"))

        self.signal_box = QComboBox()
        self.signal_box.addItems(get_signal_types())
        self.signal_box.setMinimumWidth(120)
        self.signal_box.currentTextChanged.connect(self.signal_changed)
        row.addWidget(self.signal_box)

        row.addWidget(QLabel("Protocol"))

        self.protocol_box = QComboBox()
        self.protocol_box.currentTextChanged.connect(self.protocol_changed)
        self.protocol_box.setMinimumWidth(340)
        row.addWidget(self.protocol_box, stretch=1)

        self.use_btn = QPushButton("Use ECG setup → Recorder")
        self.use_btn.setObjectName("primaryButton")
        self.use_btn.clicked.connect(self.use_setup_clicked)
        row.addWidget(self.use_btn)

        layout.addWidget(group)

        # ------------------------------------------------------------
        # Dashboard summary
        # ------------------------------------------------------------

        dashboard_row = QHBoxLayout()
        dashboard_row.setSpacing(10)

        self.protocol_card = QTextEdit()
        self.protocol_card.setReadOnly(True)
        self.protocol_card.setObjectName("dashboardCard")
        dashboard_row.addWidget(self.protocol_card, stretch=2)

        self.logic_card = QTextEdit()
        self.logic_card.setReadOnly(True)
        self.logic_card.setObjectName("dashboardCard")
        dashboard_row.addWidget(self.logic_card, stretch=1)

        layout.addLayout(dashboard_row, stretch=1)

        # ------------------------------------------------------------
        # Centre watermark: opal + waveform
        # ------------------------------------------------------------
        self.center_watermark_label = QLabel(self)
        self.center_watermark_label.setAlignment(Qt.AlignCenter)
        self.center_watermark_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.center_watermark_label.setStyleSheet("background: transparent; border: none;")

        self.center_watermark_opacity = QGraphicsOpacityEffect(self.center_watermark_label)
        self.center_watermark_opacity.setOpacity(0.18)
        self.center_watermark_label.setGraphicsEffect(self.center_watermark_opacity)

        self.center_watermark_source = self.load_center_watermark_pixmap()

        self.apply_dark_style()
        self.signal_changed(self.signal_box.currentText())
        self.update_center_watermark()


    def logo_candidates(self):
        return [
            PROJECT_ROOT / "assets" / "openphysiolab.png",
            PROJECT_ROOT / "assets" / "openphysiologylab.png",
            PROJECT_ROOT / "assets" / "openphysiolab_logo.png",
            PROJECT_ROOT / "assets" / "openphysiologylab_logo.png",
            PROJECT_ROOT / "assets" / "openphysiolab_icon.png",
            PROJECT_ROOT / "assets" / "openphysiolab.ico",
        ]

    def load_logo(self):
        for candidate in self.logo_candidates():
            if candidate.exists():
                pix = QPixmap(str(candidate))

                if not pix.isNull():
                    pix = pix.scaled(
                        90,
                        90,
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation
                    )
                    self.logo_label.setPixmap(pix)
                    return

        self.logo_label.setText("OPL")
        self.logo_label.setObjectName("logoFallback")

    def load_center_watermark_pixmap(self):
        """
        Load the opal + waveform image used as centre watermark.

        Preferred file:
        assets/setup_watermark.png
        """

        candidates = [
            PROJECT_ROOT / "assets" / "setup_watermark_transparent.png",
            PROJECT_ROOT / "assets" / "setup_watermark.png",
            PROJECT_ROOT / "assets" / "setup_watermark.jpg",
            PROJECT_ROOT / "assets" / "setup_watermark.jpeg",
            PROJECT_ROOT / "assets" / "setup_watermark.webp",
            PROJECT_ROOT / "assets" / "openphysiolab_icon.png",
            PROJECT_ROOT / "assets" / "openphysiologylab_icon.png",
        ]

        for candidate in candidates:
            if candidate.exists():
                pix = QPixmap(str(candidate))

                if not pix.isNull():
                    return pix

        return None

    def update_center_watermark(self):
        if not hasattr(self, "center_watermark_label"):
            return

        if self.center_watermark_source is None or self.center_watermark_source.isNull():
            self.center_watermark_label.clear()
            return

        area_w = max(700, self.width())
        area_h = max(550, self.height())

        # Large faint watermark: visible as identity, not as clutter.
        target_w = int(area_w * 0.46)
        target_h = int(area_h * 0.70)

        scaled = self.center_watermark_source.scaled(
            target_w,
            target_h,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )

        self.center_watermark_label.setPixmap(scaled)
        self.center_watermark_label.resize(scaled.size())

        x = (self.width() - self.center_watermark_label.width()) // 2
        y = (self.height() - self.center_watermark_label.height()) // 2 + 55

        self.center_watermark_label.move(max(0, x), max(0, y))
        self.center_watermark_label.lower()


    def apply_dark_style(self):
        self.setStyleSheet(
            """
            QWidget {
                background-color: #0A0A0C;
                color: #F2F2F4;
                font-family: Segoe UI, Arial;
                font-size: 10pt;
            }

            QLabel {
                color: #F2F2F4;
                background-color: transparent;
            }

            QFrame#heroFrame {
                background-color: #0E1118;
                border: 1px solid #303441;
                border-radius: 12px;
            }

            QLabel#heroTitle {
                color: #F2F2F4;
                font-size: 28px;
                font-weight: bold;
                letter-spacing: 1px;
            }

            QLabel#heroTagline {
                color: #D4AF37;
                font-size: 17px;
                font-weight: bold;
            }

            QLabel#heroMission {
                color: #50C878;
                font-size: 11pt;
                font-weight: bold;
            }

            QLabel#heroHelper {
                color: #B8BBC6;
                font-size: 11pt;
            }

            QLabel#logoFallback {
                background-color: #050609;
                color: #D4AF37;
                border: 2px solid #25D8FF;
                border-radius: 46px;
                font-size: 24px;
                font-weight: bold;
            }

            QGroupBox {
                background-color: #0E1218;
                border: 1px solid #50C878;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 9px;
                font-weight: bold;
                color: #50C878;
            }

            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 9px;
                padding: 0px 6px;
                background-color: #0E1218;
                color: #50C878;
                font-weight: bold;
            }

            QPushButton {
                background-color: #161A23;
                color: #F2F2F4;
                border: 1px solid #3A3D46;
                border-radius: 5px;
                padding: 6px 10px;
                min-height: 24px;
            }

            QPushButton:hover {
                background-color: #202636;
                border: 1px solid #25D8FF;
            }

            QPushButton:pressed {
                background-color: #0E1016;
                border: 1px solid #FF2BC2;
            }

            QPushButton#primaryButton {
                background-color: #123022;
                color: #F2F2F4;
                border: 1px solid #45F28C;
                font-weight: bold;
                padding: 8px 14px;
            }

            QPushButton#primaryButton:hover {
                background-color: #17422D;
                border: 1px solid #25D8FF;
            }

            QComboBox {
                background-color: #08090D;
                color: #F2F2F4;
                border: 1px solid #3A3D46;
                border-radius: 4px;
                padding: 5px 8px;
                min-height: 24px;
            }

            QComboBox:hover {
                border: 1px solid #25D8FF;
            }

            QTextEdit {
                background-color: rgba(11, 13, 18, 224);
                color: #E8EAF0;
                border: 1px solid #2B2E36;
                border-radius: 6px;
                padding: 8px;
                selection-background-color: #25D8FF;
                selection-color: #000000;
            }

            QTextEdit#dashboardCard {
                background-color: rgba(11, 13, 18, 224);
                border: 1px solid #303441;
                border-radius: 8px;
                padding: 10px;
            }
            """
        )

    def set_external_theme(self, light_mode):
        self.apply_dark_style()

    def signal_changed(self, signal_type):
        self.protocol_box.blockSignals(True)
        self.protocol_box.clear()

        for protocol in get_protocols_for_signal(signal_type):
            self.protocol_box.addItem(
                protocol.get("display_name", protocol.get("protocol_name")),
                protocol.get("protocol_name")
            )

        self.protocol_box.blockSignals(False)
        self.protocol_changed(self.protocol_box.currentText())

    def protocol_changed(self, _text):
        config = self.get_current_config()
        self.protocol_card.setHtml(self.format_config_summary(config))
        self.logic_card.setHtml(self.format_logic_summary(config))

    def get_current_config(self):
        signal_type = self.signal_box.currentText()
        protocol_name = self.protocol_box.currentData()

        if protocol_name is None:
            protocol_name = self.protocol_box.currentText()

        return build_recorder_config(signal_type, protocol_name)

    def html_style(self):
        return """
        <style>
            body {
                color: #F2F5FA;
                font-family: Segoe UI, Arial;
                font-size: 10pt;
                line-height: 1.38;
                background: transparent;
            }

            .title {
                color: #D4AF37;
                font-size: 10.5pt;
                font-weight: 800;
                margin-top: 0px;
                margin-bottom: 9px;
            }

            .section-a {
                color: #D4AF37;
                font-size: 10pt;
                font-weight: 800;
                margin-top: 13px;
                margin-bottom: 5px;
            }

            .section-b {
                color: #D4AF37;
                font-weight: 800;
            }

            .section-c {
                color: #D4AF37;
                font-size: 10pt;
                font-weight: 800;
                margin-top: 13px;
                margin-bottom: 5px;
            }

            .section-d {
                color: #D4AF37;
                font-size: 10pt;
                font-weight: 800;
                margin-top: 13px;
                margin-bottom: 5px;
            }

            .section-e {
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

            .note {
                color: #F2F2F4;
                font-weight: 400;
                line-height: 1.35;
            }

            .bullet {
                color: #F2F2F4;
                font-weight: 400;
                margin-left: 10px;
            }

            .diagram {
                color: #D7D9DE;
                background-color: rgba(3, 4, 6, 120);
                border: 1px solid #2D333F;
                border-radius: 6px;
                padding: 8px;
                font-family: Consolas, Courier New, monospace;
                font-size: 9pt;
            }

            table {
                border-collapse: collapse;
            }

            .connection-table {
                width: 100%;
                border-collapse: collapse;
                margin-top: 6px;
                margin-bottom: 8px;
                background-color: rgba(3, 4, 6, 110);
                border: 1px solid #2D333F;
                border-radius: 6px;
            }

            .connection-table th {
                color: #D4AF37;
                font-weight: 800;
                padding: 6px 8px;
                border-bottom: 1px solid #2D333F;
                text-align: left;
            }

            .connection-table td {
                padding: 5px 8px;
                vertical-align: middle;
                border-bottom: 1px solid rgba(45, 51, 63, 120);
            }

            .body-point {
                color: #F2F2F4;
                font-weight: 400;
            }

            .npg-pin {
                color: #F2F2F4;
                font-weight: 700;
            }

            .arrow {
                color: #D4AF37;
                font-weight: 800;
                text-align: center;
            }

            .hint-box {
                color: #F2F2F4;
                background-color: rgba(80, 200, 120, 24);
                border-left: 3px solid #50C878;
                padding: 7px 9px;
                margin-top: 8px;
                line-height: 1.35;
            }

            .warning-box {
                color: #F2F2F4;
                background-color: rgba(255, 92, 92, 25);
                border-left: 3px solid #FF5C5C;
                padding: 7px 9px;
                margin-top: 8px;
                line-height: 1.35;
            }

            td {
                padding: 3px 12px 3px 0px;
                vertical-align: top;
            }
        </style>
        """

    def connection_guide_html(self, signal_type):
        signal_type = str(signal_type).upper()

        if signal_type != "ECG":
            return """
            <div class='section'>First public workflow</div>
            <div class='note'>
                This build is being cleaned for the ECG → HRV teaching pathway first.
                Other biosignals can be brought back after this path is stable.
            </div>
            """

        return """
        <div class='section'>Electrode placement</div>
        <div class='note'>
            Lead-II-like limb-axis ECG for education and exploratory physiology work.
            Use fresh gel electrodes, reduce cable tug, and record the exact pin mapping.
        </div>

        <table class='connection-table'>
            <tr>
                <th>Body electrode</th>
                <th></th>
                <th>NPG Lite input</th>
            </tr>
            <tr>
                <td class='body-point'>Right wrist / RA</td>
                <td class='arrow'>→</td>
                <td class='npg-pin'>A0P / CH input P</td>
            </tr>
            <tr>
                <td class='body-point'>Left leg / LL</td>
                <td class='arrow'>→</td>
                <td class='npg-pin'>A0N / CH input N</td>
            </tr>
            <tr>
                <td class='body-point'>Right leg / RL</td>
                <td class='arrow'>→</td>
                <td class='npg-pin'>REF / GND</td>
            </tr>
        </table>

        <div class='hint-box'>
            <b>Expected recording:</b> upright, Lead-II-like ECG with visible R peaks and enough
            ADC headroom for RR/NN interval teaching.
        </div>

        <div class='warning-box'>
            <b>Scope:</b> This is not a certified diagnostic Lead II. It is the current OPL/NPG Lite
            practical polarity configuration for teaching ECG timing and HRV workflow development.
        </div>
        """

    def format_config_summary(self, config):
        filt = config.get("filter", {}) or {}
        signal_type = config.get("signal_type")
        guide_html = self.connection_guide_html(signal_type)

        html = f"""
        <html>
        <head>{self.html_style()}</head>
        <body>
            <table width="100%">
                <tr>
                    <td width="42%" valign="top">
                        <div class="title">ECG acquisition setup</div>

                        <table>
                            <tr><td class="label">Signal</td><td class="value">{config.get('signal_type')}</td></tr>
                            <tr><td class="label">Protocol</td><td class="value">{config.get('protocol_display_name')}</td></tr>
                            <tr><td class="label">Channels</td><td class="value">{config.get('recommended_channels')}</td></tr>
                            <tr><td class="label">Sample rate</td><td class="value">{config.get('recommended_sample_rate_hz')} Hz</td></tr>
                            <tr><td class="label">Duration</td><td class="value">{config.get('recommended_duration_text')}</td></tr>
                        </table>

                        <div class="section">Recorder preset</div>
                        <div class="bullet">• Save raw CSV with a usable time column when available.</div>
                        <div class="bullet">• Keep channel naming consistent, preferably ch1 for the first ECG path.</div>
                        <div class="bullet">• Document subject/session/posture/electrode placement before recording.</div>

                        <div class="section">Review filter</div>
                        <table>
                            <tr><td class="label">Low cut</td><td class="value">{filt.get('low_hz')} Hz</td></tr>
                            <tr><td class="label">High cut</td><td class="value">{filt.get('high_hz')} Hz</td></tr>
                            <tr><td class="label">50 Hz notch</td><td class="value">{filt.get('notch_50hz')}</td></tr>
                        </table>

                        <div class="section">After recording</div>
                        <div class="bullet">• ECG Calipers checks the waveform and R-reference beats.</div>
                        <div class="bullet">• RR Pairs and RR Triplets teach interval-to-interval change.</div>
                        <div class="bullet">• RR / NN Table decides accepted NN intervals.</div>
                        <div class="bullet">• Visual HRV shows where each number comes from.</div>
                    </td>

                    <td width="58%" valign="top">
                        {guide_html}
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """

        return html

    def format_logic_summary(self, config):
        notes = config.get("protocol_notes", "")

        html = f"""
        <html>
        <head>{self.html_style()}</head>
        <body>
            <div class="title">Clean ECG → HRV workflow</div>

            <div class='note'>
                OPL should behave like one guided physiology path, not separate calculators.
                The first public path is ECG acquisition followed by transparent HRV derivation.
            </div>

            <div class="section">Workflow map</div>
            <div class="bullet">1. <b>Setup</b>: choose hardware, protocol, polarity, and recording plan.</div>
            <div class="bullet">2. <b>Recorder</b>: acquire and save raw ECG with metadata.</div>
            <div class="bullet">3. <b>ECG Calipers</b>: inspect raw/filtered ECG, average beat, and R-centred complexes.</div>
            <div class="bullet">4. <b>RR Pairs</b>: see one interval as A→B, beat by beat.</div>
            <div class="bullet">5. <b>RR Triplets</b>: see RR-pre, RR-post, ΔRR, pNN50, and RMSSD source geometry.</div>
            <div class="bullet">6. <b>RR / NN Table</b>: accept or reject intervals; this becomes the HRV source of truth.</div>
            <div class="bullet">7. <b>Visual HRV</b>: derive mean NN, HR, SDNN, RMSSD, pNN50, and Poincaré plots visually.</div>

            <div class="section">Rule</div>
            <div class="hint-box">
                Never show a number before showing where it came from.
            </div>

            <div class="section">Protocol note</div>
            <div class="note">{notes}</div>
        </body>
        </html>
        """

        return html

    def resizeEvent(self, event):
        super().resizeEvent(event)

        try:
            self.update_center_watermark()
        except Exception:
            pass

    def use_setup_clicked(self):
        self.protocol_selected.emit(self.get_current_config())
