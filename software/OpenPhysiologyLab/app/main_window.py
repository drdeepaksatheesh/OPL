# app/main_window.py

import sys
from pathlib import Path

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QMessageBox
)

from app.setup_panel import SetupPanel
from app.recorder_panel import RecorderPanel
from app.analysis_panel import AnalysisPanel
from app.results_panel import ResultsPanel
from app.compare_panel import ComparePanel
from app.machine_panel import MachinePanel
from app.theme import build_stylesheet


class OpenPhysiologyLabMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("OpenPhysiologyLab")
        self.resize(1500, 950)

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.theme_mode = "dark"

        self.setup_panel = SetupPanel()
        self.recorder_panel = RecorderPanel()
        self.analysis_panel = AnalysisPanel()
        self.results_panel = ResultsPanel()
        self.compare_panel = ComparePanel()
        try:
            self.analysis_panel.open_results_requested.connect(self.open_results_report)
        except Exception:
            pass
        self.setup_panel.protocol_selected.connect(self.apply_protocol_to_recorder)
        self.machine_panel = MachinePanel()

        self.tabs.addTab(self.setup_panel, "Setup")
        self.tabs.addTab(self.recorder_panel, "Recorder")
        self.tabs.addTab(self.analysis_panel, "Analysis")
        self.tabs.addTab(self.results_panel, "Results")
        self.tabs.addTab(self.compare_panel, "Compare")
        self.tabs.addTab(self.machine_panel, "Machine")

        self.apply_global_dark_theme()
        self.sync_child_theme(light_mode=False)
        self.connect_recorder_to_analysis()

    def apply_global_dark_theme(self):
        self.theme_mode = "dark"

        self.setStyleSheet(build_stylesheet("dark"))
        self.apply_child_plot_themes("dark")

    def apply_global_light_theme(self):
        self.theme_mode = "light"

        self.setStyleSheet(build_stylesheet("light"))
        self.apply_child_plot_themes("light")

    def apply_child_plot_themes(self, mode):
        """
        Apply plot theme to child panels that expose apply_plot_theme().
        ResultsPanel has no plots, so it is harmless if skipped.
        """

        for panel_name in [
            "recorder_panel",
            "analysis_panel",
            "results_panel",
        ]:
            panel = getattr(self, panel_name, None)

            if panel is None:
                continue

            try:
                if hasattr(panel, "apply_plot_theme"):
                    panel.apply_plot_theme(mode)
            except Exception:
                pass


    def open_results_report(self, report_path):
        """
        Load a specific analysis_report.json in Results tab and switch to it.
        """

        try:
            report_path = Path(report_path)
        except Exception:
            pass

        try:
            ok = self.results_panel.load_report_path(report_path)
        except Exception as e:
            try:
                QMessageBox.warning(
                    self,
                    "Results Load Failed",
                    f"Could not load Results report:\\n{report_path}\\n\\n{e}"
                )
            except Exception:
                pass
            return

        if ok is False:
            try:
                QMessageBox.warning(
                    self,
                    "Results Load Failed",
                    f"Results panel could not load report:\\n{report_path}"
                )
            except Exception:
                pass
            return

        try:
            self.tabs.setCurrentWidget(self.results_panel)
        except Exception:
            try:
                for i in range(self.tabs.count()):
                    if self.tabs.widget(i) is self.results_panel:
                        self.tabs.setCurrentIndex(i)
                        break
            except Exception:
                pass


    def sync_child_theme(self, light_mode):
        """
        Keep child panels aligned with the global theme.
        """

        for panel_name in [
            "setup_panel",
            "recorder_panel",
            "analysis_panel",
            "results_panel",
            "compare_panel",
            "machine_panel",
        ]:
            try:
                panel = getattr(self, panel_name, None)

                if panel is not None and hasattr(panel, "set_external_theme"):
                    panel.set_external_theme(light_mode)
            except Exception:
                pass


    def connect_recorder_to_analysis(self):
        """
        Connect RecorderPanel to AnalysisPanel if the recorder exposes
        analyse_recording_requested signal.
        """

        if hasattr(self.recorder_panel, "analyse_recording_requested"):
            self.recorder_panel.analyse_recording_requested.connect(
                self.open_recording_in_analysis
            )
        else:
            QMessageBox.information(
                self,
                "Recorder Not Yet Linked",
                (
                    "RecorderPanel does not yet expose analyse_recording_requested.\\n\\n"
                    "You can still use the Analysis tab manually.\\n"
                    "Next patch will add the Analyse Recording button to Recorder."
                )
            )

    def open_recording_in_analysis(self, folder_path):
        folder_path = Path(folder_path)

        if not folder_path.exists():
            QMessageBox.warning(
                self,
                "Recording Folder Missing",
                f"Could not find recording folder:\\n{folder_path}"
            )
            return

        ok = self.analysis_panel.load_recording_folder_path(
            folder_path,
            temporary=True
        )

        if ok:
            self.tabs.setCurrentWidget(self.analysis_panel)


    def apply_protocol_to_recorder(self, config):
        """
        Receive protocol config from Setup tab, apply it to Recorder,
        then switch to Recorder tab.
        """

        try:
            if hasattr(self, "recorder_panel") and hasattr(self.recorder_panel, "apply_protocol_config"):
                self.recorder_panel.apply_protocol_config(config)
        except Exception as e:
            print(f"Could not apply protocol to recorder: {e}")

        try:
            for tab_name in ["tabs", "tab_widget"]:
                tabs = getattr(self, tab_name, None)

                if tabs is None:
                    continue

                idx = tabs.indexOf(self.recorder_panel)

                if idx >= 0:
                    tabs.setCurrentIndex(idx)
                    break
        except Exception as e:
            print(f"Could not switch to Recorder tab: {e}")


def main():
    app = QApplication(sys.argv)

    window = OpenPhysiologyLabMainWindow()
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()