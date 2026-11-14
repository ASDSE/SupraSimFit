"""What Sensitivity shows of a sensitivity run, and the settings of the next one, with no widget (DESIGN.md §8).

Every number here is read off one :class:`~core.pipeline.sensitivity.SensitivityResult`
— its Sobol' indices and intervals, its budget (:mod:`core.pipeline.budget`), its
samples — and, for the readings it is set beside, off the fit the session reports; the
functions return the text and the coordinates :mod:`gui.views.sensitivity` draws, and
work nothing out again. A Sobol' run shows, per binding constant, the spread of Kₐ the
stated inputs give (:func:`spread`) beside the samples (:func:`histogram`), the share of
the variance each source explains (:func:`index_chart`), the variance budget
(:func:`budget_table`) and what one source known better would buy (:func:`what_if_answer`);
a heatmap shows Kₐ over two inputs swept on a grid (:func:`heatmaps`). The callouts, the
facts of the run and the CSV of the budget are here too, and so is
:class:`AnalysisForm`, the run's own settings and the rules of stating them.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from html import escape

import numpy as np

from core.assays.registry import ASSAY_REGISTRY, AssayType
from core.pipeline.budget import what_if
from core.pipeline.fit_pipeline import FitResult
from core.pipeline.inputs import (
    ADDITIONS,
    TITRANT,
    ErrorModel,
    InputSpec,
    SpecKind,
    _to_fraction,
    axis_reaches_zero,
    is_shared,
    nominal_value,
    source_name,
    spec_bounds,
)
from core.pipeline.reporting import ParameterSummary, reports_conditional, summarize_parameters
from core.pipeline.sensitivity import (
    _SOBOL_BLOCKS,
    _SOBOL_SAMPLE_SIZES,
    MAX_SEED,
    SensitivityConfig,
    SensitivityMode,
    SensitivityResult,
)
from core.units import Q_
from gui import results as R
from gui.plotting.labels import (
    NO_LOWER,
    NO_UPPER,
    THIN,
    fmt_constant,
    fmt_r2,
    fmt_value,
    plain_label,
    spaced,
    superscript,
)
from gui.widgets.assay_conditions import condition_field, input_labels

# ---------------------------------------------------------------------------
# Names and the settings a run is made with
# ---------------------------------------------------------------------------

MODES = ('Sensitivity indices', 'Heatmap')
SAMPLE_SIZES: tuple[int, ...] = _SOBOL_SAMPLE_SIZES
#: The heatmap grids offered: cells per axis.
GRIDS = (11, 21, 31)
#: How far a heatmap axis stated as a σ reaches either side of the entered value, in σ.
SPANS = (1.0, 2.0, 3.0)
DEFAULT_SPAN = 2.0
#: The toolbar's Run analysis, the same key as Run fit (the primary of the view on screen).
RUN_ANALYSIS_KEY = R.RUN_FIT_KEY

ADDITIONS_LABEL = 'Each addition (random)'
ADDITIONS_NOTE = (
    'The random error of each addition is part of the reported interval when stated under Input uncertainty; '
    'it is listed here to be ranked against the other sources.'
)
INTERACTIONS = 'Interactions'
ALL_SOURCES = 'All sources'
NOT_A_NUMBER = 'n/a'
NONE = '–'
#: The budget's columns; the variance column's header carries the power of ten its numbers share.
BUDGET_COLUMNS = ('Source', 'Stated', 'Elasticity', 'Variance', 'Spread if exact (decades)')
#: The reductions the what-if row offers, as a share of the stated uncertainty.
WHAT_IF_RATIOS = (0.75, 0.5, 0.25, 0.0)
WHAT_IF_START = 0.5

NOTHING_VARIES = (
    'Every input is set to fixed under Input uncertainty, so the analysis has nothing to vary. '
    'Choose a σ or a range for at least one input.'
)
NOT_A_CONFIDENCE_INTERVAL = 'Every sample counts the same; the input-aware interval also weighs the data.'
COMPARE = 'Compare in Fit results'
EDIT_INPUTS = 'Edit in Input uncertainty'


def _minus(text: str) -> str:
    return text.replace('-', '−')


def share(value: float) -> str:
    """A Sobol' index to two decimals, or three below 0.1 so a small share keeps two figures; ``n/a`` for none."""
    if not math.isfinite(value):
        return NOT_A_NUMBER
    return _minus(format(value, '.2f' if abs(value) >= 0.1 else '.3f'))


def _pct(value: float) -> str:
    """A percentage to three significant figures: ``5 %``, ``2.33 %``."""
    return f'{float(f"{value:.3g}"):g}{THIN}%'


def _signed_pct(value: float) -> str:
    sign = '+' if value > 0 else '−' if value < 0 else ''
    return f'{sign}{_pct(abs(value))}'


def ka_name(key: str) -> str:
    """A binding constant as the glossary names it, in HTML: ``K<sub>a</sub> guest``, ``K<sub>a</sub> HG₂``."""
    return fmt_constant(key)


def _assay(result: SensitivityResult) -> AssayType | None:
    try:
        return AssayType[result.assay_type]
    except KeyError:
        return None


def source_label(assay_type: AssayType | None, key: str) -> str:
    """An error source as Sensitivity names it, in HTML: the input, the shared source's name, or the additions.

    A shared source carries the name the user typed, which is escaped.
    """
    if key == ADDITIONS:
        return ADDITIONS_LABEL
    if is_shared(key):
        return escape(source_name(key))
    if assay_type is None:
        return escape(key)
    if key == TITRANT:
        return f'{ASSAY_REGISTRY[assay_type].x_label} (titrant)'
    return input_labels(assay_type).get(key, escape(key))


def _source_spec(result: SensitivityResult, source: str) -> tuple[InputSpec, float | None]:
    """How *source*'s uncertainty was stated, and the value it is stated against (``None`` when relative)."""
    errors = result.config.errors
    if source == ADDITIONS:
        return InputSpec.sigma_pct(errors.additions.sigma_pct), None
    spec = errors.source_specs()[source]
    if spec.relative or result.baseline_fit is None:
        return spec, None
    return spec, nominal_value(source, result.baseline_fit.conditions)


def stated_pct(result: SensitivityResult, source: str) -> float:
    """*source*'s stated uncertainty as one figure in percent: a standard deviation, or half a range's width.

    A range is reduced by shrinking it about its centre, so half its width is the size that scales.
    """
    spec, nominal = _source_spec(result, source)
    if spec.kind is SpecKind.SIGMA:
        return 100.0 * _to_fraction(spec.sigma, spec.relative, nominal, source_name(source))
    lo, hi = spec_bounds(spec, nominal, source_name(source))
    return 100.0 * (hi - lo) / 2.0


def stated_text(result: SensitivityResult, source: str) -> str:
    """What was stated for *source*, in percent of the entered value however it was stated: ``σ 3 %``, ``−6 % to +4 %``."""
    spec, nominal = _source_spec(result, source)
    if spec.kind is SpecKind.SIGMA:
        each = ' each addition' if source == ADDITIONS else ''
        return f'σ {_pct(stated_pct(result, source))}{each}'
    lo, hi = spec_bounds(spec, nominal, source_name(source))
    return f'{_signed_pct(100.0 * lo)} to {_signed_pct(100.0 * hi)}'


def _reduced_text(result: SensitivityResult, source: str, ratio: float) -> str:
    """*source*'s stated uncertainty reduced to *ratio* of itself, as the what-if menu offers it."""
    if ratio == 0.0:
        return 'Exact'
    sign = 'σ ' if _source_spec(result, source)[0].kind is SpecKind.SIGMA else '±'
    return f'{sign}{_pct(ratio * stated_pct(result, source))}'


# ---------------------------------------------------------------------------
# The run's own settings
# ---------------------------------------------------------------------------


