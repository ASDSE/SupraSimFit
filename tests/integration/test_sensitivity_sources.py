"""The variance budget of real refits, against references the run does not compute.

- A source common to every concentration of a direct-binding assay moves Ka by
  exactly ``1 / (1 + e)`` (the homogeneity identity), so its row of the budget
  is ``Var(log10(1 + e))``, known in closed form, and it interacts with nothing.
- A stock behind every concentration of a competitive assay and behind the
  Ka_dye measured with it is a change of the concentration unit as well: every
  refit moves Ka by exactly ``1 / (1 + e)``, which holds only if the shared
  source moves Ka_dye by ``1 / (1 + e)`` while it moves the concentrations by
  ``1 + e``.
- In a competitive assay an error host and dye share moves Ka by the sum of
  both elasticities; every row of the budget agrees with the first-order figure
  from its elasticity, and the shared source outranks the own error of either.
- The random errors of the additions are reported as one item whose variance is,
  to first order, ``sum_j (dY/d delta_j)² sigma²``; the derivatives are taken
  here by finite differences through ordinary fits of a titrant series perturbed
  by this file's own arithmetic.
- Replicates are separate titrations, and the analysis refits their average at
  ``sigma / sqrt(m)``: simulated titrations with independent addition errors,
  averaged and fitted, have that variance.
"""

import math

import numpy as np
import pytest
from scipy.integrate import quad
from scipy.stats import truncnorm

import core.pipeline.sensitivity as sens
from core.assays.dba import DBAAssay
from core.assays.ida import IDAAssay
from core.data_processing.measurement_set import MeasurementSet
from core.models.equilibrium import dba_signal
from core.pipeline.fit_pipeline import FitConfig, fit_measurement_set
from core.pipeline.inputs import ADDITIONS, TITRANT, AdditionError, ErrorModel, InputSpec, SharedSource, shared_key
from core.pipeline.sensitivity import SensitivityConfig, SensitivityMode, default_worker_count, run_sensitivity
from core.units import Q_
from tests.conftest import DBA_TRUE, IDA_TRUE, _make_dba_data, _make_ida_data

_N_POINTS = 20
_N_SAMPLES = 1024
_DBA_CONDITIONS = {'fixed_conc': Q_(DBA_TRUE['fixed_conc'], 'M'), 'mode': 'DtoH'}
_IDA_CONDITIONS = {
    'Ka_dye': Q_(IDA_TRUE['Ka_dye'], '1/M'),
    'h0': Q_(IDA_TRUE['h0'], 'M'),
    'd0': Q_(IDA_TRUE['d0'], 'M'),
}


def _noisy(x: np.ndarray, y: np.ndarray) -> MeasurementSet:
    """One replicate with 1 % of the signal range as noise, so the optimum moves with every input."""
    rng = np.random.default_rng(1)
    signal = y + rng.normal(0.0, 0.01 * np.ptp(y), y.size)
    return MeasurementSet(concentrations=x, signals=signal.reshape(1, -1), replica_ids=('r0',))


def _dba() -> MeasurementSet:
    return _noisy(*_make_dba_data(DBA_TRUE, n_points=_N_POINTS))


def _run(ms, assay_cls, conditions, errors: ErrorModel, seed: int):
    cfg = SensitivityConfig(SensitivityMode.SOBOL, _N_SAMPLES, errors, seed=seed)
    return run_sensitivity(ms, assay_cls, conditions, FitConfig(), cfg, max_workers=default_worker_count())


def test_a_source_common_to_every_concentration_costs_exactly_its_own_variance():
    """DBA dye-to-host, 3 % on host and titrant each, and 4 % common to both.

    Host and titrant are every concentration of the assay, so the common source
    is a change of the concentration unit: ``log10 Ka`` moves by
    ``-log10(1 + e)`` whatever the data, additively. Its variance is that of
    ``log10(1 + e)`` under the truncated normal the source is sampled from, and
    its total index equals its first-order index.
    """
    shared = SharedSource('Stock balance', 4.0, ('fixed_conc', TITRANT))
    errors = ErrorModel(
        specs={'fixed_conc': InputSpec.sigma_pct(3.0), TITRANT: InputSpec.sigma_pct(3.0)}, shared=(shared,)
    )

    result = _run(_dba(), DBAAssay, _DBA_CONDITIONS, errors, seed=1)

    source = truncnorm(a=-1 / 0.04, b=np.inf, loc=0.0, scale=0.04)
    low, high = source.ppf([1e-12, 1 - 1e-12])
    mean = quad(lambda e: math.log10(1 + e) * source.pdf(e), low, high)[0]
    exact = quad(lambda e: (math.log10(1 + e) - mean) ** 2 * source.pdf(e), low, high)[0]

    key = shared_key(shared.name)
    row = next(row for row in result.budget['Ka_dye'].rows if row.source == key)
    half_width = (row.variance_ci[1] - row.variance_ci[0]) / 2
    assert half_width < 0.5 * exact  # the interval says something
    assert abs(row.variance - exact) <= 3 * half_width
    assert row.elasticity == pytest.approx(-1.0, abs=1e-3)
    assert abs(result.sobol_st['Ka_dye'][key] - result.sobol_s1['Ka_dye'][key]) <= 0.03


