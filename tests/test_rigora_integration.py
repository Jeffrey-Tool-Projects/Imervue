"""Optional-package refusal and the host's explicit Rigora integration contract."""
from __future__ import annotations

import ast
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

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
    owner = SimpleNamespace(**{page_name: page, workspace_name: None},
                            _on_rigora_installed=lambda: None)
    try:
        getattr(MainWindowLayoutMixin, builder)(owner)
        getattr(MainWindowLayoutMixin, builder)(owner)
        notices = page.findChildren(QLabel, "rigoraMissingNotice")
        assert len(notices) == 1
        assert len(page.findChildren(QPushButton, "rigoraInstallButton")) == 1
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


# ---------------------------------------------------------------------------
# Installing Rigora from inside Imervue (source and packaged builds)
# ---------------------------------------------------------------------------


def test_requirement_is_pinned_to_the_release_commit():
    requirement = integration.RIGORA_REQUIREMENT
    assert requirement == f"rigora @ {integration.RIGORA_ARCHIVE_URL}"
    assert integration.RIGORA_COMMIT in requirement
    assert integration.RIGORA_ARCHIVE_URL.startswith("https://github.com/")


def test_install_takes_rigora_alone():
    # Every Rigora dependency is already an Imervue dependency; resolving them
    # would put a second PySide6 in front of the bundled (or the user's) one.
    assert integration.RIGORA_INSTALL_ARGS == ("--no-deps",)


def test_rigora_available_reports_a_missing_package(monkeypatch):
    monkeypatch.setattr(integration, "import_module", _missing)
    assert integration.rigora_available() is False


def test_rigora_available_keeps_a_broken_dependency_visible(monkeypatch):
    def broken(_name):
        raise ModuleNotFoundError("No module named 'numpy'", name="numpy")

    monkeypatch.setattr(integration, "import_module", broken)
    with pytest.raises(ModuleNotFoundError, match="numpy"):
        integration.rigora_available()


def test_install_button_opens_the_installer_for_the_pinned_release(qapp, monkeypatch):
    from Imervue.plugin import pip_install_dialog

    opened = []

    class FakeDialog:
        def __init__(self, parent, missing, on_success=None, install_args=()):
            opened.append((missing, install_args, on_success))

        def setAttribute(self, *_args):
            pass

        def open(self):
            pass

    monkeypatch.setattr(integration, "import_module", _missing)
    monkeypatch.setattr(pip_install_dialog, "InstallDependenciesDialog", FakeDialog)
    page = QWidget()
    QVBoxLayout(page)
    try:
        assert optional_tabs.prepare_workspace(page, lambda: None) is False
        page.findChild(QPushButton, "rigoraInstallButton").click()
        [(missing, args, on_success)] = opened
        assert missing == [("rigora", integration.RIGORA_REQUIREMENT)]
        assert args == ("--no-deps",)
        assert callable(on_success)
    finally:
        page.deleteLater()


def test_finished_install_runs_the_callback_once_rigora_imports(monkeypatch):
    calls = []
    monkeypatch.setattr(integration, "import_module", lambda _name: object())
    optional_tabs._finish_install(lambda: calls.append("built"))
    assert calls == ["built"]


def test_finished_install_that_still_cannot_import_is_an_error(monkeypatch):
    monkeypatch.setattr(integration, "import_module", _missing)
    with pytest.raises(RuntimeError, match="cannot be imported"):
        optional_tabs._finish_install(lambda: pytest.fail("must not build"))


def test_after_install_each_tab_drops_its_notice_and_builds(qapp, monkeypatch):
    monkeypatch.setattr(integration, "import_module", _missing)
    pages = {"_puppet_page": QWidget(), "_pet_page": QWidget()}
    for page in pages.values():
        QVBoxLayout(page)
        optional_tabs.prepare_workspace(page, lambda: None)
    built = []
    owner = SimpleNamespace(
        **pages, puppet_workspace=None, pet_workspace="already built",
        _build_puppet_workspace=lambda: built.append("puppet"),
        _build_pet_workspace=lambda: built.append("pet"),
    )
    try:
        MainWindowLayoutMixin._on_rigora_installed(owner)
        assert built == ["puppet"]
        for page in pages.values():
            assert page.findChildren(QWidget, "rigoraMissingPanel") == []
    finally:
        for page in pages.values():
            page.deleteLater()


def test_after_install_a_turned_off_tab_is_skipped():
    owner = SimpleNamespace(
        _puppet_page=None, _pet_page=None, puppet_workspace=None, pet_workspace=None,
        _build_puppet_workspace=lambda: pytest.fail("tab is off"),
        _build_pet_workspace=lambda: pytest.fail("tab is off"),
    )
    MainWindowLayoutMixin._on_rigora_installed(owner)
