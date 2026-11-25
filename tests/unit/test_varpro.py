"""Variable projection engine — scientific behaviour tests.

Every binding model is ``y = A(K) c + e``: the design at fixed binding
constants K holds a column of ones and the species the signal coefficients
multiply, and the best coefficients at that K are an exact bounded linear
least-squares solve. These tests pin what makes the engine trustworthy:

- the design reconstructs the forward model for every assay, and the projected
  residual equals an independent bounded least-squares solve;
- noise-free data give the true Ka back to the search's own resolution for
  every assay, one or two binding constants alike, and a repeat is bit-identical;
- the two-Ka search is at least as good as a dense brute-force grid, and both
  searches reach a basin or valley narrower than a search cell where the
  minimum lies;
- a constant whose objective falls to its bound rests there however far short
  of it the search stopped, and a signal offset the minimum holds on zero is
  not counted however close to the minimiser the search stopped;
- the interval edges lie exactly on the F-test cut-off, a saturated design is
  reported open on the side the data cannot close, and a pinned Ka has none;
- the routine both interval engines cut a profile with finds, on an excess of
  known roots, a stretch and a gap that lie between two search-grid nodes and
  a stretch that begins where the cut-off steps up, however narrow and however
  far out, as an independent F test finds it on measured titrations, and
  the other constant closes an edge only on its bound and where the objective
  still falls towards it;
- structurally degenerate coefficients are named per assay;
- the replicate test leaves out the replicates that need another Ka, even two
  of five that share one, and a replicate whose scatter is far larger than the
  others', keeps replicates that agree, does not depend on their order, and
  does not judge two replicates; its scatter limit reproduces Cochran's table;
- invalid inputs are refused with a plain-language message and a stop request
  is honoured;
- the projected residual at moved inputs is that of an assay entered at those
  values, and the start a search over the other Ka is given is where a dense
  independent scan puts the minimum;
- weights of the titration points: weights of one change no bit of a fit or an
  interval, a weighted solve is the bounded least squares of the whitened
  arrays, only the ratios of the weights matter, ranks are those of the
  unweighted design, and a point the weights call imprecise steers Ka less;
- a design effect of one is the plain F test to the last bit; a larger one
  moves both closed edges out to the widened cut-off, opens a side only where
  that cut-off passes the profile at the Ka bound, and raises the one-step
  p-value to the F tail of the ratio divided by it.
"""

from collections.abc import Callable

import numpy as np
import pytest
from scipy.optimize import lsq_linear, minimize_scalar
from scipy.stats import f as f_dist

from core.assays import ASSAY_CLASSES
from core.assays.base import TITRANT
from core.assays.dye_alone import DyeAloneAssay
from core.assays.ida import IDAAssay
from core.assays.registry import ASSAY_REGISTRY, AssayType, ParamKind
from core.models.equilibrium import gda_species, h2g_signal, h2g_species, hg2_signal, hg2_species, ida_signal
from core.pipeline import varpro
from core.pipeline.varpro import (
    LEVEL,
    REPLICATE_TEST_MIN,
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


def test_the_residual_at_moved_inputs_is_that_of_an_assay_entered_at_those_values():
    x, y = _make_ida_data(IDA_TRUE, n_points=12)
    y = _homoscedastic(y, 0.02, 8)
    projection = Projection(_assay(AssayType.IDA, x, y, **_IDA_CONDITIONS), GDA_IDA_RECOVERY_BOUNDS)
    offsets = {'Ka_dye': 0.08, 'h0': -0.05, 'd0': 0.02, TITRANT: -0.03}
    moved = {k: v * (1 + offsets[k]) for k, v in _IDA_CONDITIONS.items()}
    direct = Projection(_assay(AssayType.IDA, x * 0.97, y, **moved), GDA_IDA_RECOVERY_BOUNDS)
    ka = {'Ka_guest': 1.3e6}
    residual = projection.residual(ka, offsets=offsets)
    assert residual.shape == (12,)
    assert residual @ residual == pytest.approx(direct.row_ssr(ka)[0], rel=1e-12)
    # No offsets: the entered inputs, and the residual the row's best coefficients leave.
    entered = projection.residual(ka)
    assert entered @ entered == pytest.approx(projection.row_ssr(ka)[0], rel=1e-12)
    assert np.array_equal(entered, projection.residual(ka, offsets={}))
    assert abs(entered @ entered - residual @ residual) > 1e-3 * (entered @ entered)


def test_the_residual_is_infinite_where_the_model_has_no_solution_and_asks_before_it_solves(monkeypatch):
    x, y = _make_ida_data(IDA_TRUE, n_points=12)
    assay = _assay(AssayType.IDA, x, y, **_IDA_CONDITIONS)
    asked = []
    projection = Projection(assay, GDA_IDA_RECOVERY_BOUNDS, should_cancel=lambda: bool(asked.append(1)))
    solved = []
    monkeypatch.setattr(
        IDAAssay,
        'species',
        lambda self, params: solved.append(len(asked)) or {k: np.full(12, np.nan) for k in ('H', 'D', 'G', 'HD', 'HG')},
    )
    residual = projection.residual({'Ka_guest': 1e6}, offsets={'h0': 0.01})
    assert residual.shape == (12,) and np.all(np.isinf(residual))
    assert solved == [1]  # asked once, before the one species solve


def test_inner_start_is_where_a_dense_scan_of_the_other_ka_puts_the_minimum():
    h0 = 1e-5
    x = np.linspace(0.0, 1e-4, 20)
    y = _homoscedastic(_hg2_truth_signal(x, h0, 1e6, 1e5), 0.01, 2)
    box = (Q_(1e4, '1/M'), Q_(1e8, '1/M'))
    projection = Projection(
        _assay(AssayType.DBA_HG2, x, y, h0=Q_(h0, 'M')),
        {**ASSAY_REGISTRY[AssayType.DBA_HG2].default_bounds, 'Ka_HG': box, 'Ka_HG2': box},
    )
    node = float(projection._grid()[0][0][9])
    for ka in (node, node * 1.37):
        start = projection.inner_start('Ka_HG', ka)
        assert list(start) == ['Ka_HG2']

        def ssr(t: float) -> float:
            return projection.row_ssr({'Ka_HG': ka, 'Ka_HG2': 10.0**t})[0]

        scan = np.linspace(4, 8, 65)
        i = int(np.argmin([ssr(t) for t in scan]))
        dense = minimize_scalar(ssr, bounds=(scan[max(i - 1, 0)], scan[min(i + 1, 64)]), method='bounded')
        assert ssr(np.log10(start['Ka_HG2'])) <= dense.fun * (1 + 1e-9)
        assert np.log10(start['Ka_HG2']) == pytest.approx(dense.x, abs=1e-3)
    assert _ida().inner_start('Ka_guest', 1e6) == {}


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


def test_two_ka_starts_are_the_lowest_local_minima_of_the_search_grid_and_the_fit_is_no_worse_than_any():
    h0 = 1e-5
    x = np.linspace(0.0, 2e-4, 15)
    y = _homoscedastic(_hg2_truth_signal(x, h0, 1e6, 1e5), 0.05, 3)  # noisy enough for four local minima
    box = (Q_(1e2, '1/M'), Q_(1e10, '1/M'))
    projection = Projection(
        _assay(AssayType.DBA_HG2, x, y, h0=Q_(h0, 'M')),
        {**ASSAY_REGISTRY[AssayType.DBA_HG2].default_bounds, 'Ka_HG': box, 'Ka_HG2': box},
    )
    first, second = (np.geomspace(1e2, 1e10, 33),) * 2  # four nodes per decade
    ssr = np.array([[projection.row_ssr({'Ka_HG': k1, 'Ka_HG2': k2})[0] for k2 in second] for k1 in first])
    minima = []
    for i in range(first.size):
        for j in range(second.size):
            around = ssr[max(i - 1, 0) : i + 2, max(j - 1, 0) : j + 2]
            if ssr[i, j] <= around.min():
                minima.append((ssr[i, j], {'Ka_HG': float(first[i]), 'Ka_HG2': float(second[j])}))
    expected = [ka for _, ka in sorted(minima, key=lambda found: found[0])[:5]]
    assert len(minima) == 4 and projection.two_ka_starts() == expected
    assert projection.fit().objective <= min(value for value, _ in minima)


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


def test_a_one_ka_fit_finds_a_basin_whose_grid_node_is_not_the_lowest():
    """A weighted one-Ka titration (GDA, 1:1000 dye to guest, proportional noise, the weights its four replicates
    give) whose objective has three basins on the search grid: the lowest node lies at 10^3.75, but the minimum,
    3.6 % lower, lies in a narrow basin near 10^7.9 whose own node reads higher. An independent 400-per-decade scan
    refined by bounded Brent puts the minimum there."""
    from core.pipeline.noise import noise_law
    from validation.checks import CHECKS
    from validation.generate import dataset

    (case,) = (case for case in CHECKS['reference-agreement'].cases if case.id == 'GDA,K=1000,n=12,noise=0.02,prop,m=4')
    data = dataset(case, 64)
    mean = data.signals.mean(axis=0)
    projection = Projection(
        data.assay,
        data.assay.get_default_bounds(),
        signals=mean[np.newaxis, :],
        point_weights=noise_law(data.signals).weights(mean),
    )
    fit = projection.fit()
    best, s_min, _ = _independent_one_ka(projection, per_decade=400)
    assert fit.objective <= s_min + varpro._R2_RESOLUTION * float(projection.ss_tot[0])
    assert np.log10(fit.ka['Ka_guest']) == pytest.approx(best, abs=1e-4)


@pytest.mark.parametrize(
    ('case', 'seed', 'second'),
    [('DBA_HG2,K=0.1,n=8,noise=0.01', 137, 3500.80), ('DBA_H2G,K=10,n=12,noise=0.01', 11, 13672.8)],
    ids=['HG2-valley', 'H2G-plateau'],
)
def test_a_two_ka_fit_reaches_a_valley_narrower_than_a_search_cell(case, seed, second):
    """Stepwise titrations whose K₁·K₂ valley leaves no local minimum on the search grid, which shows a lower
    plateau of the second constant or another valley instead. With the second constant held where an independent
    brute force puts the minimum, an independent scan of the first constant reaches 2.8e-3 and 1e-2 of the objective
    below where the grid local minima alone lead; the fit is no higher than that."""
    projection = _grid_projection(case, seed)
    fit = projection.fit()
    independent, _, _ = _independent_first_constant_minimum(projection, second)
    assert fit.objective <= independent + varpro._R2_RESOLUTION * float(projection.ss_tot[0])


def test_no_solvable_ka_is_refused_in_plain_language(monkeypatch):
    x, y = _make_ida_data(IDA_TRUE, n_points=12)
    assay = _assay(AssayType.IDA, x, y, **_IDA_CONDITIONS)
    monkeypatch.setattr(
        IDAAssay, 'species', lambda self, params: {k: np.full(12, np.nan) for k in ('H', 'D', 'G', 'HD', 'HG')}
    )
    with pytest.raises(ValueError, match='no solution at any association constant between 1×10⁻⁸ M⁻¹ and 1×10¹² M⁻¹'):
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
    'bad, says',
    [
        ((Q_(0, '1/M'), Q_(1e12, '1/M')), 'lower bound 0 M⁻¹ under Binding model.*above zero'),
        ((Q_(-5, '1/M'), Q_(1e12, '1/M')), 'lower bound -5 M⁻¹ under Binding model.*above zero'),
        ((Q_(1e8, '1/M'), Q_(1e6, '1/M')), 'lower bound of 1×10⁸ M⁻¹ above its upper bound of 1×10⁶ M⁻¹'),
    ],
    ids=['zero', 'negative', 'inverted'],
)
def test_invalid_ka_bounds_are_refused_in_the_words_and_units_the_bounds_panel_shows(bad, says):
    """The message names the value the user entered, in M⁻¹ as the panel writes it, never a dictionary key."""
    x, y = _make_ida_data(IDA_TRUE, n_points=12)
    assay = _assay(AssayType.IDA, x, y, **_IDA_CONDITIONS)
    with pytest.raises(FitRefused, match=says) as refused:
        Projection(assay, {**GDA_IDA_RECOVERY_BOUNDS, 'Ka_guest': bad})
    assert 'Ka_guest' not in str(refused.value) and '1/M' not in str(refused.value)


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
        assert interval.low <= fit.ka[key] <= interval.high
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