def test_a_stock_behind_every_input_of_a_displacement_assay_moves_ka_as_a_change_of_unit(monkeypatch):
    """IDA with one stock behind [Host]0, [Dye]0, the titrant and the Ka(dye) measured with it.

    Every concentration ``1 + e`` times the entered value and Ka(dye) ``1 / (1 + e)``
    times it is the same titration in another concentration unit, so every
    refit's Ka_guest is the baseline's over ``1 + e`` and the source's elasticity
    is exactly -1: in this case the error does not cancel.
    """
    monkeypatch.setattr(sens, '_SOBOL_BLOCKS', 2)
    monkeypatch.setattr(sens, '_SOBOL_SAMPLE_SIZES', (4,))
    ms = _noisy(*_make_ida_data(IDA_TRUE, n_points=_N_POINTS))
    stock = SharedSource('Stock', 4.0, ('Ka_dye', 'h0', 'd0', TITRANT))
    cfg = SensitivityConfig(SensitivityMode.SOBOL, 4, ErrorModel(shared=(stock,)), seed=3)

    result = run_sensitivity(ms, IDAAssay, _IDA_CONDITIONS, FitConfig(), cfg, max_workers=1)

    e = result.sample_offsets_pct[shared_key(stock.name)] / 100
    moved = np.log10(result.sample_ka['Ka_guest'] / result.baseline_ka['Ka_guest'])
    np.testing.assert_allclose(moved, -np.log10(1 + e), rtol=0, atol=1e-5)
    (row,) = result.budget['Ka_guest'].rows
    assert row.elasticity == pytest.approx(-1.0, abs=1e-3)


def test_an_error_host_and_dye_share_outranks_the_own_error_of_either():
    """IDA, 3 % of their own on host and dye, 4 % common to both.

    The common error moves Ka_guest by the sum of the host's and the dye's
    elasticities, each own error by one of them. To first order a source of
    elasticity ``s`` and relative sigma contributes ``(s sigma / ln 10)²``
    decades²: every row of the budget, estimated from the Sobol' design, has to
    agree with that figure from the run's finite differences, and the common
    source, the largest of the three, has to rank first beyond its interval.
    """
    ms = _noisy(*_make_ida_data(IDA_TRUE, n_points=_N_POINTS))
    shared = SharedSource('Host and dye stock', 4.0, ('h0', 'd0'))
    errors = ErrorModel(specs={'h0': InputSpec.sigma_pct(3.0), 'd0': InputSpec.sigma_pct(3.0)}, shared=(shared,))

    result = _run(ms, IDAAssay, _IDA_CONDITIONS, errors, seed=2)

    budget = result.budget['Ka_guest']
    rows = {row.source: row for row in budget.rows}
    common = rows[shared_key(shared.name)]
    elasticity = result.elasticity['Ka_guest']
    assert common.elasticity == pytest.approx(elasticity['h0'] + elasticity['d0'], rel=1e-12)
    for row, sigma in ((rows['h0'], 0.03), (rows['d0'], 0.03), (common, 0.04)):
        first_order = (row.elasticity * sigma / math.log(10)) ** 2
        assert row.variance == pytest.approx(first_order, rel=0.10, abs=0.01 * budget.variance), row.source
    for own in ('h0', 'd0'):
        assert common.variance_ci[0] > rows[own].variance_ci[1], own


def _with_addition_errors(x: np.ndarray, deltas: np.ndarray, sequential: bool) -> np.ndarray:
    """The titrant series after volume errors *deltas*, with no dilution: concentration follows volume.

    One cuvette: addition j delivers ``(x_j - x_{j-1}) (1 + delta_j)`` and point
    i holds every addition up to its own. Separate samples: point i is its one
    addition.
    """
    if not sequential:
        return x * (1 + deltas)
    steps = np.diff(np.concatenate([[0.0], x]))
    return np.array([np.sum(steps[: i + 1] * (1 + deltas[: i + 1])) for i in range(x.size)])


