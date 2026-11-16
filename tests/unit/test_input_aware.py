"""Input-aware Ka interval — scientific behaviour tests.

The entered inputs of a fit (concentrations, a carried-over binding constant,
the titrant series) become nuisance parameters held by the uncertainty the user
states for them, and the interval of Ka is cut from the penalised profile
``P(k) = min [n log S + z'z]``. These tests pin what makes it trustworthy:

- with no varying input it IS the fixed-input interval, and with vanishing
  uncertainties it converges to it;
- a profile value equals an independently written objective minimised by a
  different algorithm (Nelder-Mead from seeded random starts on a
  species-function + BVLS residual), for one and two binding constants;
- the closed edges lie on the F-test threshold of that independent objective,
  and the cut-off of a profile point counts the signal parameters its own
  solution holds on a bound;
- a repeat is bit-identical and an edge does not depend on the side root
  finding walks the bracket from; a loading that hands the offsets through is
  the fit without one, bit for bit, and a shared source moves every input it
  loads by the product of their sources, against the independent objective;
- a planted entry error is recovered as a shift of that input, the truth lies
  inside the input-aware interval and outside the fixed-input one; an input
  stated as a range stays inside it and is reported on its edge when the truth
  lies beyond, where it is held and absorbs nothing of the other inputs;
- at vanishing uncertainty a search cell is read as the fixed-input interval
  reads it: an accepted stretch and a gap that lie inside one cell are found,
  against an independent fixed-input profile; a node solved into the shallower
  of two input basins does not cut the interval short; a binding constant whose
  minimum lies on its bound is put there and not counted as fitted;
- a Ka the model cannot be solved at opens the interval the way the fixed-input
  one does; too few points and a stop request are refused in plain language;
- a design effect of one changes no bit; a larger one widens the acceptance
  excess to ``n log(1 + kappa m F / nu)``, so the closed edges move out onto
  that cut-off of the independent objective, the drawn cut follows it, the
  one-step test is widened with it, and with no varying input the result is
  the fixed-input interval at the same design effect.
"""

import numpy as np
import pytest
from scipy.optimize import brentq, lsq_linear, minimize, minimize_scalar
from scipy.stats import f as f_dist

from core.assays import ASSAY_CLASSES
from core.assays.gda import GDAAssay
from core.assays.ida import IDAAssay
from core.assays.registry import ASSAY_REGISTRY, AssayType
from core.models.equilibrium import (
    dba_signal,
    dba_species,
    gda_signal,
    gda_species,
    h2g_signal,
    h2g_species,
    hg2_species,
    ida_species,
)
from core.pipeline.input_aware import (
    AwareProfile,
    _input_directions,
    at_edge,
    conflict,
    fit_jacobian,
    input_aware,
    input_shifts,
    misfit_design,
    penalised_objective,
)
from core.pipeline.inputs import TITRANT, ErrorModel, InputSpec, SharedSource, constraints, shared_key
from core.pipeline.varpro import (
    LEVEL,
    SECOND_STEP_LEVEL,
    FitCancelled,
    FitRefused,
    Projection,
    _norms,
    _rank,
    on_ka_bound,
)
from core.units import Q_
from tests.conftest import DBA_TRUE, GDA_IDA_RECOVERY_BOUNDS, IDA_TRUE, _make_ida_data
from tests.unit.test_varpro import _ONE_STEP, _grid_projection, _hg2_truth_signal, _stepwise

_IDA_SIGMAS = {'Ka_dye': 0.10, 'h0': 0.03, 'd0': 0.03, TITRANT: 0.03}


def _noisy(y: np.ndarray, frac: float, seed: int) -> np.ndarray:
    return y + np.random.default_rng(seed).normal(0.0, frac * np.ptp(y), y.size)


def _ida(n: int, noise: float, seed: int, *, h0_factor: float = 1.0, ka_box=(1e5, 1e8), point_weights=None):
    """IDA on the conftest truth, the host optionally entered wrong, Ka searched in a narrow box."""
    x, y = _make_ida_data(IDA_TRUE, n_points=n)
    assay = IDAAssay(
        x_data=Q_(x, 'M'),
        y_data=Q_(_noisy(y, noise, seed), 'au'),
        Ka_dye=Q_(IDA_TRUE['Ka_dye'], '1/M'),
        h0=Q_(IDA_TRUE['h0'] * h0_factor, 'M'),
        d0=Q_(IDA_TRUE['d0'], 'M'),
    )
    bounds = {**GDA_IDA_RECOVERY_BOUNDS, 'Ka_guest': (Q_(ka_box[0], '1/M'), Q_(ka_box[1], '1/M'))}
    return assay, Projection(assay, bounds, point_weights=point_weights)


def _sigma_constraints(assay, sigmas: dict):
    return constraints(
        ErrorModel(specs={k: InputSpec.sigma_pct(100 * s) for k, s in sigmas.items()}), assay.get_conditions()
    )


def _aware(assay, projection, sigmas: dict):
    fit = projection.fit()
    return fit, input_aware(projection, fit, _sigma_constraints(assay, sigmas))


@pytest.fixture(scope='module')
def ida_case():
    assay, projection = _ida(15, 0.01, 2)
    fit, result = _aware(assay, projection, _IDA_SIGMAS)
    return assay, projection, fit, result


# ---------------------------------------------------------------------------
# Independent reference: species functions + BVLS + Nelder-Mead
# ---------------------------------------------------------------------------


def _reference_ssr(columns: np.ndarray, y: np.ndarray, lb: np.ndarray, ub: np.ndarray, weights=None) -> float:
    """Best ``sum_i w_i (y_i - (A c)_i)²`` over the coefficient box, by a bounded solve of the whitened problem."""
    root = 1.0 if weights is None else np.sqrt(weights)[:, np.newaxis]
    columns, y = columns * root, y * np.ravel(root)
    norm = np.linalg.norm(columns, axis=0)
    solved = lsq_linear(columns / norm, y, bounds=(lb * norm, ub * norm), method='bvls')
    return float(np.sum((columns @ np.clip(solved.x / norm, lb, ub) - y) ** 2))


def _coefficient_box(projection: Projection):
    return projection._lb, projection._ub


def _reference_minimum(objective, n_coords: int, seed: int, spread: np.ndarray) -> float:
    """Lowest value Nelder-Mead reaches from 20 seeded random starts."""
    rng = np.random.default_rng(seed)
    best = np.inf
    for _ in range(20):
        start = rng.normal(0.0, 1.0, n_coords) * spread
        found = minimize(
            objective, start, method='Nelder-Mead', options={'xatol': 1e-9, 'fatol': 1e-11, 'maxiter': 4000}
        )
        best = min(best, found.fun)
    return float(best)


def _ida_reference(assay, projection, k: float, weights=None) -> float:
    x, y = assay.x_data.magnitude, assay.y_data.magnitude
    lb, ub = _coefficient_box(projection)
    sigma = np.array([_IDA_SIGMAS[key] for key in ('Ka_dye', 'h0', 'd0', TITRANT)])
    entered = np.array([assay.Ka_dye.magnitude, assay.h0.magnitude, assay.d0.magnitude, 1.0])

    def objective(z: np.ndarray) -> float:
        ka_dye, h0, d0, scale = entered * (1.0 + sigma * z)
        species = ida_species(k, ka_dye, h0, d0, scale * x)
        columns = np.column_stack([np.ones(x.size), species['D'], species['HD']])
        return x.size * np.log(_reference_ssr(columns, y, lb, ub, weights)) + float(z @ z)

    return _reference_minimum(objective, 4, seed=11, spread=np.ones(4))


def test_a_profile_value_is_the_minimum_an_independent_objective_and_algorithm_find(ida_case):
    """IDA, four varying inputs: at the estimate and at a node outside the interval (the edges follow below)."""
    assay, projection, _, result = ida_case
    profile = result.profiles['Ka_guest']
    assert profile.grid[0] < profile.interval.low
    for ka in (result.fit.ka['Ka_guest'], float(profile.grid[0])):
        engine = float(profile.objective[np.flatnonzero(profile.grid == ka)[0]])
        assert engine == pytest.approx(_ida_reference(assay, projection, ka), abs=1e-6)


def test_closed_edges_lie_on_the_f_test_threshold_of_the_independent_objective(ida_case):
    assay, projection, _, result = ida_case
    profile = result.profiles['Ka_guest']
    n, p = assay.n_points, result.fit.n_params
    # Free plus bound dye sum to the dye total, collinear with the offset: rank 2, and one Ka.
    assert p == 3
    # The four inputs take up part of the residual degrees of freedom, less than one each.
    dof = profile.interval.dof
    assert n - p - 4 < dof < n - p
    excess = n * np.log(1 + f_dist.ppf(LEVEL, 1, dof) / dof)
    assert profile.threshold == pytest.approx(result.fit.objective + excess, rel=1e-12)
    for edge in (profile.interval.low, profile.interval.high):
        assert _ida_reference(assay, projection, edge) == pytest.approx(profile.threshold, rel=1e-6)
    assert profile.interval.level == LEVEL


