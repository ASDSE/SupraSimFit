"""HTML display labels for parameter names.

Used by the views, the reports and the plots to render math-style names
in Qt widgets that support HTML (QLabel, QFormLayout, pg.TextItem).
:func:`plain_label` flattens such a label for widgets that paint plain text,
:func:`fmt_r2` renders a coefficient of determination for either,
:func:`fmt_value` writes every fitted value and interval edge, and
:func:`fmt_interval_html` / :func:`fmt_interval_plain` write a confidence
interval the same way wherever one is reported. An estimate that sits on an
end of its search box reads in words (:func:`fmt_bound_estimate`), and a stated
input uncertainty in one notation (:func:`stated_uncertainty`).

:func:`verdict_headline`, :func:`verdict_sentence`, :func:`fmt_shift`,
:func:`fmt_misfit` and :func:`fmt_p` write what the diagnostics of a fit say —
whether the model and the entered inputs describe the data, and where the fit
put the inputs it was free to move — so Fit results, Ka confidence and the
exported report say it in the same words.
:func:`one_step_sentence` says what the test of a second binding step found,
:func:`widening_sentences` why an interval is wider than the plain F test's,
:func:`region_sentence` why the joint region of a pair is, and :func:`offset_note` when a signal offset held at zero may be why the curve
misses the data.

Units are formatted by Pint's built-in formatters (``f"{ureg.Unit(unit_str):~H}"``
for HTML, ``~P`` for pretty Unicode).

Reciprocal units (e.g. 1/M) are post-processed into negative-exponent
notation (M⁻¹ / M<sup>−1</sup>) because Pint 0.25 does not have a
format modifier for that.
"""

from __future__ import annotations

import math
import re
from html import escape, unescape
from typing import Iterable, Sequence

from core.units import ureg

_SUPERSCRIPT_DIGITS = str.maketrans('0123456789-−', '⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁻')
_SUBSCRIPT_DIGITS = str.maketrans('0123456789', '₀₁₂₃₄₅₆₇₈₉')

#: The narrow no-break space the design sets around × and before %, σ and a unit's power:
#: it keeps a number whole where a line of text wraps.
THIN = '\u202f'


def superscript(n: int) -> str:
    """``-3`` as ``⁻³``."""
    return str(n).translate(_SUPERSCRIPT_DIGITS)


def spaced(text: str) -> str:
    """``1.59×10⁸`` as the design writes it in prose and headlines: ``1.59 × 10⁸``, unbreakable."""
    return text.replace('×', f'{THIN}×{THIN}')


def times_ten(e: int) -> str:
    """The `` × 10ⁿ`` a mantissa is followed by; nothing for ``n = 0``."""
    return '' if e == 0 else f'{THIN}×{THIN}10{superscript(e)}'


_SUB_TAG_RE = re.compile(r'<sub>(.*?)</sub>')
_SUP_TAG_RE = re.compile(r'<sup>(.*?)</sup>')
_ANY_TAG_RE = re.compile(r'<[^>]+>')
# The *a* that opens the subscript of an association constant: K<sub>a</sub>, K<sub>a,dye</sub>, K<sub>a(G)</sub>.
_KA_SUBSCRIPT_RE = re.compile(r'^a(?=$|[,(])')

#: What a sensitivity run says while it stops: the status bar and the Ka Sensitivity tab both show it.
STOPPING_TEXT = 'Stopping — finishing the fits already running…'

# Decimals that separate every R² a double can hold from 1: the largest double
# below 1 is 1 − 1.1×10⁻¹⁶.
_R2_MAX_DECIMALS = 17

# Decimals a log₁₀ reading is held between, whatever its spread asks for.
_LOG10_DECIMALS = (2, 6)


def _format_exponent_unicode(exp: int) -> str:
    """Convert an integer exponent to Unicode superscript, e.g. 5 → '⁵', -3 → '⁻³'."""
    return str(exp).translate(_SUPERSCRIPT_DIGITS)


def and_join(items) -> str:
    """Names as a sentence lists them: ``a``, ``a and b``, ``a, b and c``; ``''`` for none."""
    items = list(items)
    if len(items) <= 1:
        return ''.join(items)
    return f'{", ".join(items[:-1])} and {items[-1]}'


def _subscript(text: str) -> str:
    """The text of a ``<sub>`` in plain text: its digits subscripted, and the *a* of an association constant too.

    ``K<sub>a,dye</sub>`` reads ``Kₐ,dye`` and ``K<sub>a(G)</sub>`` reads ``Kₐ(G)``, as the
    glossary writes Kₐ (DESIGN.md §9); a word such as ``max`` keeps its letters.
    """
    return _KA_SUBSCRIPT_RE.sub('ₐ', text).translate(_SUBSCRIPT_DIGITS)


def plain_label(html: str) -> str:
    """Flatten an HTML display label into plain text.

    Digits inside ``<sub>`` and ``<sup>`` become their Unicode sub- and
    superscripts, as does the *a* of an association constant's subscript
    (``K<sub>a,dye</sub>`` → ``Kₐ,dye``); every remaining tag is dropped and the entities left behind
    become the characters they stand for, so the label reads in widgets that
    paint plain text — pyqtgraph axis ticks, combo box entries, check box
    labels. A name the user typed reaches a label escaped, and an ampersand in
    it has to read as an ampersand here.

    Parameters
    ----------
    html : str
        A display label such as ``'[Host]<sub>0</sub>'`` or ``'M<sup>−1</sup>'``.

    Returns
    -------
    str
        The same label as plain text: ``'[Host]₀'``, ``'M⁻¹'``.
    """
    text = _SUB_TAG_RE.sub(lambda m: _subscript(m.group(1)), html)
    text = _SUP_TAG_RE.sub(lambda m: m.group(1).translate(_SUPERSCRIPT_DIGITS), text)
    return unescape(_ANY_TAG_RE.sub('', text))


