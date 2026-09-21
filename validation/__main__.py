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

``python -m validation prune``
    Drop the rows an earlier version of the code produced.
"""

from __future__ import annotations

import argparse
import re

from validation import run as runner
from validation import store
from validation.checks import CHECKS, matching_cases
from validation.tables import tables

_CASES_HELP = 'regular expression searched in the case ids; repeatable, any match selects'


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

    commands.add_parser('prune', help='drop rows from another code hash')

    args = parser.parse_args()
    unknown = [name for name in getattr(args, 'checks', []) if name not in CHECKS]
    if unknown:
        raise SystemExit(f'no such check: {", ".join(unknown)}. The checks are: {", ".join(CHECKS)}.')
    for pattern in getattr(args, 'cases', None) or ():
        try:
            re.compile(pattern)
        except re.error as bad:
            raise SystemExit(f'--cases {pattern!r} is not a regular expression: {bad}') from bad
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
