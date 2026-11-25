"""The drawn input-aware profile of the demo IDA titration is the profile, and Ka confidence reads it.

The penalised profile is a minimum over the inputs at each Ka, and on the demo
titration that inner problem has two basins whose order changes along Ka. Every
point the curve is drawn through must be the lower of them — no higher than a
fine continuation of the profile reaches at that Ka, continued from either end
of the plotted stretch and from the estimate in both directions — and the
readout of Ka confidence, which reads the curve as it is drawn, must equal that
profile between the drawn points as well.
"""

import pathlib

import numpy as np
import pytest

from core.assays.ida import IDAAssay
from core.data_processing.measurement_set import MeasurementSet
from core.data_processing.preprocessing import apply_preprocessing
from core.io import load_measurements
from core.pipeline.fit_pipeline import FitConfig, _resolve_bounds, fit_measurement_set
from core.pipeline.input_aware import _Point, _Problem
from core.pipeline.inputs import TITRANT, ErrorModel, InputSpec, constraints
from core.pipeline.profile import fit_profile
from core.pipeline.reporting import fit_replica_ids
from core.pipeline.varpro import Projection
from core.units import Q_
from gui.confidence import curve

_DEMO_PATH = pathlib.Path(__file__).resolve().parents[2] / 'data' / 'IDA_system.txt'
_CONDITIONS = {'Ka_dye': Q_(16.8e6, '1/M'), 'h0': Q_(4.3e-6, 'M'), 'd0': Q_(6e-6, 'M')}
# The uncertainties Demo IDA states (gui.fitting_session._DEMO_UNCERTAINTIES).
_ERRORS = ErrorModel(
    specs={
        'Ka_dye': InputSpec.sigma_pct(10.0),
        'h0': InputSpec.sigma_pct(3.0),
        'd0': InputSpec.sigma_pct(3.0),
        TITRANT: InputSpec.sigma_pct(3.0),
    }
)
# The plotted stretch of log10 Ka (the interval is 8.06 to 8.32) and the step of the
# continuation, in decades: fine enough to follow either basin across the stretch.
_STRETCH = (7.4, 8.9)
_STEP = 1 / 200
# Where the readout of the reported issue was taken (log10 Ka).
_READ_AT = 8.376
# Tolerance in units of the rise the cut-off allows: the drawn curve follows the
# profile to 0.1 % of its depth, a few thousandths at two to three such rises.
_TOL = 0.01


@pytest.fixture(scope='module')
def demo():
    ms = MeasurementSet.from_dataframe(load_measurements(_DEMO_PATH))
    apply_preprocessing(ms, [{'name': 'zscore_replica_filter', 'params': {'threshold': 3.5, 'min_replicas': 3}}])
    config = FitConfig(per_replica=False, errors=_ERRORS)
    result = fit_measurement_set(ms, IDAAssay, _CONDITIONS, config)
    used = ms.with_active(fit_replica_ids(result))
    aware = fit_profile(used, IDAAssay, _CONDITIONS, config, **result.profile_arguments()).profiles['Ka_guest'].aware
    assay = used.to_assay(IDAAssay, conditions=_CONDITIONS, use_average=True)
    projection = Projection(assay, _resolve_bounds(assay, None), point_weights=result.point_weights)
    entered = assay.get_conditions()
    problem = _Problem(projection, constraints(_ERRORS, entered), loading=_ERRORS.loading(entered))

    logs = np.log10(aware.grid)
    shown = logs[(logs >= _STRETCH[0]) & (logs <= _STRETCH[1])]
    fine = np.union1d(np.union1d(np.arange(_STRETCH[0], _STRETCH[1] + 1e-12, _STEP), shown), [_READ_AT])
    fit = result.aware.fit
    estimate = np.log10(fit.ka['Ka_guest'])
    coords = np.array([fit.offsets[key] for key in problem.keys]) / problem.unit
    at_fit = _Point(np.nan, {'Ka_guest': fit.ka['Ka_guest']}, coords, np.nan)
    at_entered = _Point(np.nan, {'Ka_guest': 10.0 ** fine[0]}, problem.start_coords(), np.nan)
    sweeps = [
        (fine, at_entered),
        (fine[::-1], at_entered),
        (fine[fine >= estimate], at_fit),
        (fine[fine <= estimate][::-1], at_fit),
    ]
    profile = dict.fromkeys(fine.tolist(), np.inf)
    for xs, point in sweeps:
        for x in xs.tolist():
            point = problem.solve({'Ka_guest': 10.0**x}, point)
            profile[x] = min(profile[x], point.value)
    return aware, profile, assay.n_points


def test_every_drawn_point_is_the_lowest_solution_over_the_inputs(demo):
    aware, profile, _n = demo
    logs = np.log10(aware.grid)
    span = aware.cut - aware.minimum
    shown = (logs >= _STRETCH[0]) & (logs <= _STRETCH[1])
    above = np.array(
        [(value - profile[x]) / s for x, value, s in zip(logs[shown].tolist(), aware.objective[shown], span[shown])]
    )
    worst = int(np.argmax(above))
    assert above[worst] <= _TOL, (
        f'drawn {above[worst]:.3f} cut-off units above the profile at log Ka {logs[shown][worst]:.4f}'
    )


def test_the_readout_reads_the_profile_between_the_drawn_points(demo):
    aware, profile, n = demo
    drawn = curve('Input-aware', 'accent', aware, n, None, '', None)
    i = int(np.argmin(np.abs(np.log10(aware.grid) - _READ_AT)))
    rise = aware.cut[i] - aware.minimum
    # Read from the curve's own lowest point, the readout is the profile's rise above its minimum.
    assert drawn.at(_READ_AT) - np.nanmin(drawn.y) == pytest.approx(profile[_READ_AT] - aware.minimum, abs=_TOL * rise)