def fmt_r2(value: float) -> str:
    """*value* as an R², with enough decimals that it reads for what it is.

    Four decimals at least, and more where four would hide how far below 1 the
    value lies or round it up to 1. A value below 1 then always reads below 1,
    so a fit that does not describe the data exactly is never shown as one that
    does: ``0.9908``, ``0.999984``.

    Parameters
    ----------
    value : float
        The coefficient of determination to render.

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
        if value >= 1.0 or float(text) < 1.0:
            break
    return text


#: What an interval endpoint reads where the data do not close it, and what the
#: whole interval reads where they close neither end. A side is open when the
#: profile stays inside the F-test threshold as far as it goes, so no number
#: would be the limit; words say that, where a number would claim a bound.
NO_UPPER = 'no upper limit'
NO_LOWER = 'no lower limit'
UNLIMITED = 'not limited by the data'

#: Marks a reported interval whose accepted values come in separate stretches,
#: wherever the bracket alone would read as one connected range.
SPLIT_MARK = '†'

#: What that mark means, in one sentence, wherever a split interval is reported.
SPLIT_NOTE = (
    'not every value inside this interval explains the data well enough: the ones that do come in separate '
    'stretches and the interval spans all of them. Ka confidence shows where they are.'
)

#: Said of an open side the binding model cannot be solved past: the edge is
#: where the arithmetic stops, not where the data stop, so more points cannot
#: move it. The bracket reads the same as a side more points would close.
UNSOLVABLE_NOTE = (
    'the open side is where the binding model stops having a solution, not where the data stop, so more '
    'measurements cannot close it.'
)


def fmt_interval_html(low: str, high: str, open_low: bool, open_high: bool) -> str:
    """A confidence interval as HTML, from endpoints already formatted.

    ``[1.3×10⁸, 1.9×10⁸]`` where the data close both ends, and the open side in
    words — italic, so prose is not read as a number — where they do not:
    ``[1.3×10⁸, <i>no upper limit</i>]``, ``[<i>no lower limit</i>, 1.9×10⁸]``,
    ``[<i>not limited by the data</i>]``.

    Parameters
    ----------
    low, high : str
        The endpoints, formatted by the caller so every reported number of one
        parameter reads the same way.
    open_low, open_high : bool
        Per endpoint, whether the interval reaches as far as the profile goes
        rather than being closed by the data.
    """
    return _interval_text(low, high, open_low, open_high, '<i>{}</i>')


def fmt_interval_plain(low: str, high: str, open_low: bool, open_high: bool) -> str:
    """A confidence interval as plain text; see :func:`fmt_interval_html`.

    ``[1.3×10⁸, no upper limit]`` — the same wording, for a file or a widget
    that paints plain text.
    """
    return _interval_text(low, high, open_low, open_high, '{}')


def _interval_text(low: str, high: str, open_low: bool, open_high: bool, words: str) -> str:
    """The shared interval wording, with the prose phrases wrapped in *words*."""
    if open_low and open_high:
        return f'[{words.format(UNLIMITED)}]'
    lo = words.format(NO_LOWER) if open_low else low
    hi = words.format(NO_UPPER) if open_high else high
    return f'[{lo}, {hi}]'


def log10_decimals(stats: dict | None) -> int:
    """Decimals a log₁₀ reading is written to, so a value is never coarser than the spread beside it.

    A log₁₀ value sits between about 0 and 12 while its spread can be a few
    thousandths, and three or four significant figures would then round 8.9974
    to 9. Fixed decimals, enough for two figures of the tightest spread the row
    reports, keep the value and its spread on the same scale. A row whose
    statistics report no spread at all has nothing to match, so it is written to
    the finest reading rather than the coarsest.

    Parameters
    ----------
    stats : dict or None
        The row's ``describe()`` statistics, or ``None`` when it reports none.

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

    The text report and the summary of a sensitivity run's samples write a log₁₀
    value, its interval and its spread through this, so the same fit reads the same
    on screen and in the file. A
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


#: Significant figures of every fitted value and interval edge a view shows.
_VALUE_DIGITS = 3


def fmt_value(value: float) -> str:
    """A fitted value or an interval edge as every view writes it: ``8.00×10⁴``, ``2.41×10³``, ``150``, ``0.0120``.

    Three significant figures with the trailing zeros kept, so the digits
    shown are the digits meant. Fit results, Ka confidence and the
    text report all write a number of a fit through this, and one edge of one
    interval reads the same wherever it stands.
    """
    return fmt_sci(value, _VALUE_DIGITS)


def fmt_bound_estimate(
    side: str, low: str | None, high: str | None, open_low: bool, open_high: bool, *, html: bool
) -> str:
    """An estimate that sits on an end of its Ka search box, in words: ``not limited below 2.41×10³``.

    The search stopped at the box because the data do not limit Ka on that
    side, so the value it stopped at is the box, not a measurement, and no view
    prints it as one. What the data do say is the closed end of the interval:
    Ka lies below it (``side == 'low'``) or above it (``'high'``). With no
    closed end they say nothing either way.

    Parameters
    ----------
    side : str
        ``'low'`` or ``'high'``: which end of its box the estimate sits on.
    low, high : str or None
        The interval's ends, formatted by the caller as every other number of
        the row is; ``None`` for a binding constant that carries no interval.
    open_low, open_high : bool
        Per end, whether the interval reaches as far as the profile goes.
    html : bool
        Whether the result goes into a rich-text widget, where the words are
        set in italics so prose is not read as a number.
    """
    words = '<i>{}</i>' if html else '{}'
    below = side == 'low'
    if low is None and high is None:
        return words.format(f'at the {"lower" if below else "upper"} end of its search range')
    closed = (high, open_high) if below else (low, open_low)
    if closed[1]:
        return words.format(UNLIMITED)
    return f'{words.format("not limited below" if below else "not limited above")} {closed[0]}'


def fmt_estimate(value: float, at_bound: str, interval, open_ends, fmt=fmt_value, *, html: bool) -> str:
    """One estimate as every view writes it: its value, or in words where it sits on an end of its Ka search box.

    Parameters
    ----------
    value : float
        The estimate, in the row's own scale.
    at_bound : str
        ``''``, or which end of its search box the estimate sits on (``'low'``,
        ``'high'``), as :class:`~core.pipeline.reporting.ParameterSummary`
        records it.
    interval : tuple[float, float] or None
        The interval beside the estimate, in the same scale; ``None`` where
        there is none.
    open_ends : tuple[bool, bool]
        Per end of *interval*, whether the data leave it open.
    fmt : Callable[[float], str]
        How the row writes a number: :func:`fmt_value`, or a log₁₀ reading.
    html : bool
        Whether the result goes into a rich-text widget.
    """
    if not at_bound:
        return fmt(value)
    ends = (None, None) if interval is None else (fmt(interval[0]), fmt(interval[1]))
    return fmt_bound_estimate(at_bound, *ends, *open_ends, html=html)


def own_estimates(result, keys, *, html: bool, fmt=fmt_value) -> list[str]:
    """One replicate's own fit of each of *keys*, as the replicate tables write it; ``—`` for a key it lacks.

    Read through :func:`~core.pipeline.reporting.summarize_parameters`, so a
    replicate whose own binding constant ran to a bound of its search box reads
    in words, as every other estimate does. *fmt* writes a number, as
    :func:`fmt_estimate` takes it.
    """
    from core.pipeline.reporting import summarize_parameters

    rows = {spec.key: spec for spec in summarize_parameters(result) if not spec.is_log}
    return [
        '—'
        if key not in rows
        else fmt_estimate(
            rows[key].estimate,
            rows[key].estimate_at_bound,
            rows[key].interval,
            rows[key].interval_open,
            fmt,
            html=html,
        )
        for key in keys
    ]


#: How the single-replicate fits relate to the interval beside them. Both are
#: honest and they answer different questions, so the reader is told which.
REPLICATES_RELATION = (
    "These show how far the replicates' own fits disagree. The interval says how precisely the fit of their "
    "average pins Ka down, which is a different question, so a single replicate's value can fall outside it."
)


