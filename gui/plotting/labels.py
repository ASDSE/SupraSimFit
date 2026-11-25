"""HTML display labels for parameter names.

Used by FitSummaryWidget and plot annotations to render math-style names
in Qt widgets that support HTML (QLabel, QFormLayout, pg.TextItem).
:func:`plain_label` flattens such a label for widgets that paint plain text,
and :func:`fmt_r2` renders a coefficient of determination for either.

Value and unit formatting is handled by Pint's built-in formatters:
  - ``f"{Q_(value, unit):.3g~H}"`` for HTML values+units
  - ``f"{Q_(value, 'dimensionless'):.3g~P}"`` for pretty Unicode values
  - ``f"{ureg.Unit(unit_str):~H}"`` for HTML unit display

Reciprocal units (e.g. 1/M) are post-processed into negative-exponent
notation (M⁻¹ / M<sup>−1</sup>) because Pint 0.25 does not have a
format modifier for that.
"""

from __future__ import annotations

import math
import re

from core.units import ureg

_SUPERSCRIPT_DIGITS = str.maketrans('0123456789-−', '⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁻')
_SUBSCRIPT_DIGITS = str.maketrans('0123456789', '₀₁₂₃₄₅₆₇₈₉')
_SUB_TAG_RE = re.compile(r'<sub>(.*?)</sub>')
_SUP_TAG_RE = re.compile(r'<sup>(.*?)</sup>')
_ANY_TAG_RE = re.compile(r'<[^>]+>')

# Decimals that separate every R² a double can hold from 1: the largest double
# below 1 is 1 − 1.1×10⁻¹⁶.
_R2_MAX_DECIMALS = 17

# Decimals a log₁₀ reading is held between, whatever its spread asks for.
_LOG10_DECIMALS = (2, 6)


def _format_exponent_unicode(exp: int) -> str:
    """Convert an integer exponent to Unicode superscript, e.g. 5 → '⁵', -3 → '⁻³'."""
    return str(exp).translate(_SUPERSCRIPT_DIGITS)


def plain_label(html: str) -> str:
    """Flatten an HTML display label into plain text.

    Digits inside ``<sub>`` and ``<sup>`` become their Unicode sub- and
    superscripts and every remaining tag is dropped, so the label reads in
    widgets that paint plain text — pyqtgraph axis ticks, combo box entries,
    check box labels.

    Parameters
    ----------
    html : str
        A display label such as ``'[Host]<sub>0</sub>'`` or ``'M<sup>−1</sup>'``.

    Returns
    -------
    str
        The same label as plain text: ``'[Host]₀'``, ``'M⁻¹'``.
    """
    text = _SUB_TAG_RE.sub(lambda m: m.group(1).translate(_SUBSCRIPT_DIGITS), html)
    text = _SUP_TAG_RE.sub(lambda m: m.group(1).translate(_SUPERSCRIPT_DIGITS), text)
    return _ANY_TAG_RE.sub('', text)


def fmt_r2(value: float, floor: float | None = None) -> str:
    """*value* as an R², with enough decimals that it reads for what it is.

    Four decimals at least, and more where four would hide how far below 1 the
    value lies, round it up to 1, or carry it across *floor*. A value below 1 or
    below *floor* then always reads below it, so a shown R² never appears to
    meet a mark it misses: ``0.9908``, ``0.999984``, and ``0.98996`` against a
    floor of 0.99.

    Parameters
    ----------
    value : float
        The coefficient of determination to render.
    floor : float or None
        A mark the reading must stay on its own side of, such as the Min R² a
        fit has to clear. ``None`` leaves only the distance to 1 to satisfy.

    Returns
    -------
    str
        The value in fixed-point notation, four decimals or more — as many as
        seventeen, which tells any two double-precision R² values apart.
    """
    gap = 1.0 - value
    start = 4 if not math.isfinite(gap) or gap <= 0 else max(4, math.ceil(-math.log10(gap)) + 1)
    for digits in range(min(start, _R2_MAX_DECIMALS), _R2_MAX_DECIMALS + 1):
        text = f'{value:.{digits}f}'
        shown = float(text)
        if (value >= 1.0 or shown < 1.0) and (floor is None or (value < floor) == (shown < floor)):
            break
    return text


def log10_decimals(stats: dict | None) -> int:
    """Decimals a log₁₀ reading is written to, so a value is never coarser than the spread beside it.

    A log₁₀ value sits between about 0 and 12 while its spread can be a few
    thousandths, and three or four significant figures would then round 8.9974
    to 9. Fixed decimals, enough for two figures of the tightest spread the row
    reports, keep the value and its spread on the same scale. A row whose pool
    reports no spread at all — a pool of one fit — has nothing to match, so it
    is written to the finest reading rather than the coarsest.

    Parameters
    ----------
    stats : dict or None
        The row's ``describe()`` statistics, or ``None`` when it has no pool.

    Returns
    -------
    int
        Between the two ends of ``_LOG10_DECIMALS``.
    """
    least, most = _LOG10_DECIMALS
    if stats is None:
        return 4
    spreads = [abs(stats['mad']), abs(stats['std']), stats['p84'] - stats['p16'], stats['max'] - stats['min']]
    tightest = min((spread for spread in spreads if spread > 0), default=0.0)
    if not tightest:
        return most
    return int(min(max(math.ceil(-math.log10(tightest)) + 1, least), most))


def fmt_log10(value: float, stats: dict | None) -> str:
    """*value* as a log₁₀ reading, to the decimals :func:`log10_decimals` gives *stats*.

    The summary table and the text report write a log₁₀ value and its spread
    through this, so the same fit reads the same on screen and in the file. A
    spread too tight for those decimals is written to four significant figures
    instead, so a number that is not zero never reads as zero.
    """
    text = f'{value:.{log10_decimals(stats)}f}'
    return f'{value:.4g}' if value and float(text) == 0.0 else text


