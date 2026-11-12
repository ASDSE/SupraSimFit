"""Sensitivity view (analysis): a finished Sobol' run on the IDA demo session.

Canvas: how far the stated input uncertainties spread Ka guest (the spread as the hero,
the samples as a histogram beside the reported input-aware value), the Sobol' indices of
each error source with their 95 % whiskers, the variance budget and the what-if row; a
warning above them when the fit reports an input conflict. Inspector: the run's settings
(Analysis settings) and the facts of the run.

Every number comes from data/sensitivity.json, written by
data/compute_sensitivity.py: a real run_sensitivity() call on the demo session
with the arguments FittingSession.run_sensitivity() passes; the input-aware value and
interval come from the same session's fit (common.DEMO).
"""

from __future__ import annotations

import math

import numpy as np
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFontMetrics, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QGridLayout, QLabel, QScrollArea, QSizePolicy, QWidget

from gui.design import components as C
from gui.design import icons
from gui.design.tokens import Theme, font, space

from .common import DEMO, THIN, load, sci, sub

RUN = load('sensitivity.json')
KA = 'Ka_guest'
MINUS = '−'
# The fit reports an input conflict: the app's sensitivity summary leads with it.
CONFLICT = any('further from their entered values' in s for s in RUN['summary_texts'])
AWARE = DEMO['headline']  # the reported input-aware Ka guest and its interval

# Source names as rich text, in the label style of view_fit (K with the subscript a,dye).
_NAMES = {'h0': '[Host]₀', 'd0': '[Dye]₀', '__titrant__': 'Guest (titrant)'}

# The chart's name column and the budget table's Source column share this width, so
# the chart's bars start where the table's Stated column does.
SRC_W = 132


def name(source: str, size: int = 11) -> str:
    """A source's display name; *size* is the subscript's pixel size (10 beside 12-px text)."""
    return f'K{sub("a,dye", size)}' if source == 'Ka_dye' else _NAMES[source]


def S(index: str, size: int = 11) -> str:
    """A Sobol' index symbol, S₁ or S_T, with the same rich subscript as every other label."""
    return f'S{sub(index, size)}'


def signed(v: float, fmt: str) -> str:
    return format(v, fmt).replace('-', MINUS)


def share(v: float) -> str:
    """An index to two decimals, or three below 0.1 so a small share keeps two figures."""
    return signed(v, '.2f' if abs(v) >= 0.1 else '.3f')


def ordered_sources() -> list[str]:
    """Sources ranked by their first-order index, largest first."""
    s1 = RUN['sobol_s1'][KA]
    return sorted(RUN['sources'], key=lambda s: -s1[s])


def e8(v: float) -> str:
    return f'{v / 1e8:.2f}'


# ── Painted pieces (tokens only) ───────────────────────────────────────────────────


def bar_fill(t: Theme, inside: bool) -> QColor:
    """A sample bar: solid inside the middle 90 % of samples, faded in the tails."""
    return t.q('text-secondary', 0.62 if inside else 0.22)


