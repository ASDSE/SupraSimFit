"""Tests for the TXT report and CSV table exports in gui.session (no Qt required).

These guard the *reported* numbers, which are the point of the exports: the
estimate is a real fit, the range is the pool's own extent, and log₁₀ rows are
computed in log space. They also pin that a result with no pool says so rather
than emitting a fabricated range.
"""

from __future__ import annotations

import csv
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from core.pipeline.fit_pipeline import FitResult
from core.units import Q_
from gui.session import export_results_csv, export_results_txt


def _result(*, pool: bool = True) -> FitResult:
    rng = np.random.default_rng(0)
    x = np.linspace(1e-6, 5e-5, 10)
    samples = None
    if pool:
        samples = {
            'Ka_guest': rng.normal(1.24e6, 9e4, 60).clip(1e5),
            'I_0': rng.normal(1000.0, 20.0, 60),
        }
    return FitResult(
        parameters={'Ka_guest': Q_(1.24e6, '1/M'), 'I_0': Q_(1000.0, 'au')},
        rmse=12.3,
        r_squared=0.9962,
        n_passing=60 if pool else 1,
        n_total=100,
        x_fit=Q_(x, 'M'),
        y_fit=Q_(x, 'au'),
        assay_type='IDA',
        model_name='equilibrium_4param',
        source_file='IDA_system.txt',
        parameter_samples=samples,
    )


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding='utf-8', newline='') as handle:
        return list(csv.DictReader(handle))


def test_txt_report_states_what_it_reports(tmp_path: Path) -> None:
    """The old report printed '± Uncert.' without saying what the ± was."""
    path = tmp_path / 'r.txt'
    export_results_txt([_result()], path)
    text = path.read_text(encoding='utf-8')

    assert 'Estimate = the single best fit (highest R²) of 60 accepted fits.' in text
    assert 'Range    = (min, max) across those 60 fits.' in text
    assert '± Uncert.' not in text
    # Every column of the summary table is carried, across the two blocks.
    for header in ('Estimate', 'Range (min, max)', 'Median ± MAD', 'Mean ± SD', '68% Range [p16, p84]', 'Units'):
        assert header in text


def _with_attempts(
    result: FitResult, shown: int, *, per_replicate: bool = True, replica_fits: bool = True
) -> FitResult:
    """*result* with a 60-attempt pool, showing attempt *shown*.

    Attempt 0 has the pool's highest R². As a per-replicate fit its replicates
    hold attempts 0-29 and 30-59, led by attempts 7 and 30; attempt 7 fits the
    average of the replicates used better, so the fit chose attempt 7.
    """
    r2 = np.linspace(0.99, 0.98, 60)
    r2[0], r2[7] = 0.999, 0.995
    replicas = [
        replace(
            result, parameter_samples={k: v[s] for k, v in result.parameter_samples.items()}, representative_index=i
        )
        for s, i in ((slice(0, 30), 7), (slice(30, 60), 0))
    ]
    return replace(
        result,
        uncertainty_source='replicate' if per_replicate else 'optimizer',
        quality_samples={'r_squared': r2, 'rmse': 1.0 - r2},
        replica_fits=replicas if per_replicate and replica_fits else None,
        representative_index=shown,
    )


PICKED = 'Estimate = one of the 60 accepted fits, picked by hand in the app.'


@pytest.mark.parametrize(
    ('make', 'sentence'),
    [
        (
            lambda r: _with_attempts(r, 7),
            "Estimate = one of the 60 accepted fits: of each replicate's best fit, "
            'the one with the highest R² against the average of the replicates it used.',
        ),
        (lambda r: _with_attempts(r, 40), PICKED),
        (lambda r: _with_attempts(r, 7, per_replicate=False), PICKED),
        (lambda r: replace(r, representative_index=7, metadata={'fitted_representative_index': 3}), PICKED),
        (
            lambda r: _with_attempts(r, 7, replica_fits=False),
            'Estimate = one of the 60 accepted fits; the file does not record which one the fit chose.',
        ),
    ],
    ids=['per-replicate-choice', 'per-replicate-pick', 'single-fit-pick', 'recorded-pick', 'choice-unknown'],
)
def test_txt_report_names_the_fit_the_estimate_reports(tmp_path: Path, make, sentence) -> None:
    """Only a single fit left on its own choice reports the pool's highest-R² fit."""
    path = tmp_path / 'r.txt'
    export_results_txt([make(_result())], path)
    text = path.read_text(encoding='utf-8')

    assert sentence in text
    assert 'highest R²) of' not in text


def _left_out_fit() -> FitResult:
    """*_result* as a per-replicate fit given replicates '0'-'3' that left out '2'."""
    metadata = {
        'active_replica_ids': ['0', '1', '2', '3'],
        'replica_ids_fit': ['0', '1', '3'],
        'replica_failures': {'2': 'None of its fit attempts reached the minimum R² of 0.99.'},
    }
    return replace(_result(), uncertainty_source='replicate', metadata=metadata)


def test_txt_report_names_the_replicates_the_fit_used_and_left_out(tmp_path: Path) -> None:
    """The report names replicates as the app does, so a reader knows which data its R² describes."""
    path = tmp_path / 'r.txt'
    export_results_txt([_left_out_fit()], path, replica_ids=('0', '1', '2', '3'))
    text = path.read_text(encoding='utf-8')

    assert 'Replicates used:      A, B, D' in text
    assert 'Left out of the fit:  C: None of its fit attempts reached the minimum R² of 0.99.' in text
    assert 'RMSE and R² are measured against the average of the replicates used.' in text


