"""The noise law read from replicates, and the point weights it gives the fit.

The property under test is always the same one: what the replicates scatter by
is the noise, and what whole replicates differ by — a scale factor and an
offset, the affine freedom every registered model already has — is not. The
truth each test scores against is the noise law the data were drawn with, never
a number a previous run produced.

The datasets use the many-replicate limit (:data:`M_LARGE`) so that the share
they read is the estimator's answer and not one draw of the noise; the two
tests that must run at a realistic replicate count say so where they stand.
"""

import json
from types import SimpleNamespace

import numpy as np
import pytest
from scipy.optimize import minimize_scalar

import core.pipeline.noise as noise
from core.pipeline.noise import MIN_REPLICATES, NoiseBasis, NoiseLaw, noise_law, replicate_scatter

# Replicates per dataset. The estimator reads one number off the scatter at
# each titration point, so its spread falls like 1/sqrt(m); at 200 the share is
# determined to about 0.01, which makes every assertion below a statement about
# the method rather than about a seed.
M_LARGE = 200


def _replicates(curve, sd, m=M_LARGE, seed=0, scale=0.0, offset=0.0):
    """*m* replicates of *curve*, each with its own scale factor and offset, plus independent noise.

    *sd* is the standard deviation of the independent noise at each point,
    *scale* the standard deviation of one replicate's multiplicative factor and
    *offset* that of its additive shift, as a fraction of the signal range.
    """
    rng = np.random.default_rng(seed)
    curve = np.asarray(curve, dtype=float)
    rows = (1.0 + scale * rng.standard_normal((m, 1))) * curve
    rows = rows + offset * np.ptp(curve) * rng.standard_normal((m, 1))
    return rows + sd * rng.standard_normal((m, curve.size))


def _raw_share(signals):
    """The share the same objective reads from the RAW per-point variance of the replicates.

    Written out here rather than imported: it is the estimator the module does
    not use, and the contrast between the two is what the detrending buys.
    """
    signals = np.asarray(signals, dtype=float)
    mean = signals.mean(axis=0)
    relative = mean**2 / np.mean(mean**2)

    def objective(share):
        scatter = np.sum((signals - mean) ** 2 / ((1.0 - share) + share * relative), axis=0)
        logs = np.log(scatter[scatter > 0.0])
        return float(np.sum((logs - logs.mean()) ** 2))

    nodes = np.linspace(0.0, 1.0, 101)
    return float(nodes[int(np.argmin([objective(node) for node in nodes]))])


def _unguarded_share(signals):
    """The share the objective reads with no floor on ``u`` and every point that scatters after detrending counted.

    Written out here rather than imported: on data where no mean is zero and
    every point scatters, the guards of :func:`noise_law` must change nothing,
    and this is the estimator they guard.
    """
    signals = np.asarray(signals, dtype=float)
    mean = signals.mean(axis=0)
    relative = mean**2 / np.mean(mean**2)

    def scatter(share):
        residuals, leverage = replicate_scatter(signals, 1.0 / ((1.0 - share) + share * relative))
        return np.sum(residuals**2, axis=0) / (1.0 - leverage)

    def objective(share):
        logs = np.log(scatter(share))
        return float(np.sum((logs - logs.mean()) ** 2))

    nodes = np.linspace(0.0, 1.0, 101)
    values = np.array([objective(node) for node in nodes])
    best = int(values.argmin())
    refined = minimize_scalar(
        objective,
        bounds=(nodes[max(best - 1, 0)], nodes[min(best + 1, 100)]),
        method='bounded',
        options={'xatol': 1e-5},
    )
    share = float(refined.x) if refined.fun < values[best] else float(nodes[best])
    return 0.0 if share < 1e-5 else 1.0 if share > 1.0 - 1e-5 else share


def test_constant_noise_reads_a_share_of_zero_and_the_true_floor(gda_clean):
    """Noise that does not grow with the signal: the share goes to its lower end and the floor is the sd it was drawn with."""
    curve = gda_clean[1].magnitude
    sd = 0.02 * np.ptp(curve)
    law = noise_law(_replicates(curve, np.full(curve.size, sd)))
    assert law.basis is NoiseBasis.REPLICATES
    assert law.n_replicates == M_LARGE
    assert law.share < 0.05
    assert law.floor == pytest.approx(sd, rel=0.05)


def test_proportional_noise_reads_a_share_of_one_and_the_true_fraction(gda_clean):
    """Noise of a fixed percentage of the signal: the share goes to its upper end and the percentage is recovered."""
    curve = gda_clean[1].magnitude
    law = noise_law(_replicates(curve, 0.02 * curve))
    assert law.share > 0.95
    assert law.proportional == pytest.approx(0.02, rel=0.05)


