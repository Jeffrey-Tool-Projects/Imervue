"""Large walls draw candidates only, with no whole-library iteration per frame."""
from __future__ import annotations

from types import SimpleNamespace

from Imervue.gpu_image_view import tile_grid_renderer as module, tile_loader


def _wall(monkeypatch, images):
    view = SimpleNamespace(
        model=SimpleNamespace(images=images), thumbnail_size=128, tile_cache={},
        tile_scale=1., tile_padding=8, grid_offset_x=0., grid_offset_y=-500_000.,
        width=lambda: 1920, height=lambda: 1080, devicePixelRatio=lambda: 1.,
        _evict_tile_textures_if_needed=lambda: None, tile_selection_mode=False,
        focused_tile_index=0, focus_ring_visible=False, _drag_selecting=False,
    )
    monkeypatch.setattr(module, "glLoadIdentity", lambda: None)
    monkeypatch.setattr(module, "glPixelStorei", lambda *args: None)
    return module.TileGridRenderer(view)


def test_frame_never_walks_the_entire_library(monkeypatch):
    class IndexedImages(list):
        def __iter__(self):
            raise AssertionError("whole-library traversal in a frame")

    renderer = _wall(monkeypatch, IndexedImages(str(i) for i in range(100_000)))
    visited = []
    monkeypatch.setattr(renderer, "_draw_single", lambda i, *args: visited.append(i))
    renderer.paint()
    assert 0 < len(visited) < 200
    assert min(visited) > 50_000


def test_only_a_frame_with_finished_uploads_starts_lookahead(monkeypatch):
    renderer = _wall(monkeypatch, ["a", "b"])
    view = renderer._view
    view.grid_offset_y = 0
    view._tile_queue = object()
    events = []
    view.update = lambda: events.append("repaint")
    remaining = {"a", "b"}

    def draw(_i, path, *_args):
        if path in remaining and renderer._upload_budget.allow(renderer._upload_budget.limit):
            remaining.remove(path)
            events.append(path)

    monkeypatch.setattr(renderer, "_draw_single", draw)
    monkeypatch.setattr(tile_loader, "pump_thumbnail_workers",
                        lambda view, *, allow_lookahead: events.append(allow_lookahead))
    renderer.paint()
    renderer.paint()
    assert events == ["a", "repaint", False, "b", True]
