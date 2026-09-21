"""Stored rows rendered as the tables the documents and the paper print.

Nothing here computes a fit. It reads what
:func:`validation.store.load` holds, turns each judged series into a rate with
exact limits and each reported series into a distribution, and prints them per
case and pooled per assay. A rate that appears in a document comes from here
verbatim.
"""

from __future__ import annotations

import collections
import csv
import dataclasses
import datetime
import io
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

import numpy as np

from validation import store
from validation.checks import CHECKS, Check, matches
from validation.criteria import Criterion, clopper_pearson

__all__ = ['Rate', 'Spread', 'render', 'summarise', 'summarise_group', 'tables']


@dataclass(frozen=True)
class Rate:
    """How often a judged or reported yes/no series came out yes.

    Attributes
    ----------
    case : str
        The case, or the assay family for a pooled row.
    series : str
        The metric's name, without the ``~`` that marks a reported one.
    n, hits : int
        Rows that said anything about this series, and how many said yes.
    low, high : float
        Exact 95 % limits of the rate.
    criterion : Criterion | None
        What this rate is judged against; ``None`` for a reported series.
    verdict : str
        ``'pass'``, ``'conservative'``, ``'fail'`` or ``'undecided'`` from
        :meth:`~validation.criteria.Criterion.verdict`; ``''`` where nothing
        judges the series, and ``'partial'`` on a pooled row whose family is
        unevenly sampled.
    """

    case: str
    series: str
    n: int
    hits: int
    low: float
    high: float
    criterion: Criterion | None
    verdict: str

    @property
    def rate(self) -> float:
        """The proportion itself."""
        return self.hits / self.n if self.n else float('nan')


@dataclass(frozen=True)
class Spread:
    """The distribution of a reported number over the rows of one case.

    Attributes
    ----------
    case : str
        The case, or the assay family for a pooled row.
    series : str
        The metric's name, without the ``~`` that marks a reported one.
    n : int
        Rows that carried a finite value.
    median : float
        Median of the values themselves, signs included.
    p99, largest : float
        99th percentile and maximum of the *magnitudes*. Every series read
        here is an error, a width or a time, so what a reader wants of the
        tail is how far from zero it reaches; on a signed series the maximum
        of the values alone would hide a large negative one.
    rms : float
        Root mean square of the values.
    """

    case: str
    series: str
    n: int
    median: float
    p99: float
    largest: float
    rms: float


def _series_values(check: Check, rows: Iterable[dict[str, Any]]) -> dict[str, list[Any]]:
    """Every metric of *rows*, by series name, with the rows that say nothing left out."""
    values: dict[str, list[Any]] = collections.defaultdict(list)
    for row in rows:
        for series, value in check.metrics(row).items():
            if value is not None:
                values[series].append(value)
    return values


def summarise_group(check: Check, case: str, rows: list[dict[str, Any]]) -> tuple[list[Rate], list[Spread]]:
    """The rates and the distributions of one case, or of one pooled family."""
    values = _series_values(check, rows)
    rates, spreads = [], []
    for series, found in sorted(values.items()):
        reported = series.startswith('~')
        name = series[1:] if reported else series
        if all(isinstance(v, bool) for v in found):
            criterion = None if reported else check.criterion
            hits, n = int(sum(found)), len(found)
            low, high = clopper_pearson(hits, n)
            verdict = criterion.verdict(hits, n) if criterion is not None else ''
            rates.append(Rate(case, name, n, hits, low, high, criterion, verdict))
        else:
            numbers = np.array([float(v) for v in found], dtype=float)
            finite = numbers[np.isfinite(numbers)]
            if not finite.size:
                continue
            spreads.append(
                Spread(
                    case,
                    name,
                    int(finite.size),
                    float(np.median(finite)),
                    float(np.percentile(np.abs(finite), 99)),
                    float(np.max(np.abs(finite))),
                    float(np.sqrt(np.mean(finite**2))),
                )
            )
    return rates, spreads


@dataclass(frozen=True)
class Summary:
    """Everything the tables of one check are rendered from.

    Attributes
    ----------
    check : Check
        The check these rows belong to.
    rates, spreads : list
        Per case.
    pooled_rates, pooled_spreads : list
        Per assay family. A family whose cases are unevenly sampled carries
        the verdict ``'partial'``, because an unbalanced pool is the rate of
        whichever cases happened to finish and not the family's.
    seeds : dict[str, int]
        Rows per case, for the cases that have any.
    declared : int
        Cases this summary covers — the check's own, narrowed by ``patterns``
        — which is what ``seeds`` is read against: a run stopped early leaves
        fewer cases with rows than were asked for.
    refused, errors : int
        Rows that carry a refusal message and rows that carry an exception.
    messages : list[tuple[str, int]]
        The three commonest of those messages, with their counts.
    patterns : tuple[str, ...]
        The expressions the cases were filtered by, empty for the whole
        check. A table rendered from a filtered summary says so, because the
        cases left out are not cases that failed.
    """

    check: Check
    rates: list[Rate]
    spreads: list[Spread]
    pooled_rates: list[Rate]
    pooled_spreads: list[Spread]
    seeds: dict[str, int]
    declared: int
    refused: int
    errors: int
    messages: list[tuple[str, int]]
    patterns: tuple[str, ...] = ()

    @property
    def complete(self) -> bool:
        """Whether every case this summary covers has rows."""
        return not self.declared or len(self.seeds) >= self.declared


