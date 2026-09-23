"""Session-level helpers: JSON/TXT/CSV export and import of fit results, plot image export."""

from __future__ import annotations

import csv
import json
import math
import textwrap
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Sequence

from core.assays.registry import AssayType
from core.pipeline.diagnostics import MisfitTest
from core.pipeline.fit_pipeline import (
    FitResult,
    ParameterSummary,
    fit_replica_ids,
    input_replica_ids,
    parameters_on_bound,
    summarize_parameters,
)
from core.pipeline.inputs import TITRANT_STOCK, ErrorModel, InputSpec, SpecKind, shared_key
from core.pipeline.sensitivity import SensitivityMode
from core.units import Quantity
from gui.plotting.export import ExportRefused
from gui.plotting.labels import (
    NO_UNCERTAINTY,
    NOT_RUN,
    SPLIT_NOTE,
    fmt_against,
    fmt_bound_note,
    fmt_concentration,
    fmt_estimate,
    fmt_interval_plain,
    fmt_log10,
    fmt_misfit,
    fmt_p,
    fmt_percent,
    fmt_r2,
    fmt_sci,
    fmt_stat,
    fmt_unit_pretty,
    fmt_value,
    not_run_reason,
    own_estimates,
    replicate_summary,
    stated_uncertainty,
    verdict_headline,
    verdict_sentence,
)
from gui.widgets.assay_conditions import result_input_labels
from gui.widgets.replica_panel import _display_label

if TYPE_CHECKING:
    from gui.fitting_session import FittingSession


def export_results(results: list[FitResult], path: str | Path) -> None:
    """Export a list of FitResult objects to a JSON file.

    Parameters
    ----------
    results : list[FitResult]
        Fit results to export.
    path : str or Path
        Output file path (should have ``.json`` extension).
    """
    path = Path(path)
    data = [r.to_dict() for r in results]
    path.write_text(json.dumps(data, indent=2))


def import_results(path: str | Path) -> list[FitResult]:
    """Import fit results from a JSON file created by :func:`export_results`.

    Parameters
    ----------
    path : str or Path
        Path to the JSON file.

    Returns
    -------
    list[FitResult]
        Reconstructed FitResult objects.
    """
    path = Path(path)
    raw = json.loads(path.read_text())
    if isinstance(raw, dict):
        raw = [raw]
    return [FitResult.from_dict(d) for d in raw]


#: Said of a result that carries no interval for a binding constant it reports.
_NO_INTERVAL_NOTE = (
    'This result comes from a file written by an earlier version of SupraSimFit, which reported an estimate '
    'without a confidence interval. Fit the data again to get the interval.'
)

#: What a starred row means, in the words the summary table on screen uses.
_DEGENERATE_NOTE = (
    'The data fix only a combination of the starred values, not each one on its own: many different sets of '
    'them draw the same curve. Each starred value is one member of that family. It reconstructs the fitted '
    'curve correctly and is not a measurement of that one coefficient.'
)

#: What to do about an interval the data leave open, per side, in the words the
#: Identifiability tab uses.
_OPEN_ADVICE = {
    'low': ('the data cannot rule out a lower Ka. Points at a higher titrant concentration would pin it down.'),
    'high': (
        'the data cannot rule out a higher Ka. Points taken before the signal levels off, or a lower fixed '
        'concentration, would pin it down.'
    ),
}

#: Said of a side the binding model cannot be solved past. The edge is where the
#: arithmetic stops, not where the data stop, so more points cannot move it.
_UNSOLVABLE_NOTE = (
    'the binding model has no solution past this value, so the profile stops there rather than at a limit the '
    'data set. More measurements cannot close this side.'
)

#: Said of a side that closes only because the other binding constant has
#: reached its bound. The limit is a property of that bound, so it is named with
#: the value it produces and not reported as one.
_LIMITED_BY_NOTE = (
    'the fit is rejected beyond {edge} only because {other} cannot go past its bound there; the data alone set no '
    'limit on this side. If you know {other}, hold it at that value under Parameter Bounds (equal lower and upper '
    'bound); otherwise only data that determine it close this side.'
)


def _replicate_record(
    result: FitResult, replica_ids: Sequence[str] | None
) -> tuple[list[str], list[tuple[str, str]]] | None:
    """The replicates *result* used and those it left out, with the reason, as the user names them.

    A replicate is named by its display label (A, B, …) when *replica_ids*, the
    loaded data's replicate order, holds every replicate the result names, and
    by its id otherwise. ``None`` when the result does not record its replicates.
    """
    used = fit_replica_ids(result)
    if used is None:
        return None
    given = input_replica_ids(result) or used
    reasons = result.metadata.get('replica_failures') or {}
    left_out = [rid for rid in given if rid not in used]
    named = list(dict.fromkeys([*used, *given]))
    order = list(replica_ids or ())
    if all(rid in order for rid in named):
        name = {rid: _display_label(order.index(rid)) for rid in named}
    else:
        name = {rid: rid for rid in named}
    return [name[rid] for rid in used], [(name[rid], reasons.get(rid, '')) for rid in left_out]


def _replicate_names(result: FitResult, replica_ids: Sequence[str] | None) -> dict[str, str]:
    """Every replicate *result* names, mapped to the name the user reads for it."""
    given = input_replica_ids(result) or fit_replica_ids(result) or []
    order = list(replica_ids or ())
    if given and all(rid in order for rid in given):
        return {rid: _display_label(order.index(rid)) for rid in given}
    return {rid: rid for rid in given}


