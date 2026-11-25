"""The factor the interval of each Ka is widened by: the design effect of the noise law and the addition errors.

- With no law of positive share and no stated additions every factor is
  exactly 1.0, without a single solve: the cut-off multiplies by 1.0 and the
  interval is the profile's own to the last bit.
- The additions part against an independent computation of the closed form
  ``(σ²_PM c_kk + e'MGM'e) / (σ̂² c_kk)``: the addition loading by central
  differences of the perturbed series through the forward model, the
  Paule-Mandel root on the null space of the Jacobian's transpose by a dense
  solve, the estimator from the full Jacobian with
  the Ka's column taken by index. The law part against the sandwich
  ``(M D M')_kk / (σ̄² c_kk)`` of that same full Jacobian, the largest over the
  accepted shares.
- Two binding constants: each gets the factor of its own column, and the joint
  factor is the mean eigenvalue ``tr(A⁻¹V)/2``, which lies between the smallest
  and the largest generalised eigenvalue of ``(V, A)`` — the range that also
  holds each Ka's own factor before its floor at 1.
- What a factor answers to: never below 1, larger for a larger stated error of
  the additions and for a wider set of accepted shares, and the replicates of
  separate titrations average the additions as ``σ/√m`` while repeated reads of
  one titration do not.
- Coverage: sequential 3 % additions on a direct-binding titration with 0.2 %
  noise, where the profile alone covers about half the time.
- What else the stated additions reach: the reference of the conflict
  statistic, which reads the same shifts against a wider null; and the
  replicate test of separate titrations, whose Cochran step compares each
  replicate's residual with its own addition residue taken out — exactly the
  residual where there is none, and against a dense solve of the root pooled
  over every replicate's residual space where there is — and which, with both
  steps corrected, stops leaving out replicates that agree.
"""

from dataclasses import replace

import numpy as np
import pytest
from scipy.linalg import null_space
from scipy.optimize import brentq

from core.assays import ASSAY_CLASSES
from core.assays.base import TITRANT
from core.assays.registry import AssayType
from core.models.equilibrium import dba_signal, hg2_signal
from core.pipeline.fit_pipeline import FitConfig, _replicate_additions, fit_assay
from core.pipeline.inflation import addition_signal_loading, inflation, joint_inflation, replicate_scatter_ssr
from core.pipeline.inputs import AdditionError, ErrorModel, InputSpec, perturb_titrant
from core.pipeline.noise import NoiseBasis, NoiseLaw
from core.pipeline.varpro import Projection, replicate_outliers
from core.units import Q_

_N = 12
_CONC = 1e-5  # the dye of a host-into-dye titration, M
_KA = 10.0 / _CONC  # Ka * [dye] = 10: the curve bends inside the titration
_X = np.linspace(10.0 * _CONC / _N, 10.0 * _CONC, _N)
_SEQUENTIAL = AdditionError(3.0, sequential=True)


def _dba_signal(x, conc=_CONC):
    return dba_signal(I0=0.0, Ka_dye=_KA, I_dye_free=1e7, I_dye_bound=5e7, x_titrant=x, y_fixed=conc, mode='HtoD')


def _dba(seed, additions=0.03, noise=0.002, stock=None):
    """A host-into-dye titration whose additions (sequential, relative SD *additions*) went wrong, entered as planned."""
    rng = np.random.default_rng(seed)
    true_x = perturb_titrant(_X, additions * rng.standard_normal(_N), True, stock)
    conc = _CONC if stock is None else _CONC * (1.0 - true_x / stock)
    clean = _dba_signal(true_x, conc)
    y = clean + noise * np.ptp(clean) * rng.standard_normal(_N)
    dilution = {} if stock is None else {'titrant_stock': Q_(stock, 'M')}
    assay = ASSAY_CLASSES[AssayType.DBA_HtoD](
        x_data=Q_(_X, 'M'), y_data=Q_(y, 'au'), fixed_conc=Q_(_CONC, 'M'), mode='HtoD', **dilution
    )
    return Projection(assay, assay.get_default_bounds())


