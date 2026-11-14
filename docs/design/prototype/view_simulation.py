"""Simulation window: forward simulation for experiment design, beside the fitting window.

A window of its own, opened from the main window's *Simulate…* and tied to no session:
experiment design happens before or beside a fit. It carries the main window's toolbar,
canvas | inspector split and status bar, with no session sidebar; its window buttons sit
at the left of its toolbar.

Canvas: the titration (model curve and the simulated measurement, and a measurement
file laid over them) above the speciation, both on one titrant axis; the pointer's
position reads out on both. Inspector: the binding model, one control per knob of the
registry, the titrant concentrations, the noise. Every change recomputes both plots.

Every number comes from ``data/simulation.json``, written by
``data/compute_simulation.py`` with ``core.simulation`` (``simulate_signal``,
``simulate_species``, ``simulate_dataset``, ``build_concentration_vector``). The values
are the IDA demo's entered conditions with the fit made at those inputs, as a user
would type them into this window.
"""

from __future__ import annotations

import math

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QFontMetrics, QPainter, QPen
from PyQt6.QtWidgets import QScrollArea, QSplitter, QWidget

from gui.design import components as C
from gui.design.plot_theme import apply_plot_theme, fit_line, px, scatter
from gui.design.tokens import SIZE, Theme, font, space

from . import shell
from .common import THIN, command, load, molar, sci, sub

DATA = load('simulation.json')


WINDOW_SIZE = (1280, 800)
VALUE_W, UNIT_W = 112, 76  # the knob grid: name | value | unit, shared by every row with a unit
END_W = 36  # a slider end's text column
SUP = str.maketrans('0123456789-', '⁰¹²³⁴⁵⁶⁷⁸⁹⁻')

UM = 1e6
COND, PAR, NOISE, GRID = DATA['conditions'], DATA['parameters'], DATA['noise'], DATA['grid']
X_DENSE = np.array(DATA['x_dense_M']) * UM
Y_DENSE = np.array(DATA['y_dense'])
SPECIES = {k: np.array(v) * UM for k, v in DATA['species_M'].items()}
REPLICAS = NOISE['replicas']
OVERLAY = DATA['overlay']
HOVER_UM = 3.0  # where the pointer rests in this render
HOVER_I = int(np.argmin(np.abs(X_DENSE - HOVER_UM)))
Y_SCALE = 1e-5  # signal axis in 10⁵ a.u.

# The species lines by partner, each in its species token: the dye states, the guest states, the
# free host. Solid = in a complex, dashed = free; the readout groups them under those two words.
SPECIES_STYLE = {
    'HD': ('species-dye', 2.0, False),
    'HG': ('species-guest', 2.0, False),
    'D': ('species-dye', 1.75, True),
    'G': ('species-guest', 1.75, True),
    'H': ('species-host', 1.75, True),
}
COMPLEXES, FREE = ('HD', 'HG'), ('D', 'G', 'H')


def sig3(v: float) -> str:
    return f'{v:#.3g}'.rstrip('.')


def grouped(v: float) -> str:
    return f'{v:,.0f}'.replace(',', THIN)


def decade(e: int) -> str:
    return f'10{str(e).translate(SUP)}'


def log_pos(v: float, lo: float, hi: float) -> float:
    return (math.log10(v) - math.log10(lo)) / (math.log10(hi) - math.log10(lo))


def species_pen(t: Theme, key: str) -> QPen:
    """A species' pen for the readout swatch, in widget pixels (the plot uses cosmetic pens)."""
    color, width, dashed = SPECIES_STYLE[key]
    pen = QPen(t.q(color), width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap if not dashed else Qt.PenCapStyle.FlatCap)
    if dashed:
        pen.setDashPattern([3, 2.5])
    return pen


