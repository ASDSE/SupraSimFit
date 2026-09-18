"""Relative accuracy of every equilibrium solve, against exact rational arithmetic.

The reference is the model's own mass balance written here in
``fractions.Fraction``: a double converts to a Fraction exactly, so the sign of
the balance at ``x·(1 ± k·eps)`` is known with certainty, and a returned free
concentration ``x`` whose two neighbours give opposite signs lies within
``k·eps`` (relative) of the true root.  No floating-point solver is involved in
the reference, so the certificate holds at any binding constant, including the
tight-binding and equivalence-point regimes where a solve converged to an
absolute tolerance keeps only a few digits.

Tolerances: 8 eps for the root and for the mass balances (the solves stop at
4 eps), 32 eps for each species (root error times a log-sensitivity of at most
two, plus the rounding of the three to five operations that form a species),
16 eps between two independently solved closed-form limits (8 eps each).
"""

import math
import random
import sys
import threading
from fractions import Fraction as F

import numpy as np
import pytest
from scipy.optimize import brentq

from core.models.equilibrium import (
    competitive_species_point,
    dba_species,
    gda_species,
    h2g_species,
    hg2_species,
    ida_species,
    legacy_arithmetic,
)

EPS = F(sys.float_info.epsilon)

# Binding constants (1/M): the lower and upper default bounds, an ordinary
# value, and two far beyond the default box.  Totals (M) span the app's nM-mM range.
CONSTANTS = (1e-8, 1e6, 1e12, 1e20, 1e100)
TOTALS = (1e-9, 1e-6, 1e-3)
# Titrant / fixed ratios: absent, 1e3 deficit, either side of equivalence at
# 1e-9, exact equivalence, 1e3 excess.
RATIOS = (0.0, 1e-3, 1 - 1e-9, 1.0, 1 + 1e-9, 1e3)


# ---------------------------------------------------------------------------
# Exact-rational reference
# ---------------------------------------------------------------------------


def _host_balance(Kg, Kd, h0, d0, g0):
    """Competitive host balance ``[H] + [HD] + [HG] − h0`` as a function of free host."""
    Kg, Kd, h0, d0, g0 = map(F, (Kg, Kd, h0, d0, g0))
    return lambda h: h + d0 * Kd * h / (1 + Kd * h) + g0 * Kg * h / (1 + Kg * h) - h0


def _ligand_balance(K1, K2, core, ligand):
    """Stepwise 1:2 ligand balance ``l + [CL] + 2·[CL2] − L`` as a function of free ligand."""
    K1, K2, core, ligand = map(F, (K1, K2, core, ligand))
    return lambda x: x + core * (K1 * x + 2 * K1 * K2 * x * x) / (1 + K1 * x + K1 * K2 * x * x) - ligand


def _one_to_one_balance(K, total, partner):
    """1:1 balance ``z + [complex] − total`` times ``1 + K·z``: a quadratic in the free ``z``."""
    K, total, partner = map(F, (K, total, partner))
    return lambda z: K * z * z + (K * (partner - total) + 1) * z - total


def _brackets_root(f, x, k_eps):
    """True when the exact balance *f* changes sign between ``x·(1 − k·eps)`` and ``x·(1 + k·eps)``."""
    x, delta = F(x), k_eps * EPS
    return f(x * (1 - delta)) < 0 < f(x * (1 + delta))


def _exact_root(f, x, k_eps):
    """Root of *f* to 1e-20 relative, by exact bisection of the certified bracket around *x*."""
    lo, hi = F(x) * (1 - k_eps * EPS), F(x) * (1 + k_eps * EPS)
    for _ in range(20):
        mid = (lo + hi) / 2
        if f(mid) < 0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def _assert_close(actual, exact, k_eps, what):
    assert abs(F(actual) - exact) <= k_eps * EPS * abs(exact), f'{what}: {actual!r} against {float(exact)!r}'