def _hg2(seed):
    """A stepwise 1:2 titration with sequential 3 % additions: two binding constants a decade apart."""
    rng = np.random.default_rng(seed)
    h0, x = 1e-5, np.linspace(2e-6, 6e-5, 14)
    true_x = perturb_titrant(x, 0.03 * rng.standard_normal(x.size), True, None)
    clean = hg2_signal(I0=0.0, Ka_HG=1e6, Ka_HG2=1e5, I_G=1e5, I_H=0.0, I_HG=1e7, I_HG2=3e7, h0=h0, g0_values=true_x)
    y = clean + 0.003 * np.ptp(clean) * rng.standard_normal(x.size)
    assay = ASSAY_CLASSES[AssayType.DBA_HG2](x_data=Q_(x, 'M'), y_data=Q_(y, 'au'), h0=Q_(h0, 'M'))
    return Projection(assay, assay.get_default_bounds())


def _law(signal, share, share_set):
    """A noise law of positive share read off replicates, scaled to the rms of *signal*."""
    reference = float(np.sqrt(np.mean(signal**2)))
    u_floor = float(np.min(signal**2) / reference**2)
    return NoiseLaw(NoiseBasis.REPLICATES, share, 1.0, 0.01, reference, 3, u_floor, share_set)


# -- the independent closed forms ---------------------------------------------------


def _jacobian(projection, fit):
    """The whitened ``[C | K]`` through the forward model: inside-bound signal columns, then d f / d log10 Ka."""
    assay, keys = projection.assay, projection.assay.parameter_keys
    params = projection.params(fit)
    step = 1e-4
    ka_columns = []
    for key in projection.free_ka:
        up, down = params.copy(), params.copy()
        up[keys.index(key)] *= 10**step
        down[keys.index(key)] /= 10**step
        change = assay.forward_model(up).magnitude - assay.forward_model(down).magnitude
        ka_columns.append(np.sqrt(projection.point_weights) * change / (2 * step))
    signal = projection.fitted_parameters(fit.ka).columns
    return np.column_stack([signal, *ka_columns]), signal.shape[1]


def _addition_covariance(projection, fit, sigma, sequential):
    """``W^½ H H' W^½ σ²`` with H the central differences of the fitted signal under each addition's error."""
    assay, params = projection.assay, projection.params(fit)
    x = assay.x_data.magnitude
    stock = None if assay.titrant_stock is None else assay.titrant_stock.magnitude
    h = 1e-6

    def signal(deltas):
        moved = replace(assay, x_data=Q_(perturb_titrant(x, deltas, sequential, stock), 'M'))
        return moved.forward_model(params).magnitude

    loading = np.column_stack([(signal(h * e) - signal(-h * e)) / (2 * h) for e in np.eye(x.size)])
    whitened = np.sqrt(projection.point_weights)[:, None] * loading
    return sigma**2 * whitened @ whitened.T, loading


def _residual_space_root(jacobian, residual, added, variance):
    """The noise variance beside *added* read on the residual space, dense, within ``[1e-12 σ̂², σ̂²]``.

    The root of ``(Q'r)'(σ² I + Q'GQ)⁻¹ Q'r = n - p``, ``Q`` an orthonormal
    basis of the null space of the Jacobian's transpose.
    """
    rest = null_space(jacobian.T)
    projected, covariance = rest.T @ residual, rest.T @ added @ rest
    dof = rest.shape[1]

    def excess(s2):
        return projected @ np.linalg.solve(s2 * np.eye(dof) + covariance, projected) - dof

    if excess(1e-12 * variance) <= 0:
        return 1e-12 * variance
    return brentq(excess, 1e-12 * variance, variance, xtol=1e-14 * variance)


