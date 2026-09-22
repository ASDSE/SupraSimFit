"""The absolute Ka uncertainty budget, on functions whose answers are known; no fit of data is made here.

- The estimator (``sobol_indices_with_ci``) on a linear-additive Gaussian
  function, whose variance, explained variances and spreads-if-exact are sums of
  squares, and on the Ishigami function with inputs 1 and 3 reported as one
  group, whose first-order and total index are both ``1 - S_2``.
- The job builder (``sobol_jobs``): own sources reproduce ``spec_fraction``
  column by column, a shared source moves every input it loads, and the
  additions add one column per titration point, reported as one item and
  sampled at ``sigma / sqrt(replicates)``.
- A run whose refits are replaced by a function of the offsets with known
  elasticities: the budget's rows, the elasticity of a shared source as the sum
  over its inputs, the additions as one item.
- ``what_if`` against the exact variance of an additive function, by the formula
  and by re-weighting, and where it must decline.
- ``homogeneity_sum`` and the fit count of a run with every kind of source.
"""

import math
from types import SimpleNamespace

import numpy as np
import pytest
from scipy.stats import norm

import core.pipeline.sensitivity as sens
from core.assays.ida import IDAAssay
from core.data_processing.measurement_set import MeasurementSet
from core.pipeline.fit_pipeline import FitConfig
from core.pipeline.inputs import ADDITIONS, TITRANT, AdditionError, ErrorModel, InputSpec, SharedSource, shared_key
from core.pipeline.sensitivity import (
    Budget,
    BudgetRow,
    SensitivityConfig,
    SensitivityMode,
    SensitivityResult,
    estimated_fit_count,
    homogeneity_sum,
    nominal_value,
    run_sensitivity,
    sobol_design,
    sobol_indices_with_ci,
    sobol_jobs,
    spec_fraction,
    what_if,
)
from core.pipeline.varpro import FitRefused
from core.units import Q_
from tests.conftest import GDA_IDA_RECOVERY_BOUNDS, IDA_TRUE, _make_ida_data

_BLOCKS = sens._SOBOL_BLOCKS
_N = 2048

_IDA_CONDITIONS = {
    'Ka_dye': Q_(IDA_TRUE['Ka_dye'], '1/M'),
    'h0': Q_(IDA_TRUE['h0'], 'M'),
    'd0': Q_(IDA_TRUE['d0'], 'M'),
}
_STOCK = SharedSource('Host and dye stock', 4.0, ('h0', 'd0'))


def _outputs(function, n_columns: int, groups: list[list[int]], seed: int):
    """``(f_A, f_B, [f_AB_g])`` of *function* on a design, ``AB_g`` being A with the columns of g from B."""
    a_points, b_points = sobol_design(_N, n_columns, _BLOCKS, seed)
    mixed = []
    for group in groups:
        points = a_points.copy()
        points[:, group] = b_points[:, group]
        mixed.append(function(points))
    return function(a_points), function(b_points), mixed


# -- the estimator ---------------------------------------------------------------------


def test_budget_of_a_linear_gaussian_function_is_its_sum_of_squares():
    """``Y = sum a_i z_i`` with standard normal ``z``: V = sum a_i², V_i = a_i², SD without i = sqrt(V - a_i²)."""
    a = np.array([0.08, 0.05, 0.02])
    estimate = sobol_indices_with_ci(
        *_outputs(lambda points: 3.0 + norm.ppf(points) @ a, 3, [[0], [1], [2]], seed=11), _BLOCKS
    )

    variance = float(np.sum(a**2))
    assert estimate.variance == pytest.approx(variance, rel=0.03)
    np.testing.assert_allclose(estimate.source_variance, a**2, rtol=0.05, atol=0.02 * variance)
    np.testing.assert_allclose(estimate.sd_if_exact, np.sqrt(variance - a**2), rtol=0.03)
    np.testing.assert_allclose(estimate.s1, a**2 / variance, atol=0.02)
    np.testing.assert_allclose(estimate.st, a**2 / variance, atol=0.02)
    # Every interval is around its own estimate and no wider than the quantity is known to a tenth of the variance.
    for value, interval in (
        (estimate.variance, np.array([estimate.variance_ci])),
        (estimate.source_variance, estimate.source_variance_ci),
        (estimate.sd_if_exact, estimate.sd_if_exact_ci),
    ):
        assert np.all(interval[:, 0] < value) and np.all(value < interval[:, 1])
    assert np.all(np.diff(estimate.source_variance_ci, axis=1) < 0.1 * variance)


