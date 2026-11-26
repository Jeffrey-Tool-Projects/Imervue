"""Buttons and panels sized in pixels must still hold their text in every language."""
from __future__ import annotations

import numpy as np
import pytest
from PIL import Image
from PySide6.QtCore import QSize
from PySide6.QtWidgets import QFrame, QToolButton

from Imervue.multi_language.language_wrapper import language_wrapper
from Imervue.system import ui_scale

LANGUAGES = ("English", "Traditional_Chinese", "Chinese", "Japanese", "Korean")


@pytest.fixture(params=LANGUAGES)
def language(request):
    original = language_wrapper.language
    language_wrapper.reset_language(request.param)
    yield request.param
    language_wrapper.reset_language(original)


@pytest.fixture(params=[1.0, 1.5])
def scale(request, monkeypatch):
    monkeypatch.setattr(ui_scale, "scale_factor", lambda: request.param)
    return request.param


def _assert_text_fits(buttons):
    assert buttons
    for button in buttons:
        hint = button.sizeHint()
        assert button.width() >= hint.width(), button.text()
        assert button.height() >= hint.height(), button.text()


def test_uniform_size_starts_from_the_scaled_base_and_grows_to_the_longest(qapp, monkeypatch):
    monkeypatch.setattr(ui_scale, "scale_factor", lambda: 2.0)
    short, long = QToolButton(), QToolButton()
    short.setText("A")
    long.setText("A label far longer than the base width allows")
    size = ui_scale.uniform_button_size([short, long], QSize(40, 10))
    assert size.width() == long.sizeHint().width()
    assert size.height() == 20                     # the scaled base was taller
    assert short.size() == long.size() == size
    for button in (short, long):
        button.deleteLater()


def test_modify_actions_fit_their_labels(qapp, language, scale):
    from Imervue.gui.modify_actions_widget import ModifyActionsWidget
    widget = ModifyActionsWidget(main_gui=None)
    try:
        buttons = widget.findChildren(QToolButton)
        _assert_text_fits(buttons)
        assert len({button.size().toTuple() for button in buttons}) == 1
        assert buttons[0].width() >= ui_scale.scaled_px(84)
    finally:
        widget.deleteLater()


def test_annotation_toolbox_and_panel_fit_their_labels(qapp, language, scale):
    from Imervue.gui.annotation_dialog import AnnotationDialog
    base = Image.fromarray(np.full((40, 60, 4), 255, dtype=np.uint8), "RGBA")
    dialog = AnnotationDialog(base, source_path="")
    try:
        toolbox = dialog.findChild(QFrame, "annotationLeftToolbox")
        tools = [b for b in toolbox.findChildren(QToolButton) if b.isCheckable()]
        _assert_text_fits(tools)
        assert toolbox.width() >= tools[0].width()
        panel = dialog.findChild(QFrame, "annotationRightPanel")
        assert panel.width() >= panel.layout().sizeHint().width()
        assert panel.width() >= ui_scale.scaled_px(248)
    finally:
        dialog.deleteLater()