def test_a_mixed_law_recovers_both_of_its_components(gda_clean):
    """A floor and a proportional part together are read apart, each to within 10 %.

    Both components have to be visible in the data for that: the floor where
    the signal is small, the proportional part where it is large. The GDA
    titration spans 228 to 1 in signal, which shows both.
    """
    curve = gda_clean[1].magnitude
    floor, proportional = 0.005 * np.ptp(curve), 0.02
    law = noise_law(_replicates(curve, np.hypot(floor, proportional * curve)))
    assert law.floor == pytest.approx(floor, rel=0.10)
    assert law.proportional == pytest.approx(proportional, rel=0.10)


def test_replicates_that_differ_by_a_scale_factor_are_not_read_as_proportional_noise(gda_clean):
    """Constant noise stays constant noise when whole replicates differ by a gain and a background.

    An affine image of the fitted curve is a member of the same model, so a
    replicate measured 5 % high is not a measurement 5 % less precise. Read
    from the raw per-point variance the same data look strongly
    signal-proportional, which is the error this estimator is built to avoid.
    """
    curve = gda_clean[1].magnitude
    sd = 0.01 * np.ptp(curve)
    signals = _replicates(curve, np.full(curve.size, sd), scale=0.05, offset=0.005)
    law = noise_law(signals)
    assert law.share < 0.2
    assert _raw_share(signals) > 0.8
    assert law.floor == pytest.approx(sd, rel=0.05)


def test_the_weights_are_exactly_one_wherever_no_law_was_read(gda_clean):
    """Weights of one, to the bit, so that a fit without a noise law is the fit of today.

    Whitening multiplies the design and the signal by ``sqrt(w)``; an array of
    exactly 1.0 leaves every floating-point operation of the fit unchanged.
    """
    curve = gda_clean[1].magnitude
    ones = np.ones(curve.size)
    for law in (
        NoiseLaw(NoiseBasis.SINGLE_TITRATION),
        NoiseLaw(NoiseBasis.TOO_FEW_POINTS, n_replicates=3),
        NoiseLaw(
            NoiseBasis.REPLICATES, share=0.0, floor=12.0, reference=float(np.sqrt(np.mean(curve**2))), u_floor=0.3
        ),
    ):
        weights = law.weights(curve)
        assert np.array_equal(weights, ones)
        assert weights.dtype == float


def test_scaling_every_signal_leaves_the_shape_and_scales_the_level(gda_clean):
    """The share and the proportional part are dimensionless; the floor and the reference are in au.

    Reading the same measurement in a thousand times larger unit must not
    change what the fit is told about precision.
    """
    curve = gda_clean[1].magnitude
    signals = _replicates(curve, np.hypot(0.005 * np.ptp(curve), 0.02 * curve), seed=3)
    law, scaled = noise_law(signals), noise_law(1000.0 * signals)
    assert scaled.share == pytest.approx(law.share, rel=1e-9)
    assert scaled.proportional == pytest.approx(law.proportional, rel=1e-9)
    assert scaled.floor == pytest.approx(1000.0 * law.floor, rel=1e-9)
    assert scaled.reference == pytest.approx(1000.0 * law.reference, rel=1e-9)
    assert scaled.weights(1000.0 * curve) == pytest.approx(law.weights(curve), rel=1e-9)


def test_one_titration_cannot_show_a_noise_law(gda_clean):
    """No replicates, no scatter to read: the noise is taken as constant and the summary says so."""
    curve = gda_clean[1].magnitude
    for signals in (None, curve, curve[np.newaxis, :]):
        law = noise_law(signals)
        assert law.basis is NoiseBasis.SINGLE_TITRATION
        assert law.share == 0.0
        assert np.array_equal(law.weights(curve), np.ones(curve.size))


def test_replicates_that_scatter_nowhere_cannot_show_a_noise_law(gda_clean):
    """Identical replicates have a variance of zero everywhere, which names no share."""
    curve = gda_clean[1].magnitude
    law = noise_law(np.tile(curve, (4, 1)))
    assert law.basis is NoiseBasis.TOO_FEW_POINTS
    assert law.n_replicates == 4
    assert np.array_equal(law.weights(curve), np.ones(curve.size))