def test_a_group_of_columns_is_reported_as_one_item():
    """Ishigami inputs 1 and 3 interact with each other and not with input 2.

    The closed first-order index of the group {1, 3} is everything input 2 does
    not explain alone, and so is its total index: both are ``1 - S_2``, while
    the single first-order indices of 1 and 3 add up to less (their interaction
    is inside the group). ``S_2 = (a²/8) / V`` in closed form.
    """
    a, b = 7.0, 0.1

    def ishigami(points):
        x = np.pi * (2.0 * points - 1.0)
        return np.sin(x[:, 0]) + a * np.sin(x[:, 1]) ** 2 + b * x[:, 2] ** 4 * np.sin(x[:, 0])

    variance = a**2 / 8 + b * np.pi**4 / 5 + b**2 * np.pi**8 / 18 + 0.5
    s2 = (a**2 / 8) / variance
    estimate = sobol_indices_with_ci(*_outputs(ishigami, 3, [[1], [0, 2]], seed=5), _BLOCKS)

    assert estimate.variance == pytest.approx(variance, rel=0.03)
    np.testing.assert_allclose(estimate.s1, [s2, 1 - s2], atol=0.03)
    np.testing.assert_allclose(estimate.st, [s2, 1 - s2], atol=0.03)
    assert estimate.source_variance[1] == pytest.approx((1 - s2) * variance, rel=0.05)


# -- the job builder -------------------------------------------------------------------


def _quantiles(points: np.ndarray) -> np.ndarray:
    return np.clip(points, sens._QUANTILE_EPS, 1 - sens._QUANTILE_EPS)


def test_own_sources_are_mapped_column_by_column_in_the_order_stated():
    """Without a shared source a job is ``spec_fraction`` of its design row, float for float, and carries no deltas."""
    specs = {
        'h0': InputSpec.sigma_pct(5.0),
        'Ka_dye': InputSpec.sigma_pct(0.0),  # stated, does not vary: no column
        TITRANT: InputSpec.interval_pct(-8.0, 4.0),
        'd0': InputSpec.sigma_abs(2e-7),
    }
    built = sobol_jobs(ErrorModel(specs=specs), _IDA_CONDITIONS, 16, 20, 1, seed=13)

    varying = ['h0', TITRANT, 'd0']
    a_points, b_points = sobol_design(16, 3, _BLOCKS, 13)
    matrices = [a_points, b_points]
    for column in range(3):
        mixed = a_points.copy()
        mixed[:, column] = b_points[:, column]
        matrices.append(mixed)
    expected = [
        {
            key: spec_fraction(specs[key], nominal_value(key, _IDA_CONDITIONS), key, float(q))
            for key, q in zip(varying, row)
        }
        for row in _quantiles(np.vstack(matrices))
    ]
    assert built.sources == tuple(varying)
    assert [offsets for offsets, _ in built.jobs] == expected
    assert built.source_offsets == expected
    assert all(deltas is None for _, deltas in built.jobs)


