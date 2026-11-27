"""The optional main-window tabs, Puppet and Desktop Pet: whether to build them, and when.

**Preferences** turns each one on or off (on by default); the choice takes effect
at the next start. A tab that is off is not added and its package is never
imported, so the viewer and the Modify tab run without it. A tab that is on
starts as an empty page and builds its workspace the first time it is opened,
like Paint; the Desktop Pet tab builds at startup instead when its pet is set
to show on launch.
"""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from Imervue.user_settings.user_setting_dict import user_setting_dict
from Imervue.system.rigora_integration import initialize_embedded_rigora

PUPPET_TAB = "puppet_tab_enabled"
DESKTOP_PET_TAB = "desktop_pet_tab_enabled"
OPTIONAL_TABS = (PUPPET_TAB, DESKTOP_PET_TAB)


def tab_enabled(key: str) -> bool:
    """Whether the optional tab under setting *key* is on; tabs are on unless turned off."""
    return bool(user_setting_dict.get(key, True))


def set_tab_enabled(key: str, enabled: bool) -> None:
    """Turn the optional tab under *key* on or off from the next start; the caller saves."""
    if key not in OPTIONAL_TABS:
        raise ValueError(f"not an optional tab: {key!r}")
    user_setting_dict[key] = bool(enabled)


def pet_shows_on_launch() -> bool:
    """Whether the desktop pet is set to appear at startup (its tab must then build at once)."""
    if not initialize_embedded_rigora():
        return False
    from rigora.desktop_pet import settings as pet_settings
    return bool(pet_settings.load().get("show_on_launch"))


RIGORA_NOTICE = "rigoraMissingNotice"
RIGORA_INSTALL_BUTTON = "rigoraInstallButton"
RIGORA_PANEL = "rigoraMissingPanel"


def prepare_workspace(page, on_installed: Callable[[], None]) -> bool:
    """Initialize Rigora, or show one notice with an Install Rigora button in its tab.

    *on_installed* runs on the GUI thread once the in-app install has made
    ``rigora`` importable, so the caller can build its workspaces in place.
    """
    if initialize_embedded_rigora():
        return True
    if page.findChild(QWidget, RIGORA_PANEL) is None:
        page.layout().addWidget(_install_panel(page, on_installed))
    return False


def _install_panel(page, on_installed: Callable[[], None]) -> QWidget:
    from Imervue.system.rigora_integration import INSTALL_MESSAGE
    from Imervue.multi_language.language_wrapper import language_wrapper

    lang = language_wrapper.language_word_dict
    panel = QWidget(page)
    panel.setObjectName(RIGORA_PANEL)
    layout = QVBoxLayout(panel)
    notice = QLabel(lang.get("rigora_missing_notice", INSTALL_MESSAGE), panel)
    notice.setObjectName(RIGORA_NOTICE)
    notice.setWordWrap(True)
    button = QPushButton(lang.get("rigora_install_button", "Install Rigora"), panel)
    button.setObjectName(RIGORA_INSTALL_BUTTON)
    button.clicked.connect(lambda: open_rigora_installer(page, on_installed))
    row = QHBoxLayout()
    row.addWidget(button)
    row.addStretch(1)
    layout.addWidget(notice)
    layout.addLayout(row)
    layout.addStretch(1)
    return panel


def open_rigora_installer(page, on_installed: Callable[[], None]) -> QDialog:
    """Open the dependency installer for the pinned Rigora release."""
    from Imervue.plugin.pip_install_dialog import InstallDependenciesDialog
    from Imervue.system.rigora_integration import RIGORA_INSTALL_ARGS, RIGORA_REQUIREMENT

    dialog = InstallDependenciesDialog(
        page.window(), [("rigora", RIGORA_REQUIREMENT)],
        on_success=lambda: _finish_install(on_installed),
        install_args=RIGORA_INSTALL_ARGS,
    )
    dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
    dialog.open()
    return dialog


def _finish_install(on_installed: Callable[[], None]) -> None:
    from Imervue.system.rigora_integration import rigora_available

    if not rigora_available():
        raise RuntimeError("Rigora was installed but cannot be imported")
    on_installed()


def clear_install_notice(page) -> None:
    """Take the missing-Rigora notice and its button out of *page*."""
    for panel in page.findChildren(QWidget, RIGORA_PANEL):
        panel.setParent(None)
        panel.deleteLater()
