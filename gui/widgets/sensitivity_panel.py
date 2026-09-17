"""SensitivityPanel — configure a Ka input-sensitivity run.

The panel exposes the knobs of :class:`~core.pipeline.sensitivity.SensitivityConfig`:
the analysis *mode* (Sobol indices / heatmap), the SOBOL sample size, the uncertainty
of every perturbable input (the titrant plus each concentration / binding-constant
condition) as a σ or a range, in percent or in the input's own unit, the two heatmap
axes, and an optional fixed seed. It emits :attr:`run_requested` /
:attr:`cancel_requested`; the owning session runs the worker and calls
:meth:`set_running` to flip the button. An assay without an exact Ka profile
(:func:`core.pipeline.profile.profile_supported`) cannot be refitted reliably
enough to be analysed, so the whole panel is disabled with a sentence saying why.
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
from core.pipeline.fit_pipeline import MAX_SEED
from core.pipeline.profile import profile_supported
from core.pipeline.sensitivity import (
    _SOBOL_BLOCKS,
    _SOBOL_SAMPLE_SIZES,
    TITRANT,
    InputSpec,
    ReplicateMode,
    SensitivityConfig,
    SensitivityMode,
    SpecKind,
    axis_reaches_zero,
    perturbable_inputs,
)
from core.units import Q_, Quantity
from gui.plotting.colors import INK_2
from gui.plotting.labels import plain_label
from gui.widgets.assay_conditions import ASSAY_CONDITIONS, ConditionField
from gui.widgets.assay_config_panel import _UNIT_TYPE_CHOICES
from gui.widgets.info_button import InfoButton, InfoGroupBox
from gui.widgets.numeric_inputs import NoScrollDoubleSpinBox, NoScrollSpinBox, SciLineEdit, format_number

_SECTION_HELP_HTML = """
<h3>K<sub>a</sub> Sensitivity Analysis</h3>
<p>A fitted association constant is only as good as the <i>inputs</i> you feed
the model — the titrant concentrations and the fixed conditions
(<i>[Host]<sub>0</sub></i>, <i>[Dye]<sub>0</sub></i>, <i>K<sub>a,dye</sub></i>, …).
Each carries pipetting / calibration error, and the fit silently absorbs it by
shifting the reported K<sub>a</sub>.</p>
<p>This tool re-runs the fit many times with those inputs varied by the
uncertainty you set under <i>Input uncertainty</i>, and shows the resulting spread
of K<sub>a</sub> — so you can see how much of your uncertainty comes from the inputs
rather than the fit itself.</p>
"""

_MODE_HELP_HTML = """
<h3>Mode</h3>
<ul>
  <li><b>Sensitivity indices</b> — vary every input together and measure how
      much of the spread in K<sub>a</sub> each one is responsible for. You get
      a K<sub>a</sub> distribution plus two Sobol indices per input:
      S<sub>1</sub> (first order), its effect on its own, and S<sub>T</sub>
      (total), which also counts that input acting in combination with the
      others.</li>
  <li><b>Heatmap</b> — sweep two chosen inputs on a regular grid and fit at
      every cell, giving a 2-D K<sub>a</sub> surface.</li>
