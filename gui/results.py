"""What Fit results shows of a fit, with no widget (DESIGN.md §8).

Every function here reads one :class:`~core.pipeline.fit_pipeline.FitResult` and what the
session holds beside it, and returns text and numbers for :mod:`gui.views.fit_results` to
draw: the headline of each binding constant with its interval-chart rows and the tooltips
that carry its notes (:func:`ka_blocks`, which the side panel of Input uncertainty draws
too), the single-replicate line (:func:`replicate_line`), the callouts (:func:`callouts`),
the titration plot (:func:`titration`), and the sections of *Fit details* — fit quality
(:func:`quality`, :func:`noise_stat`), the replicates' own fits (:func:`replicate_rows`),
the tests with each one's full sentence (:func:`test_rows`), the parameters
(:func:`parameter_rows`, :func:`parameter_notes`) and the input shifts
(:func:`shift_rows`). Every reported row comes from
:func:`~core.pipeline.reporting.summarize_parameters` and every number is written by
:mod:`gui.plotting.labels`, so the view, the TXT and CSV reports and the status bar quote
one fit alike; nothing is computed again here.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum
from html import escape

import numpy as np

from core.assays.registry import ASSAY_REGISTRY, AssayType, ParamKind
from core.data_processing.plotting import prepare_plot_data
from core.pipeline.fit_pipeline import FitResult
from core.pipeline.inputs import ErrorModel, input_name
from core.pipeline.reporting import (
    fit_replica_ids,
    input_replica_ids,
    parameters_on_bound,
    replica_order,
    reports_conditional,
    summarize_parameters,
)
from core.units import Quantity
from gui.plotting.labels import (
    NO_LOWER,
    NO_UPPER,
    NOT_RUN,
    REPLICATES_RELATION,
    SPLIT_NOTE,
    THIN,
    UNLIMITED,
    UNSOLVABLE_NOTE,
    _display_label,
    and_join,
    describe_replicates,
    fmt_against,
    fmt_bound_note,
    fmt_estimate,
    fmt_interval_plain,
    fmt_misfit,
    fmt_p,
    fmt_param,
    fmt_param_plain,
    fmt_percent,
    fmt_r2,
    fmt_rmse,
    fmt_sci,
    fmt_shifts,
    fmt_stat,
    fmt_test_p,
    fmt_unit_html,
    fmt_unit_pretty,
    fmt_value,
    not_run_reason,
    offset_note,
    one_step_sentence,
    own_estimates,
    shift_order,
    superscript,
    times_ten,
    widening_sentences,
)
from gui.views.titration import TitrationData
from gui.widgets.assay_conditions import result_input_labels

_NO_VALUE = '—'

#: The shortcut of *Run fit*, which the toolbar's primary button and the empty view name.
RUN_FIT_KEY = 'Ctrl+R'

INPUT_AWARE = 'Input-aware'
AS_ENTERED = 'Inputs as entered'
SPLIT = 'Split'

#: What the titration plot shows of the replicates, as the replicate-display tool offers it.
REPLICATE_DISPLAYS = ('Replicates and mean ± SD', 'Mean ± SD only', 'Replicates only')

#: The replicate display of the raw titration in Measurements: each replicate's own points, as loaded.
RAW = 2

LEGACY_NOTE = (
    'Imported from a file written by an earlier version: a multi-start estimate without a confidence interval. '
    'Fit the data again to get the interval.'
)

UNCHECKED_NOTE = (
    'No data are loaded, so these numbers are shown as stored in the file and could not be checked against '
    'the data. To check them, load the data first and import the results again.'
)

#: Said in the plot header where the curve is drawn at the inputs the fit moved, not at the entered ones.
SHIFTED_CURVE_NOTE = 'curve drawn at the fitted input shifts'


#: What the mark of a split interval means, wherever a split interval is reported.
SPLIT_FOOTNOTE = f'{SPLIT_NOTE[0].upper()}{SPLIT_NOTE[1:]}'

_FIT_DEGENERATE_TAIL = (
    'Each starred value is one member of that family. It reconstructs the fitted curve correctly and is not a '
    'measurement of that one coefficient.'
)


def _sentence(note: str) -> str:
    return f'{note[0].upper()}{note[1:]}'


def degenerate_note(names: Sequence[str], tail: str) -> str:
    """Why the starred rows are starred: the shared fact about *names*, then what it means where they are shown."""
    return (
        f'The data fix only a combination of {and_join(names)}, not each one on its own: many different sets of '
        f'their values draw the same curve. {tail}'
    )


# ---------------------------------------------------------------------------
# The reading reported, and each binding constant's headline and interval chart
# ---------------------------------------------------------------------------


def reading(fit: FitResult) -> tuple[str, str]:
    """The reading the headline reports and the tone of its badge: Input-aware (accent), or Inputs as entered."""
    return (AS_ENTERED, 'neutral') if reports_conditional(fit) else (INPUT_AWARE, 'accent')


def nice_ticks(lo: float, hi: float) -> list[float]:
    """Two to six round values for a log axis from *lo* to *hi*.

    Powers of ten on an axis of many decades; on a shorter one the densest set of round
    mantissas that keeps to six; on an axis too short for any of them, evenly spaced
    round values.
    """
    if math.log10(hi / lo) > 2.5:
        decades = [10.0**e for e in range(math.ceil(math.log10(lo)), math.floor(math.log10(hi)) + 1)]
        return decades[:: math.ceil(len(decades) / 6)]
    powers = range(math.floor(math.log10(lo)), math.ceil(math.log10(hi)) + 1)
    for mantissas in ((1, 1.5, 2, 3, 4, 5, 7), (1, 2, 3, 5), (1, 2, 5), (1, 3), (1,)):
        inside = [float(f'{m * 10.0**e:.6g}') for e in powers for m in mantissas]
        inside = [v for v in inside if lo <= v <= hi]
        if 2 <= len(inside) <= 6:
            return inside
    # Evenly spaced round values: the coarsest step giving three to six, else two.
    k = math.floor(math.log10(hi - lo))
    candidates = []
    for step in (m * 10.0**e for e in range(k, k - 4, -1) for m in (5, 2.5, 2, 1)):
        inside = [float(f'{i * step:.6g}') for i in range(math.ceil(lo / step), math.floor(hi / step) + 1)]
        if 2 <= len(inside) <= 6:
            candidates.append(inside)
    return max(candidates, key=lambda ticks: 3 <= len(ticks), default=[lo, hi])


def shared_power(values: Sequence[float]) -> int | None:
    """The one power of ten *values* are written in, that of the largest; ``None`` where none serves them all.

    Under one power the smallest value would read as a mantissa of ``0.0…`` once it lies
    more than a decade below the largest, which is read as a different number, so each
    value is then written with its own power.
    """
    top = math.floor(math.log10(max(values)))
    return top if top - math.floor(math.log10(min(values))) <= 1 else None


def tick_label(value: float, e: int | None) -> str:
    """A tick of an axis whose numbers share the power *e*: its mantissa; with ``None``, the value in full (``2 × 10⁴``)."""
    if e is not None:
        return f'{value / 10.0**e:g}'
    power = math.floor(math.log10(value))
    if -2 <= power <= 2:
        return f'{value:g}'
    mantissa = float(f'{value / 10.0**power:.6g}')
    return f'10{superscript(power)}' if mantissa == 1 else f'{mantissa:g}{times_ten(power)}'


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


def headline_interval(low: float, high: float, open_low: bool, open_high: bool, unit: str) -> str:
    """An interval as a headline writes it, one power of ten shared: ``1.14 – 2.08 × 10⁸ M⁻¹``.

    Ends more than a decade apart are each written with their own power, ``2.00 × 10³ –
    5.00 × 10⁸ M⁻¹`` (:func:`shared_power`). A side the data leave open reads in words —
    ``no lower limit – 2.08 × 10⁸ M⁻¹`` — and one open on both sides reads ``not limited by
    the data``: the bound the profile ran to is not a limit.
    """
    if open_low and open_high:
        return UNLIMITED
    closed = [v for v, is_open in ((low, open_low), (high, open_high)) if not is_open]
    e = shared_power(closed)

    def number(v: float) -> str:
        return fmt_value(v) if e is None else fmt_value(v / 10.0**e)

    tail = f'{times_ten(e or 0)} {unit}'.rstrip()
    if open_low:
        return f'{NO_LOWER} – {number(high)}{tail}'
    if open_high:
        return f'{number(low)}{tail} – {NO_UPPER}'
    return f'{number(low)} – {number(high)}{tail}'


def headline_value(estimate: float, at_bound: str, interval, open_) -> tuple[str, str]:
    """An estimate as a headline writes it, and the words before it: ``('1.59 × 10⁸', '')``.

    An estimate on an end of its Ka search box is no number: it reads ``Not limited
    below`` or ``Not limited above``, and the value is the closed end of its interval that
    bounds it (``2.41 × 10³``), or ``''`` where the data close neither.
    """
    if not at_bound:
        return fmt_value(estimate), ''
    words = fmt_estimate(estimate, at_bound, interval, open_, html=False)
    # 'not limited below 2.41 × 10³': the words, then the bound the data do set, if any.
    for phrase in ('not limited below', 'not limited above'):
        if words.startswith(phrase):
            return words[len(phrase) :].strip(), _sentence(phrase)
    return '', _sentence(words)


@dataclass(frozen=True)
class KaBlock:
    """One binding constant as the headline states it, with its interval-chart rows.

    Attributes
    ----------
    key : str
        The constant's parameter key.
    name : str
        Its glossary name, HTML (``K<sub>a</sub> guest``).
    value : str
        The reported estimate, ``1.59 × 10⁸``; where it rests on an end of its Ka search
        box, the closed end of its interval that bounds it (``2.41 × 10³``).
    unit : str
        Its unit, ``M⁻¹``.
    level : str
        ``95 % interval``; ``Interval`` where the fit records no level.
    interval : str
        The reported interval (:func:`headline_interval`), or why there is none.
    tooltip : str
        What the interval line's numbers do not show: a side no data can close, the test of a
        second binding step, what widened the interval, a file that records none.
    rows : list[dict]
        :class:`~gui.design.components.IntervalChart` rows: Input-aware beside Inputs as
        entered, or the one reading of a fit that took every input as entered; empty where
        there is no interval.
    lo, hi : float
        The chart's log axis.
    ticks : list[tuple[float, str]]
        Its ticks, each value with its label.
    exponent : int or None
        The power of ten every number of the rows is written in; ``None`` where they span
        too many decades to share one, and each is written in full (:func:`shared_power`).
    ratio : float or None
        The log width of the Input-aware interval over that at the inputs as entered;
        ``None`` with one reading.
    qualifier : str
        ``Not limited below`` or ``Not limited above`` for an estimate on an end of its Ka
        search box, which is no number (*value* is then the bound the data do set); ``''``
        otherwise.
    chart_tooltip : str
        What a *Split* badge on the chart means, where a reading is split; ``''`` otherwise.
    """

    key: str
    name: str
    value: str
    unit: str
    level: str
    interval: str
    tooltip: str = ''
    rows: list[dict] = field(default_factory=list)
    lo: float = 1.0
    hi: float = 10.0
    ticks: list[tuple[float, str]] = field(default_factory=list)
    exponent: int | None = 0
    ratio: float | None = None
    qualifier: str = ''
    chart_tooltip: str = ''

    @property
    def axis_unit(self) -> str:
        """What follows the last tick of the chart: ``× 10⁸ M⁻¹``, or the unit alone where the numbers are written in full."""
        return f'{times_ten(self.exponent or 0).strip()} {self.unit}'.strip()

    @property
    def plain_name(self) -> str:
        """The constant's glossary name as plain text, ``Kₐ guest``."""
        return fmt_param_plain(self.key)

    @property
    def plain_value(self) -> str:
        """The headline value with its unit as plain text: ``1.59 × 10⁸ M⁻¹``, ``not limited below 2.41 × 10³ M⁻¹``."""
        return ' '.join(text for text in (self.qualifier.lower(), self.value, self.unit) if text)