def test_replicates_that_are_exact_images_of_one_curve_show_no_law():
    """Replicates that differ by a scale factor and an offset alone scatter nowhere once detrended.

    What is left is the rounding error of the projection, which crosses the
    rounding threshold at a few points that change with the candidate share. The
    points that scatter are decided once, so no share can collect three of them
    and read a law off floating-point noise.
    """
    rng = np.random.default_rng(3)
    x = np.linspace(0.0, 1.0, 12)
    for _ in range(12):
        m = int(rng.integers(2, 9))
        curve = rng.uniform(10.0, 1e5) + rng.uniform(1e2, 1e6) * x / (rng.uniform(0.05, 2.0) + x)
        images = (1.0 + 0.03 * rng.standard_normal((m, 1))) * curve + rng.uniform(0.0, 100.0, (m, 1))
        law = noise_law(images)
        assert law.basis is NoiseBasis.TOO_FEW_POINTS
        assert np.array_equal(law.weights(curve), np.ones(curve.size))


def test_a_share_at_the_end_of_its_range_is_that_end_exactly(gda_clean, monkeypatch):
    """A share of zero has to be 0.0, because only then are the weights exactly one and the fit the unweighted one.

    Bounded Brent never evaluates an end of its bracket, so a minimum at the
    end comes back a tolerance short of it; here the refinement is made to
    return such a value with a lower objective, at either end.
    """
    curve = gda_clean[1].magnitude
    constant = _replicates(curve, np.full(curve.size, 0.02 * np.ptp(curve)))
    proportional = _replicates(curve, 0.02 * np.abs(curve))
    for signals, short_of_the_end, end in ((constant, 3e-6, 0.0), (proportional, 1.0 - 3e-6, 1.0)):
        monkeypatch.setattr(
            noise, 'minimize_scalar', lambda *a, x=short_of_the_end, **k: SimpleNamespace(x=x, fun=-np.inf)
        )
        law = noise_law(signals)
        assert law.share == end
        if end == 0.0:
            assert np.array_equal(law.weights(curve), np.ones(curve.size))


def test_a_mean_of_exactly_zero_leaves_every_weight_finite(gda_clean):
    """A blank-subtracted point whose mean lands on zero is fitted, not divided by.

    A purely proportional law would give it a variance of zero, so the
    estimator refuses a share of 1 on such data; every weight stays finite.
    """
    curve = gda_clean[1].magnitude - gda_clean[1].magnitude[0]
    rng = np.random.default_rng(1)
    deviations = 0.02 * np.ptp(curve) * rng.standard_normal((2, curve.size))
    # Paired ± deviations put the mean of the four replicates exactly on the
    # curve, whose first point is exactly zero.
    signals = np.vstack([curve + deviations[0], curve - deviations[0], curve + deviations[1], curve - deviations[1]])
    mean = signals.mean(axis=0)
    assert mean[0] == 0.0
    law = noise_law(signals)
    assert law.basis is NoiseBasis.REPLICATES
    # The zero-mean point scatters, so it sets the floor on u: zero.
    assert law.u_floor == 0.0
    assert law.share < 1.0
    assert np.isfinite(law.weights(mean)).all()
    json.dumps(law.to_dict(), allow_nan=False)


def test_blank_subtracted_replicates_read_a_finite_law(gda_clean):
    """Each replicate minus its own first point: a column of exact zeros, which scatters nowhere and has a mean of zero.

    That point judges nothing, so the law is read from the others, and the
    smallest ``u`` among them is the floor every point's ``u`` is clipped at,
    the zero included: the weights stay finite and spread no wider than
    ``max u / u_floor``, the range of the points the law was read on. Constant,
    proportional and mixed noise, two to four replicates.
    """
    curve = gda_clean[1].magnitude
    floor, proportional = 0.02 * np.ptp(curve), 0.02
    for seed in range(60):
        m = 2 + seed % 3
        sd = (np.full(curve.size, floor), proportional * curve, np.hypot(0.25 * floor, proportional * curve))[seed % 3]
        signals = _replicates(curve, sd, m=m, seed=seed)
        signals = signals - signals[:, :1]
        mean = signals.mean(axis=0)
        law = noise_law(signals)
        assert law.basis is NoiseBasis.REPLICATES
        assert np.isfinite([law.share, law.floor, law.proportional, law.reference]).all()
        u = mean**2 / law.reference**2
        assert law.u_floor == pytest.approx(u[1:].min(), rel=1e-12)
        weights = law.weights(mean)
        assert np.isfinite(weights).all() and (weights > 0.0).all()
        assert weights.max() / weights.min() <= u.max() / law.u_floor * (1.0 + 1e-12)
        json.dumps(law.to_dict(), allow_nan=False)


