"""Shared data and formatting helpers for the prototype views."""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

DATA = Path(__file__).resolve().parent / 'data'


def load(name: str):
    """The JSON file *name* of ``data/``."""
    return json.loads((DATA / name).read_text())


DEMO = load('demo.json')
SUP = str.maketrans('0123456789-', '⁰¹²³⁴⁵⁶⁷⁸⁹⁻')
THIN = ' '
LETTERS = 'ABCDEFGH'


def sci(v: float, digits: int = 3) -> str:
    e = math.floor(math.log10(abs(v)))
    return f'{v / 10**e:.{digits - 1}f}{THIN}×{THIN}10{str(e).translate(SUP)}'


def sub(text: str, size: int = 11) -> str:
    return f'<span style="font-size:{size}px; vertical-align:sub">{text}</span>'


def molar(v: float) -> str:
    """A face value in molar, as a concentration table shows it: 0, or mantissa × 10ⁿ with the file's digits."""
    if v == 0:
        return '0'
    e = math.floor(math.log10(abs(v)))
    m = f'{v / 10**e:.5f}'.rstrip('0').rstrip('.')
    return f'{m}{THIN}×{THIN}10{str(e).translate(SUP)}'


def split_stretches(prof: dict) -> list[tuple[float, float]]:
    """Accepted stretches of the conditional profile inside its interval."""
    g = np.array(prof['grid_per_M'])
    ok = np.array(prof['r2']) >= np.array(prof['r2_cut'])
    iv = prof['interval_per_M']
    ok &= (g >= iv['low'] * 0.999) & (g <= iv['high'] * 1.001)
    out, start = [], None
    for i, flag in enumerate(ok):
        if flag and start is None:
            start = i
        if not flag and start is not None:
            out.append((g[start], g[i - 1]))
            start = None
    if start is not None:
        out.append((g[start], g[len(g) - 1]))
    out[0] = (iv['low'], out[0][1])
    out[-1] = (out[-1][0], iv['high'])
    return out


def keys(sequence: str) -> str:
    """A shortcut in the platform's own keys (``'Ctrl+O'`` reads ⌘O on macOS)."""
    from PyQt6.QtGui import QKeySequence

    return QKeySequence(sequence).toString(QKeySequence.SequenceFormat.NativeText)