def ka_blocks(fit: FitResult, profile=None, profile_running: bool = False) -> list[KaBlock]:
    """Every binding constant of *fit*, in the order the fit reports them.

    *profile* is the session's :class:`~core.pipeline.profile.ProfileSet` of this fit, from
    which the accepted stretches of a split interval are drawn; *profile_running* says it is
    still being computed. Without either, a split reading says in words why its stretches
    are not drawn.
    """
    rows = summarize_parameters(fit)
    specs = {s.key: s for s in rows if not s.is_log}
    keys = [s.key for s in rows if s.is_log]  # every binding constant has a log₁₀ twin
    conditional_only = reports_conditional(fit)
    reported = reading(fit)[0]
    blocks = []
    for key in keys:
        s = specs[key]
        unit = fmt_unit_pretty(s.unit)
        level = f'{s.level * 100:g}{THIN}% interval' if s.level else 'Interval'
        value, qualifier = headline_value(s.estimate, s.estimate_at_bound, s.interval, s.interval_open)
        if s.interval is None:
            legacy = fit.intervals is None
            why = 'not recorded in this result' if legacy else 'fixed, not fitted'
            blocks.append(
                KaBlock(
                    key, fmt_param(key), value, unit, level, why, LEGACY_NOTE if legacy else '', qualifier=qualifier
                )
            )
            continue
        tooltip = ' '.join(
            [
                *([_sentence(UNSOLVABLE_NOTE)] if any(s.interval_unsolvable) else []),
                *([one_step_sentence(fmt_param_plain(key), s.one_step_p)] if s.one_step_p is not None else []),
                *widening_sentences([s], fit, fmt_param_plain),
            ]
        )
        curve = None if profile is None else profile.profiles.get(key)
        aware = reported == INPUT_AWARE
        # The Input-aware reading's stretches are those of its own penalised profile.
        own_curve = curve if curve is None or not aware else (getattr(curve, 'aware', None) or curve)
        readings = [
            (
                reported,
                'accent' if aware else 'text-secondary',
                s.estimate,
                s.estimate_at_bound,
                s.interval,
                s.interval_open,
                s.interval_split,
                own_curve,
            )
        ]
        ratio = None
        if not conditional_only and s.conditional_interval is not None:
            readings.append(
                (
                    AS_ENTERED,
                    'text-secondary',
                    s.conditional_estimate,
                    s.conditional_at_bound,
                    s.conditional_interval,
                    s.conditional_open,
                    s.conditional_split,
                    curve,
                )
            )
            (a_lo, a_hi), (e_lo, e_hi) = s.interval, s.conditional_interval
            if e_hi > e_lo > 0 and a_hi > a_lo > 0:
                ratio = math.log(a_hi / a_lo) / math.log(e_hi / e_lo)
        # One power of ten for the numbers written: an open end or an estimate on a
        # bound sits at the search box, is written in words and sets none.
        written = [
            value_
            for _l, _c, est, at_bound, (lo, hi), open_, _s, _p in readings
            for value_, shown in ((est, not at_bound), (lo, not open_[0]), (hi, not open_[1]))
            if shown
        ]
        # The axis spans what is written; a side left open runs on past it, where the
        # search box ends decades away, so its bar is drawn to the axis's edge.
        middle = math.sqrt(s.interval[0] * s.interval[1])
        lo_axis = min(written or [middle]) / 1.25
        hi_axis = max(written or [middle]) * 1.25
        if any(r[5][0] for r in readings):
            lo_axis /= 3
        if any(r[5][1] for r in readings):
            hi_axis *= 3
        e = shared_power(written or [middle])

        def clip(segments: list[tuple[float, float]]) -> list[tuple[float, float]]:
            return [(max(a, lo_axis), min(b, hi_axis)) for a, b in segments if b >= lo_axis and a <= hi_axis]

        def fmt(v: float) -> str:
            return fmt_value(v) if e is None else fmt_value(v / 10.0**e)

        chart_rows = []
        for label, color, est, at_bound, (lo, hi), open_, split, reading_curve in readings:
            estimate = fmt_estimate(est, at_bound, (lo, hi), open_, fmt, html=False)
            row = {
                'label': label,
                'color': color,
                'segments': [(lo, hi)],
                'est': None if at_bound else est,
                'text': estimate if at_bound else f'{estimate}  {fmt_interval_plain(fmt(lo), fmt(hi), *open_)}',
            }
            if split:
                row['badge'] = SPLIT
                if reading_curve is not None:
                    row['segments'] = accepted_stretches(
                        reading_curve.grid, reading_curve.r2, reading_curve.r2_cut, lo, hi
                    )
                else:
                    # Words in place of the bars, and no estimate mark on a line with no bars.
                    row['segments'], row['est'] = [], None
                    row['note'] = (
                        'Stretches appear once the Kₐ profile is ready'
                        if profile_running
                        else 'No Kₐ profile, so the stretches are not drawn'
                    )
            row['segments'] = clip(row['segments'])
            if row['est'] is not None and not lo_axis <= row['est'] <= hi_axis:
                row['est'] = None
            chart_rows.append(row)
        blocks.append(
            KaBlock(
                key,
                fmt_param(key),
                value,
                unit,
                level,
                headline_interval(*s.interval, *s.interval_open, unit),
                tooltip,
                chart_rows,
                lo_axis,
                hi_axis,
                [(tick, tick_label(tick, e)) for tick in nice_ticks(lo_axis, hi_axis)],
                e,
                ratio,
                qualifier,
                SPLIT_FOOTNOTE if s.interval_split or s.conditional_split else '',
            )
        )
    return blocks