def replicate_summary(rows, n: int, name, unit) -> str:
    """The binding constants' single-replicate fits, as one line beside the interval; ``''`` where there are none.

    ``Single-replicate fits (inputs as entered): Ka(G) median 4.56×10⁴, range
    [4.49×10⁴, 8.16×10⁴] M⁻¹.`` Each replicate the fit used, fitted on its own
    with the inputs as entered; a fit that ran to a bound of its search range
    is not a value of Ka and is counted instead of summarised. One sentence
    then says how these figures relate to the interval.

    Parameters
    ----------
    rows : Sequence[core.pipeline.reporting.ParameterSummary]
        The binding-constant rows of the fit (no log₁₀ twins).
    n : int
        How many replicates the fit used, each of which has a fit of its own.
    name, unit : Callable[[ParameterSummary], str]
        The row's name and its unit, formatted for where the line goes.
    """
    figures, bounds = [], []
    for spec in rows:
        stats = spec.replicates
        if stats is not None:
            span = f'[{fmt_value(stats["min"])}, {fmt_value(stats["max"])}]'
            figures.append(f'{name(spec)} median {fmt_value(stats["median"])}, range {f"{span} {unit(spec)}".strip()}')
        count = spec.replicates_at_bound
        if count:
            if stats is None:
                tail = 'so too few are left to summarise'
            else:
                tail = f'and {"is" if count == 1 else "are"} left out of these figures'
            bounds.append(
                f'{count} of {n} single-replicate fits of {name(spec)} ran to a bound of its search range, which '
                f'is not a value of it, {tail}.'
            )
    if not figures and not bounds:
        return ''
    head = f'Single-replicate fits (inputs as entered): {"; ".join(figures)}.' if figures else ''
    return ' '.join(part for part in (head, *bounds, REPLICATES_RELATION if figures else '') if part)


def fmt_spread(sd_decades: float, *, html: bool) -> str:
    """A spread of log₁₀(Ka) as decades and as the factor Ka spreads by: ``0.084 decades (×/÷ 1.21)``.

    Decades are what the analysis works in; the factor is what they mean for Ka
    itself — a standard deviation of 0.084 decades is a Ka known to within a
    factor of 1.21 either way — so a spread is written as both wherever it is
    reported. Two significant figures on the spread, the reading an uncertainty
    carries, and three on the factor it maps to.

    Parameters
    ----------
    sd_decades : float
        The spread: one standard deviation of log₁₀(Ka), in decades.
    html : bool
        Whether the result goes into a rich-text widget. There the factor is
        tied to its sign with a non-breaking space, so a wrapped line never
        leaves ``×/÷`` standing at the end of one.

    Raises
    ------
    ValueError
        For anything that is not a standard deviation. A spread that could not
        be worked out is said in words by the caller, where there is room to
        say why.
    """
    if not (math.isfinite(sd_decades) and sd_decades >= 0.0):
        raise ValueError(f'{sd_decades} is not a spread: a standard deviation is a finite number, zero or more.')
    space = '&nbsp;' if html else ' '
    return f'{fmt_sci(sd_decades, 2)} decades (×/÷{space}{fmt_sci(10.0**sd_decades, 3)})'


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


#: Each parameter in plain text, for accessible names, sentences and widgets that paint
#: plain text: a binding constant by its glossary name (DESIGN.md §9), ``Kₐ guest``, and a
#: signal coefficient as its HTML label writes it, a letter subscript after ``_``: ``I_D``.
PARAM_LABELS_PLAIN: dict[str, str] = {
    'Ka_guest': 'Kₐ guest',
    'Ka_dye': 'Kₐ,dye',
    'I0': 'I₀',
    'I_dye_free': 'I_D',
    'I_dye_bound': 'I_HD',
    'slope': 'slope',
    'intercept': 'intercept',
    'Ka_HG': 'Kₐ HG',
    'Ka_HG2': 'Kₐ HG₂',
    'Ka_H2G': 'Kₐ H₂G',
    'I_G': 'I_G',
    'I_H': 'I_H',
    'I_HG': 'I_HG',
    'I_HG2': 'I_HG₂',
    'I_H2G': 'I_H₂G',
}


#: A binding constant as the interface names it (DESIGN.md §9): its subscript and its name.
CONSTANT_NAMES: dict[str, str] = {
    'Ka_guest': 'K<sub>a</sub> guest',
    'Ka_dye': 'K<sub>a,dye</sub>',
    'Ka_HG': 'K<sub>a</sub> HG',
    'Ka_HG2': 'K<sub>a</sub> HG₂',
    'Ka_H2G': 'K<sub>a</sub> H₂G',
}


def fmt_constant(key: str) -> str:
    """Binding constant *key* as the glossary names it, in HTML: ``K<sub>a</sub> guest``; *key* itself if unknown."""
    return CONSTANT_NAMES.get(key, key)


def fmt_param_plain(name: str) -> str:
    """Parameter *name* in plain text (:data:`PARAM_LABELS_PLAIN`): ``Kₐ guest``, ``I_D``; *name* itself if unknown."""
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


#: The concentration units the conditions form offers, largest first.
_CONCENTRATION_UNITS = ('M', 'mM', 'µM', 'nM')


def fmt_concentration(value, digits: int = 4) -> str:
    """*value* in the largest concentration unit the form offers that leaves it at 1 or more: ``500 µM``.

    A concentration is entered in one of these units, so a report reads it back
    in the one it was typed in rather than in raw molar. Values below one
    nanomolar, and zero, are shown in nanomolar.
    """
    for unit in _CONCENTRATION_UNITS:
        magnitude = float(value.to(unit).magnitude)
        if abs(magnitude) >= 1.0 or unit == _CONCENTRATION_UNITS[-1]:
            return f'{magnitude:.{digits}g} {unit}'


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


def fmt_bound_note(on_bound: dict) -> str:
    """What to tell the user about signal parameters a fit ended on an entered bound; ``''`` for none.

    *on_bound* maps each such parameter to the bound it sits on, as
    :func:`core.pipeline.reporting.parameters_on_bound` returns it.
    """
    if not on_bound:
        return ''
    held = '; '.join(
        f'{fmt_param_plain(key)} at {fmt_sci(float(bound.magnitude))} {fmt_unit_pretty(str(bound.units))}'.strip()
        for key, bound in on_bound.items()
    )
    return (
        f'The fit ended on a bound entered under Binding model ({held}), which may hold the curve away from '
        'the data. Unless that bound is something you know about the system, widen it and fit again.'
    )


#: Said where the fit holds the signal offset on its floor of zero and the
#: curve misses the data: blank-subtracted signals need an offset below zero.
OFFSET_AT_ZERO_NOTE = (
    'The signal offset rests on its lower bound of 0. If the signals were blank-subtracted, allow a negative '
    'offset under Binding model and fit again.'
)


