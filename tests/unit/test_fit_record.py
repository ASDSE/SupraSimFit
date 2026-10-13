"""A fit's record of the data it was made on, and every number computed from it.

A per-replicate fit tests whether its replicates share a binding constant and
leaves out the one that does not. Its reported fit, RMSE, R² and curve must then
describe the average of the replicates it used, and an imported result is shown
only once its stored quality is reproduced on the data loaded now.

The synthetic data hold three replicates of the IDA ground truth and one
generated at ten times its Ka_guest — a replicate no shared binding constant
describes. Expected scores are measured against the mean of the used replicate
rows computed here, independently of the pipeline's masking.

``tests/unit/test_released_results.py`` checks the same import rules against
files genuine releases of the app wrote.
"""

from __future__ import annotations

import copy
import json
from dataclasses import replace

import numpy as np
import pytest

from core.assays.ida import IDAAssay
from core.data_processing.measurement_set import MeasurementSet
from core.models.equilibrium import MODEL_ARITHMETIC
from core.optimizer.filters import calculate_fit_metrics
from core.pipeline.fit_pipeline import FitConfig, FitResult, fit_measurement_set
from core.pipeline.reporting import fit_replica_ids, input_replica_ids
from core.pipeline.results_io import verify_imported_result
from core.units import Q_
from tests.conftest import GDA_IDA_RECOVERY_BOUNDS, IDA_TRUE, _make_ida_data

_CONDITIONS = {
    'Ka_dye': Q_(IDA_TRUE['Ka_dye'], '1/M'),
    'h0': Q_(IDA_TRUE['h0'], 'M'),
    'd0': Q_(IDA_TRUE['d0'], 'M'),
}
_KEYS = ('Ka_guest', 'I0', 'I_dye_free', 'I_dye_bound')
_CONFIG = FitConfig(custom_bounds=GDA_IDA_RECOVERY_BOUNDS, per_replica=True)


def _measurement_set() -> MeasurementSet:
    """'a', 'b' and 'c' follow the ground truth; 'odd' binds ten times as tightly."""
    x, y = _make_ida_data(IDA_TRUE, n_points=15)
    _, y_odd = _make_ida_data({**IDA_TRUE, 'Ka_guest': 10 * IDA_TRUE['Ka_guest']}, n_points=15)
    rng = np.random.default_rng(3)
    noise = 0.01 * np.ptp(y)
    signals = np.vstack([row + rng.normal(0.0, noise, row.size) for row in (y, y, y, y_odd)])
    return MeasurementSet(concentrations=x, signals=signals, replica_ids=('a', 'b', 'c', 'odd'))


def _score(signal: np.ndarray, x: np.ndarray, result: FitResult) -> tuple[float, float]:
    """RMSE and R² of *result*'s parameters against *signal*, measured outside the pipeline."""
    assay = IDAAssay(x_data=Q_(x, 'M'), y_data=Q_(signal, 'au'), **_CONDITIONS)
    vector = np.array([result.parameters[k].magnitude for k in _KEYS], dtype=float)
    return calculate_fit_metrics(signal, assay.forward_model(vector).magnitude)


@pytest.fixture(scope='module')
def fitted():
    """(ms, per-replicate fit) — one fit shared by the tests that only read it."""
    ms = _measurement_set()
    return ms, fit_measurement_set(ms, IDAAssay, _CONDITIONS, _CONFIG)


def _used_mean(ms: MeasurementSet) -> np.ndarray:
    return ms.signals[:3].mean(axis=0)


# ---------------------------------------------------------------------------
# Which replicates the fit used
# ---------------------------------------------------------------------------


def test_the_replicate_that_needs_another_ka_is_left_out_and_named(fitted):
    """Its own fit lands at ten times the Ka the others share, which the test rejects."""
    ms, result = fitted

    assert fit_replica_ids(result) == ['a', 'b', 'c']
    assert input_replica_ids(result) == ['a', 'b', 'c', 'odd']
    assert list(result.metadata['replica_failures']) == ['odd']
    reason = result.metadata['replica_failures']['odd']
    assert 'different Ka' in reason and 'p = ' in reason
    assert result.metadata['replicate_test']['level'] == 0.01
    assert result.metadata['replicate_test']['p_values']['odd'] < 0.01 / 4
    assert min(result.metadata['replicate_test']['p_values'][rid] for rid in ('a', 'b', 'c')) > 0.01 / 4


