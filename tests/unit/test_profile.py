"""Exact Ka profile — scientific behaviour tests.

The profile is the best R² achievable at each fixed Ka, solved exactly because
the signal is linear in every other parameter. These tests pin what makes it
trustworthy:

- it bounds every multistart attempt from above at that attempt's own Ka;
- its maximum is the multistart best fit, on GDA, IDA, DBA and the IDA demo;
- its F-test interval reproduces the IDA demo anchor and covers the true Ka at
  about the stated rate on noisy synthetic data;
- per-replicate mode adds each replicate's own best residuals;
- custom bounds (a pinned coefficient, narrowed Ka bounds) are honoured;
- an interval the data cannot close is reported open on that side;
- assays without a single binding constant are rejected.
"""

import pathlib

import numpy as np
import pytest

from core.assays.dba import DBAAssay
from core.assays.gda import GDAAssay
from core.assays.hg2 import HG2Assay
from core.assays.ida import IDAAssay
from core.assays.registry import AssayType
from core.data_processing.measurement_set import MeasurementSet
from core.io import load_measurements
from core.optimizer.filters import calculate_fit_metrics
from core.pipeline import profile as profile_module
from core.pipeline.fit_pipeline import FitConfig, _resolve_bounds, fit_assay
from core.pipeline.profile import best_fit_by_profile, fit_profile, profile_supported
from core.units import Q_
from tests.conftest import (
    DBA_RECOVERY_BOUNDS,
    DBA_TRUE,
    GDA_IDA_RECOVERY_BOUNDS,
    GDA_TRUE,
    HG2_TRUE,
    IDA_TRUE,
    _make_hg2_data,
    _make_ida_data,
)

_DEMO_PATH = pathlib.Path(__file__).resolve().parents[2] / 'data' / 'IDA_system.txt'
_DEMO_CONDITIONS = {'Ka_dye': Q_(16.8e6, '1/M'), 'h0': Q_(4.3e-6, 'M'), 'd0': Q_(6e-6, 'M')}
_IDA_CONDITIONS = {
    'Ka_dye': Q_(IDA_TRUE['Ka_dye'], '1/M'),
    'h0': Q_(IDA_TRUE['h0'], 'M'),
    'd0': Q_(IDA_TRUE['d0'], 'M'),
}
_GDA_CONDITIONS = {
    'Ka_dye': Q_(GDA_TRUE['Ka_dye'], '1/M'),
    'h0': Q_(GDA_TRUE['h0'], 'M'),
    'g0': Q_(GDA_TRUE['g0'], 'M'),
}
_DBA_CONDITIONS = {'fixed_conc': Q_(DBA_TRUE['fixed_conc'], 'M'), 'mode': 'DtoH'}
_AVERAGE = FitConfig(per_replica=False)


def _demo_ms() -> MeasurementSet:
    return MeasurementSet.from_dataframe(load_measurements(_DEMO_PATH))


def _single(x, y) -> MeasurementSet:
    """One-replicate measurement set from Quantity or bare arrays."""
    x = getattr(x, 'magnitude', x)
    y = getattr(y, 'magnitude', y)
    return MeasurementSet(concentrations=x, signals=np.asarray(y).reshape(1, -1), replica_ids=('r0',))


def _regular_grid_size(profile) -> int:
    """Points of the log-spaced grid a profile's drawn curve starts from."""
    return profile_module._ka_grid(profile.grid[0], profile.grid[-1], profile_module._PROFILE_PER_DECADE).size


def _homoscedastic(y: np.ndarray, frac: float, seed: int) -> np.ndarray:
    """*y* plus Gaussian noise of constant sigma, *frac* of the largest signal."""
    return y + np.random.default_rng(seed).normal(0.0, frac * np.abs(y).max(), y.size)


# ---------------------------------------------------------------------------
# Which assays have a profile
# ---------------------------------------------------------------------------


def test_profile_supported_for_single_binding_constant_assays_only():
    supported = {t for t in AssayType if profile_supported(t)}
    assert supported == {AssayType.GDA, AssayType.IDA, AssayType.DBA_HtoD, AssayType.DBA_DtoH}


def test_fit_profile_rejects_an_assay_with_two_binding_constants():
    x, y = _make_hg2_data(HG2_TRUE)
    with pytest.raises(ValueError, match='binding constant'):
        fit_profile(_single(x, y), HG2Assay, {'h0': Q_(HG2_TRUE['h0'], 'M')}, _AVERAGE)