def _hand_built(monkeypatch, design: np.ndarray, y: np.ndarray, **bounds) -> Projection:
    """A host-to-dye projection whose design (offset, free dye, bound dye) is *design* at every Ka."""
    assay = _assay(AssayType.DBA_HtoD, np.linspace(1e-6, 2e-5, y.size), y)
    limits = {**ASSAY_REGISTRY[AssayType.DBA_HtoD].default_bounds, **bounds}
    projection = Projection(assay, limits)
    monkeypatch.setattr(projection, '_design', lambda ka, assay=None: design)
    return projection


def test_fitted_rank_leaves_out_a_coefficient_the_solve_holds_on_its_bound(monkeypatch):
    t = np.linspace(0.0, 1.0, 9)
    design = np.column_stack([np.ones(9), t, t**2])
    wide = (Q_(-1e3, 'au'), Q_(1e3, 'au'))
    floor = {
        'I0': wide,
        'I_dye_free': (Q_(0.0, 'au/M'), Q_(1e3, 'au/M')),
        'I_dye_bound': (Q_(0.5, 'au/M'), Q_(1e3, 'au/M')),
    }
    # Every coefficient of 2 + 3 t + t² is inside its bounds: three fitted parameters.
    assert _hand_built(monkeypatch, design, 2 + 3 * t + t**2, **floor).fitted_parameters({'Ka_dye': 1e5}).rank == 3
    # The slope of 2 - 0.2 t + 3 t² is negative, so it is held on zero: two are fitted.
    assert (
        _hand_built(monkeypatch, design, 2 - 0.2 * t + 3 * t**2, **floor).fitted_parameters({'Ka_dye': 1e5}).rank == 2
    )
    # A falling line also puts the curvature on its bound of 0.5, a bound that is not zero: one is left.
    assert _hand_built(monkeypatch, design, 2 - 3 * t, **floor).fitted_parameters({'Ka_dye': 1e5}).rank == 1
    # A pinned coefficient is no fitted parameter, inside its bounds or not.
    pinned = {**floor, 'I_dye_bound': (Q_(1.0, 'au/M'), Q_(1.0, 'au/M'))}
    assert _hand_built(monkeypatch, design, 2 + 3 * t + t**2, **pinned).fitted_parameters({'Ka_dye': 1e5}).rank == 2


def test_fitted_rank_does_not_change_with_a_constant_background_under_the_signal(monkeypatch):
    # 2 + 3 t + 0.1 t² with every bound far away: three fitted parameters, whatever constant the
    # instrument adds. "On a bound" is read against the signal's variation, which a background
    # leaves as it is, and the curvature carries 0.1 of a signal that varies by 3.1.
    t = np.linspace(0.0, 1.0, 9)
    design = np.column_stack([np.ones(9), t, t**2])
    wide = {
        'I0': (Q_(-1e14, 'au'), Q_(1e14, 'au')),
        'I_dye_free': (Q_(0.0, 'au/M'), Q_(1e14, 'au/M')),
        'I_dye_bound': (Q_(0.0, 'au/M'), Q_(1e14, 'au/M')),
    }
    for background in (0.0, 1e5, 1e7, 1e9):
        projection = _hand_built(monkeypatch, design, background + 2 + 3 * t + 0.1 * t**2, **wide)
        assert projection.fitted_parameters({'Ka_dye': 1e5}).rank == 3


def test_a_profile_point_of_one_free_ka_is_one_solve_for_its_residual_and_what_it_fitted(monkeypatch):
    projection = _ida(n=15, frac=0.02, seed=5)
    calls = []
    design = projection._design
    monkeypatch.setattr(projection, '_design', lambda ka, assay=None: calls.append(ka) or design(ka, assay))
    point, value, fitted = projection.profile_point('Ka_guest', 3e6)
    assert len(calls) == 1
    again = projection.fitted_parameters(point)
    assert (value, fitted.ka, fitted.rank) == (projection.row_ssr(point)[0], again.ka, again.rank)


def test_fitted_rank_counts_columns_a_mass_balance_ties_once(monkeypatch):
    # Free plus bound dye sum to the dye total, so the three columns span two
    # directions and the solve returns one member of a family: three
    # coefficients inside their bounds are two fitted parameters.
    t = np.linspace(0.1, 0.9, 9)
    design = np.column_stack([np.ones(9), t, 1.0 - t])
    projection = _hand_built(monkeypatch, design, 5 + 2 * t + 7 * (1 - t))
    _, coef = projection._solve(design)
    assert np.all(coef[0] > 0)
    assert projection.fitted_parameters({'Ka_dye': 1e5}).rank == 2


def test_fitted_rank_is_zero_where_the_model_has_no_solution(monkeypatch):
    t = np.linspace(0.0, 1.0, 9)
    projection = _hand_built(monkeypatch, np.full((9, 3), np.nan), 2 + 3 * t)
    assert projection.fitted_parameters({'Ka_dye': 1e5}).rank == 0


def _gda_offset_on_its_floor() -> Projection:
    """GDA with no background under the signal: the offset's floor of zero holds it wherever the noise asks
    for less, as it does at this seed."""
    x, y = _make_gda_data(GDA_TRUE, n_points=12)
    assay = _assay(AssayType.GDA, x, _homoscedastic(y, 0.01, 0), **_GDA_CONDITIONS)
    return Projection(assay, dict(ASSAY_REGISTRY[AssayType.GDA].default_bounds))


def test_the_interval_counts_only_what_the_best_fit_fitted_in_its_degrees_of_freedom():
    """``n - p`` is the dimension the residual keeps: a parameter held on a bound takes none of it.

    Here the offset rests on its floor of zero, so the best fit fits Ka and two
    signal coefficients of the three the model has: ``n - p`` is 12 - 3, not
    12 - 4, and the cut-off is the F test on 9 degrees of freedom.
    """
    projection = _gda_offset_on_its_floor()
    fit = projection.fit()
    assert fit.coefficients[0][0] == 0.0, 'the bounded solve holds the offset on its floor'
    assert (fit.n_free_ka, fit.rank) == (1, 3)
    fitted = projection.fitted_parameters(fit.ka)
    assert (fitted.ka, fitted.rank, fitted.count) == (('Ka_guest',), 2, 3)
    assert projection.n_params(fit) == 3
    interval = projection.interval('Ka_guest', fit)
    assert interval.dof == 12 - 3
    assert projection.threshold(fit) == pytest.approx(fit.objective * (1 + f_dist.ppf(LEVEL, 1, 9) / 9), rel=1e-12)


def test_a_ka_on_its_bound_is_not_counted_among_what_the_fit_fitted():
    """Bounds that stop below where the data put Ka leave the estimate on the upper one, held there."""
    x, y = _make_ida_data(IDA_TRUE, n_points=15)
    assay = _assay(AssayType.IDA, x, _homoscedastic(y, 0.02, 5), **_IDA_CONDITIONS)
    bounds = dict(ASSAY_REGISTRY[AssayType.IDA].default_bounds)
    capped = Projection(assay, {**bounds, 'Ka_guest': (Q_(1e-8, '1/M'), Q_(1e6, '1/M'))})
    fit = capped.fit()
    assert fit.ka['Ka_guest'] == pytest.approx(1e6, rel=1e-12)
    fitted = capped.fitted_parameters(fit.ka)
    assert fitted.ka == () and fitted.count == fitted.rank == 2
    assert capped.interval('Ka_guest', fit).dof == 15 - 2
    # The same data over bounds the estimate lies inside: the constant is counted.
    free = Projection(assay, bounds)
    assert free.fitted_parameters(free.fit().ka).count == 3


def _independent_first_constant_minimum(projection: Projection, ka_second: float) -> tuple[float, float, int]:
    """The residual of a stepwise titration minimised over its first constant, the second held at *ka_second*.

    ``(SSR, first constant, fitted rank)`` from the model's species and a bounded solve of this function's own on
    norm-scaled columns (the offset, free guest and both complexes, every coefficient at or above zero; the free-host
    coefficient is held at zero): the first constant read on a 16-per-decade scan of its whole box and refined by
    bounded Brent between the neighbours of the best node. The rank is that of the columns whose coefficient the
    solve leaves off zero.
    """
    assay, y = projection.assay, projection.signals[0]
    names = [ASSAY_REGISTRY[assay.assay_type].signal_species.get(k) for k in projection.coef_keys if k != 'I_H']

    def solve(t: float) -> tuple[float, int]:
        params = np.zeros(len(assay.parameter_keys))
        params[:2] = 10.0**t, ka_second
        species = assay.species(params)
        columns = np.column_stack([np.ones(y.size) if name is None else species[name] for name in names])
        scaled = columns / np.linalg.norm(columns, axis=0)
        found = lsq_linear(scaled, y, bounds=(0.0, np.inf), method='bvls', tol=1e-14)
        inside = scaled[:, found.active_mask == 0]
        singular = np.linalg.svd(inside, compute_uv=False) if inside.shape[1] else np.zeros(1)
        return float(np.sum((scaled @ found.x - y) ** 2)), int(np.sum(singular > 1e-8 * singular.max()))

    low, high = np.log10(projection.ka_bounds[projection.ka_keys[0]])
    scan = np.linspace(low, high, int(round((high - low) * 16)) + 1)
    i = int(np.argmin([solve(t)[0] for t in scan]))
    found = minimize_scalar(
        lambda t: solve(t)[0],
        bounds=(scan[max(i - 1, 0)], scan[min(i + 1, scan.size - 1)]),
        method='bounded',
        options={'xatol': 1e-10},
    )
    ssr, rank = solve(found.x)
    return ssr, float(10.0**found.x), rank