</ul>
<p>Each input is drawn on its own, so the shares assume the inputs' errors are
unrelated. Inputs that share a stock, a pipette or a calibration move together, and
the shares do not separate them.</p>
<p>S<sub>T</sub> covers S<sub>1</sub>, so it cannot really be smaller. Drawn below
S<sub>1</sub>, the input acts almost entirely on its own: the two are equal to within
sampling noise, and either can come out on top in any run, at any sample size. Where
the gap is wider than the whiskers span, take that input's two indices as unreliable.</p>
"""

_SAMPLES_HELP_HTML = f"""
<h3>Sample size</h3>
<p>How thoroughly the input space is explored. A run fits
<i>sample size × (k + 2)</i> samples for <i>k</i> inputs that vary, so every step up
doubles the work.</p>
<p>The whisker on each index is its 95% confidence interval. It is built so that
in about 95 of every 100 analyses it contains the index you would get with
unlimited samples for the uncertainties you set. A repeat run with fresh samples
usually lands inside it, but not always.
It is worked out from {_SOBOL_BLOCKS} independent sample sets, which costs accuracy:
index by index, an index at {_SOBOL_SAMPLE_SIZES[0]} carries up to about five times the error
of one undivided set of the same size. {_SOBOL_SAMPLE_SIZES[1]} and {_SOBOL_SAMPLE_SIZES[2]}
narrow them.
It does not account for errors in the input settings or in the model.</p>
<p>Whiskers that clearly stand apart settle which of two inputs matters more.
Overlapping whiskers are a conservative sign: two 95% intervals can overlap while the
difference between the indices is still significant, so their order may hold —
a larger sample size decides it.</p>
"""

_REPLICATES_HELP_HTML = """
<h3>Replicates &mdash; how each perturbed fit uses them</h3>
<p><b>Follow fit setting</b> uses whatever the Fit panel is set to, so the analysis
matches the fit you are studying.</p>
<p><b>Per replicate</b> fits each replicate the baseline fit used separately and reports
the one that fits the replicates' average best, the way a per-replicate fit does;
a replicate the baseline fit leaves out enters no sample. It takes about as many
times longer as there are replicates.</p>
<p><b>Average replicates</b> fits a single averaged signal, once per sample.</p>
"""

_UNCERTAINTY_HELP_HTML = """
<h3>Input uncertainty</h3>
<p>How far each input may be off. Choose a kind for each input:</p>
<ul>
  <li><b>± σ %</b> and <b>± σ</b> — σ is one standard deviation of a normal
      distribution, in percent of the input's set value or in the input's own unit.
      Each fit draws the input from it, cut off so the input stays above zero. With
      σ = 5 %, about 95 of every 100 draws land within ±10 %, and a few further out.</li>
  <li><b>range %</b> and <b>range</b> — each fit draws the input evenly between
      <i>from</i> and <i>to</i>: offsets in percent of the set value, or the lowest
      and highest value in the input's own unit. A range may be lopsided, such as
      −6 % to +4 %.</li>
  <li><b>fixed</b> — the input keeps its set value and is left out of the analysis.</li>
