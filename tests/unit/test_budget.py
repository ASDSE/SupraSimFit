"""The absolute Ka uncertainty budget (``core.pipeline.budget``), on functions whose answers are known.

No fit of data is made here: every run's refits are replaced by a function of
the offsets, and every what-if is asked of a result built without a run.

- A run whose refits are replaced by a function of the offsets with known
  elasticities: the budget's rows, the elasticity of a shared source as the sum
  over its inputs — a binding constant measured with the shared stock counted
  with the opposite sign — and the additions as one item.
- ``what_if`` against the exact variance of an additive function, by the formula
  and by re-weighting, and where it must decline.
- ``homogeneity_sum`` and the tolerance the run holds it to.
"""

import math
from types import SimpleNamespace

import numpy as np
import pytest

import core.pipeline.sensitivity as sens
from core.assays.ida import IDAAssay
from core.data_processing.measurement_set import MeasurementSet
from core.pipeline.budget import Budget, BudgetRow, homogeneity_sum, homogeneity_tolerance, what_if
from core.pipeline.fit_pipeline import FitConfig
from core.pipeline.inputs import ADDITIONS, TITRANT, AdditionError, ErrorModel, InputSpec, SharedSource, shared_key
from core.pipeline.sensitivity import (
    SensitivityConfig,
    SensitivityMode,
    SensitivityResult,
    run_sensitivity,
    sobol_indices_with_ci,
    sobol_jobs,
)
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


def test_the_elasticity_of_a_stock_behind_a_concentration_and_a_binding_constant_is_their_difference(
    ida_setup, monkeypatch
):
    """``Ka ∝ (1 + e)^2`` through [Host]0 and ``(1 + e)^(-0.7)`` through Ka(dye) measured with the same stock.

    The stock moves [Host]0 by ``1 + e`` and Ka(dye) by ``1 / (1 + e)``, so Ka
    moves by ``(1 + e)^(2 + 0.7)``: the source's elasticity is ``2 - (-0.7)``.
    """
    powers = {'h0': 2.0, 'Ka_dye': -0.7}

    def fit(ms, assay_cls, x_base, base_conditions, offsets, fit_config, *_):
        log_ka = 8.0 + sum(p * math.log10(1 + offsets.get(key, 0.0)) for key, p in powers.items())
        return {'Ka_guest': 10.0**log_ka, **dict.fromkeys(('I0', 'I_dye_free', 'I_dye_bound'), 0.0)}, 1.0, 1.0

    monkeypatch.setattr(sens, '_fit_perturbed', fit)
    monkeypatch.setattr(sens, '_SOBOL_BLOCKS', 2)
    monkeypatch.setattr(sens, '_SOBOL_SAMPLE_SIZES', (4,))
    ms, assay_cls, conditions, fit_config = ida_setup
    stock = SharedSource('Host stock', 4.0, ('h0', 'Ka_dye'))
    cfg = SensitivityConfig(SensitivityMode.SOBOL, 4, ErrorModel(shared=(stock,)), seed=6)

    result = run_sensitivity(ms, assay_cls, conditions, fit_config, cfg, max_workers=1)

    (row,) = result.budget['Ka_guest'].rows
    assert row.elasticity == pytest.approx(2.7, abs=1e-6)
    # Each sample's Ka is the power law of the source's own offset, exponent 2.7.
    e = result.sample_offsets_pct[shared_key(stock.name)] / 100
    np.testing.assert_allclose(np.log10(result.sample_ka['Ka_guest']), 8.0 + 2.7 * np.log10(1 + e), rtol=1e-12)


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


# -- the identity ---------------------------------------------------------------------------


def test_the_tolerance_on_the_identity_is_a_few_refit_resolutions():
    """Ten times the slope error two refits resolved to ``_LOG_KA_XTOL`` leave, per input.

    Well above what identified fits miss by (at most 6e-4 over the six binding
    assays) and far below what a flat or jumping refit misses by (0.8 and more).
    """
    per_slope = 2 * 1e-7 * np.log(10) / (np.log1p(1e-3) - np.log1p(-1e-3))
    assert homogeneity_tolerance(4) == pytest.approx(10 * 4 * per_slope, rel=1e-12)
    assert 6e-4 < homogeneity_tolerance(2) < homogeneity_tolerance(4) < 0.8


def test_homogeneity_sum_counts_an_entered_binding_constant_against_the_concentrations():
    """IDA: s_h0 + s_d0 + s_titrant - s_Kadye; the designer's measured elasticities add up to -1."""
    kinds = {'Ka_dye': 'binding_constant', 'h0': 'concentration', 'd0': 'concentration', TITRANT: 'titrant'}
    elasticity = {'Ka_dye': 0.9458, 'h0': 2.9274, 'd0': 0.9508, TITRANT: -3.9324}

    assert homogeneity_sum(elasticity, kinds) == pytest.approx(-1.0, abs=1e-3)
    # The sign of a term is the input's kind, not its key: counting [Host]₀ as a
    # binding constant subtracts what it added, twice its elasticity below.
    as_constant = homogeneity_sum(elasticity, {**kinds, 'h0': 'binding_constant'})
    assert as_constant == pytest.approx(homogeneity_sum(elasticity, kinds) - 2 * elasticity['h0'], abs=1e-12)
