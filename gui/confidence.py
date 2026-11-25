"""What Ka confidence shows of a fit and its Ka profile, with no widget (DESIGN.md §8).

Every function here reads one :class:`~core.pipeline.fit_pipeline.FitResult`, the
session's :class:`~core.pipeline.profile.ProfileSet` of it and what the session holds
beside them, and returns text and numbers for :mod:`gui.views.confidence` to draw: the two
readings of each binding constant (:func:`headers`), the callouts (:func:`callouts`), one
profile plot per binding constant (:func:`profile_plot`) with the pointer's readout
(:func:`readout`), the joint region of a stepwise model (:func:`joint_region`), and the
sections of the *Notes* side panel (:func:`notes`).

The plots read both profiles on **one axis, Δ(−2 ln L) from the lower of the two best
fits** (:func:`deviance`): ``n · ln S`` for the conditional profile and the penalised objective
``n · ln S + z'z`` for the Input-aware one — −2 ln of the Gaussian likelihood with its noise
profiled out, and of the Gaussian uncertainty stated for each input — the same quantity
where no input moves, so a curve drawn lower explains the data better at that Ka and the
depth between the two minima shows. Each reading keeps its own 95 % cut-off, drawn as its own line, so each curve meets
its line where its interval ends.
Every reported number comes from :func:`~core.pipeline.reporting.summarize_parameters`
and is written by :mod:`gui.results` and :mod:`gui.plotting.labels`; nothing is computed
again here.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field, replace

import numpy as np

from core.assays.registry import ASSAY_REGISTRY, AssayType, ParamKind
from core.pipeline.fit_pipeline import FitResult
from core.pipeline.inputs import ErrorModel
from core.pipeline.reporting import fit_replica_ids, input_replica_ids, reports_conditional, summarize_parameters
from core.pipeline.varpro import SECOND_STEP_LEVEL, KaInterval
from gui import results as R
from gui.plotting.labels import (
    THIN,
    conflict_note,
    describe_replicates,
    fmt_p,
    fmt_param_plain,
    fmt_stat,
    fmt_unit_pretty,
    fmt_value,
    not_run_reason,
    one_step_sentence,
    region_sentence,
    superscript,
    times_ten,
    widening_sentences,
)
from gui.widgets.assay_conditions import result_input_labels

#: The y axis of every profile plot.
#: The likelihood-ratio statistic Δ(−2 ln L) from the plot's lower best fit, named in words; Title Case, as the owner chose.
Y_TITLE = 'Loss of Fit'
#: The default view runs from just below the best fit to this many cut-off rises above the higher curve's minimum.
Y_RISES = 3.0
#: Share of the y span left below 0, so the diamonds on it are seen whole.
Y_PAD = 0.04

#: Share of the Ka span the default view adds on either side, so each curve is seen
#: rising past its cut-off outside its interval.
X_PAD = 0.2
#: The narrowest default view, in decades of Ka.
MIN_SPAN = 0.5

#: The action of the conflict callout: it opens Notes at the input shifts.
SHOW_SHIFTS = 'Show the input shifts'

PENDING = 'The readings above are the fit’s own; the curves appear here when its Kₐ profile is ready.'
SPLIT_EXPLAINED = (
    'Not every Kₐ inside a split interval explains the data well enough: the ones that do come in separate '
    'stretches, and the interval spans all of them.'
)
NO_KA = 'This fit has no association constant, so there is no Kₐ to profile. Its parameters are listed in Fit details.'


def badge(fit: FitResult | None) -> str | None:
    """The summary beside the title, ``Profile likelihood · 95 %``; ``None`` without a profile-likelihood interval."""
    if fit is None or not _ka_keys(fit):
        return None
    rows = summarize_parameters(fit)
    if not any(s.interval is not None for s in rows if not s.is_log):
        return None  # no binding constant has a profile-likelihood interval: every one is fixed, or none was recorded
    levels = [s.level for s in rows if s.is_log and s.level]
    return f'Profile likelihood · {levels[0] * 100:g}{THIN}%' if levels else 'Profile likelihood'


def _scale(e: int | None, unit: str) -> str:
    """What an axis title states its numbers in: ``10⁸ M⁻¹``, or the unit alone."""
    return unit if not e else f'10{superscript(e)} {unit}'


def _ka_keys(fit: FitResult) -> list[str]:
    meta = ASSAY_REGISTRY[AssayType[fit.assay_type]]
    return [k for k in meta.parameter_keys if meta.param_kinds[k] is ParamKind.BINDING_CONSTANT]


def no_profile_sentence(has_data: bool) -> str:
    """What the view says of a fit that carries no Kₐ profile; *has_data* says whether a fit can run to draw one."""
    then = 'Run the fit again' if has_data else 'Load its titration data with Load data and run the fit'
    return (
        'This fit carries no Kₐ profile, so its curves are not drawn: a fit read from a results file, or one whose '
        f'profile was stopped, has none. {then} to draw them.'
    )


def split_explained(drawn: bool) -> str:
    """What *Split* means, with where the plot shows each stretch when it is *drawn*."""
    return f'{SPLIT_EXPLAINED} The strip under the plot shows each stretch.' if drawn else SPLIT_EXPLAINED


def failed_sentence(message: str) -> str:
    """What the view says where the Kₐ profile of the fit could not be worked out; *message* says why, in plain words."""
    reason = ' '.join(message.split())
    return f'{reason} The fit and its readings are unaffected; run the fit again to try once more.'


# ---------------------------------------------------------------------------
# The two readings of each binding constant
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Reading:
    """One reading of a binding constant as the header states it.

    *label* and *tone* are its badge (Input-aware in ``accent``, Inputs as entered
    ``neutral``); *value* the estimate, with *qualifier* where it rests on an end of its Ka
    search box (``Not limited below``); *interval* the 95 % interval as a headline writes
    it, *split* where its accepted Ka come in separate stretches; *reach* how far each
    closed end lies from the estimate; *tooltip* what the numbers do not show.
    """

    label: str
    tone: str
    value: str
    unit: str
    qualifier: str
    level: str
    interval: str
    split: bool = False
    reach: str = ''
    tooltip: str = ''
    reported: bool = True


@dataclass(frozen=True)
class Header:
    """One binding constant: its glossary name (HTML) and its readings, Input-aware first."""

    key: str
    name: str
    readings: list[Reading]


def _pct(ratio: float) -> str:
    """Signed percent change for a ratio to the best fit, with a real minus sign.

    Whole percent, with as many decimals as it takes for a drop to stay short of −100 %,
    which would read as a Ka of zero.
    """
    change = 100.0 * (ratio - 1.0)
    decimals = 0
    while decimals < 4 and round(change, decimals) <= -100.0 < change:
        decimals += 1
    return f'{change:+.{decimals}f}{THIN}%'.replace('-', '−')


def reach(estimate: float, at_bound: str, interval, open_) -> str:
    """How far each closed end of *interval* lies from *estimate*: ``−28 % / +31 % of the best fit``.

    An estimate on an end of its search box is no number to be a percentage of, and an open
    end no distance from it: those are left out, and a single closed end is named.
    """
    if interval is None or at_bound:
        return ''
    closed = [
        (side, _pct(edge / estimate))
        for edge, is_open, side in ((interval[0], open_[0], 'lower end'), (interval[1], open_[1], 'upper end'))
        if not is_open
    ]
    if len(closed) == 2:
        return f'{closed[0][1]} / {closed[1][1]} of the best fit'
    return f'{closed[0][0]} {closed[0][1]} of the best fit' if closed else ''


def headers(fit: FitResult) -> list[Header]:
    """Each binding constant of *fit* with its readings: Input-aware beside Inputs as entered, or the one reading.

    The reported reading is the headline of Fit results (:func:`gui.results.ka_blocks`):
    the same value, interval and what hovering over it says, a constant its bounds fix and
    a file that records no interval included.
    """
    specs = {s.key: s for s in summarize_parameters(fit) if not s.is_log}
    reported, tone = R.reading(fit)
    out = []
    for block in R.ka_blocks(fit):
        s = specs[block.key]
        readings = [
            Reading(
                reported,
                tone,
                block.value,
                block.unit,
                block.qualifier,
                block.level,
                block.interval,
                s.interval_split,
                reach(s.estimate, s.estimate_at_bound, s.interval, s.interval_open),
                block.tooltip,
            )
        ]
        if not reports_conditional(fit) and s.conditional_interval is not None:
            interval, open_ = s.conditional_interval, s.conditional_open
            value, qualifier = R.headline_value(s.conditional_estimate, s.conditional_at_bound, interval, open_)
            readings.append(
                Reading(
                    R.AS_ENTERED,
                    'neutral',
                    value,
                    block.unit,
                    qualifier,
                    block.level,
                    R.headline_interval(*interval, *open_, block.unit),
                    s.conditional_split,
                    reach(s.conditional_estimate, s.conditional_at_bound, interval, open_),
                    reported=False,
                )
            )
        out.append(Header(block.key, block.name, readings))
    return out


# ---------------------------------------------------------------------------
# Callouts
# ---------------------------------------------------------------------------


def callouts(
    fit: FitResult | None,
    note: str | None,
    *,
    pending: bool = False,
    unchecked: bool = False,
    others_hidden: str | None = None,
) -> list[R.CalloutSpec]:
    """The callouts of Ka confidence: those of Fit results, with the conflict's action opening the shifts here.

    *note* hides the fit and is then the only thing said; *unchecked* says its numbers
    could not be checked against data, *others_hidden* names the held fits not shown
    (:func:`gui.results.callouts`); *pending* adds the notice that the curves are still
    being computed.
    """
    specs = [
        R.CalloutSpec(spec.tone, spec.title, spec.body, SHOW_SHIFTS, R.Place.SHIFTS)
        if spec.action == R.REVIEW
        else spec
        for spec in R.callouts(fit, note, unchecked=unchecked, others_hidden=others_hidden)
    ]
    if pending and note is None:
        specs.append(R.CalloutSpec('neutral', 'Working out the curves', PENDING))
    return specs


# ---------------------------------------------------------------------------
# The profile plot of one binding constant
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Curve:
    """One reading's profile as drawn: x in log₁₀ Ka, y its Δ(−2 ln L) from the plot's lower best fit.

    *cut* is the reading's own 95 % cut-off at each *x*, on the same axis: one level for a
    model with one binding constant, stepping up with two where the fit at a Ka holds a
    signal parameter on its bound. *estimate* is the reading's estimate on the curve, ``None``
    where it rests on an end of its search box; *band* its interval in log₁₀ Ka, shaded in
    its colour; *stretches* are the Ka (1/M) the reading accepts, one per stretch of a split
    interval.
    """

    label: str
    color: str
    x: np.ndarray
    y: np.ndarray
    cut: np.ndarray
    estimate: tuple[float, float] | None = None
    band: tuple[float, float] | None = None
    stretches: list[tuple[float, float]] = field(default_factory=list)

    def at(self, x: float) -> float:
        """The curve's height at *x* (log₁₀ Ka) as drawn — straight between its points; NaN off its ends."""
        return _read(self.x, self.y, x)

    def cut_at(self, x: float) -> float:
        """The reading's cut-off at *x* (log₁₀ Ka); NaN off the curve's ends."""
        return _read(self.x, self.cut, x)

    def accepts(self, x: float) -> bool:
        """Whether the reading accepts the Ka at *x* (log₁₀ Ka): inside one of its stretches."""
        ka = 10.0**x
        return any(lo * (1 - 1e-9) <= ka <= hi * (1 + 1e-9) for lo, hi in self.stretches)