# Stepwise titrations whose second constant the least-squares fit puts on the top of its box: the objective, the
# first constant minimised, falls all the way to that bound, along a valley so flat that the two-constant search can
# stop a tenth of a decade to several decades short of it. Four are datasets of the reference-agreement grid (the
# last three stop 4.3, 1.5 and 1.6 decades short, where the first constant left where the search stopped is far off
# the valley), the others random designs from the vanishing-sigma comparison of the two engines.
_ON_TOP = {
    'grid-HG2-n8': lambda: _grid_projection('DBA_HG2,K=0.1,n=8,noise=0.01', 0),
    'grid-H2G-n12-far': lambda: _grid_projection('DBA_H2G,K=0.1,n=12,noise=0.01', 5),
    'grid-HG2-n12-far': lambda: _grid_projection('DBA_HG2,K=0.1,n=12,noise=0.01', 317),
    'grid-HG2-K10-n8-far': lambda: _grid_projection('DBA_HG2,K=10,n=8,noise=0.01', 343),
    'H2G-n20': lambda: _stepwise(
        AssayType.DBA_H2G, 2902916.6898986776, 16416694.18737613, 3, 710983164, n=20, noise=0.02
    )[0],
    'HG2-n8': lambda: _stepwise(AssayType.DBA_HG2, 29531.854796112406, 29847.003735592458, 3, 533310309, n=8)[0],
}


def _grid_projection(case_id: str, seed: int) -> Projection:
    """The average of the replicates of one reference-agreement dataset, every point counted equally."""
    from validation.checks import CHECKS
    from validation.generate import dataset

    (case,) = (case for case in CHECKS['reference-agreement'].cases if case.id == case_id)
    data = dataset(case, seed)
    return Projection(data.assay, data.assay.get_default_bounds(), signals=data.signals.mean(axis=0)[np.newaxis, :])


@pytest.mark.parametrize('case', list(_ON_TOP))
def test_a_constant_whose_objective_falls_to_its_bound_is_fitted_on_that_bound_and_not_counted(case):
    """Where the objective is no higher on the bound than anywhere in the last search cell before it, the fit rests there.

    Resting on the bound, the constant is held and not fitted, so ``p`` counts the first constant and the signal
    columns the bounded solve leaves free there — and the report says the data do not limit it from above.
    """
    projection = _ON_TOP[case]()
    second = projection.second_step
    top = projection.ka_bounds[second][1]
    resolution = varpro._R2_RESOLUTION * float(projection.ss_tot[0])
    on_top, first, rank = _independent_first_constant_minimum(projection, top)
    inside = [_independent_first_constant_minimum(projection, top * 10.0**-d)[0] for d in (1e-6, 1e-3, 0.03, 0.13)]
    assert all(on_top <= value + resolution for value in inside)
    assert not varpro.on_ka_bound(first, projection.ka_bounds[projection.ka_keys[0]])

    fit = projection.fit()
    assert fit.ka[second] == top
    assert fit.objective <= on_top + resolution
    assert projection.n_params(fit) == 1 + rank


@pytest.mark.parametrize(
    ('case', 'seed'), [('DBA_HG2,K=1000,n=12,noise=0.01', 273), ('DBA_HG2,K=1000,n=8,noise=0.01', 164)]
)
def test_a_signal_offset_the_minimum_holds_on_zero_is_not_counted_among_what_the_fit_fitted(case, seed):
    """1:2 titrations of the reference-agreement grid (K₂/K₁ = 1000, 1 % noise) whose minimum holds the second
    constant on the top of its box and the signal offset on zero.

    Minimised over the first constant with the offset held at zero (16-per-decade scan and bounded Brent to 1e-10
    decade, this test's own bounded solves), the residual is the least the model reaches, and there the solve with
    the offset free to go below zero takes it below zero: the bound binds at the minimum. Within 1e-7 decade of that
    point the solve leaves the offset inside its bound on one side while the residual differs by rounding, so only
    the minimiser itself says what the fit fitted: the first constant and the rank of the coefficients left free.
    """
    projection = _grid_projection(case, seed)
    assay, y = projection.assay, projection.signals[0]
    top = projection.ka_bounds['Ka_HG2'][1]
    names = [ASSAY_REGISTRY[assay.assay_type].signal_species[k] for k in projection.coef_keys if k not in ('I0', 'I_H')]

    def solve(t: float, offset_free: bool = False) -> tuple[float, int, float]:
        params = np.zeros(len(assay.parameter_keys))
        params[:2] = 10.0**t, top
        species = assay.species(params)
        columns = np.column_stack([np.ones(y.size)] * offset_free + [species[name] for name in names])
        scaled = columns / np.linalg.norm(columns, axis=0)
        lower = np.r_[[-np.inf] * offset_free, np.zeros(len(names))]
        found = lsq_linear(scaled, y, bounds=(lower, np.inf), method='bvls', tol=1e-14)
        inside = scaled[:, offset_free:][:, found.active_mask[offset_free:] == 0]
        singular = np.linalg.svd(inside, compute_uv=False) if inside.shape[1] else np.zeros(1)
        return float(np.sum((scaled @ found.x - y) ** 2)), int(np.sum(singular > 1e-8 * singular.max())), found.x[0]

    low, high = np.log10(projection.ka_bounds['Ka_HG'])
    scan = np.linspace(low, high, int(round((high - low) * 16)) + 1)
    i = int(np.argmin([solve(t)[0] for t in scan]))
    face = minimize_scalar(
        lambda t: solve(t)[0], bounds=(scan[i - 1], scan[i + 1]), method='bounded', options={'xatol': 1e-10}
    ).x
    s_face, rank, _ = solve(face)
    assert solve(face, offset_free=True)[2] < 0.0

    fit = projection.fit()
    assert fit.ka['Ka_HG2'] == top
    assert fit.objective <= s_face + varpro._R2_RESOLUTION * float(projection.ss_tot[0])
    assert projection.n_params(fit) == 1 + rank


def test_a_fit_inside_its_box_is_where_the_search_stopped_to_the_last_bit():
    """Where the objective rises towards every bound, nothing is moved: the fit is the search's own optimum."""
    projection = Projection(*_noisy_hg2())
    stopped, objective = projection._search_two(np.ones(1))
    fit = projection.fit()
    assert fit.ka == stopped and fit.objective == objective


def test_a_constant_rests_on_its_bound_only_where_the_objective_there_is_no_higher_than_where_the_search_stopped():
    """The rule both fit engines share, on a stated objective, from a stop of objective one at a resolution of 1e-10.

    A trial is made with the other parameters minimised again and with them where the search stopped — the first
    within the last search cell before the bound, the second further out — and the move stands where either is within
    the resolution; the nearer bound first, a constant put on its bound held there while the next is tried.
    """
    bounds = {'K1': (1e-8, 1e12), 'K2': (1e-8, 1e12)}
    asked = []

    def rest(ka: dict, on_bound) -> object:
        def held(found, pinned: dict, again: bool):
            asked.append((dict(pinned), again))
            return ('moved', tuple(sorted(pinned))), {**ka, **pinned}, on_bound(pinned, again)

        asked.clear()
        return varpro._rest_on_bounds('stopped', ka, 1.0, list(ka), bounds, held, 1e-10)

    near = {'K1': 1e12 * 10.0**-0.1}
    assert rest(near, lambda pinned, again: 1.0 - 1e-13) == ('moved', ('K1',))
    assert asked == [({'K1': 1e12}, True)]
    assert rest(near, lambda pinned, again: 1.0 + 0.5e-10) == ('moved', ('K1',))
    assert rest(near, lambda pinned, again: 1.0 + 2e-10) == 'stopped'
    assert asked == [({'K1': 1e12}, True), ({'K1': 1e12}, False)]
    assert rest(near, lambda pinned, again: 1.0 + 2e-10 if again else 1.0) == ('moved', ('K1',))
    far = {'K1': 1e12 * 10.0**-3}
    assert rest(far, lambda pinned, again: 1.0) == ('moved', ('K1',))
    assert asked == [({'K1': 1e12}, False)]
    # A valley the other parameters follow to the bound: left where the search stopped, they are far off it.
    assert rest(far, lambda pinned, again: 1.0 - 1e-7 if again else 1.2) == ('moved', ('K1',))
    assert asked == [({'K1': 1e12}, False), ({'K1': 1e12}, True)]
    two = {'K1': 1e12 * 10.0**-0.2, 'K2': 1e-8 * 10.0**0.01}
    assert rest(two, lambda pinned, again: 1.0) == ('moved', ('K1', 'K2'))
    assert asked == [({'K2': 1e-8}, True), ({'K2': 1e-8, 'K1': 1e12}, True)]
    assert rest(two, lambda pinned, again: 1.0 if pinned.keys() == {'K1'} else 2.0) == ('moved', ('K1',))
    assert asked == [({'K2': 1e-8}, True), ({'K2': 1e-8}, False), ({'K1': 1e12}, True)]
    assert rest({'K1': 1e12, 'K2': 1e-8 * 10.0**0.1}, lambda pinned, again: 1.0) == ('moved', ('K1', 'K2'))
    assert asked == [({'K1': 1e12, 'K2': 1e-8}, True)]
    # The second constant is measured against the lowest objective found: the first, put on its bound, lowered it
    # by ten resolutions, and holding the second as well would raise it by ten and a half.
    both = {'K1': 1e12 * 10.0**-0.05, 'K2': 1e-8 * 10.0**0.2}
    lowered = 1.0 - 10e-10
    assert rest(both, lambda pinned, again: lowered if pinned.keys() == {'K1'} else 1.0 + 0.5e-10) == ('moved', ('K1',))
    assert rest(both, lambda pinned, again: lowered if pinned.keys() == {'K1'} else 1.0 - 9.5e-10) == (
        'moved',
        ('K1', 'K2'),
    )


def test_the_cut_off_steps_on_the_signal_parameters_a_tested_value_pins_and_not_on_the_other_binding_constant():
    """Along the profile of Ka_HG2 above the best fit, Ka_HG runs to its bound of 1e12, where the objective is
    flat towards it. Whether the inner search lands on that bound or a millionth of a decade inside it is
    arbitrary, so it does not move the cut-off; a signal parameter pinned there does."""
    projection = _study_projection()
    fit = projection.fit()
    best = projection.fitted_parameters(fit.ka)
    assert best.ka == ('Ka_HG', 'Ka_HG2')
    cut = projection.cut_off(fit)
    readings = [projection.profile_point('Ka_HG2', ka, varpro._INNER_PER_DECADE)[2] for ka in (1.86e5, 1.87e5)]
    assert all(reading.rank == best.rank for reading in readings)
    assert {reading.ka for reading in readings} <= {('Ka_HG2',), ('Ka_HG', 'Ka_HG2')}
    assert all(cut(reading) == projection.threshold(fit) for reading in readings)
    pinned = varpro.FittedParameters(ka=best.ka, columns=best.columns[:, 1:], rank=best.rank - 1)
    assert cut(pinned) == projection.threshold(fit, released=1)


