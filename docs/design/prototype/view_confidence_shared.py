"""Ka confidence view, shared-axis variant: both profiles on one weighted-R² axis, as the app draws them.

Built from view_confidence's pieces; only the plot's y axis and the notes on reading it differ.
The R² span follows the app's own framing rule (``_default_r2_range`` in
gui/plotting/identifiability_widget.py): from one level span below the lowest drawn level
(each best R² and every step of each cut-off inside the Ka span) to 0.6 spans above the
highest, never more than 0.1 span above 1. Both cut-offs are drawn, each stepped where its
fit holds a signal parameter at its bound. The input-aware curve is drawn on this axis as the
app draws it, though its height is weighted R² less the input penalty; the notes say so.
"""

from __future__ import annotations

import math

import numpy as np
import pyqtgraph as pg

from gui.design.tokens import Theme

from . import view_confidence as V

_levels = [V.best_r2(V.COND), V.best_r2(V.AWARE)]
for _prof in (V.COND, V.AWARE):
    _lg = np.log10(np.array(_prof['grid_per_M']))
    _levels += np.array(_prof['r2_cut'])[(_lg >= V.X_RANGE[0]) & (_lg <= V.X_RANGE[1])].tolist()
_span = max(_levels) - min(_levels)
R2_Y = (min(_levels) - _span, min(max(_levels) + 0.6 * _span, 1.0 + 0.1 * _span))
R2_TICKS = [0.980, 0.985, 0.990, 0.995, 1.000]


def add_cut(pi, t: Theme, prof: dict, color: str):
    """The cut-off of one profile, stepped centred on its grid nodes."""
    item = pg.PlotDataItem(
        V.cut_steps(prof), np.array(prof['r2_cut'], float), stepMode='center', pen=V.dotted(t, color)
    )
    item.setZValue(1.5)
    pi.addItem(item, ignoreBounds=True)


def shared_plot(t: Theme):
    ticks = [(v, f'{v:.3f}') for v in R2_TICKS]
    main = V.profile_axes(t, 'Weighted R²', R2_Y, ticks, left_width=72)
    pi = main.getPlotItem()
    V.add_band(pi, t, V.HEAD['low_per_M'], V.HEAD['high_per_M'])
    add_cut(pi, t, V.COND, 'text-secondary')
    add_cut(pi, t, V.AWARE, 'accent')
    for prof, color, width in ((V.COND, 'text-secondary', 1.75), (V.AWARE, 'accent', 2.25)):
        x, y = V.crop(np.log10(np.array(prof['grid_per_M'])), np.array(prof['r2'], float))
        V.add_curve(pi, t, x, y, color, width)
    V.add_marker(pi, t, math.log10(V.COND['best_ka_per_M']), V.best_r2(V.COND), 'text-secondary')
    V.add_marker(pi, t, math.log10(V.NUM['aware']['estimate']), V.best_r2(V.AWARE), 'accent')

    a, c = V.NUM['aware'], V.NUM['conditional']
    V.add_tag(pi, t, f'cut-off {a["cut"]}', V.RIGHT_X, V.AWARE['r2_threshold'], anchor=(1, 1.05))
    # Under its line mid-plot, where neither curve passes: both cross it again at the right.
    V.add_tag(pi, t, f'cut-off {c["cut"]}', math.log10(3.6e8), V.COND['r2_threshold'], anchor=(1, -0.05))
    V.add_tag(pi, t, f'cut-off {c["cut_levels"][0]}', V.X_RANGE[0] + 0.008, min(V.COND['r2_cut']), anchor=(0, 1.05))
    return V.stack(main, V.interval_strip(t, main, left_width=72))


READING_SHARED = (
    f'The as-entered curve is the best weighted R² reachable at each {V.KA} with the inputs as entered. The '
    'input-aware curve is the same with the inputs free to move, less a penalty for each input’s move, measured '
    'against its stated uncertainty.',
    f'Where a curve lies above its own dotted cut-off, that {V.KA} is accepted.',
    V.WEIGHTED_NOTE,
)
SPLIT_SHARED = V.split_text('its cut-off')


def build(t: Theme) -> dict:
    return {
        'nav': 'Ka confidence',
        'title': 'Ka confidence',
        'badge': V.BADGE,
        'canvas': V.canvas(t, shared_plot(t), V.LEGEND),
        'inspector': V.inspector(t, READING_SHARED, SPLIT_SHARED),
    }