def _read(xs: np.ndarray, ys: np.ndarray, x: float) -> float:
    """*ys* at *x*, straight between the finite points; NaN off their ends."""
    finite = np.isfinite(xs) & np.isfinite(ys)
    xs, ys = xs[finite], ys[finite]
    if xs.size == 0 or not xs[0] <= x <= xs[-1]:
        return math.nan
    return float(np.interp(x, xs, ys))


@dataclass(frozen=True)
class ProfilePlot:
    """One binding constant's profile plot: its curves (Inputs as entered first, drawn underneath), axes and view.

    *x_range* is the default view in log₁₀ Ka and *y_range* in Δ(−2 ln L); *ticks*
    ``(log₁₀ Ka, label)`` share the power of ten the axis title states; *cut_label* names the
    cut-off lines in the legend; *stepped* says whether a cut-off steps inside the default view.
    """

    key: str
    name: str
    x_title: str
    curves: list[Curve]
    x_range: tuple[float, float]
    y_range: tuple[float, float]
    ticks: list[tuple[float, str]]
    unit: str
    exponent: int | None
    cut_label: str = '95 % cut-off'
    stepped: bool = False

    def readout_title(self, x: float) -> str:
        """``Loss of Fit at 1.70 × 10⁸ M⁻¹``: what the readout card at *x* (log₁₀ Ka) reads."""
        ka = 10.0**x
        e = self.exponent
        number = fmt_value(ka) if e is None else f'{fmt_value(ka / 10.0**e)}{times_ten(e)}'
        return f'{Y_TITLE} at {number} {self.unit}'

    def chip(self, x: float) -> str:
        """The pointer's Ka at the top of its hairline, in the axis's own power of ten."""
        ka = 10.0**x
        return fmt_value(ka) if self.exponent is None else fmt_value(ka / 10.0**self.exponent)