def offset_note(result) -> str:
    """:data:`OFFSET_AT_ZERO_NOTE` where it applies to *result*; ``''`` elsewhere.

    It applies when the fit holds a signal offset on a lower bound of zero
    (:func:`~core.pipeline.reporting.offsets_held_at_zero`) and the misfit
    test rejects the fit the result reports: an offset held at zero against
    blank-subtracted data is one way a curve comes to miss them. An offset at
    zero under a curve the test does not reject is where the data put it.
    """
    from core.pipeline.diagnostics import Verdict
    from core.pipeline.reporting import offsets_held_at_zero

    diagnostics = result.diagnostics
    rejected = diagnostics is not None and diagnostics.verdict in (Verdict.MODEL_INADEQUATE, Verdict.MODEL_AND_INPUTS)
    return OFFSET_AT_ZERO_NOTE if rejected and offsets_held_at_zero(result) else ''


def _one_figure(p: float) -> str:
    """*p* to one significant figure, ``0.03``; one that rounds to 1 reads ``> 0.9``, which is what it says."""
    rounded = float(f'{p:.1g}')
    return '> 0.9' if rounded >= 1.0 else f'= {rounded:g}'


def _at_most(p: float) -> str:
    """The smallest one-figure number at or above *p*, so ``≤`` it is true: ``0.0034`` reads ``≤ 0.004``.

    Below :data:`_P_FLOOR` it reads ``≤ 0.001``, the floor every p-value here
    is reported to.
    """
    if p <= _P_FLOOR:
        return f'≤ {_P_FLOOR:g}'
    exponent = math.floor(math.log10(p))
    # Rounded first, so a p that is one figure exactly is not lifted by its last bit.
    figure = math.ceil(round(p / 10.0**exponent, 9))
    return f'≤ {figure * 10.0**exponent:.{max(0, -exponent)}f}'


def one_step_sentence(label: str, p: float) -> str:
    """What the test of the second binding step says, beside the interval of that constant.

    Above :data:`~core.pipeline.varpro.SECOND_STEP_LEVEL` a model without the
    second step fits the data nearly as well, so the constant is not limited
    below and its interval is open there: ``Ka(HG₂) not limited below: a model
    without the second binding step fits nearly as well (one-step test p =
    0.03).``, and ``p > 0.005`` where one figure would round *p* down onto the
    level. At or below it the closed lower end is a claim that the step
    exists, and the sentence says what supports it: ``Ka(HG₂): second binding
    step supported (one-step model rejected at p ≤ 0.001).`` The F reference
    of the test is conservative here, so the p-value is written as a bound,
    rounded up so the bound holds.

    Parameters
    ----------
    label : str
        The constant's name, formatted for where the sentence goes.
    p : float
        :attr:`~core.pipeline.varpro.KaInterval.one_step_p` of the interval.
    """
    from core.pipeline.varpro import SECOND_STEP_LEVEL

    if p > SECOND_STEP_LEVEL:
        # One figure can round a p just above the level down onto it, the value a closed end is written with.
        shown = _one_figure(p) if float(f'{p:.1g}') > SECOND_STEP_LEVEL else f'> {SECOND_STEP_LEVEL:g}'
        return (
            f'{label} not limited below: a model without the second binding step fits nearly as well '
            f'(one-step test p {shown}).'
        )
    return f'{label}: second binding step supported (one-step model rejected at p {_at_most(p)}).'


def stated_additions(additions, n_replicates: int) -> str:
    """The stated random error of each addition in words, with what it is for the average of the replicates.

    ``3 %, sequential``; with replicates, ``3 %, sequential; σ/√3 for 3
    replicates as separate titrations`` or ``3 %, separate samples; σ itself
    for 3 repeated reads of one titration``.

    Parameters
    ----------
    additions : core.pipeline.inputs.AdditionError
        The stated error.
    n_replicates : int
        How many replicates the fitted signal is the average of.
    """
    text = f'{additions.sigma_pct:g} %, {"sequential" if additions.sequential else "separate samples"}'
    if n_replicates < 2:
        return text
    if additions.separate_titrations:
        return f'{text}; σ/√{n_replicates} for {n_replicates} replicates as separate titrations'
    return f'{text}; σ itself for {n_replicates} repeated reads of one titration'


def widening_sentences(rows, result, name) -> list[str]:
    """Why each reported interval is wider than the plain F test's, one sentence per binding constant it widens.

    An interval's cut-off is widened by a design effect
    (:attr:`~core.pipeline.varpro.KaInterval.inflation`, a factor on the
    variance of the estimate) where a random error of each addition is stated,
    and where the replicates leave the share of the noise law uncertain. The
    conditional interval, at the entered inputs, carries the law's part alone,
    so a law that widened it is named beside the additions; with no additions
    stated the reported interval's factor is the law's. Stated additions take
    over part of the scatter the law's residual part would otherwise carry, so
    their factor together with the law's can come out at or below the law's
    alone: the sentence then says the interval allows for both and gives the
    two factors, and says *widen* only where the reported factor is the larger.
    It compares factors, not intervals: where an input moved, the reported
    interval sits at other inputs than the conditional one.
    Each sentence says how
    much wider in the reader's terms — about the square root of the factor,
    the width of a profile interval growing with the square root of the
    variance it allows for — and what the factor is a factor on. Nothing is
    said of an interval that was not widened. The joint region of a two-step
    model is said by :func:`region_sentence`.

    Parameters
    ----------
    rows : list[ParameterSummary]
        :func:`~core.pipeline.reporting.summarize_parameters` of *result*.
    result : FitResult
        The fit, whose configuration records the stated additions and whose
        noise law the share set.
    name : Callable[[str], str]
        Formats a parameter key for where the sentence goes.
    """
    from core.pipeline.inputs import ErrorModel

    additions = ErrorModel.from_dict(result.fit_config).additions
    noise = result.noise
    n_replicates = 1 if noise is None else noise.n_replicates
    sentences = []
    for spec in rows:
        if spec.is_log or spec.inflation is None or not spec.inflation > 1.0:
            continue
        by_law = spec.inflation if additions is None else (spec.conditional_inflation or 1.0)
        label = name(spec.key)
        how_much = _widened_by(math.sqrt(spec.inflation))
        meaning = f'it takes the variance of the estimate as {_variance_ratio(spec.inflation)}'
        uncertain = None
        if by_law > 1.0 and noise is not None:
            low, high = noise.share_set
            uncertain = f'share between {low:.2g} and {high:.2g}'
        if additions is not None:
            stated = stated_additions(additions, n_replicates)
            causes = f'Random error of each addition ({stated})'
            if uncertain is None:
                sentences.append(f'{causes} widens the interval of {label} {how_much}: {meaning}.')
            elif spec.inflation > by_law:
                sentences.append(
                    f'{causes} and the noise law the replicates leave uncertain ({uncertain}) widen the interval '
                    f'of {label} {how_much}: {meaning}.'
                )
            else:
                sentences.append(
                    f'The interval of {label} allows for the random error of each addition ({stated}) and for the '
                    f'noise law the replicates leave uncertain ({uncertain}): {meaning}, no more than the '
                    f'{by_law:.3g} of the noise law alone, since part of the scatter is put down to the additions.'
                )
        elif uncertain is not None:
            sentences.append(
                f'The replicates leave the noise law uncertain ({uncertain}); the interval of {label} is widened '
                f'{how_much} to hold for every share they allow: {meaning}.'
            )
    return sentences