def _certify_free(f, x, total, what):
    """A free concentration is the certified root of its balance (zero when its total is zero)."""
    if total == 0.0:
        assert x == 0.0, what
    else:
        assert math.isfinite(x) and _brackets_root(f, x, 8), f'{what}: {x!r} is not within 8 eps of the root'


def _check_competitive(sp, i, Kg, Kd, h0, d0, g0):
    """Root certificate, every species and all three mass balances of one competitive point."""
    what = f'Kg={Kg:g} Kd={Kd:g} h0={h0:g} d0={d0:g} g0={g0:g}'
    f = _host_balance(Kg, Kd, h0, d0, g0)
    got = {k: float(sp[k][i]) for k in ('H', 'D', 'G', 'HD', 'HG')}
    _certify_free(f, got['H'], h0, what)
    h = _exact_root(f, got['H'], 8)
    d, g = F(d0) / (1 + F(Kd) * h), F(g0) / (1 + F(Kg) * h)
    exact = {'H': h, 'D': d, 'G': g, 'HD': F(Kd) * h * d, 'HG': F(Kg) * h * g}
    for k in exact:
        _assert_close(got[k], exact[k], 32, f'[{k}] at {what}')
    _assert_close(F(got['H']) + F(got['HD']) + F(got['HG']), F(h0), 8, f'host balance at {what}')
    _assert_close(F(got['D']) + F(got['HD']), F(d0), 8, f'dye balance at {what}')
    _assert_close(F(got['G']) + F(got['HG']), F(g0), 8, f'guest balance at {what}')


def _check_stepwise(free_ligand, free_core, single, double, K1, K2, core, ligand):
    """Root certificate, every species and both mass balances of one 1:2 point."""
    what = f'K1={K1:g} K2={K2:g} core={core:g} ligand={ligand:g}'
    f = _ligand_balance(K1, K2, core, ligand)
    _certify_free(f, free_ligand, ligand, what)
    x = _exact_root(f, free_ligand, 8)
    c = F(core) / (1 + F(K1) * x + F(K1) * F(K2) * x * x)
    for name, got, exact in (
        ('free ligand', free_ligand, x),
        ('free core', free_core, c),
        ('1:1 complex', single, F(K1) * c * x),
        ('1:2 complex', double, F(K1) * F(K2) * c * x * x),
    ):
        _assert_close(got, exact, 32, f'{name} at {what}')
    _assert_close(F(free_ligand) + F(single) + 2 * F(double), F(ligand), 8, f'ligand balance at {what}')
    _assert_close(F(free_core) + F(single) + F(double), F(core), 8, f'core balance at {what}')


# ---------------------------------------------------------------------------
# Structured regimes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize('Kg', CONSTANTS)
def test_gda_and_ida_speciation_is_exact_to_rounding_in_every_regime(Kg):
    """Weak to 1e100, nM to mM, deficit / equivalence / excess of either partner.

    The point ``titrant = h0 − fixed`` is the joint equivalence ``d0 + g0 = h0``,
    where free host is smallest against the totals.
    """
    Kd = 1e7
    for h0 in TOTALS:
        for fixed_ratio in (0.25, 1.0, 1e3):
            fixed = fixed_ratio * h0
            titrant = np.array([r * h0 for r in RATIOS] + [max(h0 - fixed, 0.0)])
            gda = gda_species(Kg, Kd, h0, titrant, fixed)
            ida = ida_species(Kg, Kd, h0, fixed, titrant)
            for i, x in enumerate(titrant):
                _check_competitive(gda, i, Kg, Kd, h0, float(x), fixed)
                _check_competitive(ida, i, Kg, Kd, h0, fixed, float(x))