def deviance(r2, n: int) -> np.ndarray:
    """``n · ln(1 − R²)``: −2 ln L of a profile, up to one constant shared by both readings.

    The conditional profile's R² is ``1 − S/SS_tot`` and the penalised profile's
    ``1 − exp(P/n)/SS_tot`` (:class:`~core.pipeline.input_aware.AwareProfile`), on the same
    weighted ``SS_tot``, so this is ``n · ln S`` and ``P`` less the same ``n · ln SS_tot``:
    their differences are differences of the objective, and where every input stays where
    it was entered the two are equal. Not a number where R² is not.
    """
    with np.errstate(invalid='ignore', divide='ignore'):
        return n * np.log(1.0 - np.asarray(r2, dtype=float))


def curve(label: str, color: str, profile, n: int, estimate: float | None, at_bound: str, interval) -> Curve:
    """The drawn curve of one reading of *profile* — a :class:`~core.pipeline.profile.ProfileResult` or an
    :class:`~core.pipeline.input_aware.AwareProfile` — on the Δ(−2 ln L) axis of *n* titration points, unshifted,
    with its cut-off, its estimate and the stretches of *interval* it accepts.

    A Ka the profile was read at twice is drawn once.
    """
    grid, keep = np.unique(np.asarray(profile.grid, dtype=float), return_index=True)
    r2, r2_cut = np.asarray(profile.r2, dtype=float)[keep], np.asarray(profile.r2_cut, dtype=float)[keep]
    x = np.log10(grid)
    y = np.where(np.isfinite(r2), deviance(r2, n), np.nan)
    stretches = [] if interval is None else R.accepted_stretches(grid, r2, r2_cut, *interval)
    mark = None if at_bound or estimate is None else (math.log10(estimate), _read(x, y, math.log10(estimate)))
    band = None if interval is None else (math.log10(interval[0]), math.log10(interval[1]))
    return Curve(label, color, x, y, deviance(r2_cut, n), mark, band, stretches)


