"""Ka confidence view (analysis): the two readings of Ka, the conflict, one profile plot holding both
profiles, and a Notes inspector.

Both profiles share one log-Ka axis. Up the plot, each is read against its own 95 % cut-off: how far
the fit falls from its best, as a share of the drop its test allows at that Ka, computed point by
point so a stepped cut-off is handled. Both curves are 0 at their best fit and cross the one line at
1 where their interval ends; a strip under the plot shows the accepted Ka of each, the split of the
as-entered interval included. ``view_confidence_shared`` draws the same curves on one shared
weighted-R² axis, built from the pieces here.

The fit is scored differently by the two curves: the as-entered one by weighted R², the input-aware
one by weighted R² less the penalty for moving the inputs (``1 - exp(P/n)/SS_tot`` with
``P = n log S + z'z``, core/pipeline/input_aware.py). That score is not the weighted R² of any fit,
so the view never names it so: the plot's axis is the share of the allowed drop, and the header
gives a best weighted R² for the as-entered reading only, as the app's own summary does.

Spec note for the app: the input-aware profile is solved on a coarse grid (54 nodes here, about a
dozen in view), and this axis magnifies it about 9000-fold against weighted R², so straight runs
between nodes read as features of the data. The mock marks the nodes rather than interpolating.
Before this axis ships, the app must refine the input-aware grid against the normalised statistic,
with a tolerance in units of the allowed drop rather than in R².

Every number comes from demo.json (the real IDA demo fit and its ProfileWorker output) or from
data/*.json, which the app's own code wrote (dump_confidence.py drives the real
IdentifiabilityWidget; derive_confidence.py and derive_readout.py run its formatters).
"""

from __future__ import annotations

import math

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QFontMetrics, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QGridLayout, QLabel, QScrollArea, QSizePolicy, QWidget

from gui.design import components as C
from gui.design import icons
from gui.design.plot_theme import apply_plot_theme, px
from gui.design.tokens import Theme, font, space

from .common import DEMO, THIN, load, sub

TEXTS = load('confidence_texts.json')
NUM = load('confidence_numbers.json')
READOUT = load('confidence_readout.json')
PROF = DEMO['profile']['profiles']['Ka_guest']
COND, AWARE = PROF['conditional'], PROF['input_aware']
HEAD = DEMO['headline']


E8 = 1e8
KA = f'K{sub("a", 10)}'
X_TICKS = [1, 1.5, 2, 3, 4, 5]
X_TITLE = f'{KA} guest (10⁸ M⁻¹, log scale)'
# Default view, framed as the app frames it: every interval and best fit, plus a fifth of
# that span on either side so the curves are seen rising past their cut-offs.
_lo = math.log10(min(HEAD['low_per_M'], COND['interval_per_M']['low']))
_hi = math.log10(max(HEAD['high_per_M'], COND['interval_per_M']['high']))
X_RANGE = (_lo - 0.2 * (_hi - _lo), _hi + 0.2 * (_hi - _lo))
RIGHT_X = X_RANGE[1] - 0.008  # right-aligned in-plot labels end here
# Up the normalised plot: best fit at 0, the cut-off at 1, and room for the curves to be seen leaving.
REL_Y, REL_TICKS = (-0.3, 3.3), [0, 1, 2, 3]


def e8(v: float) -> str:
    return f'{v / E8:.2f}'


def unit_html(sec: str, size: int = 20) -> str:
    return f'<span style="font-size:{size}px; font-weight:400; color:{sec}">&nbsp;M⁻¹</span>'


def row(*items, spacing: int = 3) -> QWidget:
    w = QWidget()
    w.setLayout(C.hbox(*items, None, spacing=spacing))
    return w


# ── Header: the two readings of Ka guest ────────────────────────────────────────────


