"""Misfit tests, the conflict statistic and the verdict — against hand-computed references.

- the runs test has the binomial distribution of sign changes when nothing is
  fitted, the hand-derived distribution for three residuals about a fitted
  offset, and its stated level on a fitted curve; drawn in chunks, its
  reference is the one drawn at once, to the last bit;
- the lack-of-fit F is the hand-computed ratio on a 2 x 4 toy, weighted and
  unweighted, and it fires on replicates that differ by a scale and a
  background where the raw spread between them hides the misfit entirely;
  replicates with no scatter above the resolution of a fit are not tested;
- with weights read off the same replicates, its p-value comes from a
  parametric bootstrap that holds the 5 % level on a linear model where the F
  tail rejects twice as often, repeats exactly on the same data, still rejects
  a gross misfit, and does not depend on tied or rescaled design columns;
- the weights of the conflict reference are g / (1 + g) for the information g
  the data hold on an input: 1 for an input the data determine, 0 for one the
  residual does not depend on; they do not depend on the units a parameter's
  column is measured in;
- the conflict p-value has its two analytic limits (chi-squared where the data
  determine the inputs, a scaled beta where they say nothing) and, on a linear
  Gaussian model fitted the same way, rejects a consistent fit at the stated
  rate with few points, where a reference that takes the noise scale as known
  rejects twice as often;
- the verdict judges the misfit test and the conflict statistic together by
  Holm's procedure, names both when both reject, and a results file records
  which test was not run and why.
"""

import json

import numpy as np
import pytest
from scipy.optimize import minimize
from scipy.stats import beta, binom, chi2
from scipy.stats import f as f_dist

from core.pipeline.diagnostics import (
    LOF_BOOTSTRAP_DRAWS,
    Conflict,
    FitDiagnostics,
    InputShift,
    MisfitTest,
    Verdict,
    conflict_p_value,
    conflict_reference,
    conflict_test,
    lack_of_fit,
    no_scatter,
    runs_test,
    verdict,
)
from core.pipeline.noise import NoiseBasis, NoiseLaw, noise_law


def test_runs_test_of_unfitted_residuals_is_the_binomial_distribution_of_sign_changes():
    """Nothing fitted: the signs are fair coins, so runs - 1 is Binomial(n - 1, 1/2); the p-value is its mid-p."""
    n = 9
    x = np.arange(float(n))
    nothing_fitted = np.empty((n, 0))
    for signs, runs in (('++++-----', 2), ('++--++--+', 5), ('+-+-+-+-+', 9)):
        residuals = np.array([1.5 if s == '+' else -0.5 for s in signs])
        found = runs_test(residuals, x, nothing_fitted)
        assert (found.kind, found.statistic, found.dof, found.reference) == ('runs', runs, None, 'simulated')
        mid_p = binom.cdf(runs - 2, n - 1, 0.5) + 0.5 * binom.pmf(runs - 1, n - 1, 0.5)
        assert found.p_value == pytest.approx(mid_p, abs=3e-3)
        assert found.expected == pytest.approx(1 + (n - 1) / 2, abs=0.02)


def test_runs_test_knows_that_a_fitted_offset_makes_the_signs_alternate():
    """Three residuals about their fitted mean sum to zero, so one has the opposite sign of the other two and
    is the largest. The three are exchangeable, so it is the middle one — three runs — one time in three, and
    no ordering has a single run. Over all orderings of two signs and one, three runs would be as rare."""
    x = np.arange(3.0)
    offset = np.ones((3, 1))
    two, three = runs_test([1.0, 1.0, -2.0], x, offset), runs_test([1.0, -2.0, 1.0], x, offset)
    assert two.p_value == pytest.approx(0.5 * 2 / 3, abs=3e-3)
    assert three.p_value == pytest.approx(2 / 3 + 0.5 / 3, abs=3e-3)
    assert two.expected == three.expected == pytest.approx(7 / 3, abs=0.01)


def test_runs_test_holds_its_level_on_a_fitted_curve_and_sees_a_systematic_deviation():
    """A parabola fitted to 12 points, 500 seeded datasets.

    The number of runs takes few values, so the mid-p test of one design has a size near the level and not
    at it: 0.071 here (400 000 draws of the residuals this fit leaves of noise), which 500 datasets place
    between 0.048 and 0.093.
    A deviation of three noise standard deviations that the parabola cannot follow is rejected in most.
    """
    rng = np.random.default_rng(3)
    t = np.linspace(0.0, 1.0, 12)
    columns = np.column_stack([np.ones(12), t, t**2])
    leaves = np.eye(12) - columns @ np.linalg.pinv(columns)

    def rejection(misfit: np.ndarray) -> float:
        p = [
            runs_test(leaves @ (misfit + rng.standard_normal(12)), t, columns, draws=5_000).p_value for _ in range(500)
        ]
        return float(np.mean(np.array(p) < 0.05))

    assert 0.048 <= rejection(np.zeros(12)) <= 0.093
    assert rejection(3.0 * np.sin(2 * np.pi * t)) > 0.6