def interval_caption(fit: FitResult, blocks: Sequence[KaBlock]) -> str:
    """What made the Input-aware interval differ from the one at the inputs as entered, from the fit's record.

    The inputs moved where the fit records shifts of them, and a stated random error of
    each addition widens the cut-off where the fit records one; a noise law reads alike in
    both intervals, so it explains a difference only beside the additions, which take over
    part of the scatter it would otherwise carry.
    """
    if reports_conditional(fit):
        return (
            'Every input was taken as entered and no error of the additions was stated, so this fit has one interval.'
        )
    ratios = [b.ratio for b in blocks if b.ratio is not None]
    narrower = any(r < 0.95 for r in ratios)
    wider = any(r > 1.05 for r in ratios)
    moved = bool(fit.input_shifts)
    additions = ErrorModel.from_dict(fit.fit_config).additions is not None
    if wider and not narrower:
        cause = {
            (True, False): 'Letting the inputs move within what you stated widens',
            (False, True): 'The random error of each addition you stated widens',
            (True, True): 'Letting the inputs move within what you stated and the random error of each addition widen',
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


def replicate_line(fit: FitResult) -> tuple[str, str]:
    """The binding constants' single-replicate fits as one HTML line under the headline, and its tooltip.

    ``Single-replicate fits (inputs as entered, 4 replicates): Kₐ guest median 1.20 × 10⁶,
    range [1.00 × 10⁶, 1.40 × 10⁶] M⁻¹`` — each replicate the fit used, fitted on its own with
    the inputs as entered. A fit that ran to a bound of its Ka search box is no value of Ka:
    it is counted (``1 of 4 at a search bound``) and left out of the median and range. The
    tooltip says how the figures shown relate to the interval beside them, and why a count
    stands in for a figure. ``('', '')`` where the fit has no single-replicate fits.
    """
    rows = summarize_parameters(fit)
    ka = [s for s in rows if not s.is_log and any(t.is_log and t.key == s.key for t in rows)]
    n = len(fit_replica_ids(fit) or ())
    parts, figures, summarised, unsummarised = [], False, False, False
    for spec in ka:
        stats, count = spec.replicates, spec.replicates_at_bound
        if stats is None and not count:
            continue
        text = fmt_param(spec.key)
        if stats is not None:
            figures = True
            span = f'[{fmt_value(stats["min"])}, {fmt_value(stats["max"])}]'
            text += f' median {fmt_value(stats["median"])}, range {span} {fmt_unit_html(spec.unit)}'.rstrip()
        if count:
            summarised |= stats is not None
            unsummarised |= stats is None
            text += f'{"," if stats is not None else ":"} {count} of {n} at a search bound'
        parts.append(text)
    if not parts:
        return '', ''
    line = f'Single-replicate fits (inputs as entered, {n} replicate{"" if n == 1 else "s"}): {"; ".join(parts)}'
    tip = [REPLICATES_RELATION] if figures else []
    if summarised or unsummarised:
        tip.append(
            'A replicate whose own fit ran to a bound of its search range has no value of that constant, so it is '
            + {
                (True, False): 'counted and left out of the median and range.',
                (False, True): 'counted, and too few values are left for a median and range.',
                (True, True): 'counted and left out of the median and range; where too few values are left, none '
                'is shown.',
            }[summarised, unsummarised]
        )
    return line, ' '.join(tip)


# ---------------------------------------------------------------------------
# The summary beside the title and the callouts
# ---------------------------------------------------------------------------


def badge(fit: FitResult | None, ms) -> str | None:
    """The summary beside the title: the reading reported and the replicates it rests on, ``Input-aware · 7 of 8 replicates``."""
    if fit is None:
        return None
    used = fit_replica_ids(fit)
    if used is None:
        return reading(fit)[0]
    order = replica_order(fit, None if ms is None else ms.replica_ids)
    total = len(order) if order is not None else len(input_replica_ids(fit) or used)
    n = len(used)
    count = f'{n} replicate{"" if n == 1 else "s"}' if n == total else f'{n} of {total} replicates'
    return f'{reading(fit)[0]} · {count}'


class Place(Enum):
    """A place in a session's views that a link, a callout's action or a refusal takes the user to.

    :meth:`gui.fitting_session.FittingSession.reveal` shows it: its view on screen, the
    section holding it open, scrolled to the top of its scroll area, focused and marked.
    """

    #: Measurements' concentration grid, its first point open for typing.
    CONCENTRATIONS = 'concentrations'
    #: The headline of Fit results.
    FIT = 'fit'
    #: Diagnostics in Fit details.
    DIAGNOSTICS = 'diagnostics'
    #: The two readings of each binding constant in Ka confidence.
    READINGS = 'readings'
    #: The input shifts in the Notes of Ka confidence.
    SHIFTS = 'shifts'
    #: The inputs table of Input uncertainty.
    INPUTS = 'inputs'
    #: The first problem Binding model shows, with the setting it is about.
    BINDING_PROBLEM = 'binding problem'
    #: The first problem Input uncertainty shows, with the setting it is about.
    INPUT_PROBLEM = 'input problem'
    #: The problem beside the settings of the next sensitivity run.
    ANALYSIS_PROBLEM = 'analysis problem'


@dataclass(frozen=True)
class CalloutSpec:
    """One callout of the canvas (DESIGN.md §5): ``warning`` or ``neutral``, a title, a body and an optional
    action, which takes the user to *place*."""

    tone: str
    title: str
    body: str
    action: str = ''
    place: Place | None = None


#: The action of the conflict callout, which shows the two readings in Ka confidence.
REVIEW = 'Review in Ka confidence'


def callouts(
    fit: FitResult | None,
    note: str | None,
    *,
    others: Sequence[FitResult] = (),
    order: Sequence[str] | None = None,
    unchecked: bool = False,
    others_hidden: str | None = None,
) -> list[CalloutSpec]:
    """The callouts of the fit on view, *fit*, drawn beside the fits *others*.

    *note* hides the fit (:meth:`~gui.session_model.SessionModel.mismatch_note`), and is
    then the only thing said about it. Otherwise: a conflict of the inputs, as one
    statement about them together; a curve that misses the data by more than their scatter
    allows, at the fit reported or — where the inputs do not conflict, which says it
    already — only at the inputs as entered, as
    :func:`~core.pipeline.diagnostics.rejections` judges them; *unchecked* for numbers that
    could not be checked against data; *others_hidden* for held fits not drawn; the numbers
    of the *others* (:func:`other_fits_note`); and, with *order* the loaded data's replicates,
    where the fits drawn used different replicates (:func:`differing_replicates_note`).
    """
    if note is not None:
        return [CalloutSpec('neutral', 'Results hidden', note)]
    out = []
    diagnostics = None if fit is None else fit.diagnostics
    if diagnostics is not None:
        from core.pipeline.diagnostics import rejections

        rejected = rejections(diagnostics.conditional_misfit, diagnostics.misfit, diagnostics.conflict)
        if 'conflict' in rejected:
            out.append(
                CalloutSpec(
                    'warning',
                    'Inputs conflict',
                    'Together, the inputs moved further from their entered values than you stated.',
                    REVIEW,
                    Place.READINGS,
                )
            )
        if 'misfit' in rejected:
            where = ' even with the inputs moved' if fit.input_shifts else ''
            out.append(
                CalloutSpec(
                    'warning',
                    'Curve misses the data',
                    f'The curve misses the data by more than their scatter allows{where}. Try another binding model, '
                    'or check the data.',
                )
            )
        elif 'conditional_misfit' in rejected and fit.input_shifts and 'conflict' not in rejected:
            out.append(
                CalloutSpec(
                    'warning',
                    'Misfit at inputs as entered',
                    'At the entered inputs the curve misses the data; it fits once the inputs move within what you '
                    'stated.',
                )
            )
    if unchecked:
        out.append(CalloutSpec('neutral', 'Not checked', UNCHECKED_NOTE))
    if others_hidden:
        out.append(CalloutSpec('neutral', 'Fits hidden', others_hidden))
    drawn = [*others, fit] if fit is not None else []
    others_note = other_fits_note(drawn)
    if others_note:
        out.append(CalloutSpec('neutral', 'Other fits shown', others_note))
    replicates_note = None if order is None else differing_replicates_note(drawn, order)
    if replicates_note:
        out.append(CalloutSpec('neutral', 'Different replicates', replicates_note))
    return out


# ---------------------------------------------------------------------------
# The titration plot
# ---------------------------------------------------------------------------


def differing_replicates_note(fits: Sequence[FitResult], order: Sequence[str]) -> str | None:
    """A plain note when overlaid fits used different replicates, naming each set; otherwise ``None``.

    The mean and SD follow the last fit, the one the headline reports.
    """
    if len(fits) < 2:
        return None
    reported = fit_replica_ids(fits[-1]) or []
    used = [fit_replica_ids(fit) or [] for fit in fits[:-1]]
    others = [ids for ids in used if set(ids) != set(reported)]
    if not others:
        return None
    other_names = '; '.join(describe_replicates(ids, order) for ids in others)
    return (
        f'Mean ± SD is over {describe_replicates(reported, order)}, the ones the reported fit used. '
        f'{"Another fit" if len(others) == 1 else "Other fits"} shown used {other_names}.'
    )


def fit_numbers(fit: FitResult) -> str:
    """One fit's numbers in a line of plain text: each binding constant with its reading and interval, then R².

    ``Kₐ guest 1.59 × 10⁸ M⁻¹ (Input-aware), 95 % interval 1.14 – 2.08 × 10⁸ M⁻¹; R² 0.9980``.
    Where the curve is drawn at the inputs the fit moved, the line says so.
    """
    reported = reading(fit)[0]
    parts = []
    for block in ka_blocks(fit):
        parts.append(f'{block.plain_name} {block.plain_value} ({reported}), {block.level} {block.interval}')
    parts.append(f'R² {fmt_r2(fit.r_squared)}')
    line = '; '.join(parts)
    return f'{line}; {SHIFTED_CURVE_NOTE}' if fit.input_shifts else line


#: The action of Measurements' fit cue, which shows the headline of Fit results.
SHOW_FIT = 'Show fit results'


def fit_cue(fit: FitResult | None, note: str | None, fit_running: bool) -> str | None:
    """What Measurements says above its raw titration of the fit shown, or ``None`` where it says nothing.

    ``Kₐ guest 1.59 × 10⁸ M⁻¹ — the fitted curve is in Fit results.`` Nothing with no fit,
    while *note* hides it, or while a fit runs: the value would then describe no fit on
    view.
    """
    if fit is None or note is not None or fit_running:
        return None
    values = and_join(f'{block.plain_name} {block.plain_value}' for block in ka_blocks(fit))
    return f'{values} — the fitted curve is in Fit results.' if values else 'The fitted curve is in Fit results.'


def other_fits_note(shown: Sequence[FitResult]) -> str | None:
    """The numbers of every shown fit but the reported one (the last), whose curves the plot draws dashed; ``None`` for one fit."""
    others = list(shown[:-1])
    if not others:
        return None
    if len(others) == 1:
        return f'The dashed curve is another fit shown with the reported one: {fit_numbers(others[0])}.'
    listed = ' '.join(f'Fit {i}: {fit_numbers(fit)}.' for i, fit in enumerate(others, start=1))
    return f'The dashed curves are other fits shown with the reported one. {listed}'


def figure_summary(shown: Sequence[FitResult], ms) -> list[str]:
    """What a saved titration states under its head: the reported fit — the last of *shown* — and any other.

    One line per binding constant with the reading reported and its interval, then R² and
    the replicates used (*ms* the data loaded, or ``None``); each other fit, whose curve is
    drawn dashed, in a line of its numbers.
    """
    if not shown:
        return []
    fit, reported = shown[-1], reading(shown[-1])[0]
    lines = [
        f'{block.plain_name} {block.plain_value} ({reported}), {block.level} {block.interval}'
        for block in ka_blocks(fit)
    ]
    q = quality(fit, ms)
    used = '' if q.used == _NO_VALUE else f' · Replicates used {q.used}' + (f' ({q.used_note})' if q.used_note else '')
    lines.append(f'R² {q.r2}{used}')
    if len(shown) > 1:
        lines[0] = f'Reported fit: {lines[0]}'
    lines += [f'Other fit {i} (dashed): {fit_numbers(other)}' for i, other in enumerate(shown[:-1], start=1)]
    return lines


@dataclass(frozen=True)
class Titration:
    """What the titration plot of Fit results shows: its data, legend row and description, and what its saved figure adds.

    The legend names each replicate drawn by its letter, ``(kind, text, index)`` with its
    place in the data's order, so it is marked in the replicate's own colour. *summary* is what a saved figure
    states under its head, where the view on screen has the headline and Fit details
    (:func:`figure_summary`).
    """

    data: TitrationData | None
    legend: list[tuple]
    description: str = ''
    summary: list[str] = field(default_factory=list)


def _curve_legend(n: int) -> list[tuple[str, str]]:
    """The legend of *n* fitted curves: the reported one, and the others drawn dashed."""
    if n == 0:
        return []
    if n == 1:
        return [('line', 'Fit')]
    others = 'Other fit' if n == 2 else f'Other fits ({n - 1})'
    return [('line', 'Reported fit'), ('line-other', others)]


def titration(ms, shown: Sequence[FitResult], assay_type: AssayType, display: int = 0) -> Titration:
    """The titration plot of the loaded data with the curves of the *shown* fits.

    The replicates the reported fit (the last shown) used are drawn as replicates and
    averaged into the mean ± SD; a replicate switched off, and one the fit left out of
    itself, are drawn as ×. Each replicate is drawn and named in the legend by its place in
    the order the app names them A, B, … (:func:`~core.pipeline.reporting.replica_order`),
    which with the data loaded is the data's own. The reported fit's curve is drawn solid, any other shown
    fit's dashed, with every fit's numbers in the saved figure's :attr:`Titration.summary`
    and the others' in the callouts (:func:`callouts`). With no fit shown every active replicate is drawn and
    averaged. Without data, the shown curves alone. *display* is the index of
    :data:`REPLICATE_DISPLAYS`.
    """
    x_name = ASSAY_REGISTRY[assay_type].x_label
    replicates, mean = display in (0, 2), display in (0, 1)
    shifted = SHIFTED_CURVE_NOTE if shown and shown[-1].input_shifts else ''
    summary = figure_summary(shown, ms)
    if ms is None:
        if not shown:
            return Titration(None, [])
        x = np.asarray(shown[-1].x_fit.magnitude, dtype=float)
        curves = [(np.asarray(r.x_fit.magnitude, float), np.asarray(r.y_fit.magnitude, float)) for r in shown]
        data = TitrationData(x, np.empty((0, x.size)), [], x_name, curves=curves[-1:], other_curves=curves[:-1])
        return Titration(data, _curve_legend(len(curves)), shifted, summary=summary)
    plot = prepare_plot_data(ms, list(shown), show_dropped=True)
    order = list(ms.replica_ids)
    used = {rid for rid, _ in plot['active_replicas']}
    letters = {rid: _display_label(i) for i, rid in enumerate(order)}
    off = {rid for rid, _ in plot['dropped_replicas']}
    left_out = {rid for rid, _ in plot['left_out_replicas']}
    curves = [(np.asarray(f['x'], float), np.asarray(f['y'], float)) for f in plot['fits']]
    data = TitrationData(
        x_molar=np.asarray(ms.concentrations, dtype=float),
        signals=np.asarray(ms.signals, dtype=float),
        active=[rid in used for rid in order],
        x_name=x_name,
        mean_sd=mean,
        curves=curves[-1:],
        replicates=replicates,
        other_curves=curves[:-1],
        replicate_ids=order,
    )
    legend: list[tuple] = []
    if replicates:
        for index, rid in enumerate(order):
            if rid in off:
                legend.append(('cross', f'{letters[rid]} switched off', index))
            elif rid in left_out:
                legend.append(('cross', f'{letters[rid]} left out by the fit', index))
            else:
                legend.append(('dots', letters[rid], index))
    if mean and used:
        legend.append(('mean', 'Mean ± SD'))
    legend += _curve_legend(len(curves))
    return Titration(data, legend, shifted, summary)


# ---------------------------------------------------------------------------
# Fit details: Fit quality
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Quality:
    """Fit quality as Fit details states it: four stats, each a value with an optional note.

    *used* is ``7 of 8``; *used_note* names the replicates the fit did not use and why
    (``A switched off``); *left_out* gives each replicate the fit left out of itself with
    the reason it records. *noise* is the noise law in a few characters (:func:`noise_stat`)
    with its *noise_note* and, as *noise_tooltip*, the law's own sentence; *noise* is
    ``None`` for a calibration line, which is fitted with no noise law.
    """

    r2: str
    rmse: str
    used: str
    used_note: str
    left_out: str
    noise: str | None
    noise_note: str = ''
    noise_tooltip: str = ''


def noise_stat(law) -> tuple[str, str, str]:
    """A noise law as the Noise stat reads it: value, note and tooltip.

    ``0.6 % + 80 a.u.`` — the proportional part and the constant floor of one replicate's
    noise — from replicate scatter; a constant law reads its floor alone (``80 a.u.``) and a
    proportional one its percentage. Where no law could be read the value says so, the note
    says why, and the tooltip is :meth:`~core.pipeline.noise.NoiseLaw.describe`.
    """
    from core.pipeline.noise import NoiseBasis

    if law is None:
        return _NO_VALUE, 'not recorded in this result', ''
    tooltip = _sentence(law.describe().rstrip('.')) + '.'
    if not law.estimated:
        why = 'one titration' if law.basis is NoiseBasis.SINGLE_TITRATION else 'too few scattered points'
        return 'Not estimated', why, tooltip
    floor = f'{fmt_sci(law.floor, 2)} {fmt_unit_pretty("au")}'
    percent = f'{100.0 * law.proportional:.1f} %'
    value = {0.0: floor, 1.0: percent}.get(law.share, f'{percent} + {floor}')
    return value, 'from replicate scatter', tooltip


def _replica_name(replica_id: str | None, order: Sequence[str] | None) -> str:
    """One replicate's display label: its letter in Measurements, or its id in quotes where *order* lacks it.

    An id is a label from the data file, often a number; quoted, ``'0' left out`` reads as a
    name rather than a count.
    """
    order = list(order or ())
    if replica_id in order:
        return _display_label(order.index(replica_id))
    return _NO_VALUE if replica_id is None else f"'{replica_id}'"


def quality(fit: FitResult, ms) -> Quality:
    """R², RMSE, the replicates used and the noise of *fit*, with *ms* the data loaded (or ``None``)."""
    order = replica_order(fit, None if ms is None else ms.replica_ids)
    used, given = fit_replica_ids(fit), input_replica_ids(fit)
    if used is None or given is None:
        counted, note, left = _NO_VALUE, '', ''
    else:
        everything = order if order is not None else given
        counted = f'{len(used)} of {len(everything)}'
        off = [rid for rid in everything if rid not in given]
        out = [rid for rid in given if rid not in used]
        parts = []
        if off:
            parts.append(f'{and_join(_replica_name(r, order) for r in off)} switched off')
        if out:
            parts.append(f'{and_join(_replica_name(r, order) for r in out)} left out by the fit')
        note = ' · '.join(parts)
        failures = fit.metadata.get('replica_failures') or {}
        left = ' '.join(f'{_replica_name(rid, order)} — {failures.get(rid, "left out of the fit.")}' for rid in out)
    noise = (None, '', '') if fit.assay_type == AssayType.DYE_ALONE.name else noise_stat(fit.noise)
    return Quality(fmt_r2(fit.r_squared), fmt_rmse(fit.rmse), counted, note, left, *noise)


def column_power(values: Sequence[float]) -> int | None:
    """The power of ten a table column of *values* states in its header, or ``None`` where none serves them all.

    That of the smallest value, so each reads as a mantissa from 1 to 999 — ``3.56``, ``139``,
    ``32.8`` under ``10³`` — and none as a ``0.0…`` that would be taken for another number.
    Each value is taken as written, to three significant figures, so 999.6 counts as the
    1.00 × 10³ it is written as. Where the largest would need four or more digits under
    that power — its power of ten three or more above the smallest's — each value is
    written in full.
    """
    powers = [math.floor(math.log10(float(f'{v:.3g}'))) for v in values]
    return min(powers) if max(powers) - min(powers) <= 2 else None


def _p_cell(p: float | None) -> str:
    """A replicate's p-value in its table cell as :func:`~gui.plotting.labels.fmt_p` writes it, without the ``p``:
    ``0.55``, ``< 0.001``, ``> 0.99`` — escaped, since a cell is rich text and reads ``< 0.001`` as a tag."""
    if p is None:
        return _NO_VALUE
    return escape(fmt_p(p).removeprefix('p = ').removeprefix('p '))


def replicate_rows(fit: FitResult, ms) -> tuple[list[str], list[list[str]], list[str]]:
    """The replicates' own fits, for a fit of each replicate separately: headers, rows and a tooltip per row.

    One row per replicate the fit was given: its letter — with *left out* under it where
    the fit left it out — its own fit of each binding constant (in words where it ran to a
    bound of its search box), and its p-value in the test of whether every replicate shares
    the binding constants: none where the set was too small to test or the replicate was
    left out for its scatter. The row's tooltip gives the R² of its own fit and, for one
    left out, the reason. The numbers of one binding constant share the power of ten in its
    header where :func:`column_power` finds one; with the narrow columns this keeps the table
    inside the side panel at its least width. Empty for a fit of the average.
    """
    fits = fit.replica_fits
    if not fits:
        return [], [], []
    order = replica_order(fit, None if ms is None else ms.replica_ids)
    used = set(fit_replica_ids(fit) or ())
    p_values = (fit.metadata.get('replicate_test') or {}).get('p_values') or {}
    failures = fit.metadata.get('replica_failures') or {}
    keys = [s.key for s in summarize_parameters(fit) if s.is_log]
    own = [{s.key: s for s in summarize_parameters(rf) if not s.is_log} for rf in fits]
    powers = {}
    for key in keys:
        numbers = [rows[key].estimate for rows in own if key in rows and not rows[key].estimate_at_bound]
        powers[key] = column_power(numbers) if numbers else None
    # A header is painted as plain text, so the binding constants are named in plain text,
    # the shared power and the unit on a line of their own to keep the column narrow.
    headers = ['Replicate']
    for key in keys:
        power = '' if not powers[key] else f'10{superscript(powers[key])} '
        headers.append(f'{fmt_param_plain(key)}\n({power}{fmt_unit_pretty(_unit(fit, key))})')
    headers.append('p')
    rows, tips = [], []
    for rf in fits:
        rid = rf.metadata.get('replica_id')
        name = escape(_replica_name(rid, order))
        cells = []
        for key in keys:
            e = powers[key]
            fmt = fmt_value if e is None else (lambda v, e=e: fmt_value(v / 10.0**e))
            cells += [text for text in own_estimates(rf, [key], html=True, fmt=fmt)]
        rows.append([name if rid in used else f'{name}<br>left out', *cells, _p_cell(p_values.get(rid))])
        tip = f'R² of its own fit {fmt_r2(rf.r_squared)}.'
        tips.append(tip if rid in used else f'{failures.get(rid, "Left out of the fit.")} {tip}')
    return headers, rows, tips


def _unit(fit: FitResult, key: str) -> str:
    value = fit.parameters.get(key)
    return str(value.units) if isinstance(value, Quantity) else ''


# ---------------------------------------------------------------------------
# Fit details: Diagnostics
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TestRow:
    """One test of a fit as a diagnostics list shows it: its mark, what it found and its p-value.

    *text* is what the test found; for a test that was not run, that and why. *tooltip* is
    the test's full sentence, statistic included.
    """

    name: str
    icon: str
    tone: str
    text: str
    p: str
    tooltip: str = ''


def test_rows(fit: FitResult) -> list[TestRow]:
    """Each test of *fit*, judged as :func:`~core.pipeline.diagnostics.rejections` judges them; ``[]`` without diagnostics.

    Where the fit was free to move an input the misfit test is reported at both fits and the
    test of the inputs against what was stated is listed; otherwise the one misfit test at the
    inputs as entered. A test that was not run reads so, with the reason
    :attr:`~core.pipeline.diagnostics.FitDiagnostics.skipped` records. Each row's tooltip is
    its full sentence: the misfit test with its statistic, and the test of the inputs with
    what it says about them together and where the fit put each — never naming one input as
    the cause.
    """
    from core.pipeline.diagnostics import rejections

    diagnostics = fit.diagnostics
    if diagnostics is None:
        return []
    shifts = fit.input_shifts or {}
    moved = bool(shifts)
    rejected = rejections(diagnostics.conditional_misfit, diagnostics.misfit, diagnostics.conflict)
    entered = 'Fit with the inputs as entered' if moved else 'Fit at the entered inputs'
    tests = []
    if moved:
        tests.append(
            (
                'misfit',
                diagnostics.misfit,
                'Curve fits with inputs moved',
                'Curve misses with inputs moved',
                'Fit with the inputs free to move',
            )
        )
    tests.append(
        (
            'conditional_misfit',
            diagnostics.conditional_misfit,
            'Curve fits at inputs as entered',
            'Misfit at inputs as entered',
            entered,
        )
    )
    if moved:
        tests.append(('conflict', diagnostics.conflict, 'Inputs agree with what you stated', 'Inputs conflict', ''))
    out = []
    for name, test, passed, failed, which in tests:
        if test is None:
            kind = 'conflict' if name == 'conflict' else 'misfit'
            # A result that records no reason is read from what was stated, as the report reads it.
            fallback = (
                (
                    'conflict',
                    'no_informed_direction' if any(s.z is not None for s in shifts.values()) else 'no_uncertainty',
                )
                if kind == 'conflict'
                else ('misfit', 'too_few_dof')
            )
            reason = not_run_reason(diagnostics, kind) or NOT_RUN[fallback]
            # With both fits listed, each misfit row says which fit it is about, as a row that ran does.
            where = {'misfit': ' with inputs moved', 'conditional_misfit': ' at inputs as entered'}.get(name, '')
            subject = 'Inputs' if kind == 'conflict' else 'Curve'
            text = f'{subject} not tested{where if moved else ""}: {reason}.'
            tooltip = f'{which}: not tested, because {reason}.' if which else text
            out.append(TestRow(name, 'info', 'text-tertiary', text, _NO_VALUE, tooltip))
            continue
        if name == 'conflict':
            p = fmt_p(test.p_value)
            labels = result_input_labels(fit.assay_type, fit.fit_config)
            tooltip = _inputs_line(diagnostics, shifts, labels)
        else:
            p = fmt_test_p(test)
            tooltip = f'{which}: {fmt_misfit(test)}.'
        tone = ('alert-circle', 'warning', failed) if name in rejected else ('check-circle', 'success', passed)
        out.append(TestRow(name, *tone, p, tooltip))
    return out


def _inputs_line(diagnostics, shifts: dict, labels: dict[str, str]) -> str:
    """What the conflict statistic says about the inputs together, then where the fit put each.

    The shifts say where the fit put the correction, never which input is wrong: the
    statistic weighs the inputs together.
    """
    k = diagnostics.conflict.k
    return (
        f'Inputs, taken together: q = {fmt_stat(diagnostics.conflict.q)} across {k} '
        f'direction{"" if k == 1 else "s"} the data inform, {fmt_p(diagnostics.conflict.p_value)}. '
        f'Shifts: {fmt_shifts(shifts, labels, html=False)}. They show where the fit put the correction, '
        'not which input is wrong.'
    )


# ---------------------------------------------------------------------------
# Fit details: Parameters and Input shifts
# ---------------------------------------------------------------------------


#: The total each model holds fixed whose mass balance can tie its signal parameters, and the
#: species letter of that component: the dye where the dye is not titrated, the host in the
#: stepwise models (CLAUDE.md, Scientific conventions).
_HELD_TOTAL = {
    AssayType.IDA.name: ('dye', 'D'),
    AssayType.DBA_HtoD.name: ('dye', 'D'),
    AssayType.DBA_HG2.name: ('host', 'H'),
    AssayType.DBA_H2G.name: ('host', 'H'),
}


def _held_total(fit: FitResult) -> str | None:
    """The total whose mass balance ties the starred parameters of *fit*, ``'dye'`` or ``'host'``; ``None`` for none.

    The balance ties the offset to every coefficient of a species holding that component; it
    is named only where the fit starred every one of them. A parameter starred for another
    reason — a species the fitted constants leave unpopulated, or a stepwise model with the
    free host's coefficient pinned — is not one of the balance.
    """
    held = _HELD_TOTAL.get(fit.assay_type)
    if held is None:
        return None
    word, component = held
    meta = ASSAY_REGISTRY[AssayType[fit.assay_type]]
    offsets = [key for key, kind in meta.param_kinds.items() if kind is ParamKind.SIGNAL_OFFSET]
    tied = {*offsets, *(key for key, species in meta.signal_species.items() if component in species)}
    return word if tied <= set(fit.degenerate_keys or ()) else None


def parameter_rows(fit: FitResult) -> tuple[list[list[str]], list[str], str]:
    """Each fitted parameter as Fit details lists it — name, estimate, unit — the tooltip of each name, and the footnote.

    An estimate on an end of its Ka search box reads in words. A parameter the data
    determine only in combination with others is starred; the footnote says so in one
    sentence naming the total the model holds fixed where its balance ties them
    (:func:`_held_total`), ``* Not separately determined while the dye total is fixed.``, and
    each starred name's tooltip says what that means. The
    footnote is ``''`` where nothing is starred.
    """
    specs = [s for s in summarize_parameters(fit) if not s.is_log]
    starred = [s for s in specs if s.degenerate]
    note = degenerate_note([fmt_param(s.key) for s in starred], _FIT_DEGENERATE_TAIL) if starred else ''
    cells, tips = [], []
    for s in specs:
        estimate = fmt_estimate(s.estimate, s.estimate_at_bound, s.interval, s.interval_open, html=True)
        # The words of an estimate on its search bound stand on a line above the number, which keeps its line.
        estimate = estimate.replace('</i> ', '</i><br>')
        name = fmt_param(s.key) + (' *' if s.degenerate else '')
        cells.append([name, estimate, fmt_unit_html(s.unit) if s.unit else _NO_VALUE])
        tips.append(note if s.degenerate else '')
    if not starred:
        return cells, tips, ''
    held = _held_total(fit)
    footnote = f'while the {held} total is fixed' if held else 'by these data'
    return cells, tips, f'* Not separately determined {footnote}.'


def parameter_notes(fit: FitResult) -> list[str]:
    """What Parameters says under its table besides the footnote: a file that records no interval of its binding
    constants and how to get one, a signal parameter the fit ended on an entered bound, and a signal offset held
    at zero under a curve that misses the data."""
    legacy = LEGACY_NOTE if fit.intervals is None and any(s.is_log for s in summarize_parameters(fit)) else ''
    return [text for text in (legacy, fmt_bound_note(parameters_on_bound(fit)), offset_note(fit)) if text]


@dataclass(frozen=True)
class ShiftRow:
    """One input the fit was free to move: its name, its shift in σ (``None`` for a range), the % and the tooltip.

    *note* is where an input stated as a range rests — ``at the edge of its range`` or
    ``inside its range`` — shown in place of the bar, which a range without σ has none of;
    ``''`` for an input stated with a σ.
    """

    name: str
    z: float | None
    percent: str
    tooltip: str
    note: str = ''


def shifts_footnote(rows: Sequence[ShiftRow]) -> str:
    """The footnote of Input shifts: where the correction went, never which input is wrong.

    The bars are explained only where one is drawn; an input stated as a range has no σ
    and so no bar.
    """
    if not rows:
        return 'Every input was taken as entered, so the fit moved none of them.'
    meaning = 'where the fit put the correction, not which input is wrong.'
    if any(row.z is not None for row in rows):
        return f'Bars in σ, band ±1 σ. They show {meaning}'
    return f'The shifts show {meaning}'


def shift_rows(fit: FitResult) -> list[ShiftRow]:
    """Where the fit put each input it was free to move, largest ``|z|`` first, ranges after them.

    The % is the shift from the entered value; the tooltip says it in σ, or where an input
    stated as a range rests. The order is :func:`~gui.plotting.labels.shift_order`'s, so it
    is the order every report lists them in.
    """
    labels = result_input_labels(fit.assay_type, fit.fit_config)
    out = []
    for shift in sorted((fit.input_shifts or {}).values(), key=shift_order):
        note = ''
        if shift.z is not None:
            tip = f'{shift.z:+.1f} σ'.replace('-', '−')
        else:
            note = fmt_against(shift) or 'inside its range'
            tip = f'Stated as a range, so there is no σ; {note}.'
        out.append(ShiftRow(input_name(shift.key, labels), shift.z, fmt_percent(shift.fraction), tip, note))
    return out