def _closed_forms(projection, fit, sigma=None, sequential=True, shapes=()):
    """Each free Ka's additions factor ``(σ²_PM c + e'MGM'e)/(σ̂² c)`` and law factors ``(M D M')/(σ̄² c)``."""
    jacobian, n_signal = _jacobian(projection, fit)
    jacobian = jacobian / np.linalg.norm(jacobian, axis=0)
    inverse = np.linalg.pinv(jacobian.T @ jacobian)
    estimator = inverse @ jacobian.T
    n = jacobian.shape[0]
    p = np.linalg.matrix_rank(jacobian)
    residual = np.sqrt(projection.point_weights) * (
        projection.signals[0] - projection._design(fit.ka) @ fit.coefficients[0]
    )
    variance = residual @ residual / (n - p)
    leverage = np.diag(jacobian @ inverse @ jacobian.T)
    out = {}
    for j, key in enumerate(projection.free_ka):
        e = np.zeros(jacobian.shape[1])
        e[n_signal + j] = 1.0
        c = e @ inverse @ e
        found = {}
        if sigma is not None:
            added, _ = _addition_covariance(projection, fit, sigma, sequential)
            pm = _residual_space_root(jacobian, residual, added, variance)
            found['additions'] = (pm * c + e @ estimator @ added @ estimator.T @ e) / (variance * c)
        found['law'] = [
            (e @ estimator @ np.diag(d) @ estimator.T @ e) / (np.sum((1 - leverage) * d) / (n - p) * c) for d in shapes
        ]
        out[key] = found
    return out


# -- exactly one where nothing is stated ---------------------------------------------


def test_with_nothing_stated_every_factor_is_exactly_one_and_nothing_is_solved(monkeypatch):
    projection = _dba(0)
    fit = projection.fit()

    def no_solve(*_, **__):
        raise AssertionError('the factor solved the model although nothing was stated')

    monkeypatch.setattr(projection, '_design', no_solve)
    constant = NoiseLaw(NoiseBasis.REPLICATES, 0.0, 1.0, 0.0, 1.0, 3, 0.1, (0.0, 0.4))
    single = NoiseLaw(NoiseBasis.SINGLE_TITRATION)
    for law in (None, constant, single):
        found = inflation(projection, fit, law=law)
        assert found == {'Ka_dye': 1.0} and type(found['Ka_dye']) is float
        assert joint_inflation(projection, fit, law=law) == 1.0


# -- the closed forms ----------------------------------------------------------------


@pytest.mark.parametrize('sequential', [True, False], ids=['sequential', 'separate'])
def test_the_additions_factor_is_the_closed_form_design_effect(sequential):
    projection = _dba(1)
    fit = projection.fit()
    found = inflation(projection, fit, additions=AdditionError(3.0, sequential))['Ka_dye']
    expected = _closed_forms(projection, fit, sigma=0.03, sequential=sequential)['Ka_dye']['additions']
    assert expected > 2.0  # the additions dominate: the floor at 1 is not what is compared
    assert found == pytest.approx(expected, rel=1e-6)


def test_the_addition_loading_follows_the_series_through_a_stock_and_moved_inputs():
    stock = 20.0 * _CONC
    projection = _dba(2, stock=stock)
    fit = projection.fit()
    offsets = {TITRANT: 0.02}
    found = addition_signal_loading(projection, fit.ka, offsets, _SEQUENTIAL, stock * 1.02)

    # The same titration entered at the moved inputs, its loading by central differences of the forward model.
    entered = projection.assay.with_inputs(offsets)
    at_offsets = Projection(entered, projection.assay.get_default_bounds())
    refit = replace(fit, coefficients=at_offsets._solve(at_offsets._design(fit.ka))[1])
    _, expected = _addition_covariance(at_offsets, refit, 0.03, True)
    assert found == pytest.approx(expected, rel=1e-4, abs=1e-6 * np.abs(expected).max())


def test_the_law_factor_is_the_largest_sandwich_over_the_accepted_shares():
    projection = _dba(3, additions=0.0, noise=0.01)
    fit = projection.fit()
    signal = projection.signals[0]
    law = _law(signal, 0.4, (0.3, 0.6))
    shares = np.round(np.arange(0.3, 0.6 + 1e-9, 0.01), 12)
    shapes = [law.relative_variance(signal, s) / law.relative_variance(signal) for s in shares]
    expected = max(1.0, max(_closed_forms(projection, fit, shapes=shapes)['Ka_dye']['law']))
    assert inflation(projection, fit, law=law)['Ka_dye'] == pytest.approx(expected, rel=1e-6)