class Readout(QWidget):
    """The pointer's readout over the species plot, and its legend: the titrant at the
    pointer, then the complexes (solid) and the free species (dashed), each group under
    its own word, every species with a swatch in its own pen and its concentration."""

    GAP = space(4)

    def __init__(self, t: Theme, x_name: str, idx: int):
        super().__init__()
        self.t, self.x_name, self.idx = t, x_name, idx
        self.groups = [('Complexes', COMPLEXES), ('Free', FREE)]
        self.setFixedHeight(20)
        self.setFixedWidth(int(self._run(None)))

    def _run(self, p: QPainter | None) -> float:
        """Lay the readout out once; paint it when given a painter, measure it either way."""
        t, h = self.t, 20.0
        x = 0.0

        def text(s: str, role: str, tone: str):
            nonlocal x
            if p is not None:
                p.setFont(font(role))
                p.setPen(t.q(tone))
                p.drawText(QRectF(x, 0, 200, h), Qt.AlignmentFlag.AlignVCenter, s)
            x += QFontMetrics(font(role)).horizontalAdvance(s)

        def divider():
            nonlocal x
            x += self.GAP
            if p is not None:
                p.fillRect(QRectF(x, h / 2 - 6, 1, 12), t.q('border'))
            x += 1 + self.GAP

        text(self.x_name, 'small', 'text-secondary')
        x += space(2)
        text(f'{X_DENSE[self.idx]:.2f} µM', 'small-number', 'text-primary')
        for gi, (word, species) in enumerate(self.groups):
            divider()
            text(word, 'small', 'text-tertiary')
            for k in species:
                x += space(3)
                if p is not None:
                    p.setPen(species_pen(t, k))
                    p.drawLine(QPointF(x + 1, h / 2), QPointF(x + 15, h / 2))
                x += 16 + space(2)
                text(k, 'small', 'text-secondary')
                x += space(2)
                text(sig3(SPECIES[k][self.idx]), 'small-number', 'text-primary')
        x += space(3)
        text('µM', 'small', 'text-tertiary')
        return x

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._run(p)
        p.end()


SETTINGS_MENU = [
    command('save', 'Save settings…', 'Ctrl+S'),
    command('open', 'Load settings…'),
    None,
    command('rotate', 'Reset to defaults'),
]
SETTINGS_NOTE = 'Saves every value, slider end and noise setting of this window to a file.'


# ── Canvas ─────────────────────────────────────────────────────────────────────────


def _crosshair(pi, t: Theme):
    pen = pg.mkPen(t.q('text-tertiary'), width=px(1), style=Qt.PenStyle.DashLine)
    pen.setDashPattern([3, 3])
    line = pg.InfiniteLine(pos=X_DENSE[HOVER_I], angle=90, pen=pen, movable=False)
    line.setZValue(1)
    pi.addItem(line, ignoreBounds=True)


def _marker(pi, t: Theme, x: float, y: float, color: str, size: float):
    m = pg.ScatterPlotItem(
        x=[x], y=[y], size=size, brush=pg.mkBrush(t.q(color)), pen=pg.mkPen(t['bg-surface'], width=px(2))
    )
    m.setZValue(6)
    pi.addItem(m, ignoreBounds=True)


def _share_x(pi):
    pi.setXRange(-0.25, 9.25, padding=0)
    pi.getAxis('bottom').setTicks([[(v, f'{v:g}') for v in range(0, 10)]])
    pi.getViewBox().setMouseEnabled(x=False, y=False)


def signal_plot(t: Theme, overlay: bool) -> pg.PlotWidget:
    pw = pg.PlotWidget()
    pw.setFrameShape(pg.QtWidgets.QFrame.Shape.NoFrame)
    pi = apply_plot_theme(pw, t, 'Guest (µM)', 'Signal (10⁵ a.u.)', [0.5, 1.0, 1.5, 2.0, 2.5, 3.0])
    x_pts = np.array((OVERLAY if overlay else DATA)['x_M' if overlay else 'x_points_M']) * UM
    for y in OVERLAY['simulated'] if overlay else DATA['simulated']:
        pi.addItem(scatter(t, x_pts, np.array(y) * Y_SCALE, 'replicate', 0.8 if t.dark else 0.55, 6))
    if overlay:  # the measurement file: hollow rings, one ink for every replicate
        for y in OVERLAY['signals']:
            rings = scatter(t, x_pts, np.array(y) * Y_SCALE, 'text-secondary', 0.75, 7, hollow=True)
            rings.setZValue(3)
            pi.addItem(rings)
    curve = fit_line(t, X_DENSE, Y_DENSE * Y_SCALE)
    curve.setZValue(4)
    pi.addItem(curve)
    _crosshair(pi, t)
    yh = Y_DENSE[HOVER_I] * Y_SCALE
    _marker(pi, t, X_DENSE[HOVER_I], yh, 'accent', 10)
    tag = pg.TextItem(f'{sci(Y_DENSE[HOVER_I])} a.u.', color=t.q('text-primary'), anchor=(0, 1.15))
    tag.setFont(font('small-number'))
    tag.setPos(X_DENSE[HOVER_I] + 0.12, yh)
    tag.setZValue(7)
    pi.addItem(tag, ignoreBounds=True)
    _share_x(pi)
    pi.setYRange(0.12, 3.08, padding=0)  # one range for both states, so the overlay changes no axis
    # Shares the species plot's titrant axis: an axis line with ticks, no values.
    ax = pi.getAxis('bottom')
    ax.setStyle(showValues=False, tickLength=4)
    ax.showLabel(False)
    ax.setHeight(6)
    return pw