def _shifted(c: Curve, by: float) -> Curve:
    mark = None if c.estimate is None else (c.estimate[0], c.estimate[1] - by)
    return replace(c, y=c.y - by, cut=c.cut - by, estimate=mark)


def profile_plot(fit: FitResult, profile) -> ProfilePlot | None:
    """The profile plot of *profile*'s binding constant in *fit*; ``None`` for a constant its bounds fix.

    Inputs as entered is the conditional curve; Input-aware the fit's penalised profile,
    or — where no input moves and a stated error of the additions widens the reported
    interval — the same curve under that wider cut-off. With every input exact the one
    reading is Inputs as entered. Both stand on one Δ(−2 ln L) axis, 0 at the lower of their
    best fits.
    """
    if profile.interval is None:
        return None
    spec = next(s for s in summarize_parameters(fit) if s.key == profile.ka_key and not s.is_log)
    conditional_only = reports_conditional(fit)
    if conditional_only:
        entered = (spec.estimate, spec.estimate_at_bound, spec.interval)
    else:
        entered = (spec.conditional_estimate, spec.conditional_at_bound, spec.conditional_interval)
    n = profile.n_points
    curves = [curve(R.AS_ENTERED, 'text-secondary', profile, n, *entered)]
    aware = profile.aware
    if aware is not None and not conditional_only:
        curves.append(curve(R.INPUT_AWARE, 'accent', aware, n, spec.estimate, spec.estimate_at_bound, spec.interval))
    floor = min(float(np.nanmin(c.y)) for c in curves)
    curves = [_shifted(c, floor) for c in curves]
    # Every estimate and interval end, both readings: the view frames them and a fifth of their span beside.
    shown = [entered, (spec.estimate, spec.estimate_at_bound, spec.interval)][: len(curves)]
    logs = [
        math.log10(v)
        for est, at_bound, interval in shown
        if interval is not None
        for v, written in ((est, not at_bound), (interval[0], True), (interval[1], True))
        if written
    ]
    lo, hi = min(logs), max(logs)
    if hi - lo < MIN_SPAN:
        middle = 0.5 * (lo + hi)
        lo, hi = middle - MIN_SPAN / 2, middle + MIN_SPAN / 2
    pad = X_PAD * (hi - lo)
    drawn = np.log10(profile.grid)
    # Never past the drawn curve, and never inside what the readings ask for.
    lo, hi = max(lo - pad, min(float(drawn[0]), lo)), min(hi + pad, max(float(drawn[-1]), hi))
    # Up the plot: from the lower best fit to a few of its own cut-off rises above each curve's minimum.
    top = max(
        float(np.nanmin(c.y)) + Y_RISES * max(float(np.nanmin(c.cut)) - float(np.nanmin(c.y)), 0.0) for c in curves
    )
    top = top if top > 0 else 1.0
    ticks = R.nice_ticks(10.0**lo, 10.0**hi)
    e = R.shared_power(ticks)
    unit = fmt_unit_pretty(spec.unit)
    name = fmt_param_plain(profile.ka_key)
    scale = _scale(e, unit)
    level = f'{spec.level * 100:g}{THIN}%' if spec.level else ''
    return ProfilePlot(
        key=profile.ka_key,
        name=name,
        x_title=f'{name} ({scale}, log scale)',
        curves=curves,
        x_range=(lo, hi),
        y_range=(-Y_PAD * top, top),
        ticks=[(math.log10(v), R.tick_label(v, e)) for v in ticks],
        unit=unit,
        exponent=e,
        cut_label=f'{level} cut-off'.strip(),
        stepped=any(np.any(np.diff(c.cut[(c.x >= lo) & (c.x <= hi)]) != 0) for c in curves),
    )


