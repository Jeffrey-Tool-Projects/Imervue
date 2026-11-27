"""Tests for the sub-frame signal coalescer.

The coalescer needs Qt's event loop to deliver the timer callback,
so all tests pump ``qapp.processEvents`` after ``schedule()`` to
let the timer fire.
"""
from __future__ import annotations

import time

import pytest
import shiboken6
from PySide6.QtCore import QObject, QTimer

from Imervue.gpu_image_view.signal_coalescer import (
    DEFAULT_INTERVAL_MS,
    SignalCoalescer,
)


def _wait(qapp, predicate, timeout_s: float = 1.0) -> bool:
    """Pump the Qt event loop until ``predicate`` is true or the
    timeout elapses. The coalescer fires via a QTimer which
    only delivers when the loop is processed."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        qapp.processEvents()
        if predicate():
            return True
        time.sleep(0.005)
    qapp.processEvents()
    return predicate()


def test_starts_not_pending(qapp):
    c = SignalCoalescer()
    try:
        assert c.is_pending() is False
    finally:
        c.deleteLater()


def test_first_schedule_arms_pending(qapp):
    c = SignalCoalescer(interval_ms=100)
    try:
        c.schedule()
        assert c.is_pending() is True
    finally:
        c.deleteLater()


def test_n_schedule_calls_produce_one_emit(qapp):
    """The whole point: bursts of schedule() within one window
    collapse into a single flush_requested signal."""
    fired: list[int] = []
    c = SignalCoalescer(interval_ms=10)
    c.flush_requested.connect(lambda: fired.append(1))
    try:
        for _ in range(100):
            c.schedule()
        assert _wait(qapp, lambda: bool(fired))
        assert fired == [1]
    finally:
        c.deleteLater()


def test_after_flush_can_schedule_again(qapp):
    """The coalescer must reset its pending state after each flush
    so the next burst gets its own emit."""
    fired: list[int] = []
    c = SignalCoalescer(interval_ms=5)
    c.flush_requested.connect(lambda: fired.append(1))
    try:
        c.schedule()
        assert _wait(qapp, lambda: len(fired) >= 1)
        assert c.is_pending() is False
        c.schedule()
        assert _wait(qapp, lambda: len(fired) >= 2)
        assert fired == [1, 1]
    finally:
        c.deleteLater()


def test_force_flush_runs_immediately(qapp):
    """End-of-burst case: caller knows the last item arrived
    and wants the user to see the final state without waiting
    for the timer window."""
    fired: list[int] = []
    c = SignalCoalescer(interval_ms=10_000)   # huge window
    c.flush_requested.connect(lambda: fired.append(1))
    try:
        c.schedule()
        c.force_flush()
        assert fired == [1]
        assert c.is_pending() is False
    finally:
        c.deleteLater()


def test_force_flush_when_not_pending_is_noop(qapp):
    """Force-flushing without a pending schedule mustn't emit
    duplicate signals — that would re-do the expensive GUI
    update for no reason."""
    fired: list[int] = []
    c = SignalCoalescer()
    c.flush_requested.connect(lambda: fired.append(1))
    try:
        c.force_flush()
        assert fired == []
    finally:
        c.deleteLater()


def test_force_flush_then_reschedule_gives_the_new_burst_its_own_window(qapp):
    c = SignalCoalescer(interval_ms=100)
    fired = []
    c.flush_requested.connect(lambda: fired.append(1))
    try:
        c.schedule()
        time.sleep(0.15)  # the first timeout is due, but has not been dispatched
        c.force_flush()
        c.schedule()
        qapp.processEvents()
        assert fired == [1]
        assert c.is_pending()
        assert _wait(qapp, lambda: len(fired) == 2)
    finally:
        c.deleteLater()


def test_owner_reuses_one_timer_and_destroys_it_with_a_flush_pending(qapp, monkeypatch):
    monkeypatch.setattr(QTimer, "singleShot", lambda *_args: pytest.fail("static singleShot"))
    owner = QObject()
    c = SignalCoalescer(interval_ms=10, parent=owner)
    timer = c.findChild(QTimer)
    assert timer is not None
    fired = []
    c.flush_requested.connect(lambda: fired.append(1))
    c.schedule()
    assert _wait(qapp, lambda: bool(fired))
    c.schedule()
    assert c.findChildren(QTimer) == [timer]
    shiboken6.delete(owner)
    assert not shiboken6.isValid(timer)
    assert not _wait(qapp, lambda: len(fired) > 1, timeout_s=0.05)


def test_timer_after_force_flush_does_not_double_emit(qapp):
    """A forced flush must cancel the timer's scheduled delivery."""
    fired: list[int] = []
    c = SignalCoalescer(interval_ms=5)
    c.flush_requested.connect(lambda: fired.append(1))
    try:
        c.schedule()
        c.force_flush()
        assert fired == [1]
        # Wait long enough for the queued timer to fire.
        deadline = time.monotonic() + 0.1
        while time.monotonic() < deadline:
            qapp.processEvents()
            time.sleep(0.005)
        assert fired == [1]   # still one — no duplicate from the late timer
    finally:
        c.deleteLater()


def test_interval_zero_clamps_to_minimum(qapp):
    """An interval of 0 would mean 'fire immediately', losing the
    coalescing benefit. Clamp to 1 ms so the contract holds
    (bursts still collapse to one emit per loop iteration)."""
    c = SignalCoalescer(interval_ms=0)
    try:
        assert c.findChild(QTimer).interval() == 1
    finally:
        c.deleteLater()


def test_negative_interval_clamps_to_minimum(qapp):
    c = SignalCoalescer(interval_ms=-50)
    try:
        assert c.findChild(QTimer).interval() == 1
    finally:
        c.deleteLater()


def test_default_interval_matches_constant(qapp):
    """Sanity guard: the documented default and the module constant
    must agree."""
    c = SignalCoalescer()
    try:
        assert c.findChild(QTimer).interval() == DEFAULT_INTERVAL_MS
    finally:
        c.deleteLater()