def _row_label(spec: ParameterSummary) -> str:
    """Plain-text row label; log twins are named ``log10(<key>)``."""
    return f'log10({spec.key})' if spec.is_log else spec.key


def _row_unit(spec: ParameterSummary) -> str:
    """Unit shown for a row.

    A log₁₀ value is dimensionless, but the number is only meaningful against
    the unit its parameter was measured in — so the row names that reference
    rather than dropping it.
    """
    if not spec.unit:
        return '—'
    pretty = fmt_unit_pretty(spec.unit)
    return f'log10({pretty})' if spec.is_log else pretty


def _fmt_report(spec: ParameterSummary, value: float) -> str:
    """One number of *spec*'s row as the text report writes it, the way the summary table on screen writes it.

    A log₁₀ row goes through :func:`~gui.plotting.labels.fmt_log10`, so a
    value is never written coarser than the spread of the replicates' own
    fits: four significant figures would turn 8.496983 ± 0.000096 into 8.497 ±
    9.6e-05. Every other number goes through
    :func:`~gui.plotting.labels.fmt_value`.
    """
    return fmt_log10(value, spec.replicates) if spec.is_log else fmt_value(value)


def _estimate_text(spec: ParameterSummary, value: float, interval, open_ends, at_bound: str) -> str:
    """An estimate as the report writes it: its value, or in words where it sits on an end of its Ka search box."""
    return fmt_estimate(value, at_bound, interval, open_ends, lambda number: _fmt_report(spec, number), html=False)


def _ka_keys(specs: list[ParameterSummary]) -> set[str]:
    """Keys of the binding constants among *specs*: the rows that carry a log₁₀ twin."""
    return {spec.key for spec in specs if spec.is_log}


def _interval_cell(spec: ParameterSummary, result: FitResult, ka_keys: set[str]) -> str:
    """The interval column of one row: the interval, ``fixed`` for a pinned Ka, ``—`` for anything else."""
    if spec.interval is not None:
        low, high = spec.interval
        return fmt_interval_plain(
            _fmt_report(spec, low), _fmt_report(spec, high), spec.interval_open[0], spec.interval_open[1]
        )
    if spec.key in ka_keys and result.intervals is not None:
        # The fit was given equal bounds for this constant, so it was held at
        # one value and there is nothing for the data to bracket.
        return 'fixed'
    return '—'


#: Said above the per-Ka line that reports the interval with every input taken as entered.
_CONDITIONAL_NOTE = (
    'The interval above covers the input uncertainties stated below; the one here takes every input exactly as entered.'
)

#: Said after the reason the inputs were not tested against what was stated:
#: the shifts are reported, and what they mean for the entered values is not
#: something the fit can say.
_NOT_TESTED_TAIL = (
    'Where the fit put each shift is above; whether the inputs are right is not something this fit can say.'
)


def _input_uncertainty_block(result: FitResult) -> list[str]:
    """The INPUT UNCERTAINTY table: what was stated per source and where the fit put it.

    One row per input with an uncertainty of its own, then one per source
    several inputs share, which the label names with the inputs it moves.
    Empty for a fit that took every input as entered, which has no source to
    report and no shift to show.
    """
    errors = ErrorModel.from_dict(result.fit_config)
    specs = errors.specs
    if not specs and not errors.shared:
        return []
    labels = result_input_labels(result.assay_type, result.fit_config)
    stated: list[tuple[str, InputSpec]] = list(specs.items())
    stated += [(shared_key(source.name), InputSpec.sigma_pct(source.sigma_pct)) for source in errors.shared]
    rows: list[tuple[str, ...]] = []
    for key, spec in stated:
        unit = str(result.conditions[key].units) if isinstance(result.conditions.get(key), Quantity) else ''
        shift = result.input_shifts.get(key)
        if shift is None:
            moved, against = '—', '—'
        else:
            # The same percentage and σ the summary block and the plot show.
            moved, against = fmt_percent(shift.fraction), fmt_against(shift) or '—'
        rows.append(
            (labels.get(key, key), stated_uncertainty(spec, fmt_unit_pretty(unit) if unit else ''), moved, against)
        )

    lines = ['INPUT UNCERTAINTY', '-' * 60]
    lines.extend(
        _wrapped(
            'The fit was free to move each input inside the uncertainty stated for it, and the interval it '
            'reports covers that freedom. Where it put each one is below, as a percentage of the value entered '
            'and against the uncertainty stated for it.'
        )
    )
    if errors.shared:
        lines.extend(
            _wrapped(
                'A shared source is one error several inputs have in common — one stock, balance or pipette '
                'behind all of them — and it moves every input it applies to by the same percentage.'
            )
        )
    lines.append('')
    lines.extend(_fixed_width_table(('Source', 'Stated', 'Shift', 'Against what was stated'), rows))
    lines.append('')
    return lines


#: The two conditions that say how the samples were made rather than what is in
#: them: a report names them in one sentence instead of printing their keys.
_DILUTION_KEYS = (TITRANT_STOCK, 'stock_contains')


