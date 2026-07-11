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

Note: The variable naming in legacy code (Kd, Kg) was misleading as it suggested
dissociation constants, but the formulas actually use association form. This
module uses explicit Ka_* naming to avoid confusion.

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

References
----------
See docs/scientific-summary.md for detailed derivations.
"""

import numpy as np
from scipy.optimize import brentq

# =============================================================================
# DBA (Direct Binding Assay) Models
# =============================================================================


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

    where ``y_free`` is the free conc. of the fixed species; the
    physically meaningful (non-negative) root is selected.  The free
    titrant concentration is ``x_free = y_free + (x - y_fixed)`` and
    ``[HD] = Ka_dye · y_free · x_free``.  ``mode`` only decides which of
    the two frees is the host and which is the dye.

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
        ``x_titrant``.  Entries are NaN where the quadratic has no physical root.
    """
    if mode not in ('HtoD', 'DtoH'):
        raise ValueError(f"mode must be 'HtoD' or 'DtoH', got {mode!r}")

    x_titrant = np.asarray(x_titrant, dtype=float)
    H = np.empty_like(x_titrant)
    D = np.empty_like(x_titrant)
    HD = np.empty_like(x_titrant)

    for i, x in enumerate(x_titrant):
        delta = x - y_fixed

        # Quadratic coefficients for y_free (free concentration of fixed species)
        # Ka_dye * y_free^2 + (Ka_dye * delta + 1) * y_free - y_fixed = 0
        a = Ka_dye
        b = Ka_dye * delta + 1
        c = -y_fixed

        discriminant = b**2 - 4 * a * c

        if discriminant < 0:
            H[i] = D[i] = HD[i] = np.nan
            continue

        sqrt_disc = np.sqrt(discriminant)
        y1 = (-b + sqrt_disc) / (2 * a)
        y2 = (-b - sqrt_disc) / (2 * a)

        # Choose physically meaningful (non-negative) root
        y_free = y1 if y1 >= 0 else (y2 if y2 >= 0 else np.nan)

        if np.isnan(y_free):
            H[i] = D[i] = HD[i] = np.nan
            continue

        x_free = y_free + delta
        hd_complex = Ka_dye * y_free * x_free

        # Which free is host vs dye depends on the titrant.
        # HtoD: host titrated -> x_free is [H], y_free (fixed dye) is [D].
        # DtoH: dye titrated  -> x_free is [D], y_free (fixed host) is [H].
        if mode == 'HtoD':
            H[i], D[i] = x_free, y_free
        else:
            H[i], D[i] = y_free, x_free
        HD[i] = hd_complex

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
        Predicted signal values, NaN where the equilibrium solve fails.
    """
    sp = dba_species(Ka_dye, x_titrant, y_fixed, mode=mode)
    return I0 + I_dye_free * sp['D'] + I_dye_bound * sp['HD']


# =============================================================================
# =============================================================================
# Competitive Binding Models (GDA / IDA)
# =============================================================================


_COMPETITIVE_SPECIES = ('H', 'D', 'G', 'HD', 'HG')


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

    Free host ``[H]`` is found with Brent's method on the host mass balance
    ``h0 = [H] + [HD] + [HG]``; the remaining species follow from
    ``[D] = d0/(1+Ka_dye·[H])``, ``[G] = g0/(1+Ka_guest·[H])`` and the complex
    definitions.  Returning the full speciation lets both
    :func:`competitive_signal_point` and species inspection share one solve.

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
        if the mass-balance solve fails (non-physical parameters).
    """
    try:

        def mass_balance(h):
            """Residual for host mass balance equation."""
            denom_D = 1 + Ka_dye * h
            denom_G = 1 + Ka_guest * h
            hd = (Ka_dye * h * d0) / denom_D
            hg = (Ka_guest * h * g0) / denom_G
            return h + hd + hg - h0

        # Solve for free host concentration
        h_free = brentq(mass_balance, 1e-20, h0, xtol=1e-14, maxiter=1000)

        # Remaining species follow directly from the free-host concentration
        d_free = d0 / (1 + Ka_dye * h_free)
        g_free = g0 / (1 + Ka_guest * h_free)
        return {
            'H': h_free,
            'D': d_free,
            'G': g_free,
            'HD': Ka_dye * h_free * d_free,
            'HG': Ka_guest * h_free * g_free,
        }

    except (ValueError, RuntimeError):
        return {k: np.nan for k in _COMPETITIVE_SPECIES}


