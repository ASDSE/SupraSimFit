"""Command line of the validation package.

``python -m validation run <check>... [--jobs N] [--max-n 400] [--time-limit-min M] [--cases RE]``
    Compute the rows the named checks are missing; every check with cases of
    its own when none is named. Idempotent: rows already stored for the current
    code are not computed again.

``python -m validation tables [<check>...] [--format md|csv] [--cases RE]``
    Render what the store holds.

``python -m validation list [--cases RE]``
    What each check claims and how many cases and rows it has, or the ids of
    the cases matching ``--cases``.

``--cases`` takes a regular expression searched in each case id and may be
repeated; a case is taken when one of them matches. A fix round re-runs and
prints the cells it touched and nothing else.

``python -m validation compare CODE_A [CODE_B] [<check>...] [--ignore FIELD]``
    Compare the rows two code hashes stored for the same cases and seeds, field
    by field. ``CODE_B`` is the current hash when it is left out. Exits 1 as
    soon as one field differs, or when a check named on the command line holds
    no row under both hashes. ``--ignore`` may be repeated and names a field
    left out of the comparison: one that only one of the two hashes writes.

``python -m validation prune``
    Drop the rows an earlier version of the code produced.
"""

from __future__ import annotations

import argparse
import re
from collections import Counter

from validation import run as runner
from validation import store
from validation.checks import CHECKS, matching_cases
from validation.tables import tables

_CASES_HELP = 'regular expression searched in the case ids; repeatable, any match selects'

#: What a code hash looks like on the command line: the twelve hexadecimal
#: digits :func:`~validation.store.code_hash` prints. An argument of ``compare``
#: that is not one is a check name, and an unknown check name is refused rather
#: than read as a hash nothing was ever stored under.
_CODE_HASH = re.compile('[0-9a-f]{12}')


def _list_checks() -> None:
    """What every check claims, what it rests on and how many rows it has."""
    code = store.code_hash()
    print(f'code {code}\n')
    for name, check in CHECKS.items():
        rows = store.load(check.derived_from or name, code)
        cases = f'{len(check.cases)} cases' if check.cases else 'every case'
        source = f'reads {cases} of {check.derived_from}' if check.derived_from else cases
        criterion = 'reported' if check.criterion is None else check.criterion.text
        print(f'{name:22s} {source:40s} {criterion:18s} {len(rows)} rows')
        print(f'  {check.claim}\n')


def _list_cases(patterns: list[str]) -> None:
    """The id of every case *patterns* selects, check by check."""
    for name, check in CHECKS.items():
        selected = matching_cases(check, patterns)
        if not selected:
            continue
        print(f'{name}: {len(selected)} of {len(check.cases)} cases match')
        for case in selected:
            print(f'  {case.id}')


def _compare(code_a: str, code_b: str, names: list[str], ignore: list[str]) -> int:
    """Print what the rows of two code hashes disagree on, and return the exit status.

    Every named check, or every check whose file holds rows, is compared over
    the ``(case, seed)`` keys both hashes hold. Zero differing rows over rows
    that exist is the pass; a check named on the command line with no common
    rows is a failure, because the comparison it was asked for did not happen.

    A check that differs names every field it differs on and how many keys
    each one moved on. A field only one of the hashes writes differs on every
    key; *ignore* names such fields, so that the exit status is decided by the
    fields both sides carry.
    """
    print(f'comparing {code_a} against {code_b}\n')
    if ignore:
        print(f'not compared: {", ".join(ignore)}\n')
    failed = False
    compared_anything = False
    for name in names or list(CHECKS):
        compared, found = store.differences(name, code_a, code_b, ignore=(*store.UNCOMPARED, *ignore))
        compared_anything = compared_anything or compared > 0
        if not compared:
            if names:
                print(f'{name:22s} no rows stored under both hashes')
                failed = True
            continue
        differing = {(case, seed) for case, seed, _ in found}
        print(f'{name:22s} {compared} rows compared, {len(differing)} differing')
        if found:
            tally = Counter(field for _, _, field in found)
            print('  fields: ' + ', '.join(f'{field} ({count})' for field, count in sorted(tally.items())))
            case, seed, field = found[0]
            print(f'  first difference: {case} seed {seed} field {field}')
            failed = True
    if not compared_anything:
        print('no check holds rows under both hashes; nothing was compared.')
        failed = True
    return 1 if failed else 0


def main() -> None:
    """Read the command line and do what it says."""
    parser = argparse.ArgumentParser(prog='python -m validation', description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest='command', required=True)

    run_parser = commands.add_parser('run', help='compute missing rows')
    run_parser.add_argument('checks', nargs='*', help='checks to run (default: all)')
    run_parser.add_argument('--jobs', type=int, default=None, help='worker processes (default: cores minus two)')
    run_parser.add_argument('--max-n', type=int, default=400, help='most seeds per case (default 400)')
    run_parser.add_argument('--time-limit-min', type=float, default=None, help='wall-clock limit in minutes')
    run_parser.add_argument('--cases', action='append', metavar='RE', help=_CASES_HELP)

    table_parser = commands.add_parser('tables', help='render the stored rows')
    table_parser.add_argument('checks', nargs='*', help='checks to render (default: all)')
    table_parser.add_argument('--format', choices=('md', 'csv'), default='md', help='markdown (default) or CSV')
    table_parser.add_argument('--cases', action='append', metavar='RE', help=_CASES_HELP)

    list_parser = commands.add_parser('list', help='what each check claims')
    list_parser.add_argument('--cases', action='append', metavar='RE', help=_CASES_HELP)

    compare_parser = commands.add_parser('compare', help='compare the rows of two code hashes')
    compare_parser.add_argument('code_a', metavar='CODE_A', help='code hash the rows are compared from')
    compare_parser.add_argument(
        'rest',
        nargs='*',
        metavar='CODE_B | check',
        help='the second code hash (default: the current one), then the checks to compare (default: all)',
    )
    compare_parser.add_argument(
        '--ignore',
        action='append',
        default=[],
        metavar='FIELD',
        help='a row field to leave out of the comparison; may be repeated',
    )

    commands.add_parser('prune', help='drop rows from another code hash')

    args = parser.parse_args()
    if args.command == 'compare':
        rest = list(args.rest)
        code_b = rest.pop(0) if rest and _CODE_HASH.fullmatch(rest[0]) else store.code_hash()
        args.checks = rest
    unknown = [name for name in getattr(args, 'checks', []) if name not in CHECKS]
    if unknown:
        raise SystemExit(f'no such check: {", ".join(unknown)}. The checks are: {", ".join(CHECKS)}.')
    for pattern in getattr(args, 'cases', None) or ():
        try:
            re.compile(pattern)
        except re.error as bad:
            raise SystemExit(f'--cases {pattern!r} is not a regular expression: {bad}') from bad
    if args.command == 'compare':
        raise SystemExit(_compare(args.code_a, code_b, args.checks, args.ignore))
    if args.command == 'run':
        runner.run(args.checks, jobs=args.jobs, max_n=args.max_n, time_limit_min=args.time_limit_min, cases=args.cases)
    elif args.command == 'tables':
        print(tables(args.checks, args.format, args.cases))
    elif args.command == 'list' and args.cases:
        _list_cases(args.cases)
    elif args.command == 'list':
        _list_checks()
    elif args.command == 'prune':
        for name in CHECKS:
            dropped = store.prune(name)
            if dropped:
                print(f'{name}: dropped {dropped} rows from another code hash')


if __name__ == '__main__':
    main()