def region_sentence(result) -> str | None:
    """What widened the joint region of a two-step model's pair of binding constants, or ``None`` where nothing did.

    The region is drawn at the entered inputs with the design effect of the
    pair (:attr:`~core.pipeline.fit_pipeline.FitResult.joint_inflation`), which
    carries a stated random error of each addition and a noise law the
    replicates leave uncertain, as the reported intervals do.
    """
    from core.pipeline.inputs import ErrorModel

    factor = result.joint_inflation
    if not factor > 1.0:
        return None
    noise = result.noise
    causes = [
        cause
        for cause, applies in (
            ('the random error of each addition', ErrorModel.from_dict(result.fit_config).additions is not None),
            ('the noise law the replicates leave uncertain', noise is not None and noise.estimated and noise.share > 0),
        )
        if applies
    ]
    why = f' for {" and ".join(causes)}' if causes else ''
    return (
        f'The joint region of the pair, at the entered inputs, is widened{why}: it takes the variance of the pair '
        f'as {_variance_ratio(factor)}.'
    )


def _widened_by(factor: float) -> str:
    """How much wider an interval is, roughly, for a cut-off whose rise grew by ``factor²``: ``by about 12 %``."""
    return f'by about {(factor - 1) * 100:.2g} %' if factor < 2 else f'about {factor:.2g}-fold'


def _variance_ratio(factor: float) -> str:
    """``3.88 times what the scatter of the data alone implies``: what a design effect is a factor on."""
    return f'{factor:.3g} times what the scatter of the data alone implies'


def _escape(text: str) -> str:
    """Plain text made safe for a rich-text widget: ``p < 0.001`` must not read as the start of a tag."""
    return escape(text, quote=False)


#: Below this a p-value is reported as a bound. The references of the runs test
#: and the conflict statistic are Monte-Carlo quadratures — 100 000 and 200 000
#: draws — whose own error is 5e-4 to 7e-4 at p = 0.05, so digits past the third
#: decimal would report the quadrature, not the data. The simulated reference of
#: the lack-of-fit test has its own floor, which :func:`fmt_misfit` writes.
_P_FLOOR = 0.001

#: Above this two significant figures round to 1, and ``p = 1`` would read as a
#: test that is certain rather than one that found nothing; such a p is reported
#: as a bound from this value instead.
_P_CEILING = 0.99


def fmt_p(p: float) -> str:
    """A p-value as every report writes it: ``p = 0.55``, ``p = 0.0012``, ``p < 0.001``, ``p > 0.99``.

    Two significant figures and a bound past :data:`_P_FLOOR` and
    :data:`_P_CEILING`. A simulated lack-of-fit p-value is a multiple of
    ``1 / (LOF_BOOTSTRAP_DRAWS + 1)``; two figures write it to within that step
    (``21/200`` reads ``0.1``), and :func:`fmt_test_p` writes its floor as a bound.
    """
    if p < _P_FLOOR:
        return f'p < {_P_FLOOR:g}'
    rounded = float(f'{p:.2g}')
    if rounded > _P_CEILING:
        return f'p > {_P_CEILING:g}'
    return f'p = {rounded:g}'


def fmt_stat(value: float) -> str:
    """A test statistic to three significant figures: ``0.9``, ``12``, ``24.2``, ``200``, ``1.2×10⁵``.

    Plain digits over the range an F ratio or a conflict statistic reads in,
    and ``×10ⁿ`` notation outside it, so a number never appears as ``1.2e+05``.

    Raises
    ------
    ValueError
        For a statistic that is not finite. ``inf`` is library phrasing, not a
        reading a user can act on, and no test a fit runs produces one: data
        with no scatter to judge a curve against are not tested at all.
    """
    if not math.isfinite(value):
        raise ValueError(f'A test statistic of {value} has no reading as a number; say in words what it means.')
    if value and not 0.01 <= abs(value) < 1e4:
        return fmt_sci(value, 2)
    return f'{float(f"{value:.3g}"):g}'


#: Said after the p-value of a lack-of-fit test whose reference was simulated:
#: the weights came from the replicates' own scatter, or an error of each
#: addition was stated, so the F distribution is not the reference and the test
#: names what is.
SIMULATED_P = 'simulated from the fitted curve and the noise law, with any addition error you stated'


def fmt_misfit(test, *, named: bool = True) -> str:
    """One misfit test as a report quotes it, with its statistic and p-value.

    ``lack-of-fit F(9, 72) = 0.9, p = 0.55`` for the replicate F test and
    ``runs test: 6 runs, 7.0 expected, p = 0.41`` for the runs test. A
    lack-of-fit p-value read from a simulated reference — the replicates
    showed the noise law, so the weights are estimated, or a random error of
    each addition was stated, which the simulation draws as well — says so:
    ``lack-of-fit F(9, 72) = 0.9, p = 0.55, simulated from the fitted curve and
    the noise law, with any addition error you stated``. When no simulated
    ratio reached the observed one, the
    p-value is the smallest the simulation can show,
    ``1 / (LOF_BOOTSTRAP_DRAWS + 1)``, and is written as the bound it is,
    ``p ≤ 0.005``: the curve may miss the data by far more.

    Parameters
    ----------
    test : core.pipeline.diagnostics.MisfitTest
        The test to write.
    named : bool
        Whether to name the F test. The runs test names itself either way; the
        F ratio is named where the sentence around it does not say which test
        it is.
    """
    if test.kind == 'runs':
        runs = int(round(test.statistic))
        head = f'runs test: {runs} run{"" if runs == 1 else "s"}, {test.expected:.1f} expected'
    else:
        dof = '' if test.dof is None else f'({test.dof[0]}, {test.dof[1]})'
        head = f'{"lack-of-fit " if named else ""}F{dof} = {fmt_stat(test.statistic)}'
        if test.reference == 'bootstrap':
            return f'{head}, {fmt_test_p(test)}, {SIMULATED_P}'
    return f'{head}, {fmt_test_p(test)}'


def fmt_test_p(test) -> str:
    """The p-value of one misfit test as every report writes it.

    :func:`fmt_p`, except where no simulated ratio reached the observed one: the
    p-value is then the smallest the simulation can show, ``1 / (LOF_BOOTSTRAP_DRAWS +
    1)``, and is written as the bound it is, ``p ≤ 0.005``.
    """
    if test.kind != 'runs' and test.reference == 'bootstrap':
        from core.pipeline.diagnostics import LOF_BOOTSTRAP_DRAWS

        smallest = 1.0 / (LOF_BOOTSTRAP_DRAWS + 1)
        if test.p_value <= smallest:
            return f'p ≤ {smallest:g}'
    return fmt_p(test.p_value)


