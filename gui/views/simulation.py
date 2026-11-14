"""The Simulation window: forward simulation for experiment design, beside the fitting window (DESIGN.md §8).

A window of its own, part of no session: the main window's toolbar, side panel and status
bar, without the sidebar. Toolbar: *Simulation* and its badge, *Overlay data…*, *Export ▾*,
Help, the side-panel toggle and the primary *Fit in new session*. Canvas: **Titration**
(the simulated replicates at the measurement points, the model drawn continuously, an
overlaid file as rings) above **Species** on the same x axis, with the readout at the
pointer. Side panel *Simulation settings*, its ⋯ menu holding *Save settings…*, *Load
settings…* and *Reset to defaults*; under Fixed totals, whether the additions dilute them and
the titrant stock, as Binding model states it. Every setting is
:class:`~gui.simulation.SimulationForm`'s; every change recomputes both plots. The plots are
drawn from the tokens alone; *Curve image…* saves both, the titration above the species on
their shared axis, as one PNG or SVG in the light theme on white.
"""

from __future__ import annotations

import json
import logging
import math
from html import escape
from pathlib import Path

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import QObject, QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QFontMetrics, QKeySequence, QPainter, QPen
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QLabel,
    QMainWindow,
    QMessageBox,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QWidget,
)

from core.assays.registry import ASSAY_REGISTRY
from core.data_processing.concentration import read_raw_concentrations, save_concentration_vector
from core.data_processing.measurement_set import InvalidData
from core.units import Q_
from gui.binding import CATEGORIES
from gui.dataset import Dataset
from gui.design import components as C
from gui.design.appearance import appearance, theme
from gui.design.plot_theme import apply_plot_theme, fit_line, px, replicate_alpha, scatter
from gui.design.tokens import SIZE, Theme, font, space
from gui.dialogs.plot_guide_dialog import show_plot_guide
from gui.plotting.export import ExportRefused, export_stacked
from gui.plotting.labels import fmt_species, superscript
from gui.simulation import (
    COMPLEXES,
    CONCENTRATION_UNITS,
    SPECIES_TOKENS,
    Knob,
    Overlay,
    Simulation,
    SimulationForm,
    SimulationProblem,
    readout_value,
    species_groups,
    tag_text,
    value_text,
)
from gui.views.titration import EXPORT_SIZE, power_of_ten

logger = logging.getLogger(__name__)

WINDOW_SIZE = (1280, 800)
VALUE_W, UNIT_W, END_W = SIZE['knob-value'], SIZE['knob-unit'], SIZE['slider-end']
#: What the ⋯ menu's footnote says the settings file holds.
SETTINGS_NOTE = 'Saves every value, slider end and noise setting of this window to a file.'
#: What to check when a file cannot be written, after the sentence naming it.
WRITE_HINT = 'Check that the folder exists and that you may write there.'
#: Heights of the saved titration and species plots, in px at :data:`EXPORT_SIZE`'s width: the canvas's 13 : 10.
EXPORT_HEIGHTS = (SIZE['export-signal'], SIZE['export-species'])
#: The dash of a free species' line and its swatch, in px.
DASH = [3, 2.5]


def _widget(layout) -> QWidget:
    w = QWidget()
    w.setLayout(layout)
    return w


def _column(name: str, control: QWidget) -> QWidget:
    """A labelled field: the name above, the field filling its column."""
    return _widget(C.vbox(C.label(name, 'small', 'secondary'), control, spacing=1))


def _caption(text: str) -> QLabel:
    return C.wrapped(text, 'small', 'tertiary', rich=True)


def species_pen(t: Theme, key: str, width: float | None = None) -> QPen:
    """A species' pen: its token, solid in a complex, dashed when free; *width* in device px for a plot."""
    solid = key in COMPLEXES
    pen = QPen(t.q(SPECIES_TOKENS[key]), (2.0 if solid else 1.75) if width is None else width)
    pen.setCosmetic(True)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap if solid else Qt.PenCapStyle.FlatCap)
    if not solid:
        pen.setDashPattern(DASH)
    return pen


def _legend_items(form) -> list[tuple[str, str]]:
    """The titration's legend (:class:`~gui.design.components.LegendRow` items): the simulated replicates,
    an overlaid file, the model."""
    r = form.replicates()
    if form.overlay is None:
        return [('dots', f'Simulated replicates ({r})'), ('line', 'Model')]
    return [
        ('dots', f'Simulated ({r})'),
        ('rings', f'{form.overlay.name} ({len(form.overlay.signals)})'),
        ('line', 'Model'),
    ]


#: Each plot's title and caption, as the canvas heads it.
TITRATION_HEAD = ('Titration', 'simulated signal')
SPECIES_HEAD = ('Species', 'in the cuvette')


def _figure_head(t: Theme, head: tuple[str, str], legend: QWidget) -> QWidget:
    """A saved plot's head in theme *t*: its title and caption on the left, its *legend* on the right."""
    title, caption = (C.PaintedText(t, text, role) for text, role in zip(head, ('body-strong', 'small'), strict=True))
    for text in (title, caption):
        text.setFixedWidth(text.minimumWidth())
    w = C.Figure(t)
    w.setLayout(C.hbox(title, 3, caption, None, legend, spacing=0, margins=(0, 3, 0, 2)))
    return w


# ── Canvas ─────────────────────────────────────────────────────────────────────────