# ---------------------------------------------------------------------------
# The profile against the multistart optimizer
# ---------------------------------------------------------------------------


def _ida_noisy_assay(ida_noisy):
    x, y, _ = ida_noisy
    return IDAAssay(x_data=x, y_data=y, **_IDA_CONDITIONS)


@pytest.mark.parametrize('source', ['synthetic', 'demo'])
def test_every_multistart_attempt_lies_on_or_below_the_profile(source, ida_noisy):
    if source == 'demo':
        assay = _demo_ms().to_assay(IDAAssay, conditions=_DEMO_CONDITIONS)
    else:
        assay = _ida_noisy_assay(ida_noisy)
    bounds = _resolve_bounds(assay, None)
    fit = fit_assay(assay, FitConfig(n_trials=40, seed=0))

    excess = []
    for ka, r2 in zip(fit.attempt_samples['Ka_guest'], fit.attempt_quality['r_squared']):
        pinned = dict(bounds, Ka_guest=(Q_(ka, '1/M'), Q_(ka, '1/M')))
        _, profile_r2 = best_fit_by_profile(assay, pinned)
        excess.append(r2 - profile_r2)
    assert max(excess) <= 1e-9


def test_straight_lines_between_the_drawn_points_follow_the_exact_profile():
    # The plot joins the profile's points with straight lines. On the demo the
    # exact curve bends away from lines between 20-per-decade points by up to
    # 2e-4 R² next to the interval's lower edge, enough to draw attempts above it.
    ms = _demo_ms()
    profile = fit_profile(ms, IDAAssay, _DEMO_CONDITIONS, _AVERAGE)
    assay = ms.to_assay(IDAAssay, conditions=_DEMO_CONDITIONS, use_average=True)
    y = ms.average_signal(active_only=True)[np.newaxis, :]
    _, _, ssr_at = profile_module._profile_function(assay, _resolve_bounds(assay, None), y)
    ss_tot = profile_module._ss_tot(y)[0]
    log_grid = np.log10(profile.grid)

    log_ka = np.linspace(np.log10(profile.ci[0]) - 0.3, np.log10(profile.ci[1]) + 0.3, 1500)
    exact = np.array([1.0 - ssr_at(10.0**t)[0] / ss_tot for t in log_ka])
    drawn = np.interp(log_ka, log_grid, profile.r2)
    allowance = profile_module._CURVE_R2_TOL + profile_module._CURVE_DEPTH_TOL * (profile.best_r2 - exact)
    assert np.all(np.abs(exact - drawn) <= allowance)

    # The line peaks at the best fit and meets the cut-off at the interval's edges.
    assert np.interp(np.log10(profile.best_ka), log_grid, profile.r2) == pytest.approx(profile.best_r2, abs=1e-12)
    for edge in profile.ci:
        assert np.interp(np.log10(edge), log_grid, profile.r2) == pytest.approx(profile.r2_threshold, abs=1e-8)


@pytest.mark.parametrize('case', ['GDA', 'IDA', 'DBA', 'demo'])
def test_profile_best_fit_matches_the_multistart_best_fit(case, gda_noisy, ida_noisy, dba_noisy):
    if case == 'demo':
        assay, custom = _demo_ms().to_assay(IDAAssay, conditions=_DEMO_CONDITIONS), None
    elif case == 'GDA':
        x, y, _ = gda_noisy
        assay, custom = GDAAssay(x_data=x, y_data=y, **_GDA_CONDITIONS), GDA_IDA_RECOVERY_BOUNDS
    elif case == 'IDA':
        assay, custom = _ida_noisy_assay(ida_noisy), GDA_IDA_RECOVERY_BOUNDS
    else:
        x, y, _ = dba_noisy
        assay, custom = DBAAssay(x_data=x, y_data=y, **_DBA_CONDITIONS), DBA_RECOVERY_BOUNDS
    ka_key = assay.parameter_keys[0]

    # No quality floor, so the representative is the best attempt found.
    fit = fit_assay(assay, FitConfig(n_trials=30, seed=0, min_r_squared=0.0, custom_bounds=custom))
    best_ka, best_r2 = best_fit_by_profile(assay, _resolve_bounds(assay, custom))

    fit_ka = fit.parameters[ka_key].magnitude
    assert abs(best_ka - fit_ka) / fit_ka < 0.01
    assert abs(best_r2 - fit.r_squared) < 1e-6


