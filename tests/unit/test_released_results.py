"""Results files written by released versions, imported against the data they were made on.

The fixtures under ``tests/fixtures/results`` are genuine exports, each written
by the version of the app its entry in that folder's README names. The five
released files fit ``data/IDA_system.txt`` with the demo conditions below;
``unmarked_gda.json`` fits the synthetic GDA titration beside it and records no
``model_arithmetic``, so its scores are those of the earlier equilibrium
arithmetic. What the app shows for such a file is decided by
:func:`verify_imported_result`, so each fixture pins the status and the numbers
a user importing it sees.

Expected scores are computed here from the replicate rows the file names,
independently of the masking and averaging the pipeline does.
"""

from __future__ import annotations

import contextlib
import json
from pathlib import Path

import numpy as np
import pytest

from core.assays.gda import GDAAssay
from core.assays.ida import IDAAssay
from core.data_processing.measurement_set import MeasurementSet
from core.io import load_measurements
from core.models.equilibrium import MODEL_ARITHMETIC, legacy_arithmetic
from core.optimizer.filters import calculate_fit_metrics
from core.pipeline.fit_pipeline import (
    FitResult,
    fit_replica_ids,
    fitted_representative_index,
    representative_view,
    scoring_assay,
    verify_imported_result,
)
from core.units import Q_

_ROOT = Path(__file__).resolve().parents[2]
_FIXTURES = _ROOT / 'tests' / 'fixtures' / 'results'
_DEMO_DATA = _ROOT / 'data' / 'IDA_system.txt'

#: The conditions every fixture was fitted with (the demo IDA system).
_CONDITIONS = {'Ka_dye': Q_(16.8e6, '1/M'), 'h0': Q_(4.3e-6, 'M'), 'd0': Q_(6e-6, 'M')}

_KEYS = ('Ka_guest', 'I0', 'I_dye_free', 'I_dye_bound')

_UNMARKED_DATA = _FIXTURES / 'unmarked_gda_data.txt'

#: The conditions ``unmarked_gda.json`` was fitted with (the synthetic GDA system).
_UNMARKED_CONDITIONS = {'Ka_dye': Q_(1e7, '1/M'), 'h0': Q_(2e-7, 'M'), 'g0': Q_(2e-7, 'M')}


@pytest.fixture(scope='module')
def demo() -> MeasurementSet:
    """The data every fixture was made on."""
    return MeasurementSet.from_dataframe(load_measurements(_DEMO_DATA), source_file=str(_DEMO_DATA))


def _released(name: str) -> FitResult:
    return FitResult.from_dict(json.loads((_FIXTURES / f'{name}.json').read_text()))


def _score_on(ms: MeasurementSet, replica_ids: list[str], result: FitResult) -> tuple[float, float]:
    """RMSE and R² of *result*'s reported parameters against the mean of *replica_ids*' own rows."""
    rows = [ms.replica_ids.index(rid) for rid in replica_ids]
    signal = ms.signals[rows].mean(axis=0)
    assay = IDAAssay(x_data=Q_(np.array(ms.concentrations), 'M'), y_data=Q_(signal, 'au'), **_CONDITIONS)
    vector = np.array([result.parameters[k].magnitude for k in _KEYS], dtype=float)
    return calculate_fit_metrics(signal, assay.forward_model(vector).magnitude)


@pytest.mark.parametrize('name', ['v1_3_0_avg', 'v150_avg', 'v150_pr_all'])
def test_a_released_file_whose_numbers_reproduce_is_shown_unchanged(name, demo):
    """Its stored RMSE and R² are measured again on the replicates it used and hold."""
    released = _released(name)

    status, shown = verify_imported_result(released, demo)

    assert status == 'verified'
    assert (shown.rmse, shown.r_squared) == (released.rmse, released.r_squared)
    assert shown.metadata['data_fingerprint'] == demo.fingerprint()


@pytest.mark.parametrize('name', ['v1_3_0_pr_drop', 'v150_pr_drop'])
def test_a_released_file_scored_on_every_replicate_is_rescored_on_the_ones_it_used(name, demo):
    """It left replicate '0' out of the fit but scored against all eight; the shown quality drops it."""
    released = _released(name)
    used = fit_replica_ids(released)
    assert used == ['1', '2', '3', '4', '5', '6', '7']

    status, shown = verify_imported_result(released, demo)

    assert status == 'rescored_legacy'
    rmse, r_squared = _score_on(demo, used, shown)
    assert shown.rmse == pytest.approx(rmse, rel=1e-9)
    assert shown.r_squared == pytest.approx(r_squared, rel=1e-9)
    assert shown.r_squared != released.r_squared
    assert fit_replica_ids(shown) == used