def test_at_the_estimated_share_alone_the_law_adds_nothing_to_the_additions():
    """``D = 1`` at the share the weights were built from, so the composed meat is the additions' alone."""
    projection = _dba(4)
    fit = projection.fit()
    law = _law(projection.signals[0], 0.5, (0.5, 0.5))
    both = inflation(projection, fit, law=law, additions=_SEQUENTIAL)
    assert both['Ka_dye'] == pytest.approx(inflation(projection, fit, additions=_SEQUENTIAL)['Ka_dye'], rel=1e-12)


# -- two binding constants ------------------------------------------------------------


def test_each_of_two_binding_constants_gets_the_factor_of_its_own_column():
    projection = _hg2(5)
    fit = projection.fit()
    found = inflation(projection, fit, additions=_SEQUENTIAL)
    expected = _closed_forms(projection, fit, sigma=0.03)
    assert set(found) == {'Ka_HG', 'Ka_HG2'}
    for key in found:
        assert found[key] == pytest.approx(expected[key]['additions'], rel=1e-6)
    # The two factors differ, so a factor read off the other constant's column would fail above.
    assert abs(np.log(found['Ka_HG'] / found['Ka_HG2'])) > 0.1

    # With the first constant pinned, the second is the only free one and keeps its own factor's form.
    bounds = projection.assay.get_default_bounds()
    bounds['Ka_HG'] = (Q_(fit.ka['Ka_HG'], '1/M'), Q_(fit.ka['Ka_HG'], '1/M'))
    pinned = Projection(projection.assay, bounds)
    pinned_fit = pinned.fit()
    alone = inflation(pinned, pinned_fit, additions=_SEQUENTIAL)
    assert set(alone) == {'Ka_HG2'}
    assert alone['Ka_HG2'] == pytest.approx(
        _closed_forms(pinned, pinned_fit, sigma=0.03)['Ka_HG2']['additions'], rel=1e-6
    )


def test_the_joint_factor_is_the_mean_eigenvalue_and_lies_in_the_range_of_the_per_ka_factors():
    projection = _hg2(5)
    fit = projection.fit()
    joint = joint_inflation(projection, fit, additions=_SEQUENTIAL)
    per_ka = inflation(projection, fit, additions=_SEQUENTIAL)

    jacobian, n_signal = _jacobian(projection, fit)
    jacobian = jacobian / np.linalg.norm(jacobian, axis=0)
    inverse = np.linalg.pinv(jacobian.T @ jacobian)
    estimator = inverse @ jacobian.T
    n, p = jacobian.shape[0], np.linalg.matrix_rank(jacobian)
    added, _ = _addition_covariance(projection, fit, 0.03, True)
    residual = np.sqrt(projection.point_weights) * (
        projection.signals[0] - projection._design(fit.ka) @ fit.coefficients[0]
    )
    variance = residual @ residual / (n - p)
    pm = _residual_space_root(jacobian, residual, added, variance)
    block = slice(n_signal, n_signal + 2)
    model = variance * inverse[block, block]
    sandwich = (estimator @ (pm * np.eye(n) + added) @ estimator.T)[block, block]
    eigenvalues = np.linalg.eigvals(np.linalg.solve(model, sandwich)).real

    assert joint == pytest.approx(eigenvalues.mean(), rel=1e-5)
    assert eigenvalues.min() * (1 - 1e-9) <= joint <= eigenvalues.max() * (1 + 1e-9)
    for value in per_ka.values():
        assert eigenvalues.min() * (1 - 1e-9) <= value <= eigenvalues.max() * (1 + 1e-9)
    # One free binding constant has no joint region.
    assert joint_inflation(_dba(0), _dba(0).fit(), additions=_SEQUENTIAL) == 1.0


# -- what a factor answers to ---------------------------------------------------------


def test_a_factor_grows_with_the_stated_error_of_the_additions():
    projection = _dba(6, additions=0.005)
    fit = projection.fit()
    factors = [inflation(projection, fit, additions=AdditionError(s, True))['Ka_dye'] for s in (1e-4, 0.5, 1, 2, 4)]
    assert factors[0] == pytest.approx(1.0, abs=1e-6)  # a negligible error changes next to nothing
    assert all(a <= b for a, b in zip(factors, factors[1:])) and factors[-1] > 2.0