@pytest.mark.parametrize('K1', CONSTANTS)
def test_hg2_and_h2g_speciation_is_exact_to_rounding_in_every_regime(K1):
    """Both stoichiometric points (L = C and L = 2C), their 1e-9 neighbours and 1e3 excess either way,
    for equal steps and for a second step far from the first (cooperative or anti-cooperative)."""
    ligand_per_core = (1e-3, 1 - 1e-9, 1.0, 1 + 1e-9, 2 * (1 - 1e-9), 2.0, 2 * (1 + 1e-9), 1e3)
    for K2 in (K1, 1e3):
        for fixed in TOTALS:
            # HG2: the titrated guest is the ligand, fixed host the core.
            g0 = np.array([r * fixed for r in ligand_per_core])
            sp = hg2_species(K1, K2, fixed, g0)
            for i, x in enumerate(g0):
                _check_stepwise(*(float(sp[k][i]) for k in ('G', 'H', 'HG', 'HG2')), K1, K2, fixed, float(x))
            # H2G: fixed host is the ligand, the titrated guest the core.
            g0 = np.array([fixed / r for r in ligand_per_core])
            sp = h2g_species(K1, K2, fixed, g0)
            for i, x in enumerate(g0):
                _check_stepwise(*(float(sp[k][i]) for k in ('H', 'G', 'HG', 'H2G')), K1, K2, float(x), fixed)


@pytest.mark.parametrize('mode', ['HtoD', 'DtoH'])
def test_dba_speciation_is_exact_to_rounding_in_every_regime(mode):
    """Both directions up to 1e200 1/M, where the square of the linear coefficient exceeds a double."""
    for K in (*CONSTANTS, 1e200):
        for fixed in TOTALS:
            titrant = np.array([r * fixed for r in RATIOS])
            sp = dba_species(K, titrant, fixed, mode=mode)
            fixed_key, titrant_key = ('D', 'H') if mode == 'HtoD' else ('H', 'D')
            for i, x in enumerate(titrant):
                x, what = float(x), f'K={K:g} titrant={x:g} fixed={fixed:g} {mode}'
                free_fixed, free_titrant, hd = (float(sp[k][i]) for k in (fixed_key, titrant_key, 'HD'))
                f_fixed, f_titrant = _one_to_one_balance(K, fixed, x), _one_to_one_balance(K, x, fixed)
                _certify_free(f_fixed, free_fixed, fixed, what)
                _certify_free(f_titrant, free_titrant, x, what)
                exact_hd = (
                    F(K) * _exact_root(f_fixed, free_fixed, 8) * (_exact_root(f_titrant, free_titrant, 8) if x else 0)
                )
                _assert_close(hd, exact_hd, 32, f'[HD] at {what}')
                _assert_close(F(free_fixed) + F(hd), F(fixed), 8, f'fixed-species balance at {what}')
                _assert_close(F(free_titrant) + F(hd), F(x), 8, f'titrant balance at {what}')


# ---------------------------------------------------------------------------
# Seeded random block: constants over the default box and beyond, any ratio
# ---------------------------------------------------------------------------


def _random_constant(rng):
    return 10 ** rng.uniform(-8, rng.choice((12, 12, 100)))


def _random_partner(rng, total):
    return total * rng.choice((1.0, 1 + 1e-9, 2.0, 10 ** rng.uniform(-3, 3)))


def test_random_competitive_roots_are_certified():
    rng = random.Random(20240917)
    for _ in range(300):
        Kg, Kd, h0 = _random_constant(rng), _random_constant(rng), 10 ** rng.uniform(-9, -3)
        d0, g0 = _random_partner(rng, h0), _random_partner(rng, h0)
        if rng.random() < 0.25:
            g0 = max(h0 - d0, 0.0)
        h = competitive_species_point(Kg, Kd, h0, d0, g0)['H']
        _certify_free(_host_balance(Kg, Kd, h0, d0, g0), h, h0, f'Kg={Kg!r} Kd={Kd!r} h0={h0!r} d0={d0!r} g0={g0!r}')


