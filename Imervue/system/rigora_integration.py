"""Initialize the optional Rigora package without sharing Imervue's settings file."""
from __future__ import annotations

from importlib import import_module, invalidate_caches

_initialized = False

# Rigora has no PyPI release; the in-app installer builds it from the public
# repository's source archive, pinned to the commit tagged v0.1.1 so a later
# push cannot change what an install receives.
RIGORA_COMMIT = "9f1dbbe8bf43633c86136a110fb257704527ce7f"
RIGORA_ARCHIVE_URL = (
    f"https://github.com/Jeffrey-Tool-Projects/Rigora/archive/{RIGORA_COMMIT}.zip"
)
INSTALL_MESSAGE = (
    "Puppet and Desktop Pet require Rigora. Install the Rigora package in the same "
    "Python environment, or use Install Rigora in the Puppet or Desktop Pet tab, "
    "which also works in the packaged executable."
)


# Rigora needs numpy, Pillow, PySide6, PyOpenGL, imageio and imageio-ffmpeg,
# all of which Imervue itself depends on (and a packaged executable bundles).
# Letting pip resolve them anyway re-installs Qt: in a packaged build into
# lib/site-packages, which sits in front of the bundle on sys.path and would
# shadow the bundled PySide6; in a source environment over the user's own copy.
RIGORA_REQUIREMENT = f"rigora @ {RIGORA_ARCHIVE_URL}"
RIGORA_INSTALL_ARGS = ("--no-deps",)


def rigora_available() -> bool:
    """Whether ``rigora`` imports now, after the finders forget any earlier miss."""
    invalidate_caches()
    try:
        import_module("rigora")
    except ModuleNotFoundError as exc:
        if exc.name != "rigora":
            raise
        return False
    return True


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