@dataclass(frozen=True)
class ReadoutRow:
    """One curve at the pointer: its name and colour, its Δ(−2 ln L) there and whether that Ka is accepted."""

    label: str
    color: str
    value: str
    verdict: str


def readout(plot: ProfilePlot, x: float) -> list[ReadoutRow]:
    """What each curve of *plot* reads at *x* (log₁₀ Ka), the reported reading first."""
    rows = []
    for drawn in reversed(plot.curves):
        y = drawn.at(x)
        value = '—' if math.isnan(y) else f'{y:.1f}'
        rows.append(ReadoutRow(drawn.label, drawn.color, value, 'accepted' if drawn.accepts(x) else 'rejected'))
    return rows


# ---------------------------------------------------------------------------
# The joint region of two binding constants
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Region:
    """The joint region of a stepwise model's two binding constants, on log₁₀ Ka axes.

    *accepted* is the accepted cells (shape ``(len(x), len(y))``), *extent* their outer
    edges ``(x_lo, x_hi, y_lo, y_hi)``; *bands* the interval of each constant at the
    region's footing, ``(axis, low, high)`` with axis ``'x'`` or ``'y'``.
    """

    x_title: str
    y_title: str
    accepted: np.ndarray
    extent: tuple[float, float, float, float]
    best: tuple[float, float]
    x_ticks: list[tuple[float, str]]
    y_ticks: list[tuple[float, str]]
    bands: list[tuple[str, float, float]]
    description: str


def _log_extent(values: np.ndarray) -> tuple[float, float]:
    """Outer edges, in log₁₀, of the cells a log-spaced grid of *values* stands for."""
    logs = np.log10(values)
    half = 0.5 * float(logs[1] - logs[0]) if logs.size > 1 else 0.5
    return float(logs[0]) - half, float(logs[-1]) + half


def _axis(key: str, unit: str, lo: float, hi: float) -> tuple[str, list[tuple[float, str]]]:
    ticks = R.nice_ticks(10.0**lo, 10.0**hi)
    e = R.shared_power(ticks)
    scale = _scale(e, unit)
    return f'{fmt_param_plain(key)} ({scale}, log scale)', [(math.log10(v), R.tick_label(v, e)) for v in ticks]


