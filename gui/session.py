"""Session-level helpers: JSON/TXT/CSV export and import of fit results, plot image export."""

from __future__ import annotations

import csv
import json
import textwrap
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Sequence

from core.pipeline.fit_pipeline import (
    FitResult,
    ParameterSummary,
    fit_replica_ids,
    input_replica_ids,
    parameters_on_bound,
    summarize_parameters,
)
from core.units import Quantity
from gui.plotting.labels import SPLIT_NOTE, fmt_bound_note, fmt_interval_plain, fmt_log10, fmt_r2, fmt_unit_pretty
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
    """One number of *spec*'s row as the text report writes it.

    A log₁₀ row goes through :func:`~gui.plotting.labels.fmt_log10`, the same
    rule the summary table on screen follows, so a value is never written
    coarser than the interval or the replicate spread printed beside it: four
    significant figures would turn 8.496983 ± 0.000096 into 8.497 ± 9.6e-05.
    """
    return fmt_log10(value, spec.replicates) if spec.is_log else f'{value:.4g}'


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
    are in the stored base units, named per row in the ``unit`` column. The
    interval columns are filled for every binding constant the fit was free to
    move — its endpoints, whether each side is open, whether an open side is
    open because the binding model has no solution past it, and whether the
    accepted values come in separate stretches — and the replicate columns for
    every parameter whose own fits at least
    two replicates contributed. RMSE and R² are measured against the average of
    the replicates the fit used, listed (``;``-separated) with the ones it left
    out; both are blank when the result does not record its replicates.

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
        'degenerate',
        'replicate_median',
        'replicate_min',
        'replicate_max',
        'n_replicates',
        'rmse',
        'r_squared',
        'replicates_used',
        'replicates_left_out',
    )

    def flag(value: bool) -> str:
        return 'true' if value else 'false'

    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        for index, result in enumerate(results):
            record = _replicate_record(result, replica_ids)
            used, left_out = ('', '') if record is None else (';'.join(record[0]), ';'.join(n for n, _ in record[1]))
            n_used = len(fit_replica_ids(result) or ())
            intervals = result.intervals or {}
            for spec in summarize_parameters(result):
                ci = spec.interval
                dof = intervals[spec.key].dof if spec.key in intervals else None
                across = spec.replicates
                writer.writerow(
                    [
                        index,
                        result.assay_type,
                        result.source_file or '',
                        _row_label(spec),
                        # Log rows are dimensionless; the row they log is in
                        # the same file, so its unit is one lookup away.
                        '' if spec.is_log else spec.unit,
                        f'{spec.estimate:.6e}',
                        *(
                            ('',) * 9
                            if ci is None
                            else (
                                f'{ci[0]:.6e}',
                                f'{ci[1]:.6e}',
                                *map(flag, spec.interval_open),
                                *map(flag, spec.interval_unsolvable),
                                *spec.interval_limited_by,
                                flag(spec.interval_split),
                            )
                        ),
                        '' if spec.level is None else f'{spec.level:g}',
                        '' if dof is None else dof,
                        flag(spec.degenerate),
                        *(
                            ('', '', '', '')
                            if across is None
                            else (f'{across["median"]:.6e}', f'{across["min"]:.6e}', f'{across["max"]:.6e}', n_used)
                        ),
                        f'{result.rmse:.6e}',
                        f'{result.r_squared:.6f}',
                        used,
                        left_out,
                    ]
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
        values = [f'{float(own.parameters[key].magnitude):.4g}' if key in own.parameters else '—' for key in ka_keys]
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
                'data cannot tell apart from that fit, cut from the fit’s own profile by an F test.'
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
                        _fmt_report(spec, spec.estimate),
                        _interval_cell(spec, result, ka_keys),
                        _row_unit(spec),
                    )
                    for spec in specs
                ],
            )
        )
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

        replicates_block = _replicates_block(result, replica_ids)
        lines.extend(replicates_block)

        # Fit quality
        lines.append('FIT QUALITY')
        lines.append('-' * 60)
        lines.append(f'  RMSE:          {result.rmse:.4g} {fmt_unit_pretty("au")}')
        lines.append(f'  R²:            {fmt_r2(result.r_squared)}')
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
            for cond_key, cond_val in result.conditions.items():
                if isinstance(cond_val, Quantity):
                    lines.append(f'  {cond_key}: {cond_val:.4g~P}')
                else:
                    lines.append(f'  {cond_key}: {cond_val}')
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
    - Style template: always available (style widget is always present).

    While every held result is hidden, the result artefacts give the note
    hiding them as the reason, as the window's own export actions do.
    """
    state = session._state
    ms_loaded = state.measurement_set is not None
    has_results = bool(state.fit_results)
    has_sensitivity = state.sensitivity_result is not None and state.sensitivity_note is None
    # The Identifiability tab is cleared by an import of results fitted elsewhere,
    # so what it has to save is a question for the tab, not for the held results.
    has_identifiability = session._identifiability_widget.has_chart()

    no_data_msg = 'Load a measurement file first.'
    no_fit_msg = session.hidden_results_note() or 'Run a fit first.'
    no_identifiability_msg = session.hidden_results_note() or 'Run a fit in this session first.'
    no_sensitivity_msg = state.sensitivity_note or 'Run a sensitivity analysis first.'

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