def test_a_factor_is_never_below_one():
    """Shares on one side of the estimate make the sandwich smaller than the profile assumes; the factor stays 1."""
    projection = _dba(9, additions=0.0, noise=0.01)
    fit = projection.fit()
    signal = projection.signals[0]
    below, above = (inflation(projection, fit, law=_law(signal, 0.5, s))['Ka_dye'] for s in ((0.0, 0.5), (0.5, 1.0)))
    assert min(below, above) == pytest.approx(1.0, abs=1e-12)
    assert min(below, above) >= 1.0 and max(below, above) > 1.01


def test_a_factor_grows_with_the_set_of_shares_the_replicates_accept():
    projection = _dba(7, additions=0.0, noise=0.01)
    fit = projection.fit()
    signal = projection.signals[0]
    sets = [(0.5, 0.5), (0.4, 0.6), (0.2, 0.8), (0.0, 1.0)]
    factors = [inflation(projection, fit, law=_law(signal, 0.5, s))['Ka_dye'] for s in sets]
    assert all(f >= 1.0 for f in factors)
    assert all(a <= b for a, b in zip(factors, factors[1:])) and factors[-1] > factors[0]


def test_separate_titrations_average_the_additions_and_repeated_reads_do_not():
    projection = _dba(8)
    fit = projection.fit()
    separate = inflation(projection, fit, additions=AdditionError(3.0, True), n_replicates=4)['Ka_dye']
    reads = inflation(projection, fit, additions=AdditionError(3.0, True, separate_titrations=False), n_replicates=4)[
        'Ka_dye'
    ]
    assert separate == pytest.approx(inflation(projection, fit, additions=AdditionError(1.5, True))['Ka_dye'], rel=1e-9)
    assert reads == pytest.approx(inflation(projection, fit, additions=AdditionError(3.0, True))['Ka_dye'], rel=1e-12)
    assert reads > separate


# -- coverage ------------------------------------------------------------------------


def test_the_widened_interval_covers_the_true_ka_under_sequential_addition_errors():
    """100 titrations with 3 % sequential additions and 0.2 % noise: the profile alone covers about half."""
    covered = plain = 0
    for seed in range(100):
        projection = _dba(1000 + seed)
        fit = projection.fit()
        kappa = inflation(projection, fit, additions=_SEQUENTIAL)['Ka_dye']
        widened = projection.interval('Ka_dye', fit, inflation=kappa)
        profile = projection.interval('Ka_dye', fit)
        covered += widened.low <= _KA <= widened.high
        plain += profile.low <= _KA <= profile.high
    assert plain <= 70  # the profile alone does undercover here: the check has something to fix
    assert covered >= 90


# -- what else the additions reach ----------------------------------------------------


def test_stated_additions_widen_the_reference_of_the_conflict_statistic_and_leave_the_statistic_alone():
    """The same fit of the same inputs: the shifts are the same, the null they are read against is wider."""
    specs = {'fixed_conc': InputSpec.sigma_pct(3.0), TITRANT: InputSpec.sigma_pct(3.0)}
    compared = 0
    for seed in range(6):
        assay = _dba(2000 + seed).assay
        plain = fit_assay(assay, FitConfig(errors=ErrorModel(specs=specs))).diagnostics.conflict
        stated = fit_assay(assay, FitConfig(errors=ErrorModel(specs=specs, additions=_SEQUENTIAL))).diagnostics.conflict
        if plain is None:
            continue
        compared += 1
        assert stated.q == pytest.approx(plain.q, rel=1e-9)
        assert stated.weights == pytest.approx(plain.weights, rel=1e-9)
        assert stated.p_value >= plain.p_value
    assert compared >= 3


