"""Measurements with the toolbar's *Load data* menu open: the one place data come in.

A session holds one experiment. Its files are replicates on one concentration grid, so
data either join this session (*Add files…*, the same command as the canvas button),
take its place (*Replace data…*), or start another experiment (*Load data into a new
session…*, the same command as in the session switcher).
"""

from __future__ import annotations

from PyQt6.QtWidgets import QWidget

from gui.design import components as C
from gui.design.tokens import Theme

from . import view_measurements
from .common import command


def items() -> list:
    return [
        command('plus', 'Add files to this session…', 'Ctrl+O'),
        command('open', 'Replace data…'),
        None,
        command('file-plus', view_measurements.NEW_SESSION, 'Ctrl+Shift+O'),
    ]


NOTE = 'Added files become replicates and must share this session’s concentrations.'


def build(t: Theme) -> dict:
    spec = view_measurements.build(t)

    def overlay(root: QWidget):
        btn = root.findChild(QWidget, 'LoadData')
        btn.setCheckable(True)
        btn.setChecked(True)
        btn.update()
        pos = btn.mapTo(root, btn.rect().bottomLeft())
        menu = C.PopoverMenu(t, root, items(), NOTE, hover=0)
        menu.move(pos.x() - C.SHADOW, pos.y() + 2)
        menu.show()
        menu.raise_()

    spec['overlay'] = overlay
    return spec
