"""Tile texture uploads are spread over frames by a per-frame byte budget."""
from __future__ import annotations

from Imervue.gpu_image_view.tile_textures import UPLOAD_BYTES_PER_FRAME, UploadBudget


def test_uploads_stop_at_the_frame_budget_and_note_the_rest():
    budget = UploadBudget(1000)
    assert budget.allow(400) and budget.allow(600)
    assert not budget.allow(1)
    assert budget.deferred
    assert (budget.used, budget.uploads) == (1000, 2)


def test_the_first_upload_always_fits_even_when_larger_than_the_budget():
    budget = UploadBudget(10)
    assert budget.allow(10_000)
    assert not budget.allow(1)


def test_a_frame_within_budget_defers_nothing():
    budget = UploadBudget()
    tile = 256 * 256 * 4
    assert all(budget.allow(tile) for _ in range(UPLOAD_BYTES_PER_FRAME // tile))
    assert not budget.deferred


def test_negative_sizes_count_as_nothing():
    budget = UploadBudget(-5)
    assert budget.limit == 0
    assert budget.allow(-3)
    assert budget.used == 0
