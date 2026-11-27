"""Watched folder, refresh and folder sessions of the main window.

Polling the open folder for changes (``system/folder_poll.py``: nothing holds
it open, so Windows can still rename or move the folders above it), refreshing
the image list and the folder tree while keeping
the deep-zoom image in place, recovering when the folder disappears, and
saving / restoring each folder's session (view mode, current image).
``ImervueMainWindow`` mixes these methods in.
"""
from __future__ import annotations

import contextlib
import logging
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, Signal

from Imervue.system.qt_timers import call_later
from Imervue.image.browser_state import detect_renamed_paths, filter_paths, migrate_view_path_state
from Imervue.system.file_transfer import follow_saved_data
from Imervue.multi_language.language_wrapper import language_wrapper
from Imervue.user_settings.user_setting_dict import schedule_save, user_setting_dict


# Poll interval while waiting for the async folder scan to surface the image a
# startup deep-zoom restore is targeting (bounded by the retry count).
_DEEP_ZOOM_RESTORE_RETRY_MS = 50

logger = logging.getLogger("Imervue.folders")


class _FolderRescanSignals(QObject):
    done = Signal(str, object, int)   # folder, sorted paths or None, generation


class FolderRescanWorker(QRunnable):
    """List and sort the open folder off the GUI thread after it changed on disk.

    A header sort (resolution, date taken) opens every file, and even a name
    sort lists a large folder for a noticeable time, so neither may run in the
    timer slot that the folder poll fires after a delete.
    """

    def __init__(self, folder: str, generation: int, sort_by: str, ascending: bool):
        super().__init__()
        self.folder = folder
        self.generation = generation
        self.sort_by = sort_by
        self.ascending = ascending
        self.signals = _FolderRescanSignals()

    def run(self) -> None:
        from Imervue.gpu_image_view.images.image_loader_scan import _scan_images
        images = None
        try:
            images = _scan_images(self.folder, sort_by=self.sort_by, ascending=self.ascending)
        except Exception:  # a worker must always report; None keeps the shown list
            logger.exception("Rescanning %s failed", self.folder)
        self.signals.done.emit(self.folder, images, self.generation)


class _StatPrimeSignals(QObject):
    done = Signal(object)   # list[ImageMeta]


class MetadataPrimeWorker(QRunnable):
    """Stat a folder's first images off the GUI thread for the metadata index.

    The index keeps sizes and times for rename matching and the size/date
    filters; up to 512 stats ran on the GUI thread on every folder click and
    scan update, which a network share turns into a visible stall.
    """

    def __init__(self, paths: list[str]):
        super().__init__()
        self.paths = paths
        self.signals = _StatPrimeSignals()

    def run(self) -> None:
        from Imervue.image.browser_state_index import ImageMetadataIndex
        metas = []
        try:
            metas = ImageMetadataIndex.read_stats(self.paths)
        except Exception:  # a worker must always report
            logger.exception("Reading file stats failed")
        self.signals.done.emit(metas)


