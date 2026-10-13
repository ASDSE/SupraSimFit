"""Ka profiles and joint region — scientific behaviour tests.

The profile is the best R² achievable at each fixed Ka with every other
parameter free: exact for the signal parameters, a search over the other Ka in
a two-constant model. These tests pin what makes it trustworthy:

- its best fit, interval and cut-off are the engine's own numbers for the
  averaged signal, so the Identifiability tab shows the fit it belongs to;
- its F-test interval reproduces the IDA demo anchor and is cut at exactly one
  and n − p degrees of freedom (coverage over many noise draws is checked in
  ``tests/integration/test_profile_fits.py``);
- straight lines between the drawn points follow the exact curve, peak at the
  best fit and cross the cut-off at the interval's edges;
- per-replicate mode adds each replicate's own curve for a one-Ka model;
- custom bounds (a pinned coefficient, narrowed Ka bounds) are honoured;
- an interval the data cannot close is reported open on that side, one that
  spans a gap of rejected Ka is reported split, and a pinned Ka has none;
- a Ka the equilibrium model cannot be solved at counts as no fit, while a Ka
  bound far above any real affinity still has a curve at every point;
- the profiled residuals stay smooth in Ka, so the minimum the profile reports
  is the data's and not the solve's;
- for two binding constants the joint region contains the best fit and only Ka
  pairs that clear the joint cut-off, and pinning one Ka leaves one profile and
  no region (each curve against a brute-force minimum over the other Ka is in
  ``tests/integration/test_profile_fits.py``);
- where the inputs were stated with an uncertainty, the tab also gets the
  fit's own penalised profile, which lies above the fixed-input curve
  everywhere it is drawn; where only the design effect of the reported
  interval differs, that interval is this curve under its wider cut-off;
- the point weights and design effects are the fit's, handed in: with them
  the profile reproduces the fit's interval, the widened cut-offs and the
  joint region cut at its own design effect, and without them it is the
  unweighted plain F test whatever the replicates show;
- a stop request ends the profile at its next solve.
"""

import pathlib

import numpy as np
import pytest
from scipy.optimize import brentq, lsq_linear
from scipy.stats import f as f_dist

