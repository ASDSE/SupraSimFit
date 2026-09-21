"""Rows survive a restart, belong to the code that produced them, and are computed once.

The store is what makes a long run resumable and a quoted rate traceable. A row
that outlived a change of the fit engine, or a key computed twice, would put
numbers from two different programs in one table — and a half-written line
that made the whole file unreadable would cost a run that was killed everything
it had already finished.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from validation import store
from validation.checks import CHECKS
from validation.run import pending_jobs

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def results(tmp_path, monkeypatch):
    """A results directory of this test's own."""
    monkeypatch.setattr(store, 'RESULTS_DIR', tmp_path)
    return tmp_path


def test_rows_come_back_as_they_went_in(results):
    """A run that is killed keeps what it finished, so reading has to give it back unchanged."""
    rows = [{'case': 'A', 'seed': seed, 'code': 'abc', 'cov': {'Ka': seed % 2 == 0}} for seed in range(3)]
    store.append('demo', rows)
    store.append('demo', [{'case': 'B', 'seed': 0, 'code': 'abc', 'cov': {'Ka': True}}])
    loaded = store.load('demo', 'abc')
    assert set(loaded) == {('A', 0), ('A', 1), ('A', 2), ('B', 0)}
    assert loaded[('A', 1)]['cov'] == {'Ka': False}


def test_a_row_of_another_code_is_not_read_but_is_not_lost(results):
    """A row from an earlier engine would silently mix two programs' numbers in one rate."""
    store.append('demo', [{'case': 'A', 'seed': 0, 'code': 'old', 'cov': {'Ka': False}}])
    store.append('demo', [{'case': 'A', 'seed': 1, 'code': 'new', 'cov': {'Ka': True}}])
    assert set(store.load('demo', 'new')) == {('A', 1)}
    assert set(store.load('demo', 'old')) == {('A', 0)}
    assert len(store.path('demo').read_text().splitlines()) == 2


def test_pruning_drops_only_the_rows_of_another_code(results):
    """Pruning is how the file stops growing, and it must not take the live rows with it."""
    store.append('demo', [{'case': 'A', 'seed': s, 'code': 'old'} for s in range(3)])
    store.append('demo', [{'case': 'A', 'seed': 3, 'code': 'new'}])
    assert store.prune('demo', 'new') == 3
    assert [json.loads(line)['seed'] for line in store.path('demo').read_text().splitlines()] == [3]


def test_a_resumed_run_computes_only_the_missing_rows(results):
    """Seeds run in order so an extension re-uses everything; recomputing would waste a run and the rows."""
    check = CHECKS['conditional-coverage']
    cases = [case.id for case in check.cases[:2]]
    store.append('demo', [{'case': cases[0], 'seed': seed, 'code': 'abc'} for seed in range(4)])
    done = set(store.load('demo', 'abc'))
    jobs = pending_jobs(check, cases, 4, done, 'abc')
    assert [(job[1], job[2]) for job in jobs] == [(cases[1], seed) for seed in range(4)]
    assert pending_jobs(check, cases, 6, done, 'abc')[:2] == [
        (check.name, cases[0], 4, 'abc'),
        (check.name, cases[0], 5, 'abc'),
    ]


def test_a_half_written_line_costs_its_own_row_and_no_other(results):
    """A kill between two rows is how a long run ends; every row it finished has to survive it."""
    store.append('demo', [{'case': 'A', 'seed': seed, 'code': 'abc'} for seed in range(3)])
    file = store.path('demo')
    lines = file.read_text().splitlines()
    file.write_text('\n'.join(lines[:-1] + [lines[-1][:20]]) + '\n')
    assert set(store.load('demo', 'abc')) == {('A', 0), ('A', 1)}


def test_pruning_repairs_a_damaged_file(results):
    """Pruning is the only repair there is, so it cannot be the thing that trips over the damage."""
    store.append('demo', [{'case': 'A', 'seed': seed, 'code': 'abc'} for seed in range(3)])
    file = store.path('demo')
    lines = file.read_text().splitlines()
    file.write_text('\n'.join(lines[:-1] + [lines[-1][:20]]) + '\n')
    assert store.prune('demo', 'abc') == 1
    assert [json.loads(line)['seed'] for line in file.read_text().splitlines()] == [0, 1]
    assert set(store.load('demo', 'abc')) == {('A', 0), ('A', 1)}


@pytest.fixture
def code_copy(tmp_path):
    """A copy of the modules the hash covers, to edit without touching the repository."""
    for package in store.CODE_ROOTS:
        shutil.copytree(ROOT / package, tmp_path / package)
    return tmp_path


def test_rewording_a_docstring_keeps_the_rows(code_copy):
    """Rows cost hours; a documentation pass must not throw them away."""
    before = store.code_hash(code_copy)
    target = code_copy / 'core' / 'pipeline' / 'varpro.py'
    text = target.read_text(encoding='utf-8')
    head, _, rest = text.partition('"""')
    body, _, tail = rest.partition('"""')
    target.write_text(f'{head}"""{body} One more sentence about what this does."""{tail}', encoding='utf-8')
    assert store.code_hash(code_copy) == before


def test_changing_what_the_code_does_retires_the_rows(code_copy):
    """A row describes the program that produced it; a changed engine makes it a different claim."""
    before = store.code_hash(code_copy)
    target = code_copy / 'core' / 'pipeline' / 'varpro.py'
    text = target.read_text(encoding='utf-8')
    assert 'LEVEL = ' in text
    target.write_text(text.replace('LEVEL = ', 'LEVEL = 0.5 * ', 1), encoding='utf-8')
    assert store.code_hash(code_copy) != before


def test_the_hash_covers_every_package_a_fit_goes_through(code_copy):
    """A root left out would let a change there pass unnoticed and keep rows it invalidates."""
    for package in store.CODE_ROOTS:
        files = sorted((code_copy / package).rglob('*.py'))
        assert files, f'{package} holds no modules'
        before = store.code_hash(code_copy)
        text = files[0].read_text(encoding='utf-8')
        files[0].write_text(text + '\nUNREACHED = 1\n', encoding='utf-8')
        assert store.code_hash(code_copy) != before, f'a change in {package} does not reach the hash'
        files[0].write_text(text, encoding='utf-8')
