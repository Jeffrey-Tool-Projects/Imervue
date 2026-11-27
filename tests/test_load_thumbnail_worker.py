"""Tests for ``LoadThumbnailWorker``: RAW through raw_loader's upright preview, EXIF-upright rasters."""
from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from Imervue.gpu_image_view.images import load_thumbnail_worker as mod
from Imervue.image import raw_loader


def _developed(monkeypatch, shape):
    calls = []

    def develop(path, thumbnail=False):
        calls.append((path, thumbnail))
        return np.full(shape, 200, dtype=np.uint8)
    monkeypatch.setattr(raw_loader, "develop_raw", develop)
    return calls


@pytest.mark.parametrize(("size", "shape"), [(None, (1500, 1000, 3)), (64, (64, 43, 4))])
def test_a_raw_thumbnail_is_raw_loaders_upright_preview(monkeypatch, size, shape):
    """The worker had its own libraw path that never turned a portrait preview upright."""
    calls = _developed(monkeypatch, (1500, 1000, 3))
    data = mod.LoadThumbnailWorker("shot.cr3", size=size)._load_raw()  # noqa: SLF001
    assert calls == [("shot.cr3", True)]
    assert data.shape == shape


def test_a_large_raw_preview_is_capped_at_2048(monkeypatch):
    _developed(monkeypatch, (4000, 6000, 3))
    data = mod.LoadThumbnailWorker("shot.nef", size=None)._load_raw()  # noqa: SLF001
    assert 2040 <= max(data.shape[:2]) <= 2048   # int() of the scaled sides


def test_an_unreadable_raw_is_an_image_read_error(tmp_path):
    from Imervue.image.read_errors import IMAGE_READ_ERRORS
    path = tmp_path / "broken.cr2"
    path.write_bytes(b"not a raw file" * 20)
    with pytest.raises(IMAGE_READ_ERRORS):
        mod.LoadThumbnailWorker(str(path), size=64)._load_raw()  # noqa: SLF001


def _portrait(tmp_path):
    exif = Image.Exif()
    exif[0x0112] = 6
    path = tmp_path / "portrait.jpg"
    Image.new("RGB", (40, 20)).save(path, exif=exif)
    return str(path)


@pytest.mark.parametrize("size", [None, 16])
def test_tagged_photo_thumbnail_is_upright(tmp_path, size):
    worker = mod.LoadThumbnailWorker(_portrait(tmp_path), size=size)
    arr = worker._bake_fresh(None)
    height, width = arr.shape[:2]
    assert height > width


def test_legacy_geometry_recipe_keeps_the_stored_orientation(tmp_path):
    from Imervue.image.recipe import Recipe
    worker = mod.LoadThumbnailWorker(_portrait(tmp_path), size=None)
    arr = worker._bake_fresh(Recipe.from_dict({"rotate_steps": 2}))
    assert arr.shape[:2] == (20, 40)   # rotated 180 on the stored 40x20 pixels



