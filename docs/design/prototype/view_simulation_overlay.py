"""Simulation window with a measurement file laid over the titration (*Overlay data…*):
IDA_system.txt's replicates as hollow rings over the simulated ones, the model computed
on the file's own concentrations, which the Concentrations section now lists."""

from __future__ import annotations

from gui.design.tokens import Theme

from . import view_simulation as V


def build(t: Theme) -> dict:
    return {'root': V.window(t, overlay=True, hover_end=False), 'size': V.WINDOW_SIZE}
