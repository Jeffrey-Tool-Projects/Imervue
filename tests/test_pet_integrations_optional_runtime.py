"""The plugin remains discoverable without the optional character runtime."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest

from pet_integrations import pet_integrations_plugin as plugin


def test_missing_runtime_keeps_plugin_discovery_and_menu_available():
    script = """
import importlib.abc
import sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, str(Path.cwd() / 'plugins'))
class RejectRigora(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'rigora' or fullname.startswith('rigora.'):
            raise ModuleNotFoundError('Rigora is absent', name='rigora')
sys.meta_path.insert(0, RejectRigora())
from PySide6.QtWidgets import QApplication, QMenu
import pet_integrations
app = QApplication([])
instance = pet_integrations.plugin_class(SimpleNamespace(viewer=None))
menu = QMenu()
instance.on_build_menu_bar(menu)
entries = menu.actions()[0].menu().actions()
assert len(entries) == 1
assert not entries[0].isEnabled()
assert 'Rigora' in entries[0].text()
assert not any(name == 'rigora' or name.startswith('rigora.') for name in sys.modules)
instance.on_plugin_unloaded()
"""
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1], env=env,
        capture_output=True, text=True, timeout=30, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_broken_installed_runtime_is_not_reported_as_absent(monkeypatch):
    monkeypatch.setattr(plugin, "INTEGRATIONS", None)

    def broken(_name):
        raise ModuleNotFoundError("missing dependency", name="some_dependency")

    monkeypatch.setattr(plugin, "import_module", broken)
    with pytest.raises(ModuleNotFoundError, match="missing dependency"):
        plugin.integration_definitions()
