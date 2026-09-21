"""Running the checks: a staged ladder, one process pool, rows flushed as they finish.

Seeds are always 0, 1, 2 … in order, so extending a case re-uses every row it
already has and a run that is killed loses nothing. Every case runs the first
stage of the ladder; a case stops there once every rate judged of it has
passed, and every other case goes on to the next stage. A pass at 100 seeds
would be a pass at 400, so stopping on it changes no decision; a fail and an
undecided go on, which is what puts every published fail on the full number of
draws the ladder reaches.

A job that raises inside its worker is stored as an error row. A worker
process that dies outright takes its pool with it; the jobs that had not
produced a row are resubmitted on a new pool, since a job is a pure function
of ``(check, case, seed)``.
"""

from __future__ import annotations

import os
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from concurrent.futures.process import BrokenProcessPool
from typing import Any, Iterable, Sequence

from validation import store
from validation.checks import CHECKS, Check, case_by_id, matching_cases
from validation.criteria import stops_early
from validation.tables import summarise_group

__all__ = ['TimeLimit', 'compute', 'pending_jobs', 'run']

#: Cores left to the machine when the worker count is not given.
_SPARE_CORES = 2

#: How many times in a row a pool may die without finishing a single row
#: before the run gives up: past that the jobs themselves are killing the
#: workers and resubmitting them forever would hide it.
_POOL_REBUILDS = 3


class TimeLimit(Exception):
    """Raised when a run reaches the wall-clock limit it was given."""


_CASES: dict[str, dict[str, Any]] = {}


def _case(check: str, case_id: str) -> Any:
    """The case of *check* with this id, looked up once per process."""
    if check not in _CASES:
        _CASES[check] = case_by_id(CHECKS[check])
    return _CASES[check][case_id]


def compute(job: tuple[str, str, int, str]) -> dict[str, Any]:
    """One row: run *check*'s row function on the named case and seed.

    A row always comes back. What the row function itself does not catch is
    caught here and stored as an error, so one broken case cannot end a run.
    """
    check, case_id, seed, code = job
    try:
        row = CHECKS[check].row(_case(check, case_id), seed)
    except Exception:  # noqa: BLE001 - the row records the failure instead of ending the run
        row = {'refused': None, 'error': traceback.format_exc(limit=3)[-500:]}
    return {'case': case_id, 'seed': seed, 'code': code, **row}


def pending_jobs(check: Check, case_ids: Iterable[str], size: int, done: set[tuple[str, int]], code: str) -> list:
    """The ``(check, case, seed, code)`` jobs still missing to reach *size* seeds of each case."""
    return [
        (check.name, case_id, seed, code) for case_id in case_ids for seed in range(size) if (case_id, seed) not in done
    ]


def _case_passed(check: Check, case_id: str, rows: list[dict[str, Any]], views: list[Check]) -> bool:
    """Whether every rate judged of *case_id* has passed — by the check and by the checks reading it.

    Only that stops a case before the end of the ladder. A case with nothing
    judged of it yet, because every fit of it so far was refused, goes on with
    the rest.
    """
    judged: list = []
    for reader in [check, *views]:
        if reader.criterion is None:
            continue
        if reader.cases and case_id not in case_by_id(reader):
            continue
        rates, _ = summarise_group(reader, case_id, rows)
        judged += [rate for rate in rates if rate.criterion is not None]
    return bool(judged) and all(stops_early(rate.verdict) for rate in judged)


def _ladder(check: Check, max_n: int) -> list[int]:
    """The seed counts *check* steps through, capped at *max_n*."""
    return sorted({min(size, max_n) for size in check.stages})


def _error_row(job: tuple[str, str, int, str], failure: BaseException) -> dict[str, Any]:
    """The row a job gets when its worker died before it could produce one."""
    return {
        'case': job[1],
        'seed': job[2],
        'code': job[3],
        'refused': None,
        'error': f'{type(failure).__name__}: {failure}',
    }


