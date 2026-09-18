"""Variable projection engine — scientific behaviour tests.

Every binding model is ``y = A(K) c + e``: the design at fixed binding
constants K holds a column of ones and the species the signal coefficients
multiply, and the best coefficients at that K are an exact bounded linear
least-squares solve. These tests pin what makes the engine trustworthy:

- the design reconstructs the forward model for every assay, and the projected
  residual equals an independent bounded least-squares solve;
- noise-free data give the true Ka back to the search's own resolution for
  every assay, one or two binding constants alike, and a repeat is bit-identical;
- the two-Ka search is at least as good as a dense brute-force grid;
- the interval edges lie exactly on the F-test cut-off, a saturated design is
  reported open on the side the data cannot close, and a pinned Ka has none;
- structurally degenerate coefficients are named per assay;
- the replicate test excludes a replicate that needs another Ka, keeps
  replicates that merely scatter more, and does not judge two replicates;
- invalid inputs are refused with a plain-language message and a stop request
  is honoured.
"""

import numpy as np
import pytest
from scipy.optimize import lsq_linear
from scipy.stats import f as f_dist

from core.assays import ASSAY_CLASSES
from core.assays.dye_alone import DyeAloneAssay
from core.assays.ida import IDAAssay
from core.assays.registry import ASSAY_REGISTRY, AssayType, ParamKind
from core.models.equilibrium import gda_species, hg2_signal, ida_signal
from core.pipeline import varpro
from core.pipeline.varpro import (
    LEVEL,
    FitCancelled,
    FitRefused,
    KaInterval,
    Projection,
    projectable,
    replicate_outliers,
)
from core.units import Q_
from tests.conftest import (
    GDA_IDA_RECOVERY_BOUNDS,
    GDA_TRUE,
    IDA_TRUE,
    _make_gda_data,
    _make_ida_data,
)

# Conditions of one representative titration per binding assay: micromolar
# totals, a dye affinity in the middle of the default box.
_CONDITIONS = {
    AssayType.GDA: dict(Ka_dye=Q_(5e5, '1/M'), h0=Q_(1e-5, 'M'), g0=Q_(2e-5, 'M')),
    AssayType.IDA: dict(Ka_dye=Q_(5e5, '1/M'), h0=Q_(1e-5, 'M'), d0=Q_(5e-6, 'M')),
    AssayType.DBA_HtoD: dict(fixed_conc=Q_(5e-6, 'M'), mode='HtoD'),
    AssayType.DBA_DtoH: dict(fixed_conc=Q_(5e-6, 'M'), mode='DtoH'),
    AssayType.DBA_HG2: dict(h0=Q_(1e-5, 'M')),
    AssayType.DBA_H2G: dict(h0=Q_(1e-5, 'M')),
}
_BINDING_ASSAYS = tuple(_CONDITIONS)
_IDA_CONDITIONS = dict(Ka_dye=Q_(IDA_TRUE['Ka_dye'], '1/M'), h0=Q_(IDA_TRUE['h0'], 'M'), d0=Q_(IDA_TRUE['d0'], 'M'))
_GDA_CONDITIONS = dict(Ka_dye=Q_(GDA_TRUE['Ka_dye'], '1/M'), h0=Q_(GDA_TRUE['h0'], 'M'), g0=Q_(GDA_TRUE['g0'], 'M'))


def _assay(assay_type: AssayType, x: np.ndarray, y: np.ndarray, **conditions):
    cond = conditions or _CONDITIONS[assay_type]
    return ASSAY_CLASSES[assay_type](x_data=Q_(x, 'M'), y_data=Q_(y, 'au'), **cond)


def _ka_keys(assay_type: AssayType) -> list[str]:
    meta = ASSAY_REGISTRY[assay_type]
    return [k for k in meta.parameter_keys if meta.param_kinds[k] is ParamKind.BINDING_CONSTANT]


