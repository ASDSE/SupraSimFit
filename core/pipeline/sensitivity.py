"""Ka input-sensitivity analysis (pure compute layer, no Qt).

A fitted association constant (Ka) is only as trustworthy as the *inputs* fed
into the model — the titrant concentration vector, the fixed conditions
(``h0`` / ``d0`` / …) and any non-fitted binding constant (``Ka_dye``). Each
carries measurement error, and the fit silently compensates by shifting the
fitted Ka. This module re-runs the fit many times with those inputs perturbed
according to each input's stated uncertainty and reports the resulting spread
of Ka, and which of the inputs that spread comes from.

The uncertainties are the ones stated for the fit
(:attr:`~core.pipeline.fit_pipeline.FitConfig.input_specs`); the reported
interval of the fit itself already accounts for them
(:mod:`core.pipeline.input_aware`). What this analysis adds is where the spread
comes from: every sample here is a fit at inputs held at their sampled values,
and the sample with no offset is the fit at the inputs as entered.

Two analysis modes:

- **SOBOL** — every varied input sampled together on a Saltelli design built
  from independently scrambled Sobol' blocks → the Ka distribution, first- and
  total-order Sobol' indices of log₁₀(Ka) with 95 % intervals for their Monte
  Carlo sampling error, and each sample's input offsets, Ka and R².
- **HEATMAP** — sweep two chosen input offsets on a grid, fit at each cell →
  a 2D Ka surface with the R² of every cell.

Every perturbation is refitted by variable projection
(:class:`~core.pipeline.varpro.Projection`), the fit engine: the binding
constants are the minimum of an exactly projected residual over the Ka box, so
one set of perturbed inputs gives one fit however often it is run and the spread
the analysis reports is the inputs' own. Every perturbation yields that fit
whatever its quality; a perturbation the binding model cannot be solved at
anywhere in the Ka box is one sample without a fit, and the thousands of others
stand.

Layering: this module must not import from ``gui.*``. Perturbable inputs are
classified by pint dimensionality of the passed condition Quantities
(``M`` → concentration, ``1/M`` → binding constant); pretty display labels are
derived in the GUI layer.
"""

from __future__ import annotations

import multiprocessing as mp
import operator
import os
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from contextlib import contextmanager
from dataclasses import dataclass, replace
from enum import Enum
from itertools import islice
from typing import Callable, Iterator, Optional

import numpy as np
from scipy.stats import qmc
from scipy.stats import t as student_t

from core.assays.registry import ASSAY_REGISTRY, AssayType, ParamKind
from core.data_processing.measurement_set import MeasurementSet
from core.optimizer.filters import calculate_fit_metrics
from core.pipeline.fit_pipeline import (
    FitConfig,
    FitResult,
    _resolve_bounds,
    fit_measurement_set,
    fit_replica_ids,
)

# The inputs and how their uncertainty is stated live in ``core.pipeline.inputs``;
# every one of these names is importable from this module as well.
from core.pipeline.inputs import (  # noqa: F401
    TITRANT,
    InputSpec,
    SpecKind,
    _to_fraction,
    axis_reaches_zero,
    input_name,
    nominal_value,
    perturbable_inputs,
    spec_bounds,
    spec_fraction,
)
from core.pipeline.varpro import _SEARCH_PER_DECADE, FitCancelled, FitRefused, Projection, _ka_grid


class SensitivityMode(Enum):
    """Analysis mode for a sensitivity run."""

    SOBOL = 'sobol'
    HEATMAP = 'heatmap'


@dataclass(frozen=True)
class SensitivityConfig:
    """User-facing configuration for a sensitivity run.

    Attributes
    ----------
    mode : SensitivityMode
        Which analysis to run.
    n_samples : int
        SOBOL only — base sample count ``N``; the run fits ``N × (k + 2)``
        perturbations for ``k`` varied inputs. ``N`` is split evenly over
        ``_SOBOL_BLOCKS`` independent scrambles and must be one of
        ``_SOBOL_SAMPLE_SIZES``.
    input_specs : dict[str, InputSpec]
        Input key (``TITRANT`` or a condition key) → its uncertainty. An
        absent key, or a spec that does not vary, holds that input fixed.
    seed : int or None
        Seed of the run: fixes the Sobol' scrambles, the one random part of a
        run. ``None`` lets the run draw one, which it reports as
        ``SensitivityResult.seed_used``, so any run can be repeated.
    x_key : str or None
        HEATMAP only — input key swept along the X axis.
    y_key : str or None
        HEATMAP only — input key swept along the Y axis.
    n_steps : int
        HEATMAP only — grid resolution per axis (odd includes the 0 offset).
    """

    mode: SensitivityMode
    n_samples: int
    input_specs: dict[str, InputSpec]
    seed: Optional[int] = None
    x_key: Optional[str] = None
    y_key: Optional[str] = None
    n_steps: int = 11