class SampleHistogram(QWidget):
    """Every sample's best Ka on a log axis in the neutral data colour: the middle 90 % of
    samples solid, the tails faded. Two markers, each labelled at its top end in the band
    above the bars, as Ka confidence labels its lines: the fit at the inputs as entered
    (dashed, where the samples centre) and the reported input-aware Ka (accent), its
    95 % interval as the accent tint Ka confidence draws it with."""

    LABEL_H = 16  # the marker labels
    TOP = 22  # the bars' top; the markers start just under their labels
    BASE = 80  # the axis
    H = 104

    def __init__(self, t: Theme, ka: np.ndarray, baseline: float, ticks: list[float]):
        super().__init__()
        self.t, self.ka, self.baseline, self.ticks = t, ka, baseline, ticks
        self.lo, self.hi = 0.95e8, 6.5e8  # the 1 tick clear of the left edge, as on Fit results
        self.setFixedHeight(self.H)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def _x(self, v: float, w: float) -> float:
        return (math.log10(v) - math.log10(self.lo)) / (math.log10(self.hi) - math.log10(self.lo)) * w

    def paintEvent(self, _):
        t = self.t
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width() - 2.0
        top, base = float(self.TOP), float(self.BASE)
        X = lambda v: self._x(v, w)  # noqa: E731
        # the reported interval, under everything
        a_lo, a_hi = X(AWARE['low_per_M']), X(AWARE['high_per_M'])
        p.fillRect(QRectF(a_lo, top - 2, a_hi - a_lo, base - top + 2), t.q('accent', 0.07 if t.dark else 0.08))
        # grid
        p.setPen(QPen(t.q('grid'), 1))
        for tk in self.ticks:
            p.drawLine(QPointF(X(tk), top), QPointF(X(tk), base))
        # bars
        edges = np.logspace(math.log10(self.lo), math.log10(self.hi), 53)
        counts, _ = np.histogram(self.ka, bins=edges)
        p5, p95 = np.percentile(self.ka, [5, 95])
        peak = counts.max()
        p.setPen(Qt.PenStyle.NoPen)
        for i, c in enumerate(counts):
            if not c:
                continue
            a, b = X(edges[i]), X(edges[i + 1])
            inside = p5 <= math.sqrt(edges[i] * edges[i + 1]) <= p95
            h = max(c / peak * (base - top - 4), 1.5)
            path = QPainterPath()
            path.addRoundedRect(QRectF(a + 0.75, base - h, b - a - 1.5, h), 1.5, 1.5)
            p.fillPath(path, bar_fill(t, inside))
        # axis
        p.setPen(QPen(t.q('border-strong'), 1))
        p.drawLine(QPointF(0, base + 0.5), QPointF(w, base + 0.5))
        p.setFont(font('small-number'))
        for tk in self.ticks:
            x = X(tk)
            p.setPen(QPen(t.q('border-strong'), 1))
            p.drawLine(QPointF(x, base), QPointF(x, base + 4))
            p.setPen(t.q('text-tertiary'))
            p.drawText(QRectF(x - 30, base + 6, 60, 16), Qt.AlignmentFlag.AlignHCenter, f'{tk / 1e8:g}')
        p.drawText(QRectF(w - 120, base + 6, 120, 16), Qt.AlignmentFlag.AlignRight, f'×{THIN}10⁸ M⁻¹')
        # markers: a halo so each line reads over the bars, then the line
        y0 = self.LABEL_H + 4.0
        bx, ax = X(self.baseline), X(AWARE['estimate_per_M'])
        for x in (bx, ax):
            p.setPen(QPen(t.q('bg-surface'), 4.5))
            p.drawLine(QPointF(x, y0), QPointF(x, base))
        dash = QPen(t.q('text-primary'), 1.5)
        dash.setDashPattern([3, 2.5])
        p.setPen(dash)
        p.drawLine(QPointF(bx, y0), QPointF(bx, base))
        p.setPen(QPen(t.q('accent'), 2))
        p.drawLine(QPointF(ax, y0), QPointF(ax, base))
        # their labels, centred on the line and kept inside the plot
        fm = QFontMetrics(font('small'))
        p.setFont(font('small'))
        for x, text, tone in (
            (
                ax,
                f'Input-aware {e8(AWARE["estimate_per_M"])}  [{e8(AWARE["low_per_M"])}, {e8(AWARE["high_per_M"])}]',
                'accent',
            ),
            (bx, f'Inputs as entered {e8(self.baseline)}', 'text-secondary'),
        ):
            tw = fm.horizontalAdvance(text)
            left = min(max(x - tw / 2, 0.0), w - tw)
            p.setPen(t.q(tone))
            p.drawText(QRectF(left, 0, tw + 1, self.LABEL_H), Qt.AlignmentFlag.AlignVCenter, text)
        p.end()


class BarChip(QWidget):
    """The legend key for the solid sample bars."""

    def __init__(self, t: Theme):
        super().__init__()
        self.t = t
        self.setFixedSize(10, 20)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(1, 5, 8, 10), 1.5, 1.5)
        p.fillPath(path, bar_fill(self.t, True))
        p.end()


BAR_H = 8  # each index bar; a pair is two bars and a 4-px gap


def paint_bar(p: QPainter, t: Theme, rect: QRectF, total: bool) -> None:
    """One index bar in the neutral data colour (accent stays for selection and the
    input-aware result): S₁ solid, S_T a pale fill inside an edge of the same colour, so
    the pair reads as two values of one source without a second hue."""
    path = QPainterPath()
    if total:
        path.addRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 2, 2)
        p.fillPath(path, t.q('text-secondary', 0.24 if t.dark else 0.16))  # same weight on both surfaces
        p.strokePath(path, QPen(t.q('text-secondary', 0.72), 1))
    else:
        path.addRoundedRect(rect, 2, 2)
        p.fillPath(path, t.q('text-secondary', 0.62))