def test_the_cut_off_rises_by_one_numerator_degree_of_freedom_per_parameter_the_tested_ka_pins():
    projection = _ida(n=9, frac=0.02, seed=5)
    fit = projection.fit()
    assert projection.n_points - projection.n_params(fit) == 6
    # Upper 5 % points of F(m, 6) from a printed table, m = 1, 2, 3.
    for released, (m, f_table) in enumerate([(1, 5.987), (2, 5.143), (3, 4.757)]):
        cut = projection.threshold(fit, released=released)
        assert cut == pytest.approx(fit.objective * (1 + m * f_table / 6), rel=2e-4)
    # The joint region constrains two binding constants before anything is pinned.
    assert projection.threshold(fit, n_constrained=2, released=1) == projection.threshold(fit, released=2)


# One titration of the two-Ka weak-regime study (DBA_HG2, K1 h0 = 3, K1 / K2 = 100, 12 points,
# noise 1 % of the range): the best fit leaves every signal parameter free, and the fit at the
# true Ka_HG2 holds one on zero.
_STUDY_H0 = 2.76600857008148e-05
_STUDY_X = np.linspace(2.2485019902941192e-05, 0.0002698202388352943, 12)
_STUDY_Y = np.array(
    [15361.057416840944, 22712.52619322637, 26412.194508553486, 27993.236319842894, 28977.97973701973,
     29628.64868829678, 29954.86676714702, 30320.057542987903, 30831.151389614395, 31292.74707372996,
     31408.892195287306, 31722.487579587392]
)  # fmt: skip
_STUDY_TRUE = {'Ka_HG': 108459.53380078019, 'Ka_HG2': 1084.595338007802}


def _study_projection() -> Projection:
    assay = _assay(AssayType.DBA_HG2, _STUDY_X, _STUDY_Y, h0=Q_(_STUDY_H0, 'M'))
    return Projection(assay, dict(ASSAY_REGISTRY[AssayType.DBA_HG2].default_bounds))


def test_a_true_ka_whose_fit_pins_a_signal_parameter_is_judged_with_that_parameter_counted():
    projection = _study_projection()
    fit = projection.fit()
    dof = projection.n_points - projection.n_params(fit)
    point, at_truth, fitted = projection.profile_point('Ka_HG2', _STUDY_TRUE['Ka_HG2'], varpro._INNER_PER_DECADE)
    assert fitted.rank == projection.fitted_parameters(point).rank == projection.fitted_parameters(fit.ka).rank - 1
    assert fitted.ka == projection.fitted_parameters(fit.ka).ka == ('Ka_HG', 'Ka_HG2')
    # The rise to the true Ka_HG2 gives up two parameters, the constant and the pinned
    # coefficient. Judged as one it is rejected; judged as the two it is, it is accepted.
    one, two = (fit.objective * (1 + m * f_dist.ppf(LEVEL, m, dof) / dof) for m in (1, 2))
    assert one < at_truth < two
    assert projection.cut_off(fit)(fitted) == pytest.approx(two, rel=1e-12)
    interval = projection.interval('Ka_HG2', fit)
    assert interval.low <= _STUDY_TRUE['Ka_HG2'] <= interval.high
    # The closed edge is still where the profile crosses the cut-off of its own point.
    assert interval.open_high is False
    cut = projection.cut_off(fit)
    inside, outside = (
        projection.profile_point('Ka_HG2', interval.high * s, varpro._INNER_PER_DECADE) for s in (0.999, 1.001)
    )
    assert inside[1] <= cut(inside[2]) and outside[1] > cut(outside[2])


def test_where_the_tested_ka_pins_nothing_the_interval_is_that_of_the_constant_cut_off():
    projection = _ida(n=15, frac=0.02, seed=5)
    fit = projection.fit()
    grid = varpro._ka_grid(*projection.ka_bounds['Ka_guest'], varpro._PROFILE_PER_DECADE)
    fitted = projection.fitted_parameters(fit.ka).rank
    interval = projection.interval('Ka_guest', fit)
    # Every grid Ka the interval is cut from: the accepted ones and the two that bracket each edge.
    near = grid[(grid > interval.low / 1.3) & (grid < interval.high * 1.3)]
    assert all(projection.fitted_parameters({'Ka_guest': ka}).rank == fitted for ka in near)
    # The envelope of S(K) <= S_min (1 + F(1, n - p) / (n - p)), cut with the constant on the same grid.
    profile, threshold = projection.profile('Ka_guest'), projection.threshold(fit)
    (low, high), *_ = varpro._interval(
        lambda ka: profile(ka) - threshold, grid, np.array([profile(ka) for ka in grid]) - threshold, fit.ka['Ka_guest']
    )
    assert (interval.low, interval.high) == (low, high)


# ---------------------------------------------------------------------------
# Design effect on the cut-off
# ---------------------------------------------------------------------------


def test_a_design_effect_of_one_is_the_plain_f_test_to_the_last_bit():
    """A fit with no noise law of positive share and no addition error widens nothing, and no bit may move."""
    projection = _ida(n=15, frac=0.02, seed=5)
    fit = projection.fit()
    dof = projection.n_points - projection.n_params(fit)
    # The cut-off of the F test in its own order of operations: S_min (1 + m F / (n - p)).
    assert projection.threshold(fit, inflation=1.0) == fit.objective * (1.0 + 1 * f_dist.ppf(LEVEL, 1, dof) / dof)
    plain = projection.interval('Ka_guest', fit)
    assert projection.interval('Ka_guest', fit, inflation=1.0) == plain and plain.inflation == 1.0
    stepwise, key = _stepwise(AssayType.DBA_HG2, 1e5, 0.1, 10, _ONE_STEP[AssayType.DBA_HG2])
    fit = stepwise.fit()
    assert stepwise.one_step_p(fit, inflation=1.0) == stepwise.one_step_p(fit)
    assert stepwise.interval(key, fit, inflation=1.0) == stepwise.interval(key, fit)


def test_a_design_effect_moves_both_closed_edges_out_to_the_widened_cut_off():
    projection = _ida(n=15, frac=0.02, seed=5)
    fit = projection.fit()
    dof = projection.n_points - projection.n_params(fit)
    plain, wide = (projection.interval('Ka_guest', fit, inflation=kappa) for kappa in (1.0, 2.0))
    assert wide.inflation == 2.0
    assert wide.low < plain.low < fit.ka['Ka_guest'] < plain.high < wide.high
    assert not (wide.open_low or wide.open_high)
    # The F quantile scaled by the design effect, from scipy; no signal parameter is pinned out to these edges.
    threshold = fit.objective * (1 + 2.0 * f_dist.ppf(LEVEL, 1, dof) / dof)
    assert projection.threshold(fit, inflation=2.0) == pytest.approx(threshold, rel=1e-12)
    profile = projection.profile('Ka_guest')
    for edge in (wide.low, wide.high):
        assert profile(edge) == pytest.approx(threshold, rel=1e-6)


def test_a_design_effect_opens_a_side_only_where_its_cut_off_passes_the_profile_at_the_ka_bound():
    """In a box of 8e5 to 5e6 1/M every fit leaves both signal columns free, so the cut-off is one constant.

    The profile at the bounds lies 12 and 15 widened F quantiles above the minimum: a factor of 13.5 opens the lower
    side alone and 20 both, and each side is open exactly where the profile at its bound is under the cut-off.
    """
    projection = _ida(n=15, frac=0.02, seed=5, Ka_guest=(Q_(8e5, '1/M'), Q_(5e6, '1/M')))
    fit = projection.fit()
    dof = projection.n_points - projection.n_params(fit)
    profile = projection.profile('Ka_guest')
    at_low, at_high = profile(8e5), profile(5e6)
    sides = set()
    for kappa in (1.0, 13.5, 20.0):
        threshold = fit.objective * (1 + kappa * f_dist.ppf(LEVEL, 1, dof) / dof)
        interval = projection.interval('Ka_guest', fit, inflation=kappa)
        assert (interval.open_low, interval.open_high) == (at_low <= threshold, at_high <= threshold)
        if interval.open_low:
            assert interval.low == 8e5
        sides.add((interval.open_low, interval.open_high))
    assert sides == {(False, False), (True, False), (True, True)}


def test_a_design_effect_below_one_or_not_a_number_is_refused():
    projection = _ida(n=12)
    fit = projection.fit()
    for kappa in (0.9, np.nan, np.inf):
        with pytest.raises(ValueError, match='finite number of one or more'):
            projection.threshold(fit, inflation=kappa)


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
    second_step = KaInterval(1e-8, 2.5e6, True, False, 0.95, 6, one_step_p=0.03)
    assert KaInterval.from_dict(second_step.to_dict()) == second_step
    widened = KaInterval(1.2e6, 3.1e6, False, False, 0.95, 12, inflation=2.75)
    assert KaInterval.from_dict(widened.to_dict()) == widened
    read = KaInterval.from_dict(
        {'low': 1.0, 'high': 2.0, 'open_low': False, 'open_high': False, 'level': 0.95, 'dof': 5}
    )
    assert read == KaInterval(1.0, 2.0, False, False, 0.95, 5, one_step_p=None)
    # A results file written before intervals carried a design effect holds the plain F test's interval.
    assert read.inflation == 1.0


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
        # Only the second constant is judged by the one-step test, which the second step passes here.
        assert first.one_step_p is None and second.one_step_p < varpro.SECOND_STEP_LEVEL
        edges[top] = (first.low, second.low)
    assert np.log10(edges[1e8][0] / edges[1e10][0]) == pytest.approx(2.0, abs=0.01)
    assert edges[1e8][1] == pytest.approx(edges[1e10][1], rel=1e-6)


def test_the_interval_routine_finds_a_stretch_and_a_gap_that_lie_between_two_search_grid_nodes():
    """An excess with known roots: accepted on |t - 3| <= 0.41 and on |t - 2.4| <= 0.04, t = log10 Ka.

    The narrow stretch and the gap beside it lie between nodes of a 4-per-decade grid that the excess rejects, so
    read at the nodes alone the interval would be [10^2.59, 10^3.41] and whole.
    """

    def judge(ka: float) -> tuple[float, int]:
        t = np.log10(ka)
        return min((t - 3.0) ** 2 - 0.41**2, 50.0 * ((t - 2.4) ** 2 - 0.04**2)), 0

    nodes = varpro._ka_grid(1.0, 1e5, varpro._SEARCH_PER_DECADE)
    points = {float(ka): judge(ka) for ka in nodes.tolist()}
    interval, _ = varpro._cut_interval(judge, points, 1e3, lambda rank: 0.0, LEVEL, 7, 1.0, nodes=nodes)
    assert np.log10(interval.low) == pytest.approx(2.36, abs=2e-7)
    assert np.log10(interval.high) == pytest.approx(3.41, abs=2e-7)
    assert interval.split and not (interval.open_low or interval.open_high)