@dataclass
class AnalysisForm:
    """The settings of the next sensitivity run, as Analysis settings states them, and the rules of stating them.

    The error sources are stated once, in Input uncertainty; :meth:`problems` and
    :meth:`config` take them, with the inputs' names and entered values, from the session.
    """

    mode: SensitivityMode = SensitivityMode.SOBOL
    n_samples: int = SAMPLE_SIZES[0]
    fixed_seed: bool = False
    seed_text: str = '0'
    x_key: str | None = None
    y_key: str | None = None
    grid: int = GRIDS[0]
    x_span: float = DEFAULT_SPAN
    y_span: float = DEFAULT_SPAN
    log_axis: bool = True

    def set_inputs(self, keys: Sequence[str]) -> None:
        """Offer *keys* as the heatmap axes; an axis on an input the model does not have moves to the first two."""
        keys = list(keys)
        if self.x_key not in keys:
            self.x_key = keys[0] if keys else None
        if self.y_key not in keys:
            others = [k for k in keys if k != self.x_key]
            self.y_key = others[0] if others else None

    def seed(self) -> int | None:
        """The seed the run is fixed to, ``None`` with Fixed seed off or a seed that cannot be read."""
        if not self.fixed_seed:
            return None
        text = self.seed_text.strip().replace(',', '')
        # ASCII decimal digits only: str.isdigit() also passes superscripts, which int() refuses,
        # and int() reads digits of other scripts, which no one types as a seed.
        # More digits than MAX_SEED has are out of range, and int() refuses more than 4,300 of them.
        if not (text.isascii() and text.isdecimal()) or len(text) > len(str(MAX_SEED)):
            return None
        return int(text) if int(text) <= MAX_SEED else None

    def spans_shown(self, errors: ErrorModel) -> tuple[bool, bool]:
        """Whether the X and the Y axis show a span menu: an axis stated as a σ does, one stated as a range not."""
        return tuple(
            (spec := errors.specs.get(key)) is not None and spec.kind is SpecKind.SIGMA
            for key in (self.x_key, self.y_key)
        )

    def problems(self, errors: ErrorModel, labels: Mapping[str, str], nominals: Mapping[str, float]) -> list[str]:
        """Why a run cannot be made with these settings and *errors*, one sentence each; empty when it can.

        *labels* names each input as Input uncertainty does; *nominals* holds the entered
        values an axis stated in the input's own unit is read against.
        """
        problems = []
        if self.fixed_seed and self.seed() is None:
            problems.append(f'The fixed seed must be a whole number from 0 to {MAX_SEED:,}.')
        if self.mode is not SensitivityMode.HEATMAP:
            return problems
        if self.x_key is None or self.y_key is None:
            return [*problems, 'A heatmap needs two inputs to sweep, and this model has fewer.']
        if self.x_key == self.y_key:
            return [*problems, f'{labels[self.x_key]} is both heatmap axes: choose another input for one of them.']
        for key, span in ((self.x_key, self.x_span), (self.y_key, self.y_span)):
            problem = self._axis_problem(key, span, errors, labels[key], nominals.get(key))
            if problem:
                problems.append(problem)
        return problems

    @staticmethod
    def _axis_problem(key: str, span: float, errors: ErrorModel, name: str, nominal: float | None) -> str | None:
        """Why input *key* cannot be a heatmap axis swept at *span* σ; ``None`` when it can.

        An axis runs over the whole range, or from −span·σ to +span·σ, both ends
        included, so an end at −100 % would fit the model with the input at zero.
        """
        spec = errors.specs.get(key)
        if spec is None or not spec.varies:
            if any(key in source.inputs for source in errors.shared):
                return (
                    f'{name} varies only through a shared source, which moves several inputs together and is no '
                    'heatmap axis: set a σ or a range of its own for it under Input uncertainty.'
                )
            return (
                f'{name} is a heatmap axis, so it cannot be fixed: set a σ or a range for it under Input uncertainty.'
            )
        if not spec.relative and (nominal is None or not nominal > 0):
            # An uncertainty in the input's own unit has no entered value to be read against;
            # Input uncertainty says so for the input, and that stops the run.
            return None
        if not axis_reaches_zero(spec, nominal, name, span):
            return None
        if spec.kind is SpecKind.SIGMA:
            k = f'{span:g}'
            if spec.relative:
                limit = _pct(100.0 / span)
            else:
                limit = {1.0: 'its set value', 2.0: 'half its set value'}.get(span, f'1/{k} of its set value')
            return (
                f'{name} as a heatmap axis would reach zero or below, since the axis runs from −{k}σ to +{k}σ: '
                f'set σ below {limit}, choose a narrower span, or use a range.'
            )
        return f'{name} as a heatmap axis would reach zero: set “from” above {"−100 %" if spec.relative else "0"}.'

    def config(self, errors: ErrorModel, labels: Mapping[str, str], nominals: Mapping[str, float]) -> SensitivityConfig:
        """The configuration of a run of these settings over *errors*.

        Sensitivity indices take every source. A heatmap is a grid over two inputs and
        takes those two inputs' own uncertainties and nothing else.

        Raises
        ------
        ValueError
            When :meth:`problems` finds a reason the run cannot be made.
        """
        problems = self.problems(errors, labels, nominals)
        if problems:
            raise ValueError(' '.join(problems))
        heatmap = self.mode is SensitivityMode.HEATMAP
        used = ErrorModel(specs={key: errors.specs[key] for key in (self.x_key, self.y_key)}) if heatmap else errors
        return SensitivityConfig(
            mode=self.mode,
            n_samples=self.n_samples,
            errors=used,
            seed=self.seed(),
            x_key=self.x_key,
            y_key=self.y_key,
            n_steps=self.grid,
            x_span=self.x_span,
            y_span=self.y_span,
        )

    def summary(self) -> str:
        """The settings in a few words: ``Sobol’ · N = 1024``, ``Heatmap · 21 × 21``."""
        if self.mode is SensitivityMode.HEATMAP:
            return f'Heatmap · {self.grid}{THIN}×{THIN}{self.grid}'
        return f'Sobol’ · N = {self.n_samples}'


def config_summary(config: SensitivityConfig) -> str:
    """What a run was made with in a few words, as :meth:`AnalysisForm.summary` writes the settings."""
    if config.mode is SensitivityMode.HEATMAP:
        return f'Heatmap · {config.n_steps}{THIN}×{THIN}{config.n_steps}'
    return f'Sobol’ · N = {config.n_samples}'


def sample_size_note(n: int, n_sources: int, n_inputs: int) -> str:
    """What sample size *n* costs, with *n_sources* sources varying over *n_inputs* inputs.

    The fits are counted as the cost dialog and the status bar count them: the perturbed
    fits, the elasticity refits and the fit at the inputs as entered. With no source
    varying the run is refused, so no fit count is quoted.
    """
    if not n_sources:
        return f'2 × N = {2 * n:,} samples. Each step up doubles the time.'
    fits = n * (n_sources + 2) + 2 * n_inputs + 1
    return f'2 × N = {2 * n:,} samples, {fits:,} fits in all. Each step up doubles the time.'


def grid_label(n: int) -> str:
    """A grid as its menu offers it, its fits counted as This run counts them: ``21 × 21 · 442 fits``.

    One fit per cell, and the fit at the inputs as entered.
    """
    return f'{n}{THIN}×{THIN}{n} · {n * n + 1:,} fits'


def span_label(span: float) -> str:
    return f'±{span:g}σ'


def badge(result: SensitivityResult | None, form: AnalysisForm) -> str:
    """The summary beside the title: what the run on show was made with, else what the next one will be."""
    return config_summary(result.config) if result is not None else form.summary()


# ---------------------------------------------------------------------------
# The canvas before and around a result
# ---------------------------------------------------------------------------


def empty_sentence(has_data: bool, varies: bool, shortcut: str) -> str:
    """What the canvas says before any analysis, with *shortcut* the platform's text for Run analysis.

    It names only the steps still to take: loading data where none is loaded, stating an
    uncertainty where no source *varies*.
    """
    steps = [] if has_data else ['add your titration files with Load data']
    if not varies:
        steps.append('state how uncertain each input is under Input uncertainty')
    steps.append(f'choose Run analysis ({shortcut})')
    first, *rest = steps
    text = ', '.join([first, *rest[:-1]]) + (f', then {rest[-1]}' if rest else '')
    return f'No analysis yet. {text[0].upper()}{text[1:]}.'


RUNNING = 'The analysis is running. Its results appear here when it finishes; the status bar counts its fits.'
NO_KA = 'This model has no association constant, so there is nothing for a sensitivity analysis to follow.'


