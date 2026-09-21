"""Tests for the TXT report and CSV table exports in gui.session (no Qt required).

These guard the *reported* numbers, which are the point of the exports: the
estimate is a real fit and the interval beside it is that fit's own confidence
interval, an open side is written in words rather than as a number, a binding
constant that was held fixed says so instead of showing a made-up range, a file
that carries no interval says why, and log₁₀ rows are computed in log space.

Where the fit was free to move an input inside a stated uncertainty, the report
carries a second interval — the one conditional on the inputs exactly as
entered — the shift of every input beside what was stated for it, and what the
misfit tests and the conflict statistic say about the model and those inputs.
The two intervals are never mixed, and a statistic is never printed without the
test it comes from.

The results are hand-built rather than fitted: each one pins one shape the
writers have to render (closed interval, open side, pinned Ka, no interval at
all, replicates with one left out, inputs that moved, each verdict), and
building them directly is what lets a single test hold exactly one of those
shapes.
"""

from __future__ import annotations

import csv
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from core.pipeline.diagnostics import Conflict, FitDiagnostics, InputShift, MisfitTest, Verdict
from core.pipeline.fit_pipeline import ConditionalFit, FitResult
from core.pipeline.inputs import TITRANT, InputSpec, specs_to_dict
from core.pipeline.varpro import KaInterval
from core.units import Q_
from gui.session import export_results, export_results_csv, export_results_txt, import_results

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


#: The interval the fit reports once the inputs may move: wider than the one at
#: the entered inputs, which the same result carries as its conditional fit.
_AWARE = KaInterval(low=0.90e6, high=1.80e6, open_low=False, open_high=False, level=0.95, dof=6.2)

#: What the user stated: a standard deviation on the host stock and on the
#: titrant, and a range on the dye stock.
_SPECS = {
    'h0': InputSpec.sigma_pct(3.0),
    TITRANT: InputSpec.sigma_pct(5.0),
    'd0': InputSpec.interval_pct(-6.0, 6.0),
}


def _input_aware_result(
    *,
    shifts: dict[str, InputShift] | None = None,
    diagnostics: FitDiagnostics | None = None,
) -> FitResult:
    """A fit whose inputs were free to move: the wider interval, the shifts and the diagnostics.

    The conditional fit beside it is the same fit with every input held at the
    value entered, which is what :func:`_result` alone reports.
    """
    entered = _result()
    result = replace(
        entered,
        parameters={**_PARAMS, 'Ka_guest': Q_(1.31e6, '1/M')},
        intervals={'Ka_guest': _AWARE},
        conditional=ConditionalFit(
            parameters=dict(_PARAMS),
            intervals=dict(entered.intervals),
            rmse=12.3,
            r_squared=0.9962,
        ),
        input_shifts=shifts
        if shifts is not None
        else {
            'h0': InputShift(key='h0', fraction=-0.114, z=-3.8, at_edge=False),
            TITRANT: InputShift(key=TITRANT, fraction=0.093, z=1.86, at_edge=False),
            'd0': InputShift(key='d0', fraction=-0.06, z=None, at_edge=True),
        },
        diagnostics=diagnostics
        if diagnostics is not None
        else FitDiagnostics(
            conditional_misfit=MisfitTest(kind='lack_of_fit', statistic=200.0, p_value=1e-9, dof=(9, 72)),
            misfit=MisfitTest(kind='lack_of_fit', statistic=0.9, p_value=0.55, dof=(9, 72)),
            conflict=Conflict(q=24.2, k=2, p_value=2e-5, weights=(0.23, 0.92)),
            verdict=Verdict.INPUTS_CONFLICT,
        ),
    )
    result.fit_config['input_uncertainty'] = specs_to_dict(_SPECS)
    return result


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
        # The same file predates the second interval and the diagnostics.
        assert row['cond_estimate'] == row['cond_ci_low'] == row['verdict'] == row['conflict_q'] == ''
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


# ---------------------------------------------------------------------------
# Input uncertainties: the second interval, the shifts and the diagnostics
# ---------------------------------------------------------------------------


def test_txt_report_puts_the_conditional_interval_under_the_headline_one(tmp_path: Path) -> None:
    """Two intervals answer two questions, so the report says which is which and never mixes their ends."""
    text = _txt(tmp_path, [_input_aware_result()])

    headline = next(ln for ln in text.splitlines() if ln.strip().startswith('Ka_guest'))
    assert '[9e+05, 1.8e+06]' in headline  # the interval that covers the stated uncertainties
    assert 'Conditional on the entered inputs: Ka_guest = 1.24e+06 [1.1e+06, 1.4e+06] M⁻¹' in text
    assert 'takes every input exactly as entered' in _prose(text)