def test_replicates_of_one_titration_are_all_kept():
    """Replicates that differ only by noise share their Ka, so none is excluded."""
    x, y = _make_ida_data(IDA_TRUE, n_points=15)
    rng = np.random.default_rng(17)
    signals = np.vstack([y + rng.normal(0.0, 0.01 * np.ptp(y), y.size) for _ in range(4)])
    ms = MeasurementSet(concentrations=x, signals=signals, replica_ids=('a', 'b', 'c', 'd'))

    result = fit_measurement_set(ms, IDAAssay, _CONDITIONS, _CONFIG)

    assert fit_replica_ids(result) == ['a', 'b', 'c', 'd']
    assert 'replica_failures' not in result.metadata
    assert result.metadata['replicate_test']['p_values'].keys() == {'a', 'b', 'c', 'd'}


def test_the_reported_fit_is_the_fit_of_the_average_of_the_replicates_used(fitted):
    """Two replicates of equal scatter weigh the same, so their joint fit is the fit of their mean."""
    ms, result = fitted

    average_mode = fit_measurement_set(
        ms.with_active(fit_replica_ids(result)),
        IDAAssay,
        _CONDITIONS,
        replace(_CONFIG, per_replica=False),
    )

    assert result.parameters == average_mode.parameters
    assert (result.rmse, result.r_squared) == (average_mode.rmse, average_mode.r_squared)
    assert result.intervals == average_mode.intervals
    assert result.degenerate_keys == average_mode.degenerate_keys


def test_the_reported_quality_is_measured_on_the_replicates_used(fitted):
    ms, result = fitted
    rmse, r_squared = _score(_used_mean(ms), ms.concentrations, result)
    on_all, _ = _score(ms.signals.mean(axis=0), ms.concentrations, result)

    assert result.rmse == pytest.approx(rmse, rel=1e-12)
    assert result.r_squared == pytest.approx(r_squared, rel=1e-12)
    assert abs(on_all / result.rmse - 1) > 1e-3, 'the left-out replicate must tell the two averages apart'


def test_every_given_replicate_has_its_own_fit_measured_against_itself(fitted):
    """The Replicates table shows each replicate's own Ka, so each fit is its replicate's own."""
    ms, result = fitted

    assert [rf.metadata['replica_id'] for rf in result.replica_fits] == list(ms.replica_ids)
    for row, rf in enumerate(result.replica_fits):
        rmse, r_squared = _score(ms.signals[row], ms.concentrations, rf)
        assert rf.rmse == pytest.approx(rmse, rel=1e-12)
        assert rf.r_squared == pytest.approx(r_squared, rel=1e-12)
        assert rf.intervals is None
        assert fit_replica_ids(rf) == [ms.replica_ids[row]]

    own_ka = [float(rf.parameters['Ka_guest'].magnitude) for rf in result.replica_fits]
    assert own_ka[3] / np.median(own_ka[:3]) == pytest.approx(10.0, rel=0.15), 'the odd replicate keeps its own Ka'


def test_a_fit_records_the_equilibrium_arithmetic_its_scores_were_computed_with(fitted):
    """The marker an import reads to know which arithmetic wrote a file's scores."""
    _, result = fitted

    assert result.metadata['model_arithmetic'] == MODEL_ARITHMETIC
    assert all(sub.metadata['model_arithmetic'] == MODEL_ARITHMETIC for sub in result.replica_fits)
    assert result.metadata['quality_scored_on'] == 'fitted_replicates'
    assert result.metadata['method'] == 'variable_projection'


def test_the_same_data_fitted_twice_give_the_same_numbers(fitted):
    """The fit draws no random number, so nothing about it is left to chance."""
    ms, result = fitted

    again = fit_measurement_set(_measurement_set(), IDAAssay, _CONDITIONS, _CONFIG)

    assert again.parameters == result.parameters
    assert (again.rmse, again.r_squared) == (result.rmse, result.r_squared)
    assert again.intervals == result.intervals
    assert fit_replica_ids(again) == fit_replica_ids(result)
    assert ms.concentrations is not None  # the fixture data are untouched by the second fit


# ---------------------------------------------------------------------------
# Imported results
# ---------------------------------------------------------------------------


def _round_trip(result: FitResult) -> FitResult:
    return FitResult.from_dict(json.loads(json.dumps(result.to_dict())))