def test_runs_test_orders_by_x_leaves_out_zeros_and_carries_penalty_rows():
    x = np.array([3.0, 1.0, 2.0, 0.0, 4.0])
    residuals = np.array([-1.0, 1.0, 0.0, 1.0, -1.0])  # along x: + + 0 - -
    rng = np.random.default_rng(0)
    jacobian = np.vstack([rng.normal(size=(5, 2)), np.eye(2)])  # two inputs held by a penalty row each
    found = runs_test(residuals, x, jacobian)
    assert found.statistic == 2
    order = np.argsort(x)
    ordered = runs_test(residuals[order], x[order], np.vstack([jacobian[:5][order], jacobian[5:]]))
    assert (found.p_value, found.expected) == (ordered.p_value, ordered.expected)
    with pytest.raises(ValueError, match='needs 5 or more rows'):
        runs_test(residuals, x, jacobian[:4])


def test_the_runs_reference_drawn_in_chunks_is_the_reference_drawn_at_once():
    """The reference is read chunk by chunk to keep its memory bounded; the p-value is the same number.

    Written out here the way one draw of the whole reference computes it: the
    residuals the linearised fit leaves of standard normal noise, their runs,
    and the mid-p against the observed runs. 300 points and 3 000 000 numbers
    need several chunks.
    """
    rng = np.random.default_rng(7)
    n = 300
    x = np.linspace(0.0, 1.0, n)
    jacobian = np.column_stack([np.ones(n), x, x**2])
    residuals = np.sin(9 * x) + 0.3 * rng.standard_normal(n)
    found = runs_test(residuals, x, jacobian, draws=10_000, seed=3)

    u = np.linalg.svd(jacobian / np.linalg.norm(jacobian, axis=0), full_matrices=False)[0]
    e = np.random.default_rng(3).standard_normal((10_000, n))
    signs = np.sign(e - (e @ u) @ u.T)
    null = 1 + np.sum(signs[:, 1:] != signs[:, :-1], axis=1)
    observed = 1 + int(np.sum(np.sign(residuals[1:]) != np.sign(residuals[:-1])))
    assert found.statistic == observed
    assert found.p_value == float(np.mean(null < observed) + 0.5 * np.mean(null == observed))
    assert found.expected == float(null.mean())


def test_lack_of_fit_is_the_hand_computed_f_on_a_two_by_four_toy():
    """Two replicates about the mean curve 0, 1, 2, 3, which is a straight line in the point index.

    Their difference from the mean, d = (1, -1, -1, 1), has zero sum and zero
    slope against that line, so the line each replicate is detrended against is
    the mean curve itself and the scatter is d: SS = 2 * 4 = 8 on
    (m - 1)(n - 2) = 2 degrees of freedom, a pure-error variance of 4. The
    fitted curve 1, 1, 2, 2 misses the mean by (-1, 0, 0, 1), so with one
    fitted parameter F = (2 * 2 / 3) / 4 = 1/3 on (3, 2).
    """
    mean = np.array([0.0, 1.0, 2.0, 3.0])
    signals = np.vstack([mean + np.array([1.0, -1.0, -1.0, 1.0]), mean - np.array([1.0, -1.0, -1.0, 1.0])])
    found = lack_of_fit(signals, np.array([1.0, 1.0, 2.0, 2.0]), n_params=1)
    assert (found.kind, found.dof, found.expected) == ('lack_of_fit', (3, 2), None)
    assert found.statistic == pytest.approx(1 / 3, rel=1e-12)
    assert found.p_value == pytest.approx(f_dist.sf(1 / 3, 3, 2), rel=1e-12)


def test_lack_of_fit_weighs_every_titration_point_by_what_the_noise_law_says_about_it():
    """The same toy with weights, built so that the weighted detrending is exact by hand.

    The mean curve (-3, -1, 1, 3) and the weights (1, 4, 4, 1) make the two
    columns 1 and ybar orthogonal in the weighted inner product, and the
    difference d = (4, -3, 3, -4) is weight-orthogonal to both (sum w d = 0,
    sum w d ybar = -24 + 24 = 0), so again the scatter is d: SS = 2 sum w d² =
    208 on 2 degrees of freedom. A fitted curve that misses the mean by
    (2, 1, -1, -2) misses it by sum w f² = 16 in the same metric, so with one
    fitted parameter F = (2 * 16 / 3) / 104 = 4/39.

    Only the ratios of the weights matter: both sums are linear in their scale.
    """
    mean = np.array([-3.0, -1.0, 1.0, 3.0])
    weights = np.array([1.0, 4.0, 4.0, 1.0])
    d = np.array([4.0, -3.0, 3.0, -4.0])
    signals = np.vstack([mean + d, mean - d])
    fitted = mean + np.array([2.0, 1.0, -1.0, -2.0])
    found = lack_of_fit(signals, fitted, n_params=1, weights=weights)
    assert (found.kind, found.dof) == ('lack_of_fit', (3, 2))
    assert found.statistic == pytest.approx(4 / 39, rel=1e-12)
    assert found.p_value == pytest.approx(f_dist.sf(4 / 39, 3, 2), rel=1e-12)
    rescaled = lack_of_fit(signals, fitted, n_params=1, weights=7.5 * weights)
    assert rescaled.statistic == pytest.approx(found.statistic, rel=1e-12)
    # Weights of exactly one are the unweighted test.
    assert lack_of_fit(signals, fitted, 1, np.ones(4)).statistic == lack_of_fit(signals, fitted, 1).statistic


