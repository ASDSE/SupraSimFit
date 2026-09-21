"""InputUncertaintyPanel — what the user knows about the inputs a fit rests on.

One row per perturbable input (the titrant series plus every concentration /
binding-constant condition): its uncertainty as a σ or a range, in percent of the
entered value or in the input's own unit, or *fixed*. Every row opens fixed, so a
fit takes the entered inputs as exact until an uncertainty is stated.

The specs the panel collects feed two things: the confidence interval of every fit
(:func:`core.pipeline.input_aware.input_aware` lets the fit move each input inside
its uncertainty) and the Ka sensitivity analysis
(:class:`~core.pipeline.sensitivity.SensitivityConfig`), which draws the inputs from
the same specs. The panel itself runs neither — it emits :attr:`specs_changed` and
the owning session reads :meth:`current_specs` and :meth:`problems`.

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
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QStackedWidget,
    QStyle,
    QStyleOptionFrame,
    QVBoxLayout,
    QWidget,
)

from core.assays.registry import ASSAY_REGISTRY, AssayType
from core.pipeline.inputs import InputSpec, SpecKind, axis_reaches_zero, perturbable_inputs
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
      these inputs and splits the resulting spread of K<sub>a</sub> between them. It
      needs at least one input that is not fixed.</li>
</ul>
<p>Choose a kind for each input:</p>
<ul>
  <li><b>± σ %</b> and <b>± σ</b> — σ is one standard deviation of a normal
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
<p>Each input is stated on its own, so both the interval and the analysis take their
errors to be unrelated. Inputs made from one stock, pipetted with one pipette or read
against one calibration move together; for those, the spread and the shares describe a
different experiment from yours.</p>
<p>The titrant moves as one factor over the whole series — a stock or dilution error
that shifts every concentration by the same fraction. Scatter from point-to-point
pipetting is not part of it.</p>
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
            ('± σ %', (SpecKind.SIGMA, True)),
            ('range %', (SpecKind.INTERVAL, True)),
        ]
        if field is not None:
            choices += [('± σ', (SpecKind.SIGMA, False)), ('range', (SpecKind.INTERVAL, False))]
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

        self._warning = QLabel()
        self._warning.setWordWrap(True)
        self._warning.setStyleSheet('color: #b42318;')
        self._warning.hide()

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


class InputUncertaintyPanel(InfoGroupBox):
    """The stated uncertainty of every input of the current assay.

    Signals
    -------
    specs_changed()
        Emitted whenever the specs the panel reports may have changed: an edit, a
        kind chosen, a set value taken from the conditions form, or a rebuild for
        another assay.
    """

    specs_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__('Input Uncertainty', 'Input Uncertainty', _UNCERTAINTY_HELP_HTML, parent)
        self._assay_type: AssayType = AssayType.GDA
        # input key -> its uncertainty row; rebuilt per assay type.
        self._rows: dict[str, _InputSpecRow] = {}
        # input key -> the plain display name shown for it, the titrant included.
        self._labels: dict[str, str] = {}
        self._rows_assay: AssayType | None = None
        # Each assay's rows as the user left them, restored on switching back. Keyed by
        # assay as well: one key can name another species, or another set value, in
        # another assay (DBA's fixed_conc is the dye in one direction, the host in the other).
        self._remembered: dict[tuple[AssayType, str], _RowState] = {}
        # Condition key -> its set value in the base unit, from the conditions form.
        self._nominals: dict[str, float] = {}
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

    def current_specs(self) -> dict[str, InputSpec]:
        """The uncertainty of every input that is not fixed, as the rows state it.

        A percentage spec is in percent of the set value and an absolute one in the
        input's base unit, both as entered: the conversion to a relative offset belongs
        to :func:`core.pipeline.inputs.constraints`, which reads the conditions of the
        assay being fitted. A fixed input is left out, which takes it as exact.

        A row that cannot vary as set — a σ of 0, a range that does not open — is
        reported by :meth:`problems` and stops the fit; it is not silently dropped here.
        """
        return {key: spec for key, row in self._rows.items() if (spec := row.spec()) is not None}

    def problems(self) -> list[str]:
        """Why the uncertainties cannot be used as set, one sentence per problem naming the input.

        Empty when every row can be used. Every row is checked: a fit lets each input
        that is not fixed move within its uncertainty.
        """
        return [problem for row in self._rows.values() if (problem := row.problem())]

    def reset_to_defaults(self) -> None:
        """Take every input as exact again, as the panel opens with them.

        The uncertainties are settings of the fit, like the parameter bounds,
        so whatever resets a session to its defaults resets these too.
        """
        for row in self._rows.values():
            blocked = row.blockSignals(True)
            row.set_spec(None)
            row.blockSignals(blocked)
        # Reported once, when every row is fixed: a half-reset panel describes
        # no state a reader of the signal should act on.
        self.specs_changed.emit()

    def set_running(self, running: bool) -> None:
        """Lock the rows while a fit or an analysis is live."""
        for row in self._rows.values():
            row.setEnabled(not running)

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

        self._rebuild_inputs(self._assay_type)

    def _rebuild_inputs(self, assay_type: AssayType) -> None:
        """Rebuild the uncertainty rows for ``assay_type``, as last left for that assay.

        The set values of another assay's conditions are dropped: the new assay's
        arrive through :meth:`set_nominal_values`.
        """
        if self._rows_assay is not None:
            self._remembered.update({(self._rows_assay, key): row.state() for key, row in self._rows.items()})
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

        self.specs_changed.emit()