def fmt_percent(fraction: float) -> str:
    """An offset from an entered value as a signed percentage of it, to one decimal: ``−11.4 %``.

    An offset that rounds to zero reads ``0.0 %``: a sign on it would claim a
    direction the digits shown do not have.
    """
    text = f'{fraction * 100:+.1f}'
    if float(text) == 0.0:
        return '0.0 %'
    return f'{text} %'.replace('-', '−')


def fmt_against(shift) -> str:
    """How one fitted offset compares with what was stated: ``3.8 σ``, ``at the edge of its range``, or ``''``.

    An input stated with a standard deviation is measured in it; one stated as
    a range has none, and the only thing to say is whether the fit took it to
    an end of that range.
    """
    if shift.z is not None:
        return f'{abs(shift.z):.1f} σ'
    return 'at the edge of its range' if shift.at_edge else ''


def fmt_shift(shift, label: str, *, html: bool) -> str:
    """Where the fit put one input, as every report names it.

    ``[Host]₀ −11.4 % (3.8 σ)`` for an input stated with a standard deviation —
    the percentage it moved and how many standard deviations that is — and
    ``[Dye]₀ −6.0 % (at the edge of its range)`` for one stated as a range that
    the fit took to an end of. A range the fit stayed inside reads as the
    percentage alone: there is no standard deviation to compare it with.

    Parameters
    ----------
    shift : core.pipeline.diagnostics.InputShift
        The fitted offset of one input.
    label : str
        The input's name as Input uncertainty writes it (:meth:`~gui.uncertainty.UncertaintyForm.input_labels`).
    html : bool
        Whether the result goes into a rich-text widget, which needs its
        markup characters escaped.
    """
    against = fmt_against(shift)
    text = f'{label} {fmt_percent(shift.fraction)}{f" ({against})" if against else ""}'
    return _escape(text) if html else text


def stated_uncertainty(spec, unit: str) -> str:
    """One input's uncertainty as the user stated it: ``σ 10 %``, ``σ 2.0×10⁻⁷ M``, ``−5 % to +5 %``.

    A standard deviation is written ``σ`` and a range as its two ends, in
    percent of the entered value or in the input's own unit — one notation for
    a stated uncertainty on screen and in every report. A value in the input's
    own unit is written in ``×10ⁿ`` notation, as every other concentration a
    report shows is, so no reader meets ``2e-07``.

    Parameters
    ----------
    spec : core.pipeline.inputs.InputSpec
        The stated uncertainty.
    unit : str
        The input's unit, already formatted for where the text goes (plain or
        HTML); ``''`` for one with no unit.
    """
    from core.pipeline.inputs import SpecKind

    if spec.kind is SpecKind.SIGMA:
        return f'σ {spec.sigma:g} %' if spec.relative else f'σ {fmt_sci(spec.sigma, 2)} {unit}'.rstrip()
    if spec.relative:
        return f'{spec.lo:+g} % to {spec.hi:+g} %'.replace('-', '−')
    return f'{fmt_sci(spec.lo, 2)} to {fmt_sci(spec.hi, 2)} {unit}'.rstrip()


#: Why a conflict does not name the input that is wrong. Said of a fit whose
#: only input free to move is the one the correction landed on.
_ALIKE_ONE = 'this is the only input the fit was free to move, so the correction landed there whatever its real cause'

#: The same, where inputs stated as a range moved as well: the statistic weighs
#: only the inputs stated with a standard deviation, and there is one of those.
_ALIKE_ONE_JUDGED = (
    'this is the only input stated with a standard deviation, so the correction landed there whatever its real cause'
)

#: Said where the data do inform one direction per input stated with a standard
#: deviation: the shifts are then each the fit's own reading, and what is left
#: to say is that the statistic weighs them as one.
_ALIKE_TOGETHER = 'the statistic weighs them together, so it does not say which of them is off'


def _alike(conflict, judged: int, ranged: bool) -> str:
    """Why the listed shifts do not name the input that is off, read from the fit's own weights.

    ``conflict.k`` is how many combinations of the *judged* inputs — those
    stated with a standard deviation — these data pin down. Fewer than there
    are such inputs and the fit could not tell them apart — the host
    concentration and the titrant scale move the curve almost alike — so the
    correction landed where the combinations it does see point, which need not
    be the input that is off: with a planted 3 σ error in one input the largest
    shift sat on that input in 27 to 58 % of the conflicts (design 1.5). As
    many directions as inputs and the data do see each one, so no such claim
    is made.

    An input stated as a range carries no standard deviation and no ``z``, and
    so enters neither the statistic nor this count; *ranged* says whether one
    moved, so a single judged input is not called the only one that could.
    """
    if judged <= 1:
        return _ALIKE_ONE_JUDGED if ranged else _ALIKE_ONE
    if conflict.k >= judged:
        return _ALIKE_TOGETHER
    one = conflict.k == 1
    return (
        f'the data see only {"one combination" if one else f"{conflict.k} combinations"} of these {judged} '
        f'inputs, so the correction landed where {"that combination points" if one else "those combinations point"}'
    )


#: What is left to say when the data are too few for any misfit test: the fit
#: is reported, and nothing here speaks for or against it.
_NO_MISFIT_TEST = (
    'The data leave too few points beyond the fitted parameters to test whether the model and the entered '
    'inputs describe them, so nothing here speaks for or against the fit.'
)

#: Said wherever the interval is reported under a model the data reject.
_MODEL_TAIL = 'The interval assumes a model the data reject; try another binding model or check the data.'

#: Why a fit whose every stated uncertainty is a range carries no conflict
#: statistic: a range is a hard limit the fit is free anywhere inside, not a
#: spread a shift can be weighed against. A clause, so the summary block and
#: the exported report each lead into it in their own voice.
RANGES_ONLY = (
    'every uncertainty is stated as a range, so the fit is free anywhere inside it and there is nothing to '
    'test a shift against'
)

#: What the record of the input uncertainties reads when none was stated. The
#: summary block on screen and the exported report each state it in their own
#: line, in the same words.
NO_UNCERTAINTY = 'none — the interval takes the inputs as exact'

#: Why a test of :class:`~core.pipeline.diagnostics.FitDiagnostics` was not
#: run, per test and per reason token of ``FitDiagnostics.skipped``: a clause
#: that follows "not tested —", so every report leads into it the same way.
NOT_RUN = {
    ('misfit', 'no_scatter'): (
        'the data carry no scatter above rounding, as noise-free or identical replicates do, so there is no '
        'noise to measure a distance from the curve against'
    ),
    ('misfit', 'too_few_dof'): 'the data leave too few points beyond the fitted parameters',
    ('conflict', 'no_uncertainty'): RANGES_ONLY,
    ('conflict', 'no_informed_direction'): (
        'the data do not determine any combination of the inputs you gave a standard deviation, so they cannot '
        'check the entered values'
    ),
}


