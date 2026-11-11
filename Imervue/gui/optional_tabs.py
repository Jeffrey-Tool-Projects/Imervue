"""The optional main-window tabs, Puppet and Desktop Pet: whether to build them, and when.

**Preferences** turns each one on or off (on by default); the choice takes effect
at the next start. A tab that is off is not added and its package is never
imported, so the viewer and the Modify tab run without it. A tab that is on
starts as an empty page and builds its workspace the first time it is opened,
like Paint; the Desktop Pet tab builds at startup instead when its pet is set
to show on launch.
"""
from __future__ import annotations

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


def prepare_workspace(page) -> bool:
    """Initialize Rigora or display one actionable notice in its optional tab."""
    if initialize_embedded_rigora():
        return True
    from PySide6.QtWidgets import QLabel
    from Imervue.system.rigora_integration import INSTALL_MESSAGE
    from Imervue.multi_language.language_wrapper import language_wrapper

    if page.findChild(QLabel, "rigoraMissingNotice") is None:
        text = language_wrapper.language_word_dict.get("rigora_missing_notice", INSTALL_MESSAGE)
        notice = QLabel(text, page)
        notice.setObjectName("rigoraMissingNotice")
        notice.setWordWrap(True)
        page.layout().addWidget(notice)
    return False