def _conditions_lines(result: FitResult) -> list[str]:
    """The entered conditions, named as the Assay Configuration panel names them and in the unit they read in.

    A concentration reads in the largest unit the form offers that leaves it
    at 1 or more, and a binding constant in M⁻¹ with ``×10ⁿ`` notation, both
    to the four figures an entered value is read back to, so no key and no
    ``1/M`` reaches the report. A condition the panel has no label
    for — one a newer file carries — is named by its key rather than left out.
    """
    labels = result_input_labels(result.assay_type, result.fit_config)
    lines = []
    for key, value in result.conditions.items():
        if key in _DILUTION_KEYS:
            continue
        if isinstance(value, Quantity):
            if value.check('[concentration]'):
                text = fmt_concentration(value)
            else:
                text = f'{fmt_sci(float(value.magnitude), 4)} {fmt_unit_pretty(str(value.units))}'.rstrip()
        else:
            text = str(value)
        lines.append(f'  {labels.get(key, key)}: {text}')
    return lines


def _dilution_lines(result: FitResult) -> list[str]:
    """How the titrant diluted the sample, as the CONDITIONS block states it; empty when the totals stayed constant."""
    stock = result.conditions.get(TITRANT_STOCK)
    if not isinstance(stock, Quantity):
        return []
    lines = [f'  Titrant stock: {fmt_concentration(stock)}; fixed concentrations diluted by each addition']
    contains = tuple(result.conditions.get('stock_contains') or ())
    if contains:
        labels = result_input_labels(result.assay_type, result.fit_config)
        lines.append(f'  also in the stock: {", ".join(labels.get(key, key) for key in contains)}')
    return lines


#: Width the MODEL AND INPUTS lines label their test in, so the statistics line up.
_TEST_LABEL_WIDTH = 32


def _misfit_line(diagnostics, test: MisfitTest | None) -> str:
    """One misfit test as the report quotes it, or why there was none to run."""
    if test is None:
        return f'not tested — {not_run_reason(diagnostics, "misfit")}.'
    return fmt_misfit(test)


def _model_and_inputs_block(result: FitResult) -> list[str]:
    """The MODEL AND INPUTS block: what the tests say about the model and about the entered inputs.

    Empty for a result that carries no diagnostics — an assay with no
    association constant, or a file written before they were reported.
    """
    diagnostics = result.diagnostics
    if diagnostics is None:
        return []
    labels = result_input_labels(result.assay_type, result.fit_config)
    lines = ['MODEL AND INPUTS', '-' * 60]
    lines.append(f'  Verdict: {verdict_headline(diagnostics)[0]}.')
    lines.extend(_wrapped(verdict_sentence(diagnostics, result.input_shifts, labels, html=False)))
    lines.append('')
    lines.append(
        f'  {"Model at the entered inputs:":<{_TEST_LABEL_WIDTH}}'
        f'{_misfit_line(diagnostics, diagnostics.conditional_misfit)}'
    )
    if result.input_shifts:
        lines.append(
            f'  {"Model with the inputs moved:":<{_TEST_LABEL_WIDTH}}{_misfit_line(diagnostics, diagnostics.misfit)}'
        )
    conflict = diagnostics.conflict
    specs = ErrorModel.from_dict(result.fit_config).source_specs()
    # What the block's readings are conditioned on, so a printed report says it
    # rather than leaving it to be inferred from a section that is not there.
    stated = 'stated above under INPUT UNCERTAINTY.' if specs else f'{NO_UNCERTAINTY}.'
    lines.append(f'  {"Input uncertainties used:":<{_TEST_LABEL_WIDTH}}{stated}')
    if conflict is not None:
        lines.append(
            f'  {"Inputs against what you stated:":<{_TEST_LABEL_WIDTH}}'
            f'q = {fmt_stat(conflict.q)}, {fmt_p(conflict.p_value)}'
        )
        lines.append('')
        directions = 'the one combination' if conflict.k == 1 else f'the {conflict.k} combinations'
        # q weighs the inputs stated with a standard deviation; a range enters it not at all.
        judged = sum(1 for shift in result.input_shifts.values() if shift.z is not None)
        if judged == 1:
            lines.extend(
                _wrapped(
                    f'q judges the stated input against what you said you knew, over {directions} these data '
                    'pin down. The shift says where the fit put the correction, not that this input is the one '
                    'that is off.'
                )
            )
        else:
            lines.extend(
                _wrapped(
                    f'q judges the stated inputs together, over {directions} of them these data pin down. '
                    'The shift on each input says where the fit put the correction, not which input is off.'
                )
            )
    elif specs:
        # A result that records no reason is read from what was stated: with
        # every uncertainty a range there is nothing stated with a σ to test.
        ranges = all(spec.kind is SpecKind.INTERVAL for spec in specs.values())
        recorded = not_run_reason(diagnostics, 'conflict')
        reason = recorded or NOT_RUN[('conflict', 'no_uncertainty' if ranges else 'no_informed_direction')]
        lines.append('')
        lines.extend(_wrapped(f'The inputs were not tested against what you stated: {reason}. {_NOT_TESTED_TAIL}'))
    lines.append('')
    return lines


def _fixed_width_table(headers: tuple[str, ...], rows: list[tuple[str, ...]]) -> list[str]:
    """Render *rows* as space-padded columns sized to their widest entry.

    The first column is left-aligned (names), the numeric middle columns are
    right-aligned, and the trailing column reads better left-aligned.
    """
    if not rows:
        return []
    widths = [max(len(headers[i]), max(len(row[i]) for row in rows)) for i in range(len(headers))]

    def render(cells: tuple[str, ...]) -> str:
        out = [f'  {cells[0]:<{widths[0]}}']
        out += [f'{cells[i]:>{widths[i]}}' for i in range(1, len(cells) - 1)]
        out.append(f'{cells[-1]:<{widths[-1]}}')
        return '   '.join(out).rstrip()

    header = render(headers)
    body = [render(row) for row in rows]
    rule = '  ' + '-' * (max(len(line) for line in (header, *body)) - 2)
    return [header, rule, *body]