class MainWindowFoldersMixin:
    """Watched folder, refresh and folder sessions of the main window."""

    def watch_folder(self, folder: str):
        """Poll *folder* for changes and refresh the grid when it changes; ``""`` stops."""
        self._folder_watcher.watch(folder)

    def _on_application_state_changed(self, state) -> None:
        """Back in front: catch up with changes made in other programs meanwhile."""
        if state != Qt.ApplicationState.ApplicationActive:
            return
        self._folder_watcher.poll()
        self.tree.refresh()

    def _on_watched_folder_changed(self, _path: str):
        """Coalesce folder-change bursts into one stable refresh."""
        self._folder_change_events += 1
        self._folder_change_last_path = _path
        self._folder_refresh_timer.start(1200 if self._folder_change_events >= 8 else 500)

    def _do_folder_refresh(self):
        """去抖動後在背景重新掃描資料夾，結果回到 GUI 執行緒再更新 tile grid"""
        self._folder_change_events = 0
        folder = self._current_view_folder()
        if not folder:
            return
        if not Path(folder).is_dir():
            self._handle_active_folder_missing(folder)
            return
        self._folder_rescan_generation = getattr(self, "_folder_rescan_generation", 0) + 1
        worker = FolderRescanWorker(folder, self._folder_rescan_generation,
                                    user_setting_dict.get("sort_by", "name"),
                                    user_setting_dict.get("sort_ascending", True))
        worker.signals.done.connect(self._apply_folder_rescan,
                                    Qt.ConnectionType.QueuedConnection)
        self._folder_rescan_worker = worker
        QThreadPool.globalInstance().start(worker)

    def _apply_folder_rescan(self, folder: str, scanned: list | None, generation: int) -> None:
        """Bring the grid up to date with a finished rescan, if it still applies."""
        if generation != getattr(self, "_folder_rescan_generation", None):
            return
        self._folder_rescan_worker = None
        if scanned is None or folder != self._current_view_folder():
            return
        from Imervue.gpu_image_view.actions.delete import pending_deleted_paths
        viewer = self.viewer
        # Soft-deleted files stay on disk until the shutdown commit, while the
        # stored list already leaves them out: compare without them, or every
        # change in the folder looks like a new listing and rebuilds everything.
        pending = pending_deleted_paths(getattr(viewer, "undo_stack", []))
        new_images = [p for p in scanned if p not in pending] if pending else list(scanned)
        current_full = list(getattr(viewer, "_unfiltered_images", None) or viewer.model.images)
        if new_images == current_full:
            return
        appeared = not set(new_images) <= set(current_full)
        self._apply_refreshed_image_list(new_images)
        if appeared:
            # The tree's own model drops removed rows by itself; re-reading it
            # from disk is only needed for files it has not seen yet.
            self.tree.refresh()

    def _prime_metadata(self, paths, limit: int = 512) -> None:
        """Have the metadata index learn the first *limit* of *paths*, off the GUI thread."""
        index = self._image_metadata_index
        todo = index.unprimed(paths, limit=limit)
        if not todo:
            return
        worker = MetadataPrimeWorker(todo)
        worker.signals.done.connect(self._absorb_metadata, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(worker)

    def _absorb_metadata(self, metas) -> None:
        self._image_metadata_index.absorb_stats(metas)

    def _current_view_folder(self) -> str:
        """Folder backing the current viewer state, if any."""
        images = self.viewer.model.images
        if images:
            return str(Path(images[0]).parent)
        dirs = self._folder_watcher.directories()
        return dirs[0] if dirs else ""

    def _save_current_folder_session(self) -> None:
        folder = self._current_view_folder()
        if not folder:
            return
        viewer = self.viewer
        scroll = 0
        if self._browse_mode == "list" and hasattr(self, "image_list_view"):
            with contextlib.suppress(RuntimeError):   # list view already deleted
                scroll = self.image_list_view.verticalScrollBar().value()
        elif hasattr(viewer, "scroll_y"):
            scroll = int(getattr(viewer, "scroll_y", 0))
        self._folder_view_sessions[folder] = {
            "filter": self._filter_state(),
            "browse_mode": self._browse_mode,
            "scroll": scroll,
            "selected": list(getattr(viewer, "selected_tiles", set())),
            "current": viewer._current_path() if hasattr(viewer, "_current_path") else "",
            "deep_zoom": bool(
                getattr(viewer, "deep_zoom", None) is not None
                and not getattr(viewer, "tile_grid_mode", False)
            ),
        }
        user_setting_dict["folder_view_sessions"] = self._folder_view_sessions
        # Debounced: every folder click lands here, and a synchronous JSON
        # write of the whole settings file each time stalled the click. The
        # close path flushes it (``_persist_for_close``).
        schedule_save()

    def _restore_folder_session(self, folder: str) -> None:
        state = self._folder_view_sessions.get(folder) or {}
        self._restore_filter_state(state.get("filter") or {})
        selected = set(state.get("selected") or [])
        if isinstance(getattr(self.viewer, "selected_tiles", None), set):
            self.viewer.selected_tiles.clear()
            self.viewer.selected_tiles.update(
                path for path in selected if path in self.viewer.model.images
            )
        current = state.get("current") or ""
        if current in self.viewer.model.images:
            self.viewer.current_index = self.viewer.model.images.index(current)
        self._apply_image_filter()
        if state.get("browse_mode") in {"grid", "list"}:
            self.set_browse_mode(state["browse_mode"])
        scroll = int(state.get("scroll") or 0)
        if self._browse_mode == "list" and hasattr(self, "image_list_view"):
            call_later(0, self, lambda: self.image_list_view.verticalScrollBar().setValue(scroll))
        elif hasattr(self.viewer, "scroll_y"):
            self.viewer.scroll_y = scroll

    def _restore_deep_zoom_if_saved(self, state: dict, _retries: int = 60) -> None:
        """Re-enter deep zoom on the remembered image after a startup restore.

        The folder scan fills ``model.images`` asynchronously, so the target
        may not exist yet on the first pass; retry (bounded) until it lands,
        then open it in deep zoom. Running after the scan also means the window
        has reached its restored size, so the fit is correct. Startup-only (not
        folder navigation), so browsing the tree still lands on the tile wall.
        """
        from Imervue.sessions.folder_session import (
            deep_zoom_restore_target,
            should_retry_deep_zoom_restore,
        )
        viewer = self.viewer
        target = deep_zoom_restore_target(state, viewer.model.images)
        if target is not None:
            viewer.current_index = viewer.model.images.index(target)
            viewer.tile_grid_mode = False
            viewer.load_deep_zoom_image(target)
            return
        if _retries > 0 and should_retry_deep_zoom_restore(state, viewer.model.images):
            call_later(
                _DEEP_ZOOM_RESTORE_RETRY_MS, self,
                lambda: self._restore_deep_zoom_if_saved(state, _retries - 1),
            )

    def _handle_active_folder_missing(self, folder: str) -> None:
        """Reset viewer chrome when the folder currently being browsed is gone."""
        viewer = self.viewer
        viewer._unfiltered_images = []
        viewer.load_tile_grid_async([])
        viewer.current_index = 0
        if self._browse_mode == "list":
            self.refresh_list_view()
            self._view_stack.setCurrentIndex(1)
        else:
            self._view_stack.setCurrentIndex(0)

        parent = self._nearest_existing_parent(Path(folder))
        if parent:
            self.tree.set_root_path(parent)
            self._clear_view_folder_watch()
            self.breadcrumb.set_path(parent)
        else:
            self.watch_folder("")

        lang = language_wrapper.language_word_dict
        self.filename_label.setText(
            lang.get(
                "main_window_folder_missing",
                "Folder no longer exists: {path}",
            ).format(path=folder),
        )
        if hasattr(self, "toast"):
            self.toast.warning(
                lang.get(
                    "folder_removed",
                    "Folder was removed: {name}",
                ).format(name=Path(folder).name or folder),
            )

    def _clear_view_folder_watch(self) -> None:
        """Stop the viewer folder watcher without changing the file-tree root."""
        watcher = getattr(self, "_folder_watcher", None)
        if watcher is not None:
            watcher.watch("")

    @staticmethod
    def _nearest_existing_parent(path: Path) -> str:
        """Return the nearest existing parent folder for a removed path."""
        for candidate in (path.parent, *path.parents):
            if candidate and candidate.is_dir():
                return str(candidate)
        return ""

    def _apply_refreshed_image_list(self, new_images: list[str]) -> None:
        """Update tile/list/deep-zoom state after an external folder change."""
        from Imervue.gpu_image_view.actions.delete import pending_deleted_paths
        viewer = self.viewer
        # A fresh disk scan re-includes soft-deleted files (unlinked only at
        # shutdown); drop them so a watch-folder refresh or folder revisit can't
        # resurrect them.
        pending = pending_deleted_paths(getattr(viewer, "undo_stack", []))
        if pending:
            new_images = [p for p in new_images if p not in pending]
        old_images = list(viewer.model.images)
        old_full = list(getattr(viewer, "_unfiltered_images", None) or old_images)
        rename_map = detect_renamed_paths(old_full, new_images, self._image_metadata_index)
        if rename_map:
            migrate_view_path_state(viewer, rename_map)
            for old, new in rename_map.items():
                self._image_metadata_index.move(old, new)
            # A rename made outside Imervue: the rating, tags and library notes
            # follow. keep_existing, because Imervue's own renames show up here
            # too, after carry_along already moved everything (and the new path
            # may carry data of its own).
            follow_saved_data(rename_map, keep_existing=True)
        old_index = viewer.current_index
        # A deep-zoom load in flight (`_deep_zoom_loading`) has `deep_zoom` still
        # None, but the user is already committed to that image — treat it as an
        # active deep-zoom session so a refresh that reorders or drops the image
        # keeps them in deep zoom instead of stranding a "Loading…" view that the
        # completion guard then discards.
        loading_path = getattr(viewer, "_deep_zoom_loading", None)
        current_path = loading_path or (
            old_images[old_index]
            if 0 <= old_index < len(old_images) else None
        )
        current_path = rename_map.get(current_path, current_path)

        if not new_images:
            viewer._unfiltered_images = []
            self._update_filter_results([], [])
            viewer.load_tile_grid_async([])
            viewer.current_index = 0
            if self._browse_mode == "list":
                self.refresh_list_view()
            return

        viewer._unfiltered_images = list(new_images)
        self._prime_metadata(new_images)
        self._refresh_tag_filter_options()
        filtered_images = filter_paths(
            new_images,
            self._current_filter_spec(),
            self._image_metadata_index,
        )
        self._update_filter_results(new_images, filtered_images)

        if viewer.tile_grid_mode:
            from Imervue.gpu_image_view.tile_loader import sync_tile_grid_incremental
            sync_tile_grid_incremental(viewer, filtered_images)
            return

        self._reconcile_deep_zoom_onto_list(filtered_images, current_path, old_index)

    def _reconcile_deep_zoom_onto_list(self, filtered: list[str],
                                       current: str | None, old_index: int) -> None:
        """Settle the viewer onto *filtered*, keeping or reopening the deep-zoom
        image. Shared by the folder-refresh and the filter paths so the deep-zoom
        reconciliation can't drift between them. Callers handle the tile-grid and
        wholly-empty-folder cases before delegating here.

        ``current`` is the path that should stay shown (the loading target when a
        load is in flight, else the displayed image).
        """
        viewer = self.viewer
        viewer.model.set_images(filtered)
        active_deep_zoom = (
            viewer.deep_zoom is not None
            or bool(getattr(viewer, "_deep_zoom_loading", None))
        )
        if current in filtered:
            viewer.current_index = filtered.index(current)
            self.refresh_list_view()
            # Same image, but the list length may have crossed the filmstrip
            # threshold (1 <-> many), changing the reserved bottom band the fit
            # letterboxes above. Re-fit so it doesn't stay the wrong size with the
            # strip overlapping it. A no-op once the fit is correct or the user
            # has taken zoom/pan control.
            if active_deep_zoom:
                viewer._schedule_settle_refit()
            viewer.update()
            return

        if active_deep_zoom and filtered:
            # The shown image left the visible list — reopen a neighbour so the
            # viewer never keeps rendering a filtered-out / removed picture.
            viewer.current_index = min(old_index, len(filtered) - 1)
            viewer._clear_deep_zoom()
            viewer.tile_grid_mode = False
            viewer.load_deep_zoom_image(filtered[viewer.current_index])
            return

        if active_deep_zoom:
            # Nothing left to show — drop the orphaned deep-zoom image and fall
            # back to the (empty) wall instead of freezing on a phantom.
            viewer._clear_deep_zoom()
            viewer.tile_grid_mode = True

        viewer.current_index = (
            min(old_index, len(filtered) - 1) if filtered else 0
        )
        self.refresh_list_view()
        viewer.update()