class _Readout(QWidget):
    """The species readout, which is also the species legend: the titrant at the pointer, then the complexes
    (solid) and the free species (dashed), each under its word, with its swatch and concentration.

    Without a titrant or concentrations it is the legend alone, as a saved figure carries it.
    """

    HEIGHT = 20

    def __init__(self, t: Theme):
        super().__init__()
        self.t = t
        self.x_text, self.unit = '', ''
        self.groups: list[tuple[str, list[tuple[str, str]]]] = []
        self.setFixedHeight(self.HEIGHT)

    def set_values(self, x_text: str, unit: str, groups: list[tuple[str, list[tuple[str, str]]]]) -> None:
        self.x_text, self.unit, self.groups = x_text, unit, groups
        self.setFixedWidth(int(self._run(None)) + 1)
        flat = '; '.join(f'{word}: ' + ', '.join(f'{n} {v}' for n, v in items) for word, items in groups)
        self.setAccessibleName(f'{x_text}. {flat} {unit}')
        self.update()

    def _run(self, p: QPainter | None) -> float:
        t, h, x = self.t, float(self.HEIGHT), 0.0

        def text(s: str, role: str, tone: str) -> None:
            nonlocal x
            if p is not None:
                p.setFont(font(role))
                p.setPen(t.q(tone))
                p.drawText(QRectF(x, 0, 400, h), Qt.AlignmentFlag.AlignVCenter, s)
            x += QFontMetrics(font(role)).horizontalAdvance(s)

        text(self.x_text, 'small-number', 'text-primary')
        for i, (word, items) in enumerate(self.groups):
            if i or self.x_text:
                x += space(4)
                if p is not None:
                    p.fillRect(QRectF(x, h / 2 - 6, 1, 12), t.q('border'))
                x += 1 + space(4)
            text(word, 'small', 'text-tertiary')
            for key, value in items:
                x += space(3)
                if p is not None:
                    p.setPen(species_pen(t, key))
                    p.drawLine(QPointF(x + 1, h / 2), QPointF(x + 15, h / 2))
                x += 16 + space(2)
                text(fmt_species(key, brackets=False), 'small', 'text-secondary')
                x += space(2)
                text(value, 'small-number', 'text-primary')
        x += space(3)
        text(self.unit, 'small', 'text-tertiary')
        return x

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._run(p)
        p.end()


