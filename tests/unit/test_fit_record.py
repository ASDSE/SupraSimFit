"""A fit's record of the data it was made on, and every number computed from it.

A per-replicate fit leaves out a replicate with no acceptable fit. Its quality
pool, its representative and its reported RMSE, R² and curve must then describe
the average of the replicates it used, whatever is active when a representative
is picked later, and an imported result is shown only once its stored quality is
reproduced on the data loaded now.

The synthetic data hold two replicates that fit well and one of pure noise that
no attempt fits to the R² floor. Expected scores are measured against the mean
of the used replicates computed here, independently of the pipeline's masking.
"""

from __future__ import annotations

import copy
import json

import numpy as np
import pytest

from core.assays.ida import IDAAssay
from core.data_processing.measurement_set import MeasurementSet
from core.optimizer.filters import calculate_fit_metrics
from core.pipeline.fit_pipeline import (
    FitConfig,
    FitResult,
    fit_measurement_set,
    fit_replica_ids,
    input_replica_ids,
    scoring_assay,
    select_representative,
    verify_imported_result,
)
from core.units import Q_
from tests.conftest import GDA_IDA_RECOVERY_BOUNDS, IDA_TRUE, _make_ida_data

_CONDITIONS = {
    'Ka_dye': Q_(IDA_TRUE['Ka_dye'], '1/M'),
    'h0': Q_(IDA_TRUE['h0'], 'M'),
    'd0': Q_(IDA_TRUE['d0'], 'M'),
}
_KEYS = ('Ka_guest', 'I0', 'I_dye_free', 'I_dye_bound')


def _measurement_set() -> MeasurementSet:
    """'a' and 'b' carry slight noise; 'c' holds no titration curve at all."""
    x, y = _make_ida_data(IDA_TRUE, n_points=15)
    rng = np.random.default_rng(3)
    good = [y + rng.normal(0.0, 0.002 * np.ptp(y), y.size) for _ in range(2)]
    noise = rng.normal(float(np.mean(y)), 0.3 * np.ptp(y), y.size)
    return MeasurementSet(concentrations=x, signals=np.vstack([*good, noise]), replica_ids=('a', 'b', 'c'))


