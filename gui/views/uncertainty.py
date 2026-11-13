"""Input uncertainty: how far each entered input may be off, and what that did to the last fit (DESIGN.md §8).

Canvas: an intro with *About input uncertainty*; **Each input** — one row per input on a
shared column grid: name and entered value, Fixed / σ / Range, the amount, what it is
stated in, the span on one shared ±20 % axis and in numbers; **Shared error sources**;
**Random error of each addition**. Side panel *Effect on the fit*: the interval of the
last fit, Input-aware against Inputs as entered, and its tests of the inputs against what
was stated. Every edit goes to the session model's :class:`~gui.uncertainty.UncertaintyForm`;
the view redraws when the model says the statement or the results changed.
"""

from __future__ import annotations

import math

import numpy as np
from PyQt6.QtCore import QMargins, QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QScrollArea, QWidget

from core.assays.registry import ASSAY_REGISTRY, AssayType, ParamKind
from core.pipeline.diagnostics import Verdict, rejections
from core.pipeline.inputs import TITRANT, ErrorModel, SpecKind
from core.pipeline.reporting import reports_conditional, summarize_parameters
from core.units import Q_
from gui.design import components as C
from gui.design.appearance import theme
from gui.design.tokens import SIZE, space
from gui.plotting.labels import (
    fmt_constant,
    fmt_estimate,
    fmt_interval_plain,
    fmt_p,
    fmt_value,
    not_run_reason,
    verdict_headline,
)
from gui.session_model import SessionModel
from gui.uncertainty import ADDITION_MODES, HELP_HTML, HELP_TITLE, REPLICATE_KINDS, InputEntry, spread_pct
from gui.widgets.assay_conditions import format_condition
from gui.widgets.info_button import show_help

_THIN = ' '
_SUPERSCRIPT = str.maketrans('0123456789-', '⁰¹²³⁴⁵⁶⁷⁸⁹⁻')
_KINDS = (None, SpecKind.SIGMA, SpecKind.INTERVAL)

#: Column grid of the inputs table; the span column takes the rest.
COL_NAME, COL_KIND, COL_UNIT, COL_BAR = SIZE['input-name'], SIZE['input-kind'], SIZE['stated-in'], SIZE['spread-bar']
GUTTER = 4  # a step of the spacing scale
#: The widest amount a field must show: a sign, five figures and an exponent.
_WIDEST_AMOUNT = '−1.2345e7'
#: What each amount field of an input holds, as its accessible name says.
_AMOUNTS = ('σ', 'Lower end', 'Upper end')


def _power(e: int) -> str:
    return f'{_THIN}×{_THIN}10{str(e).translate(_SUPERSCRIPT)}'


def _num(v: float) -> str:
    return f'{v:.3g}'.replace('-', '−')


def _pct(v: float) -> str:
    return f'{v:+.3g}'.replace('-', '−')


def span_text(entry: InputEntry, span: tuple[float, float] | None, nominal: float | None, unit: str) -> str:
    """What *span* (offsets in percent) covers, in the entered value's own unit: ``4.04 – 4.56 µM``.

    The titrant has no single value, so its span is in percent of every point.
    """
    if span is None:
        return '—'
    lo, hi = span
    symmetric = math.isclose(-lo, hi)
    if entry.key == TITRANT or nominal is None or not nominal > 0:
        head = 'every point ' if entry.key == TITRANT else ''
        return f'{head}±{_num(hi)} %' if symmetric else f'{head}{_pct(lo)} to {_pct(hi)} %'
    scale = float(Q_(1, unit).to(entry.field.unit).magnitude)
    a, b = nominal * (1 + lo / 100) / scale, nominal * (1 + hi / 100) / scale
    if abs(b) >= 1e4:  # one shared power of ten: 1.34 – 2.02 × 10⁷ M⁻¹
        e = math.floor(math.log10(abs(b)))
        return f'{a / 10**e:.2f} – {b / 10**e:.2f}{_power(e)} {unit}'.replace('-', '−')
    return f'{_num(a)} – {_num(b)} {unit}'