def _homoscedastic(y: np.ndarray, frac: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return y + rng.normal(0.0, frac * np.ptp(y), y.size)


def _ida(n: int = 15, frac: float = 0.02, seed: int = 0, **bounds):
    """IDA projection on conftest truths with homoscedastic noise and the recovery bounds."""
    x, y = _make_ida_data(IDA_TRUE, n_points=n)
    assay = _assay(AssayType.IDA, x, _homoscedastic(y, frac, seed), **_IDA_CONDITIONS)
    return Projection(assay, {**GDA_IDA_RECOVERY_BOUNDS, **bounds})


def _hg2_truth_signal(x: np.ndarray, h0: float, ka_hg: float, ka_hg2: float) -> np.ndarray:
    return hg2_signal(I0=100.0, Ka_HG=ka_hg, Ka_HG2=ka_hg2, I_G=1e6, I_H=0.0, I_HG=1e7, I_HG2=5e6, h0=h0, g0_values=x)


# ---------------------------------------------------------------------------
# Design and inner solve
# ---------------------------------------------------------------------------


def test_projectable_means_one_or_two_binding_constants_with_linear_signal_parameters():
    for assay_type in _BINDING_ASSAYS:
        assert projectable(assay_type)
    assert not projectable(AssayType.DYE_ALONE)


@pytest.mark.parametrize('assay_type', _BINDING_ASSAYS, ids=lambda t: t.name)
def test_design_times_coefficients_is_the_forward_model(assay_type):
    """The columns are the species the signal is linear in; ``A(K) c`` is the model signal."""
    rng = np.random.default_rng(1)
    x = np.linspace(1e-7, 5e-5, 12)
    # The signal is not what is checked here, only the design the projection builds
    # from it — but a projection needs a signal that changes to be built at all.
    assay = _assay(assay_type, x, np.linspace(1.0, 2.0, 12))
    meta = ASSAY_REGISTRY[assay_type]
    bounds = {k: (lo, hi) for k, (lo, hi) in meta.default_bounds.items()}
    # The free-host coefficient of the 1:2 models is pinned to zero by default; free it so
    # every column is exercised.
    if 'I_H' in bounds:
        bounds['I_H'] = (Q_(0, 'au/M'), Q_(1e12, 'au/M'))
    projection = Projection(assay, bounds)
    for _ in range(5):
        ka = {k: 10 ** rng.uniform(3, 8) for k in projection.ka_keys}
        coef = {k: rng.uniform(1e5, 1e7) for k in projection.coef_keys}
        coef[next(k for k in projection.coef_keys if meta.param_kinds[k] is ParamKind.SIGNAL_OFFSET)] = 37.0
        params = np.array([{**ka, **coef}[k] for k in assay.parameter_keys])
        expected = assay.forward_model(params).magnitude
        design = projection._design(ka)
        actual = design @ np.array([coef[k] for k in projection.coef_keys])
        assert actual == pytest.approx(expected, rel=1e-12)


def test_row_ssr_equals_an_independent_bounded_least_squares_solve():
    """At a fixed Ka the best residual is that of BVLS on the raw species columns."""
    x, y = _make_gda_data(GDA_TRUE, n_points=15)
    y = _homoscedastic(y, 0.03, 4)
    assay = _assay(AssayType.GDA, x, y, **_GDA_CONDITIONS)
    bounds = GDA_IDA_RECOVERY_BOUNDS
    projection = Projection(assay, bounds)
    ka = 8e5
    species = gda_species(ka, GDA_TRUE['Ka_dye'], GDA_TRUE['h0'], x, GDA_TRUE['g0'])
    columns = np.column_stack([np.ones(x.size), species['D'], species['HD']])
    lb = np.array([bounds[k][0].magnitude for k in ('I0', 'I_dye_free', 'I_dye_bound')])
    ub = np.array([bounds[k][1].magnitude for k in ('I0', 'I_dye_free', 'I_dye_bound')])
    independent = lsq_linear(columns, y, bounds=(lb, ub), method='bvls', tol=1e-14)
    expected = float(np.sum((columns @ independent.x - y) ** 2))
    assert projection.row_ssr({'Ka_guest': ka})[0] == pytest.approx(expected, rel=1e-8)


def test_a_zero_weight_row_is_solved_but_does_not_steer_the_shared_ka():
    x, y = _make_ida_data(IDA_TRUE, n_points=12)
    rows = np.vstack([_homoscedastic(y, 0.02, 1), _homoscedastic(1.3 * y, 0.02, 2)])
    assay = _assay(AssayType.IDA, x, rows.mean(axis=0), **_IDA_CONDITIONS)
    joint = Projection(assay, GDA_IDA_RECOVERY_BOUNDS, signals=rows)
    alone = Projection(assay, GDA_IDA_RECOVERY_BOUNDS, signals=rows[1:])
    fit = joint.fit(weights=np.array([0.0, 1.0]))
    assert fit.ka == alone.fit().ka
    assert fit.objective == fit.row_ssr[1]
    assert fit.coefficients.shape == (2, 3) and np.isfinite(fit.coefficients).all()
    assert fit.row_ssr[0] == pytest.approx(joint.row_ssr(fit.ka)[0])


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


def _noise_free_case(assay_type: AssayType, free_host: float = 0.0):
    """A titration each binding constant is well determined by, with its truth and bounds.

    *free_host* is the signal coefficient of the free host of a 1:2 model; a
    non-zero value frees it in the bounds too.
    """
    meta = ASSAY_REGISTRY[assay_type]
    bounds = dict(meta.default_bounds)
    if assay_type in (AssayType.DBA_HG2, AssayType.DBA_H2G):
        x = np.linspace(0.0, 5e-5, 20)
        truth = {'Ka_HG': 1e6, 'Ka_HG2': 1e5, 'Ka_H2G': 1e5}
        second = _ka_keys(assay_type)[1]
        params = {
            'Ka_HG': 1e6,
            second: 1e5,
            'I0': 100.0,
            'I_G': 1e6,
            'I_H': free_host,
            'I_HG': 1e7,
            meta.parameter_keys[-1]: 5e6,
        }
        if free_host:
            bounds['I_H'] = (Q_(0, 'au/M'), Q_(1e12, 'au/M'))
    else:
        x = np.linspace(1e-7, 5e-5, 20)
        truth = {'Ka_guest': 3e6, 'Ka_dye': 8e5}
        params = {
            _ka_keys(assay_type)[0]: truth[_ka_keys(assay_type)[0]],
            'I0': 100.0,
            'I_dye_free': 5e7,
            'I_dye_bound': 3e8,
        }
    probe = _assay(assay_type, x, np.ones(x.size))
    y = probe.forward_model(np.array([params[k] for k in meta.parameter_keys])).magnitude
    return _assay(assay_type, x, y), bounds, {k: truth[k] for k in _ka_keys(assay_type)}


@pytest.mark.parametrize('assay_type', _BINDING_ASSAYS, ids=lambda t: t.name)
def test_noise_free_data_return_the_true_ka_to_the_search_resolution(assay_type):
    assay, bounds, truth = _noise_free_case(assay_type)
    fit = Projection(assay, bounds).fit()
    for key, value in truth.items():
        assert abs(np.log10(fit.ka[key]) - np.log10(value)) < 1e-6, key
    assert fit.n_free_ka == len(truth)


def test_a_repeated_fit_and_interval_are_bit_identical():
    x, y = _make_ida_data(IDA_TRUE, n_points=15)
    y = _homoscedastic(y, 0.02, 3)

    def run():
        projection = Projection(_assay(AssayType.IDA, x, y, **_IDA_CONDITIONS), GDA_IDA_RECOVERY_BOUNDS)
        fit = projection.fit()
        return fit, projection.interval('Ka_guest', fit)

    first, second = run(), run()
    assert first[0].ka == second[0].ka
    assert first[0].objective == second[0].objective
    assert np.array_equal(first[0].coefficients, second[0].coefficients)
    assert first[1] == second[1]


def test_two_ka_search_is_at_least_as_good_as_a_dense_brute_force_grid():
    """The 4/decade grid plus refinement beats every node of a 16/decade grid."""
    h0 = 1e-5
    x = np.linspace(0.0, 2e-4, 12)
    y = _homoscedastic(_hg2_truth_signal(x, h0, 1e6, 1e5), 0.02, 7)
    assay = _assay(AssayType.DBA_HG2, x, y, h0=Q_(h0, 'M'))
    narrow = (Q_(1e5, '1/M'), Q_(1e7, '1/M'))
    projection = Projection(
        assay, {**ASSAY_REGISTRY[AssayType.DBA_HG2].default_bounds, 'Ka_HG': narrow, 'Ka_HG2': narrow}
    )
    fit = projection.fit()
    grid = np.geomspace(1e5, 1e7, 33)
    brute = min(projection.row_ssr({'Ka_HG': k1, 'Ka_HG2': k2})[0] for k1 in grid for k2 in grid)
    assert fit.objective <= brute * (1 + 1e-9)
    assert fit.n_free_ka == 2


def test_no_solvable_ka_is_refused_in_plain_language(monkeypatch):
    x, y = _make_ida_data(IDA_TRUE, n_points=12)
    assay = _assay(AssayType.IDA, x, y, **_IDA_CONDITIONS)
    monkeypatch.setattr(
        IDAAssay, 'species', lambda self, params: {k: np.full(12, np.nan) for k in ('H', 'D', 'G', 'HD', 'HG')}
    )
    with pytest.raises(ValueError, match='no solution at any association constant between 1e-08 and 1e\\+12'):
        Projection(assay, GDA_IDA_RECOVERY_BOUNDS).fit()


def test_a_fit_asked_to_stop_stops_before_its_next_solve():
    x, y = _make_ida_data(IDA_TRUE, n_points=12)
    assay = _assay(AssayType.IDA, x, y, **_IDA_CONDITIONS)
    asked = 0

    def stop_at_the_fourth_ask() -> bool:
        nonlocal asked
        asked += 1
        return asked == 4

    projection = Projection(assay, GDA_IDA_RECOVERY_BOUNDS, should_cancel=stop_at_the_fourth_ask)
    with pytest.raises(FitCancelled):
        projection.fit()
    assert asked == 4


@pytest.mark.parametrize(
    'assay_type, bad',
    [
        (AssayType.IDA, (Q_(0, '1/M'), Q_(1e12, '1/M'))),
        (AssayType.IDA, (Q_(1e8, '1/M'), Q_(1e6, '1/M'))),
    ],
    ids=['non-positive', 'inverted'],
)
def test_invalid_ka_bounds_are_refused(assay_type, bad):
    x, y = _make_ida_data(IDA_TRUE, n_points=12)
    assay = _assay(assay_type, x, y, **_IDA_CONDITIONS)
    with pytest.raises(ValueError, match='bounds of Ka_guest must be positive'):
        Projection(assay, {**GDA_IDA_RECOVERY_BOUNDS, 'Ka_guest': bad})


def test_an_assay_without_a_binding_constant_is_refused():
    x = np.linspace(0, 1e-5, 8)
    assay = DyeAloneAssay(x_data=Q_(x, 'M'), y_data=Q_(x * 1e6, 'au'))
    with pytest.raises(ValueError, match='DYE_ALONE'):
        Projection(assay, assay.get_default_bounds())


def test_a_signal_that_never_changes_is_refused_rather_than_fitted():
    # Every binding constant reproduces a constant signal equally well, and the
    # total sum of squares such a signal is judged against is zero, so the F
    # test would be cut from rounding noise. One refusal in the engine makes
    # every entry point answer these data the same way, instead of the fit of
    # an average reporting a closed interval where the per-replicate path
    # refuses.
    x, _ = _make_ida_data(IDA_TRUE, n_points=12)
    flat = np.full(x.size, 1234.0)
    with pytest.raises(FitRefused, match='same at every titration point'):
        Projection(_assay(AssayType.IDA, x, flat, **_IDA_CONDITIONS), GDA_IDA_RECOVERY_BOUNDS)

    # A row among several is named by its place in the rows given.
    rows = np.vstack([_make_ida_data(IDA_TRUE, n_points=12)[1], flat])
    with pytest.raises(FitRefused, match='row\\(s\\) 2'):
        Projection(
            _assay(AssayType.IDA, x, rows.mean(axis=0), **_IDA_CONDITIONS),
            GDA_IDA_RECOVERY_BOUNDS,
            signals=rows,
        )


# ---------------------------------------------------------------------------
# Threshold and interval
# ---------------------------------------------------------------------------


def test_interval_edges_lie_on_the_f_test_cut_off():
    projection = _ida(n=15, frac=0.02, seed=5)
    fit = projection.fit()
    # Free plus bound dye sum to the fixed dye total, collinear with the offset:
    # the design has rank 2, so p = 1 (Ka) + 2.
    assert projection.n_params(fit) == 3
    dof = 15 - 3
    threshold = fit.objective * (1 + f_dist.ppf(LEVEL, 1, dof) / dof)
    assert projection.threshold(fit) == pytest.approx(threshold, rel=1e-12)

    interval = projection.interval('Ka_guest', fit)
    profile = projection.profile('Ka_guest')
    assert interval.open_low is False and interval.open_high is False
    assert interval.dof == dof and interval.level == LEVEL
    assert interval.low < fit.ka['Ka_guest'] < interval.high
    for edge in (interval.low, interval.high):
        assert profile(edge) == pytest.approx(threshold, rel=1e-6)
    # A twentieth of a decade inside an edge the profile is below the cut-off, outside above it.
    assert profile(interval.low * 10**0.05) < threshold < profile(interval.low / 10**0.05)
    assert profile(interval.high / 10**0.05) < threshold < profile(interval.high * 10**0.05)


def test_two_ka_interval_edges_lie_on_the_cut_off_of_the_profile_over_the_other_ka():
    h0 = 1e-5
    x = np.linspace(0.0, 2e-4, 15)
    y = _homoscedastic(_hg2_truth_signal(x, h0, 1e6, 1e5), 0.01, 11)
    assay = _assay(AssayType.DBA_HG2, x, y, h0=Q_(h0, 'M'))
    box = (Q_(1e4, '1/M'), Q_(1e8, '1/M'))
    projection = Projection(assay, {**ASSAY_REGISTRY[AssayType.DBA_HG2].default_bounds, 'Ka_HG': box, 'Ka_HG2': box})
    fit = projection.fit()
    threshold = projection.threshold(fit)
    for key, other in (('Ka_HG', 'Ka_HG2'), ('Ka_HG2', 'Ka_HG')):
        interval = projection.interval(key, fit)
        profile = projection.profile(key)
        assert interval.low < fit.ka[key] < interval.high
        for edge, is_open in ((interval.low, interval.open_low), (interval.high, interval.open_high)):
            if not is_open:
                assert profile(edge) == pytest.approx(threshold, rel=1e-6)
                # The profile at the edge is the minimum over the other Ka: no node of a
                # dense scan of the other axis gets below it.
                scan = min(projection.row_ssr({key: edge, other: k})[0] for k in np.geomspace(1e4, 1e8, 65))
                assert profile(edge) <= scan * (1 + 1e-9)
                # A closed edge means the accepted Ka stop there, so a whole search
                # cell beyond it holds none, read at the density the interval is cut
                # at. Left to the search grid the profile of a stepwise model can dip
                # back below the cut-off between two nodes and the edge is invented.
                cell = 1.0 / varpro._SEARCH_PER_DECADE
                above = edge == interval.high
                span = varpro._ka_grid(
                    *sorted((edge, edge * 10.0 ** (cell if above else -cell))), varpro._PROFILE_PER_DECADE
                )
                assert all(profile(ka) > threshold for ka in (span[1:] if above else span[:-1]))


def test_a_saturated_design_is_open_on_the_side_the_data_cannot_close():
    # Guest binding far stronger than the dye's makes the displacement
    # stoichiometric: raising Ka further does not change the curve, so the data
    # set a lower limit on Ka and no upper one.
    x, y = _make_ida_data(dict(IDA_TRUE, Ka_guest=1e11))
    assay = _assay(AssayType.IDA, x, _homoscedastic(y, 0.01, 1), **_IDA_CONDITIONS)
    projection = Projection(assay, GDA_IDA_RECOVERY_BOUNDS)
    fit = projection.fit()
    interval = projection.interval('Ka_guest', fit)
    assert (interval.open_low, interval.open_high) == (False, True)
    assert interval.high == 1e12
    assert 1e-8 < interval.low < 1e11
    assert not interval.split and not interval.unsolvable_high


def test_noise_free_data_still_give_an_interval_of_finite_width():
    # With no scatter the residual floor is arithmetic, so the cut-off is taken
    # from the resolution of R² rather than from a residual of rounding error.
    assay, bounds, truth = _noise_free_case(AssayType.GDA)
    projection = Projection(assay, bounds)
    fit = projection.fit()
    interval = projection.interval('Ka_guest', fit)
    assert projection.threshold(fit) >= varpro._R2_RESOLUTION * projection.ss_tot[0]
    assert interval.low < truth['Ka_guest'] < interval.high
    assert np.log10(interval.high / interval.low) > 10 * varpro._LOG_KA_XTOL


def test_a_pinned_ka_is_not_searched_and_has_no_interval():
    ka = IDA_TRUE['Ka_guest']
    projection = _ida(n=12, Ka_guest=(Q_(ka, '1/M'), Q_(ka, '1/M')))
    fit = projection.fit()
    assert fit.ka == {'Ka_guest': ka} and fit.n_free_ka == 0
    assert projection.free_ka == ()
    assert projection.interval('Ka_guest', fit) is None
    # Ka is fixed, so the F test judges the coefficients alone.
    assert projection.n_params(fit) == 2


def test_pinning_one_of_two_ka_collapses_the_search_to_the_other():
    h0 = 1e-5
    x = np.linspace(0.0, 2e-4, 15)
    y = _homoscedastic(_hg2_truth_signal(x, h0, 1e6, 1e5), 0.01, 2)
    assay = _assay(AssayType.DBA_HG2, x, y, h0=Q_(h0, 'M'))
    bounds = {**ASSAY_REGISTRY[AssayType.DBA_HG2].default_bounds, 'Ka_HG2': (Q_(1e5, '1/M'), Q_(1e5, '1/M'))}
    projection = Projection(assay, bounds)
    fit = projection.fit()
    assert projection.free_ka == ('Ka_HG',) and fit.n_free_ka == 1
    assert fit.ka['Ka_HG2'] == 1e5
    assert projection.interval('Ka_HG2', fit) is None
    interval = projection.interval('Ka_HG', fit)
    assert interval.low < fit.ka['Ka_HG'] < interval.high
    # Against a dense scan of the free axis at the pinned value.
    scan = min(projection.row_ssr({'Ka_HG': k, 'Ka_HG2': 1e5})[0] for k in np.geomspace(1e-8, 1e12, 801))
    assert fit.objective <= scan * (1 + 1e-9)


def test_too_few_points_for_a_cut_off_is_refused_and_says_no_fit_is_reported():
    # Every fit cuts its intervals, so this refusal ends the fit: the message
    # has to say that, and name the way out, rather than promise a fit without
    # an interval.
    projection = _ida(n=3)
    fit = projection.fit()
    with pytest.raises(FitRefused, match='3 titration points, too few to judge the 3 parameters'):
        projection.interval('Ka_guest', fit)


def test_ka_interval_round_trips_through_a_dict():
    interval = KaInterval(1.5e6, 2.5e6, False, True, 0.95, 12, split=True, unsolvable_high=True)
    assert KaInterval.from_dict(interval.to_dict()) == interval
    assert KaInterval.from_dict(
        {'low': 1.0, 'high': 2.0, 'open_low': False, 'open_high': False, 'level': 0.95, 'dof': 5}
    ) == (KaInterval(1.0, 2.0, False, False, 0.95, 5))


def _compensated_hg2(scale: float = 1.0):
    """A 1:2 titration whose first constant the second can stand in for: only the 1:2 complex and the singly
    bound host signal, so a lower Ka_HG is made up by a higher Ka_HG2 for as long as its bound lets it rise."""
    x = np.linspace(0.0, 5e-5, 20)
    y = hg2_signal(I0=0.0, Ka_HG=1e6, Ka_HG2=1e5, I_G=0.0, I_H=0.0, I_HG=1e8, I_HG2=3e8, h0=1e-5, g0_values=x)
    return _assay(AssayType.DBA_HG2, x, scale * _homoscedastic(y, 0.01, 5))


def _compensated_bounds(ka_hg2_top: float) -> dict:
    return {
        **ASSAY_REGISTRY[AssayType.DBA_HG2].default_bounds,
        'Ka_HG': (Q_(1e0, '1/M'), Q_(1e9, '1/M')),
        'Ka_HG2': (Q_(1e2, '1/M'), Q_(ka_hg2_top, '1/M')),
    }


def test_a_crossing_only_the_other_constants_bound_produces_is_open_and_names_that_constant():
    # Below the fit, Ka_HG is compensated by Ka_HG2 until Ka_HG2 reaches its upper bound; from there the residual
    # rises and crosses the threshold. That crossing belongs to the bound — it moves two decades when the bound
    # does — so it is no lower limit of Ka_HG. The lower edge of Ka_HG2 is set by the data and stays where it is.
    edges = {}
    for top in (1e8, 1e10):
        projection = Projection(_compensated_hg2(), _compensated_bounds(top))
        fit = projection.fit()
        first, second = projection.interval('Ka_HG', fit), projection.interval('Ka_HG2', fit)
        assert (first.open_low, first.limited_by_low) == (True, 'Ka_HG2')
        assert (second.open_low, second.limited_by_low) == (False, '')
        edges[top] = (first.low, second.low)
    assert np.log10(edges[1e8][0] / edges[1e10][0]) == pytest.approx(2.0, abs=0.01)
    assert edges[1e8][1] == pytest.approx(edges[1e10][1], rel=1e-6)


@pytest.mark.parametrize('scale', [1e-3, 1e6])
def test_the_fit_and_its_intervals_do_not_depend_on_the_gain_the_signal_was_recorded_at(scale):
    # The same titration read at another detector gain is the same experiment: the default bounds leave every
    # signal parameter free above zero, so nothing in the fit is tied to the size of the numbers.
    bounds = _compensated_bounds(1e8)
    reference, scaled = Projection(_compensated_hg2(), bounds), Projection(_compensated_hg2(scale), bounds)
    fit_ref, fit_scaled = reference.fit(), scaled.fit()
    for key in reference.ka_keys:
        assert fit_scaled.ka[key] == pytest.approx(fit_ref.ka[key], rel=1e-6)
        ci_ref, ci_scaled = reference.interval(key, fit_ref), scaled.interval(key, fit_scaled)
        assert (ci_scaled.low, ci_scaled.high) == pytest.approx((ci_ref.low, ci_ref.high), rel=1e-6)
        assert (ci_scaled.open_low, ci_scaled.open_high) == (ci_ref.open_low, ci_ref.open_high)
    assert fit_scaled.coefficients == pytest.approx(scale * fit_ref.coefficients, rel=1e-6)


def test_a_bright_signal_from_a_dilute_dye_is_fitted_like_any_other():
    # 10 nM dye read at 1e5 au needs a coefficient of 2e13 au/M. The default bounds put no ceiling on it.
    c, ka = 1e-8, 1e9
    x = np.linspace(0.0, 5 * c, 20)
    y = ida_signal(I0=0.0, Ka_guest=ka, I_dye_free=2e12, I_dye_bound=2e13, Ka_dye=ka, h0=c, d0=c, g0_values=x)
    conditions = dict(Ka_dye=Q_(ka, '1/M'), h0=Q_(c, 'M'), d0=Q_(c, 'M'))
    assay = _assay(AssayType.IDA, x, _homoscedastic(y, 0.01, 5), **conditions)
    projection = Projection(assay, assay.get_default_bounds())
    fit = projection.fit()
    interval = projection.interval('Ka_guest', fit)

    assert 1.0 - fit.objective / projection.ss_tot[0] > 0.995
    assert interval.low < ka < interval.high and not (interval.open_low or interval.open_high)


# ---------------------------------------------------------------------------
# Degenerate coefficients
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    'assay_type, free_host, expected',
    [
        (AssayType.IDA, False, ('I0', 'I_dye_free', 'I_dye_bound')),
        (AssayType.DBA_HtoD, False, ('I0', 'I_dye_free', 'I_dye_bound')),
        (AssayType.GDA, False, ()),
        (AssayType.DBA_DtoH, False, ()),
        (AssayType.DBA_HG2, False, ()),
        (AssayType.DBA_H2G, False, ()),
        (AssayType.DBA_HG2, True, ('I0', 'I_H', 'I_HG', 'I_HG2')),
        (AssayType.DBA_H2G, True, ('I0', 'I_H', 'I_HG', 'I_H2G')),
    ],
    ids=lambda v: v.name if isinstance(v, AssayType) else str(v),
)
def test_degenerate_keys_are_the_coefficients_a_mass_balance_ties_to_the_offset(assay_type, free_host, expected):
    # Where the fixed partner's free and bound forms sum to its total, their
    # columns and the offset are collinear: only a combination of the three is
    # determined. Freeing the host coefficient of a 1:2 model adds the host
    # balance H + HG + HG2 = h0 (or H + 2 H2G + HG = h0 for the 2:1 model).
    clean, bounds, truth = _noise_free_case(assay_type, free_host=3e5 if free_host else 0.0)
    x, y = clean.x_data.magnitude, clean.y_data.magnitude
    assay = _assay(assay_type, x, _homoscedastic(y, 0.005, 3))
    # Two decades around each truth keep the two-Ka search quick; the flags are a property of the design at the optimum.
    bounds = {**bounds, **{k: (Q_(v / 100, '1/M'), Q_(v * 100, '1/M')) for k, v in truth.items()}}
    projection = Projection(assay, bounds)
    fit = projection.fit()
    assert projection.degenerate_keys(fit) == expected
    # One tied combination costs the design one rank.
    n_free = sum(bounds[k][0] != bounds[k][1] for k in projection.coef_keys)
    assert fit.rank == n_free - (1 if expected else 0)