def not_run_reason(diagnostics, test: str) -> str:
    """Why *test* (``'misfit'`` or ``'conflict'``) was not run on this fit, as a clause; ``''`` where it was.

    Read from ``diagnostics.skipped``. A results file without a ``skipped``
    entry for a missing misfit test had too few points for it: that is what
    such a record means in the file format.
    """
    reason = diagnostics.skipped.get(test)
    if reason is not None:
        return NOT_RUN[(test, reason)]
    if test == 'misfit' and diagnostics.misfit is None and diagnostics.conditional_misfit is None:
        return NOT_RUN[('misfit', 'too_few_dof')]
    return ''


def verdict_sentence(diagnostics, shifts, labels, *, html: bool) -> str:
    """What the diagnostics of one fit say, in one plain-language sentence group.

    The five verdicts read: no test found evidence against the model or the
    entered inputs; the entered inputs miss the data and a shift inside their
    stated uncertainties explains it; the data need the inputs, *taken
    together*, further out than stated; no allowed shift rescues the model;
    or both of the last two, the inputs named first, since an error in an input
    can by itself make the curve miss. A test that could not be run is named
    with the reason, so a verdict of no evidence is not read as one of a test
    that passed. The shifts are listed largest ``|z|`` first, the inputs stated
    as a range after them — a range carries no ``z`` to rank by — and each by
    its own key where two are equal, so the order is the same on every report.

    The sentence never names one input as the cause of a conflict: the
    statistic judges them together (:mod:`core.pipeline.diagnostics`), and it
    judges only the inputs stated with a standard deviation, so every count and
    every pronoun of a conflict refers to those, and an input stated as a range
    is reported as moved inside that range.

    Parameters
    ----------
    diagnostics : core.pipeline.diagnostics.FitDiagnostics
        The tests of the fit and the verdict they give.
    shifts : Mapping[str, core.pipeline.diagnostics.InputShift]
        Where the fit put every input it was free to move; empty when every
        input was taken as entered.
    labels : Mapping[str, str]
        Each input's name as Input uncertainty writes it (:meth:`~gui.uncertainty.UncertaintyForm.input_labels`).
    html : bool
        Whether the result goes into a rich-text widget.
    """
    text = _verdict_text(diagnostics, shifts, labels)
    return _escape(text) if html else text


def _verdict_text(diagnostics, shifts, labels) -> str:
    """:func:`verdict_sentence` as plain text."""
    from core.pipeline.diagnostics import Verdict

    verdict = diagnostics.verdict
    if verdict is Verdict.CONSISTENT:
        return _consistent_text(diagnostics, shifts)

    if verdict is Verdict.INPUTS_EXPLAIN:
        return (
            f'At the entered inputs the model misses the data ({fmt_misfit(diagnostics.conditional_misfit, named=False)}). '
            f'It fits once the inputs move within their stated uncertainties: {fmt_shifts(shifts, labels, html=False)}. '
            'The interval includes these shifts.'
        )

    test = diagnostics.misfit or diagnostics.conditional_misfit
    if verdict is Verdict.INPUTS_CONFLICT:
        lead, where, moved, checked = _conflict_text(diagnostics, shifts, labels)
        many = len(shifts) > 1
        return f'{lead}. {where} Check {checked}. The interval assumes the {"shifts are" if many else "shift is"} real.'

    if verdict is Verdict.MODEL_INADEQUATE:
        if shifts:
            return (
                'The model does not describe the data even with the inputs free to move within their uncertainties '
                f'(after the shifts, {fmt_misfit(test, named=False)}). {_MODEL_TAIL}'
            )
        return (
            f'The model does not describe the data at the entered inputs ({fmt_misfit(test, named=False)}). '
            f'{_MODEL_TAIL} Enter the uncertainty of the inputs under Input uncertainty to test whether the '
            'inputs explain it.'
        )

    # Both tests reject: the inputs lead, since an input that is off can by
    # itself make the curve miss the data.
    lead, where, moved, checked = _conflict_text(diagnostics, shifts, labels)
    return (
        f'{lead}, and even with {moved} moved the model misses the data '
        f'(after the shifts, {fmt_misfit(test, named=False)}). {where} '
        f'Check first {checked}: an input that '
        'is off can by itself make the curve miss the data. If the entered values are right, try another binding '
        'model or check the data. The interval assumes both the shifts and the model.'
    )


def _consistent_text(diagnostics, shifts) -> str:
    """No evidence against the fit: the tests that ran with their readings, then each test that could not run and why.

    A test of the inputs against what was stated is named as not run only
    where an input was free to move: with every input taken as exact there is
    nothing stated for it to test, and the misfit test at the entered inputs is
    what tests them.
    """
    test = diagnostics.misfit or diagnostics.conditional_misfit
    conflict = diagnostics.conflict
    readings = [] if test is None else [fmt_misfit(test)]
    if conflict is not None:
        readings.append(f'inputs q = {fmt_stat(conflict.q)}, {fmt_p(conflict.p_value)}')
    not_run = []
    misfit_reason = not_run_reason(diagnostics, 'misfit') if test is None else ''
    if misfit_reason:
        not_run.append(f'The curve was not tested against the data: {misfit_reason}.')
    conflict_reason = not_run_reason(diagnostics, 'conflict') if shifts and conflict is None else ''
    if conflict_reason:
        not_run.append(f'The entered inputs were not tested against what you stated: {conflict_reason}.')
    if not readings:
        if not diagnostics.skipped:
            return _NO_MISFIT_TEST
        head = 'No test could be run on this fit, so nothing here speaks for or against it.'
    else:
        tested = 'the model or the entered inputs' if test is not None else 'the entered inputs'
        head = f'No test found evidence against {tested} ({"; ".join(readings)}).'
    return ' '.join([head, *not_run])


def _conflict_text(diagnostics, shifts, labels) -> tuple[str, str, str, str]:
    """A conflict's opening clause, where the fit put the correction, what moved, and which entered values to check.

    The statistic judges the inputs stated with a standard deviation; the
    opening clause and the list the correction is read from are those inputs.
    The inputs stated as a range follow as moved inside what was stated, which
    is what they did. The advice covers every input that moved, those stated
    as a range included: one resting on the edge of its range is where the data
    wanted more room, so it is as likely to be off as a judged one.
    """
    from core.pipeline.inputs import input_name

    conflict = diagnostics.conflict
    judged = {key: shift for key, shift in shifts.items() if shift.z is not None}
    ranged = {key: shift for key, shift in shifts.items() if shift.z is None}
    one = len(judged) == 1
    if one:
        # One judged input is one input the sentence can name: there are no
        # others for the statistic to have weighed it against. Why naming it is
        # not naming the cause is said by :func:`_alike`.
        (shift,) = judged.values()
        lead = (
            f'The data fit only with {input_name(shift.key, dict(labels))} further from the value you entered '
            'than the uncertainty you stated allows'
        )
    elif ranged:
        lead = (
            'The data fit only with the inputs you gave a standard deviation, taken together, further from their '
            'entered values than those uncertainties allow'
        )
    else:
        lead = (
            'The data fit only with the inputs, taken together, further from their entered values than their '
            'stated uncertainties allow'
        )
    lead += f' (q = {fmt_stat(conflict.q)}, {fmt_p(conflict.p_value)})'
    where = (
        f'The fit put the correction here: {fmt_shifts(judged, labels, html=False)} — '
        f'{_alike(conflict, len(judged), bool(ranged))}.'
    )
    if ranged:
        where += (
            f' Inside the {"range" if len(ranged) == 1 else "ranges"} you stated it also moved '
            f'{fmt_shifts(ranged, labels, html=False)}.'
        )
        if any(shift.at_edge for shift in ranged.values()):
            where += ' An input at the edge of its range is one the data would have moved further.'
        return lead, where, 'the inputs', 'the values you entered for all the inputs listed, ranges included'
    return (
        lead,
        where,
        'it' if one else 'them',
        f'the {"value" if one else "values"} you entered for {"it" if one else "them"}',
    )


