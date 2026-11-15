"""Fit results view (analysis): headline, interval chart, conflict callout, titration plot; Fit details inspector."""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QGridLayout, QLabel, QScrollArea, QWidget

from gui.design import components as C
from gui.design import icons
from gui.design.plot_theme import apply_plot_theme, fit_line, px, scatter
from gui.design.tokens import Theme, space

from .common import DEMO, THIN, sci, split_stretches, sub

#: The opacity of the replicates' dots in this reference, in the plot and in its legend alike.
DOT_ALPHA = 0.45


def hero(t: Theme) -> QWidget:
    h = DEMO['headline']
    cond = DEMO['profile']['profiles']['Ka_guest']['conditional']
    lo_hi = f'{h["low_per_M"] / 1e8:.2f} – {h["high_per_M"] / 1e8:.2f}{THIN}×{THIN}10⁸'
    sec = t['text-secondary']

    lbl_row = C.hbox(
        C.label(f'K{sub("a", 10)} guest', 'label', 'secondary', rich=True),
        C.badge('Input-aware', 'accent'),
        None,
        spacing=3,
    )
    value = C.label(
        f'{sci(h["estimate_per_M"])}<span style="font-size:20px; font-weight:400; color:{sec}">&nbsp;M⁻¹</span>',
        'metric',
        rich=True,
    )
    interval = C.label(f'<span style="color:{sec}">95 % interval</span>&nbsp;&nbsp;{lo_hi} M⁻¹', 'number', rich=True)
    left_w = QWidget()
    left_w.setFixedWidth(264)
    left_w.setLayout(C.vbox(lbl_row, value, interval, None, spacing=2))

    ci = DEMO['conditional']
    rows = [
        {
            'label': 'Input-aware',
            'color': 'accent',
            'segments': [(h['low_per_M'], h['high_per_M'])],
            'est': h['estimate_per_M'],
            'text': f'{h["estimate_MM"] / 100:.2f}  [{h["low_MM"] / 100:.2f}, {h["high_MM"] / 100:.2f}]',
        },
        {
            'label': 'Inputs as entered',
            'color': 'text-tertiary',
            'segments': split_stretches(cond),
            'est': cond['best_ka_per_M'],
            'text': f'{ci["estimate_MM"] / 100:.2f}  [{ci["low_MM"] / 100:.2f}, {ci["high_MM"] / 100:.2f}]',
            'badge': 'Split',
        },
    ]
    chart = C.IntervalChart(
        t, rows, 0.95e8, 5.3e8, [(v * 1e8, f'{v:g}') for v in (1, 1.5, 2, 3, 4, 5)], f'×{THIN}10⁸ M⁻¹'
    )
    chart.setToolTip(
        'Split: the conditional interval holds rejected values; the accepted ones come in separate '
        'stretches. See Ka confidence.'
    )
    right = C.vbox(C.hbox(None, C.link_button('All results and diagnostics  →')), chart, None, spacing=2)

    w = QWidget()
    w.setLayout(C.hbox(left_w, right, spacing=7))
    return w


def titration_plot(t: Theme) -> pg.PlotWidget:
    pw = pg.PlotWidget()
    pw.setFrameShape(pg.QtWidgets.QFrame.Shape.NoFrame)
    pi = apply_plot_theme(pw, t, 'Guest (µM)', 'Signal (10⁵ a.u.)', [0.5, 1.0, 1.5, 2.0, 2.5, 3.0])
    x = np.array(DEMO['x_uM'])
    s = 1e-5
    for rep in DEMO['replicates']:
        y = np.array(rep['signal']) * s
        if rep['used_by_fit']:
            pi.addItem(scatter(t, x, y, 'replicate', DOT_ALPHA, 6))
        else:
            pi.addItem(scatter(t, x, y, 'replicate-off', 0.75, 7, symbol='x'))
    fc = DEMO['fit_curve']
    pi.addItem(fit_line(t, np.array(fc['x_uM']), np.array(fc['y']) * s))
    mean, sd = np.array(DEMO['mean']) * s, np.array(DEMO['sd']) * s
    eb = pg.ErrorBarItem(x=x, y=mean, height=2 * sd, beam=0.09, pen=pg.mkPen(t['text-primary'], width=px(1)))
    pi.addItem(eb)
    pi.addItem(scatter(t, x, mean, 'text-primary', 1.0, 6))
    pi.setXRange(-0.25, 9.25, padding=0)
    pi.setYRange(0.15, 3.05, padding=0)
    pi.getAxis('bottom').setTicks([[(v, f'{v:g}') for v in range(0, 10)]])
    return pw