def paint_whisker(p: QPainter, t: Theme, a: float, b: float, y: float) -> None:
    """A 95 % whisker from *a* to *b* at height *y*, with end caps."""
    p.setPen(QPen(t.q('text-primary'), 1.25))
    p.drawLine(QPointF(a, y), QPointF(b, y))
    for x in (a, b):
        p.drawLine(QPointF(x, y - 3), QPointF(x, y + 3))


class IndexChart(QWidget):
    """Sobol' indices per source as a pair of bars from zero, S₁ above S_T, each with its
    own 95 % whisker; the two values in tabular figures on the right. A heading row names
    the columns, as the budget table's does: Source at the table's own x, S₁ and S_T over
    their values."""

    HEAD_H = 24
    ROW_H = 30
    AXIS_H = 24
    LAB_W = SRC_W + space(5)  # the table's Source column plus its column gap
    NUM_W, NUM_GAP = 48, 16  # each value column, and the gap between the two

    def __init__(self, t: Theme, sources: list[str], hi: float = 0.5):
        super().__init__()
        self.t, self.sources, self.hi = t, sources, hi
        self.s1, self.st = RUN['sobol_s1'][KA], RUN['sobol_st'][KA]
        self.s1_ci, self.st_ci = RUN['sobol_s1_ci'][KA], RUN['sobol_st_ci'][KA]
        self.setFixedHeight(self.HEAD_H + len(sources) * self.ROW_H + self.AXIS_H)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def paintEvent(self, _):
        t = self.t
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W = float(self.width())
        st_right = W
        s1_right = W - self.NUM_W - self.NUM_GAP
        x0 = float(self.LAB_W)
        w = s1_right - self.NUM_W - space(6) - x0

        def X(v: float) -> float:
            return x0 + max(0.0, min(v, self.hi)) / self.hi * w

        n = len(self.sources)
        top = float(self.HEAD_H)
        bottom = top + n * self.ROW_H
        # heading row and its rule, as in the table below
        ter = t.q('text-tertiary')
        C.paint_rich(p, QRectF(0, 0, self.LAB_W, self.HEAD_H), 'Source', 'label', ter)
        C.paint_rich(p, QRectF(s1_right - self.NUM_W, 0, self.NUM_W, self.HEAD_H), S('1', 10), 'label', ter, right=True)
        C.paint_rich(p, QRectF(st_right - self.NUM_W, 0, self.NUM_W, self.HEAD_H), S('T', 10), 'label', ter, right=True)
        p.setPen(QPen(t.q('border'), 1))
        p.drawLine(QPointF(0, top - 0.5), QPointF(W, top - 0.5))
        # grid and axis
        ticks = [i / 10 for i in range(int(self.hi * 10) + 1)]
        p.setFont(font('small-number'))
        for tk in ticks:
            x = X(tk)
            p.setPen(QPen(t.q('border-strong' if tk == 0 else 'grid'), 1))
            p.drawLine(QPointF(x, top), QPointF(x, bottom))
            p.setPen(ter)
            p.drawText(QRectF(x - 20, bottom + 6, 40, 16), Qt.AlignmentFlag.AlignHCenter, f'{tk:g}')
        right = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight
        for i, s in enumerate(self.sources):
            cy = top + i * self.ROW_H + self.ROW_H / 2
            C.paint_rich(p, QRectF(0, cy - 10, self.LAB_W, 20), name(s), 'body', t.q('text-primary'))
            # the pair: S1 above the row's centre, S_T below it, 4 px apart
            pair = (
                (self.s1[s], self.s1_ci[s], cy - 2 - BAR_H / 2, False),
                (self.st[s], self.st_ci[s], cy + 2 + BAR_H / 2, True),
            )
            for value, (lo, hi_), y, total in pair:
                bar = QRectF(X(0), y - BAR_H / 2, max(X(value) - X(0), 2), BAR_H)
                paint_bar(p, t, bar, total)
                paint_whisker(p, t, X(lo), X(hi_), y)
            p.setFont(font('number'))
            p.setPen(t.q('text-primary'))
            p.drawText(QRectF(s1_right - self.NUM_W, cy - 10, self.NUM_W, 20), right, share(self.s1[s]))
            p.drawText(QRectF(st_right - self.NUM_W, cy - 10, self.NUM_W, 20), right, share(self.st[s]))
        p.end()


