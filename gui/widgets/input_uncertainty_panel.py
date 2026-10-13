"""InputUncertaintyPanel — what the user knows about the inputs a fit rests on.

One row per perturbable input (the titrant series plus every concentration /
binding-constant condition): its uncertainty as a σ or a range, in percent of the
entered value or in the input's own unit, or *fixed*. Every row opens fixed, so a
fit takes the entered inputs as exact until an uncertainty is stated.

Below the rows the panel states the rest of the
:class:`~core.pipeline.inputs.ErrorModel`: the shared error sources, each a σ in
percent and the inputs it moves together, and the random error of each titrant
addition.

What the panel collects feeds two things: the confidence interval of every fit
(:func:`core.pipeline.input_aware.input_aware` lets the fit move each input inside
its uncertainty, and :mod:`core.pipeline.inflation` widens the cut-off by what the
random error of each addition adds) and the Ka sensitivity analysis
(:class:`~core.pipeline.sensitivity.SensitivityConfig`), which draws the sources from
the same model. The panel itself runs neither — it emits :attr:`specs_changed` and
the owning session reads :meth:`current_errors` and :meth:`problems`.

An assay whose signal the engine cannot project onto binding constants
(:func:`core.pipeline.varpro.projectable`) reports no association constant, so an
input uncertainty would change nothing there: the panel is disabled with a sentence
saying why.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QStyle,
    QStyleOptionFrame,
    QVBoxLayout,
    QWidget,
)

from core.assays.registry import ASSAY_REGISTRY, AssayType
from core.pipeline.inputs import (
    AdditionError,
    ErrorModel,
    InputSpec,
    SharedSource,
    SpecKind,
    axis_reaches_zero,
    perturbable_inputs,
    source_problems,
)
from core.pipeline.varpro import projectable
from core.units import Q_, Quantity
from gui.plotting.colors import INK_2
from gui.plotting.labels import plain_label
from gui.widgets.assay_conditions import ASSAY_CONDITIONS, ConditionField, input_labels
from gui.widgets.assay_config_panel import _UNIT_TYPE_CHOICES
from gui.widgets.info_button import InfoGroupBox
from gui.widgets.numeric_inputs import NoScrollDoubleSpinBox, SciLineEdit, format_number

_UNCERTAINTY_HELP_HTML = """
<h3>Input Uncertainty</h3>
<p>How far each input may be off: the titrant concentrations and the fixed
conditions (<i>[Host]<sub>0</sub></i>, <i>[Dye]<sub>0</sub></i>,
<i>K<sub>a,dye</sub></i>, …). Each carries pipetting, weighing or calibration error,
and the fit absorbs it by shifting the K<sub>a</sub> it reports.</p>
<p>What you state here feeds two things:</p>
<ul>
  <li><b>The interval of every fit.</b> The fit may move each input within its
      uncertainty, and the reported interval covers every K<sub>a</sub> that stays
      acceptable while it does. Stating uncertainties usually widens the interval.
      It narrows it where moving the inputs explains a misfit the entered values
      could not.</li>
  <li><b>The K<sub>a</sub> Sensitivity analysis</b>, which re-fits over many draws of
      these inputs and ranks the sources of the resulting spread of K<sub>a</sub>. It
      propagates what you state here with every draw counted the same, whereas the
      interval also weighs what the data say about the inputs, so the two can differ.
      It needs at least one input that is not fixed.</li>
</ul>
<p>Choose a kind for each input:</p>
<ul>
  <li><b>σ %</b> and <b>σ</b> — σ is one standard deviation of a normal
      distribution, in percent of the input's set value or in the input's own unit.
      The fit may put the input anywhere, but moving it by <i>e</i> costs
      (<i>e</i>/σ)<sup>2</sup>: one σ is cheap, three σ is not. Each sample of the
      analysis draws the input from that distribution, cut off so the input stays
      above zero. With σ = 5 %, about 95 of every 100 draws land within ±10 %, and a
      few further out.</li>
  <li><b>range %</b> and <b>range</b> — <i>from</i> and <i>to</i> as offsets in
      percent of the set value, or as the lowest and highest value in the input's own
      unit. For the fit every value between them is equally acceptable and none
      outside; each sample of the analysis draws evenly between them. A range may be
      lopsided, such as −6 % to +4 %.</li>
  <li><b>fixed</b> — the input is taken as exact: the fit holds it at the value you
      entered, and the analysis leaves it out.</li>