def test_the_cut_off_of_a_profile_point_counts_the_signal_parameters_its_own_solution_pins(ida_case):
    assay, projection, _, result = ida_case
    profile = result.profiles['Ka_guest']
    x, y = assay.x_data.magnitude, assay.y_data.magnitude
    lb, ub = _coefficient_box(projection)
    entered = {'Ka_dye': assay.Ka_dye.magnitude, 'h0': assay.h0.magnitude, 'd0': assay.d0.magnitude, TITRANT: 1.0}

    def fitted(ka: float, offsets: dict) -> int:
        """Rank of the columns an independent bounded solve at the moved inputs leaves inside their bounds."""
        moved = {key: value * (1.0 + offsets[key]) for key, value in entered.items()}
        species = ida_species(ka, moved['Ka_dye'], moved['h0'], moved['d0'], moved[TITRANT] * x)
        columns = np.column_stack([np.ones(x.size), species['D'], species['HD']])
        norm = np.linalg.norm(columns, axis=0)
        solved = lsq_linear(columns / norm, y, bounds=(lb * norm, ub * norm), method='bvls')
        inside = (solved.x > lb * norm) & (solved.x < ub * norm)
        return int(np.linalg.matrix_rank((columns / norm)[:, inside])) if inside.any() else 0

    n, dof = assay.n_points, profile.interval.dof
    best = fitted(result.fit.ka['Ka_guest'], result.fit.offsets)
    given_up = set()
    for at in (0, int(np.argmin(profile.objective)), profile.grid.size - 1):
        offsets = dict(zip(result.fit.constraint_keys, profile.offsets[at]))
        m = 1 + max(0, best - fitted(float(profile.grid[at]), offsets))
        given_up.add(m)
        excess = n * np.log(1 + m * f_dist.ppf(LEVEL, m, dof) / dof)
        assert profile.cut[at] == pytest.approx(result.fit.objective + excess, rel=1e-12)
    # At the ends of the Ka box the signal parameters run into their bounds; at the estimate none does.
    assert given_up == {1, 2, 3}
    assert profile.cut.min() == profile.threshold


def test_dba_profile_value_matches_the_independent_minimum():
    """DBA dye-to-host, two varying inputs (the fixed host and the titrant)."""
    sigmas = {'fixed_conc': 0.03, TITRANT: 0.03}
    x = np.linspace(5e-7, 4e-5, 14)
    truth = dict(I0=DBA_TRUE['I0'], I_dye_free=DBA_TRUE['I_dye_free'], I_dye_bound=DBA_TRUE['I_dye_bound'])
    y = dba_signal(Ka_dye=DBA_TRUE['Ka_dye'], x_titrant=x, y_fixed=1e-5, mode='DtoH', **truth)
    assay = ASSAY_CLASSES[AssayType.DBA_DtoH](
        x_data=Q_(x, 'M'), y_data=Q_(_noisy(y, 0.01, 4), 'au'), fixed_conc=Q_(1.02e-5, 'M'), mode='DtoH'
    )
    bounds = {**ASSAY_REGISTRY[AssayType.DBA_DtoH].default_bounds, 'Ka_dye': (Q_(1e4, '1/M'), Q_(1e7, '1/M'))}
    projection = Projection(assay, bounds)
    _, result = _aware(assay, projection, sigmas)
    lb, ub = _coefficient_box(projection)
    sigma = np.array([0.03, 0.03])
    profile = result.profiles['Ka_dye']

    def reference(k: float) -> float:
        def objective(z: np.ndarray) -> float:
            fixed, scale = np.array([1.02e-5, 1.0]) * (1.0 + sigma * z)
            species = dba_species(k, scale * x, fixed, mode='DtoH')
            columns = np.column_stack([np.ones(x.size), species['D'], species['HD']])
            return x.size * np.log(_reference_ssr(columns, assay.y_data.magnitude, lb, ub)) + float(z @ z)

        return _reference_minimum(objective, 2, seed=12, spread=np.ones(2))

    for ka in (result.fit.ka['Ka_dye'], profile.interval.high):
        engine = float(profile.objective[np.flatnonzero(profile.grid == ka)[0]])
        assert engine == pytest.approx(reference(ka), abs=1e-6)


@pytest.fixture(scope='module')
def hg2_case():
    h0 = 1e-5
    x = np.linspace(0.0, 1e-4, 20)
    y = _noisy(_hg2_truth_signal(x, h0, 1e6, 1e5), 0.01, 1)
    assay = ASSAY_CLASSES[AssayType.DBA_HG2](x_data=Q_(x, 'M'), y_data=Q_(y, 'au'), h0=Q_(1.03 * h0, 'M'))
    box = (Q_(1e4, '1/M'), Q_(1e7, '1/M'))
    projection = Projection(assay, {**ASSAY_REGISTRY[AssayType.DBA_HG2].default_bounds, 'Ka_HG': box, 'Ka_HG2': box})
    fit, result = _aware(assay, projection, {'h0': 0.03, TITRANT: 0.03})
    return assay, projection, fit, result


def test_two_ka_profile_value_matches_the_independent_minimum_over_the_other_ka_and_the_inputs(hg2_case):
    assay, projection, fit, result = hg2_case
    x, y = assay.x_data.magnitude, assay.y_data.magnitude
    lb, ub = _coefficient_box(projection)
    free = lb != ub
    profile = result.profiles['Ka_HG']
    assert not profile.interval.open_high
    k = profile.interval.high
    at = int(np.flatnonzero(profile.grid == k)[0])
    other_hat = np.log10(profile.other_ka[at])

    def objective(v: np.ndarray) -> float:
        h0 = assay.h0.magnitude * (1.0 + 0.03 * v[1])
        species = hg2_species(k, 10.0 ** (other_hat + v[0]), h0, (1.0 + 0.03 * v[2]) * x)
        columns = np.column_stack([np.ones(x.size), species['G'], species['H'], species['HG'], species['HG2']])
        return x.size * np.log(_reference_ssr(columns[:, free], y, lb[free], ub[free])) + float(v[1:] @ v[1:])

    reference = _reference_minimum(objective, 3, seed=13, spread=np.array([0.5, 1.0, 1.0]))
    assert float(profile.objective[at]) == pytest.approx(reference, abs=1e-6)
    assert float(profile.objective[at]) == pytest.approx(profile.threshold, rel=1e-6)


def test_two_ka_fit_is_never_worse_than_the_fit_at_the_entered_inputs(hg2_case):
    assay, _, fit, result = hg2_case
    assert result.fit.objective <= assay.n_points * np.log(fit.objective) + 1e-9
    for key, profile in result.profiles.items():
        assert profile.threshold == result.profiles['Ka_HG'].threshold
        assert profile.interval.low <= result.fit.ka[key] <= profile.interval.high
        assert np.nanmin(profile.objective) >= result.fit.objective - 1e-9


def test_with_a_clear_second_step_the_input_aware_interval_keeps_its_lower_limit(hg2_case):
    _, _, _, result = hg2_case
    second = result.profiles['Ka_HG2'].interval
    assert second.one_step_p < SECOND_STEP_LEVEL and not second.open_low
    assert result.profiles['Ka_HG'].interval.one_step_p is None


