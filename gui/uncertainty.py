"""What the user states about the inputs a fit rests on, and the rules of stating it, without widgets.

One entry per perturbable input of the assay (every concentration and binding-constant
condition, then the titrant): *Fixed*, a σ or a range, stated in percent of the entered
value or in the input's own unit. The titrant is a series with no single value, so it is
stated in percent only. Below the inputs come the named shared error sources — a σ in
percent and the inputs each moves together — and the random error of each titrant
addition. Together they are one :class:`~core.pipeline.inputs.ErrorModel`
(:meth:`UncertaintyForm.errors`), which feeds the interval of every fit and the
sensitivity analysis.

Every amount is kept as the text shown for it, so the number used is the number on
screen; a text that is not a number is a problem naming the input, and so is every
statement no fit could use (:meth:`UncertaintyForm.problems`). Each assay's statements
are kept apart and come back when the assay is chosen again.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping

from core.assays.registry import ASSAY_REGISTRY, AssayType
from core.pipeline.inputs import (
    TITRANT,
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
from gui.plotting.labels import decimal_text, field_text, parse_decimal, parse_number, plain_label
from gui.widgets.assay_conditions import ASSAY_CONDITIONS, UNIT_CHOICES, ConditionField, input_labels

HELP_HTML = """
<p>How far each input may be off: the titrant concentrations and the fixed
conditions (<i>[Host]<sub>0</sub></i>, <i>[Dye]<sub>0</sub></i>,
<i>K<sub>a</sub>,dye</i>, …). Each carries pipetting, weighing or calibration error,
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
<p>Choose a kind for each input, and state its amount in percent of the input's
entered value or in the input's own unit (<i>Stated in</i>):</p>
<ul>
  <li><b>σ</b> — one standard deviation of a normal distribution.
      The fit may put the input anywhere, but moving it by <i>e</i> costs
      (<i>e</i>/σ)<sup>2</sup>: one σ is cheap, three σ is not. Each sample of the
      analysis draws the input from that distribution, cut off so the input stays
      above zero. With σ = 5 %, about 95 of every 100 draws land within ±10 %, and a
      few further out.</li>
  <li><b>Range</b> — <i>from</i> and <i>to</i> as offsets in percent of the entered
      value, or as the lowest and highest value in the input's own unit. For the fit
      every value between them is equally acceptable and none outside; each sample of
      the analysis draws evenly between them. A range may be lopsided, such as −6 % to
      +4 %.</li>
  <li><b>Fixed</b> — the input is taken as exact: the fit holds it at the value you
      entered, and the analysis leaves it out.</li>