@dataclass
class SensitivityResult:
    """Outcome of a sensitivity run.

    Attributes
    ----------
    mode : SensitivityMode
        The mode that produced this result.
    assay_type : str
        ``AssayType.name`` of the fitted assay.
    ka_keys : tuple[str, ...]
        Association-constant parameter keys (registry ``log_scale_keys``).
    baseline_ka : dict[str, float]
        Unperturbed Ka per key, in ``1/M``: the baseline fit's own, at the
        inputs exactly as entered.
    x_offsets_pct : np.ndarray or None
        HEATMAP only — X-axis offset grid, in percent.
    y_offsets_pct : np.ndarray or None
        HEATMAP only — Y-axis offset grid, in percent.
    ka_grid : dict[str, np.ndarray] or None
        HEATMAP only — ka_key → 2D array ``[iy, ix]`` in ``1/M``; ``NaN``
        where no fit could be produced.
    n_success : int
        Perturbed fits that produced a fit, whatever its quality.
    n_total : int
        Perturbed fits attempted (excludes the baseline).
    config : SensitivityConfig
        The configuration that produced this result.
    seed_used : int
        Root seed of the run: ``config.seed`` when one was set, otherwise the
        seed the run drew. Feeding it back as ``config.seed`` repeats the run.
    sobol_s1, sobol_st : dict[str, dict[str, float]] or None
        SOBOL only — ka_key → input key → first-order / total-order index of
        the variance of log₁₀(Ka).
    sobol_s1_ci, sobol_st_ci : dict[str, dict[str, tuple[float, float]]] or None
        SOBOL only — ka_key → input key → ``(low, high)`` 95 % t-interval of
        the matching index: the estimate ± t(B − 1, 0.975) × its standard
        error from the delete-one-block jackknife over the ``B`` independent
        scrambles that hold a usable sample (see
        :func:`sobol_indices_with_ci`). It covers the Monte Carlo sampling
        error of that one index only, not errors in the stated input
        uncertainties or in the model; it is not clipped to 0 … 1, and it is
        ``NaN`` when fewer than three scrambles hold a usable sample.
    sample_offsets_pct : dict[str, np.ndarray] or None
        SOBOL only — varied input key → its offset in percent of nominal for
        each ``A`` sample, then each ``B`` sample.
    sample_ka : dict[str, np.ndarray] or None
        SOBOL only — ka_key → best Ka (1/M) per sample, index-aligned with
        ``sample_offsets_pct``; ``NaN`` only where no fit could be produced.
    sample_r2 : np.ndarray or None
        SOBOL only — R² of each sample's best fit, aligned the same way.
    r2_grid : np.ndarray or None
        HEATMAP only — R² of each cell's best fit, aligned with ``ka_grid``.
    baseline_fit : FitResult or None
        The fit of the inputs as entered, made by
        :func:`~core.pipeline.fit_pipeline.fit_measurement_set` with every
        input held at the value entered, that every perturbation is compared
        against. The analysis moves the inputs itself, one sample at a time, so
        the fit it starts from is the one that moves none of them: its interval
        is the interval conditional on the entered inputs, not the headline of
        a fit that lets them move. The same engine fits the baseline and every
        sample, so a sample with no input offset reproduces it exactly. It
        records the replicates it used and left out, and every sample uses and
        is scored on the same replicates.
    sample_params : dict[str, np.ndarray] or None
        SOBOL only — parameter key → that parameter's best-fit value per
        sample, index-aligned with ``sample_ka`` (whose arrays are its Ka
        entries) and in the canonical units of ``FitResult.parameters``;
        ``NaN`` where no fit could be produced.
    degenerate_keys : tuple[str, ...]
        Signal parameters the data determine only in combination, not one by
        one, at the baseline fit's binding constants; empty when every fitted
        signal parameter is identifiable.
    sobol_rows_left_out : dict[str, int] or None
        SOBOL only — ka_key → how many of the ``n_samples`` design rows that
        key's indices and intervals leave out: the rows where the ``A``, the
        ``B`` or any mixed sample gave no finite log₁₀(Ka).
    stopped : bool
        Whether the run was stopped before every planned perturbed fit
        finished. The fits it never reached are ``NaN`` like the ones that
        could not be produced, and ``n_total`` counts only the fits that
        finished.
    """

    mode: SensitivityMode
    assay_type: str
    ka_keys: tuple[str, ...]
    baseline_ka: dict[str, float]
    x_offsets_pct: Optional[np.ndarray]
    y_offsets_pct: Optional[np.ndarray]
    ka_grid: Optional[dict[str, np.ndarray]]
    n_success: int
    n_total: int
    config: SensitivityConfig
    seed_used: int
    sobol_s1: Optional[dict[str, dict[str, float]]] = None
    sobol_st: Optional[dict[str, dict[str, float]]] = None
    sobol_s1_ci: Optional[dict[str, dict[str, tuple[float, float]]]] = None
    sobol_st_ci: Optional[dict[str, dict[str, tuple[float, float]]]] = None
    sample_offsets_pct: Optional[dict[str, np.ndarray]] = None
    sample_ka: Optional[dict[str, np.ndarray]] = None
    sample_r2: Optional[np.ndarray] = None
    r2_grid: Optional[np.ndarray] = None
    baseline_fit: FitResult | None = None
    sample_params: dict[str, np.ndarray] | None = None
    degenerate_keys: tuple[str, ...] = ()
    sobol_rows_left_out: dict[str, int] | None = None
    stopped: bool = False


def estimated_fit_count(sens_config: SensitivityConfig) -> int:
    """Number of perturbed fits a config will run, the baseline excluded.

    Parameters
    ----------
    sens_config : SensitivityConfig
        The configuration to size.

    Returns
    -------
    int
        SOBOL → ``n_samples × (k + 2)`` for ``k`` varied inputs;
        HEATMAP → ``n_steps ** 2``.
    """
    if sens_config.mode is SensitivityMode.SOBOL:
        n_active = sum(1 for spec in sens_config.input_specs.values() if spec.varies)
        return sens_config.n_samples * (n_active + 2)
    return sens_config.n_steps**2


#: Model solves above which a run is worth warning about before it starts. One
#: solve — the species of one design, then the bounded linear least squares on
#: them — takes about 0.2 ms for thirty titration points, so this is about two
#: minutes of one core.
LONG_RUN_SOLVES = 700_000