def species_plot(t: Theme) -> pg.PlotWidget:
    pw = pg.PlotWidget()
    pw.setFrameShape(pg.QtWidgets.QFrame.Shape.NoFrame)
    pi = apply_plot_theme(pw, t, 'Guest (µM)', 'Concentration (µM)', [0.0, 2.0, 4.0, 6.0])
    # The dye states drawn last, so the signal's own species stay on top where curves cross.
    for key in ('H', 'G', 'HG', 'D', 'HD'):
        color, width, dashed = SPECIES_STYLE[key]
        pen = pg.mkPen(t.q(color), width=px(width))  # cosmetic: width in screen pixels
        if dashed:
            pen.setDashPattern([3, 2.5])
        else:
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        item = pg.PlotDataItem(X_DENSE, SPECIES[key], pen=pen, antialias=True)
        item.setZValue(3 if key in ('HD', 'D') else 2)
        pi.addItem(item)
    _crosshair(pi, t)
    for key in SPECIES_STYLE:
        _marker(pi, t, X_DENSE[HOVER_I], SPECIES[key][HOVER_I], SPECIES_STYLE[key][0], 8)
    _share_x(pi)
    pi.setYRange(-0.3, 6.4, padding=0)
    return pw


def canvas(t: Theme, overlay: bool) -> QWidget:
    w = QWidget()
    w.setObjectName('Canvas')
    w.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)

    if overlay:
        items = [
            ('dots', f'Simulated ({REPLICAS})'),
            ('rings', f'{OVERLAY["file"]} ({len(OVERLAY["signals"])})'),
            ('line', 'Model'),
        ]
    else:
        items = [('dots', f'Simulated replicates ({REPLICAS})'), ('line', 'Model')]
    image = C.tool_button(t, None, 'image')
    image.setToolTip('Export this plot as an image')
    titration_head = C.hbox(
        C.label('Titration', 'body-strong'),
        3,
        C.label('simulated signal', 'small', 'tertiary'),
        None,
        C.LegendRow(t, items, dot_alpha=0.8 if t.dark else 0.6),
        5,
        image,
        spacing=0,
    )
    species_head = C.hbox(
        C.label('Species', 'body-strong'),
        3,
        C.label('in the cuvette', 'small', 'tertiary'),
        None,
        Readout(t, 'Guest', HOVER_I),
        spacing=0,
    )
    lay = C.vbox(titration_head, 2, spacing=0, margins=(6, 5, 6, 4))
    lay.addWidget(signal_plot(t, overlay), 13)
    lay.addSpacing(space(5))
    lay.addLayout(species_head)
    lay.addSpacing(space(2))
    lay.addWidget(species_plot(t), 10)
    w.setLayout(lay)
    return w


# ── Inspector ──────────────────────────────────────────────────────────────────────


def caption(text: str) -> QWidget:
    lbl = C.label(text, 'small', 'tertiary', rich=True)
    lbl.setWordWrap(True)
    return lbl


def unit_cell(t: Theme, unit: str, menu: bool) -> QWidget:
    """The knob grid's unit column: a unit menu, or a fixed unit whose text starts where
    a menu's text does."""
    if menu:
        return C.Field(t, unit, UNIT_W, kind='choice')
    lbl = C.label(unit, 'body', 'secondary')
    lbl.setIndent(space(3))
    lbl.setFixedWidth(UNIT_W)
    return lbl