def joint_region(fit: FitResult, profile_set) -> Region | None:
    """The joint region of *profile_set*, or ``None`` for a model with one free binding constant."""
    region = None if profile_set is None else profile_set.region
    if region is None:
        return None
    k1, k2 = region.ka_keys
    units = {s.key: fmt_unit_pretty(s.unit) for s in summarize_parameters(fit) if not s.is_log}
    x_lo, x_hi = _log_extent(region.x)
    y_lo, y_hi = _log_extent(region.y)
    x_title, x_ticks = _axis(k1, units.get(k1, ''), x_lo, x_hi)
    y_title, y_ticks = _axis(k2, units.get(k2, ''), y_lo, y_hi)
    bands = [
        (axis, math.log10(interval.low), math.log10(interval.high))
        for axis, key in (('x', k1), ('y', k2))
        if (interval := region.intervals.get(key)) is not None
    ]
    moved = not reports_conditional(fit)
    return Region(
        x_title=x_title,
        y_title=y_title,
        accepted=np.isfinite(region.r2) & (region.r2 >= region.r2_cut),
        extent=(x_lo, x_hi, y_lo, y_hi),
        best=(math.log10(region.best[0]), math.log10(region.best[1])),
        x_ticks=x_ticks,
        y_ticks=y_ticks,
        bands=bands,
        description='inputs as entered' if moved else '',
    )


# ---------------------------------------------------------------------------
# Notes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NoteSection:
    """One section of *Notes*: a title, its paragraphs (plain text), a trailing summary and a warning flag.

    *shifts* holds the rows of the input shifts, drawn between the first paragraph and the
    rest; *quiet* is how many of the last paragraphs read in ``text-tertiary``.
    """

    key: str
    title: str
    paragraphs: list[str]
    trailing: str = ''
    flag: bool = False
    shifts: list = field(default_factory=list)
    quiet: int = 0


def _count(n: int, noun: str) -> str:
    return f'{n} {noun}' if n == 1 else f'{n} {noun}s'


def _intervals(fit: FitResult) -> tuple[dict[str, KaInterval], dict[str, KaInterval]]:
    """The reported and the conditional interval of every binding constant the fit was free to move."""
    reported = dict(fit.intervals or {})
    conditional = reported if fit.conditional is None else dict(fit.conditional.intervals)
    return reported, conditional


def _open_sentences(label: str, interval: KaInterval, unit: str) -> list[str]:
    """What each open side of *interval* of *label* stops at, and what would close it."""
    out = []
    shown = interval.one_step_p is not None and interval.one_step_p > SECOND_STEP_LEVEL
    for is_open, unsolvable, limited_by, side, edge, advice in (
        (
            interval.open_low,
            interval.unsolvable_low,
            interval.limited_by_low,
            'lower',
            interval.low,
            'Points at a higher titrant concentration would pin it down.',
        ),
        (
            interval.open_high,
            interval.unsolvable_high,
            interval.limited_by_high,
            'higher',
            interval.high,
            'Points taken before the signal levels off, or a lower fixed concentration, would pin it down.',
        ),
    ):
        if not is_open or (side == 'lower' and shown):
            continue
        where = f'{fmt_value(edge)} {unit}'.strip()
        if limited_by:
            other = fmt_param_plain(limited_by)
            tail = (
                f'The fit is rejected beyond {where} only because {other} cannot go past its bound there. If you '
                f'know {other}, hold it at that value under Binding model (equal lower and upper bound); otherwise '
                'only data that determine it close this side.'
            )
        elif unsolvable:
            tail = (
                f'The binding model cannot be solved past {where}, so the curve stops there, short of the bound this '
                'fit was given. More measurements cannot close this side.'
            )
        else:
            tail = f'It reaches the bound of {where}. {advice}'
        out.append(f'{label}: the data cannot rule out a {side} value. {tail}')
    return out


