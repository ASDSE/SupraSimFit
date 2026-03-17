"""HTML display labels for parameter names and units.

Used by FitSummaryWidget and plot annotations to render math-style names
in Qt widgets that support HTML (QLabel, QFormLayout, pg.TextItem).
"""

from __future__ import annotations

import math

PARAM_LABELS: dict[str, str] = {
    'Ka_guest': '<b>K<sub>a(G)</sub></b>',
    'Ka_dye': '<b>K<sub>a(D)</sub></b>',
    'I0': '<b>I<sub>0</sub></b>',
    'I_dye_free': '<b>I<sub>D</sub></b>',
    'I_dye_bound': '<b>I<sub>HD</sub></b>',
    'slope': '<b>slope</b>',
    'intercept': '<b>intercept</b>',
}

UNIT_LABELS: dict[str, str] = {
    'M^-1': 'M<sup>&#8722;1</sup>',
    'a.u.': 'a.u.',
}

_SUPERSCRIPT_TABLE = {
    '0': '⁰',
    '1': '¹',
    '2': '²',
    '3': '³',
    '4': '⁴',
    '5': '⁵',
    '6': '⁶',
    '7': '⁷',
    '8': '⁸',
    '9': '⁹',
    '-': '⁻',
    '+': '⁺',
}


def _to_superscript(n: int) -> str:
    """Convert an integer exponent to Unicode superscript characters."""
    return ''.join(_SUPERSCRIPT_TABLE.get(c, c) for c in str(n))


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


def _fmt_value(value: float, decimals: int = 2) -> str:
    """Format a float for display using ×10ⁿ notation.

    Uses scientific notation for |v| >= 1e5 or |v| < 1e-3 (and v != 0).
    Returns ``"NaN"`` / ``"Inf"`` for special values.

    Parameters
    ----------
    value : float
    decimals : int
        Number of significant figures (default 2).

    Returns
    -------
    str
    """
    if math.isnan(value):
        return 'NaN'
    if math.isinf(value):
        return 'Inf' if value > 0 else '-Inf'
    if value == 0.0:
        return '0.0'
    abs_v = abs(value)
    fmt = f'.{decimals}g'
    if abs_v >= 1e3 or abs_v < 1e-3:
        exp = int(math.floor(math.log10(abs_v)))
        mantissa = value / 10**exp
        exp_str = _to_superscript(exp)
        if abs(mantissa - 1.0) < 1e-9:
            return f'10{exp_str}'
        elif abs(mantissa + 1.0) < 1e-9:
            return f'\u221210{exp_str}'
        else:
            return f'{mantissa:{fmt}}\xd710{exp_str}'  # × = \xd7
    return f'{value:{fmt}}'


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
