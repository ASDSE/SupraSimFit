"""Misfit tests, the conflict statistic and the verdict — against hand-computed references.

- the runs test has the binomial distribution of sign changes when nothing is
  fitted, the hand-derived distribution for three residuals about a fitted
  offset, and its stated level on a fitted curve;
- the lack-of-fit F is the hand-computed ratio on a 2 x 4 toy, weighted and
  unweighted, and it fires on replicates that differ by a scale and a
  background where the raw spread between them hides the misfit entirely;
- the weights of the conflict reference are g / (1 + g) for the information g
  the data hold on an input: 1 for an input the data determine, 0 for one the
  residual does not depend on;
- the conflict p-value has its two analytic limits (chi-squared where the data
  determine the inputs, a scaled beta where they say nothing) and, on a linear
  Gaussian model fitted the same way, rejects a consistent fit at the stated
  rate with few points, where a reference that takes the noise scale as known
  rejects twice as often;
- the verdict names the first cause that applies, in its fixed order.
"""

import json
import math

import numpy as np
import pytest
from scipy.optimize import minimize
from scipy.stats import beta, binom, chi2
from scipy.stats import f as f_dist

from core.pipeline.diagnostics import (
    Conflict,
    FitDiagnostics,
    InputShift,
    MisfitTest,
    Verdict,
    conflict_p_value,
    conflict_reference,
    conflict_test,
    lack_of_fit,
    runs_test,
    verdict,
)


def test_runs_test_of_unfitted_residuals_is_the_binomial_distribution_of_sign_changes():
    """Nothing fitted: the signs are fair coins, so runs - 1 is Binomial(n - 1, 1/2); the p-value is its mid-p."""
    n = 9
    x = np.arange(float(n))
    nothing_fitted = np.empty((n, 0))
    for signs, runs in (('++++-----', 2), ('++--++--+', 5), ('+-+-+-+-+', 9)):
        residuals = np.array([1.5 if s == '+' else -0.5 for s in signs])
        found = runs_test(residuals, x, nothing_fitted)
        assert (found.kind, found.statistic, found.dof) == ('runs', runs, None)
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


def test_replicates_that_leave_only_the_rounding_error_of_the_projection_have_no_scatter():
    """Identical replicates, and exact affine images of one curve, are an infinite ratio, not a rounding artefact.

    Detrending them leaves what the projection rounds off — about 1e-31 of the
    data's squared norm — and a finite F over that would be floating-point
    noise shown to the user as a statistic. Scatter of one part in 1e9, far
    below any instrument, is still scatter and gives a finite ratio.
    """
    fitted = np.array([1.0, 2.0, 3.0, 5.0])
    agreeing = np.vstack([[1.0, 2.0, 3.0, 4.0]] * 3)
    found = lack_of_fit(agreeing, fitted, n_params=1)
    assert found.statistic == math.inf and found.p_value == 0.0

    images = np.array([[0.97], [1.0], [1.04]]) * agreeing[0] + np.array([[0.3], [0.0], [-0.2]])
    assert lack_of_fit(images, fitted, n_params=1).statistic == math.inf
    assert lack_of_fit(images, fitted, n_params=1, weights=np.array([4.0, 2.0, 1.0, 0.5])).statistic == math.inf

    rng = np.random.default_rng(2)
    barely = agreeing * (1.0 + 1e-9 * rng.standard_normal(agreeing.shape))
    assert math.isfinite(lack_of_fit(barely, fitted, n_params=1).statistic)


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
        (0.01, 0.01, 0.01, Verdict.MODEL_INADEQUATE),  # a model the inputs cannot rescue outranks everything
        (0.50, 0.01, 0.40, Verdict.MODEL_INADEQUATE),
        (0.05, 0.05, 0.05, Verdict.CONSISTENT),  # at the level itself nothing is rejected
    ],
)
def test_the_verdict_names_the_first_cause_that_applies(conditional, aware, conflict, expected):
    assert verdict(_misfit(conditional), _misfit(aware), _conflict(conflict)) is expected


def test_the_verdict_without_a_test_or_without_varying_inputs():
    assert verdict(None, None, None) is Verdict.CONSISTENT
    # Nothing varies: both misfit entries are the test at the entered inputs.
    assert verdict(_misfit(0.001), _misfit(0.001), None) is Verdict.MODEL_INADEQUATE
    # A range-only specification has no conflict statistic.
    assert verdict(_misfit(0.001), _misfit(0.7), None) is Verdict.INPUTS_EXPLAIN
    assert verdict(_misfit(0.03), _misfit(0.03), None, level=0.01) is Verdict.CONSISTENT


def test_a_value_json_cannot_hold_is_written_as_null_and_read_back_as_what_it_stood_for():
    """The lack-of-fit ratio is infinite where the replicates leave no scatter at all, and JSON has no
    token for it.

    Everything else a results file holds here is finite: the p-values are
    proportions, the degrees of freedom are counts, and the weights lie in
    ``[0, 1]``.
    """
    agreeing = np.vstack([[1.0, 2.0, 3.0, 4.0]] * 3)
    exact = lack_of_fit(agreeing, np.array([1.0, 2.0, 3.0, 5.0]), n_params=1)
    assert exact.statistic == math.inf
    assert exact.to_dict()['statistic'] is None
    assert MisfitTest.from_dict(json.loads(json.dumps(exact.to_dict(), allow_nan=False))) == exact

    far = Conflict(q=math.inf, k=2, p_value=0.0, weights=(0.2, 0.9))
    assert far.to_dict()['q'] is None
    assert Conflict.from_dict(json.loads(json.dumps(far.to_dict(), allow_nan=False))) == far

    # A finite test is written as it stands, field for field.
    ordinary = MisfitTest('lack_of_fit', 1.2, 0.34, dof=(3, 8))
    assert ordinary.to_dict() == {
        'kind': 'lack_of_fit',
        'statistic': 1.2,
        'p_value': 0.34,
        'dof': [3, 8],
        'expected': None,
    }
    assert _conflict(0.003).to_dict() == {'q': 9.0, 'k': 2, 'p_value': 0.003, 'weights': [0.2, 0.9]}


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
    empty = FitDiagnostics(None, None, None, Verdict.CONSISTENT)
    assert FitDiagnostics.from_dict(empty.to_dict()) == empty
    for shift in (InputShift('h0', -0.114, -3.8, False), InputShift('d0', -0.06, None, True)):
        assert InputShift.from_dict(shift.to_dict()) == shift