class IndexLegend(QWidget):
    """Legend chips drawn with the chart's own marks."""

    ITEMS = (('first', S('1', 10) + ' first order'), ('total', S('T', 10) + ' total'), ('whisker', '95 % interval'))
    CHIP, GAP = 22, 16

    def __init__(self, t: Theme):
        super().__init__()
        self.t = t
        widths = [self.CHIP + C.rich_width(txt, 'small') for _, txt in self.ITEMS]
        self.setFixedSize(math.ceil(sum(widths) + self.GAP * (len(widths) - 1)), 20)

    def paintEvent(self, _):
        t = self.t
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        x, cy = 0.0, self.height() / 2
        for kind, txt in self.ITEMS:
            if kind == 'whisker':
                paint_whisker(p, t, x + 1, x + 15, cy)
            else:
                paint_bar(p, t, QRectF(x, cy - BAR_H / 2, 16, BAR_H), kind == 'total')
            tw = C.paint_rich(p, QRectF(x + self.CHIP, 0, 300, self.height()), txt, 'small', t.q('text-secondary'))
            x += self.CHIP + tw + self.GAP
        p.end()


class Banner(QWidget):
    """A message across the canvas in the style of the Fit results callout (tinted fill,
    1 px border, icon, bold title, body, trailing link), with an optional second line under
    the title. *tone* is 'warning' or 'neutral'."""

    def __init__(self, t: Theme, tone: str, title: str, body: str, more: str = '', action: str | None = None):
        super().__init__()
        self.t, self.tone = t, tone
        ic = QLabel()
        ic.setPixmap(
            icons.pixmap(
                'alert' if tone == 'warning' else 'info', t['warning' if tone == 'warning' else 'text-secondary'], 16
            )
        )
        ic.setFixedSize(16, 16)
        first = [C.label(title, 'body-strong'), C.label(body, 'body', 'secondary'), None]
        if action:
            first.append(C.link_button(action))
        lines = [C.hbox(*first, spacing=3)]
        if more:
            extra = C.label(more, 'body', 'secondary', rich=True)
            extra.setWordWrap(True)
            lines.append(extra)
        self.setLayout(
            C.hbox(C.vbox(1, ic, None, spacing=0), C.vbox(*lines, spacing=0), spacing=3, margins=(4, 3, 4, 3))
        )

    def paintEvent(self, _):
        t = self.t
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 8, 8)
        warn = self.tone == 'warning'
        p.fillPath(path, t.q('warning-bg' if warn else 'bg-subtle'))
        p.setPen(QPen(t.q('warning-border' if warn else 'border'), 1))
        p.drawPath(path)
        p.end()


# ── Canvas ─────────────────────────────────────────────────────────────────────────


def hero(t: Theme) -> QWidget:
    """The spread is the answer this view gives, so it is the hero; the samples' centre is
    a secondary line, never set as large as a reported Ka."""
    b = RUN['budget'][KA]
    sec = t['text-secondary']
    title = C.label(f'Spread of K{sub("a", 10)} guest from the stated inputs', 'label', 'secondary', rich=True)
    title.setFixedHeight(20)  # the height of the key row beside it, so the two read as one line
    value = C.label(
        f'×/÷{THIN}{10 ** b["sd"]:.2f}'
        f'<span style="font-size:13px; font-weight:400; color:{sec}">&nbsp;&nbsp;1 SD · {b["sd"]:.3f} decades</span>',
        'title',
        rich=True,
    )
    value.setFixedHeight(32)
    value.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)
    centre = C.label(
        f'<span style="color:{sec}">Centred on</span> <b>{sci(RUN["sample_param_stats"][KA]["linear"]["median"])} M⁻¹</b>'
        f'<span style="color:{sec}">, the fit at the inputs as entered</span>',
        'number',
        rich=True,
    )
    centre.setWordWrap(True)
    left = QWidget()
    left.setFixedWidth(264)
    left.setLayout(C.vbox(title, value, 1, centre, None, spacing=1))

    ka = np.array(RUN['sample_ka'][KA])
    p5, p95 = np.percentile(ka, [5, 95])
    hist = SampleHistogram(t, ka, RUN['baseline_ka'][KA], [1e8, 1.5e8, 2e8, 3e8, 4e8, 5e8])
    key = C.hbox(
        BarChip(t),
        C.label(f'Middle 90 % of samples span a {p95 / p5:.2f}-fold range', 'small', 'secondary'),
        None,
        C.link_button('Plot against each source  →'),
        spacing=2,
    )
    right = C.vbox(key, hist, None, spacing=2)
    w = QWidget()
    w.setLayout(C.hbox(left, right, spacing=7))
    return w