def _scores(signal: np.ndarray, x: np.ndarray, samples: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    """RMSE and R² of every pooled attempt against *signal*."""
    assay = IDAAssay(x_data=Q_(x, 'M'), y_data=Q_(signal, 'au'), **_CONDITIONS)
    rows = np.column_stack([samples[k] for k in _KEYS])
    scores = np.array([calculate_fit_metrics(signal, assay.forward_model(row).magnitude) for row in rows])
    return {'rmse': scores[:, 0], 'r_squared': scores[:, 1]}


@pytest.fixture(scope='module')
def fitted():
    """(ms, per-replicate fit) — one fit shared by the tests that only read it."""
    ms = _measurement_set()
    config = FitConfig(n_trials=8, custom_bounds=GDA_IDA_RECOVERY_BOUNDS, per_replica=True, seed=5)
    return ms, fit_measurement_set(ms, IDAAssay, _CONDITIONS, config)


def _used_mean(ms: MeasurementSet) -> np.ndarray:
    return ms.signals[:2].mean(axis=0)


# ---------------------------------------------------------------------------
# The fit scores what it used
# ---------------------------------------------------------------------------


def test_left_out_replicate_is_recorded(fitted):
    _, result = fitted

    assert fit_replica_ids(result) == ['a', 'b']
    assert input_replica_ids(result) == ['a', 'b', 'c']
    assert list(result.metadata['replica_failures']) == ['c']


def test_pool_quality_is_measured_against_the_average_of_the_used_replicates(fitted):
    ms, result = fitted
    used = _scores(_used_mean(ms), ms.concentrations, result.parameter_samples)
    given = _scores(ms.signals.mean(axis=0), ms.concentrations, result.parameter_samples)

    for key in ('rmse', 'r_squared'):
        np.testing.assert_allclose(result.quality_samples[key], used[key], rtol=1e-12, atol=0)
    assert not np.allclose(result.quality_samples['r_squared'], given['r_squared'], rtol=1e-6)


def test_reported_fit_is_the_best_replicate_best_attempt_on_the_used_replicates(fitted):
    """Of each fitted replicate's best attempt, the one with the highest R² against the used average is reported."""
    ms, result = fitted
    used = _scores(_used_mean(ms), ms.concentrations, result.parameter_samples)
    sizes = [rf.n_passing for rf in result.replica_fits]
    offsets = np.cumsum([0, *sizes[:-1]])
    bests = [int(offset) + rf.representative_index for offset, rf in zip(offsets, result.replica_fits)]
    expected = bests[int(np.argmax(used['r_squared'][bests]))]

    assert result.representative_index == expected
    assert result.r_squared == pytest.approx(used['r_squared'][expected], rel=1e-12)
    assert result.rmse == pytest.approx(used['rmse'][expected], rel=1e-12)


def _best_attempts(result: FitResult) -> list[int]:
    """Pool index of each fitted replicate's best attempt, in replicate order."""
    offsets = np.cumsum([0, *[rf.n_passing for rf in result.replica_fits][:-1]])
    return [int(offset) + rf.representative_index for offset, rf in zip(offsets, result.replica_fits)]


def test_representative_is_chosen_on_the_used_replicates_even_where_every_given_replicate_would_choose_another():
    """'a', 'b' and 'd' are the ground truth scaled by 1, 1.004 and 1.03, so each best attempt follows its own replicate.

    Their average lies closest to 'b'. The left-out 'c' (scaled by 1.12 under a
    zigzag no attempt fits) would pull the average of all four replicates
    closest to 'd', so a fit that chose among the best attempts on every
    replicate it was given would report 'd'.
    """
    x, y = _make_ida_data(IDA_TRUE, n_points=15)
    zigzag = 0.6 * np.ptp(y) * (-1.0) ** np.arange(y.size)
    signals = np.vstack([y, 1.004 * y, 1.12 * y + zigzag, 1.03 * y])
    ms = MeasurementSet(concentrations=x, signals=signals, replica_ids=('a', 'b', 'c', 'd'))
    config = FitConfig(n_trials=6, custom_bounds=GDA_IDA_RECOVERY_BOUNDS, per_replica=True, seed=5)

    result = fit_measurement_set(ms, IDAAssay, _CONDITIONS, config)

    assert fit_replica_ids(result) == ['a', 'b', 'd']
    bests = _best_attempts(result)
    used = _scores(signals[[0, 1, 3]].mean(axis=0), x, result.parameter_samples)
    given = _scores(signals.mean(axis=0), x, result.parameter_samples)
    on_used = bests[int(np.argmax(used['r_squared'][bests]))]
    on_given = bests[int(np.argmax(given['r_squared'][bests]))]
    assert (on_used, on_given) == (bests[1], bests[2]), 'the data must tell the two rules apart'
    assert result.representative_index == on_used
    assert result.r_squared == pytest.approx(used['r_squared'][on_used], rel=1e-12)


# ---------------------------------------------------------------------------
# A pick is scored on the record, not on the selection active now
# ---------------------------------------------------------------------------


@pytest.mark.parametrize('active_now', [['a', 'b'], ['a'], ['b', 'c']], ids=['left-out-off', 'used-off', 'mixed'])
def test_pick_reports_the_quality_its_pool_records(fitted, active_now):
    ms, result = fitted
    live = ms.with_active(active_now)
    r2 = result.quality_samples['r_squared']
    shown = copy.deepcopy(result)

    for index in (int(np.argmin(r2)), int(np.argmax(r2)), len(r2) // 2):
        select_representative(shown, scoring_assay(live, shown), index)
        assert shown.r_squared == r2[index]
        assert shown.rmse == result.quality_samples['rmse'][index]

    select_representative(shown, scoring_assay(live, shown), result.representative_index)
    assert (shown.rmse, shown.r_squared) == (result.rmse, result.r_squared)
    np.testing.assert_array_equal(shown.y_fit.magnitude, result.y_fit.magnitude)
    assert live.active_replica_ids == active_now


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
    assert (shown.representative_index, shown.rmse, shown.r_squared) == (
        result.representative_index,
        result.rmse,
        result.r_squared,
    )
    np.testing.assert_array_equal(shown.quality_samples['r_squared'], result.quality_samples['r_squared'])
    assert selection.active_replica_ids == ['a']


def _legacy(ms: MeasurementSet, result: FitResult) -> FitResult:
    """*result* as a per-replicate file that scored its pool against every replicate it was given.

    Its reported fit is a pick scored the same way, and it records neither the
    replicates it was given, nor the scoring marker, nor a fingerprint.
    """
    old = _round_trip(result)
    old.quality_samples = _scores(ms.signals.mean(axis=0), ms.concentrations, old.parameter_samples)
    picked = int(np.argmin(old.quality_samples['r_squared']))
    select_representative(old, ms.to_assay(IDAAssay, conditions=_CONDITIONS), picked)
    for key in ('quality_scored_on', 'data_fingerprint', 'active_replica_ids'):
        del old.metadata[key]
    return old


def test_legacy_per_replicate_file_is_rescored_on_the_used_replicates(fitted):
    ms, result = fitted
    old = _legacy(ms, result)

    status, shown = verify_imported_result(old, ms)

    assert status == 'rescored_legacy'
    for key in ('rmse', 'r_squared'):
        np.testing.assert_allclose(shown.quality_samples[key], result.quality_samples[key], rtol=1e-12, atol=0)
    assert shown.representative_index == result.representative_index
    assert 'fitted_representative_index' not in shown.metadata
    assert shown.rmse == pytest.approx(result.rmse, rel=1e-12)
    assert shown.r_squared == pytest.approx(result.r_squared, rel=1e-12)
    np.testing.assert_allclose(shown.y_fit.magnitude, result.y_fit.magnitude, rtol=1e-12)
    for key in _KEYS:
        assert shown.parameters[key].magnitude == result.parameters[key].magnitude
    assert shown.metadata['quality_scored_on'] == 'fitted_replicates'
    assert shown.metadata['data_fingerprint'] == ms.fingerprint()


def test_results_on_other_data_are_refused(fitted):
    """Concentrations rescaled by 1 %: the fingerprint tells, and for a file without one the re-score does."""
    ms, result = fitted
    rescaled = MeasurementSet(concentrations=ms.concentrations * 1.01, signals=ms.signals, replica_ids=ms.replica_ids)

    assert verify_imported_result(_round_trip(result), rescaled)[0] == 'different_data'
    assert verify_imported_result(_legacy(ms, result), rescaled)[0] == 'different_data'


def _released_file(result: FitResult, *, r_squared: float | None = None, rmse: float | None = None) -> dict:
    """*result* as a file from a release without condition units, quality pool or record of the data.

    Such a file stores every condition as a bare number and may report RMSE and
    R² measured on other replicates than the ones the fit used.
    """
    d = json.loads(json.dumps(result.to_dict()))
    for key in ('condition_units', 'quality_samples', 'attempt_samples', 'attempt_quality', 'representative_index'):
        d.pop(key)
    for key in ('quality_scored_on', 'data_fingerprint', 'active_replica_ids'):
        d['metadata'].pop(key)
    for replica_fit in d['replica_fits'] or ():
        replica_fit.pop('condition_units')
    d['rmse'] = d['rmse'] if rmse is None else rmse
    d['r_squared'] = d['r_squared'] if r_squared is None else r_squared
    return d


def test_bare_number_conditions_load_in_the_units_their_assay_holds_them_in(fitted):
    _, result = fitted
    loaded = FitResult.from_dict(_released_file(result))

    for key, value in _CONDITIONS.items():
        assert loaded.conditions[key].units == value.units
        assert loaded.conditions[key].magnitude == value.magnitude

    unknown = _released_file(result)
    unknown['conditions']['temperature'] = 298.0
    with pytest.raises(ValueError, match="no unit for condition 'temperature'"):
        FitResult.from_dict(unknown)


def test_released_per_replicate_file_without_a_pool_is_rescored_on_the_used_replicates(fitted):
    """Its reported R² and RMSE were measured against every replicate it was given; they are measured again."""
    ms, result = fitted
    vector = {key: np.array([result.parameters[key].magnitude]) for key in _KEYS}
    as_given = _scores(ms.signals.mean(axis=0), ms.concentrations, vector)
    as_used = _scores(_used_mean(ms), ms.concentrations, vector)
    released = FitResult.from_dict(
        _released_file(result, rmse=float(as_given['rmse'][0]), r_squared=float(as_given['r_squared'][0]))
    )

    status, shown = verify_imported_result(released, ms)

    assert status == 'rescored_legacy'
    assert shown.r_squared == pytest.approx(as_used['r_squared'][0], rel=1e-12)
    assert shown.rmse == pytest.approx(as_used['rmse'][0], rel=1e-12)
    for key in _KEYS:
        assert shown.parameters[key].magnitude == result.parameters[key].magnitude
    assert shown.metadata['data_fingerprint'] == ms.fingerprint()
    rescaled = MeasurementSet(concentrations=ms.concentrations * 1.01, signals=ms.signals, replica_ids=ms.replica_ids)
    assert verify_imported_result(released, rescaled)[0] == 'different_data'


def test_results_without_data_are_unverifiable_and_unchanged(fitted):
    _, result = fitted
    imported = _round_trip(result)

    status, shown = verify_imported_result(imported, None)

    assert status == 'unverifiable'
    assert shown is imported


def test_average_fit_without_a_replicate_record_is_scored_on_the_selection_loaded_now():
    """A file that does not name its replicates verifies only on the selection it was made on, and then names it."""
    ms = _measurement_set().with_active(['a', 'b'])
    fit = fit_measurement_set(
        ms,
        IDAAssay,
        _CONDITIONS,
        FitConfig(n_trials=6, custom_bounds=GDA_IDA_RECOVERY_BOUNDS, per_replica=False, seed=2),
    )
    old = _round_trip(fit)
    for key in ('quality_scored_on', 'data_fingerprint', 'active_replica_ids'):
        del old.metadata[key]

    status, shown = verify_imported_result(old, ms)

    assert status == 'verified'
    assert fit_replica_ids(shown) == ['a', 'b']
    assert verify_imported_result(old, ms.with_active(['a', 'b', 'c']))[0] == 'different_data'
    assert verify_imported_result(old, ms.with_active(['a']))[0] == 'different_data'