def test_a_species_the_fit_barely_populates_is_named_degenerate_like_the_rest():
    # With the host coefficient free, the host balance H + HG + HG2 = h0 ties
    # the offset and the three host species together: none of their four
    # coefficients is determined on its own. Where the second step is a hundred
    # times the first the host is almost never singly bound, so the HG column is
    # orders of magnitude shorter than the others — which changes nothing about
    # what the data determine.
    x = np.linspace(0.0, 5e-5, 20)
    truth = dict(I0=100.0, Ka_HG=1e5, Ka_HG2=1e7, I_G=1e6, I_H=3e5, I_HG=1e7, I_HG2=5e6, h0=1e-5)
    assay = _assay(AssayType.DBA_HG2, x, _homoscedastic(hg2_signal(**truth, g0_values=x), 0.005, 3), h0=Q_(1e-5, 'M'))
    bounds = {
        **ASSAY_REGISTRY[AssayType.DBA_HG2].default_bounds,
        'I_H': (Q_(0, 'au/M'), Q_(1e12, 'au/M')),
        'Ka_HG': (Q_(1e3, '1/M'), Q_(1e7, '1/M')),
        'Ka_HG2': (Q_(1e5, '1/M'), Q_(1e9, '1/M')),
    }
    projection = Projection(assay, bounds)
    fit = projection.fit()

    species = assay.species(projection.params(fit))
    assert species['HG'].max() < 1e-3 * species['HG2'].max(), 'the design does not populate HG sparsely'
    assert projection.degenerate_keys(fit) == ('I0', 'I_H', 'I_HG', 'I_HG2')


