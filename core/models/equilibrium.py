"""Forward models for equilibrium binding assays.

This module contains pure mathematical functions for computing predicted signals
from binding equilibria. All functions are unit-free (magnitudes only) and
stateless.

Scientific Conventions
----------------------
All binding constants use the ASSOCIATION form:
    Ka = [complex] / ([free_A][free_B])

For Host-Dye binding:  Ka_dye = [HD] / ([H][D])
For Host-Guest binding: Ka_guest = [HG] / ([H][G])

Models
------
- DBA (Direct Binding Assay): Host-Dye equilibrium, fits Ka_dye
- GDA (Guest Displacement Assay): Dye titrated, guest fixed, fits Ka_guest
- IDA (Indicator Displacement Assay): Guest titrated, dye fixed, fits Ka_guest
- HG2 (stepwise 1:2 host:guest): host binds two guests, fits Ka_HG, Ka_HG2
- H2G (stepwise 2:1 host:guest): two hosts bind one guest, fits Ka_HG, Ka_H2G

Signal Model
------------
1:1 assays:  Signal = I0 + I_dye_free * [D_free] + I_dye_bound * [HD]
HG2 / H2G:   Signal = I0 + I_G * [G] + I_H * [H] + (per-complex terms)
             where the free-host coefficient I_H defaults to zero.

Where:
- I0: background signal
- I_dye_free: signal coefficient for free dye
- I_dye_bound: signal coefficient for host-dye complex

Numerical accuracy
------------------
Every model returns the free concentration it solves for within a few machine
epsilons (relative) of the exact root of its mass balance, at any binding
constant and any ratio of the totals whose product with that constant a double
can still hold (``Ka·x0`` below 1.8e308).  That root can lie ten
or more decades below the totals (tight binding at an equivalence point), so
two things are needed.  The solves stop on a *relative* step, ``_ROOT_RTOL``.
And the balance is evaluated in a form that adds, per binding partner, only
its minority species: ``[HD]`` while less than half the dye is bound, and
``d0 − [D]`` with ``d0`` folded exactly into the constant of the balance once
more than half is bound.  The rounding error of the balance is then a few eps
of the minority species, which is the scale ``x·f′(x)`` on which the balance
responds to a relative change of the root ``x``; summing the species as they
stand rounds at eps times the *total* and leaves the root undetermined by the
ratio of the two.  DBA has a closed form and is evaluated without cancellation.
The iterations stop where the balance stops decreasing as well, which is the
same floor reached from the other side and is what makes them terminate: a
step below the rounding error of the balance carries no digits.  Every mass
balance holds to a few eps of its total throughout; the one place a *species*
does not is one whose exact value lies below the smallest normal double, free
or bound, which carries the digits gradual underflow leaves it (it takes a
constant near 1e-290 or 1e300 1/M against nanomolar totals, and the balances
and every species above that floor are unaffected).

Species are NaN, and nothing is raised, where there is no speciation to
report: a negative or non-finite constant or total, a product of a constant
with a total beyond the range of a double (which leaves the derivative of the
balance infinite at every iterate, so no step can find the root), a stepwise
product ``K1·K2·l²`` beyond that range, or a solved free concentration — free
host for the competitive models, free ligand for the stepwise ones — below the
smallest normal double, which no longer has digits to solve for.
The free concentrations that follow from it are quotients of the totals, and
each complex is its total times a bound fraction, so free and bound add up to
the total and a complex above the subnormal floor keeps full relative accuracy
even where the free form it stands next to has underflowed.

References
----------
See docs/scientific-summary.md for detailed derivations.
"""

import contextlib
import math
import sys
from contextvars import ContextVar
from typing import Iterator

import numpy as np
from scipy.optimize import brentq

# Identifier of the equilibrium arithmetic, recorded with every fit as
# ``FitResult.metadata['model_arithmetic']``.  The scores stored in a results
# file are reproducible only with the arithmetic that wrote them; a file
# without the entry stores scores of the absolute-tolerance Brent solves kept
# below as ``_legacy_competitive_free_host`` and ``_legacy_free_ligand_12``.
MODEL_ARITHMETIC: int = 2

# Relative step at which the iterative solves stop.  The minority-species
# balances carry a rounding error of 2-3 eps relative to x·f′(x), so a smaller
# step is rounding noise; 4 eps is also the tightest relative tolerance scipy's
# bracketing solvers accept.  Every returned root is bracketed by exact
# rational arithmetic within 4 eps (tests/unit/test_equilibrium_precision.py
# asserts 8).  It is where a solve stops, not what makes it stop: the rounding
# error reaches 4.07 eps at some inputs, so the sign of the balance is what ends
# the iteration (see :func:`_competitive_free_host`).
_ROOT_RTOL = 4 * np.finfo(float).eps

# Iteration limit; reaching it returns NaN, never an unconverged number.  At an
# exact equivalence point with tight binding K·x roughly doubles per step up to
# the root, about log2(sqrt(K·c)) + 10 steps: below 530 for any finite doubles
# (measured: at most 21 for constants up to 1e12 M⁻¹ and totals up to 1 mM,
# median 4; 498 at 1e300 M⁻¹).  1000 is that bound with a factor of two.
_ROOT_MAXITER = 1000