@pytest.mark.parametrize('coarse', [False, True], ids=['profile-density', 'search-nodes'])
@pytest.mark.parametrize(
    ('step', 'outer'),
    [(3.5713, 3.5913), (4.6213, 4.6413)],
    ids=['just-past-the-edge', 'beyond-a-rejected-search-cell'],
)
def test_an_accepted_stretch_that_begins_where_the_cut_off_steps_up_is_inside_the_interval(coarse, step, outer):
    """A continuous profile ``(t - 3)²`` against a cut-off that steps up at *step*, t = log10 Ka.

    Below the step the fit has rank one and the cut-off is 0.41², so the profile crosses it at t = 3.41; from the step
    on the rank is zero and the cut-off ``(outer - 3)²``, so the stretch from *step* to *outer* is accepted again, past
    a stretch the test rejects. The stretch is 0.02 decade wide, between two points of the 20-per-decade profile and
    inside a search cell whose two nodes the test rejects; the second lies more than a whole search cell beyond the
    first edge. By the definition of the interval — every Ka the test accepts — its upper edge is *outer*, and the gap
    makes it split.
    """

    cut = {1: 0.41**2, 0: (outer - 3.0) ** 2}

    def judge(ka: float) -> tuple[float, int]:
        t = np.log10(ka)
        rank = 1 if t < step else 0
        return (t - 3.0) ** 2 - cut[rank], rank

    density = varpro._SEARCH_PER_DECADE if coarse else varpro._PROFILE_PER_DECADE
    read = varpro._ka_grid(1.0, 1e6, density)
    points = {float(ka): judge(ka) for ka in read.tolist()}
    interval, _ = varpro._cut_interval(judge, points, 1e3, cut.get, LEVEL, 7, 1.0, nodes=read if coarse else None)
    assert np.log10(interval.low) == pytest.approx(2.59, abs=2e-7)
    assert np.log10(interval.high) == pytest.approx(outer, abs=2e-7)
    assert interval.split and not (interval.open_low or interval.open_high)


@pytest.mark.parametrize('coarse', [False, True], ids=['profile-density', 'search-nodes'])
def test_a_gap_between_two_accepted_points_where_the_cut_off_steps_makes_the_interval_split(coarse):
    """A continuous profile ``(t - 3)²`` against a cut-off that steps up at t = 3.43, t = log10 Ka.

    Below the step the cut-off is 0.41², so the profile crosses it at t = 3.41; from the step on it is 0.47², so the
    test accepts again up to 3.47. Of the 20-per-decade profile, 3.40 lies under the first cut-off and 3.45 under the
    second: both points read either side of the rejected stretch from 3.41 to 3.43 are accepted, and it is the step of
    the cut-off between them that rejects it. The interval runs to 3.47 and is split.
    """

    step, cut = 3.43, {1: 0.41**2, 0: 0.47**2}

    def judge(ka: float) -> tuple[float, int]:
        t = np.log10(ka)
        rank = 1 if t < step else 0
        return (t - 3.0) ** 2 - cut[rank], rank

    density = varpro._SEARCH_PER_DECADE if coarse else varpro._PROFILE_PER_DECADE
    read = varpro._ka_grid(1.0, 1e6, density)
    points = {float(ka): judge(ka) for ka in read.tolist()}
    interval, _ = varpro._cut_interval(judge, points, 1e3, cut.get, LEVEL, 7, 1.0, nodes=read if coarse else None)
    assert np.log10(interval.low) == pytest.approx(2.59, abs=2e-7)
    assert np.log10(interval.high) == pytest.approx(3.47, abs=2e-7)
    assert interval.split and not (interval.open_low or interval.open_high)


def _independent_one_ka(projection: Projection, per_decade: int = 40) -> tuple[float, float, Callable[[float], bool]]:
    """The least-squares fit of a one-Ka titration and its F test, from this function's own solves.

    ``(log10 Ka of the best fit, its residual, verdict)``: the design from the model's species, every point weighted
    by the projection's point weights, a bounded solve on norm-scaled columns (every signal parameter at or above
    zero), a coefficient fitted where it lies above 1e-8 of the signal's weighted variation in those units, the rank of
    the fitted columns by their singular values at 1e-8; the best fit from a *per_decade* scan of the whole box refined
    by bounded Brent; and ``verdict(t)`` whether ``log10 Ka = t`` lies at or under
    ``S_min (1 + F(0.95; 1, n - p) / (n - p))``, the plain F test of a model with one binding constant.
    """
    assay, root = projection.assay, np.sqrt(projection.point_weights)
    y = projection.signals[0] * root
    (key,) = projection.ka_keys
    names = [ASSAY_REGISTRY[assay.assay_type].signal_species.get(k) for k in projection.coef_keys]
    centre = np.sum(root * y) / np.sum(root**2)
    variation = float(np.sqrt(np.sum((y - root * centre) ** 2)))

    def solve(t: float) -> tuple[float, int]:
        params = np.zeros(len(assay.parameter_keys))
        params[assay.parameter_keys.index(key)] = 10.0**t
        species = assay.species(params)
        columns = np.column_stack([np.ones(y.size) if name is None else species[name] for name in names])
        columns = columns * root[:, np.newaxis]
        scaled = columns / np.linalg.norm(columns, axis=0)
        found = lsq_linear(scaled, y, bounds=(0.0, np.inf), method='bvls', tol=1e-14)
        inside = scaled[:, found.x > 1e-8 * variation]
        singular = np.linalg.svd(inside, compute_uv=False) if inside.shape[1] else np.zeros(1)
        return float(np.sum((scaled @ found.x - y) ** 2)), int(np.sum(singular > 1e-8 * singular.max()))

    low, high = np.log10(projection.ka_bounds[key])
    scan = np.linspace(low, high, int(round((high - low) * per_decade)) + 1)
    i = int(np.argmin([solve(t)[0] for t in scan]))
    best = minimize_scalar(
        lambda t: solve(t)[0], bounds=(scan[max(i - 1, 0)], scan[min(i + 1, scan.size - 1)]), method='bounded'
    ).x
    s_min, r_best = solve(best)
    dof = y.size - 1 - r_best

    def verdict(t: float) -> bool:
        return solve(t)[0] <= s_min * (1.0 + f_dist.ppf(LEVEL, 1, dof) / dof)

    return float(best), s_min, verdict


@pytest.mark.parametrize(('case', 'seed'), [('DBA_DtoH,K=0.1,n=8,noise=0.01', 32), ('GDA,K=0.1,n=8,noise=0.01', 150)])
def test_a_one_ka_interval_is_one_range_where_the_fit_pins_a_signal_parameter_past_its_edge(case, seed):
    """Past the upper edge the fit puts a signal parameter on its bound. A model with one binding constant counts
    nothing for it, so the test accepts no stretch out there: an independent plain F test, read every
    two-thousandth of a decade over half a decade beyond each edge, accepts nothing outside the interval and
    accepts the Ka just inside each edge, and the interval is not split."""
    projection = _grid_projection(case, seed)
    (key,) = projection.ka_keys
    interval = projection.interval(key, projection.fit())
    best, _, accepts = _independent_one_ka(projection)
    low, high = np.log10([interval.low, interval.high])
    assert low < best < high
    assert accepts(low + 1e-6) and accepts(high - 1e-6)
    beyond = np.concatenate([np.arange(low - 0.5, low - 1e-6, 5e-4), np.arange(high + 1e-6, high + 0.5, 5e-4)])
    assert not any(accepts(t) for t in beyond)
    fitted = projection.fitted_parameters
    assert fitted({key: 10.0 ** (high + 0.4)}).rank < fitted(projection.fit().ka).rank, (
        'a coefficient is pinned out there'
    )
    assert not interval.split


def _independent_two_ka(projection: Projection, fit, key: str, per_decade: int = 32) -> Callable[[float], bool]:
    """Whether the F test accepts ``log10 key = t`` on a stepwise titration, from this function's own solves.

    The design from the model's species, a bounded solve on norm-scaled columns (the offset, free guest and both
    complexes, every coefficient at or above zero; the free-host coefficient held at zero), the rank of the columns
    whose coefficient the solve leaves off zero. The profile at t scans the other constant at *per_decade* over its
    whole box, ends included, and refines the eight lowest local minima by bounded Brent. ``S_min`` and the rank
    ``r_best`` are this solve's at the fitted constants, ``p`` counts ``r_best`` and the fitted constants more than
    1e-7 decade inside their box, and t is accepted where the profile lies at or under
    ``S_min (1 + m F(0.95; m, n - p) / (n - p))``, ``m`` one plus how far its rank falls short of ``r_best``.
    """
    assay, y = projection.assay, projection.signals[0]
    names = [ASSAY_REGISTRY[assay.assay_type].signal_species.get(k) for k in projection.coef_keys if k != 'I_H']
    (other,) = (k for k in projection.ka_keys if k != key)
    position = {k: assay.parameter_keys.index(k) for k in projection.ka_keys}

    def solve(ka: dict) -> tuple[float, int]:
        params = np.zeros(len(assay.parameter_keys))
        for k, value in ka.items():
            params[position[k]] = value
        species = assay.species(params)
        columns = np.column_stack([np.ones(y.size) if name is None else species[name] for name in names])
        scaled = columns / np.linalg.norm(columns, axis=0)
        found = lsq_linear(scaled, y, bounds=(0.0, np.inf), method='bvls', tol=1e-14)
        inside = scaled[:, found.active_mask == 0]
        singular = np.linalg.svd(inside, compute_uv=False) if inside.shape[1] else np.zeros(1)
        return float(np.sum((scaled @ found.x - y) ** 2)), int(np.sum(singular > 1e-8 * singular.max()))

    low, high = np.log10(projection.ka_bounds[other])
    scan = np.linspace(low, high, int(round((high - low) * per_decade)) + 1)

    def profile(t: float) -> tuple[float, int]:
        def at(u: float) -> float:
            return solve({key: 10.0**t, other: 10.0**u})[0]

        values = np.array([at(u) for u in scan])
        best = int(np.argmin(values))
        u_best, s_best = scan[best], values[best]
        padded = np.pad(values, 1, constant_values=np.inf)
        minima = np.flatnonzero(values <= np.minimum(padded[:-2], padded[2:]))
        for i in minima[np.argsort(values[minima])][:8]:
            bracket = (scan[max(i - 1, 0)], scan[min(i + 1, scan.size - 1)])
            found = minimize_scalar(at, bounds=bracket, method='bounded', options={'xatol': 1e-10})
            if found.fun < s_best:
                u_best, s_best = found.x, found.fun
        return s_best, solve({key: 10.0**t, other: 10.0**u_best})[1]

    s_min, r_best = solve(fit.ka)
    inside = sum(
        min(np.log10(fit.ka[k] / lo), np.log10(hi / fit.ka[k])) > 1e-7 for k, (lo, hi) in projection.ka_bounds.items()
    )
    dof = y.size - inside - r_best

    def verdict(t: float) -> bool:
        ssr, rank = profile(t)
        m = 1 + max(0, r_best - rank)
        return ssr <= s_min * (1.0 + m * f_dist.ppf(LEVEL, m, dof) / dof)

    return verdict