def test_random_stepwise_roots_are_certified():
    rng = random.Random(20240918)
    for _ in range(300):
        K1, K2, core = _random_constant(rng), _random_constant(rng), 10 ** rng.uniform(-9, -3)
        ligand = _random_partner(rng, core)
        what = f'K1={K1!r} K2={K2!r} core={core!r} ligand={ligand!r}'
        f = _ligand_balance(K1, K2, core, ligand)
        _certify_free(f, float(hg2_species(K1, K2, core, np.array([ligand]))['G'][0]), ligand, 'HG2 ' + what)
        _certify_free(f, float(h2g_species(K1, K2, ligand, np.array([core]))['H'][0]), ligand, 'H2G ' + what)


def test_random_dba_roots_are_certified():
    rng = random.Random(20240919)
    for _ in range(300):
        K, fixed = 10 ** rng.uniform(-8, rng.choice((12, 12, 300))), 10 ** rng.uniform(-9, -3)
        x = _random_partner(rng, fixed)
        sp = dba_species(K, np.array([x]), fixed, mode='HtoD')
        what = f'K={K!r} titrant={x!r} fixed={fixed!r}'
        _certify_free(_one_to_one_balance(K, fixed, x), float(sp['D'][0]), fixed, what)
        _certify_free(_one_to_one_balance(K, x, fixed), float(sp['H'][0]), x, what)


# ---------------------------------------------------------------------------
# Termination: an iteration that never stops is a point with no speciation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    'Kg, Kd, h0, d0, g0',
    [
        (104712854.80508985, 1e7, 1e-6, 1.379310344827586e-07, 2e-6),
        (77.9730038274983, 24236.917072128028, 0.0032810889114772805, 0.006370894921627029, 0.0026660639949532853),
    ],
)
def test_a_balance_whose_rounding_floor_is_wider_than_the_step_tolerance_still_has_a_root(Kg, Kd, h0, d0, g0):
    """At these inputs the rounding error of the balance is 9.0e-16 relative, just above the 8.9e-16
    step the solve stops at, so only the sign of the balance can say the root has been reached."""
    got = competitive_species_point(Kg, Kd, h0, d0, g0)['H']
    _certify_free(_host_balance(Kg, Kd, h0, d0, g0), got, h0, f'Kg={Kg!r} Kd={Kd!r} h0={h0!r} d0={d0!r} g0={g0!r}')


def test_every_solve_of_a_profiled_titration_returns_a_number():
    """A Ka profile solves the balance at every titration point of every Ka on its grid, so one
    input the iteration does not terminate at puts a hole in the curve. This design and grid are
    the app's own: 401 constants across the default bounds, 15 dye concentrations to 2·h0."""
    h0, Ka_dye, g0 = 5e-7, 1e8, 1e-6
    d0_values = np.linspace(0.0, 2 * h0, 15)
    for Ka_guest in np.geomspace(1e-8, 1e12, 401):
        species = gda_species(Ka_guest, Ka_dye, h0, d0_values, g0)
        assert np.all(np.isfinite(species['H'])), f'no free host at Ka_guest={Ka_guest!r}'
        assert np.all(np.isfinite(species['HD'])), f'no host-dye complex at Ka_guest={Ka_guest!r}'


# ---------------------------------------------------------------------------
# Closed-form limits: two different solves of the same chemistry
# ---------------------------------------------------------------------------


def _assert_same(a, b, what):
    assert abs(a - b) <= 16 * float(EPS) * abs(b), f'{what}: {a!r} against {b!r}'