# ---------------------------------------------------------------------------
# Confidence interval
# ---------------------------------------------------------------------------


def test_ida_demo_interval_matches_the_reference():
    # Reference from an independent F-test profile of the averaged demo signal:
    # IDA's offset/contrast degeneracy (free + bound dye = d0) leaves a rank-2
    # coefficient design, so p = 1 + 2 = 3 with 12 points.
    profile = fit_profile(_demo_ms(), IDAAssay, _DEMO_CONDITIONS, _AVERAGE)

    assert profile.n_points == 12
    assert profile.n_params == 3
    assert profile.best_ka == pytest.approx(3.257e8, rel=0.03)
    assert profile.best_r2 == pytest.approx(0.99341, abs=1e-4)
    assert profile.r2_threshold == pytest.approx(0.98967, abs=1e-4)
    assert profile.ci[0] == pytest.approx(1.708e8, rel=0.03)
    assert profile.ci[1] == pytest.approx(9.847e8, rel=0.03)
    assert profile.ci_open == (False, False)


def test_interval_covers_the_true_ka_at_about_the_stated_rate():
    # Homoscedastic Gaussian noise meets the F test's assumptions, so the 95 %
    # interval should cover the truth in close to 95 % of noise draws. 40 draws
    # leave sampling slack; 85 % still catches an interval that is too narrow.
    # Ka bounds a few decades either side of the truth keep the grid short.
    x, y = _make_ida_data(IDA_TRUE, n_points=12)
    config = FitConfig(per_replica=False, custom_bounds={'Ka_guest': (Q_(1e3, '1/M'), Q_(1e10, '1/M'))})
    n_seeds = 40
    covered = 0
    for seed in range(n_seeds):
        profile = fit_profile(_single(x, _homoscedastic(y, 0.02, seed)), IDAAssay, _IDA_CONDITIONS, config)
        covered += profile.ci[0] <= IDA_TRUE['Ka_guest'] <= profile.ci[1]
    print(f'95% interval coverage of the true Ka: {covered}/{n_seeds}')
    assert covered / n_seeds >= 0.85


def test_interval_the_data_cannot_close_is_open_on_that_side():
    # Guest binding far stronger than the dye's makes the displacement
    # stoichiometric: raising Ka further no longer changes the curve, so the
    # data set a lower limit on Ka but no upper one.
    strong = dict(IDA_TRUE, Ka_guest=1e11)
    x, y = _make_ida_data(strong)
    profile = fit_profile(_single(x, _homoscedastic(y, 0.01, 1)), IDAAssay, _IDA_CONDITIONS, _AVERAGE)

    ka_lo, ka_hi = (b.magnitude for b in GDA_IDA_RECOVERY_BOUNDS['Ka_guest'])
    assert profile.ci_open == (False, True)
    assert profile.ci[1] == pytest.approx(ka_hi)
    assert ka_lo < profile.ci[0] < strong['Ka_guest']


# ---------------------------------------------------------------------------
# Replicates and bounds
# ---------------------------------------------------------------------------


def test_per_replicate_profile_describes_the_average_and_adds_each_replicates_curve():
    """The curve and interval are the averaged signal's; each active replicate contributes its own curve."""
    x, y = _make_ida_data(IDA_TRUE, n_points=15)
    signals = np.vstack([_homoscedastic(y, 0.02, seed) for seed in range(4)])
    ms = MeasurementSet(concentrations=x, signals=signals, replica_ids=('a', 'b', 'c', 'd'))
    ms.set_active('c', False)
    active = ['a', 'b', 'd']

    profile = fit_profile(ms, IDAAssay, _IDA_CONDITIONS, FitConfig(per_replica=True))
    averaged = fit_profile(ms, IDAAssay, _IDA_CONDITIONS, _AVERAGE)

    # The replicates' curves add drawing points of their own; every Ka both grids share
    # (at least the regular grid) carries the same averaged R².
    shared, in_profile, in_averaged = np.intersect1d(profile.grid, averaged.grid, return_indices=True)
    assert shared.size >= _regular_grid_size(averaged)
    np.testing.assert_allclose(profile.r2[in_profile], averaged.r2[in_averaged], rtol=0, atol=1e-12)
    assert (profile.best_ka, profile.ci, profile.r2_threshold) == (averaged.best_ka, averaged.ci, averaged.r2_threshold)
    assert (profile.n_points, profile.n_params) == (15, averaged.n_params)
    assert profile.per_replica and not averaged.per_replica
    assert averaged.replica_r2 is None

    assert list(profile.replica_r2) == active
    for rid in active:
        own = fit_profile(_single(x, ms.get_replica_signal(rid)), IDAAssay, _IDA_CONDITIONS, _AVERAGE)
        shared, in_profile, in_own = np.intersect1d(profile.grid, own.grid, return_indices=True)
        assert shared.size >= _regular_grid_size(own)
        np.testing.assert_allclose(profile.replica_r2[rid][in_profile], own.r2[in_own], rtol=0, atol=1e-12)