# Smallest normal double.  A concentration below it has lost digits to gradual
# underflow, so there is nothing left for a solve to find: a solve whose root
# lies below it reports no speciation (NaN), and it is the floor a solve starts
# its search from.
_TINY = sys.float_info.min

_LEGACY: ContextVar[bool] = ContextVar('equilibrium_legacy_arithmetic', default=False)


@contextlib.contextmanager
def legacy_arithmetic() -> Iterator[None]:
    """Solve the iterative balances with the arithmetic of unmarked results files.

    Inside the block the competitive (GDA/IDA) and stepwise (HG2/H2G) solves
    are :func:`_legacy_competitive_free_host` and :func:`_legacy_free_ligand_12`,
    which reproduce the scores stored in a results file that has no
    ``model_arithmetic`` entry.  DBA is one arithmetic throughout.  The switch
    is a ``ContextVar``, so it is confined to the calling thread: a check on
    the GUI thread leaves a fit running in a worker thread untouched.
    """
    token = _LEGACY.set(True)
    try:
        yield
    finally:
        _LEGACY.reset(token)


def _all_valid(*values: float) -> bool:
    """True when every constant and total is finite and non-negative (NaN compares false)."""
    return all(0.0 <= v < math.inf for v in values)


# =============================================================================
# DBA (Direct Binding Assay) Models
# =============================================================================


def _positive_root(a: float, b: float, total: float, sqrt_disc: float) -> float:
    """Non-negative root of ``a·z² + b·z − total = 0``, taken without cancellation.

    *sqrt_disc* is the square root of the discriminant ``b² + 4·a·total``. For
    ``b ≥ 0`` the usual numerator ``−b + sqrt_disc`` subtracts two numbers that
    agree to as many digits as ``a·total`` is small against ``b²``, so at a
    binding constant above about 1e17 M⁻¹ the root is rounding error rather
    than a concentration; ``2·total / (b + sqrt_disc)`` is the same root with
    its two terms added instead.  For ``b < 0`` the numerator is a sum as it
    stands, and dividing by ``a`` before halving keeps ``2·a`` out of overflow.

    Parameters
    ----------
    a, b : float
        Quadratic and linear coefficients, ``a ≥ 0``.
    total : float
        The total concentration the root belongs to (M), ``≥ 0``.
    sqrt_disc : float
        ``sqrt(b² + 4·a·total)``, shared by both species of the equilibrium.

    Returns
    -------
    float
        The root, in the unit of *total*; NaN where it is below the smallest
        normal double.
    """
    if total == 0.0:
        return 0.0
    root = 2.0 * total / (b + sqrt_disc) if b >= 0.0 else (sqrt_disc - b) / a / 2.0
    return root if root >= _TINY else math.nan


def dba_species(
    Ka_dye: float,
    x_titrant: np.ndarray,
    y_fixed: float,
    *,
    mode: str,
) -> dict:
    """Equilibrium speciation for 1:1 host–dye binding (H + D ⇌ HD).

    Works for both Host→Dye and Dye→Host titrations with
    ``Ka_dye = [HD] / ([H][D])``.  The free concentration of the *fixed*
    species solves the quadratic derived from the two mass balances and
    ``[HD] = Ka_dye·[H]·[D]``::

        Ka_dye · y_free² + (Ka_dye · (x - y_fixed) + 1) · y_free - y_fixed = 0

    where ``y_free`` is the free conc. of the fixed species.  The titrant's
    free concentration solves the same quadratic with ``x`` and ``y_fixed``
    exchanged, which has the same discriminant, and ``[HD] = Ka_dye · [H] · [D]``
    follows from the two.  Each free concentration is taken from the form of
    the quadratic root that adds its two terms rather than subtracting them:
    the subtracting form loses every significant digit to cancellation once
    ``Ka_dye · c`` passes about 1e12, and returns speciation that is finite
    noise rather than a solution.  The discriminant's square root is taken as
    ``hypot(b, 2·sqrt(Ka_dye · y_fixed))``, which holds where ``b²`` exceeds a
    double (Ka_dye above about 1e150 M⁻¹).  Both frees are within 2 eps of the
    exact roots.  ``mode`` only decides which of the two frees is the host and
    which is the dye.

    Returning the full speciation (not just the signal) keeps one solve
    shared by both the signal model (:func:`dba_signal`) and species-level
    inspection, so they can never disagree.

    Parameters
    ----------
    Ka_dye : float
        Association constant for host-dye binding (M⁻¹).
    x_titrant : np.ndarray
        Titrant concentrations (M) — host for ``HtoD``, dye for ``DtoH``.
    y_fixed : float
        Fixed component concentration (M) — dye for ``HtoD``, host for ``DtoH``.
    mode : str
        ``"HtoD"`` (host titrated into fixed dye) or ``"DtoH"`` (dye titrated
        into fixed host), keyword-only.

    Returns
    -------
    dict
        ``{'H', 'D', 'HD'}`` → arrays of concentrations (M), same shape as
        ``x_titrant``.  A point is NaN where ``Ka_dye`` or a total is negative
        or non-finite.
    """
    if mode not in ('HtoD', 'DtoH'):
        raise ValueError(f"mode must be 'HtoD' or 'DtoH', got {mode!r}")

    x_titrant = np.asarray(x_titrant, dtype=float)
    H = np.full_like(x_titrant, np.nan)
    D = np.full_like(x_titrant, np.nan)
    HD = np.full_like(x_titrant, np.nan)
    # Python floats: the same IEEE arithmetic as numpy scalars at a third of the cost.
    Ka_dye, y_fixed = float(Ka_dye), float(y_fixed)
    if not _all_valid(Ka_dye, y_fixed):
        return {'H': H, 'D': D, 'HD': HD}
    two_sqrt_ay = 2.0 * math.sqrt(Ka_dye * y_fixed)

    for i, x in enumerate(x_titrant.tolist()):
        if not _all_valid(x):
            continue
        # Quadratic for y_free (free concentration of the fixed species),
        #   Ka_dye * y_free^2 + (Ka_dye * delta + 1) * y_free - y_fixed = 0,
        # and, with the two species exchanged, for x_free.  Both share the
        # discriminant b_y^2 + 4 * Ka_dye * y_fixed.
        delta = x - y_fixed
        b_y = Ka_dye * delta + 1.0
        b_x = 1.0 - Ka_dye * delta
        sqrt_disc = math.hypot(b_y, two_sqrt_ay)
        y_free = _positive_root(Ka_dye, b_y, y_fixed, sqrt_disc)
        x_free = _positive_root(Ka_dye, b_x, x, sqrt_disc)
        hd = Ka_dye * y_free * x_free
        if sqrt_disc == math.inf or not math.isfinite(hd):  # Ka_dye · c, or its inverse, beyond a double
            continue

        # Which free is host vs dye depends on the titrant.
        # HtoD: host titrated -> x_free is [H], y_free (fixed dye) is [D].
        # DtoH: dye titrated  -> x_free is [D], y_free (fixed host) is [H].
        if mode == 'HtoD':
            H[i], D[i] = x_free, y_free
        else:
            H[i], D[i] = y_free, x_free
        HD[i] = hd

    return {'H': H, 'D': D, 'HD': HD}