@pytest.mark.parametrize(
    ('case', 'seed', 'stretch'),
    [
        ('DBA_H2G,K=1000,n=8,noise=0.01', 11, 4.64),
        ('DBA_HG2,K=10,n=8,noise=0.01', 160, -3.62),
        ('DBA_HG2,K=10,n=8,noise=0.01', 358, 0.85),
    ],
    ids=['profile-dips-where-the-rank-changes', 'rank-dips-between-nodes-of-one-rank', 'rank-dips-far-below-the-edge'],
)
def test_a_two_ka_interval_holds_a_stretch_the_test_accepts_beyond_where_the_outward_reading_stops(case, seed, stretch):
    """1:2 and 2:1 titrations of the reference-agreement grid on which the test accepts a stretch of the first
    constant a tenth of a decade wide around 10^*stretch*, between two search-grid nodes it rejects and one to two
    decades below the stretch around the estimate: where the fitted rank changes between the nodes and the profile
    dips under an unchanged cut-off, and where the rank dips by one inside a cell whose nodes share it and the
    profile there lies under the cut-off of the lower rank. An independent F test accepts the stretch and the Ka just
    inside the lower edge, and nothing over the tenth of a decade below it."""
    projection = _grid_projection(case, seed)
    fit = projection.fit()
    interval = projection.interval('Ka_HG', fit)
    accepts = _independent_two_ka(projection, fit, 'Ka_HG')
    low = np.log10(interval.low)
    assert low < stretch and interval.split
    assert accepts(stretch) and accepts(low + 1e-6)
    assert not any(accepts(t) for t in np.arange(low - 0.1, low - 1e-6, 0.01))


def test_the_other_constant_closes_an_edge_only_on_its_bound_and_where_the_objective_still_falls_towards_it():
    projection, _ = _stepwise(AssayType.DBA_HG2, 1e6, 1e5, 10, 0)
    lo, hi = projection.ka_bounds['Ka_HG2']
    asked = []

    def rise(by: float):
        def at(inside: float) -> float:
            asked.append(inside)
            return by

        return at

    # A bound is read at on_ka_bound's resolution, and the rise one search-grid step inside it.
    assert projection._bound_behind('Ka_HG', hi * 10.0**-5e-8, rise(1.0), 1.0) == 'Ka_HG2'
    assert asked == [pytest.approx(hi * 10.0 ** (-1.0 / varpro._SEARCH_PER_DECADE), rel=1e-12)]
    assert projection._bound_behind('Ka_HG', lo, rise(1.0), 1.0) == 'Ka_HG2'
    assert asked[-1] == pytest.approx(lo * 10.0 ** (1.0 / varpro._SEARCH_PER_DECADE), rel=1e-12)
    # Off the bound, or on it with an objective that no longer changes towards it, the data set the edge.
    assert projection._bound_behind('Ka_HG', hi * 10.0**-1e-6, rise(1.0), 1.0) == ''
    assert projection._bound_behind('Ka_HG', hi, rise(0.5 * varpro._BOUND_RISE), 1.0) == ''


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
# One-step test of the second binding constant
# ---------------------------------------------------------------------------

_STEPWISE_SPECIES = {AssayType.DBA_HG2: hg2_species, AssayType.DBA_H2G: h2g_species}
_STEPWISE_SIGNAL = {AssayType.DBA_HG2: hg2_signal, AssayType.DBA_H2G: h2g_signal}


def _stepwise(
    assay_type: AssayType,
    ka_hg: float,
    ka_second: float,
    equivalents: float,
    seed: int,
    *,
    n: int = 12,
    noise: float = 0.005,
    **bounds,
):
    """*n* points of guest up to *equivalents* times a 10 µM host, noise *noise* of the range, the default bounds."""
    h0 = 1e-5
    x = np.linspace(0.0, equivalents * h0, n)
    keys = ASSAY_REGISTRY[assay_type].parameter_keys
    y = _STEPWISE_SIGNAL[assay_type](
        I0=100.0, Ka_HG=ka_hg, **{keys[1]: ka_second}, I_G=1e6, I_H=0.0, I_HG=1e7, **{keys[-1]: 5e6}, h0=h0, g0_values=x
    )
    assay = _assay(assay_type, x, _homoscedastic(y, noise, seed), h0=Q_(h0, 'M'))
    return Projection(assay, {**ASSAY_REGISTRY[assay_type].default_bounds, **bounds}), keys[1]


# Titrations without a second step (K1 h0 = 1, the second constant a millionth of the first) on which the
# profile alone closes the interval of the second constant below, four to five decades above its truth.
_ONE_STEP = {AssayType.DBA_HG2: 26, AssayType.DBA_H2G: 66}


@pytest.mark.parametrize('assay_type', [AssayType.DBA_HG2, AssayType.DBA_H2G], ids=lambda t: t.name)
def test_the_second_constant_at_zero_is_the_one_step_model(assay_type):
    """No second complex forms, and the first is that of 1:1 binding, written in closed form."""
    ka, h0, x = 2e5, 1e-5, np.linspace(0.0, 1e-4, 12)
    species = _STEPWISE_SPECIES[assay_type](ka, 0.0, h0, x)
    second = 'HG2' if assay_type is AssayType.DBA_HG2 else 'H2G'
    s = h0 + x + 1.0 / ka
    assert np.array_equal(species[second], np.zeros(x.size))
    assert species['HG'] == pytest.approx(0.5 * (s - np.sqrt(s**2 - 4.0 * h0 * x)), rel=1e-9, abs=1e-20)


@pytest.mark.parametrize('assay_type', list(_ONE_STEP), ids=lambda t: t.name)
def test_without_a_second_step_the_second_constant_has_no_lower_limit(assay_type):
    projection, key = _stepwise(assay_type, 1e5, 0.1, 10, _ONE_STEP[assay_type])
    fit = projection.fit()
    interval = projection.interval(key, fit)
    assert interval.one_step_p > varpro.SECOND_STEP_LEVEL
    assert (interval.open_low, interval.low, interval.limited_by_low) == (True, 1e-8, '')
    assert interval.low <= 0.1 <= interval.high


def test_the_one_step_p_value_is_the_f_test_of_an_independent_fit_without_the_second_step():
    projection, key = _stepwise(AssayType.DBA_HG2, 1e5, 0.1, 10, _ONE_STEP[AssayType.DBA_HG2])
    fit = projection.fit()
    x, y, h0 = projection.assay.x_data.magnitude, projection.signals[0], projection.assay.h0.magnitude

    def solve(ka_hg: float, ka_hg2: float, names: tuple[str, ...]) -> tuple[float, int]:
        """Best SSR on the offset and the *names* species, every coefficient at or above zero, and how many are
        strictly above it."""
        species = hg2_species(ka_hg, ka_hg2, h0, x)
        columns = np.column_stack([np.ones(x.size), *(species[name] for name in names)])
        norm = np.linalg.norm(columns, axis=0)
        found = lsq_linear(columns / norm, y, bounds=(0.0, np.inf), method='bvls')
        return float(np.sum((columns @ (found.x / norm) - y) ** 2)), int(np.count_nonzero(found.active_mask == 0))

    two_step = solve(fit.ka['Ka_HG'], fit.ka['Ka_HG2'], ('G', 'HG', 'HG2'))
    grid = np.geomspace(1e-8, 1e12, 641)
    scan = [solve(k, 0.0, ('G', 'HG'))[0] for k in grid]
    best = int(np.argmin(scan))
    found = minimize_scalar(
        lambda t: solve(10.0**t, 0.0, ('G', 'HG'))[0],
        bounds=(np.log10(grid[max(best - 1, 0)]), np.log10(grid[min(best + 1, grid.size - 1)])),
        method='bounded',
        options={'xatol': 1e-9},
    )
    one_step = solve(10.0**found.x, 0.0, ('G', 'HG'))
    # Both constants of the fit lie inside their box, so the two fits differ by the second constant and by
    # every signal coefficient the fit without the second complex holds at zero.
    assert all(1e-8 < ka < 1e12 for ka in fit.ka.values())
    m = (2 + two_step[1]) - (1 + one_step[1])
    dof = projection.n_points - 2 - two_step[1]
    expected = f_dist.sf((one_step[0] - two_step[0]) / m / (two_step[0] / dof), m, dof)
    assert projection.one_step_p(fit) == pytest.approx(expected, rel=1e-4)


def test_raising_the_lower_bound_of_the_second_constant_leaves_the_one_step_test_where_it_is():
    seed = _ONE_STEP[AssayType.DBA_HG2]
    default, _ = _stepwise(AssayType.DBA_HG2, 1e5, 0.1, 10, seed)
    raised, _ = _stepwise(AssayType.DBA_HG2, 1e5, 0.1, 10, seed, Ka_HG2=(Q_(1e3, '1/M'), Q_(1e12, '1/M')))
    fit, fit_raised = default.fit(), raised.fit()
    assert fit_raised.objective == pytest.approx(fit.objective, rel=1e-9)
    assert raised.one_step_p(fit_raised) == pytest.approx(default.one_step_p(fit), rel=1e-6)


@pytest.mark.parametrize(
    'assay_type, ka_hg, ka_second, equivalents',
    [(AssayType.DBA_HG2, 1e6, 1e5, 10), (AssayType.DBA_H2G, 1e7, 1e6, 3)],
    ids=lambda v: v.name if isinstance(v, AssayType) else str(v),
)
def test_with_a_clear_second_step_the_lower_edge_stays_where_the_profile_crosses_its_cut_off(
    assay_type, ka_hg, ka_second, equivalents
):
    projection, key = _stepwise(assay_type, ka_hg, ka_second, equivalents, 0)
    fit = projection.fit()
    interval = projection.interval(key, fit)
    assert interval.one_step_p < 1e-3
    assert not interval.open_low
    _, value, fitted = projection.profile_point(key, interval.low, varpro._INNER_PER_DECADE)
    assert value == pytest.approx(projection.cut_off(fit)(fitted), rel=1e-6)