def test_without_a_second_step_the_input_aware_interval_opens_below_with_the_conditional_one():
    """The one-step test on the penalised profile: the model without the second step, its objective minimised over
    the first constant and the inputs, judged against the optimum by the rule that cuts the interval."""
    box = (Q_(1e2, '1/M'), Q_(1e8, '1/M'))
    projection, key = _stepwise(AssayType.DBA_HG2, 1e5, 0.1, 10, _ONE_STEP[AssayType.DBA_HG2], Ka_HG=box, Ka_HG2=box)
    assay, fit = projection.assay, projection.fit()
    conditional = projection.interval(key, fit)
    sigmas = {'h0': 0.03, TITRANT: 0.03}
    result = input_aware(projection, fit, _sigma_constraints(assay, sigmas), conditional={key: conditional})
    aware = result.profiles[key].interval
    assert conditional.open_low and aware.open_low
    assert (aware.low, aware.limited_by_low) == (1e2, '')

    # P(0) of the independent objective, from the first constant where the fixed-input fit without the second
    # step puts it.
    x, y = assay.x_data.magnitude, assay.y_data.magnitude
    centre = np.log10(projection.profile_point(key, 0.0)[0]['Ka_HG'])

    def solve(v: np.ndarray) -> tuple[float, int]:
        h0 = assay.h0.magnitude * (1.0 + 0.03 * v[1])
        species = hg2_species(10.0 ** (centre + v[0]), 0.0, h0, (1.0 + 0.03 * v[2]) * x)
        columns = np.column_stack([np.ones(x.size), species['G'], species['HG']])
        norm = np.linalg.norm(columns, axis=0)
        found = lsq_linear(columns / norm, y, bounds=(0.0, np.inf), method='bvls')
        ssr = float(np.sum((columns @ (found.x / norm) - y) ** 2))
        return x.size * np.log(ssr) + float(v[1:] @ v[1:]), int(np.count_nonzero(found.active_mask == 0))

    rng = np.random.default_rng(17)
    starts = rng.normal(0.0, 1.0, (20, 3)) * np.array([0.5, 1.0, 1.0])
    options = {'xatol': 1e-9, 'fatol': 1e-11, 'maxiter': 4000}
    zero = min((minimize(lambda v: solve(v)[0], start, method='Nelder-Mead', options=options) for start in starts),
               key=lambda found: found.fun)  # fmt: skip
    # The optimum fits every free signal coefficient (offset, guest, both complexes); without the second step
    # the coefficient of the second complex has nothing to fit.
    lb, ub = _coefficient_box(projection)
    free = lb != ub
    inside = int(
        np.count_nonzero((result.fit.coefficients[free] > lb[free]) & (result.fit.coefficients[free] < ub[free]))
    )
    m = 1 + inside - solve(zero.x)[1]
    nu = aware.dof
    expected = f_dist.sf(np.expm1((zero.fun - result.fit.objective) / x.size) * nu / m, m, nu)
    assert aware.one_step_p == pytest.approx(expected, rel=1e-3)
    assert aware.one_step_p > SECOND_STEP_LEVEL


def test_with_the_first_constant_held_the_input_aware_interval_is_judged_by_the_one_step_test_too():
    """The H2G titration without a second step whose profile alone closes the second constant below."""
    held = Q_(1e5, '1/M')
    projection, key = _stepwise(AssayType.DBA_H2G, 1e5, 0.1, 10, _ONE_STEP[AssayType.DBA_H2G], Ka_HG=(held, held))
    fit = projection.fit()
    conditional = projection.interval(key, fit)
    result = input_aware(
        projection, fit, _sigma_constraints(projection.assay, {'h0': 0.03}), conditional={key: conditional}
    )
    aware = result.profiles[key].interval
    assert conditional.one_step_p > SECOND_STEP_LEVEL and aware.one_step_p > SECOND_STEP_LEVEL
    assert conditional.open_low and aware.open_low and aware.low == 1e-8


# ---------------------------------------------------------------------------
# Reduction to the fixed-input interval
# ---------------------------------------------------------------------------


def test_with_no_varying_input_the_result_is_the_fixed_input_fit_and_its_own_interval_objects():
    assay, projection = _ida(15, 0.02, 5)
    fit = projection.fit()
    conditional = {'Ka_guest': projection.interval('Ka_guest', fit)}
    result = input_aware(projection, fit, (), conditional=conditional)
    assert result.profiles['Ka_guest'].interval is conditional['Ka_guest']
    assert result.fit.ka == fit.ka and result.fit.offsets == {} and result.fit.jacobian.shape == (15, 1)
    assert np.array_equal(result.fit.coefficients, fit.coefficients[0])
    assert result.fit.objective == pytest.approx(15 * np.log(fit.objective), rel=1e-14)
    assert result.fit.n_params == projection.n_params(fit)
    # Without the caller's intervals the same ones are computed.
    assert input_aware(projection, fit, ()).profiles['Ka_guest'].interval == conditional['Ka_guest']
    assert conflict(result) is None and input_shifts(result) == {}
    # A spec that does not vary is no constraint at all.
    assert constraints(ErrorModel(specs={'h0': InputSpec.sigma_pct(0.0)}), assay.get_conditions()) == ()


def test_with_no_varying_input_and_a_design_effect_the_result_is_the_fixed_input_interval_at_that_effect():
    assay, projection = _ida(15, 0.02, 5)
    fit = projection.fit()
    n = assay.n_points
    plain = projection.interval('Ka_guest', fit)
    widened = projection.interval('Ka_guest', fit, inflation=2.0)
    assert widened.low < plain.low and plain.high < widened.high
    # An interval cut at another design effect is not handed back: the one at the effect asked for is.
    result = input_aware(projection, fit, (), conditional={'Ka_guest': plain}, inflation={'Ka_guest': 2.0})
    profile = result.profiles['Ka_guest']
    assert profile.interval == widened and profile.interval.inflation == 2.0
    assert profile.threshold == pytest.approx(n * np.log(projection.threshold(fit, inflation=2.0)), rel=1e-14)
    assert profile.threshold > n * np.log(projection.threshold(fit))
    # One cut at the effect asked for is the object returned.
    again = input_aware(projection, fit, (), conditional={'Ka_guest': widened}, inflation={'Ka_guest': 2.0})
    assert again.profiles['Ka_guest'].interval is widened


def test_a_design_effect_of_one_is_the_fit_without_one_to_the_last_bit(ida_case):
    _, _, _, plain = ida_case
    assay, projection = _ida(15, 0.01, 2)
    one = input_aware(projection, projection.fit(), _sigma_constraints(assay, _IDA_SIGMAS), inflation={'Ka_guest': 1.0})
    assert one.fit.ka == plain.fit.ka and one.fit.objective == plain.fit.objective
    a, b = plain.profiles['Ka_guest'], one.profiles['Ka_guest']
    assert a.interval == b.interval and a.threshold == b.threshold
    assert np.array_equal(a.grid, b.grid) and np.array_equal(a.objective, b.objective)
    assert np.array_equal(a.cut, b.cut)


def test_a_design_effect_moves_the_closed_edges_out_onto_the_widened_cut_off_of_the_independent_objective(ida_case):
    assay, projection, fit, plain = ida_case
    n = assay.n_points
    result = input_aware(projection, fit, _sigma_constraints(assay, _IDA_SIGMAS), inflation={'Ka_guest': 2.0})
    profile, before = result.profiles['Ka_guest'], plain.profiles['Ka_guest'].interval
    interval = profile.interval
    # The optimum and its degrees of freedom are those of the fit without the design effect.
    assert result.fit.objective == pytest.approx(plain.fit.objective, abs=1e-9)
    assert interval.dof == pytest.approx(before.dof, rel=1e-9) and interval.inflation == 2.0
    assert interval.low < before.low and before.high < interval.high
    assert not (interval.open_low or interval.open_high)
    excess = n * np.log1p(2.0 * f_dist.ppf(LEVEL, 1, interval.dof) / interval.dof)
    assert profile.threshold == pytest.approx(result.fit.objective + excess, rel=1e-12)
    # The drawn cut is that threshold wherever the solution pins nothing the optimum fits, and never below it.
    assert profile.cut.min() == profile.threshold
    for edge in (interval.low, interval.high):
        assert _ida_reference(assay, projection, edge) == pytest.approx(profile.threshold, rel=1e-6)


def test_a_design_effect_widens_the_input_aware_one_step_test_with_its_cut_off():
    """The weak second step of the fixed-input test, the first constant held and the host free within 3 %.

    The rise to the model without the second step is one and the same at both design effects; judged by the
    F tail of that rise divided by the effect, the data reject the one-step model at 0.005 under the plain cut-off
    and no longer under the cut-off widened by 2, where the lower side opens at the bound with the fixed-input one.
    """
    held = Q_(1e5, '1/M')
    projection, key = _stepwise(AssayType.DBA_HG2, 1e5, 2e4, 10, 0, Ka_HG=(held, held))
    fit = projection.fit()
    cons = _sigma_constraints(projection.assay, {'h0': 0.03})
    plain, wide = (input_aware(projection, fit, cons, inflation={key: kappa}).profiles[key] for kappa in (1.0, 2.0))
    nu = plain.interval.dof
    assert wide.interval.dof == nu
    # At zero the solve pins no signal parameter the optimum fits (the fixed-input test's two solves say so), so
    # one parameter is given up and F(1, nu) is the reference.
    rise = [f_dist.isf(profile.interval.one_step_p, 1, nu) * kappa for profile, kappa in ((plain, 1.0), (wide, 2.0))]
    assert rise[1] == pytest.approx(rise[0], rel=1e-9)
    assert plain.interval.one_step_p < SECOND_STEP_LEVEL < wide.interval.one_step_p
    assert not plain.interval.open_low
    assert (wide.interval.open_low, wide.interval.low) == (True, 1e-8)
    assert projection.interval(key, fit, inflation=2.0).open_low