def dba_signal(
    I0: float,
    Ka_dye: float,
    I_dye_free: float,
    I_dye_bound: float,
    x_titrant: np.ndarray,
    y_fixed: float,
    *,
    mode: str,
) -> np.ndarray:
    """Compute DBA signal for host-dye equilibrium (H + D ⇌ HD).

    Delegates the equilibrium solve to :func:`dba_species` and combines the
    per-species concentrations into the observed signal::

        Signal = I0 + I_dye_free · [D] + I_dye_bound · [HD]

    so the plotted signal and the speciation come from a single solve.  The
    signal uses the free *dye* concentration regardless of titration direction.

    Parameters
    ----------
    I0 : float
        Background signal intensity.
    Ka_dye : float
        Association constant for host-dye binding (M⁻¹).
    I_dye_free, I_dye_bound : float
        Signal coefficients for free dye and the host-dye complex.
    x_titrant : np.ndarray
        Titrant concentrations (M) — host for ``HtoD``, dye for ``DtoH``.
    y_fixed : float
        Fixed component concentration (M) — dye for ``HtoD``, host for ``DtoH``.
    mode : str
        ``"HtoD"`` or ``"DtoH"`` (keyword-only).

    Returns
    -------
    np.ndarray
        Predicted signal values, NaN where the speciation is.
    """
    sp = dba_species(Ka_dye, x_titrant, y_fixed, mode=mode)
    return I0 + I_dye_free * sp['D'] + I_dye_bound * sp['HD']


# =============================================================================
# Competitive Binding Models (GDA / IDA)
# =============================================================================