</ul>
<p>With every input fixed, as the panel starts, the reported interval is the interval
conditional on the entered inputs — what the data alone allow, the inputs taken as
exactly right.</p>
<p>Switching the kind carries the numbers over: σ = 5 % becomes the range −5 % to
+5 %, or a σ of 5 % of the set value in the input's unit, and a range becomes a σ of
half its width, centred on the set value. The spread of the draws changes with the
kind: an even draw between −5 % and +5 % varies less than a σ of 5 %. A number the new
boxes cannot hold, such as a range starting below −100 %, is replaced by the nearest one
they can, and the input says so.</p>
<p>A σ of 0, or a range whose <i>to</i> is not above its <i>from</i>, does not vary
the input. Nor can a value in the input's unit be used while the input is 0 in the
conditions. The input then shows a warning, and neither a fit nor an analysis starts
until you change the value or choose <b>fixed</b>.</p>
<p>Use realistic numbers: pipetting error is often a few percent, a stated
literature K<sub>a,dye</sub> may be uncertain by 10–20%.</p>
<h3>Shared error sources</h3>
<p>The entry on an input above is the error <b>only that input</b> has. An error several
inputs have in common — their solutions come from one stock, were weighed on one balance
or pipetted with one pipette — is a <b>shared error source</b>: name it, state its σ in
percent, and tick every input it moves. The sources are independent and multiply, so an
input with an entry of its own and a shared source carries both. A shared source moves
every concentration made from that stock by the same percentage, and a binding constant
measured with it (such as a K<sub>a,dye</sub> fitted with the same stock) by the same
percentage the other way.</p>
<p>Both the interval of every fit and the K<sub>a</sub> Sensitivity analysis use exactly
this model. The analysis reports a shared source as one item, which is what you can act
on: one stock to re-make, one pipette to recalibrate.</p>
<h3>Random error of each addition</h3>
<p>The titrant entry above moves the whole series by one factor — a stock or dilution
error that shifts every concentration by the same fraction. The scatter of the individual
additions is stated here instead. Choose <i>sequential additions into one cuvette</i>,
where every point carries the errors of the additions before it as well as its own, or
<i>separately prepared samples</i>, where each point is pipetted on its own.</p>
<p>A random error in each addition moves every point along the titrant axis. The
residuals show only part of that: for additions into one cuvette, most of it shifts the
whole curve the way a different K<sub>a</sub> would. When you state it, the fit works out
from your σ and the slope of the fitted curve how much more K<sub>a</sub> varies than the
scatter alone implies, and widens the interval of K<sub>a</sub> by the factor this
implies, never narrowing it. The result says by how much.</p>
<p>Choose what your replicates are. Replicates made as <i>separate titrations</i> each have
their own addition errors, and their average carries σ/√<i>m</i> of them for <i>m</i>
replicates. <i>Repeated reads of one titration</i> share them, and their average carries
σ itself. The data cannot tell the two apart reliably, so it is stated here; separate
titrations is the setting the panel opens with.</p>
<p>A σ larger than the real one gives a wider interval than needed. The K<sub>a</sub>
Sensitivity analysis samples the same error and ranks it against the other sources.</p>
"""

#: Significant figures an absolute value is shown and kept with.
_SIGFIGS = 5
#: The widest absolute value an entry box must show in full at ``_SIGFIGS``.
_WIDEST_ABSOLUTE = '8.8888e-10'
#: The σ a row offers when a kind is first chosen. Every row opens *fixed*, so this
#: number reaches a fit or an analysis only once the user picks a kind for the input.
_DEFAULT_SPEC = InputSpec.sigma_pct(5.0)
#: Indent of an input's value line under its label, and the gap below it before the next input.
_VALUE_INDENT = 12
_INPUT_GAP = 8
#: The σ a shared source and the additions entry open with — the number a row offers
#: when a kind is chosen. Stating the source is the user's explicit act; the number is
#: there to be edited, and reaches nothing until the source or the mode is stated.
_DEFAULT_SOURCE_SIGMA = _DEFAULT_SPEC.sigma
#: The entries of the per-addition error selector, each with the ``sequential`` flag it
#: states; ``None`` is no statement at all, not an error of zero.
_ADDITION_MODES: tuple[tuple[str, bool | None], ...] = (
    ('none', None),
    ('sequential additions into one cuvette', True),
    ('separately prepared samples', False),
)
#: The entries of the replicate selector of the additions entry, each with the
#: ``separate_titrations`` flag it states.
_REPLICATE_KINDS: tuple[tuple[str, bool], ...] = (
    ('separate titrations', True),
    ('repeated reads of one titration', False),
)
#: The additions entry as the panel opens it: no mode chosen, a σ to edit once one is,
#: and the replicates taken as separate titrations.
_NO_ADDITIONS = (0, _DEFAULT_SOURCE_SIGMA, 0)


def _unavailable_reason(assay_type: AssayType) -> str:
    """Why an input uncertainty changes nothing for *assay_type*, in one plain sentence."""
    return (
        f'{ASSAY_REGISTRY[assay_type].subtype_label} has no association constant, '
        'so an uncertainty in the inputs changes nothing here.'
    )


def _number(value: float, unit: str) -> str:
    """*value* in *unit* as the boxes show it, with a real minus sign: ``−150 %``, ``0.2 µM``."""
    return f'{format_number(value, _SIGFIGS)} {unit}'.replace('-', '−')


def _restate(spec: InputSpec, kind: SpecKind, relative: bool, nominal: float | None) -> InputSpec | None:
    """*spec* stated as another kind with the same centre and half-width.

    A σ is a half-width centred on the nominal value: σ = s becomes the range −s..+s,
    and a range becomes the σ of half its width, which drops any shift of its centre.
    A percentage and a value in the input's unit convert through *nominal*. Returns
    ``None`` when the conversion needs a nominal value and there is no positive one.
    """
    if (spec.kind, spec.relative) == (kind, relative):
        return spec
    if not (spec.relative and relative) and not (nominal is not None and nominal > 0):
        return None
    if spec.kind is SpecKind.SIGMA:
        centre, half = 0.0, spec.sigma / 100.0 if spec.relative else spec.sigma / nominal
    elif spec.relative:
        centre, half = (spec.lo + spec.hi) / 200.0, (spec.hi - spec.lo) / 200.0
    else:
        centre, half = ((spec.lo + spec.hi) / 2 - nominal) / nominal, (spec.hi - spec.lo) / (2 * nominal)
    if relative:
        if kind is SpecKind.SIGMA:
            return InputSpec.sigma_pct(100.0 * half)
        return InputSpec.interval_pct(100.0 * (centre - half), 100.0 * (centre + half))
    if kind is SpecKind.SIGMA:
        return InputSpec.sigma_abs(nominal * half)
    return InputSpec.interval_abs(nominal * (1 + centre - half), nominal * (1 + centre + half))


def _warning_label() -> QLabel:
    """A hidden red line for what is wrong with the row above it, as every row of the panel shows it."""
    label = QLabel()
    label.setWordWrap(True)
    label.setStyleSheet('color: #b42318;')
    label.hide()
    return label


def _fit_text_width(edit: QLineEdit, sample: str) -> None:
    """Fix *edit*'s width to show *sample* in full, measured with its font and style."""
    fm = edit.fontMetrics()
    text = edit.textMargins()
    content = edit.contentsMargins()
    # QLineEdit keeps 2 px of its own on each side; one digit more leaves room for the cursor.
    width = fm.horizontalAdvance(sample + '0') + text.left() + text.right() + content.left() + content.right() + 4
    opt = QStyleOptionFrame()
    edit.initStyleOption(opt)
    size = edit.style().sizeFromContents(QStyle.ContentsType.CT_LineEdit, opt, QSize(width, fm.height()), edit)
    edit.setFixedWidth(size.width())