def _family(case_id: str) -> str:
    """The assay family a case belongs to: the first field of its id."""
    return case_id.split(',')[0]


def summarise(
    check: Check, rows: dict[tuple[str, int], dict[str, Any]], patterns: Sequence[str] | None = None
) -> Summary:
    """Read *rows* into the rates and distributions of *check*, per case and pooled per family.

    A check that names its cases is summarised from those cases alone, so a
    derived check reads the rows of the grid its claim is about and not every
    row its parent holds. *patterns* narrows that to the cases whose id one of
    them matches, which is how a fix round prints the cells it touched.
    """
    if check.cases:
        declared = {case.id for case in check.cases if matches(case.id, patterns)}
        kept = {key: row for key, row in rows.items() if key[0] in declared}
    else:
        declared = set()
        kept = {key: row for key, row in rows.items() if matches(key[0], patterns)}
    by_case: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for (case, _seed), row in kept.items():
        by_case[case].append(row)
    rates: list[Rate] = []
    spreads: list[Spread] = []
    for case in sorted(by_case):
        case_rates, case_spreads = summarise_group(check, case, by_case[case])
        rates.extend(case_rates)
        spreads.extend(case_spreads)

    by_family: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for case, found in by_case.items():
        by_family[_family(case)].extend(found)
    balanced = _balanced_families(declared, {case: len(found) for case, found in by_case.items()})
    pooled_rates: list[Rate] = []
    pooled_spreads: list[Spread] = []
    for family in sorted(by_family):
        family_rates, family_spreads = summarise_group(check, family, by_family[family])
        if family not in balanced:
            family_rates = [dataclasses.replace(rate, criterion=None, verdict='partial') for rate in family_rates]
        pooled_rates.extend(family_rates)
        pooled_spreads.extend(family_spreads)

    messages = collections.Counter(row['refused'] for row in kept.values() if row.get('refused')) + collections.Counter(
        row['error'] for row in kept.values() if row.get('error')
    )
    return Summary(
        check=check,
        rates=rates,
        spreads=spreads,
        pooled_rates=pooled_rates,
        pooled_spreads=pooled_spreads,
        seeds={case: len(found) for case, found in sorted(by_case.items())},
        declared=len(declared),
        refused=sum(1 for row in kept.values() if row.get('refused')),
        errors=sum(1 for row in kept.values() if row.get('error')),
        messages=messages.most_common(3),
        patterns=tuple(patterns or ()),
    )


def _balanced_families(declared: set[str], seeds: dict[str, int]) -> set[str]:
    """The families every declared case of which has rows, all at the same seed count.

    A pooled rate over an uneven set of cases is the rate of the cases that
    finished, weighted by how far each got, which is nobody's claim. With no
    declared cases — a derived check reading its parent whole — a family is
    balanced when its cases agree on their seed count.
    """
    by_family: dict[str, list[str]] = collections.defaultdict(list)
    for case in declared or seeds:
        by_family[_family(case)].append(case)
    return {
        family
        for family, cases in by_family.items()
        if all(case in seeds for case in cases) and len({seeds[case] for case in cases}) <= 1
    }


def _criterion_text(criterion: Criterion | None) -> str:
    """The criterion as a table names it."""
    return '' if criterion is None else criterion.text


def _rate_table(rates: list[Rate], first: str) -> list[str]:
    """One markdown table of rates."""
    lines = [
        f'| {first} | series | N | rate | 95 % exact | criterion | verdict |',
        '| --- | --- | ---: | ---: | --- | --- | --- |',
    ]
    for rate in rates:
        lines.append(
            f'| {rate.case} | {rate.series} | {rate.n} | {rate.rate:.3f} | '
            f'[{rate.low:.3f}, {rate.high:.3f}] | {_criterion_text(rate.criterion)} | {rate.verdict} |'
        )
    return lines