def test_weights_of_exactly_one_are_the_fit_without_weights_to_the_last_bit():
    """A titration with no replicates behind it is fitted with weights of one, and nothing may move.

    The whole input-aware path — the objective, the residual where the model
    has no solution, the scale, the effective degrees of freedom and the
    interval — has to come back with the numbers it had before there were any
    weights.
    """
    assay, plain = _ida(12, 0.02, 5)
    _, ones = _ida(12, 0.02, 5, point_weights=np.ones(12))

    without = input_aware(plain, plain.fit(), _sigma_constraints(assay, _IDA_SIGMAS))
    with_ones = input_aware(ones, ones.fit(), _sigma_constraints(assay, _IDA_SIGMAS))

    assert with_ones.fit.ka == without.fit.ka
    assert with_ones.fit.offsets == without.fit.offsets
    assert with_ones.fit.objective == without.fit.objective
    assert np.array_equal(with_ones.fit.coefficients, without.fit.coefficients)
    assert with_ones.profiles['Ka_guest'].interval == without.profiles['Ka_guest'].interval


def test_a_weighted_profile_value_is_the_minimum_of_the_independent_weighted_objective():
    """With point weights the penalised objective is ``n log S_w + z'z``, and nothing of it is left unweighted.

    The independent objective is the same four inputs moved by hand, the
    species solved by the model's own function and the coefficients by a
    bounded solve of the whitened problem, minimised by Nelder-Mead from
    seeded random starts.
    """
    assay, _ = _ida(12, 0.02, 5)
    signal = assay.y_data.magnitude
    # The weights of a purely proportional noise law: the low end of the
    # titration is the precise end, by a factor of fifteen here.
    weights = np.mean(signal**2) / signal**2
    assert weights.max() > 10 * weights.min()
    _, projection = _ida(12, 0.02, 5, point_weights=weights)

    result = input_aware(projection, projection.fit(), _sigma_constraints(assay, _IDA_SIGMAS))

    profile = result.profiles['Ka_guest']
    for ka in (result.fit.ka['Ka_guest'], float(profile.grid[0])):
        engine = float(profile.objective[np.flatnonzero(profile.grid == ka)[0]])
        assert engine == pytest.approx(_ida_reference(assay, projection, ka, weights), abs=1e-6)
    # The unweighted objective is a different number, so the weights really reached it.
    assert engine != pytest.approx(_ida_reference(assay, projection, ka), abs=1e-3)


def test_vanishing_uncertainties_converge_to_the_fixed_input_profile_and_interval():
    assay, projection = _ida(15, 0.02, 5)
    fit = projection.fit()
    conditional = projection.interval('Ka_guest', fit)
    fixed_profile = projection.profile('Ka_guest')
    n = assay.n_points

    def gap(sigma: float, ka: float) -> float:
        cons = _sigma_constraints(assay, {key: sigma for key in _IDA_SIGMAS})
        return (
            n * np.log(fixed_profile(ka))
            - penalised_objective(projection, {'Ka_guest': ka}, cons, {}, other_ka=None)[0]
        )

    # The profile itself: what the inputs can buy shrinks with the square of their uncertainty.
    for ka in (conditional.low, fit.ka['Ka_guest'] * 1.3):
        coarse, fine = gap(1e-3, ka), gap(1e-5, ka)
        assert 0 < fine < 1e-6
        assert coarse / fine == pytest.approx(1e4, rel=0.05)
        assert 0 <= gap(1e-7, ka) < 1e-9

    result = input_aware(projection, fit, _sigma_constraints(assay, {key: 1e-7 for key in _IDA_SIGMAS}))
    aware = result.profiles['Ka_guest'].interval
    # Both edges are roots at a tolerance of 1e-7 decades, found in different brackets.
    assert abs(np.log10(aware.low / conditional.low)) < 2e-7
    assert abs(np.log10(aware.high / conditional.high)) < 2e-7
    assert abs(np.log10(result.fit.ka['Ka_guest'] / fit.ka['Ka_guest'])) < 2e-7
    assert (aware.open_low, aware.open_high, aware.split) == (False, False, False)
    assert aware.dof == pytest.approx(conditional.dof, abs=1e-6)


def _independent_one_ka_excess(projection: Projection, species_of, ks) -> np.ndarray:
    """The fixed-input profile of a one-Ka model minus its own F cut-off, from species functions and BVLS alone.

    The offset and the free and bound dye coefficients are solved in their bounds at every Ka of a 64-per-decade
    scan, refined at its best point; ``m`` is one plus the rank of the columns the best fit leaves inside their
    bounds that the solve at a tested Ka does not, and ``n - p`` that of the best fit.
    """
    y = projection.signals[0]
    lb, ub = _coefficient_box(projection)

    def solve(k: float) -> tuple[float, int]:
        species = species_of(k)
        columns = np.column_stack([np.ones(y.size), species['D'], species['HD']])
        norm = np.linalg.norm(columns, axis=0)
        found = lsq_linear(columns / norm, y, bounds=(lb * norm, ub * norm), method='bvls')
        inside = found.active_mask == 0
        rank = int(np.linalg.matrix_rank((columns / norm)[:, inside])) if inside.any() else 0
        return float(np.sum((columns @ np.clip(found.x / norm, lb, ub) - y) ** 2)), rank

    (lo, hi), = projection.ka_bounds.values()  # fmt: skip
    scan = np.geomspace(lo, hi, int(np.log10(hi / lo) * 64) + 1)
    i = int(np.argmin([solve(k)[0] for k in scan]))
    found = minimize_scalar(
        lambda t: solve(10.0**t)[0],
        bounds=(np.log10(scan[max(i - 1, 0)]), np.log10(scan[min(i + 1, scan.size - 1)])),
        method='bounded',
        options={'xatol': 1e-10},
    )
    best, best_rank = solve(10.0**found.x)
    dof = y.size - 1 - best_rank

    def excess(k: float) -> float:
        ssr, rank = solve(k)
        m = 1 + max(0, best_rank - rank)
        return ssr - best * (1.0 + m * f_dist.ppf(LEVEL, m, dof) / dof)

    return np.array([excess(k) for k in ks])


def _vanishing(projection: Projection, keys) -> tuple:
    """The fixed-input fit and interval of a one-Ka projection, and its input-aware interval at a sigma of 1e-5 %."""
    fit = projection.fit()
    ((key, _),) = projection.ka_bounds.items()
    conditional = projection.interval(key, fit)
    tiny = constraints(
        ErrorModel(specs={k: InputSpec.sigma_pct(1e-5) for k in keys}), projection.assay.get_conditions()
    )
    return conditional, input_aware(projection, fit, tiny, conditional={key: conditional}).profiles[key].interval


def test_an_accepted_stretch_inside_one_search_cell_extends_the_interval_as_far_as_the_fixed_input_one():
    """Dye-to-host DBA, twelve points at 3 % noise, true Ka 2.2×10⁶ M⁻¹.

    Below the estimate the cut-off steps up where a signal coefficient reaches its bound, so the test accepts Ka
    down to 7.4×10⁴ M⁻¹, a stretch that starts and ends between two search-grid nodes the test rejects. Read at the
    nodes alone the lower edge closes at 9.5×10⁴ M⁻¹; read as the fixed-input interval reads it, the vanishing-σ
    interval holds every Ka the independent profile accepts.
    """
    x = np.linspace(1e-7, 5e-5, 12)
    y = dba_signal(I0=0.0, Ka_dye=2154904.336304565, I_dye_free=5e7, I_dye_bound=3e8, x_titrant=x, y_fixed=1e-5,
                   mode='DtoH')  # fmt: skip
    assay = ASSAY_CLASSES[AssayType.DBA_DtoH](
        x_data=Q_(x, 'M'), y_data=Q_(_noisy(y, 0.03, 494788571), 'au'), fixed_conc=Q_(1e-5, 'M'), mode='DtoH'
    )
    projection = Projection(assay, ASSAY_REGISTRY[AssayType.DBA_DtoH].default_bounds)
    conditional, aware = _vanishing(projection, ('fixed_conc', TITRANT))

    accepted = np.geomspace(7.7e4, 8.9e4, 4)
    assert (_independent_one_ka_excess(projection, lambda k: dba_species(k, x, 1e-5, mode='DtoH'), accepted) < 0).all()
    assert aware.low < accepted[0] and not aware.open_low
    assert abs(np.log10(aware.low / conditional.low)) < 2e-7


