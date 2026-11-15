"""The binding model of a session and the rules of stating it, without widgets.

The model is chosen in two steps — a category, then a model of that category — from
``ASSAY_REGISTRY``. Under it come the conditions the model needs (each concentration in
nM, µM, mM or M, chosen per condition; each binding constant in M⁻¹), whether the
additions of titrant dilute the sample (the totals stay constant until the user says
they do, and then the titrant stock and the concentrations it holds are stated), the
bounds of the fitted parameters, and whether the replicates are fitted only as their
average or each on its own as well.

Every number is kept as the text shown for it, so the number used is the number on
screen; a text that is not a number is a problem naming the input
(:meth:`BindingForm.problems`, :meth:`BindingForm.bound_problems`). A condition written
by the form — a default, a unit switch, a value set from code — keeps the very number it
was written from; a bound written by the form is shown with every figure it has, and a
bound from a dye-alone calibration is rounded to the figures shown before it is used.
Choosing a model gives a fresh form — that model's default conditions in their default
units, constant totals and the registry's bounds — and the titrant stock keeps its value
and unit, seen again before it can reach a fit, since the totals go back to constant.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from core.assays.registry import ASSAY_REGISTRY, AssayType, ParamKind
from core.pipeline.fit_pipeline import FitConfig
from core.pipeline.inputs import TITRANT_STOCK
from core.pipeline.varpro import projectable
from core.units import Q_, Quantity
from gui.assay_descriptions import ASSAY_DESCRIPTIONS
from gui.parameter_descriptions import PARAMETER_DESCRIPTIONS, SCI_NOTE_HTML
from gui.plotting.labels import and_join, fmt_param_plain
from gui.uncertainty import amount_text, parse_amount, shifted_text
from gui.widgets.assay_conditions import (
    ASSAY_NAMES,
    DBA_MODES,
    TITRANT_STOCK_FIELD,
    UNIT_CHOICES,
    ConditionField,
    condition_fields,
    condition_name,
)

#: The models of each category, in registry order: what the two menus offer.
CATEGORIES: dict[str, list[AssayType]] = {}
for _assay_type, _meta in ASSAY_REGISTRY.items():
    CATEGORIES.setdefault(_meta.category, []).append(_assay_type)

_CONDITIONS_HELP_HTML = """
<p class="topic">Conditions</p>
<p>The conditions are what the model needs besides the data: the fixed totals in the
cuvette and any binding constant measured beforehand. Each concentration is entered in
nM, µM, mM or M, chosen beside it; a binding constant in M<sup>−1</sup>. Switching the
unit rewrites the number, so the concentration stays the same.</p>
<p>How well each condition is known is stated under <b>Input uncertainty</b>: with every
input fixed, as that view opens, the interval takes the conditions you entered as exact;
state an uncertainty for one and the fit may move it within what you stated, and the
interval covers that as well.</p>
"""

_STOCK_HELP_HTML = """
<p class="topic">Titrant stock</p>
<p>Here you state whether each addition of titrant dilutes the sample. The fixed
concentrations <b>stay constant</b> when the samples were made up to the same volume, or
when the titrant stock was prepared in the sample solution itself; otherwise they are
<b>diluted</b> by each addition. The concentrations in your data file are the titrant
concentrations <b>in the cuvette after each addition</b>. If yours were computed without
dilution — stock concentration times volume added, over the starting volume, call it
<i>x</i><sub>nominal</sub> — convert them with
<i>x</i> = <i>x</i><sub>nominal</sub>·<i>c</i><sub>T</sub> /
(<i>c</i><sub>T</sub> + <i>x</i><sub>nominal</sub>), where <i>c</i><sub>T</sub> is the
titrant stock concentration.</p>
<p><b>Diluted</b> asks for that stock concentration. A sample of volume
<i>V</i><sub>0</sub> that has taken up a volume <i>W</i> of the stock holds
<i>x</i> = <i>c</i><sub>T</sub>·<i>W</i>/(<i>V</i><sub>0</sub>+<i>W</i>) of titrant, so a
fraction <i>x</i>/<i>c</i><sub>T</sub> of the final volume came from the stock and every
fixed concentration falls by it — no volumes needed. Tick a species the stock itself holds
at the sample's own concentration: the additions leave that one where it is.</p>
"""

_BOUNDS_HELP_HTML = """
<p class="topic">Bounds of the fitted parameters</p>
<p>Lower and upper limits for each fitted parameter. They open on the defaults of the
model; edit them to constrain the fit where you know more, and <b>Reset to defaults</b>
brings the defaults back.</p>
"""

_UNLIMITED_HELP_HTML = """
<p>A signal parameter with no upper limit shows an empty upper field: leave it empty to
keep none. Signals that were blank-subtracted can need an offset below zero: enter a
negative lower bound for it.</p>
"""

_BOUNDS_KA_HELP_HTML = """
<p>The two kinds of parameter use their bounds differently. An association constant is
searched across its bounds, so they set the range the fit and the confidence interval are
looked for in. A signal parameter is not searched at all: its value is solved exactly at
each association constant, subject to these bounds, so a bound the best value lies outside
of holds it at that bound &mdash; and equal lower and upper bounds pin the parameter at
that value and take it out of the fit.</p>
<p>The confidence interval in <b>Ka confidence</b> is read inside these bounds, and an end
that reaches one is reported as open rather than as a measured limit. The interval holds
if the model is right, the conditions you entered are right to within the uncertainty you
stated for them under <b>Input uncertainty</b>, and the scatter is independent from point
to point and as large at each point as the noise law of the fit says; it says nothing
about an error in any of those.</p>
"""

_BOUNDS_LINE_HELP_HTML = """
<p>Neither parameter of the straight line is searched: both are solved exactly, subject
to these bounds, so a bound the best value lies outside of holds it at that bound &mdash;
and equal lower and upper bounds pin the parameter at that value and take it out of the
fit.</p>
"""

_DYE_ALONE_DEGENERACY_HTML = """
<p>Where the dye concentration is held fixed &mdash; IDA and DBA host-to-dye &mdash; the
three signal coefficients (I<sub>0</sub>, I<sub>D</sub> of the free dye, I<sub>HD</sub> of
the host&ndash;dye complex) are degenerate: many combinations give the same curve, so the
fit reports them starred, and only their combination is determined. Where the dye is
titrated, the data can determine each one. Confining two of them to what a dye-alone
experiment measured breaks that degeneracy, which makes all three coefficients meaningful
on their own and can narrow the confidence interval of the association constant.</p>
"""

#: What a dye-alone calibration sets each signal coefficient it bounds to.
_DYE_ALONE_BOUNDS = {
    'I0': 'I<sub>0</sub> &isin; [0.8 &middot; intercept, 1.2 &middot; intercept]',
    'I_dye_free': 'I<sub>D</sub> &isin; [0.8 &middot; slope, 1.2 &middot; slope]',
}


def _dye_alone_help(keys: tuple[str, ...]) -> str:
    """The help of *Bounds from dye alone…* for a model whose signal coefficients *keys* it bounds."""
    lines = '<br>\n  '.join(f'<i>{_DYE_ALONE_BOUNDS[key]}</i>' for key in keys)
    return (
        '<p><b>Bounds from dye alone</b></p>\n'
        + _DYE_ALONE_DEGENERACY_HTML
        + '<p><b>Bounds from dye alone…</b> fits a straight line\n'
        '<i>S = slope &middot; [D] + intercept</i> to a dye-only calibration recorded on the same\n'
        'instrument and the same day as your titration, and sets</p>\n'
        f'<p align="center">\n  {lines}\n</p>\n'
        '<p>The bounds then read as any bounds you typed: edit them, or reset them to the\n'
        'defaults.</p>\n'
    )


#: The help of the replicate choice; it states the level and the replicate count the test needs.
REPLICATES_HELP_HTML = """
<p class="topic">Replicates</p>