def test_the_guards_change_nothing_where_no_mean_is_zero_and_every_point_scatters(gda_clean, ida_clean):
    """On data the guards do not act on, the share is the unguarded estimator's, to 1e-8.

    The floor on ``u`` is the smallest ``u`` of all points, so it clips
    nothing; the scattering set is every point; and the snap to a share of 1
    is the unguarded one wherever the objective is finite there.
    """
    for fixture in (gda_clean, ida_clean):
        curve = fixture[1].magnitude
        for seed in range(12):
            kind = seed % 3
            sd = (
                np.full(curve.size, 0.02 * np.ptp(curve)),
                0.02 * curve,
                np.hypot(0.005 * np.ptp(curve), 0.02 * curve),
            )
            signals = _replicates(curve, sd[kind], m=2 + seed % 7, seed=seed, scale=0.02 * (seed % 2))
            mean = signals.mean(axis=0)
            assert (mean != 0.0).all()
            law = noise_law(signals)
            assert law.u_floor == pytest.approx(np.min(mean**2) / law.reference**2, rel=1e-12)
            assert law.share == pytest.approx(_unguarded_share(signals), abs=1e-8)


def test_the_weights_spread_no_wider_than_the_range_of_u_the_law_was_read_on(gda_clean):
    """``max(w)/min(w) <= max u / u_floor``, with equality only at a share of one.

    Below ``u_floor`` a point takes the weight of a point at ``u_floor``: the
    law is not extrapolated beneath the signals it was read on. The bound is
    the range of ``u`` over those signals, which is large when one of them has
    a mean near zero; the GDA titration's first mean is 0.4 % of the signal
    range, and with that point among them the bound is five orders of
    magnitude.
    """
    curve = gda_clean[1].magnitude
    reference = float(np.sqrt(np.mean(curve**2)))
    u = curve**2 / reference**2
    for u_floor in (0.0, float(np.sort(u)[2])):
        bound = u.max() / (u_floor if u_floor > 0.0 else u.min())
        assert bound > 1e4 or u_floor > 0.0
        for share in np.linspace(0.0, 1.0, 11):
            law = NoiseLaw(NoiseBasis.REPLICATES, share=float(share), reference=reference, u_floor=u_floor)
            weights = law.weights(curve)
            spread = weights.max() / weights.min()
            if share == 1.0:
                assert spread == pytest.approx(bound, rel=1e-12)
            else:
                assert spread < bound
            if share > 0.0 and u_floor > 0.0:
                below = u <= u_floor
                assert np.all(weights[below] == 1.0 / ((1.0 - share) + share * u_floor))


def test_constant_noise_at_a_near_zero_point_does_not_pull_the_share_to_one(gda_clean):
    """With many replicates, the widest weights are reached only when the noise really is proportional that far down.

    The GDA titration's first point is 0.4 % of the signal range, so a share of
    one would give it 5×10⁴ times the weight of the top point. Under constant
    noise the estimator does not go there: that point's whitened scatter would
    then stand out by the same factor, which the objective charges as a squared
    log. With two or three replicates the share is one noisy reading and can
    land near 1 all the same.
    """
    curve = gda_clean[1].magnitude
    law = noise_law(_replicates(curve, np.full(curve.size, 0.02 * np.ptp(curve)), seed=4))
    assert law.share < 0.5
    assert law.weights(curve).max() / law.weights(curve).min() < 10.0


def test_the_reported_level_is_the_variance_the_data_were_drawn_with(gda_clean):
    """What ``floor`` and ``proportional`` claim, at the replicate count a real experiment has.

    The level comes from the mean of ``log t_i``, which is biased low by the
    mean of a log chi-square; at four replicates the correction is a factor
    1.45, so a level read without it would be a third too small. Averaged over
    150 datasets — geometrically, because the estimate is unbiased in the log —
    the variance the law states at the rms signal is the one the data were
    drawn with.
    """
    curve = gda_clean[1].magnitude
    sd = 0.02 * np.ptp(curve)
    rng = np.random.default_rng(11)
    laws = [noise_law(curve + sd * rng.standard_normal((4, curve.size))) for _ in range(150)]
    level = np.array([law.floor**2 + (law.proportional * law.reference) ** 2 for law in laws])
    assert np.exp(np.mean(np.log(level))) == pytest.approx(sd**2, rel=0.15)


def test_the_law_round_trips_through_a_results_file():
    """A results file is JSON without NaN or infinity, and what it holds reads back as the same law."""
    laws = (
        NoiseLaw(
            NoiseBasis.REPLICATES,
            share=0.37,
            floor=890.4,
            proportional=0.011,
            reference=4.2e4,
            n_replicates=8,
            u_floor=0.0123,
        ),
        NoiseLaw(NoiseBasis.SINGLE_TITRATION),
        NoiseLaw(NoiseBasis.TOO_FEW_POINTS, n_replicates=3),
    )
    for law in laws:
        written = law.to_dict()
        assert written['basis'] == law.basis.value
        assert written['u_floor'] == law.u_floor
        assert NoiseLaw.from_dict(json.loads(json.dumps(written, allow_nan=False))) == law
    # A results file that holds no floor on u reads as no floor.
    written = laws[0].to_dict()
    del written['u_floor']
    assert NoiseLaw.from_dict(written).u_floor == 0.0


