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

Signal Model
------------
Signal = I0 + I_dye_free * [D_free] + I_dye_bound * [HD]

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


def dba_signal(
    I0: float,
    Ka_dye: float,
    I_dye_free: float,
    I_dye_bound: float,
    x_titrant: np.ndarray,
    y_fixed: float,
) -> np.ndarray:
    """Compute DBA signal for host-dye equilibrium.

    Works for both Host→Dye and Dye→Host titrations depending on which
    concentration is varied (x_titrant) vs fixed (y_fixed).

    The equilibrium is: H + D ⇌ HD with Ka_dye = [HD] / ([H][D])

    Parameters
    ----------
    I0 : float
        Background signal intensity.
    Ka_dye : float
        Association constant for host-dye binding (M^-1).
    I_dye_free : float
        Signal coefficient for free dye.
    I_dye_bound : float
        Signal coefficient for host-dye complex.
    x_titrant : np.ndarray
        Titrant concentrations (M).
    y_fixed : float
        Fixed component concentration (M).

    Returns
    -------
    np.ndarray
        Predicted signal values.

    Notes
    -----
    The quadratic solution comes from mass balance:
        x_total = x_free + [HD]
        y_total = y_free + [HD]
    Combined with Ka_dye = [HD] / (x_free * y_free), we get:
        [HD] = Ka_dye * x_free * y_free
    Substituting gives a quadratic in y_free.
    """
    signal_values = np.empty_like(x_titrant)

    for i, x in enumerate(x_titrant):
        delta = x - y_fixed

        # Quadratic coefficients for y_free (free concentration of fixed species)
        # Ka_dye * y_free^2 + (Ka_dye * delta + 1) * y_free - y_fixed = 0
        a = Ka_dye
        b = Ka_dye * delta + 1
        c = -y_fixed

        discriminant = b**2 - 4 * a * c

        if discriminant < 0:
            signal_values[i] = np.nan
            continue

        sqrt_disc = np.sqrt(discriminant)
        y1 = (-b + sqrt_disc) / (2 * a)
        y2 = (-b - sqrt_disc) / (2 * a)

        # Choose physically meaningful (non-negative) root
        y_free = y1 if y1 >= 0 else (y2 if y2 >= 0 else np.nan)

        if np.isnan(y_free):
            signal_values[i] = np.nan
            continue

        x_free = y_free + delta
        hd_complex = Ka_dye * y_free * x_free

        # Signal = I0 + I_dye_free * [D_free] + I_dye_bound * [HD]
        signal_values[i] = I0 + I_dye_free * y_free + I_dye_bound * hd_complex

    return signal_values


# =============================================================================
# =============================================================================
# Competitive Binding Models (GDA / IDA)
# =============================================================================


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

    This is the core calculation for both GDA and IDA. The system has two
    competing equilibria:
        H + D ⇌ HD  (Ka_dye = [HD]/([H][D]))
        H + G ⇌ HG  (Ka_guest = [HG]/([H][G]))

    Parameters
    ----------
    I0 : float
        Background signal intensity.
    Ka_guest : float
        Association constant for guest/indicator (M^-1). This is fitted.
    I_dye_free : float
        Signal coefficient for free dye.
    I_dye_bound : float
        Signal coefficient for host-dye complex.
    Ka_dye : float
        Known association constant for host-dye (M^-1).
    h0 : float
        Total host concentration (M).
    d0 : float
        Total dye concentration (M).
    g0 : float
        Total guest/indicator concentration (M).

    Returns
    -------
    float
        Predicted signal value.

    Notes
    -----
    We solve for free host [H] using Brent's method on the mass balance:
        h0 = [H] + [HD] + [HG]
           = [H] + Ka_dye*[H]*d0/(1 + Ka_dye*[H]) + Ka_guest*[H]*g0/(1 + Ka_guest*[H])
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

        # Calculate species concentrations
        denom_D = 1 + Ka_dye * h_free
        d_free = d0 / denom_D
        hd_complex = Ka_dye * h_free * d_free

        # Signal from free dye and complex
        return I0 + I_dye_free * d_free + I_dye_bound * hd_complex

    except (ValueError, RuntimeError):
        return np.nan


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