def test_a_gap_inside_one_search_cell_is_reported_as_the_fixed_input_interval_reports_it():
    """GDA, eight points at 0.5 % noise, true Ka 1.3×10⁴ M⁻¹: the profile rejects Ka about 4.5×10⁵ M⁻¹ between two
    stretches it accepts, all of it inside one search cell."""
    x = np.linspace(1e-7, 3e-5, 8)
    y = gda_signal(I0=0.0, Ka_guest=13435.076103099427, I_dye_free=5e7, I_dye_bound=3e8, Ka_dye=5e5, h0=1e-5,
                   d0_values=x, g0=2e-5)  # fmt: skip
    assay = GDAAssay(
        x_data=Q_(x, 'M'), y_data=Q_(_noisy(y, 0.005, 857474922), 'au'), Ka_dye=Q_(5e5, '1/M'), h0=Q_(1e-5, 'M'),
        g0=Q_(2e-5, 'M'),
    )  # fmt: skip
    projection = Projection(assay, ASSAY_REGISTRY[AssayType.GDA].default_bounds)
    conditional, aware = _vanishing(projection, ('h0', 'g0', TITRANT))

    ks = (3.98e5, 4.47e5, 5.01e5)
    excess = _independent_one_ka_excess(projection, lambda k: gda_species(k, 5e5, 1e-5, x, 2e-5), ks)
    assert excess[0] < 0 < excess[1] and excess[2] < 0
    assert aware.split and aware.high > ks[2]
    assert abs(np.log10(aware.high / conditional.high)) < 2e-7


def test_an_accepted_stretch_past_a_step_of_the_cut_off_is_inside_the_input_aware_interval_too():
    """Dye-to-host DBA of the reference-agreement grid (K₂ h0 of 0.1, eight points, 1 % noise, seed 32).

    Past the upper edge of the stretch around the estimate the fit puts a signal coefficient on its bound, the
    cut-off steps up, and the test accepts Ka from 10^5.874 to 10^5.889 again, 0.35 decade further out and between
    two search-grid nodes it rejects. The independent fixed-input profile accepts that stretch; at a vanishing σ the
    input-aware interval reaches as far as the fixed-input one.
    """
    projection = _grid_projection('DBA_DtoH,K=0.1,n=8,noise=0.01', 32)
    assay = projection.assay
    index = assay.parameter_keys.index('Ka_dye')

    def species_of(k: float) -> dict:
        params = np.zeros(len(assay.parameter_keys))
        params[index] = k
        return assay.species(params)

    conditional, aware = _vanishing(projection, ('fixed_conc', TITRANT))
    accepted = 10.0 ** np.array([5.876, 5.882, 5.888])
    assert (_independent_one_ka_excess(projection, species_of, accepted) < 0).all()
    assert aware.high > accepted[-1] and not aware.open_high
    assert abs(np.log10(aware.high / conditional.high)) < 2e-7


def test_a_binding_constant_whose_minimum_lies_on_its_bound_is_put_on_it_and_not_counted_as_fitted():
    """A 2:1 titration whose second constant runs to the top of its box.

    The independent fixed-input objective, the first constant minimised, falls all the way to that bound, so the
    minimum lies on it. The trust-region solve of both constants and the inputs keeps its iterates inside the box
    and stops short of it, by more than the resolution a bound is read at; the solve puts the constant on the
    bound, where it is held and not fitted.
    """
    h0, x = 1e-5, np.linspace(0.0, 1e-4, 20)
    y = h2g_signal(I0=100.0, Ka_HG=15271675.297786418, Ka_H2G=19886909.313149683, I_G=1e6, I_H=0.0, I_HG=1e7,
                   I_H2G=5e6, h0=h0, g0_values=x)  # fmt: skip
    assay = ASSAY_CLASSES[AssayType.DBA_H2G](
        x_data=Q_(x, 'M'), y_data=Q_(_noisy(y, 0.005, 52824378), 'au'), h0=Q_(h0, 'M')
    )
    bounds = ASSAY_REGISTRY[AssayType.DBA_H2G].default_bounds
    projection = Projection(assay, bounds)
    lb, ub = _coefficient_box(projection)
    free = lb != ub
    top = projection.ka_bounds['Ka_H2G'][1]

    def lowest(ka_h2g: float) -> float:
        """The independent fixed-input objective at *ka_h2g*, minimised over the first constant near the top."""

        def ssr(t: float) -> float:
            species = h2g_species(10.0**t, ka_h2g, h0, x)
            columns = np.column_stack([np.ones(x.size), species['G'], species['HG'], species['H2G']])
            return _reference_ssr(columns, assay.y_data.magnitude, lb[free], ub[free])

        return minimize_scalar(ssr, bounds=(10.0, 12.0), method='bounded', options={'xatol': 1e-10}).fun

    on_top = lowest(top)
    assert all(on_top <= lowest(top * 10.0**-step) for step in (1e-6, 1e-3, 1e-1))

    fit, result = _aware(assay, projection, {'h0': 1e-5, TITRANT: 1e-5})
    assert on_ka_bound(result.fit.ka['Ka_H2G'], projection.ka_bounds['Ka_H2G'])
    assert result.fit.ssr == pytest.approx(on_top, rel=1e-6)
    # Held there, it is not fitted: the first constant and the four signal columns the solve leaves free.
    assert result.fit.ka_fitted == ('Ka_HG',) and result.fit.n_params == 5


@pytest.mark.parametrize(
    'titration',
    [
        lambda: _stepwise(AssayType.DBA_H2G, 2902916.6898986776, 16416694.18737613, 3, 710983164, n=20, noise=0.02),
        lambda: _stepwise(AssayType.DBA_HG2, 29531.854796112406, 29847.003735592458, 3, 533310309, n=8, noise=0.005),
        lambda: (_grid_projection('DBA_H2G,K=0.1,n=12,noise=0.01', 5), 'Ka_H2G'),
        lambda: (_grid_projection('DBA_HG2,K=1000,n=12,noise=0.01', 273), 'Ka_HG2'),
    ],
    ids=['H2G-n20', 'HG2-n8', 'grid-H2G-n12-far', 'grid-HG2-offset-on-zero'],
)
def test_at_a_vanishing_sigma_both_engines_rest_the_same_constant_on_its_bound(titration):
    """Stepwise titrations whose second constant's objective falls all the way to the top of its box.

    With the inputs known to 0.001 % the input-aware fit is the fixed-input one, so the two must agree on where that
    constant lies — on the bound, held and not fitted — and therefore on ``p``, the degrees of freedom and the
    one-step test; with a different count their intervals of the first constant would differ by tenths of a decade.
    In the third titration the searches stop 4.3 decades short of the bound, along a K₁·K₂ valley the first constant
    follows all the way; in the fourth the minimum also holds the signal offset on zero, which each solve leaves a
    hair inside its bound on the side of the minimiser it stops on.
    """
    projection, second = titration()
    fit = projection.fit()
    conditional = {key: projection.interval(key, fit) for key in projection.free_ka}
    tiny = InputSpec.sigma_pct(1e-3)
    cons = constraints(ErrorModel(specs={'h0': tiny, TITRANT: tiny}), projection.assay.get_conditions())
    result = input_aware(projection, fit, cons, conditional=conditional)

    top = projection.ka_bounds[second][1]
    assert fit.ka[second] == top and result.fit.ka[second] == top
    assert result.fit.n_params == projection.n_params(fit)
    for key, fixed in conditional.items():
        aware = result.profiles[key].interval
        assert aware.dof == pytest.approx(fixed.dof, abs=1e-6)
        assert abs(np.log10(aware.low / fixed.low)) < 1e-3 and abs(np.log10(aware.high / fixed.high)) < 1e-3
    assert result.profiles[second].interval.one_step_p == pytest.approx(conditional[second].one_step_p, rel=1e-3)


def test_the_drawn_profile_is_never_below_the_fixed_input_one_on_the_r2_axis(ida_case):
    """The entered inputs are feasible, so freeing them can only lower the objective."""
    assay, projection, _, result = ida_case
    profile = result.profiles['Ka_guest']
    fixed_profile = projection.profile('Ka_guest')
    ss_tot = float(projection.ss_tot[0])
    for ka, r2 in zip(profile.grid[::3], profile.r2[::3]):
        assert r2 >= 1.0 - fixed_profile(ka) / ss_tot - 1e-12
    inside = (profile.grid > profile.interval.low * 1.001) & (profile.grid < profile.interval.high / 1.001)
    assert np.all(profile.r2[inside] > profile.r2_threshold)
    assert np.all(profile.r2[(profile.grid < profile.interval.low / 1.001)] < profile.r2_threshold)
    # Drawn at 20 per decade through the search-grid cells of the estimate and the edges, which span this interval.
    assert np.max(np.diff(np.log10(profile.grid[inside]))) <= 1 / 20 + 1e-9