def knob(
    t: Theme,
    name: str,
    value: str,
    unit: str,
    pos: float,
    lo: str,
    hi: str,
    *,
    unit_menu: bool = False,
    decades: int = 0,
    hover: str = '',
) -> QWidget:
    """One registry knob: name, value and unit on the first line; on the second, the
    slider between its two ends, each end edited in place (``hover`` = 'lo' / 'hi'
    draws that end under the pointer)."""
    row1 = C.hbox(
        C.label(name, 'body', rich=True), None, C.Field(t, value, VALUE_W), 2, unit_cell(t, unit, unit_menu), spacing=0
    )
    row2 = C.hbox(
        C.SliderEnd(t, lo, END_W, hover=hover == 'lo'),
        C.Slider(t, pos, decades),
        C.SliderEnd(t, hi, END_W, right=True, hover=hover == 'hi'),
        spacing=1,
    )
    w = QWidget()
    w.setLayout(C.vbox(row1, row2, spacing=1))
    return w


def column(t: Theme, name: str, control: QWidget) -> QWidget:
    """A labelled field, as Measurements' fields: the name above, the field filling its column."""
    w = QWidget()
    w.setLayout(C.vbox(C.label(name, 'small', 'secondary'), control, spacing=2))
    return w


def titrant_section(t: Theme, overlay: bool) -> QWidget:
    """The titrant concentrations: an even grid (From / To in one unit, and the number
    of points), or a custom list — the one an overlaid file brings with it."""
    w = QWidget()
    if overlay:
        x = OVERLAY['x_M']
        vec = C.hbox(C.link_button('Load vector…'), C.link_button('Save vector…'), None, spacing=5)
        w.setLayout(
            C.vbox(
                C.Segmented(t, ['Even steps', 'Custom list'], 1),
                3,
                caption(f'Taken from {OVERLAY["file"]}, so the model is computed where the data were measured.'),
                3,
                C.ConcentrationGrid(t, [molar(v) for v in x], 'Guest (M)'),
                2,
                vec,
                spacing=0,
            )
        )
        return w
    start, stop, n = GRID['start_M'] * UM, GRID['stop_M'] * UM, GRID['points']
    blank = C.label('', 'small', 'secondary')
    unit = QWidget()
    unit.setLayout(C.vbox(blank, C.Field(t, 'µM', UNIT_W, kind='choice'), spacing=2))
    span = C.hbox(
        column(t, 'From', C.Field(t, f'{start:g}')), 4, column(t, 'To', C.Field(t, f'{stop:g}')), 2, unit, spacing=0
    )
    step = QWidget()
    step.setLayout(
        C.vbox(
            C.label('', 'small', 'secondary'),
            C.label(f'Step {(stop - start) / (n - 1):.2f} µM', 'small', 'tertiary'),
            spacing=2,
        )
    )
    step.layout().itemAt(1).widget().setFixedHeight(28)
    points = C.hbox(column(t, 'Points', C.Field(t, str(n))), 4, step, 2, QWidget(), spacing=0)
    points.setStretch(0, 1)
    points.setStretch(2, 1)
    points.itemAt(4).widget().setFixedWidth(UNIT_W)
    w.setLayout(
        C.vbox(
            C.Segmented(t, ['Even steps', 'Custom list'], 0),
            3,
            span,
            3,
            points,
            3,
            caption('Points are where you would measure; the curve between them is drawn continuously.'),
            spacing=0,
        )
    )
    return w


def noise_section(t: Theme, overlay: bool) -> QWidget:
    """The two-part noise law ``var(y) = floor² + (proportional·y)²`` — a floor σ in signal units and a
    part proportional to the signal — with the replicates and the seed of the draw, a new draw, and
    the law read from an overlaid file's replicates."""
    floor = column(t, 'Floor', C.Field(t, grouped(NOISE['sd_au']), prefix='σ', suffix='a.u.'))
    proportional = column(t, 'Proportional', C.Field(t, '0', suffix='%'))
    reps = column(t, 'Replicates', C.Field(t, str(REPLICAS)))
    seed = column(t, 'Seed', C.Field(t, str(NOISE['seed'])))
    new_draw = C.OutlineButton(t, 'New draw')
    new_draw.setToolTip('Draw new noise: moves the seed on by one')
    read = C.OutlineButton(t, 'Read from overlaid data')
    read.setEnabled(overlay)
    w = QWidget()
    w.setLayout(
        C.vbox(
            C.Checkbox(t, 'Add measurement noise', checked=True),
            2,
            C.hbox(floor, 4, proportional, spacing=0),
            3,
            C.hbox(reps, 4, seed, spacing=0),
            3,
            C.hbox(new_draw, 3, read, None, spacing=0),
            3,
            caption('σ² = floor² + (proportional × signal)². The same seed gives the same draws.'),
            spacing=0,
        )
    )
    return w