def _competitive_free_host(Ka_guest: float, Ka_dye: float, h0: float, d0: float, g0: float) -> float:
    """Free host (M) of the competitive H/D/G system, within ``_ROOT_RTOL`` of the exact root.

    With ``u = Ka_dye·h`` and ``v = Ka_guest·h`` the host balance is::

        f(h) = h + d0·u/(1+u) + g0·v/(1+v) − h0,
        f′(h) = 1 + Ka_dye·d0/(1+u)² + Ka_guest·g0/(1+v)² > 0,   f″(h) < 0.

    ``f`` is increasing and concave on ``h ≥ 0``, so Newton's iteration from
    any point with ``f ≤ 0`` increases monotonically towards the root and
    never passes it: it needs no bracket and cannot leave ``(0, h0]``.  The
    start ``h0 / (1 + Ka_dye·d0 + Ka_guest·g0)`` is such a point, because
    ``[HD] ≤ Ka_dye·d0·h`` and ``[HG] ≤ Ka_guest·g0·h``.

    That monotonicity is also the stopping rule.  In exact arithmetic ``f``
    stays negative until the root, so a computed ``f ≥ 0`` means the iterate
    is within the rounding error of ``f`` of the root and no further step
    carries information; without that test the iterate alternates between two
    neighbouring doubles whenever the rounding error of the balance is larger
    than ``_ROOT_RTOL·x·f′(x)``.  The relative-step test below then only ends
    the runs that reach the root from one side.

    Each partner enters ``f`` through its minority species (module docstring):
    ``+d0·u/(1+u)`` for ``u ≤ 1``, and ``−d0/(1+u)`` with ``d0`` moved into the
    constant ``c = d0 + g0 − h0`` for ``u > 1``.  The switch at ``u = 1`` is
    where bound and free dye are equal; the two forms are the same number up
    to rounding, so any threshold within a constant factor serves.  ``c`` is
    summed with ``math.fsum``: at an equivalence point it is far below the
    totals, and adding three totals one after the other leaves eps·h0 in it.
    ``f′`` is formed as ``(K·x0/(1+w))/(1+w)`` so that no square can overflow.

    Returns NaN for a negative or non-finite input, where a product ``Ka·x0``
    is beyond the range of a double and so leaves ``f′`` infinite at every
    iterate, and where free host itself falls below the smallest normal
    double.  Inside :func:`legacy_arithmetic` the result is that of
    :func:`_legacy_competitive_free_host`.
    """
    # Python floats: the same IEEE arithmetic as numpy scalars at a third of the cost.
    Kg, Kd, h0, d0, g0 = float(Ka_guest), float(Ka_dye), float(h0), float(d0), float(g0)
    if not _all_valid(Kg, Kd, h0, d0, g0):
        return math.nan
    if _LEGACY.get():
        return _legacy_competitive_free_host(Kg, Kd, h0, d0, g0)
    if h0 == 0.0:
        return 0.0

    # ``Ka·x0`` is the whole of ``f′`` beyond 1 and does not change with the iterate: beyond
    # the range of a double it makes ``f′`` infinite at every iterate, the step exactly zero
    # and the start itself the answer, which it is not.  There is then no root to report.
    kd_d0, kg_g0 = Kd * d0, Kg * g0
    if not (math.isfinite(kd_d0) and math.isfinite(kg_g0)):
        return math.nan

    h = h0 / (1.0 + kd_d0 + kg_g0)
    # The start is a lower bound on the root, and the root is the number to report, so a
    # start that has underflowed says nothing yet: the smallest normal double is a lower
    # bound too as long as the balance is not already positive there, and a positive
    # balance there puts free host below it, where there is nothing to report.
    raised = h < _TINY
    if raised:
        h = _TINY
    for _ in range(_ROOT_MAXITER):
        u, v = Kd * h, Kg * h
        if u <= 1.0:
            term_d, const_d = d0 * u / (1.0 + u), 0.0
        else:
            term_d, const_d = -d0 / (1.0 + u), d0
        if v <= 1.0:
            term_g, const_g = g0 * v / (1.0 + v), 0.0
        else:
            term_g, const_g = -g0 / (1.0 + v), g0
        f = (h + math.fsum((-h0, const_d, const_g))) + (term_d + term_g)
        if f >= 0.0:  # the rounding floor of the balance; no step below it carries digits
            return math.nan if (raised and f > 0.0) else h
        raised = False
        slope = 1.0 + kd_d0 / (1.0 + u) / (1.0 + u) + kg_g0 / (1.0 + v) / (1.0 + v)
        new = h - f / slope
        if new - h <= _ROOT_RTOL * new:
            return new
        h = new
    return math.nan


def _legacy_competitive_free_host(Ka_guest: float, Ka_dye: float, h0: float, d0: float, g0: float) -> float:
    """Free host (M) by Brent's method on ``[1e-20, h0]`` to an absolute 1e-14 M.

    The arithmetic of results files without a ``model_arithmetic`` entry, kept
    so that their stored scores can be reproduced (:func:`legacy_arithmetic`).
    Its relative error grows with the binding constant, and it has no solution
    (NaN) once free host falls below the bracket's lower end.
    """

    def mass_balance(h):
        denom_D = 1 + Ka_dye * h
        denom_G = 1 + Ka_guest * h
        hd = (Ka_dye * h * d0) / denom_D
        hg = (Ka_guest * h * g0) / denom_G
        return h + hd + hg - h0

    try:
        return brentq(mass_balance, 1e-20, h0, xtol=1e-14, maxiter=1000)
    except (ValueError, RuntimeError):
        return math.nan


def _competitive_speciation(h, Ka_guest: float, Ka_dye: float, d0, g0) -> dict:
    """All five species from free host *h* (scalar or array), by products and quotients only.

    Each complex is its partner's total times the bound fraction ``u/(1+u)``,
    so it is a product of normal numbers wherever the total is one: a free dye
    or guest concentration that underflows to a subnormal keeps the digits
    gradual underflow leaves it, and the complex that holds the rest of that
    total keeps full relative accuracy unless it is subnormal itself.  Free and
    bound then also sum to the total exactly.  NaN in *h* propagates to every
    species.
    """
    with np.errstate(over='ignore', invalid='ignore'):  # absurd totals overflow; the species are NaN
        u, v = Ka_dye * h, Ka_guest * h
        return {
            'H': h,
            'D': d0 / (1.0 + u),
            'G': g0 / (1.0 + v),
            'HD': d0 * (u / (1.0 + u)),
            'HG': g0 * (v / (1.0 + v)),
        }


