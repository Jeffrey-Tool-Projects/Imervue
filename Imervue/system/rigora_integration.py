"""Initialize the optional Rigora package without sharing Imervue's settings file."""
from __future__ import annotations

from importlib import import_module

_initialized = False
INSTALL_MESSAGE = (
    "Puppet and Desktop Pet require Rigora. Install the Rigora package in the same "
    "Python environment, then restart Imervue. Packaged executables require a build "
    "that includes Rigora."
)


def require_rigora() -> None:
    """Require Rigora while preserving failures from an installed package's dependencies."""
    try:
        import_module("rigora")
    except ModuleNotFoundError as exc:
        if exc.name != "rigora":
            raise
        raise RuntimeError(INSTALL_MESSAGE) from exc


def initialize_embedded_rigora() -> bool:
    """Load Rigora settings once and apply the host's active language to its widgets."""
    global _initialized
    try:
        import_module("rigora")
    except ModuleNotFoundError as exc:
        if exc.name == "rigora":
            return False
        raise
    from rigora.i18n.language_wrapper import language_wrapper as rigora_language
    from rigora.system import settings
    from Imervue.multi_language.language_wrapper import language_wrapper
    from Imervue.user_settings.user_setting_dict import user_setting_dict

    if not _initialized:
        settings.configure()
        settings.import_legacy_settings(user_setting_dict)
        _initialized = True
    from PySide6.QtCore import QCoreApplication
    if QCoreApplication.instance() is not None:
        from rigora.gui.background_jobs import set_job_registry
        from Imervue.gui.background_jobs import job_registry
        set_job_registry(job_registry())
    rigora_language.reset_language(language_wrapper.language)
    return True


def flush_rigora_settings() -> None:
    """Persist the independently owned Rigora settings after its workspaces stop."""
    if _initialized:
        from rigora.system.settings import flush
        flush()