def _wrapped(text: str, width: int = 74) -> list[str]:
    """*text* broken into lines of at most *width* characters, indented two spaces."""
    return [f'  {line}' for line in textwrap.wrap(text, width=width)]


def export_results_csv(results: list[FitResult], path: str | Path, *, replica_ids: Sequence[str] | None = None) -> None:
    """Export fit results as a tidy CSV — one row per reported parameter.

    Complements the TXT report: same numbers, but machine-readable so the
    values can go straight into a spreadsheet or a plotting script. Magnitudes
    are in the stored base units, named per row in the ``unit`` column.

    An empty cell is a number there is none of, never a stand-in for one. The
    interval columns are filled for every binding constant the fit was free to
    move: its ends, whether each side is open, whether an open side is open
    because the binding model has no solution past it, which other binding
    constant's bound ends it, and whether the accepted values come in separate
    stretches. The end of an open side is empty — the profile stopped at the
    search box there, which is not a limit — and ``ci_open_low`` /
    ``ci_open_high`` say so. An estimate that sits on an end of its Ka search
    box is empty too, and ``estimate_at_bound`` names the end (``low`` or
    ``high``): the value is the box, not a measurement. The results file (JSON)
    keeps every raw number, and these flags follow from it.

    Where the fit was free to move an input, the ``cond_`` columns carry the
    same binding constant with every input held as entered, under the same
    rules (``cond_estimate_at_bound``), and one row per source it could move
    carries where the fit put it: ``parameter`` is the source's key — the
    input's own key, and ``shared:<name>`` for a source several inputs share,
    listed after the inputs — ``unit`` is ``% of entered``, ``estimate`` the
    shift in percent, and ``input_z`` how many stated standard deviations that
    is (blank for an input stated as a range, where ``input_at_edge`` says
    whether the fit took it to an end of that range). Which inputs a shared
    source moves is in the TXT report and in the results file's
    ``fit_config``.

    The replicate columns summarise the own fits of the replicates the fit
    used, for every parameter at least two of them contributed to; a
    replicate whose own binding constant ran to a bound of its search box is
    not a value of it, is left out of the median and range, and is counted in
    ``replicates_at_bound``. RMSE and R² are measured against the average of
    the replicates the fit used, listed (``;``-separated) with the ones it
    left out; both lists are blank when the result does not record its
    replicates. The ``noise``, ``verdict``, ``misfit_p``, ``cond_misfit_p``,
    ``conflict_q`` and ``conflict_p`` columns describe the fit as a whole and
    repeat on every one of its rows; ``misfit_p`` is the misfit test of the
    fit the interval comes from and ``cond_misfit_p`` the one at the inputs
    exactly as entered. ``noise`` is the law the replicates showed, the one
    the fit weighted its titration points by, and is blank where the result
    records none.

    Parameters
    ----------
    results : list[FitResult]
        Fit results to export.
    path : str or Path
        Output file path (should have ``.csv`` extension).
    replica_ids : sequence of str, optional
        Replicate ids of the loaded data in their order, so replicates are named
        by their display labels; without it they are named by id.
    """
    path = Path(path)
    columns = (
        'result_index',
        'assay_type',
        'source_file',
        'parameter',
        'unit',
        'estimate',
        'estimate_at_bound',
        'ci_low',
        'ci_high',
        'ci_open_low',
        'ci_open_high',
        'ci_unsolvable_low',
        'ci_unsolvable_high',
        'ci_limited_by_low',
        'ci_limited_by_high',
        'ci_split',
        'ci_level',
        'ci_dof',
        'cond_estimate',
        'cond_estimate_at_bound',
        'cond_ci_low',
        'cond_ci_high',
        'cond_ci_open_low',
        'cond_ci_open_high',
        'cond_ci_split',
        'degenerate',
        'replicate_median',
        'replicate_min',
        'replicate_max',
        'n_replicates',
        'replicates_at_bound',
        'rmse',
        'r_squared',
        'noise',
        'replicates_used',
        'replicates_left_out',
        'verdict',
        'misfit_p',
        'cond_misfit_p',
        'conflict_q',
        'conflict_p',
        'input_z',
        'input_at_edge',
    )

    def flag(value: bool) -> str:
        return 'true' if value else 'false'

    def number(value: float) -> str:
        return f'{value:.6e}'

    def ends(interval, open_ends) -> tuple[str, str]:
        """The two ends of an interval, each empty where the data leave that side open."""
        return tuple('' if is_open else number(edge) for edge, is_open in zip(interval, open_ends))

    def diagnostic_cells(result: FitResult) -> dict[str, str]:
        """What the fit's diagnostics say, repeated on every row of that fit: they describe the fit, not a parameter.

        Both misfit tests are written. The verdict is read from the fit at the
        entered inputs as much as from the fit that reports the interval, so a
        reader of the table alone can see what it was read from.
        """
        diagnostics = result.diagnostics
        if diagnostics is None:
            return {}

        def p_value(test) -> str:
            return '' if test is None else f'{test.p_value:.6g}'

        cells = {
            'verdict': diagnostics.verdict.value,
            'misfit_p': p_value(diagnostics.misfit),
            'cond_misfit_p': p_value(diagnostics.conditional_misfit),
        }
        if diagnostics.conflict is not None:
            cells |= {
                'conflict_q': f'{diagnostics.conflict.q:.6e}',
                'conflict_p': f'{diagnostics.conflict.p_value:.6g}',
            }
        return cells

    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, columns, restval='')
        writer.writeheader()
        for index, result in enumerate(results):
            record = _replicate_record(result, replica_ids)
            used, left_out = ('', '') if record is None else (';'.join(record[0]), ';'.join(n for n, _ in record[1]))
            n_used = len(fit_replica_ids(result) or ())
            intervals = result.intervals or {}
            # The noise law describes the fit, like the verdict beside it, so it
            # repeats on every row of that fit; blank where none was recorded.
            whole_fit = {
                'result_index': index,
                'assay_type': result.assay_type,
                'source_file': result.source_file or '',
                'rmse': number(result.rmse),
                'r_squared': f'{result.r_squared:.6f}',
                'noise': '' if result.noise is None else result.noise.describe(),
                'replicates_used': used,
                'replicates_left_out': left_out,
                **diagnostic_cells(result),
            }
            for spec in summarize_parameters(result):
                row = {
                    **whole_fit,
                    'parameter': _row_label(spec),
                    # Log rows are dimensionless; the row they log is in the
                    # same file, so its unit is one lookup away.
                    'unit': '' if spec.is_log else spec.unit,
                    'estimate': '' if spec.estimate_at_bound else number(spec.estimate),
                    'estimate_at_bound': spec.estimate_at_bound,
                    'ci_level': '' if spec.level is None else f'{spec.level:g}',
                    'degenerate': flag(spec.degenerate),
                }
                if spec.interval is not None:
                    low, high = ends(spec.interval, spec.interval_open)
                    row |= {
                        'ci_low': low,
                        'ci_high': high,
                        'ci_open_low': flag(spec.interval_open[0]),
                        'ci_open_high': flag(spec.interval_open[1]),
                        'ci_unsolvable_low': flag(spec.interval_unsolvable[0]),
                        'ci_unsolvable_high': flag(spec.interval_unsolvable[1]),
                        'ci_limited_by_low': spec.interval_limited_by[0],
                        'ci_limited_by_high': spec.interval_limited_by[1],
                        'ci_split': flag(spec.interval_split),
                    }
                if spec.key in intervals:
                    # Residual degrees of freedom: a whole number where every
                    # input was held as entered, and a fraction where the fit
                    # was free to move one, since an input the data pin down
                    # takes a residual degree of freedom with it.
                    row['ci_dof'] = f'{intervals[spec.key].dof:.6g}'
                if spec.conditional_interval is not None:
                    low, high = ends(spec.conditional_interval, spec.conditional_open)
                    row |= {
                        'cond_estimate': '' if spec.conditional_at_bound else number(spec.conditional_estimate),
                        'cond_estimate_at_bound': spec.conditional_at_bound,
                        'cond_ci_low': low,
                        'cond_ci_high': high,
                        'cond_ci_open_low': flag(spec.conditional_open[0]),
                        'cond_ci_open_high': flag(spec.conditional_open[1]),
                        'cond_ci_split': flag(spec.conditional_split),
                    }
                if spec.replicates is not None:
                    across = spec.replicates
                    row |= {
                        'replicate_median': number(across['median']),
                        'replicate_min': number(across['min']),
                        'replicate_max': number(across['max']),
                        'n_replicates': n_used,
                    }
                if spec.replicates_at_bound:
                    row['replicates_at_bound'] = spec.replicates_at_bound
                writer.writerow(row)
            # One row per source the fit was free to move: where it put that
            # source, in percent of the value entered, and how far that is
            # against the uncertainty stated for it. The source is named by its
            # key, as every other row of the column is, so a reader can join an
            # input to the condition of that name; the TXT report gives the
            # names, a shared source's inputs included. The interval,
            # conditional and replicate columns describe a fitted parameter;
            # an input has none.
            for key, shift in result.input_shifts.items():
                writer.writerow(
                    {
                        **whole_fit,
                        'parameter': key,
                        'unit': '% of entered',
                        'estimate': number(100 * shift.fraction),
                        'input_z': '' if shift.z is None else number(shift.z),
                        'input_at_edge': flag(shift.at_edge),
                    }
                )