def estimated_model_solves(sens_config: SensitivityConfig, fit_config: FitConfig, assay_type: AssayType) -> int:
    """Work a configuration will take, counted in solves of the binding model.

    A fit solves the model once per node of its Ka search grid, plus the handful
    the refinement adds, so the grid the bounds in force span is what sets how
    long a run takes; :func:`estimated_fit_count` counts perturbations only.

    Parameters
    ----------
    sens_config : SensitivityConfig
        The sensitivity configuration to size.
    fit_config : FitConfig
        Supplies the custom bounds, which decide the Ka box the search grid
        covers and whether a binding constant is pinned out of it.
    assay_type : AssayType
        Assay being fitted; its registry defaults fill in the bounds the
        configuration does not override.

    Returns
    -------
    int
        Solves of the equilibrium model, the baseline's own fit included.
    """
    meta = ASSAY_REGISTRY[assay_type]
    bounds = {**meta.default_bounds, **(fit_config.custom_bounds or {})}
    nodes = 1
    for key in meta.parameter_keys:
        if meta.param_kinds[key] is ParamKind.BINDING_CONSTANT:
            lo, hi = (float(bound.to(meta.units[key]).magnitude) for bound in bounds[key])
            nodes *= _ka_grid(lo, hi, _SEARCH_PER_DECADE).size
    return (estimated_fit_count(sens_config) + 1) * nodes


#: Keeps a quantile off the exact edges, where a truncated normal maps to its bound.
_QUANTILE_EPS = 1e-9


def _axis_bounds(sens_config: 'SensitivityConfig', key: str, base_conditions: dict, name: str) -> tuple[float, float]:
    """Offset range a heatmap axis sweeps, as fractions of nominal."""
    spec = sens_config.input_specs.get(key)
    if spec is None:
        return 0.0, 0.0
    return spec_bounds(spec, nominal_value(key, base_conditions), name)


#: Largest seed a run draws for itself. A reported seed is meant to be typed
#: back in, and the interface's Fixed seed box is a 32-bit signed integer, so a
#: drawn seed stays inside that range.
MAX_SEED = 2**31 - 1

#: Independent Sobol' scrambles behind each SOBOL design. Splitting the rows
#: into scrambles is what gives the jackknife independent replicates to measure
#: the sampling error from, and it costs accuracy: a Sobol' point set balances
#: each coordinate over its whole length, so N rows split into blocks are a
#: coarser design than N rows in one scramble. Measured on the Ishigami function
#: and a g-function, the indices pooled over eight scrambles of N/8 rows carry
#: about the error of one scramble of N/2 rows — half the design size, for the
#: eight replicates the intervals need. More scrambles give the jackknife more
#: degrees of freedom and so a narrower t quantile, fewer give each scramble
#: more rows. ``python -m validation run sobol-coverage sobol-blocking`` is the
#: coverage study behind this value and behind ``_SOBOL_SAMPLE_SIZES``: it
#: reruns the interval over many designs of functions whose indices are known
#: and reports how often each interval held its index.
_SOBOL_BLOCKS: int = 8

#: SOBOL sample sizes a run accepts. The smallest is the size at which an index
#: already carries about the error of one undivided scramble of half it, which is
#: the price the eight scrambles cost; below that the indices are too coarse to
#: rank the inputs by. ``python -m validation run sobol-coverage sobol-blocking``
#: measures both the blocking price and how often the intervals hold their index
#: at these sizes.
_SOBOL_SAMPLE_SIZES: tuple[int, ...] = (1024, 2048, 4096)


def _check_design_size(n_base: int, n_blocks: int) -> None:
    """Raise unless *n_base* is *n_blocks* times a power of two of at least 2."""
    n_base, n_blocks = operator.index(n_base), operator.index(n_blocks)
    if n_blocks < 1:
        raise ValueError(f'A design needs at least one block; {n_blocks} was given.')
    per_block = n_base // n_blocks
    if n_base != per_block * n_blocks or per_block < 2 or per_block & (per_block - 1):
        raise ValueError(
            f'The sample size must be {n_blocks} times a power of two, at least {2 * n_blocks}: '
            f'{2 * n_blocks}, {4 * n_blocks}, {8 * n_blocks} and so on.'
        )


def sobol_design(
    n_base: int, n_inputs: int, n_blocks: int, seed: int | np.random.SeedSequence | None = None
) -> tuple[np.ndarray, np.ndarray]:
    """Sobol' matrices ``A`` and ``B`` made of independently scrambled blocks.

    Block *j* occupies rows ``j·n`` to ``(j + 1)·n − 1`` of both matrices, with
    ``n = n_base // n_blocks``. Each block is the first ``n`` points of its own
    scrambled ``2·n_inputs``-dimensional Sobol' sequence, split by columns into
    ``A`` and ``B``: splitting one sequence by columns keeps ``A`` and ``B``
    independent, as the index estimators require, and the independent scrambles
    make the blocks independent replicates of one design, whose spread
    :func:`sobol_indices_with_ci` turns into an error estimate.

    Parameters
    ----------
    n_base : int
        Rows per matrix; *n_blocks* times a power of two of at least 2, so
        every block is a balanced Sobol' point set.
    n_inputs : int
        Dimensions, i.e. inputs being varied.
    n_blocks : int
        Independent scrambles.
    seed : int, SeedSequence or None
        Root of the scrambles; each block draws from its own spawned child.
        A passed ``SeedSequence`` is spawned from, so passing the same object
        again gives new scrambles. ``None`` is nondeterministic.

    Returns
    -------
    tuple of np.ndarray
        Matrices ``A`` and ``B``, each ``(n_base, n_inputs)``.

    Raises
    ------
    ValueError
        If *n_base* is not *n_blocks* times a power of two of at least 2.
    """
    _check_design_size(n_base, n_blocks)
    per_block = n_base // n_blocks
    root = seed if isinstance(seed, np.random.SeedSequence) else np.random.SeedSequence(seed)
    # qmc.Sobol spawns from the generator's SeedSequence, which changes it, so
    # every block gets a fresh child and a fresh generator, each used once.
    points = np.vstack(
        [
            qmc.Sobol(d=2 * n_inputs, scramble=True, rng=np.random.default_rng(child)).random(per_block)
            for child in root.spawn(n_blocks)
        ]
    )
    return points[:, :n_inputs], points[:, n_inputs:]