def accepted_stretches(grid, r2, r2_cut, low: float, high: float) -> list[tuple[float, float]]:
    """The stretches of Ka from *low* to *high* whose profile stays above its cut-off, ends at *low* and *high*.

    *grid*, *r2* and *r2_cut* are a profile's Ka values, best R² and cut-off at each
    (:class:`~core.pipeline.profile.ProfileResult`,
    :class:`~core.pipeline.input_aware.AwareProfile`). A split interval spans every
    stretch and the rejected values between them; one bar per stretch shows which is which.
    """
    grid, r2, r2_cut = (np.asarray(a, dtype=float) for a in (grid, r2, r2_cut))
    inside = (grid >= low * (1 - 1e-9)) & (grid <= high * (1 + 1e-9))
    ok = inside & np.isfinite(r2) & (r2 >= r2_cut)
    stretches: list[tuple[float, float]] = []
    start = None
    for i, flag in enumerate(ok):
        if flag and start is None:
            start = i
        if not flag and start is not None:
            stretches.append((float(grid[start]), float(grid[i - 1])))
            start = None
    if start is not None:
        stretches.append((float(grid[start]), float(grid[-1])))
    if not stretches:
        return [(low, high)]
    stretches[0] = (low, stretches[0][1])
    stretches[-1] = (stretches[-1][0], high)
    return stretches


def _nice_ticks(lo: float, hi: float) -> list[float]:
    """Round values for a log axis from *lo* to *hi*."""
    ticks = []
    for e in range(math.floor(math.log10(lo)), math.ceil(math.log10(hi)) + 1):
        ticks += [m * 10**e for m in (1, 1.5, 2, 3, 4, 5, 7)]
    inside = [t for t in ticks if lo <= t <= hi]
    if len(inside) > 6:
        inside = [t for t in inside if str(t / 10 ** math.floor(math.log10(t)))[0] in '125']
    return inside


class _InputRow:
    """The widgets of one input's row on the inputs grid."""

    def __init__(self, view: UncertaintyView, entry: InputEntry, grid: QGridLayout, r: int, amount_w: int):
        t, key = view.t, entry.key
        self.key = key
        titrant = key == TITRANT
        x_name = ASSAY_REGISTRY[view.model.uncertainty.assay_type].x_label
        name = QWidget()
        name.setFixedHeight(SIZE['input-row'])
        self.entered = C.label('', 'small-number', 'secondary')
        title = f'{x_name} (titrant)' if titrant else entry.label
        name.setLayout(C.vbox(None, C.label(title, 'body-strong', rich=True), self.entered, None, spacing=1))
        grid.addWidget(name, r, 0)

        self.kind = C.Segmented(t, ['Fixed', 'σ', 'Range'], 0, COL_KIND, dividers=True)
        self.kind.setAccessibleName(f'Kind of uncertainty of {entry.name}')
        self.kind.setToolTip(
            'σ is one standard deviation of a normal distribution. A range is drawn evenly between '
            'its two ends and may be lopsided. Fixed takes the entered value as exact.'
        )
        self.kind.changed.connect(lambda i: view._edit(lambda f: f.choose_kind(key, _KINDS[i])))
        grid.addWidget(self.kind, r, 1, Qt.AlignmentFlag.AlignVCenter)

        self.fields = []
        for i, prefix in enumerate(('σ', 'from', 'to')):
            field = C.Field(t, '', amount_w, prefix=prefix, editable=True)
            index = 0 if i == 0 else i - 1
            field.typed.connect(lambda text, index=index: view._edit(lambda f: f.edit(key, index, text)))
            self.fields.append(field)
        amount = QWidget()
        amount.setLayout(C.vbox(None, *self.fields, None, spacing=1))
        grid.addWidget(amount, r, 2, Qt.AlignmentFlag.AlignVCenter)

        self.unit = C.Segmented(t, ['%', ''], 0, COL_UNIT, disabled=(1,) if titrant else (), dividers=True)
        self.unit.setAccessibleName(f'Unit the uncertainty of {entry.name} is stated in')
        if titrant:
            self.unit.setToolTip('The titrant is a series with no single value, so its uncertainty is a percentage.')
        self.unit.changed.connect(lambda i: view._edit(lambda f: f.state_in(key, i == 0)))
        grid.addWidget(self.unit, r, 3, Qt.AlignmentFlag.AlignVCenter)

        self.bar = C.SpreadBar(t, None, COL_BAR)
        grid.addWidget(self.bar, r, 4, Qt.AlignmentFlag.AlignVCenter)
        self.span = C.wrapped('', 'number', 'secondary')
        grid.addWidget(self.span, r, 5, Qt.AlignmentFlag.AlignVCenter)
        self.problem = C.Problem(t)
        grid.addWidget(self.problem, r + 1, 1, 1, 5)

    def focus_chain(self) -> list[QWidget]:
        return [self.kind, *(f.editor for f in self.fields), self.unit]

    def controls(self) -> list[QWidget]:
        return [self.kind, *self.fields, self.unit]


