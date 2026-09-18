"""Tests for the TXT report and CSV table exports in gui.session (no Qt required).

These guard the *reported* numbers, which are the point of the exports: the
estimate is a real fit and the interval beside it is that fit's own confidence
interval, an open side is written in words rather than as a number, a binding
constant that was held fixed says so instead of showing a made-up range, a file
that carries no interval says why, and log₁₀ rows are computed in log space.

The results are hand-built rather than fitted: each one pins one shape the
writers have to render (closed interval, open side, pinned Ka, no interval at
all, replicates with one left out), and building them directly is what lets a
single test hold exactly one of those shapes.
"""

from __future__ import annotations

import csv
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from core.pipeline.fit_pipeline import FitResult
from core.pipeline.varpro import KaInterval
from core.units import Q_
from gui.session import export_results_csv, export_results_txt

_X = np.linspace(1e-6, 5e-5, 10)

#: The fit every result below reports: one association constant and two signal
#: coefficients the IDA model determines only in combination.
_PARAMS = {'Ka_guest': Q_(1.24e6, '1/M'), 'I0': Q_(1000.0, 'au'), 'I_dye_free': Q_(5.0e4, 'au/M')}


def _result(
    *,
    interval: KaInterval | None = KaInterval(
        low=1.10e6, high=1.40e6, open_low=False, open_high=False, level=0.95, dof=7
    ),
    intervals_reported: bool = True,
    per_replicate: bool = False,
    metadata: dict | None = None,
    replica_fits: list[FitResult] | None = None,
) -> FitResult:
    """One reported fit.

    ``interval=None`` with ``intervals_reported`` leaves the binding constant
    pinned by equal bounds; ``intervals_reported=False`` is a result imported
    from a file written before intervals were reported.
    """
    intervals = None
    if intervals_reported:
        intervals = {} if interval is None else {'Ka_guest': interval}
    return FitResult(
        parameters=dict(_PARAMS),
        rmse=12.3,
        r_squared=0.9962,
        x_fit=Q_(_X, 'M'),
        y_fit=Q_(_X, 'au'),
        assay_type='IDA',
        model_name='equilibrium_4param',
        source_file='IDA_system.txt',
        fit_config={'per_replicate': per_replicate, 'level': 0.95},
        intervals=intervals,
        degenerate_keys=('I0', 'I_dye_free'),
        metadata=metadata or {},
        replica_fits=replica_fits,
    )


def _replica(rid: str, ka: float, r_squared: float) -> FitResult:
    """One replicate's own fit, as the pipeline records it under ``replica_fits``."""
    return FitResult(
        parameters={**_PARAMS, 'Ka_guest': Q_(ka, '1/M')},
        rmse=11.0,
        r_squared=r_squared,
        x_fit=Q_(_X, 'M'),
        y_fit=Q_(_X, 'au'),
        assay_type='IDA',
        model_name='equilibrium_4param',
        metadata={'replica_id': rid, 'active_replica_ids': [rid]},
    )


_EXCLUDED = (
    'Its own best fit needs a different Ka than the other replicates share '
    '(p = 0.0012; limit 0.01 shared across 3 replicates).'
)


def _per_replicate_result() -> FitResult:
    """A per-replicate fit of three replicates that left the third one out."""
    return _result(
        per_replicate=True,
        metadata={
            'active_replica_ids': ['a', 'b', 'c'],
            'replica_ids_fit': ['a', 'b'],
            'replica_failures': {'c': _EXCLUDED},
            'replicate_test': {'level': 0.01, 'p_values': {'a': 0.71, 'b': 0.44, 'c': 0.0012}},
        },
        replica_fits=[_replica('a', 1.20e6, 0.997), _replica('b', 1.30e6, 0.996), _replica('c', 4.00e6, 0.950)],
    )


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding='utf-8', newline='') as handle:
        return list(csv.DictReader(handle))


def _txt(tmp_path: Path, results: list[FitResult], **kwargs) -> str:
    path = tmp_path / 'r.txt'
    export_results_txt(results, path, **kwargs)
    return path.read_text(encoding='utf-8')


def _prose(text: str) -> str:
    """*text* with every run of whitespace collapsed, so a wrapped sentence reads as one."""
    return ' '.join(text.split())


def _table_rows(text: str, section: str) -> dict[str, str]:
    """The rows of the fixed-width table under *section*, keyed by their first cell."""
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(section))
    body = lines[start:]
    rule = next(i for i, line in enumerate(body) if set(line.strip()) == {'-'} and i >= 1)
    rows = {}
    for line in body[rule + 1 :]:
        if not line.startswith('  ') or not line.strip():
            break
        rows[line.split()[0]] = line
    return rows


