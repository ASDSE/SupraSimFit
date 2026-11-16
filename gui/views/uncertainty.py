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

from core.assays.registry import ASSAY_REGISTRY
from core.pipeline.diagnostics import Verdict
from core.pipeline.inputs import TITRANT, SpecKind
from core.units import Q_
from gui.design import components as C
from gui.design.appearance import theme
from gui.design.tokens import SIZE, space
from gui.plotting.labels import THIN, times_ten, verdict_headline
from gui.results import Place, interval_caption, ka_blocks, test_rows
from gui.session_model import Change, SessionModel
from gui.uncertainty import ADDITION_MODES, REPLICATE_KINDS, InputEntry, spread_pct
from gui.widgets.assay_conditions import format_condition

_KINDS = (None, SpecKind.SIGMA, SpecKind.INTERVAL)

#: Column grid of the inputs table; the span column takes the rest.
COL_NAME, COL_KIND, COL_UNIT, COL_BAR = SIZE['input-name'], SIZE['input-kind'], SIZE['stated-in'], SIZE['spread-bar']
GUTTER = 4  # a step of the spacing scale
#: The widest amount a field must show: a sign, five figures and an exponent.
_WIDEST_AMOUNT = '−1.2345e7'
#: What each amount field of an input holds, as its accessible name says.
_AMOUNTS = ('σ', 'Lower end', 'Upper end')


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
        return f'{a / 10**e:.2f} – {b / 10**e:.2f}{times_ten(e)} {unit}'.replace('-', '−')
    return f'{_num(a)} – {_num(b)} {unit}'


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

    :attr:`reveal_requested` asks for the readings of Ka confidence (*Review in Ka
    confidence →*), where the tests are reviewed; the session shows them.
    """

    reveal_requested = pyqtSignal(object)

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
        model.changed.connect(self._on_changed)
        self.refresh()

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def _edit(self, change) -> None:
        """Make *change* to the session's statement, and tell the model it changed."""
        change(self.model.uncertainty)
        self.model.uncertainty_edited()

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
        self.review.clicked.connect(lambda: self.reveal_requested.emit(Place.READINGS))
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

    def _on_changed(self, what: Change) -> None:
        # A fit and an analysis read the statement as it was when they started.
        running = self.model.fit_running() or self.model.sensitivity_running()
        if running != self._locked:
            self.set_locked(running)
        elif what & (Change.UNCERTAINTY | Change.DATA):
            self.refresh()
        elif what & (Change.RESULTS | Change.PROFILE):
            self._refresh_side()

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
                value = format_condition(entry.field, Q_(nominal, entry.field.unit), unit)
                row.entered.setText(f'Entered {value}'.replace('×', f'{THIN}×{THIN}'))
            else:
                row.entered.setText('')
            fixed = entry.kind is None
            row.kind.set_current(_KINDS.index(entry.kind))
            row.unit.set_options(['%', unit])
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
                f'{self.model.empty_view("Fit results").title}. The interval and the tests the stated uncertainties '
                'give appear here with the fit.'
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
        profile = self.model.profile if self.model.profiled_fit is fit else None
        blocks = ka_blocks(fit, profile, self.model.profile_running())
        if not blocks:
            self._caption('This fit has no association constant, so it has no interval.')
            return
        drawn = [b for b in blocks if b.rows]
        missing = [b.name for b in blocks if not b.rows]
        no_interval = f'This fit records no interval for {" and ".join(missing)}.' if missing else ''
        for block in drawn:
            # The compact chart has no badge: a split reading says so in its label.
            rows = [
                {**row, 'label': f'{row["label"]} · {row["badge"]}' if row.get('badge') else row['label']}
                for row in block.rows
            ]
            unit_line = C.label(f'{block.name}, {block.level}, {block.axis_unit}', 'small', 'tertiary', rich=True)
            chart = C.CompactIntervals(self.t, rows, block.lo, block.hi, block.ticks)
            for widget in (unit_line, chart):
                self.interval_box.addWidget(widget)
            self.unit_lines.append(unit_line)
            self.charts.append(chart)
        caption = interval_caption(fit, drawn) if drawn else ''
        self._caption(' '.join(filter(None, (caption, no_interval))))

    def _caption(self, text: str) -> None:
        self.interval_caption.setText(text)
        self.interval_caption.setVisible(bool(text))

    def _show_tests(self, fit) -> None:
        diag = fit.diagnostics
        self.tests_section.setVisible(diag is not None)
        if diag is None:
            return
        for test in test_rows(fit):
            self.test_rows.addWidget(C.test_line(self.t, test.icon, test.tone, test.text, test.p, test.tooltip))
        caption = verdict_headline(diag)[0] + '.'
        if diag.verdict in (Verdict.INPUTS_CONFLICT, Verdict.MODEL_AND_INPUTS):
            caption += ' The test weighs the inputs together, so it does not say which of them is off.'
        self.tests_caption.setText(caption)