def test_txt_report_of_a_fit_that_took_the_inputs_as_entered_has_one_interval(tmp_path: Path) -> None:
    """With nothing free to move the two intervals are the same one, and a second line would invent a difference."""
    text = _txt(tmp_path, [_result()])

    assert 'Conditional on the entered inputs' not in text
    assert 'INPUT UNCERTAINTY' not in text


def test_txt_report_tables_what_was_stated_and_where_the_fit_put_each_input(tmp_path: Path) -> None:
    """The stated uncertainty and the fitted shift belong side by side: the shift only means something against it."""
    text = _txt(tmp_path, [_input_aware_result()])

    rows = _table_rows(text, '  Input ')
    assert set(rows) == {'[Host]₀', 'Guest', '[Dye]₀'}  # the titrant is named as the panel names it
    assert 'σ 3 %' in rows['[Host]₀'] and '−11.4 %' in rows['[Host]₀'] and '3.8 σ' in rows['[Host]₀']
    assert 'σ 5 %' in rows['Guest'] and '+9.3 %' in rows['Guest'] and '1.9 σ' in rows['Guest']
    # A range carries no σ to judge a shift against; resting at its end is what there is to say.
    assert '−6 % to +6 %' in rows['[Dye]₀'] and 'at the edge of its range' in rows['[Dye]₀']


def test_txt_report_writes_an_uncertainty_in_the_input_s_own_unit_the_way_it_writes_a_concentration(
    tmp_path: Path,
) -> None:
    """A σ in molar is a number the reader compares with the value entered, so it is written as one, not as 2e-07."""
    result = replace(_input_aware_result(), conditions={'h0': Q_(4.3e-6, 'M')})
    result.fit_config['input_uncertainty'] = specs_to_dict({**_SPECS, 'h0': InputSpec.sigma_abs(2e-7)})

    rows = _table_rows(_txt(tmp_path, [result]), '  Input ')

    assert 'σ 2.0×10⁻⁷ M' in rows['[Host]₀']
    assert 'e-07' not in rows['[Host]₀']


def test_txt_report_gives_the_verdict_with_both_misfit_tests_and_the_conflict(tmp_path: Path) -> None:
    """The verdict is a reading of the tests, so the report prints the tests it was read from."""
    text = _prose(_txt(tmp_path, [_input_aware_result()]))

    assert 'MODEL AND INPUTS' in text
    assert 'further from their entered values than their stated uncertainties allow (q = 24.2, p < 0.001)' in text
    assert 'Model at the entered inputs: lack-of-fit F(9, 72) = 200, p < 0.001' in text
    assert 'Model with the inputs moved: lack-of-fit F(9, 72) = 0.9, p = 0.55' in text
    assert 'Inputs against what you stated: q = 24.2, p < 0.001' in text
    assert 'judges the stated inputs together, over the 2 combinations of them these data pin down' in text
    # The statistic judges the inputs together; no sentence may pin the blame on one of them.
    assert 'says where the fit put the correction, not which input is off' in text


def test_txt_report_records_what_the_interval_took_the_inputs_to_be(tmp_path: Path) -> None:
    """A printed report is the archive of a fit, and what its interval was conditioned on is part of the fit.

    Without the line, a reader has to infer it from a section that is not there.
    """
    consistent = FitDiagnostics(
        conditional_misfit=MisfitTest(kind='lack_of_fit', statistic=0.9, p_value=0.55, dof=(9, 72)),
        misfit=MisfitTest(kind='lack_of_fit', statistic=0.9, p_value=0.55, dof=(9, 72)),
        conflict=None,
        verdict=Verdict.CONSISTENT,
    )
    fixed = _prose(_txt(tmp_path, [replace(_result(), diagnostics=consistent)]))
    assert 'INPUT UNCERTAINTY' not in fixed
    assert 'Input uncertainties used: none — the interval takes the inputs as exact.' in fixed

    moved = _prose(_txt(tmp_path, [_input_aware_result()]))
    assert 'Input uncertainties used: stated above under INPUT UNCERTAINTY.' in moved