<p><b>What is fitted either way</b></p>
<p>The reported fit is always the fit of the <i>average</i> of the replicates
that are used. For replicates that scatter by the same amount, fitting them all
at once and fitting their average give the same answer, and the average of
replicates that share their binding constants is itself a model curve. The
reported R<sup>2</sup> and RMSE are measured against that average.</p>

<p><b>The average</b></p>
<p>Every replicate you have switched on goes into the average, whatever it
looks like.</p>

<p><b>Each replicate separately</b> (how a session opens)</p>
<p>Each replicate is also fitted on its own, and those fits are reported beside
the main one: the <i>Replicates</i> table lists each replicate&rsquo;s own
K<sub>a</sub> and R<sup>2</sup>, and a line under the headline of Fit results
gives the median and range of their own K<sub>a</sub>, each fitted with the
inputs as entered. That is real replicate-to-replicate spread, measured on your
experiment.</p>

<p>Their own fits are also used to test the two assumptions the average rests
on: that every replicate is describing the same binding constant, and that
each one is about as precise as the others. A replicate whose own curve needs a
different K<sub>a</sub> than the others agree on, or whose points scatter about
its own curve far more than the others&rsquo; do, is left out of the average
and named, with the reason, in the Replicates table and in the report.</p>

<p><b>What the replicates also give the report</b></p>
<p>With two or more replicates in the fit, their scatter about their mean
measures the noise without using the model at all, and <i>Diagnostics</i> in
Fit details uses it to say whether the fitted curve misses the data
by more than that scatter allows. With a single replicate that question is
answered instead from runs of points on one side of the curve.</p>