def test_txt_report_puts_the_interval_beside_the_estimate(tmp_path: Path) -> None:
    """The headline table is estimate and interval; nothing claims a spread the fit does not have."""
    text = _txt(tmp_path, [_result()])

    for header in ('Parameter', 'Estimate', '95% interval', 'Units'):
        assert header in text
    line = next(ln for ln in text.splitlines() if ln.strip().startswith('Ka_guest'))
    assert '1.24e+06' in line
    assert '[1.1e+06, 1.4e+06]' in line


def test_txt_report_writes_an_open_side_in_words_and_says_what_would_close_it(tmp_path: Path) -> None:
    """A number at an open end would claim a bound the data do not give."""
    open_high = KaInterval(low=1.10e6, high=9.9e9, open_low=False, open_high=True, level=0.95, dof=7)
    text = _txt(tmp_path, [_result(interval=open_high)])

    assert '[1.1e+06, no upper limit]' in text
    assert '9.9e+09' not in text  # the bound the profile reached is not the interval's end
    assert 'the data cannot rule out a higher Ka' in text
    assert 'signal levels off' in text


def test_txt_report_does_not_ask_for_more_data_where_the_model_has_no_solution(tmp_path: Path) -> None:
    """An edge the arithmetic stops at cannot be moved by measuring more, so the advice would be wrong."""
    unsolvable = KaInterval(
        low=1.10e6, high=9.9e9, open_low=False, open_high=True, level=0.95, dof=7, unsolvable_high=True
    )
    text = _prose(_txt(tmp_path, [_result(interval=unsolvable)]))

    assert 'the binding model has no solution past this value' in text
    assert 'More measurements cannot close this side.' in text
    assert 'signal levels off' not in text


def test_txt_report_names_the_bound_a_side_rests_on_instead_of_reporting_a_limit(tmp_path: Path) -> None:
    """A crossing the other constant's bound produces is not a limit from the data, so it is not printed as one."""
    limited = KaInterval(
        low=2.3e2, high=1.40e6, open_low=True, open_high=False, level=0.95, dof=7, limited_by_low='Ka_HG2'
    )
    text = _prose(_txt(tmp_path, [_result(interval=limited)]))

    assert '[no lower limit, 1.4e+06]' in text
    assert 'only because Ka_HG2 cannot go past its bound' in text
    assert 'the data alone set no limit on this side' in text
    assert 'higher titrant concentration' not in text  # the advice for a side the data leave open does not apply


def test_txt_report_says_when_a_signal_parameter_ended_on_an_entered_bound(tmp_path: Path) -> None:
    """A curve held by a bound must not read as a plain fit; zero, the physical limit, is not a finding."""
    held = _result()
    held.fit_config['custom_bounds'] = {'I0': [0.0, 1000.0, 'au'], 'I_dye_free': [0.0, 1.0e9, 'au/M']}
    text = _prose(_txt(tmp_path, [held]))

    assert 'The fit ended on a bound entered under Parameter Bounds (I₀ at 1.0×10³ a.u.)' in text
    assert 'widen it and fit again' in text
    assert 'ended on a bound' not in _prose(_txt(tmp_path, [_result()]))


def test_txt_report_says_when_the_accepted_values_are_not_one_stretch(tmp_path: Path) -> None:
    """An interval that spans values the data reject must not read as a plain range."""
    split = KaInterval(low=1.10e6, high=1.40e6, open_low=False, open_high=False, level=0.95, dof=7, split=True)
    text = _prose(_txt(tmp_path, [_result(interval=split)]))

    assert 'come in separate stretches' in text
    assert 'come in separate stretches' not in _prose(_txt(tmp_path, [_result()]))


def test_txt_report_says_a_binding_constant_was_held_fixed(tmp_path: Path) -> None:
    """A pinned Ka has no interval to report, and an em dash would read as one that is missing."""
    text = _txt(tmp_path, [_result(interval=None)])

    line = next(ln for ln in text.splitlines() if ln.strip().startswith('Ka_guest'))
    assert 'fixed' in line


def test_txt_report_of_a_file_without_intervals_says_why_there_are_none(tmp_path: Path) -> None:
    text = _txt(tmp_path, [_result(intervals_reported=False)])

    assert 'without a confidence interval' in _prose(text)
    assert 'Fit the data again to get the interval.' in _prose(text)
    assert 'no upper limit' not in text