</ul>
<p>With every input fixed, as the view opens, the fit reports one interval, <b>Inputs as
entered</b>: what the data alone allow, the inputs taken as exactly right. Once an input
may move or an error of the additions is stated, the fit reports the <b>Input-aware</b>
interval, with the one of the inputs as entered beside it.</p>
<p>Switching the kind or the unit carries the numbers over: σ = 5 % becomes the range
−5 % to +5 %, or a σ of 5 % of the entered value in the input's unit, and a range becomes
a σ of half its width, centred on the entered value. The spread of the draws changes with
the kind: an even draw between −5 % and +5 % varies less than a σ of 5 %. An amount that
is not a number cannot be carried over: correct it, or choose <b>Fixed</b>.</p>
<p>A σ of 0, or a range whose <i>to</i> is not above its <i>from</i>, does not vary
the input. Nor can a value in the input's unit be used while the input is not a number
above 0 under <b>Binding model</b>, nor a range that reaches down to zero. The input then shows a warning, and
neither a fit nor an analysis starts until you change the value or choose
<b>Fixed</b>.</p>
<p>Use realistic numbers: pipetting error is often a few percent, a stated
literature K<sub>a</sub>,dye may be uncertain by 10–20%.</p>
<p class="topic">Shared error sources</p>
<p>The entry on an input above is the error <b>only that input</b> has. An error several
inputs have in common — their solutions come from one stock, were weighed on one balance
or pipetted with one pipette — is a <b>shared error source</b>: name it, state its σ in
percent, and tick every input it moves. The sources are independent and multiply, so an
input with an entry of its own and a shared source carries both. A shared source moves
every concentration made from that stock by the same percentage, and a binding constant
measured with it (such as a K<sub>a</sub>,dye fitted with the same stock) by the same
percentage the other way.</p>
<p>Both the interval of every fit and the K<sub>a</sub> Sensitivity analysis use exactly
this model. The analysis reports a shared source as one item, which is what you can act
on: one stock to re-make, one pipette to recalibrate.</p>
<p class="topic">Random error of each addition</p>
<p>The titrant entry above moves the whole series by one factor — a stock or dilution
error that shifts every concentration by the same fraction. The scatter of the individual
additions is stated here instead. Choose <i>One cuvette</i>, sequential additions where
every point carries the errors of the additions before it as well as its own, or
<i>Separate samples</i>, where each point is pipetted on its own.</p>
<p>A random error in each addition moves every point along the titrant axis. The
residuals show only part of that: for additions into one cuvette, most of it shifts the
whole curve the way a different K<sub>a</sub> would. When you state it, the fit works out
from your σ and the slope of the fitted curve how much more K<sub>a</sub> varies than the
scatter alone implies, and allows for that factor in the interval of K<sub>a</sub>. Part
of the scatter is then put down to the additions rather than to noise, so where the
replicates show a noise law, the interval can come out about as wide as, or slightly
narrower than, the one without the additions. The result says by what factor. The misfit test, the check of the
inputs against what you stated and the test of the replicates allow for the same
error.</p>
<p>Choose what your replicates are. Replicates made as <i>separate titrations</i> each have
their own addition errors, and their average carries σ/√<i>m</i> of them for <i>m</i>
replicates. <i>Repeated reads of one titration</i> share them, and their average carries
σ itself. The data cannot tell the two apart reliably, so it is stated here; separate
titrations is the setting the view opens with.</p>
<p>A σ larger than the real one gives a wider interval than needed. The K<sub>a</sub>
Sensitivity analysis samples the same error and ranks it against the other sources.</p>
<p class="topic">Effect on the fit</p>
<p>The side panel, <i>Effect on the fit</i>, reads the last fit against what you stated.
<b>Interval of the last fit</b> draws each binding constant's <i>Input-aware</i> interval
beside the one of the <i>Inputs as entered</i> on one K<sub>a</sub> axis.
<b>Inputs against what you stated</b> gives the fit's tests: whether the curve misses the data,
with the inputs moved and as entered, and whether the inputs together moved further than you
stated; <i>Review in Ka confidence</i> shows where the fit put them. <b>Also used by</b>
names the Sensitivity analysis, which draws the inputs from the same statement.</p>
"""

#: The σ an input, a shared source and the additions entry offer when first stated. Every
#: input opens *Fixed*, no source is stated and the additions read *None*, so this number
#: reaches a fit only once the user states something.
DEFAULT_SIGMA_PCT = 5.0
#: How the titrant was added, as the additions entry offers it: no statement, one cuvette
#: filled addition after addition, or a sample prepared on its own for every point.
ADDITION_MODES = ('None', 'One cuvette', 'Separate samples')
#: What the replicates are, for an error of the additions.
REPLICATE_KINDS = ('Separate titrations', 'Repeated reads')

_DEFAULT_SPEC = InputSpec.sigma_pct(DEFAULT_SIGMA_PCT)


def shifted_text(text: str, factor: float) -> str:
    """The amount *text* states, multiplied by *factor*, with every figure typed kept: ``0.215`` × 1000 is ``215``.

    A factor between the units a concentration is shown in is a power of ten, which
    moves the decimal point and loses no figure; any other factor is written as the form
    writes an amount.
    """
    exponent = round(math.log10(factor))
    value = parse_decimal(text)
    if value is not None and math.isclose(factor, 10.0**exponent, rel_tol=1e-12):
        return decimal_text(value.scaleb(exponent))
    return field_text(parse_number(text) * factor)


def _kind_name(kind: SpecKind) -> str:
    """*kind* as a sentence names it: ``a σ``, ``a range``."""
    return 'a σ' if kind is SpecKind.SIGMA else 'a range'


def restate(spec: InputSpec, kind: SpecKind, relative: bool, nominal: float | None) -> InputSpec | None:
    """*spec* stated as *kind*, in percent or in the input's unit, with the same centre and half-width.

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


