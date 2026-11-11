"""The host job indicator remains usable without the optional animation package."""
from PySide6.QtWidgets import QMainWindow

from Imervue.gui.background_jobs import JobRegistry
from Imervue.gui.job_indicator import JobIndicator, install_job_indicator
from Imervue.system.job_state import JobState


def test_indicator_keeps_failure_count_and_opens_existing_panel(qapp, monkeypatch):
    window = QMainWindow()
    registry = JobRegistry()
    state = JobState(["capture.png"])
    state.finish(error="disk full")
    indicator = JobIndicator(window, registry=registry)
    registry.add_completed("Capture", state)
    assert "1" in indicator.text() and "failed" in indicator.text()
    opened = []
    monkeypatch.setattr("Imervue.gui.job_indicator.open_background_jobs", opened.append)
    indicator.click()
    assert opened == [window]
    assert install_job_indicator(window).parent() == window.statusBar()
    registry.clear_finished()
    assert "1" not in indicator.text()
    window.deleteLater()
    registry.deleteLater()
