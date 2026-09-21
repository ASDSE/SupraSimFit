"""Append-only rows, one file per check, keyed by scenario, seed and the code that produced them.

A row is valid for the code it was computed with. :func:`code_hash` reads
every module the fit goes through, strips the docstrings and hashes what is
left, so reformatting or rewording keeps a run's rows and any change of
executable code retires them. Retired rows stay on disk — they are the record
of what the previous code did — until ``python -m validation prune`` removes
them.

A row is written as one unbuffered append of the whole encoded line, and a
line that is nonetheless unreadable is skipped with a count rather than
raising: a run killed mid-append keeps every row it had finished, and
``prune`` rewrites the file without the damaged line.
"""

from __future__ import annotations

import ast
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any, Iterable

__all__ = [
    'CODE_ROOTS',
    'RESULTS_DIR',
    'UNCOMPARED',
    'append',
    'code_hash',
    'differences',
    'load',
    'path',
    'prune',
    'row_key',
]

#: Where the rows live: one JSON Lines file per check.
RESULTS_DIR = Path(__file__).resolve().parent / 'results'

#: The packages a fit goes through. A change anywhere in them can move any
#: number in any check, so every row names the hash of all of them together.
CODE_ROOTS = (
    'core/models',
    'core/assays',
    'core/pipeline',
    'core/optimizer',
    'core/data_processing',
)

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _without_docstrings(tree: ast.AST) -> ast.AST:
    """*tree* with the docstring removed from every module, class and function it holds."""
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = node.body
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
            if isinstance(body[0].value.value, str):
                node.body = body[1:] or [ast.Pass()]
    return tree


def code_hash(root: Path | None = None) -> str:
    """Short hash of the executable code of :data:`CODE_ROOTS` under *root* (the repository by default).

    Every ``.py`` file is parsed, its docstrings are dropped and the remaining
    syntax tree is dumped, so comments, docstrings and formatting are outside
    the hash and anything the interpreter runs is inside it.

    Returns
    -------
    str
        The first 12 hexadecimal digits of the SHA-256 of the dumped trees,
        each preceded by its path.
    """
    base = _REPO_ROOT if root is None else Path(root)
    digest = hashlib.sha256()
    for package in CODE_ROOTS:
        for file in sorted((base / package).rglob('*.py')):
            digest.update(file.relative_to(base).as_posix().encode('utf-8'))
            tree = _without_docstrings(ast.parse(file.read_text(encoding='utf-8')))
            digest.update(ast.dump(tree).encode('utf-8'))
    return digest.hexdigest()[:12]


def path(check: str) -> Path:
    """The file the rows of *check* live in."""
    return RESULTS_DIR / f'{check}.jsonl'


def row_key(row: dict[str, Any]) -> tuple[str, int]:
    """The ``(case, seed)`` a row belongs to."""
    return row['case'], int(row['seed'])


def append(check: str, rows: Iterable[dict[str, Any]]) -> None:
    """Add *rows* to *check*'s file, creating it if it does not exist.

    Each row is one unbuffered write of the whole encoded line to a file
    opened for appending, so a process that dies between two rows leaves whole
    lines behind it.
    """
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with path(check).open('ab', buffering=0) as handle:
        for row in rows:
            handle.write((json.dumps(row, default=float) + '\n').encode('utf-8'))


def _readable(file: Path) -> tuple[list[dict[str, Any]], int]:
    """Every row of *file* that parses, and how many lines did not.

    Returns
    -------
    tuple[list[dict], int]
        The rows in file order, and the number of unreadable lines — a line a
        killed run left half-written, or one a full disk cut short.
    """
    rows: list[dict[str, Any]] = []
    damaged = 0
    for line in file.read_text(encoding='utf-8', errors='replace').splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            damaged += 1
    return rows, damaged


def load(check: str, code: str | None = None) -> dict[tuple[str, int], dict[str, Any]]:
    """Every row of *check* computed with code hash *code* (the current one by default).

    An unreadable line is skipped and the count is reported on stderr, so a
    damaged file costs the rows it damaged and not the file.

    Returns
    -------
    dict
        ``(case, seed)`` → the row. A key written more than once keeps the last
        row, so a re-run of a case replaces what it replaces.
    """
    wanted = code_hash() if code is None else code
    file = path(check)
    if not file.exists():
        return {}
    found, damaged = _readable(file)
    if damaged:
        print(f'{file.name}: {damaged} unreadable lines skipped; `prune` rewrites the file.', file=sys.stderr)
    return {row_key(row): row for row in found if row.get('code') == wanted}


def prune(check: str, code: str | None = None) -> int:
    """Drop every row of *check* that another code hash produced, and every unreadable line.

    Returns
    -------
    int
        How many lines were removed.
    """
    wanted = code_hash() if code is None else code
    file = path(check)
    if not file.exists():
        return 0
    found, damaged = _readable(file)
    kept = [row for row in found if row.get('code') == wanted]
    file.write_text(''.join(json.dumps(row, default=float) + '\n' for row in kept), encoding='utf-8')
    return len(found) - len(kept) + damaged


#: Fields two runs of the same code are not expected to agree on: which code
#: produced the row, and how long the fit took.
UNCOMPARED = ('code', 't_fit', 't_total')


def _same(a: Any, b: Any) -> bool:
    """Whether two stored values are the same number, structure for structure.

    Rows are compared after a JSON round trip, which reproduces a float from
    its shortest repr, so two bit-identical fits give values that compare equal
    exactly. Two ``NaN`` are the same answer here — a quantity the fit could
    not produce — although they are never equal.
    """
    if isinstance(a, float) and isinstance(b, float):
        return a == b or (math.isnan(a) and math.isnan(b))
    if isinstance(a, dict) and isinstance(b, dict):
        return set(a) == set(b) and all(_same(a[key], b[key]) for key in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b))
    return a == b


def differences(
    check: str, code_a: str, code_b: str, ignore: Iterable[str] = UNCOMPARED
) -> tuple[int, list[tuple[str, int, str]]]:
    """Every field in which the rows of *check* under two code hashes disagree.

    Only the ``(case, seed)`` keys both hashes hold are compared; a key one of
    them is missing says nothing about whether the numbers moved. A field
    present under one hash and absent under the other is a difference, as is a
    field whose value changed.

    Returns
    -------
    tuple[int, list[tuple[str, int, str]]]
        How many ``(case, seed)`` keys were compared, and one
        ``(case, seed, field)`` per differing field, in key order.
    """
    left, right = load(check, code_a), load(check, code_b)
    skip = set(ignore)
    found: list[tuple[str, int, str]] = []
    common = sorted(set(left) & set(right))
    for case, seed in common:
        a, b = left[(case, seed)], right[(case, seed)]
        for field in sorted((set(a) | set(b)) - skip):
            if field not in a or field not in b or not _same(a[field], b[field]):
                found.append((case, seed, field))
    return len(common), found