def test_the_fit_is_never_worse_than_the_fit_at_the_entered_inputs(ida_case):
    """The entered inputs at the fixed-input Ka are allowed, and the search is offered that point."""
    assay, _, fit, result = ida_case
    assert result.fit.objective <= assay.n_points * np.log(fit.objective) + 1e-9


def test_a_node_solved_into_the_shallower_of_two_input_basins_does_not_cut_the_interval_short():
    """Stoichiometric IDA, eight points, inputs entered five standard deviations off.

    The input space has two basins. The search-grid node below the estimate,
    solved from the estimate's side, lands in the shallower one, above the
    threshold, while the independent objective there lies below it: the
    profile is read again across that search cell and the node solved again
    from its neighbours, so the lower edge lies where the independent
    objective crosses the threshold, below the node, with no gap reported.
    """
    x = [5.045663887196735e-06, 1.009132777439347e-05, 1.5136991661590206e-05, 2.018265554878694e-05]
    x += [2.522831943598368e-05, 3.0273983323180412e-05, 3.531964721037715e-05, 4.036531109757388e-05]
    y = [516804301.5117509, 413749773.0957198, 280815953.7107911, 178221253.79302385]
    y += [140762674.7090417, 130828298.41243015, 124425258.24760026, 124279590.30513297]
    assay = IDAAssay(
        x_data=Q_(np.array(x), 'M'),
        y_data=Q_(np.array(y), 'au'),
        Ka_dye=Q_(135969.60128617313, '1/M'),
        h0=Q_(2.5732880284727687e-05, 'M'),
        d0=Q_(2.06888486735804e-05, 'M'),
    )
    projection = Projection(assay, dict(ASSAY_REGISTRY[AssayType.IDA].default_bounds))
    _, result = _aware(assay, projection, _IDA_SIGMAS)
    profile = result.profiles['Ka_guest']
    interval, estimate = profile.interval, result.fit.ka['Ka_guest']
    nodes = projection._grid()[0][0]
    below = nodes[nodes < estimate][-1]
    value = dict(zip(profile.grid.tolist(), profile.objective.tolist()))
    # The independent objective accepts the node, and crosses the threshold below it.
    assert _ida_reference(assay, projection, below) < profile.threshold
    assert value[below] == pytest.approx(_ida_reference(assay, projection, below), abs=1e-6)
    assert interval.low < below and not (interval.open_low or interval.split)
    assert _ida_reference(assay, projection, interval.low) == pytest.approx(profile.threshold, abs=1e-5)
    assert value[interval.low] == pytest.approx(profile.threshold, abs=1e-5)


def test_with_every_binding_constant_pinned_the_inputs_are_still_fitted():
    assay, _ = _ida(15, 0.001, 3, h0_factor=1.10)
    pinned = Q_(IDA_TRUE['Ka_guest'], '1/M')
    projection = Projection(assay, {**GDA_IDA_RECOVERY_BOUNDS, 'Ka_guest': (pinned, pinned)})
    fit = projection.fit()
    result = input_aware(projection, fit, _sigma_constraints(assay, {'h0': 0.10}))
    assert result.profiles == {} and result.fit.ka == {'Ka_guest': IDA_TRUE['Ka_guest']}
    # Entered 10 % high, and the true Ka held: the host comes back to its true value.
    assert result.fit.offsets['h0'] == pytest.approx(1 / 1.10 - 1, abs=0.01)
    assert result.fit.objective < 15 * np.log(fit.objective)
    assert conflict(result).k == 1 and fit_jacobian(projection, result).shape == (16, 3)


def test_the_jacobian_of_the_whole_fit_holds_the_free_signal_columns_the_residual_is_orthogonal_to(ida_case):
    assay, projection, _, result = ida_case
    n = assay.n_points
    jacobian = fit_jacobian(projection, result)
    # The signal parameters inside their bounds, then Ka and the four inputs; four penalty rows.
    lb, ub = _coefficient_box(projection)
    c = int(np.sum((result.fit.coefficients > lb) & (result.fit.coefficients < ub)))
    assert c >= 2 and jacobian.shape == (n + 4, c + 1 + 4)
    residual = projection.residual(result.fit.ka, offsets=result.fit.offsets)
    columns = jacobian[:n, :c]
    assert np.abs(columns.T @ residual) == pytest.approx(
        0.0, abs=1e-7 * np.linalg.norm(columns) * np.linalg.norm(residual)
    )
    assert not jacobian[n:, : c + 1].any() and np.array_equal(jacobian[n:, c + 1 :], np.eye(4))
    # The residual rows are in units of the noise scale sqrt(S / n).
    scale = np.sqrt(result.fit.ssr / n)
    assert jacobian[:n, c:] * scale == pytest.approx(result.fit.jacobian[:n], rel=1e-12)


def test_the_misfit_design_holds_the_fitted_parameters_in_signal_units():
    """No varying input, one Ka: the species columns of the signal parameters inside their bounds, then the
    derivative of the fitted signal per decade of Ka, against central differences of the projected fit."""
    assay, projection = _ida(15, 0.01, 2)
    fit = projection.fit()
    design = misfit_design(projection, input_aware(projection, fit, ()))
    # Free plus bound dye sum to the dye total, so the signal columns have rank two whichever of them the solve
    # leaves inside their bounds; with Ka, three parameters.
    assert design.shape[0] == 15 and _rank(design / _norms(design)) == projection.n_params(fit) == 3
    k, h = fit.ka['Ka_guest'], 1e-4

    def fitted(t: float) -> np.ndarray:
        return assay.y_data.magnitude - projection.residual({'Ka_guest': k * 10.0**t})

    central = (fitted(h) - fitted(-h)) / (2 * h)
    assert np.linalg.norm(design[:, -1] - central) < 1e-4 * np.linalg.norm(central)


def test_the_misfit_design_of_an_input_aware_fit_has_the_rank_of_its_parameter_count(ida_case, hg2_case):
    for _, projection, _, result in (ida_case, hg2_case):
        design = misfit_design(projection, result)
        # Inputs stated with a standard deviation are held back by their penalty and have no column.
        signal = projection.fitted_parameters(result.fit.ka, result.fit.input_offsets).columns.shape[1]
        assert design.shape == (projection.n_points, signal + len(result.fit.ka_fitted))
        assert _rank(design / _norms(design)) == result.fit.n_params


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_a_repeat_is_bit_identical(ida_case):
    _, _, _, first = ida_case
    assay, projection = _ida(15, 0.01, 2)
    _, second = _aware(assay, projection, _IDA_SIGMAS)
    assert first.fit.ka == second.fit.ka and first.fit.offsets == second.fit.offsets
    assert first.fit.objective == second.fit.objective
    a, b = first.profiles['Ka_guest'], second.profiles['Ka_guest']
    assert a.interval == b.interval
    assert np.array_equal(a.grid, b.grid) and np.array_equal(a.objective, b.objective)


def test_a_loading_that_hands_the_offsets_through_is_the_fit_without_one(ida_case):
    _, _, _, plain = ida_case
    assay, projection = _ida(15, 0.01, 2)
    loaded = input_aware(projection, projection.fit(), _sigma_constraints(assay, _IDA_SIGMAS), loading=dict)
    assert plain.fit.ka == loaded.fit.ka and plain.fit.objective == loaded.fit.objective
    assert plain.fit.offsets == loaded.fit.offsets == loaded.fit.input_offsets == plain.fit.input_offsets
    assert np.array_equal(plain.fit.coefficients, loaded.fit.coefficients)
    assert np.array_equal(plain.fit.jacobian, loaded.fit.jacobian)
    a, b = plain.profiles['Ka_guest'], loaded.profiles['Ka_guest']
    assert a.interval == b.interval
    assert np.array_equal(a.grid, b.grid) and np.array_equal(a.objective, b.objective)
    assert np.array_equal(a.offsets, b.offsets) and np.array_equal(a.cut, b.cut)