<p><b>The test</b></p>
<p>It starts from the majority of the replicates whose own K<sub>a</sub> lie
closest to the middle of all of them, and adds back the others one at a time,
the one that agrees best with their shared fit first, until none of the rest
agrees. A replicate already in that the others then disagree with leaves again,
and the ones outside at the end are left out. Starting from that majority means that two
replicates which share a wrong K<sub>a</sub> cannot pull the shared fit their
way and push a good replicate out instead. The replicates kept are then
compared for scatter (Cochran&rsquo;s test), and one whose scatter is far larger
than the others&rsquo; is left out as well. Where you stated a random error of each
addition under <b>Input uncertainty</b> and the replicates are separate titrations,
both steps allow for each replicate&rsquo;s own additions, which move its K<sub>a</sub>
and its points apart from the others&rsquo;.</p>
<p>Both steps work at a 1&thinsp;% level (the outlier level of
ISO&nbsp;5725-2): the K<sub>a</sub> step shares it out over the replicates you
gave, Cochran&rsquo;s test over the replicates still in it. Together they never
remove half or more of them &mdash; a majority is what defines the consensus
&mdash; and the test needs at least <b>three</b> replicates to run at all: with
two, nothing says which of the two is the odd one.</p>
"""


def binding_constants(assay_type: AssayType) -> str:
    """How many binding constants *assay_type* fits, in words: ``no binding constant``, ``2 binding constants``."""
    n = sum(kind is ParamKind.BINDING_CONSTANT for kind in ASSAY_REGISTRY[assay_type].param_kinds.values())
    return 'no binding constant' if n == 0 else f'{n} binding constant{"" if n == 1 else "s"}'


def dye_alone_keys(assay_type: AssayType) -> tuple[str, ...]:
    """The signal coefficients a dye-alone calibration bounds in *assay_type*; empty where it bounds none.

    The calibration measures the free dye, so it bounds the baseline and the free-dye
    coefficient of a model that has one, and nothing in a model without a dye.
    """
    return tuple(_DYE_ALONE_BOUNDS) if 'I_dye_free' in ASSAY_REGISTRY[assay_type].default_bounds else ()


def help_html(assay_type: AssayType) -> str:
    """The help of the view for *assay_type*: the model, its conditions, its parameters' bounds and the replicates.

    It explains what the view offers for that model only: the titrant stock where there
    is a fixed concentration to dilute, a model with no binding constant as a straight
    line fitted from the average of the replicates, and the dye-alone command with the
    coefficients it bounds.
    """
    _title, model = ASSAY_DESCRIPTIONS[assay_type.name]
    parameters = ''.join(PARAMETER_DESCRIPTIONS[key][1] for key in ASSAY_REGISTRY[assay_type].default_bounds)
    keys = dye_alone_keys(assay_type)
    name = ASSAY_NAMES[assay_type][0]
    fields = condition_fields(assay_type)
    if fields:
        conditions = _CONDITIONS_HELP_HTML
    else:
        conditions = f'<p class="topic">Conditions</p>\n<p>{name} needs no conditions besides the data.</p>\n'
    if any(f.unit_type == 'concentration' for f in fields):
        conditions += _STOCK_HELP_HTML
    unlimited = any(
        math.isinf(float(Q_(hi).magnitude)) for _lo, hi in ASSAY_REGISTRY[assay_type].default_bounds.values()
    )
    head = _BOUNDS_HELP_HTML + (_UNLIMITED_HELP_HTML if unlimited else '')
    if projectable(assay_type):
        bounds = _BOUNDS_KA_HELP_HTML + (_dye_alone_help(keys) if keys else '')
        replicates = REPLICATES_HELP_HTML
    else:
        bounds = _BOUNDS_LINE_HELP_HTML
        replicates = (
            f'<p class="topic">Replicates</p>\n<p>{name} is fitted from the average of the replicates '
            'switched on: with no binding constant there is nothing to test the replicates by.</p>\n'
        )
    return model + conditions + head + bounds + parameters + SCI_NOTE_HTML + replicates


@dataclass
class Amount:
    """A number as shown, and the exact value the form wrote it from (``None`` once typed over, and for a bound).

    A condition's exact value is in its base unit; a bound's text reads back as its value.
    """

    text: str
    exact: float | None = None

    def value(self) -> float | None:
        """The exact value the text was written from, else the number the text states."""
        return self.exact if self.exact is not None else parse_amount(self.text)


@dataclass
class ConditionEntry:
    """One condition as entered: its field, the unit it is shown in, and the amount in that unit.

    An amount the form wrote keeps its exact value in the condition's base unit.
    """

    field: ConditionField
    unit: str
    amount: Amount

    @property
    def name(self) -> str:
        return condition_name(self.field)

    def scale(self, unit: str | None = None) -> float:
        """One *unit* (the unit shown by default) in the condition's base unit."""
        return float(Q_(1, unit or self.unit).to(self.field.unit).magnitude)

    def value(self) -> float | None:
        """The value entered, in the base unit; ``None`` when it cannot be read."""
        if self.amount.exact is not None:
            return self.amount.exact
        shown = parse_amount(self.amount.text)
        return None if shown is None else shown * self.scale()