@pytest.mark.parametrize('assay_type', list(_ONE_STEP), ids=lambda t: t.name)
def test_with_the_first_constant_held_the_second_is_still_judged_by_the_one_step_test(assay_type):
    """Holding Ka_HG at one value leaves the profile of the second constant as shallow towards zero.

    On the H2G titration the profile alone closes the interval below, four decades above the truth of 0.1. The
    test there is two linear solves.
    """
    held = Q_(1e5, '1/M')
    projection, key = _stepwise(assay_type, 1e5, 0.1, 10, _ONE_STEP[assay_type], Ka_HG=(held, held))
    fit = projection.fit()
    x, y, h0 = projection.assay.x_data.magnitude, projection.signals[0], projection.assay.h0.magnitude
    second = key.removeprefix('Ka_')

    def solve(ka_second: float, names: tuple[str, ...]) -> tuple[float, int]:
        """Best SSR at Ka_HG = 1e5 on the offset and the *names* species, every coefficient at or above zero."""
        species = _STEPWISE_SPECIES[assay_type](1e5, ka_second, h0, x)
        columns = np.column_stack([np.ones(x.size), *(species[name] for name in names)])
        norm = np.linalg.norm(columns, axis=0)
        found = lsq_linear(columns / norm, y, bounds=(0.0, np.inf), method='bvls')
        return float(np.sum((columns @ (found.x / norm) - y) ** 2)), int(np.count_nonzero(found.active_mask == 0))

    two_step, one_step = solve(fit.ka[key], ('G', 'HG', second)), solve(0.0, ('G', 'HG'))
    # The constant itself is the one parameter the test gives up beside the coefficients the solve at zero holds
    # on a bound; the fit counts it only inside its box (on H2G it rests on the upper bound).
    m = 1 + two_step[1] - one_step[1]
    dof = projection.n_points - int(1e-8 < fit.ka[key] < 1e12) - two_step[1]
    expected = f_dist.sf((one_step[0] - two_step[0]) / m / (two_step[0] / dof), m, dof)
    interval = projection.interval(key, fit)
    assert interval.one_step_p == pytest.approx(expected, rel=1e-4)
    assert interval.one_step_p > varpro.SECOND_STEP_LEVEL
    assert (interval.open_low, interval.low) == (True, 1e-8)


def test_a_design_effect_divides_the_one_step_ratio_and_opens_the_lower_side_where_the_test_no_longer_rejects():
    """An H2G-style weak second step with the first constant held: the one-step test is two linear solves.

    At the plain F test the data reject the model without the second step at 0.005 and the interval keeps a lower
    limit; the cut-off widened by 2 widens the test with it, and the lower side opens at the bound.
    """
    held = Q_(1e5, '1/M')
    projection, key = _stepwise(AssayType.DBA_HG2, 1e5, 2e4, 10, 0, Ka_HG=(held, held))
    fit = projection.fit()
    x, y, h0 = projection.assay.x_data.magnitude, projection.signals[0], projection.assay.h0.magnitude

    def solve(ka_second: float, names: tuple[str, ...]) -> tuple[float, int]:
        species = hg2_species(1e5, ka_second, h0, x)
        columns = np.column_stack([np.ones(x.size), *(species[name] for name in names)])
        norm = np.linalg.norm(columns, axis=0)
        found = lsq_linear(columns / norm, y, bounds=(0.0, np.inf), method='bvls')
        return float(np.sum((columns @ (found.x / norm) - y) ** 2)), int(np.count_nonzero(found.active_mask == 0))

    two_step, one_step = solve(fit.ka[key], ('G', 'HG', 'HG2')), solve(0.0, ('G', 'HG'))
    assert 1e-8 < fit.ka[key] < 1e12
    m = 1 + two_step[1] - one_step[1]
    dof = projection.n_points - 1 - two_step[1]
    ratio = (one_step[0] - two_step[0]) / m / (two_step[0] / dof)
    p = {kappa: projection.one_step_p(fit, inflation=kappa) for kappa in (1.0, 2.0)}
    for kappa, value in p.items():
        assert value == pytest.approx(f_dist.sf(ratio / kappa, m, dof), rel=1e-4)
    assert p[1.0] < varpro.SECOND_STEP_LEVEL < p[2.0]
    plain, wide = (projection.interval(key, fit, inflation=kappa) for kappa in (1.0, 2.0))
    assert not plain.open_low and plain.one_step_p == p[1.0]
    assert (wide.open_low, wide.low, wide.one_step_p) == (True, 1e-8, p[2.0])


def test_a_model_without_a_free_second_step_constant_has_no_one_step_test():
    projection = _ida()
    assert projection.one_step_p(projection.fit()) is None
    held, _ = _stepwise(AssayType.DBA_HG2, 1e6, 1e5, 10, 0, Ka_HG2=(Q_(1e5, '1/M'), Q_(1e5, '1/M')))
    fit = held.fit()
    assert held.one_step_p(fit) is None and held.interval('Ka_HG', fit).one_step_p is None


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
    assert test.scatter == {}  # left out for its binding constant, not for its scatter
    assert test.p_values[0] < 0.01 / 4
    assert all(p >= 0.01 / 4 for r, p in test.p_values.items() if r != 0)
    assert test.level == 0.01


#: Datasets each rate below is read over: five replicates, twelve points, 2 % noise.
_RATE_SEEDS = range(50)


def test_two_replicates_that_share_a_shifted_ka_are_both_left_out_and_the_rest_kept():
    """Two of five replicates at three times the Ka must not drag the shared fit and push a good one out.

    A test that starts from every replicate and removes the worst one at a time
    fits the first round's shared Ka between the two groups, where a good
    replicate can look worse than the shifted pair; the clean start is the
    majority nearest the median of the replicates' own fits, which a minority
    cannot move.
    """
    both_out = good_lost = 0
    for seed in _RATE_SEEDS:
        x, rows = _replicates(12, 0.02, seed, ka_factors=(3.0, 3.0, 1.0, 1.0, 1.0))
        test = replicate_outliers(_replicate_projection(x, rows))
        both_out += {0, 1} <= set(test.excluded)
        good_lost += bool(set(test.excluded) - {0, 1})
    assert both_out >= 45
    assert good_lost <= 1


def test_every_replicate_kept_passes_the_limit_while_the_allowance_lasts():
    """The table's p-values and its used / left-out column never contradict each other.

    A replicate at twice the Ka can pass against a smaller set and fail once
    another replicate joins; admitting several in one round would keep it with a
    p-value below the limit although it could still have been left out.
    """
    for seed in _RATE_SEEDS:
        x, rows = _replicates(12, 0.02, seed, ka_factors=(2.0, 1.0, 1.0, 1.0, 1.0))
        test = replicate_outliers(_replicate_projection(x, rows))
        limit = test.level / 5
        for r, p in test.p_values.items():
            if r in test.excluded:
                assert p < limit, seed
            elif len(test.excluded) < (5 - 1) // 2:
                assert p >= limit, seed


def test_a_replicate_three_times_noisier_than_the_others_is_left_out_for_its_scatter():
    """Cochran's test at 1 %: a replicate with three times the noise enters the average at full weight otherwise."""
    out = good_lost = 0
    for seed in _RATE_SEEDS:
        x, rows = _replicates(12, 0.02, seed, noise_factors=(3.0, 1.0, 1.0, 1.0, 1.0))
        test = replicate_outliers(_replicate_projection(x, rows))
        out += 0 in test.scatter
        good_lost += bool(set(test.excluded) - {0})
        # A replicate left out for its scatter is not judged on its binding constant.
        assert set(test.scatter).isdisjoint(test.p_values)
    assert out >= 35
    assert good_lost <= 1


def test_replicates_that_share_ka_and_scatter_are_all_kept():
    """On replicates that agree, a left-out replicate is a false alarm: rare at a 1 % family-wise level."""
    alarms = 0
    for seed in _RATE_SEEDS:
        x, rows = _replicates(12, 0.02, seed, ka_factors=(1.0,) * 5)
        test = replicate_outliers(_replicate_projection(x, rows))
        assert test.tested
        alarms += bool(test.excluded)
        if not test.excluded:
            assert set(test.p_values) == set(range(5))
    assert alarms <= 2


def test_the_outcome_does_not_depend_on_the_order_of_the_replicates():
    x, rows = _replicates(12, 0.02, 3, ka_factors=(3.0, 3.0, 1.0, 1.0, 1.0))
    order = np.array([3, 0, 4, 1, 2])
    given = replicate_outliers(_replicate_projection(x, rows))
    shuffled = replicate_outliers(_replicate_projection(x, rows[order]))
    assert {int(order[r]) for r in shuffled.excluded} == set(given.excluded)
    assert {int(order[r]): p for r, p in shuffled.p_values.items()} == pytest.approx(given.p_values, rel=1e-6)


@pytest.mark.parametrize(
    ('level', 'groups', 'dof', 'table'),
    # Cochran's table (Eisenhart, Hastay & Wallis 1947, ch. 15; ISO 5725-2 Table 4 for dof 1 and 2).
    [(0.01, 4, 1, 0.9676), (0.01, 5, 2, 0.7885), (0.05, 5, 1, 0.8412), (0.01, 10, 10, 0.2704)],
)
def test_the_scatter_limit_is_cochrans_published_critical_value(level, groups, dof, table):
    assert varpro._cochran_limit(level, groups, dof) == pytest.approx(table, abs=2e-4)


def test_two_replicates_are_not_judged():
    x, rows = _replicates(12, 0.02, 30, ka_factors=(10.0, 1.0))
    test = replicate_outliers(_replicate_projection(x, rows[: REPLICATE_TEST_MIN - 1]))
    assert not test.tested and test.excluded == () and test.p_values == {}


def test_the_test_never_removes_half_of_the_replicates():
    # Two of four replicates at another Ka: a majority defines the consensus, so
    # at most one may go.
    x, rows = _replicates(20, 0.02, 40, ka_factors=(10.0, 10.0, 1.0, 1.0))
    test = replicate_outliers(_replicate_projection(x, rows))
    assert len(test.excluded) <= 1


# ---------------------------------------------------------------------------
# Weights of the titration points
# ---------------------------------------------------------------------------


def _uneven_weights(n: int, seed: int = 0, decades: float = 4.0) -> np.ndarray:
    """Weights spread log-uniformly over *decades*, both ends present."""
    w = 10.0 ** np.random.default_rng(seed).uniform(-decades / 2, decades / 2, n)
    w[0], w[-1] = 10.0 ** (-decades / 2), 10.0 ** (decades / 2)
    return w


def _noisy_hg2():
    """A noisy 1:2 titration with both binding constants free.

    The Ka box is five decades about the truth, not the registry's twenty: the
    two-constant search costs the square of the decades it covers, and what
    these tests pin — the arithmetic of the weights — is the same in any box.
    """
    x = np.linspace(0.0, 5e-5, 20)
    y = _homoscedastic(_hg2_truth_signal(x, 1e-5, 1e6, 1e5), 0.01, 6)
    box = (Q_(1e3, '1/M'), Q_(1e8, '1/M'))
    bounds = {**ASSAY_REGISTRY[AssayType.DBA_HG2].default_bounds, 'Ka_HG': box, 'Ka_HG2': box}
    return _assay(AssayType.DBA_HG2, x, y), bounds