def _competitive_species_grid(Ka_guest, Ka_dye, h0, d0_values, g0_values) -> dict:
    """Speciation across a titration for the competitive model.

    Exactly one of ``d0_values`` / ``g0_values`` is the titrant array; the other
    is a scalar broadcast to every point.  GDA (dye titrant) and IDA (guest
    titrant) both route through here so they share the per-point solve.
    """
    d0_values = np.atleast_1d(np.asarray(d0_values, dtype=float))
    g0_values = np.atleast_1d(np.asarray(g0_values, dtype=float))
    n = max(d0_values.size, g0_values.size)
    d0_values = np.broadcast_to(d0_values, (n,))
    g0_values = np.broadcast_to(g0_values, (n,))
    out = {k: np.empty(n, dtype=float) for k in _COMPETITIVE_SPECIES}
    for i in range(n):
        sp = competitive_species_point(Ka_guest, Ka_dye, h0, d0_values[i], g0_values[i])
        for k in _COMPETITIVE_SPECIES:
            out[k][i] = sp[k]
    return out


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
        Predicted signal value, NaN if the solve fails.
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
    signal_values = np.empty_like(d0_values)
    for i, d0 in enumerate(d0_values):
        signal_values[i] = competitive_signal_point(I0, Ka_guest, I_dye_free, I_dye_bound, Ka_dye, h0, d0, g0)
    return signal_values


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
    signal_values = np.empty_like(g0_values)
    for i, g0 in enumerate(g0_values):
        signal_values[i] = competitive_signal_point(I0, Ka_guest, I_dye_free, I_dye_bound, Ka_dye, h0, d0, g0)
    return signal_values


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
# The combined system is a cubic in the free-ligand concentration; rather than
# select a cubic root by hand we solve the (strictly monotonic) mass balance
# with Brent's method, matching the GDA/IDA solver style above.


def _solve_free_ligand_12(K1: float, K2: float, core_total: float, ligand_total: float) -> float:
    """Solve for free-ligand concentration in a stepwise 1:2 (core·ligand₂) system.

    A single *core* species C binds up to two *ligand* molecules L in two
    steps with stepwise association constants ``K1`` (C + L ⇌ CL) and
    ``K2`` (CL + L ⇌ CL₂)::

        [CL]  = K1 · [C] · l
        [CL2] = K1 · K2 · [C] · l²
        [C]   = core_total / (1 + K1·l + K1·K2·l²)

    where ``l`` is the free-ligand concentration.  Substituting these into
    the ligand mass balance ``ligand_total = l + [CL] + 2·[CL2]`` (the factor
    of two because CL₂ holds two ligands) gives a function of ``l`` whose
    derivative ``1 + core_total·(K1 + 4·K1·K2·l + K1²·K2·l²)/D²`` is strictly
    positive for non-negative parameters.  The balance is therefore strictly
    increasing, so it has a unique non-negative root and is bracketed by
    ``[0, ligand_total]`` (it equals ``-ligand_total ≤ 0`` at ``l = 0`` and is
    ``≥ 0`` at ``l = ligand_total``).  Brent's method finds it.

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
        Free-ligand concentration (M).  ``0.0`` when ``ligand_total <= 0``;
        ``nan`` if the bracket is degenerate (non-physical parameters), so
        callers propagate NaN rather than raising — matching the other
        equilibrium solvers in this module.
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
        return np.nan


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
    :func:`_solve_free_ligand_12`, then the remaining species follow from
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
        shape as ``g0_values``.  Entries are NaN where the solve fails.
    """
    g0 = np.asarray(g0_values, dtype=float)
    H = np.empty_like(g0)
    G = np.empty_like(g0)
    HG = np.empty_like(g0)
    HG2 = np.empty_like(g0)

    for i, g0_i in enumerate(g0):
        g = _solve_free_ligand_12(Ka_HG, Ka_HG2, h0, g0_i)
        if not np.isfinite(g):
            H[i] = G[i] = HG[i] = HG2[i] = np.nan
            continue
        denom = 1.0 + Ka_HG * g + Ka_HG * Ka_HG2 * g * g
        h = h0 / denom
        H[i] = h
        G[i] = g
        HG[i] = Ka_HG * h * g
        HG2[i] = Ka_HG * Ka_HG2 * h * g * g

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
        shape as ``g0_values``.  Entries are NaN where the solve fails.
    """
    g0 = np.asarray(g0_values, dtype=float)
    H = np.empty_like(g0)
    G = np.empty_like(g0)
    HG = np.empty_like(g0)
    H2G = np.empty_like(g0)

    for i, g0_i in enumerate(g0):
        h = _solve_free_ligand_12(Ka_HG, Ka_H2G, g0_i, h0)
        if not np.isfinite(h):
            H[i] = G[i] = HG[i] = H2G[i] = np.nan
            continue
        denom = 1.0 + Ka_HG * h + Ka_HG * Ka_H2G * h * h
        g = g0_i / denom
        H[i] = h
        G[i] = g
        HG[i] = Ka_HG * h * g
        H2G[i] = Ka_HG * Ka_H2G * h * h * g

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