def conflict_note(diagnostics, shifts, labels) -> str:
    """What a conflict says after its list of shifts, for a view that draws the shifts as rows.

    Why the shifts do not name the input that is off, where the inputs stated as a range
    moved, which entered values to check and what the interval assumes: the sentences of
    :func:`verdict_sentence` that follow ``The fit put the correction here:``, so a view
    showing the shifts beside them says what the report says, without naming one input as
    the cause.
    """
    from core.pipeline.diagnostics import Verdict

    judged = sum(shift.z is not None for shift in shifts.values())
    ranged = any(shift.z is None for shift in shifts.values())
    _lead, where, _moved, checked = _conflict_text(diagnostics, shifts, labels)
    alike = _alike(diagnostics.conflict, judged, ranged)
    after = where.split(f'{alike}.', 1)[1].strip()
    if diagnostics.verdict is Verdict.INPUTS_CONFLICT:
        tail = f'Check {checked}. The interval assumes the {"shifts are" if len(shifts) > 1 else "shift is"} real.'
    else:
        tail = (
            f'Check first {checked}: an input that is off can by itself make the curve miss the data. The interval '
            'assumes both the shifts and the model.'
        )
    return ' '.join(part for part in (f'{alike[0].upper()}{alike[1:]}.', after, tail) if part)


#: The tones a verdict's headline is given: nothing to act on, something to check, and a
#: result that rests on an assumption the data reject.
VERDICT_TONES = ('neutral', 'amber', 'red')


def verdict_headline(diagnostics) -> tuple[str, str]:
    """What the diagnostics of one fit say in a few words, and the tone of :data:`VERDICT_TONES` to show it in.

    The line a reader sees first — in Input uncertainty's side panel and the
    exported report; :func:`verdict_sentence` says the rest. It never names an
    input: a conflict is a statement about the inputs together. A rejected
    model is named by what the test measured — the curve misses the data by
    more than their scatter allows — rather than by the conclusion: replicates
    that scatter little make the test strong enough to reject a curve that
    follows the data closely. And no headline claims the model or the inputs
    are right: a test that finds nothing says only that.
    """
    from core.pipeline.diagnostics import Verdict

    verdict = diagnostics.verdict
    if verdict is Verdict.CONSISTENT:
        if diagnostics.misfit or diagnostics.conditional_misfit:
            return 'No test found evidence against the model or the entered inputs', 'neutral'
        if diagnostics.conflict:
            return 'No test found evidence against the entered inputs; the curve was not tested', 'neutral'
        return 'Not tested: nothing here speaks for or against the fit', 'neutral'
    if verdict is Verdict.INPUTS_EXPLAIN:
        return 'The data fit once the inputs move within their uncertainties', 'amber'
    misses = 'the curve misses the data by more than their scatter allows'
    if verdict is Verdict.INPUTS_CONFLICT:
        return 'The inputs together are further from their entered values than you stated', 'red'
    if verdict is Verdict.MODEL_INADEQUATE:
        return f'{misses[0].upper()}{misses[1:]}', 'red'
    return f'The inputs together are further from their entered values than you stated, and {misses}', 'red'


def fmt_shifts(shifts, labels, *, html: bool) -> str:
    """Every shift of one fit, largest ``|z|`` first, named as Input uncertainty names its inputs.

    The inputs stated as a range come after the ones stated with a standard
    deviation — a range carries no ``z`` to rank by — and two that moved
    equally far are ordered by their key, so the same fit reads the same on
    every report.

    Parameters
    ----------
    shifts : Mapping[str, core.pipeline.diagnostics.InputShift]
        Where the fit put every input it was free to move.
    labels : Mapping[str, str]
        Each input's name as Input uncertainty writes it (:meth:`~gui.uncertainty.UncertaintyForm.input_labels`).
    html : bool
        Whether the result goes into a rich-text widget.
    """
    from core.pipeline.inputs import input_name

    ordered = sorted(shifts.values(), key=shift_order)
    return ', '.join(fmt_shift(shift, input_name(shift.key, dict(labels)), html=html) for shift in ordered)


def shift_order(shift) -> tuple:
    """Sort key: the inputs stated with a σ by how far they moved in σ, then the ranges, then by key."""
    if shift.z is None:
        return (1, -abs(shift.fraction), shift.key)
    return (0, -abs(shift.z), shift.key)


def plain_number(value: float) -> str:
    """Up to four significant figures, with a power of ten written as ``1.68×10⁷``."""
    mantissa, _, exponent = f'{value:.4g}'.partition('e')
    return f'{mantissa}×10{str(int(exponent)).translate(_SUPERSCRIPT_DIGITS)}' if exponent else mantissa


def _display_label(index: int) -> str:
    """Map a zero-based replica index to an A–Z display label.

    For indices 0–25 returns 'A'–'Z'.  Beyond that, returns 'AA', 'AB', etc.
    """
    if index < 26:
        return chr(65 + index)
    # Overflow: AA, AB, ...
    return chr(65 + index // 26 - 1) + chr(65 + index % 26)


def describe_replicates(replica_ids: Iterable[str], order: Sequence[str] | None = None) -> str:
    """Name *replica_ids* as the Replicates panel does: ``replicate B``, ``replicates B–H``, ``replicates A, C and E``.

    A replicate is named by its display label, from its position in *order*
    (the loaded data's replicate ids), with three or more neighbours joined
    into a span. When *order* is missing or lacks one of them, the ids are
    named as they are.
    """
    ids = list(replica_ids)
    noun = 'replicate' if len(ids) == 1 else 'replicates'
    order = list(order or ())
    if all(rid in order for rid in ids):
        runs: list[list[int]] = []
        for pos in sorted(order.index(rid) for rid in ids):
            if runs and pos == runs[-1][-1] + 1:
                runs[-1].append(pos)
            else:
                runs.append([pos])
        names = []
        for run in runs:
            if len(run) >= 3:
                names.append(f'{_display_label(run[0])}–{_display_label(run[-1])}')
            else:
                names.extend(_display_label(pos) for pos in run)
    else:
        names = ids
    joined = names[0] if len(names) == 1 else f'{", ".join(names[:-1])} and {names[-1]}'
    return f'{noun} {joined}'