def spread_pct(spec: InputSpec, nominal: float | None) -> tuple[float, float] | None:
    """The offsets in percent of the entered value that *spec* spans: ±2σ, or the range's ends.

    ``None`` for a value in the input's unit while there is no positive entered value.
    """
    if spec.relative:
        if spec.kind is SpecKind.SIGMA:
            return -2 * spec.sigma, 2 * spec.sigma
        return spec.lo, spec.hi
    if nominal is None or not nominal > 0:
        return None
    if spec.kind is SpecKind.SIGMA:
        half = 200 * spec.sigma / nominal
        return -half, half
    return 100 * (spec.lo - nominal) / nominal, 100 * (spec.hi - nominal) / nominal


@dataclass
class InputEntry:
    """One input as stated: its kind (``None`` for *Fixed*), percent or unit, and the amounts shown.

    ``texts`` holds one amount for a σ and two (*from*, *to*) for a range, in percent or
    in ``unit``. ``carried`` is the last uncertainty that varied the input, carried into
    the next kind chosen; ``pending`` an uncertainty the kind shown could not take yet,
    for want of an entered value above 0. ``exact`` holds the amounts in the base unit
    that ``texts`` were written from when the condition's unit changed, so the
    uncertainty stays the very number it was. ``refused`` names the kind or unit a switch
    was refused to while an amount could not be read; ``''`` otherwise.
    """

    key: str
    name: str
    label: str
    field: ConditionField | None
    kind: SpecKind | None = None
    relative: bool = True
    texts: tuple[str, ...] = ()
    unit: str = ''
    carried: InputSpec = _DEFAULT_SPEC
    pending: InputSpec | None = None
    exact: tuple[tuple[str, ...], tuple[float, ...]] | None = None
    refused: str = ''


@dataclass
class SourceEntry:
    """One shared error source as stated: its name, its σ in percent as shown, and the inputs it moves."""

    name: str
    sigma_text: str = field_text(DEFAULT_SIGMA_PCT, point=True)
    inputs: set[str] = field(default_factory=set)


@dataclass
class AdditionsEntry:
    """The random error of each addition as stated: the mode (an index of :data:`ADDITION_MODES`), σ and replicates."""

    mode: int = 0
    sigma_text: str = field_text(DEFAULT_SIGMA_PCT, point=True)
    separate: bool = True