def message(t: Theme) -> Banner:
    """The conflict warning when the fit reports one (worded as on Fit results, naming no
    input); otherwise the neutral note that the spread is not a confidence interval."""
    if CONFLICT:
        return Banner(
            t,
            'warning',
            'Inputs conflict',
            'Together, the inputs moved further from their entered values than you stated.',
            f'The samples centre on the inputs as entered, so they show how far the stated inputs move '
            f'K{sub("a", 10)} guest, not where it lies.',
            'Review in Ka confidence',
        )
    return Banner(
        t,
        'neutral',
        'Not a confidence interval',
        'Every sample counts the same; the input-aware interval also weighs the data.',
        action='Compare in Fit results',
    )


def index_block(t: Theme) -> QWidget:
    sources = ordered_sources()
    head = C.hbox(C.label('Share of the variance, by source', 'body-strong'), None, IndexLegend(t), spacing=3)
    chart = IndexChart(t, sources)
    s1, stt = RUN['sobol_s1'][KA], RUN['sobol_st'][KA]
    s1_ci, st_ci = RUN['sobol_s1_ci'][KA], RUN['sobol_st_ci'][KA]
    below = [s for s in sources if stt[s] < s1[s]]
    foot = None
    if below:
        # A true total order is never below its first order: the order of the two bars
        # comes from the estimates, and the whiskers say whether sampling covers the gap.
        names = ', '.join(name(s, 10) for s in below)
        apart = any(st_ci[s][1] < s1_ci[s][0] for s in below)
        T, one = S('T', 10), S('1', 10)
        said = (
            'The gap is wider than the whiskers span: take these two indices as unreliable and run again with more samples.'
            if apart
            else 'The two agree within their whiskers, so it acts almost entirely on its own.'
        )
        foot = C.label(
            f'{names}: {T} comes out just below {one}, which a true total never does. {said}',
            'small',
            'tertiary',
            rich=True,
        )
        foot.setWordWrap(True)
    w = QWidget()
    items = [head, 3, chart]
    if foot is not None:
        items += [1, foot]
    w.setLayout(C.vbox(*items, spacing=0))
    return w


def budget_block(t: Theme) -> QWidget:
    """What each source does to the spread in absolute terms. Its share of the variance is
    the chart above, whisker and all, so the table carries the columns the chart does not."""
    b = RUN['budget'][KA]
    rows_by = {r['source']: r for r in b['rows']}
    e3 = 1e3
    none = '–'

    def ci(lo, hi, f):
        return f'<span style="color:{t["text-tertiary"]}">[{signed(lo, f)}, {signed(hi, f)}]</span>'

    head = C.hbox(
        C.label('Variance budget', 'body-strong'),
        None,
        C.label(f'log₁₀ K{sub("a", 10)} guest  ·  [95 % sampling interval]', 'small', 'tertiary', rich=True),
        spacing=3,
    )
    g = QGridLayout()
    g.setContentsMargins(0, 0, 0, 0)
    g.setHorizontalSpacing(space(5))
    g.setVerticalSpacing(0)
    headers = ['Source', 'Stated', 'Elasticity', 'Variance (×10⁻³ decades²)', 'Spread if exact (decades)']
    right = {2, 3, 4}
    for c, h in enumerate(headers):
        lbl = C.label(h, 'label', 'tertiary', rich=True)
        lbl.setFixedHeight(24)
        if c in right:
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        g.addWidget(lbl, 0, c)
    g.addWidget(C.hairline(), 1, 0, 1, len(headers))

    lines = []
    for s in ordered_sources():
        r = rows_by[s]
        lines.append(
            [
                name(s),
                RUN['stated'][s],
                signed(r['elasticity'], '+.2f'),
                f'{r["variance"] * e3:.2f} {ci(r["variance_ci"][0] * e3, r["variance_ci"][1] * e3, ".2f")}',
                f'{r["sd_if_exact"]:.3f} {ci(*r["sd_if_exact_ci"], ".3f")}',
            ]
        )
    lines.append(['Interactions', none, none, signed(b['interactions'] * b['variance'] * e3, '.4f'), none])
    # The total of the variance is a sum; the spread left with every source exact is no
    # entry (it would be zero), so the total row writes none there, as Interactions does.
    total = [
        'All sources',
        none,
        none,
        f'{b["variance"] * e3:.2f} {ci(b["variance_ci"][0] * e3, b["variance_ci"][1] * e3, ".2f")}',
        none,
    ]
    row = 2
    for i, cells in enumerate(lines + [total]):
        is_total = i == len(lines)
        if is_total:
            g.addWidget(C.hairline(), row, 0, 1, len(headers))
            row += 1
        for c, text in enumerate(cells):
            role = (
                ('body-strong' if is_total else 'body')
                if c == 0
                else ('number-strong' if is_total and text != none else 'number')
            )
            tone = 'secondary' if (c == 1 or text == none or (i == len(lines) - 1 and not is_total)) else None
            lbl = C.label(text, role, tone, rich=True)
            lbl.setFixedHeight(28)
            if c in right:
                lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            g.addWidget(lbl, row, c)
        row += 1
        if not is_total and i < len(lines) - 1:
            g.addWidget(C.hairline(), row, 0, 1, len(headers))
            row += 1
    # Source at the chart's name width, so Stated starts where the chart's bars do; the
    # spare width goes to Elasticity, a right-aligned column.
    g.setColumnMinimumWidth(0, SRC_W)
    g.setColumnStretch(2, 1)
    table = QWidget()
    table.setLayout(g)
    w = QWidget()
    w.setLayout(C.vbox(head, 3, table, spacing=0))
    return w