class _ValueLine(QWidget):
    """The value fields of one uncertainty kind, on a single line.

    ``σ = [5.0] %`` or ``from [-6.0] to [4.0] %`` for a percentage, and ``σ = [8.4e5] M⁻¹``
    or ``from [4.085] to [4.515] µM`` in the input's own unit. An input offering several
    units gets a unit selector; one with a single unit shows it as text. Every box has a
    fixed width taken from its font, so the line is as wide whatever it holds.
    """

    edited = pyqtSignal()

    def __init__(self, interval: bool, field: ConditionField | None, parent=None):
        super().__init__(parent)
        self.absolute = field is not None
        self._units: list[tuple[str, float]] = [('%', 1.0)]
        default_unit = '%'
        if field is not None:
            choices, default_unit = _UNIT_TYPE_CHOICES[field.unit_type]
            self._units = [(label, float(Q_(1, label).to(field.unit).magnitude)) for label in choices]
        self._index = next(i for i, (label, _) in enumerate(self._units) if label == default_unit)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self._boxes: list[NoScrollDoubleSpinBox | SciLineEdit] = []
        self._words = ['“from”', '“to”'] if interval else ['σ']
        for word in ('from', 'to') if interval else ('σ =',):
            layout.addWidget(QLabel(word))
            box = self._absolute_box() if self.absolute else self._percent_box(interval)
            layout.addWidget(box)
            self._boxes.append(box)
        if len(self._units) > 1:
            self._unit_combo: QComboBox | None = QComboBox()
            for label, _ in self._units:
                self._unit_combo.addItem(label)
            self._unit_combo.setCurrentIndex(self._index)
            self._unit_combo.currentIndexChanged.connect(self._on_unit_changed)
            layout.addWidget(self._unit_combo)
        else:
            self._unit_combo = None
            layout.addWidget(QLabel(self._units[0][0]))
        layout.addStretch(1)

    def focus_widgets(self) -> list[QWidget]:
        """The widgets that take the keyboard on this line, in reading order."""
        return [*self._boxes] if self._unit_combo is None else [*self._boxes, self._unit_combo]

    def _percent_box(self, interval: bool) -> NoScrollDoubleSpinBox:
        box = NoScrollDoubleSpinBox()
        box.setDecimals(1)
        box.setSingleStep(1.0)
        box.setAlignment(Qt.AlignmentFlag.AlignRight)
        # Sized for the widest value any percent box takes, so σ and range boxes match.
        box.setRange(-100.0, 1000.0)
        box.setFixedWidth(box.sizeHint().width())
        # A σ cannot be negative; a range end can, down to -100 %.
        box.setRange(-100.0 if interval else 0.0, 1000.0)
        box.valueChanged.connect(self.edited)
        return box

    def _absolute_box(self) -> SciLineEdit:
        box = SciLineEdit(allow_negative=False, sigfigs=_SIGFIGS)
        _fit_text_width(box, _WIDEST_ABSOLUTE)
        # Keep a typed value to the figures shown, so the value used is the value on screen.
        box.value_changed.connect(lambda value: box.setValue(float(format_number(value, _SIGFIGS))))
        box.value_changed.connect(self.edited)
        return box

    def values(self) -> list[float]:
        """The entered values: percentages, or magnitudes in the input's base unit."""
        scale = self._units[self._index][1]
        return [box.value() * scale for box in self._boxes]

    def unreadable(self) -> list[str]:
        """The texts typed into this line that are not numbers."""
        return [box.text() for box in self._boxes if isinstance(box, SciLineEdit) and box.has_unreadable_edit()]

    def set_values(self, values: list[float]) -> list[str]:
        """Show *values* without emitting :attr:`edited`, as the boxes can hold them; name those they could not.

        A percentage is rounded to the box's one decimal and kept inside its range. A
        value in the input's unit is kept to the significant figures shown and to zero
        or more. Either way the value used is the value on screen. Returns a phrase for
        each value shown otherwise than by that rounding, such as
        ``“from” would be −150 %; this box can only show −100 %``.
        """
        unit, scale = self._units[self._index]
        misfits = []
        for word, box, value in zip(self._words, self._boxes, values):
            if isinstance(box, SciLineEdit):
                given = value / scale
                box.setValue(float(format_number(max(given, 0.0), _SIGFIGS)))
                shown = box.value()
                misfit = not math.isclose(shown, given, rel_tol=1e-4)
            else:
                given = value
                blocked = box.blockSignals(True)
                box.setValue(value)
                box.blockSignals(blocked)
                shown = box.value()
                # Beyond the rounding to one decimal, or a number that rounds away to 0.
                misfit = abs(shown - given) > 0.05 + 1e-9 or (shown == 0 and abs(given) > 1e-9)
            if misfit:
                misfits.append(f'{word} would be {_number(given, unit)}; this box can only show {_number(shown, unit)}')
        return misfits

    def unit_index(self) -> int:
        return self._index

    def set_unit_index(self, index: int) -> None:
        if self._unit_combo is not None:
            self._unit_combo.setCurrentIndex(index)

    def _on_unit_changed(self, index: int) -> None:
        values = self.values()
        self._index = index
        self.set_values(values)
        self.edited.emit()


@dataclass(frozen=True)
class _RowState:
    """An input's row as the user left it: the kind shown, what is carried into the next kind, and every kind's entries.

    ``pages`` holds, per kind, the values in the base unit and the unit index shown;
    ``None`` for *fixed*.
    """

    index: int
    carried: InputSpec
    pending: InputSpec | None
    pages: tuple[tuple[tuple[float, ...], int] | None, ...]