class UncertaintyForm:
    """The stated error model of the assay chosen, with every rule of stating it.

    :meth:`set_assay` shows another assay's inputs, as last left for that assay;
    :meth:`set_conditions` gives the entered values and units that a percentage is read
    against. The edits are the methods a view calls when the user changes something;
    :meth:`errors` and :meth:`problems` are what a fit reads.
    """

    def __init__(self, assay_type: AssayType = AssayType.GDA) -> None:
        self._entries: dict[tuple[AssayType, str], InputEntry] = {}
        self._sources: dict[AssayType, list[SourceEntry]] = {}
        self._additions: dict[AssayType, AdditionsEntry] = {}
        self.nominals: dict[str, float] = {}
        self.units: dict[str, str] = {}
        self.assay_type = assay_type
        self.set_assay(assay_type)

    # ------------------------------------------------------------------
    # The assay and its inputs
    # ------------------------------------------------------------------

    def set_assay(self, assay_type: AssayType) -> None:
        """Show *assay_type*'s inputs, sources and additions entry as last left for it.

        The entered values of another assay are dropped: the new assay's arrive
        through :meth:`set_conditions`.
        """
        if assay_type is not self.assay_type:
            self.nominals, self.units = {}, {}
        self.assay_type = assay_type
        fields = ASSAY_CONDITIONS[assay_type]
        by_key = {f.key: f for f in fields}
        self._base = {f.key: Q_(f.default, f.unit) for f in fields if f.unit_type in UNIT_CHOICES}
        html = input_labels(assay_type)
        self.keys = [key for key, _kind in perturbable_inputs(self._base)]
        for key in self.keys:
            if (assay_type, key) not in self._entries:
                entry = InputEntry(key, plain_label(html[key]), html[key], by_key.get(key))
                self._entries[(assay_type, key)] = entry
                self._write(entry, _DEFAULT_SPEC)
        self._sources.setdefault(assay_type, [])
        self._additions.setdefault(assay_type, AdditionsEntry())

    @property
    def available(self) -> bool:
        """Whether the assay reports an association constant, so an uncertainty in its inputs changes anything."""
        return projectable(self.assay_type) and bool(self.keys)

    def unavailable_reason(self) -> str:
        """Why an uncertainty in the inputs changes nothing for the assay, in one plain sentence."""
        return (
            f'{ASSAY_REGISTRY[self.assay_type].subtype_label} has no association constant, '
            'so an uncertainty in the inputs changes nothing here.'
        )

    def entry(self, key: str) -> InputEntry:
        """Input *key* of the assay shown, as stated."""
        return self._entries[(self.assay_type, key)]

    def entries(self) -> list[InputEntry]:
        """Every input of the assay shown, in the order the fit lists them (the titrant last)."""
        return [self.entry(key) for key in self.keys]

    def input_labels(self) -> dict[str, str]:
        """Each input's key and the plain name the form gives it, the titrant included."""
        return {key: self.entry(key).name for key in self.keys}

    def nominal(self, key: str) -> float | None:
        """Input *key*'s entered value in its base unit; ``None`` for the titrant and while none can be read."""
        return None if key == TITRANT else self.nominals.get(key)

    def set_conditions(self, conditions: Mapping[str, Any], units: Mapping[str, str], finished: bool = True) -> None:
        """Take the entered values and the units they are shown in.

        A percentage is read against the entered value when the kind changes, and an
        amount in the input's unit is written in the unit its condition is shown in: one
        whose unit changed is written again in the new one, with every figure kept, and
        states the very number it stated before. A condition that cannot be read (NaN)
        has no entered value. A conversion waiting for an entered value above 0 is made
        once the edit of the conditions is *finished* (:meth:`convert_pending`): a value
        still being typed is not the number the user is entering.
        """
        self.nominals = {
            key: float(v.magnitude)
            for key, v in conditions.items()
            if isinstance(v, Quantity) and math.isfinite(v.magnitude)
        }
        self.units = dict(units)
        for entry in self.entries():
            unit = self._unit(entry)
            if entry.kind is not None and not entry.relative and entry.unit and entry.unit != unit:
                values = self._values(entry)
                if values is not None:
                    factor = self._scale(entry, entry.unit) / self._scale(entry, unit)
                    entry.texts = tuple(shifted_text(text, factor) for text in entry.texts)
                    entry.exact = (entry.texts, tuple(values))
                entry.unit = unit
        if finished:
            self.convert_pending()

    def convert_pending(self) -> bool:
        """Make every conversion waiting for an entered value above 0 that has one now; say whether any was made."""
        waiting = [e for e in self.entries() if e.pending is not None and (self.nominal(e.key) or 0) > 0]
        for entry in waiting:
            self._write(entry, entry.pending)
        return bool(waiting)

    # ------------------------------------------------------------------
    # Edits of one input
    # ------------------------------------------------------------------

    def choose_kind(self, key: str, kind: SpecKind | None) -> None:
        """State input *key* as *kind* (``None``: *Fixed*), carrying its last uncertainty over.

        An amount that cannot be read has nothing to carry over: a switch to another
        kind is then refused and named by :meth:`problem`. *Fixed* is always taken and
        keeps the text, which comes back with the kind it was typed for.
        """
        entry = self.entry(key)
        if kind is entry.kind:
            return
        if self._unreadable(entry):
            if kind is None or (entry.kind is None and len(entry.texts) == _count(kind)):
                entry.kind, entry.refused = kind, ''
                return
            if entry.kind is not None:
                entry.refused = _kind_name(kind)
                return
        self._carry(entry)
        entry.kind = kind
        if kind is not None:
            self._write(entry, entry.carried)

    def state_in(self, key: str, relative: bool) -> None:
        """State input *key* in percent (*relative*) or in its own unit, carrying the numbers over.

        The titrant has no single value, so it is stated in percent only. An amount that
        cannot be read has nothing to carry over, so the switch is then refused and named
        by :meth:`problem`.
        """
        entry = self.entry(key)
        if relative is entry.relative or (key == TITRANT and not relative):
            return
        if self._unreadable(entry):
            if entry.kind is not None:
                entry.refused = '%' if relative else self._unit(entry)
                return
            entry.texts = ()  # left with Fixed in the other unit, so they no longer apply
        self._carry(entry)
        entry.relative = relative
        if entry.kind is not None:
            self._write(entry, entry.carried)

    def edit(self, key: str, index: int, text: str) -> None:
        """Take *text* as amount *index* of input *key*: its σ, or the *from* (0) or *to* (1) of its range."""
        entry = self.entry(key)
        texts = list(entry.texts)
        texts[index] = text
        entry.texts, entry.pending, entry.refused = tuple(texts), None, ''
        if not entry.relative:
            entry.unit = self._unit(entry)

    def set_spec(self, key: str, spec: InputSpec | None) -> None:
        """State *spec* on input *key* as given; ``None`` fixes it."""
        entry = self.entry(key)
        entry.pending, entry.refused = None, ''
        entry.kind = None if spec is None else spec.kind
        if spec is not None:
            entry.relative = spec.relative
            self._write(entry, spec)

    def spec(self, key: str) -> InputSpec | None:
        """The uncertainty input *key* states; ``None`` when it is *Fixed* or its amounts cannot be read."""
        entry = self.entry(key)
        if entry.kind is None or entry.pending is not None:
            return None
        values = self._values(entry)
        if values is None:
            return None
        if entry.kind is SpecKind.SIGMA:
            return InputSpec(SpecKind.SIGMA, sigma=values[0], relative=entry.relative)
        return InputSpec(SpecKind.INTERVAL, lo=values[0], hi=values[1], relative=entry.relative)

    def problem(self, key: str) -> str | None:
        """Why input *key*'s statement cannot be used, as a sentence naming it; ``None`` when it can.

        A σ is a penalty the fit pays and a distribution cut off above zero, so only a
        range can take the input down to zero, where the model has nothing to fit.
        """
        entry = self.entry(key)
        name = entry.name
        if entry.kind is None:
            return None
        if entry.pending is not None:
            target = f'{_kind_name(entry.kind)} in {"%" if entry.relative else self._unit(entry)}'
            return self._no_value(key, f'its uncertainty cannot be converted to {target}')
        refused = f' to carry over to {entry.refused}' if entry.refused else ''
        for text in entry.texts:
            if not text.strip():
                return f'{name} has no amount{refused}: enter a number, or choose “Fixed”.'
            if parse_number(text) is None:
                over = f', so it cannot be carried over to {entry.refused}' if entry.refused else ''
                return f'{name}: “{text}” is not a number{over}. Enter a number, or choose “Fixed”.'
        nominal = self.nominal(key)
        if not entry.relative and not (nominal is not None and nominal > 0):
            return self._no_value(key, 'an uncertainty in its unit cannot be used')
        spec = self.spec(key)
        if not spec.varies:
            if spec.kind is SpecKind.SIGMA:
                return f'{name} cannot vary: set σ above 0, or choose “Fixed”.'
            return f'{name} cannot vary: set “to” above “from”, or choose “Fixed”.'
        if spec.kind is SpecKind.INTERVAL and axis_reaches_zero(spec, nominal, name):
            end = '−100 %' if spec.relative else '0'
            return f'{name} would be taken down to zero: set “from” above {end}.'
        return None

    def _no_value(self, key: str, consequence: str) -> str:
        """Why input *key* has no entered value above 0 to read its uncertainty against, and *consequence*."""
        name = self.entry(key).name
        if self.nominal(key) is None:
            return (
                f'{name} cannot be read under Binding model, so {consequence}: enter a number for {name} there first.'
            )
        if self.nominal(key) < 0:
            return f'{name} is below 0 under Binding model, so {consequence}: set {name} above 0 there first.'
        return f'{name} is 0 in the conditions, so {consequence}: set {name} above 0 first.'

    def unit(self, key: str) -> str:
        """The unit input *key* is stated in besides percent: its condition's unit, the titrant's none."""
        return self._unit(self.entry(key))

    # ------------------------------------------------------------------
    # Shared sources
    # ------------------------------------------------------------------

    @property
    def sources(self) -> list[SourceEntry]:
        """The shared error sources of the assay shown, in the order they are reported."""
        return self._sources[self.assay_type]

    def add_source(self, source: SharedSource | None = None) -> None:
        """State one more shared source: *source*, or one under a name no other source has, with a σ to edit."""
        if source is not None:
            self.sources.append(SourceEntry(source.name, field_text(source.sigma_pct, point=True), set(source.inputs)))
            return
        taken = {source.name for source in self.sources}
        number = 1
        while f'Shared source {number}' in taken:
            number += 1
        self.sources.append(SourceEntry(f'Shared source {number}'))

    def remove_source(self, index: int) -> None:
        del self.sources[index]

    def rename_source(self, index: int, name: str) -> None:
        self.sources[index].name = name

    def set_source_sigma(self, index: int, text: str) -> None:
        self.sources[index].sigma_text = text

    def tick(self, index: int, key: str, on: bool) -> None:
        """Let shared source *index* move input *key*, or not."""
        inputs = self.sources[index].inputs
        if on:
            inputs.add(key)
        else:
            inputs.discard(key)

    def _source(self, source: SourceEntry, readable: bool = False) -> SharedSource:
        """*source* as the model states it: its name without surrounding blanks, its σ and its inputs as listed.

        With *readable*, a σ that is not a number is read as 1 %, for the checks that do not
        concern the σ.
        """
        sigma = parse_number(source.sigma_text)
        if sigma is None:
            sigma = 1.0 if readable else math.nan
        return SharedSource(source.name.strip(), sigma, tuple(key for key in self.keys if key in source.inputs))

    def source_problems(self) -> list[list[str]]:
        """What is wrong with each shared source, in the sentences a run refuses with, one list per source.

        The sources are put to :func:`core.pipeline.inputs.source_problems` one more at a
        time, and a source gets every sentence it added — a name another source already
        has included.
        """
        stated: list[SharedSource] = []
        reported: list[str] = []
        found: list[list[str]] = []
        for source in self.sources:
            stated.append(self._source(source, readable=True))
            every = source_problems(ErrorModel(shared=tuple(stated)), self._base, self.input_labels())
            own = every[len(reported) :]
            reported = every
            if parse_number(source.sigma_text) is None:
                own.insert(
                    0,
                    f"The uncertainty of the shared error source '{source.name.strip()}': “{source.sigma_text}” "
                    'is not a number. Enter it in percent, or remove the source.',
                )
            found.append(own)
        return found

    # ------------------------------------------------------------------
    # The random error of each addition
    # ------------------------------------------------------------------

    @property
    def additions_entry(self) -> AdditionsEntry:
        return self._additions[self.assay_type]

    def set_additions_mode(self, mode: int) -> None:
        """How the titrant was added, an index of :data:`ADDITION_MODES`; 0 states no error of the additions."""
        self.additions_entry.mode = mode

    def set_additions_sigma(self, text: str) -> None:
        self.additions_entry.sigma_text = text

    def set_separate_titrations(self, separate: bool) -> None:
        self.additions_entry.separate = separate

    def additions(self) -> AdditionError | None:
        """The random error of each addition as stated; ``None`` while no mode is chosen."""
        entry = self.additions_entry
        if entry.mode == 0:
            return None
        sigma = parse_number(entry.sigma_text)
        return AdditionError(
            sigma_pct=math.nan if sigma is None else sigma,
            sequential=entry.mode == 1,
            separate_titrations=entry.separate,
        )

    def additions_problem(self) -> str | None:
        """Why the additions entry cannot be used, in the sentence a run refuses with; ``None`` when it can."""
        entry = self.additions_entry
        if entry.mode == 0:
            return None
        if parse_number(entry.sigma_text) is None:
            return (
                f'The random error of each addition: “{entry.sigma_text}” is not a number. '
                "Enter it in percent, or set it to 'None'."
            )
        found = source_problems(ErrorModel(additions=self.additions()), self._base, self.input_labels())
        return found[0] if found else None

    # ------------------------------------------------------------------
    # The model
    # ------------------------------------------------------------------

    def errors(self) -> ErrorModel:
        """The whole error model as stated.

        An input's own uncertainty is in ``specs``, left out while the input is *Fixed*,
        which takes it as exact. A percentage is in percent of the entered value and an
        amount in the input's unit in its base unit: the conversion to a relative offset
        belongs to :func:`core.pipeline.inputs.constraints`, which reads the conditions
        of the assay being fitted. The shared sources come in the order they are shown,
        and the additions entry is ``None`` until a mode is chosen. A statement that
        cannot be used is named by :meth:`problems`, which stops the fit; it is not
        dropped silently here. An assay without an association constant states nothing.
        """
        if not self.available:
            return ErrorModel()
        return ErrorModel(
            specs={key: spec for key in self.keys if (spec := self.spec(key)) is not None},
            shared=tuple(self._source(source) for source in self.sources),
            additions=self.additions(),
        )

    def problems(self) -> list[str]:
        """Why the model cannot be used as stated, one sentence per problem naming its source; empty when it can.

        Every input is checked, then every shared source and the additions entry, so
        nothing is left to find on the next attempt.
        """
        if not self.available:
            return []
        found = [problem for key in self.keys if (problem := self.problem(key))]
        found += [problem for own in self.source_problems() for problem in own]
        additions = self.additions_problem()
        return found + ([additions] if additions else [])

    def varying(self) -> int:
        """How many inputs the model moves: by an uncertainty of their own or through a shared source.

        A σ of 0, a range with no width or a source whose σ is not above 0 moves nothing.
        """
        errors = self.errors()
        own = {key for key, spec in errors.specs.items() if spec.varies}
        shared = {key for source in errors.shared if source.sigma_pct > 0 for key in source.inputs}
        return len(own | shared)

    def set_specs(self, specs: Mapping[str, InputSpec]) -> None:
        """State *specs* on the inputs they name, and nothing else.

        Every other input *Fixed*, no shared source, and no error of the additions: the
        form then states exactly ``ErrorModel(specs=specs)``. A key naming no input of the
        assay shown is an error of the caller.
        """
        unknown = set(specs) - set(self.keys)
        if unknown:
            raise KeyError(f'no input {sorted(unknown)} in {self.assay_type.name}')
        for key in self.keys:
            self.set_spec(key, specs.get(key))
        self.sources.clear()
        self._additions[self.assay_type] = AdditionsEntry()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _unit(self, entry: InputEntry) -> str:
        if entry.field is None:
            return ''
        return self.units.get(entry.key) or UNIT_CHOICES[entry.field.unit_type][1]

    @staticmethod
    def _scale(entry: InputEntry, unit: str) -> float:
        """One *unit* in the input's base unit."""
        return float(Q_(1, unit).to(entry.field.unit).magnitude)

    def _values(self, entry: InputEntry) -> list[float] | None:
        """The amounts shown, in percent or in the input's base unit; ``None`` when one cannot be read.

        Amounts written again in another unit are the very numbers they were written from.
        """
        if not entry.relative and entry.exact is not None and entry.exact[0] == entry.texts:
            return list(entry.exact[1])
        values = [parse_number(text) for text in entry.texts]
        if any(v is None for v in values):
            return None
        if entry.relative:
            return values
        scale = self._scale(entry, entry.unit or self._unit(entry))
        return [v * scale for v in values]

    @staticmethod
    def _unreadable(entry: InputEntry) -> bool:
        """Whether an amount the entry shows, or keeps while *Fixed*, is not a number."""
        return entry.pending is None and any(parse_number(text) is None for text in entry.texts)

    def _carry(self, entry: InputEntry) -> None:
        """Keep what the entry states as the uncertainty the next kind starts from.

        Amounts waiting for a conversion are stale: the uncertainty to carry is the one
        waiting, and the blank amounts shown meanwhile are dropped.
        """
        current = self.spec(entry.key)
        if current is not None:
            entry.carried = current
        elif entry.pending is not None:
            entry.carried, entry.texts = entry.pending, ()
        entry.pending, entry.refused = None, ''

    def _write(self, entry: InputEntry, spec: InputSpec) -> None:
        """Show *spec* as the entry's kind; wait when that needs an entered value above 0."""
        kind = entry.kind or spec.kind
        restated = restate(spec, kind, entry.relative, self.nominal(entry.key))
        n = _count(kind)
        entry.exact, entry.refused = None, ''
        if restated is None:
            entry.pending, entry.texts = spec, ('',) * n
            return
        entry.pending = None
        values = [restated.sigma] if kind is SpecKind.SIGMA else [restated.lo, restated.hi]
        if entry.relative:
            entry.texts = tuple(field_text(v, point=True) for v in values)
        else:
            entry.unit = self._unit(entry)
            entry.texts = tuple(field_text(v / self._scale(entry, entry.unit)) for v in values)


def _count(kind: SpecKind) -> int:
    """How many amounts *kind* is stated with: a σ one, a range its two ends."""
    return 1 if kind is SpecKind.SIGMA else 2