def notes(fit: FitResult, profile_set=None, replica_order: Sequence[str] | None = None) -> list[NoteSection]:
    """The sections of *Notes* for *fit* and its *profile_set* (``None`` while it is computed or where it failed)."""
    from core.pipeline.diagnostics import rejections

    sections: list[NoteSection] = []
    labels = result_input_labels(fit.assay_type, fit.fit_config)
    diagnostics = fit.diagnostics
    shifts = fit.input_shifts or {}
    rows = R.shift_rows(fit)
    conflicted = diagnostics is not None and 'conflict' in rejections(
        diagnostics.conditional_misfit, diagnostics.misfit, diagnostics.conflict
    )
    if conflicted:
        # The statistic judges the inputs stated with a σ: they are the correction, and
        # the note after them says where the inputs stated as a range moved.
        sections.append(
            NoteSection(
                'conflict',
                'Inputs conflict',
                [
                    'The fit put the correction here:',
                    conflict_note(diagnostics, shifts, labels),
                    'Bars in σ, band ±1 σ.',
                ],
                fmt_p(diagnostics.conflict.p_value),
                True,
                [row for row in rows if row.z is not None],
                quiet=1,
            )
        )
    elif rows:
        tested, trailing = _inputs_tested(diagnostics)
        sections.append(
            NoteSection(
                'conflict',
                'Input shifts',
                [
                    'Where the fit put the inputs it was free to move:',
                    f'{tested} The Input-aware interval includes these shifts.',
                    R.shifts_footnote(rows),
                ],
                trailing,
                shifts=rows,
                quiet=1,
            )
        )

    plots = [] if profile_set is None else [profile_plot(fit, p) for p in profile_set.profiles.values()]
    plots = [p for p in plots if p is not None]
    aware = any(len(p.curves) > 1 for p in plots) or not reports_conditional(fit)
    reading = [
        'Each curve shows, at every Kₐ, how much worse the data are explained than by the best fit on the plot, '
        'as its loss of fit — the likelihood-ratio statistic Δ(−2 ln L): 0 is that best fit, and a lower curve '
        'explains the data better. Each reading has its own 95 % cut-off, the dotted line in its colour; '
        'where its curve is at or below that line, the reading accepts that Kₐ.'
    ]
    if aware:
        reading.append(
            'Input-aware scores each fit by its residual plus a penalty for every input’s move, measured against '
            'the uncertainty you stated; Inputs as entered by the residual alone. Inputs as entered is one of the '
            'fits Input-aware can choose, so its curve never runs below the Input-aware curve. The gap between the '
            'two lowest points shows how much better the data are explained once the inputs may move.'
        )
    if any(p.stepped for p in plots):
        reading.append(
            'Where the fit at a Kₐ has to hold a signal parameter at its bound, it gives up that parameter as well as '
            'Kₐ, so the test allows it a larger rise and the cut-off steps up there.'
        )
    reading.append('Point at the plot to read every curve at any Kₐ.')
    if plots:
        sections.append(NoteSection('reading', 'Reading the curves', reading, quiet=1))

    split = []
    for header in headers(fit):
        for r in header.readings:
            if not r.split:
                continue
            plot = next((p for p in plots if p.key == header.key), None)
            drawn = None if plot is None else next((c for c in plot.curves if c.label == r.label), None)
            stretches = [] if drawn is None else drawn.stretches
            gaps = [(stretches[i][1], stretches[i + 1][0]) for i in range(len(stretches) - 1)]
            rejected = ', '.join(f'from {fmt_value(a)} to {fmt_value(b)} {r.unit}' for a, b in gaps)
            name = fmt_param_plain(header.key)
            text = f'{r.label}: the range {r.interval} of {name} has a gap'
            split.append(f'{text}; {name} {rejected} is rejected.' if rejected else f'{text}.')
    if split:
        split.append(split_explained(bool(plots)))
        sections.append(NoteSection('split', 'Split interval', split))

    reported, conditional = _intervals(fit)
    units = {h.key: h.readings[0].unit for h in headers(fit)}
    opened, steps = [], []
    for key in reported:
        name = fmt_param_plain(key)
        both = [(R.reading(fit)[0], reported[key])]
        if not reports_conditional(fit) and key in conditional:
            both.append((R.AS_ENTERED, conditional[key]))
        for label, interval in both:
            prefix = f'{name}, {label.lower()}' if len(both) > 1 else name
            opened += _open_sentences(prefix, interval, units.get(key, ''))
            if interval.one_step_p is not None:
                sentence = one_step_sentence(name, interval.one_step_p)
                steps.append(f'{label}: {sentence}' if len(both) > 1 else sentence)
    if opened:
        sections.append(NoteSection('open', 'Open sides', opened))
    if steps:
        steps.append(
            f'A lower limit on the second constant claims that the second binding step exists, so it is given only '
            f'where the data reject the model without that step at p ≤ {SECOND_STEP_LEVEL:g}.'
        )
        sections.append(NoteSection('step', 'Second binding step', steps))

    sections.append(
        NoteSection('rest', 'What the intervals rest on', _rest(fit, profile_set, bool(plots), replica_order))
    )
    widened = widening_sentences(summarize_parameters(fit), fit, fmt_param_plain)
    if widened:
        sections.append(NoteSection('widened', 'What widened the intervals', widened))
    region = None if profile_set is None else profile_set.region
    if region is not None:
        k1, k2 = (fmt_param_plain(k) for k in region.ka_keys)
        text = [
            f'The region holds the pairs of {k1} and {k2} the data accept together at {region.level * 100:g} %, '
            'with the inputs as entered; the diamond marks the best fit, and the bands are the interval of each '
            'constant on its own.'
        ]
        if not reports_conditional(fit) and fit.input_shifts:
            text.append(
                'The uncertainties you stated for the inputs widen each binding constant’s own interval, in the '
                'plots above, not the region.'
            )
        widened_region = region_sentence(fit)
        if widened_region:
            text.append(widened_region)
        sections.append(NoteSection('region', 'Joint region', text))
    return sections


