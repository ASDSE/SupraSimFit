"""Results files written by released versions, imported against the data they were made on.

The fixtures under ``tests/fixtures/results`` are genuine exports: each was
produced by the release its name carries, fitting ``data/IDA_system.txt`` with
the demo conditions below. What the app shows for such a file is decided by
:func:`verify_imported_result`, so each fixture pins the status and the numbers
a user importing it sees.

Expected scores are computed here from the replicate rows the file names,
independently of the masking and averaging the pipeline does.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from core.assays.ida import IDAAssay
from core.data_processing.measurement_set import MeasurementSet
from core.io import load_measurements
from core.optimizer.filters import calculate_fit_metrics
from core.pipeline.fit_pipeline import FitResult, fit_replica_ids, verify_imported_result
from core.units import Q_

_ROOT = Path(__file__).resolve().parents[2]
_FIXTURES = _ROOT / 'tests' / 'fixtures' / 'results'
_DEMO_DATA = _ROOT / 'data' / 'IDA_system.txt'

#: The conditions every fixture was fitted with (the demo IDA system).
_CONDITIONS = {'Ka_dye': Q_(16.8e6, '1/M'), 'h0': Q_(4.3e-6, 'M'), 'd0': Q_(6e-6, 'M')}

_KEYS = ('Ka_guest', 'I0', 'I_dye_free', 'I_dye_bound')


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