def _replicates_block(result: FitResult, replica_ids: Sequence[str] | None) -> list[str]:
    """The REPLICATES table: each replicate's own fit, its p-value in the shared-Ka test, and whether it was used.

    Empty unless the fit ran per replicate and recorded the replicates' own
    fits; a fit of one averaged signal has nothing to compare.
    """
    fits = {rf.metadata.get('replica_id'): rf for rf in result.replica_fits or ()}
    if not fits:
        return []
    names = _replicate_names(result, replica_ids)
    given = input_replica_ids(result) or list(fits)
    used = set(fit_replica_ids(result) or ())
    reasons = result.metadata.get('replica_failures') or {}
    test = result.metadata.get('replicate_test') or {}
    p_values = test.get('p_values') or {}
    ka_keys = [spec.key for spec in summarize_parameters(result) if spec.is_log]

    headers = ('Replicate', *(f'own {key}' for key in ka_keys), 'own R²', 'p-value', 'In the fit')
    rows: list[tuple[str, ...]] = []
    for rid in given:
        own = fits.get(rid)
        if own is None:
            continue
        values = own_estimates(own, ka_keys, html=False)
        p = p_values.get(rid)
        rows.append(
            (
                names.get(rid, rid),
                *values,
                fmt_r2(own.r_squared),
                '—' if p is None else f'{p:.2g}',
                'used' if rid in used else 'left out',
            )
        )
    if not rows:
        return []

    lines = ['REPLICATES', '-' * 60]
    lines.extend(
        _wrapped(
            'Each replicate fitted on its own. The reported fit is the fit of the average of the replicates '
            'marked used.'
        )
    )
    if test:
        lines.extend(
            _wrapped(
                f'A replicate is left out when its own fit needs a different Ka than the others share, at a '
                f'{test.get("level", 0.01):g} level shared across the {len(given)} replicates given.'
            )
        )
    lines.append('')
    lines.extend(_fixed_width_table(headers, rows))
    for rid in given:
        if rid in used or rid not in reasons:
            continue
        lines.append('')
        lines.extend(_wrapped(f'{names.get(rid, rid)} left out: {reasons[rid]}'))
    lines.append('')
    return lines