def competitive_species_point(
    Ka_guest: float,
    Ka_dye: float,
    h0: float,
    d0: float,
    g0: float,
) -> dict:
    """Equilibrium speciation for one point of the competitive H/D/G system.

    Core solve shared by GDA and IDA.  Two competing equilibria::

        H + D ⇌ HD  (Ka_dye  = [HD]/([H][D]))
        H + G ⇌ HG  (Ka_guest = [HG]/([H][G]))

    Free host ``[H]`` is the root of the host mass balance
    ``h0 = [H] + [HD] + [HG]`` (:func:`_competitive_free_host`); the remaining
    species follow from ``[D] = d0/(1+Ka_dye·[H])``,
    ``[G] = g0/(1+Ka_guest·[H])`` and the complex definitions.  Returning the
    full speciation lets both :func:`competitive_signal_point` and species
    inspection share one solve.

    Parameters
    ----------
    Ka_guest : float
        Association constant for host-guest binding (M⁻¹) — the fitted quantity.
    Ka_dye : float
        Known association constant for host-dye binding (M⁻¹).
    h0, d0, g0 : float
        Total host, dye and guest/indicator concentrations (M).

    Returns
    -------
    dict
        ``{'H', 'D', 'G', 'HD', 'HG'}`` → scalar concentrations (M); all NaN
        where a constant or total is negative or non-finite.
    """
    h_free = _competitive_free_host(Ka_guest, Ka_dye, h0, d0, g0)
    return _competitive_speciation(h_free, float(Ka_guest), float(Ka_dye), float(d0), float(g0))


def _competitive_species_grid(Ka_guest, Ka_dye, h0, d0_values, g0_values) -> dict:
    """Speciation across a titration for the competitive model.

    Exactly one of ``d0_values`` / ``g0_values`` is the titrant array; the other
    is a scalar broadcast to every point.  GDA (dye titrant) and IDA (guest
    titrant) both route through here so they share the per-point solve.
    """
    d0_values = np.atleast_1d(np.asarray(d0_values, dtype=float))
    g0_values = np.atleast_1d(np.asarray(g0_values, dtype=float))
    d0_values, g0_values = np.broadcast_arrays(d0_values, g0_values)
    h_free = np.array(
        [_competitive_free_host(Ka_guest, Ka_dye, h0, d0, g0) for d0, g0 in zip(d0_values.tolist(), g0_values.tolist())]
    )
    return _competitive_speciation(h_free, float(Ka_guest), float(Ka_dye), d0_values, g0_values)


def gda_species(Ka_guest, Ka_dye, h0, d0_values, g0) -> dict:
    """Competitive speciation for GDA (dye titrated, guest fixed).

    Returns ``{'H','D','G','HD','HG'}`` arrays over ``d0_values`` (M).  See
    :func:`competitive_species_point`.
    """
    return _competitive_species_grid(Ka_guest, Ka_dye, h0, d0_values, g0)


def ida_species(Ka_guest, Ka_dye, h0, d0, g0_values) -> dict:
    """Competitive speciation for IDA (guest titrated, dye fixed).

    Returns ``{'H','D','G','HD','HG'}`` arrays over ``g0_values`` (M).  See
    :func:`competitive_species_point`.
    """
    return _competitive_species_grid(Ka_guest, Ka_dye, h0, d0, g0_values)


def competitive_signal_point(
    I0: float,
    Ka_guest: float,
    I_dye_free: float,
    I_dye_bound: float,
    Ka_dye: float,
    h0: float,
    d0: float,
    g0: float,
) -> float:
    """Compute signal for a single point in competitive binding equilibrium.

    Delegates the equilibrium solve to :func:`competitive_species_point` and
    combines the free dye and host-dye complex into the observed signal::

        Signal = I0 + I_dye_free · [D] + I_dye_bound · [HD]

    Parameters
    ----------
    I0 : float
        Background signal intensity.
    Ka_guest : float
        Association constant for guest/indicator (M⁻¹). This is fitted.
    I_dye_free, I_dye_bound : float
        Signal coefficients for free dye and the host-dye complex.
    Ka_dye : float
        Known association constant for host-dye (M⁻¹).
    h0, d0, g0 : float
        Total host, dye and guest/indicator concentrations (M).

    Returns
    -------
    float
        Predicted signal value, NaN where the speciation is.
    """
    sp = competitive_species_point(Ka_guest, Ka_dye, h0, d0, g0)
    return I0 + I_dye_free * sp['D'] + I_dye_bound * sp['HD']


def gda_signal(
    I0: float,
    Ka_guest: float,
    I_dye_free: float,
    I_dye_bound: float,
    Ka_dye: float,
    h0: float,
    d0_values: np.ndarray,
    g0: float,
) -> np.ndarray:
    """Compute GDA signal across dye concentration range.

    In GDA (Guest Displacement Assay), dye is titrated into a host-guest mixture.
    As dye binds host, it displaces guest, changing the signal.

    Titrant: Dye (d0 varies)
    Fixed: Host (h0), Guest (g0)
    Fitted: Ka_guest

    Parameters
    ----------
    I0 : float
        Background signal intensity.
    Ka_guest : float
        Association constant for host-guest binding (M^-1). This is fitted.
    I_dye_free : float
        Signal coefficient for free dye.
    I_dye_bound : float
        Signal coefficient for host-dye complex.
    Ka_dye : float
        Known association constant for host-dye (M^-1).
    h0 : float
        Total host concentration (M).
    d0_values : np.ndarray
        Dye concentrations (M) - the independent variable (titrant).
    g0 : float
        Total guest concentration (M) - fixed.

    Returns
    -------
    np.ndarray
        Predicted signal values.
    """
    sp = gda_species(Ka_guest, Ka_dye, h0, d0_values, g0)
    return I0 + I_dye_free * sp['D'] + I_dye_bound * sp['HD']