def fmt_sci(value: float, digits: int = 2) -> str:
    """*value* to *digits* significant figures: plain from 0.01 to 999, else as ``1.7×10⁸``.

    Examples: ``150``, ``0.012``, ``3.22×10³`` (``digits=3``), ``5.7×10⁴``.
    """
    if value == 0 or not math.isfinite(value):
        return f'{value:g}'
    rounded = float(f'{value:.{digits}g}')
    exp = math.floor(math.log10(abs(rounded)))
    if -2 <= exp <= 2:
        return f'{rounded:.{max(digits - 1 - exp, 0)}f}'
    return f'{rounded / 10.0**exp:.{digits - 1}f}×10{_format_exponent_unicode(exp)}'


def _canonical_unit(unit_str: str) -> str:
    """Map the signal unit's display alias ``a.u.`` to its parseable token ``au``.

    Pint parses the dotted ``a.u.`` as ``year · atomic_mass_unit`` (the dots are
    multiplications), so any unit string reaching the formatters below must use
    ``au``. The registry stores the y-axis unit as ``a.u.`` for raw display; this
    guard keeps that alias from garbling if it is ever formatted here.
    """
    return 'au' if unit_str.strip() in ('a.u.', 'a.u') else unit_str


PARAM_LABELS: dict[str, str] = {
    'Ka_guest': '<b>K<sub>a(G)</sub></b>',
    'Ka_dye': '<b>K<sub>a(D)</sub></b>',
    'I0': '<b>I<sub>0</sub></b>',
    'I_dye_free': '<b>I<sub>D</sub></b>',
    'I_dye_bound': '<b>I<sub>HD</sub></b>',
    'slope': '<b>slope</b>',
    'intercept': '<b>intercept</b>',
    # Stepwise 1:2 / 2:1 host–guest parameters
    'Ka_HG': '<b>K<sub>a(HG)</sub></b>',
    'Ka_HG2': '<b>K<sub>a(HG₂)</sub></b>',
    'Ka_H2G': '<b>K<sub>a(H₂G)</sub></b>',
    'I_G': '<b>I<sub>G</sub></b>',
    'I_H': '<b>I<sub>H</sub></b>',
    'I_HG': '<b>I<sub>HG</sub></b>',
    'I_HG2': '<b>I<sub>HG₂</sub></b>',
    'I_H2G': '<b>I<sub>H₂G</sub></b>',
}


def fmt_param(name: str) -> str:
    """Return HTML display label for a parameter name, fallback to raw name."""
    return PARAM_LABELS.get(name, name)


# Plain-text (no HTML) labels for widgets that cannot render rich text,
# e.g. QCheckBox toggle labels. Uses Unicode subscripts where unambiguous.
PARAM_LABELS_PLAIN: dict[str, str] = {
    'Ka_guest': 'Ka(G)',
    'Ka_dye': 'Ka(D)',
    'I0': 'I₀',
    'I_dye_free': 'I(D)',
    'I_dye_bound': 'I(HD)',
    'slope': 'slope',
    'intercept': 'intercept',
    'Ka_HG': 'Ka(HG)',
    'Ka_HG2': 'Ka(HG₂)',
    'Ka_H2G': 'Ka(H₂G)',
    'I_G': 'I(G)',
    'I_H': 'I(H)',
    'I_HG': 'I(HG)',
    'I_HG2': 'I(HG₂)',
    'I_H2G': 'I(H₂G)',
}


def fmt_param_plain(name: str) -> str:
    """Return a plain-text (no HTML) parameter label, fallback to raw name."""
    return PARAM_LABELS_PLAIN.get(name, name)


# Bracketed concentration labels for equilibrium species, keyed by the species
# names returned by ``BaseAssay.species()``.  Unicode subscripts so they render
# in plain-text widgets (legend entries, hover readouts) as well as rich text.
SPECIES_LABELS: dict[str, str] = {
    'H': '[H]',
    'D': '[D]',
    'G': '[G]',
    'HD': '[HD]',
    'HG': '[HG]',
    'HG2': '[HG₂]',
    'H2G': '[H₂G]',
}


def fmt_species(key: str, *, brackets: bool = True) -> str:
    """Return a concentration label for a species, e.g. ``HG2`` → ``[HG₂]``.

    ``brackets=False`` drops them (``HG₂``) — used for the compact plot legend,
    where the concentration-bracket notation isn't needed.
    """
    label = SPECIES_LABELS.get(key, f'[{key}]')
    return label if brackets else label.strip('[]')


def fmt_unit_html(unit_str: str) -> str:
    """Format a unit string as abbreviated HTML with negative exponents.

    Pint's ``~H`` formatter renders reciprocal units as fractions (e.g.
    ``1/M``).  This function post-processes the output to use superscript
    negative exponents instead (e.g. ``M<sup>−1</sup>``).
    """
    if not unit_str:
        return ''
    formatted = f'{ureg.Unit(_canonical_unit(unit_str)):~H}'
    if formatted.startswith('1/'):
        base = formatted[2:].strip()
        return f'{base}<sup>−1</sup>'
    return formatted


def fmt_unit_pretty(unit_str: str) -> str:
    """Format a unit string as abbreviated Unicode with negative exponents.

    Like :func:`fmt_unit_html` but returns plain Unicode (e.g. ``M⁻¹``)
    suitable for text files.
    """
    if not unit_str:
        return ''
    formatted = f'{ureg.Unit(_canonical_unit(unit_str)):~P}'
    if formatted.startswith('1/'):
        base = formatted[2:].strip()
        return f'{base}⁻¹'
    return formatted