class SimulationPlots(QObject):
    """The titration above the species, on one titrant axis, drawn in theme *t*.

    The two plot widgets are placed by the caller. :meth:`show` draws a simulation; :meth:`point_at` moves the pointer's hairline, the
    marker and value tag on the model, and the species markers, and :attr:`pointed` says
    where it now is (an index into the dense curve).
    """

    pointed = pyqtSignal(int)

    def __init__(self, t: Theme):
        super().__init__()
        self.t = t
        self.sim: Simulation | None = None
        self.overlay: Overlay | None = None
        self.unit, self.x_name = 'µM', ''
        self.index = 0
        self.signal_pw = pg.PlotWidget()
        self.species_pw = pg.PlotWidget()
        for pw in (self.signal_pw, self.species_pw):
            pw.setFrameShape(QFrame.Shape.NoFrame)
        self._items: list[tuple[pg.PlotItem, object]] = []
        self._style()
        self.species_pw.getPlotItem().setXLink(self.signal_pw.getPlotItem())
        for pw in (self.signal_pw, self.species_pw):
            pw.scene().sigMouseMoved.connect(lambda pos, pw=pw: self._moved(pw, pos))

    def _style(self) -> None:
        t = self.t
        sp = apply_plot_theme(self.signal_pw, t, '', 'Signal (a.u.)')
        cp = apply_plot_theme(self.species_pw, t, '', 'Concentration (µM)')
        # The titration shares the species plot's titrant axis: an axis line with ticks, no values.
        ax = sp.getAxis('bottom')
        ax.setStyle(showValues=False, tickLength=4)
        ax.showLabel(False)
        ax.setHeight(6)
        # A y tick on the top edge of the range has its label centred on that edge: half a
        # label of room above the axes keeps it whole.
        half_label = math.ceil(QFontMetrics(font('small-number')).height() / 2)
        for pi in (sp, cp):
            pi.getViewBox().setMouseEnabled(x=False, y=False)
            pi.getAxis('left').setStyle(autoExpandTextSpace=False)
            left, _top, right, bottom = pi.layout.getContentsMargins()
            pi.layout.setContentsMargins(left, half_label, right, bottom)

    def _add(self, pi: pg.PlotItem, item, z: float = 0, bounds: bool = True) -> None:
        item.setZValue(z)
        pi.addItem(item, ignoreBounds=not bounds)
        self._items.append((pi, item))

    def show(self, sim: Simulation | None, overlay: Overlay | None, unit: str, x_name: str) -> None:
        """Draw *sim* (and *overlay*) with the concentrations in *unit*."""
        self.sim, self.overlay, self.unit, self.x_name = sim, overlay, unit, x_name
        for pi, item in self._items:
            pi.removeItem(item)
        self._items = []
        if sim is None:
            return
        t = self.t
        sp, cp = self.signal_pw.getPlotItem(), self.species_pw.getPlotItem()
        scale = float(Q_(1.0, 'M').to(unit).magnitude)
        shown = [sim.signals.ravel(), sim.y_dense] + ([overlay.signals.ravel()] if overlay is not None else [])
        e = power_of_ten(np.concatenate(shown))
        self.y_scale = 10.0**-e
        sp.getAxis('left').setLabel(f'Signal ({"" if e == 0 else f"10{superscript(e)} "}a.u.)')
        cp.getAxis('left').setLabel(f'Concentration ({unit})')
        cp.getAxis('bottom').setLabel(f'{x_name} ({unit})')
        for row in sim.signals:
            self._add(sp, scatter(t, sim.x * scale, row * self.y_scale, 'replicate', replicate_alpha(t), 6), 2)
        if overlay is not None:
            for row in overlay.signals:
                rings = scatter(t, overlay.x * scale, row * self.y_scale, 'text-secondary', 0.75, 7, hollow=True)
                self._add(sp, rings, 3)
        self._add(sp, fit_line(t, sim.x_dense * scale, sim.y_dense * self.y_scale), 4)
        # The signal's own species are drawn last, so they stay on top where curves cross.
        for key in sorted(sim.species, key=lambda k: k in COMPLEXES):
            curve = pg.PlotDataItem(sim.x_dense * scale, sim.species[key] * scale, antialias=True)
            curve.setPen(species_pen(t, key, px(2.0 if key in COMPLEXES else 1.75)))
            self._add(cp, curve, 3 if key in COMPLEXES else 2)
        lo, hi = float(sim.x_dense[0] * scale), float(sim.x_dense[-1] * scale)
        pad = 0.03 * (hi - lo) if hi > lo else 1.0
        sp.setXRange(lo - pad, hi + pad, padding=0)
        sp.enableAutoRange(axis='y')
        cp.enableAutoRange(axis='y')
        self._pointer_items()
        self.point_at(min(self.index, len(sim.x_dense) - 1) if self.index else len(sim.x_dense) // 3)

    def _pointer_items(self) -> None:
        t = self.t
        pen = pg.mkPen(t.q('text-tertiary'), width=px(1), style=Qt.PenStyle.DashLine)
        pen.setDashPattern([3, 3])
        sp, cp = self.signal_pw.getPlotItem(), self.species_pw.getPlotItem()
        self.hairlines = [pg.InfiniteLine(angle=90, pen=pen, movable=False) for _ in range(2)]
        self._add(sp, self.hairlines[0], 1, bounds=False)
        self._add(cp, self.hairlines[1], 1, bounds=False)
        ring = pg.mkPen(t['bg-surface'], width=px(2))
        self.marker = pg.ScatterPlotItem(size=SIZE['pointer-signal'], brush=pg.mkBrush(t.q('accent')), pen=ring)
        self._add(sp, self.marker, 6, bounds=False)
        self.tag = pg.TextItem('', color=t.q('text-primary'), anchor=(0, 1.15))
        self.tag.setFont(font('small-number'))
        self._add(sp, self.tag, 7, bounds=False)
        self.species_marks = {}
        for key in self.sim.species:
            mark = pg.ScatterPlotItem(
                size=SIZE['pointer-species'], brush=pg.mkBrush(t.q(SPECIES_TOKENS[key])), pen=ring
            )
            self._add(cp, mark, 6, bounds=False)
            self.species_marks[key] = mark

    def set_pointer_visible(self, visible: bool) -> None:
        for item in [*self.hairlines, self.marker, self.tag, *self.species_marks.values()]:
            item.setVisible(visible)

    def point_at(self, index: int) -> None:
        """Put the pointer at point *index* of the dense curve."""
        sim = self.sim
        if sim is None:
            return
        self.index = index
        scale = float(Q_(1.0, 'M').to(self.unit).magnitude)
        x = float(sim.x_dense[index] * scale)
        y = float(sim.y_dense[index] * self.y_scale)
        for line in self.hairlines:
            line.setPos(x)
        self.marker.setData([x], [y])
        self.tag.setText(tag_text(float(sim.y_dense[index])))
        self.tag.setPos(x + 0.012 * (sim.x_dense[-1] - sim.x_dense[0]) * scale, y)
        for key, mark in self.species_marks.items():
            mark.setData([x], [float(sim.species[key][index] * scale)])
        self.pointed.emit(index)

    def _moved(self, pw: pg.PlotWidget, pos) -> None:
        if self.sim is None:
            return
        vb = pw.getPlotItem().getViewBox()
        if not vb.sceneBoundingRect().contains(pos):
            return
        x = vb.mapSceneToView(pos).x() / float(Q_(1.0, 'M').to(self.unit).magnitude)
        index = int(np.argmin(np.abs(self.sim.x_dense - x)))
        if index != self.index:
            self.point_at(index)


# ── Side panel ─────────────────────────────────────────────────────────────────────


class _KnobRow(QWidget):
    """One input: name, value and unit on the first line; the slider between its two ends on the second."""

    def __init__(self, view: SimulationWindow, knob: Knob):
        super().__init__()
        t, self.key, self.view = view.t, knob.key, view
        name = knob.name()
        self.value = C.Field(t, '', VALUE_W, editable=True)
        self.value.setAccessibleName(f'{name} ({knob.shown_unit})')
        self.value.edited.connect(lambda text: view.edit(lambda f: f.set_value(self.key, text)))
        if knob.kind == 'concentration':
            self.unit = C.Dropdown(t, knob.unit, UNIT_W, options=list(CONCENTRATION_UNITS))
            self.unit.setAccessibleName(f'Unit of {name}')
            self.unit.chosen.connect(lambda i: view.edit(lambda f: f.set_unit(self.key, CONCENTRATION_UNITS[i])))
        else:
            self.unit = C.label(knob.shown_unit, 'body', 'secondary')
            self.unit.setIndent(space(3))
            self.unit.setFixedWidth(UNIT_W)
        self.slider = C.Slider(t, knob.pos(), knob.decades())
        self.slider.setAccessibleName(f'{name} slider')
        self.slider.moved.connect(lambda pos: view.edit(lambda f: f.slide(self.key, pos)))
        self.ends = (C.SliderEnd(t, '', END_W), C.SliderEnd(t, '', END_W, right=True))
        for high, end in enumerate(self.ends):
            end.setAccessibleName(f'{"Upper" if high else "Lower"} end of the {name} slider')
            end.edited.connect(lambda text, high=bool(high): view.edit(lambda f: f.set_end(self.key, high, text)))
        row1 = C.hbox(C.label(knob.label, 'body', rich=True), None, self.value, 2, self.unit, spacing=0)
        row2 = C.hbox(self.ends[0], self.slider, self.ends[1], spacing=1)
        self.setLayout(C.vbox(row1, row2, spacing=1))
        self.sync(knob)

    def sync(self, knob: Knob) -> None:
        self.value.set_text(knob.value_text())
        if isinstance(self.unit, C.Dropdown):
            self.unit.set_choice(knob.unit)
        self.slider.set_pos(knob.pos(), knob.decades())
        for end, text in zip(self.ends, knob.end_texts(), strict=True):
            end.set_text(text)


class SimulationWindow(QMainWindow):
    """The Simulation window; see the module docstring.

    :attr:`fit_requested` carries the form and the simulation on screen when *Fit in new
    session* is pressed; the main window opens the session.
    """

    fit_requested = pyqtSignal(object, object)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.t = theme()
        self.form = SimulationForm()
        self.sim: Simulation | None = None
        self._problem: str | None = None
        self._popover: C.PopoverMenu | None = None
        self.setWindowTitle('Simulation — SupraSimFit')
        if C.MAC:
            self.setWindowFlag(Qt.WindowType.ExpandedClientAreaHint, True)
            self.setWindowFlag(Qt.WindowType.NoTitleBarBackgroundHint, True)
            self.setAttribute(Qt.WidgetAttribute.WA_ContentsMarginsRespectsSafeArea, False)
        self.resize(*WINDOW_SIZE)
        self._actions()
        toolbar = self._build_toolbar()
        self.split = QSplitter(Qt.Orientation.Horizontal)
        self.split.setHandleWidth(1)
        self.split.setChildrenCollapsible(False)
        self.canvas = self._build_canvas()
        self.split.addWidget(self.canvas)
        self.inspector = self._build_inspector()
        self.split.addWidget(self.inspector)
        self.split.setStretchFactor(0, 1)
        self.split.setSizes([WINDOW_SIZE[0] - 1 - SIZE['inspector'], SIZE['inspector']])
        root = QWidget()
        root.setLayout(C.vbox(toolbar, C.hairline(), self.split, C.hairline(), self._build_status(), spacing=0))
        root.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        if C.MAC:
            root.setAttribute(Qt.WidgetAttribute.WA_ContentsMarginsRespectsSafeArea, False)
            if QApplication.platformName() == 'cocoa':
                C.hide_title_text(self)
        self.setCentralWidget(root)
        root.setFocus()  # no control holds the focus, so no focus ring shows until the keyboard moves it
        appearance().changed.connect(self._restyle)
        self._rebuild()

    # ------------------------------------------------------------------
    # Building
    # ------------------------------------------------------------------

    def _actions(self) -> None:
        def action(text: str, icon: str, slot, shortcut: str = '') -> QAction:
            a = QAction(text, self)
            a.setProperty('design_icon', icon)
            if shortcut:
                a.setShortcut(QKeySequence(shortcut))
            a.triggered.connect(slot)
            self.addAction(a)
            return a

        self.act_save = action('Save settings…', 'save', self.save_settings, 'Ctrl+S')
        self.act_load = action('Load settings…', 'open', self.load_settings)
        self.act_reset = action(
            'Reset to defaults', 'rotate', lambda: self.edit(lambda f: f.set_assay(f.assay_type), rebuild=True)
        )
        self.act_image = action('Curve image…', 'image', self.export_image)
        self.act_data = action('Data file…', 'file-text', self.export_data)

    def _build_toolbar(self) -> QWidget:
        t = self.t
        bar = C.TitleBarArea()
        bar.setObjectName('Toolbar')
        bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        bar.setFixedHeight(SIZE['toolbar'])
        self.badge = C.badge('')
        overlay = C.tool_button(t, 'Overlay data…', 'layers')
        overlay.setToolTip('Show a measurement file over the simulated titration')
        overlay.clicked.connect(self.overlay_data)
        self.export = C.tool_button(t, 'Export', 'export', menu=True)
        self.export.clicked.connect(lambda: self._menu([self.act_image, self.act_data], self.export, width=220))
        help_btn = C.tool_button(t, None, 'help')
        help_btn.setToolTip('How the simulation works')
        help_btn.setAccessibleName('How the simulation works')
        help_btn.clicked.connect(lambda: show_plot_guide(self, 'Simulation'))
        self.side = C.tool_button(t, None, 'panel-right', checked=True)
        self.side.setToolTip('Show or hide the side panel')
        self.side.setAccessibleName('Side panel')
        self.side.clicked.connect(lambda: self.inspector.setVisible(self.side.isChecked()))
        fit = C.primary_button(t, 'Fit in new session', 'arrow-up-right')
        fit.setToolTip('Open the simulated data in a new session with this binding model and fit it')
        fit.clicked.connect(self.fit_in_new_session)
        divider = C.hairline(vertical=True)
        divider.setFixedHeight(space(6) - space(2))
        inset = QWidget()  # room for the window controls the title bar keeps on macOS
        inset.setFixedWidth(space(8) + space(6))
        inset.setVisible(C.MAC)
        bar.setLayout(
            C.hbox(
                inset,
                C.label('Simulation', 'title'),
                3,
                self.badge,
                None,
                overlay,
                self.export,
                2,
                divider,
                2,
                help_btn,
                self.side,
                2,
                fit,
                spacing=1,
                margins=(6, 0, 5, 0),
            )
        )
        return bar

    def _build_canvas(self) -> QWidget:
        t = self.t
        w = QWidget()
        w.setObjectName('Canvas')
        w.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.legend = C.LegendRow(t, [])
        self.legend.removed.connect(lambda: self.edit(lambda f: f.set_overlay(None)))
        image = C.tool_button(t, None, 'image')
        image.setToolTip('Save the titration and species plots as one image')
        image.setAccessibleName('Save the titration and species plots as one image')
        image.clicked.connect(self.export_image)
        self.readout = _Readout(t)
        self.plots = SimulationPlots(t)
        self.plots.pointed.connect(self._show_readout)
        titration_head = C.hbox(
            C.label(TITRATION_HEAD[0], 'body-strong'),
            3,
            C.label(TITRATION_HEAD[1], 'small', 'tertiary'),
            None,
            self.legend,
            5,
            image,
            spacing=0,
        )
        species_head = C.hbox(
            C.label(SPECIES_HEAD[0], 'body-strong'),
            3,
            C.label(SPECIES_HEAD[1], 'small', 'tertiary'),
            None,
            self.readout,
            spacing=0,
        )
        lay = C.vbox(titration_head, 2, spacing=0, margins=(6, 5, 6, 4))
        lay.addWidget(self.plots.signal_pw, 13)
        lay.addSpacing(space(5))
        lay.addLayout(species_head)
        lay.addSpacing(space(2))
        lay.addWidget(self.plots.species_pw, 10)
        w.setLayout(lay)
        return w

    def _build_inspector(self) -> QWidget:
        t = self.t
        w = QWidget()
        w.setObjectName('Inspector')
        w.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        w.setMinimumWidth(SIZE['inspector-min'])
        self.more = C.tool_button(t, None, 'more')
        self.more.setToolTip('Save, load or reset these settings')
        self.more.setAccessibleName('Settings menu')
        self.more.clicked.connect(
            lambda: self._menu(
                [self.act_save, self.act_load, None, self.act_reset], self.more, SETTINGS_NOTE, 264, True
            )
        )
        close = C.tool_button(t, None, 'x')
        close.setToolTip('Close the side panel')
        close.setAccessibleName('Close Simulation settings')
        close.clicked.connect(lambda: (self.inspector.hide(), self.side.setChecked(False)))
        head = _widget(
            C.hbox(
                C.label('Simulation settings', 'body-strong'), None, self.more, close, spacing=1, margins=(5, 0, 3, 0)
            )
        )
        head.setFixedHeight(SIZE['toolbar'] - space(2))

        # Binding model: the category, then the model within it.
        self.category = C.Dropdown(t, '', VALUE_W, options=list(CATEGORIES))
        self.category.setAccessibleName('Category of the binding model')
        self.category.chosen.connect(
            lambda i: self.edit(lambda f: f.choose_category(list(CATEGORIES)[i]), rebuild=True)
        )
        self.model_menu = C.Dropdown(t, '', VALUE_W)
        self.model_menu.setAccessibleName('Binding model')
        self.model_menu.chosen.connect(
            lambda i: self.edit(lambda f: f.choose_model(CATEGORIES[f.category][i]), rebuild=True)
        )
        for dropdown in (self.category, self.model_menu):
            dropdown.setMinimumWidth(0)
            dropdown.setMaximumWidth(16_777_215)
            dropdown.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        model = _widget(C.vbox(self.category, self.model_menu, spacing=2))

        self.knob_boxes = {kind: _widget(C.vbox(spacing=4)) for kind in ('binding', 'concentration', 'signal')}
        self.formula = _caption('')
        signal = _widget(C.vbox(self.knob_boxes['signal'], 2, self.formula, spacing=0))
        totals = _widget(C.vbox(self.knob_boxes['concentration'], 4, self._build_dilution(), spacing=0))
        self.sections = {
            'model': C.section(t, 'Binding model', model, first=True),
            'binding': C.section(t, 'Binding constants', self.knob_boxes['binding']),
            'concentration': C.section(t, 'Fixed totals', totals, trailing='in the cuvette'),
            'grid': C.section(t, 'Concentrations', self._build_grid()),
            'noise': C.section(t, 'Noise', self._build_noise()),
            'signal': C.section(t, 'Signal', signal, open_=False),
        }
        body = QWidget()
        body.setObjectName('InspectorBody')
        body.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        body.setLayout(C.vbox(*self.sections.values(), None, spacing=0, margins=(5, 0, 5, 4)))
        self.scroll = QScrollArea()
        self.scroll.setObjectName('InspectorScroll')
        self.scroll.setWidget(body)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        w.setLayout(C.vbox(head, self.scroll, spacing=0))
        return w

    def _build_dilution(self) -> QWidget:
        """Whether the additions dilute the fixed totals, the stock and the totals it holds, as Binding
        model states them."""
        t = self.t
        self.dilution = C.Segmented(t, ['Stay constant', 'Are diluted'], dividers=True)
        self.dilution.setAccessibleName('Whether the additions of titrant dilute the fixed totals')
        self.dilution.setToolTip(
            'Whether each addition of titrant dilutes the sample. It does not if the samples are made up to the '
            'same volume, or if the titrant stock is prepared in the sample solution itself.'
        )
        self.dilution.changed.connect(lambda i: self.edit(lambda f: f.set_diluted(i == 1)))
        self.stock = C.Field(t, '', editable=True)
        self.stock.setToolTip(
            'Concentration of the stock the titrant is added from. Each addition dilutes the fixed totals by the '
            'share of the volume that came from it: the titrant concentration over the stock.'
        )
        self.stock.edited.connect(lambda text: self.edit(lambda f: f.set_stock(text)))
        self.stock_unit = C.Dropdown(t, '', UNIT_W, options=list(CONCENTRATION_UNITS))
        self.stock_unit.setAccessibleName('Unit of the titrant stock concentration')
        self.stock_unit.chosen.connect(lambda i: self.edit(lambda f: f.set_stock_unit(CONCENTRATION_UNITS[i])))
        unit = _widget(C.vbox(C.label('', 'small', 'secondary'), self.stock_unit, spacing=1))
        self.stock_row = _widget(
            C.vbox(
                C.hbox(_column('Stock concentration', self.stock), 2, unit, spacing=0),
                2,
                _caption('The concentrations are the titrant in the cuvette after each addition.'),
                spacing=0,
            )
        )
        self.contains_box = C.hbox(spacing=5)
        self.contains_row = _widget(
            C.vbox(
                C.wrapped('Stock also contains, at the sample’s own concentration', 'small', 'secondary'),
                C.hbox(self.contains_box, None, spacing=0),
                spacing=1,
            )
        )
        self._contains: dict[str, C.Checkbox] = {}
        self.dilution_box = _widget(
            C.vbox(
                C.label('Totals during the titration', 'small', 'secondary'),
                1,
                self.dilution,
                3,
                self.stock_row,
                3,
                self.contains_row,
                spacing=0,
            )
        )
        return self.dilution_box

    def _build_grid(self) -> QWidget:
        t = self.t
        self.grid_mode = C.Segmented(t, ['Even steps', 'Custom list'])
        self.grid_mode.setAccessibleName('How the concentrations are stated')
        self.grid_mode.changed.connect(lambda i: self.edit(lambda f: f.set_grid_mode(('even', 'custom')[i])))
        self.start, self.stop, self.n_points = (C.Field(t, '', editable=True) for _ in range(3))
        for field, name in ((self.start, 'From'), (self.stop, 'To'), (self.n_points, 'Points')):
            field.setAccessibleName(f'{name} of the concentrations')
            field.edited.connect(lambda _text: self._edit_even())
        self.grid_unit = C.Dropdown(t, '', UNIT_W, options=list(CONCENTRATION_UNITS))
        self.grid_unit.setAccessibleName('Unit of the concentrations')
        self.grid_unit.chosen.connect(lambda i: self.edit(lambda f: f.set_grid_unit(CONCENTRATION_UNITS[i])))
        unit = _widget(C.vbox(C.label('', 'small', 'secondary'), self.grid_unit, spacing=1))
        self.step = C.label('', 'small', 'tertiary')
        self.step.setFixedHeight(SIZE['control'])
        step = _widget(C.vbox(C.label('', 'small', 'secondary'), self.step, spacing=1))
        spacer = QWidget()
        spacer.setFixedWidth(UNIT_W)
        span = C.hbox(_column('From', self.start), 4, _column('To', self.stop), 2, unit, spacing=0)
        points = C.hbox(_column('Points', self.n_points), 4, step, 2, spacer, spacing=0)
        points.setStretch(0, 1)
        points.setStretch(2, 1)
        self.even = _widget(
            C.vbox(
                span,
                3,
                points,
                3,
                _caption('Points are where you would measure; the curve between them is drawn continuously.'),
                spacing=0,
            )
        )
        self.custom_note = _caption('')
        self.custom_grid = C.ConcentrationGrid(t, [], '', editable=True)
        self.custom_grid.edited.connect(lambda i, text: self.edit(lambda f: f.set_point(i, text)))
        load = C.link_button('Load vector…')
        load.clicked.connect(self.load_vector)
        save = C.link_button('Save vector…')
        save.clicked.connect(self.save_vector)
        self.custom = _widget(
            C.vbox(self.custom_note, 3, self.custom_grid, 2, C.hbox(load, save, None, spacing=5), spacing=0)
        )
        return _widget(C.vbox(self.grid_mode, 3, self.even, self.custom, spacing=0))

    def _build_noise(self) -> QWidget:
        t = self.t
        self.noise_on = C.Checkbox(t, 'Add measurement noise', checked=True)
        self.noise_on.toggled.connect(lambda on: self.edit(lambda f: f.set_noise(on=on)))
        self.floor = C.Field(t, '', prefix='σ', suffix='a.u.', editable=True)
        self.floor.setAccessibleName('Noise floor, one standard deviation (a.u.)')
        self.proportional = C.Field(t, '', suffix='%', editable=True)
        self.proportional.setAccessibleName('Noise proportional to the signal (%)')
        self.replicates = C.Field(t, '', editable=True)
        self.replicates.setAccessibleName('Replicates')
        self.seed = C.Field(t, '', editable=True)
        self.seed.setAccessibleName('Seed of the noise')
        for field, name in (
            (self.floor, 'floor'),
            (self.proportional, 'proportional'),
            (self.replicates, 'replicates'),
            (self.seed, 'seed'),
        ):
            field.edited.connect(lambda text, name=name: self.edit(lambda f: f.set_noise_text(name, text)))
        self.new_draw = C.OutlineButton(t, 'New draw')
        self.new_draw.setToolTip('Draw new noise: moves the seed on by one')
        self.new_draw.clicked.connect(lambda: self.edit(lambda f: f.new_draw()))
        self.read_noise = C.OutlineButton(t, 'Read from overlaid data')
        self.read_noise.clicked.connect(self._read_noise)
        level = C.hbox(_column('Floor', self.floor), 4, _column('Proportional', self.proportional), spacing=0)
        draws = C.hbox(_column('Replicates', self.replicates), 4, _column('Seed', self.seed), spacing=0)
        return _widget(
            C.vbox(
                self.noise_on,
                2,
                level,
                3,
                draws,
                3,
                C.hbox(self.new_draw, 3, self.read_noise, None, spacing=0),
                3,
                _caption('σ² = floor² + (proportional × signal)². The same seed gives the same draws.'),
                spacing=0,
            )
        )

    def _build_status(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName('StatusBar')
        bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        bar.setFixedHeight(SIZE['statusbar'])
        self.dot = C.StatusDot(self.t, 'text-tertiary')
        self.status = C.ElidedLabel('Ready', 'small', 'secondary')
        self.model_line = C.label('', 'small', 'tertiary')
        lay = C.hbox(self.dot, 2, self.status, 4, self.model_line, spacing=0, margins=(5, 0, 5, 0))
        lay.setStretchFactor(self.status, 1)
        bar.setLayout(lay)
        return bar

    def _menu(self, actions: list, anchor: C.Button, note: str = '', width: int = 264, right: bool = False) -> None:
        if self._popover is not None:
            self._popover.close_popover()
        menu = C.PopoverMenu(self.t, self, actions, note, width)
        anchor.setCheckable(True)
        anchor.setChecked(True)

        def closed() -> None:
            anchor.setChecked(False)
            anchor.setCheckable(False)
            self._popover = None

        menu.closed.connect(closed)
        self._popover = menu
        menu.popup(anchor, right)

    # ------------------------------------------------------------------
    # Editing
    # ------------------------------------------------------------------

    def edit(self, change, rebuild: bool = False) -> None:
        """Apply *change* to the form and draw again; a setting the form refuses is said on the status bar."""
        try:
            change(self.form)
        except SimulationProblem as problem:
            self._say(str(problem))
            self._sync()
            return
        self._say(None)
        if rebuild:
            self._rebuild()
        else:
            self._sync()

    def _edit_even(self) -> None:
        self.edit(lambda f: f.set_even(self.start.editor.text(), self.stop.editor.text(), self.n_points.editor.text()))

    def _say(self, message: str | None) -> None:
        self._problem = message
        self.dot.set_tone('warning' if message else 'text-tertiary')
        self.status.set_full_text(message or 'Ready')
        self.status.setToolTip(message or '')

    def _read_noise(self) -> None:
        try:
            self.form.read_noise()
        except SimulationProblem as problem:
            QMessageBox.warning(self, 'Noise Not Read', str(problem))
            return
        self._sync()

    # ------------------------------------------------------------------
    # Drawing from the form
    # ------------------------------------------------------------------

    def _rebuild(self) -> None:
        """Build the knob rows of the model chosen, then draw everything."""
        self.rows: dict[str, _KnobRow] = {}
        for kind, box in self.knob_boxes.items():
            lay = box.layout()
            while lay.count():
                item = lay.takeAt(0)
                if item.widget() is not None:
                    C.drop(item.widget())
            for knob in self.form.section(kind):
                row = _KnobRow(self, knob)
                self.rows[knob.key] = row
                lay.addWidget(row)
        for box in self._contains.values():
            self.contains_box.removeWidget(box)
            C.drop(box)
        self._contains = {}
        for knob in self.form.section('concentration') if self.form.offers_contains else ():
            box = C.Checkbox(self.t, knob.label, rich=True)
            box.setAccessibleName(f'The titrant stock also contains {knob.name()} at the sample’s concentration')
            box.toggled.connect(lambda on, key=knob.key: self.edit(lambda f: f.set_contains(key, on)))
            self.contains_box.addWidget(box)
            self._contains[knob.key] = box
        has = {kind: bool(self.form.section(kind)) for kind in self.knob_boxes}
        for kind, on in has.items():
            self.sections[kind].setVisible(on)
        self._sync()

    def _sync(self) -> None:
        """Show every setting of the form and draw the simulation."""
        form = self.form
        meta = ASSAY_REGISTRY[form.assay_type]
        self.category.set_choice(form.category)
        self.model_menu.set_choice(
            meta.subtype_label, [ASSAY_REGISTRY[a].subtype_label for a in CATEGORIES[form.category]]
        )
        for key, row in self.rows.items():
            row.sync(form.knobs[key])
        self.dilution_box.setVisible(form.offers_dilution)
        self.dilution.set_current(int(form.diluted))
        self.stock_row.setVisible(form.diluted)
        self.stock.set_text(form.stock_text())
        self.stock.setAccessibleName(f'Titrant stock concentration ({form.stock_unit})')
        self.stock_unit.set_choice(form.stock_unit)
        self.contains_row.setVisible(form.diluted and form.offers_contains)
        for key, box in self._contains.items():
            box.set_checked(key in form.contains)
        n_signal = len(form.section('signal'))
        self.sections['signal'].header.set_trailing(f'{n_signal} coefficient{"s" if n_signal != 1 else ""}')
        self.formula.setText(form.signal_formula())
        # Concentrations
        g = form.grid
        custom = g.mode == 'custom'
        self.grid_mode.set_current(int(custom))
        self.even.setVisible(not custom)
        self.custom.setVisible(custom)
        scale = float(Q_(1.0, 'M').to(g.unit).magnitude)
        self.start.set_text(value_text(g.start * scale))
        self.stop.set_text(value_text(g.stop * scale))
        self.n_points.set_text(str(g.points))
        self.grid_unit.set_choice(g.unit)
        self.step.setText(f'Step {value_text(float(f"{(g.stop - g.start) / (g.points - 1) * scale:.2g}"))} {g.unit}')
        self.custom_note.setText(
            f'Taken from {escape(g.source)}, so the model is computed where the data were measured.'
            if g.source
            else 'Double-click a value to change it.'
        )
        self.custom_grid.set_values([value_text(v) for v in g.values], f'{form.x_name} (M)')
        self.sections['grid'].header.set_trailing(f'{len(form.points())} points')
        # Noise
        n = form.noise
        self.noise_on.set_checked(n.on)
        self.floor.set_text(value_text(n.floor))
        self.proportional.set_text(value_text(100 * n.proportional))
        self.replicates.set_text(str(n.replicates))
        self.seed.set_text(str(n.seed))
        for control in (self.floor, self.proportional, self.replicates, self.seed, self.new_draw):
            control.setEnabled(n.on)
        refusal = form.read_noise_refusal()
        self.read_noise.setEnabled(refusal is None)
        self.read_noise.setToolTip(refusal or 'Take the floor and the proportional part from the overlaid replicates')
        r = form.replicates()
        self.sections['noise'].header.set_trailing(f'{r} replicate{"s" if r != 1 else ""}')
        self._simulate()

    def _simulate(self) -> None:
        form = self.form
        try:
            self.sim = form.simulate()
        except SimulationProblem as problem:
            self.sim = None
            self._say(str(problem))
        self.legend.set_items(_legend_items(form))
        self.plots.show(self.sim, form.overlay, form.grid.unit, form.x_name)
        self.badge.setText(form.badge())
        self.model_line.setText('  ·  '.join(form.model_line()))

    def _restyle(self) -> None:
        """Draw the plots again in the theme as it is now: a theme styles their axes and grid once."""
        old, new = self.plots, SimulationPlots(self.t)
        new.index = old.index
        new.pointed.connect(self._show_readout)
        for a, b in ((old.signal_pw, new.signal_pw), (old.species_pw, new.species_pw)):
            self.canvas.layout().replaceWidget(a, b)
            C.drop(a)
        self.plots = new
        self._simulate()

    def _show_readout(self, index: int) -> None:
        sim, unit = self.sim, self.form.grid.unit
        scale = float(Q_(1.0, 'M').to(unit).magnitude)
        x = f'{self.form.x_name} {readout_value(float(sim.x_dense[index] * scale))} {unit}'
        groups = [
            (word, [(k, readout_value(float(sim.species[k][index] * scale))) for k in keys])
            for word, keys in species_groups(sim.species)
        ]
        self.readout.set_values(x, unit, groups)

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def fit_in_new_session(self) -> None:
        if self.sim is None:
            QMessageBox.warning(
                self,
                'Nothing to Fit',
                f'{self._problem or "The model cannot be computed with these settings."} Change the settings, '
                'then fit again.',
            )
            return
        self.fit_requested.emit(self.form, self.sim)

    def overlay_data(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, 'Overlay data', '', 'Data files (*.txt *.csv *.xlsx);;All files (*)'
        )
        if not path:
            return
        try:
            ms = Dataset.open([path]).ms
        except InvalidData as exc:  # written for the user: it names the file and the fix
            QMessageBox.warning(self, 'Data Not Overlaid', str(exc))
            return
        overlay = Overlay(
            Path(path).name, np.asarray(ms.concentrations, dtype=float), np.asarray(ms.signals, dtype=float)
        )
        self.edit(lambda f: f.set_overlay(overlay))

    def export_image(self) -> None:
        """Save the titration above the species on their shared titrant axis, as one PNG or SVG.

        Drawn again in the light theme on white, each plot under its title and caption with
        its legend: the titration's entries, and the species' names and line styles.
        """
        if self.sim is None:
            QMessageBox.warning(self, 'Nothing to Save', self._problem or 'There is no simulation to save.')
            return
        name = f'simulation_{self.form.assay_type.name}.png'
        path, _ = QFileDialog.getSaveFileName(self, 'Save curve image', name, 'PNG image (*.png);;SVG drawing (*.svg)')
        if not path:
            return
        light = Theme(dark=False)
        figure = SimulationPlots(light)
        for pw, height in zip((figure.signal_pw, figure.species_pw), EXPORT_HEIGHTS, strict=True):
            pw.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
            pw.resize(EXPORT_SIZE[0], height)
            pw.show()
        figure.show(self.sim, self.form.overlay, self.form.grid.unit, self.form.x_name)
        figure.set_pointer_visible(False)
        species = _Readout(light)
        species.set_values('', '', [(word, [(k, '') for k in keys]) for word, keys in species_groups(self.sim.species)])
        heads = [
            _figure_head(light, TITRATION_HEAD, C.LegendRow(light, _legend_items(self.form), removable=False)),
            _figure_head(light, SPECIES_HEAD, species),
        ]
        for head in heads:
            head.setFixedWidth(EXPORT_SIZE[0])
            head.adjustSize()
            head.show()
        QApplication.processEvents()
        try:
            export_stacked(
                [heads[0], figure.signal_pw.getPlotItem(), heads[1], figure.species_pw.getPlotItem()],
                path,
                width_px=2 * EXPORT_SIZE[0],
            )
        except ExportRefused as exc:
            QMessageBox.warning(self, 'Image Not Saved', str(exc))
        except Exception:
            logger.exception('Could not save the curve image to %s', path)
            QMessageBox.warning(self, 'Image Not Saved', f'Could not save the image to {Path(path).name}. {WRITE_HINT}')
        else:
            self._say(None)
            self.status.set_full_text(f'Ready  ·  Curve image saved to {Path(path).name}')
        finally:
            for w in (figure.signal_pw, figure.species_pw, *heads):
                w.close()
                w.deleteLater()

    def export_data(self) -> None:
        from core.io.formats.measurement_writer import write_measurements_csv, write_measurements_txt

        if self.sim is None:
            QMessageBox.warning(self, 'Nothing to Save', self._problem or 'There is no simulation to save.')
            return
        name = f'simulation_{self.form.assay_type.name}.txt'
        path, _ = QFileDialog.getSaveFileName(self, 'Save data file', name, 'Text file (*.txt);;CSV file (*.csv)')
        if not path:
            return
        ms = self.form.measurement_set(self.sim)
        try:
            if Path(path).suffix.lower() == '.csv':
                write_measurements_csv(ms, path)
            else:
                path = str(Path(path).with_suffix('.txt'))
                write_measurements_txt(ms, path)
        except Exception:
            logger.exception('Could not save the simulated data to %s', path)
            QMessageBox.warning(self, 'Data Not Saved', f'Could not save the data to {Path(path).name}. {WRITE_HINT}')
            return
        self.status.set_full_text(f'Ready  ·  Data saved to {Path(path).name}')

    def save_settings(self) -> None:
        name = f'simulation_{self.form.assay_type.name}.json'
        path, _ = QFileDialog.getSaveFileName(self, 'Save settings', name, 'Settings (*.json)')
        if not path:
            return
        try:
            Path(path).write_text(json.dumps(self.form.to_dict(), indent=2), encoding='utf-8')
        except OSError:
            QMessageBox.warning(
                self, 'Settings Not Saved', f'Could not save the settings to {Path(path).name}. {WRITE_HINT}'
            )
            return
        self.status.set_full_text(f'Ready  ·  Settings saved to {Path(path).name}')

    def load_settings(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, 'Load settings', '', 'Settings (*.json);;All files (*)')
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding='utf-8'))
            self.form.load_dict(data)
        except (OSError, ValueError, AttributeError, TypeError):
            QMessageBox.warning(
                self,
                'Settings Not Loaded',
                f'Could not read simulation settings from {Path(path).name}. Choose a file written with Save '
                'settings… in this window.',
            )
            return
        self._say(None)
        self._rebuild()
        self.status.set_full_text(f'Ready  ·  Settings loaded from {Path(path).name}')

    def load_vector(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, 'Load vector', '', 'Concentrations (*.json);;All files (*)')
        if not path:
            return
        try:
            values = read_raw_concentrations(path).to('M').magnitude
        except Exception:
            QMessageBox.warning(
                self,
                'Concentrations Not Loaded',
                f'Could not read {Path(path).name}. Make sure it is a concentration file (.json) saved by SupraSimFit.',
            )
            return
        self.edit(lambda f: f.set_custom(list(np.atleast_1d(values))))

    def save_vector(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, 'Save vector', 'concentrations.json', 'Concentrations (*.json)')
        if not path:
            return
        try:
            save_concentration_vector(np.asarray(self.form.grid.values), path, unit='M')
        except OSError:
            QMessageBox.warning(
                self,
                'Concentrations Not Saved',
                f'Could not save the concentrations to {Path(path).name}. {WRITE_HINT}',
            )