def sobol_indices_from_outputs(
    f_a: np.ndarray, f_b: np.ndarray, f_ab: list[np.ndarray]
) -> tuple[np.ndarray, np.ndarray]:
    """First-order and total-order Sobol' indices from evaluated matrices.

    ``f_ab[i]`` holds the outputs for ``A`` with column *i* taken from ``B``.
    First order uses the Saltelli estimator and total order the Jansen one.

    The outputs are centred on the mean of ``A`` and ``B`` first. Neither
    estimator's expectation changes with a constant shift, but the Saltelli
    one's scatter grows with the square of the outputs' mean: log10(Ka) sits
    near 8 with a spread of a few tenths, and uncentred it would bury the first
    order indices in noise.

    Returns
    -------
    tuple of np.ndarray
        ``(S1, S_total)``, one entry per input.
    """
    centre = float(np.mean(np.concatenate([f_a, f_b])))
    f_a = np.asarray(f_a, dtype=float) - centre
    f_b = np.asarray(f_b, dtype=float) - centre
    f_ab = [np.asarray(ab, dtype=float) - centre for ab in f_ab]
    variance = float(np.var(np.concatenate([f_a, f_b])))
    if variance <= 0:
        zeros = np.zeros(len(f_ab))
        return zeros, zeros
    s1 = np.array([float(np.mean(f_b * (ab - f_a))) / variance for ab in f_ab])
    st = np.array([float(np.mean((f_a - ab) ** 2)) / (2 * variance) for ab in f_ab])
    return s1, st


