"""The input-aware interval with an error several inputs have in common — single datasets.

- Direct binding, one source shared by the fixed concentration and the titrant.
  Every concentration then moves by the same factor ``1 + e``, and the binding
  model is homogeneous: scaling every concentration by ``c`` and the binding
  constant by ``1 / c`` scales every species by ``c``, which the signal
  coefficients absorb. So ``S(K, e) = S_entered(K (1 + e))`` and the penalised
  profile is ``P(k) = min over e of [n log S_entered(k (1 + e)) + (e / s)²]``,
  built here from the fixed-input profile alone — no moved assay, no loading, no
  inner solve of the engine. The data cannot tell the source from Ka, so the
  fit leaves it where it was entered and the interval widens.
- Competitive binding, inputs with an error of their own and one in common: the
  fit reports a shift per source, and the record it writes is enough for an
  import to find the inputs where the fit put them and reproduce its scores.
"""

import json

import numpy as np
import pytest
from scipy.optimize import brentq, minimize_scalar

from core.assays.dba import DBAAssay
from core.assays.ida import IDAAssay
from core.data_processing.measurement_set import MeasurementSet
from core.pipeline.fit_pipeline import (
    FitConfig,
    FitResult,
    _fitted_offsets,
    _resolve_bounds,
    fit_assay,
    fit_measurement_set,
    verify_imported_result,
)
from core.pipeline.inputs import TITRANT, ErrorModel, InputSpec, SharedSource, shared_key
from core.pipeline.varpro import Projection
from core.units import Q_
from tests.conftest import DBA_TRUE, IDA_TRUE, _make_dba_data, _make_ida_data

_SIGMA = 0.04


@pytest.fixture(scope='module')
def dba_with_a_common_scale():
    x, y = _make_dba_data(DBA_TRUE, n_points=20, mode='DtoH')
    y = y + np.random.default_rng(8).normal(0.0, 0.01 * np.ptp(y), y.size)
    assay = DBAAssay(x_data=Q_(x, 'M'), y_data=Q_(y, 'au'), fixed_conc=Q_(DBA_TRUE['fixed_conc'], 'M'), mode='DtoH')
    source = SharedSource('Stock calibration', 100 * _SIGMA, ('fixed_conc', TITRANT))
    return assay, source, fit_assay(assay, FitConfig(errors=ErrorModel(shared=(source,))))


def test_a_source_common_to_every_concentration_widens_the_interval_by_its_own_sigma(dba_with_a_common_scale):
    assay, source, result = dba_with_a_common_scale
    n = assay.n_points
    entered = Projection(assay, _resolve_bounds(assay, None)).profile('Ka_dye')

    def penalised(k: float) -> float:
        found = minimize_scalar(
            lambda e: n * np.log(entered(k * (1.0 + e))) + (e / _SIGMA) ** 2,
            bounds=(-0.5, 0.5),
            method='bounded',
            options={'xatol': 1e-10},
        )
        return float(found.fun)

    profile, fit = result.aware.profiles['Ka_dye'], result.aware.fit
    excess = profile.threshold - fit.objective
    k_hat = float(result.conditional.parameters['Ka_dye'].magnitude)
    lowest = penalised(k_hat)  # e = 0 at the fixed-input fit: nothing lower exists
    assert fit.objective == pytest.approx(lowest, abs=1e-6)

    def edge(side: float) -> float:
        return brentq(lambda t: penalised(10.0**t) - lowest - excess, np.log10(k_hat), np.log10(k_hat) + side)

    interval = result.intervals['Ka_dye']
    assert not (interval.open_low or interval.open_high)
    conditional = result.conditional.intervals['Ka_dye']
    # The source moves each edge outward by some 3e-3 decades here, so the agreement asked for resolves it.
    assert np.log10(interval.low) == pytest.approx(edge(-1.5), abs=1e-5)
    assert np.log10(interval.high) == pytest.approx(edge(1.5), abs=1e-5)
    assert np.log10(conditional.low / interval.low) > 1e-3 and np.log10(interval.high / conditional.high) > 1e-3
    # The data say nothing about the source: it stays as entered, and takes none of their degrees of freedom.
    shift = result.input_shifts[shared_key(source.name)]
    assert set(result.input_shifts) == {shared_key(source.name)}
    assert abs(shift.z) < 0.05
    assert interval.dof == pytest.approx(conditional.dof, abs=0.05)
    assert set(fit.input_offsets) == {'fixed_conc', TITRANT}


def test_own_and_shared_sources_are_reported_per_source_and_the_record_verifies():
    x, y = _make_ida_data(IDA_TRUE, n_points=12)
    rng = np.random.default_rng(5)
    signals = np.vstack([y + rng.normal(0.0, 0.005 * np.ptp(y), y.size) for _ in range(3)])
    ms = MeasurementSet(concentrations=x, signals=signals, replica_ids=('a', 'b', 'c'))
    # Host and dye come from one stock whose concentration was taken 6 % too high.
    conditions = {
        'Ka_dye': Q_(IDA_TRUE['Ka_dye'], '1/M'),
        'h0': Q_(IDA_TRUE['h0'] * 1.06, 'M'),
        'd0': Q_(IDA_TRUE['d0'] * 1.06, 'M'),
    }
    source = SharedSource('Host and dye stock', 4.0, ('h0', 'd0'))
    errors = ErrorModel(specs={'h0': InputSpec.sigma_pct(3), 'd0': InputSpec.sigma_pct(3)}, shared=(source,))
    result = fit_measurement_set(ms, IDAAssay, conditions, FitConfig(per_replica=False, errors=errors))

    key = shared_key(source.name)
    assert list(result.input_shifts) == ['h0', 'd0', key]
    assert result.input_shifts[key].z == pytest.approx(result.input_shifts[key].fraction / 0.04)
    assert result.fit_config['shared_sources'] == [{'name': source.name, 'sigma_pct': 4.0, 'inputs': ['h0', 'd0']}]
    interval = result.intervals['Ka_guest']
    assert interval.low < IDA_TRUE['Ka_guest'] < interval.high

    restored = FitResult.from_dict(json.loads(json.dumps(result.to_dict())))
    assert restored.input_shifts == result.input_shifts
    # Each input sits where its own source and the common one put it together.
    common = result.input_shifts[key].fraction
    moved = _fitted_offsets(restored)
    assert set(moved) == {'h0', 'd0'}
    for own in ('h0', 'd0'):
        assert 1 + moved[own] == pytest.approx((1 + result.input_shifts[own].fraction) * (1 + common), rel=1e-14)
    assert abs(common) > 1e-3, 'the common error is large enough for the scores to depend on it'
    status, _ = verify_imported_result(restored, ms)
    assert status == 'verified'