def callouts(
    result: SensitivityResult | None,
    fit: FitResult | None,
    note: str | None,
    *,
    running: bool = False,
    error: str | None = None,
    nothing_varies: bool = False,
) -> list[R.CalloutSpec]:
    """The callouts above the results of *result*, beside *fit*, the fit the session reports.

    *note* hides the run (:meth:`~gui.session_model.SessionModel.mismatch_note`) and is
    then the only thing said of it. *error* says why the last run could not be completed,
    and *nothing_varies* that no source is stated, which stops a run before it starts —
    said only while no run goes (*running*), whose state shows where run state does.
    """
    out = []
    if error:
        out.append(R.CalloutSpec('warning', 'Analysis failed', ' '.join(error.split())))
    if result is None:
        if nothing_varies and not running:
            out.append(R.CalloutSpec('neutral', 'Nothing to vary', NOTHING_VARIES, EDIT_INPUTS))
        return out
    if note is not None:
        return [*out, R.CalloutSpec('neutral', 'Results hidden', note)]
    names = ', '.join(plain_label(ka_name(k)) for k in result.ka_keys)
    conflict = False
    diagnostics = None if fit is None else fit.diagnostics
    if diagnostics is not None:
        from core.pipeline.diagnostics import rejections

        conflict = 'conflict' in rejections(diagnostics.conditional_misfit, diagnostics.misfit, diagnostics.conflict)
    if conflict:
        drawn = 'grid centres' if result.mode is SensitivityMode.HEATMAP else 'samples centre'
        out.append(
            R.CalloutSpec(
                'warning',
                'Inputs conflict',
                'Together, the inputs moved further from their entered values than you stated. The '
                f'{drawn} on the inputs as entered, so they show how far the stated inputs move {names}, '
                'not where it lies.',
                R.REVIEW,
            )
        )
    elif result.mode is SensitivityMode.SOBOL:
        out.append(R.CalloutSpec('neutral', 'Not a confidence interval', NOT_A_CONFIDENCE_INTERVAL, COMPARE))
    stopped = stopped_sentence(result)
    if stopped:
        out.append(R.CalloutSpec('neutral', 'Analysis stopped', stopped))
    return out


def stopped_sentence(result: SensitivityResult) -> str:
    """What a stopped run rests on; ``''`` for a run that finished."""
    if not result.stopped:
        return ''
    if result.mode is SensitivityMode.HEATMAP:
        return (
            f'The analysis was stopped after {result.n_total:,} of {result.config.n_steps**2:,} cells: the cells it '
            'did not reach are left empty.'
        )
    kept = result.n_blocks_finished
    if not kept:
        return (
            f'The analysis was stopped before any of its {_SOBOL_BLOCKS} sample blocks had finished, so there is '
            'nothing to rank the sources by. Run it again and let it finish, or choose a smaller sample size.'
        )
    groups = result.config.n_samples // _SOBOL_BLOCKS * kept
    return (
        f'The analysis was stopped after {kept} of {_SOBOL_BLOCKS} sample blocks had finished: everything here rests '
        f'on the {groups:,} sample groups of {"that block" if kept == 1 else "those blocks"}.'
    )


def withheld_note(result: SensitivityResult, ka_key: str) -> str | None:
    """Why *ka_key*'s shares, spread and elasticities are not given, in plain words; ``None`` when they are."""
    reason = (result.withheld or {}).get(ka_key, '')
    name = plain_label(ka_name(ka_key))
    withheld = f'so no share, spread or elasticity is given for {name}. Ka confidence shows what the data say of it.'
    if reason == 'baseline_on_bound':
        return (
            f'The data do not limit {name} at the inputs as entered: the fit ran to the edge of its bounds, {withheld}'
        )
    if reason == 'open_interval':
        fit = result.baseline_fit
        interval = None if fit is None else (fit.intervals or {}).get(ka_key)
        side = 'upper or lower'
        if interval is not None and interval.open_low != interval.open_high:
            side = 'lower' if interval.open_low else 'upper'
        return (
            f'The data give {name} no {side} limit at the inputs as entered, so its refits land wherever its flat '
            f'profile lets them and describe the bounds of the search rather than the inputs, {withheld}'
        )
    if reason == 'homogeneity':
        if not math.isfinite((result.homogeneity or {}).get(ka_key, math.nan)):
            return (
                f'One of the refits that check how {name} follows the inputs gave no fit. Whether its refits '
                f'respond to the inputs smoothly cannot be told, {withheld}'
            )
        return (
            f'The refits of {name} do not follow the inputs smoothly: multiplying every concentration by a factor, '
            f'and dividing every entered binding constant by it, should divide {name} by exactly that factor, '
            f'and here they do not. They jump between different fits, {withheld}'
        )
    return None


def withheld_title(result: SensitivityResult, ka_key: str) -> str:
    """The title of a withheld constant's callout: what is not given, in a few words."""
    reason = (result.withheld or {}).get(ka_key, '')
    return f'No shares for {plain_label(ka_name(ka_key))}' if reason else ''


def _design_fits(result: SensitivityResult) -> int:
    """Perturbed fits the analysis rests on: every matrix of the Saltelli design in the finished blocks, or every cell."""
    if result.mode is SensitivityMode.HEATMAP:
        return result.n_total if result.stopped else result.config.n_steps**2
    blocks = result.n_blocks_finished if result.stopped else _SOBOL_BLOCKS
    return result.config.n_samples * (len(result.sources) + 2) * blocks // _SOBOL_BLOCKS


def on_bound_note(result: SensitivityResult, ka_key: str) -> str | None:
    """What the fits that ran to the edge of the Kₐ box mean for *ka_key*; ``None`` when none did."""
    n = int((result.n_on_bound or {}).get(ka_key, 0))
    total = _design_fits(result)
    if not n or not total:
        return None
    name = plain_label(ka_name(ka_key))
    return (
        f'In {n:,} of {total:,} {"fit" if total == 1 else "fits"} ({_pct(100.0 * n / total)}) {name} ran to the edge '
        f'of its bounds; {"that fit jumps" if n == 1 else "those fits jump"} by many decades and '
        f'{"inflates" if n == 1 else "inflate"} the spread and the budget. The uncertainties stated for the inputs '
        f'are wide enough to leave {name} unidentifiable over part of their range.'
    )


# ---------------------------------------------------------------------------
# The spread of one binding constant and its samples
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Spread:
    """The spread the stated inputs give one binding constant (the hero of its block).

    *factor* (``×/÷ 1.20``) and *decades* (``1 SD · 0.078 decades``) are empty where no
    spread is given, and *missing* then says why; *centre* is the value it is read around,
    the fit at the inputs as entered; *tooltip* the sampling interval of the spread.
    """

    title: str
    factor: str
    decades: str
    centre: str
    tooltip: str = ''
    missing: str = ''


def spread(result: SensitivityResult, ka_key: str) -> Spread:
    """The spread of *ka_key* from :attr:`~core.pipeline.budget.Budget.sd`, around the fit at the inputs as entered."""
    centre = f'{spaced(fmt_value(result.baseline_ka[ka_key]))} M⁻¹'
    title = f'Spread of {ka_name(ka_key)} from the stated inputs'
    budget = (result.budget or {}).get(ka_key)
    if (result.withheld or {}).get(ka_key):
        return Spread(title, '', '', centre, missing='Not given: the callout below says why.')
    if budget is None or not math.isfinite(budget.variance):
        return Spread(title, '', '', centre, missing='Too few fits finished to work the spread out.')
    sd = budget.sd
    ends = [math.sqrt(max(end, 0.0)) for end in budget.variance_ci]
    tooltip = ''
    if all(math.isfinite(end) for end in ends):
        tooltip = (
            f'95 % sampling interval of the spread: {ends[0]:.3f} – {ends[1]:.3f} decades. It covers the sampling '
            'error of the analysis, not errors in what you stated.'
        )
    return Spread(title, f'×/÷\u00a0{10.0**sd:.2f}', f'1 SD · {sd:.3f} decades', centre, tooltip)