def test_a_shared_source_moves_every_input_it_loads():
    errors = ErrorModel(specs={'h0': InputSpec.sigma_pct(3.0), TITRANT: InputSpec.sigma_pct(2.0)}, shared=(_STOCK,))
    built = sobol_jobs(errors, _IDA_CONDITIONS, 1024, 20, 1, seed=2)

    stock = shared_key(_STOCK.name)
    assert built.sources == ('h0', TITRANT, stock)
    assert len(built.jobs) == 1024 * (3 + 2)
    for e, (offsets, _) in zip(built.source_offsets, built.jobs):
        assert set(e) == {'h0', TITRANT, stock} and set(offsets) == {'h0', 'd0', TITRANT}
        # The perturbed inputs by hand: entered x prod(1 + e) over the sources that move each.
        assert 1 + offsets['h0'] == pytest.approx((1 + e['h0']) * (1 + e[stock]), rel=1e-15)
        assert offsets['d0'] == e[stock]
        assert offsets[TITRANT] == e[TITRANT]
    # The shared column is the 4 % normal it was stated as: the A and B rows have that spread.
    shared = np.array([e[stock] for e in built.source_offsets[:2048]])
    assert np.std(shared) == pytest.approx(0.04, rel=0.02)


@pytest.mark.parametrize('n_replicates', [1, 4])
def test_the_additions_are_one_item_of_one_column_per_point(n_replicates):
    """Sources + n_points columns; ``ADDITIONS`` last; deltas at sigma / sqrt(replicates).

    In the matrix of the additions every delta comes from ``B`` and every
    single source from ``A``; in a single source's matrix the deltas are A's.
    """
    n_points, n_base, sigma = 12, 1024, 2.0
    errors = ErrorModel(specs={'h0': InputSpec.sigma_pct(3.0)}, additions=AdditionError(sigma, sequential=True))
    designs = []
    real = sens.sobol_design

    def spy(*args, **kwargs):
        designs.append(real(*args, **kwargs))
        return designs[-1]

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(sens, 'sobol_design', spy)
        built = sobol_jobs(errors, _IDA_CONDITIONS, n_base, n_points, n_replicates, seed=3)

    ((a_points, _),) = designs
    assert a_points.shape == (n_base, 1 + n_points)
    assert built.sources == ('h0', ADDITIONS)
    assert len(built.jobs) == n_base * (2 + 2)
    deltas = np.array([d for _, d in built.jobs])
    assert deltas.shape == (4 * n_base, n_points)
    assert np.std(deltas[: 2 * n_base]) == pytest.approx(sigma / 100 / math.sqrt(n_replicates), rel=0.02)
    h0 = np.array([offsets['h0'] for offsets, _ in built.jobs])
    in_a, in_b, in_ab_h0, in_ab_additions = (slice(i * n_base, (i + 1) * n_base) for i in range(4))
    np.testing.assert_array_equal(h0[in_ab_h0], h0[in_b])
    np.testing.assert_array_equal(deltas[in_ab_h0], deltas[in_a])
    np.testing.assert_array_equal(h0[in_ab_additions], h0[in_a])
    np.testing.assert_array_equal(deltas[in_ab_additions], deltas[in_b])


# -- a run with known elasticities -------------------------------------------------------


@pytest.fixture
def ida_setup():
    x, y = _make_ida_data(IDA_TRUE, n_points=20)
    ms = MeasurementSet(concentrations=x, signals=y.reshape(1, -1), replica_ids=('r0',))
    return ms, IDAAssay, dict(_IDA_CONDITIONS), FitConfig(custom_bounds=GDA_IDA_RECOVERY_BOUNDS)


_POWERS = {'h0': 2.0, 'd0': -3.0, TITRANT: 0.5}


def _power_law_fit(ms, assay_cls, x_base, base_conditions, offsets, fit_config, deltas=None, *_):
    """``Ka = 1e8 x prod (1 + offset_j)^p_j x 10^(3 x mean delta)``: elasticities ``p_j``, exactly."""
    log_ka = 8.0 + sum(p * math.log10(1 + offsets.get(key, 0.0)) for key, p in _POWERS.items())
    if deltas is not None:
        log_ka += 3.0 * float(np.sum(deltas)) / math.sqrt(len(deltas))
    return {'Ka_guest': 10.0**log_ka, **dict.fromkeys(('I0', 'I_dye_free', 'I_dye_bound'), 0.0)}, 1.0, 1.0


