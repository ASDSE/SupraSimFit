"""Ka input-sensitivity analysis (pure compute layer, no Qt).

A fitted association constant (Ka) is only as trustworthy as the *inputs* fed
into the model — the titrant concentration vector, the fixed conditions
(``h0`` / ``d0`` / …) and any non-fitted binding constant (``Ka_dye``). Each
carries measurement error, and the fit silently compensates by shifting the
fitted Ka. This module re-runs the fit many times with those inputs perturbed
according to the stated error sources and reports the resulting spread of Ka,
and which of the sources that spread comes from.

The error sources are the ones stated for the fit
(:attr:`~core.pipeline.fit_pipeline.FitConfig.errors`, an
:class:`~core.pipeline.inputs.ErrorModel`): the error each input has alone, the
errors several inputs share, and the random error of each titrant addition.
The analysis is a propagation of those stated distributions (GUM Supplement 1,
JCGM 101:2008): every sample is a fit at inputs held at their sampled values,
each sample counts equally however well it fits the data, and the sample with
no offset is the fit at the inputs as entered. The input-aware interval of a
fit (:mod:`core.pipeline.input_aware`) also weighs what the data say about the
inputs — an input value the titration rules out costs it — so the two answer
different questions and can differ, the spread here being the wider where the
data inform an input. That interval takes in a stated random error of each
addition through a widened cut-off (:mod:`core.pipeline.inflation`); here it is
sampled like every other source, so that it can be ranked against them.

Two analysis modes:

- **SOBOL** — every source sampled together on a Saltelli design built from
  independently scrambled Sobol' blocks → the Ka distribution, first- and
  total-order Sobol' indices of log₁₀(Ka) per source with 95 % intervals for
  their Monte Carlo sampling error, each sample's source offsets, Ka and R²,
  and the absolute variance budget (:class:`Budget`, :func:`what_if`) with the
  elasticity of Ka to every input, and the homogeneity identity those
  elasticities obey (:func:`homogeneity_sum`) checked on every run.
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

import math
import multiprocessing as mp
import operator
import os
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from enum import Enum
from itertools import islice
from typing import Callable, Iterator, Mapping, Optional

import numpy as np
from scipy.stats import qmc, truncnorm
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
    ADDITIONS,
    TITRANT,
    TITRANT_STOCK,
    ErrorModel,
    InputSpec,
    SpecKind,
    _to_fraction,
    axis_reaches_zero,
    input_name,
    nominal_value,
    perturb_titrant,
    perturbable_inputs,
    source_name,
    spec_bounds,
    spec_fraction,
    validate,
)
from core.pipeline.varpro import (
    _LOG_KA_XTOL,
    _SEARCH_PER_DECADE,
    FitCancelled,
    FitRefused,
    Projection,
    _ka_grid,
    on_ka_bound,
)


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
        SOBOL only — base sample count ``N``; the run fits ``N × (g + 2)``
        perturbations for ``g`` reported sources. ``N`` is split evenly over
        ``_SOBOL_BLOCKS`` independent scrambles and must be one of
        ``_SOBOL_SAMPLE_SIZES``.
    errors : ErrorModel
        The stated error sources. SOBOL samples every one of them; HEATMAP
        reads the own uncertainty (``errors.specs``) of its two axis inputs. An
        input with no spec, or one that does not vary, has no error of its own.
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
    errors: ErrorModel
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
        SOBOL only — ka_key → source key → first-order / total-order index of
        the variance of log₁₀(Ka). An input's own error goes by the input's
        key, a shared source by :func:`~core.pipeline.inputs.shared_key` of its
        name, and the random errors of the additions, all of them as one
        item, by ``ADDITIONS``.
    sobol_s1_ci, sobol_st_ci : dict[str, dict[str, tuple[float, float]]] or None
        SOBOL only — ka_key → source key → ``(low, high)`` 95 % t-interval of
        the matching index: the estimate ± t(B − 1, 0.975) × its standard
        error from the delete-one-block jackknife over the ``B`` independent
        scrambles that hold a usable sample (see
        :func:`sobol_indices_with_ci`). It covers the Monte Carlo sampling
        error of that one index only, not errors in the stated input
        uncertainties or in the model; it is not clipped to 0 … 1, and it is
        ``NaN`` when fewer than three scrambles hold a usable sample.
    sample_offsets_pct : dict[str, np.ndarray] or None
        SOBOL only — source key → the source's offset in percent for each ``A``
        sample, then each ``B`` sample. ``ADDITIONS`` has no entry: it is one
        offset per titration point, not one per sample.
    sample_ka : dict[str, np.ndarray] or None
        SOBOL only — ka_key → best Ka (1/M) per sample, index-aligned with
        ``sample_offsets_pct``; ``NaN`` only where no fit could be produced.
    sample_usable : dict[str, np.ndarray] or None
        SOBOL only — ka_key → whether each sample belongs to a design row the
        indices and the budget were built from, aligned with ``sample_ka``: the
        rows whose ``A``, ``B`` and every mixed sample gave a finite
        log₁₀(Ka). The ``A`` and the ``B`` sample of one row stand or fall
        together, so the mask repeats over the two halves. It is what
        :func:`what_if` re-weights, so its answer and the budget it is compared
        against describe the same rows.
    sample_r2 : np.ndarray or None
        SOBOL only — R² of each sample's best fit, aligned the same way:
        the unweighted R² against the averaged signal that a fit reports as its
        quality.
    sample_profile_r2 : np.ndarray or None
        SOBOL only — each sample's place on the Identifiability tab's axis,
        ``1 - S_w / SS_tot,w`` of its best fit: the objective that fit
        minimised, with every titration point counted by the weight of the
        baseline's noise law, which is the scale the Ka profiles are drawn on.
        A sample above the profile there has moved the inputs to something
        that fits better at that Ka than the entered ones do. ``None`` for a
        heatmap run, like ``sample_r2``.
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
    baseline_on_bound : dict[str, bool]
        Free binding constant → whether the baseline fit's estimate rests on a
        bound of its box (:func:`~core.pipeline.varpro.on_ka_bound`) rather than
        inside it. There the data do not limit that constant at the inputs as
        entered: every elasticity of it is zero and the spread the analysis
        reports is not the inputs' own. A constant pinned to one value has no
        entry.
    n_on_bound : dict[str, int]
        Free binding constant → how many of the run's perturbed fits put it on a
        bound: the samples of every matrix of the SOBOL design in the finished
        sample blocks, or every cell of a heatmap grid. The elasticity refits
        and the fits that produced no fit at all are not counted
        (``n_total - n_success`` counts the latter). Such a fit is the edge of
        the box rather than a value the data chose, and it sits decades from
        the rest, so a share of them inflates the spread and the budget.
    stopped : bool
        Whether the run was stopped before every planned perturbed fit
        finished. The fits it never reached are ``NaN`` like the ones that
        could not be produced, and ``n_total`` counts only the fits that
        finished. A SOBOL run fits its design sample block by sample block,
        every matrix of a block together, and keeps only the blocks all of
        whose fits finished (``n_blocks_finished``): the samples of the others
        read ``NaN``, so the indices, the budget and the samples all describe
        the same finished blocks.
    n_blocks_finished : int
        SOBOL only — the independent sample blocks (``_SOBOL_BLOCKS`` of them)
        all of whose fits finished; every one of them unless ``stopped``.
    budget : dict[str, Budget] or None
        SOBOL only — ka_key → the absolute variance budget of log₁₀(Ka).
    elasticity : dict[str, dict[str, float]] or None
        SOBOL only — ka_key → input key → ``d ln Ka / d ln input`` at the
        entered inputs, for every perturbable input whether it varies or not:
        a central difference of two refits at ``±_ELASTICITY_STEP``, made
        before the design; ``NaN`` where a refit gave no fit.
    sources : tuple[str, ...]
        SOBOL only — the reported source keys in the order of the design,
        ``ADDITIONS`` last.
    source_inputs : dict[str, tuple[str, ...]]
        SOBOL only — source key → the input keys that source moves.
    n_planned : int
        Perturbed fits the run planned, the elasticity refits included and the
        baseline excluded; ``n_total`` reaches it unless the run was stopped.
    homogeneity : dict[str, float]
        SOBOL only — ka_key → :func:`homogeneity_sum` of that constant's
        elasticities, which the models make exactly ``−1``. ``NaN`` where the
        identity does not apply to the fit (a binding constant pinned to one
        value, or a signal coefficient at a bound other than zero or infinity,
        which a change of the concentration unit would move), where one of the
        elasticity refits gave no fit or was stopped before it ran, and for a
        heatmap run, which makes no elasticity refits.
    withheld : dict[str, str]
        ka_key → why the indices, the budget, the what-if and the elasticities
        of that constant are not to be reported, or ``''`` when they are:
        ``'baseline_on_bound'`` — the fit at the inputs as entered rests on a
        bound of the Ka box; ``'open_interval'`` — its conditional interval is
        open on a side, so the data do not limit the constant there and the
        refits land wherever its flat profile lets them; ``'homogeneity'`` — the
        identity ``homogeneity`` checks misses ``−1`` by more than
        :func:`homogeneity_tolerance`, or one of its refits gave no fit, so the
        refits do not respond smoothly to the inputs. A run stopped before its
        elasticity refits finished gives no reason: it has no finished sample
        block, which ``stopped`` and ``n_blocks_finished`` already say. The
        numbers stay in the result; this says they describe the search, not
        the inputs.
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
    sample_usable: Optional[dict[str, np.ndarray]] = None
    sample_r2: Optional[np.ndarray] = None
    sample_profile_r2: Optional[np.ndarray] = None
    r2_grid: Optional[np.ndarray] = None
    baseline_fit: FitResult | None = None
    sample_params: dict[str, np.ndarray] | None = None
    degenerate_keys: tuple[str, ...] = ()
    sobol_rows_left_out: dict[str, int] | None = None
    baseline_on_bound: dict[str, bool] = field(default_factory=dict)
    n_on_bound: dict[str, int] = field(default_factory=dict)
    stopped: bool = False
    budget: dict[str, Budget] | None = None
    elasticity: dict[str, dict[str, float]] | None = None
    sources: tuple[str, ...] = ()
    source_inputs: dict[str, tuple[str, ...]] = field(default_factory=dict)
    n_planned: int = 0
    n_blocks_finished: int = 0
    homogeneity: dict[str, float] = field(default_factory=dict)
    withheld: dict[str, str] = field(default_factory=dict)


def _reported_sources(errors: ErrorModel) -> tuple[str, ...]:
    """Source keys a SOBOL run reports: every single source, then ``ADDITIONS`` when stated."""
    return (*errors.source_specs(), *((ADDITIONS,) if errors.additions is not None else ()))


def estimated_fit_count(sens_config: SensitivityConfig, n_inputs: int) -> int:
    """Number of perturbed fits a config will run, the baseline excluded.

    Parameters
    ----------
    sens_config : SensitivityConfig
        The configuration to size.
    n_inputs : int
        Perturbable inputs of the assay, ``len(perturbable_inputs(base_conditions))``.

    Returns
    -------
    int
        SOBOL → ``n_samples × (g + 2)`` for ``g`` reported sources, plus the
        ``2 × n_inputs`` refits of the elasticities; HEATMAP → ``n_steps ** 2``.
    """
    if sens_config.mode is SensitivityMode.SOBOL:
        return sens_config.n_samples * (len(_reported_sources(sens_config.errors)) + 2) + 2 * n_inputs
    return sens_config.n_steps**2


#: Model solves above which a run is worth warning about before it starts. One
#: solve — the species of one design, then the bounded linear least squares on
#: them — takes about 0.2 ms for thirty titration points, so this is about two
#: minutes of one core.
LONG_RUN_SOLVES = 700_000


def estimated_model_solves(
    sens_config: SensitivityConfig, fit_config: FitConfig, assay_type: AssayType, n_inputs: int
) -> int:
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
    n_inputs : int
        Perturbable inputs of the assay, as :func:`estimated_fit_count` takes it.

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
    return (estimated_fit_count(sens_config, n_inputs) + 1) * nodes


#: Keeps a quantile off the exact edges, where a truncated normal maps to its bound.
_QUANTILE_EPS = 1e-9


def _axis_bounds(sens_config: 'SensitivityConfig', key: str, base_conditions: dict, name: str) -> tuple[float, float]:
    """Offset range a heatmap axis sweeps, as fractions of nominal."""
    spec = sens_config.errors.specs.get(key)
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

    ``f_ab[i]`` holds the outputs for ``A`` with the columns of reported item
    *i* taken from ``B``: one column for a single source, several for a group,
    for which the same estimators give the group's closed first-order index
    ``Var(E[Y | group]) / Var(Y)`` and its total index.
    First order uses the Saltelli estimator and total order the Jansen one.

    The outputs are centred on the mean of ``A`` and ``B`` first. Neither
    estimator's expectation changes with a constant shift, but the Saltelli
    one's scatter grows with the square of the outputs' mean: log10(Ka) sits
    near 8 with a spread of a few tenths, and uncentred it would bury the first
    order indices in noise.

    Returns
    -------
    tuple of np.ndarray
        ``(S1, S_total)``, one entry per reported item.
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


@dataclass(frozen=True)
class SobolEstimate:
    """Sobol' indices and the absolute variances behind them, each with its jackknife interval.

    ``g`` is the number of reported items. Every interval is ``(low, high)``.

    Attributes
    ----------
    s1, st : np.ndarray, shape (g,)
        First-order and total-order index per item.
    s1_ci, st_ci : np.ndarray, shape (g, 2)
        Their intervals.
    variance : float
        Variance of the output over the usable ``A`` and ``B`` rows.
    variance_ci : tuple[float, float]
        Its interval.
    source_variance : np.ndarray, shape (g,)
        ``s1 × variance``: the variance of the output an item explains alone,
        ``Var(E[Y | item])``.
    source_variance_ci : np.ndarray, shape (g, 2)
        Its interval. The variance has a sampling error of its own, so this is
        not the interval of ``s1`` times the variance.
    sd_if_exact : np.ndarray, shape (g,)
        ``sqrt(max(variance − source_variance, 0))``: the standard deviation
        left, on average, once the item is known exactly. By the law of total
        variance ``E[Var(Y | item)] = Var(Y) (1 − S1)``, so it is the
        first-order index that answers it.
    sd_if_exact_ci : np.ndarray, shape (g, 2)
        Its interval.
    """

    s1: np.ndarray
    s1_ci: np.ndarray
    st: np.ndarray
    st_ci: np.ndarray
    variance: float
    variance_ci: tuple[float, float]
    source_variance: np.ndarray
    source_variance_ci: np.ndarray
    sd_if_exact: np.ndarray
    sd_if_exact_ci: np.ndarray


def sobol_indices_with_ci(
    f_a: np.ndarray, f_b: np.ndarray, f_ab: list[np.ndarray], n_blocks: int, level: float = 0.95
) -> SobolEstimate:
    """Sobol' indices and absolute variances with t-intervals from a delete-one-block jackknife.

    The outputs follow the row order of :func:`sobol_design`, block by block.
    A row whose output is not finite in ``A``, ``B`` or any ``AB_i`` is left
    out everywhere, since the estimators pair rows across the matrices. The
    indices come from :func:`sobol_indices_from_outputs` on every usable row
    pooled, the variance is that of the pooled ``A`` and ``B`` outputs, and the
    other quantities of :class:`SobolEstimate` follow from the two. Of the
    ``B`` blocks that keep at least one usable row, each is left out in turn
    and every quantity recomputed; their spread gives the standard error
    ``SE = sqrt((B − 1)/B · Σ_j (θ_(j) − mean θ_(·))²)``, and the interval is
    the estimate ± t(B − 1, (1 + level)/2) · SE.

    The blocks are independent scrambles, so the jackknife sees independent
    replicates of the design; the rows inside a scrambled block are not
    independent draws and cannot stand in for them. The interval covers the
    Monte Carlo sampling error of one quantity at a time, not errors in the
    input distributions or in the model. It is symmetric and not clipped.

    Parameters
    ----------
    f_a, f_b : np.ndarray
        Outputs for ``A`` and ``B``, one per design row.
    f_ab : list[np.ndarray]
        ``f_ab[i]`` holds the outputs for ``A`` with the columns of reported
        item *i* taken from ``B``.
    n_blocks : int
        Scrambles the rows are split into, in equal consecutive runs.
    level : float
        Coverage the interval is built for.

    Returns
    -------
    SobolEstimate
        The intervals are ``NaN`` when fewer than three blocks or fewer than
        two rows are usable, and the estimates too when fewer than two rows
        are.

    Raises
    ------
    ValueError
        If the row count is not a multiple of *n_blocks*.
    """
    f_a = np.asarray(f_a, dtype=float)
    f_b = np.asarray(f_b, dtype=float)
    f_ab = np.asarray(f_ab, dtype=float)
    n_items = len(f_ab)
    if n_blocks < 1 or f_a.size % n_blocks:
        raise ValueError(f'{f_a.size} design rows cannot be split into {n_blocks} equal blocks.')
    usable = np.isfinite(f_a) & np.isfinite(f_b) & np.all(np.isfinite(f_ab), axis=0)

    def quantities(rows: np.ndarray) -> np.ndarray:
        """``[s1 (g), st (g), variance (1), source variance (g), sd if exact (g)]`` on *rows*."""
        s1, st = sobol_indices_from_outputs(f_a[rows], f_b[rows], f_ab[:, rows])
        variance = float(np.var(np.concatenate([f_a[rows], f_b[rows]])))
        source_variance = s1 * variance
        sd_if_exact = np.sqrt(np.maximum(variance - source_variance, 0.0))
        return np.concatenate([s1, st, [variance], source_variance, sd_if_exact])

    def estimate_of(values: np.ndarray, interval: np.ndarray) -> SobolEstimate:
        cuts = np.cumsum([n_items, n_items, 1, n_items])
        s1, st, variance, source_variance, sd_if_exact = np.split(values, cuts)
        s1_ci, st_ci, variance_ci, source_variance_ci, sd_if_exact_ci = np.split(interval, cuts)
        return SobolEstimate(
            s1=s1,
            s1_ci=s1_ci,
            st=st,
            st_ci=st_ci,
            variance=float(variance[0]),
            variance_ci=(float(variance_ci[0, 0]), float(variance_ci[0, 1])),
            source_variance=source_variance,
            source_variance_ci=source_variance_ci,
            sd_if_exact=sd_if_exact,
            sd_if_exact_ci=sd_if_exact_ci,
        )

    no_interval = np.full((4 * n_items + 1, 2), np.nan)
    if int(usable.sum()) < 2:
        return estimate_of(np.full(4 * n_items + 1, np.nan), no_interval)
    estimate = quantities(usable)
    block = np.arange(f_a.size) // (f_a.size // n_blocks)
    kept = np.unique(block[usable])
    n_kept = kept.size
    if n_kept < 3:
        return estimate_of(estimate, no_interval)
    leave_one_out = np.array([quantities(usable & (block != j)) for j in kept])
    se = np.sqrt((n_kept - 1) / n_kept * np.sum((leave_one_out - leave_one_out.mean(axis=0)) ** 2, axis=0))
    half = student_t.ppf((1 + level) / 2, n_kept - 1) * se
    return estimate_of(estimate, np.column_stack([estimate - half, estimate + half]))


@dataclass(frozen=True)
class BudgetRow:
    """One source's line of a :class:`Budget`.

    Attributes
    ----------
    source : str
        Source key.
    variance : float
        Variance of log₁₀(Ka), in decades², the source explains alone
        (``SobolEstimate.source_variance``).
    variance_ci : tuple[float, float]
        Its jackknife interval.
    sd_if_exact : float
        Standard deviation of log₁₀(Ka), in decades, left once this source is
        known exactly (``SobolEstimate.sd_if_exact``).
    sd_if_exact_ci : tuple[float, float]
        Its jackknife interval.
    elasticity : float or None
        ``d ln Ka / d ln`` of the inputs the source moves, each times the power
        the source moves it by (:meth:`~core.pipeline.inputs.ErrorModel.powers`)
        and summed over them: to first order, the percent Ka moves per percent
        of this source, which is where a source whose inputs pull Ka in
        opposite directions shows how far it cancels. ``None`` for
        ``ADDITIONS``, which is no single offset.
    """

    source: str
    variance: float
    variance_ci: tuple[float, float]
    sd_if_exact: float
    sd_if_exact_ci: tuple[float, float]
    elasticity: float | None


@dataclass(frozen=True)
class Budget:
    """Absolute variance budget of log₁₀ of one binding constant under the stated error sources.

    Attributes
    ----------
    variance : float
        Variance of log₁₀(Ka) over the samples, in decades².
    variance_ci : tuple[float, float]
        Its jackknife interval.
    rows : tuple[BudgetRow, ...]
        One row per reported source, in the order of ``SensitivityResult.sources``.
    """

    variance: float
    variance_ci: tuple[float, float]
    rows: tuple[BudgetRow, ...]

    @property
    def sd(self) -> float:
        """Standard deviation of log₁₀(Ka), in decades; ``10 ** sd`` is the factor Ka spreads by."""
        return math.sqrt(self.variance)

    @property
    def interactions(self) -> float:
        """Share of the variance no single source explains alone, ``1 − Σ S1``.

        An estimate, reported with its sign: sampling error takes it below zero
        when the sources add up to the whole variance. ``NaN`` when too few fits
        finished to work the variance out, since there is then no share to state;
        ``0`` when the variance is exactly zero, where no source explains
        anything because there is nothing to explain.
        """
        if not math.isfinite(self.variance):
            return math.nan
        if not self.variance > 0:
            return 0.0
        return 1.0 - sum(row.variance for row in self.rows) / self.variance


@dataclass(frozen=True)
class WhatIf:
    """Spread of log₁₀(Ka) if one source's uncertainty were reduced (:func:`what_if`).

    Attributes
    ----------
    sd : float
        Standard deviation in decades, by the first-order formula.
    sd_reweighted : float or None
        The same from the run's samples re-weighted to the reduced
        distribution, which assumes nothing about the model; ``None`` when too
        few samples carry weight, or when no re-weighting applies.
    effective_samples : float or None
        Effective size of the re-weighted sample, ``(Σw)² / Σw²``; ``None``
        when no re-weighting applies.
    largest_after : str
        Source key of the largest row of the budget after the reduction.
    """

    sd: float
    sd_reweighted: float | None
    effective_samples: float | None
    largest_after: str


#: Effective sample size below which the re-weighted what-if is withheld. The
#: relative standard error of a variance estimated from m normal values is
#: sqrt(2 / m): 10 % on the variance and 5 % on its root at m = 200. Below that
#: the cross-check is less certain than the first-order formula it checks.
_MIN_EFFECTIVE_SAMPLES = 200


def _density_ratio(
    spec: InputSpec, nominal: Optional[float], name: str, offsets: np.ndarray, ratio: float
) -> np.ndarray:
    """Density of a source reduced to *ratio* of its width over the density it was sampled from, at *offsets*.

    The sampled density is the one :func:`spec_fraction` draws from: a normal
    truncated at −1 for a standard deviation, a uniform one for a range. The
    reduced one has *ratio* times the standard deviation, or the range shrunk
    to *ratio* of its width about its centre.
    """
    if spec.kind is SpecKind.SIGMA:
        s = _to_fraction(spec.sigma, spec.relative, nominal, name)

        def density(scale: float) -> np.ndarray:
            return truncnorm.pdf(offsets, a=-1.0 / scale, b=np.inf, loc=0.0, scale=scale)

        return density(ratio * s) / density(s)
    lo, hi = spec_bounds(spec, nominal, name)
    inside = np.abs(offsets - (lo + hi) / 2.0) <= ratio * (hi - lo) / 2.0
    return np.where(inside, 1.0 / ratio, 0.0)


def what_if(result: SensitivityResult, ka_key: str, source: str, ratio: float) -> WhatIf:
    """Spread of log₁₀(Ka) if *source*'s uncertainty were *ratio* times what was stated; makes no fit.

    The formula ``V' = V − V_i (1 − ratio²)`` is exact for a model additive in
    the source with a linear effect of it, and first order otherwise. The
    cross-check assumes no model: it weights every ``A`` and ``B`` sample the
    budget was built from (``SensitivityResult.sample_usable``) by
    ``w = reduced density / sampled density`` of the source's offset and takes
    the weighted variance ``Σ w (y − ȳ_w)² / Σ w``. Both answers are over the
    same rows, so a gap between them is the first-order approximation and
    nothing else. It is given when at least
    ``_MIN_EFFECTIVE_SAMPLES`` effective samples carry it, and never for
    ``ADDITIONS`` (a product of one weight per titration point leaves no
    effective sample) or for ``ratio = 0`` (a point mass has no density; the
    answer there is the row's ``sd_if_exact``).

    Parameters
    ----------
    result : SensitivityResult
        A SOBOL result.
    ka_key : str
        Binding constant to answer for.
    source : str
        One of ``result.sources``.
    ratio : float
        Reduced uncertainty over stated uncertainty, from 0 (exact) to 1
        (unchanged). Only improvements: weights towards a wider density are
        unbounded.

    Raises
    ------
    ValueError
        For a result without a budget, a source the result does not report, or
        a ratio outside 0 … 1.
    """
    if result.budget is None:
        raise ValueError('Only a Sobol analysis has a variance budget to ask a what-if of.')
    if not 0.0 <= ratio <= 1.0:
        raise ValueError(f'The reduced uncertainty must be between 0 and 1 times the stated one; {ratio} was given.')
    budget = result.budget[ka_key]
    after = {row.source: row.variance * (ratio**2 if row.source == source else 1.0) for row in budget.rows}
    if source not in after:
        raise ValueError(f'{source!r} is not a source of this analysis.')
    explained = next(row.variance for row in budget.rows if row.source == source)
    sd = math.sqrt(max(budget.variance - explained * (1.0 - ratio**2), 0.0))
    largest_after = max(after, key=after.__getitem__)
    if source == ADDITIONS or ratio == 0.0:
        return WhatIf(sd, None, None, largest_after)

    spec = result.config.errors.source_specs()[source]
    # Only an input's own spec can be absolute, and its source key is the input's key.
    nominal = None if spec.relative else nominal_value(source, result.baseline_fit.conditions)
    log_ka = np.log10(result.sample_ka[ka_key])
    # The rows the budget was built from, which is not every row with a fit of
    # its own: a row whose mixed samples gave no fit is out of the estimators
    # everywhere, so re-weighting it here would answer over a wider sample than
    # the variance the answer is read beside.
    usable = result.sample_usable[ka_key]
    y = log_ka[usable]
    w = _density_ratio(spec, nominal, source_name(source), result.sample_offsets_pct[source][usable] / 100.0, ratio)
    total = float(np.sum(w))
    if not total > 0:
        return WhatIf(sd, None, 0.0, largest_after)
    effective = total**2 / float(np.sum(w**2))
    if effective < _MIN_EFFECTIVE_SAMPLES:
        return WhatIf(sd, None, effective, largest_after)
    mean = float(np.sum(w * y)) / total
    return WhatIf(sd, math.sqrt(float(np.sum(w * (y - mean) ** 2)) / total), effective, largest_after)


def homogeneity_sum(elasticity: Mapping[str, float], kinds: Mapping[str, str]) -> float:
    """``Σ s_j`` over the concentrations and the titrant minus ``Σ s_j`` over the entered binding constants.

    A binding model built from mass balances and association constants is
    homogeneous: every concentration times ``c`` and every entered constant
    divided by ``c`` is the same least-squares problem with every fitted
    constant divided by ``c``. Differentiated at ``c = 1`` that makes this sum
    ``−1`` for every fitted binding constant, which is a test of the refits and
    of the model code, not information about the data.

    Parameters
    ----------
    elasticity : Mapping[str, float]
        Input key → ``d ln Ka / d ln input`` of one binding constant.
    kinds : Mapping[str, str]
        Input key → its kind, ``dict(perturbable_inputs(base_conditions))``.
    """
    return sum(-value if kinds[key] == 'binding_constant' else value for key, value in elasticity.items())


@dataclass(frozen=True)
class SobolJobs:
    """The perturbations of one SOBOL design (:func:`sobol_jobs`).

    Attributes
    ----------
    sources : tuple[str, ...]
        Reported source keys: item *i* of the design, ``ADDITIONS`` last.
    source_offsets : list[dict[str, float]]
        Per design row, the relative offset of every single source. The rows
        run matrix by matrix: ``A``, ``B``, then ``AB_i`` for each reported item.
    jobs : list[tuple[dict[str, float], np.ndarray | None]]
        Per design row, what one refit takes: the relative offset of every
        input the sources move, and the relative error of every titrant
        addition or ``None`` when no error of the additions is stated.
    """

    sources: tuple[str, ...]
    source_offsets: list[dict[str, float]]
    jobs: list[tuple[dict[str, float], np.ndarray | None]]


def sobol_jobs(
    errors: ErrorModel,
    base_conditions: Mapping,
    n_base: int,
    n_points: int,
    n_replicates: int,
    seed: int | np.random.SeedSequence | None,
    input_labels: Optional[Mapping[str, str]] = None,
) -> SobolJobs:
    """Build the Saltelli design of a SOBOL run over the sources of *errors*; makes no fit.

    The design has one column per single source (``errors.source_specs()``, in
    its order) and, when an error of the additions is stated, one column per
    titration point after them. A reported item is one single source, or all
    the addition columns together as ``ADDITIONS``; ``AB_i`` is ``A`` with the
    columns of item *i* taken from ``B``, which for a group of columns gives
    the group's closed first-order index and its total index at the cost of one
    matrix, whatever the number of points.

    Every column goes through the inverse CDF of its source
    (:func:`spec_fraction`). A refit is of the average of the replicates.
    Where they are separate titrations
    (``AdditionError.separate_titrations``), each with its own addition
    errors, the first-order addition error of the average is the mean of
    *n_replicates* independent ones and the addition columns are sampled at
    ``sigma / sqrt(n_replicates)``; where they are repeated reads of one
    titration they share their additions, and the columns are sampled at
    ``sigma``.

    Parameters
    ----------
    errors : ErrorModel
        The stated sources.
    base_conditions : Mapping
        Entered assay conditions; an absolute spec is measured against them.
    n_base : int
        Rows per matrix.
    n_points : int
        Titration points.
    n_replicates : int
        Replicates whose average every refit fits.
    seed : int, SeedSequence or None
        Root of the scrambles, as :func:`sobol_design` takes it.
    input_labels : Mapping[str, str], optional
        Display label per input key, to name an input in a message.
    """
    specs = errors.source_specs()
    n_single = len(specs)
    n_columns = n_single + (n_points if errors.additions is not None else 0)
    groups = [[column] for column in range(n_single)]
    if errors.additions is not None:
        groups.append(list(range(n_single, n_columns)))
    a_points, b_points = sobol_design(n_base, n_columns, _SOBOL_BLOCKS, seed)
    matrices = [a_points, b_points]
    for group in groups:
        mixed = a_points.copy()
        mixed[:, group] = b_points[:, group]
        matrices.append(mixed)
    # One batch for every matrix. Each source is mapped through its inverse CDF
    # one column at a time: the same numbers as row by row, and fast enough not
    # to hold the run up before the first fit is dispatched.
    quantiles = np.clip(np.vstack(matrices), _QUANTILE_EPS, 1.0 - _QUANTILE_EPS)
    columns = [
        spec_fraction(
            spec,
            nominal_value(key, base_conditions) if key in errors.specs else None,
            source_name(key, input_labels),
            quantiles[:, column],
        ).tolist()
        for column, (key, spec) in enumerate(specs.items())
    ]
    source_offsets = [dict(zip(specs, row)) for row in zip(*columns)] if columns else [{} for _ in quantiles]
    deltas: list[np.ndarray | None] = [None] * len(quantiles)
    if errors.additions is not None:
        divisor = n_replicates if errors.additions.separate_titrations else 1
        per_average = InputSpec.sigma_pct(errors.additions.sigma_pct / math.sqrt(divisor))
        deltas = list(spec_fraction(per_average, None, source_name(ADDITIONS), quantiles[:, n_single:]))
    return SobolJobs(
        sources=_reported_sources(errors),
        source_offsets=source_offsets,
        jobs=[(errors.input_offsets(offsets, base_conditions), row) for offsets, row in zip(source_offsets, deltas)],
    )


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


def _init_worker(ms, assay_cls, x_base, base_conditions, fit_config, sequential, point_weights) -> None:
    """Hand a worker process the data every job in the batch needs."""
    _WORKER_STATE.update(
        ms=ms,
        assay_cls=assay_cls,
        x_base=x_base,
        base_conditions=base_conditions,
        fit_config=fit_config,
        sequential=sequential,
        point_weights=point_weights,
    )


def _run_job(state: dict, job):
    """Run one perturbation ``(index, offsets, deltas or None)`` with the batch state *state* → ``(index, result)``."""
    index, offsets, deltas = job
    return index, _fit_perturbed(
        state['ms'],
        state['assay_cls'],
        state['x_base'],
        state['base_conditions'],
        offsets,
        state['fit_config'],
        deltas,
        state['sequential'],
        state['point_weights'],
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
    perturbations,
    *,
    sequential,
    max_workers,
    on_result,
    should_cancel,
    point_weights=None,
):
    """Fit a batch of perturbations, in parallel when that is worthwhile.

    A perturbation is ``(input offsets, addition errors or None)``, what
    :func:`_fit_perturbed` takes; *sequential* says how the addition errors of
    the batch accumulate and *point_weights* is the weight of every titration
    point, the same for every fit of the batch. Results come back in the order
    of *perturbations* however the work was scheduled, so a Sobol' row pairing
    or a heatmap cell index stays valid, and ``on_result(index, value)`` hears of
    each fit as it finishes, *index* being its place in *perturbations*: a
    perturbation never reached and one without a fit are both ``None`` in the
    list, and only the second is ever reported. A perturbation has one fit, so
    the answer does not depend on which worker ran it.

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
    results: list = [None] * len(perturbations)
    jobs = [(index, offsets, deltas) for index, (offsets, deltas) in enumerate(perturbations)]
    state = {
        'ms': ms,
        'assay_cls': assay_cls,
        'x_base': x_base,
        'base_conditions': base_conditions,
        'fit_config': fit_config,
        'sequential': sequential,
        'point_weights': point_weights,
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
            on_result(index, value)
        return results

    queue = iter(jobs)
    with _thread_capped_children():
        executor = ProcessPoolExecutor(
            max_workers=max_workers,
            mp_context=mp.get_context('spawn'),
            initializer=_init_worker,
            initargs=(ms, assay_cls, x_base, base_conditions, fit_config, sequential, point_weights),
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
                on_result(index, value)
            pending.update(executor.submit(_worker_fit, job) for job in islice(queue, len(finished)))
    finally:
        executor.shutdown(cancel_futures=True)
    return results


def _perturbed_ms(ms, x_base: np.ndarray, offsets: dict) -> MeasurementSet:
    """Copy of *ms* with the titrant grid *x_base* rescaled, replica activity preserved.

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


def _stock_magnitude(base_conditions: Mapping) -> Optional[float]:
    """The declared titrant stock in M, the unit of the titrant grid; ``None`` when no dilution is declared."""
    stock = base_conditions.get(TITRANT_STOCK)
    return None if stock is None else float(stock.to('M').magnitude)


def _fit_perturbed(
    ms, assay_cls, x_base, base_conditions, offsets, fit_config, deltas=None, sequential=False, point_weights=None
):
    """Fit of one perturbation → ``({parameter key: value}, R², profile R²)``.

    *offsets* is the relative offset per input key. Every entered condition
    takes its own; the ``TITRANT`` offset is the error of the stock's
    concentration, so it scales the titrant grid and the declared titrant stock
    together and the dilution of every point stays what the volumes made it.
    *deltas*, when given, is the relative volume error of every addition
    (:func:`~core.pipeline.inputs.perturb_titrant`, accumulating when
    *sequential*); it moves the grid first, since the scale error applies to
    whatever volumes were delivered.

    The averaged signal of the active replicates is projected onto the
    perturbed model and its binding constants searched over the Ka box in
    force, which is how the headline fit of these data is made; every parameter
    comes back in its canonical registry unit, the unit ``FitResult.parameters``
    carries, and the R² is measured against that averaged signal.

    *point_weights* is the weight of every titration point the baseline fit
    ran with (:attr:`~core.pipeline.fit_pipeline.FitResult.point_weights`).
    The noise law they come from is read off the measured replicates, which
    moving the inputs leaves untouched, and every fit of a run carries the same
    weights: each sample minimises the objective the baseline minimised, and a
    sample with no offset is the baseline fit. Beside the R² above, which counts every point equally, the
    fit's place on the Identifiability tab's axis comes back as
    ``1 - S_w / SS_tot,w``: the weighted objective this fit minimised, on the
    scale the Ka profiles are drawn on.

    ``None`` when the perturbed inputs leave the model with no solution
    anywhere in the Ka box: that is one sample without a fit, which the caller
    records as NaN, and the other thousands of samples stand. Quality is not
    judged here — every fit is reported whatever its R².
    """
    if deltas is not None:
        x_base = perturb_titrant(x_base, deltas, sequential, _stock_magnitude(base_conditions))
    perturbed = _perturbed_ms(ms, x_base, offsets)
    conditions = {k: (v * (1 + offsets[k]) if k in offsets else v) for k, v in base_conditions.items()}
    if TITRANT in offsets and TITRANT_STOCK in conditions:
        conditions[TITRANT_STOCK] = conditions[TITRANT_STOCK] * (1 + offsets[TITRANT])
    assay = perturbed.to_assay(assay_cls, conditions=conditions, use_average=True)
    projection = Projection(assay, _resolve_bounds(assay, fit_config.custom_bounds), point_weights=point_weights)
    try:
        fit = projection.fit()
    except FitRefused:
        return None
    params = projection.params(fit)
    _, r_squared = calculate_fit_metrics(assay.y_data.magnitude, assay.forward_model(params).magnitude)
    profile_r2 = 1.0 - fit.objective / float(projection.ss_tot[0])
    return dict(zip(assay.parameter_keys, params.tolist())), float(r_squared), float(profile_r2)


#: Relative step of the central difference behind an elasticity. The slope of
#: ln Ka against ln input is smooth, so the truncation error falls with the
#: square of the step, while a refit resolves log10 Ka to about 1e-7 decades (the
#: tolerance of the Ka refinement), an error in the slope that grows as the step
#: shrinks. Over the six binding assays the truncation error is below 1e-5 at
#: 1e-3 (3e-4 to 7e-4 at 1e-2) and the resolution costs about 1e-4 per slope
#: (1.5e-3 at 1e-4), so 1e-3 is where the two together are smallest.
_ELASTICITY_STEP = 1e-3


#: ``ln(1 + step) - ln(1 - step)``: the width in ``ln input`` the central difference spans.
_ELASTICITY_SPAN = math.log1p(_ELASTICITY_STEP) - math.log1p(-_ELASTICITY_STEP)


def homogeneity_tolerance(n_inputs: int) -> float:
    """Largest ``|homogeneity_sum + 1|`` at which the elasticities of *n_inputs* inputs count as the refits' own.

    A refit resolves log₁₀(Ka) to ``_LOG_KA_XTOL``, so the two refits behind
    one elasticity differ by up to twice that from their true difference,
    which is ``2 · _LOG_KA_XTOL · ln 10 / _ELASTICITY_SPAN`` ≈ 2.3e-4 on the
    slope, and the sum over *n_inputs* inputs by *n_inputs* times it; the
    truncation error of the step is below 1e-5 per slope. Ten times that
    bound, 9e-3 for four inputs, leaves an identified fit (measured at most
    6e-4 over the six binding assays, with and without dilution) well inside,
    while a refit that jumps between fits or rides a flat profile misses by
    0.8 to thousands.
    """
    return 10.0 * n_inputs * 2.0 * _LOG_KA_XTOL * math.log(10.0) / _ELASTICITY_SPAN


def _elasticity_perturbations(base_conditions: Mapping) -> list[tuple[dict[str, float], None]]:
    """One step up and one step down for every perturbable input, in the order of :func:`perturbable_inputs`."""
    return [
        ({key: sign * _ELASTICITY_STEP}, None) for key, _ in perturbable_inputs(base_conditions) for sign in (1.0, -1.0)
    ]


def _elasticities(base_conditions: Mapping, ka: Mapping[str, np.ndarray]) -> dict[str, dict[str, float]]:
    """ka key → input key → ``d ln Ka / d ln input`` from the fits of :func:`_elasticity_perturbations`."""
    keys = [key for key, _ in perturbable_inputs(base_conditions)]
    return {
        ka_key: {
            key: float(np.log(values[2 * i]) - np.log(values[2 * i + 1])) / _ELASTICITY_SPAN
            for i, key in enumerate(keys)
        }
        for ka_key, values in ka.items()
    }


def _free_ka_bounds(assay, fit_config: FitConfig, ka_keys: tuple[str, ...]) -> dict[str, tuple[float, float]]:
    """The Ka box every free binding constant is searched over, in that key's registry unit.

    A constant whose two bounds are equal is pinned to that value rather than
    searched, and it is left out: it rests on its bounds by construction, which
    says nothing about what the data limit.
    """
    units = ASSAY_REGISTRY[assay.assay_type].units
    bounds = _resolve_bounds(assay, fit_config.custom_bounds)
    box = {key: tuple(float(end.to(units[key]).magnitude) for end in bounds[key]) for key in ka_keys}
    return {key: ends for key, ends in box.items() if ends[0] < ends[1]}


def _count_on_bound(values: np.ndarray, bounds: tuple[float, float]) -> int:
    """How many of the fitted *values* rest on a bound of *bounds*; a perturbation with no fit is not one."""
    return sum(on_ka_bound(float(value), bounds) for value in values if np.isfinite(value))


def _identity_applies(
    assay, fit_config: FitConfig, ka_box: Mapping[str, tuple[float, float]], baseline: FitResult
) -> bool:
    """Whether :func:`homogeneity_sum` has to be ``−1`` for the elasticities of *baseline*.

    Summed as :func:`homogeneity_sum` sums them, the elasticities are the
    response to a change of the concentration unit by ``1 ± _ELASTICITY_STEP``,
    which divides every fitted binding constant and every signal coefficient by
    that factor — as long as nothing holds them: every binding constant has to
    be searched (a pinned one cannot follow), and no signal coefficient may sit
    within ten steps of a bound other than zero or infinity, which read the
    same in any unit. The edges of the Ka box are what the identity is there to
    catch, so they do not count here.
    """
    meta = ASSAY_REGISTRY[assay.assay_type]
    if set(ka_box) != set(meta.log_scale_keys):
        return False
    bounds = _resolve_bounds(assay, fit_config.custom_bounds)
    margin = 10.0 * _ELASTICITY_STEP
    for key, kind in meta.param_kinds.items():
        if kind is not ParamKind.SIGNAL_COEFFICIENT:
            continue
        value = float(baseline.parameters[key].to(meta.units[key]).magnitude)
        for end in (float(bound.to(meta.units[key]).magnitude) for bound in bounds[key]):
            if math.isfinite(end) and end != 0.0 and not abs(value - end) > margin * abs(value):
                return False
    return True


def _withheld(
    ka_key: str,
    baseline: FitResult,
    baseline_on_bound: Mapping[str, bool],
    homogeneity: float,
    identity_applies: bool,
    n_inputs: int,
) -> str:
    """Why *ka_key*'s indices, budget, what-if and elasticities describe the search rather than the inputs; ``''`` if not.

    The reason tokens are those of ``SensitivityResult.withheld``, checked in
    that order: the one that says most about the fit comes first.
    """
    if baseline_on_bound.get(ka_key):
        return 'baseline_on_bound'
    interval = baseline.intervals.get(ka_key)
    if ka_key in baseline_on_bound and (interval is None or interval.open_low or interval.open_high):
        return 'open_interval'
    if identity_applies and not abs(homogeneity + 1.0) <= homogeneity_tolerance(n_inputs):
        return 'homogeneity'
    return ''


def _block_order(n_base: int, n_matrices: int, n_blocks: int) -> np.ndarray:
    """The rows of a design of *n_matrices* matrices in the order they are fitted: block by block.

    Row ``m · n_base + i`` is row *i* of matrix *m*, the order
    :class:`SobolJobs` lists them in. Every matrix of one sample block is fitted
    before the next block starts, so a stopped run leaves whole blocks behind
    it, and whole blocks are what the estimators and their jackknife take.
    """
    per_block = n_base // n_blocks
    return np.arange(n_matrices * n_base).reshape(n_matrices, n_blocks, per_block).transpose(1, 0, 2).ravel()


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
        error sources are not used here — this run samples the ones in
        *sens_config*, and every fit it makes holds the inputs at their sampled
        values.
    sens_config : SensitivityConfig
        What to perturb and how.
    progress : callable, optional
        Called ``progress(done, total)`` after every fit (baseline included).
    should_cancel : callable, optional
        Polled before the baseline fit, inside it and in the perturbation loop;
        on ``True`` the run stops early and returns the result of what
        finished: for SOBOL, the elasticities (fitted first) and the sample
        blocks all of whose fits finished (``SensitivityResult.stopped``).
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
        ``_SOBOL_SAMPLE_SIZES``, nothing set to vary, negative percent, a range
        reaching below zero, unknown key, a shared source or an error of the
        additions :func:`~core.pipeline.inputs.validate` refuses, sequential
        additions on a titrant series that falls, HEATMAP with
        ``x_key == y_key``, a non-perturbable axis key or an axis reaching
        zero), for an assay with no
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
    errors = sens_config.errors
    for key, spec in errors.specs.items():
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
    validate(errors, base_conditions, input_labels)
    if sens_config.mode is SensitivityMode.SOBOL and not errors.varies:
        raise FitRefused('No input is set to vary — give at least one input a non-zero uncertainty.')
    if sens_config.mode is SensitivityMode.HEATMAP and not any(spec.varies for spec in errors.specs.values()):
        raise FitRefused(
            'No input is set to vary — give at least one input a non-zero uncertainty of its own. '
            'The heatmap sweeps two inputs over their own uncertainty; shared error sources and the random '
            'error of the additions are part of the Sobol analysis only.'
        )
    sobol_additions = errors.additions if sens_config.mode is SensitivityMode.SOBOL else None
    if sobol_additions is not None:
        # Additions into one cuvette cannot lower the concentration: a series
        # that falls is refused here, before any fit is made.
        perturb_titrant(x_base, np.zeros(x_base.size), sobol_additions.sequential, _stock_magnitude(base_conditions))

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
            spec = errors.specs.get(axis_key)
            name = input_name(axis_key, input_labels)
            if spec is not None and axis_reaches_zero(spec, nominal_value(axis_key, base_conditions), name):
                raise FitRefused(
                    f'The heatmap axis for {name} reaches zero or below, and a concentration or binding constant '
                    'must stay positive. Use a σ below 50 % of the set value, or a range whose lower end is above zero.'
                )
        if sens_config.n_steps < 1:
            raise FitRefused('Heatmap grid resolution must be at least 1.')

    # --- Baseline (unperturbed) fit --------------------------------------
    n_planned = estimated_fit_count(sens_config, len(valid_keys))
    total = n_planned + 1  # +1 for the baseline
    done = 0

    # One root seed drives the whole run, drawn here when none was configured, so
    # every run can be repeated by feeding its `seed_used` back in. It is drawn
    # within MAX_SEED, the range the interface's Fixed seed box accepts, so a
    # reported seed can always be entered there.
    seed_used = int(np.random.SeedSequence().generate_state(1)[0] % (MAX_SEED + 1))
    seed_used = seed_used if sens_config.seed is None else sens_config.seed

    def _tally(counters: dict, finished: np.ndarray):
        """Progress callback that counts a finished fit however it was scheduled, and marks it finished."""

        def record(index: int, value) -> None:
            finished[index] = True
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
    # The baseline is the fit at the inputs as entered: the sources are what
    # this run samples, so letting the baseline fit move the inputs as well would
    # report the spread of the samples around a fit that already absorbed them.
    baseline_result = fit_measurement_set(
        ms, assay_cls, base_conditions, replace(fit_config, errors=ErrorModel()), should_cancel=should_cancel
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
    # Every fit of the run carries the weights the baseline fit ran with, read
    # off the replicates it used. They describe the measured replicates, which
    # moving the inputs leaves untouched, so every sample is weighted alike and
    # the baseline is the sample with no offset.
    point_weights = baseline_result.point_weights
    baseline_ka = {k: baseline_result.parameters[k].to('1/M').magnitude for k in ka_keys}
    degenerate_keys = baseline_result.degenerate_keys
    # The Ka box every fit of the run searches, and where the baseline landed in
    # it: on a bound the data do not limit that constant, and neither the spread
    # nor the budget below describes the inputs any more.
    ka_box = _free_ka_bounds(probe_assay, fit_config, ka_keys)
    baseline_on_bound = {
        key: on_ka_bound(float(baseline_result.parameters[key].to(metadata.units[key]).magnitude), bounds)
        for key, bounds in ka_box.items()
    }

    def _evaluate(
        perturbations: list[tuple[dict, np.ndarray | None]],
    ) -> tuple[dict[str, np.ndarray], np.ndarray, np.ndarray, dict, np.ndarray]:
        """Fit every perturbation → (value per parameter key, R², profile R², counters, finished), NaN without a fit."""
        counters = {'total': 0, 'success': 0, 'done': done}
        finished = np.zeros(len(perturbations), dtype=bool)
        values = _evaluate_batch(
            ms,
            assay_cls,
            x_base,
            base_conditions,
            fit_config,
            perturbations,
            sequential=sobol_additions is not None and sobol_additions.sequential,
            max_workers=workers,
            on_result=_tally(counters, finished),
            should_cancel=_cancelled,
            point_weights=point_weights,
        )
        params = {
            key: np.array([np.nan if v is None else v[0][key] for v in values]) for key in probe_assay.parameter_keys
        }
        r2 = np.array([np.nan if v is None else v[1] for v in values])
        profile_r2 = np.array([np.nan if v is None else v[2] for v in values])
        return params, r2, profile_r2, counters, finished

    kinds = dict(perturbable_inputs(base_conditions))
    identity_applies = _identity_applies(probe_assay, fit_config, ka_box, baseline_result)

    # --- Dispatch on mode ------------------------------------------------
    if sens_config.mode is SensitivityMode.SOBOL:
        n_base = sens_config.n_samples
        design = sobol_jobs(
            errors,
            base_conditions,
            n_base,
            x_base.size,
            len(fit_replica_ids(baseline_result) or ()) or 1,
            seed_used,
            input_labels,
        )
        sources = design.sources
        n_design = len(design.jobs)
        # One batch: the refits of the elasticities first, a handful that every
        # later statement about the run is checked against, then the design
        # block by block (_block_order), so a stopped run keeps whole blocks.
        elastic = _elasticity_perturbations(base_conditions)
        order = _block_order(n_base, len(sources) + 2, _SOBOL_BLOCKS)
        perturbations = elastic + [design.jobs[i] for i in order]
        queued, queued_r2, queued_profile_r2, counters, queued_finished = _evaluate(perturbations)
        elasticity = _elasticities(base_conditions, {key: queued[key][: len(elastic)] for key in ka_keys})

        def in_design_order(values: np.ndarray) -> np.ndarray:
            out = np.empty(n_design, dtype=values.dtype)
            out[order] = values[len(elastic) :]
            return out

        params = {key: in_design_order(values) for key, values in queued.items()}
        r2, profile_r2, finished = map(in_design_order, (queued_r2, queued_profile_r2, queued_finished))
        # A block some fit of which never ran is dropped whole: its rows would
        # otherwise enter the estimators as a part-block the jackknife would
        # take for an independent replicate of the design.
        block = (np.arange(n_design) % n_base) // (n_base // _SOBOL_BLOCKS)
        blocks_finished = np.array([finished[block == j].all() for j in range(_SOBOL_BLOCKS)])
        dropped = ~blocks_finished[block]
        for values in (*params.values(), r2, profile_r2):
            values[dropped] = np.nan
        n_samples = 2 * n_base  # the A and B rows

        sobol_s1: dict[str, dict[str, float]] = {}
        sobol_st: dict[str, dict[str, float]] = {}
        sobol_s1_ci: dict[str, dict[str, tuple[float, float]]] = {}
        sobol_st_ci: dict[str, dict[str, tuple[float, float]]] = {}
        rows_left_out: dict[str, int] = {}
        usable: dict[str, np.ndarray] = {}
        budget: dict[str, Budget] = {}
        powers = {source: errors.powers(source, base_conditions) for source in sources}
        for key in ka_keys:
            # The indices split the variance of log10(Ka): Ka spans orders of
            # magnitude, and on the raw scale one far-off fit would own almost
            # all of the variance and push the indices far outside 0 to 1. A
            # row without a fit in every matrix is left out of the indices.
            by_matrix = np.log10(params[key]).reshape(len(sources) + 2, n_base)
            estimate = sobol_indices_with_ci(by_matrix[0], by_matrix[1], by_matrix[2:], _SOBOL_BLOCKS)
            sobol_s1[key] = {k: float(v) for k, v in zip(sources, estimate.s1)}
            sobol_st[key] = {k: float(v) for k, v in zip(sources, estimate.st)}
            sobol_s1_ci[key] = {k: (float(lo), float(hi)) for k, (lo, hi) in zip(sources, estimate.s1_ci)}
            sobol_st_ci[key] = {k: (float(lo), float(hi)) for k, (lo, hi) in zip(sources, estimate.st_ci)}
            # The rows the estimators could use. The A and the B sample of a row
            # are dropped together, so the mask over the samples is it twice.
            rows_used = np.all(np.isfinite(by_matrix), axis=0)
            rows_left_out[key] = int(np.sum(~rows_used))
            usable[key] = np.tile(rows_used, 2)
            budget[key] = Budget(
                variance=estimate.variance,
                variance_ci=estimate.variance_ci,
                rows=tuple(
                    BudgetRow(
                        source=source,
                        variance=float(estimate.source_variance[i]),
                        variance_ci=tuple(map(float, estimate.source_variance_ci[i])),
                        sd_if_exact=float(estimate.sd_if_exact[i]),
                        sd_if_exact_ci=tuple(map(float, estimate.sd_if_exact_ci[i])),
                        # To first order a source moves Ka by the sum of what
                        # the inputs it moves do, each by the power it moves it by.
                        elasticity=None
                        if source == ADDITIONS
                        else sum(power * elasticity[key][moved] for moved, power in powers[source].items()),
                    )
                    for i, source in enumerate(sources)
                ),
            )
        # A stop during the elasticity refits leaves them unrun, not failed:
        # the identity was never checked, so it is no reason to withhold.
        checked = identity_applies and bool(queued_finished[: len(elastic)].all())
        homogeneity = {key: homogeneity_sum(elasticity[key], kinds) if checked else math.nan for key in ka_keys}

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
                k: 100.0 * np.array([offsets[k] for offsets in design.source_offsets[:n_samples]])
                for k in errors.source_specs()
            },
            sample_ka={key: params[key][:n_samples] for key in ka_keys},
            sample_usable=usable,
            sample_r2=r2[:n_samples],
            sample_profile_r2=profile_r2[:n_samples],
            baseline_fit=baseline_result,
            sample_params={key: values[:n_samples] for key, values in params.items()},
            degenerate_keys=degenerate_keys,
            sobol_rows_left_out=rows_left_out,
            baseline_on_bound=baseline_on_bound,
            n_on_bound={key: _count_on_bound(params[key], bounds) for key, bounds in ka_box.items()},
            stopped=counters['total'] < len(perturbations),
            budget=budget,
            elasticity=elasticity,
            sources=sources,
            source_inputs={source: errors.loaded(source) for source in sources},
            n_planned=n_planned,
            n_blocks_finished=int(blocks_finished.sum()),
            homogeneity=homogeneity,
            withheld={
                key: _withheld(key, baseline_result, baseline_on_bound, homogeneity[key], checked, len(kinds))
                for key in ka_keys
            },
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
    perturbations = [
        ({sens_config.x_key: float(x_offsets[ix]), sens_config.y_key: float(y_offsets[iy])}, None) for iy, ix in cells
    ]
    params, r2, _, counters, _ = _evaluate(perturbations)
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
        baseline_on_bound=baseline_on_bound,
        n_on_bound={key: _count_on_bound(params[key], bounds) for key, bounds in ka_box.items()},
        stopped=counters['total'] < len(perturbations),
        n_planned=n_planned,
        homogeneity=dict.fromkeys(ka_keys, math.nan),
        withheld={key: _withheld(key, baseline_result, baseline_on_bound, math.nan, False, 0) for key in ka_keys},
    )