@dataclass(frozen=True)
class Marker:
    """One reading of the fit marked on the sample histogram.

    *kind* is ``aware`` (accent line and band) or ``entered`` (dashed line, interval
    bracket); *x* the estimate in axis coordinates (``None`` for an estimate on an end of
    its search box), *span* the interval's ends, an open end at the axis' edge.
    """

    kind: str
    label: str
    x: float | None
    span: tuple[float, float] | None


@dataclass(frozen=True)
class Histogram:
    """The samples of one binding constant on its Kₐ axis: bars, the middle 90 % solid, the two readings marked.

    Every coordinate is on the axis as drawn: log₁₀ Kₐ, or Kₐ itself on a linear axis.
    """

    edges: np.ndarray
    counts: np.ndarray
    inside: np.ndarray
    x_range: tuple[float, float]
    ticks: list[tuple[float, str]]
    unit: str
    markers: list[Marker]
    fold: str
    log: bool = True


def _usable(result: SensitivityResult, ka_key: str) -> np.ndarray:
    """The samples the budget was built from: the rows every estimator used, with a finite Kₐ above 0."""
    ka = np.asarray(result.sample_ka[ka_key], dtype=float)
    usable = (result.sample_usable or {}).get(ka_key)
    keep = np.isfinite(ka) & (ka > 0)
    if usable is not None:
        keep &= np.asarray(usable, dtype=bool)
    return ka[keep]


def _linear_ticks(lo: float, hi: float) -> list[float]:
    """Round values from *lo* to *hi*, 1, 2 or 5 times a power of ten apart, three to seven of them."""
    span = hi - lo
    if not span > 0:
        return [lo]
    for step in (
        m * 10.0**e
        for e in range(math.floor(math.log10(span)) - 2, math.floor(math.log10(span)) + 2)
        for m in (1, 2, 5)
    ):
        values = [float(f'{i * step:.6g}') for i in range(math.ceil(lo / step), math.floor(hi / step) + 1)]
        if len(values) <= 7:
            return values
    return [lo, hi]


def ka_axis(values: Sequence[float], log: bool) -> tuple[tuple[float, float], list[tuple[float, str]], str, int]:
    """The Kₐ axis that holds *values* (Kₐ in M⁻¹): range and ticks in axis coordinates, the unit after the last tick,
    and the power of ten the tick labels share."""
    lo, hi = min(values), max(values)
    if log:
        a, b = math.log10(lo), math.log10(hi)
        pad = max(0.04 * (b - a), 0.02)
        a, b = a - pad, b + pad
        if b - a < 0.1:
            a, b = (a + b) / 2 - 0.05, (a + b) / 2 + 0.05
        ticks = R.nice_ticks(10.0**a, 10.0**b)
        e = R.shared_power(ticks)
        labels = [(math.log10(v), R.tick_label(v, e)) for v in ticks]
        return (a, b), labels, _unit_after(e), e or 0
    pad = max(0.04 * (hi - lo), 0.01 * hi)
    a, b = max(lo - pad, 0.0), hi + pad
    ticks = _linear_ticks(a, b)
    e = math.floor(math.log10(max(abs(v) for v in ticks if v) or 1.0)) if any(ticks) else 0
    return (a, b), [(v, f'{v / 10.0**e:g}') for v in ticks], _unit_after(e), e


def _unit_after(e: int | None) -> str:
    return f'×{THIN}10{superscript(e)} M⁻¹' if e else 'M⁻¹'


def _row(fit: FitResult, key: str) -> ParameterSummary | None:
    return next((s for s in summarize_parameters(fit) if s.key == key and not s.is_log), None)


def _reading_marker(kind: str, name: str, row, conditional: bool, x_of, x_range, e: int) -> Marker:
    """One reading of *row* (a :class:`ParameterSummary`) on the axis: its estimate and interval."""
    if conditional:
        estimate, at_bound = row.conditional_estimate, row.conditional_at_bound
        interval, open_ = row.conditional_interval, row.conditional_open
    else:
        estimate, at_bound = row.estimate, row.estimate_at_bound
        interval, open_ = row.interval, row.interval_open

    def number(v: float) -> str:
        return f'{v / 10.0**e:.2f}' if e else spaced(fmt_value(v))

    label = name if at_bound else f'{name} {number(estimate)}'
    span = None
    if interval is not None:
        low = NO_LOWER if open_[0] else number(interval[0])
        high = NO_UPPER if open_[1] else number(interval[1])
        label = f'{label}  [{low}, {high}]'
        span = (
            x_range[0] if open_[0] else x_of(interval[0]),
            x_range[1] if open_[1] else x_of(interval[1]),
        )
    return Marker(kind, label, None if at_bound else x_of(estimate), span)


def _readings(result: SensitivityResult, fit: FitResult | None, ka_key: str):
    """The rows of the readings marked: Input-aware from *fit* where it reports one, Inputs as entered from the run."""
    rows = []
    if fit is not None and not reports_conditional(fit) and fit.assay_type == result.assay_type:
        row = _row(fit, ka_key)
        if row is not None and row.interval is not None:
            rows.append(('aware', R.INPUT_AWARE, row, False))
    if result.baseline_fit is not None:
        row = _row(result.baseline_fit, ka_key)
        if row is not None and row.conditional_interval is not None:
            rows.append(('entered', R.AS_ENTERED, row, True))
        elif row is not None:
            rows.append(('entered', R.AS_ENTERED, row, False))
    return rows


def histogram(result: SensitivityResult, fit: FitResult | None, ka_key: str, log: bool = True) -> Histogram | None:
    """The samples of *ka_key* binned on its axis, with the readings of *fit* and of the run marked; ``None`` without samples.

    A constant whose numbers are withheld keeps its samples on show with no figure read
    off them: no fold, and no middle 90 % marked off.
    """
    if result.sample_ka is None or ka_key not in result.sample_ka:
        return None
    ka = _usable(result, ka_key)
    if not ka.size:
        return None
    readings = _readings(result, fit, ka_key)
    reach = [float(ka.min()), float(ka.max())]
    for _kind, _name, row, conditional in readings:
        estimate = row.conditional_estimate if conditional else row.estimate
        at_bound = row.conditional_at_bound if conditional else row.estimate_at_bound
        interval = row.conditional_interval if conditional else row.interval
        open_ = row.conditional_open if conditional else row.interval_open
        if not at_bound:
            reach.append(estimate)
        if interval is not None:
            reach += [v for v, is_open in zip(interval, open_) if not is_open and v > 0]
    x_range, ticks, unit, e = ka_axis(reach, log)
    x_of = math.log10 if log else float
    positions = np.log10(ka) if log else ka
    edges = np.linspace(*x_range, 53)
    counts, _ = np.histogram(positions, bins=edges)
    markers = [_reading_marker(kind, name, row, cond, x_of, x_range, e) for kind, name, row, cond in readings]
    if (result.withheld or {}).get(ka_key):
        return Histogram(edges, counts, np.ones(counts.size, dtype=bool), x_range, ticks, unit, markers, '', log)
    p5, p95 = np.percentile(ka, [5, 95])
    centres = (edges[:-1] + edges[1:]) / 2
    inside = (centres >= x_of(p5)) & (centres <= x_of(p95))
    fold = f'Middle 90{THIN}% of samples span a {p95 / p5:.2f}-fold range'
    return Histogram(edges, counts, inside, x_range, ticks, unit, markers, fold, log)


# ---------------------------------------------------------------------------
# Share of the variance, by source
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IndexRow:
    """One source of the index chart: S₁ and S_T with their 95 % intervals, and the two values as written."""

    key: str
    name: str
    s1: float
    st: float
    s1_ci: tuple[float, float]
    st_ci: tuple[float, float]


@dataclass(frozen=True)
class IndexChart:
    """The Sobol' indices of one binding constant, the sources largest first, on an axis from *lo* to *hi*.

    *notes* are the sentences under the chart: an index drawn off the axis, an S_T
    below its S₁, and the sample groups the indices leave out.
    """

    rows: list[IndexRow]
    lo: float
    hi: float
    ticks: list[float]
    notes: list[str] = field(default_factory=list)


#: The widest index axis drawn; an index or a whisker past it is cut at the edge and marked.
INDEX_LIMITS = (-0.5, 1.5)