def sobol_indices_with_ci(
    f_a: np.ndarray, f_b: np.ndarray, f_ab: list[np.ndarray], n_blocks: int, level: float = 0.95
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Sobol' indices with t-intervals from a delete-one-block jackknife.

    The outputs follow the row order of :func:`sobol_design`, block by block.
    A row whose output is not finite in ``A``, ``B`` or any ``AB_i`` is left
    out everywhere, since the estimators pair rows across the matrices. The
    indices come from :func:`sobol_indices_from_outputs` on every usable row
    pooled. Of the ``B`` blocks that keep at least one usable row, each is left
    out in turn and the indices recomputed; their spread gives the standard
    error ``SE = sqrt((B − 1)/B · Σ_j (θ_(j) − mean θ_(·))²)``, and the interval
    is the estimate ± t(B − 1, (1 + level)/2) · SE.

    The blocks are independent scrambles, so the jackknife sees independent
    replicates of the design; the rows inside a scrambled block are not
    independent draws and cannot stand in for them. The interval covers the
    Monte Carlo sampling error of one index at a time, not errors in the input
    distributions or in the model. It is symmetric and not clipped to 0 … 1.

    Parameters
    ----------
    f_a, f_b : np.ndarray
        Outputs for ``A`` and ``B``, one per design row.
    f_ab : list[np.ndarray]
        ``f_ab[i]`` holds the outputs for ``A`` with column *i* taken from ``B``.
    n_blocks : int
        Scrambles the rows are split into, in equal consecutive runs.
    level : float
        Coverage the interval is built for.

    Returns
    -------
    tuple of np.ndarray
        ``(S1, S1 interval, S_total, S_total interval)``; the indices have
        shape ``(n_inputs,)`` and the intervals ``(n_inputs, 2)``, low then
        high. The intervals are ``NaN`` when fewer than three blocks or fewer
        than two rows are usable, and the indices too when fewer than two rows
        are.

    Raises
    ------
    ValueError
        If the row count is not a multiple of *n_blocks*.
    """
    f_a = np.asarray(f_a, dtype=float)
    f_b = np.asarray(f_b, dtype=float)
    f_ab = np.asarray(f_ab, dtype=float)
    n_inputs = len(f_ab)
    if n_blocks < 1 or f_a.size % n_blocks:
        raise ValueError(f'{f_a.size} design rows cannot be split into {n_blocks} equal blocks.')
    usable = np.isfinite(f_a) & np.isfinite(f_b) & np.all(np.isfinite(f_ab), axis=0)
    no_interval = np.full((n_inputs, 2), np.nan)
    if int(usable.sum()) < 2:
        return np.full(n_inputs, np.nan), no_interval, np.full(n_inputs, np.nan), no_interval.copy()

    def indices(rows: np.ndarray) -> np.ndarray:
        return np.concatenate(sobol_indices_from_outputs(f_a[rows], f_b[rows], f_ab[:, rows]))

    estimate = indices(usable)
    block = np.arange(f_a.size) // (f_a.size // n_blocks)
    kept = np.unique(block[usable])
    n_kept = kept.size
    if n_kept < 3:
        return estimate[:n_inputs], no_interval, estimate[n_inputs:], no_interval.copy()
    leave_one_out = np.array([indices(usable & (block != j)) for j in kept])
    se = np.sqrt((n_kept - 1) / n_kept * np.sum((leave_one_out - leave_one_out.mean(axis=0)) ** 2, axis=0))
    half = student_t.ppf((1 + level) / 2, n_kept - 1) * se
    interval = np.column_stack([estimate - half, estimate + half])
    return estimate[:n_inputs], interval[:n_inputs], estimate[n_inputs:], interval[n_inputs:]


#: Below this many perturbations, starting worker processes costs more than it
#: saves — every worker re-imports numpy and scipy before it can fit anything.
_PARALLEL_MIN_JOBS = 8

#: How long the perturbation loop waits for a result before it asks again
#: whether the user has stopped the run. Short enough that a stop is acted on
#: while the button is still under the pointer, long enough that the wait does
#: not spin.
_CANCEL_POLL_SECONDS = 0.05

#: Perturbations handed to the pool at once, per worker. A pool holds about one
#: call per worker in its own queue, and those are the fits a stop cannot take
#: back, so the batch keeps only a couple of rounds in flight and holds the rest
#: here, where stopping drops them without a worker ever seeing them.
_IN_FLIGHT_PER_WORKER = 2

#: Cap each worker's own internal threading, so N processes do not each start M
#: threads and fight over the machine. A linear-algebra library reads these when
#: it is loaded, so they only bite when a worker inherits them before it imports
#: numpy: see :func:`_thread_capped_children`.
_THREAD_LIMIT_VARS = (
    'OMP_NUM_THREADS',
    'OPENBLAS_NUM_THREADS',
    'MKL_NUM_THREADS',
    'NUMEXPR_NUM_THREADS',
    'VECLIB_MAXIMUM_THREADS',
)


def default_worker_count() -> int:
    """Worker processes to use when the user has not chosen a number.

    One core is left free so the interface stays responsive while a run is
    going. ``process_cpu_count`` reports the cores this process may actually
    use, which is what a container or an affinity mask allows rather than what
    the machine physically has. A single-core machine gives 1, meaning the work
    runs in this process.
    """
    counter = getattr(os, 'process_cpu_count', None)
    total = counter() if counter is not None else os.cpu_count()
    return max(1, (total or 1) - 1)


@contextmanager
def _thread_capped_children() -> Iterator[None]:
    """Hold the thread-cap variables in this process while worker processes start.

    A linear-algebra library reads them when it is loaded, which in a worker
    happens before any code of ours runs there, so the cap has to be in the
    environment the worker inherits. Only the variables that are not already set
    are touched, and this process's environment is put back as it was, so a run
    leaves the application exactly as it found it.
    """
    previous = {name: os.environ.get(name) for name in _THREAD_LIMIT_VARS}
    os.environ.update({name: '1' for name, value in previous.items() if value is None})
    try:
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)


#: Everything the jobs of a batch share, in the worker process that runs them.
#: A worker cannot be handed the batch with every job, so the pool's initializer
#: leaves it here for :func:`_worker_fit` to pick up. Only a worker process fills
#: it; this process keeps a batch's state in a local of :func:`_evaluate_batch`,
#: so two runs going at once never see each other's data.
_WORKER_STATE: dict = {}


def _init_worker(ms, assay_cls, x_base, base_conditions, fit_config) -> None:
    """Hand a worker process the data every job in the batch needs."""
    _WORKER_STATE.update(
        ms=ms,
        assay_cls=assay_cls,
        x_base=x_base,
        base_conditions=base_conditions,
        fit_config=fit_config,
    )


def _run_job(state: dict, job):
    """Run one perturbation with the batch state *state* → ``(index, result)``."""
    index, offsets = job
    return index, _fit_perturbed(
        state['ms'],
        state['assay_cls'],
        state['x_base'],
        state['base_conditions'],
        offsets,
        state['fit_config'],
    )


def _worker_fit(job):
    """Run one perturbation in the worker process that picked the job up."""
    return _run_job(_WORKER_STATE, job)


#: Shown when a perturbation stops the run rather than reporting no fit: the fits
#: themselves already turn a failure into a sample without a fit, so whatever is
#: left is not something the analysis can work around.
_BATCH_FAILURE_MESSAGE = (
    'The analysis stopped because one of the re-fits of your data could not be completed. '
    'Run it again, and if it stops again choose a smaller sample size or vary fewer inputs.'
)


class SensitivityRunError(RuntimeError):
    """A perturbation stopped the run. Its message is written for the user to read."""


def _evaluate_batch(
    ms,
    assay_cls,
    x_base,
    base_conditions,
    fit_config,
    offsets_list,
    *,
    max_workers,
    on_result,
    should_cancel,
):
    """Fit a batch of perturbations, in parallel when that is worthwhile.

    Results come back in the order of *offsets_list* however the work was
    scheduled, so a Sobol' row pairing or a heatmap cell index stays valid. A
    perturbation has one fit, so the answer does not depend on which worker ran
    it.

    ``spawn`` is used on every platform. Workers start from a Qt application
    that already runs threads, and forking such a process is unsafe, so the
    platform default is not inherited.

    Stopping is answered within seconds at any point of the batch, including
    while the pool is still starting: only ``_IN_FLIGHT_PER_WORKER`` rounds of
    fits are handed to the pool at a time, and the wait for a result times out
    every ``_CANCEL_POLL_SECONDS`` so *should_cancel* is asked again. What is
    left when a stop arrives is therefore a handful of fits mid-solve rather
    than the whole batch.

    Raises
    ------
    SensitivityRunError
        If a job fails in a way the per-fit guard does not cover. The queued
        jobs are dropped and the pool shut down before the error is raised, so
        the caller hears about it instead of waiting out the rest of the batch.
    """
    results: list = [None] * len(offsets_list)
    jobs = list(enumerate(offsets_list))
    state = {
        'ms': ms,
        'assay_cls': assay_cls,
        'x_base': x_base,
        'base_conditions': base_conditions,
        'fit_config': fit_config,
    }

    if max_workers <= 1 or len(jobs) < _PARALLEL_MIN_JOBS:
        for job in jobs:
            if should_cancel():
                break
            # A failed perturbation says the same thing whichever branch ran
            # the work: what the user is told cannot depend on how many cores
            # the run happened to use or how many cells the heatmap has.
            try:
                index, value = _run_job(state, job)
            except Exception as exc:
                raise SensitivityRunError(_BATCH_FAILURE_MESSAGE) from exc
            results[index] = value
            on_result(value)
        return results

    queue = iter(jobs)
    with _thread_capped_children():
        executor = ProcessPoolExecutor(
            max_workers=max_workers,
            mp_context=mp.get_context('spawn'),
            initializer=_init_worker,
            initargs=(ms, assay_cls, x_base, base_conditions, fit_config),
        )
        # Submitting inside the cap: the pool starts a process per job until it
        # is full, so the first round starts every worker under the cap.
        try:
            pending = {executor.submit(_worker_fit, job) for job in islice(queue, max_workers * _IN_FLIGHT_PER_WORKER)}
        except BaseException:
            executor.shutdown(cancel_futures=True)
            raise
    try:
        while pending:
            if should_cancel():
                break
            finished, pending = wait(pending, timeout=_CANCEL_POLL_SECONDS, return_when=FIRST_COMPLETED)
            for future in finished:
                try:
                    index, value = future.result()
                except Exception as exc:
                    raise SensitivityRunError(_BATCH_FAILURE_MESSAGE) from exc
                results[index] = value
                on_result(value)
            pending.update(executor.submit(_worker_fit, job) for job in islice(queue, len(finished)))
    finally:
        executor.shutdown(cancel_futures=True)
    return results


def _perturbed_ms(ms, x_base: np.ndarray, offsets: dict) -> MeasurementSet:
    """Copy of *ms* with the titrant grid rescaled, replica activity preserved.

    The signals are untouched, and so is which replicates are active: the
    perturbation moves the inputs, not the measurements or the set of them the
    baseline fit used.
    """
    scaled = x_base * (1 + offsets.get(TITRANT, 0.0))
    out = MeasurementSet(
        concentrations=scaled,
        signals=ms.signals,
        replica_ids=ms.replica_ids,
        metadata=dict(ms.metadata),
    )
    for replica_id in ms.replica_ids:
        out.set_active(replica_id, ms.is_active(replica_id))
    return out


def _fit_perturbed(ms, assay_cls, x_base, base_conditions, offsets, fit_config):
    """Fit of one perturbation → ``({parameter key: value}, R²)``.

    The averaged signal of the active replicates is projected onto the
    perturbed model and its binding constants searched over the Ka box in
    force, which is how the headline fit of these data is made; every parameter
    comes back in its canonical registry unit, the unit ``FitResult.parameters``
    carries, and the R² is measured against that averaged signal.

    ``None`` when the perturbed inputs leave the model with no solution
    anywhere in the Ka box: that is one sample without a fit, which the caller
    records as NaN, and the other thousands of samples stand. Quality is not
    judged here — every fit is reported whatever its R².
    """
    perturbed = _perturbed_ms(ms, x_base, offsets)
    conditions = {k: (v * (1 + offsets[k]) if k in offsets else v) for k, v in base_conditions.items()}
    assay = perturbed.to_assay(assay_cls, conditions=conditions, use_average=True)
    projection = Projection(assay, _resolve_bounds(assay, fit_config.custom_bounds))
    try:
        fit = projection.fit()
    except FitRefused:
        return None
    params = projection.params(fit)
    _, r_squared = calculate_fit_metrics(assay.y_data.magnitude, assay.forward_model(params).magnitude)
    return dict(zip(assay.parameter_keys, params.tolist())), float(r_squared)


def run_sensitivity(
    ms,
    assay_cls,
    base_conditions: dict,
    fit_config: FitConfig,
    sens_config: SensitivityConfig,
    *,
    progress: Optional[Callable[[int, int], None]] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
    max_workers: Optional[int] = None,
    input_labels: Optional[dict[str, str]] = None,
) -> SensitivityResult:
    """Run a Ka input-sensitivity analysis.

    Parameters
    ----------
    ms : MeasurementSet
        Source data. The baseline fit uses its active replicates; the
        replicates that fit used (:func:`fit_replica_ids`) are then fixed for
        the rest of the run, so every perturbation fits and is scored on exactly
        that set. Each perturbation refits a copy whose titrant grid carries the
        sampled offset.
    assay_cls : type[BaseAssay]
        Concrete assay class to build each perturbed fit with.
    base_conditions : dict
        Baseline assay conditions (Quantity values in base units).
    fit_config : FitConfig
        Per-fit configuration: it decides the parameter bounds every fit of the
        run is made under and how the baseline fit treats the replicates. Its
        input uncertainties are not used here — this run samples the ones in
        *sens_config*, and every fit it makes holds the inputs at their sampled
        values.
    sens_config : SensitivityConfig
        What to perturb and how.
    progress : callable, optional
        Called ``progress(done, total)`` after every fit (baseline included).
    should_cancel : callable, optional
        Polled before the baseline fit, inside it and in the perturbation loop;
        on ``True`` the run stops early and returns a partial result.
    max_workers : int, optional
        Worker processes to fit with. ``1`` keeps everything in this process;
        omitted uses :func:`default_worker_count`. Results are the same either
        way, since a perturbation has one fit.
    input_labels : dict[str, str], optional
        Display label per input key, as the interface writes it. Used only to
        name an input in a message shown to the user.

    Returns
    -------
    SensitivityResult
        Populated per ``sens_config.mode``.

    Raises
    ------
    ValueError
        For an invalid config (a SOBOL ``n_samples`` outside
        ``_SOBOL_SAMPLE_SIZES``, no input set to vary, negative percent, a range
        reaching below zero, unknown key, HEATMAP with ``x_key == y_key``, a
        non-perturbable axis key or an axis reaching zero), for an assay with no
        association constant (DYE_ALONE), and for whatever the baseline fit
        itself refuses — bounds it cannot fit under, or a model the engine
        cannot project. Its message is written for the user.
    FitCancelled
        If the run is cancelled before its baseline fit finishes, so there is no
        reference fit to report anything against.
    SensitivityRunError
        If a perturbation fails in a way the per-fit guard does not cover. Its
        message is written for the user and can be shown as it stands.
    """
    x_base = np.asarray(ms.concentrations)
    workers = default_worker_count() if max_workers is None else max(1, int(max_workers))

    # Assay type / Ka keys come from an instance that is built, never fitted.
    probe_assay = ms.to_assay(assay_cls, conditions=base_conditions, use_average=True)
    assay_type: AssayType = probe_assay.assay_type
    metadata = ASSAY_REGISTRY[assay_type]
    ka_keys = metadata.log_scale_keys
    if not ka_keys:
        raise FitRefused('This assay has no association constant to analyse, so sensitivity analysis does not apply.')

    valid_keys = {k for k, _ in perturbable_inputs(base_conditions)}

    # --- Validate the config before doing any real work ------------------
    size = sens_config.n_samples
    whole = isinstance(size, (int, np.integer)) and not isinstance(size, bool)
    if sens_config.mode is SensitivityMode.SOBOL and not (whole and size in _SOBOL_SAMPLE_SIZES):
        *smaller, largest = _SOBOL_SAMPLE_SIZES
        raise FitRefused(
            f'The number of samples must be {", ".join(map(str, smaller))} or {largest}; '
            f'{sens_config.n_samples} was chosen.'
        )
    for key, spec in sens_config.input_specs.items():
        if key not in valid_keys:
            raise FitRefused(
                'An uncertainty is set for an input this assay does not have, so the analysis cannot run. '
                'Set uncertainties only for the inputs this assay lists.'
            )
        name = input_name(key, input_labels)
        if spec.kind is SpecKind.SIGMA and spec.sigma < 0:
            raise FitRefused(f'The uncertainty of {name} must not be negative.')
        if spec.kind is SpecKind.INTERVAL and spec.hi < spec.lo:
            raise FitRefused(f'The upper bound for {name} must not be below its lower bound.')
        # Surfaces a titrant given an absolute spec, which has no nominal value.
        _to_fraction(0.0, spec.relative, nominal_value(key, base_conditions), name)
        if spec.kind is SpecKind.INTERVAL and spec_bounds(spec, nominal_value(key, base_conditions), name)[0] < -1.0:
            raise FitRefused(
                f'The range for {name} reaches below zero, and a concentration or binding constant cannot be '
                f'negative. Raise its lower end to {"-100 %" if spec.relative else "0"} or more.'
            )
    if not any(spec.varies for spec in sens_config.input_specs.values()):
        raise FitRefused('No input is set to vary — give at least one input a non-zero uncertainty.')

    if sens_config.mode is SensitivityMode.HEATMAP:
        for axis, axis_key in (('X', sens_config.x_key), ('Y', sens_config.y_key)):
            if axis_key not in valid_keys:
                raise FitRefused(
                    f'The {axis} axis of the heatmap is set to an input this assay does not have, so the analysis '
                    'cannot run. Pick one of the inputs this assay lists.'
                )
        if sens_config.x_key == sens_config.y_key:
            raise FitRefused('Heatmap X and Y axes must be two different inputs.')
        for axis_key in (sens_config.x_key, sens_config.y_key):
            spec = sens_config.input_specs.get(axis_key)
            name = input_name(axis_key, input_labels)
            if spec is not None and axis_reaches_zero(spec, nominal_value(axis_key, base_conditions), name):
                raise FitRefused(
                    f'The heatmap axis for {name} reaches zero or below, and a concentration or binding constant '
                    'must stay positive. Use a σ below 50 % of the set value, or a range whose lower end is above zero.'
                )
        if sens_config.n_steps < 1:
            raise FitRefused('Heatmap grid resolution must be at least 1.')

    # --- Baseline (unperturbed) fit --------------------------------------
    total = estimated_fit_count(sens_config) + 1  # +1 for the baseline
    done = 0

    # One root seed drives the whole run, drawn here when none was configured, so
    # every run can be repeated by feeding its `seed_used` back in. It is drawn
    # within MAX_SEED, the range the interface's Fixed seed box accepts, so a
    # reported seed can always be entered there.
    seed_used = int(np.random.SeedSequence().generate_state(1)[0] % (MAX_SEED + 1))
    seed_used = seed_used if sens_config.seed is None else sens_config.seed

    def _tally(counters: dict):
        """Progress callback that counts a finished fit however it was scheduled."""

        def record(value) -> None:
            counters['total'] += 1
            counters['done'] += 1
            if value is not None:
                counters['success'] += 1
            if progress is not None:
                progress(counters['done'], total)

        return record

    def _cancelled() -> bool:
        return should_cancel is not None and should_cancel()

    if _cancelled():
        raise FitCancelled('The sensitivity analysis was stopped before its first fit.')
    # The baseline is the fit at the inputs as entered: the specs are what this
    # run samples, so letting the baseline fit move the inputs as well would
    # report the spread of the samples around a fit that already absorbed them.
    baseline_result = fit_measurement_set(
        ms, assay_cls, base_conditions, replace(fit_config, input_specs={}), should_cancel=should_cancel
    )
    done += 1
    if progress is not None:
        progress(done, total)

    # Every later fit uses the replicates the baseline used, scored against
    # their average: a replicate the fit left out never enters a sample, and
    # every sample describes the same data. The baseline is what a sample with
    # no input offset gets — the same engine fits both — so the estimate and the
    # spread around it come from one fitting method.
    ms = ms.with_active(fit_replica_ids(baseline_result))
    probe_assay = ms.to_assay(assay_cls, conditions=base_conditions, use_average=True)
    baseline_ka = {k: baseline_result.parameters[k].to('1/M').magnitude for k in ka_keys}
    degenerate_keys = baseline_result.degenerate_keys

    def _evaluate(offsets_list: list[dict]) -> tuple[dict[str, np.ndarray], np.ndarray, dict]:
        """Fit every perturbation → (value per parameter key, R²), NaN where no fit was produced."""
        counters = {'total': 0, 'success': 0, 'done': done}
        values = _evaluate_batch(
            ms,
            assay_cls,
            x_base,
            base_conditions,
            fit_config,
            offsets_list,
            max_workers=workers,
            on_result=_tally(counters),
            should_cancel=_cancelled,
        )
        params = {
            key: np.array([np.nan if v is None else v[0][key] for v in values]) for key in probe_assay.parameter_keys
        }
        r2 = np.array([np.nan if v is None else v[1] for v in values])
        return params, r2, counters

    # --- Dispatch on mode ------------------------------------------------
    if sens_config.mode is SensitivityMode.SOBOL:
        active_keys = [key for key, spec in sens_config.input_specs.items() if spec.varies]
        n_base, n_inputs = sens_config.n_samples, len(active_keys)
        a_points, b_points = sobol_design(n_base, n_inputs, _SOBOL_BLOCKS, seed_used)
        matrices = [a_points, b_points]
        for column in range(n_inputs):
            mixed = a_points.copy()
            mixed[:, column] = b_points[:, column]
            matrices.append(mixed)
        # One batch for every matrix, in the order A, B, AB_1 … AB_k. Each input
        # is mapped through its inverse CDF one column at a time: the same
        # numbers as row by row, and fast enough not to hold the run up before
        # the first fit is dispatched.
        quantiles = np.clip(np.vstack(matrices), _QUANTILE_EPS, 1.0 - _QUANTILE_EPS)
        columns = [
            spec_fraction(
                sens_config.input_specs[key],
                nominal_value(key, base_conditions),
                input_name(key, input_labels),
                quantiles[:, column],
            ).tolist()
            for column, key in enumerate(active_keys)
        ]
        offsets_list = [dict(zip(active_keys, row)) for row in zip(*columns)]
        params, r2, counters = _evaluate(offsets_list)
        n_samples = 2 * n_base  # the A and B rows

        sobol_s1: dict[str, dict[str, float]] = {}
        sobol_st: dict[str, dict[str, float]] = {}
        sobol_s1_ci: dict[str, dict[str, tuple[float, float]]] = {}
        sobol_st_ci: dict[str, dict[str, tuple[float, float]]] = {}
        rows_left_out: dict[str, int] = {}
        for key in ka_keys:
            # The indices split the variance of log10(Ka): Ka spans orders of
            # magnitude, and on the raw scale one far-off fit would own almost
            # all of the variance and push the indices far outside 0 to 1. A
            # row without a fit in every matrix is left out of the indices.
            by_matrix = np.log10(params[key]).reshape(len(matrices), n_base)
            s1, s1_ci, st, st_ci = sobol_indices_with_ci(by_matrix[0], by_matrix[1], by_matrix[2:], _SOBOL_BLOCKS)
            sobol_s1[key] = {k: float(v) for k, v in zip(active_keys, s1)}
            sobol_st[key] = {k: float(v) for k, v in zip(active_keys, st)}
            sobol_s1_ci[key] = {k: (float(lo), float(hi)) for k, (lo, hi) in zip(active_keys, s1_ci)}
            sobol_st_ci[key] = {k: (float(lo), float(hi)) for k, (lo, hi) in zip(active_keys, st_ci)}
            rows_left_out[key] = int(np.sum(~np.all(np.isfinite(by_matrix), axis=0)))

        return SensitivityResult(
            mode=sens_config.mode,
            assay_type=assay_type.name,
            ka_keys=ka_keys,
            baseline_ka=baseline_ka,
            x_offsets_pct=None,
            y_offsets_pct=None,
            ka_grid=None,
            sobol_s1=sobol_s1,
            sobol_st=sobol_st,
            n_success=counters['success'],
            n_total=counters['total'],
            config=sens_config,
            seed_used=seed_used,
            sobol_s1_ci=sobol_s1_ci,
            sobol_st_ci=sobol_st_ci,
            sample_offsets_pct={
                k: 100.0 * np.array([offsets[k] for offsets in offsets_list[:n_samples]]) for k in active_keys
            },
            sample_ka={key: params[key][:n_samples] for key in ka_keys},
            sample_r2=r2[:n_samples],
            baseline_fit=baseline_result,
            sample_params={key: values[:n_samples] for key, values in params.items()},
            degenerate_keys=degenerate_keys,
            sobol_rows_left_out=rows_left_out,
            stopped=counters['total'] < len(offsets_list),
        )

    # --- HEATMAP ---------------------------------------------------------
    x_lo, x_hi = _axis_bounds(
        sens_config, sens_config.x_key, base_conditions, input_name(sens_config.x_key, input_labels)
    )
    y_lo, y_hi = _axis_bounds(
        sens_config, sens_config.y_key, base_conditions, input_name(sens_config.y_key, input_labels)
    )
    x_offsets = np.linspace(x_lo, x_hi, sens_config.n_steps)
    y_offsets = np.linspace(y_lo, y_hi, sens_config.n_steps)
    cells = [(iy, ix) for iy in range(len(y_offsets)) for ix in range(len(x_offsets))]
    offsets_list = [
        {sens_config.x_key: float(x_offsets[ix]), sens_config.y_key: float(y_offsets[iy])} for iy, ix in cells
    ]
    params, r2, counters = _evaluate(offsets_list)
    shape = (len(y_offsets), len(x_offsets))
    r2_grid = r2.reshape(shape)

    return SensitivityResult(
        mode=sens_config.mode,
        assay_type=assay_type.name,
        ka_keys=ka_keys,
        baseline_ka=baseline_ka,
        x_offsets_pct=x_offsets * 100.0,
        y_offsets_pct=y_offsets * 100.0,
        ka_grid={key: params[key].reshape(shape) for key in ka_keys},
        n_success=counters['success'],
        n_total=counters['total'],
        config=sens_config,
        seed_used=seed_used,
        r2_grid=r2_grid,
        baseline_fit=baseline_result,
        degenerate_keys=degenerate_keys,
        stopped=counters['total'] < len(offsets_list),
    )
