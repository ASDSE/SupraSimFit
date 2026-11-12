"""Simulation window with its settings scrolled to the end and *Signal* opened (the
titrant concentrations, the noise and the signal coefficients), and the inspector's ⋯
menu open: saving, loading and resetting this window's settings."""

from __future__ import annotations

from PyQt6.QtWidgets import QScrollArea, QWidget

from gui.design.tokens import Theme

from . import view_simulation as V


def build(t: Theme) -> dict:
    def overlay(root: QWidget) -> None:
        bar = root.findChild(QScrollArea, 'InspectorScroll').verticalScrollBar()
        bar.setValue(bar.maximum())
        V.open_settings_menu(t, root)

    return {'root': V.window(t, signal_open=True, hover_end=False), 'size': V.WINDOW_SIZE, 'overlay': overlay}