def reading(
    t: Theme,
    tag: tuple[str, str],
    value: str,
    role: str,
    lo: float,
    hi: float,
    pct: list[str],
    trailing_badge: tuple[str, str] | None = None,
    r2: str | None = None,
) -> list[QWidget]:
    """One reading of Ka guest as the rows of a header column: name + reading badge, value, 95 % interval
    (a property badge such as Split after it), its reach, and the best weighted R² where the reading has one."""
    sec, ter = t['text-secondary'], t['text-tertiary']
    head = row(C.label(f'{KA} guest', 'label', 'secondary', rich=True), C.badge(*tag))
    val = C.label(f'{value}{unit_html(sec, 20 if role == "metric" else 16)}', role, rich=True)
    val.setFixedHeight(36)
    val.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)
    # Bottom-aligned values of two sizes share a baseline once the smaller is lifted by the difference in descent.
    val.setContentsMargins(0, 0, 0, QFontMetrics(font('metric')).descent() - QFontMetrics(font(role)).descent())
    iv = C.label(
        f'<span style="color:{sec}">95 % interval</span>&nbsp;&nbsp;{e8(lo)} – {e8(hi)}{THIN}×{THIN}10⁸ M⁻¹',
        'number',
        rich=True,
    )
    if trailing_badge:
        iv = row(iv, C.badge(*trailing_badge))
    reach = f'{pct[0]} / {pct[1]}'.replace('%', f'{THIN}%')
    rows = [
        head,
        val,
        iv,
        C.label(f'<span style="color:{ter}">{reach} of the best fit</span>', 'small-number', rich=True),
    ]
    if r2:
        rows.append(C.label(f'<span style="color:{sec}">Best weighted R²</span>&nbsp;&nbsp;{r2}', 'number', rich=True))
    return rows


def header(t: Theme) -> QWidget:
    """The input-aware and the as-entered reading side by side, one grid so their rows share baselines."""
    a, c, iv = NUM['aware'], NUM['conditional'], COND['interval_per_M']
    columns = (
        reading(
            t,
            ('Input-aware', 'accent'),
            f'{e8(a["estimate"])}{THIN}×{THIN}10⁸',
            'metric',
            HEAD['low_per_M'],
            HEAD['high_per_M'],
            a['pct'],
        ),
        reading(
            t,
            ('Inputs as entered', 'neutral'),
            f'{e8(COND["best_ka_per_M"])}{THIN}×{THIN}10⁸',
            'title',
            iv['low'],
            iv['high'],
            c['pct'],
            trailing_badge=('Split', 'neutral'),
            r2=c['best_r2'],
        ),
    )
    g = QGridLayout()
    g.setContentsMargins(0, 0, 0, 0)
    g.setHorizontalSpacing(space(6))
    g.setVerticalSpacing(space(1))
    for col, rows in zip((0, 2), columns):
        for r, w in enumerate(rows):
            w.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            g.addWidget(w, r, col)
    g.addWidget(C.hairline(vertical=True), 0, 1, max(map(len, columns)), 1)
    g.setColumnStretch(0, 1)
    g.setColumnStretch(2, 1)
    w = QWidget()
    w.setLayout(g)
    return w


# ── Profile data ────────────────────────────────────────────────────────────────────


def best_r2(prof: dict) -> float:
    """Top of the profile's curve (the estimate is a grid node)."""
    return float(np.nanmax(np.array(prof['r2'], float)))