def test_txt_report_writes_a_conflict_over_one_input_in_the_singular(tmp_path: Path) -> None:
    """One input free to move is one input to name; the plural reads as though more had been weighed against it.

    Naming the only input the fit could move is not naming the cause of the
    misfit, and the sentence still says so.
    """
    one_input = FitDiagnostics(
        conditional_misfit=MisfitTest(kind='lack_of_fit', statistic=200.0, p_value=1e-9, dof=(9, 72)),
        misfit=MisfitTest(kind='lack_of_fit', statistic=0.9, p_value=0.55, dof=(9, 72)),
        conflict=Conflict(q=15.6, k=1, p_value=7e-5, weights=(0.92,)),
        verdict=Verdict.INPUTS_CONFLICT,
    )
    result = _input_aware_result(
        shifts={'h0': InputShift(key='h0', fraction=-0.197, z=-3.9, at_edge=False)},
        diagnostics=one_input,
    )
    result.fit_config['input_uncertainty'] = specs_to_dict({'h0': InputSpec.sigma_pct(5.0)})
    text = _prose(_txt(tmp_path, [result]))

    assert (
        'The data fit only with [Host]₀ further from the value you entered than the uncertainty you stated '
        'allows (q = 15.6, p < 0.001).'
    ) in text
    assert 'taken together' not in text and 'the 1 combination' not in text
    assert (
        'q judges the stated input against what you said you knew, over the one combination these data pin down' in text
    )
    assert 'not that this input is the one that is off' in text
    assert 'whatever its real cause' in text
    assert 'Check the value you entered for it.' in text


def test_txt_report_says_the_model_is_rejected_even_with_the_inputs_free(tmp_path: Path) -> None:
    """An interval under a model the data reject is reported with that fact beside it, never silently."""
    rejected = FitDiagnostics(
        conditional_misfit=MisfitTest(kind='lack_of_fit', statistic=200.0, p_value=1e-9, dof=(9, 72)),
        misfit=MisfitTest(kind='lack_of_fit', statistic=12.0, p_value=1e-6, dof=(9, 72)),
        conflict=Conflict(q=1.2, k=2, p_value=0.42, weights=(0.23, 0.92)),
        verdict=Verdict.MODEL_INADEQUATE,
    )
    text = _prose(_txt(tmp_path, [_input_aware_result(diagnostics=rejected)]))

    assert 'does not describe the data even with the inputs free to move within their uncertainties' in text
    assert 'The interval assumes a model the data reject' in text
    assert 'Ka_guest' in text  # the interval is still reported


def test_txt_report_says_when_the_data_cannot_check_the_entered_inputs(tmp_path: Path) -> None:
    """With no direction of the inputs informed there is no conflict test, and silence would read as a pass."""
    untested = FitDiagnostics(
        conditional_misfit=MisfitTest(kind='runs', statistic=6.0, p_value=0.41, dof=None, expected=7.0),
        misfit=MisfitTest(kind='runs', statistic=6.0, p_value=0.41, dof=None, expected=7.0),
        conflict=None,
        verdict=Verdict.CONSISTENT,
    )
    text = _prose(_txt(tmp_path, [_input_aware_result(diagnostics=untested)]))

    assert 'cannot check the values you entered' in text
    assert 'q =' not in text
    assert 'runs test: 6 runs, 7.0 expected, p = 0.41' in text


def test_txt_report_of_a_file_without_diagnostics_claims_none(tmp_path: Path) -> None:
    """A result from an earlier version carries no tests, and an empty block would read as a clean bill."""
    text = _txt(tmp_path, [_result()])

    assert 'MODEL AND INPUTS' not in text
    assert 'verdict' not in text.lower()


