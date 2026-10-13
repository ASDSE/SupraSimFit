"""The homogeneity identity of the binding models, through the refits of the sensitivity analysis.

Every registered binding model is built from mass balances and association
constants in 1/M only. Multiplying every concentration of an experiment (the
fixed totals, the titrant and the titrant stock) by ``c`` and dividing every
entered binding constant by ``c`` is therefore a change of the concentration
unit and nothing else: the signal coefficients take up ``1/c``, the
least-squares problem is the same, and every fitted constant is divided by
``c``. It holds whatever the data are, as long as the box of the fit is the
same problem after the change of unit too: a signal bound of zero or infinity
is (the default box has no other), while the Ka box is a pair of numbers in
1/M, so the fitted constants have to lie strictly inside it.

Two consequences are checked for the six binding assays, with constant totals
and with totals a titrant stock dilutes by 10 %:

- the finite scaling itself, by ordinary fits of the scaled experiment: log10 Ka
  moves by ``-log10 c`` to the resolution of the search. A refit that answers to
  an input it should not, a total that is not diluted, or a search that stops
  short of the optimum breaks it;
- its derivative at ``c = 1`` (Euler): the elasticities of each fitted constant
  add up to ``-1`` over the concentrations, minus the entered binding constants
  (``homogeneity_sum``). With a stock declared this holds only if the titrant's
  elasticity moves the stock with the titrant, which is how the refits treat it.
  The sum is read off a sensitivity run, which works it out from its own
  elasticity refits on every run, and holds nothing back over it.
"""

import numpy as np
import pytest

import core.pipeline.sensitivity as sens
from core.assays.dba import DBAAssay
from core.assays.gda import GDAAssay
from core.assays.h2g import H2GAssay
from core.assays.hg2 import HG2Assay
from core.assays.ida import IDAAssay
from core.assays.registry import ASSAY_REGISTRY
from core.data_processing.measurement_set import MeasurementSet
from core.pipeline.budget import homogeneity_sum
from core.pipeline.fit_pipeline import FitConfig, _resolve_bounds, fit_measurement_set
from core.pipeline.inputs import TITRANT, TITRANT_STOCK, ErrorModel, InputSpec, perturbable_inputs
from core.pipeline.sensitivity import SensitivityConfig, SensitivityMode, run_sensitivity
from core.units import Q_, Quantity
from tests.conftest import (
    DBA_TRUE,
    GDA_TRUE,
    H2G_TRUE,
    HG2_TRUE,
    IDA_TRUE,
    _make_dba_data,
    _make_gda_data,
    _make_h2g_data,
    _make_hg2_data,
    _make_ida_data,
)

_N_POINTS = 20

#: Fraction of the last point's volume that is titrant stock in the diluted cases.
_DILUTION = 0.10

#: Relative noise on the signal range. It keeps the optimum off an exactly
#: reproducible curve, so it moves with every input like a measured one does.
_NOISE = 0.01


def _conditions(true: dict, keys: tuple[str, ...], **extra) -> dict:
    units = {'Ka_dye': '1/M'}
    return {**{key: Q_(true[key], units.get(key, 'M')) for key in keys}, **extra}


_CASES = {
    'IDA': (IDAAssay, _make_ida_data, IDA_TRUE, _conditions(IDA_TRUE, ('Ka_dye', 'h0', 'd0'))),
    'GDA': (GDAAssay, _make_gda_data, GDA_TRUE, _conditions(GDA_TRUE, ('Ka_dye', 'h0', 'g0'))),
    'DBA_HtoD': (
        DBAAssay,
        lambda true, n_points: _make_dba_data(true, n_points=n_points, mode='HtoD'),
        DBA_TRUE,
        _conditions(DBA_TRUE, ('fixed_conc',), mode='HtoD'),
    ),
    'DBA_DtoH': (DBAAssay, _make_dba_data, DBA_TRUE, _conditions(DBA_TRUE, ('fixed_conc',), mode='DtoH')),
    'HG2': (HG2Assay, _make_hg2_data, HG2_TRUE, _conditions(HG2_TRUE, ('h0',))),
    'H2G': (H2GAssay, _make_h2g_data, H2G_TRUE, _conditions(H2G_TRUE, ('h0',))),
}