def _share(prof: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """log10 Ka, (R²_best − R²) / (R²_best − R²_cut) per grid node, and the cut-off per node."""
    lg = np.log10(np.array(prof['grid_per_M']))
    r2, cut = np.array(prof['r2'], float), np.array(prof['r2_cut'], float)
    best = best_r2(prof)
    return lg, (best - r2) / (best - cut), cut


def relative_drop(prof: dict) -> tuple[np.ndarray, np.ndarray]:
    """The share of the allowed drop along the profile: 0 at the best fit, 1 where it meets its cut-off.

    Where the cut-off steps, the statistic jumps; the curve is broken there (nan) rather than drawn
    as a steep slope.
    """
    lg, y, cut = _share(prof)
    steps = np.flatnonzero(np.diff(cut) != 0) + 1
    return np.insert(lg, steps, np.nan), np.insert(y, steps, np.nan)


def risers(prof: dict) -> list[tuple[float, float, float]]:
    """Where the statistic jumps because the cut-off steps: (log10 Ka of the last node before the step,
    y there, y at the next node). The last node is where an accepted stretch ends, so the riser, the
    strip and the notes name the same Ka."""
    lg, y, cut = _share(prof)
    return [(lg[i], y[i], y[i + 1]) for i in np.flatnonzero(np.diff(cut) != 0)]


def nodes(prof: dict) -> tuple[np.ndarray, np.ndarray]:
    """The grid nodes the profile was solved on, each once (the grid repeats a node where a search cell
    meets the fill), as log10 Ka and share of the allowed drop."""
    lg, y, _ = _share(prof)
    lg, first = np.unique(lg, return_index=True)
    return lg, y[first]


def cut_steps(prof: dict) -> np.ndarray:
    """Bin edges of the stepped cut-off: midway between grid nodes in log Ka."""
    lg = np.log10(np.array(prof['grid_per_M']))
    return np.concatenate([lg[:1], 0.5 * (lg[:-1] + lg[1:]), lg[-1:]])


def crop(x: np.ndarray, *ys: np.ndarray, pad: float = 0.25):
    m = np.isnan(x) | ((x >= X_RANGE[0] - pad) & (x <= X_RANGE[1] + pad))
    return (x[m], *(y[m] for y in ys))


# ── Plot primitives ─────────────────────────────────────────────────────────────────


def add_band(pi, t: Theme, lo: float, hi: float):
    """The reported interval as a tint; lighter on dark, where the bright accent would read as a fill."""
    band = pg.LinearRegionItem(
        values=(math.log10(lo), math.log10(hi)),
        movable=False,
        brush=pg.mkBrush(t.q('accent', 0.07 if t.dark else 0.08)),
        pen=pg.mkPen(None),
    )
    for line in band.lines:
        line.setPen(pg.mkPen(None))
    band.setZValue(-11)
    pi.addItem(band, ignoreBounds=True)


def dotted(t: Theme, color: str) -> QPen:
    pen = pg.mkPen(t.q(color), width=px(1.25), style=Qt.PenStyle.DashLine)
    pen.setDashPattern([2, 3])
    return pen


def add_curve(pi, t: Theme, x: np.ndarray, y: np.ndarray, color: str, width: float):
    pen = pg.mkPen(t.q(color), width=px(width))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    item = pg.PlotDataItem(x, y, pen=pen, antialias=True, connect='finite')
    item.setZValue(3)
    pi.addItem(item, ignoreBounds=True)


def _diamond() -> QPainterPath:
    """A square diamond, the legend's own glyph (pyqtgraph's 'd' is a narrow one)."""
    path = QPainterPath()
    path.moveTo(0, -0.5)
    path.lineTo(0.5, 0)
    path.lineTo(0, 0.5)
    path.lineTo(-0.5, 0)
    path.closeSubpath()
    return path


DIAMOND = _diamond()


def add_marker(pi, t: Theme, x: float, y: float, color: str, symbol=DIAMOND, size: float = 14, z: float = 4):
    m = pg.ScatterPlotItem(
        x=[x],
        y=[y],
        symbol=symbol,
        size=size,
        brush=pg.mkBrush(t.q(color)),
        pen=pg.mkPen(t['bg-surface'], width=px(2)),
    )
    m.setZValue(z)
    pi.addItem(m, ignoreBounds=True)


def add_tag(
    pi, t: Theme, text: str, x: float, y: float, anchor=(1, 1), role: str = 'small-number', filled: bool = False
) -> pg.TextItem:
    """An in-plot label: always secondary text, so it never reads as a link; the mark beside it carries the
    colour. *filled* backs it with the plot's own surface, for a label that marks may run up to."""
    item = pg.TextItem(text, color=t.q('text-secondary'), anchor=anchor, fill=t.q('bg-surface') if filled else None)
    item.setFont(font(role))
    item.setZValue(5)
    item.setPos(x, y)
    pi.addItem(item, ignoreBounds=True)
    return item


def profile_axes(
    t: Theme, y_title: str, y_range: tuple[float, float], ticks: list[tuple[float, str]], left_width: int
) -> pg.PlotWidget:
    """The profile plot: log-Ka x without values (the strip under it carries them), y as given."""
    pw = pg.PlotWidget()
    pw.setFrameShape(pg.QtWidgets.QFrame.Shape.NoFrame)
    pi = apply_plot_theme(pw, t, '', y_title, [v for v, _ in ticks])
    left = pi.getAxis('left')
    left.setTicks([ticks])
    left.setWidth(left_width)
    ax = pi.getAxis('bottom')
    ax.setTicks([[(math.log10(v * E8), f'{v:g}') for v in X_TICKS]])
    ax.setStyle(showValues=False, tickLength=4)
    ax.showLabel(False)
    ax.setHeight(6)
    pi.setXRange(*X_RANGE, padding=0)
    pi.setYRange(*y_range, padding=0)
    pi.getViewBox().setMouseEnabled(x=False, y=False)
    return pw


def interval_strip(t: Theme, above: pg.PlotWidget, left_width: int) -> pg.PlotWidget:
    """The accepted Ka of each profile as a lane under the plot, on its x axis: one stretch input-aware,
    two at the inputs as entered.

    Each lane's name sits at the left edge, and its track starts after the name, so no line runs
    through the text. Should the name reach a lane's first bar, the axis opens further left until
    it clears it (re-run on every resize; it does not trigger at this frame).
    """
    pw = pg.PlotWidget()
    pw.setFrameShape(pg.QtWidgets.QFrame.Shape.NoFrame)
    pi = apply_plot_theme(pw, t, X_TITLE, '', [])
    left = pi.getAxis('left')
    left.setTicks([[]])
    left.setLabel(None)
    left.showLabel(False)
    left.setPen(pg.mkPen(None))
    left.setWidth(left_width)
    pi.getAxis('bottom').setTicks([[(math.log10(v * E8), f'{v:g}') for v in X_TICKS]])
    pi.setXLink(above.getPlotItem())
    pi.setXRange(*X_RANGE, padding=0)
    pi.setYRange(-0.75, 1.75, padding=0)
    vb = pi.getViewBox()
    vb.setMouseEnabled(x=False, y=False)
    lanes = []
    for y, name, stretches, color in (
        (1, 'Input-aware', [(HEAD['low_per_M'], HEAD['high_per_M'])], 'accent'),
        (0, 'Inputs as entered', NUM['conditional']['stretches_per_M'], 'text-secondary'),
    ):
        track = pg.PlotDataItem([X_RANGE[0], X_RANGE[1]], [y, y], pen=pg.mkPen(t['border'], width=px(1)))
        track.setZValue(-5)
        pi.addItem(track, ignoreBounds=True)
        for lo, hi in stretches:
            pen = pg.mkPen(t.q(color), width=px(6))
            pen.setCapStyle(Qt.PenCapStyle.FlatCap)
            bar = pg.PlotDataItem([math.log10(lo), math.log10(hi)], [y, y], pen=pen)
            bar.setZValue(2)
            pi.addItem(bar, ignoreBounds=True)
        tag = add_tag(pi, t, name, X_RANGE[0], y, anchor=(0, 0.5), role='small', filled=True)
        lanes.append((y, tag, track, math.log10(stretches[0][0])))

    def clear_names():
        (x0, x1), dx = vb.viewRange()[0], vb.viewPixelSize()[0]
        if not (dx > 0 and math.isfinite(dx)):
            return
        for y, tag, track, first_bar in lanes:
            tag.setPos(x0 + space(1) * dx, y)
            end = x0 + (space(1) + tag.boundingRect().width() + space(2)) * dx
            if end > first_bar:
                vb.setXRange(x0 - 1.1 * (end - first_bar), x1, padding=0)
                return  # the range change runs this again
            track.setData([end, x1], [y, y])

    vb.sigResized.connect(clear_names)
    vb.sigXRangeChanged.connect(clear_names)
    clear_names()
    pw.setFixedHeight(44 + 52)
    return pw


def stack(main: pg.PlotWidget, strip: pg.PlotWidget) -> QWidget:
    w = QWidget()
    lay = C.vbox(spacing=0)
    lay.addWidget(main, 1)
    lay.addSpacing(space(2))
    lay.addWidget(strip)
    w.setLayout(lay)
    return w


# ── The normalised plot ─────────────────────────────────────────────────────────────


def raised(p: QPainter, t: Theme, rect: QRectF, radius: float):
    """The raised surface of the pointer's card and chip: fill and a 1-px border."""
    path = QPainterPath()
    path.addRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
    p.fillPath(path, t.q('bg-raised'))
    p.setPen(QPen(t.q('border-strong' if t.dark else 'border'), 1))
    p.drawPath(path)


class Readout(QWidget):
    """What the pointer reads at one Ka: each curve's height there, as plotted, and whether that Ka is accepted."""

    def __init__(self, t: Theme, parent: QWidget):
        super().__init__(parent)
        self.t = t
        g = QGridLayout()
        g.setContentsMargins(space(4), space(3), space(4), space(3))
        g.setHorizontalSpacing(space(3))
        g.setVerticalSpacing(space(1))
        head = C.label(f'Share of allowed drop at {e8(READOUT["ka_per_M"])}{THIN}×{THIN}10⁸ M⁻¹', 'label', 'secondary')
        g.addWidget(head, 0, 0, 1, 4)
        digits = QFontMetrics(font('small-number')).horizontalAdvance('0.00')
        for r, (key, name, color) in enumerate(
            (('aware', 'Input-aware', 'accent'), ('conditional', 'Inputs as entered', 'text-secondary')), start=1
        ):
            reading_ = READOUT[key]
            accepted = reading_['ratio'] <= 1
            g.addWidget(Swatch(t, color), r, 0)
            g.addWidget(C.label(name, 'small'), r, 1)
            # One width and tabular figures, right-aligned: the decimal points line up.
            val = C.label(f'{reading_["ratio"]:.2f}', 'small-number')
            val.setFixedWidth(digits)
            val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            g.addWidget(val, r, 2)
            g.addWidget(
                C.label('accepted' if accepted else 'rejected', 'small', None if accepted else 'secondary'), r, 3
            )
        g.setColumnStretch(1, 1)
        self.setLayout(g)
        self.adjustSize()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        raised(p, self.t, QRectF(self.rect()), 8)
        p.end()


class KaChip(QWidget):
    """The pointer's Ka at the top end of its hairline, in the card's surface, so the two read as one."""

    def __init__(self, t: Theme, text: str, parent: QWidget):
        super().__init__(parent)
        self.t, self.text = t, text
        self.setFixedSize(QFontMetrics(font('small-number')).horizontalAdvance(text) + 2 * space(3), 18)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        raised(p, self.t, QRectF(self.rect()), 9)
        p.setFont(font('small-number'))
        p.setPen(self.t.q('text-primary'))
        p.drawText(QRectF(self.rect()), Qt.AlignmentFlag.AlignCenter, self.text)
        p.end()


class Swatch(QWidget):
    """A 12-px stroke in a curve's colour."""

    def __init__(self, t: Theme, color: str):
        super().__init__()
        self.t, self.color = t, color
        self.setFixedSize(12, 16)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(self.t.q(self.color), 2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawLine(QPointF(1, 8), QPointF(11, 8))
        p.end()


def normalised_plot(t: Theme) -> tuple[QWidget, callable]:
    """One plot, both profiles, each over its own cut-off; returns the plot and its overlay hook."""
    ticks = [(v, f'{v:g}') for v in REL_TICKS]
    main = profile_axes(t, 'Share of allowed drop', REL_Y, ticks, left_width=48)
    pi = main.getPlotItem()
    add_band(pi, t, HEAD['low_per_M'], HEAD['high_per_M'])
    cut = pg.InfiniteLine(pos=1, angle=0, pen=dotted(t, 'text-secondary'), movable=False)
    cut.setZValue(1.5)
    pi.addItem(cut, ignoreBounds=True)
    add_tag(pi, t, '95 % cut-off', RIGHT_X, 1, anchor=(1, 1.05))

    for prof, color, width in ((COND, 'text-secondary', 1.75), (AWARE, 'accent', 2.25)):
        add_curve(pi, t, *crop(*relative_drop(prof)), color, width)
        # The jump where the cut-off steps, dotted so it reads as a step rather than as the curve.
        for x, y0, y1 in risers(prof):
            if X_RANGE[0] < x < X_RANGE[1]:
                riser = pg.PlotDataItem([x, x], [y0, y1], pen=dotted(t, color))
                riser.setZValue(2.9)
                pi.addItem(riser, ignoreBounds=True)
    # The input-aware profile is solved on a coarse grid: its nodes are marked, so the line reads
    # as sampled values joined straight (see the spec note in the module docstring).
    nx, ny = crop(*nodes(AWARE))
    dots = pg.ScatterPlotItem(
        x=nx, y=ny, symbol='o', size=4, brush=pg.mkBrush(t.q('accent')), pen=pg.mkPen(None), useCache=False
    )
    dots.setZValue(3.1)
    pi.addItem(dots, ignoreBounds=True)
    add_marker(pi, t, math.log10(COND['best_ka_per_M']), 0, 'text-secondary')
    add_marker(pi, t, math.log10(NUM['aware']['estimate']), 0, 'accent')

    # The pointer: a hairline at one Ka with its value at the top, a dot where it meets each curve,
    # and the readout.
    x = math.log10(READOUT['ka_per_M'])
    hair = pg.InfiniteLine(pos=x, angle=90, pen=pg.mkPen(t.q('text-tertiary', 0.8), width=px(1)), movable=False)
    hair.setZValue(4.5)
    pi.addItem(hair, ignoreBounds=True)
    for key, color in (('conditional', 'text-secondary'), ('aware', 'accent')):
        add_marker(pi, t, x, READOUT[key]['ratio'], color, symbol='o', size=9, z=5)
    readout = Readout(t, main)
    chip = KaChip(t, e8(READOUT['ka_per_M']), main)
    for w in (readout, chip):
        w.hide()

    def place(_root):
        vb = pi.getViewBox()
        rect = main.mapFromScene(vb.sceneBoundingRect()).boundingRect()
        readout.adjustSize()
        readout.move(rect.right() - readout.width() - space(3), rect.top() + space(3))
        top = main.mapFromScene(vb.mapViewToScene(QPointF(x, REL_Y[1])))
        chip.move(round(top.x() - chip.width() / 2), rect.top())
        for w in (readout, chip):
            w.show()
            w.raise_()

    return stack(main, interval_strip(t, main, left_width=48)), place


class ProfileLegend(QWidget):
    """Legend chips drawn with the plot's own marks: each curve, the accepted bars, the diamond."""

    def __init__(self, theme: Theme, items: list[tuple[str, str]]):
        super().__init__()
        self.t, self.items = theme, items
        self.setFixedHeight(20)
        fm = QFontMetrics(font('small'))
        self.setFixedWidth(sum(24 + fm.horizontalAdvance(txt) + 16 for _, txt in items) - 16)

    def paintEvent(self, _):
        t = self.t
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setFont(font('small'))
        fm = p.fontMetrics()
        x, cy = 0.0, self.height() / 2
        for kind, txt in self.items:
            if kind in ('aware', 'entered'):
                if kind == 'aware':
                    band = QPainterPath()
                    band.addRoundedRect(QRectF(x + 2, cy - 7, 14, 14), 3, 3)
                    p.fillPath(band, t.q('accent', 0.16 if t.dark else 0.14))
                pen = QPen(t.q('accent' if kind == 'aware' else 'text-secondary'), 2 if kind == 'aware' else 1.75)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                p.setPen(pen)
                p.drawLine(QPointF(x, cy), QPointF(x + 18, cy))
            elif kind == 'accepted':
                for color, dy in (('accent', -2.5), ('text-secondary', 2.5)):
                    pen = QPen(t.q(color), 3)
                    pen.setCapStyle(Qt.PenCapStyle.FlatCap)
                    p.setPen(pen)
                    p.drawLine(QPointF(x + 1, cy + dy), QPointF(x + 17, cy + dy))
            elif kind == 'best':
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(t.q('text-secondary'))
                path = QPainterPath()
                path.moveTo(x + 9, cy - 5.5)
                path.lineTo(x + 14.5, cy)
                path.lineTo(x + 9, cy + 5.5)
                path.lineTo(x + 3.5, cy)
                path.closeSubpath()
                p.drawPath(path)
            p.setPen(t.q('text-secondary'))
            p.drawText(QRectF(x + 24, 0, 400, self.height()), Qt.AlignmentFlag.AlignVCenter, txt)
            x += 24 + fm.horizontalAdvance(txt) + 16
        p.end()


LEGEND = [
    ('aware', 'Input-aware'),
    ('entered', 'Inputs as entered'),
    ('accepted', 'Accepted Kₐ'),
    ('best', 'Best fit'),
]


# ── Notes inspector ─────────────────────────────────────────────────────────────────


def body(text: str, tone: str = 'secondary') -> QLabel:
    lbl = C.label(text, 'small', tone, rich=True)
    lbl.setWordWrap(True)
    lbl.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    return lbl


def column(*items: QWidget | str, spacing: int = 2) -> QWidget:
    w = QWidget()
    lay = C.vbox(spacing=spacing)
    for it in items:
        lay.addWidget(body(it) if isinstance(it, str) else it)
    w.setLayout(lay)
    return w


def shift_rows(t: Theme) -> QWidget:
    """Input shifts in the one format of every view: entered order, bar in σ, % and σ."""
    sh = DEMO['input_shifts']
    rows = [
        (f'K{sub("a,dye")}', sh['Ka_dye']),
        ('[Host]₀', sh['h0']),
        ('[Dye]₀', sh['d0']),
        ('Guest (titrant)', sh['__titrant__']),
    ]
    w = QWidget()
    g = QGridLayout()
    g.setContentsMargins(0, 0, 0, 0)
    g.setHorizontalSpacing(space(3))
    g.setVerticalSpacing(0)
    for i, (name, s) in enumerate(rows):
        nl = C.label(name, 'body', rich=True)
        nl.setFixedHeight(28)
        bar = C.ShiftBar(t, s['z'])
        pct = C.label(f'{s["fraction"] * 100:+.1f}{THIN}%'.replace('-', '−'), 'number')
        pct.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        sig = C.label(f'{abs(s["z"]):.1f}{THIN}σ', 'small-number', 'tertiary')
        sig.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        sig.setMinimumWidth(32)
        g.addWidget(nl, i, 0)
        g.addWidget(bar, i, 1)
        g.addWidget(pct, i, 2)
        g.addWidget(sig, i, 3)
    g.setColumnStretch(0, 1)
    w.setLayout(g)
    return w


class FlagHeader(C.SectionHeader):
    """A section header with the status glyph Diagnostics marks the same finding with, after its title."""

    def __init__(self, theme: Theme, title: str, tone: str, trailing: str = ''):
        super().__init__(theme, title, True, trailing)
        self.tone = tone

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        x = 18 + QFontMetrics(font('body-strong')).horizontalAdvance(self._title) + space(3)
        icons.paint(p, 'alert-circle', self.t.q(self.tone), x, 8, 16)
        p.end()


def flagged_section(t: Theme, title: str, content: QWidget, tone: str, trailing: str) -> QWidget:
    """``C.section`` (first in its panel, open) with a flagged header."""
    w = QWidget()
    w.setLayout(C.vbox(FlagHeader(t, title, tone, trailing), 2, content, 5, spacing=0))
    return w


# The as-entered interval steps where its first accepted stretch ends: the last node before the step.
STEP_KA = NUM['conditional']['stretches_per_M'][0][1]
_S2 = NUM['conditional']['stretches_per_M'][1][0]
_IV = COND['interval_per_M']


def split_text(steps: str) -> str:
    """The Split note; *steps* names what steps down on the plot (the curve, or its cut-off)."""
    return (
        f'The as-entered range {e8(_IV["low"])} – {e8(_IV["high"])}{THIN}×{THIN}10⁸ M⁻¹ has a gap: {KA} from '
        f'{e8(STEP_KA)} to {e8(_S2)} is rejected. Up to {e8(STEP_KA)} the fit reaches the data only with a signal '
        f'coefficient held at its limit, so the test allows it a larger drop and {steps} steps down.'
    )


WEIGHTED_NOTE = TEXTS['weighted_r2_note'].replace('Fit Quality', 'Fit quality')
READING_NORMALISED = (
    f'Each curve shows how far the fit falls from its best, as a share of the drop the 95 % test allows at '
    f'that {KA}: 0 is the best fit, 1 is the cut-off. Where a curve is at or below 1, that {KA} is accepted.',
    'The fit is scored by weighted R²; with the inputs free, less a penalty for each input’s move, measured '
    'against its stated uncertainty.',
    f'Point at the plot to read both curves at any {KA}. {WEIGHTED_NOTE}',
)
SPLIT_NORMALISED = split_text('the curve')


def inspector(t: Theme, reading: tuple[str, ...], split: str) -> QWidget:
    """The Notes panel. *reading* says how the plot's height is read (its last line quieter); *split*
    explains the as-entered gap as it shows on this plot."""
    # The verdict's first sentence is the callout over the plot; the section starts where the fit put the correction.
    rest = TEXTS['verdict_sentence_plain'].split(' The fit put the correction here: ')[1]
    tail = rest.split(' — ', 1)[1]
    tail = tail[0].upper() + tail[1:]
    basis = TEXTS['notes_list_html'][1]
    basis = basis[basis.index('>') + 1 : basis.rindex('<')]
    rest_on, widened = basis.split(' The replicates leave', 1)
    widened = ('The replicates leave' + widened).replace('<b>K<sub>a(G)</sub></b>', f'{KA} guest')

    conflict = column(
        C.label('The fit put the correction here:', 'small', 'secondary'),
        shift_rows(t),
        tail,
        C.label('Bars in σ, band ±1 σ.', 'small', 'tertiary'),
    )
    inner = QWidget()
    inner.setObjectName('InspectorBody')
    inner.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
    inner.setLayout(
        C.vbox(
            flagged_section(t, 'Inputs conflict', conflict, 'warning', 'p < 0.001'),
            C.section(t, 'Reading the curves', column(*reading[:-1], body(reading[-1], 'tertiary'))),
            C.section(t, 'Split interval', column(split), trailing='Inputs as entered'),
            C.section(t, 'What the intervals rest on', column(rest_on)),
            C.section(t, 'Widened by the noise law', column(widened), trailing='about 1.3-fold'),
            None,
            spacing=0,
            margins=(5, 0, 5, 4),
        )
    )
    scroll = QScrollArea()
    scroll.setObjectName('InspectorScroll')
    scroll.setWidget(inner)
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    head = QWidget()
    head.setFixedHeight(44)
    head.setLayout(
        C.hbox(
            C.label('Notes', 'body-strong'),
            None,
            C.link_button('Reading this plot  →'),
            2,
            C.tool_button(t, None, 'x'),
            margins=(5, 0, 3, 0),
        )
    )
    w = QWidget()
    w.setObjectName('Inspector')
    w.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
    w.setLayout(C.vbox(head, scroll, spacing=0))
    return w


# ── Canvas ──────────────────────────────────────────────────────────────────────────


def canvas(t: Theme, plot: QWidget, legend: list[tuple[str, str]]) -> QWidget:
    """Header, the conflict (worded as on Fit results, whose callout links here), then the profile."""
    w = QWidget()
    w.setObjectName('Canvas')
    w.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
    callout = C.Callout(
        t,
        'warning',
        'Inputs conflict',
        'Together, the inputs moved further from their entered values than you stated.',
        'Show the input shifts',
    )
    plot_head = C.hbox(
        C.label('Profile', 'body-strong'),
        None,
        ProfileLegend(t, legend),
        5,
        C.tool_button(t, None, 'maximize'),
        C.tool_button(t, None, 'image'),
        spacing=1,
    )
    lay = C.vbox(header(t), 5, callout, 6, plot_head, 2, spacing=0, margins=(6, 5, 6, 4))
    lay.addWidget(plot, 1)
    w.setLayout(lay)
    return w


BADGE = ('Profile likelihood · 95 %', 'neutral')


def build(t: Theme) -> dict:
    plot, place = normalised_plot(t)
    return {
        'nav': 'Ka confidence',
        'title': 'Ka confidence',
        'badge': BADGE,
        'canvas': canvas(t, plot, LEGEND),
        'inspector': inspector(t, READING_NORMALISED, SPLIT_NORMALISED),
        'overlay': place,
    }