def _entry(field: ConditionField, base_value: float | None, concentration_unit: str) -> ConditionEntry:
    if field.unit_type == 'concentration':
        unit = concentration_unit
    else:
        unit = UNIT_CHOICES[field.unit_type][1] if field.unit_type in UNIT_CHOICES else field.unit
    entry = ConditionEntry(field, unit, Amount(''))
    if base_value is not None:
        _write(entry, base_value)
    return entry


def _write(entry: ConditionEntry, base_value: float) -> None:
    """Show *base_value* in the entry's unit, keeping the very number."""
    entry.amount = Amount(amount_text(base_value / entry.scale(), False), base_value)


def _bound_text(value: float) -> str:
    """What a bound field shows: the number with every figure it has, or nothing for no limit."""
    if not math.isfinite(value):
        return ''
    text = amount_text(value, False)
    if parse_amount(text) != value:
        text = repr(value)  # the fewest figures that read back as this very number
        if 'e' in text:
            mantissa, exponent = text.split('e')
            text = f'{mantissa.removesuffix(".0")}e{int(exponent)}'
        text = text.removesuffix('.0').replace('-', '−')
    return text


@dataclass
class BoundEntry:
    """One parameter's bounds as shown, in the parameter's unit; *default* is the registry's."""

    key: str
    unit: str
    default: tuple[float, float]
    amounts: list[Amount] = field(default_factory=list)

    @property
    def name(self) -> str:
        """The parameter as the interface names it: a binding constant by its glossary name, ``Kₐ guest``."""
        return fmt_param_plain(self.key)

    @property
    def may_be_unbounded(self) -> bool:
        """Whether the parameter has no upper limit while its upper field is empty: a signal parameter's."""
        return math.isinf(self.default[1])

    def values(self) -> tuple[float, float] | None:
        lo = self.amounts[0].value()
        hi = math.inf if self.may_be_unbounded and not self.amounts[1].text.strip() else self.amounts[1].value()
        return None if lo is None or hi is None else (lo, hi)

    def problem(self) -> str | None:
        """Why these bounds cannot be used, naming the parameter; ``None`` when they can."""
        values = self.values()
        if values is None:
            for amount, edge in zip(self.amounts, ('lower', 'upper'), strict=True):
                unbounded = edge == 'upper' and self.may_be_unbounded and not amount.text.strip()
                if amount.value() is None and not unbounded:
                    shown = amount.text.strip()
                    says = f'“{shown}” is not a number' if shown else 'is empty'
                    return f'{self.name}: the {edge} bound {says}. Enter a number, such as 1e3.'
        # Equal bounds are a deliberate pin: the parameter is held at that value and
        # not fitted, which Ka confidence reports for a binding constant.
        if values[0] > values[1]:
            return f'{self.name}: the lower bound must not be above the upper bound.'
        return None

    def set(self, lo: float, hi: float) -> None:
        """Show *lo* and *hi*; the text shown reads back as each very number."""
        self.amounts = [Amount(_bound_text(lo)), Amount(_bound_text(hi))]