def canvas(t: Theme) -> QWidget:
    w = QWidget()
    w.setObjectName('Canvas')
    w.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
    callout = C.Callout(
        t,
        'warning',
        'Inputs conflict',
        'Together, the inputs moved further from their entered values than you stated.',
        'Review in Ka confidence',
    )
    used = len(DEMO['replicates_used'])
    legend = C.LegendRow(
        t,
        [('dots', f'Replicates ({used})'), ('cross', 'A switched off'), ('mean', 'Mean ± SD'), ('line', 'Fit')],
        dot_alpha=DOT_ALPHA,
    )
    plot_head = C.hbox(
        C.label('Titration', 'body-strong'),
        None,
        legend,
        5,
        C.tool_button(t, None, 'scatter'),
        C.tool_button(t, None, 'image'),
        spacing=1,
    )
    lay = C.vbox(hero(t), 5, callout, 6, plot_head, 2, spacing=0, margins=(6, 5, 6, 4))
    lay.addWidget(titration_plot(t), 1)
    w.setLayout(lay)
    return w


def stat(name: str, value: str, sub: str = '') -> QWidget:
    w = QWidget()
    items = [C.label(name, 'small', 'secondary'), C.label(value, 'number-strong')]
    if sub:
        items.append(C.label(sub, 'small', 'tertiary'))
    w.setLayout(C.vbox(*items, spacing=1))
    return w