def test_lack_of_fit_judges_the_curve_against_the_scatter_within_a_replicate_not_between_them():
    """Three replicates of one curve, each at its own gain and background, plus noise of 0.5 au.

    An affine image of a registered model is a member of the same model, so a
    replicate measured 3 % brighter is not a replicate measured less precisely:
    what its points scatter by about its own image of the mean curve is 0.5 au,
    and a curve missing the mean by 2 au everywhere it bends is a real misfit.
    The raw spread between the replicates is the gains and the backgrounds,
    tens of au, and a test that calls that noise cannot see the misfit at all.
    """
    rng = np.random.default_rng(0)
    t = np.linspace(0.0, 1.0, 12)
    curve = 1000.0 * t / (0.2 + t)
    gain = np.array([0.97, 1.0, 1.03])  # mean exactly one, so the mean curve is the curve
    background = np.array([-5.0, 0.0, 5.0])
    signals = gain[:, None] * curve + background[:, None] + 0.5 * rng.standard_normal((3, 12))
    fitted = curve + 2.0 * np.sin(2 * np.pi * t)

    found = lack_of_fit(signals, fitted, n_params=3)
    assert found.dof == (9, 20) and found.statistic > 15.0 and found.p_value < 1e-3

    # The raw pure error of the same data and the same misfit, on its own degrees of freedom.
    raw_dof = (12 - 3, 12 * (3 - 1))
    raw = (3 * np.sum((signals.mean(axis=0) - fitted) ** 2) / raw_dof[0]) / (
        np.sum((signals - signals.mean(axis=0)) ** 2) / raw_dof[1]
    )
    assert raw < 0.2 and f_dist.sf(raw, *raw_dof) > 0.9


def test_lack_of_fit_refuses_data_that_cannot_carry_the_test():
    signals = np.array([[1.0, 2.0, 3.0, 4.0], [2.0, 2.0, 5.0, 4.0], [3.0, 2.0, 4.0, 7.0]])
    fitted = np.array([2.5, 2.0, 3.0, 5.5])
    with pytest.raises(ValueError, match='two or more replicates'):
        lack_of_fit(signals[:1], fitted, 1)
    with pytest.raises(ValueError, match='more points'):
        lack_of_fit(signals, fitted, 4)
    # Two points: the line through the mean curve leaves the replicates no scatter to be judged against.
    with pytest.raises(ValueError, match='three or more titration points'):
        lack_of_fit(signals[:, :2], fitted[:2], 1)
    with pytest.raises(ValueError, match='one value per titration point'):
        lack_of_fit(signals, fitted, 1, weights=np.ones(3))


def test_replicates_with_no_scatter_above_the_resolution_of_a_fit_are_not_tested():
    """Identical replicates, and exact affine images of one curve, carry no noise to judge a curve against.

    Detrending them leaves what the projection rounds off, and a ratio over
    that is floating-point noise shown to the user as a statistic. The floor
    is the resolution a fit reads a residual at, 1e-10 of the signal's sum of
    squares (a scatter of 1e-5 of its spread): scatter of one part in 1e9 is
    below it, one part in 1e3 is measured noise.
    """
    fitted = np.array([1.0, 2.0, 3.0, 5.0])
    agreeing = np.vstack([[1.0, 2.0, 3.0, 4.0]] * 3)
    assert lack_of_fit(agreeing, fitted, n_params=1) is None

    images = np.array([[0.97], [1.0], [1.04]]) * agreeing[0] + np.array([[0.3], [0.0], [-0.2]])
    assert lack_of_fit(images, fitted, n_params=1) is None
    assert lack_of_fit(images, fitted, n_params=1, weights=np.array([4.0, 2.0, 1.0, 0.5])) is None

    rng = np.random.default_rng(2)
    barely = agreeing * (1.0 + 1e-9 * rng.standard_normal(agreeing.shape))
    assert lack_of_fit(barely, fitted, n_params=1) is None
    noisy = agreeing * (1.0 + 1e-3 * rng.standard_normal(agreeing.shape))
    found = lack_of_fit(noisy, fitted, n_params=1)
    assert found is not None and np.isfinite(found.statistic) and found.p_value < 1e-6


