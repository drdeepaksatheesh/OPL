# app/ecg_calipers_panel.py

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout,
    QGroupBox, QTextEdit
)
from PyQt5.QtCore import Qt


class ECGCalipersPanel(QWidget):
    """
    ECG Calipers tab.

    Planned purpose:
    - Load current or saved ECG recording
    - Show raw / filtered signal
    - Select one beat with previous and next ECG complexes visible
    - Place manual ECG calipers
    - Export beat-wise ECG morphology measurements
    """

    def __init__(self):
        super().__init__()

        self.setWindowTitle("OpenPhysiologyLab ECG Calipers")

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        title = QLabel("OpenPhysiologyLab ECG Calipers")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(title)

        subtitle = QLabel(
            "Beat-wise ECG morphology measurement using manual calipers. "
            "This tab is separate from HRV analysis."
        )
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        source_group = QGroupBox("Recording Source")
        source_layout = QHBoxLayout(source_group)

        self.use_latest_btn = QPushButton("Use Latest Recording")
        self.load_folder_btn = QPushButton("Load Recording Folder")
        self.load_raw_btn = QPushButton("Load raw.csv")

        self.use_latest_btn.setToolTip(
            "Planned: load the most recent recording from Recorder."
        )
        self.load_folder_btn.setToolTip(
            "Planned: load a saved OPL recording folder."
        )
        self.load_raw_btn.setToolTip(
            "Planned: load a raw.csv file directly."
        )

        source_layout.addWidget(self.use_latest_btn)
        source_layout.addWidget(self.load_folder_btn)
        source_layout.addWidget(self.load_raw_btn)

        layout.addWidget(source_group)

        view_group = QGroupBox("Signal View")
        view_layout = QVBoxLayout(view_group)

        self.placeholder = QTextEdit()
        self.placeholder.setReadOnly(True)
        self.placeholder.setText(
            "ECG Calipers Stage 1\n\n"
            "This is a placeholder tab.\n\n"
            "Planned workflow:\n"
            "1. Load latest recording or raw.csv.\n"
            "2. Show raw or filtered ECG signal.\n"
            "3. Select an ECG beat.\n"
            "4. Display previous, selected, and next PQRST complexes.\n"
            "5. Place manual calipers for P onset, P peak, P offset, Q, R, S, J point, T peak, T offset, and baseline.\n"
            "6. Calculate amplitudes, durations, intervals, pre-RR, and post-RR.\n"
            "7. Export beat_measurements.csv.\n\n"
            "Safety: This is for education and experimentation, not diagnosis."
        )

        view_layout.addWidget(self.placeholder)
        layout.addWidget(view_group, stretch=1)