class _SourceRow(QWidget):
    """One shared error source: its name, its σ in percent, the inputs it moves, and its removal."""

    def __init__(self, view: UncertaintyView, index: int, amount_w: int):
        super().__init__()
        t, form = view.t, view.model.uncertainty
        self.name = C.Field(t, '', COL_NAME, kind='text', editable=True)
        self.name.setAccessibleName(f'Name of shared error source {index + 1}')
        self.name.setToolTip('What every report calls this source, such as “Host and dye stock”.')
        self.name.typed.connect(lambda text: view._edit(lambda f: f.rename_source(index, text)))
        self.sigma = C.Field(t, '', amount_w, prefix='σ', suffix='%', editable=True)
        self.sigma.setAccessibleName(f'σ of shared error source {index + 1} (%)')
        self.sigma.setToolTip('One standard deviation of the error the ticked inputs share, in percent.')
        self.sigma.typed.connect(lambda text: view._edit(lambda f: f.set_source_sigma(index, text)))
        self.remove = C.tool_button(t, None, 'x')
        self.remove.setToolTip('Remove this shared error source')
        self.remove.setAccessibleName(f'Remove shared error source {index + 1}')
        self.remove.clicked.connect(lambda: view._edit(lambda f: f.remove_source(index)))
        self.ticks: dict[str, C.Checkbox] = {}
        for key in form.keys:
            entry = form.entry(key)
            box = C.Checkbox(t, entry.label, rich=True)
            box.setAccessibleName(f'Shared error source {index + 1} moves {entry.name}')
            box.toggled.connect(lambda on, key=key: view._edit(lambda f: f.tick(index, key, on)))
            self.ticks[key] = box
        moves = C.label('Moves', 'label', 'tertiary')
        moves.setFixedWidth(COL_NAME)
        self.problem = C.Problem(t)
        self.setLayout(
            C.vbox(
                C.hbox(self.name, GUTTER, self.sigma, None, self.remove, spacing=0),
                C.hbox(moves, GUTTER, *self.ticks.values(), None, spacing=5),
                self.problem,
                spacing=2,
            )
        )

    def focus_chain(self) -> list[QWidget]:
        return [self.name.editor, self.sigma.editor, *self.ticks.values(), self.remove]


