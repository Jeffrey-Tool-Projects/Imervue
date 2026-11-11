"""Optional-package refusal and the host's explicit Rigora integration contract."""
from __future__ import annotations

import ast
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from Imervue.gui import optional_tabs
from Imervue.gui.main_window_layout import MainWindowLayoutMixin
from Imervue.mcp_server import tools_read
from Imervue.system import rigora_integration as integration
from Imervue.user_settings.user_setting_dict import user_setting_dict


def _missing(_name):
    raise ModuleNotFoundError("No module named 'rigora'", name="rigora")


def test_absent_package_does_not_autostart_a_pet(monkeypatch):
    monkeypatch.setattr(integration, "import_module", _missing)
    user_setting_dict["desktop_pet"] = {"show_on_launch": True}
    assert optional_tabs.pet_shows_on_launch() is False


@pytest.mark.parametrize("builder,page_name,workspace_name", [
    ("_build_puppet_workspace", "_puppet_page", "puppet_workspace"),
    ("_build_pet_workspace", "_pet_page", "pet_workspace"),
])
def test_absent_package_keeps_tab_open_with_one_notice(
    qapp, monkeypatch, builder, page_name, workspace_name,
):
    monkeypatch.setattr(integration, "import_module", _missing)
    page = QWidget()
    QVBoxLayout(page)
    owner = SimpleNamespace(**{page_name: page, workspace_name: None})
    try:
        getattr(MainWindowLayoutMixin, builder)(owner)
        getattr(MainWindowLayoutMixin, builder)(owner)
        notices = page.findChildren(QLabel, "rigoraMissingNotice")
        assert len(notices) == 1
        assert "Rigora" in notices[0].text()
        assert getattr(owner, workspace_name) is None
    finally:
        page.deleteLater()


@pytest.mark.parametrize("handler,args", [
    (tools_read.puppet_schema, ()),
    (tools_read.puppet_validate, ("model.puppet",)),
    (tools_read.puppet_inspect, ("model.puppet",)),
    (tools_read.puppet_from_png, ("image.png", "model.puppet")),
])
def test_absent_package_has_actionable_command_error(monkeypatch, handler, args):
    monkeypatch.setattr(integration, "import_module", _missing)
    with pytest.raises(RuntimeError, match="Install the Rigora package"):
        handler(*args)


def test_installed_package_dependency_failure_is_not_reported_as_absent(monkeypatch):
    def broken(_name):
        raise ModuleNotFoundError("No module named 'numpy'", name="numpy")

    monkeypatch.setattr(integration, "import_module", broken)
    with pytest.raises(ModuleNotFoundError, match="numpy"):
        integration.require_rigora()
    with pytest.raises(ModuleNotFoundError, match="numpy"):
        integration.initialize_embedded_rigora()


def test_installed_schema_uses_rigora_command_contract():
    pytest.importorskip("rigora", reason="optional Rigora integration")
    from rigora.commands import puppet_schema

    assert tools_read.puppet_schema("motion") == puppet_schema("motion")


def test_embedding_imports_legacy_settings_once_and_flushes_own_file(qapp, tmp_path):
    pytest.importorskip("rigora", reason="optional Rigora integration")
    from rigora.system import settings

    user_setting_dict["desktop_pet"] = {"show_on_launch": False, "opacity": 0.7}
    assert integration.initialize_embedded_rigora()
    assert settings.user_setting_dict["desktop_pet"]["opacity"] == 0.7
    settings.user_setting_dict["desktop_pet"] = {"opacity": 0.9}
    user_setting_dict["desktop_pet"] = {"opacity": 0.2}
    assert integration.initialize_embedded_rigora()
    assert settings.user_setting_dict["desktop_pet"]["opacity"] == 0.9
    integration.flush_rigora_settings()
    saved = json.loads((tmp_path / "rigora.json").read_text(encoding="utf-8"))
    assert saved["desktop_pet"]["opacity"] == 0.9


def test_embedded_recording_results_reach_host_job_history(qapp):
    pytest.importorskip("rigora", reason="optional Rigora integration")
    from rigora.gui.background_jobs import job_registry as rigora_jobs
    from rigora.system.job_state import JobState
    from Imervue.gui.background_jobs import job_registry as host_jobs

    assert integration.initialize_embedded_rigora()
    state = JobState(["frame"])
    state.record("frame", output="frame.png")
    state.finish()
    job = rigora_jobs().add_completed("Rigora capture", state)
    try:
        assert rigora_jobs() is host_jobs()
        assert job in host_jobs().jobs and job.settled
    finally:
        host_jobs().jobs.remove(job)


def test_host_consumers_never_import_the_legacy_implementation():
    root = Path(__file__).resolve().parents[1] / "Imervue"
    offenders = []
    for path in root.rglob("*.py"):
        if path.relative_to(root).parts[0] in {"puppet", "desktop_pet"}:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            elif isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            else:
                continue
            if any(name.startswith(("Imervue.puppet", "Imervue.desktop_pet")) for name in names):
                offenders.append(f"{path.relative_to(root)}:{node.lineno}")
    assert offenders == []