def test_the_individual_fits_of_a_released_per_replicate_file_are_measured_again_too(demo):
    """Every number the copy carries is the present arithmetic's, the nested ones included.

    The copy records that arithmetic, and a per-replicate file stores each
    replicate's own fit beside the pooled one; those are measured against the
    replicate they were fitted on.
    """
    released = _released('v150_pr_drop')

    _, shown = verify_imported_result(released, demo)

    for rid, stored, sub in zip(fit_replica_ids(released), released.replica_fits, shown.replica_fits):
        rmse, r_squared = _score_on(demo, [rid], sub)
        assert sub.rmse == pytest.approx(rmse, rel=1e-12)
        assert sub.r_squared == pytest.approx(r_squared, rel=1e-12)
        assert sub.metadata['model_arithmetic'] == MODEL_ARITHMETIC
        assert stored.rmse != sub.rmse, 'the file stored the earlier arithmetic here'
        assert sub.parameters == stored.parameters


def test_a_released_file_is_refused_on_other_data(demo):
    """Concentrations rescaled by 1 %: the fit's numbers do not describe these data."""
    other = MeasurementSet(
        concentrations=np.array(demo.concentrations) * 1.01,
        signals=np.array(demo.signals),
        replica_ids=demo.replica_ids,
    )

    assert verify_imported_result(_released('v150_pr_all'), other)[0] == 'different_data'
    assert verify_imported_result(_released('v1_3_0_avg'), other)[0] == 'different_data'


def test_conditions_stored_as_bare_numbers_load_in_the_units_their_assay_holds_them_in():
    """A file from a release that stored no condition units still carries physical conditions."""
    loaded = _released('v1_3_0_avg')

    for key, value in _CONDITIONS.items():
        assert loaded.conditions[key].units == value.units
        assert loaded.conditions[key].magnitude == pytest.approx(value.magnitude)


def test_a_condition_with_no_known_unit_is_refused():
    unknown = json.loads((_FIXTURES / 'v1_3_0_avg.json').read_text())
    unknown['conditions']['temperature'] = 298.0

    with pytest.raises(ValueError, match="no unit for condition 'temperature'"):
        FitResult.from_dict(unknown)


# ---------------------------------------------------------------------------
# A file written before the results format recorded the equilibrium arithmetic
# ---------------------------------------------------------------------------


@pytest.fixture(scope='module')
def unmarked_data() -> MeasurementSet:
    """The synthetic GDA titration ``unmarked_gda.json`` was fitted on."""
    return MeasurementSet.from_dataframe(load_measurements(_UNMARKED_DATA), source_file=_UNMARKED_DATA.name)


def _gda_scores(ms: MeasurementSet, rows: np.ndarray) -> np.ndarray:
    """RMSE and R² of each parameter vector in *rows* against the mean of the replicate rows."""
    signal = np.asarray(ms.signals).mean(axis=0)
    assay = GDAAssay(x_data=Q_(np.asarray(ms.concentrations), 'M'), y_data=Q_(signal, 'au'), **_UNMARKED_CONDITIONS)
    return np.array([calculate_fit_metrics(signal, assay.forward_model(row).magnitude) for row in rows])


def _pool_rows(result: FitResult) -> np.ndarray:
    return np.column_stack([np.asarray(result.parameter_samples[k], dtype=float) for k in _KEYS])


def test_a_file_without_an_arithmetic_marker_keeps_its_fit_and_shows_present_scores(unmarked_data):
    """Its stored scores were computed by an earlier, less precise equilibrium solve.

    The fit itself — the parameters, the pool and the reported attempt — is the
    file's; only the numbers measured from it are computed again.
    """
    released = _released('unmarked_gda')
    assert 'model_arithmetic' not in released.metadata

    status, shown = verify_imported_result(released, unmarked_data)

    assert status == 'rescored_precision'
    assert shown.representative_index == released.representative_index
    for key in _KEYS:
        assert shown.parameters[key].magnitude == released.parameters[key].magnitude
        np.testing.assert_array_equal(shown.parameter_samples[key], released.parameter_samples[key])
    rmse, r_squared = _gda_scores(unmarked_data, _pool_rows(shown)[[shown.representative_index]])[0]
    assert shown.rmse == pytest.approx(rmse, rel=1e-9)
    assert shown.r_squared == pytest.approx(r_squared, rel=1e-9)
    assert shown.metadata['model_arithmetic'] == MODEL_ARITHMETIC
    # The file's own numbers really differ from these, so the import exercised
    # both arithmetics rather than passing on a pool nothing moves.
    stored = np.asarray(released.quality_samples['rmse'], dtype=float)
    assert np.max(np.abs(np.asarray(shown.quality_samples['rmse']) / stored - 1)) > 1e-5