def export_results_txt(results: list[FitResult], path: str | Path, *, replica_ids: Sequence[str] | None = None) -> None:
    """Export fit results as a human-readable text report.

    The report holds the fitted parameters with their intervals, the
    replicates' own fits, the fit quality and the conditions entered. A fit
    that was free to move an input inside a stated uncertainty adds the
    interval conditional on the inputs exactly as entered, a table of what was
    stated for each input and where the fit put it, and what the misfit tests
    and the conflict statistic say about the model and those inputs.

    Parameters
    ----------
    results : list[FitResult]
        Fit results to export (typically a single-element list).
    path : str or Path
        Output file path (should have ``.txt`` extension).
    replica_ids : sequence of str, optional
        Replicate ids of the loaded data in their order, so the report names
        replicates by their display labels; without it they are named by id.
    """
    path = Path(path)
    lines: list[str] = []

    lines.append('=' * 60)
    lines.append('FIT RESULTS REPORT')
    lines.append('=' * 60)
    lines.append(f'Generated: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")}')
    lines.append('')

    for i, result in enumerate(results):
        if len(results) > 1:
            lines.append(f'--- Result {i + 1} of {len(results)} ---')
            lines.append('')

        # Header
        lines.append(f'Assay type:  {result.assay_type}')
        lines.append(f'Model:       {result.model_name}')
        if result.source_file:
            lines.append(f'Source file: {result.source_file}')
        lines.append(f'Timestamp:   {result.timestamp}')
        lines.append('')

        specs = summarize_parameters(result)
        ka_keys = _ka_keys(specs)
        level = next((spec.level for spec in specs if spec.level is not None), None)
        heading = 'Interval' if level is None else f'{level:.0%} interval'

        lines.append('FITTED PARAMETERS')
        lines.append('-' * 60)
        lines.extend(
            _wrapped(
                'Estimate = the least-squares fit of the data. Interval = the range of a binding constant the '
                'data cannot tell apart from that fit, cut from the fit’s own profile by an F test. Where an '
                'input was given an uncertainty, the fit was free to move it inside that uncertainty and the '
                'interval covers that freedom.'
            )
        )
        if ka_keys and result.intervals is None:
            lines.extend(_wrapped(_NO_INTERVAL_NOTE))
        lines.append('')
        lines.extend(
            _fixed_width_table(
                ('Parameter', 'Estimate', heading, 'Units'),
                [
                    (
                        f'{_row_label(spec)}{" *" if spec.degenerate else ""}',
                        _estimate_text(spec, spec.estimate, spec.interval, spec.interval_open, spec.estimate_at_bound),
                        _interval_cell(spec, result, ka_keys),
                        _row_unit(spec),
                    )
                    for spec in specs
                ],
            )
        )
        conditional = [spec for spec in specs if not spec.is_log and spec.conditional_interval is not None]
        if conditional:
            lines.append('')
            lines.extend(_wrapped(_CONDITIONAL_NOTE))
            for spec in conditional:
                low, high = spec.conditional_interval
                bracket = fmt_interval_plain(_fmt_report(spec, low), _fmt_report(spec, high), *spec.conditional_open)
                estimate = _estimate_text(
                    spec,
                    spec.conditional_estimate,
                    spec.conditional_interval,
                    spec.conditional_open,
                    spec.conditional_at_bound,
                )
                lines.append(
                    f'  Conditional on the entered inputs: {spec.key} = {estimate} {bracket} {_row_unit(spec)}'.rstrip()
                )
                if spec.conditional_split:
                    lines.extend(_wrapped(f'{spec.key} conditional on the entered inputs: {SPLIT_NOTE}'))
        replicates = replicate_summary(
            [spec for spec in specs if spec.key in ka_keys and not spec.is_log],
            len(fit_replica_ids(result) or ()),
            lambda spec: spec.key,
            lambda spec: fmt_unit_pretty(spec.unit),
        )
        if replicates:
            lines.append('')
            lines.extend(_wrapped(replicates))
        if any(spec.degenerate for spec in specs):
            lines.append('')
            lines.extend(_wrapped(f'* {_DEGENERATE_NOTE}'))
        for spec in specs:
            if spec.is_log or spec.interval is None:
                continue
            if spec.interval_split:
                lines.append('')
                lines.extend(_wrapped(f'{spec.key}: {SPLIT_NOTE}'))
            sides = zip(
                ('low', 'high'), spec.interval, spec.interval_open, spec.interval_unsolvable, spec.interval_limited_by
            )
            for side, edge, is_open, unsolvable, limited_by in sides:
                if not is_open:
                    continue
                lines.append('')
                if limited_by:
                    note = _LIMITED_BY_NOTE.format(
                        edge=f'{_fmt_report(spec, edge)} {_row_unit(spec)}'.strip(), other=limited_by
                    )
                else:
                    note = _UNSOLVABLE_NOTE if unsolvable else _OPEN_ADVICE[side]
                lines.extend(_wrapped(f'{spec.key}: open at the {side} end — {note}'))
        bound_note = fmt_bound_note(parameters_on_bound(result))
        if bound_note:
            lines.append('')
            lines.extend(_wrapped(bound_note))
        lines.append('')

        lines.extend(_input_uncertainty_block(result))
        lines.extend(_model_and_inputs_block(result))

        replicates_block = _replicates_block(result, replica_ids)
        lines.extend(replicates_block)

        # Fit quality
        lines.append('FIT QUALITY')
        lines.append('-' * 60)
        lines.append(f'  RMSE:          {result.rmse:.4g} {fmt_unit_pretty("au")}')
        lines.append(f'  R²:            {fmt_r2(result.r_squared)}')
        # A dye-alone calibration is a line fitted by fit_linear_assay, which
        # reads no noise law and needs none.
        if result.assay_type != AssayType.DYE_ALONE.name:
            noise = 'not recorded in this result.' if result.noise is None else result.noise.describe()
            lines.append(f'  Noise:         {noise}')
        record = _replicate_record(result, replica_ids)
        if record is None:
            lines.append('  Replicates:    not recorded in this result.')
        else:
            used, left_out = record
            lines.append(f'  Replicates used:      {", ".join(used)}')
            lines.append(f'  Left out of the fit:  {", ".join(name for name, _ in left_out) or "none"}')
            if not replicates_block:
                # The REPLICATES table gives each reason in full; without that
                # table this is the only place they can be read.
                for name, reason in left_out:
                    if reason:
                        lines.extend(_wrapped(f'{name} left out: {reason}'))
            lines.append('  RMSE and R² are measured against the average of the replicates used.')
        lines.append('')

        # Conditions
        if result.conditions:
            lines.append('CONDITIONS')
            lines.append('-' * 60)
            lines.extend(_conditions_lines(result))
            lines.extend(_dilution_lines(result))
            lines.append('')

        if i < len(results) - 1:
            lines.append('')

    lines.append('=' * 60)

    path.write_text('\n'.join(lines), encoding='utf-8')