def _line_fit(signals, design):
    """The noise law of *signals*, its weights, and the weighted least-squares fit of their mean on *design*.

    The fit a linear model gets from the pipeline: weights read off the
    replicates, then the mean fitted with them.
    """
    law = noise_law(signals)
    mean = signals.mean(axis=0)
    weights = law.weights(mean)
    root = np.sqrt(weights)
    coefficients = np.linalg.lstsq(design * root[:, np.newaxis], mean * root, rcond=None)[0]
    return law, weights, design @ coefficients


def test_lack_of_fit_with_weights_read_off_the_replicates_holds_its_level_by_the_bootstrap():
    """A straight line fitted to two replicates of a straight line, 20 points, constant noise, 20x signal range.

    The model holds, so a test at 5 % rejects 5 % of datasets. The share of
    the noise law is read off these same replicates, which makes the F tail
    reject about twice that; the bootstrap that reads the share again in every
    draw rejects within Bradley's liberal band [0.025, 0.075] (400 datasets,
    sampling sd 0.011).
    """
    rng = np.random.default_rng(20)
    x = np.linspace(0.0, 1.0, 20)
    design = np.column_stack([np.ones(x.size), x])
    rejected = {'F': 0, 'bootstrap': 0}
    draws = 400
    for _ in range(draws):
        signals = 1.0 + 19.0 * x + rng.standard_normal((2, x.size))
        law, weights, fitted = _line_fit(signals, design)
        assert law.estimated
        bootstrap = lack_of_fit(signals, fitted, 2, weights, law=law, design=design)
        plain = lack_of_fit(signals, fitted, 2, weights)
        assert (bootstrap.reference, plain.reference) == ('bootstrap', 'F')
        rejected['bootstrap'] += bootstrap.p_value <= 0.05
        rejected['F'] += plain.p_value <= 0.05
    assert 0.025 <= rejected['bootstrap'] / draws <= 0.075
    assert rejected['F'] / draws > 0.075


def test_the_bootstrap_p_value_is_a_function_of_the_data():
    """Seeded from the signals: the same data give the same p-value, and the statistic is the F ratio of today.

    Its resolution is that of a Monte-Carlo test with 199 draws: a multiple of 1/200.
    """
    rng = np.random.default_rng(3)
    x = np.linspace(0.0, 1.0, 12)
    design = np.column_stack([np.ones(x.size), x])
    signals = 2.0 + 30.0 * x + (0.2 + 0.05 * x) * rng.standard_normal((3, x.size))
    law, weights, fitted = _line_fit(signals, design)
    first = lack_of_fit(signals, fitted, 2, weights, law=law, design=design)
    again = lack_of_fit(signals.copy(), fitted, 2, weights, law=law, design=design)
    assert first == again
    plain = lack_of_fit(signals, fitted, 2, weights)
    assert (first.statistic, first.dof) == (plain.statistic, plain.dof)
    assert (first.p_value * (LOF_BOOTSTRAP_DRAWS + 1)) == pytest.approx(round(first.p_value * 200), abs=1e-9)


def test_the_bootstrap_still_rejects_a_gross_misfit():
    """A straight line through a saturating curve misses it by many noise sds: no draw reaches its ratio."""
    rng = np.random.default_rng(4)
    x = np.linspace(0.0, 1.0, 15)
    design = np.column_stack([np.ones(x.size), x])
    signals = 100.0 * x / (0.1 + x) + rng.standard_normal((3, x.size))
    law, weights, fitted = _line_fit(signals, design)
    found = lack_of_fit(signals, fitted, 2, weights, law=law, design=design)
    assert found.reference == 'bootstrap'
    assert found.p_value == 1 / (LOF_BOOTSTRAP_DRAWS + 1)


def test_the_bootstrap_reads_the_column_space_of_the_design_not_its_columns():
    """Tied columns and the units a column is measured in change nothing: the refit is the same.

    A signal coefficient tied to another, and a column a thousand million times
    smaller than the others, are what the design of a real fit holds; the
    count of fitted parameters is what fixes the dimension projected off.
    """
    rng = np.random.default_rng(5)
    x = np.linspace(0.0, 1.0, 14)
    design = np.column_stack([np.ones(x.size), x, x**2])
    signals = 3.0 + 20.0 * x - 8.0 * x**2 + (0.3 + 0.1 * x) * rng.standard_normal((3, x.size))
    law, weights, fitted = _line_fit(signals, design)
    found = lack_of_fit(signals, fitted, 3, weights, law=law, design=design)
    tied = np.column_stack([design, 2.0 * design[:, 1]])
    rescaled = design * np.array([1.0, 1e-9, 1e3])
    assert lack_of_fit(signals, fitted, 3, weights, law=law, design=tied) == found
    assert lack_of_fit(signals, fitted, 3, weights, law=law, design=rescaled) == found