@pytest.mark.parametrize('K', [1e4, 1e12])
class TestClosedFormLimits:
    h0 = 4e-6
    x = np.array([1e-7, 2e-6, 4e-6, 8e-6, 5e-5])  # includes both stoichiometric points of each limit

    def test_equal_constants_make_dye_and_guest_one_ligand(self, K):
        """Ka_dye = Ka_guest: the host sees one ligand of total d0 + g0 (d0 = g0, so the sum is exact)."""
        half = self.x / 2
        for i, half_i in enumerate(half):
            sp = gda_species(K, K, self.h0, np.array([half_i]), half_i)
            one = dba_species(K, np.array([2 * half_i]), self.h0, mode='DtoH')
            _assert_same(sp['H'][0], one['H'][0], f'[H] at point {i}')
            _assert_same(sp['HD'][0] + sp['HG'][0], one['HD'][0], f'bound host at point {i}')

    @pytest.mark.parametrize('absent', ['g0', 'Ka_guest'])
    def test_no_competitor_is_direct_binding(self, K, absent):
        g0, Kg = (0.0, 1e6) if absent == 'g0' else (3e-6, 0.0)
        sp = gda_species(Kg, K, self.h0, self.x, g0)
        one = dba_species(K, self.x, self.h0, mode='DtoH')
        for k in ('H', 'D', 'HD'):
            for a, b in zip(sp[k], one[k]):
                _assert_same(a, b, f'[{k}]')
        np.testing.assert_array_equal(sp['HG'], 0.0)

    def test_no_second_step_is_one_to_one(self, K):
        one = dba_species(K, self.x, self.h0, mode='DtoH')  # 'dye' stands for the guest
        for sp, second in (
            (hg2_species(K, 0.0, self.h0, self.x), 'HG2'),
            (h2g_species(K, 0.0, self.h0, self.x), 'H2G'),
        ):
            for a, b in zip(sp['G'], one['D']):
                _assert_same(a, b, '[G]')
            for a, b in zip(sp['HG'], one['HD']):
                _assert_same(a, b, '[HG]')
            np.testing.assert_array_equal(sp[second], 0.0)

    def test_statistical_constants_are_two_independent_sites(self, K):
        """K1 = 4·K2: two identical independent sites of constant K1/2, i.e. 1:1 binding to 2·C sites."""
        K1, K2 = 4 * K, K
        for ligand in self.x:
            sites = dba_species(K1 / 2, np.array([ligand]), 2 * self.h0, mode='DtoH')  # 'dye' is the ligand
            hg2 = hg2_species(K1, K2, self.h0, np.array([ligand]))
            _assert_same(hg2['G'][0], sites['D'][0], 'HG2 free guest')
            _assert_same(hg2['HG'][0] + 2 * hg2['HG2'][0], sites['HD'][0], 'HG2 bound guest')
            h2g = h2g_species(K1, K2, ligand, np.array([self.h0]))
            _assert_same(h2g['H'][0], sites['D'][0], 'H2G free host')


# ---------------------------------------------------------------------------
# Sentinel contract: NaN, never an exception and never a wrong number
# ---------------------------------------------------------------------------

_X = np.array([1e-6, 5e-6])
_MODELS = {
    'gda': (lambda Kg, Kd, h0, g0, x=_X: gda_species(Kg, Kd, h0, x, g0), (1e6, 1e7, 4e-6, 2e-6)),
    'ida': (lambda Kg, Kd, h0, d0, x=_X: ida_species(Kg, Kd, h0, d0, x), (1e6, 1e7, 4e-6, 2e-6)),
    'hg2': (lambda K1, K2, h0, x=_X: hg2_species(K1, K2, h0, x), (1e6, 1e5, 4e-6)),
    'h2g': (lambda K1, K2, h0, x=_X: h2g_species(K1, K2, h0, x), (1e6, 1e5, 4e-6)),
    'dba_htod': (lambda K, y, x=_X: dba_species(K, x, y, mode='HtoD'), (1e6, 4e-6)),
    'dba_dtoh': (lambda K, y, x=_X: dba_species(K, x, y, mode='DtoH'), (1e6, 4e-6)),
}


@pytest.mark.parametrize('model', _MODELS)
@pytest.mark.parametrize('bad', [-1.0, math.nan, math.inf])
def test_a_negative_or_non_finite_input_gives_nan_species(model, bad):
    species, nominal = _MODELS[model]
    assert all(np.all(np.isfinite(v)) for v in species(*nominal).values())
    for position in range(len(nominal)):
        args = list(nominal)
        args[position] = bad
        for key, values in species(*args).items():
            assert np.all(np.isnan(values)), f'{model} argument {position} = {bad}: [{key}] = {values}'
    # A bad titrant point is NaN on its own; its neighbour keeps its speciation.
    for key, values in species(*nominal, x=np.array([1e-6, bad])).items():
        assert np.isfinite(values[0]) and np.isnan(values[1]), f'{model} titrant {bad}: [{key}] = {values}'