class BindingForm:
    """The binding model as stated, with every rule of stating it.

    The edits are the methods a view calls when the user changes something;
    :meth:`conditions`, :meth:`problems`, :meth:`bounds`, :meth:`custom_bounds`,
    :meth:`bound_problems` and :attr:`per_replica` are what a fit reads. Every
    concentration of a fresh form is shown in *concentration_unit*.
    """

    def __init__(
        self, assay_type: AssayType = AssayType.GDA, concentration_unit: str = UNIT_CHOICES['concentration'][1]
    ) -> None:
        self.per_replica: bool = FitConfig().per_replica
        self.concentration_unit = concentration_unit
        self.stock = _entry(TITRANT_STOCK_FIELD, None, concentration_unit)
        self.set_assay(assay_type)

    # ------------------------------------------------------------------
    # The model
    # ------------------------------------------------------------------

    def set_assay(self, assay_type: AssayType) -> None:
        """Choose *assay_type* with a fresh form: its default conditions, constant totals, default bounds.

        The concentrations are shown in :attr:`concentration_unit`. The titrant stock
        keeps its value and unit. A stock carried over from another model would reach a
        fit without being seen, so the totals go back to constant with every choice of a
        model, and the stock is seen again when dilution is chosen.
        """
        self.assay_type = assay_type
        self.entries = {f.key: _entry(f, f.default, self.concentration_unit) for f in condition_fields(assay_type)}
        self.diluted = False
        self.contains: set[str] = set()
        meta = ASSAY_REGISTRY[assay_type]
        self.bound_entries: dict[str, BoundEntry] = {}
        for key, (lo, hi) in meta.default_bounds.items():
            default = tuple(float(v.magnitude) if isinstance(v, Quantity) else float(v) for v in (lo, hi))
            entry = BoundEntry(key, meta.units.get(key, ''), default)
            entry.set(*default)
            self.bound_entries[key] = entry

    @property
    def category(self) -> str:
        return ASSAY_REGISTRY[self.assay_type].category

    def choose_category(self, category: str) -> None:
        """Choose the first model of *category*; the category shown already keeps its model."""
        if category != self.category:
            self.set_assay(CATEGORIES[category][0])

    def choose_model(self, assay_type: AssayType) -> None:
        """Choose *assay_type*; the model shown already keeps everything stated for it."""
        if assay_type is not self.assay_type:
            self.set_assay(assay_type)

    def badge(self) -> str:
        """The model in short, with how many binding constants it fits: ``IDA · 1 binding constant``."""
        return f'{ASSAY_NAMES[self.assay_type][0]} · {binding_constants(self.assay_type)}'

    # ------------------------------------------------------------------
    # Conditions
    # ------------------------------------------------------------------

    def concentration_keys(self) -> tuple[str, ...]:
        """The model's fixed concentrations, in field order: what a dilution dilutes."""
        return tuple(key for key, e in self.entries.items() if e.field.unit_type == 'concentration')

    @property
    def offers_dilution(self) -> bool:
        """Whether there is a fixed concentration for the additions to dilute."""
        return bool(self.concentration_keys())

    @property
    def offers_contains(self) -> bool:
        """Whether the stock can hold some of the fixed concentrations and not others.

        With one fixed concentration a stock holding it leaves nothing diluted, which is
        the constant case.
        """
        return len(self.concentration_keys()) > 1

    def entry(self, key: str) -> ConditionEntry:
        """Condition *key*, the titrant stock included."""
        return self.stock if key == TITRANT_STOCK else self.entries[key]

    def edit(self, key: str, text: str) -> None:
        """Take *text* as the value of condition *key* in the unit it is shown in."""
        self.entry(key).amount = Amount(text)

    def set_value(self, key: str, base_value: float) -> None:
        """Show *base_value* (in the condition's base unit) as condition *key*, in the unit it is shown in."""
        _write(self.entry(key), base_value)

    def set_unit(self, key: str, unit: str) -> None:
        """Show condition *key* in *unit*, the same concentration written in it with every figure kept.

        A value that cannot be read keeps its text, which is then read in the new unit.
        """
        entry = self.entry(key)
        if unit == entry.unit:
            return
        value = entry.value()
        factor = entry.scale() / entry.scale(unit)
        entry.unit = unit
        if value is not None:
            text = shifted_text(entry.amount.text, factor) if entry.amount.exact is None else None
            entry.amount = Amount(text or amount_text(value / entry.scale(), False), value)

    def set_diluted(self, diluted: bool) -> None:
        """State that the additions dilute the sample (*diluted*), or that the totals stay constant."""
        self.diluted = diluted and self.offers_dilution

    def set_contains(self, key: str, on: bool) -> None:
        """State that the stock holds fixed concentration *key* at the sample's own concentration, or not."""
        if on:
            self.contains.add(key)
        else:
            self.contains.discard(key)

    def conditions(self) -> dict[str, Any]:
        """The conditions as entered, in base units, with a direct binding assay's ``mode``.

        With dilution stated they also carry ``titrant_stock`` and ``stock_contains`` (the
        concentrations the stock holds, in field order); with the totals constant neither
        key is there, so the assay is built exactly as it is without a dilution. A value
        that cannot be read is NaN, and :meth:`problems` names it.
        """
        out: dict[str, Any] = {}
        for key, entry in self.entries.items():
            value = entry.value()
            out[key] = Q_(math.nan if value is None else value, entry.field.unit)
        if self.assay_type in DBA_MODES:
            out['mode'] = DBA_MODES[self.assay_type]
        if self.diluted:
            stock = self.stock.value()
            out[TITRANT_STOCK] = Q_(math.nan if stock is None else stock, TITRANT_STOCK_FIELD.unit)
            out['stock_contains'] = tuple(key for key in self.concentration_keys() if key in self.contains)
        return out

    def condition_units(self) -> dict[str, str]:
        """The unit each condition is shown in, the titrant stock included."""
        return {**{key: e.unit for key, e in self.entries.items()}, TITRANT_STOCK: self.stock.unit}

    def condition_problem(self, key: str) -> str | None:
        """Why condition *key* cannot be used, as a sentence naming it; ``None`` when it can."""
        entry = self.entry(key)
        if key == TITRANT_STOCK:
            if not self.diluted:
                return None
            value = entry.value()
            text = entry.amount.text.strip()
            if value is None and text:
                return f'{entry.name}: “{text}” is not a number. Enter the concentration of the stock, such as 1.'
            if value is None or value <= 0:
                return (
                    'Enter the titrant stock concentration, or choose “Stay constant”. It is the concentration '
                    'of the stock the titrant was added from, and it says how much each addition dilutes the sample.'
                )
            return None
        text = entry.amount.text.strip()
        if entry.value() is None:
            if not text:
                return f'{entry.name} has no value: enter a number.'
            return f'{entry.name}: “{text}” is not a number. Enter a number, such as 2.5.'
        if entry.value() < 0:
            return f'{entry.name} is below zero: enter a value of 0 or more.'
        return None

    def problems(self) -> list[str]:
        """Why the conditions as stated cannot be used, one sentence per problem; empty when they can.

        The remaining check — the stock has to be more concentrated than the highest
        titrant concentration — needs the loaded data, so the session makes that one.
        """
        found = [p for key in self.entries if (p := self.condition_problem(key))]
        stock = self.condition_problem(TITRANT_STOCK)
        if stock:
            found.append(stock)
        held = [key for key in self.concentration_keys() if key in self.contains]
        if self.diluted and held and len(held) == len(self.concentration_keys()):
            names = and_join(self.entries[key].name for key in held)
            found.append(
                f'The titrant stock is ticked for every fixed concentration ({names}), so nothing is left '
                'for the additions to dilute — that is the “Stay constant” case: choose it instead.'
            )
        return found

    # ------------------------------------------------------------------
    # Bounds
    # ------------------------------------------------------------------

    def edit_bound(self, key: str, index: int, text: str) -> None:
        """Take *text* as the lower (0) or upper (1) bound of parameter *key*, in its unit."""
        self.bound_entries[key].amounts[index] = Amount(text)

    def set_bounds(self, key: str, lo: float, hi: float) -> None:
        """Show *lo* and *hi* as the bounds of parameter *key*, in its unit."""
        self.bound_entries[key].set(lo, hi)

    def reset_bounds(self) -> None:
        """Show the model's default bounds again."""
        for entry in self.bound_entries.values():
            entry.set(*entry.default)

    def bounds(self) -> dict[str, tuple[Quantity, Quantity] | None]:
        """Every parameter's bounds as Quantities in its unit; ``None`` for one :meth:`bound_problems` names."""
        shown: dict[str, tuple[Quantity, Quantity] | None] = {}
        for key, entry in self.bound_entries.items():
            values = None if entry.problem() is not None else entry.values()
            shown[key] = None if values is None else (Q_(values[0], entry.unit), Q_(values[1], entry.unit))
        return shown

    def custom_bounds(self) -> dict[str, tuple[Quantity, Quantity]] | None:
        """The bounds that differ from the defaults, as Quantities; ``None`` when none does.

        A parameter whose bounds cannot be used is left out; :meth:`bound_problems` names it.
        """
        changed = {
            key: bounds
            for key, bounds in self.bounds().items()
            if bounds is not None and (bounds[0].magnitude, bounds[1].magnitude) != self.bound_entries[key].default
        }
        return changed or None

    def bound_problems(self) -> list[str]:
        """Why the bounds shown cannot be used, one sentence per parameter; empty when they can."""
        return [problem for entry in self.bound_entries.values() if (problem := entry.problem())]

    def dye_alone_keys(self) -> tuple[str, ...]:
        """The signal coefficients a dye-alone calibration bounds in this model; empty where it bounds none."""
        return dye_alone_keys(self.assay_type)

    def apply_dye_alone(self, bounds: dict[str, tuple[Quantity, Quantity]]) -> None:
        """Show the bounds a dye-alone calibration gives, each in its parameter's unit, rounded to the figures shown.

        A ±20 % margin needs no more figures than a field shows, and the number used is
        then the number on screen.
        """
        for key in self.dye_alone_keys():
            if key in bounds:
                entry = self.bound_entries[key]
                lo, hi = (parse_amount(amount_text(float(Q_(v).to(entry.unit).magnitude), False)) for v in bounds[key])
                entry.set(lo, hi)

    # ------------------------------------------------------------------
    # Replicates
    # ------------------------------------------------------------------

    def set_per_replica(self, on: bool) -> None:
        """Fit each replicate on its own as well (*on*), or only their average."""
        self.per_replica = on
