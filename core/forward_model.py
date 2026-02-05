"""Legacy Forward Model Functions - Mathematical Source of Truth.

Scientific Conventions
----------------------
This module uses association constants (Ka):
- Ka_dye = [HD]/([H][D])  for host-dye binding
- Ka_guest = [HG]/([H][G])  for host-guest binding

All Ka values are in M^-1 (inverse molar).

4-Parameter Signal Model
------------------------
Signal = I0 + I_dye_free * [D_free] + I_dye_bound * [HD]

Where:
- I0: background/offset signal
- I_dye_free: signal coefficient for free dye
- I_dye_bound: signal coefficient for bound dye (host-dye complex)

Assay Types
-----------
- DBA: Direct binding, fits Ka_dye
- GDA: Guest Displacement Assay - dye titrated, guest fixed, fits Ka_guest
- IDA: Indicator Displacement Assay - guest titrated, dye fixed, fits Ka_guest
"""

import numpy as np
from scipy.optimize import brentq


def compute_signal_dba(params, x_titrations, y_fixed):
    r"""Compute signal for Direct Binding Assay (DBA).

    This function handles both Dye-to-Host and Host-to-Dye binding assays,
    depending on the values of x_titrations and y_fixed.

    Parameters
    ----------
    params : tuple
        (I0, Ka_dye, I_dye_free, I_dye_bound) where:
        - I0: background signal
        - Ka_dye: association constant for host-dye (M^-1)
        - I_dye_free: signal coefficient for free dye
        - I_dye_bound: signal coefficient for host-dye complex
    x_titrations : array-like
        Titrant concentrations (M)
    y_fixed : float
        Fixed component concentration (M)

    Returns
    -------
    np.ndarray
        Predicted signal values.
    """
    I0, Ka_dye, I_dye_free, I_dye_bound = params
    Signal_values = []
    for x in x_titrations:
        delta = x - y_fixed
        a = Ka_dye
        b = Ka_dye * delta + 1
        c = -y_fixed
        discriminant = b**2 - 4 * a * c

        if discriminant < 0:
            Signal_values.append(np.nan)
            continue

        sqrt_discriminant = np.sqrt(discriminant)
        y1 = (-b + sqrt_discriminant) / (2 * a)
        y2 = (-b - sqrt_discriminant) / (2 * a)

        y = y1 if y1 >= 0 else y2 if y2 >= 0 else np.nan
        if np.isnan(y):
            Signal_values.append(np.nan)
            continue

        x_calc = y + delta
        hd = Ka_dye * y * x_calc  # Association form: [HD] = Ka * [H] * [D]
        Signal = I0 + I_dye_free * y + I_dye_bound * hd
        Signal_values.append(Signal)

    return np.array(Signal_values)


def compute_competitive_signal(params, Ka_dye, h0, d0, g0):
    """Compute signal for competitive binding (GDA/IDA).

    Solves the competitive equilibrium between host-dye and host-guest.

    Parameters
    ----------
    params : tuple
        (I0, Ka_guest, I_dye_free, I_dye_bound) where:
        - I0: background signal
        - Ka_guest: association constant for host-guest (M^-1)
        - I_dye_free: signal coefficient for free dye
        - I_dye_bound: signal coefficient for host-dye complex
    Ka_dye : float
        Association constant for host-dye (M^-1), pre-determined from DBA.
    h0 : float
        Total host concentration (M)
    d0 : float
        Total dye concentration (M)
    g0 : float
        Total guest concentration (M)

    Returns
    -------
    float
        Predicted signal value.
    """
    I0, Ka_guest, I_dye_free, I_dye_bound = params
    try:

        def equation_h(h):
            denom_Ka_dye = 1 + Ka_dye * h
            denom_Ka_guest = 1 + Ka_guest * h
            h_d = (Ka_dye * h * d0) / denom_Ka_dye
            h_g = (Ka_guest * h * g0) / denom_Ka_guest
            return h + h_d + h_g - h0

        h_sol = brentq(equation_h, 1e-20, h0, xtol=1e-14, maxiter=1000)
        denom_Ka_dye = 1 + Ka_dye * h_sol
        d_free = d0 / denom_Ka_dye
        h_d = Ka_dye * h_sol * d_free  # Association form
        Signal = I0 + I_dye_free * d_free + I_dye_bound * h_d
        return Signal
    except Exception:
        return np.nan


def compute_signal_gda(params, d0_values, Ka_dye, h0, g0):
    """Compute signal for Guest Displacement Assay (GDA).

    GDA: Dye is titrated into host+guest solution.
    - Titrant: Dye (d0 varies)
    - Fixed: Host (h0) and Guest (g0)
    - Fits: Ka_guest (association constant for host-guest)

    Parameters
    ----------
    params : tuple
        (I0, Ka_guest, I_dye_free, I_dye_bound)
    d0_values : array-like
        Dye concentrations (M) - the titrant
    Ka_dye : float
        Association constant for host-dye (M^-1), pre-determined from DBA.
    h0 : float
        Total host concentration (M)
    g0 : float
        Total guest concentration (M) - fixed

    Returns
    -------
    np.ndarray
        Predicted signal values.
    """
    signal_values = np.empty_like(d0_values)
    for i, d0 in enumerate(d0_values):
        signal = compute_competitive_signal(params, Ka_dye, h0, d0, g0)
        signal_values[i] = signal
    return signal_values


def compute_signal_ida(params, g0_values, Ka_dye, h0, d0):
    """Compute signal for Indicator Displacement Assay (IDA).

    IDA: Guest is titrated into host+dye solution.
    - Titrant: Guest (g0 varies)
    - Fixed: Host (h0) and Dye (d0)
    - Fits: Ka_guest (association constant for host-guest)

    Parameters
    ----------
    params : tuple
        (I0, Ka_guest, I_dye_free, I_dye_bound)
    g0_values : array-like
        Guest concentrations (M) - the titrant
    Ka_dye : float
        Association constant for host-dye (M^-1), pre-determined from DBA.
    h0 : float
        Total host concentration (M)
    d0 : float
        Total dye concentration (M) - fixed

    Returns
    -------
    list
        Predicted signal values.
    """
    signal_values = []
    for g0 in g0_values:
        signal = compute_competitive_signal(params, Ka_dye, h0, d0, g0)
        signal_values.append(signal)
    return signal_values