def test_txt_report_stars_the_parameters_the_data_fix_only_together(tmp_path: Path) -> None:
    text = _txt(tmp_path, [_result()])

    rows = _table_rows(text, '  Parameter')
    starred = [name for name, line in rows.items() if ' *' in line]
    assert starred == ['I0', 'I_dye_free']
    assert 'The data fix only a combination of the starred values' in _prose(text)


def test_txt_report_log_row_is_the_interval_read_on_a_log_scale(tmp_path: Path) -> None:
    """log₁₀ endpoints are the parameter's endpoints transformed, which is exact for a monotone map."""
    text = _txt(tmp_path, [_result()])
    line = next(ln for ln in text.splitlines() if ln.strip().startswith('log10(Ka_guest)'))

    lo, hi = np.log10([1.10e6, 1.40e6])
    assert f'{lo:.4g}' in line.replace('[', ' ').replace(',', ' ')
    assert f'{hi:.4g}' in line.replace(']', ' ')
    assert f'{np.log10(1.24e6):.4g}' in line


def test_txt_report_lists_every_replicate_with_its_own_fit_and_its_verdict(tmp_path: Path) -> None:
    """The replicate table is the between-replicate evidence; a left-out replicate is named with its reason."""
    text = _txt(tmp_path, [_per_replicate_result()], replica_ids=('a', 'b', 'c'))

    assert 'REPLICATES' in text
    rows = _table_rows(text, '  Replicate ')
    assert set(rows) == {'A', 'B', 'C'}
    assert '1.2e+06' in rows['A'] and rows['A'].endswith('used')
    assert '4e+06' in rows['C'] and rows['C'].endswith('left out')
    assert '0.0012' in rows['C']
    assert _EXCLUDED in _prose(text)
    assert 'Replicates used:      A, B' in text


def test_the_report_wraps_to_one_width_and_gives_each_reason_once(tmp_path: Path) -> None:
    """One text file, one right margin — and no sentence printed twice.

    Fit Quality names the replicates left out; REPLICATES above it is where each
    reason is written out, so repeating it there only widened the file.
    """
    from gui.session import _wrapped

    text = _txt(tmp_path, [_per_replicate_result()], replica_ids=('a', 'b', 'c'))
    margin = max(len(line) for line in _wrapped('word ' * 200))

    assert 'Left out of the fit:  C' in text
    # The reason is written once, where the replicate table explains it.
    assert _prose(text).count(_EXCLUDED) == 1
    over = [line for line in text.splitlines() if len(line) > margin]
    assert over == []


def test_txt_report_of_a_fit_of_one_signal_has_no_replicate_table(tmp_path: Path) -> None:
    """Nothing was fitted separately, so there is nothing to compare — and no empty table to read."""
    text = _txt(tmp_path, [_result(metadata={'active_replica_ids': ['a', 'b']})], replica_ids=('a', 'b'))

    assert 'REPLICATES' not in text
    assert 'Replicates used:      A, B' in text
    assert 'Left out of the fit:  none' in text


def test_csv_is_one_row_per_reported_parameter(tmp_path: Path) -> None:
    path = tmp_path / 'r.csv'
    export_results_csv([_result()], path)
    rows = _csv_rows(path)

    assert [r['parameter'] for r in rows] == ['Ka_guest', 'log10(Ka_guest)', 'I0', 'I_dye_free']
    assert {r['unit'] for r in rows} == {'1 / molar', '', 'au', 'au / molar'}
    assert all(r['assay_type'] == 'IDA' for r in rows)


def test_csv_carries_the_interval_and_its_test(tmp_path: Path) -> None:
    """A reader must be able to tell a closed end from an open one, and at which level and dof."""
    open_high = KaInterval(low=1.10e6, high=9.9e9, open_low=False, open_high=True, level=0.95, dof=7)
    path = tmp_path / 'r.csv'
    export_results_csv([_result(), _result(interval=open_high)], path)
    closed, opened = (
        next(r for r in _csv_rows(path) if r['parameter'] == 'Ka_guest' and r['result_index'] == i) for i in ('0', '1')
    )

    assert float(closed['ci_low']) == pytest.approx(1.10e6)
    assert float(closed['ci_high']) == pytest.approx(1.40e6)
    assert (closed['ci_open_low'], closed['ci_open_high']) == ('false', 'false')
    assert (closed['ci_level'], closed['ci_dof']) == ('0.95', '7')
    assert opened['ci_open_high'] == 'true'
    # The estimate lies inside its own interval, whichever end is open.
    assert float(closed['ci_low']) <= float(closed['estimate']) <= float(closed['ci_high'])
    assert (closed['ci_unsolvable_low'], closed['ci_unsolvable_high'], closed['ci_split']) == (
        'false',
        'false',
        'false',
    )


