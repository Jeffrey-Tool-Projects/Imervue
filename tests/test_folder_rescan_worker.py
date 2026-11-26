"""The folder poll's rescan runs off the GUI thread and rebuilds only what changed."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThreadPool

from Imervue.gui import main_window_folders
from Imervue.gui.main_window_folders import FolderRescanWorker
from tests.test_main_window_folder_refresh import _StubMainWindow


class _CountingTree:
    def __init__(self):
        self.refreshes = 0

    def refresh(self):
        self.refreshes += 1


class _RescanWindow(_StubMainWindow):
    _do_folder_refresh = main_window_folders.MainWindowFoldersMixin._do_folder_refresh
    _apply_folder_rescan = main_window_folders.MainWindowFoldersMixin._apply_folder_rescan
    _current_view_folder = main_window_folders.MainWindowFoldersMixin._current_view_folder

    def __init__(self, images):
        super().__init__(images)
        self.viewer.tile_grid_mode = False
        self.tree = _CountingTree()
        self._folder_change_events = 3
        self._folder_watcher.directories = lambda: []


def _folder_with(tmp_path: Path, *names: str) -> list[str]:
    for name in names:
        (tmp_path / name).write_bytes(b"x")
    return [str(tmp_path / name) for name in names]


def test_worker_lists_and_sorts_the_folder(qapp, tmp_path):
    expected = _folder_with(tmp_path, "b.png", "a.png", "c.jpg")
    results = []
    worker = FolderRescanWorker(str(tmp_path), 7, "name", True)
    worker.setAutoDelete(False)
    worker.signals.done.connect(lambda *args: results.append(args))
    worker.run()
    assert results == [(str(tmp_path), sorted(expected), 7)]


def test_worker_that_fails_reports_none(qapp, tmp_path, monkeypatch):
    from Imervue.gpu_image_view.images import image_loader_scan

    def broken(*_args, **_kwargs):
        raise RuntimeError("sort key exploded")

    monkeypatch.setattr(image_loader_scan, "_scan_images", broken)
    results = []
    worker = FolderRescanWorker(str(tmp_path), 1, "name", True)
    worker.setAutoDelete(False)
    worker.signals.done.connect(lambda *args: results.append(args))
    worker.run()
    assert results == [(str(tmp_path), None, 1)]


def test_refresh_runs_the_scan_on_the_thread_pool(qapp, tmp_path, monkeypatch):
    started = []
    images = _folder_with(tmp_path, "a.png")
    win = _RescanWindow(images)
    monkeypatch.setattr(QThreadPool.globalInstance(), "start", started.append)
    win._do_folder_refresh()
    [worker] = started
    assert isinstance(worker, FolderRescanWorker)
    assert worker.folder == str(tmp_path)
    assert win._folder_change_events == 0


def test_a_removed_file_updates_the_list_without_rereading_the_tree(qapp, tmp_path):
    a, b = _folder_with(tmp_path, "a.png", "b.png")
    win = _RescanWindow([a, b])
    win._folder_rescan_generation = 4
    win._apply_folder_rescan(str(tmp_path), [a], 4)
    assert win.viewer._unfiltered_images == [a]
    assert win.tree.refreshes == 0


def test_a_new_file_also_rereads_the_tree(qapp, tmp_path):
    a, b = _folder_with(tmp_path, "a.png", "b.png")
    win = _RescanWindow([a])
    win._folder_rescan_generation = 1
    win._apply_folder_rescan(str(tmp_path), [a, b], 1)
    assert win.viewer._unfiltered_images == [a, b]
    assert win.tree.refreshes == 1


def test_pending_soft_deletes_do_not_count_as_a_change(qapp, tmp_path):
    # The file is still on disk; the stored list already leaves it out.
    a, b = _folder_with(tmp_path, "a.png", "b.png")
    win = _RescanWindow([a])
    win.viewer.undo_stack.append({"mode": "delete", "deleted_paths": [b],
                                  "indices": [1], "restored": False})
    win._folder_rescan_generation = 1
    win._apply_folder_rescan(str(tmp_path), [a, b], 1)
    assert win.viewer.loaded_deep_zoom == []
    assert win.tree.refreshes == 0


def test_a_superseded_or_failed_scan_changes_nothing(qapp, tmp_path):
    a, b = _folder_with(tmp_path, "a.png", "b.png")
    win = _RescanWindow([a, b])
    win._folder_rescan_generation = 2
    win._apply_folder_rescan(str(tmp_path), [a], 1)
    win._apply_folder_rescan(str(tmp_path), None, 2)
    win._apply_folder_rescan(str(tmp_path / "elsewhere"), [a], 2)
    assert win.viewer._unfiltered_images == [a, b]
    assert win.tree.refreshes == 0
