"""Frozen probe: press Install Rigora in a packaged build and build the tabs it unlocks."""
import json
import os
import sys
import tempfile
import time
import traceback

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_state = tempfile.mkdtemp(prefix="rigora-probe-")
os.environ["RIGORA_SETTINGS_PATH"] = os.path.join(_state, "rigora.json")
os.environ["RIGORA_DATA_DIR"] = os.path.join(_state, "data")

result = {}


def pump(app, predicate, timeout):
    end = time.monotonic() + timeout
    while not predicate() and time.monotonic() < end:
        app.processEvents()
        time.sleep(0.02)
    return predicate()


def main():
    from PySide6.QtWidgets import QApplication, QPushButton, QVBoxLayout, QWidget
    app = QApplication([])
    from Imervue.system.app_paths import frozen_site_packages, is_frozen
    from Imervue.gui import optional_tabs
    from Imervue.gui.main_window_layout import MainWindowLayoutMixin
    from Imervue.plugin.pip_install_dialog import InstallDependenciesDialog
    from Imervue.system.rigora_integration import rigora_available
    import PySide6

    result["frozen"] = is_frozen()
    result["site_packages"] = str(frozen_site_packages())
    result["rigora_before"] = rigora_available()
    page = QWidget()
    QVBoxLayout(page)
    installed = []
    owner = type("Owner", (), {})()
    owner._puppet_page, owner._pet_page = page, None
    owner.puppet_workspace = owner.pet_workspace = None
    owner._build_puppet_workspace = lambda: MainWindowLayoutMixin._build_puppet_workspace(owner)
    owner._build_pet_workspace = lambda: None
    owner._on_rigora_installed = lambda: (installed.append(True),
                                          MainWindowLayoutMixin._on_rigora_installed(owner))
    result["notice_shown"] = not optional_tabs.prepare_workspace(page, owner._on_rigora_installed)
    page.findChild(QPushButton, "rigoraInstallButton").click()
    dialogs = [w for w in app.topLevelWidgets() if isinstance(w, InstallDependenciesDialog)]
    result["dialog_opened"] = len(dialogs) == 1
    dialog = dialogs[0]
    log = []
    dialog._log.textChanged.connect(lambda: log.append(dialog._log.toPlainText()))
    dialog._install_btn.click()
    result["installed_in_time"] = pump(app, lambda: installed, 900)
    result["install_log_tail"] = (log[-1] if log else "")[-1500:]
    result["rigora_after"] = rigora_available()
    import rigora
    result["rigora_file"] = rigora.__file__
    target = str(frozen_site_packages())
    result["rigora_in_site_packages"] = rigora.__file__.startswith(target)
    result["pyside_file"] = PySide6.__file__
    result["pyside_from_bundle"] = not PySide6.__file__.startswith(target)
    result["second_pyside_installed"] = os.path.isdir(os.path.join(target, "PySide6"))
    result["puppet_workspace_built"] = type(owner.puppet_workspace).__name__
    result["notice_removed"] = page.findChild(QPushButton, "rigoraInstallButton") is None or \
        not page.findChild(QPushButton, "rigoraInstallButton").isVisibleTo(page)
    from rigora.desktop_pet import PetWorkspace
    result["pet_workspace_built"] = type(PetWorkspace()).__name__
    from rigora.system.app_paths import examples_dir
    imeru = os.path.join(str(examples_dir()), "puppet", "imeru.puppet")
    result["imeru_example"] = os.path.isfile(imeru)


try:
    main()
    result["ok"] = True
except BaseException:  # noqa: BLE001 - the probe reports every failure as JSON
    result["ok"] = False
    result["error"] = traceback.format_exc()
print(json.dumps(result, indent=1))
sys.stdout.flush()
os._exit(0)