def inspector(t: Theme, overlay: bool, signal_open: bool, hover_end: bool) -> QWidget:
    w = QWidget()
    w.setObjectName('Inspector')
    w.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
    more = C.tool_button(t, None, 'more')
    more.setObjectName('SettingsMenu')
    more.setToolTip('Save, load or reset these settings')
    head = QWidget()
    head.setFixedHeight(44)
    head.setLayout(
        C.hbox(
            C.label('Simulation settings', 'body-strong'),
            None,
            more,
            C.tool_button(t, None, 'x'),
            spacing=1,
            margins=(5, 0, 3, 0),
        )
    )

    # Binding model: category, then the model within it (ASSAY_REGISTRY category + subtype_label).
    model = QWidget()
    model.setLayout(
        C.vbox(
            C.Field(t, 'Competitive Displacement', kind='choice'),
            C.Field(t, 'IDA — Indicator Displacement (1:1)', kind='choice'),
            spacing=2,
        )
    )

    # Binding constants: log sliders over whole decades, entered in M⁻¹ as in the main window.
    ka_dye, ka_guest = COND['Ka_dye'], PAR['Ka_guest']
    consts = QWidget()
    consts.setLayout(
        C.vbox(
            knob(
                t, f'K{sub("a,dye")}', sci(ka_dye), 'M⁻¹', log_pos(ka_dye, 1e4, 1e10), decade(4), decade(10), decades=6
            ),
            knob(
                t,
                f'K{sub("a,guest")}',
                sci(ka_guest),
                'M⁻¹',
                log_pos(ka_guest, 1e5, 1e11),
                decade(5),
                decade(11),
                decades=6,
                hover='hi' if hover_end else '',
            ),
            spacing=4,
        )
    )

    # Fixed totals in the cuvette; sliders from 0 to five times the default. Under them, whether
    # the additions dilute the totals, as Binding model states it: constant until the user says so.
    totals = QWidget()
    totals.setLayout(
        C.vbox(
            knob(t, '[Host]₀', f'{COND["h0"] * UM:g}', 'µM', 0.2, '0', '21.5', unit_menu=True),
            knob(t, '[Dye]₀', f'{COND["d0"] * UM:g}', 'µM', 0.2, '0', '30', unit_menu=True),
            C.vbox(
                C.label('Totals during the titration', 'small', 'secondary'),
                1,
                C.Segmented(t, ['Stay constant', 'Are diluted'], 0, dividers=True),
                spacing=0,
            ),
            spacing=4,
        )
    )

    # Signal coefficients: the 4-parameter signal of the registry.
    sig = QWidget()
    sig.setLayout(
        C.vbox(
            knob(t, f'I{sub("0")}', grouped(PAR['I0']), 'a.u.', PAR['I0'] / 1e4, '0', decade(4)),
            knob(t, f'I{sub("dye,free")}', sci(PAR['I_dye_free']), 'a.u./M', PAR['I_dye_free'] / 1e9, '0', decade(9)),
            knob(
                t, f'I{sub("dye,bound")}', sci(PAR['I_dye_bound']), 'a.u./M', PAR['I_dye_bound'] / 1e11, '0', decade(11)
            ),
            2,
            caption(f'Signal = I{sub("0")} + I{sub("dye,free")}·[D] + I{sub("dye,bound")}·[HD]'),
            spacing=4,
        )
    )

    n = len(OVERLAY['x_M']) if overlay else GRID['points']
    body = QWidget()
    body.setObjectName('InspectorBody')
    body.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
    body.setLayout(
        C.vbox(
            C.section(t, 'Binding model', model, first=True),
            C.section(t, 'Binding constants', consts),
            C.section(t, 'Fixed totals', totals, trailing='in the cuvette'),
            C.section(t, 'Concentrations', titrant_section(t, overlay), trailing=f'{n} points'),
            C.section(t, 'Noise', noise_section(t, overlay), trailing=f'{REPLICAS} replicates'),
            C.section(t, 'Signal', sig, open_=signal_open, trailing='3 coefficients'),
            None,
            spacing=0,
            margins=(5, 0, 5, 4),
        )
    )
    scroll = QScrollArea()
    scroll.setObjectName('InspectorScroll')
    scroll.setWidget(body)
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    w.setLayout(C.vbox(head, scroll, spacing=0))
    return w