class _InputSpecRow(QWidget):
    """Uncertainty of one input: the chosen kind's values on one line, and a warning under them.

    The kind selector :attr:`kind` belongs to the row but sits on the input's label line,
    so the values get the panel's full width. A row opens on *fixed*, which takes the
    input as entered. A percentage is read against the input's nominal value; an absolute
    entry uses the input's own unit. The titrant is a series with no single nominal value,
    so it offers the percentage kinds only. Choosing another kind carries the entered
    numbers over (see :func:`_restate`), and a number the new kind's boxes cannot hold is
    named under the values until the next edit. A conversion that needs a nominal value
    above 0 waits for one, with a warning. The value line has one page per kind, so the
    row is as wide whichever kind is chosen.
    """

    changed = pyqtSignal()

    def __init__(self, name: str, field: ConditionField | None, parent=None):
        super().__init__(parent)
        self.name = name
        self._nominal: float | None = None if field is None else field.default

        choices: list[tuple[str, tuple[SpecKind, bool] | None]] = [
            ('σ %', (SpecKind.SIGMA, True)),
            ('range %', (SpecKind.INTERVAL, True)),
        ]
        if field is not None:
            choices += [('σ', (SpecKind.SIGMA, False)), ('range', (SpecKind.INTERVAL, False))]
        choices.append(('fixed', None))

        self.kind = QComboBox()
        self.kind.setToolTip(
            'σ is one standard deviation of a normal distribution. A range is drawn evenly between '
            'its two ends and may be lopsided. Fixed takes the set value as exact.'
        )
        self._values = QStackedWidget()
        for text, data in choices:
            self.kind.addItem(text, data)
            if data is None:
                page = QLabel('taken as exact')
            else:
                page = _ValueLine(data[0] is SpecKind.INTERVAL, None if data[1] else field)
                page.edited.connect(self._on_edited)
            self._values.addWidget(page)
        self._values.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        self._warning = _warning_label()

        layout = QVBoxLayout(self)
        # Indented under the label; the bottom margin separates this input from the next.
        layout.setContentsMargins(_VALUE_INDENT, 0, 0, _INPUT_GAP)
        layout.setSpacing(4)
        layout.addWidget(self._values)
        layout.addWidget(self._warning)

        # The last uncertainty that varied the input, carried into the next kind chosen.
        self._carried = _DEFAULT_SPEC
        # A carried uncertainty the kind shown could not take yet: it needs a nominal value above 0.
        self._pending: InputSpec | None = None
        # The numbers the kind shown could not hold as carried over, until the next edit.
        self._misfits: list[str] = []
        # Every input starts fixed, so a fit takes the entered inputs as exact until the
        # user states an uncertainty; the σ page already holds the value a kind starts from.
        fixed = self.kind.count() - 1
        self._shown = fixed
        self._write(0, _DEFAULT_SPEC)
        self.kind.setCurrentIndex(fixed)
        self._values.setCurrentIndex(fixed)
        self.kind.currentIndexChanged.connect(self._on_kind_changed)
        self._refresh()

    def setEnabled(self, enabled: bool) -> None:  # Qt override: the selector is not a child
        super().setEnabled(enabled)
        self.kind.setEnabled(enabled)

    def focus_widgets(self) -> list[QWidget]:
        """The widgets that take the keyboard in this row: the kind selector, then the values.

        Every kind's page is chained; Qt passes over the hidden ones, so the order
        holds whichever kind is shown.
        """
        widgets: list[QWidget] = [self.kind]
        for page in map(self._values.widget, range(self._values.count())):
            if isinstance(page, _ValueLine):
                widgets += page.focus_widgets()
        return widgets

    def spec(self) -> InputSpec | None:
        """The :class:`InputSpec` this row describes; ``None`` when the input is fixed."""
        return self._read(self.kind.currentIndex())

    def set_spec(self, spec: InputSpec | None) -> None:
        """Show *spec* as entered; ``None`` fixes the input."""
        data = None if spec is None else (spec.kind, spec.relative)
        index = next(i for i in range(self.kind.count()) if self.kind.itemData(i) == data)
        blocked = self.kind.blockSignals(True)
        self.kind.setCurrentIndex(index)
        self.kind.blockSignals(blocked)
        self._pending, self._misfits = None, []
        if spec is not None:
            self._write(index, spec)
        self._show(index)

    def set_nominal(self, nominal: float) -> None:
        """The input's set value in its base unit, which percentages are read against.

        A conversion waiting for a set value above 0 is made now.
        """
        self._nominal = nominal
        if self._pending is not None and nominal > 0:
            self._write(self._shown, self._pending)
        self._refresh()

    def state(self) -> _RowState:
        """What this row shows, for :meth:`restore`."""
        pages = tuple(
            (tuple(page.values()), page.unit_index()) if isinstance(page, _ValueLine) else None
            for page in map(self._values.widget, range(self._values.count()))
        )
        return _RowState(self._shown, self._carried, self._pending, pages)

    def restore(self, state: _RowState) -> None:
        """Show *state* again: the kind, every kind's entries and units, and what is carried over."""
        for index, page_state in enumerate(state.pages):
            if page_state is not None:
                values, unit_index = page_state
                page = self._values.widget(index)
                page.set_unit_index(unit_index)
                page.set_values(list(values))
        blocked = self.kind.blockSignals(True)
        self.kind.setCurrentIndex(state.index)
        self.kind.blockSignals(blocked)
        self._carried, self._pending, self._misfits = state.carried, state.pending, []
        self._show(state.index)

    def problem(self) -> str | None:
        """Why the values shown cannot be used, as a sentence naming the input; ``None`` when they can.

        A σ is a penalty the fit pays and a distribution truncated above zero, so only a
        range can take the input down to zero, where the model has nothing to fit.
        """
        problem = self._entry_problem()
        if problem is not None:
            return problem
        spec = self.spec()
        if spec is not None and spec.kind is SpecKind.INTERVAL and axis_reaches_zero(spec, self._nominal, self.name):
            end = '−100 %' if spec.relative else '0'
            return f'{self.name} would be taken down to zero: set “from” above {end}.'
        return None

    def _entry_problem(self) -> str | None:
        """Why the values shown cannot be read or cannot vary the input; ``None`` when they can."""
        spec = self.spec()
        if spec is None:
            return None
        page = self._values.widget(self.kind.currentIndex())
        typed = page.unreadable() if isinstance(page, _ValueLine) else []
        if typed:
            return f'{self.name}: “{typed[0]}” is not a number. Enter a number, or choose “fixed”.'
        if self._pending is not None:
            return (
                f'{self.name} is 0 in the conditions, so its uncertainty cannot be converted to '
                f'“{self.kind.currentText()}”: set {self.name} above 0 first.'
            )
        if not spec.relative and not (self._nominal is not None and self._nominal > 0):
            return (
                f'{self.name} is 0 in the conditions, so an uncertainty in its unit cannot be used: '
                f'set {self.name} above 0 first.'
            )
        if spec.varies:
            return None
        if spec.kind is SpecKind.SIGMA:
            return f'{self.name} cannot vary: set σ above 0, or choose “fixed”.'
        return f'{self.name} cannot vary: set “to” above “from”, or choose “fixed”.'

    def _read(self, index: int) -> InputSpec | None:
        data = self.kind.itemData(index)
        if data is None:
            return None
        kind, relative = data
        values = self._values.widget(index).values()
        if kind is SpecKind.SIGMA:
            return InputSpec(kind, sigma=values[0], relative=relative)
        return InputSpec(kind, lo=values[0], hi=values[1], relative=relative)

    def _write(self, index: int, spec: InputSpec) -> None:
        """Show *spec* on the page of kind *index*, keeping what it could not hold; wait when that needs a nominal value."""
        kind, relative = self.kind.itemData(index)
        restated = _restate(spec, kind, relative, self._nominal)
        if restated is None:
            self._pending = spec
            return
        self._pending = None
        values = [restated.sigma] if kind is SpecKind.SIGMA else [restated.lo, restated.hi]
        self._misfits = self._values.widget(index).set_values(values)

    def _on_edited(self) -> None:
        self._pending, self._misfits = None, []
        self._refresh()

    def _on_kind_changed(self, index: int) -> None:
        previous = self._read(self._shown)
        # Values waiting for a conversion are stale: the uncertainty to carry is the one waiting.
        if previous is not None and self._pending is None:
            self._carried = previous
        self._pending, self._misfits = None, []
        if self.kind.itemData(index) is not None:
            source, target = self._values.widget(self._shown), self._values.widget(index)
            if isinstance(source, _ValueLine) and source.absolute and target.absolute:
                target.set_unit_index(source.unit_index())
            self._write(index, self._carried)
        self._show(index)

    def _show(self, index: int) -> None:
        self._shown = index
        self._values.setCurrentIndex(index)
        self._refresh()

    def _refresh(self) -> None:
        lines = [self.problem(), *(f'{self.name}: {misfit}.' for misfit in self._misfits)]
        text = '\n'.join(line for line in lines if line)
        self._warning.setText(text)
        self._warning.setVisible(bool(text))
        self.changed.emit()