def test_pinned_coefficients_make_the_profile_the_model_at_those_values(dba_clean):
    x, y, true = dba_clean
    # The free-dye coefficient is pinned in a non-canonical unit (50 au/µM = 5e7 au/M).
    pinned = {
        'Ka_dye': (Q_(1e3, '1/M'), Q_(1e8, '1/M')),
        'I0': (Q_(0, 'au'), Q_(0, 'au')),
        'I_dye_free': (Q_(50, 'au/µM'), Q_(50, 'au/µM')),
        'I_dye_bound': (Q_(true['I_dye_bound'], 'au/M'), Q_(true['I_dye_bound'], 'au/M')),
    }
    profile = fit_profile(_single(x, y), DBAAssay, _DBA_CONDITIONS, FitConfig(per_replica=False, custom_bounds=pinned))

    assert profile.grid[0] == pytest.approx(1e3)
    assert profile.grid[-1] == pytest.approx(1e8)
    assay = DBAAssay(x_data=x, y_data=y, **_DBA_CONDITIONS)
    for ka, r2 in zip(profile.grid[::25], profile.r2[::25]):
        params = np.array([ka, 0.0, true['I_dye_free'], true['I_dye_bound']])
        _, direct_r2 = calculate_fit_metrics(y.magnitude, assay.forward_model(params).magnitude)
        assert r2 == pytest.approx(direct_r2, abs=1e-12)
    assert profile.n_params == 1  # nothing left to fit but Ka
    assert profile.best_ka == pytest.approx(true['Ka_dye'], rel=1e-3)


def test_narrowing_a_coefficient_bound_never_raises_the_profile(dba_noisy):
    x, y, true = dba_noisy
    ms = _single(x, y)
    free = fit_profile(ms, DBAAssay, _DBA_CONDITIONS, _AVERAGE)
    capped = dict(DBA_RECOVERY_BOUNDS, I_dye_bound=(Q_(0, 'au/M'), Q_(0.5 * true['I_dye_bound'], 'au/M')))
    restricted = fit_profile(ms, DBAAssay, _DBA_CONDITIONS, FitConfig(per_replica=False, custom_bounds=capped))

    # Same Ka bounds, so the same regular grid: a smaller feasible set can only lose fit.
    shared, in_restricted, in_free = np.intersect1d(restricted.grid, free.grid, return_indices=True)
    assert shared.size >= _regular_grid_size(free)
    assert np.all(restricted.r2[in_restricted] <= free.r2[in_free] + 1e-12)
    assert restricted.best_r2 < free.best_r2 - 1e-3


def test_profile_coefficients_never_leave_their_bounds():
    # Across a Ka sweep of the averaged demo signal the free-dye coefficient's
    # unbounded optimum is negative, so the bounded solve lands it on its lower
    # bound of 0; that value must be the bound itself, not a rounding step below.
    assay = _demo_ms().to_assay(IDAAssay, conditions=_DEMO_CONDITIONS, use_average=True)
    ka_key, coef_keys = profile_module._split_keys(assay)
    lb, ub = profile_module._coefficient_bounds(
        profile_module._float_bounds(assay, _resolve_bounds(assay, None)), coef_keys
    )
    y = assay.y_data.magnitude[None, :]

    coefficients = np.vstack(
        [
            profile_module._solve(profile_module._design(assay, ka_key, coef_keys, ka), lb, ub, y)[1]
            for ka in np.logspace(4, 12, 400)
        ]
    )

    assert np.any(coefficients == lb)  # the sweep does reach a bound
    assert np.all((coefficients >= lb) & (coefficients <= ub))