def what_if_block(t: Theme) -> QWidget:
    src = ordered_sources()[0]  # the largest share: the question worth asking first
    stated = RUN['stated_pct'][src]
    a = RUN['what_if'][KA][f'{src}@0.5']
    before = RUN['budget'][KA]['sd']
    after = a['sd_reweighted']
    sec = t['text-secondary']
    controls = C.hbox(
        C.label('Reduce', 'body', 'secondary'),
        C.Dropdown(t, name(src), 168),
        C.label('to', 'body', 'secondary'),
        C.Dropdown(t, f'σ {stated / 2:g} %', 84, align_right=True),
        3,
        C.label(
            f'<span style="color:{sec}">and the spread of K{sub("a", 10)} guest shrinks from</span> '
            f'×/÷{THIN}{10**before:.2f} <span style="color:{sec}">to</span> ×/÷{THIN}{10**after:.2f}',
            'number',
            rich=True,
        ),
        None,
        spacing=3,
    )
    how = C.label(
        f'<span style="color:{sec}">{before:.3f} → {after:.3f} decades; {name(a["largest_after"], 10)} would then be '
        f'the largest item.</span> Read from the samples re-weighted to the narrower uncertainty '
        f'({a["effective_samples"]:,.0f} effective samples); the first-order formula gives {a["sd"]:.3f}.',
        'small',
        'tertiary',
        rich=True,
    )
    how.setWordWrap(True)
    w = QWidget()
    w.setLayout(C.vbox(C.label('What if one source were known better', 'body-strong'), 3, controls, 2, how, spacing=0))
    return w


def canvas(t: Theme) -> QWidget:
    body = QWidget()
    body.setObjectName('Canvas')
    body.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
    lay = C.vbox(
        hero(t),
        5,
        message(t),
        6,
        index_block(t),
        6,
        budget_block(t),
        6,
        what_if_block(t),
        None,
        spacing=0,
        margins=(6, 5, 6, 4),
    )
    body.setLayout(lay)
    scroll = QScrollArea()
    scroll.setObjectName('Canvas')
    scroll.setWidget(body)
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    return scroll


# ── Inspector ──────────────────────────────────────────────────────────────────────


def wrapped(text: str, role: str, tone: str) -> QLabel:
    """A caption that wraps, so it never widens the inspector past its column."""
    lbl = C.label(text, role, tone)
    lbl.setWordWrap(True)
    return lbl


def stat(name: str, value: str, sub_: str = '') -> QWidget:
    w = QWidget()
    items = [C.label(name, 'small', 'secondary'), C.label(value, 'number-strong')]
    if sub_:
        items.append(wrapped(sub_, 'small', 'tertiary'))
    w.setLayout(C.vbox(*items, spacing=1))
    return w


def field_label(text: str) -> QLabel:
    return C.label(text, 'label', 'secondary')


