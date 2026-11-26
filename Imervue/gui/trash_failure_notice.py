"""Ask what to do with deleted files the Recycle Bin could not take.

A file on a drive without a Recycle Bin (a memory card, USB stick or network
share), or one another program holds, stays where it is when Imervue commits
its deletions (``trash_ops.recycle_bin_holds``). Saying nothing made the
delete look lost; deleting it for good unasked is what the Recycle Bin is
there to prevent. So the user sees the files and decides.
"""
from __future__ import annotations

import logging
from collections.abc import Sequence

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox, QWidget

from Imervue.multi_language.language_wrapper import language_wrapper
from Imervue.system.trash_ops import delete_outright

logger = logging.getLogger("Imervue.trash_failure_notice")

_LISTED = 10          # paths spelled out in the message; the rest become "…"


def _ask_to_delete_permanently(parent: QWidget | None, paths: Sequence[str]) -> bool:
    """Whether the user chose to delete *paths* for good; keeping them is the default."""
    lang = language_wrapper.language_word_dict
    listing = "\n".join(paths[:_LISTED]) + ("\n…" if len(paths) > _LISTED else "")
    text = lang.get(
        "trash_left_in_place",
        "{count} deleted file(s) could not go to the Recycle Bin and are still on disk: "
        "their drive has none (a memory card, USB stick or network share), or another "
        "program is using them.\n\n{paths}\n\nDelete them permanently? This cannot be undone.",
    ).format(count=len(paths), paths=listing)
    box = QMessageBox(
        QMessageBox.Icon.Warning,
        lang.get("trash_left_in_place_title", "Not moved to the Recycle Bin"), text,
        QMessageBox.StandardButton.NoButton, parent)
    delete = box.addButton(lang.get("recycle_bin_purge", "Delete Forever"),
                           QMessageBox.ButtonRole.DestructiveRole)
    keep = box.addButton(lang.get("trash_keep_files", "Keep Them"),
                         QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(keep)
    box.exec()
    return box.clickedButton() is delete


def offer_permanent_delete(parent: QWidget | None, paths: Sequence[str]) -> list[str]:
    """List the files left in place and delete them for good if the user says so.

    Returns the paths removed (a folder with its contents, a file with its
    sidecars); nothing is asked when *paths* is empty.
    """
    paths = list(paths)
    if not paths or not _ask_to_delete_permanently(parent, paths):
        return []
    removed, failed = delete_outright(paths)
    for path in failed:
        logger.warning("Couldn't delete %s permanently either; it is still on disk", path)
    return removed


def commit_pending_in_background(window) -> object | None:
    """Send the viewer's pending deletions to the Recycle Bin without blocking the window.

    The File menu's commit used to run ``trash_batch`` in the menu slot: about
    0.27 s per shell call plus a stat per file, so a large pending set froze
    the window for seconds. The pending actions stay on the undo stack, marked
    ``committing`` so Undo leaves them alone, until the worker reports; then
    only those actions are dropped. Returns the worker, or ``None`` when
    nothing was pending or a commit is already running.
    """
    from Imervue.gpu_image_view.actions.delete import pending_delete_actions
    from Imervue.system.trash_ops import FileDeleteWorker

    viewer = window.viewer
    if getattr(window, "_pending_commit_worker", None) is not None:
        return None
    actions = pending_delete_actions(viewer.undo_stack)
    paths = list(dict.fromkeys(path for action in actions for path in action["deleted_paths"]))
    if not paths:
        return None
    for action in actions:
        action["committing"] = True
    worker = FileDeleteWorker(paths, parent=window)
    worker.commit_actions = actions
    worker.commit_result = ([], list(paths))
    # Recorded on the worker thread too, so a window closing mid-commit can
    # read the result after wait(): no event loop is left to run the slot.
    worker.finished_with.connect(
        lambda done, failed: setattr(worker, "commit_result", (done, failed)),
        Qt.ConnectionType.DirectConnection)
    worker.finished_with.connect(
        lambda done, failed: _commit_finished(window, worker, done, failed))
    window._pending_commit_worker = worker
    worker.start()
    return worker


def finish_pending_commit(window) -> None:
    """Wait for a running menu commit and settle it; the window is closing."""
    worker = getattr(window, "_pending_commit_worker", None)
    if worker is None:
        return
    worker.wait()
    _commit_finished(window, worker, *worker.commit_result)


def _commit_finished(window, worker, done: list[str], failed: list[str]) -> None:
    if getattr(window, "_pending_commit_worker", None) is not worker:
        return
    actions = worker.commit_actions
    window._pending_commit_worker = None
    worker.deleteLater()
    committed = {id(action) for action in actions}
    stack = window.viewer.undo_stack
    stack[:] = [action for action in stack if id(action) not in committed]
    logger.info("Sent %d pending deletion(s) to the Recycle Bin", len(done))
    offer_permanent_delete(window, failed)