def test_a_species_too_sparse_to_change_the_rank_of_the_design_is_still_named_degenerate():
    # With the second step ten orders of magnitude above the first, HG is populated below the resolution the
    # rank of the design is read at: the other columns look dependent with or without it. The host balance moves
    # its coefficient as much as the others all the same, so it is no better determined than they are.
    # The flag is a property of the design at the binding constants, so the signal is any that changes.
    x = np.linspace(3e-4, 3e-3, 20)
    assay = _assay(AssayType.DBA_HG2, x, np.linspace(1.0, 2.0, x.size), h0=Q_(1e-4, 'M'))
    bounds = {**ASSAY_REGISTRY[AssayType.DBA_HG2].default_bounds, 'I_H': (Q_(0, 'au/M'), Q_(1e12, 'au/M'))}
    projection = Projection(assay, bounds)
    ka = {'Ka_HG': 17.6, 'Ka_HG2': 9.5e11}
    fit = varpro.ProjectedFit(
        ka=ka, coefficients=np.zeros((1, 5)), row_ssr=np.zeros(1), objective=0.0, rank=3, n_free_ka=2
    )

    species = assay.species(np.array([ka['Ka_HG'], ka['Ka_HG2'], 0, 0, 0, 0, 0]))
    sparse = np.linalg.norm(species['HG']) / np.linalg.norm(species['HG2'])
    assert sparse < varpro._RANK_RTOL, 'the design does not populate HG below the rank cut-off'
    assert projection.degenerate_keys(fit) == ('I0', 'I_H', 'I_HG', 'I_HG2')