def inspector(t: Theme) -> QWidget:
    w = QWidget()
    w.setObjectName('Inspector')
    w.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)

    head = QWidget()
    head.setFixedHeight(44)
    head.setLayout(
        C.hbox(C.label('Fit details', 'body-strong'), None, C.tool_button(t, None, 'x'), margins=(5, 0, 3, 0))
    )

    # Fit quality
    q = QWidget()
    g = QGridLayout()
    g.setContentsMargins(0, 0, 0, 0)
    g.setHorizontalSpacing(space(5))
    g.setVerticalSpacing(space(4))
    g.addWidget(stat('R²', f'{DEMO["r_squared"]:.6f}'), 0, 0)
    g.addWidget(stat('RMSE', f'{DEMO["rmse"]:.0f} a.u.'), 0, 1)
    g.addWidget(stat('Replicates used', '7 of 8', 'A switched off'), 1, 0)
    g.addWidget(stat('Noise', '0.6 % + 80 a.u.', 'from replicate scatter'), 1, 1)
    g.setColumnStretch(0, 1)
    g.setColumnStretch(1, 1)
    q.setLayout(g)

    # Diagnostics
    d = DEMO['diagnostics']
    diag_rows = [
        ('check-circle', 'success', 'Curve fits with inputs moved', f'p = {d["misfit"]["p_value"]:.2f}'),
        ('alert-circle', 'warning', 'Misfit at inputs as entered', f'p = {d["conditional_misfit"]["p_value"]:.3f}'),
        ('alert-circle', 'warning', 'Inputs conflict', 'p < 0.001'),
    ]
    dw = QWidget()
    dl = C.vbox(spacing=0)
    for ic, tone, text, pv in diag_rows:
        icl = QLabel()
        icl.setPixmap(icons.pixmap(ic, t[tone], 16))
        row = QWidget()
        row.setFixedHeight(28)
        row.setLayout(C.hbox(icl, C.label(text), None, C.label(pv, 'small-number', 'secondary'), spacing=3))
        dl.addWidget(row)
    dw.setLayout(dl)

    # Parameters
    pw = QWidget()
    pg_ = QGridLayout()
    pg_.setContentsMargins(0, 0, 0, 0)
    pg_.setHorizontalSpacing(space(4))
    pg_.setVerticalSpacing(0)
    params = [
        (f'K{sub("a")} guest', sci(DEMO['parameters']['Ka_guest']['value']), 'M⁻¹'),
        (f'I{sub("0")} *', f'{DEMO["parameters"]["I0"]["value"]:,.0f}'.replace(',', THIN), 'a.u.'),
        (f'I{sub("dye,free")} *', '0', 'a.u./M'),
        (f'I{sub("dye,bound")} *', sci(DEMO['parameters']['I_dye_bound']['value']), 'a.u./M'),
    ]
    for c, h in enumerate(('Parameter', 'Estimate', 'Unit')):
        lbl = C.label(h, 'label', 'tertiary')
        lbl.setFixedHeight(24)
        if c == 1:
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        pg_.addWidget(lbl, 0, c)
    pg_.addWidget(C.hairline(), 1, 0, 1, 3)
    for i, (n, v, u) in enumerate(params):
        r = 2 + 2 * i
        nl = C.label(n, 'body', rich=True)
        nl.setFixedHeight(28)
        vl = C.label(v, 'number')
        vl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        pg_.addWidget(nl, r, 0)
        pg_.addWidget(vl, r, 1)
        pg_.addWidget(C.label(u, 'small', 'secondary'), r, 2)
        if i < len(params) - 1:
            pg_.addWidget(C.hairline(), r + 1, 0, 1, 3)
    pg_.setColumnStretch(0, 1)
    foot = C.label('* Not separately determined while the dye total is fixed.', 'small', 'tertiary')
    foot.setWordWrap(True)
    pw.setLayout(C.vbox(pg_, foot, spacing=3))

    # Input shifts
    sh = DEMO['input_shifts']
    shift_rows = [
        (f'K{sub("a,dye")}', sh['Ka_dye']),
        ('[Host]₀', sh['h0']),
        ('[Dye]₀', sh['d0']),
        ('Guest (titrant)', sh['__titrant__']),
    ]
    sw = QWidget()
    sl = QGridLayout()
    sl.setContentsMargins(0, 0, 0, 0)
    sl.setHorizontalSpacing(space(4))
    sl.setVerticalSpacing(0)
    for i, (n, s) in enumerate(shift_rows):
        nl = C.label(n, 'body', rich=True)
        nl.setFixedHeight(28)
        bar = C.ShiftBar(t, s['z'])
        bar.setToolTip(f'{s["z"]:+.1f} σ')
        v = C.label(f'{s["fraction"] * 100:+.1f} %'.replace('-', '−'), 'number')
        v.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        sl.addWidget(nl, i, 0)
        sl.addWidget(bar, i, 1)
        sl.addWidget(v, i, 2)
    sl.setColumnStretch(0, 1)
    cap = C.label(
        'Bars in σ, band ±1 σ. They show where the fit put the correction, not which input is wrong.',
        'small',
        'tertiary',
    )
    cap.setWordWrap(True)
    sw.setLayout(C.vbox(sl, cap, spacing=3))

    body = QWidget()
    body.setObjectName('InspectorBody')
    body.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
    bl = C.vbox(
        C.section(t, 'Fit quality', q, first=True),
        C.section(t, 'Diagnostics', dw),
        C.section(t, 'Parameters', pw),
        C.section(t, 'Input shifts', sw),
        None,
        spacing=0,
        margins=(5, 0, 5, 4),
    )
    body.setLayout(bl)
    scroll = QScrollArea()
    scroll.setWidget(body)
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    w.setLayout(C.vbox(head, scroll, spacing=0))
    return w


def build(t: Theme) -> dict:
    return {
        'nav': 'Fit results',
        'title': 'Fit results',
        'badge': ('Input-aware · 7 of 8 replicates', 'neutral'),
        'canvas': canvas(t),
        'inspector': inspector(t),
    }
