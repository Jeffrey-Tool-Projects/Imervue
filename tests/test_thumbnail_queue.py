"""Bounded planning reprioritizes visible work and preserves explicit requests."""
from __future__ import annotations

from Imervue.gpu_image_view.thumbnail_queue import ThumbnailQueue
from Imervue.gpu_image_view.tile_viewport import TileViewport


def _viewport(count=100_000, y=0):
    return TileViewport(count, 10, 100, 1, 90, 1000, 300, 0, y, (90, 90))


def test_normal_plan_has_no_work_objects_for_unvisited_rows_and_hover_wins():
    images = [str(i) for i in range(100_000)]
    queue = ThumbnailQueue(images, 7, limit=2)
    paths = queue.plan(_viewport(), {}, {}, set(), hover="0")
    assert paths[0] == "0"
    assert len(paths) == len(queue.requested) == 30
    assert queue.generation == 7
    assert queue.active == {}


def test_pan_replaces_unstarted_work_and_keeps_old_active_path_until_it_finishes():
    images = [str(i) for i in range(100_000)]
    queue = ThumbnailQueue(images, 1, limit=2)
    old = queue.plan(_viewport(), {}, {}, set())
    token = object()
    queue.started(old[0], token)
    new = queue.plan(_viewport(y=-500_000), {}, {}, set())
    assert all(int(path) > 49_900 for path in new)
    assert old[0] in queue.requested
    assert old[1] not in queue.requested
    assert queue.active[old[0]] is token


def test_membership_handles_replacement_delete_insert_reorder_rename_and_duplicates():
    images = ["a", "b", "a"]
    queue = ThumbnailQueue(images, 1)
    assert queue.contains(images, "a")
    images[0] = "renamed"
    assert queue.contains(images, "renamed")
    assert queue.contains(images, "a")
    images.pop()
    assert not queue.contains(images, "a")
    images.insert(0, "new")
    assert queue.contains(images, "new")
    images.reverse()
    assert queue.contains(images, "new")
    assert not queue.contains(["other"], "new")


def test_explicit_retry_and_filmstrip_bypass_cached_failed_and_offline_states():
    queue = ThumbnailQueue(["a", "b", "c"], 1)
    queue.request("c", filmstrip=True)
    queue.request("a")
    plan = queue.plan(_viewport(3), {"c": object()}, {"a": "error"}, {"b"}, wall=False)
    assert plan == ["c", "a"]
    assert queue.started("c", object()) == "filmstrip"
    assert queue.started("a", object()) == "wall"
    assert not queue.plan(_viewport(3), {}, {}, set(), wall=False)
    assert queue.completed_count({"c": object()}, {"a": "error"}, set()) == 2


def test_full_resolution_backfill_is_bounded_and_eventually_discovers_all_extents():
    images = [str(i) for i in range(100)]
    queue = ThumbnailQueue(images, 1, limit=3)
    cache = {}
    for _ in range(100):
        plan = queue.plan(_viewport(100, y=-100_000), cache, {}, set(), full_resolution=True)
        assert len(plan) <= 3
        for path in plan:
            queue.started(path, object())
            cache[path] = object()
            queue.active.pop(path)
    assert len(cache) == 100
    assert not queue.plan(_viewport(100, y=-100_000), cache, {}, set(), full_resolution=True)


def test_progress_is_current_workload_not_all_unvisited_files():
    images = [str(i) for i in range(100_000)]
    queue = ThumbnailQueue(images, 1)
    paths = queue.plan(_viewport(), {}, {}, set())
    cache = dict.fromkeys(paths)
    assert queue.completed_count(cache, {}, set()) == len(queue.requested)
    queue.plan(_viewport(y=-500_000), cache, {}, set())
    assert queue.completed_count(cache, {}, set()) == 0
    assert len(queue.requested) <= 50


def test_lookahead_waits_for_visible_results_and_stays_within_one_screen():
    images = [str(i) for i in range(100_000)]
    queue = ThumbnailQueue(images, 1, limit=2)
    # 10 columns of 100 px, a 300 px viewport scrolled to row 50.
    viewport = _viewport(y=-5_000)
    visible = {str(i) for i in viewport.indices(buffer=0)}
    assert set(queue.plan(viewport, {}, {}, set())) == visible
    cache = dict.fromkeys(visible)
    last = cache.popitem()[0]
    queue.started(last, object())
    assert queue.plan(viewport, cache, {}, set()) == []
    assert queue.plan(viewport, cache, {last: "unreadable"}, set(), allow_lookahead=False) == []
    paths = queue.plan(viewport, cache, {last: "unreadable"}, set())
    rows = {int(path) // 10 for path in paths}
    assert rows == {47, 48, 49, 53, 54, 55}
    # Look-ahead is spare work: progress still counts only what is on screen.
    assert queue.requested == visible


def test_lookahead_skips_cached_failed_and_offline_rows():
    images = [str(i) for i in range(200)]
    queue = ThumbnailQueue(images, 1)
    viewport = _viewport(200)
    visible = dict.fromkeys(queue.plan(viewport, {}, {}, set()))
    first = [*visible, *queue.plan(viewport, visible, {}, set())]
    done = dict.fromkeys(first)
    assert not queue.plan(_viewport(200), done, {}, set())
    assert not queue.plan(_viewport(200), {}, done, set())
    assert not queue.plan(_viewport(200), {}, {}, set(first))


def test_hidden_wall_plans_no_lookahead():
    queue = ThumbnailQueue([str(i) for i in range(200)], 1)
    assert queue.plan(_viewport(200), {}, {}, set(), wall=False) == []