def ordered_sources(result: SensitivityResult, ka_key: str) -> list[str]:
    """The sources of *ka_key*, ranked by their first-order index, largest first; one with none last."""
    s1 = (result.sobol_s1 or {}).get(ka_key, {})

    def rank(key: str) -> float:
        value = s1.get(key, math.nan)
        return -value if math.isfinite(value) else math.inf

    return sorted(result.sources or tuple(s1), key=rank)


def index_chart(result: SensitivityResult, ka_key: str) -> IndexChart:
    """The index chart of *ka_key* from the run's own indices and intervals."""
    assay = _assay(result)
    s1 = (result.sobol_s1 or {}).get(ka_key, {})
    st = (result.sobol_st or {}).get(ka_key, {})
    s1_ci = (result.sobol_s1_ci or {}).get(ka_key, {})
    st_ci = (result.sobol_st_ci or {}).get(ka_key, {})
    nan2 = (math.nan, math.nan)
    rows = [
        IndexRow(
            key,
            source_label(assay, key),
            s1.get(key, math.nan),
            st.get(key, math.nan),
            tuple(s1_ci.get(key, nan2)),
            tuple(st_ci.get(key, nan2)),
        )
        for key in ordered_sources(result, ka_key)
    ]
    values = [v for r in rows for v in (r.s1, r.st, *r.s1_ci, *r.st_ci) if math.isfinite(v)]
    lo = max(math.floor(min(values, default=0.0) * 10) / 10, INDEX_LIMITS[0]) if min(values, default=0.0) < 0 else 0.0
    hi = min(max(math.ceil(max(values, default=0.1) * 10 - 1e-9) / 10, 0.1), INDEX_LIMITS[1])
    step = 0.1 if hi - lo <= 0.6 else 0.2 if hi - lo <= 1.2 else 0.5
    ticks = [round(v, 6) for v in np.arange(math.ceil(lo / step) * step, hi + 1e-9, step)]
    notes = []
    if any(v < INDEX_LIMITS[0] or v > INDEX_LIMITS[1] for v in values):
        lo_, hi_ = INDEX_LIMITS
        notes.append(
            f'An arrow marks an index or whisker beyond {_minus(f"{lo_:g}")} to {hi_:g}: too few samples to pin it '
            'down. More samples bring it back in range.'
        )
    below = [r for r in rows if math.isfinite(r.s1) and math.isfinite(r.st) and r.st < r.s1]
    if below:
        names = ', '.join(r.name for r in below)
        apart = any(math.isfinite(r.st_ci[1]) and math.isfinite(r.s1_ci[0]) and r.st_ci[1] < r.s1_ci[0] for r in below)
        said = (
            'The gap is wider than the whiskers span: take these two indices as unreliable and run again with more '
            'samples.'
            if apart
            else 'The two agree within their whiskers, so it acts almost entirely on its own.'
        )
        notes.append(
            f'{names}: S<sub>T</sub> comes out just below S<sub>1</sub>, which a true total never does. {said}'
        )
    if not values:
        notes.append(_no_index_reason(result, ka_key))
    left_out = (result.sobol_rows_left_out or {}).get(ka_key, 0)
    dropped = _dropped_groups(result)
    groups = result.config.n_samples - dropped
    if values and left_out - dropped > 0 and groups:
        n = left_out - dropped
        notes.append(
            f'The indices leave out {n:,} of the {groups:,} sample groups: at least one fit in '
            f'{"that group" if n == 1 else "each of those groups"} could not be made.'
        )
    return IndexChart(rows, lo, hi, ticks, notes)


def _dropped_groups(result: SensitivityResult) -> int:
    """Sample groups in the blocks a stopped run left unfinished, which no count of the run includes."""
    if not result.stopped:
        return 0
    return result.config.n_samples // _SOBOL_BLOCKS * (_SOBOL_BLOCKS - result.n_blocks_finished)


def _fitted_samples(result: SensitivityResult) -> int:
    """Samples with a fit of every binding constant; a sample of an unfinished block has none."""
    if not result.sample_ka:
        return 0
    ka = np.vstack([np.asarray(v, dtype=float) for v in result.sample_ka.values()])
    return int(np.all(np.isfinite(ka), axis=0).sum())


def _no_index_reason(result: SensitivityResult, ka_key: str) -> str:
    """Why the chart has no bars, and what to do about it.

    A group needs every one of its fits, so most samples can have a fit while no group
    has all of them; the two counts are given together so neither reads as contradicting
    the samples counted under This run.
    """
    if result.stopped and not result.n_blocks_finished:
        return 'No index: the analysis was stopped before any sample block had finished.'
    dropped = _dropped_groups(result)
    groups = result.config.n_samples - dropped
    left_out = (result.sobol_rows_left_out or {}).get(ka_key, result.config.n_samples) - dropped
    finished = max(groups - left_out, 0)
    fitted = _fitted_samples(result)
    has = 'has all of its fits' if finished == 1 else 'have all of their fits'
    counts = f'{finished:,} of the {groups:,} sample groups {has}'
    if fitted:
        counts += f', although {fitted:,} sample{" was" if fitted == 1 else "s were"} fitted'
    return (
        f'No index: {counts}, so there is nothing to rank the sources by. Narrow the uncertainties under Input '
        'uncertainty, or widen the bounds under Binding model, and run it again.'
    )


# ---------------------------------------------------------------------------
# The variance budget and the what-if row
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Cell:
    """One cell of the budget: its number, its 95 % sampling interval (quieter) and whether it reads as none."""

    value: str
    interval: str = ''
    quiet: bool = False


@dataclass(frozen=True)
class BudgetTable:
    """The variance budget of one binding constant (:class:`~core.pipeline.budget.Budget`).

    One row per source in the order of the index chart, then *Interactions*; *total* is
    the whole variance. *headers* are the columns' titles, the variance column's with
    the power of ten its numbers share.
    """

    caption: str
    headers: tuple[str, ...]
    rows: list[list[Cell]]
    total: list[Cell]
    notes: list[str] = field(default_factory=list)


def _decimals_apart(value: float, ends: Sequence[float], base: int, most: int = 2) -> int:
    """The fewest decimals from *base* that tell *value* and its interval *ends* apart, up to *most* more.

    ``0.050 [0.050, 0.050]`` reads as no uncertainty at all; one or two more figures show
    what the interval is.
    """
    numbers = [v for v in (value, *ends) if math.isfinite(v)]
    pairs = [(a, b) for i, a in enumerate(numbers) for b in numbers[i + 1 :] if a != b]
    for d in range(base, base + most):
        if all(f'{a:.{d}f}' != f'{b:.{d}f}' for a, b in pairs):
            return d
    return base + most


def _number(value: float, decimals: int) -> str:
    return _minus(f'{value:.{decimals}f}') if math.isfinite(value) else NOT_A_NUMBER


def _with_interval(value: float, interval: Sequence[float], base: int, scale: float = 1.0) -> Cell:
    value, ends = value / scale, [end / scale for end in interval]
    d = _decimals_apart(value, ends, base)
    text = '' if not all(math.isfinite(e) for e in ends) else f'[{_number(ends[0], d)}, {_number(ends[1], d)}]'
    return Cell(_number(value, d), text)


def _figures(value: float, base: int) -> int:
    """Decimals that give *value* at least two significant figures, *base* at least."""
    if not math.isfinite(value) or value == 0:
        return base
    return min(max(base, 1 - math.floor(math.log10(abs(value)))), base + 4)