def test_a_shared_source_moves_its_inputs_together_in_the_independent_objective():
    """IDA, host and dye each with an error of their own and one in common: three penalised offsets, two inputs."""
    assay, projection = _ida(15, 0.01, 2)
    own, common = 0.03, 0.04
    errors = ErrorModel(
        specs={'h0': InputSpec.sigma_pct(100 * own), 'd0': InputSpec.sigma_pct(100 * own)},
        shared=(SharedSource('Stock', 100 * common, ('h0', 'd0')),),
    )
    cons = constraints(errors, assay.get_conditions())
    x, y = assay.x_data.magnitude, assay.y_data.magnitude
    lb, ub = _coefficient_box(projection)

    def reference(k: float) -> float:
        def objective(z: np.ndarray) -> float:
            h0 = assay.h0.magnitude * (1.0 + own * z[0]) * (1.0 + common * z[2])
            d0 = assay.d0.magnitude * (1.0 + own * z[1]) * (1.0 + common * z[2])
            species = ida_species(k, assay.Ka_dye.magnitude, h0, d0, x)
            columns = np.column_stack([np.ones(x.size), species['D'], species['HD']])
            return x.size * np.log(_reference_ssr(columns, y, lb, ub)) + float(z @ z)

        return _reference_minimum(objective, 3, seed=5, spread=np.ones(3))

    for ka in (projection.fit().ka['Ka_guest'], 4e6):
        value, offsets, _, _ = penalised_objective(
            projection, {'Ka_guest': ka}, cons, {}, other_ka=None, loading=errors.loading(assay.get_conditions())
        )
        assert set(offsets) == {'h0', 'd0', shared_key('Stock')}
        assert value == pytest.approx(reference(ka), abs=1e-6)


def test_an_edge_does_not_depend_on_the_side_root_finding_walks_the_bracket_from(ida_case):
    """Every value is a function of its Ka and the two bracketing node solutions, so the other order finds the same root."""
    assay, projection, _, result = ida_case
    profile = result.profiles['Ka_guest']
    cons = result.constraints
    nodes = projection._grid()[0][0]
    keys = [c.key for c in cons]
    for edge, outward in ((profile.interval.low, -1), (profile.interval.high, 1)):
        inner = profile.grid[(profile.grid > edge) if outward < 0 else (profile.grid < edge)]
        inner = inner[np.isin(inner, nodes)]
        bracket = [nodes[nodes < edge][-1], inner[0]] if outward < 0 else [inner[-1], nodes[nodes > edge][0]]
        starts = [dict(zip(keys, profile.offsets[np.flatnonzero(profile.grid == ka)[0]])) for ka in bracket]

        def excess(t: float) -> float:
            values = [penalised_objective(projection, {'Ka_guest': 10.0**t}, cons, s, other_ka=None)[0] for s in starts]
            return min(values) - profile.threshold

        a, b = np.log10(bracket)
        forward = brentq(excess, a, b, xtol=1e-9)
        backward = brentq(excess, b, a, xtol=1e-9)
        assert forward == pytest.approx(backward, abs=1e-8)
        assert np.log10(edge) == pytest.approx(forward, abs=2e-7)


# ---------------------------------------------------------------------------
# What the interval is for: entry errors
# ---------------------------------------------------------------------------


def test_a_planted_entry_error_is_recovered_as_a_shift_and_the_truth_is_inside_only_the_aware_interval():
    assay, projection = _ida(15, 0.001, 3, h0_factor=1.10)
    fit, result = _aware(assay, projection, {'h0': 0.10})
    conditional = projection.interval('Ka_guest', fit)
    aware = result.profiles['Ka_guest'].interval
    truth = IDA_TRUE['Ka_guest']
    assert not conditional.low <= truth <= conditional.high
    assert aware.low <= truth <= aware.high
    # Entered 10 % high: the true host is 1 / 1.1 of the entered one, a shift of -9.1 %.
    shift = input_shifts(result)['h0']
    assert shift.fraction == pytest.approx(1 / 1.10 - 1, abs=0.01)
    assert shift.z == pytest.approx(shift.fraction / 0.10) and shift.at_edge is False
    assert result.fit.ka['Ka_guest'] == pytest.approx(truth, rel=0.03)
    found = conflict(result)
    assert found.k == 1 and found.q == pytest.approx(shift.z**2)
    assert all(0.0 <= w <= 1.0 for w in found.weights) and 0.0 <= found.p_value <= 1.0


def test_a_binding_constant_on_its_bound_is_held_there_and_takes_no_share_of_the_inputs():
    """DBA host-to-dye, 8 points: the data put Ka_dye on the top of its box, where it is held and not fitted.

    Both inputs were entered within their stated 3 %. With the column of that
    held constant in the reference, the constant took the one direction of the
    inputs the data inform (weight 0.04 instead of 0.96), the statistic's
    reference collapsed onto that sliver and the test returned p = 0. The
    reference here is built independently — the speciation and a bounded
    solve of the signal coefficients, central differences over the two input
    coordinates with Ka_dye held on its bound — and the test agrees with it.
    """
    x = np.array([3.5956845446575212e-06 * k for k in range(1, 9)])
    y = np.array([0.25797743358281594, 0.17783503163577002, 0.16633813598767203, 0.1610830729221144,
                  0.1588025696965124, 0.1574060619491764, 0.1554913225617098, 0.15535553311458644])  # fmt: skip
    dye = 2.265465452774337e-06
    assay = ASSAY_CLASSES[AssayType.DBA_HtoD](
        x_data=Q_(x, 'M'), y_data=Q_(y, 'au'), fixed_conc=Q_(dye, 'M'), mode='HtoD'
    )
    projection = Projection(assay, dict(ASSAY_REGISTRY[AssayType.DBA_HtoD].default_bounds))
    _, result = _aware(assay, projection, {'fixed_conc': 0.03, TITRANT: 0.03})
    fit = result.fit
    top = projection.ka_bounds['Ka_dye'][1]
    assert fit.ka['Ka_dye'] == pytest.approx(top, rel=1e-6) and fit.ka_fitted == ()
    # Held on its bound, the constant is not among the parameters: the offset and the one signal coefficient
    # a mass balance leaves (free and bound dye add up to the dye total).
    assert fit.n_params == 2

    lb, ub = _coefficient_box(projection)
    sigma = np.array([0.03, 0.03])

    def residual(z: np.ndarray) -> np.ndarray:
        fixed, scale = np.array([dye, 1.0]) * (1.0 + sigma * z)
        species = dba_species(top, scale * x, fixed, mode='HtoD')
        columns = np.column_stack([np.ones(x.size), species['D'], species['HD']])
        norm = np.linalg.norm(columns, axis=0)
        solved = lsq_linear(columns / norm, y, bounds=(lb * norm, ub * norm), method='bvls')
        return columns @ np.clip(solved.x / norm, lb, ub) - y

    at = np.array([fit.offsets['fixed_conc'], fit.offsets[TITRANT]]) / sigma
    s = np.sqrt(float(residual(at) @ residual(at)) / x.size)
    h = 1e-5
    columns = [(residual(at + step) - residual(at - step)) / (2 * h) / s for step in h * np.eye(2)]
    jacobian = np.vstack([np.column_stack(columns), np.eye(2)])
    weights, directions = np.linalg.eigh(np.eye(2) - np.linalg.inv(jacobian.T @ jacobian))
    informed = weights >= 0.01

    found = conflict(result)
    assert found.k == np.count_nonzero(informed) == 1
    assert found.weights == pytest.approx(tuple(weights[informed]), abs=2e-3)
    # The statistic is the squared offset along the informed direction.
    assert found.q == pytest.approx(float(np.sum((directions[:, informed].T @ at) ** 2)), rel=1e-3)
    assert found.p_value > 0.3


def test_an_input_stated_as_a_range_stays_inside_it_and_is_reported_on_its_edge():
    assay, projection = _ida(15, 0.001, 3, h0_factor=1.10)
    fit = projection.fit()
    narrow = input_aware(
        projection, fit, constraints(ErrorModel(specs={'h0': InputSpec.interval_pct(-5, 5)}), assay.get_conditions())
    )
    shift = input_shifts(narrow)['h0']
    assert shift.fraction == pytest.approx(-0.05, abs=1e-7) and shift.at_edge is True and shift.z is None
    assert conflict(narrow) is None
    profile = narrow.profiles['Ka_guest']
    assert np.all(profile.offsets >= -0.05 - 1e-12) and np.all(profile.offsets <= 0.05 + 1e-12)
    # A range is a free parameter with no pseudo-observation, counted in p wherever the fit leaves it inside the
    # range. Held on its edge the host is not fitted: p and the whole fit's Jacobian have the signal parameters and
    # Ka alone.
    assert narrow.fit.n_params == projection.n_params(fit) and profile.interval.dof == 15 - 3
    signal = projection.fitted_parameters(narrow.fit.ka, narrow.fit.offsets).columns.shape[1]
    assert fit_jacobian(projection, narrow).shape == (15, signal + 1)
    design = misfit_design(projection, narrow)
    assert design.shape == (15, signal + 1) and _rank(design / _norms(design)) == narrow.fit.n_params

    wide = input_aware(
        projection, fit, constraints(ErrorModel(specs={'h0': InputSpec.interval_pct(-20, 20)}), assay.get_conditions())
    )
    shift = input_shifts(wide)['h0']
    assert shift.fraction == pytest.approx(1 / 1.10 - 1, abs=0.01) and shift.at_edge is False
    signal = projection.fitted_parameters(wide.fit.ka, wide.fit.offsets).columns.shape[1]
    assert fit_jacobian(projection, wide).shape == (15, signal + 2)
    design = misfit_design(projection, wide)
    assert design.shape == (15, signal + 2) and _rank(design / _norms(design)) == wide.fit.n_params
    assert wide.fit.n_params == projection.n_params(fit) + 1 and wide.profiles['Ka_guest'].interval.dof == 15 - 4
    interval = wide.profiles['Ka_guest'].interval
    assert interval.low <= IDA_TRUE['Ka_guest'] <= interval.high