class UncertaintyView(QObject):
    """The canvas and side panel of Input uncertainty over *model*; *parent* is where its dialogs open.

    :attr:`review_requested` asks for Ka confidence, where the tests are reviewed.
    """

    review_requested = pyqtSignal()

    def __init__(self, model: SessionModel, parent: QWidget):
        super().__init__(parent)
        self.model, self.parent, self.t = model, parent, theme()
        self._locked = False
        self._rows: dict[str, _InputRow] = {}
        self._sources: list[_SourceRow] = []
        self._shape: tuple | None = None
        self.amount_w = C.Field.width_for(_WIDEST_AMOUNT, 'from')
        self.canvas = self._build_canvas()
        self.side = self._build_side()
        model.uncertainty_changed.connect(self.refresh)
        model.data_changed.connect(self.refresh)
        model.results_changed.connect(lambda _scope: self._refresh_side())
        model.profile_changed.connect(self._refresh_side)
        self.refresh()

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def _edit(self, change) -> None:
        """Make *change* to the session's statement, and tell the model it changed."""
        change(self.model.uncertainty)
        self.model.uncertainty_edited()

    def show_help(self) -> None:
        show_help(self.parent.window(), HELP_TITLE, HELP_HTML)

    def set_locked(self, locked: bool) -> None:
        """Lock every control while a fit or an analysis reads the statement."""
        self._locked = locked
        self.refresh()

    def badge(self) -> str | None:
        """The summary beside the title: how many inputs the statement moves; none while every one is fixed."""
        n = self.model.uncertainty.varying()
        return f'{n} input{" varies" if n == 1 else "s vary"}' if n else None

    # ------------------------------------------------------------------
    # Building
    # ------------------------------------------------------------------

    def _build_canvas(self) -> QWidget:
        t = self.t
        w = QWidget()
        w.setObjectName('Canvas')
        w.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        intro = C.wrapped(
            'How far each entered input may be off. A fixed input is taken as exact; the fit lets the others '
            'move within what you state, and the Sensitivity analysis draws them from it.'
        )
        self.help_link = C.link_button('About input uncertainty')
        self.help_link.clicked.connect(self.show_help)
        self.unavailable = C.wrapped('', 'body', 'secondary')

        self.table = QWidget()
        self.grid = QGridLayout()
        self.grid.setContentsMargins(QMargins())
        self.grid.setHorizontalSpacing(space(GUTTER))
        self.grid.setVerticalSpacing(0)
        self.table.setLayout(self.grid)
        legend = []
        for term, text in (
            ('σ', 'one standard deviation of a normal distribution'),
            ('Range', 'drawn evenly between its two ends, may be lopsided'),
            ('Fixed', 'taken as exact'),
        ):
            legend += [C.label(term, 'label', 'secondary'), 2, C.label(text, 'small', 'tertiary'), 6]
        inputs = QWidget()
        inputs.setLayout(C.vbox(self.table, 3, C.hbox(*legend[:-1], None, spacing=0), spacing=0))

        # Shared error sources
        self.add_source = C.tool_button(t, 'Add shared source', 'plus')
        self.add_source.setToolTip('State an error several inputs have in common')
        self.add_source.clicked.connect(lambda: self._edit(lambda f: f.add_source()))
        self.no_sources = C.label('None stated, so each input above carries only its own error.', 'body', 'tertiary')
        self.sources_box = C.vbox(spacing=4)
        shared = QWidget()
        shared.setLayout(
            C.vbox(
                C.wrapped(
                    'Errors several inputs have in common: one stock, one balance, one pipette. '
                    'Each moves the inputs you tick alike.'
                ),
                3,
                self.sources_box,
                C.hbox(self.no_sources, None, self.add_source, spacing=3),
                spacing=0,
            )
        )

        # Random error of each addition
        form_w = COL_KIND + self.amount_w + COL_UNIT + 2 * space(GUTTER)
        self.mode = C.Segmented(t, list(ADDITION_MODES), 0, form_w, dividers=True)
        self.mode.setAccessibleName('How the titrant was added')
        self.mode.setToolTip(
            'How the titrant was added: sequential additions into one cuvette, or separately '
            'prepared samples, each point pipetted on its own.'
        )
        self.mode.changed.connect(lambda i: self._edit(lambda f: f.set_additions_mode(i)))
        self.replicates = C.Segmented(t, list(REPLICATE_KINDS), 0, form_w, dividers=True)
        self.replicates.setAccessibleName('What the replicates are, for the error of each addition')
        self.replicates.setToolTip(
            'Separate titrations each have their own addition errors, so their average carries σ/√m of them for '
            'm replicates; repeated reads of one titration share them, and their average carries σ.'
        )
        self.replicates.changed.connect(lambda i: self._edit(lambda f: f.set_separate_titrations(i == 0)))
        self.add_sigma = C.Field(t, '', self.amount_w, prefix='σ', suffix='%', editable=True)
        self.add_sigma.setAccessibleName('σ of each addition (%)')
        self.add_sigma.setToolTip('One standard deviation of a single addition, in percent of its volume.')
        self.add_sigma.typed.connect(lambda text: self._edit(lambda f: f.set_additions_sigma(text)))
        self.sigma_row = QWidget()
        self.sigma_row.setLayout(self._form_row('σ of each addition', self.add_sigma))
        self.add_hint = QWidget()
        self.add_hint.setLayout(
            self._form_row(
                '', C.label('Choose how the titrant was added to state σ of each addition.', 'small', 'tertiary')
            )
        )
        self.add_problem = C.Problem(t)
        additions = QWidget()
        additions.setLayout(
            C.vbox(
                C.wrapped(
                    'The titrant entry above moves the whole series by one factor; '
                    'the scatter of single additions goes here.'
                ),
                5,
                self._form_row('How the titrant was added', self.mode),
                3,
                self._form_row('Replicates are', self.replicates),
                3,
                self.sigma_row,
                self.add_hint,
                2,
                self.add_problem,
                spacing=0,
            )
        )

        self.sections = QWidget()
        self.sections.setLayout(
            C.vbox(
                C.canvas_section('Each input', inputs, '±2σ holds about 95 of every 100 draws', first=True),
                C.canvas_section('Shared error sources', shared),
                C.canvas_section('Random error of each addition', additions),
                spacing=0,
            )
        )
        head = C.hbox(intro, 6, C.vbox(self.help_link, None), spacing=0)
        head.setStretch(0, 1)
        w.setLayout(
            C.vbox(
                head,
                6,
                self.unavailable,
                self.sections,
                None,
                spacing=0,
                margins=(6, 5, 6, 4),
            )
        )
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        area.setWidget(w)
        return area

    @staticmethod
    def _form_row(caption: str, control: QWidget) -> QHBoxLayout:
        cap = C.label(caption, 'label', 'tertiary')
        cap.setFixedWidth(COL_NAME)
        return C.hbox(cap, control, None, spacing=GUTTER)

    def _build_table(self) -> None:
        """Lay the inputs grid out again for the inputs of the assay shown."""
        grid, form = self.grid, self.model.uncertainty
        while grid.count():
            item = grid.takeAt(0)
            if item.widget() is not None:
                C.drop(item.widget())
        for c, width in enumerate((COL_NAME, COL_KIND, self.amount_w, COL_UNIT, COL_BAR)):
            grid.setColumnMinimumWidth(c, width)
        grid.setColumnStretch(5, 1)
        heads = ['Input', 'Kind', 'Amount', 'Stated in', None, '±2σ spans']
        for c, h in enumerate(heads):
            cell = C.AxisScale(self.t, COL_BAR) if h is None else C.label(h, 'label', 'tertiary')
            cell.setFixedHeight(SIZE['control'])
            grid.addWidget(cell, 0, c, Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(C.hairline(), 1, 0, 1, 6)
        self._rows = {}
        for i, key in enumerate(form.keys):
            r = 2 + 3 * i
            self._rows[key] = _InputRow(self, form.entry(key), grid, r, self.amount_w)
            if i < len(form.keys) - 1:
                grid.addWidget(C.hairline(), r + 2, 0, 1, 6)

    def _build_sources(self) -> None:
        for row in self._sources:
            self.sources_box.removeWidget(row)
            C.drop(row)
        self._sources = [_SourceRow(self, i, self.amount_w) for i in range(len(self.model.uncertainty.sources))]
        for row in self._sources:
            self.sources_box.addWidget(row)

    def _chain_focus(self) -> None:
        """Chain the controls in the order they are read: Qt orders them by creation, and rows come and go."""
        chain: list[QWidget] = []
        for row in self._rows.values():
            chain += row.focus_chain()
        for source in self._sources:
            chain += source.focus_chain()
        chain += [self.add_source, self.mode, self.replicates, self.add_sigma.editor]
        for first, second in zip(chain, chain[1:]):
            QWidget.setTabOrder(first, second)

    def _build_side(self) -> QWidget:
        t = self.t
        self.no_fit = C.wrapped('', 'small', 'tertiary')
        self.unit_lines: list[QLabel] = []
        self.charts: list[C.CompactIntervals] = []
        self.interval_box = C.vbox(spacing=2)
        self.interval_caption = C.wrapped('', 'small', 'tertiary')
        self.interval_caption.setTextFormat(Qt.TextFormat.RichText)  # it names constants by their glossary HTML
        iv = QWidget()
        iv.setLayout(C.vbox(self.no_fit, self.interval_box, 2, self.interval_caption, spacing=0))

        self.test_rows = C.vbox(spacing=0)
        self.tests_caption = C.wrapped('', 'small', 'tertiary')
        self.review = C.link_button('Review in Ka confidence  →')
        self.review.clicked.connect(self.review_requested)
        tests = QWidget()
        tests.setLayout(C.vbox(self.test_rows, 2, self.tests_caption, 3, C.hbox(self.review, None), spacing=0))
        self.interval_section = C.section(t, 'Interval of the last fit', iv, first=True)
        self.tests_section = C.section(t, 'Inputs against what you stated', tests)
        also = C.wrapped(
            'The Sensitivity analysis draws the inputs from what you state here and ranks the sources of the '
            'spread of Kₐ.',
            'small',
            'tertiary',
        )
        also_section = C.section(t, 'Also used by', also, open_=False, trailing='Sensitivity')
        content = QWidget()
        content.setLayout(C.vbox(self.interval_section, self.tests_section, also_section, spacing=0))
        return content

    # ------------------------------------------------------------------
    # Drawing from the model
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """Draw the statement as the model holds it, rebuilding the rows when the inputs or sources changed."""
        form = self.model.uncertainty
        shape = (form.assay_type, tuple(form.keys), len(form.sources))
        if shape != self._shape:
            if shape[:2] != (self._shape or (None, None))[:2]:
                self._build_table()
            self._build_sources()
            self._shape = shape
            self._chain_focus()
        available = form.available
        self.sections.setVisible(available)
        self.unavailable.setVisible(not available)
        self.unavailable.setText('' if available else form.unavailable_reason())
        on = not self._locked
        ms = self.model.measurement_set
        x_unit = self.model.settings.display_unit
        for key, row in self._rows.items():
            entry = form.entry(key)
            nominal = form.nominal(key)
            unit = x_unit if key == TITRANT else form.unit(key)
            if key == TITRANT:
                if ms is not None:
                    x = np.asarray(ms.concentrations, dtype=float) * Q_(1.0, 'M').to(x_unit).magnitude
                    row.entered.setText(f'Whole series, {x.min():.3g} – {x.max():.3g} {x_unit}')
                else:
                    row.entered.setText('Whole series')
            elif nominal is not None:
                row.entered.setText(
                    f'Entered{_THIN} {format_condition(entry.field, Q_(nominal, entry.field.unit), unit)}'
                )
            else:
                row.entered.setText('')
            fixed = entry.kind is None
            row.kind.set_current(_KINDS.index(entry.kind))
            row.unit.options = ['%', unit]
            row.unit.set_current(0 if entry.relative else 1)
            row.unit.setVisible(not fixed)
            sigma = entry.kind is SpecKind.SIGMA
            shown = [sigma, not fixed and not sigma, not fixed and not sigma]
            texts = [entry.texts[0] if sigma else '', *(entry.texts if not fixed and not sigma else ('', ''))]
            stated_in = '%' if entry.relative else unit
            for field, visible, text, what in zip(row.fields, shown, texts, _AMOUNTS):
                field.setVisible(visible)
                field.set_text(text)
                field.setAccessibleName(f'{what} of the uncertainty of {entry.name} ({stated_in})')
            spec = form.spec(key)
            problem = form.problem(key)
            span = None if fixed or spec is None else spread_pct(spec, nominal)
            row.bar.set_span(None if problem else span)
            row.span.setText('taken as exact' if fixed else span_text(entry, None if problem else span, nominal, unit))
            row.problem.show_problems([problem] if problem else [])
            for control in row.controls():
                control.setEnabled(on)
        # Shared sources
        problems = form.source_problems()
        for row, source, found in zip(self._sources, form.sources, problems):
            row.name.set_text(source.name)
            row.sigma.set_text(source.sigma_text)
            for key, box in row.ticks.items():
                box.set_checked(key in source.inputs)
                box.setEnabled(on)
            row.problem.show_problems(found)
            for control in (row.name, row.sigma, row.remove):
                control.setEnabled(on)
        self.no_sources.setVisible(not form.sources)
        self.add_source.setEnabled(on)
        # Additions
        additions = form.additions_entry
        self.mode.set_current(additions.mode)
        self.replicates.set_current(0 if additions.separate else 1)
        self.add_sigma.set_text(additions.sigma_text)
        self.sigma_row.setVisible(additions.mode > 0)
        self.add_hint.setVisible(additions.mode == 0)
        problem = form.additions_problem()
        self.add_problem.show_problems([problem] if problem else [])
        self.mode.setEnabled(on)
        self.replicates.setEnabled(on and additions.mode > 0)
        self.add_sigma.setEnabled(on)
        self._refresh_side()

    def _refresh_side(self) -> None:
        """Show what the stated uncertainties did to the last fit shown; say so plainly when there is none."""
        fit, note = self.model.fit_view()
        for widget in (*self.unit_lines, *self.charts):
            self.interval_box.removeWidget(widget)
            C.drop(widget)
        self.unit_lines, self.charts = [], []
        while self.test_rows.count():
            item = self.test_rows.takeAt(0)
            if item.widget() is not None:
                C.drop(item.widget())
        if fit is None or note is not None:
            self.no_fit.setText(
                'No fit is shown. Run a fit to see the interval and the tests the stated uncertainties give.'
                if fit is None
                else f'The last fit is not shown. {note}'
            )
            self.no_fit.show()
            self.interval_caption.hide()
            self.tests_section.hide()
            return
        self.no_fit.hide()
        self._show_intervals(fit)
        self._show_tests(fit)

    def _show_intervals(self, fit) -> None:
        """The interval of each binding constant the fit reports, Input-aware beside Inputs as entered.

        A constant the fit records no interval for — one held fixed, or one read from a
        results file that carries none — is named in the caption rather than drawn.
        """
        kinds = ASSAY_REGISTRY[AssayType[fit.assay_type]].param_kinds
        constants = [
            s for s in summarize_parameters(fit) if not s.is_log and kinds.get(s.key) is ParamKind.BINDING_CONSTANT
        ]
        if not constants:
            self._caption('This fit has no association constant, so it has no interval.')
            return
        rows = [s for s in constants if s.interval is not None]
        missing = [fmt_constant(s.key) for s in constants if s.interval is None]
        no_interval = f'This fit records no interval for {" and ".join(missing)}.' if missing else ''
        if not rows:
            self._caption(no_interval)
            return
        conditional_only = reports_conditional(fit)
        profile = self.model.profile if self.model.profiled_fit is fit else None
        narrower = wider = False
        for s in rows:
            curve = None if profile is None else profile.profiles.get(s.key)
            readings = [
                (
                    'Inputs as entered',
                    'text-secondary',
                    s.estimate,
                    s.estimate_at_bound,
                    s.interval,
                    s.interval_open,
                    s.interval_split,
                    curve,
                )
            ]
            if not conditional_only and s.conditional_interval is not None:
                readings = [
                    (
                        'Input-aware',
                        'accent',
                        s.estimate,
                        s.estimate_at_bound,
                        s.interval,
                        s.interval_open,
                        s.interval_split,
                        None if curve is None else curve.aware or curve,
                    ),
                    (
                        'Inputs as entered',
                        'text-secondary',
                        s.conditional_estimate,
                        s.conditional_at_bound,
                        s.conditional_interval,
                        s.conditional_open,
                        s.conditional_split,
                        curve,
                    ),
                ]
                aware, entered = s.interval, s.conditional_interval
                ratio = math.log(aware[1] / aware[0]) / math.log(entered[1] / entered[0])
                narrower |= ratio < 0.95
                wider |= ratio > 1.05
            lo_axis = min(r[4][0] for r in readings) / 1.25
            hi_axis = max(r[4][1] for r in readings) * 1.25
            # One power of ten for the numbers written: an open end or an estimate on a
            # bound sits at the search box, is written in words and sets none.
            written = [
                value
                for _l, _c, est, at_bound, (lo, hi), open_, _s, _p in readings
                for value, shown in ((est, not at_bound), (lo, not open_[0]), (hi, not open_[1]))
                if shown
            ]
            e = math.floor(math.log10(max(written) if written else math.sqrt(lo_axis * hi_axis)))
            scale = 10.0**e

            def fmt(v: float, scale: float = scale) -> str:
                return fmt_value(v / scale)

            chart_rows = []
            for label, color, est, at_bound, (lo, hi), open_, split, reading_curve in readings:
                estimate = fmt_estimate(est, at_bound, (lo, hi), open_, fmt, html=False)
                row = {
                    'label': f'{label} · Split' if split else label,
                    'color': color,
                    'segments': [(lo, hi)],
                    'est': None if at_bound else est,
                    'text': estimate if at_bound else f'{estimate}  {fmt_interval_plain(fmt(lo), fmt(hi), *open_)}',
                }
                if split:
                    if reading_curve is not None:
                        row['segments'] = accepted_stretches(
                            reading_curve.grid, reading_curve.r2, reading_curve.r2_cut, lo, hi
                        )
                    else:
                        # Words in place of the bars, and no estimate mark on a line with no bars.
                        row['segments'], row['est'] = [], None
                        row['note'] = (
                            'Stretches appear once the Kₐ profile is ready'
                            if self.model.profile_running()
                            else 'No Kₐ profile, so the stretches are not drawn'
                        )
                chart_rows.append(row)
            level = f'{s.level * 100:g}{_THIN}% ' if s.level else ''
            unit_line = C.label(
                f'{fmt_constant(s.key)}, {level}interval, ×{_THIN}10{str(e).translate(_SUPERSCRIPT)} M⁻¹',
                'small',
                'tertiary',
                rich=True,
            )
            chart = C.CompactIntervals(self.t, chart_rows, lo_axis, hi_axis, _nice_ticks(lo_axis, hi_axis), scale)
            for widget in (unit_line, chart):
                self.interval_box.addWidget(widget)
            self.unit_lines.append(unit_line)
            self.charts.append(chart)
        self._caption(
            ' '.join(filter(None, (self._interval_caption(fit, conditional_only, narrower, wider), no_interval)))
        )

    def _caption(self, text: str) -> None:
        self.interval_caption.setText(text)
        self.interval_caption.setVisible(bool(text))

    @staticmethod
    def _interval_caption(fit, conditional_only: bool, narrower: bool, wider: bool) -> str:
        """What made the Input-aware interval differ from the one at the inputs as entered, from the fit's record.

        The inputs moved where the fit records shifts of them, and a stated random error
        of each addition widens the cut-off where the fit records one; a noise law reads
        alike in both intervals, so it explains a difference only beside the additions,
        which take over part of the scatter it would otherwise carry.
        """
        if conditional_only:
            return 'Every input was taken as entered and no error of the additions was stated, so this fit has one interval.'
        moved = bool(fit.input_shifts)
        additions = ErrorModel.from_dict(fit.fit_config).additions is not None
        if wider and not narrower:
            cause = {
                (True, False): 'Letting the inputs move within what you stated widens',
                (False, True): 'The random error of each addition you stated widens',
                (
                    True,
                    True,
                ): 'Letting the inputs move within what you stated and the random error of each addition widen',
            }[moved, additions]
            return f'{cause} the interval beyond the one with the inputs as entered.'
        if narrower and not wider:
            return {
                (True, False): 'Letting the inputs move within what you stated explains a misfit the entered values '
                'could not, so the interval is narrower than with the inputs as entered.',
                (False, True): 'The random error of each addition you stated takes over part of the scatter the noise '
                'law of the replicates would carry, so the interval is narrower than with the inputs as entered.',
                (True, True): 'With the inputs free to move within what you stated and the random error of each '
                'addition, the interval is narrower than with the inputs as entered.',
            }[moved, additions]
        return ''

    def _show_tests(self, fit) -> None:
        diag = fit.diagnostics
        self.tests_section.setVisible(diag is not None)
        if diag is None:
            return
        rejected = rejections(diag.conditional_misfit, diag.misfit, diag.conflict)
        moved = bool(fit.input_shifts)
        rows = []
        if moved:
            rows.append(('misfit', diag.misfit, 'Curve fits with inputs moved', 'Curve misses with inputs moved'))
        rows.append(
            (
                'conditional_misfit',
                diag.conditional_misfit,
                'Curve fits at inputs as entered',
                'Misfit at inputs as entered',
            )
        )
        if moved:
            rows.append(('conflict', diag.conflict, 'Inputs agree with what you stated', 'Inputs conflict'))
        for name, test, passed, failed in rows:
            if test is None:
                reason = not_run_reason(diag, 'conflict' if name == 'conflict' else 'misfit')
                icon, tone, p = 'info', 'text-tertiary', '—'
                text = 'Inputs not tested' if name == 'conflict' else 'Curve not tested'
            else:
                bad = name in rejected
                icon, tone, text, p = (
                    ('alert-circle', 'warning', failed, fmt_p(test.p_value))
                    if bad
                    else ('check-circle', 'success', passed, fmt_p(test.p_value))
                )
                reason = ''
            row = QWidget()
            row.setFixedHeight(SIZE['control'])
            row.setLayout(
                C.hbox(
                    C.Icon(self.t, icon, tone), C.label(text), None, C.label(p, 'small-number', 'secondary'), spacing=3
                )
            )
            if reason:
                row.setToolTip(f'Not tested: {reason}.')
            self.test_rows.addWidget(row)
        caption = verdict_headline(diag)[0] + '.'
        if diag.verdict in (Verdict.INPUTS_CONFLICT, Verdict.MODEL_AND_INPUTS):
            caption += ' The test weighs the inputs together, so it does not say which of them is off.'
        self.tests_caption.setText(caption)