class _SharedSourceRow(QWidget):
    """One error several inputs have in common: its name, its σ in percent, and the inputs it moves.

    A shared source is the precision figure of one physical thing — a stock, a balance,
    a pipette — so it is a standard deviation in percent and nothing else. Every input of
    the assay gets a checkbox; the source moves the ticked ones by the same offset, and
    the name is what every report calls it. What is wrong with the source is shown under
    it, in the sentence a run would refuse with, as an input's row shows its own.
    """

    changed = pyqtSignal()
    remove_requested = pyqtSignal()

    def __init__(self, labels: dict[str, str], parent=None):
        super().__init__(parent)
        self._name = QLineEdit()
        self._name.setToolTip('What every report calls this source, such as “Host and dye stock”.')
        self._name.textChanged.connect(self.changed)

        self._sigma = NoScrollDoubleSpinBox()
        self._sigma.setDecimals(1)
        self._sigma.setSingleStep(1.0)
        self._sigma.setRange(0.0, 1000.0)
        self._sigma.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._sigma.setFixedWidth(self._sigma.sizeHint().width())
        self._sigma.setToolTip('One standard deviation of the error the ticked inputs share, in percent.')
        self._sigma.valueChanged.connect(self.changed)

        self._remove_btn = QPushButton('Remove')
        self._remove_btn.setToolTip('Remove this shared error source.')
        self._remove_btn.clicked.connect(self.remove_requested)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(4)
        top.addWidget(self._name, 1)
        top.addWidget(QLabel('σ ='))
        top.addWidget(self._sigma)
        top.addWidget(QLabel('%'))
        top.addWidget(self._remove_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, _INPUT_GAP)
        layout.setSpacing(4)
        layout.addLayout(top)
        applies = QLabel('applies to:')
        applies.setStyleSheet(f'color: {INK_2};')
        layout.addWidget(applies)

        # One tick per input of the assay, labelled as the rows above label it, so a
        # source is stated against the same names the fit and the analysis report.
        self._ticks: dict[str, QCheckBox] = {}
        self._labels: dict[str, QLabel] = {}
        for key, html in labels.items():
            line = QHBoxLayout()
            line.setContentsMargins(_VALUE_INDENT, 0, 0, 0)
            line.setSpacing(4)
            tick = QCheckBox()
            # The macOS style lays a check box out by a rectangle narrower than the
            # one it paints, which puts the label beside it on the box.
            tick.setAttribute(Qt.WidgetAttribute.WA_LayoutUsesWidgetRect)
            tick.toggled.connect(self.changed)
            label = QLabel(html)
            label.setTextFormat(Qt.TextFormat.RichText)
            line.addWidget(tick)
            line.addWidget(label)
            line.addStretch(1)
            layout.addLayout(line)
            self._ticks[key] = tick
            self._labels[key] = label

        self._warning = _warning_label()
        layout.addWidget(self._warning)

    def focus_widgets(self) -> list[QWidget]:
        """The widgets that take the keyboard in this row, in reading order."""
        return [self._name, self._sigma, *self._ticks.values(), self._remove_btn]

    def set_problem(self, problem: str | None) -> None:
        """Show *problem* under the row, or nothing when the source can be used."""
        self._warning.setText(problem or '')
        self._warning.setVisible(bool(problem))

    def source(self) -> SharedSource:
        """The source this row states: its name without surrounding blanks, its σ, and the ticked inputs as listed."""
        return SharedSource(
            name=self._name.text().strip(),
            sigma_pct=self._sigma.value(),
            inputs=tuple(key for key, tick in self._ticks.items() if tick.isChecked()),
        )

    def set_source(self, source: SharedSource) -> None:
        """Show *source* again, ticking the inputs it moves."""
        self._name.setText(source.name)
        self._sigma.setValue(source.sigma_pct)
        for key, tick in self._ticks.items():
            tick.setChecked(key in source.inputs)