def test_budget_rows_of_a_run_with_known_elasticities(ida_setup, monkeypatch):
    """Own, shared and addition sources of a power law in the inputs.

    ``log10 Ka`` is additive in the sources, so each row's variance is the
    variance of its own term: ``(p ln(1 + e) / ln 10)²`` averaged, which for a
    small sigma is ``(p sigma / ln 10)²``; the shared source moves h0 and d0
    together, so its power is ``2 - 3 = -1`` and that is its elasticity; the
    additions contribute ``9 sigma²`` and have no elasticity.
    """
    monkeypatch.setattr(sens, '_fit_perturbed', _power_law_fit)
    ms, assay_cls, conditions, fit_config = ida_setup
    errors = ErrorModel(
        specs={'h0': InputSpec.sigma_pct(3.0), TITRANT: InputSpec.sigma_pct(2.0)},
        shared=(_STOCK,),
        additions=AdditionError(1.0, sequential=False),
    )
    cfg = SensitivityConfig(SensitivityMode.SOBOL, 1024, errors, seed=6)
    reports = []

    result = run_sensitivity(
        ms, assay_cls, conditions, fit_config, cfg, max_workers=1, progress=lambda *report: reports.append(report)
    )

    stock = shared_key(_STOCK.name)
    assert result.sources == ('h0', TITRANT, stock, ADDITIONS)
    assert result.source_inputs == {'h0': ('h0',), TITRANT: (TITRANT,), stock: ('h0', 'd0'), ADDITIONS: (TITRANT,)}
    assert set(result.sample_offsets_pct) == {'h0', TITRANT, stock}
    assert result.n_planned == result.n_total == 1024 * (4 + 2) + 2 * 4
    assert reports[-1] == (result.n_planned + 1, result.n_planned + 1) and len(reports) == result.n_planned + 1

    assert result.elasticity['Ka_guest'] == pytest.approx({'Ka_dye': 0.0, **_POWERS}, abs=1e-9)
    budget = result.budget['Ka_guest']
    rows = {row.source: row for row in budget.rows}
    assert [row.source for row in budget.rows] == list(result.sources)
    assert {key: row.elasticity for key, row in rows.items()} == pytest.approx(
        {'h0': 2.0, TITRANT: 0.5, stock: -1.0, ADDITIONS: None}, abs=1e-9
    )
    ln10 = math.log(10)
    expected = {
        'h0': (2.0 * 0.03 / ln10) ** 2,
        TITRANT: (0.5 * 0.02 / ln10) ** 2,
        stock: (1.0 * 0.04 / ln10) ** 2,
        ADDITIONS: 9 * 0.01**2,
    }
    total = sum(expected.values())
    assert budget.variance == pytest.approx(total, rel=0.03)
    assert budget.sd == pytest.approx(math.sqrt(total), rel=0.015)
    # The function has no interaction; what is left is the sampling error of four first-order indices.
    half_widths = [np.diff(result.sobol_s1_ci['Ka_guest'][key])[0] / 2 for key in result.sources]
    assert abs(budget.interactions) < sum(half_widths)
    for key, variance in expected.items():
        # A first-order variance at N = 1024 is known to about a tenth of the total; its own interval says how well.
        low, high = rows[key].variance_ci
        assert high - low < 0.2 * total
        assert abs(rows[key].variance - variance) < 0.75 * (high - low)
        assert rows[key].sd_if_exact == pytest.approx(math.sqrt(total - variance), rel=0.03)
        # No interaction: the total index is the same share (the Jansen estimator is the sharper of the two).
        assert result.sobol_st['Ka_guest'][key] == pytest.approx(variance / total, abs=0.03)