def test_without_an_estimated_law_the_test_is_the_f_test():
    """No law, or one taken as constant, leaves the F reference and every number exactly as they were."""
    mean = np.array([-3.0, -1.0, 1.0, 3.0])
    d = np.array([4.0, -3.0, 3.0, -4.0])
    signals = np.vstack([mean + d, mean - d])
    fitted = mean + np.array([2.0, 1.0, -1.0, -2.0])
    plain = lack_of_fit(signals, fitted, 1)
    assert plain.reference == 'F'
    for law in (None, NoiseLaw(NoiseBasis.SINGLE_TITRATION), NoiseLaw(NoiseBasis.TOO_FEW_POINTS, n_replicates=2)):
        assert lack_of_fit(signals, fitted, 1, law=law) == plain
        assert lack_of_fit(signals, fitted, 1, law=law, design=np.ones((4, 1))) == plain


def test_the_bootstrap_refuses_to_run_without_the_design_of_the_fit():
    rng = np.random.default_rng(6)
    x = np.linspace(0.0, 1.0, 10)
    design = np.column_stack([np.ones(x.size), x])
    signals = 1.0 + 5.0 * x + 0.1 * rng.standard_normal((3, x.size))
    law, weights, fitted = _line_fit(signals, design)
    for wrong in (None, design[:-1], design[:, :1], design[:, 0]):
        with pytest.raises(ValueError, match='design of the fit'):
            lack_of_fit(signals, fitted, 2, weights, law=law, design=wrong)


def test_no_scatter_is_a_variance_below_the_resolution_of_the_signal_it_describes():
    """1e-10 of the signal's variance per point: a scale-free floor, so a gain on the signal moves nothing."""
    for gain in (1e-6, 1.0, 1e9):
        ss_tot, n = 50.0 * gain**2, 10
        assert no_scatter(0.99e-10 * ss_tot / n, ss_tot, n)
        assert not no_scatter(1.01e-10 * ss_tot / n, ss_tot, n)


def test_conflict_weights_are_one_for_a_determined_input_and_zero_for_an_unseen_one():
    """Linear toy r = y - a * z1, a second input the residual does not depend on, no binding-constant column.

    With noise scale s the information on z1 is g = |a|² / s², and the weights
    are g / (1 + g) and 0.
    """
    rng = np.random.default_rng(0)
    a = rng.normal(size=12)
    jacobian = np.zeros((14, 2))
    jacobian[:12, 0] = -a
    jacobian[12, 0] = jacobian[13, 1] = 1.0
    for scale in (1e-4, 1.0, 1e3):
        g = float(a @ a) / scale**2
        weights, directions = conflict_reference(jacobian, 0, [True, True], scale)
        assert weights == pytest.approx((0.0, g / (1 + g)), abs=1e-12)
        # The unseen direction is the second input, the seen one the first.
        assert np.abs(directions) == pytest.approx(np.array([[0.0, 1.0], [1.0, 0.0]]), abs=1e-9)
    assert conflict_reference(jacobian, 0, [True, True], 1e-4)[0][1] == pytest.approx(1.0, abs=1e-6)


def test_conflict_weights_discount_what_a_binding_constant_or_a_range_input_absorbs():
    """An input whose effect a free Ka reproduces exactly is as unseen as one with no effect at all."""
    rng = np.random.default_rng(1)
    a = rng.normal(size=10)
    jacobian = np.zeros((11, 2))
    jacobian[:10, 0] = a  # the Ka column
    jacobian[:10, 1] = 2.0 * a  # the input: same direction
    jacobian[10, 1] = 1.0
    assert conflict_reference(jacobian, 1, [True], 1e-3)[0] == pytest.approx((0.0,), abs=1e-6)
    # The same with the absorbing column a range input (no penalty row) listed before the sigma input.
    assert conflict_reference(jacobian, 0, [False, True], 1e-3)[0] == pytest.approx((0.0,), abs=1e-6)


def test_conflict_weights_do_not_depend_on_the_units_a_binding_constant_is_measured_in():
    """Rescaling a column is measuring its parameter in another unit, which changes nothing the data say.

    A binding constant whose column is short against the others — one the
    residual barely depends on in the units it happens to be written in — is
    still a parameter the fit is free to move, and still absorbs its share of
    the inputs. The reference is the same with that column multiplied by 1e-9
    or by 1e3; here the first input shares a direction with it, and the
    weights are the textbook ``I - [(J'J)⁻¹]_zz`` of the unscaled problem.
    """
    rng = np.random.default_rng(5)
    n = 12
    ka = rng.normal(size=n)
    inputs = np.column_stack([0.8 * ka + 0.2 * rng.normal(size=n), rng.normal(size=n)])
    jacobian = np.vstack([np.column_stack([ka, inputs]), np.hstack([np.zeros((2, 1)), np.eye(2)])])
    covariance = np.linalg.inv(jacobian.T @ jacobian)[1:, 1:]
    textbook = np.linalg.eigvalsh(np.eye(2) - covariance)
    for factor in (1.0, 1e-9, 1e3):
        scaled = jacobian.copy()
        scaled[:, 0] *= factor
        weights, _ = conflict_reference(scaled, 1, [True, True], 1.0)
        assert weights == pytest.approx(textbook, rel=1e-9, abs=1e-12)