def test_the_level_is_the_variance_at_the_rms_signal():
    """``floor² + (proportional·reference)²``: the constant and the proportional part at the reference signal."""
    law = NoiseLaw(NoiseBasis.REPLICATES, share=0.37, floor=890.4, proportional=0.011, reference=4.2e4)
    assert law.level == pytest.approx(890.4**2 + (0.011 * 4.2e4) ** 2, rel=1e-15)


def test_the_law_is_described_in_one_sentence():
    """The five sentences the summary, the report and the CSV carry, to two digits."""
    scatter = '(scatter of 8 replicates about the curve)'
    mixed = NoiseLaw(
        NoiseBasis.REPLICATES, share=0.37, floor=890.4, proportional=0.011, reference=4.2e4, n_replicates=8
    )
    assert mixed.describe() == f'about 1.1 % of the signal plus 890 a.u. {scatter}'
    constant = NoiseLaw(NoiseBasis.REPLICATES, share=0.0, floor=2287.0, reference=4.2e4, n_replicates=8)
    assert constant.describe() == f'constant, about 2300 a.u. {scatter}'
    proportional = NoiseLaw(NoiseBasis.REPLICATES, share=1.0, proportional=0.0204, reference=4.2e4, n_replicates=8)
    assert proportional.describe() == f'proportional to the signal, about 2.0 % of it {scatter}'
    # Written out in full at any magnitude: a normalised signal has a small floor.
    small = NoiseLaw(NoiseBasis.REPLICATES, share=0.0, floor=1.52e-5, reference=1.0, n_replicates=8)
    assert small.describe() == f'constant, about 0.000015 a.u. {scatter}'
    assert NoiseLaw(NoiseBasis.SINGLE_TITRATION).describe() == (
        'taken as constant — one titration cannot show how the noise varies with the signal.'
    )
    assert NoiseLaw(NoiseBasis.TOO_FEW_POINTS, n_replicates=3).describe() == (
        'taken as constant — the replicates scatter at too few titration points to show how it varies.'
    )


def test_replicate_scatter_removes_the_affine_part_of_every_replicate(gda_clean):
    """What is left scatters about the mean curve and carries nothing the model could have followed.

    The residuals sum to zero over the replicates — the mean is one of the two
    directions removed — and are orthogonal to both whitened columns, so no
    offset and no scale factor survives in them.
    """
    curve = gda_clean[1].magnitude
    signals = _replicates(curve, 0.02 * curve, m=5, scale=0.05, offset=0.01, seed=2)
    weights = 1.0 / (0.3 + 0.7 * curve**2 / np.mean(curve**2))
    residuals, leverage = replicate_scatter(signals, weights)
    assert residuals.shape == signals.shape
    scale = np.abs(residuals).max()
    assert residuals.sum(axis=0) == pytest.approx(np.zeros(curve.size), abs=1e-9 * scale)
    columns = np.column_stack([np.ones(curve.size), signals.mean(axis=0)]) * np.sqrt(weights)[:, np.newaxis]
    assert residuals @ columns == pytest.approx(np.zeros((5, 2)), abs=1e-9 * scale * np.abs(columns).max())
    # Two directions are removed from n points, wherever they sit.
    assert leverage.sum() == pytest.approx(2.0)
    assert ((leverage > 0.0) & (leverage <= 1.0)).all()


def test_replicate_scatter_refuses_data_that_has_no_scatter_to_read(gda_clean):
    """Fail-fast contracts: too few replicates, too few points, a mean that does not vary, mismatched weights."""
    curve = gda_clean[1].magnitude
    signals = _replicates(curve, 0.02 * curve, m=4, seed=5)
    with pytest.raises(ValueError, match=f'{MIN_REPLICATES} or more replicates'):
        replicate_scatter(signals[:1])
    with pytest.raises(ValueError, match='3 or more titration points'):
        replicate_scatter(signals[:, :2])
    with pytest.raises(ValueError, match='same at every titration point'):
        replicate_scatter(np.tile(np.full(curve.size, 7.0), (3, 1)))
    with pytest.raises(ValueError, match='one value per titration point'):
        replicate_scatter(signals, np.ones(curve.size - 1))
