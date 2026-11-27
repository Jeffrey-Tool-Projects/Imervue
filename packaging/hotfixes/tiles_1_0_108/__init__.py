"""Progress timer hotfix for the published Imervue 1.0.108 Windows executable."""
import hashlib
import logging

from PySide6.QtCore import QTimer

from Imervue.plugin.plugin_base import ImervuePlugin
from Imervue.system.app_paths import app_dir


class TilesProgressFix(ImervuePlugin):
    plugin_name = "Tiles progress fix for 1.0.108"
    plugin_version = "1.0.0"
    plugin_description = "Use a viewer-owned timer when thumbnails arrive."

    def on_plugin_loaded(self):
        exe = app_dir() / "Imervue.exe"
        if not exe.is_file() or exe.stat().st_size != 75383808:
            return
        with exe.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if digest != "134516a700f81565727d2f52c503b31d5578a7dc247745a92b41ddf362eab455":
            return

        self._progress = self.viewer._progress_coalescer
        self._timer = QTimer(self._progress)
        self._timer.setSingleShot(True)
        self._timer.setInterval(self._progress._interval_ms)
        self._timer.timeout.connect(self._progress._flush)
        self._progress.schedule = self._schedule
        self._progress.force_flush = self._force_flush
        logging.getLogger("Imervue.tiles").info("1.0.108 thumbnail progress timer fix active")

    def _schedule(self):
        if not self._progress._pending:
            self._progress._pending = True
            self._timer.start()

    def _force_flush(self):
        self._timer.stop()
        self._progress._flush()

    def on_plugin_unloaded(self):
        if hasattr(self, "_timer"):
            self._force_flush()
            del self._progress.schedule, self._progress.force_flush
            self._timer.deleteLater()


plugin_class = TilesProgressFix