def inspector(t: Theme) -> QWidget:
    w = QWidget()
    w.setObjectName('Inspector')
    w.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
    head = QWidget()
    head.setFixedHeight(44)
    head.setLayout(
        C.hbox(C.label('Analysis settings', 'body-strong'), None, C.tool_button(t, None, 'x'), margins=(5, 0, 3, 0))
    )

    # Run settings
    n_sources = len(RUN['sources'])
    mode = C.Segmented(t, ['Sensitivity indices', 'Heatmap'], 0)
    size = C.Segmented(t, ['1024', '2048', '4096'], 0)
    size_cap = wrapped(
        f'2 × N = {2 * RUN["n_samples"]:,} samples, {RUN["n_planned"]:,} fits in all. Each step up doubles the time.',
        'small',
        'tertiary',
    )
    seed_row = C.hbox(
        C.Checkbox(t, 'Fixed seed'),
        None,
        C.Dropdown(t, '0', 120, disabled=True, chevron=False, align_right=True),
        spacing=3,
    )
    seed_cap = wrapped('Off: fresh draws each run.', 'small', 'tertiary')
    settings = QWidget()
    settings.setLayout(
        C.vbox(
            field_label('Mode'),
            mode,
            4,
            field_label('Sample size (N)'),
            size,
            size_cap,
            4,
            seed_row,
            seed_cap,
            spacing=2,
        )
    )

    # Error sources: stated once, under Input uncertainty; the canvas table lists them.
    src_w = QWidget()
    src_w.setLayout(C.vbox(C.hbox(C.link_button('Edit in Input uncertainty  →'), None), spacing=0))

    # This run
    q = QWidget()
    g = QGridLayout()
    g.setContentsMargins(0, 0, 0, 0)
    g.setHorizontalSpacing(space(5))
    g.setVerticalSpacing(space(4))
    texts = RUN['summary_texts']
    med_r2 = texts[texts.index('Median R²:') + 1]
    r2_range = texts[texts.index('R² range:') + 1].strip('[]').replace(', ', ' – ')
    top = Qt.AlignmentFlag.AlignTop
    g.addWidget(
        stat('Samples fitted', f'{RUN["n_fitted_samples"]:,} of {RUN["n_samples_total"]:,}', '2 × N'), 0, 0, top
    )
    g.addWidget(stat('Fits', f'{RUN["n_success"]:,}', f'{RUN["n_blocks_finished"]} of 8 sample blocks'), 0, 1, top)
    g.addWidget(stat('Median R² of samples', med_r2, f'range {r2_range}'), 1, 0, top)
    g.addWidget(stat('Duration', f'{RUN["seconds"]:.0f} s', f'{RUN["workers"]} worker processes'), 1, 1, top)
    g.setColumnStretch(0, 1)
    g.setColumnStretch(1, 1)
    q.setLayout(g)
    seed = C.vbox(
        C.label('Seed used', 'small', 'secondary'),
        C.label(f'{RUN["seed_used"]}', 'number-strong'),
        wrapped('Enter it under Fixed seed to repeat this run exactly.', 'small', 'tertiary'),
        spacing=1,
    )
    run_w = QWidget()
    run_w.setLayout(C.vbox(q, 4, seed, spacing=0))

    body = QWidget()
    body.setObjectName('InspectorBody')
    body.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
    body.setLayout(
        C.vbox(
            C.section(t, 'Run', settings, first=True),
            C.section(t, 'Error sources', src_w, trailing=f'{n_sources} varying'),
            C.section(t, 'This run', run_w),
            C.section(t, 'Display', None, open_=False, trailing='Log₁₀ axis'),
            None,
            spacing=0,
            margins=(5, 0, 5, 4),
        )
    )
    scroll = QScrollArea()
    scroll.setWidget(body)
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    w.setLayout(C.vbox(head, scroll, spacing=0))
    return w


def relabel_run(root: QWidget) -> None:
    """The toolbar's primary action in this view is the analysis, as in the app."""
    for b in root.findChildren(C.Button):
        if b.variant == 'primary':
            b.set_text('Run analysis')


def build(t: Theme) -> dict:
    return {
        'nav': 'Sensitivity',
        'title': 'Sensitivity',
        'badge': (f"Sobol' · N = {RUN['n_samples']}", 'neutral'),
        'canvas': canvas(t),
        'inspector': inspector(t),
        'overlay': relabel_run,
    }
