"""Binding model: the model a fit describes the data with, and what it needs besides the data (DESIGN.md §8).

A form on the canvas, from the components of Input uncertainty and on its column grid:
**Model** — the category, then the model; **Conditions** — each entered condition with
its unit; **Titrant stock** — whether the additions dilute the sample, and if so the
stock and the concentrations it holds; **Bounds of the fitted parameters**;
**Replicates** — the average only, or each replicate on its own as well. No side panel.
Every edit goes to the session model's :class:`~gui.binding.BindingForm`; the view redraws
when the model says the binding model or the data changed.
"""

from __future__ import annotations

from PyQt6.QtCore import QMargins, QObject, Qt, QTimer
from PyQt6.QtWidgets import QFileDialog, QGridLayout, QMessageBox, QScrollArea, QWidget

from core.assays.registry import ASSAY_REGISTRY, ParamKind
from core.pipeline.inputs import TITRANT_STOCK
from core.pipeline.varpro import projectable
from gui.binding import CATEGORIES, HELP_TITLE, help_html
from gui.dataset import file_filter
from gui.design import components as C
from gui.design.appearance import theme
from gui.design.tokens import SIZE, space
from gui.plotting.labels import CONSTANT_NAMES, and_join, fmt_constant, fmt_param, fmt_param_plain, fmt_unit_pretty
from gui.session_model import Change, SessionModel
from gui.views.uncertainty import COL_KIND, COL_NAME, COL_UNIT, GUTTER
from gui.widgets.assay_conditions import ASSAY_NAMES, TITRANT_STOCK_FIELD, UNIT_CHOICES
from gui.widgets.info_button import show_help

#: The widest value a field must show: a sign, five figures and an exponent.
_WIDEST_VALUE = '−1.2345e−12'
#: The concentration units a condition is entered in.
_UNITS = list(UNIT_CHOICES['concentration'][0])
#: Pause in typing after which an edit of a condition counts as finished, in ms.
_EDIT_SETTLE_MS = 600
_DILUTION = ('Stay constant', 'Are diluted')
_REPLICATES = ('The average', 'Each replicate separately')


def _caption(text: str) -> QWidget:
    """A form row's caption in the name column."""
    cap = C.label(text, 'label', 'tertiary')
    cap.setFixedWidth(COL_NAME)
    return cap


def _grid() -> QGridLayout:
    grid = QGridLayout()
    grid.setContentsMargins(QMargins())
    grid.setHorizontalSpacing(space(GUTTER))
    grid.setVerticalSpacing(space(3))
    return grid


def _clear(grid: QGridLayout) -> None:
    while grid.count():
        item = grid.takeAt(0)
        if item.widget() is not None:
            C.drop(item.widget())


def _name(html: str) -> QWidget:
    """A row's name in the name column, rich text on the control's height."""
    lbl = C.label(html, 'body-strong', rich=True)
    lbl.setFixedHeight(SIZE['control'])
    return lbl


def _model_summary(form) -> str:
    """What the model fits under the bounds stated, in HTML: ``Fits K<sub>a</sub> guest and 3 signal parameters``.

    A parameter whose bounds meet is held there and not fitted (as I_H in the stepwise
    models opens), so it is neither named nor counted.
    """
    kinds = ASSAY_REGISTRY[form.assay_type].param_kinds
    fitted = [key for key in kinds if not _held(form.bound_entries[key])]
    constants = [key for key in fitted if kinds[key] is ParamKind.BINDING_CONSTANT]
    if fitted and not any(kind is ParamKind.BINDING_CONSTANT for kind in kinds.values()):
        return f'Fits a straight line: its {and_join(fmt_param_plain(key) for key in fitted)}'
    n = len(fitted) - len(constants)
    terms = [
        *(fmt_constant(key) for key in constants),
        *([f'{n} signal parameter{"" if n == 1 else "s"}'] if n else []),
    ]
    return f'Fits {and_join(terms)}' if terms else 'Fits no parameter: the bounds of each one meet'