</ul>
<p>Switching the kind carries the numbers over: σ = 5 % becomes the range −5 % to
+5 %, or a σ of 5 % of the set value in the input's unit, and a range becomes a σ of
half its width, centred on the set value. The spread of the draws changes with the
kind: an even draw between −5 % and +5 % varies less than a σ of 5 %. A number the new
boxes cannot hold, such as a range starting below −100 %, is replaced by the nearest one
they can, and the input says so.</p>
<p>A σ of 0, or a range whose <i>to</i> is not above its <i>from</i>, does not vary
the input. Nor can a value in the input's unit be used while the input is 0 in the
conditions. The input then shows a warning, and the analysis does not start until you
change the value or choose <b>fixed</b>. A heatmap checks only its two axes, since it
holds every other input at its set value.</p>
<p>Use realistic numbers: pipetting error is often a few percent, a stated
literature K<sub>a,dye</sub> may be uncertain by 10–20%.</p>
<p>Every input is drawn on its own, so the analysis takes their errors to be unrelated.
Inputs made from one stock, pipetted with one pipette or read against one calibration
move together; for those, the spread and the shares describe a different experiment
from yours.</p>
<p>The titrant moves as one factor over the whole series — a stock or dilution error
that shifts every concentration by the same fraction. Scatter from point-to-point
pipetting is not part of the analysis.</p>
"""

_HEATMAP_HELP_HTML = """
<h3>Heatmap axes</h3>
<p>Choose two different inputs to sweep; every other input keeps its set value. An axis
set as a range runs from its <i>from</i> to its <i>to</i>. An axis set as a σ runs
from −2σ to +2σ, so its σ must stay below half the set value (50 %) for the axis to
stay above zero. A heatmap axis cannot be <i>fixed</i>.</p>
<p>Each axis is split into <i>Grid steps</i> points and the fit runs once per cell —
cost grows as <i>steps²</i>, so 11×11 = 121 fits is a good starting resolution.</p>
"""

_SEED_HELP_HTML = """
<h3>Fixed seed</h3>
<p>Tick to make the random draws reproducible: the same seed always produces the
same histogram. Leave unticked for a fresh random sample each run.</p>
"""

#: Significant figures an absolute value is shown and kept with.
_SIGFIGS = 5
#: The widest absolute value an entry box must show in full at ``_SIGFIGS``.
_WIDEST_ABSOLUTE = '8.8888e-10'
#: The σ every input starts with.
_DEFAULT_SPEC = InputSpec.sigma_pct(5.0)
#: Indent of an input's value line under its label, and the gap below it before the next input.
_VALUE_INDENT = 12
_INPUT_GAP = 8


def _unavailable_reason(assay_type: AssayType) -> str:
    """Why the analysis cannot be run for *assay_type*, in one plain sentence."""
    if assay_type is AssayType.DYE_ALONE:
        return 'Dye Alone has no association constant, so there is nothing to analyse here.'
    return (
        'This analysis is not available for an assay with more than one association constant: '
        'its fits cannot yet be repeated reliably enough to measure how the inputs move Ka.'
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
    so the values get the panel's full width. A percentage is read against the input's
    nominal value; an absolute entry uses the input's own unit. The titrant is a series
    with no single nominal value, so it offers the percentage kinds only. Choosing
    another kind carries the entered numbers over (see :func:`_restate`), and a number
    the new kind's boxes cannot hold is named under the values until the next edit. A
    conversion that needs a nominal value above 0 waits for one, with a warning. The
    value line has one page per kind, so the row is as wide whichever kind is chosen.
    """

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
            'its two ends and may be lopsided. Fixed keeps the set value.'
        )
        self._values = QStackedWidget()
        for text, data in choices:
            self.kind.addItem(text, data)
            if data is None:
                page = QLabel('kept at its set value')
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
        self._shown = 0
        self._write(0, _DEFAULT_SPEC)
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

        A σ is drawn from a distribution truncated above zero, so only a range can
        take the input down to zero, where the model has nothing to fit.
        """
        problem = self._entry_problem()
        if problem is not None:
            return problem
        spec = self.spec()
        if spec is not None and spec.kind is SpecKind.INTERVAL and axis_reaches_zero(spec, self._nominal, self.name):
            end = '−100 %' if spec.relative else '0'
            return f'{self.name} would be drawn down to zero: set “from” above {end}.'
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

    def axis_problem(self) -> str | None:
        """Why this input cannot be a heatmap axis as set, as a sentence naming it; ``None`` when it can.

        An axis runs over the whole range, or from −2σ to +2σ, both ends included, so
        an end at −100 % would fit the model with the input at zero.
        """
        spec = self.spec()
        if spec is None:
            return f'{self.name} is a heatmap axis, so it cannot be fixed: choose a σ or a range.'
        problem = self._entry_problem()
        if problem is not None:
            return problem
        if not axis_reaches_zero(spec, self._nominal, self.name):
            return None
        if spec.kind is SpecKind.SIGMA:
            limit = '50 %' if spec.relative else 'half its set value'
            return (
                f'{self.name} as a heatmap axis would reach zero or below, since the axis runs from −2σ to +2σ: '
                f'set σ below {limit}, or use a range.'
            )
        return f'{self.name} as a heatmap axis would reach zero: set “from” above {"−100 %" if spec.relative else "0"}.'

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


class SensitivityPanel(InfoGroupBox):
    """Configuration panel for a :class:`SensitivityConfig` run.

    Signals
    -------
    run_requested()
        Emitted when the user clicks *Run* (panel idle).
    cancel_requested()
        Emitted when the user clicks the button while a run is in progress.
    """

    run_requested = pyqtSignal()
    cancel_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__('Ka Sensitivity', 'Ka Sensitivity Analysis', _SECTION_HELP_HTML, parent)
        self._assay_type: AssayType = AssayType.GDA
        self._running = False
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
        """Rebuild the uncertainty rows and heatmap axis combos for ``assay_type``.

        An assay the analysis cannot refit — one without an exact Ka profile, such
        as Dye Alone or a stepwise two-constant assay — disables the whole panel and
        shows a sentence saying why.
        """
        self._assay_type = assay_type
        self._rebuild_inputs(assay_type)
        available = profile_supported(assay_type) and bool(self._rows)
        self.setEnabled(available)
        self._unavailable.setVisible(not available)
        if not available:
            self._unavailable.setText(_unavailable_reason(assay_type))

    def input_labels(self) -> dict[str, str]:
        """Each input's key and the plain display name the panel shows for it.

        The titrant is included. The analysis uses these names in the messages it
        reports, so a problem names the input as the panel does.
        """
        return dict(self._labels)

    def set_nominal_values(self, conditions: dict[str, Quantity]) -> None:
        """Take the conditions' set values, which a percentage is read against when the kind changes."""
        self._nominals = {
            key: float(value.magnitude) for key, value in conditions.items() if isinstance(value, Quantity)
        }
        for key, row in self._rows.items():
            if key in self._nominals:
                row.set_nominal(self._nominals[key])

    def run_problems(self) -> list[str]:
        """Why the analysis cannot run as set, one sentence per problem naming the input; empty when it can.

        Sensitivity indices vary every input that is not fixed, so every row is checked.
        A heatmap sweeps its two axes and holds every other input at its set value, so
        only the axes are checked.
        """
        if self._mode_combo.currentData() is not SensitivityMode.HEATMAP:
            return [problem for row in self._rows.values() if (problem := row.problem())]
        axes = [
            self._rows[key] for key in (self._x_combo.currentData(), self._y_combo.currentData()) if key in self._rows
        ]
        if len(axes) == 2 and axes[0] is axes[1]:
            return [f'{axes[0].name} is both heatmap axes: choose another input for one of them.']
        return [problem for row in axes if (problem := row.axis_problem())]

    def current_config(self) -> SensitivityConfig:
        """Build a :class:`SensitivityConfig` from the current widget state.

        A fixed input is left out, which holds it at its set value; a heatmap takes only
        its two axes, holding every other input there.

        Raises
        ------
        ValueError
            When :meth:`run_problems` finds a reason the analysis cannot run.
        """
        problems = self.run_problems()
        if problems:
            raise ValueError(' '.join(problems))
        mode: SensitivityMode = self._mode_combo.currentData()
        x_key, y_key = self._x_combo.currentData(), self._y_combo.currentData()
        rows = {key: self._rows[key] for key in (x_key, y_key)} if mode is SensitivityMode.HEATMAP else self._rows
        specs = {key: row.spec() for key, row in rows.items()}
        seed = int(self._seed_spin.value()) if self._seed_check.isChecked() else None
        return SensitivityConfig(
            mode=mode,
            n_samples=self._samples_combo.currentData(),
            input_specs={key: spec for key, spec in specs.items() if spec is not None},
            seed=seed,
            x_key=x_key,
            y_key=y_key,
            n_steps=self._steps_spin.value(),
            replicate_mode=self._replicates_combo.currentData(),
        )

    def set_running(self, running: bool) -> None:
        """Flip the Run/Cancel button and lock the inputs while a run is live."""
        self._running = running
        self._run_btn.setText('Cancel' if running else 'Run Sensitivity Analysis')
        for w in self._input_widgets():
            w.setEnabled(not running)
        if not running:
            # Seed value follows its checkbox once inputs are re-enabled.
            self._seed_spin.setEnabled(self._seed_check.isChecked())

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Shown in place of a usable panel for an assay the analysis cannot refit.
        self._unavailable = QLabel()
        self._unavailable.setWordWrap(True)
        self._unavailable.setStyleSheet(f'color: {INK_2};')
        self._unavailable.hide()
        layout.addWidget(self._unavailable)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)

        self._mode_combo = QComboBox()
        self._mode_combo.addItem('Sensitivity indices', SensitivityMode.SOBOL)
        self._mode_combo.addItem('Heatmap', SensitivityMode.HEATMAP)
        self._mode_combo.currentIndexChanged.connect(self._update_mode_visibility)
        form.addRow('Mode:', self._with_info(self._mode_combo, 'Mode', _MODE_HELP_HTML))

        self._samples_combo = QComboBox()
        for size in _SOBOL_SAMPLE_SIZES:
            self._samples_combo.addItem(str(size), size)
        self._samples_combo.setCurrentIndex(0)
        self._samples_combo.setToolTip('How thoroughly the input space is explored. Each step up doubles the work.')
        self._samples_row = self._with_info(
            self._samples_combo, 'Sample size', _SAMPLES_HELP_HTML, label='Sample size:'
        )
        form.addRow(self._samples_row)

        self._replicates_combo = QComboBox()
        self._replicates_combo.addItem('Follow fit setting', ReplicateMode.FOLLOW)
        self._replicates_combo.addItem('Per replicate', ReplicateMode.PER_REPLICA)
        self._replicates_combo.addItem('Average replicates', ReplicateMode.AVERAGE)
        self._replicates_combo.setToolTip(
            'How each perturbed fit uses the replicates. Averaging them removes the '
            'measured signal scatter from the analysis.'
        )
        form.addRow('Replicates:', self._with_info(self._replicates_combo, 'Replicates', _REPLICATES_HELP_HTML))
        layout.addLayout(form)

        # Uncertainty rows — rebuilt per assay type.
        self._delta_group = InfoGroupBox('Input uncertainty', 'Input uncertainty', _UNCERTAINTY_HELP_HTML)
        self._delta_form = QFormLayout(self._delta_group)
        self._delta_form.setContentsMargins(8, 4, 8, 0)
        self._delta_form.setVerticalSpacing(4)
        self._delta_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)
        layout.addWidget(self._delta_group)

        # Heatmap axis selectors — only visible in Heatmap mode.
        self._heatmap_group = InfoGroupBox('Heatmap axes', 'Heatmap axes', _HEATMAP_HELP_HTML)
        hm_form = QFormLayout(self._heatmap_group)
        hm_form.setContentsMargins(8, 4, 8, 8)
        self._x_combo = QComboBox()
        self._y_combo = QComboBox()
        self._steps_spin = NoScrollSpinBox()
        self._steps_spin.setRange(3, 101)
        self._steps_spin.setValue(11)
        self._steps_spin.setToolTip('Grid points per axis (fits ≈ steps²).')
        hm_form.addRow('X axis:', self._x_combo)
        hm_form.addRow('Y axis:', self._y_combo)
        hm_form.addRow('Grid steps:', self._steps_spin)
        layout.addWidget(self._heatmap_group)

        # Fixed-seed row.
        self._seed_check = QCheckBox('Fixed seed')
        self._seed_check.setToolTip('Reproducible draws — the same seed gives the same result.')
        self._seed_spin = NoScrollSpinBox()
        self._seed_spin.setRange(0, MAX_SEED)
        self._seed_spin.setValue(0)
        self._seed_spin.setEnabled(False)
        self._seed_check.toggled.connect(self._seed_spin.setEnabled)
        seed_row = QWidget()
        seed_lay = QHBoxLayout(seed_row)
        seed_lay.setContentsMargins(0, 0, 0, 0)
        seed_lay.setSpacing(8)
        seed_lay.addWidget(self._seed_check)
        self._seed_spin.setFixedWidth(140)
        seed_lay.addWidget(self._seed_spin)
        seed_lay.addWidget(InfoButton('Fixed seed', _SEED_HELP_HTML))
        seed_lay.addStretch(1)
        layout.addWidget(seed_row)

        self._run_btn = QPushButton('Run Sensitivity Analysis')
        self._run_btn.clicked.connect(self._on_run_clicked)
        layout.addWidget(self._run_btn)

        self._rebuild_inputs(self._assay_type)
        self._update_mode_visibility()

    def _rebuild_inputs(self, assay_type: AssayType) -> None:
        """Rebuild the uncertainty rows and heatmap axis combos for ``assay_type``, as last left for that assay.

        The set values of another assay's conditions are dropped: the new assay's
        arrive through :meth:`set_nominal_values`.
        """
        if self._rows_assay is not None:
            self._remembered.update({(self._rows_assay, key): row.state() for key, row in self._rows.items()})
        if assay_type is not self._rows_assay:
            self._nominals = {}
        self._rows_assay = assay_type
        self._rows.clear()
        while self._delta_form.rowCount():
            self._delta_form.removeRow(0)

        fields = ASSAY_CONDITIONS[assay_type]
        # Perturbable-input classification lives in the core layer; feed it the
        # condition Quantities so titrant/concentration/binding order is canonical.
        base = {f.key: Q_(f.default, f.unit) for f in fields if f.unit_type in ('concentration', 'binding_constant')}
        labels = {f.key: f.label for f in fields}
        # The titrant is moved as one factor over the whole series, which its label says.
        labels[TITRANT] = f'{ASSAY_REGISTRY[assay_type].x_label} (titrant, whole series)'
        inputs = perturbable_inputs(assay_type, base)

        by_key = {f.key: f for f in fields}
        self._labels = {key: plain_label(labels[key]) for key, _kind in inputs}
        self._x_combo.clear()
        self._y_combo.clear()
        for key, _kind in inputs:
            row = _InputSpecRow(self._labels[key], by_key.get(key))
            if (assay_type, key) in self._remembered:
                row.restore(self._remembered[(assay_type, key)])
            if key in self._nominals:
                row.set_nominal(self._nominals[key])
            lbl = QLabel(labels[key])
            lbl.setTextFormat(Qt.TextFormat.RichText)
            self._delta_form.addRow(lbl, row.kind)
            self._delta_form.addRow(row)
            self._rows[key] = row

            self._x_combo.addItem(self._labels[key], key)
            self._y_combo.addItem(self._labels[key], key)

        # Default heatmap axes: first two distinct perturbable inputs.
        if self._y_combo.count() > 1:
            self._y_combo.setCurrentIndex(1)

    # ------------------------------------------------------------------
    # Slots / helpers
    # ------------------------------------------------------------------

    def _update_mode_visibility(self) -> None:
        is_heatmap = self._mode_combo.currentData() is SensitivityMode.HEATMAP
        self._samples_row.setVisible(not is_heatmap)
        self._heatmap_group.setVisible(is_heatmap)

    def _on_run_clicked(self) -> None:
        if self._running:
            self.cancel_requested.emit()
        else:
            self.run_requested.emit()

    def _input_widgets(self) -> list[QWidget]:
        """Every control that must lock while a run is in progress."""
        return [
            self._mode_combo,
            self._samples_combo,
            self._replicates_combo,
            self._seed_check,
            self._seed_spin,
            self._x_combo,
            self._y_combo,
            self._steps_spin,
            *self._rows.values(),
        ]

    @staticmethod
    def _with_info(widget: QWidget, title: str, html: str, *, label: str | None = None) -> QWidget:
        """Wrap ``widget`` (optionally with a leading label) plus a trailing info button."""
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        if label is not None:
            lay.addWidget(QLabel(label))
        lay.addWidget(widget)
        lay.addWidget(InfoButton(title, html))
        lay.addStretch(1)
        return row