class InputUncertaintyPanel(InfoGroupBox):
    """The stated error model of the current assay: every input's own uncertainty, the shared sources and the additions.

    Signals
    -------
    specs_changed()
        Emitted whenever the model the panel reports may have changed: an edit, a
        kind chosen, a shared source added, changed or removed, the additions entry
        set, a set value taken from the conditions form, or a rebuild for another
        assay.
    """

    specs_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__('Input Uncertainty', 'Input Uncertainty', _UNCERTAINTY_HELP_HTML, parent)
        self._assay_type: AssayType = AssayType.GDA
        # input key -> its uncertainty row; rebuilt per assay type.
        self._rows: dict[str, _InputSpecRow] = {}
        # input key -> the plain display name shown for it, the titrant included.
        self._labels: dict[str, str] = {}
        # The shared sources as shown, in the order they are reported, and the HTML
        # label each of their tick lists offers per input.
        self._shared_rows: list[_SharedSourceRow] = []
        self._shared_labels: dict[str, str] = {}
        self._rows_assay: AssayType | None = None
        # Each assay's rows as the user left them, restored on switching back. Keyed by
        # assay as well: one key can name another species, or another set value, in
        # another assay (DBA's fixed_conc is the dye in one direction, the host in the other).
        self._remembered: dict[tuple[AssayType, str], _RowState] = {}
        # The same for the sources below the rows, which are stated against this assay's inputs.
        self._remembered_shared: dict[AssayType, tuple[SharedSource, ...]] = {}
        self._remembered_additions: dict[AssayType, tuple[int, float, int]] = {}
        # Condition key -> its set value in the base unit, from the conditions form.
        self._nominals: dict[str, float] = {}
        # The conditions the inputs are read off, as :func:`validate` takes them.
        self._base: dict[str, Quantity] = {}
        self._setup_ui()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_assay_type(self, assay_type: AssayType) -> None:
        """Rebuild the uncertainty rows for ``assay_type``, as last left for that assay.

        An assay the engine cannot project onto binding constants — such as Dye
        Alone — reports no association constant, so no interval and no analysis
        reads these uncertainties: the panel is disabled with a sentence saying why.
        """
        self._assay_type = assay_type
        self._rebuild_inputs(assay_type)
        available = projectable(assay_type) and bool(self._rows)
        self.setEnabled(available)
        self._unavailable.setVisible(not available)
        if not available:
            self._unavailable.setText(_unavailable_reason(assay_type))

    def set_nominal_values(self, conditions: dict[str, Quantity]) -> None:
        """Take the conditions' set values, which a percentage is read against when the kind changes."""
        self._nominals = {
            key: float(value.magnitude) for key, value in conditions.items() if isinstance(value, Quantity)
        }
        for key, row in self._rows.items():
            if key in self._nominals:
                row.set_nominal(self._nominals[key])

    def input_labels(self) -> dict[str, str]:
        """Each input's key and the plain display name the panel shows for it.

        The titrant is included. The fit and the analysis name an input in their
        messages with these, so a message names the input as the panel does.
        """
        return dict(self._labels)

    def current_errors(self) -> ErrorModel:
        """The whole error model as the panel states it.

        An input's own uncertainty is in ``specs``, left out when the input is fixed,
        which takes it as exact. A percentage spec is in percent of the set value and an
        absolute one in the input's base unit, both as entered: the conversion to a
        relative offset belongs to :func:`core.pipeline.inputs.constraints`, which reads
        the conditions of the assay being fitted. The shared sources come in the order
        they are shown, and the additions entry is ``None`` until a mode is chosen; once
        one is, it says whether the replicates are separate titrations.

        A source that states no error a titration can have — a σ of 0, a range that does
        not open, a shared source on one input — is reported by :meth:`problems` and
        stops the fit; it is not silently dropped here.
        """
        return ErrorModel(
            specs={key: spec for key, row in self._rows.items() if (spec := row.spec()) is not None},
            shared=tuple(row.source() for row in self._shared_rows),
            additions=self._additions(),
        )

    def problems(self) -> list[str]:
        """Why the model cannot be used as set, one sentence per problem naming its source.

        Empty when everything stated can be used. Every input row is checked — a fit
        lets each input that is not fixed move within its uncertainty — and the sources
        below them are put to :func:`core.pipeline.inputs.source_problems`, whose
        sentences are the ones a run refuses with: the panel says every one of them
        here, before the run, so nothing is left to find on the next attempt.
        """
        found = [problem for row in self._rows.values() if (problem := row.problem())]
        return found + source_problems(self.current_errors(), self._base, self._labels)

    def set_specs(self, specs: dict[str, InputSpec]) -> None:
        """State *specs* on the inputs they name, and nothing else.

        Every other input exact, no shared source, and no error on the additions:
        what the panel states afterwards is exactly ``ErrorModel(specs=specs)``.
        A key naming no input of the assay shown is an error of the caller.
        """
        unknown = set(specs) - set(self._rows)
        if unknown:
            raise KeyError(f'no uncertainty row for {sorted(unknown)}')
        blocked = self.blockSignals(True)
        for key, row in self._rows.items():
            row.set_spec(specs.get(key))
        self._clear_shared()
        self._set_additions_state(_NO_ADDITIONS)
        self.blockSignals(blocked)
        # Reported once, when the whole statement is in place: a half-set panel
        # describes no state a reader of the signal should act on.
        self.specs_changed.emit()

    def set_running(self, running: bool) -> None:
        """Lock the rows and the sources below them while a fit or an analysis is live."""
        for row in self._rows.values():
            row.setEnabled(not running)
        for shared in self._shared_rows:
            shared.setEnabled(not running)
        self._add_shared_btn.setEnabled(not running)
        self._additions_combo.setEnabled(not running)
        self._additions_sigma.setEnabled(not running)
        self._replicates_combo.setEnabled(not running and self._additions_combo.currentIndex() > 0)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Shown in place of usable rows for an assay that reports no association constant.
        self._unavailable = QLabel()
        self._unavailable.setWordWrap(True)
        self._unavailable.setStyleSheet(f'color: {INK_2};')
        self._unavailable.hide()
        layout.addWidget(self._unavailable)

        self._form = QFormLayout()
        self._form.setContentsMargins(8, 4, 8, 0)
        self._form.setVerticalSpacing(4)
        self._form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)
        layout.addLayout(self._form)

        # The titrant is the last input row, so its scatter from point to point is
        # stated directly under the factor that moves the whole series.
        additions = QVBoxLayout()
        additions.setContentsMargins(8, 4, 8, 0)
        additions.setSpacing(4)
        additions.addWidget(QLabel('Random error of each addition:'))
        self._additions_combo = QComboBox()
        for text, sequential in _ADDITION_MODES:
            self._additions_combo.addItem(text, sequential)
        self._additions_combo.setToolTip(
            'How the titrant was added: one cuvette filled addition after addition, or a sample '
            'prepared on its own for every point. The fit and the analysis need to know which to work '
            'out what the scatter of the additions does to Ka.'
        )
        self._additions_combo.currentIndexChanged.connect(self._on_additions_mode_changed)
        # The mode's wording is long, so it sits under its label rather than beside it:
        # the panel stays as wide as the input rows above make it.
        mode_line = QHBoxLayout()
        mode_line.setContentsMargins(_VALUE_INDENT, 0, 0, 0)
        mode_line.addWidget(self._additions_combo)
        additions.addLayout(mode_line)

        self._additions_sigma = NoScrollDoubleSpinBox()
        self._additions_sigma.setDecimals(1)
        self._additions_sigma.setSingleStep(1.0)
        self._additions_sigma.setRange(0.0, 1000.0)
        self._additions_sigma.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._additions_sigma.setFixedWidth(self._additions_sigma.sizeHint().width())
        self._additions_sigma.setToolTip('One standard deviation of a single addition, in percent of its volume.')
        self._additions_sigma.valueChanged.connect(self.specs_changed)
        self._additions_sigma_row = QWidget()
        sigma_line = QHBoxLayout(self._additions_sigma_row)
        sigma_line.setContentsMargins(_VALUE_INDENT, 0, 0, 0)
        sigma_line.setSpacing(4)
        sigma_line.addWidget(QLabel('σ ='))
        sigma_line.addWidget(self._additions_sigma)
        sigma_line.addWidget(QLabel('%'))
        sigma_line.addStretch(1)
        additions.addWidget(self._additions_sigma_row)

        self._replicates_combo = QComboBox()
        for text, separate in _REPLICATE_KINDS:
            self._replicates_combo.addItem(text, separate)
        self._replicates_combo.setToolTip(
            'Separate titrations each have their own addition errors, so their average carries σ/√m of them '
            'for m replicates; repeated reads of one titration share them, and their average carries σ.'
        )
        self._replicates_combo.currentIndexChanged.connect(self.specs_changed)
        replicates_line = QHBoxLayout()
        replicates_line.setContentsMargins(_VALUE_INDENT, 0, 0, 0)
        replicates_line.setSpacing(4)
        replicates_line.addWidget(QLabel('Replicates are:'))
        replicates_line.addWidget(self._replicates_combo)
        replicates_line.addStretch(1)
        additions.addLayout(replicates_line)
        self._additions_warning = _warning_label()
        self._additions_warning.setContentsMargins(_VALUE_INDENT, 0, 0, 0)
        additions.addWidget(self._additions_warning)
        layout.addLayout(additions)

        header = QHBoxLayout()
        header.setContentsMargins(8, _INPUT_GAP, 8, 0)
        title = QLabel('Shared error sources')
        title.setStyleSheet('font-weight: bold;')
        header.addWidget(title)
        header.addStretch(1)
        self._add_shared_btn = QPushButton('Add')
        self._add_shared_btn.setToolTip('State an error several inputs have in common.')
        self._add_shared_btn.clicked.connect(self._on_add_shared)
        header.addWidget(self._add_shared_btn)
        layout.addLayout(header)

        self._shared_layout = QVBoxLayout()
        self._shared_layout.setContentsMargins(8, 4, 8, 0)
        self._shared_layout.setSpacing(4)
        layout.addLayout(self._shared_layout)

        # Every change the panel reports is a change to what is wrong with it.
        self.specs_changed.connect(self._refresh_problems)
        self._rebuild_inputs(self._assay_type)

    def _refresh_problems(self) -> None:
        """Show under each shared source, and under the additions entry, what is wrong with it.

        Each sentence is the one a run would refuse with. The sources are put to
        :func:`core.pipeline.inputs.source_problems` one more at a time, and a row
        shows every sentence that source added — a name another source already has
        included.
        """
        stated: list[SharedSource] = []
        reported: list[str] = []
        for row in self._shared_rows:
            stated.append(row.source())
            found = source_problems(ErrorModel(shared=tuple(stated)), self._base, self._labels)
            row.set_problem('\n'.join(found[len(reported) :]) or None)
            reported = found
        additions = source_problems(ErrorModel(additions=self._additions()), self._base, self._labels)
        self._additions_warning.setText(additions[0] if additions else '')
        self._additions_warning.setVisible(bool(additions))

    def _apply_tab_order(self) -> None:
        """Chain the panel's controls in the order they are read.

        Qt builds its focus chain from the order widgets were created, and the
        additions entry and the Add button are built once for the session while the
        input rows and the shared sources come and go. Chaining after every rebuild
        is what keeps each control behind the one it is read after.
        """
        chain: list[QWidget] = []
        for row in self._rows.values():
            chain += row.focus_widgets()
        chain += [self._additions_combo, self._additions_sigma, self._replicates_combo, self._add_shared_btn]
        for shared in self._shared_rows:
            chain += shared.focus_widgets()
        for first, second in zip(chain, chain[1:]):
            QWidget.setTabOrder(first, second)

    def _rebuild_inputs(self, assay_type: AssayType) -> None:
        """Rebuild the rows and the sources below them for ``assay_type``, as last left for that assay.

        The set values of another assay's conditions are dropped: the new assay's
        arrive through :meth:`set_nominal_values`.
        """
        if self._rows_assay is not None:
            self._remembered.update({(self._rows_assay, key): row.state() for key, row in self._rows.items()})
            self._remembered_shared[self._rows_assay] = tuple(row.source() for row in self._shared_rows)
            self._remembered_additions[self._rows_assay] = self._additions_state()
        if assay_type is not self._rows_assay:
            self._nominals = {}
        self._rows_assay = assay_type
        self._rows.clear()
        while self._form.rowCount():
            self._form.removeRow(0)

        fields = ASSAY_CONDITIONS[assay_type]
        # Perturbable-input classification lives in the core layer; feed it the
        # condition Quantities so titrant/concentration/binding order is canonical.
        base = {f.key: Q_(f.default, f.unit) for f in fields if f.unit_type in ('concentration', 'binding_constant')}
        labels = input_labels(assay_type)
        inputs = perturbable_inputs(base)

        by_key = {f.key: f for f in fields}
        self._base = base
        self._labels = {key: plain_label(labels[key]) for key, _kind in inputs}
        for key, _kind in inputs:
            row = _InputSpecRow(self._labels[key], by_key.get(key))
            if (assay_type, key) in self._remembered:
                row.restore(self._remembered[(assay_type, key)])
            if key in self._nominals:
                row.set_nominal(self._nominals[key])
            lbl = QLabel(labels[key])
            lbl.setTextFormat(Qt.TextFormat.RichText)
            self._form.addRow(lbl, row.kind)
            self._form.addRow(row)
            self._rows[key] = row
            # Connected after the row is filled: the rebuild reports itself once, below.
            row.changed.connect(self.specs_changed)

        # A source is stated against this assay's inputs, so its row is rebuilt with them.
        self._clear_shared()
        self._shared_labels = {key: labels[key] for key, _kind in inputs}
        for source in self._remembered_shared.get(assay_type, ()):
            self._add_shared_row(source)
        self._set_additions_state(self._remembered_additions.get(assay_type, _NO_ADDITIONS))

        self._apply_tab_order()
        self.specs_changed.emit()

    # ------------------------------------------------------------------
    # Shared sources and the error of each addition
    # ------------------------------------------------------------------

    def _add_shared_row(self, source: SharedSource) -> _SharedSourceRow:
        """Show one more shared source, without reporting it: the caller says when the model changed."""
        row = _SharedSourceRow(self._shared_labels)
        row.set_source(source)
        self._shared_layout.addWidget(row)
        self._shared_rows.append(row)
        # Connected after the row is filled: what filling it emitted is not a change.
        row.changed.connect(self.specs_changed)
        row.remove_requested.connect(lambda: self._remove_shared(row))
        return row

    def _on_add_shared(self) -> None:
        self._add_shared_row(SharedSource(self._next_shared_name(), _DEFAULT_SOURCE_SIGMA, ()))
        self._apply_tab_order()
        self.specs_changed.emit()

    def _remove_shared(self, row: _SharedSourceRow) -> None:
        self._shared_rows.remove(row)
        row.setParent(None)
        row.deleteLater()
        self._apply_tab_order()
        self.specs_changed.emit()

    def _clear_shared(self) -> None:
        """Take every shared source off the panel, without reporting it."""
        for row in self._shared_rows:
            row.setParent(None)
            row.deleteLater()
        self._shared_rows.clear()

    def _next_shared_name(self) -> str:
        """A preset name no source on the panel has, so two never collide before they are named."""
        taken = {row.source().name for row in self._shared_rows}
        number = 1
        while f'Shared source {number}' in taken:
            number += 1
        return f'Shared source {number}'

    def _additions(self) -> AdditionError | None:
        """The random error of each addition as stated; ``None`` while no mode is chosen."""
        sequential = self._additions_combo.currentData()
        if sequential is None:
            return None
        return AdditionError(
            sigma_pct=self._additions_sigma.value(),
            sequential=sequential,
            separate_titrations=self._replicates_combo.currentData(),
        )

    def _additions_state(self) -> tuple[int, float, int]:
        """The additions entry as shown — the mode, the σ and the replicates, kept even while no mode is chosen."""
        return (
            self._additions_combo.currentIndex(),
            self._additions_sigma.value(),
            self._replicates_combo.currentIndex(),
        )

    def _set_additions_state(self, state: tuple[int, float, int]) -> None:
        """Show *state* again, without reporting it."""
        index, sigma, replicates = state
        for widget, set_value, value in (
            (self._additions_combo, self._additions_combo.setCurrentIndex, index),
            (self._additions_sigma, self._additions_sigma.setValue, sigma),
            (self._replicates_combo, self._replicates_combo.setCurrentIndex, replicates),
        ):
            blocked = widget.blockSignals(True)
            set_value(value)
            widget.blockSignals(blocked)
        self._show_additions_mode(index)

    def _show_additions_mode(self, index: int) -> None:
        """The σ and the replicates are statements about a mode: shown, and open to edits, once one is chosen."""
        self._additions_sigma_row.setVisible(index > 0)
        self._replicates_combo.setEnabled(index > 0 and self._additions_combo.isEnabledTo(self))

    def _on_additions_mode_changed(self, index: int) -> None:
        self._show_additions_mode(index)
        self.specs_changed.emit()