from core.assays.dba import DBAAssay
from core.assays.gda import GDAAssay
from core.assays.hg2 import HG2Assay
from core.assays.ida import IDAAssay
from core.assays.registry import ASSAY_REGISTRY, AssayType
from core.data_processing.measurement_set import MeasurementSet
from core.io import load_measurements
from core.optimizer.filters import calculate_fit_metrics
from core.pipeline import profile as profile_module
from core.pipeline import varpro
from core.pipeline.fit_pipeline import FitConfig, _resolve_bounds, fit_assay, fit_measurement_set
from core.pipeline.input_aware import input_aware
from core.pipeline.inputs import TITRANT, ErrorModel, InputSpec
from core.pipeline.profile import JointRegion, fit_profile
from core.pipeline.varpro import FitCancelled, Projection
from core.units import Q_
from tests.conftest import (
    DBA_RECOVERY_BOUNDS,
    DBA_TRUE,
    GDA_TRUE,
    HG2_TRUE,
    IDA_TRUE,
    _make_dba_data,
    _make_gda_data,
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
_HG2_CONDITIONS = {'h0': Q_(HG2_TRUE['h0'], 'M')}
# A Ka box of four decades around the HG2 truths keeps the two-Ka search grid
# at 17 x 17 nodes, so the two-dimensional cases stay quick.
_HG2_BOX = {'Ka_HG': (Q_(1e4, '1/M'), Q_(1e8, '1/M')), 'Ka_HG2': (Q_(1e4, '1/M'), Q_(1e8, '1/M'))}
_AVERAGE = FitConfig(per_replica=False)
_HG2_AVERAGE = FitConfig(per_replica=False, custom_bounds=_HG2_BOX)


def _demo_ms() -> MeasurementSet:
    return MeasurementSet.from_dataframe(load_measurements(_DEMO_PATH))


def _single(x, y) -> MeasurementSet:
    """One-replicate measurement set from Quantity or bare arrays."""
    x = getattr(x, 'magnitude', x)
    y = getattr(y, 'magnitude', y)
    return MeasurementSet(concentrations=x, signals=np.asarray(y).reshape(1, -1), replica_ids=('r0',))


def _hg2_ms(n_points: int = 12, frac: float = 0.02, seed: int = 0) -> MeasurementSet:
    x, y = _make_hg2_data(HG2_TRUE, n_points=n_points)
    return _single(x, _homoscedastic(y, frac, seed))


def _projection(ms: MeasurementSet, assay_cls, conditions, config: FitConfig) -> Projection:
    """The engine's projection of the averaged signal under *config*'s bounds."""
    assay = ms.to_assay(assay_cls, conditions=conditions, use_average=True)
    return Projection(assay, _resolve_bounds(assay, config.custom_bounds))


def _regular_grid_size(profile) -> int:
    """Points of the log-spaced grid a one-Ka profile's drawn curve starts from."""
    return varpro._ka_grid(profile.grid[0], profile.grid[-1], varpro._PROFILE_PER_DECADE).size


def _homoscedastic(y: np.ndarray, frac: float, seed: int) -> np.ndarray:
    """*y* plus Gaussian noise of constant sigma, *frac* of the largest signal."""
    return y + np.random.default_rng(seed).normal(0.0, frac * np.abs(y).max(), y.size)


def _no_number_above(ka_wall: float):
    """``IDAAssay.species`` with no number above *ka_wall*, as a model without speciation there.

    An equilibrium model reports a Ka it has no speciation for as species that
    are not a number. Which Ka those are is the model's business, so the tests
    that pin what the profile does with such a Ka put the wall where they can
    see it instead of hunting for one in the arithmetic.
    """
    real = IDAAssay.species

    def species(self, params):
        result = real(self, params)
        if params[self.parameter_keys.index('Ka_guest')] > ka_wall:
            return {name: np.full(values.shape, np.nan) for name, values in result.items()}
        return result

    return species


def _strict_local_minima(values: np.ndarray) -> int:
    """Interior points of *values* below both of their neighbours."""
    return int(np.sum((values[1:-1] < values[:-2]) & (values[1:-1] < values[2:])))


def _independent_ssr(assay, bounds: dict, ka: dict[str, float]) -> float:
    """Best residual at the binding constants *ka* from the forward model alone."""
    return _independent_fit(assay, bounds, ka)[0]


def _independent_fit(assay, bounds: dict, ka: dict[str, float]) -> tuple[float, int]:
    """Best residual at the binding constants *ka*, and how many signal parameters that fit leaves free.

    One column per signal parameter from a unit parameter vector through
    ``forward_model``, solved by bounded least squares on the raw columns:
    no species call, no scaling, no engine. The parameters left free are
    the rank of the columns whose coefficient the solve leaves strictly
    inside its bounds.
    """
    meta = ASSAY_REGISTRY[assay.assay_type]
    keys = assay.parameter_keys
    coef_keys = [k for k in keys if k not in ka]
    columns = []
    for key in coef_keys:
        params = np.array([ka.get(k, 0.0) for k in keys])
        params[keys.index(key)] = 1.0
        columns.append(assay.forward_model(params).magnitude)
    lb = np.array([bounds[k][0].to(meta.units[k]).magnitude for k in coef_keys])
    ub = np.array([bounds[k][1].to(meta.units[k]).magnitude for k in coef_keys])
    design, y = np.column_stack(columns), assay.y_data.magnitude
    pinned = lb == ub
    target = y - design[:, pinned] @ lb[pinned]
    free = design[:, ~pinned]
    sol = lsq_linear(free, target, bounds=(lb[~pinned], ub[~pinned]), method='bvls')
    inside = (sol.x > lb[~pinned]) & (sol.x < ub[~pinned])
    fitted = free[:, inside] / np.linalg.norm(free[:, inside], axis=0)
    return float(np.sum((free @ sol.x - target) ** 2)), int(np.linalg.matrix_rank(fitted)) if inside.any() else 0


# ---------------------------------------------------------------------------
# The profile is the fit it belongs to
# ---------------------------------------------------------------------------


@pytest.mark.parametrize('model', ['one_ka', 'two_ka'])
def test_the_profile_carries_the_fit_it_belongs_to_exactly(model):
    # The Identifiability tab shows the best fit and interval next to the fit
    # they belong to, so both have to be the same numbers, not a re-estimate
    # that could land a rounding step away.
    if model == 'one_ka':
        x, y = _make_ida_data(IDA_TRUE, n_points=12)
        ms, cls, cond, config = _single(x, _homoscedastic(y, 0.02, 0)), IDAAssay, _IDA_CONDITIONS, _AVERAGE
    else:
        ms, cls, cond, config = _hg2_ms(), HG2Assay, _HG2_CONDITIONS, _HG2_AVERAGE
    profiles = fit_profile(ms, cls, cond, config)
    result = fit_measurement_set(ms, cls, cond, config)
    projection = _projection(ms, cls, cond, config)
    fit = projection.fit()

    assert list(profiles.profiles) == list(projection.ka_keys) == list(result.intervals)
    for key, profile in profiles.profiles.items():
        assert profile.best_ka == result.parameters[key].magnitude
        assert profile.interval == result.intervals[key]
        # The cut-off and its parameter count are the engine's for the same projection.
        assert profile.n_params == projection.n_params(fit)
        assert profile.best_r2 == 1.0 - fit.objective / projection.ss_tot[0]
        assert profile.r2_threshold == 1.0 - projection.threshold(fit) / projection.ss_tot[0]
    if model == 'two_ka':
        assert profiles.region.best == (fit.ka['Ka_HG'], fit.ka['Ka_HG2'])
        # The evidence for a second binding step the joint region is read beside is the fit's own one-step test.
        assert profiles.profiles['Ka_HG2'].interval.one_step_p == projection.one_step_p(fit)
        assert profiles.profiles['Ka_HG'].interval.one_step_p is None
    else:
        assert profiles.region is None


def test_straight_lines_between_the_drawn_points_follow_the_exact_profile():
    # The plot joins the profile's points with straight lines. On the demo the
    # exact curve bends away from lines between 20-per-decade points by up to
    # 2e-4 R² next to the interval's lower edge, enough to misplace a fit.
    ms = _demo_ms()
    profile = fit_profile(ms, IDAAssay, _DEMO_CONDITIONS, _AVERAGE).profiles['Ka_guest']
    projection = _projection(ms, IDAAssay, _DEMO_CONDITIONS, _AVERAGE)
    ss_tot = projection.ss_tot[0]
    log_grid = np.log10(profile.grid)

    edges = (profile.interval.low, profile.interval.high)
    log_ka = np.linspace(np.log10(edges[0]) - 0.3, np.log10(edges[1]) + 0.3, 1500)
    exact = np.array([1.0 - projection.row_ssr({'Ka_guest': 10.0**t})[0] / ss_tot for t in log_ka])
    drawn = np.interp(log_ka, log_grid, profile.r2)
    allowance = profile_module._CURVE_R2_TOL + profile_module._CURVE_DEPTH_TOL * (profile.best_r2 - exact)
    assert np.all(np.abs(exact - drawn) <= allowance)

    # The line peaks at the best fit and meets the cut-off at the interval's edges.
    assert np.interp(np.log10(profile.best_ka), log_grid, profile.r2) == pytest.approx(profile.best_r2, abs=1e-12)
    for edge in edges:
        at = int(np.argmin(np.abs(log_grid - np.log10(edge))))
        assert profile.r2[at] == pytest.approx(profile.r2_cut[at], abs=1e-8)


# ---------------------------------------------------------------------------
# Confidence interval
# ---------------------------------------------------------------------------


def test_ida_demo_interval_matches_the_reference():
    # Reference from an independent F-test profile of the averaged demo signal:
    # IDA's offset/contrast degeneracy (free + bound dye = d0) leaves a rank-2
    # coefficient design, so p = 1 + 2 = 3 with 12 points.
    profile = fit_profile(_demo_ms(), IDAAssay, _DEMO_CONDITIONS, _AVERAGE).profiles['Ka_guest']
    interval = profile.interval

    assert profile.n_points == 12
    assert profile.n_params == 3
    assert profile.best_ka == pytest.approx(3.257e8, rel=0.03)
    assert profile.best_r2 == pytest.approx(0.99341, abs=1e-4)
    # Below 2.05e8 1/M the fit holds the offset on zero, which the best fit leaves
    # free, so the lower edge is where the rise reaches the cut-off of two parameters.
    assert interval.low == pytest.approx(1.576e8, rel=0.03)
    assert interval.high == pytest.approx(9.847e8, rel=0.03)
    assert (interval.open_low, interval.open_high) == (False, False)
    assert not interval.split
    assert interval.level == varpro.LEVEL

    # The cut is the F test at exactly 1 and n - p degrees of freedom. Counting
    # the replicates' points as n, or Ka's four nominal parameters as p, or
    # dropping the /(n - p) scaling all move it well beyond this tolerance.
    dof = profile.n_points - profile.n_params
    assert dof == 9 == interval.dof
    assert 1.0 - profile.r2_threshold == pytest.approx(
        (1.0 - profile.best_r2) * (1.0 + f_dist.ppf(interval.level, 1, dof) / dof), rel=1e-10
    )


def test_the_cut_off_steps_by_one_numerator_degree_of_freedom_where_the_fit_pins_a_signal_parameter():
    ms = _demo_ms()
    profile = fit_profile(ms, IDAAssay, _DEMO_CONDITIONS, _AVERAGE).profiles['Ka_guest']
    assay = ms.to_assay(IDAAssay, conditions=_DEMO_CONDITIONS, use_average=True)
    bounds = _resolve_bounds(assay, None)
    s_min, fitted = _independent_fit(assay, bounds, {'Ka_guest': profile.best_ka})
    ss_tot = float(np.sum((assay.y_data.magnitude - assay.y_data.magnitude.mean()) ** 2))
    # Upper 5 % points of F(m, 9) from a printed table.
    f_table = {1: 5.117, 2: 4.256}

    low, high = profile.interval.low, profile.interval.high
    counts = set()
    for at in np.flatnonzero((profile.grid > low / 3) & (profile.grid < high * 3))[::7]:
        _, fitted_here = _independent_fit(assay, bounds, {'Ka_guest': profile.grid[at]})
        m = 1 + max(0, fitted - fitted_here)
        counts.add(m)
        assert 1.0 - profile.r2_cut[at] == pytest.approx(s_min * (1 + m * f_table[m] / 9) / ss_tot, rel=2e-4)
    # The non-negative offset is on zero at the low Ka and free at the best fit and above it.
    assert counts == {1, 2}
    assert profile.r2_cut.max() == profile.r2_threshold


def test_a_profile_whose_fits_pin_nothing_the_best_fit_leaves_free_is_cut_at_one_level(dba_noisy):
    x, y, _ = dba_noisy
    ms = _single(x, y)
    profile = fit_profile(ms, DBAAssay, _DBA_CONDITIONS, _AVERAGE).profiles['Ka_dye']
    assay = ms.to_assay(DBAAssay, conditions=_DBA_CONDITIONS, use_average=True)
    bounds = _resolve_bounds(assay, None)
    # The best fit itself holds the offset on zero, so a fit elsewhere that does the same,
    # or frees it, gives up the tested Ka and nothing more.
    _, fitted = _independent_fit(assay, bounds, {'Ka_dye': profile.best_ka})
    assert fitted == 2
    assert all(_independent_fit(assay, bounds, {'Ka_dye': ka})[1] >= fitted for ka in profile.grid[::40])
    assert np.all(profile.r2_cut == profile.r2_threshold)


def test_interval_the_data_cannot_close_is_open_on_that_side():
    # Guest binding far stronger than the dye's makes the displacement
    # stoichiometric: raising Ka further no longer changes the curve, so the
    # data set a lower limit on Ka but no upper one.
    strong = dict(IDA_TRUE, Ka_guest=1e11)
    x, y = _make_ida_data(strong)
    interval = (
        fit_profile(_single(x, _homoscedastic(y, 0.01, 1)), IDAAssay, _IDA_CONDITIONS, _AVERAGE)
        .profiles['Ka_guest']
        .interval
    )

    # No custom bounds, so the interval runs into the registry defaults the fit used.
    ka_lo, ka_hi = (b.magnitude for b in ASSAY_REGISTRY[AssayType.IDA].default_bounds['Ka_guest'])
    assert (interval.open_low, interval.open_high) == (False, True)
    assert interval.high == pytest.approx(ka_hi)
    assert ka_lo < interval.low < strong['Ka_guest']


def test_an_edge_the_model_cannot_be_solved_past_is_open_not_a_limit_from_the_data(monkeypatch):
    # Same data as the open-interval case, fitted with a Ka upper bound above a
    # Ka the model has no speciation for. The profile stops at that wall, but
    # the data have not ruled out a larger Ka: the edge has to read open rather
    # than as an upper limit the measurements established.
    strong = dict(IDA_TRUE, Ka_guest=1e11)
    x, y = _make_ida_data(strong)
    ms = _single(x, _homoscedastic(y, 0.01, 1))
    monkeypatch.setattr(IDAAssay, 'species', _no_number_above(1e13))
    profile = fit_profile(
        ms,
        IDAAssay,
        _IDA_CONDITIONS,
        FitConfig(per_replica=False, custom_bounds={'Ka_guest': (Q_(1e5, '1/M'), Q_(1e30, '1/M'))}),
    ).profiles['Ka_guest']
    interval = profile.interval

    unsolved = np.isnan(profile.r2)
    assert unsolved.any()  # the bound does reach Ka the model cannot be solved at
    assert (interval.open_low, interval.open_high) == (False, True)
    assert interval.high < profile.grid[unsolved].min()
    # Why that side is open is carried with the interval: the edge is where the
    # model stops being solvable, well below the bound, and reading it as the
    # bound would name a number the fit was never given.
    assert (interval.unsolvable_low, interval.unsolvable_high) == (False, True)
    assert interval.high < 1e30


def test_a_dba_edge_the_data_cannot_close_stays_open_however_high_the_bound_reaches():
    # Dye bound so strongly that the titration is stoichiometric: raising Ka
    # further leaves the curve as it is, so the data set a lower limit and no
    # upper one, whatever upper bound the fit is given. The equilibrium solve
    # has to hold its accuracy that far up — speciation that is rounding error
    # fits the measurement scatter better than the true plateau does, which
    # closes the interval around a Ka the data say nothing about.
    strong = dict(DBA_TRUE, Ka_dye=1e9)
    x, y = _make_dba_data(strong)
    ms = _single(x, _homoscedastic(y, 0.01, 1))

    profiles = [
        fit_profile(
            ms,
            DBAAssay,
            _DBA_CONDITIONS,
            FitConfig(per_replica=False, custom_bounds={'Ka_dye': (Q_(1e3, '1/M'), Q_(hi, '1/M'))}),
        ).profiles['Ka_dye']
        for hi in (1e15, 1e20)
    ]
    modest, far = profiles

    for profile, hi in zip(profiles, (1e15, 1e20)):
        assert (profile.interval.open_low, profile.interval.open_high) == (False, True)
        assert profile.interval.high == pytest.approx(hi)
        assert not profile.interval.split
    # The lower edge is set by the data, so the higher bound does not move it,
    # and the plateau above the best fit stays one flat stretch.
    assert far.interval.low == pytest.approx(modest.interval.low, rel=1e-3)
    assert far.best_ka == pytest.approx(modest.best_ka, rel=1e-3)
    plateau = far.r2[far.grid > 1e12]
    assert np.ptp(plateau) < 1e-6


@pytest.mark.parametrize('model', ['one_ka', 'two_ka'])
def test_a_profile_asked_to_stop_ends_at_its_next_solve(model):
    """Closing the tab must not wait out a whole profile on the interface thread."""
    if model == 'one_ka':
        x, y = _make_ida_data(IDA_TRUE, n_points=12)
        ms, cls, cond, config = _single(x, _homoscedastic(y, 0.02, 0)), IDAAssay, _IDA_CONDITIONS, _AVERAGE
    else:
        ms, cls, cond, config = _hg2_ms(), HG2Assay, _HG2_CONDITIONS, _HG2_AVERAGE
    evaluated = []

    def stop_after_two() -> bool:
        evaluated.append(None)
        return len(evaluated) > 2

    with pytest.raises(FitCancelled):
        fit_profile(ms, cls, cond, config, should_cancel=stop_after_two)

    assert len(evaluated) == 3  # it stops at the check, not at the end of the grid


def test_a_gap_in_the_accepted_ka_values_is_reported_as_a_split_interval():
    # Two separated stretches of Ka clear the threshold and the Ka between them
    # do not. The reported interval is the envelope, so it has to say that it
    # spans Ka the data reject.
    def two_wells(ka: float) -> float:
        """Excess SSR accepting Ka within 0.3 decades of 1e1 and of 1e3, rejecting the stretch between."""
        t = np.log10(ka)
        return min((t - 1.0) ** 2, (t - 3.0) ** 2) - 0.09

    def one_well(ka: float) -> float:
        """Excess SSR accepting Ka within 0.3 decades of 1e2."""
        return (np.log10(ka) - 2.0) ** 2 - 0.09

    grid = np.logspace(0, 4, 81)
    split_ci, split_open, is_split, _ = varpro._interval(
        two_wells, grid, np.array([two_wells(ka) for ka in grid]), 10.0
    )
    assert is_split
    assert split_open == (False, False)
    assert split_ci == pytest.approx((10**0.7, 10**3.3), rel=1e-6)

    joined_ci, _, joined_split, _ = varpro._interval(one_well, grid, np.array([one_well(ka) for ka in grid]), 100.0)
    assert not joined_split
    assert joined_ci == pytest.approx((10**1.7, 10**2.3), rel=1e-6)


def test_a_ka_the_model_cannot_be_solved_at_is_no_fit_rather_than_an_error(monkeypatch):
    # A Ka whose species are not a number fits nothing, so it drops out of the
    # profile; raising the Ka upper bound into that range must leave the best
    # fit and the interval exactly where the solvable range already put them.
    x, y = _make_ida_data(IDA_TRUE, n_points=12)
    ms = _single(x, _homoscedastic(y, 0.02, 0))

    def profile_up_to(ka_max: float):
        bounds = {'Ka_guest': (Q_(1e5, '1/M'), Q_(ka_max, '1/M'))}
        config = FitConfig(per_replica=False, custom_bounds=bounds)
        return fit_profile(ms, IDAAssay, _IDA_CONDITIONS, config).profiles['Ka_guest']

    solvable = profile_up_to(1e15)
    assert not np.isnan(solvable.r2).any()

    monkeypatch.setattr(IDAAssay, 'species', _no_number_above(1e15))
    for ka_max in (1e20, 1e30):
        profile = profile_up_to(ka_max)
        unsolved = np.isnan(profile.r2)
        assert unsolved.any()  # the grid does reach Ka the model cannot solve
        assert profile.grid[unsolved].min() > 1e15
        assert profile.best_ka == pytest.approx(solvable.best_ka, rel=1e-6)
        assert (profile.interval.low, profile.interval.high) == pytest.approx(
            (solvable.interval.low, solvable.interval.high), rel=1e-6
        )
        assert (profile.interval.open_low, profile.interval.open_high) == (False, False)
        assert not profile.interval.split


def test_a_ka_bound_far_above_any_real_affinity_still_has_a_curve_at_every_point():
    # The profile is drawn wherever the user's Ka bounds reach. An equilibrium
    # solve whose accuracy fell away with Ka would break the curve there, or
    # close the interval around speciation that is rounding error; the data
    # alone decide, and here they leave the upper side open at the bound.
    strong = dict(IDA_TRUE, Ka_guest=1e11)
    x, y = _make_ida_data(strong)
    ms = _single(x, _homoscedastic(y, 0.01, 1))
    profile = fit_profile(
        ms,
        IDAAssay,
        _IDA_CONDITIONS,
        FitConfig(per_replica=False, custom_bounds={'Ka_guest': (Q_(1e5, '1/M'), Q_(1e30, '1/M'))}),
    ).profiles['Ka_guest']
    interval = profile.interval

    assert not np.isnan(profile.r2).any()
    assert (interval.open_low, interval.open_high) == (False, True)
    assert interval.high == pytest.approx(1e30)
    assert (interval.unsolvable_low, interval.unsolvable_high) == (False, False)
    assert not interval.split


def test_the_ka_grid_spans_bounds_whose_ratio_no_double_holds():
    """Parameter Bounds takes any number a double can hold, and the widest pair of them span
    316 decades while their ratio is no number at all; the grid is counted in decades."""
    grid = varpro._ka_grid(1e-8, 1.7e308, varpro._PROFILE_PER_DECADE)

    assert grid[0] == 1e-8
    assert grid[-1] == pytest.approx(1.7e308)
    assert np.all(np.diff(grid) > 0)
    assert grid.size > 316 * varpro._PROFILE_PER_DECADE


def test_the_profiled_residuals_fall_and_rise_once_across_the_tight_binding_decades(monkeypatch):
    # The best SSR at a fixed Ka is a smooth function of Ka: the data make it
    # fall and rise, and it has one minimum over a range where nothing else
    # happens. A speciation whose relative accuracy decays with Ka roughens it
    # into dozens of minima that the profile's refinement and its interval edges
    # would then find and report as structure in the data.
    true = dict(GDA_TRUE, Ka_guest=1e10)
    x, y = _make_gda_data(true, n_points=15)
    ms = _single(x, _homoscedastic(y, 0.01, 1))
    projection = _projection(ms, GDAAssay, _GDA_CONDITIONS, _AVERAGE)

    grid = np.geomspace(1e9, 1e12, 151)  # 50 points per decade
    ssr = np.array([float(projection.row_ssr({'Ka_guest': ka})[0]) for ka in grid])
    assert _strict_local_minima(ssr) <= 1

    # The same curve with free host solved to an absolute 1e-14 M instead, by
    # Brent's method on the balance summed as it stands: it is the solve, not
    # the data, that minima come from.
    def absolute_tolerance_host(Kg, Kd, h0, d0, g0):
        def balance(h):
            return h + Kd * h * d0 / (1 + Kd * h) + Kg * h * g0 / (1 + Kg * h) - h0

        return brentq(balance, 1e-20, h0, xtol=1e-14)

    monkeypatch.setattr('core.models.equilibrium._competitive_free_host', absolute_tolerance_host)
    rough = np.array([float(projection.row_ssr({'Ka_guest': ka})[0]) for ka in grid])
    assert _strict_local_minima(rough) > 10


def test_pinned_ka_is_not_fitted_and_has_no_interval():
    # Equal Ka bounds take Ka out of the fit: only the coefficients are
    # estimated, and there is no range to report for a value nothing moved.
    x, y = _make_ida_data(IDA_TRUE, n_points=12)
    ms = _single(x, _homoscedastic(y, 0.02, 0))
    ka = IDA_TRUE['Ka_guest']
    pinned = fit_profile(
        ms,
        IDAAssay,
        _IDA_CONDITIONS,
        FitConfig(per_replica=True, custom_bounds={'Ka_guest': (Q_(ka, '1/M'), Q_(ka, '1/M'))}),
    ).profiles['Ka_guest']
    free = fit_profile(
        ms,
        IDAAssay,
        _IDA_CONDITIONS,
        FitConfig(per_replica=False, custom_bounds={'Ka_guest': (Q_(1e5, '1/M'), Q_(1e8, '1/M'))}),
    ).profiles['Ka_guest']

    assert pinned.interval is None and free.interval is not None
    assert pinned.grid.size == 1
    assert pinned.best_ka == ka
    assert pinned.replica_r2 is None  # one point is no curve, for the replicates either
    # Ka is fixed, so the F test judges the coefficients alone: p is the design
    # rank without Ka's extra parameter.
    assert pinned.n_params == 2
    assert free.n_params == pinned.n_params + 1
    # Fixing Ka cannot beat the curve that is the best fit at every Ka.
    assert pinned.best_r2 == pytest.approx(np.interp(np.log10(ka), np.log10(free.grid), free.r2), abs=1e-6)
    assert pinned.best_r2 <= free.best_r2


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

    # Weights the fit might have run with: every curve is drawn on the weighted R² axis they define.
    weights = np.linspace(0.5, 2.0, 15)
    profile = fit_profile(ms, IDAAssay, _IDA_CONDITIONS, FitConfig(per_replica=True), point_weights=weights).profiles[
        'Ka_guest'
    ]
    averaged = fit_profile(ms, IDAAssay, _IDA_CONDITIONS, _AVERAGE, point_weights=weights).profiles['Ka_guest']

    # The replicates' curves add drawing points of their own; every Ka both grids share
    # (at least the regular grid) carries the same averaged R².
    shared, in_profile, in_averaged = np.intersect1d(profile.grid, averaged.grid, return_indices=True)
    assert shared.size >= _regular_grid_size(averaged)
    np.testing.assert_allclose(profile.r2[in_profile], averaged.r2[in_averaged], rtol=0, atol=1e-12)
    assert (profile.best_ka, profile.interval, profile.r2_threshold) == (
        averaged.best_ka,
        averaged.interval,
        averaged.r2_threshold,
    )
    assert (profile.n_points, profile.n_params) == (15, averaged.n_params)
    assert profile.per_replica and not averaged.per_replica
    assert averaged.replica_r2 is None

    # A replicate's curve is that replicate's signal projected under the fit's weights — here through a
    # projection of its own row alone.
    assert list(profile.replica_r2) == active
    for rid in active:
        row = _single(x, ms.get_replica_signal(rid))
        assay = row.to_assay(IDAAssay, conditions=_IDA_CONDITIONS, use_average=True)
        own = Projection(assay, _resolve_bounds(assay, None), point_weights=weights)
        drawn = profile.replica_r2[rid]
        expected = np.array([1.0 - own.row_ssr({'Ka_guest': ka})[0] / own.ss_tot[0] for ka in profile.grid.tolist()])
        np.testing.assert_allclose(drawn, expected, rtol=0, atol=1e-12)


def _proportional_replicates() -> MeasurementSet:
    """Four IDA replicates whose scatter grows with the signal, so the fit reads a noise law of positive share."""
    x, y = _make_ida_data(IDA_TRUE, n_points=15)
    rng = np.random.default_rng(3)
    signals = np.vstack([y * (1.0 + rng.normal(0.0, 0.03, y.size)) for _ in range(4)])
    return MeasurementSet(concentrations=x, signals=signals, replica_ids=('a', 'b', 'c', 'd'))


def test_given_the_weights_and_design_effect_a_fit_ran_with_the_profile_is_that_fit():
    """The curve, its cut-off and its interval are those of the weighted projection, cut at the widened F test.

    The R² axis is then ``1 - S_w / SS_tot,w``, with each point counted by its weight; the cut-off is
    ``S_min (1 + kappa F(1, n - p) / (n - p))`` on that scale, and the curve meets it at the interval's edges.
    """
    ms = _proportional_replicates()
    assay = ms.to_assay(IDAAssay, conditions=_IDA_CONDITIONS, use_average=True)
    weights = 1.0 / (0.2 + (assay.y_data.magnitude / assay.y_data.magnitude.max()) ** 2)
    kappa = 1.7
    profiles = fit_profile(
        ms, IDAAssay, _IDA_CONDITIONS, _AVERAGE, point_weights=weights, inflation={'Ka_guest': kappa}
    )
    profile = profiles.profiles['Ka_guest']

    weighted = Projection(assay, _resolve_bounds(assay, None), point_weights=weights)
    fit = weighted.fit()
    assert profiles.weighted
    assert profile.best_ka == fit.ka['Ka_guest']
    assert profile.interval == weighted.interval('Ka_guest', fit, inflation=kappa)
    assert profile.interval.inflation == kappa
    # The cut-off from the weighted residual and scipy's F quantile.
    ss_tot = float(
        np.sum(weights * (assay.y_data.magnitude - np.average(assay.y_data.magnitude, weights=weights)) ** 2)
    )
    dof = profile.n_points - profile.n_params
    s_min = float(np.sum(weights * (assay.y_data.magnitude - assay.forward_model(weighted.params(fit)).magnitude) ** 2))
    assert 1.0 - profile.r2_threshold == pytest.approx(
        s_min * (1 + kappa * f_dist.ppf(varpro.LEVEL, 1, dof) / dof) / ss_tot
    )
    log_grid = np.log10(profile.grid)
    for edge in (profile.interval.low, profile.interval.high):
        at = int(np.argmin(np.abs(log_grid - np.log10(edge))))
        assert profile.r2[at] == pytest.approx(profile.r2_cut[at], abs=1e-8)
    assert profile.best_r2 == pytest.approx(1.0 - s_min / ss_tot, abs=1e-12)


def test_the_profile_of_replicated_data_given_the_fits_own_weights_and_design_effects_is_that_fit():
    """With a law of positive share the fit weights by its fitted curve and widens its interval; so does the tab."""
    ms = _proportional_replicates()
    fit = fit_measurement_set(ms, IDAAssay, _IDA_CONDITIONS, _AVERAGE)
    assert fit.noise.estimated and fit.noise.share > 0.0 and fit.point_weights is not None
    conditional = fit.conditional.intervals
    profiles = fit_profile(
        ms,
        IDAAssay,
        _IDA_CONDITIONS,
        _AVERAGE,
        aware=fit.aware,
        point_weights=fit.point_weights,
        inflation={key: interval.inflation for key, interval in conditional.items()},
    )
    profile = profiles.profiles['Ka_guest']
    assert profiles.weighted
    assert profile.best_ka == fit.conditional.parameters['Ka_guest'].magnitude
    assert profile.interval == conditional['Ka_guest']
    assert (profile.interval if profile.aware is None else profile.aware.interval) == fit.intervals['Ka_guest']


def test_a_profile_handed_no_weights_is_unweighted_whatever_the_replicates_show():
    """The weights are the fit's to hand over; the profile reads no noise law of its own."""
    ms = _proportional_replicates()
    profiles = fit_profile(ms, IDAAssay, _IDA_CONDITIONS, _AVERAGE)
    profile = profiles.profiles['Ka_guest']
    assert not profiles.weighted
    plain = _projection(ms, IDAAssay, _IDA_CONDITIONS, _AVERAGE)
    fit = plain.fit()
    assert profile.interval == plain.interval('Ka_guest', fit) and profile.interval.inflation == 1.0
    assert profile.best_r2 == 1.0 - fit.objective / plain.ss_tot[0]


def test_a_single_titration_is_profiled_with_no_weights_at_all():
    """One signal cannot show how the noise varies, so the axis is the plain R² and the tab says so."""
    x, y = _make_ida_data(IDA_TRUE, n_points=15)
    ms = _single(x, _homoscedastic(y, 0.02, 7))

    profiles = fit_profile(ms, IDAAssay, _IDA_CONDITIONS, _AVERAGE)

    assert not profiles.weighted
    fit = fit_measurement_set(ms, IDAAssay, _IDA_CONDITIONS, _AVERAGE)
    assert profiles.profiles['Ka_guest'].best_r2 == pytest.approx(fit.r_squared, abs=1e-12)


def test_pinned_coefficients_make_the_profile_the_model_at_those_values(dba_clean):
    x, y, true = dba_clean
    # The free-dye coefficient is pinned in a non-canonical unit (50 au/µM = 5e7 au/M).
    pinned = {
        'Ka_dye': (Q_(1e3, '1/M'), Q_(1e8, '1/M')),
        'I0': (Q_(0, 'au'), Q_(0, 'au')),
        'I_dye_free': (Q_(50, 'au/µM'), Q_(50, 'au/µM')),
        'I_dye_bound': (Q_(true['I_dye_bound'], 'au/M'), Q_(true['I_dye_bound'], 'au/M')),
    }
    profile = fit_profile(
        _single(x, y), DBAAssay, _DBA_CONDITIONS, FitConfig(per_replica=False, custom_bounds=pinned)
    ).profiles['Ka_dye']

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
    free = fit_profile(ms, DBAAssay, _DBA_CONDITIONS, _AVERAGE).profiles['Ka_dye']
    capped = dict(DBA_RECOVERY_BOUNDS, I_dye_bound=(Q_(0, 'au/M'), Q_(0.5 * true['I_dye_bound'], 'au/M')))
    restricted = fit_profile(
        ms, DBAAssay, _DBA_CONDITIONS, FitConfig(per_replica=False, custom_bounds=capped)
    ).profiles['Ka_dye']

    # Same Ka bounds, so the same regular grid: a smaller feasible set can only lose fit.
    shared, in_restricted, in_free = np.intersect1d(restricted.grid, free.grid, return_indices=True)
    assert shared.size >= _regular_grid_size(free)
    assert np.all(restricted.r2[in_restricted] <= free.r2[in_free] + 1e-12)
    assert restricted.best_r2 < free.best_r2 - 1e-3


# ---------------------------------------------------------------------------
# Two binding constants
# ---------------------------------------------------------------------------


def test_the_joint_region_holds_the_best_fit_and_only_pairs_that_clear_the_joint_cut_off():
    ms = _hg2_ms(n_points=12, frac=0.02, seed=0)
    profiles = fit_profile(ms, HG2Assay, _HG2_CONDITIONS, _HG2_AVERAGE)
    region = profiles.region
    assay = ms.to_assay(HG2Assay, conditions=_HG2_CONDITIONS)
    bounds = _resolve_bounds(assay, _HG2_BOX)
    ss_tot = float(np.sum((assay.y_data.magnitude - assay.y_data.magnitude.mean()) ** 2))

    assert isinstance(region, JointRegion)
    assert region.ka_keys == ('Ka_HG', 'Ka_HG2')
    assert region.x.shape == region.y.shape == (profile_module._REGION_POINTS,)
    assert region.r2.shape == (region.x.size, region.y.size)
    assert np.all(np.diff(region.x) > 0) and np.all(np.diff(region.y) > 0)

    # The cut is the joint F test: two constrained binding constants, n - p
    # residual degrees of freedom, on the best fit's residual recomputed from
    # the forward model alone.
    best = dict(zip(region.ka_keys, region.best))
    s_min = _independent_ssr(assay, bounds, best)
    n_params = profiles.profiles['Ka_HG'].n_params
    dof = assay.n_points - n_params
    threshold = s_min * (1.0 + 2.0 * f_dist.ppf(region.level, 2, dof) / dof)
    assert region.level == varpro.LEVEL
    assert 1.0 - region.r2_threshold == pytest.approx(threshold / ss_tot, rel=1e-8)

    # The best fit lies inside the box and the cell nearest to it is in the region.
    assert region.x[0] <= best['Ka_HG'] <= region.x[-1]
    assert region.y[0] <= best['Ka_HG2'] <= region.y[-1]
    i = int(np.argmin(np.abs(np.log10(region.x) - np.log10(best['Ka_HG']))))
    j = int(np.argmin(np.abs(np.log10(region.y) - np.log10(best['Ka_HG2']))))
    inside = region.r2 >= region.r2_cut
    assert inside[i, j]
    assert inside.any() and not inside.all()  # the box is cut from the two 1-D intervals, wider than the region

    # Every cell is the exact projected residual, judged against the joint cut-off of its own
    # fit: one more numerator degree of freedom per signal parameter it pins and the best fit
    # leaves free.
    _, fitted = _independent_fit(assay, bounds, best)
    counts = set()
    for a in range(0, region.x.size, 9):
        for b in range(0, region.y.size, 9):
            ssr, fitted_here = _independent_fit(assay, bounds, {'Ka_HG': region.x[a], 'Ka_HG2': region.y[b]})
            assert region.r2[a, b] == pytest.approx(1.0 - ssr / ss_tot, abs=1e-9)
            m = 2 + max(0, fitted - fitted_here)
            counts.add(m)
            cut = s_min * (1.0 + m * f_dist.ppf(region.level, m, dof) / dof)
            assert 1.0 - region.r2_cut[a, b] == pytest.approx(cut / ss_tot, rel=1e-8)
            assert inside[a, b] == (ssr <= cut)
    assert {2, 3} <= counts

    # The box is cut the way an interval is: a side inside the Ka bounds lies where the profile
    # over the other Ka crosses the joint cut-off of its own profile point.
    projection = _projection(ms, HG2Assay, _HG2_CONDITIONS, _HG2_AVERAGE)
    joint_cut = projection.cut_off(projection.fit(), region.level, n_constrained=2)
    closed = [
        (key, side)
        for key, axis in zip(region.ka_keys, (region.x, region.y))
        for side in (axis[0], axis[-1])
        if side not in (1e4, 1e8)
    ]
    assert closed
    for key, side in closed:
        _, value, rank = projection.profile_point(key, side)
        assert value == pytest.approx(joint_cut(rank), rel=1e-6)


def test_the_joint_region_and_each_interval_are_cut_at_the_fits_own_design_effects():
    ms = _hg2_ms(n_points=12, frac=0.02, seed=0)
    kappa = {'Ka_HG': 1.5, 'Ka_HG2': 3.0}
    profiles = fit_profile(ms, HG2Assay, _HG2_CONDITIONS, _HG2_AVERAGE, inflation=kappa, joint_inflation=2.0)
    region = profiles.region
    assay = ms.to_assay(HG2Assay, conditions=_HG2_CONDITIONS)
    bounds = _resolve_bounds(assay, _HG2_BOX)
    ss_tot = float(np.sum((assay.y_data.magnitude - assay.y_data.magnitude.mean()) ** 2))
    s_min = _independent_ssr(assay, bounds, dict(zip(region.ka_keys, region.best)))
    dof = assay.n_points - profiles.profiles['Ka_HG'].n_params

    # The joint F test and each one-dimensional one, their quantiles scaled by the design effect handed in.
    assert region.inflation == 2.0
    joint = s_min * (1.0 + 2.0 * 2 * f_dist.ppf(region.level, 2, dof) / dof)
    assert 1.0 - region.r2_threshold == pytest.approx(joint / ss_tot, rel=1e-8)
    projection = _projection(ms, HG2Assay, _HG2_CONDITIONS, _HG2_AVERAGE)
    fit = projection.fit()
    for key, factor in kappa.items():
        profile = profiles.profiles[key]
        one = s_min * (1.0 + factor * f_dist.ppf(region.level, 1, dof) / dof)
        assert 1.0 - profile.r2_threshold == pytest.approx(one / ss_tot, rel=1e-8)
        assert profile.interval == projection.interval(key, fit, inflation=factor)
    # A side of the region's box inside the Ka bounds lies where the profile crosses the widened joint cut-off.
    joint_cut = projection.cut_off(fit, region.level, n_constrained=2, inflation=2.0)
    closed = [
        (key, side)
        for key, axis in zip(region.ka_keys, (region.x, region.y))
        for side in (axis[0], axis[-1])
        if side not in (1e4, 1e8)
    ]
    assert closed
    for key, side in closed:
        _, value, fitted = projection.profile_point(key, side)
        assert value == pytest.approx(joint_cut(fitted), rel=1e-6)


def test_stated_additions_widen_the_joint_region_and_its_bands_as_they_widen_the_reported_intervals():
    """The region at the entered inputs carries the additions; after an import, so does the reported reading."""
    from dataclasses import replace

    from core.pipeline.inflation import joint_inflation
    from core.pipeline.inputs import AdditionError

    ms = _hg2_ms(n_points=12, frac=0.005, seed=0)
    additions = AdditionError(3.0, sequential=True)
    config = replace(_HG2_AVERAGE, errors=ErrorModel(additions=additions))
    result = fit_measurement_set(ms, HG2Assay, _HG2_CONDITIONS, config)
    projection = _projection(ms, HG2Assay, _HG2_CONDITIONS, _HG2_AVERAGE)
    fit = projection.fit()
    assert result.joint_inflation == joint_inflation(projection, fit, additions=additions)
    assert result.joint_inflation > 1.0

    profiles = fit_profile(ms, HG2Assay, _HG2_CONDITIONS, config, **result.profile_arguments())
    region = profiles.region
    assert region.inflation == result.joint_inflation
    joint = projection.threshold(fit, region.level, n_constrained=2, inflation=result.joint_inflation)
    assert 1.0 - region.r2_threshold == pytest.approx(joint / float(projection.ss_tot[0]), rel=1e-12)
    for key in region.ka_keys:
        # The bands are the reported intervals: no input moved, so they are cut on this same curve.
        assert region.intervals[key] == result.intervals[key]
        assert profiles.profiles[key].interval == result.conditional.intervals[key]
    assert any(region.intervals[key].inflation > 1.0 for key in region.ka_keys)

    # A result read from a file holds no penalised profiles; its reported reading is cut again, at its own factors.
    imported = fit_profile(ms, HG2Assay, _HG2_CONDITIONS, config, **{**result.profile_arguments(), 'aware': None})
    for key in region.ka_keys:
        assert imported.profiles[key].aware.interval == result.intervals[key]
    assert imported.region.inflation == region.inflation


def test_pinning_one_of_two_ka_profiles_the_other_alone_and_leaves_no_region():
    x, y = _make_hg2_data(HG2_TRUE, n_points=12)
    signals = np.vstack([_homoscedastic(y, 0.02, seed) for seed in range(2)])
    ms = MeasurementSet(concentrations=x, signals=signals, replica_ids=('a', 'b'))
    pinned = (Q_(2e5, '1/M'), Q_(2e5, '1/M'))
    config = FitConfig(per_replica=True, custom_bounds={**_HG2_BOX, 'Ka_HG2': pinned})
    profiles = fit_profile(ms, HG2Assay, _HG2_CONDITIONS, config)

    assert profiles.region is None
    fixed, free = profiles.profiles['Ka_HG2'], profiles.profiles['Ka_HG']
    assert fixed.interval is None and fixed.grid.size == 1 and fixed.best_ka == 2e5
    # With one Ka left the profile is a one-Ka profile: 20 points per decade
    # and each replicate's own curve, cut at one constrained parameter.
    assert free.interval is not None
    assert free.interval.low < free.best_ka < free.interval.high
    assert free.grid.size >= _regular_grid_size(free)
    assert list(free.replica_r2) == ['a', 'b']
    assert free.n_params == fixed.n_params == 1 + 4  # one free Ka plus the four unpinned coefficients


# ---------------------------------------------------------------------------
# The second curve: the inputs free within their stated uncertainty
# ---------------------------------------------------------------------------

_UNCERTAIN_INPUTS = {'h0': InputSpec.sigma_pct(10), TITRANT: InputSpec.sigma_pct(3)}


@pytest.fixture(scope='module')
def uncertain_ida():
    """A 12-point IDA titration, its fit with two inputs free to move, and the profiles of that fit."""
    x, y = _make_ida_data(IDA_TRUE, n_points=12)
    ms = _single(x, _homoscedastic(y, 0.005, 4))
    config = FitConfig(per_replica=False, errors=ErrorModel(specs=_UNCERTAIN_INPUTS))
    assay = ms.to_assay(IDAAssay, conditions=_IDA_CONDITIONS, use_average=True)
    result = fit_assay(assay, config)
    return ms, config, result


def test_a_fit_that_held_every_input_as_entered_draws_one_curve():
    """Its penalised profile is that curve again, and a second copy of it would say nothing."""
    x, y = _make_ida_data(IDA_TRUE, n_points=12)
    profiles = fit_profile(_single(x, _homoscedastic(y, 0.005, 4)), IDAAssay, _IDA_CONDITIONS, _AVERAGE)

    assert profiles.profiles['Ka_guest'].aware is None


def test_a_reported_interval_at_a_larger_design_effect_is_this_curve_under_its_wider_cut_off():
    """No input free to move, and the reported interval widened further than this one (a stated error of each
    addition): the tab draws it as the second reading of the one curve, under its own cut-off."""
    x, y = _make_ida_data(IDA_TRUE, n_points=12)
    ms = _single(x, _homoscedastic(y, 0.005, 4))
    projection = _projection(ms, IDAAssay, _IDA_CONDITIONS, _AVERAGE)
    fit = projection.fit()
    headline = input_aware(projection, fit, (), inflation={'Ka_guest': 2.5})

    profile = fit_profile(ms, IDAAssay, _IDA_CONDITIONS, _AVERAGE, aware=headline).profiles['Ka_guest']

    reported = profile.aware
    assert reported is not None and reported.interval is headline.profiles['Ka_guest'].interval
    assert (profile.interval.inflation, reported.interval.inflation) == (1.0, 2.5)
    assert reported.interval.low < profile.interval.low and profile.interval.high < reported.interval.high
    assert np.array_equal(reported.grid, profile.grid) and np.array_equal(reported.r2, profile.r2)
    dof = profile.n_points - profile.n_params
    widened = fit.objective * (1.0 + 2.5 * f_dist.ppf(varpro.LEVEL, 1, dof) / dof)
    assert 1.0 - reported.r2_threshold == pytest.approx(widened / projection.ss_tot[0], rel=1e-12)
    # The curve passes through the reported interval's edges and meets its cut-off there.
    for edge in (reported.interval.low, reported.interval.high):
        (at,) = np.flatnonzero(reported.grid == edge)
        assert reported.r2[at] == pytest.approx(reported.r2_cut[at], abs=1e-8)


def test_the_tab_draws_the_penalised_profile_the_fit_itself_made(uncertain_ida):
    """Recomputing it could land on another local optimum and show a band the reported fit does not have."""
    ms, config, result = uncertain_ida

    profiles = fit_profile(ms, IDAAssay, _IDA_CONDITIONS, config, aware=result.aware)

    assert profiles.profiles['Ka_guest'].aware is result.aware.profiles['Ka_guest']
    assert profiles.profiles['Ka_guest'].aware.interval == result.intervals['Ka_guest']


def test_without_the_fits_own_profiles_the_same_ones_are_made_here(uncertain_ida):
    """A tab opened on a fit that did not carry them still shows that fit's interval."""
    ms, config, result = uncertain_ida

    profiles = fit_profile(ms, IDAAssay, _IDA_CONDITIONS, config)

    penalised = profiles.profiles['Ka_guest'].aware
    assert penalised is not None
    assert penalised.interval.low == pytest.approx(result.intervals['Ka_guest'].low, rel=1e-9)
    assert penalised.interval.high == pytest.approx(result.intervals['Ka_guest'].high, rel=1e-9)


def test_the_penalised_curve_lies_above_the_fixed_input_one(uncertain_ida):
    """Holding the inputs as entered is one of the choices the penalised profile has, so it can only do better.

    Both curves are R² against the same total sum of squares, which is what
    lets the tab draw them on one axis.
    """
    ms, config, result = uncertain_ida
    projection = _projection(ms, IDAAssay, _IDA_CONDITIONS, config)
    ss_tot = float(projection.ss_tot[0])
    penalised = fit_profile(ms, IDAAssay, _IDA_CONDITIONS, config, aware=result.aware).profiles['Ka_guest'].aware

    for ka, r2 in zip(penalised.grid.tolist(), penalised.r2.tolist()):
        fixed_input_r2 = 1.0 - float(projection.row_ssr({'Ka_guest': ka})[0]) / ss_tot
        assert r2 >= fixed_input_r2 - 1e-9, f'at Ka = {ka:g}'
    # Its cut-off is its own: the F test at the degrees of freedom the moving inputs leave.
    assert penalised.r2_threshold < 1.0 - float(np.exp(penalised.objective.min() / projection.n_points)) / ss_tot