def _log_ka(x: np.ndarray, signals: np.ndarray) -> float:
    ms = MeasurementSet(concentrations=x, signals=signals.reshape(1, -1), replica_ids=('r0',))
    fit = fit_measurement_set(ms, DBAAssay, _DBA_CONDITIONS, FitConfig())
    return math.log10(fit.parameters['Ka_dye'].to('1/M').magnitude)


#: Step of the finite differences in an addition's relative error: far above the
#: 1e-7 decades a refit resolves log10 Ka to, far below the 2 % the errors have.
_DELTA_STEP = 1e-3


@pytest.mark.parametrize('sequential', [True, False], ids=['one-cuvette', 'separate-samples'])
def test_the_additions_are_one_item_with_the_first_order_variance(sequential):
    """DBA dye-to-host, 2 % on every addition beside 3 % on the titrant's scale.

    The additions are one item for all twenty errors, with no single
    elasticity and no sample offsets, and their variance is
    ``sum_j (dY/d delta_j)² sigma²``. Their effect is additive to first order,
    so the group's total index times the variance (the Jansen estimator, the
    sharper of the two at this sample size) has to give it within 15 %, and the
    first-order row of the budget within the reach of its own interval, which at
    N = 1024 is about a tenth of the row.
    """
    ms = _dba()
    x, signal = np.asarray(ms.concentrations), ms.signals[0]
    sigma = 0.02

    errors = ErrorModel(specs={TITRANT: InputSpec.sigma_pct(3.0)}, additions=AdditionError(100 * sigma, sequential))
    result = _run(ms, DBAAssay, _DBA_CONDITIONS, errors, seed=3)

    slopes = []
    for j in range(x.size):
        up, down = (
            _log_ka(_with_addition_errors(x, sign * _DELTA_STEP * np.eye(x.size)[j], sequential), signal)
            for sign in (1, -1)
        )
        slopes.append((up - down) / (2 * _DELTA_STEP))
    reference = float(np.sum(np.square(slopes))) * sigma**2

    assert result.sources == (TITRANT, ADDITIONS)
    assert set(result.sample_offsets_pct) == {TITRANT}
    row = result.budget['Ka_dye'].rows[1]
    assert row.source == ADDITIONS and row.elasticity is None
    total_order = result.sobol_st['Ka_dye'][ADDITIONS] * result.budget['Ka_dye'].variance
    assert total_order == pytest.approx(reference, rel=0.15)
    half_width = (row.variance_ci[1] - row.variance_ci[0]) / 2
    assert half_width < 0.25 * reference
    assert abs(row.variance - reference) <= 3 * half_width


@pytest.mark.parametrize('n_replicates', [1, 4])
def test_the_average_of_replicates_carries_the_addition_error_over_root_m(n_replicates):
    """400 simulated experiments of m titrations into one cuvette, 2 % on every addition, averaged and fitted.

    Every replicate's signal is the model at its own delivered concentrations,
    read against the nominal ones, without noise. The variance of log10 Ka over
    the experiments is the first-order one at ``sigma / sqrt(m)`` within 20 %
    (the variance of 400 values is itself known to 7 %).
    """
    x, _ = _make_dba_data(DBA_TRUE, n_points=_N_POINTS)
    sigma = 0.02

    def signal(deltas: np.ndarray) -> np.ndarray:
        true = {key: DBA_TRUE[key] for key in ('I0', 'Ka_dye', 'I_dye_free', 'I_dye_bound')}
        delivered = _with_addition_errors(x, deltas, sequential=True)
        return dba_signal(**true, x_titrant=delivered, y_fixed=DBA_TRUE['fixed_conc'], mode='DtoH')

    slopes = []
    for j in range(x.size):
        up, down = (_log_ka(x, signal(sign * _DELTA_STEP * np.eye(x.size)[j])) for sign in (1, -1))
        slopes.append((up - down) / (2 * _DELTA_STEP))
    reference = float(np.sum(np.square(slopes))) * sigma**2 / n_replicates

    rng = np.random.default_rng(7)
    simulated = [
        _log_ka(x, np.mean([signal(rng.normal(0.0, sigma, x.size)) for _ in range(n_replicates)], axis=0))
        for _ in range(400)
    ]

    assert np.var(simulated) == pytest.approx(reference, rel=0.20)