def budget_table(result: SensitivityResult, ka_key: str) -> BudgetTable | None:
    """The budget of *ka_key* as Sensitivity tables it; ``None`` for a run with none, or one withheld."""
    budget = (result.budget or {}).get(ka_key)
    if budget is None or (result.withheld or {}).get(ka_key):
        return None
    assay = _assay(result)
    by_source = {row.source: row for row in budget.rows}
    e = math.floor(math.log10(budget.variance)) if math.isfinite(budget.variance) and budget.variance > 0 else 0
    scale = 10.0**e
    power = f'×10{superscript(e)} ' if e else ''
    headers = (*BUDGET_COLUMNS[:3], f'Variance ({power}decades²)', BUDGET_COLUMNS[4])
    rows = []
    for key in ordered_sources(result, ka_key):
        row = by_source.get(key)
        if row is None:
            continue
        known = row.elasticity is not None and math.isfinite(row.elasticity)
        elasticity = Cell(_minus(f'{row.elasticity:+.2f}')) if known else Cell(NONE, quiet=True)
        spread_ci = (max(row.sd_if_exact_ci[0], 0.0), row.sd_if_exact_ci[1])
        rows.append(
            [
                Cell(source_label(assay, key)),
                Cell(stated_text(result, key), quiet=True),
                elasticity,
                _with_interval(row.variance, row.variance_ci, 2, scale),
                _with_interval(row.sd_if_exact, spread_ci, 3),
            ]
        )
    interactions = budget.interactions * budget.variance / scale
    rows.append(
        [
            Cell(INTERACTIONS),
            Cell(NONE, quiet=True),
            Cell(NONE, quiet=True),
            Cell(_number(interactions, _figures(interactions, 2))),
            Cell(NONE, quiet=True),
        ]
    )
    total = [
        Cell(ALL_SOURCES),
        Cell(NONE, quiet=True),
        Cell(NONE, quiet=True),
        _with_interval(budget.variance, budget.variance_ci, 2, scale),
        Cell(NONE, quiet=True),
    ]
    caption = f'log₁₀ {plain_label(ka_name(ka_key))} · [95{THIN}% sampling interval]'
    notes = [ADDITIONS_NOTE] if ADDITIONS in by_source else []
    return BudgetTable(caption, headers, rows, total, notes)


def what_if_sources(result: SensitivityResult, ka_key: str) -> list[str]:
    """The sources a what-if can reduce, largest share first: a single source, never the additions."""
    budget = (result.budget or {}).get(ka_key)
    if budget is None:
        return []
    listed = {row.source for row in budget.rows}
    return [key for key in ordered_sources(result, ka_key) if key in listed and key != ADDITIONS]


def what_if_targets(result: SensitivityResult, source: str) -> list[tuple[float, str]]:
    """The reductions offered for *source*, each ``(ratio of the stated uncertainty, as the menu writes it)``."""
    return [(ratio, _reduced_text(result, source, ratio)) for ratio in WHAT_IF_RATIOS]


@dataclass(frozen=True)
class WhatIfAnswer:
    """What reducing one source would buy: ``{lead} {before} to {after}`` beside the menus, *detail* under them (HTML).

    *after* is empty where too few fits finished to say, and *detail* then says so.
    """

    lead: str
    before: str
    after: str
    detail: str


def what_if_answer(result: SensitivityResult, ka_key: str, source: str, ratio: float) -> WhatIfAnswer:
    """The spread of *ka_key* with *source* reduced to *ratio* of what was stated (:func:`~core.pipeline.budget.what_if`).

    The spread after is the one re-weighted from the samples wherever the run gives one,
    with the first-order formula beside it as the cross-check; otherwise the formula is
    the answer and the line says why.
    """
    assay = _assay(result)
    name = ka_name(ka_key)
    label = source_label(assay, source)
    before = result.budget[ka_key].sd
    answer = what_if(result, ka_key, source, ratio)
    if not (math.isfinite(before) and math.isfinite(answer.sd)):
        return WhatIfAnswer('', '', '', f'Too few fits finished to say what a smaller uncertainty on {label} would do.')
    after = answer.sd_reweighted if answer.sd_reweighted is not None else answer.sd
    verb = 'shrinks' if after < before else 'goes'
    lead = f'and the spread of {name} {verb} from'
    largest = source_label(assay, answer.largest_after)
    head = f'{before:.3f} → {after:.3f} decades; {largest} would then be the largest item.'
    if answer.sd_reweighted is not None:
        tail = (
            f'Read from the samples re-weighted to the narrower uncertainty ({answer.effective_samples:,.0f} '
            f'effective samples); the first-order formula gives {answer.sd:.3f}.'
        )
    elif answer.effective_samples is None:
        tail = 'From the first-order formula: with the source exact there is no sample left to re-weight.'
    else:
        tail = 'From the first-order formula: too few samples carry weight at this reduction to read it from them.'
    return WhatIfAnswer(lead, f'×/÷\u00a0{10.0**before:.2f}', f'×/÷\u00a0{10.0**after:.2f}', f'{head} {tail}')


# ---------------------------------------------------------------------------
# One binding constant's block
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class KaBlock:
    """Everything one binding constant shows of a Sobol' run, or the callouts that stand in place of it."""

    key: str
    name: str
    spread: Spread
    histogram: Histogram | None
    callouts: list[R.CalloutSpec]
    chart: IndexChart | None
    budget: BudgetTable | None
    what_if: list[str]


def ka_blocks(result: SensitivityResult, fit: FitResult | None, log: bool = True) -> list[KaBlock]:
    """One block per binding constant of a Sobol' run; a constant whose numbers are withheld keeps its samples."""
    blocks = []
    for key in result.ka_keys:
        notes = []
        withheld = withheld_note(result, key)
        if withheld:
            notes.append(R.CalloutSpec('warning', withheld_title(result, key), withheld))
        else:
            bound = on_bound_note(result, key)
            if bound:
                notes.append(R.CalloutSpec('warning', 'Fits on the Kₐ bounds', bound))
        blocks.append(
            KaBlock(
                key,
                ka_name(key),
                spread(result, key),
                histogram(result, fit, key, log),
                notes,
                None if withheld else index_chart(result, key),
                budget_table(result, key),
                [] if withheld else what_if_sources(result, key),
            )
        )
    return blocks


def figure_caption(result: SensitivityResult, block: KaBlock) -> str:
    """The line under a constant's name in a saved figure: its spread, the value it is centred on, the run.

    A figure carries no callout, so a spread that is not given says so in words that
    stand without one; :func:`figure_notes` follows with why.
    """
    spread = block.spread
    run = f'{config_summary(result.config)}, seed {result.seed_used}'
    if spread.factor:
        head = f'Spread from the stated inputs {spread.factor} ({spread.decades})'
    elif (result.withheld or {}).get(block.key):
        head = 'No spread from the stated inputs is given (see the note below)'
    else:
        head = spread.missing.rstrip('.')
    return f'{head}, centred on {spread.centre} · {run}'


def figure_notes(block: KaBlock) -> list[str]:
    """What qualifies a constant's numbers in a saved figure (HTML): its callouts, then the notes under its chart."""
    notes = [f'{escape(spec.title)}. {escape(spec.body)}' for spec in block.callouts]
    return notes + ([] if block.chart is None else list(block.chart.notes))


# ---------------------------------------------------------------------------
# The facts of the run
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stat:
    """One fact of the run in the side panel: its name, value and a quieter note."""

    name: str
    value: str
    note: str = ''


def _duration(seconds: float) -> str:
    if seconds < 60:
        return f'{seconds:.0f} s'
    minutes, rest = divmod(round(seconds), 60)
    return f'{minutes} min {rest:02d} s' if minutes < 60 else f'{minutes // 60} h {minutes % 60:02d} min'