def test_sequential_additions_on_a_falling_series_are_refused_before_any_fit(ida_setup, monkeypatch):
    ms, assay_cls, conditions, fit_config = ida_setup
    x = np.array(ms.concentrations)
    x[[4, 5]] = x[[5, 4]]
    falling = MeasurementSet(concentrations=x, signals=ms.signals, replica_ids=ms.replica_ids)
    monkeypatch.setattr(sens, 'fit_measurement_set', lambda *a, **k: pytest.fail('no fit may run'))
    errors = ErrorModel(additions=AdditionError(1.0, sequential=True))

    with pytest.raises(FitRefused, match='falls at point 6'):
        run_sensitivity(
            falling, assay_cls, conditions, fit_config, SensitivityConfig(SensitivityMode.SOBOL, 1024, errors)
        )


def test_a_heatmap_needs_an_input_with_an_uncertainty_of_its_own(ida_setup):
    """Shared sources and the additions are sampled by the Sobol analysis only; a heatmap of them alone sweeps nothing."""
    ms, assay_cls, conditions, fit_config = ida_setup
    cfg = SensitivityConfig(SensitivityMode.HEATMAP, 1, ErrorModel(shared=(_STOCK,)), x_key='h0', y_key='d0', n_steps=3)

    with pytest.raises(FitRefused, match='uncertainty of its own'):
        run_sensitivity(ms, assay_cls, conditions, fit_config, cfg, max_workers=1)


# -- what-if ---------------------------------------------------------------------------


def _additive_result(
    specs: dict[str, InputSpec], slopes: dict[str, float], conditions=None, mixed_without_fit: int | None = None
) -> SensitivityResult:
    """A SOBOL result of ``log10 Ka = 8 + sum slope_i e_i`` over *specs*, built without a run.

    *mixed_without_fit* is a design row whose first mixed sample gave no fit,
    which the estimators drop everywhere while its A and B samples keep a Ka of
    their own.
    """
    errors = ErrorModel(specs=specs)
    built = sobol_jobs(errors, conditions or _IDA_CONDITIONS, _N, 20, 1, seed=21)
    log_ka = np.array([8.0 + sum(slopes[key] * e[key] for key in slopes) for e in built.source_offsets])
    by_matrix = log_ka.reshape(len(specs) + 2, _N)
    if mixed_without_fit is not None:
        by_matrix[2, mixed_without_fit] = np.nan
    usable = np.all(np.isfinite(by_matrix), axis=0)
    estimate = sobol_indices_with_ci(by_matrix[0], by_matrix[1], by_matrix[2:], _BLOCKS)
    rows = tuple(
        BudgetRow(
            source,
            float(estimate.source_variance[i]),
            tuple(estimate.source_variance_ci[i]),
            float(estimate.sd_if_exact[i]),
            tuple(estimate.sd_if_exact_ci[i]),
            None,
        )
        for i, source in enumerate(built.sources)
    )
    return SensitivityResult(
        mode=SensitivityMode.SOBOL,
        assay_type='IDA',
        ka_keys=('Ka_guest',),
        baseline_ka={'Ka_guest': 1e8},
        x_offsets_pct=None,
        y_offsets_pct=None,
        ka_grid=None,
        n_success=len(log_ka),
        n_total=len(log_ka),
        config=SensitivityConfig(SensitivityMode.SOBOL, _N, errors, seed=21),
        seed_used=21,
        sample_offsets_pct={
            key: 100 * np.array([e[key] for e in built.source_offsets[: 2 * _N]]) for key in built.sources
        },
        sample_ka={'Ka_guest': 10.0 ** log_ka[: 2 * _N]},
        sample_usable={'Ka_guest': np.tile(usable, 2)},
        baseline_fit=SimpleNamespace(conditions=conditions or _IDA_CONDITIONS),
        budget={'Ka_guest': Budget(estimate.variance, estimate.variance_ci, rows)},
        sources=built.sources,
    )