def _separate_titrations(seed, m=4):
    """*m* host-into-dye titrations, each with its own 3 % sequential addition errors, and their own fits."""
    rng = np.random.default_rng(seed)
    rows = []
    for _ in range(m):
        clean = _dba_signal(perturb_titrant(_X, 0.03 * rng.standard_normal(_N), True, None))
        rows.append(clean + 0.005 * np.ptp(clean) * rng.standard_normal(_N))
    rows = np.array(rows)
    assay = ASSAY_CLASSES[AssayType.DBA_HtoD](
        x_data=Q_(_X, 'M'), y_data=Q_(rows.mean(axis=0), 'au'), fixed_conc=Q_(_CONC, 'M'), mode='HtoD'
    )
    bounds = assay.get_default_bounds()
    projection = Projection(assay, bounds, signals=rows)
    return projection, bounds, [projection.fit(np.eye(m)[r]) for r in range(m)]


def _alone(projection, own):
    """Every replicate's single-row projection and its own fit."""
    return [
        (
            Projection(projection.assay, projection.assay.get_default_bounds(), signals=projection.signals[r : r + 1]),
            replace(
                fit,
                coefficients=fit.coefficients[r : r + 1],
                row_ssr=fit.row_ssr[r : r + 1],
                objective=float(fit.row_ssr[r]),
            ),
        )
        for r, fit in enumerate(own)
    ]


def test_without_addition_errors_the_scatter_cochran_compares_is_each_replicates_own_residual():
    projection, _, own = _separate_titrations(5)
    found = replicate_scatter_ssr(_alone(projection, own), AdditionError(0.0, sequential=True))
    assert found == pytest.approx([float(fit.row_ssr[r]) for r, fit in enumerate(own)], rel=1e-9)


def test_with_addition_errors_cochran_compares_each_residual_on_its_residual_space_at_the_pooled_root():
    """``σ² t_r`` with ``σ²`` the root of ``sum_r t_r(σ²) = sum_r (n - p_r)``, every part by a dense solve."""
    projection, _, own = _separate_titrations(5)
    alone = _alone(projection, own)
    parts = []
    for single, fit in alone:
        jacobian, _ = _jacobian(single, fit)
        jacobian = jacobian / np.linalg.norm(jacobian, axis=0)
        residual = np.sqrt(single.point_weights) * (single.signals[0] - single._design(fit.ka) @ fit.coefficients[0])
        added, _ = _addition_covariance(single, fit, 0.03, True)
        rest = null_space(jacobian.T)
        parts.append((rest.T @ residual, rest.T @ added @ rest, residual @ residual / rest.shape[1]))
    dof = sum(projected.size for projected, _, _ in parts)

    def form(s2, projected, covariance):
        return projected @ np.linalg.solve(s2 * np.eye(projected.size) + covariance, projected)

    low, high = min(v for _, _, v in parts), max(v for _, _, v in parts)
    root = brentq(lambda s2: sum(form(s2, q, c) for q, c, _ in parts) - dof, 1e-12 * low, high, xtol=1e-14 * low)
    found = replicate_scatter_ssr(alone, _SEQUENTIAL)
    assert found != pytest.approx([float(fit.row_ssr[r]) for r, fit in enumerate(own)], rel=1e-2)
    assert found == pytest.approx([root * form(root, q, c) for q, c, _ in parts], rel=1e-6)


def test_the_replicate_test_keeps_separate_titrations_whose_own_additions_move_them_apart():
    """60 sets of four separate titrations measured alike, 3 % sequential additions each, stated.

    A test that knows only the residual noise leaves a good replicate out of
    one set in five; with the design effect and the addition residue taken
    into account, it leaves out as many as it does without addition errors,
    about one set in a hundred.
    """
    plain = carried = 0
    for seed in range(60):
        projection, bounds, own = _separate_titrations(seed)
        kappa, scatter = _replicate_additions(projection, bounds, own, _SEQUENTIAL, None)
        assert len(kappa) == len(scatter) == 4 and min(kappa) >= 1.0
        plain += bool(replicate_outliers(projection, own).excluded)
        carried += bool(replicate_outliers(projection, own, inflation=kappa, scatter_ssr=scatter).excluded)
    assert plain >= 6
    assert carried <= 1
    # Repeated reads of one titration share their additions: nothing to correct.
    assert _replicate_additions(projection, bounds, own, replace(_SEQUENTIAL, separate_titrations=False), None) == (
        None,
        None,
    )
