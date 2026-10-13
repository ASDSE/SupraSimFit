"""A sensitivity batch dispatched to real worker processes.

A sensitivity run spreads its perturbations over spawned processes, and what
happens when one of them stops early is only visible with real ones: a patched
stand-in lives in the parent, where the pool's teardown never runs. These tests
therefore start a genuine ``ProcessPoolExecutor`` and check the two ways a batch
ends other than by finishing — the user stopping it, and a job that fails in a
way the per-fit guard does not cover. Both have to hand control back at once and
leave no worker process behind: the application is a desktop interface, and a
pool draining thousands of queued fits looks exactly like one that is hung.

The thread cap the workers run under is here for the same reason: a spawned
process reads it from the environment as its numerical libraries load, which no
in-process stand-in reproduces.
"""

import multiprocessing
import os
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pytest

import core.pipeline.sensitivity as sens
from core.assays.ida import IDAAssay
from core.data_processing.measurement_set import MeasurementSet
from core.pipeline.fit_pipeline import FitConfig
from core.pipeline.noise import NoiseBasis, NoiseLaw
from core.pipeline.sensitivity import TITRANT
from core.units import Q_
from tests.conftest import GDA_IDA_RECOVERY_BOUNDS, IDA_TRUE, _make_ida_data

_CONDITIONS = {
    'Ka_dye': Q_(IDA_TRUE['Ka_dye'], '1/M'),
    'h0': Q_(IDA_TRUE['h0'], 'M'),
    'd0': Q_(IDA_TRUE['d0'], 'M'),
}
_N_JOBS = 120

#: Jobs for the latency test. Two workers need minutes for this many, so a stop
#: that came back only once the queue had drained could not stay inside
#: ``_STOP_SECONDS``.
_N_STOP_JOBS = 800

#: A stop has to be answered within this long, counted from the moment the
#: caller first says to stop. Only the fits genuinely mid-solve and the pool's
#: teardown belong in that time; the analysis shows nothing while it stops, so
#: anything longer reads as a frozen window and invites a second press.
_STOP_SECONDS = 10.0


@pytest.fixture
def batch():
    """Everything :func:`~core.pipeline.sensitivity._evaluate_batch` needs, with real offsets to fit."""
    x, y = _make_ida_data(IDA_TRUE, n_points=20)
    ms = MeasurementSet(concentrations=x, signals=y.reshape(1, -1), replica_ids=('r0',))
    perturbations = [({TITRANT: 0.001 * (index % 11 - 5)}, None) for index in range(_N_JOBS)]
    return {
        'ms': ms,
        'assay_cls': IDAAssay,
        'x_base': np.asarray(ms.concentrations),
        'base_conditions': dict(_CONDITIONS),
        'fit_config': FitConfig(custom_bounds=GDA_IDA_RECOVERY_BOUNDS),
        'perturbations': perturbations,
    }


def _evaluate(batch, *, on_result, should_cancel, max_workers=2, point_weights=None):
    """Run the batch, over worker processes or — with one core, or too few jobs — in this process."""
    return sens._evaluate_batch(
        batch['ms'],
        batch['assay_cls'],
        batch['x_base'],
        batch['base_conditions'],
        batch['fit_config'],
        batch['perturbations'],
        sequential=False,
        max_workers=max_workers,
        on_result=on_result,
        should_cancel=should_cancel,
        point_weights=point_weights,
    )


def test_a_stopped_batch_drops_the_fits_it_had_queued(batch):
    """Stopping leaves the remaining perturbations unfitted and every worker process gone.

    The interface re-enables its Run button once the analysis returns, so a pool
    still working through queued fits would be a second run's competition for
    the machine.
    """
    assert _N_JOBS >= sens._PARALLEL_MIN_JOBS  # below this the work would stay in this process
    finished: list[object] = []

    results = _evaluate(
        batch, on_result=lambda index, value: finished.append(value), should_cancel=lambda: len(finished) >= 3
    )

    assert 3 <= len(finished) < _N_JOBS
    assert sum(value is not None for value in results) == len(finished)
    assert not multiprocessing.active_children()


def test_a_stop_is_answered_while_the_pool_is_still_starting(batch):
    """A stop arriving before the first fit lands comes back within seconds.

    Spawned workers need a moment to import their numerical stack, and the
    interface has nothing to show while a run stops. A batch that asks whether
    to stop only once a fit has come back is deaf for the whole of that
    start-up, which is the slowest a stop can ever be: the queue is at its
    longest and no worker has produced anything yet.
    """
    batch['perturbations'] = [({TITRANT: 0.001 * (index % 11 - 5)}, None) for index in range(_N_STOP_JOBS)]
    finished: list[object] = []
    fits_at_each_ask: list[int] = []
    requested_at: list[float] = []

    def should_cancel() -> bool:
        fits_at_each_ask.append(len(finished))
        if len(fits_at_each_ask) == 1:
            return False  # one ask to prove the batch asks before it has anything
        requested_at.append(time.perf_counter())
        return True

    results = _evaluate(batch, on_result=lambda index, value: finished.append(value), should_cancel=should_cancel)
    latency = time.perf_counter() - requested_at[0]

    assert fits_at_each_ask[0] == 0  # asked while the workers were still starting
    assert latency < _STOP_SECONDS
    assert sum(value is not None for value in results) == len(finished)
    assert len(finished) < _N_STOP_JOBS // 4  # the queue was dropped, not fitted
    assert not multiprocessing.active_children()


