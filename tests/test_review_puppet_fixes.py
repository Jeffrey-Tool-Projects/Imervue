"""Host shutdown retains both externally provided workspace lifecycles."""
from types import SimpleNamespace


def test_main_release_closes_both_owned_workspaces_even_after_one_fails(monkeypatch):
    from Imervue.Imervue_main_window import ImervueMainWindow
    from Imervue.gpu_image_view.images import image_loader
    calls = []
    def broken():
        calls.append('puppet')
        raise RuntimeError('already gone')
    main = SimpleNamespace(
        puppet_workspace=SimpleNamespace(shutdown=broken),
        pet_workspace=SimpleNamespace(shutdown=lambda: calls.append('pet')),
    )
    monkeypatch.setattr(image_loader, 'cancel_folder_scan', lambda _viewer: None)
    ImervueMainWindow._release_for_close(main)
    assert calls == ['puppet', 'pet']