def ida_signal(
    I0: float,
    Ka_guest: float,
    I_dye_free: float,
    I_dye_bound: float,
    Ka_dye: float,
    h0: float,
    d0: float,
    g0_values: np.ndarray,
) -> np.ndarray:
    """Compute IDA signal across guest concentration range.

    In IDA (Indicator Displacement Assay), guest is titrated into a host-dye
    mixture. As guest binds host, it displaces dye (indicator), changing signal.

    Titrant: Guest (g0 varies)
    Fixed: Host (h0), Dye (d0)
    Fitted: Ka_guest

    Parameters
    ----------
    I0 : float
        Background signal intensity.
    Ka_guest : float
        Association constant for host-guest binding (M^-1). This is fitted.
    I_dye_free : float
        Signal coefficient for free dye.
    I_dye_bound : float
        Signal coefficient for host-dye complex.
    Ka_dye : float
        Known association constant for host-dye (M^-1).
    h0 : float
        Total host concentration (M).
    d0 : float
        Total dye concentration (M) - fixed.
    g0_values : np.ndarray
        Guest concentrations (M) - the independent variable (titrant).

    Returns
    -------
    np.ndarray
        Predicted signal values.
    """
    sp = ida_species(Ka_guest, Ka_dye, h0, d0, g0_values)
    return I0 + I_dye_free * sp['D'] + I_dye_bound * sp['HD']


# =============================================================================
# Stepwise 1:2 / 2:1 Binding Models (HG2 / H2G)
# =============================================================================
#
# These describe a host that forms two successive complexes with a guest.
# The guest is the optically active (titrated) species; host is fixed.  Both
# share one root-finder: the speciation of a 'core' species that binds two
# 'ligand' molecules in two steps reduces to the same monotonic mass balance.
#
#   HG2 (1:2 host:guest):  core = host,  ligand = guest
#   H2G (2:1 host:guest):  core = guest, ligand = host
#
# Stepwise association constants (never dissociation):
#   Ka1 = [CL] / ([C][L])      Ka2 = [CL2] / ([CL][L])
#
# The combined system is a cubic in the free-ligand concentration.  The roots
# of the expanded polynomial lose six to nine digits to cancellation at large
# constants, so the (strictly increasing) mass balance is solved instead.


def _solve_free_ligand_12(K1: float, K2: float, core_total: float, ligand_total: float) -> float:
    """Solve for free-ligand concentration in a stepwise 1:2 (core·ligand₂) system.

    A single *core* species C binds up to two *ligand* molecules L in two
    steps with stepwise association constants ``K1`` (C + L ⇌ CL) and
    ``K2`` (CL + L ⇌ CL₂).  With ``a = K1·l``, ``b = K1·K2·l²`` and
    ``D = 1 + a + b`` the core is divided into the fractions ``1/D`` (free),
    ``a/D`` (CL) and ``b/D`` (CL₂), and the ligand mass balance
    ``ligand_total = l + [CL] + 2·[CL2]`` (two ligands per CL₂) reads::

        g(l) = l − L + C·(a + 2b)/D,     g′(l) = 1 + C·K1·(1 + 4·K2·l + b)/D² > 0.

    ``g`` is strictly increasing, so the root is unique; it is not concave for
    cooperative binding (``K2 > K1/4``), so Newton's iteration is safeguarded
    by a bracket.  The bracket is ``[lo, L]`` with
    ``lo = max(L / (1 + C·K1 + 2·C·K1·K2·L), L − 2C)``: ``g(lo) ≤ 0`` because
    the bound ligand per core is at most ``(K1 + 2·K1·K2·L)·l`` for ``l ≤ L``
    and at most 2.  The iteration starts at ``lo``, which is the root itself
    in the weak-binding and the ligand-excess limits.

    ``g`` is evaluated in the one of three identical forms that adds only the
    minority fractions of the core (module docstring), chosen by the dominant
    fraction; ``L − C`` and ``L − 2C`` are single, correctly rounded
    subtractions::

        free core dominant (a ≤ 1 and b ≤ 1):  g = (l − L) + C·(a + 2b)/D
        CL dominant        (otherwise, a ≥ b):  g = (l − (L − C)) + C·(b − 1)/D
        CL₂ dominant       (otherwise):         g = (l − (L − 2C)) − C·(2 + a)/D

    Each step first tests convergence (``|Δl| ≤ _ROOT_RTOL·l``) and only then
    the bracket: a converged iterate coincides with a bracket end, and testing
    the bracket first would send it through some fifty needless bisections.  A
    Newton step that leaves the bracket is replaced by the geometric mean of
    its ends, since the root can lie decades below ``L``.

    Parameters
    ----------
    K1, K2 : float
        Stepwise association constants (M⁻¹) for the first and second step.
    core_total : float
        Total concentration (M) of the species that binds two ligands.
    ligand_total : float
        Total concentration (M) of the ligand being balanced.

    Returns
    -------
    float
        Free-ligand concentration (M); ``0.0`` when ``ligand_total`` is zero.
        ``nan`` for a negative or non-finite input, where ``K1·K2·l²`` or
        ``C·K1`` exceeds a double — the latter leaves ``g′`` infinite and the
        step zero wherever the iterate is — and where the free ligand itself
        falls below the smallest normal double, so callers propagate NaN
        rather than raising.
        Inside :func:`legacy_arithmetic` the result is that of
        :func:`_legacy_free_ligand_12`.
    """
    # Python floats: the same IEEE arithmetic as numpy scalars at a third of the cost.
    K1, K2, C, L = float(K1), float(K2), float(core_total), float(ligand_total)
    if not _all_valid(K1, K2, C, L):
        return math.nan
    if _LEGACY.get():
        return _legacy_free_ligand_12(K1, K2, C, L)
    if L == 0.0:
        return 0.0

    lo, hi = max(L / (1.0 + C * K1 + 2.0 * C * K1 * K2 * L), L - 2.0 * C), L
    # ``C·K1·K2·L`` overflows long before the root does — the root sits near 1/sqrt(K1·K2),
    # where ``b`` is of order one — so a bound that has underflowed (or that a product in it
    # sent to infinity) says nothing about the root.  The smallest normal double is a lower
    # bound too as long as the balance is not already positive there, and a positive balance
    # there puts the free ligand below it, where there is nothing to report.
    raised = not lo >= _TINY
    if raised:
        lo = _TINY
    x = lo
    for _ in range(_ROOT_MAXITER):
        a = K1 * x
        b = a * (K2 * x)  # both factors scale with the root, so neither overflows before b does
        D = 1.0 + a + b
        if a <= 1.0 and b <= 1.0:
            g = (x - L) + C * (a + 2.0 * b) / D
        elif a >= b:
            g = (x - (L - C)) + C * (b - 1.0) / D
        else:
            g = (x - (L - 2.0 * C)) - C * (2.0 + a) / D
        if raised:  # a positive balance at the smallest normal double puts the root below it
            if g > 0.0:
                return math.nan
            raised = False
        slope = 1.0 + C * (K1 / D) * ((1.0 + 4.0 * K2 * x + b) / D)  # no square, no K1·b: neither can overflow
        if not math.isfinite(slope):  # C·K1 beyond a double: the step is zero wherever the iterate is
            return math.nan
        new = x - g / slope
        if not math.isfinite(new):  # b beyond a double
            return math.nan
        if abs(new - x) <= _ROOT_RTOL * new:
            return new
        if g > 0.0:
            hi = x
        else:
            lo = x
        if not lo < new < hi:
            new = math.sqrt(lo) * math.sqrt(hi)
            if hi - lo <= _ROOT_RTOL * hi:
                return new
        x = new
    return math.nan