def _one_pool(jobs: list, check: str, deadline: float | None, workers: int, total: int) -> tuple[list, int]:
    """Run *jobs* in one pool, appending each row as it finishes.

    Returns
    -------
    tuple[list, int]
        The jobs that produced no row because the pool died under them, and
        how many rows were written.
    """
    ran = 0
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(compute, job): job for job in jobs}
        finished: set = set()
        try:
            for future in as_completed(futures):
                try:
                    row = future.result()
                except BrokenProcessPool:
                    pool.shutdown(wait=False, cancel_futures=True)
                    return [job for f, job in futures.items() if f not in finished], ran
                except Exception as failure:  # noqa: BLE001 - one dead job costs its row, not the run
                    row = _error_row(futures[future], failure)
                store.append(check, [row])
                finished.add(future)
                ran += 1
                if ran % 100 == 0:
                    print(f'  {ran}/{total} rows', flush=True)
                if deadline is not None and time.monotonic() > deadline:
                    raise TimeLimit(f'{ran} of {total} rows of {check} done')
        except (KeyboardInterrupt, TimeLimit):
            for future in futures:
                future.cancel()
            for process in list(pool._processes.values()):
                process.terminate()
            pool.shutdown(wait=False, cancel_futures=True)
            raise
    return [], ran


def _execute(jobs: list, check: str, deadline: float | None, workers: int) -> int:
    """Run *jobs*, rebuilding the pool around a worker that dies. Returns how many rows ran."""
    done, left, stalled = 0, list(jobs), 0
    while left:
        left, ran = _one_pool(left, check, deadline, min(workers, len(left)), len(jobs))
        done += ran
        if left:
            stalled = 0 if ran else stalled + 1
            if stalled > _POOL_REBUILDS:
                raise RuntimeError(
                    f'the workers of {check} died {stalled} times without finishing a row; '
                    f'{len(left)} rows were not computed.'
                )
            print(f'  a worker died with {len(left)} rows in flight; they go on a new pool.', flush=True)
    return done


def run(
    names: list[str],
    jobs: int | None = None,
    max_n: int = 400,
    time_limit_min: float | None = None,
    cases: Sequence[str] | None = None,
) -> None:
    """Compute the rows every named check is still missing.

    Parameters
    ----------
    names : list[str]
        Checks to run; every check with cases of its own when empty.
    jobs : int, optional
        Worker processes. The default leaves two cores to the machine.
    max_n : int
        Most seeds any one case runs.
    time_limit_min : float, optional
        Wall-clock limit. The rows finished by then are kept.
    cases : Sequence[str], optional
        Regular expressions searched in each case id; a case runs when one of
        them matches. Every case of the check when none is given.
    """
    code = store.code_hash()
    deadline = None if time_limit_min is None else time.monotonic() + 60 * time_limit_min
    workers = jobs if jobs else max(1, (os.cpu_count() or 1) - _SPARE_CORES)
    for name in names or [n for n, c in CHECKS.items() if c.cases]:
        check = CHECKS[name]
        if check.derived_from is not None:
            print(f'{name}: reads the rows of {check.derived_from}; nothing to run.', flush=True)
            continue
        views = [c for c in CHECKS.values() if c.derived_from == name]
        rows = store.load(name, code)
        active = [case.id for case in matching_cases(check, cases)]
        if not active:
            print(f'{name}: no case matches {", ".join(cases or ())}; nothing to run.', flush=True)
            continue
        print(f'{name}: {len(active)} cases, {len(rows)} rows already stored (code {code}).', flush=True)
        for size in _ladder(check, max_n):
            work = pending_jobs(check, active, size, set(rows), code)
            if work:
                print(f'  stage {size} seeds: {len(work)} rows on {workers} workers', flush=True)
                try:
                    _execute(work, name, deadline, workers)
                except TimeLimit as stop:
                    print(f'  time limit reached ({stop}); rows so far are kept.', flush=True)
                    return
                rows = store.load(name, code)
            if check.criterion is None and all(view.criterion is None for view in views):
                break
            by_case: dict[str, list[dict[str, Any]]] = {case_id: [] for case_id in active}
            for (case_id, _seed), row in rows.items():
                if case_id in by_case:
                    by_case[case_id].append(row)
            active = [c for c in active if not _case_passed(check, c, by_case[c], views)]
            print(f'  after {size} seeds: {len(active)} cases have not passed', flush=True)
            if not active:
                break