def test_a_file_without_a_marker_is_still_refused_on_other_data(unmarked_data):
    """A 1 % rescale of either axis is other data, whether or not the file fingerprints them."""
    released = _released('unmarked_gda')
    blind = _released('unmarked_gda')
    del blind.metadata['data_fingerprint']  # forces the refusal onto the scores alone

    for other in (
        MeasurementSet(
            concentrations=np.asarray(unmarked_data.concentrations) * 1.01,
            signals=np.asarray(unmarked_data.signals),
            replica_ids=unmarked_data.replica_ids,
        ),
        MeasurementSet(
            concentrations=np.asarray(unmarked_data.concentrations),
            signals=np.asarray(unmarked_data.signals) * 1.01,
            replica_ids=unmarked_data.replica_ids,
        ),
    ):
        assert verify_imported_result(released, other)[0] == 'different_data'
        assert verify_imported_result(blind, other)[0] == 'different_data'


def test_a_file_naming_an_arithmetic_this_version_does_not_have_is_not_checked(unmarked_data):
    """The marker names the arithmetic that wrote the scores, and only two can be computed here.

    A file written by a later version records a third; neither the present
    solve nor the earlier one reproduces its scores, so nothing about it is
    confirmed and its numbers are shown as stored.
    """
    later = _released('unmarked_gda')
    later.metadata['model_arithmetic'] = MODEL_ARITHMETIC + 1

    status, shown = verify_imported_result(later, unmarked_data)

    assert status == 'unverifiable'
    assert shown is later


def test_a_file_checked_with_the_present_arithmetic_alone_is_refused(unmarked_data, monkeypatch):
    """Without the arithmetic that wrote it, its stored scores do not reproduce."""
    monkeypatch.setattr('core.pipeline.fit_pipeline.legacy_arithmetic', contextlib.nullcontext)

    assert verify_imported_result(_released('unmarked_gda'), unmarked_data)[0] == 'different_data'


def test_a_shown_file_exported_again_verifies_on_its_own_numbers(unmarked_data):
    """Its numbers and its marker are the present arithmetic's, so the next import checks it directly."""
    _, shown = verify_imported_result(_released('unmarked_gda'), unmarked_data)

    status, again = verify_imported_result(FitResult.from_dict(json.loads(json.dumps(shown.to_dict()))), unmarked_data)

    assert status == 'verified'
    assert (again.rmse, again.r_squared) == (shown.rmse, shown.r_squared)


def test_a_file_whose_curve_alone_does_not_reproduce_is_shown_with_the_curve_drawn_now(unmarked_data):
    """Scores that reproduce do not vouch for the curve stored beside them.

    The check measures the curve as well, so a copy that kept one the present
    arithmetic does not draw would be refused the next time it is imported. The
    file here holds no pool, and its stored scores are the ones both
    arithmetics reach — the binding is weak enough for that — beside a curve
    that is not the one drawn now, as a file written where the two arithmetics
    part company carries.
    """
    released = _released('unmarked_gda')
    vector = _pool_rows(released)[released.representative_index].copy()
    vector[0] = 1e6  # weak binding: both arithmetics score this fit within the gate
    assay = scoring_assay(unmarked_data, released)
    with legacy_arithmetic():
        stored_rmse, stored_r_squared, stored_x, stored_y = representative_view(assay, vector)
    rmse, r_squared, _, y_fit = representative_view(assay, vector)
    assert (stored_rmse, stored_r_squared) == pytest.approx((rmse, r_squared), rel=1e-6), 'the scores pass the gate'
    released.parameters = {k: Q_(vector[i], released.parameters[k].units) for i, k in enumerate(_KEYS)}
    released.parameter_samples, released.quality_samples = {}, {}
    released.representative_index = None
    released.rmse, released.r_squared, released.x_fit = stored_rmse, stored_r_squared, stored_x
    released.y_fit = stored_y * (1.0 + 2e-6)  # a curve the present arithmetic does not draw

    status, shown = verify_imported_result(released, unmarked_data)

    assert status == 'rescored_precision'
    np.testing.assert_allclose(shown.y_fit.magnitude, y_fit.magnitude, rtol=1e-15)
    assert verify_imported_result(FitResult.from_dict(json.loads(json.dumps(shown.to_dict()))), unmarked_data)[0] == (
        'verified'
    )