def _legacy_free_ligand_12(K1: float, K2: float, core_total: float, ligand_total: float) -> float:
    """Free ligand (M) by Brent's method on ``[0, ligand_total]`` to an absolute 1e-15 M.

    The arithmetic of results files without a ``model_arithmetic`` entry, kept
    so that their stored scores can be reproduced (:func:`legacy_arithmetic`).
    Its relative error grows with the binding constants.
    """
    if ligand_total <= 0.0:
        return 0.0

    def balance(free_ligand: float) -> float:
        denom = 1.0 + K1 * free_ligand + K1 * K2 * free_ligand * free_ligand
        bound = core_total * (K1 * free_ligand + 2.0 * K1 * K2 * free_ligand * free_ligand) / denom
        return free_ligand + bound - ligand_total

    try:
        return brentq(balance, 0.0, ligand_total, xtol=1e-15, maxiter=1000)
    except (ValueError, RuntimeError):
        return math.nan


def _stepwise_species(K1: float, K2: float, core_total, ligand_total) -> tuple:
    """Free ligand, free core, CL and CL₂ (arrays, M) across a titration of a stepwise 1:2 system.

    One of the totals is the titrant array, the other a scalar broadcast to
    every point.  The free ligand comes from :func:`_solve_free_ligand_12` per
    point; the fractions of the core are formed as they are there
    (``a = K1·l``, ``b = (K1·l)·(K2·l)``), by products and quotients only.  Each
    complex is the core total times its fraction ``a/D`` or ``b/D``, so a free
    core that underflows to a subnormal carries no lost digits into the
    complexes above that floor, and the three add up to the total.  A point without a free
    ligand, or whose ``b`` exceeds a double, is NaN in every species.
    """
    core, ligand = np.broadcast_arrays(np.asarray(core_total, dtype=float), np.asarray(ligand_total, dtype=float))
    free_ligand = np.array([_solve_free_ligand_12(K1, K2, c, t) for c, t in zip(core.tolist(), ligand.tolist())])
    with np.errstate(over='ignore', invalid='ignore'):
        a = K1 * free_ligand
        b = a * (K2 * free_ligand)
        D = 1.0 + a + b
        species = (free_ligand, core / D, core * (a / D), core * (b / D))
        return tuple(np.where(np.isfinite(b), sp, np.nan) for sp in species)