def this_run(result: SensitivityResult, seconds: float | None = None, workers: int | None = None) -> list[Stat]:
    """The facts of *result*: samples and fits made of those planned, R² of the samples, how long it took.

    Fits are counted as the status bar counts them, the fit at the inputs as entered
    included. A stopped Sobol' run keeps whole sample blocks, so its samples are counted
    in those blocks: a sample of a block left unfinished is no failed fit.
    """
    stats = []
    if result.mode is SensitivityMode.SOBOL:
        total = 2 * (result.config.n_samples - _dropped_groups(result))
        if total:
            note = '2 × N' if not result.stopped else 'in the sample blocks that finished'
            stats.append(Stat('Samples fitted', f'{_fitted_samples(result):,} of {total:,}', note))
        if result.stopped:
            # The count holds the refits and the fits of the block the stop cut short as well.
            blocks = (
                f'every fit made before the stop; {result.n_blocks_finished} of {_SOBOL_BLOCKS} sample blocks finished'
            )
        else:
            blocks = f'{_SOBOL_BLOCKS} of {_SOBOL_BLOCKS} sample blocks'
        stats.append(Stat('Fits', f'{result.n_success + 1:,}', blocks))
        r2 = None if result.sample_r2 is None else np.asarray(result.sample_r2, dtype=float)
    else:
        n = result.config.n_steps
        stats.append(Stat('Grid', f'{n}{THIN}×{THIN}{n}', f'{n * n:,} cells'))
        unfitted = result.n_total - result.n_success
        cells = f'{unfitted:,} cell{"" if unfitted == 1 else "s"} with no fit' if unfitted else 'every cell fitted'
        note = f'{cells}, and the fit at the inputs as entered'
        stats.append(Stat('Fits', f'{result.n_success + 1:,} of {n * n + 1:,}', note))
        r2 = None if result.r2_grid is None else np.asarray(result.r2_grid, dtype=float).ravel()
    finite = r2[np.isfinite(r2)] if r2 is not None else np.array([])
    if finite.size:
        name = 'Median R² of samples' if result.mode is SensitivityMode.SOBOL else 'Median R² of cells'
        note = f'range {fmt_r2(float(finite.min()))} – {fmt_r2(float(finite.max()))}'
        stats.append(Stat(name, fmt_r2(float(np.median(finite))), note))
    if seconds is not None:
        note = '' if not workers else f'{workers} worker process{"" if workers == 1 else "es"}'
        stats.append(Stat('Duration', _duration(seconds), note))
    if result.stopped:
        stats.append(Stat('Stopped', 'Yes', stopped_sentence(result)))
    return stats


def seed_stat(result: SensitivityResult) -> Stat | None:
    """The seed that repeats a Sobol' run; ``None`` for a heatmap, which draws nothing at random."""
    if result.mode is not SensitivityMode.SOBOL:
        return None
    return Stat('Seed used', str(result.seed_used), 'Enter it under Fixed seed to repeat this run exactly.')


@dataclass(frozen=True)
class SourceStatement:
    """One error source a run varies, as Analysis settings lists it."""

    name: str
    stated: str


def stated_sources(errors: ErrorModel, labels: Mapping[str, str], units: Mapping[str, str]) -> list[SourceStatement]:
    """Every source *errors* varies, named by *labels*, with what was stated for it."""
    from gui.plotting.labels import stated_uncertainty

    out = [
        SourceStatement(labels.get(key, key), stated_uncertainty(spec, units.get(key, '')))
        for key, spec in errors.specs.items()
        if spec.varies
    ]
    out += [
        SourceStatement(source.name, f'σ {source.sigma_pct:g}{THIN}%')
        for source in errors.shared
        if source.sigma_pct > 0
    ]
    if errors.additions is not None:
        out.append(SourceStatement(ADDITIONS_LABEL, f'σ {errors.additions.sigma_pct:g}{THIN}% each addition'))
    return out


# ---------------------------------------------------------------------------
# Kₐ against each source
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SourcePlot:
    """Each sample's Kₐ against one source's draw: x is the draw in percent of the entered value.

    *x_range* is what the plot opens on — a range's two ends, a σ's farthest sample either
    side of zero — and *x_ticks* its labelled values, a range's two ends among them.
    """

    key: str
    name: str
    x: np.ndarray
    y: np.ndarray
    x_title: str
    x_range: tuple[float, float]
    x_ticks: list[tuple[float, str]]


#: The share of a source plot's range left free of round ticks beside each labelled end of a range.
_END_CLEARANCE = 0.12


def _offset_axis(result: SensitivityResult, key: str, drawn: np.ndarray) -> tuple[tuple[float, float], list]:
    """The draw axis of *key*'s plot: a range opens on exactly the ends entered, in percent of the entered value,
    and labels them however narrow it is; a σ has no ends and opens on ± the farthest sample drawn."""
    spec, nominal = _source_spec(result, key)
    if spec.kind is SpecKind.INTERVAL:
        lo, hi = (100.0 * end for end in spec_bounds(spec, nominal, source_name(key)))
        clear = _END_CLEARANCE * (hi - lo)
        inner = [v for v in _linear_ticks(lo, hi) if lo + clear < v < hi - clear]
        values = [lo, *inner, hi]
    else:
        finite = drawn[np.isfinite(drawn)]
        reach = float(np.max(np.abs(finite), initial=0.0)) or 1.0
        lo, hi = -reach, reach
        values = _linear_ticks(lo, hi)
    return (lo, hi), [(v, _minus(f'{v:.3g}')) for v in values]


def source_plots(result: SensitivityResult, ka_key: str) -> tuple[list[SourcePlot], str]:
    """One plot per source with a draw of its own, in the order of the index chart, and what is not plotted.

    The random error of each addition is one draw per titration point, so a sample has
    no single draw of it to plot against; the second value says so where it was stated.
    """
    assay = _assay(result)
    offsets = result.sample_offsets_pct or {}
    ka = np.asarray((result.sample_ka or {}).get(ka_key, []), dtype=float)
    plots = []
    for key in ordered_sources(result, ka_key):
        if key not in offsets:
            continue
        x = np.asarray(offsets[key], dtype=float)
        keep = np.isfinite(x) & np.isfinite(ka) & (ka > 0)
        name = source_label(assay, key)
        x_range, x_ticks = _offset_axis(result, key, x)
        plots.append(
            SourcePlot(key, name, x[keep], ka[keep], f'{plain_label(name)}, drawn change (%)', x_range, x_ticks)
        )
    note = ''
    if ADDITIONS in (result.sources or ()):
        note = (
            f'{ADDITIONS_LABEL} is not plotted: each sample draws one error per addition, so it has no single draw '
            'to plot Kₐ against. Its share is in the chart of Sensitivity.'
        )
    return plots, note


# ---------------------------------------------------------------------------
# Heatmap
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Heatmap:
    """Kₐ of one binding constant over two swept inputs, coloured on the heat scale.

    *x* and *y* are the cell centres in the axis' units, *values* the colour value of each
    cell (log₁₀ Kₐ, or Kₐ in the colour bar's power of ten) — ``NaN`` where no fit
    could be made — from *lo* to *hi* with *ticks*; *entered* is the point of the inputs
    as entered.
    """

    key: str
    name: str
    x: np.ndarray
    y: np.ndarray
    x_title: str
    y_title: str
    values: np.ndarray
    lo: float
    hi: float
    ticks: list[tuple[float, str]]
    bar_title: str
    entered: tuple[float, float]
    ka: np.ndarray
    r2: np.ndarray | None
    baseline: float
    x_label: str
    y_label: str
    x_unit: str
    y_unit: str
    e_x: int
    e_y: int


def _sweep(result: SensitivityResult, key: str, offsets_pct, units: Mapping[str, str]):
    """An axis of the grid in its input's unit: values, title, the entered value, the unit, its power of ten and name.

    The values are in the unit the condition is shown in (*units*), under one power of
    ten where they need it. The titrant is a series with no single value, so its axis
    stays in percent of the concentrations entered.
    """
    assay = _assay(result)
    name = plain_label(source_label(assay, key))
    offsets = np.asarray(offsets_pct, dtype=float)
    conditions = None if result.baseline_fit is None else result.baseline_fit.conditions
    field_ = None if assay is None or key == TITRANT else condition_field(assay, key)
    if field_ is None or not conditions or key not in conditions:
        return offsets, f'{name}, change (%)', 0.0, '%', 0, name
    unit = units.get(key) or field_.unit
    scale = float(Q_(1, unit).to(field_.unit).magnitude)
    values = nominal_value(key, conditions) * (1.0 + offsets / 100.0) / scale
    peak = float(np.max(np.abs(values))) if values.size else 0.0
    power = math.floor(math.log10(peak)) if peak > 0 else 0
    e = 0 if -2 <= power <= 2 else power
    shown = f'10{superscript(e)} {unit}' if e else unit
    entered = nominal_value(key, conditions) / scale / 10.0**e
    return values / 10.0**e, f'{name} ({shown})', entered, unit, e, name


def _ka_ticks(lo: float, hi: float) -> list[float]:
    """Round Kₐ values for a colour bar from *lo* to *hi*: evenly spaced within a decade, else round mantissas."""
    if hi < 10.0 * lo:
        return _linear_ticks(lo, hi)
    return R.nice_ticks(lo, hi)