def test_every_coefficient_a_species_the_fit_leaves_unpopulated_trades_against_is_named():
    # Where the second binding step is negligible, HG2 = Ka_HG2·[HG][G] is, to the order the fit resolves,
    # Ka_HG2·h0·[G] − (Ka_HG2/Ka_HG)·[HG]: a combination of two well-populated columns. The fit can then
    # take I_G away altogether and put the signal on the empty HG2 column instead — at a coefficient no
    # species could have, but the curve is the same, so neither I_G nor I_HG nor I_HG2 is a result. The
    # offset takes no part in the relation.
    x = np.linspace(0.0, 1e-3, 12)
    ka = {'Ka_HG': 2e3, 'Ka_HG2': 1.4e-5}
    assay = _assay(
        AssayType.DBA_HG2,
        x,
        _homoscedastic(_hg2_truth_signal(x, 8.5e-5, **{k.lower(): v for k, v in ka.items()}), 0.01, 4),
        h0=Q_(8.5e-5, 'M'),
    )
    bounds = {
        **ASSAY_REGISTRY[AssayType.DBA_HG2].default_bounds,
        **{k: (Q_(v, '1/M'), Q_(v, '1/M')) for k, v in ka.items()},
    }
    projection = Projection(assay, bounds)
    fit = projection.fit()
    species = assay.species(projection.params(fit))
    assert species['HG2'].max() < 1e-8 * species['G'].max(), 'the design does not leave HG2 unpopulated'

    assert projection.degenerate_keys(fit) == ('I_G', 'I_HG', 'I_HG2')
    # The same curve without I_G: the residual changes by under 1e-9 of the total sum of squares, within the
    # resolution of the bounded solve, and the coefficient that replaces I_G on the HG2 column is a hundred
    # million times the one the data put on the guest.
    without_g = Projection(assay, {**bounds, 'I_G': (Q_(0, 'au/M'), Q_(0, 'au/M'))}).fit()
    assert fit.coefficients[0][projection.coef_keys.index('I_G')] > 0
    assert abs(without_g.objective - fit.objective) <= 1e-9 * projection.ss_tot[0]
    i_g, i_hg2 = (projection.coef_keys.index(k) for k in ('I_G', 'I_HG2'))
    assert without_g.coefficients[0][i_hg2] > 1e8 * fit.coefficients[0][i_g]