@pytest.mark.parametrize(
    'max_workers, n_jobs',
    [(2, _N_JOBS), (1, sens._PARALLEL_MIN_JOBS - 1)],
    ids=['over worker processes', 'in this process'],
)
def test_a_job_that_fails_outright_stops_the_batch_at_once_in_plain_words(batch, max_workers, n_jobs):
    """One job failing beyond the per-fit guard ends the batch immediately, with a message a user can act on.

    The guard turns an unsolvable fit into a sample without a fit, so anything
    still raising is a failure the analysis cannot work around. The offsets of
    the first job stand in for one: they are not numbers, so the perturbation
    cannot even be built.

    A run over a single core, or one with too few perturbations to be worth a
    pool — a small heatmap — does the work in this process instead. The same
    failure has to say the same thing there: what the user is told cannot
    depend on how many cores the machine has or how many cells the grid holds.
    """
    batch['perturbations'] = batch['perturbations'][:n_jobs]
    batch['perturbations'][0] = ({TITRANT: 'not a number'}, None)
    finished: list[object] = []

    with pytest.raises(RuntimeError, match='could not be completed') as raised:
        _evaluate(
            batch,
            on_result=lambda index, value: finished.append(value),
            should_cancel=lambda: False,
            max_workers=max_workers,
        )

    assert isinstance(raised.value.__cause__, TypeError)  # the real failure is kept for the log
    assert len(finished) < n_jobs / 2  # the rest were dropped rather than fitted first
    assert not multiprocessing.active_children()


def test_the_point_weights_of_the_run_reach_every_worker_process(batch):
    """Every fit of a run carries the point weights the baseline fit ran with, wherever the fit is made.

    The weights are handed to the pool once, with the rest of the batch's
    state; a worker that started without them would fit its perturbations
    unweighted and report other binding constants for them — the samples and
    the estimate they are read against would then come from two estimators.
    """
    batch['perturbations'] = batch['perturbations'][: 4 * sens._PARALLEL_MIN_JOBS]
    signal = batch['ms'].average_signal()
    # Proportional noise: the weights fall as the square of the signal, which
    # is as far from equal weighting as this law goes.
    law = NoiseLaw(NoiseBasis.REPLICATES, share=1.0, reference=float(np.sqrt(np.mean(signal**2))), n_replicates=3)
    weights = law.weights(signal)

    weighted = _evaluate(batch, on_result=lambda index, value: None, should_cancel=lambda: False, point_weights=weights)
    equal = _evaluate(batch, on_result=lambda index, value: None, should_cancel=lambda: False)

    assert len(weighted) == len(batch['perturbations'])
    for (offsets, _), in_pool, unweighted in zip(batch['perturbations'], weighted, equal):
        here = sens._fit_perturbed(
            batch['ms'],
            batch['assay_cls'],
            batch['x_base'],
            batch['base_conditions'],
            offsets,
            batch['fit_config'],
            point_weights=weights,
        )
        assert in_pool[0]['Ka_guest'] == here[0]['Ka_guest']
        assert in_pool[2] == here[2]
        assert in_pool[0]['Ka_guest'] != unweighted[0]['Ka_guest']


def _thread_limits() -> dict[str, str | None]:
    """The thread-cap variables as the process running this sees them."""
    return {name: os.environ.get(name) for name in sens._THREAD_LIMIT_VARS}


def test_a_worker_started_under_the_cap_inherits_it(monkeypatch):
    """A worker process sees the cap in its environment from the moment it starts.

    Its numerical libraries read these as they load, which happens before any
    code of ours runs there, so a cap set inside the worker would be read by
    nothing. Left uncapped, each of a dozen workers starts a thread per core and
    they fight over the machine.
    """
    for name in sens._THREAD_LIMIT_VARS:
        monkeypatch.delenv(name, raising=False)

    with sens._thread_capped_children():
        with ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context('spawn')) as pool:
            in_worker = pool.submit(_thread_limits).result()

    assert in_worker == dict.fromkeys(sens._THREAD_LIMIT_VARS, '1')
    assert _thread_limits() == dict.fromkeys(sens._THREAD_LIMIT_VARS, None)


def test_a_batch_over_worker_processes_leaves_this_process_uncapped(batch):
    """Running an analysis does not cap the application's own numerical work."""
    before = _thread_limits()

    _evaluate(batch, on_result=lambda index, value: None, should_cancel=lambda: False)

    assert _thread_limits() == before