def test_conflict_weights_add_up_to_the_residual_degrees_of_freedom_the_inputs_take():
    """The trace of the data block of the stacked hat matrix is the effective number of parameters of a
    penalised fit: one per binding-constant column plus the sum of the weights."""
    rng = np.random.default_rng(4)
    n, n_ka, k = 9, 2, 3
    jacobian = np.vstack([rng.normal(size=(n, n_ka + k)), np.hstack([np.zeros((k, n_ka)), np.eye(k)])])
    hat = jacobian @ np.linalg.pinv(jacobian)
    weights, _ = conflict_reference(jacobian, n_ka, [True] * k, 1.0)
    assert weights.sum() == pytest.approx(np.trace(hat[:n, :n]) - n_ka, abs=1e-10)
    assert np.all((0 < weights) & (weights < 1))


def test_a_direction_the_data_cannot_see_is_no_evidence_for_or_against_the_inputs():
    """Two inputs, the data determine their sum and say nothing about their difference."""
    directions = np.array([[1.0, 1.0], [-1.0, 1.0]]) / np.sqrt(2)  # columns: difference, sum
    weights = np.array([0.0, 0.8])
    # A shift of 0.03 standard deviations along the unseen direction alone: nothing to test.
    along_unseen = conflict_test(0.03 * directions[:, 0], weights, directions, n_points=12, n_params=3)
    assert along_unseen.q == pytest.approx(0.0, abs=1e-30) and along_unseen.p_value == 1.0
    assert conflict_test([0.03, -0.03], np.zeros(2), directions, n_points=12, n_params=3) is None
    assert conflict_test([0.03, -0.03], np.array([0.0, 0.009]), directions, n_points=12, n_params=3) is None
    # The statistic is the squared shift along the seen direction, whatever lies along the other.
    z = 2.0 * directions[:, 1] + 5.0 * directions[:, 0]
    found = conflict_test(z, weights, directions, n_points=12, n_params=3)
    assert (found.k, found.weights) == (1, (0.8,)) and found.q == pytest.approx(4.0)
    assert found.p_value == conflict_p_value(4.0, [0.8], 12, 3)
    # No more directions than residual degrees of freedom: the heaviest one of two with n - p = 1.
    both = conflict_test(z, np.array([0.5, 0.8]), directions, n_points=4, n_params=3)
    assert both.weights == (0.8,) and both.q == pytest.approx(4.0)


def test_conflict_p_value_is_the_weighted_chi_squared_tail_and_repeats_exactly():
    # One unit weight: a chi-squared with one degree of freedom.
    assert conflict_p_value(3.841, [1.0]) == pytest.approx(chi2.sf(3.841, 1), abs=2e-3)
    # Unit weights add up to a chi-squared with as many degrees of freedom; zero weights add nothing.
    assert conflict_p_value(5.0, [1.0, 0.0, 1.0]) == pytest.approx(chi2.sf(5.0, 2), abs=2e-3)
    # A weight w scales the variable: P(w X >= q) = P(X >= q / w).
    assert conflict_p_value(2.0, [0.5]) == pytest.approx(chi2.sf(4.0, 1), abs=2e-3)
    assert conflict_p_value(4.2, [0.3, 0.9]) == conflict_p_value(4.2, [0.3, 0.9])
    assert conflict_p_value(0.0, [0.0, 0.0]) == 1.0


def test_conflict_p_value_with_an_estimated_scale_has_its_two_analytic_limits():
    # Inputs the data determine: their shifts are the entry errors themselves, whatever the noise scale.
    assert conflict_p_value(5.0, [1.0, 1.0], n_points=8, n_params=3) == pytest.approx(chi2.sf(5.0, 2), abs=2e-3)
    # One input the data barely see, n - p = 5: q / w is n times the share of one of five
    # squared residual components, n * Beta(1/2, 2) — bounded by n, unlike w * chi-squared.
    w, n, p = 1e-4, 8, 3
    for share in (0.2, 0.5, 0.8):
        expected = beta.sf(share, 0.5, (n - p - 1) / 2)
        assert conflict_p_value(w * n * share, [w], n_points=n, n_params=p) == pytest.approx(expected, abs=3e-3)
    assert conflict_p_value(w * n * 1.001, [w], n_points=n, n_params=p) == 0.0
    # Many points: the scale is known in effect.
    assert conflict_p_value(2.0, [0.4, 0.7], 4000, 3) == pytest.approx(conflict_p_value(2.0, [0.4, 0.7]), abs=3e-3)