def _inputs_tested(diagnostics) -> tuple[str, str]:
    """What the test of the moved inputs against what was stated said, and its p for the section's header.

    A test that could not run is named with its reason, so it is never read as one that
    passed, and a results file that records no diagnostics is said to record none; a σ is
    no bound, so no shift is called inside what was stated.
    """
    conflict = None if diagnostics is None else diagnostics.conflict
    if conflict is not None:
        return (
            'The test of the inputs against what you stated found no evidence that, taken together, they moved '
            f'further than stated (q = {fmt_stat(conflict.q)}, {fmt_p(conflict.p_value)}).',
            fmt_p(conflict.p_value),
        )
    if diagnostics is None:
        return 'The test of the inputs against what you stated is not recorded in this result.', ''
    reason = not_run_reason(diagnostics, 'conflict')
    return f'The entered inputs were not tested against what you stated{f": {reason}" if reason else ""}.', ''


def _rest(fit: FitResult, profile_set, drawn: bool, replica_order) -> list[str]:
    """What every interval of the fit rests on: its data, what was free to move, the bounds, the replicates used.

    *drawn* says whether a profile plot is drawn, which the sentences may then point to.
    """
    out = []
    first = None if profile_set is None or not profile_set.profiles else next(iter(profile_set.profiles.values()))
    # The counts come with the profile: without one, the sentence that states them is left out.
    counted = (
        ''
        if first is None
        else f'{_count(first.n_points, "data point")} and {_count(first.n_params, "fitted parameter")}'
    )
    additions = ErrorModel.from_dict(fit.fit_config or {}).additions
    allowed = 'the reported interval allows for the random error of each addition you stated'
    if fit.intervals is None:
        out.append(R.LEGACY_NOTE)
    else:
        worked = 'Each interval is worked out'
        if fit.input_shifts:
            head = (
                'Each input with a stated uncertainty was free to move within it, which usually widens the interval'
                + (f', and {allowed}.' if additions else '.')
            )
            worked = 'Each interval at the entered inputs is worked out'
        elif additions:
            head = f'{allowed[0].upper()}{allowed[1:]}{", on the same curve" if drawn else ""}.'
        else:
            head = 'Every input was taken as entered.'
        counts = f' {worked} from {counted}.' if counted else ''
        out.append(f'{head}{counts} No interval reaches further than the parameter bounds this fit was given.')
    if first is not None and first.per_replica:
        out.append('The curves are those of the average of the replicates; each replicate’s own fit is in Fit details.')
    used = fit_replica_ids(fit)
    skipped = (
        list(fit.metadata.get('replica_failures') or {})
        if used is None
        else [rid for rid in input_replica_ids(fit) or () if rid not in used]
    )
    if skipped:
        names = describe_replicates(skipped, replica_order)
        many = len(skipped) > 1
        out.append(
            f'{names[0].upper()}{names[1:]} {"are" if many else "is"} left out here, as '
            f'{"they were" if many else "it was"} from the fit.'
        )
    return out