_SLOPES = {'h0': 1.5, TITRANT: -1.0}
_SIGMAS = {'h0': 0.05, TITRANT: 0.03}


@pytest.fixture(scope='module')
def gaussian_result():
    return _additive_result({key: InputSpec.sigma_pct(100 * s) for key, s in _SIGMAS.items()}, _SLOPES)


@pytest.mark.parametrize('ratio', [1.0, 0.5, 0.2])
def test_what_if_matches_the_exact_variance_of_an_additive_function(gaussian_result, ratio):
    """Exact: ``sqrt(V - V_i (1 - r²))`` with ``V_i = (slope_i sigma_i)²``; formula and re-weighting within 3 %."""
    parts = {key: (_SLOPES[key] * _SIGMAS[key]) ** 2 for key in _SLOPES}
    exact = math.sqrt(sum(parts.values()) - parts['h0'] * (1 - ratio**2))

    answer = what_if(gaussian_result, 'Ka_guest', 'h0', ratio)

    assert answer.sd == pytest.approx(exact, rel=0.03)
    assert answer.sd_reweighted == pytest.approx(exact, rel=0.03)
    # For a normal source the weights have E[w²] = 1 / (r² sqrt(2/r² - 1)), which sets the effective size.
    expected_size = 2 * _N * ratio**2 * math.sqrt(2 / ratio**2 - 1)
    assert answer.effective_samples == pytest.approx(expected_size, rel=0.15)
    # h0 is the larger item as stated (0.075 against 0.03) and stops being it below r = 0.4.
    assert answer.largest_after == ('h0' if ratio > 0.4 else TITRANT)


def test_what_if_declines_the_cross_check_it_cannot_support(gaussian_result):
    """Below 200 effective samples, and for an exact source, only the formula answers."""
    narrow = what_if(gaussian_result, 'Ka_guest', 'h0', 0.01)
    assert narrow.sd_reweighted is None and narrow.effective_samples < 200
    assert narrow.sd == pytest.approx(abs(_SLOPES[TITRANT]) * _SIGMAS[TITRANT], rel=0.03)

    exact = what_if(gaussian_result, 'Ka_guest', 'h0', 0.0)
    assert exact.sd_reweighted is None and exact.effective_samples is None
    row = next(row for row in gaussian_result.budget['Ka_guest'].rows if row.source == 'h0')
    assert exact.sd == pytest.approx(row.sd_if_exact, rel=1e-12)


@pytest.mark.parametrize('ratio', [-0.1, 1.5, math.nan])
def test_what_if_takes_improvements_only(gaussian_result, ratio):
    with pytest.raises(ValueError, match='between 0 and 1'):
        what_if(gaussian_result, 'Ka_guest', 'h0', ratio)


def test_what_if_of_a_range_shrinks_it_about_its_centre():
    """A uniform source of half-width h has variance h²/3; shrunk to r it has (r h)²/3, about the same centre."""
    result = _additive_result(
        {'h0': InputSpec.interval_pct(-4.0, 10.0), TITRANT: InputSpec.sigma_pct(2.0)}, {'h0': 1.0, TITRANT: 1.0}
    )
    exact = math.sqrt((0.5 * 0.07) ** 2 / 3 + 0.02**2)

    answer = what_if(result, 'Ka_guest', 'h0', 0.5)

    assert answer.sd == pytest.approx(exact, rel=0.03)
    assert answer.sd_reweighted == pytest.approx(exact, rel=0.03)
    assert answer.effective_samples == pytest.approx(0.5 * 2 * _N, rel=0.05)


