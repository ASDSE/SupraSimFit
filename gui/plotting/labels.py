"""HTML display labels for parameter names and units.

Used by FitSummaryWidget and plot annotations to render math-style names
in Qt widgets that support HTML (QLabel, QFormLayout, pg.TextItem).
"""

from __future__ import annotations

import math

PARAM_LABELS: dict[str, str] = {
    "Ka_guest":    "K<sub>a,guest</sub>",
    "Ka_dye":      "K<sub>a,dye</sub>",
    "I0":          "I<sub>0</sub>",
    "I_dye_free":  "I<sub>Dye,free</sub>",
    "I_dye_bound": "I<sub>Dye,bound</sub>",
    "slope":       "slope",
    "intercept":   "intercept",
}

UNIT_LABELS: dict[str, str] = {
    "M^-1": "M<sup>&#8722;1</sup>",
    "a.u.": "a.u.",
}


def fmt_param(name: str) -> str:
    """Return HTML display label for a parameter name, fallback to raw name.

    Parameters
    ----------
    name : str
        Internal parameter key (e.g. ``"Ka_guest"``).

    Returns
    -------
    str
        HTML string (e.g. ``"K<sub>a,guest</sub>"``).
    """
    return PARAM_LABELS.get(name, name)


def _fmt_value(value: float) -> str:
    """Format a float for display.

    Uses scientific notation for |v| >= 1e5 or |v| < 1e-3 (and v != 0).
    Returns ``"NaN"`` / ``"Inf"`` for special values.

    Parameters
    ----------
    value : float

    Returns
    -------
    str
    """
    if math.isnan(value):
        return "NaN"
    if math.isinf(value):
        return "Inf" if value > 0 else "-Inf"
    if value == 0.0:
        return "0.0"
    abs_v = abs(value)
    if abs_v >= 1e5 or abs_v < 1e-3:
        return f"{value:.4e}"
    return f"{value:.6g}"


def fmt_unit(unit: str) -> str:
    """Return HTML display label for a unit string, fallback to raw string.

    Parameters
    ----------
    unit : str
        Raw unit string (e.g. ``"M^-1"``).

    Returns
    -------
    str
        HTML string (e.g. ``"M<sup>&#8722;1</sup>"``).
    """
    return UNIT_LABELS.get(unit, unit)