def _null_rejection_rates(n: int, gain: float, sims: int = 600) -> tuple[float, float]:
    """Rejection rates at 5 % of (estimated-scale, known-scale) references on a consistent linear model.

    ``y = X b + A (z_entered - z_true) + noise`` with a straight-line nuisance
    part, two inputs of unit stated sigma and unit noise; the fit minimises
    ``n log S + z'z`` like the engine, by BFGS on the closed-form projected
    residual.
    """
    rng = np.random.default_rng(1)
    t = np.linspace(0.0, 1.0, n)
    x = np.column_stack([np.ones(n), t])
    project = np.eye(n) - x @ np.linalg.pinv(x)
    effect = project @ (np.column_stack([np.sin(3 * t), t**2]) * gain)
    jacobian = np.vstack([-effect, np.eye(2)])
    rejected = np.zeros(2)
    for _ in range(sims):
        y = project @ (rng.standard_normal(n)) - effect @ rng.standard_normal(2)

        def objective(z: np.ndarray) -> float:
            return n * np.log(np.sum((y - effect @ z) ** 2)) + float(z @ z)

        z = minimize(objective, np.zeros(2), method='BFGS', options={'gtol': 1e-10}).x
        scale = np.sqrt(np.sum((y - effect @ z) ** 2) / n)
        weights, _ = conflict_reference(jacobian, 0, [True, True], scale)
        q = float(z @ z)
        rejected += [
            conflict_p_value(q, weights, n, 2, draws=20_000) < 0.05,
            conflict_p_value(q, weights, draws=20_000) < 0.05,
        ]
    return tuple(rejected / sims)


def test_the_conflict_reference_holds_its_level_on_a_consistent_linear_model_with_few_points():
    """600 seeded datasets per regime: the binomial 95 % range around 0.05 is 0.033 to 0.067."""
    weak, weak_known_scale = _null_rejection_rates(n=6, gain=0.3)
    assert 0.03 <= weak <= 0.07
    assert weak_known_scale > 0.085  # what ignoring the estimated scale costs at six points
    strong, _ = _null_rejection_rates(n=8, gain=10.0)
    assert 0.03 <= strong <= 0.07


def _misfit(p: float) -> MisfitTest:
    return MisfitTest('runs', 4.0, p, expected=6.0)


def _conflict(p: float) -> Conflict:
    return Conflict(q=9.0, k=2, p_value=p, weights=(0.2, 0.9))


@pytest.mark.parametrize(
    ('conditional', 'aware', 'conflict', 'expected'),
    [
        (0.50, 0.60, 0.40, Verdict.CONSISTENT),
        (0.01, 0.60, 0.40, Verdict.INPUTS_EXPLAIN),
        (0.01, 0.60, 0.01, Verdict.INPUTS_CONFLICT),  # the conflict outranks the explanation
        (0.50, 0.60, 0.01, Verdict.INPUTS_CONFLICT),
        (0.50, 0.01, 0.40, Verdict.MODEL_INADEQUATE),
        (0.01, 0.01, 0.01, Verdict.MODEL_AND_INPUTS),  # both reject: both are named
        (0.001, 0.02, 0.04, Verdict.MODEL_AND_INPUTS),  # 0.02 < 0.05 / 2, then 0.04 < 0.05 / 1
        (0.001, 0.03, 0.60, Verdict.INPUTS_EXPLAIN),  # 0.03 is above 0.05 / 2: the misfit is not named
        # The misfit at the entered inputs is the same test at other inputs and faces its threshold: a miss
        # the shifted inputs left as it was is no miss they explain.
        (0.03, 0.03, 0.60, Verdict.CONSISTENT),
        (0.50, 0.60, 0.03, Verdict.CONSISTENT),  # the same for the conflict
        (0.50, 0.03, 0.04, Verdict.CONSISTENT),  # the smaller p stops the procedure, the larger is not reached
        # A test rejects at its threshold itself, the rule under which the bootstrap's p-values of k/200 hold
        # 0.025 and 0.05 exactly; just above the first, the procedure stops.
        (0.50, 0.025, 0.05, Verdict.MODEL_AND_INPUTS),
        (0.50, 0.0250001, 0.05, Verdict.CONSISTENT),
    ],
)
def test_the_verdict_judges_the_misfit_and_the_conflict_together_by_holm(conditional, aware, conflict, expected):
    """Holm at 5 % over the two tests: the smaller p against 0.025, then the larger against 0.05, each at or below."""
    assert verdict(_misfit(conditional), _misfit(aware), _conflict(conflict)) is expected


def test_holm_holds_the_chance_of_a_false_finding_at_the_level_where_two_raw_tests_exceed_it():
    """Independent uniform p-values, the null of both tests: at most one false finding in twenty.

    Two tests at 5 % each name something in 1 - 0.95² = 9.75 % of fits. Holm
    names something exactly when the smaller p-value is below 0.025, in
    1 - 0.975² = 4.94 % of them.
    """
    rng = np.random.default_rng(11)
    p = rng.random((40_000, 2))
    named = np.mean([verdict(None, _misfit(a), _conflict(b)) is not Verdict.CONSISTENT for a, b in p])
    assert named == pytest.approx(1 - 0.975**2, abs=0.004)
    raw = np.mean(np.any(p < 0.05, axis=1))
    assert raw == pytest.approx(1 - 0.95**2, abs=0.005)