# ── Window ─────────────────────────────────────────────────────────────────────────


def toolbar(t: Theme, overlay: bool) -> QWidget:
    """The main window's toolbar grammar, with the window buttons at its left."""
    w = QWidget()
    w.setObjectName('Toolbar')
    w.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
    w.setFixedHeight(SIZE['toolbar'])
    div = C.hairline(vertical=True)
    div.setFixedHeight(20)
    overlay_btn = C.tool_button(t, 'Overlay data…', 'layers')
    overlay_btn.setToolTip('Show a measurement file over the simulated titration')
    export = C.tool_button(t, 'Export', 'export', menu=True)
    export.setToolTip('Curve image… · Data file… (loads as a measurement)')
    help_btn = C.tool_button(t, None, 'help')
    help_btn.setToolTip('How the simulation works. It uses the same equations as fitting.')
    fit = C.primary_button(t, 'Fit in new session', 'arrow-up-right')
    fit.setToolTip('Open the simulated data in a new fitting session with this binding model')
    n = len(OVERLAY['x_M']) if overlay else GRID['points']
    items = [
        C.TrafficLights(t),
        6,
        C.label('Simulation', 'title'),
        3,
        C.badge(f'IDA · {n} points · {REPLICAS} replicates', 'neutral'),
        None,
        overlay_btn,
        export,
        2,
        div,
        2,
        help_btn,
        C.tool_button(t, None, 'panel-right', checked=True),
        2,
        fit,
    ]
    w.setLayout(C.hbox(*items, spacing=2, margins=(5, 0, 5, 0)))
    return w


def window(t: Theme, *, overlay: bool = False, signal_open: bool = False, hover_end: bool = True) -> QWidget:
    root = QWidget()
    root.setObjectName('Root')
    split = QSplitter(Qt.Orientation.Horizontal)
    split.setHandleWidth(1)
    split.setChildrenCollapsible(False)
    split.addWidget(canvas(t, overlay))
    insp = inspector(t, overlay, signal_open, hover_end)
    insp.setMinimumWidth(SIZE['inspector-min'])
    split.addWidget(insp)
    split.setStretchFactor(0, 1)
    split.setSizes([WINDOW_SIZE[0] - 1 - SIZE['inspector'], SIZE['inspector']])
    # Left: what the window is doing, or its plain-language warning. Right: what is simulated.
    status = shell.status_bar(
        t,
        ('Ready', 'text-tertiary'),
        ['Indicator displacement', '2 binding constants', f'Noise {grouped(NOISE["sd_au"])} a.u.'],
    )
    root.setLayout(C.vbox(toolbar(t, overlay), C.hairline(), split, C.hairline(), status, spacing=0))
    return root


def open_settings_menu(t: Theme, root: QWidget) -> None:
    """Float the inspector's ⋯ menu below its button, right edges aligned."""
    btn = root.findChild(QWidget, 'SettingsMenu')
    btn.setCheckable(True)
    btn.setChecked(True)
    btn.update()
    menu = C.PopoverMenu(t, root, SETTINGS_MENU, SETTINGS_NOTE, 264)
    pos = btn.mapTo(root, btn.rect().bottomRight())
    menu.move(pos.x() - menu.width() + C.SHADOW + 1, pos.y() + 2)
    menu.show()
    menu.raise_()


def show_hover_end(t: Theme, root: QWidget) -> None:
    """Float the outline of the slider end under the pointer."""
    end = root.findChild(C.SliderEnd, 'HoverEnd')
    if end is not None:
        outline = C.SliderEndOutline(t, root, end)
        outline.show()
        outline.raise_()


def build(t: Theme) -> dict:
    return {'root': window(t), 'size': WINDOW_SIZE, 'overlay': lambda root: show_hover_end(t, root)}