# ---------------------------------------------------------------------------
# Replicates
# ---------------------------------------------------------------------------


def _replicates(n: int, noise: float, seed: int, *, ka_factors=(), noise_factors=()) -> tuple[np.ndarray, np.ndarray]:
    """IDA replicates with own amplitudes; replicate r may carry its own Ka or noise factor."""
    rng = np.random.default_rng(seed)
    x = np.linspace(0.0, 50e-6, n)
    r_total = max(len(ka_factors), len(noise_factors), 4)
    rows = []
    for r in range(r_total):
        ka = IDA_TRUE['Ka_guest'] * (ka_factors[r] if r < len(ka_factors) else 1.0)
        clean = ida_signal(
            I0=0.0,
            Ka_guest=ka,
            I_dye_free=IDA_TRUE['I_dye_free'],
            I_dye_bound=IDA_TRUE['I_dye_bound'],
            Ka_dye=IDA_TRUE['Ka_dye'],
            h0=IDA_TRUE['h0'],
            d0=IDA_TRUE['d0'],
            g0_values=x,
        )
        sigma = noise * np.ptp(clean) * (noise_factors[r] if r < len(noise_factors) else 1.0)
        rows.append(rng.uniform(0.8, 1.2) * clean + rng.normal(0.0, sigma, n))
    return x, np.array(rows)