def test_round_trip_on_the_same_data_is_verified_unchanged(fitted):
    ms, result = fitted
    selection = ms.with_active(['a'])  # the selection loaded now plays no part

    status, shown = verify_imported_result(_round_trip(result), selection)

    assert status == 'verified'
    assert (shown.rmse, shown.r_squared) == (result.rmse, result.r_squared)
    assert shown.intervals == result.intervals
    assert shown.metadata['data_fingerprint'] == ms.fingerprint()
    assert selection.active_replica_ids == ['a']


def _legacy(ms: MeasurementSet, result: FitResult) -> FitResult:
    """*result* as a per-replicate file that scored against every replicate it was given.

    It records neither the scoring marker, nor a fingerprint, nor the
    replicates it was given — only the ones it used and the one it left out.
    """
    old = copy.deepcopy(_round_trip(result))
    old.rmse, old.r_squared = _score(ms.signals.mean(axis=0), ms.concentrations, old)
    for key in ('quality_scored_on', 'data_fingerprint', 'active_replica_ids', 'model_arithmetic'):
        old.metadata.pop(key, None)
    return old


def test_a_file_scored_on_every_replicate_is_rescored_on_the_ones_the_fit_used(fitted):
    ms, result = fitted

    status, shown = verify_imported_result(_legacy(ms, result), ms)

    assert status == 'rescored_legacy'
    assert shown.rmse == pytest.approx(result.rmse, rel=1e-9)
    assert shown.r_squared == pytest.approx(result.r_squared, rel=1e-9)
    np.testing.assert_allclose(shown.y_fit.magnitude, result.y_fit.magnitude, rtol=1e-9)
    for key in _KEYS:
        assert shown.parameters[key].magnitude == result.parameters[key].magnitude
    assert shown.metadata['quality_scored_on'] == 'fitted_replicates'
    assert shown.metadata['data_fingerprint'] == ms.fingerprint()
    assert shown.metadata['model_arithmetic'] == MODEL_ARITHMETIC, "the numbers shown are the present arithmetic's"


def test_results_on_other_data_are_refused(fitted):
    """Concentrations rescaled by 1 %: the fingerprint tells, and for a file without one the re-score does."""
    ms, result = fitted
    rescaled = MeasurementSet(concentrations=ms.concentrations * 1.01, signals=ms.signals, replica_ids=ms.replica_ids)

    assert verify_imported_result(_round_trip(result), rescaled)[0] == 'different_data'
    assert verify_imported_result(_legacy(ms, result), rescaled)[0] == 'different_data'


def _with_scores_scaled(result: FitResult, factor: float) -> FitResult:
    """*result* as a file whose stored RMSE and R² both differ from a re-score by *factor*."""
    return replace(result, rmse=result.rmse * factor, r_squared=result.r_squared * factor)


def test_scores_written_by_other_arithmetic_of_the_same_model_still_verify(fitted):
    """A score shifted by far less than the import gate still verifies; one shifted by 1e-4 is not this fit's."""
    ms, result = fitted
    selection = ms.with_active(fit_replica_ids(result))

    assert verify_imported_result(_with_scores_scaled(_round_trip(result), 1 + 5e-9), selection)[0] == 'verified'
    assert verify_imported_result(_with_scores_scaled(_round_trip(result), 1 + 1e-4), selection)[0] == 'different_data'


def test_results_without_data_are_unverifiable_and_unchanged(fitted):
    _, result = fitted
    imported = _round_trip(result)

    status, shown = verify_imported_result(imported, None)

    assert status == 'unverifiable'
    assert shown is imported


def test_average_fit_without_a_replicate_record_is_scored_on_the_selection_loaded_now():
    """A file that does not name its replicates verifies only on the selection it was made on, and then names it."""
    ms = _measurement_set().with_active(['a', 'b'])
    fit = fit_measurement_set(ms, IDAAssay, _CONDITIONS, replace(_CONFIG, per_replica=False))
    old = _round_trip(fit)
    for key in ('quality_scored_on', 'data_fingerprint', 'active_replica_ids'):
        del old.metadata[key]

    status, shown = verify_imported_result(old, ms)

    assert status == 'verified'
    assert fit_replica_ids(shown) == ['a', 'b']
    assert verify_imported_result(old, ms.with_active(['a', 'b', 'c']))[0] == 'different_data'
    assert verify_imported_result(old, ms.with_active(['a']))[0] == 'different_data'