def test_zero_totals_give_the_unbound_state():
    x = np.array([0.0, 3e-6])
    sp = gda_species(1e6, 1e7, 0.0, x, 2e-6)  # no host: dye and guest stay free
    assert [list(sp[k]) for k in ('H', 'D', 'G', 'HD', 'HG')] == [[0, 0], list(x), [2e-6, 2e-6], [0, 0], [0, 0]]
    sp = ida_species(1e6, 1e7, 4e-6, 0.0, np.array([0.0]))  # host alone
    assert [sp[k][0] for k in ('H', 'D', 'G', 'HD', 'HG')] == [4e-6, 0, 0, 0, 0]
    for species, second in ((hg2_species, 'HG2'), (h2g_species, 'H2G')):
        sp = species(1e6, 1e5, 4e-6, np.array([0.0]))  # no guest
        assert [sp[k][0] for k in ('H', 'G', 'HG', second)] == [4e-6, 0, 0, 0]
        sp = species(1e6, 1e5, 0.0, np.array([3e-6]))  # no host
        assert [sp[k][0] for k in ('H', 'G', 'HG', second)] == [0, 3e-6, 0, 0]
    sp = dba_species(1e6, x, 0.0, mode='HtoD')  # no dye: the titrated host stays free
    assert [list(sp[k]) for k in ('H', 'D', 'HD')] == [list(x), [0, 0], [0, 0]]
    sp = dba_species(1e6, np.array([0.0]), 4e-6, mode='DtoH')
    assert [sp[k][0] for k in ('H', 'D', 'HD')] == [4e-6, 0, 0]


def test_a_speciation_beyond_the_range_of_a_double_is_nan_not_a_wrong_number():
    """No species is reported where K1·K2·l² exceeds 1e308, where a constant times a total does —
    the derivative of the balance is then infinite wherever the iteration stands, so no step can
    reach the root — or where the concentration the solve looks for falls below the smallest
    normal double (2e-308 M) and has no digits left to find."""
    for sp in (
        hg2_species(1e200, 1e200, 4e-6, np.array([1e-5])),  # free guest 1e-5 M: K1·K2·g² = 1e390
        h2g_species(1e200, 1e200, 4e-6, np.array([1e-12])),  # free host 4e-6 M: K1·K2·h² = 1.6e389
        ida_species(1.0, 1e290, 1e19, 1e19, np.array([0.0])),  # Ka_dye·d0 = 1e309, root at 1.9e-102 M
        hg2_species(1e300, 1.0, 1e19, np.array([1e19])),  # K1·h0 = 1e319
        ida_species(1e305, 1e7, 1e-12, 0.0, np.array([1.0])),  # free host 1e-317 M
        dba_species(1e305, np.array([1e-12]), 1.0, mode='HtoD'),
    ):
        assert all(np.all(np.isnan(v)) for v in sp.values())


def test_constants_whose_product_overflows_still_have_the_speciation_they_have():
    """K1·K2 passes 1e308 far below the point where the balance does: the root sits near
    1/sqrt(K1·K2), so K1·K2·l² is of order one there and the speciation is an ordinary double."""
    for K1, K2, core, ligand in ((1e200, 1e200, 4e-6, 2e-6), (1e200, 1e200, 4e-6, 4e-6), (1e160, 1e160, 1e-6, 1e-6)):
        what = f'K1={K1!r} K2={K2!r} core={core!r} ligand={ligand!r}'
        f = _ligand_balance(K1, K2, core, ligand)
        _certify_free(f, float(hg2_species(K1, K2, core, np.array([ligand]))['G'][0]), ligand, 'HG2 ' + what)
        _certify_free(f, float(h2g_species(K1, K2, ligand, np.array([core]))['H'][0]), ligand, 'H2G ' + what)