def _replicate_projection(x: np.ndarray, rows: np.ndarray) -> Projection:
    assay = _assay(AssayType.IDA, x, rows.mean(axis=0), **_IDA_CONDITIONS)
    return Projection(assay, ASSAY_REGISTRY[AssayType.IDA].default_bounds, signals=rows)


@pytest.mark.parametrize('seed', [0, 1, 2])
def test_a_replicate_that_needs_another_ka_is_excluded_by_name(seed):
    x, rows = _replicates(20, 0.02, seed, ka_factors=(10.0, 1.0, 1.0, 1.0))
    test = replicate_outliers(_replicate_projection(x, rows))
    assert test.tested
    assert test.excluded == (0,)
    assert test.p_values[0] < 0.01 / 4
    assert all(p >= 0.01 / 4 for r, p in test.p_values.items() if r != 0)
    assert test.level == 0.01


@pytest.mark.parametrize('seed', [10, 11, 12])
def test_replicates_that_share_ka_are_all_kept(seed):
    x, rows = _replicates(12, 0.02, seed)
    test = replicate_outliers(_replicate_projection(x, rows))
    assert test.tested and test.excluded == ()
    assert set(test.p_values) == {0, 1, 2, 3}


@pytest.mark.parametrize('seed', [20, 21, 22])
def test_a_noisier_replicate_is_not_an_outlier(seed):
    # Each replicate's misfit is measured in units of its own scatter, so
    # scatter alone is no reason to leave a replicate out.
    x, rows = _replicates(12, 0.02, seed, noise_factors=(1.0, 1.0, 1.0, 4.0))
    test = replicate_outliers(_replicate_projection(x, rows))
    assert test.tested and test.excluded == ()


def test_two_replicates_are_not_judged():
    x, rows = _replicates(12, 0.02, 30, ka_factors=(10.0, 1.0))
    test = replicate_outliers(_replicate_projection(x, rows[:2]))
    assert not test.tested and test.excluded == () and test.p_values == {}


def test_the_test_never_removes_half_of_the_replicates():
    # Two of four replicates at another Ka: a majority defines the consensus, so
    # at most one may go, and with two candidates the rule stops at one.
    x, rows = _replicates(20, 0.02, 40, ka_factors=(10.0, 10.0, 1.0, 1.0))
    test = replicate_outliers(_replicate_projection(x, rows))
    assert len(test.excluded) <= 1