@pytest.mark.parametrize("size", [None, 64])
def test_a_sixteen_bit_grey_tile_shows_its_gradient(tmp_path, size):
    path = tmp_path / "depth.png"
    Image.fromarray(np.tile(np.linspace(0, 65535, 128).astype(np.uint16), (4, 1))).save(path)
    row = mod.LoadThumbnailWorker(str(path), size=size)._bake_fresh(None)[0, :, 0].astype(int)
    assert row[0] <= 2          # a downscale averages the first pixels with their neighbours
    assert row[-1] >= 253
    assert abs(row[len(row) // 2] - 128) <= 3   # it was nearly all 255: clipped, not scaled


@pytest.mark.parametrize("size", [None, 64])
def test_a_tile_decodes_in_the_giant_decode_slot(tmp_path, monkeypatch, size):
    from contextlib import contextmanager

    from Imervue.gpu_image_view.images import image_loader
    asked = []

    @contextmanager
    def slot(pixels):
        asked.append(pixels)
        yield

    monkeypatch.setattr(image_loader, "decode_slot", slot)
    path = tmp_path / "a.png"
    Image.new("RGB", (30, 20)).save(path)
    mod.LoadThumbnailWorker(str(path), size=size)._bake_fresh(None)
    assert asked == [600]


@pytest.fixture
def disk_cache(tmp_path, monkeypatch):
    from Imervue.image import thumbnail_disk_cache as tdc
    monkeypatch.setattr(tdc, "_get_cache_dir", lambda: tmp_path / "thumbs")
    cache = tdc.ThumbnailDiskCache()
    monkeypatch.setattr(mod, "thumbnail_disk_cache", cache)
    yield cache
    cache.close()


def test_a_decode_the_wall_moved_on_from_is_still_cached(tmp_path, monkeypatch, disk_cache):
    worker = mod.LoadThumbnailWorker(_portrait(tmp_path), size=16)
    real_load = worker._load_by_extension
    delivered = []
    worker.signals.finished.connect(lambda *_args: delivered.append(True))

    def load_then_abort(**kwargs):
        data = real_load(**kwargs)
        worker.abort()          # the wall scrolled away mid-decode
        return data

    monkeypatch.setattr(worker, "_load_by_extension", load_then_abort)
    worker.run()
    assert not delivered
    assert disk_cache.get(worker.path, 16).shape == (16, 8, 4)


def test_ready_pixels_reach_the_wall_before_cache_write_and_survive_failure(tmp_path, monkeypatch,
                                                                          disk_cache):
    worker = mod.LoadThumbnailWorker(_portrait(tmp_path), size=16)
    events = []
    worker.signals.finished.connect(lambda data, *_args: events.append(data.shape))
    worker.signals.error.connect(lambda *_args: events.append("load failed"))

    def fail_write(*args, **kwargs):
        events.append("cache write")
        raise OSError("disk full")

    monkeypatch.setattr(disk_cache, "put", fail_write)
    worker.run()
    assert events == [(16, 8, 4), "cache write"]


def test_replacement_after_delivery_cannot_reuse_the_old_pixels(tmp_path, disk_cache):
    path = _portrait(tmp_path)
    worker = mod.LoadThumbnailWorker(path, size=16)
    worker.signals.finished.connect(lambda *_args: Image.new("RGB", (20, 40), "red").save(path))
    worker.run()
    assert disk_cache.total_bytes() > 0
    assert disk_cache.get(path, 16) is None


def test_an_aborted_full_size_decode_is_neither_cached_nor_returned(tmp_path, monkeypatch):
    monkeypatch.setattr(mod.thumbnail_disk_cache, "put",
                        lambda *_a: pytest.fail("full-size tiles are not disk-cached"))
    worker = mod.LoadThumbnailWorker(_portrait(tmp_path), size=None)
    worker.abort()
    assert worker._bake_fresh(None) is None


def test_a_landed_tile_takes_the_signature_its_worker_recorded(tmp_path, monkeypatch):
    from Imervue.gpu_image_view import tile_loader_offline as offline
    path = _portrait(tmp_path)
    offline.note_landed_signature(path)
    monkeypatch.setattr(offline, "file_signature",
                        lambda _p: pytest.fail("the GUI thread must not stat it again"))
    sig = offline.take_landed_signature(path)
    assert sig is not None and sig[2] == ".jpg"


def test_without_a_recorded_signature_the_landing_stats_once(tmp_path, monkeypatch):
    from Imervue.gpu_image_view import tile_loader_offline as offline
    stats = []
    monkeypatch.setattr(offline, "file_signature", lambda p: stats.append(p) or (1, 2, ".png"))
    assert offline.take_landed_signature(str(tmp_path / "x.png")) == (1, 2, ".png")
    assert stats == [str(tmp_path / "x.png")]


def test_recorded_signatures_stay_bounded(tmp_path, monkeypatch):
    from Imervue.gpu_image_view import tile_loader_offline as offline
    monkeypatch.setattr(offline, "_SIGNATURE_LIMIT", 3)
    monkeypatch.setattr(offline, "_landed_signatures", type(offline._landed_signatures)())
    monkeypatch.setattr(offline, "file_signature", lambda p, _stat: (0, 0, p))
    for name in "abcde":
        offline.note_landed_signature(name)
    assert list(offline._landed_signatures) == ["c", "d", "e"]


def test_a_sweep_sees_a_rewrite_during_decode(tmp_path, monkeypatch, disk_cache):
    from Imervue.gpu_image_view import tile_loader_offline as offline
    worker = mod.LoadThumbnailWorker(_portrait(tmp_path), size=16)
    decode = worker._bake_fresh

    def rewrite_after_decode(recipe):
        pixels = decode(recipe)
        Image.new("RGB", (150, 100), "green").save(worker.path)
        return pixels

    monkeypatch.setattr(worker, "_bake_fresh", rewrite_after_decode)
    worker.run()
    known = {worker.path: offline.take_landed_signature(worker.path)}
    assert offline.scan_folder_paths([worker.path], known) == (set(), {worker.path})
    assert disk_cache.get(worker.path, 16) is None