def _spread_table(spreads: list[Spread], first: str) -> list[str]:
    """One markdown table of distributions."""
    lines = [
        f'| {first} | series | N | median | p99 \\|x\\| | max \\|x\\| | rms |',
        '| --- | --- | ---: | ---: | ---: | ---: | ---: |',
    ]
    for spread in spreads:
        lines.append(
            f'| {spread.case} | {spread.series} | {spread.n} | {spread.median:.4g} | '
            f'{spread.p99:.4g} | {spread.largest:.4g} | {spread.rms:.4g} |'
        )
    return lines


def render(summary: Summary, code: str, fmt: str = 'md') -> str:
    """The tables of one check, as markdown or as CSV rows."""
    if fmt == 'csv':
        return _render_csv(summary, code)
    check = summary.check
    seeds = summary.seeds.values()
    failing = [r for r in summary.rates if r.verdict == 'fail']
    undecided = [r for r in summary.rates if r.verdict == 'undecided']
    lines = [
        f'## {check.name}',
        '',
        check.claim,
        '',
    ]
    if check.criterion is not None:
        lines += [f'**Criterion: {check.criterion.text}.** {check.criterion_reason}', '']
    if check.derived_from:
        lines += [f'Read from the rows of `{check.derived_from}`; it runs no fits of its own.', '']
    if summary.patterns:
        lines += [
            f'> **Filtered.** Only the cases matching {", ".join(f"`{p}`" for p in summary.patterns)} are '
            f'shown; the check defines {len(check.cases)} cases in all.',
            '',
        ]
    lines += [
        f'{len(summary.seeds)} of {summary.declared or len(summary.seeds)} cases have rows, '
        f'{sum(seeds) if summary.seeds else 0} rows in all, '
        f'{min(summary.seeds.values()) if summary.seeds else 0} to '
        f'{max(summary.seeds.values()) if summary.seeds else 0} seeds per case; '
        f'{summary.refused} refused, {summary.errors} errors; '
        f'{len(failing)} failing and {len(undecided)} undecided rates.',
        '',
    ]
    if not summary.complete:
        lines += [
            f'> **Partial.** {summary.declared - len(summary.seeds)} of the '
            f'{summary.declared} cases this check defines have no rows yet. Run it to the end before '
            'quoting anything below.',
            '',
        ]
    for message, count in summary.messages:
        lines.append(f'- {count} x `{message}`')
    if summary.messages:
        lines.append('')
    if summary.pooled_rates:
        lines += ['### Pooled per assay', ''] + _rate_table(summary.pooled_rates, 'family') + ['']
    if summary.pooled_spreads:
        lines += _spread_table(summary.pooled_spreads, 'family') + ['']
    if summary.rates:
        lines += ['### Per case', ''] + _rate_table(summary.rates, 'case') + ['']
    if summary.spreads:
        lines += _spread_table(summary.spreads, 'case') + ['']
    lines += [f'_Code {code}, rendered {datetime.date.today().isoformat()}._', '']
    return '\n'.join(lines)


def _render_csv(summary: Summary, code: str) -> str:
    """The same numbers as CSV rows, one per series."""
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(
        ['check', 'scope', 'case', 'series', 'n', 'hits', 'rate', 'low', 'high', 'criterion', 'verdict']
        + ['median', 'p99', 'max', 'rms', 'code']
    )
    for scope, rates in (('case', summary.rates), ('family', summary.pooled_rates)):
        for rate in rates:
            writer.writerow(
                [
                    summary.check.name,
                    scope,
                    rate.case,
                    rate.series,
                    rate.n,
                    rate.hits,
                    f'{rate.rate:.6f}',
                    f'{rate.low:.6f}',
                    f'{rate.high:.6f}',
                    _criterion_text(rate.criterion),
                    rate.verdict,
                    '',
                    '',
                    '',
                    '',
                    code,
                ]
            )
    for scope, spreads in (('case', summary.spreads), ('family', summary.pooled_spreads)):
        for spread in spreads:
            writer.writerow(
                [summary.check.name, scope, spread.case, spread.series, spread.n, '', '', '', '', '', '']
                + [f'{spread.median:.6g}', f'{spread.p99:.6g}', f'{spread.largest:.6g}', f'{spread.rms:.6g}', code]
            )
    return out.getvalue()


def tables(names: list[str], fmt: str = 'md', patterns: Sequence[str] | None = None) -> str:
    """Render every named check (all of them by default) from what the store holds.

    *patterns* narrows every table to the cases whose id one of them matches;
    a table so narrowed says which expressions it was narrowed by.
    """
    code = store.code_hash()
    parts = []
    for name in names or list(CHECKS):
        check = CHECKS[name]
        rows = store.load(check.derived_from or name, code)
        parts.append(render(summarise(check, rows, patterns), code, fmt))
    return ''.join(parts) if fmt == 'csv' else '\n'.join(parts)