def hg2_species(
    Ka_HG: float,
    Ka_HG2: float,
    h0: float,
    g0_values: np.ndarray,
) -> dict:
    """Equilibrium speciation for stepwise 1:2 host–guest binding.

    Two successive complexes form as guest is titrated into fixed host::

        H + G  ⇌ HG    (Ka_HG)
        HG + G ⇌ HG2   (Ka_HG2)

    Host is fixed at ``h0``; the guest total ``g0`` is the titrant.  Free
    guest is found per point from the guest mass balance
    ``g0 = [G] + [HG] + 2·[HG2]`` (two guests per HG2) via
    :func:`_solve_free_ligand_12` (core = host, ligand = guest), then the
    remaining species follow from
    ``[H] = h0 / (1 + Ka_HG·g + Ka_HG·Ka_HG2·g²)``.

    Returning the full speciation (not just the signal) keeps this routine
    reusable for both fitting and species-level inspection.

    Parameters
    ----------
    Ka_HG, Ka_HG2 : float
        Stepwise association constants (M⁻¹).
    h0 : float
        Total (fixed) host concentration (M).
    g0_values : np.ndarray
        Total guest concentrations (M) — the titrant.

    Returns
    -------
    dict
        ``{'H', 'G', 'HG', 'HG2'}`` → arrays of concentrations (M), same
        shape as ``g0_values``.  A point is NaN where a constant or total is
        negative or non-finite, or ``Ka_HG·Ka_HG2·[G]²`` exceeds a double.
    """
    G, H, HG, HG2 = _stepwise_species(Ka_HG, Ka_HG2, h0, g0_values)
    return {'H': H, 'G': G, 'HG': HG, 'HG2': HG2}


def hg2_signal(
    I0: float,
    Ka_HG: float,
    Ka_HG2: float,
    I_G: float,
    I_H: float,
    I_HG: float,
    I_HG2: float,
    h0: float,
    g0_values: np.ndarray,
) -> np.ndarray:
    """Compute the signal for stepwise 1:2 host–guest binding (HG, HG₂).

    Guest is titrated into fixed host; the observed signal sums per-species
    contributions::

        Signal = I0 + I_G·[G] + I_H·[H] + I_HG·[HG] + I_HG2·[HG2]

    ``I_H`` (free-host coefficient) is typically zero.  See
    :func:`hg2_species` for the equilibrium solve.

    Parameters
    ----------
    I0 : float
        Baseline signal.
    Ka_HG, Ka_HG2 : float
        Stepwise association constants (M⁻¹).
    I_G, I_H, I_HG, I_HG2 : float
        Signal coefficients for free guest, free host, HG and HG₂.
    h0 : float
        Total (fixed) host concentration (M).
    g0_values : np.ndarray
        Total guest concentrations (M) — the titrant.

    Returns
    -------
    np.ndarray
        Predicted signal values, same shape as ``g0_values``.
    """
    sp = hg2_species(Ka_HG, Ka_HG2, h0, g0_values)
    return I0 + I_G * sp['G'] + I_H * sp['H'] + I_HG * sp['HG'] + I_HG2 * sp['HG2']


def h2g_species(
    Ka_HG: float,
    Ka_H2G: float,
    h0: float,
    g0_values: np.ndarray,
) -> dict:
    """Equilibrium speciation for stepwise 2:1 host–guest binding.

    Two hosts bind one guest in two successive steps as guest is titrated
    into fixed host::

        H + G  ⇌ HG    (Ka_HG)
        HG + H ⇌ H2G   (Ka_H2G)

    Here the *guest* is the species that binds two partners, so free host is
    found per point from the host mass balance
    ``h0 = [H] + [HG] + 2·[H2G]`` (two hosts per H2G) via
    :func:`_solve_free_ligand_12` (core = guest, ligand = host), then
    ``[G] = g0 / (1 + Ka_HG·h + Ka_HG·Ka_H2G·h²)``.

    Parameters
    ----------
    Ka_HG, Ka_H2G : float
        Stepwise association constants (M⁻¹).
    h0 : float
        Total (fixed) host concentration (M).
    g0_values : np.ndarray
        Total guest concentrations (M) — the titrant.

    Returns
    -------
    dict
        ``{'H', 'G', 'HG', 'H2G'}`` → arrays of concentrations (M), same
        shape as ``g0_values``.  A point is NaN where a constant or total is
        negative or non-finite, or ``Ka_HG·Ka_H2G·[H]²`` exceeds a double.
    """
    H, G, HG, H2G = _stepwise_species(Ka_HG, Ka_H2G, g0_values, h0)
    return {'H': H, 'G': G, 'HG': HG, 'H2G': H2G}


def h2g_signal(
    I0: float,
    Ka_HG: float,
    Ka_H2G: float,
    I_G: float,
    I_H: float,
    I_HG: float,
    I_H2G: float,
    h0: float,
    g0_values: np.ndarray,
) -> np.ndarray:
    """Compute the signal for stepwise 2:1 host–guest binding (HG, H₂G).

    Guest is titrated into fixed host; the observed signal sums per-species
    contributions::

        Signal = I0 + I_G·[G] + I_H·[H] + I_HG·[HG] + I_H2G·[H2G]

    ``I_H`` (free-host coefficient) is typically zero.  See
    :func:`h2g_species` for the equilibrium solve.

    Parameters
    ----------
    I0 : float
        Baseline signal.
    Ka_HG, Ka_H2G : float
        Stepwise association constants (M⁻¹).
    I_G, I_H, I_HG, I_H2G : float
        Signal coefficients for free guest, free host, HG and H₂G.
    h0 : float
        Total (fixed) host concentration (M).
    g0_values : np.ndarray
        Total guest concentrations (M) — the titrant.

    Returns
    -------
    np.ndarray
        Predicted signal values, same shape as ``g0_values``.
    """
    sp = h2g_species(Ka_HG, Ka_H2G, h0, g0_values)
    return I0 + I_G * sp['G'] + I_H * sp['H'] + I_HG * sp['HG'] + I_H2G * sp['H2G']