def _same_bits(first: Projection, second: Projection) -> None:
    assert np.array_equal(first.ss_tot, second.ss_tot)
    fits = first.fit(), second.fit()
    assert fits[0].ka == fits[1].ka
    assert fits[0].objective == fits[1].objective
    assert np.array_equal(fits[0].coefficients, fits[1].coefficients)
    assert np.array_equal(fits[0].row_ssr, fits[1].row_ssr)
    assert fits[0].rank == fits[1].rank
    assert np.array_equal(first.residual(fits[0].ka), second.residual(fits[1].ka))
    assert np.array_equal(first.fitted_parameters(fits[0].ka).columns, second.fitted_parameters(fits[1].ka).columns)
    for key in first.free_ka:
        assert first.interval(key, fits[0]) == second.interval(key, fits[1]), key


def test_weights_of_one_change_no_bit_of_a_one_ka_fit_or_its_interval():
    x, y = _make_ida_data(IDA_TRUE, n_points=15)
    assay = _assay(AssayType.IDA, x, _homoscedastic(y, 0.02, 3), **_IDA_CONDITIONS)
    _same_bits(
        Projection(assay, GDA_IDA_RECOVERY_BOUNDS),
        Projection(assay, GDA_IDA_RECOVERY_BOUNDS, point_weights=np.ones(15)),
    )


def test_weights_of_one_change_no_bit_of_a_two_ka_fit_or_its_intervals():
    assay, bounds = _noisy_hg2()
    _same_bits(Projection(assay, bounds), Projection(assay, bounds, point_weights=np.ones(20)))


def test_a_weighted_solve_is_bounded_least_squares_on_the_whitened_arrays():
    """At a fixed Ka: BVLS of sqrt(w) y on sqrt(w) times the raw species columns."""
    x, y = _make_gda_data(GDA_TRUE, n_points=15)
    y = _homoscedastic(y, 0.03, 4)
    w = _uneven_weights(15, seed=1, decades=2.0)
    ka = 8e5
    bounds = {**GDA_IDA_RECOVERY_BOUNDS, 'Ka_guest': (Q_(ka, '1/M'), Q_(ka, '1/M'))}
    projection = Projection(_assay(AssayType.GDA, x, y, **_GDA_CONDITIONS), bounds, point_weights=w)
    species = gda_species(ka, GDA_TRUE['Ka_dye'], GDA_TRUE['h0'], x, GDA_TRUE['g0'])
    root = np.sqrt(w)
    columns = np.column_stack([np.ones(x.size), species['D'], species['HD']]) * root[:, None]
    lb = np.array([bounds[k][0].magnitude for k in ('I0', 'I_dye_free', 'I_dye_bound')])
    ub = np.array([bounds[k][1].magnitude for k in ('I0', 'I_dye_free', 'I_dye_bound')])
    norms = np.linalg.norm(columns, axis=0)
    independent = lsq_linear(columns / norms, root * y, bounds=(lb * norms, ub * norms), method='bvls', tol=1e-14)
    expected = independent.x / norms
    fit = projection.fit()
    assert fit.row_ssr[0] == pytest.approx(float(np.sum((columns @ expected - root * y) ** 2)), rel=1e-8)
    assert fit.objective == pytest.approx(fit.row_ssr[0], rel=1e-12)
    # Free and bound dye sum to the dye total, so only the signal is determined, not each coefficient.
    assert columns @ fit.coefficients[0] == pytest.approx(columns @ expected, rel=1e-6)
    # The total sum of squares is the residual of the weighted fit of a constant alone.
    constant = np.linalg.lstsq(root[:, None], root * y, rcond=None)[0]
    assert projection.ss_tot[0] == pytest.approx(float(np.sum((root * y - root * constant) ** 2)), rel=1e-12)
    # The weights do change the answer: this is not the unweighted residual under another name.
    unweighted = Projection(projection.assay, bounds).fit()
    assert not np.allclose(unweighted.coefficients[0], fit.coefficients[0], rtol=1e-6)


@pytest.mark.parametrize('two_ka', [False, True], ids=['one-ka', 'two-ka'])
def test_only_the_ratios_of_the_weights_matter(two_ka):
    if two_ka:
        assay, bounds = _noisy_hg2()
    else:
        x, y = _make_ida_data(IDA_TRUE, n_points=15)
        assay = _assay(AssayType.IDA, x, _homoscedastic(y, 0.02, 3), **_IDA_CONDITIONS)
        bounds = GDA_IDA_RECOVERY_BOUNDS
    w = _uneven_weights(assay.n_points, seed=2, decades=2.0)
    results = []
    for factor in (1.0, 37.5):
        projection = Projection(assay, bounds, point_weights=factor * w)
        fit = projection.fit()
        results.append((fit, {k: projection.interval(k, fit) for k in projection.free_ka}))
    (fit_a, intervals_a), (fit_b, intervals_b) = results
    assert fit_b.objective == pytest.approx(37.5 * fit_a.objective, rel=1e-6)
    for key in intervals_a:
        assert abs(np.log10(fit_b.ka[key] / fit_a.ka[key])) < 1e-6, key
        a, b = intervals_a[key], intervals_b[key]
        assert (a.open_low, a.open_high, a.split) == (b.open_low, b.open_high, b.split)
        assert abs(np.log10(b.low / a.low)) < 1e-6 and abs(np.log10(b.high / a.high)) < 1e-6, key


def test_the_residual_is_the_whitened_distance_of_the_signal_from_the_forward_model():
    x, y = _make_ida_data(IDA_TRUE, n_points=15)
    assay = _assay(AssayType.IDA, x, _homoscedastic(y, 0.02, 8), **_IDA_CONDITIONS)
    w = _uneven_weights(15, seed=3, decades=2.0)
    projection = Projection(assay, GDA_IDA_RECOVERY_BOUNDS, point_weights=w)
    fit = projection.fit()
    model = assay.forward_model(projection.params(fit)).magnitude
    expected = np.sqrt(w) * (assay.y_data.magnitude - model)
    assert projection.residual(fit.ka) == pytest.approx(expected, rel=1e-9, abs=1e-9 * np.abs(expected).max())
    assert float(np.sum(projection.residual(fit.ka) ** 2)) == pytest.approx(fit.objective, rel=1e-9)
    # Two-Ka search: the residual its refinement minimises is the same whitened one.
    assay2, bounds2 = _noisy_hg2()
    w2 = _uneven_weights(20, seed=4, decades=2.0)
    weighted = Projection(assay2, bounds2, point_weights=w2)
    fit2 = weighted.fit()
    assert float(np.sum(weighted.residual(fit2.ka) ** 2)) == pytest.approx(fit2.objective, rel=1e-9)
    # A refined optimum of the weighted objective: no grid node of the search lies below it.
    assert fit2.objective <= weighted._weighted_grid(np.ones(1)).min()


def test_ranks_are_those_of_the_unweighted_design(monkeypatch):
    t = np.linspace(0.1, 0.9, 9)
    w = _uneven_weights(9, seed=5)
    ka = {'Ka_dye': 1e5}
    # A mass balance ties free and bound dye to the offset: two directions under any weights.
    tied = np.column_stack([np.ones(9), t, 1.0 - t])
    # A falling slope is held on its bound of zero: two of three coefficients are fitted.
    powers = np.column_stack([np.ones(9), t, t**2])
    floor = {
        'I0': (Q_(-1e3, 'au'), Q_(1e3, 'au')),
        'I_dye_free': (Q_(0.0, 'au/M'), Q_(1e3, 'au/M')),
        'I_dye_bound': (Q_(0.5, 'au/M'), Q_(1e3, 'au/M')),
    }
    cases = [(tied, 5 + 2 * t + 7 * (1 - t), {}, 2, 2), (powers, 2 - 0.2 * t + 3 * t**2, floor, 3, 2)]
    for design, y, bounds, rank, fitted_rank in cases:
        readings = []
        for weights in (None, w):
            assay = _assay(AssayType.DBA_HtoD, np.linspace(1e-6, 2e-5, 9), y)
            limits = {**ASSAY_REGISTRY[AssayType.DBA_HtoD].default_bounds, **bounds}
            projection = Projection(assay, limits, point_weights=weights)
            monkeypatch.setattr(projection, '_design', lambda ka, assay=None, design=design: design)
            fit = projection.fit()
            readings.append((fit.rank, projection.fitted_parameters(ka).rank, projection.degenerate_keys(fit)))
            # The fitted columns are those of the whitened residual, one per fitted coefficient.
            columns = projection.fitted_parameters(ka).columns
            inside = (fit.coefficients[0] - projection._lb > 1e-6) & (projection._ub - fit.coefficients[0] > 1e-6)
            assert np.array_equal(columns, (design * np.sqrt(projection.point_weights)[:, None])[:, inside])
        assert readings[0] == readings[1]
        assert readings[0][:2] == (rank, fitted_rank)


def test_a_point_the_weights_call_imprecise_steers_ka_less():
    # Noise-free IDA data whose brightest point is displaced by 15 % of itself. Counted like the
    # others it drags Ka; counted at a hundredth it barely does.
    x, y = _make_ida_data(IDA_TRUE, n_points=15)
    top = int(np.argmax(y))
    y = y.copy()
    y[top] *= 1.15
    assay = _assay(AssayType.IDA, x, y, **_IDA_CONDITIONS)
    w = np.ones(15)
    w[top] = 1e-2
    truth = np.log10(IDA_TRUE['Ka_guest'])
    equal = abs(np.log10(Projection(assay, GDA_IDA_RECOVERY_BOUNDS).fit().ka['Ka_guest']) - truth)
    weighted = abs(np.log10(Projection(assay, GDA_IDA_RECOVERY_BOUNDS, point_weights=w).fit().ka['Ka_guest']) - truth)
    assert equal > 0.01
    assert weighted < 0.2 * equal


@pytest.mark.parametrize(
    'bad',
    [np.ones(14), np.ones((1, 15))] + [np.r_[np.ones(14), last] for last in (np.nan, np.inf, 0.0, -1.0)],
    ids=['too-few', 'two-dimensional', 'nan', 'infinite', 'zero', 'negative'],
)
def test_point_weights_that_are_not_one_positive_number_per_point_are_refused(bad):
    x, y = _make_ida_data(IDA_TRUE, n_points=15)
    assay = _assay(AssayType.IDA, x, y, **_IDA_CONDITIONS)
    with pytest.raises(ValueError, match='point weights'):
        Projection(assay, GDA_IDA_RECOVERY_BOUNDS, point_weights=bad)


@pytest.mark.parametrize('seed', [0, 1, 2])
def test_with_point_weights_a_replicate_that_needs_another_ka_is_still_excluded(seed):
    x, rows = _replicates(20, 0.02, seed, ka_factors=(1.0, 1.0, 10.0, 1.0))
    mean = rows.mean(axis=0)
    # The weights of noise half constant, half proportional to the signal.
    w = 1.0 / (0.5 + 0.5 * mean**2 / np.mean(mean**2))
    assay = _assay(AssayType.IDA, x, mean, **_IDA_CONDITIONS)
    projection = Projection(assay, ASSAY_REGISTRY[AssayType.IDA].default_bounds, signals=rows, point_weights=w)
    test = replicate_outliers(projection)
    assert test.tested
    assert test.excluded == (2,)