def test_csv_names_the_replicates_by_id_without_the_loaded_order(tmp_path: Path) -> None:
    path = tmp_path / 'r.csv'
    export_results_csv([_left_out_fit(), _result()], path)
    rows = _csv_rows(path)

    assert {(r['result_index'], r['replicates_used'], r['replicates_left_out']) for r in rows} == {
        ('0', '0;1;3', '2'),
        ('1', '', ''),  # the second result does not record its replicates
    }


def test_txt_report_range_is_the_pool_extent(tmp_path: Path) -> None:
    result = _result()
    path = tmp_path / 'r.txt'
    export_results_txt([result], path)
    line = next(ln for ln in path.read_text(encoding='utf-8').splitlines() if ln.strip().startswith('Ka_guest'))

    pool = result.parameter_samples['Ka_guest']
    assert f'{np.min(pool):.4g}' in line
    assert f'{np.max(pool):.4g}' in line


def test_txt_report_writes_a_log_value_no_coarser_than_its_own_spread(tmp_path: Path) -> None:
    """A log₁₀ row reads to the decimals its spread needs, as the summary table on screen does.

    Four significant figures put 8.496983 ± 0.000096 in the file as
    '8.497 ± 9.6e-05', where the value is a hundred times coarser than the
    spread it is quoted with and two fits a reader can tell apart on screen
    become one number.
    """
    rng = np.random.default_rng(3)
    tight = 10 ** rng.normal(8.496983, 1e-4, 60)  # a pool that agrees to four decimals of log₁₀
    result = replace(
        _result(),
        parameters={'Ka_guest': Q_(float(10**8.496983), '1/M'), 'I_0': Q_(1000.0, 'au')},
        parameter_samples={'Ka_guest': tight, 'I_0': rng.normal(1000.0, 20.0, 60)},
    )
    path = tmp_path / 'r.txt'
    export_results_txt([result], path)

    logs = np.log10(tight)
    lines = [ln for ln in path.read_text(encoding='utf-8').splitlines() if ln.strip().startswith('log10(Ka_guest)')]
    estimate_line, spread_line = lines
    assert f'{np.log10(result.parameters["Ka_guest"].magnitude):.6f}'[:-1] in estimate_line
    assert '8.497 ' not in estimate_line  # not rounded past the spread beside it
    assert f'{np.median(logs):.5f}'[:-1] in spread_line
    assert 'e-0' not in spread_line  # a spread in the same fixed notation as its value


def test_txt_report_without_pool_says_so(tmp_path: Path) -> None:
    path = tmp_path / 'r.txt'
    export_results_txt([_result(pool=False)], path)
    text = path.read_text(encoding='utf-8')

    assert 'Range    = unavailable: no fit pool is stored for this result.' in text
    assert 'SPREAD ACROSS THE ACCEPTED-FIT POOL' not in text


def test_csv_is_one_row_per_reported_parameter(tmp_path: Path) -> None:
    result = _result()
    path = tmp_path / 'r.csv'
    export_results_csv([result], path)
    rows = _csv_rows(path)

    # Two parameters, plus the log₁₀ twin of the association constant.
    assert [r['parameter'] for r in rows] == ['Ka_guest', 'log10(Ka_guest)', 'I_0']
    assert {r['unit'] for r in rows} == {'1 / molar', '', 'au'}
    assert all(r['n_passing'] == '60' and r['assay_type'] == 'IDA' for r in rows)


def test_csv_values_match_the_pool(tmp_path: Path) -> None:
    result = _result()
    path = tmp_path / 'r.csv'
    export_results_csv([result], path)
    row = next(r for r in _csv_rows(path) if r['parameter'] == 'Ka_guest')

    pool = result.parameter_samples['Ka_guest']
    assert float(row['estimate']) == pytest.approx(1.24e6)
    assert float(row['min']) == pytest.approx(np.min(pool))
    assert float(row['max']) == pytest.approx(np.max(pool))
    assert float(row['median']) == pytest.approx(np.median(pool))
    # The reported estimate is a real fit, so it lies inside the pool's extent.
    assert float(row['min']) <= float(row['estimate']) <= float(row['max'])


def test_csv_log_row_is_computed_in_log_space(tmp_path: Path) -> None:
    """log₁₀ statistics come from the per-fit log values, never log of a spread."""
    result = _result()
    path = tmp_path / 'r.csv'
    export_results_csv([result], path)
    row = next(r for r in _csv_rows(path) if r['parameter'] == 'log10(Ka_guest)')

    logs = np.log10(result.parameter_samples['Ka_guest'])
    assert float(row['median']) == pytest.approx(np.median(logs))
    assert float(row['std']) == pytest.approx(np.std(logs, ddof=1))
    # Independent check that this is not log10 of the linear-space spread.
    linear_std = np.std(result.parameter_samples['Ka_guest'], ddof=1)
    assert float(row['std']) != pytest.approx(np.log10(linear_std))


def test_csv_leaves_pool_columns_blank_without_a_pool(tmp_path: Path) -> None:
    path = tmp_path / 'r.csv'
    export_results_csv([_result(pool=False)], path)
    rows = _csv_rows(path)

    assert [r['parameter'] for r in rows] == ['Ka_guest', 'I_0']  # no log twin without a pool
    for row in rows:
        assert row['estimate']
        assert row['min'] == row['max'] == row['median'] == ''


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
    export_results_csv([_result(), _result()], path)
    rows = _csv_rows(path)

    assert {r['result_index'] for r in rows} == {'0', '1'}