def test_a_free_concentration_far_above_its_own_lower_bound_is_solved_for():
    """The bound h0/(1 + Kd·d0 + Kg·g0) underflows a factor sqrt(Ka·c) below the root at an
    equivalence point, which says nothing about the root: at Ka·c ≈ 1e302 the root is 1e-157 M."""
    for Kd, h0, d0 in ((1e308, 1e-6, 1e-6), (5e307, 1e-6, 1e-6)):
        got = competitive_species_point(0.0, Kd, h0, d0, 0.0)['H']
        _certify_free(_host_balance(0.0, Kd, h0, d0, 0.0), got, h0, f'Kd={Kd!r} h0={h0!r} d0={d0!r}')


# ---------------------------------------------------------------------------
# Arithmetic of results files without a `model_arithmetic` entry
# ---------------------------------------------------------------------------


class TestLegacyArithmetic:
    """Inside ``legacy_arithmetic()`` the two iterative solves are Brent's method at the absolute
    tolerance and bracket written out below; everywhere else they are the relative-precision solves."""

    competitive = (1e11, 1e7, 4e-6, 6e-6, 2e-5)  # Kg, Kd, h0, d0, g0: free host about 1e-13 M
    stepwise = (1e9, 1e8, 4e-6, 1.2e-5)  # K1, K2, core, ligand

    def _absolute_tolerance_host(self):
        Kg, Kd, h0, d0, g0 = self.competitive
        return brentq(
            lambda h: h + (Kd * h * d0) / (1 + Kd * h) + (Kg * h * g0) / (1 + Kg * h) - h0,
            1e-20,
            h0,
            xtol=1e-14,
            maxiter=1000,
        )

    def _absolute_tolerance_ligand(self):
        K1, K2, core, ligand = self.stepwise

        def balance(x):
            return x + core * (K1 * x + 2.0 * K1 * K2 * x * x) / (1.0 + K1 * x + K1 * K2 * x * x) - ligand

        return brentq(balance, 0.0, ligand, xtol=1e-15, maxiter=1000)

    def _solve(self):
        K1, K2, core, ligand = self.stepwise
        return (
            competitive_species_point(*self.competitive)['H'],
            float(hg2_species(K1, K2, core, np.array([ligand]))['G'][0]),
            float(h2g_species(K1, K2, ligand, np.array([core]))['H'][0]),
        )

    def test_reproduces_the_absolute_tolerance_solves(self):
        expected_h, expected_l = self._absolute_tolerance_host(), self._absolute_tolerance_ligand()
        with legacy_arithmetic():
            assert self._solve() == (expected_h, expected_l, expected_l)
        # The case is one where the two arithmetics differ, so the equality above is not vacuous.
        assert not _brackets_root(_host_balance(*self.competitive), expected_h, 10**6)

    def test_is_off_outside_the_block_even_after_an_error(self):
        before = self._solve()
        with pytest.raises(KeyError):
            with legacy_arithmetic():
                assert self._solve() != before
                raise KeyError
        assert self._solve() == before
        assert _brackets_root(_host_balance(*self.competitive), before[0], 8)

    def test_does_not_reach_another_thread(self):
        """A check on the GUI thread leaves a fit running in a worker thread on the present arithmetic."""
        expected, seen = self._solve(), []
        with legacy_arithmetic():
            worker = threading.Thread(target=lambda: seen.append(self._solve()))
            worker.start()
            worker.join()
        assert seen == [expected]

    def test_direct_binding_is_the_same_in_both(self):
        x = np.array([1e-6, 4e-6, 2e-5])
        now = dba_species(1e9, x, 4e-6, mode='HtoD')
        with legacy_arithmetic():
            then = dba_species(1e9, x, 4e-6, mode='HtoD')
        for k in now:
            np.testing.assert_array_equal(now[k], then[k])