def _held(entry) -> bool:
    """Whether a parameter's bounds meet, so the fit holds it there."""
    values = entry.values()
    return values is not None and values[0] == values[1]


def _parameter_name(key: str) -> str:
    """A fitted parameter's name in HTML: a binding constant by its glossary name, a signal by its symbol."""
    return fmt_constant(key) if key in CONSTANT_NAMES else fmt_param(key)


class _ConditionRow:
    """The widgets of one condition: its name, its value, its unit and what it is."""

    def __init__(self, view: BindingView, key: str, grid: QGridLayout, r: int):
        t, form = view.t, view.model.binding
        entry = form.entry(key)
        self.key = key
        field = entry.field
        self.name = _name(field.label)
        self.value = C.Field(t, '', view.value_w, editable=True)
        self.value.setToolTip(field.tooltip)
        self.value.typed.connect(lambda text: view._typed(lambda f: f.edit(key, text)))
        self.value.edited.connect(lambda _text: view._finished())
        if field.unit_type == 'concentration':
            self.unit = C.Dropdown(t, _UNITS, _UNITS.index(entry.unit), COL_UNIT)
            self.unit.setAccessibleName(f'Unit of {entry.name}')
            self.unit.chosen.connect(lambda i: view._edit(lambda f: f.set_unit(key, _UNITS[i])))
        else:
            self.unit = C.label(fmt_unit_pretty(field.unit), 'body', 'secondary')
            self.unit.setFixedWidth(COL_UNIT)
        about = C.wrapped(field.tooltip, 'small', 'tertiary')
        self.problem = C.Problem(t)
        for c, widget in enumerate((self.name, self.value, self.unit, about)):
            grid.addWidget(widget, r, c, Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(self.problem, r + 1, 1, 1, 3)

    def controls(self) -> list[QWidget]:
        return [self.value, self.unit] if isinstance(self.unit, C.Dropdown) else [self.value]

    def focus_chain(self) -> list[QWidget]:
        return [self.value.editor, *self.controls()[1:]]


class _BoundRow:
    """The widgets of one fitted parameter's bounds: its name, lower and upper bound, and unit."""

    def __init__(self, view: BindingView, key: str, grid: QGridLayout, r: int):
        t = view.t
        entry = view.model.binding.bound_entries[key]
        unit = fmt_unit_pretty(entry.unit)
        self.key = key
        self.fields = []
        for index, edge in enumerate(('Lower', 'Upper')):
            field = C.Field(t, '', view.value_w, editable=True)
            field.setAccessibleName(f'{edge} bound of {entry.name}' + (f' ({unit})' if unit else ''))
            field.typed.connect(lambda text, index=index: view._edit(lambda f: f.edit_bound(key, index, text), False))
            self.fields.append(field)
        if entry.may_be_unbounded:
            self.fields[1].editor.setPlaceholderText('no limit')
            self.fields[1].setToolTip('Leave empty for no upper limit.')
        self.unit = C.label(unit, 'body', 'secondary')
        self.unit.setFixedWidth(COL_UNIT)
        self.problem = C.Problem(t)
        for c, widget in enumerate((_name(_parameter_name(key)), *self.fields, self.unit)):
            grid.addWidget(widget, r, c, Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(self.problem, r + 1, 1, 1, 4)


class BindingView(QObject):
    """The canvas of Binding model over *model*; *parent* is where its dialogs open."""

    def __init__(self, model: SessionModel, parent: QWidget):
        super().__init__(parent)
        self.model, self.parent, self.t = model, parent, theme()
        self._locked = False
        self._shape = None
        self._conditions: dict[str, _ConditionRow] = {}
        self._bounds: dict[str, _BoundRow] = {}
        self._contains: dict[str, C.Checkbox] = {}
        self.value_w = C.Field.width_for(_WIDEST_VALUE)
        self.form_w = COL_KIND + C.Field.width_for(_WIDEST_VALUE, 'from') + COL_UNIT + 2 * space(GUTTER)
        self._settle = QTimer(self)
        self._settle.setSingleShot(True)
        self._settle.setInterval(_EDIT_SETTLE_MS)
        self._settle.timeout.connect(self._finished)
        self.canvas = self._build_canvas()
        model.changed.connect(self._on_changed)
        self.refresh()

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def _edit(self, change, finished: bool = True) -> None:
        """Make *change* to the session's binding model, and tell the model it changed."""
        change(self.model.binding)
        self.model.binding_edited(finished)

    def _typed(self, change) -> None:
        """A keystroke in a condition: taken now, and checked once the edit is finished or typing pauses."""
        self._edit(change, finished=False)
        self._settle.start()

    def _finished(self) -> None:
        self._settle.stop()
        self.model.edit_finished()

    def show_help(self) -> None:
        show_help(self.parent.window(), HELP_TITLE, help_html(self.model.binding.assay_type))

    def set_locked(self, locked: bool) -> None:
        """Lock every control while a fit or an analysis reads the binding model."""
        self._locked = locked
        self.refresh()

    def badge(self) -> str:
        """The summary beside the title: the model in short and how many binding constants it fits."""
        return self.model.binding.badge()

    def _bounds_from_dye_alone(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self.parent, 'Bounds from dye alone', '', file_filter())
        if not path:
            return
        refusal = self.model.bounds_from_dye_alone(path)
        if refusal is not None:
            QMessageBox.warning(self.parent, refusal.title, refusal.message)

    # ------------------------------------------------------------------
    # Building
    # ------------------------------------------------------------------

    def _build_canvas(self) -> QWidget:
        t = self.t
        w = QWidget()
        w.setObjectName('Canvas')
        w.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        intro = C.wrapped(
            'The model the fit describes the data with, the conditions it was measured under, and where the '
            'fit looks for each parameter.'
        )
        self.help_link = C.link_button('About this model')
        self.help_link.clicked.connect(self.show_help)

        # Model
        options = list(CATEGORIES)
        self.category = C.Dropdown(t, options, width=self.form_w)
        self.category.setAccessibleName('Category of the binding model')
        self.category.chosen.connect(lambda i: self._edit(lambda f: f.choose_category(options[i])))
        self.assay = C.Dropdown(t, width=self.form_w)
        self.assay.setAccessibleName('Binding model')
        self.assay.chosen.connect(lambda i: self._edit(lambda f: f.choose_model(CATEGORIES[f.category][i])))
        self.summary = C.label('', 'small', 'tertiary', rich=True)
        model = QWidget()
        model.setLayout(
            C.vbox(
                C.hbox(_caption('Category'), self.category, None, spacing=GUTTER),
                3,
                C.hbox(_caption('Model'), self.assay, None, spacing=GUTTER),
                1,
                C.hbox(_caption(''), self.summary, None, spacing=GUTTER),
                spacing=0,
            )
        )

        # Conditions
        self.cond_grid = _grid()
        self.no_conditions = C.label('', 'body', 'tertiary')
        conditions = QWidget()
        conditions.setLayout(C.vbox(self.no_conditions, self.cond_grid, spacing=0))

        # Titrant stock
        self.dilution = C.Segmented(t, list(_DILUTION), 0, self.form_w, dividers=True)
        self.dilution.setAccessibleName('Whether the additions of titrant dilute the fixed totals')
        self.dilution.setToolTip(
            'Whether each addition of titrant dilutes the sample. It does not if the samples were made up to '
            'the same volume, or if the titrant stock was prepared in the sample solution itself.'
        )
        self.dilution.changed.connect(lambda i: self._edit(lambda f: f.set_diluted(i == 1)))
        self.totals = C.label('Totals during the titration', 'label', 'tertiary')
        self.totals.setWordWrap(True)
        self.totals.setFixedWidth(COL_NAME)
        self.stock = C.Field(t, '', self.value_w, editable=True)
        self.stock.setToolTip(TITRANT_STOCK_FIELD.tooltip)
        self.stock.typed.connect(lambda text: self._typed(lambda f: f.edit(TITRANT_STOCK, text)))
        self.stock.edited.connect(lambda _text: self._finished())
        self.stock_unit = C.Dropdown(t, _UNITS, width=COL_UNIT)
        self.stock_unit.setAccessibleName('Unit of the titrant stock concentration')
        self.stock_unit.chosen.connect(lambda i: self._edit(lambda f: f.set_unit(TITRANT_STOCK, _UNITS[i])))
        self.stock_caption = _caption('Stock concentration')
        self.stock_row = QWidget()
        self.stock_row.setLayout(C.hbox(self.stock, self.stock_unit, None, spacing=GUTTER))
        self.stock_problem = C.Problem(t)
        self.contains_caption = _caption('Stock also contains')
        self.contains_box = C.hbox(spacing=5)
        self.contains_row = QWidget()
        self.contains_row.setLayout(
            C.hbox(self.contains_box, C.label('at the sample’s own concentration', 'small', 'tertiary'), None)
        )
        self.contains_problem = C.Problem(t)
        grid = _grid()
        left = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        rows = (
            (self.totals, self.dilution),
            (
                None,
                C.label(
                    'The concentrations in the data are the titrant in the cuvette after each addition.',
                    'small',
                    'tertiary',
                ),
            ),
            (self.stock_caption, self.stock_row),
            (None, self.stock_problem),
            (self.contains_caption, self.contains_row),
            (None, self.contains_problem),
        )
        for r, (caption, control) in enumerate(rows):
            if caption is not None:
                grid.addWidget(caption, r, 0, left)
            if isinstance(control, C.Problem):
                grid.addWidget(control, r, 1)  # a sentence takes the width of the form
            else:
                grid.addWidget(control, r, 1, left)
        grid.setColumnMinimumWidth(0, COL_NAME)
        grid.setColumnStretch(1, 1)
        stock = QWidget()
        stock.setLayout(grid)
        self.stock_section = C.canvas_section('Titrant stock', stock, 'totals stay constant until you say otherwise')

        # Bounds
        self.bound_grid = _grid()
        self.reset = C.OutlineButton(t, 'Reset to defaults')
        self.reset.clicked.connect(lambda: self._edit(lambda f: f.reset_bounds()))
        self.dye_alone = C.OutlineButton(t, 'Bounds from dye alone…')
        self.dye_alone.clicked.connect(self._bounds_from_dye_alone)
        self.dye_alone.setToolTip(
            'Fit a straight line to a dye-only calibration and bound the baseline and the free-dye signal '
            'to ±20 % of what it measured.'
        )
        bounds = QWidget()
        bounds.setLayout(
            C.vbox(self.bound_grid, 4, C.hbox(_caption(''), self.reset, self.dye_alone, None, spacing=GUTTER))
        )

        # Replicates
        self.replicates = C.Segmented(t, list(_REPLICATES), 0, self.form_w, dividers=True)
        self.replicates.setAccessibleName('How the replicates enter the fit')
        self.replicates.changed.connect(lambda i: self._edit(lambda f: f.set_per_replica(i == 1)))
        self.replicates_note = C.wrapped('', 'small', 'tertiary')
        self.replicates_note.setMaximumWidth(SIZE['measure'])
        self.replicates_row = QWidget()
        self.replicates_row.setLayout(C.hbox(_caption('Fit'), self.replicates, None, spacing=GUTTER))
        note = C.hbox(_caption(''), self.replicates_note, None, spacing=GUTTER)
        note.setStretchFactor(self.replicates_note, 1)
        replicates = QWidget()
        replicates.setLayout(
            C.vbox(
                self.replicates_row,
                2,
                note,
                spacing=0,
            )
        )

        self.conditions_section = C.canvas_section('Conditions', conditions, 'what the model needs besides the data')
        sections = C.vbox(
            C.canvas_section('Model', model, first=True),
            self.conditions_section,
            self.stock_section,
            C.canvas_section('Bounds of the fitted parameters', bounds, 'the range each parameter is fitted in'),
            C.canvas_section('Replicates', replicates),
            spacing=0,
        )
        head = C.hbox(intro, 6, C.vbox(self.help_link, None), spacing=0)
        head.setStretch(0, 1)
        w.setLayout(C.vbox(head, 6, sections, None, spacing=0, margins=(6, 5, 6, 4)))
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        area.setWidget(w)
        return area

    def _build_rows(self) -> None:
        """Lay the conditions, the stock's species and the bounds out again for the model shown."""
        form = self.model.binding
        _clear(self.cond_grid)
        self._conditions = {}
        heads = ('Condition', 'Value', 'Unit', '')
        for r, key in enumerate(form.entries):
            if r == 0:
                for c, h in enumerate(heads):
                    self.cond_grid.addWidget(C.label(h, 'label', 'tertiary'), 0, c)
                self.cond_grid.addWidget(C.hairline(), 1, 0, 1, 4)
            self._conditions[key] = _ConditionRow(self, key, self.cond_grid, 2 + 3 * r)
            if r < len(form.entries) - 1:
                self.cond_grid.addWidget(C.hairline(), 4 + 3 * r, 0, 1, 4)
        for c, width in enumerate((COL_NAME, self.value_w, COL_UNIT)):
            self.cond_grid.setColumnMinimumWidth(c, width)
        self.cond_grid.setColumnStretch(3, 1)

        for box in self._contains.values():
            self.contains_box.removeWidget(box)
            C.drop(box)
        self._contains = {}
        for key in form.concentration_keys() if form.offers_contains else ():
            entry = form.entry(key)
            box = C.Checkbox(self.t, entry.field.label, rich=True)
            box.setAccessibleName(f'The titrant stock also contains {entry.name} at the sample’s concentration')
            box.toggled.connect(lambda on, key=key: self._edit(lambda f: f.set_contains(key, on)))
            self.contains_box.addWidget(box)
            self._contains[key] = box

        _clear(self.bound_grid)
        self._bounds = {}
        for c, h in enumerate(('Parameter', 'Lower', 'Upper', 'Unit', '')):
            self.bound_grid.addWidget(C.label(h, 'label', 'tertiary'), 0, c)
        self.bound_grid.addWidget(C.hairline(), 1, 0, 1, 5)
        keys = list(form.bound_entries)
        for r, key in enumerate(keys):
            self._bounds[key] = _BoundRow(self, key, self.bound_grid, 2 + 3 * r)
            if r < len(keys) - 1:
                self.bound_grid.addWidget(C.hairline(), 4 + 3 * r, 0, 1, 5)
        for c, width in enumerate((COL_NAME, self.value_w, self.value_w, COL_UNIT)):
            self.bound_grid.setColumnMinimumWidth(c, width)
        self.bound_grid.setColumnStretch(4, 1)
        self._chain_focus()

    def _chain_focus(self) -> None:
        """Chain the controls in the order they are read: Qt orders them by creation, and rows come and go."""
        chain: list[QWidget] = [self.category, self.assay]
        for row in self._conditions.values():
            chain += row.focus_chain()
        chain += [self.dilution, self.stock.editor, self.stock_unit, *self._contains.values()]
        for row in self._bounds.values():
            chain += [field.editor for field in row.fields]
        chain += [self.reset, self.dye_alone, self.replicates]
        for first, second in zip(chain, chain[1:]):
            QWidget.setTabOrder(first, second)

    # ------------------------------------------------------------------
    # Drawing from the model
    # ------------------------------------------------------------------

    def _on_changed(self, what: Change) -> None:
        # A fit and an analysis read the binding model as it was when they started.
        running = self.model.fit_running() or self.model.sensitivity_running()
        if running != self._locked:
            self.set_locked(running)
        elif what & (Change.BINDING | Change.DATA):
            self.refresh()

    def refresh(self) -> None:
        """Draw the binding model as the model holds it, rebuilding the rows when the model chosen changed."""
        form = self.model.binding
        shape = (form.assay_type, tuple(form.entries), tuple(form.bound_entries))
        if shape != self._shape:
            self._build_rows()
            self._shape = shape
        on = not self._locked
        models = CATEGORIES[form.category]
        self.category.set_current(list(CATEGORIES).index(form.category))
        self.assay.set_options([ASSAY_REGISTRY[at].subtype_label for at in models], models.index(form.assay_type))
        name = ASSAY_NAMES[form.assay_type][0]
        self.summary.setText(_model_summary(form))
        for dropdown in (self.category, self.assay):
            dropdown.setEnabled(on)

        # Conditions
        self.no_conditions.setText(f'{name} needs no conditions besides the data.')
        self.no_conditions.setVisible(not form.entries)
        for key, row in self._conditions.items():
            entry = form.entry(key)
            row.value.set_text(entry.amount.text)
            row.value.setAccessibleName(f'{entry.name} ({entry.unit})')
            if isinstance(row.unit, C.Dropdown):
                row.unit.set_current(_UNITS.index(entry.unit))
            problem = form.condition_problem(key)
            row.problem.show_problems([problem] if problem else [])
            for control in row.controls():
                control.setEnabled(on)

        # Titrant stock
        self.stock_section.setVisible(form.offers_dilution)
        self.dilution.set_current(1 if form.diluted else 0)
        self.dilution.setEnabled(on)
        for widget in (self.stock_caption, self.stock_row):
            widget.setVisible(form.diluted)
        self.stock.set_text(form.stock.amount.text)
        self.stock.setAccessibleName(f'Titrant stock concentration ({form.stock.unit})')
        self.stock_unit.set_current(_UNITS.index(form.stock.unit))
        for control in (self.stock, self.stock_unit):
            control.setEnabled(on)
        stock_problems = [p for p in (form.condition_problem(TITRANT_STOCK), self.model.stock_problem()) if p]
        self.stock_problem.show_problems(stock_problems)
        for widget in (self.contains_caption, self.contains_row):
            widget.setVisible(form.diluted and form.offers_contains)
        for key, box in self._contains.items():
            box.set_checked(key in form.contains)
            box.setEnabled(on)
        everything = [p for p in form.problems() if p.startswith('The titrant stock is ticked for every')]
        self.contains_problem.show_problems(everything)

        # Bounds
        for key, row in self._bounds.items():
            entry = form.bound_entries[key]
            for field, amount in zip(row.fields, entry.amounts, strict=True):
                field.set_text(amount.text)
                field.setEnabled(on)
            problem = entry.problem()
            row.problem.show_problems([problem] if problem else [])
        self.reset.setEnabled(on)
        bounded = form.dye_alone_keys()
        self.dye_alone.setVisible(bool(bounded))
        self.dye_alone.setEnabled(on)

        # Replicates
        # A calibration has no binding constant to test the replicates by, so it is fitted
        # from their average whatever the mode says.
        tested = projectable(form.assay_type)
        self.replicates_row.setVisible(tested)
        self.replicates.set_current(1 if form.per_replica else 0)
        self.replicates.setEnabled(on)
        if not tested:
            note = f'{name} is fitted from the average of the replicates switched on.'
        elif form.per_replica:
            note = (
                'Each replicate is also fitted on its own; one whose Kₐ or scatter disagrees with the others is '
                'left out of the average and named. The test needs three replicates or more.'
            )
        else:
            note = 'Every replicate switched on goes into the average, whatever it looks like.'
        self.replicates_note.setText(note)
