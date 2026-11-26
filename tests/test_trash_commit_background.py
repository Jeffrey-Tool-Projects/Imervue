"""File > commit pending deletions sends them to the Recycle Bin on a worker thread."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from PySide6.QtCore import QObject, Signal

from Imervue.gpu_image_view.actions import delete
from Imervue.gui import trash_failure_notice as notice
from Imervue.system import trash_ops


class _FakeDeleteWorker(QObject):
    """Stands in for FileDeleteWorker: no thread, no real Recycle Bin."""

    finished_with = Signal(list, list)
    created: list = []

    def __init__(self, paths, parent=None):
        super().__init__()
        self.paths = list(paths)
        self.started = False
        self.waited = False
        _FakeDeleteWorker.created.append(self)

    def start(self):
        self.started = True

    def wait(self):
        self.waited = True
        return True


def _action(*paths, mode="delete"):
    return {"mode": mode, "deleted_paths": list(paths), "indices": [0] * len(paths),
            "restored": False}


@pytest.fixture
def window(monkeypatch):
    _FakeDeleteWorker.created = []
    offered = []
    monkeypatch.setattr(trash_ops, "FileDeleteWorker", _FakeDeleteWorker)
    monkeypatch.setattr(notice, "offer_permanent_delete",
                        lambda _parent, paths: offered.append(list(paths)) or [])
    win = SimpleNamespace(viewer=SimpleNamespace(undo_stack=[]), offered=offered)
    return win


def test_nothing_pending_starts_no_worker(qapp, window):
    window.viewer.undo_stack.append({"mode": "rotate"})
    assert notice.commit_pending_in_background(window) is None
    assert _FakeDeleteWorker.created == []


def test_commit_starts_a_worker_and_returns_at_once(qapp, window):
    window.viewer.undo_stack[:] = [_action("/p/a.png", "/p/b.png"),
                                   _action("/p/c", mode="delete_external")]
    worker = notice.commit_pending_in_background(window)
    assert worker.started
    assert worker.paths == ["/p/a.png", "/p/b.png", "/p/c"]
    # Still listed while the worker runs, so a rescan does not resurrect them.
    assert delete.pending_deleted_paths(window.viewer.undo_stack) == {"/p/a.png", "/p/b.png", "/p/c"}


def test_second_commit_while_one_runs_is_ignored(qapp, window):
    window.viewer.undo_stack.append(_action("/p/a.png"))
    assert notice.commit_pending_in_background(window) is not None
    assert notice.commit_pending_in_background(window) is None
    assert len(_FakeDeleteWorker.created) == 1


def test_finish_drops_only_the_committed_actions(qapp, window):
    rotate = {"mode": "rotate"}
    window.viewer.undo_stack[:] = [_action("/p/a.png"), rotate]
    worker = notice.commit_pending_in_background(window)
    later = _action("/p/later.png")
    window.viewer.undo_stack.append(later)        # deleted while the worker ran
    worker.finished_with.emit(["/p/a.png"], [])
    assert window.viewer.undo_stack == [rotate, later]
    assert window._pending_commit_worker is None
    assert window.offered == [[]]


def test_paths_the_bin_refused_are_offered_for_permanent_delete(qapp, window):
    window.viewer.undo_stack.append(_action("/usb/a.png", "/p/b.png"))
    worker = notice.commit_pending_in_background(window)
    worker.finished_with.emit(["/p/b.png"], ["/usb/a.png"])
    assert window.offered == [["/usb/a.png"]]


def test_undo_leaves_a_committing_delete_alone(qapp):
    viewer = SimpleNamespace(undo_stack=[dict(_action("/p/a.png"), committing=True)],
                             model=SimpleNamespace(images=[]))
    delete.undo_delete(viewer)
    assert len(viewer.undo_stack) == 1
    assert viewer.model.images == []


def test_closing_mid_commit_waits_and_settles_it(qapp, window):
    window.viewer.undo_stack.append(_action("/p/a.png"))
    worker = notice.commit_pending_in_background(window)
    worker.commit_result = (["/p/a.png"], [])     # what the worker thread recorded
    notice.finish_pending_commit(window)
    assert worker.waited
    assert window.viewer.undo_stack == []
    # The queued slot arriving later finds nothing left to do.
    worker.finished_with.emit(["/p/a.png"], [])
    assert window.offered == [[]]


def test_closing_with_no_commit_running_is_a_no_op(qapp, window):
    notice.finish_pending_commit(window)
    assert _FakeDeleteWorker.created == []
