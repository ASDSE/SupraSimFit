"""Fit results with the session switcher open: how several experiments live in one window.

Each row is one session (one experiment: its files, binding model, inputs and analyses).
The switcher lists every open session with its state and holds the session commands.
"""

from __future__ import annotations

from PyQt6.QtWidgets import QWidget

from gui.design import components as C
from gui.design.tokens import Theme

from . import view_fit
from .common import command, keys
from .shell import SESSIONS

# Each session's state in words, beside its glyph.
STATE = {
    'warning': 'Ka 1.59 × 10⁸ M⁻¹ · 1 warning',
    'running': 'Fitting · 62 %',
    'stale': 'Needs refit · data changed',
}


def commands() -> list:
    return [
        command('plus', 'New session', 'Ctrl+T'),
        command('file-plus', 'Load data into a new session…', 'Ctrl+Shift+O'),
        command('results', 'Open results file…'),
        None,
        command('copy', 'Duplicate IDA_system'),
        command('x', 'Close IDA_system', 'Ctrl+W'),
    ]


def build(t: Theme) -> dict:
    spec = view_fit.build(t)
    spec['sidebar'] = {'open_': True}

    def overlay(root: QWidget):
        sw = root.findChild(QWidget, 'SessionSwitcher')
        pos = sw.mapTo(root, sw.rect().bottomLeft())
        sessions = [{**s, 'status': STATE[s['state']]} for s in SESSIONS]
        pop = C.SessionPopover(t, root, sessions, commands(), title_hint=f'{keys("Ctrl+1")} – {keys("Ctrl+9")}')
        pop.move(pos.x() - C.SHADOW, pos.y() + 2)
        pop.show()
        pop.raise_()

    spec['overlay'] = overlay
    return spec