def test_the_verdict_without_a_test_or_without_varying_inputs():
    assert verdict(None, None, None) is Verdict.CONSISTENT
    # Nothing varies: both misfit entries are the test at the entered inputs, judged alone at the level.
    assert verdict(_misfit(0.04), _misfit(0.04), None) is Verdict.MODEL_INADEQUATE
    assert verdict(_misfit(0.05), _misfit(0.05), None) is Verdict.MODEL_INADEQUATE
    # A range-only specification has no conflict statistic.
    assert verdict(_misfit(0.001), _misfit(0.7), None) is Verdict.INPUTS_EXPLAIN
    assert verdict(_misfit(0.03), _misfit(0.03), None, level=0.01) is Verdict.CONSISTENT
    # A conflict alone is judged at the level too.
    assert verdict(None, None, _conflict(0.04)) is Verdict.INPUTS_CONFLICT


def test_every_number_a_results_file_holds_is_finite_and_written_field_for_field():
    ordinary = MisfitTest('lack_of_fit', 1.2, 0.34, dof=(3, 8))
    assert ordinary.to_dict() == {
        'kind': 'lack_of_fit',
        'statistic': 1.2,
        'p_value': 0.34,
        'dof': [3, 8],
        'expected': None,
        'reference': 'F',
    }
    assert MisfitTest.from_dict(json.loads(json.dumps(ordinary.to_dict(), allow_nan=False))) == ordinary
    bootstrap = MisfitTest('lack_of_fit', 1.2, 0.035, dof=(3, 8), reference='bootstrap')
    assert MisfitTest.from_dict(json.loads(json.dumps(bootstrap.to_dict(), allow_nan=False))) == bootstrap
    # A results file that names no reference holds an F test.
    written = ordinary.to_dict()
    del written['reference']
    assert MisfitTest.from_dict(written) == ordinary
    # ... and a runs test the simulated runs, its only reference.
    runs = MisfitTest('runs', 4.0, 0.2, expected=6.0, reference='simulated')
    written = runs.to_dict()
    del written['reference']
    assert MisfitTest.from_dict(written) == runs
    assert _conflict(0.003).to_dict() == {'q': 9.0, 'k': 2, 'p_value': 0.003, 'weights': [0.2, 0.9]}
    assert Conflict.from_dict(json.loads(json.dumps(_conflict(0.003).to_dict(), allow_nan=False))) == _conflict(0.003)


def test_diagnostics_round_trip_through_a_results_file_dict():
    full = FitDiagnostics(
        conditional_misfit=MisfitTest('lack_of_fit', 12.5, 1e-4, dof=(9, 72)),
        misfit=_misfit(0.41),
        conflict=_conflict(0.003),
        verdict=Verdict.INPUTS_CONFLICT,
    )
    written = full.to_dict()
    assert written['verdict'] == 'inputs_conflict' and written['conditional_misfit']['dof'] == [9, 72]
    assert FitDiagnostics.from_dict(written) == full
    empty = FitDiagnostics(None, None, None, Verdict.CONSISTENT, skipped={'misfit': 'no_scatter'})
    assert empty.to_dict()['skipped'] == {'misfit': 'no_scatter'}
    assert FitDiagnostics.from_dict(json.loads(json.dumps(empty.to_dict()))) == empty
    # A file that names no skipped test.
    written = {key: value for key, value in full.to_dict().items() if key != 'skipped'}
    assert FitDiagnostics.from_dict(written).skipped == {}
    for shift in (InputShift('h0', -0.114, -3.8, False), InputShift('d0', -0.06, None, True)):
        assert InputShift.from_dict(shift.to_dict()) == shift


def test_a_misfit_record_with_a_null_statistic_reads_as_data_with_no_scatter():
    """A null F is the ratio over a pure error of zero: replicates that agree exactly, which no test can judge.

    Read as the misfit test not run for that reason, the verdict stated on it
    is judged again from the conflict alone, and the result renders.
    """
    from gui.plotting.labels import verdict_sentence

    infinite = {'kind': 'lack_of_fit', 'statistic': None, 'p_value': 0.0, 'dof': [9, 24], 'expected': None}
    record = {
        'conditional_misfit': infinite,
        'misfit': infinite,
        'conflict': _conflict(0.6).to_dict(),
        'verdict': 'model_inadequate',
    }

    read = FitDiagnostics.from_dict(json.loads(json.dumps(record)))

    assert (read.conditional_misfit, read.misfit, read.skipped) == (None, None, {'misfit': 'no_scatter'})
    assert read.verdict is Verdict.CONSISTENT
    assert 'no scatter above rounding' in verdict_sentence(read, {}, {}, html=False)