# ---------------------------------------------------------------------------
# Multi-artefact export
# ---------------------------------------------------------------------------


@dataclass
class ExportableArtefact:
    """One thing the user can export in a batch.

    Attributes
    ----------
    key
        Stable identifier persisted under ``QSettings`` (e.g. ``raw_txt``).
    label
        Human-readable label shown in the dialog.
    suffix
        Filename suffix appended to the base, including the extension.
    available
        Whether the precondition for this artefact is currently met.
    unavailable_reason
        Tooltip text shown when ``available`` is False.
    writer
        Callable accepting a destination Path. Called only when the user
        selects this artefact and the precondition is met.
    """

    key: str
    label: str
    suffix: str
    available: bool
    unavailable_reason: str = ''
    writer: Callable[[Path], None] = field(default=lambda _p: None)


def build_artefacts(session: 'FittingSession') -> list[ExportableArtefact]:
    """Build the list of artefacts exportable from a FittingSession.

    Preconditions:
    - Raw data / fit curve plot: a measurement set is loaded.
    - Identifiability plot: the tab holds a chart.
    - Fit results (JSON/TXT/CSV): a result is shown; exported are the shown results.
    - Ka sensitivity plot: a sensitivity analysis is shown.
    - Ka uncertainty budget: the shown analysis reports sensitivity indices,
      which is what a budget is split from; a heatmap has none.
    - Style template: always available (style widget is always present).

    While every held result is hidden, the result artefacts give the note
    hiding them as the reason, as the window's own export actions do.
    """
    state = session._state
    ms_loaded = state.measurement_set is not None
    has_results = bool(state.fit_results)
    has_sensitivity = state.sensitivity_result is not None and state.sensitivity_note is None
    has_budget = has_sensitivity and state.sensitivity_result.mode is SensitivityMode.SOBOL
    # The Identifiability tab is cleared by an import of results fitted elsewhere,
    # so what it has to save is a question for the tab, not for the held results.
    has_identifiability = session._identifiability_widget.has_chart()

    no_data_msg = 'Load a measurement file first.'
    no_fit_msg = session.hidden_results_note() or 'Run a fit first.'
    no_identifiability_msg = session.hidden_results_note() or 'Run a fit in this session first.'
    no_sensitivity_msg = state.sensitivity_note or 'Run a sensitivity analysis first.'
    no_budget_msg = (
        no_sensitivity_msg
        if not has_sensitivity
        else 'The analysis shown is a heatmap. Run one with Sensitivity indices to get an uncertainty budget.'
    )

    from core.io.formats.measurement_writer import (
        write_measurements_csv,
        write_measurements_txt,
    )
    from gui.plotting.plot_style import save_style_json

    def _write_raw_txt(path: Path) -> None:
        write_measurements_txt(state.measurement_set, str(path))

    def _write_raw_csv(path: Path) -> None:
        write_measurements_csv(state.measurement_set, str(path))

    def _write_results_json(path: Path) -> None:
        export_results(state.fit_results, path)

    replica_ids = state.measurement_set.replica_ids if ms_loaded else None

    def _write_results_txt(path: Path) -> None:
        export_results_txt(state.fit_results, path, replica_ids=replica_ids)

    def _write_results_csv(path: Path) -> None:
        export_results_csv(state.fit_results, path, replica_ids=replica_ids)

    def _write_fit_plot(path: Path) -> None:
        session._plot_widget.export_image(str(path))

    def _write_identifiability(path: Path) -> None:
        session._identifiability_widget.export_image(str(path))

    def _write_sensitivity(path: Path) -> None:
        session._sensitivity_widget.export_image(str(path))

    def _write_budget_csv(path: Path) -> None:
        """The budget table as the Ka Sensitivity tab reports it, one row per source and Ka."""
        result = state.sensitivity_result
        budgets = (result.budget or {}).values()
        # A Sobol run always has a budget per binding constant; whether it holds
        # a number is the question, and a file of empty cells answers nothing.
        if result.budget and all((result.withheld or {}).get(key) for key in result.budget):
            raise ExportRefused(
                'This analysis gives no uncertainty budget: for every binding constant the Ka Sensitivity tab '
                'says why its numbers are withheld. See that tab.'
            )
        if not any(math.isfinite(budget.variance) for budget in budgets):
            raise ExportRefused(
                'This analysis reports no uncertainty budget: too few of its samples have a fit to split the '
                'spread of Ka between the sources. Run the analysis again.'
            )
        rows = session._sensitivity_widget.budget_rows()
        columns = list(dict.fromkeys(key for row in rows for key in row))
        with path.open('w', encoding='utf-8', newline='') as handle:
            writer = csv.DictWriter(handle, columns, restval='')
            writer.writeheader()
            writer.writerows(rows)

    def _write_style(path: Path) -> None:
        style = session._style_widget.widget.current_style()
        save_style_json(style, path)

    return [
        ExportableArtefact(
            key='raw_txt',
            label='Raw data (TXT)',
            suffix='_data.txt',
            available=ms_loaded,
            unavailable_reason=no_data_msg,
            writer=_write_raw_txt,
        ),
        ExportableArtefact(
            key='raw_csv',
            label='Raw data (CSV)',
            suffix='_data.csv',
            available=ms_loaded,
            unavailable_reason=no_data_msg,
            writer=_write_raw_csv,
        ),
        ExportableArtefact(
            key='results_json',
            label='Fit results (JSON)',
            suffix='_results.json',
            available=has_results,
            unavailable_reason=no_fit_msg,
            writer=_write_results_json,
        ),
        ExportableArtefact(
            key='results_txt',
            label='Fit results (TXT report)',
            suffix='_results.txt',
            available=has_results,
            unavailable_reason=no_fit_msg,
            writer=_write_results_txt,
        ),
        ExportableArtefact(
            key='results_csv',
            label='Fit results (CSV table)',
            suffix='_results.csv',
            available=has_results,
            unavailable_reason=no_fit_msg,
            writer=_write_results_csv,
        ),
        ExportableArtefact(
            key='fit_png',
            label='Fit curve plot (PNG)',
            suffix='_fit.png',
            available=ms_loaded,
            unavailable_reason=no_data_msg,
            writer=_write_fit_plot,
        ),
        ExportableArtefact(
            key='fit_svg',
            label='Fit curve plot (SVG)',
            suffix='_fit.svg',
            available=ms_loaded,
            unavailable_reason=no_data_msg,
            writer=_write_fit_plot,
        ),
        ExportableArtefact(
            key='identifiability_png',
            label='Identifiability plot (PNG)',
            suffix='_identifiability.png',
            available=has_identifiability,
            unavailable_reason=no_identifiability_msg,
            writer=_write_identifiability,
        ),
        ExportableArtefact(
            key='sensitivity_png',
            label='Ka sensitivity plot (PNG)',
            suffix='_sensitivity.png',
            available=has_sensitivity,
            unavailable_reason=no_sensitivity_msg,
            writer=_write_sensitivity,
        ),
        ExportableArtefact(
            key='budget_csv',
            label='Ka uncertainty budget (CSV)',
            suffix='_budget.csv',
            available=has_budget,
            unavailable_reason=no_budget_msg,
            writer=_write_budget_csv,
        ),
        ExportableArtefact(
            key='style_json',
            label='Style template (JSON)',
            suffix='_style.json',
            available=True,
            writer=_write_style,
        ),
    ]


def export_batch(
    arts: list[ExportableArtefact],
    folder: Path,
    base: str,
) -> list[tuple[str, Path, Exception | None]]:
    """Run a batch of artefact writers and report per-item outcomes.

    Returns a list of ``(label, path, error_or_None)`` tuples in the same
    order as ``arts``. Errors are caught so a single failure does not
    abort the rest of the batch — the caller surfaces them.
    """
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    outcomes: list[tuple[str, Path, Exception | None]] = []
    for art in arts:
        dest = folder / f'{base}{art.suffix}'
        try:
            art.writer(dest)
            outcomes.append((art.label, dest, None))
        except Exception as exc:
            outcomes.append((art.label, dest, exc))
    return outcomes