def test_csv_says_which_open_sides_the_model_stops_at_and_which_intervals_have_gaps(tmp_path: Path) -> None:
    """The flags the engine computes reach the machine-readable table too, not only the tab."""
    awkward = KaInterval(
        low=1.10e6,
        high=9.9e9,
        open_low=False,
        open_high=True,
        level=0.95,
        dof=7,
        split=True,
        unsolvable_high=True,
    )
    path = tmp_path / 'r.csv'
    export_results_csv([_result(interval=awkward)], path)
    row = next(r for r in _csv_rows(path) if r['parameter'] == 'Ka_guest')

    assert (row['ci_open_high'], row['ci_unsolvable_high'], row['ci_split']) == ('true', 'true', 'true')
    assert (row['ci_open_low'], row['ci_unsolvable_low']) == ('false', 'false')
    assert (row['ci_limited_by_low'], row['ci_limited_by_high']) == ('', '')

    limited = KaInterval(
        low=2.3e2, high=1.4e6, open_low=True, open_high=False, level=0.95, dof=7, limited_by_low='Ka_HG2'
    )
    export_results_csv([_result(interval=limited)], path)
    row = next(r for r in _csv_rows(path) if r['parameter'] == 'Ka_guest')
    assert (row['ci_open_low'], row['ci_limited_by_low'], row['ci_limited_by_high']) == ('true', 'Ka_HG2', '')


def test_csv_leaves_the_interval_columns_blank_where_there_is_none(tmp_path: Path) -> None:
    path = tmp_path / 'r.csv'
    export_results_csv([_result(intervals_reported=False)], path)
    rows = _csv_rows(path)

    for row in rows:
        assert row['estimate']
        assert row['ci_low'] == row['ci_high'] == row['ci_level'] == row['ci_dof'] == ''
        assert row['ci_unsolvable_low'] == row['ci_unsolvable_high'] == row['ci_split'] == ''
    assert {r['degenerate'] for r in rows} == {'true', 'false'}


def test_csv_replicate_columns_come_from_the_replicates_own_fits(tmp_path: Path) -> None:
    """Median and extent are over the replicates the fit used, and log rows are computed in log space."""
    path = tmp_path / 'r.csv'
    export_results_csv([_per_replicate_result()], path, replica_ids=('a', 'b', 'c'))
    rows = {r['parameter']: r for r in _csv_rows(path)}

    used = np.array([1.20e6, 1.30e6])  # 'c' was left out, so its 4e6 must not appear
    assert float(rows['Ka_guest']['replicate_median']) == pytest.approx(np.median(used))
    assert float(rows['Ka_guest']['replicate_min']) == pytest.approx(1.20e6)
    assert float(rows['Ka_guest']['replicate_max']) == pytest.approx(1.30e6)
    assert rows['Ka_guest']['n_replicates'] == '2'
    assert float(rows['log10(Ka_guest)']['replicate_median']) == pytest.approx(np.median(np.log10(used)))
    assert (rows['Ka_guest']['replicates_used'], rows['Ka_guest']['replicates_left_out']) == ('A;B', 'C')


def test_csv_names_the_replicates_by_id_without_the_loaded_order(tmp_path: Path) -> None:
    path = tmp_path / 'r.csv'
    export_results_csv([_per_replicate_result(), _result()], path)
    rows = _csv_rows(path)

    assert {(r['result_index'], r['replicates_used'], r['replicates_left_out']) for r in rows} == {
        ('0', 'a;b', 'c'),
        ('1', '', ''),  # the second result does not record its replicates
    }


def test_exports_handle_an_empty_result_list(tmp_path: Path) -> None:
    """Both writers must produce a valid, readable file with nothing to report.

    The batch exporter builds artefacts from session state, so an empty list is
    reachable; a crash there would abort the whole batch.
    """
    txt, csv_path = tmp_path / 'empty.txt', tmp_path / 'empty.csv'
    export_results_txt([], txt)
    export_results_csv([], csv_path)

    assert 'FIT RESULTS REPORT' in txt.read_text(encoding='utf-8')
    rows = _csv_rows(csv_path)
    assert rows == []  # header written, no data rows
    assert csv_path.read_text(encoding='utf-8').startswith('result_index,')


def test_csv_indexes_multiple_results(tmp_path: Path) -> None:
    path = tmp_path / 'r.csv'
    export_results_csv([_result(), replace(_result(), id='second')], path)
    rows = _csv_rows(path)

    assert {r['result_index'] for r in rows} == {'0', '1'}