def heatmaps(result: SensitivityResult, units: Mapping[str, str] | None = None, log: bool = True) -> list[Heatmap]:
    """One map per binding constant of a heatmap run, both axes in the inputs' units (*units* per input)."""
    units = units or {}
    cfg = result.config
    x, x_title, x0, x_unit, e_x, x_label = _sweep(result, cfg.x_key, result.x_offsets_pct, units)
    y, y_title, y0, y_unit, e_y, y_label = _sweep(result, cfg.y_key, result.y_offsets_pct, units)
    r2 = None if result.r2_grid is None else np.asarray(result.r2_grid, dtype=float)
    maps = []
    for key in result.ka_keys:
        ka = np.asarray(result.ka_grid[key], dtype=float)
        finite = ka[np.isfinite(ka) & (ka > 0)]
        name = plain_label(ka_name(key))
        if log:
            values = np.where(np.isfinite(ka) & (ka > 0), np.log10(np.where(ka > 0, ka, 1.0)), np.nan)
            lo, hi = (float(np.log10(finite.min())), float(np.log10(finite.max()))) if finite.size else (0.0, 1.0)
            if hi - lo < 1e-3:
                lo, hi = lo - 0.01, hi + 0.01
            ticks_ka = _ka_ticks(10.0**lo, 10.0**hi)
            e = R.shared_power(ticks_ka)
            ticks = [(math.log10(v), R.tick_label(v, e)) for v in ticks_ka if lo <= math.log10(v) <= hi]
            bar_title = f'{name} ({_unit_after(e).lstrip("×").strip()})' if e else f'{name} (M⁻¹)'
        else:
            lo, hi = (float(finite.min()), float(finite.max())) if finite.size else (0.0, 1.0)
            if hi - lo <= 1e-12 * max(abs(hi), 1.0):
                lo, hi = lo * 0.99, hi * 1.01
            ticks_v = [v for v in _linear_ticks(lo, hi) if lo <= v <= hi]
            e = math.floor(math.log10(hi)) if hi > 0 else 0
            values = ka
            ticks = [(v, f'{v / 10.0**e:g}') for v in ticks_v]
            bar_title = f'{name} (10{superscript(e)} M⁻¹)' if e else f'{name} (M⁻¹)'
        maps.append(
            Heatmap(
                key,
                name,
                x,
                y,
                x_title,
                y_title,
                values,
                lo,
                hi,
                ticks,
                bar_title,
                (x0, y0),
                ka,
                r2,
                result.baseline_ka[key],
                x_label,
                y_label,
                x_unit,
                y_unit,
                e_x,
                e_y,
            )
        )
    return maps


def _axis_value(value: float, unit: str, e: int) -> str:
    if unit == '%':
        return _signed_pct(value)
    return f'{spaced(fmt_value(value * 10.0**e))} {unit}'


def heatmap_readout(hm: Heatmap, ix: int, iy: int) -> tuple[str, list[tuple[str, str]]]:
    """The cell (*ix*, *iy*) as the readout card reads it: the two inputs as the title's lines, then Kₐ, its change and R²."""
    title = f'{hm.x_label} {_axis_value(hm.x[ix], hm.x_unit, hm.e_x)} · {hm.y_label} {_axis_value(hm.y[iy], hm.y_unit, hm.e_y)}'
    ka = hm.ka[iy, ix]
    if not math.isfinite(ka):
        return title, [(hm.name, 'no fit')]
    rows = [
        (hm.name, f'{spaced(fmt_value(ka))} M⁻¹'),
        ('Change from entered', _signed_pct(100.0 * (ka / hm.baseline - 1.0))),
    ]
    if hm.r2 is not None and math.isfinite(hm.r2[iy, ix]):
        rows.append(('R²', fmt_r2(float(hm.r2[iy, ix]))))
    return title, rows


# ---------------------------------------------------------------------------
# The budget as a CSV
# ---------------------------------------------------------------------------

#: The budget's columns in the CSV, between what a row is about and the seed it came from.
BUDGET_CSV_COLUMNS = (
    'Stated uncertainty',
    'Elasticity',
    'S1',
    'S1 low',
    'S1 high',
    'Variance (decades^2)',
    'Variance (decades^2) low',
    'Variance (decades^2) high',
    'Spread if exact (decades)',
    'Spread if exact (decades) low',
    'Spread if exact (decades) high',
)


def _csv_number(value: float) -> float | str:
    """One number for the CSV, or an empty cell where the analysis has none: no cell reads ``nan``."""
    return float(value) if math.isfinite(value) else ''


def _csv_interval(name: str, value: float, interval: Sequence[float]) -> dict:
    columns = (name, f'{name} low', f'{name} high')
    return {column: _csv_number(v) for column, v in zip(columns, (value, *interval))}


def budget_csv_rows(result: SensitivityResult) -> list[dict]:
    """The budget of every binding constant as CSV rows: the analysis's own floats, never the rounded text.

    Per constant: a note on the fits that ran to the edge of the Kₐ box, the whole
    variance, one row per source, what no single source explains, then the elasticity of
    every perturbable input. A constant whose numbers are withheld gets the note saying
    why and nothing else. Every row carries the seed that repeats the run; ``Kind`` says
    what a row is, since a source and the input it belongs to go by the same name.
    """
    if not result.budget:
        return []
    assay = _assay(result)

    def row(ka_key: str, kind: str, item: str, **values) -> dict:
        return {
            'Ka': plain_label(ka_name(ka_key)),
            'Kind': kind,
            'Item': item,
            **dict.fromkeys(BUDGET_CSV_COLUMNS, ''),
            **values,
            'Seed': result.seed_used,
        }

    rows: list[dict] = []
    for ka_key, budget in result.budget.items():
        s1 = (result.sobol_s1 or {}).get(ka_key, {})
        s1_ci = (result.sobol_s1_ci or {}).get(ka_key, {})
        withheld = withheld_note(result, ka_key)
        if withheld is not None:
            rows.append(row(ka_key, 'note', withheld))
            continue
        note = on_bound_note(result, ka_key)
        if note is not None:
            rows.append(row(ka_key, 'note', note))
        rows.append(
            row(
                ka_key,
                'total',
                'All sources together',
                **_csv_interval('Variance (decades^2)', budget.variance, budget.variance_ci),
            )
        )
        for entry in budget.rows:
            rows.append(
                row(
                    ka_key,
                    'source',
                    plain_label(source_label(assay, entry.source)),
                    **{'Stated uncertainty': stated_text(result, entry.source).replace(THIN, ' ')},
                    **({} if entry.elasticity is None else {'Elasticity': _csv_number(entry.elasticity)}),
                    **_csv_interval(
                        'S1', s1.get(entry.source, math.nan), s1_ci.get(entry.source, (math.nan, math.nan))
                    ),
                    **_csv_interval('Variance (decades^2)', entry.variance, entry.variance_ci),
                    **_csv_interval('Spread if exact (decades)', entry.sd_if_exact, entry.sd_if_exact_ci),
                )
            )
        rows.append(
            row(
                ka_key,
                'interactions',
                INTERACTIONS,
                **{
                    'S1': _csv_number(budget.interactions),
                    'Variance (decades^2)': _csv_number(budget.interactions * budget.variance),
                },
            )
        )
        for input_key, value in (result.elasticity or {}).get(ka_key, {}).items():
            rows.append(
                row(ka_key, 'input', plain_label(source_label(assay, input_key)), Elasticity=_csv_number(value))
            )
    return rows


def budget_refusal(result: SensitivityResult | None) -> str | None:
    """Why the budget of *result* cannot be written as a CSV; ``None`` when it can."""
    if result is None:
        return 'Run a sensitivity analysis first.'
    if result.mode is not SensitivityMode.SOBOL or not result.budget:
        return 'The analysis shown is a heatmap. Run one with Sensitivity indices to get an uncertainty budget.'
    if all((result.withheld or {}).get(key) for key in result.budget):
        return 'This analysis gives no uncertainty budget: for every binding constant Sensitivity says why its numbers are withheld. See that view.'
    if not any(math.isfinite(budget.variance) for budget in result.budget.values()):
        return (
            'This analysis reports no uncertainty budget: too few of its samples have a fit to split the spread of '
            'Ka between the sources. Run the analysis again.'
        )
    return None