def _experiment(name: str, diluted: bool):
    """``(ms, assay_cls, conditions)`` of one case, with noise on the conftest ground truth."""
    assay_cls, make, true, conditions = _CASES[name]
    x, y = make(true, n_points=_N_POINTS)
    if diluted:
        conditions = {**conditions, TITRANT_STOCK: Q_(float(x.max()) / _DILUTION, 'M')}
        blank = MeasurementSet(concentrations=x, signals=np.zeros((1, x.size)), replica_ids=('r0',))
        assay = blank.to_assay(assay_cls, conditions=conditions)
        y = assay.forward_model(np.array([true[key] for key in assay.parameter_keys])).magnitude
    rng = np.random.default_rng(1)
    y = y + rng.normal(0.0, _NOISE * np.ptp(y), y.size)
    return MeasurementSet(concentrations=x, signals=y.reshape(1, -1), replica_ids=('r0',)), assay_cls, conditions


def _scaled(ms: MeasurementSet, conditions: dict, c: float):
    """The same experiment with every concentration times *c* and every entered binding constant over *c*."""
    scaled = {}
    for key, value in conditions.items():
        if not isinstance(value, Quantity):
            scaled[key] = value
        elif value.is_compatible_with('M'):
            scaled[key] = value * c
        else:
            scaled[key] = value / c
    moved = MeasurementSet(concentrations=np.asarray(ms.concentrations) * c, signals=ms.signals, replica_ids=('r0',))
    return moved, scaled


@pytest.mark.parametrize('diluted', [False, True], ids=['constant-totals', 'diluted'])
@pytest.mark.parametrize('name', list(_CASES))
def test_fitted_constants_follow_the_concentration_unit(name, diluted, monkeypatch):
    ms, assay_cls, conditions = _experiment(name, diluted)
    fit_config = FitConfig()
    baseline = fit_measurement_set(ms, assay_cls, conditions, fit_config)
    assay = ms.to_assay(assay_cls, conditions=conditions)
    ka_keys = ASSAY_REGISTRY[assay.assay_type].log_scale_keys
    one_ka = len(ka_keys) == 1

    # The premise of the identity: the fitted constants are inside their box, and
    # every other bound reads the same in any concentration unit.
    for key, (low, high) in _resolve_bounds(assay, fit_config.custom_bounds).items():
        if key in ka_keys:
            assert low < baseline.parameters[key] < high, key
        else:
            assert low.magnitude == 0 and high.magnitude in (0, np.inf), key

    log_ka = {key: np.log10(baseline.parameters[key].to('1/M').magnitude) for key in ka_keys}
    for c in (0.5, 1.25, 2.0):
        scaled_ms, scaled_conditions = _scaled(ms, conditions, c)
        refit = fit_measurement_set(scaled_ms, assay_cls, scaled_conditions, fit_config)
        for key in ka_keys:
            moved = np.log10(refit.parameters[key].to('1/M').magnitude) - log_ka[key]
            assert moved == pytest.approx(-np.log10(c), abs=1e-6 if one_ka else 1e-4), (key, c)

    # The smallest design a run takes: the elasticities do not depend on it.
    monkeypatch.setattr(sens, '_SOBOL_BLOCKS', 2)
    monkeypatch.setattr(sens, '_SOBOL_SAMPLE_SIZES', (4,))
    errors = ErrorModel(specs={TITRANT: InputSpec.sigma_pct(1.0)})
    result = run_sensitivity(
        ms,
        assay_cls,
        conditions,
        fit_config,
        SensitivityConfig(SensitivityMode.SOBOL, 4, errors, seed=1),
        max_workers=1,
    )
    kinds = dict(perturbable_inputs(conditions))
    assert set(result.elasticity) == set(ka_keys)
    for key in ka_keys:
        elasticity = result.elasticity[key]
        assert set(elasticity) == set(kinds)
        assert result.homogeneity[key] == homogeneity_sum(elasticity, kinds)
        size = 1.0 if one_ka else sum(abs(value) for value in elasticity.values())
        assert result.homogeneity[key] == pytest.approx(-1.0, abs=1e-3 * size), (key, elasticity)
        # The identity holds, so the run holds nothing back over it (GDA's interval is open here, which it may).
        assert result.withheld[key] != 'homogeneity', (key, result.homogeneity[key])