def _ka_of_equal_r2(ms: MeasurementSet, row: np.ndarray, target: float, below: float, above: float) -> float:
    """The binding constant at which the fit *row* reaches R² *target*, by bisection in log Ka.

    *below* and *above* are two binding constants whose R² brackets *target*;
    R² is monotone between them, so the crossing is unique.
    """
    for _ in range(60):
        middle = np.sqrt(below * above)
        trial = row.copy()
        trial[0] = middle
        if _gda_scores(ms, trial[None, :])[0, 1] < target:
            below = middle
        else:
            above = middle
    return float(np.sqrt(below * above))


def _near_tie_ka(ms: MeasurementSet, row: np.ndarray, rival: np.ndarray) -> float:
    """A binding constant at which the two arithmetics rank *row* and *rival* the other way round.

    The R² of the fit built from *row* crosses the R² of *rival* at a binding
    constant each arithmetic puts in a slightly different place; between the two
    crossings the file's ranking and the present one disagree. The crossing is
    sought on both sides of *row*'s own binding constant, since which of the two
    lies first depends on the sign of the shift.
    """
    for below, above in ((row[0] / 10.0, row[0]), (row[0] * 10.0, row[0])):
        with legacy_arithmetic():
            stored = _ka_of_equal_r2(ms, row, _gda_scores(ms, rival[None, :])[0, 1], below, above)
        present = _ka_of_equal_r2(ms, row, _gda_scores(ms, rival[None, :])[0, 1], below, above)
        trial = row.copy()
        trial[0] = float(np.sqrt(stored * present))
        pair = np.vstack([trial, rival])
        with legacy_arithmetic():
            stored_pair = _gda_scores(ms, pair)
        present_pair = _gda_scores(ms, pair)
        if stored_pair[1, 1] > stored_pair[0, 1] and present_pair[0, 1] > present_pair[1, 1]:
            return float(trial[0])
    raise AssertionError('no binding constant near this fit is ranked differently by the two arithmetics')


def test_a_near_tie_in_the_pool_keeps_the_fit_s_own_representative(unmarked_data):
    """Re-scoring must not turn the fit's own choice into what looks like a user's pick."""
    released = _released('unmarked_gda')
    rows = _pool_rows(released)
    with legacy_arithmetic():
        stored_scores = _gda_scores(unmarked_data, rows)
    moved = int(np.argmax(np.abs(_gda_scores(unmarked_data, rows)[:, 0] / stored_scores[:, 0] - 1)))
    near_tie = rows[released.representative_index].copy()
    near_tie[0] = _near_tie_ka(unmarked_data, near_tie, rows[moved])
    pair = np.vstack([near_tie, rows[moved]])

    assay = scoring_assay(unmarked_data, released)
    with legacy_arithmetic():
        stored = _gda_scores(unmarked_data, pair)
        rmse, r_squared, x_fit, y_fit = representative_view(assay, pair[1])
    present = _gda_scores(unmarked_data, pair)
    assert stored[1, 1] > stored[0, 1], 'the file ranks the second fit first'
    assert present[0, 1] > present[1, 1], 'the present arithmetic ranks the first fit first'

    released.parameter_samples = {k: pair[:, i].copy() for i, k in enumerate(_KEYS)}
    released.quality_samples = {'rmse': stored[:, 0].copy(), 'r_squared': stored[:, 1].copy()}
    released.representative_index = 1
    released.parameters = {k: Q_(pair[1, i], released.parameters[k].units) for i, k in enumerate(_KEYS)}
    released.rmse, released.r_squared, released.x_fit, released.y_fit = rmse, r_squared, x_fit, y_fit

    status, shown = verify_imported_result(released, unmarked_data)

    assert status == 'rescored_precision'
    assert shown.representative_index == 1
    assert fitted_representative_index(shown) == 1