def test_only_an_input_stated_as_a_range_can_rest_on_an_edge():
    specs = {'h0': InputSpec.sigma_pct(5), 'd0': InputSpec.interval_pct(-5, 5)}
    sigma, ranged = constraints(ErrorModel(specs=specs), {'h0': Q_(1e-5, 'M'), 'd0': Q_(5e-6, 'M')})
    assert [at_edge(ranged, e) for e in (-0.05, 0.0, 0.05)] == [True, False, True]
    assert not any(at_edge(sigma, e) for e in (sigma.lo, -0.05, 0.0, 0.05, 10.0))


def test_a_profile_given_one_cut_off_array_fills_the_other_from_its_constant_level(ida_case):
    profile = ida_case[3].profiles['Ka_guest']
    given = AwareProfile(**{**vars(profile), 'r2_cut': None})
    assert np.array_equal(given.cut, profile.cut)
    assert np.array_equal(given.r2_cut, np.full(profile.grid.shape, profile.r2_threshold))


def test_a_range_input_the_fit_left_on_its_edge_absorbs_nothing_of_the_other_inputs():
    """Two inputs with the same effect on the signal: a sigma input, and a range input with no penalty row.

    Free inside its range the second reproduces whatever the first does, so
    the data say nothing about the first (weight 0). Held on an end of its
    range it is no parameter, and the first input has the information
    ``g = |a|² / s²`` of its column alone, weight ``g / (1 + g)``.
    """
    rng = np.random.default_rng(5)
    a = rng.normal(size=10)
    jacobian = np.zeros((11, 2))
    jacobian[:10, 0] = jacobian[:10, 1] = a
    jacobian[10, 0] = 1.0
    specs = {'h0': InputSpec.sigma_pct(3), 'd0': InputSpec.interval_pct(-5, 5)}
    stated = constraints(ErrorModel(specs=specs), {'h0': Q_(1e-5, 'M'), 'd0': Q_(5e-6, 'M')})
    n, ssr, ss_tot = 10, 2.5, 1e3
    g = float(a @ a) / (ssr / n)
    for d0_offset, weight in ((0.02, 0.0), (0.05, g / (1 + g)), (-0.05, g / (1 + g))):
        weights, _ = _input_directions(jacobian, [], stated, {'h0': 0.01, 'd0': d0_offset}, ssr, n, ss_tot)
        assert weights == pytest.approx((weight,), abs=1e-9)


# ---------------------------------------------------------------------------
# Fail-fast and the unsolvable sentinel
# ---------------------------------------------------------------------------


def test_a_ka_the_model_cannot_be_solved_at_opens_the_interval_like_the_fixed_input_one(monkeypatch):
    """Weakly determined Ka, and a model with no solution above 3e6: the high side is open because the profile stops."""
    solve = IDAAssay.species

    def species(self, params):
        found = solve(self, params)
        return {k: np.full_like(v, np.nan) for k, v in found.items()} if params[0] > 3e6 else found

    monkeypatch.setattr(IDAAssay, 'species', species)
    assay, projection = _ida(10, 0.08, 1, ka_box=(1e4, 1e9))
    fit = projection.fit()
    conditional = projection.interval('Ka_guest', fit)
    assert conditional.open_high and conditional.unsolvable_high
    aware = input_aware(projection, fit, _sigma_constraints(assay, {'h0': 0.03})).profiles['Ka_guest']
    assert aware.interval.open_high and aware.interval.unsolvable_high
    assert aware.interval.high <= 3e6
    assert not aware.interval.unsolvable_low
    assert np.isinf(aware.objective[-1]) and np.isnan(aware.r2[-1])


def test_too_few_points_are_refused_once_a_range_counts_as_a_parameter():
    assay, projection = _ida(4, 0.01, 1)
    fit = projection.fit()
    assert projection.interval('Ka_guest', fit) is not None  # n - p = 1 at the entered inputs
    with pytest.raises(FitRefused, match='too few to fit this model and also let this input move within a range'):
        input_aware(
            projection,
            fit,
            constraints(ErrorModel(specs={'h0': InputSpec.interval_pct(-5, 5)}), assay.get_conditions()),
        )


def test_too_few_points_are_refused_when_the_inputs_take_up_the_last_degree_of_freedom():
    """Five points, n - p = 2: a host and a dye the data determine leave less than one to judge the fit by."""
    assay, projection = _ida(5, 0.001, 1)
    fit = projection.fit()
    assert assay.n_points - projection.n_params(fit) == 2
    with pytest.raises(FitRefused, match='5 titration points, too few to fit this model and also let .* move. Hold'):
        input_aware(projection, fit, _sigma_constraints(assay, {'Ka_dye': 0.5, 'h0': 0.5, 'd0': 0.5}))
    # An uncertainty small enough to hold the inputs leaves the degrees of freedom to the noise.
    held = input_aware(projection, fit, _sigma_constraints(assay, {'h0': 1e-4}))
    assert held.profiles['Ka_guest'].interval.dof == pytest.approx(2.0, abs=0.05)


def test_a_stop_request_is_honoured():
    assay, projection = _ida(12, 0.01, 1)
    fit = projection.fit()
    asked = []

    def stop_at_the_third_ask() -> bool:
        asked.append(1)
        return len(asked) >= 3

    with pytest.raises(FitCancelled):
        input_aware(projection, fit, _sigma_constraints(assay, {'h0': 0.03}), should_cancel=stop_at_the_third_ask)
    assert len(asked) == 3


def test_a_multi_row_projection_is_refused():
    assay, _ = _ida(12, 0.01, 1)
    y = assay.y_data.magnitude
    projection = Projection(assay, GDA_IDA_RECOVERY_BOUNDS, signals=np.vstack([y, y * 1.01]))
    with pytest.raises(ValueError, match='describes one signal'):
        input_aware(projection, projection.fit(), _sigma_constraints(assay, {'h0': 0.03}))


def test_the_scaled_drop_of_the_penalised_profile_is_one_at_its_edges_and_its_test_is_the_f_test(ida_case):
    """``(P - P_min) / (cut - P_min)`` is the curve Ka confidence draws: 0 at the optimum, 1 at each closed edge.

    The allowed rise of a point that pins nothing the optimum fits is
    ``n log(1 + F(1, nu) / nu)``, written out here independently.
    """
    assay, _projection, _fit, result = ida_case
    profile = result.profiles['Ka_guest']
    n, dof = assay.n_points, profile.interval.dof
    assert profile.minimum == result.fit.objective
    assert profile.threshold - profile.minimum == pytest.approx(n * np.log1p(f_dist.ppf(LEVEL, 1, dof) / dof))
    drop = profile.scaled_drop()
    assert drop[profile.grid == result.fit.ka['Ka_guest']] == pytest.approx(0.0, abs=1e-12)
    for edge in (profile.interval.low, profile.interval.high):
        assert drop[profile.grid == edge] == pytest.approx(1.0, abs=1e-6)


def test_the_drawn_penalised_profile_crosses_the_cut_off_at_each_closed_edge(ida_case):
    """A plot crosses the cut-off where the edge is only if the curve is read close to it on both sides.

    The drawn points next to each closed edge lie within 0.02 decade of it, each
    on the side of the cut-off its side of the edge is.
    """
    _assay, _projection, _fit, result = ida_case
    profile = result.profiles['Ka_guest']
    logs, drop = np.log10(profile.grid), profile.scaled_drop()
    for edge, outward in ((profile.interval.low, -1), (profile.interval.high, 1)):
        (at,) = np.flatnonzero(profile.grid == edge)
        for side in (-1, 1):
            beside = at + side
            assert 0 < side * (logs[beside] - logs[at]) <= 0.02
            assert (drop[beside] > 1.0) == (side == outward)
