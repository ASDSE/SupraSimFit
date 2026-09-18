"""Results files written by earlier versions, imported against the data they were made on.

The fixtures under ``tests/fixtures/results`` are genuine exports, each written
by the version of the app its entry in that folder's README names. The five
released files and the two ``pr42`` ones fit IDA data with the conditions named
there; ``unmarked_gda.json`` fits the synthetic GDA titration beside it and
records no ``model_arithmetic``, so its scores are those of the earlier
equilibrium arithmetic. What the app shows for such a file is decided by
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
    fit_view,
    verify_imported_result,
)
from core.units import Q_

_ROOT = Path(__file__).resolve().parents[2]
_FIXTURES = _ROOT / 'tests' / 'fixtures' / 'results'
_DEMO_DATA = _ROOT / 'data' / 'IDA_system.txt'

#: The conditions the five released fixtures were fitted with (the demo IDA system).
_CONDITIONS = {'Ka_dye': Q_(16.8e6, '1/M'), 'h0': Q_(4.3e-6, 'M'), 'd0': Q_(6e-6, 'M')}

_KEYS = ('Ka_guest', 'I0', 'I_dye_free', 'I_dye_bound')

_UNMARKED_DATA = _FIXTURES / 'unmarked_gda_data.txt'

#: The conditions ``unmarked_gda.json`` was fitted with (the synthetic GDA system).
_UNMARKED_CONDITIONS = {'Ka_dye': Q_(1e7, '1/M'), 'h0': Q_(2e-7, 'M'), 'g0': Q_(2e-7, 'M')}

_PR42_DATA = _FIXTURES / 'pr42_data.txt'

#: The conditions the ``pr42`` fixtures were fitted with (the synthetic IDA system).
_PR42_CONDITIONS = {'Ka_dye': Q_(5e5, '1/M'), 'h0': Q_(10e-6, 'M'), 'd0': Q_(5e-6, 'M')}


@pytest.fixture(scope='module')
def demo() -> MeasurementSet:
    """The data the five released fixtures were made on."""
    return MeasurementSet.from_dataframe(load_measurements(_DEMO_DATA), source_file=str(_DEMO_DATA))


def _released(name: str) -> FitResult:
    return FitResult.from_dict(json.loads((_FIXTURES / f'{name}.json').read_text()))


def _score_on(ms: MeasurementSet, replica_ids: list[str], result: FitResult, conditions: dict) -> tuple[float, float]:
    """RMSE and R² of *result*'s reported parameters against the mean of *replica_ids*' own rows."""
    rows = [ms.replica_ids.index(rid) for rid in replica_ids]
    signal = ms.signals[rows].mean(axis=0)
    assay = IDAAssay(x_data=Q_(np.array(ms.concentrations), 'M'), y_data=Q_(signal, 'au'), **conditions)
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
    rmse, r_squared = _score_on(demo, used, shown, _CONDITIONS)
    assert shown.rmse == pytest.approx(rmse, rel=1e-9)
    assert shown.r_squared == pytest.approx(r_squared, rel=1e-9)
    assert shown.r_squared != released.r_squared
    assert fit_replica_ids(shown) == used


@pytest.mark.parametrize('name', ['v1_3_0_avg', 'v150_pr_all', 'pr42_avg', 'pr42_pr'])
def test_a_file_written_before_intervals_carries_none(name):
    """Its fit is a multi-start estimate, so nothing in it states a confidence interval."""
    released = _released(name)

    assert released.intervals is None
    assert released.degenerate_keys == ()
    assert released.replica_fits is None
    assert released.parameters['Ka_guest'].magnitude > 0


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
# The two files this branch wrote before the fit engine changed
# ---------------------------------------------------------------------------


@pytest.fixture(scope='module')
def pr42_data() -> MeasurementSet:
    """The synthetic IDA titration the ``pr42`` fixtures were fitted on."""
    return MeasurementSet.from_dataframe(load_measurements(_PR42_DATA), source_file=_PR42_DATA.name)


@pytest.mark.parametrize('name', ['pr42_avg', 'pr42_pr'])
def test_a_multi_start_file_of_this_branch_verifies_on_its_own_numbers(name, pr42_data):
    """One fitted the average of the three replicates, the other each replicate; both used all three."""
    released = _released(name)

    status, shown = verify_imported_result(released, pr42_data)

    assert status == 'verified'
    assert fit_replica_ids(shown) == ['0', '1', '2']
    # The file records no equilibrium arithmetic, so its numbers are the earlier
    # solve's; on these micromolar IDA data the two differ by under 1e-8 relative,
    # far inside the import gate, and the copy keeps the numbers the file holds.
    rmse, r_squared = _score_on(pr42_data, ['0', '1', '2'], shown, _PR42_CONDITIONS)
    assert shown.rmse == pytest.approx(rmse, rel=1e-7)
    assert shown.r_squared == pytest.approx(r_squared, rel=1e-7)
    assert (shown.rmse, shown.r_squared) == (released.rmse, released.r_squared)


def test_a_multi_start_file_of_this_branch_is_refused_on_other_data(pr42_data):
    other = MeasurementSet(
        concentrations=np.asarray(pr42_data.concentrations),
        signals=np.asarray(pr42_data.signals) * 1.01,
        replica_ids=pr42_data.replica_ids,
    )

    assert verify_imported_result(_released('pr42_avg'), other)[0] == 'different_data'
    assert verify_imported_result(_released('pr42_pr'), other)[0] == 'different_data'


# ---------------------------------------------------------------------------
# A file written before the results format recorded the equilibrium arithmetic
# ---------------------------------------------------------------------------


@pytest.fixture(scope='module')
def unmarked_data() -> MeasurementSet:
    """The synthetic GDA titration ``unmarked_gda.json`` was fitted on."""
    return MeasurementSet.from_dataframe(load_measurements(_UNMARKED_DATA), source_file=_UNMARKED_DATA.name)


def _gda_assay(ms: MeasurementSet) -> GDAAssay:
    signal = np.asarray(ms.signals).mean(axis=0)
    return GDAAssay(x_data=Q_(np.asarray(ms.concentrations), 'M'), y_data=Q_(signal, 'au'), **_UNMARKED_CONDITIONS)


def _gda_scores(ms: MeasurementSet, vector: np.ndarray) -> tuple[float, float]:
    """RMSE and R² of one parameter vector against the mean of the replicate rows."""
    assay = _gda_assay(ms)
    return calculate_fit_metrics(assay.y_data.magnitude, assay.forward_model(vector).magnitude)


def _vector(result: FitResult) -> np.ndarray:
    return np.array([float(result.parameters[k].magnitude) for k in _KEYS])


def test_a_file_without_an_arithmetic_marker_keeps_its_fit_and_shows_present_scores(unmarked_data):
    """Its stored scores were computed by an earlier, less precise equilibrium solve.

    The fit itself — its parameters — is the file's; only the numbers measured
    from it are computed again.
    """
    released = _released('unmarked_gda')
    assert 'model_arithmetic' not in released.metadata

    status, shown = verify_imported_result(released, unmarked_data)

    assert status == 'rescored_precision'
    for key in _KEYS:
        assert shown.parameters[key].magnitude == released.parameters[key].magnitude
    rmse, r_squared = _gda_scores(unmarked_data, _vector(shown))
    assert shown.rmse == pytest.approx(rmse, rel=1e-12)
    assert shown.r_squared == pytest.approx(r_squared, rel=1e-12)
    assert shown.metadata['model_arithmetic'] == MODEL_ARITHMETIC
    # The file's own number really differs from this one, so the import exercised
    # both arithmetics rather than passing on a score nothing moves.
    assert abs(shown.rmse / released.rmse - 1) > 1e-6


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
    file here stores the scores both arithmetics reach — its binding constant
    is weak enough for that — beside a curve that is not the one drawn now, as
    a file written where the two arithmetics part company carries.
    """
    released = _released('unmarked_gda')
    vector = _vector(released)
    vector[0] = 1e6  # weak binding: both arithmetics score this fit within the gate
    assay = _gda_assay(unmarked_data)
    with legacy_arithmetic():
        stored_rmse, stored_r_squared, stored_x, stored_y = fit_view(assay, vector)
    rmse, r_squared, _, y_fit = fit_view(assay, vector)
    assert (stored_rmse, stored_r_squared) == pytest.approx((rmse, r_squared), rel=1e-6), 'the scores pass the gate'
    released.parameters = {k: Q_(vector[i], released.parameters[k].units) for i, k in enumerate(_KEYS)}
    released.rmse, released.r_squared, released.x_fit = stored_rmse, stored_r_squared, stored_x
    released.y_fit = stored_y * (1.0 + 2e-6)  # a curve the present arithmetic does not draw

    status, shown = verify_imported_result(released, unmarked_data)

    assert status == 'rescored_precision'
    np.testing.assert_allclose(shown.y_fit.magnitude, y_fit.magnitude, rtol=1e-15)
    assert verify_imported_result(FitResult.from_dict(json.loads(json.dumps(shown.to_dict()))), unmarked_data)[0] == (
        'verified'
    )