def test_csv_carries_both_intervals_and_what_the_diagnostics_say(tmp_path: Path) -> None:
    """A reader of the table must be able to tell the two intervals apart and see what the fit was judged on."""
    path = tmp_path / 'r.csv'
    export_results_csv([_input_aware_result()], path)
    rows = {r['parameter']: r for r in _csv_rows(path)}

    ka = rows['Ka_guest']
    assert (float(ka['ci_low']), float(ka['ci_high'])) == pytest.approx((0.90e6, 1.80e6))
    assert (float(ka['cond_estimate']), float(ka['cond_ci_low']), float(ka['cond_ci_high'])) == pytest.approx(
        (1.24e6, 1.10e6, 1.40e6)
    )
    assert (ka['cond_ci_open_low'], ka['cond_ci_open_high']) == ('false', 'false')
    # An input the data pin down takes part of a residual degree of freedom
    # with it, so the dof of an input-aware interval is not a whole number.
    assert ka['ci_dof'] == '6.2'
    assert float(rows['log10(Ka_guest)']['cond_estimate']) == pytest.approx(np.log10(1.24e6))
    # The diagnostics describe the fit, so every row of it carries them.
    for row in rows.values():
        assert row['verdict'] == 'inputs_conflict'
        assert float(row['misfit_p']) == pytest.approx(0.55)
        # The verdict is read from the fit at the entered inputs as much as
        # from the one the interval comes from, so both tests are in the table:
        # misfit_p alone reads as a clean fit under a verdict that is not one.
        assert float(row['cond_misfit_p']) == pytest.approx(1e-9)
        assert (float(row['conflict_q']), float(row['conflict_p'])) == pytest.approx((24.2, 2e-5))
    # A signal coefficient has no second interval: it is the same number in both fits.
    assert rows['I0']['cond_estimate'] == ''


def test_a_split_conditional_interval_is_marked_in_both_exports(tmp_path: Path) -> None:
    """A bracket over a gap of rejected values means the same in either column, so it is marked in both."""
    aware = _input_aware_result()
    split = replace(aware.conditional.intervals['Ka_guest'], split=True)
    result = replace(aware, conditional=replace(aware.conditional, intervals={'Ka_guest': split}))

    text = _prose(_txt(tmp_path, [result]))
    assert 'Ka_guest conditional on the entered inputs' in text
    assert 'separate stretches' in text

    path = tmp_path / 'r.csv'
    export_results_csv([result], path)
    rows = {r['parameter']: r for r in _csv_rows(path)}
    assert rows['Ka_guest']['cond_ci_split'] == 'true'
    assert rows['I0']['cond_ci_split'] == ''


def test_csv_gives_every_input_that_moved_a_row_of_its_own(tmp_path: Path) -> None:
    """The fitted inputs are part of the result, and a table that omitted them would hide what the interval covers.

    Each is keyed the way every other row of the column is, so an input row can
    be joined to the condition of that name; the names a reader reads are in
    the TXT report.
    """
    path = tmp_path / 'r.csv'
    export_results_csv([_input_aware_result()], path)
    rows = {r['parameter']: r for r in _csv_rows(path)}

    assert {'h0', TITRANT, 'd0'} <= set(rows)
    assert 'Ka_guest' in rows  # the same column names the fitted parameters by their keys
    host = rows['h0']
    assert host['unit'] == '% of entered'
    assert float(host['estimate']) == pytest.approx(-11.4)
    assert float(host['input_z']) == pytest.approx(-3.8)
    assert (host['input_at_edge'], host['ci_low'], host['cond_estimate']) == ('false', '', '')
    assert rows['d0']['input_at_edge'] == 'true' and rows['d0']['input_z'] == ''


def test_csv_leaves_the_input_columns_blank_for_a_fit_that_moved_nothing(tmp_path: Path) -> None:
    """Every row of every result has the same columns, filled only where the result has something to put in them."""
    path = tmp_path / 'r.csv'
    export_results_csv([_result()], path)
    rows = _csv_rows(path)

    assert [r['parameter'] for r in rows] == ['Ka_guest', 'log10(Ka_guest)', 'I0', 'I_dye_free']
    for row in rows:
        assert row['cond_estimate'] == row['cond_ci_low'] == row['cond_ci_high'] == ''
        assert row['verdict'] == row['misfit_p'] == row['cond_misfit_p'] == ''
        assert row['conflict_q'] == row['conflict_p'] == ''
        assert row['input_z'] == row['input_at_edge'] == ''


def test_the_report_of_an_imported_result_says_what_the_fit_said(tmp_path: Path) -> None:
    """A results file carries the uncertainties and the shifts, so reading one back reports the same fit."""
    export_results([_input_aware_result()], tmp_path / 'r.json')

    direct = _prose(_txt(tmp_path, [_input_aware_result()]))
    imported = _prose(_txt(tmp_path, import_results(tmp_path / 'r.json')))

    for block in ('INPUT UNCERTAINTY', 'MODEL AND INPUTS', 'Conditional on the entered inputs'):
        assert block in imported
    # Every number and sentence below the header is the one the fit reported;
    # the header carries the times the report and the result were made.
    assert imported.split('FITTED PARAMETERS')[1] == direct.split('FITTED PARAMETERS')[1]