def test_what_if_measures_an_absolute_uncertainty_against_the_entered_value():
    """A sigma in the input's own unit is the same source as that sigma in percent of the value the fit was given."""
    h0 = IDA_TRUE['h0']
    absolute = _additive_result({'h0': InputSpec.sigma_abs(0.05 * h0), TITRANT: InputSpec.sigma_pct(3.0)}, _SLOPES)
    relative = _additive_result({'h0': InputSpec.sigma_pct(5.0), TITRANT: InputSpec.sigma_pct(3.0)}, _SLOPES)

    assert what_if(absolute, 'Ka_guest', 'h0', 0.5).sd_reweighted == pytest.approx(
        what_if(relative, 'Ka_guest', 'h0', 0.5).sd_reweighted, rel=1e-9
    )


def test_what_if_answers_over_the_rows_the_budget_was_built_from():
    """A design row the estimators dropped is out of the cross-check too, or the two describe different samples.

    At the stated uncertainty every weight is 1, so the re-weighted variance is
    the plain variance of the rows it runs over: it equals the budget's variance
    exactly when both are the rows the estimators could use, and misses it by
    the dropped row otherwise.
    """
    result = _additive_result(
        {key: InputSpec.sigma_pct(100 * s) for key, s in _SIGMAS.items()}, _SLOPES, mixed_without_fit=3
    )
    budget = result.budget['Ka_guest']

    answer = what_if(result, 'Ka_guest', 'h0', 1.0)

    assert result.sample_usable['Ka_guest'].sum() == 2 * (_N - 1)
    assert answer.sd_reweighted == pytest.approx(budget.sd, rel=1e-12)


def test_what_if_never_reweights_the_additions(gaussian_result):
    """One weight per titration point multiplies into no effective sample, so the additions get the formula alone."""
    budget = gaussian_result.budget['Ka_guest']
    additions = BudgetRow(ADDITIONS, 4e-4, (3e-4, 5e-4), 0.0, (0.0, 0.0), None)
    with_additions = SensitivityResult(
        **{
            **vars(gaussian_result),
            'budget': {'Ka_guest': Budget(budget.variance + 4e-4, budget.variance_ci, (*budget.rows, additions))},
            'sources': (*gaussian_result.sources, ADDITIONS),
        }
    )

    answer = what_if(with_additions, 'Ka_guest', ADDITIONS, 0.5)

    assert answer.sd_reweighted is None and answer.effective_samples is None
    assert answer.sd == pytest.approx(math.sqrt(budget.variance + 4e-4 * 0.25), rel=1e-12)


# -- the identity and the cost -----------------------------------------------------------


def test_homogeneity_sum_counts_an_entered_binding_constant_against_the_concentrations():
    """IDA: s_h0 + s_d0 + s_titrant - s_Kadye; the designer's measured elasticities add up to -1."""
    kinds = {'Ka_dye': 'binding_constant', 'h0': 'concentration', 'd0': 'concentration', TITRANT: 'titrant'}
    elasticity = {'Ka_dye': 0.9458, 'h0': 2.9274, 'd0': 0.9508, TITRANT: -3.9324}

    assert homogeneity_sum(elasticity, kinds) == pytest.approx(-1.0, abs=1e-3)
    # The sign of a term is the input's kind, not its key: counting [Host]₀ as a
    # binding constant subtracts what it added, twice its elasticity below.
    as_constant = homogeneity_sum(elasticity, {**kinds, 'h0': 'binding_constant'})
    assert as_constant == pytest.approx(homogeneity_sum(elasticity, kinds) - 2 * elasticity['h0'], abs=1e-12)


def test_fit_count_is_one_matrix_per_reported_item_plus_the_elasticity_refits():
    """Three single sources and the additions are four items whatever the number of points: N (4 + 2) + 2 x 4."""
    errors = ErrorModel(
        specs={'h0': InputSpec.sigma_pct(3.0), 'd0': InputSpec.sigma_pct(0.0), TITRANT: InputSpec.sigma_pct(2.0)},
        shared=(_STOCK,),
        additions=AdditionError(1.0, sequential=True),
    )
    assert estimated_fit_count(SensitivityConfig(SensitivityMode.SOBOL, 1024, errors), 4) == 1024 * 6 + 8
