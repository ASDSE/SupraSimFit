"""Ka input-sensitivity analysis (pure compute layer, no Qt).

A fitted association constant (Ka) is only as trustworthy as the *inputs* fed
into the model — the titrant concentration vector, the fixed conditions
(``h0`` / ``d0`` / …) and any non-fitted binding constant (``Ka_dye``). Each
carries measurement error, and the fit silently compensates by shifting the
fitted Ka. This module re-runs the fit many times with those inputs perturbed
according to each input's stated uncertainty and reports the resulting spread
of Ka.

Two analysis modes:

- **SOBOL** — every varied input sampled together on a Saltelli design built
  from independently scrambled Sobol' blocks → the Ka distribution, first- and
  total-order Sobol' indices of log₁₀(Ka) with 95 % intervals for their Monte
  Carlo sampling error, and each sample's input offsets, Ka and R².
- **HEATMAP** — sweep two chosen input offsets on a grid, fit at each cell →
  a 2D Ka surface with the R² of every cell.

Every perturbation yields its best fit whatever its quality. The configured R²
floor only counts and flags the fits below it, because dropping them would
remove exactly the input combinations the data disagree with and bias the Ka
distribution. Every perturbation is refitted through the exact Ka profile
(:mod:`core.pipeline.profile`), which locates the best fit along the profile by a
grid search with a bounded refinement rather than a multi-start search, so the
analysis applies to the assays whose signal is linear in every parameter but one
Ka (:func:`~core.pipeline.profile.profile_supported`).
A search that can land on a different optimum from one seed to the next would
report its own scatter as input sensitivity, so no other assay is accepted.

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
from scipy.stats import qmc, truncnorm
from scipy.stats import t as student_t

from core.assays.base import BaseAssay
from core.assays.registry import ASSAY_REGISTRY, AssayType, ParamKind
from core.data_processing.measurement_set import MeasurementSet
from core.optimizer.ensemble import select_representative_index
from core.optimizer.filters import calculate_fit_metrics
from core.optimizer.multistart import FitCancelled
from core.pipeline.fit_pipeline import (
    MAX_SEED,
    FitConfig,
    FitResult,
    PerReplicaFitError,
    _resolve_bounds,
    _wrap_params_as_quantities,
    fit_measurement_set,
    fit_replica_ids,
    representative_view,
)
from core.pipeline.profile import _LINEAR_KINDS, _RANK_RTOL, _float_bounds, best_params_by_profile, profile_supported
from core.units import Quantity

# Sentinel input key for the titrant (the varying x-axis concentration vector).
TITRANT = '__titrant__'


class SpecKind(Enum):
    """How an input's uncertainty is stated."""

    SIGMA = 'sigma'
    INTERVAL = 'interval'


@dataclass(frozen=True)
class InputSpec:
    """The uncertainty of one input.

    ``SIGMA`` is a precision figure — an instrument's pipetting tolerance, say —
    read as one standard deviation of a Gaussian and truncated so the perturbed
    value stays positive. ``INTERVAL`` is a plain range, sampled uniformly and
    free to be asymmetric; a binding constant carried over from an earlier fit
    arrives in that form, as an estimate with a low and a high bound.

    A relative spec is stated in percent of the input's nominal value. An
    absolute one is in the input's own unit: for ``SIGMA`` the spread itself,
    and for ``INTERVAL`` the low and high values the input may take. The titrant
    has no single nominal value, so it accepts relative specs only.
    """

    kind: SpecKind
    sigma: float = 0.0
    lo: float = 0.0
    hi: float = 0.0
    relative: bool = True

    @classmethod
    def sigma_pct(cls, sigma: float) -> 'InputSpec':
        """Gaussian with a standard deviation of *sigma* percent."""
        return cls(SpecKind.SIGMA, sigma=sigma, relative=True)

    @classmethod
    def sigma_abs(cls, sigma: float) -> 'InputSpec':
        """Gaussian with a standard deviation of *sigma* in the input's unit."""
        return cls(SpecKind.SIGMA, sigma=sigma, relative=False)

    @classmethod
    def interval_pct(cls, lo: float, hi: float) -> 'InputSpec':
        """Uniform between *lo* and *hi* percent of nominal."""
        return cls(SpecKind.INTERVAL, lo=lo, hi=hi, relative=True)

    @classmethod
    def interval_abs(cls, lo: float, hi: float) -> 'InputSpec':
        """Uniform between the values *lo* and *hi*, in the input's unit."""
        return cls(SpecKind.INTERVAL, lo=lo, hi=hi, relative=False)

    @property
    def varies(self) -> bool:
        """Whether this spec actually moves the input."""
        if self.kind is SpecKind.SIGMA:
            return self.sigma > 0
        return self.hi > self.lo


#: Half-width of the deterministic heatmap sweep for a SIGMA spec, in standard
#: deviations. Two covers ~95% of the distribution.
_SIGMA_GRID_SPAN = 2.0


def _to_fraction(value: float, relative: bool, nominal: Optional[float], name: str) -> float:
    """Express *value* as a fraction of the input's nominal value.

    *name* names the input in the messages a user reads, so it is a display
    label, never a dict key.
    """
    if relative:
        return value / 100.0
    if nominal is None:
        raise ValueError(
            'The titrant is a series of concentrations with no single value to measure against, '
            'so its uncertainty has to be given as a percentage.'
        )
    if nominal == 0:
        raise ValueError(f'{name} is set to zero, so an uncertainty in its own unit says nothing about it.')
    return value / nominal


def spec_bounds(spec: InputSpec, nominal: Optional[float], name: str) -> tuple[float, float]:
    """Relative-offset range a spec spans, as fractions of nominal.

    A SIGMA spec has no hard edges, so its sweep is taken at
    ``±_SIGMA_GRID_SPAN`` standard deviations. *name* names the input in the
    messages a user reads, so it is a display label, never a dict key.
    """
    if spec.kind is SpecKind.SIGMA:
        s = _to_fraction(spec.sigma, spec.relative, nominal, name)
        return -_SIGMA_GRID_SPAN * s, _SIGMA_GRID_SPAN * s
    if spec.relative:
        return spec.lo / 100.0, spec.hi / 100.0
    # An absolute interval states the input's own low and high values, the form a
    # binding constant carried over from an earlier fit already comes in.
    if nominal is None:
        raise ValueError(
            'The titrant is a series of concentrations with no single value to measure against, '
            'so its range has to be given as percentages.'
        )
    if nominal == 0:
        raise ValueError(f'{name} is set to zero, so a range in its own unit says nothing about it.')
    return (spec.lo - nominal) / nominal, (spec.hi - nominal) / nominal


def axis_reaches_zero(spec: InputSpec, nominal: Optional[float], name: str) -> bool:
    """Whether a heatmap axis swept over :func:`spec_bounds` would take the input to zero or below.

    The sweep includes both ends, so a lower end at -100 % of the nominal value, to
    rounding, would fit the model with the input at zero.
    """
    return spec_bounds(spec, nominal, name)[0] <= -1.0 + 1e-9


def spec_fraction(spec: InputSpec, nominal: Optional[float], name: str, quantile):
    """Map uniform draws in (0, 1) to relative offsets.

    Going through the inverse CDF keeps the draw independent of how the
    quantile was produced, so plain random sampling and a low-discrepancy
    sequence share one definition of an input's distribution.

    One quantile gives one float; an array of quantiles gives an array of the
    same shape, which is how a whole column of a sampling design is mapped in a
    single call.
    """
    quantiles = np.asarray(quantile, dtype=float)
    if spec.kind is SpecKind.SIGMA:
        s = _to_fraction(spec.sigma, spec.relative, nominal, name)
        if s <= 0:
            offsets = np.zeros_like(quantiles)
        else:
            # Truncated at -1 so the perturbed value never reaches zero or below.
            offsets = truncnorm.ppf(quantiles, a=-1.0 / s, b=np.inf, loc=0.0, scale=s)
    else:
        lo, hi = spec_bounds(spec, nominal, name)
        offsets = lo + quantiles * (hi - lo)
    return offsets if quantiles.ndim else float(offsets)


def nominal_value(key: str, base_conditions: dict) -> Optional[float]:
    """Magnitude of an input's nominal value; ``None`` for the titrant."""
    if key == TITRANT:
        return None
    return float(base_conditions[key].magnitude)


def input_name(key: str, input_labels: Optional[dict[str, str]]) -> str:
    """Name an input the way a message shown to the user should name it.

    Parameters
    ----------
    key : str
        Input key: ``TITRANT`` or a condition key.
    input_labels : dict[str, str] or None
        Display label per input key, as the interface writes it.

    Returns
    -------
    str
        The label when one is given. Otherwise 'the titrant' for the titrant and
        a neutral phrase for a condition, so a message never shows a dict key.
    """
    label = (input_labels or {}).get(key)
    if label:
        return label
    return 'the titrant' if key == TITRANT else 'this input'


class ReplicateMode(Enum):
    """How a perturbed fit treats the replicates.

    ``FOLLOW`` uses whatever the fit configuration already says. The other two
    override it for the sensitivity run only.
    """

    FOLLOW = 'follow'
    PER_REPLICA = 'per_replica'
    AVERAGE = 'average'


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
        Seed of the run: fixes the Sobol' scrambles and every fit's optimizer
        seed. ``None`` lets the run draw one, which it reports as
        ``SensitivityResult.seed_used``, so any run can be repeated.
    x_key : str or None
        HEATMAP only — input key swept along the X axis.
    y_key : str or None
        HEATMAP only — input key swept along the Y axis.
    n_steps : int
        HEATMAP only — grid resolution per axis (odd includes the 0 offset).
    ``replicate_mode`` decides how each perturbed fit treats the replicates:
    follow the fit configuration, force a per-replica fit, or average the
    active replicas. Replicates carry the measured signal scatter, so the
    choice changes what the resulting spread describes.
    """

    mode: SensitivityMode
    n_samples: int
    input_specs: dict[str, InputSpec]
    seed: Optional[int] = None
    x_key: Optional[str] = None
    y_key: Optional[str] = None
    n_steps: int = 11
    replicate_mode: ReplicateMode = ReplicateMode.FOLLOW


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
        Unperturbed representative Ka per key, in ``1/M``.
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
    floor : float or None
        The R² floor the flags refer to (the fit configuration's
        ``min_r_squared``).
    n_below_floor : int
        Fits kept although below the floor: among the ``A`` and ``B`` samples
        for SOBOL (``sample_r2``), among the cells for HEATMAP.
    baseline_fit : FitResult or None
        The unperturbed fit, made with the inputs as entered, that every
        perturbation starts from. It reports the fit an unperturbed sample
        gets, so the baseline and the samples share one estimator: it is the
        profile fit of the zero-offset sample, and the result carries no pool of
        its own, its multistart search only checking that the inputs as entered
        meet the R² floor. It records the replicates it used and left out, and
        every sample uses and is scored on the same replicates.
    sample_params : dict[str, np.ndarray] or None
        SOBOL only — parameter key → that parameter's best-fit value per
        sample, index-aligned with ``sample_ka`` (whose arrays are its Ka
        entries) and in the canonical units of ``FitResult.parameter_samples``;
        ``NaN`` where no fit could be produced.
    degenerate_keys : tuple[str, ...]
        Signal parameters the data determine only in combination, not one by
        one, at the baseline fit's binding constants (see
        :func:`_degenerate_keys`); empty when every fitted signal parameter is
        identifiable.
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
    floor: Optional[float] = None
    n_below_floor: int = 0
    baseline_fit: FitResult | None = None
    sample_params: dict[str, np.ndarray] | None = None
    degenerate_keys: tuple[str, ...] = ()
    sobol_rows_left_out: dict[str, int] | None = None
    stopped: bool = False


def perturbable_inputs(assay_type: AssayType, base_conditions: dict) -> list[tuple[str, str]]:
    """List the inputs that can be perturbed for an assay.

    Parameters
    ----------
    assay_type : AssayType
        The assay type (kept for API symmetry; classification is by
        dimensionality of the condition values).
    base_conditions : dict
        Assay conditions as passed to the assay constructor. Values that are
        :class:`pint.Quantity` are classified by dimensionality; non-Quantity
        values (e.g. the ``mode`` string) are skipped.

    Returns
    -------
    list[tuple[str, str]]
        Ordered ``(key, kind)`` pairs, matching the order the conditions are
        declared in, with ``TITRANT`` last, carrying kind
        ``'titrant'``; then each Quantity condition as ``'concentration'``
        (``M``) or ``'binding_constant'`` (``1/M``).
    """
    inputs: list[tuple[str, str]] = []
    for key, value in base_conditions.items():
        if not isinstance(value, Quantity):
            continue
        if value.is_compatible_with('M'):
            inputs.append((key, 'concentration'))
        elif value.is_compatible_with('1/M'):
            inputs.append((key, 'binding_constant'))
    inputs.append((TITRANT, 'titrant'))
    return inputs


def estimated_fit_count(sens_config: SensitivityConfig) -> int:
    """Number of perturbed fits a config will run.

    Excludes the baseline fit and the ``n_trials`` multiplier inside each fit.

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


def resolve_fit_config(fit_config: FitConfig, sens_config: SensitivityConfig) -> FitConfig:
    """Apply the run's replicate handling to *fit_config*.

    Parameters
    ----------
    fit_config : FitConfig
        The configuration the fit tab is using.
    sens_config : SensitivityConfig
        Supplies ``replicate_mode``.

    Returns
    -------
    FitConfig
        *fit_config* itself under ``FOLLOW``, otherwise a copy with
        ``per_replica`` set to match the requested mode.
    """
    mode = sens_config.replicate_mode
    if mode is ReplicateMode.FOLLOW:
        return fit_config
    return replace(fit_config, per_replica=mode is ReplicateMode.PER_REPLICA)


#: A profile fit of one signal costs about as much as this many L-BFGS-B runs
#: of a multi-start fit with the registry's default bounds: 49 ms against 18 ms
#: per run on the 12-point IDA demo data, 20 ms against 7 ms on 30 DBA points.
#: Narrower Ka bounds make a profile fit cheaper, so this errs on the high side.
_PROFILE_FIT_RUNS = 3


def estimated_optimizer_runs(sens_config: SensitivityConfig, fit_config: FitConfig, n_replicas: int = 1) -> int:
    """Work a configuration will take, counted in L-BFGS-B runs.

    The baseline runs the full ``n_trials`` multi-start, as the user's own fit
    does, and then the profile fit of a zero-offset sample, which it reports.
    Each perturbation is one profile fit, counted at the ``_PROFILE_FIT_RUNS``
    optimizer runs it costs. This is the number that reflects how long a run
    takes; :func:`estimated_fit_count` counts perturbations only.

    Parameters
    ----------
    sens_config : SensitivityConfig
        The sensitivity configuration to size.
    fit_config : FitConfig
        Supplies ``n_trials``, the multi-start depth of the baseline fit.
    n_replicas : int
        Replicas fitted per perturbation. A per-replica run fits each active
        replica separately, multiplying the work.

    Returns
    -------
    int
        Total optimizer runs, or their equivalent.
    """
    profile_fits = estimated_fit_count(sens_config) + 1  # the perturbations and the baseline's own
    return (fit_config.n_trials + profile_fits * _PROFILE_FIT_RUNS) * n_replicas


#: Keeps a quantile off the exact edges, where a truncated normal maps to its bound.
_QUANTILE_EPS = 1e-9


def _axis_bounds(sens_config: 'SensitivityConfig', key: str, base_conditions: dict, name: str) -> tuple[float, float]:
    """Offset range a heatmap axis sweeps, as fractions of nominal."""
    spec = sens_config.input_specs.get(key)
    if spec is None:
        return 0.0, 0.0
    return spec_bounds(spec, nominal_value(key, base_conditions), name)


#: Independent Sobol' scrambles behind each SOBOL design. Splitting the rows
#: into scrambles is what gives the jackknife independent replicates to measure
#: the sampling error from, and it costs accuracy: a Sobol' point set balances
#: each coordinate over its whole length, so N rows split into blocks are a
#: coarser design than N rows in one scramble. Measured on the Ishigami function
#: and a g-function, the indices pooled over eight scrambles of N/8 rows carry
#: about the error of one scramble of N/2 rows — half the design size, for the
#: eight replicates the intervals need. More scrambles give the jackknife more
#: degrees of freedom and so a narrower t quantile, fewer give each scramble
#: more rows. ``scripts/sobol_interval_coverage.py`` is the coverage study
#: behind this value and behind ``_SOBOL_SAMPLE_SIZES``: it reruns the interval
#: over many designs of functions whose indices are known and reports how often
#: each interval held its index.
_SOBOL_BLOCKS: int = 8

#: SOBOL sample sizes a run accepts. The smallest is the size at which an index
#: already carries about the error of one undivided scramble of half it, which is
#: the price the eight scrambles cost; below that the indices are too coarse to
#: rank the inputs by. ``scripts/sobol_interval_coverage.py`` measures both the
#: blocking price and how often the intervals hold their index at these sizes.
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
    index, offsets, seed = job
    return index, _fit_perturbed(
        state['ms'],
        state['assay_cls'],
        state['x_base'],
        state['base_conditions'],
        offsets,
        replace(state['fit_config'], seed=seed),
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
    seeds,
    *,
    max_workers,
    on_result,
    should_cancel,
):
    """Fit a batch of perturbations, in parallel when that is worthwhile.

    Results come back in the order of *offsets_list* however the work was
    scheduled, so a Sobol' row pairing or a heatmap cell index stays valid. Each
    job carries its own optimizer seed, so the answer does not depend on which
    worker ran it.

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
    jobs = [(index, offsets_list[index], seeds[index]) for index in range(len(offsets_list))]
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
            index, value = _run_job(state, job)
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

    The signals are untouched: the replicates are the measured signal scatter
    and stay intact so the configured replicate handling can use them.
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
    """Best fit of one perturbation → ``({parameter key: value}, R²)``.

    Every parameter is reported in its canonical registry unit, the unit
    ``FitResult.parameters`` and ``FitResult.parameter_samples`` carry.

    ``None`` when no fit could be produced. A perturbed design the profile
    cannot solve — a singular least-squares system, a model value that comes
    out non-finite — is one sample without a fit, which the caller records as
    NaN; the other thousands of samples are unaffected by it. Quality is not
    judged here: the caller flags the result against the R² floor.
    """
    perturbed = _perturbed_ms(ms, x_base, offsets)
    conditions = {k: (v * (1 + offsets[k]) if k in offsets else v) for k, v in base_conditions.items()}
    # The guard covers the solve, the fragile part: applying the offsets is
    # arithmetic on the values the caller validated, and a failure there is a
    # fault of the run rather than of one sample.
    try:
        return _fit_by_profile(perturbed, assay_cls, conditions, fit_config)
    except Exception:
        return None


def _fit_by_profile(ms, assay_cls, conditions, fit_config) -> tuple[dict[str, float], float] | None:
    """Best fit along the exact Ka profile, reported as :func:`fit_measurement_set` reports it.

    Each fitted signal — the averaged one, or every active replicate under
    ``per_replica`` — contributes its own best fit along the profile, and the
    one that best fits the average of the active replicates is reported. That
    is the rule :func:`~core.pipeline.fit_pipeline.fit_measurement_set_per_replica`
    applies to its replicas' best trials, scored against the average of the
    replicates it used, so the two agree on Ka and R² up to how closely a
    multi-start search reaches each replica's optimum.

    ``None`` when the model has no solution anywhere in the Ka bounds: the
    profile then scores nothing, and the coefficients at their lower bounds it
    falls back to are not a fit of these data.
    """
    template = ms.to_assay(assay_cls, conditions=conditions, use_average=True)
    if fit_config.per_replica:
        signals = [ms.to_assay(assay_cls, conditions=conditions, replica_id=rid) for rid in ms.active_replica_ids]
    else:
        signals = [template]
    candidates = [best_params_by_profile(assay, _resolve_bounds(assay, fit_config.custom_bounds)) for assay in signals]
    y_avg = template.y_data.magnitude
    rmse, r2 = np.array([calculate_fit_metrics(y_avg, template.forward_model(p).magnitude) for p in candidates]).T
    best = select_representative_index({'rmse': rmse, 'r_squared': r2})
    if not np.isfinite(r2[best]):
        return None
    return dict(zip(template.parameter_keys, candidates[best].tolist())), float(r2[best])


#: ``FitResult.metadata`` keys that describe a per-replicate pool's size.
_POOL_METADATA = ('pool_size', 'per_replica_n_passing')


def _reporting(result: FitResult, assay: BaseAssay, params: dict[str, float]) -> FitResult:
    """*result* reporting the fit *params* against *assay*'s averaged signal, without a pool.

    *params* are not a member of *result*'s multistart pool, so the pool, the
    representative index it carries and the metadata sizing it are dropped with
    it. *assay* averages the replicates *result* used, the ones *params* were
    fitted on, so the record of which replicates it used and left out stays.
    """
    vector = np.array([params[key] for key in assay.parameter_keys])
    rmse, r_squared, x_fit, y_fit = representative_view(assay, vector)
    return replace(
        result,
        metadata={key: value for key, value in result.metadata.items() if key not in _POOL_METADATA},
        parameters=_wrap_params_as_quantities(vector, assay),
        rmse=rmse,
        r_squared=r_squared,
        x_fit=x_fit,
        y_fit=y_fit,
        parameter_samples=None,
        quality_samples=None,
        representative_index=None,
    )


#: A signal parameter counts as degenerate when its unit direction keeps at
#: least this much of its length in the null space of the norm-scaled
#: coefficient design. A trade-off the data do not fix loads each parameter in
#: it at order 0.1 to 1; a parameter outside it picks up only numerical leakage
#: of order the null singular value over the smallest kept one, below 1e-5 at
#: the ``_RANK_RTOL`` cut-off.
_NULL_COMPONENT_TOL = 1e-3


def _degenerate_keys(
    assay: BaseAssay, bounds: dict[str, tuple[Quantity, Quantity]], binding_constants: dict[str, float]
) -> tuple[str, ...]:
    """Signal parameters the data determine only in combination at the given binding constants.

    With every binding constant held fixed, a signal made of offsets and
    coefficients is linear in them, one design column each. A direction in the
    null space of those columns, scaled to unit norm so coefficients of any
    magnitude weigh alike, changes the parameters without changing the signal,
    so of the parameters it involves only their combination is determined.
    Pinned parameters (equal lower and upper bound) are not fitted and stay out.

    Parameters
    ----------
    assay : BaseAssay
        Assay carrying the titrant grid and conditions to evaluate.
    bounds : dict[str, tuple[Quantity, Quantity]]
        Resolved bounds for every parameter; decide which ones are pinned.
    binding_constants : dict[str, float]
        Every binding-constant key → its value in 1/M.

    Returns
    -------
    tuple[str, ...]
        The degenerate keys in parameter order; empty when every fitted signal
        parameter is identifiable, or when the assay has a parameter other than
        a binding constant, signal offset or signal coefficient.
    """
    kinds = assay.registry_metadata.param_kinds
    keys = assay.parameter_keys
    signal_keys = [k for k in keys if kinds[k] is not ParamKind.BINDING_CONSTANT]
    if any(kinds[k] not in _LINEAR_KINDS for k in signal_keys):
        return ()
    fb = _float_bounds(assay, bounds)
    free = [k for k in signal_keys if fb[k][0] != fb[k][1]]
    if not free:
        return ()
    base = np.array([binding_constants.get(k, 0.0) for k in keys])
    columns = []
    for key in free:
        params = base.copy()
        params[keys.index(key)] = 1.0
        columns.append(assay.forward_model(params).magnitude)
    design = np.column_stack(columns)
    scale = np.linalg.norm(design, axis=0)
    scale[scale == 0] = 1.0
    _, singular, vt = np.linalg.svd(design / scale)
    rank = int(np.sum(singular > _RANK_RTOL * singular.max()))
    null_share = np.linalg.norm(vt[rank:], axis=0)
    return tuple(key for key, share in zip(free, null_share) if share > _NULL_COMPONENT_TOL)


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
        the rest of the run, so the zero-offset baseline and every perturbation
        fit and score exactly that set. Each perturbation refits a copy whose
        titrant grid carries the sampled offset; the replicates are passed
        through intact so ``sens_config.replicate_mode`` governs how they are
        used.
    assay_cls : type[BaseAssay]
        Concrete assay class to build each perturbed fit with.
    base_conditions : dict
        Baseline assay conditions (Quantity values in base units).
    fit_config : FitConfig
        Per-fit configuration. ``sens_config.replicate_mode`` may override its
        ``per_replica`` flag; every fit receives its own optimizer seed, derived
        from the run's root seed. Its ``min_r_squared`` gates the baseline fit
        only; perturbed fits are flagged against it.
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
        way, since every fit carries its own seed.
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
        ``_SOBOL_SAMPLE_SIZES``, no input set to vary,
        negative percent, a range reaching below zero, unknown key, HEATMAP with ``x_key == y_key``, a
        non-perturbable axis key or an axis reaching zero), an assay with no Ka keys (DYE_ALONE) or no
        exact Ka profile (:func:`~core.pipeline.profile.profile_supported`), or a
        baseline fit that does not clear the R² floor, just as the user's own
        fit would fail.
    FitCancelled
        If the run is cancelled before its baseline fit finishes, so there is no
        reference fit to report anything against.
    PerReplicaFitError
        If no replicate of the baseline fit could be fitted on its own. It
        carries the same per-replicate reasons an ordinary fit reports.
    SensitivityRunError
        If a perturbation fails in a way the per-fit guard does not cover. Its
        message is written for the user and can be shown as it stands.
    """
    x_base = np.asarray(ms.concentrations)
    fit_config = resolve_fit_config(fit_config, sens_config)
    workers = default_worker_count() if max_workers is None else max(1, int(max_workers))

    # Assay type / Ka keys come from an instance that is built, never fitted.
    probe_assay = ms.to_assay(assay_cls, conditions=base_conditions, use_average=True)
    assay_type: AssayType = probe_assay.assay_type
    metadata = ASSAY_REGISTRY[assay_type]
    ka_keys = metadata.log_scale_keys
    if not ka_keys:
        raise ValueError('This assay has no association constant to analyse, so sensitivity analysis does not apply.')
    if not profile_supported(assay_type):
        raise ValueError(
            f'The sensitivity analysis is not available for {metadata.display_name}. It re-fits your data thousands '
            'of times, and it needs a model whose best fit can be found exactly every time — which holds for a '
            'model with one binding constant, not for this one. Use the spread the fit itself reports to judge it.'
        )

    valid_keys = {k for k, _ in perturbable_inputs(assay_type, base_conditions)}

    # --- Validate the config before doing any real work ------------------
    size = sens_config.n_samples
    whole = isinstance(size, (int, np.integer)) and not isinstance(size, bool)
    if sens_config.mode is SensitivityMode.SOBOL and not (whole and size in _SOBOL_SAMPLE_SIZES):
        *smaller, largest = _SOBOL_SAMPLE_SIZES
        raise ValueError(
            f'The number of samples must be {", ".join(map(str, smaller))} or {largest}; '
            f'{sens_config.n_samples} was chosen.'
        )
    for key, spec in sens_config.input_specs.items():
        if key not in valid_keys:
            raise ValueError(
                'An uncertainty is set for an input this assay does not have, so the analysis cannot run. '
                'Set uncertainties only for the inputs this assay lists.'
            )
        name = input_name(key, input_labels)
        if spec.kind is SpecKind.SIGMA and spec.sigma < 0:
            raise ValueError(f'The uncertainty of {name} must not be negative.')
        if spec.kind is SpecKind.INTERVAL and spec.hi < spec.lo:
            raise ValueError(f'The upper bound for {name} must not be below its lower bound.')
        # Surfaces a titrant given an absolute spec, which has no nominal value.
        _to_fraction(0.0, spec.relative, nominal_value(key, base_conditions), name)
        if spec.kind is SpecKind.INTERVAL and spec_bounds(spec, nominal_value(key, base_conditions), name)[0] < -1.0:
            raise ValueError(
                f'The range for {name} reaches below zero, and a concentration or binding constant cannot be '
                f'negative. Raise its lower end to {"-100 %" if spec.relative else "0"} or more.'
            )
    if not any(spec.varies for spec in sens_config.input_specs.values()):
        raise ValueError('No input is set to vary — give at least one input a non-zero uncertainty.')

    if sens_config.mode is SensitivityMode.HEATMAP:
        for axis, axis_key in (('X', sens_config.x_key), ('Y', sens_config.y_key)):
            if axis_key not in valid_keys:
                raise ValueError(
                    f'The {axis} axis of the heatmap is set to an input this assay does not have, so the analysis '
                    'cannot run. Pick one of the inputs this assay lists.'
                )
        if sens_config.x_key == sens_config.y_key:
            raise ValueError('Heatmap X and Y axes must be two different inputs.')
        for axis_key in (sens_config.x_key, sens_config.y_key):
            spec = sens_config.input_specs.get(axis_key)
            name = input_name(axis_key, input_labels)
            if spec is not None and axis_reaches_zero(spec, nominal_value(axis_key, base_conditions), name):
                raise ValueError(
                    f'The heatmap axis for {name} reaches zero or below, and a concentration or binding constant '
                    'must stay positive. Use a σ below 50 % of the set value, or a range whose lower end is above zero.'
                )
        if sens_config.n_steps < 1:
            raise ValueError('Heatmap grid resolution must be at least 1.')

    # --- Baseline (unperturbed) fit --------------------------------------
    total = estimated_fit_count(sens_config) + 1  # +1 for the baseline
    done = 0

    # One root seed drives the whole run, drawn here when none was configured, so
    # every run can be repeated by feeding its `seed_used` back in. It is drawn
    # within MAX_SEED, the range the interface's Fixed seed box accepts, so a
    # reported seed can always be entered there.
    seed_used = int(np.random.SeedSequence().generate_state(1)[0] % (MAX_SEED + 1))
    seed_used = seed_used if sens_config.seed is None else sens_config.seed

    # Independent streams for the per-fit optimizer seeds and the Sobol'
    # scrambles. Pinning the scrambles alone would still let the multi-start
    # pool inside each fit wander, so a run repeats only when both are pinned.
    fit_stream, design_stream = np.random.SeedSequence(seed_used).spawn(2)
    fit_seeds = np.random.default_rng(fit_stream)

    def _fit_cfg() -> FitConfig:
        """Per-fit config carrying its own optimizer seed."""
        return replace(fit_config, seed=int(fit_seeds.integers(0, 2**32 - 1)))

    def _next_seeds(count: int) -> list:
        """Seeds for a batch, drawn before dispatch so order fixes the result."""
        return [int(fit_seeds.integers(0, 2**32 - 1)) for _ in range(count)]

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
    try:
        baseline_result = fit_measurement_set(ms, assay_cls, base_conditions, _fit_cfg(), should_cancel=should_cancel)
    except PerReplicaFitError as exc:
        # The per-replicate reasons say what went wrong; the caller shows them
        # as the ordinary fit does, rather than a bare 'did not converge'.
        raise PerReplicaFitError(
            f'{exc} There is no reference Ka for the analysis to compare against.',
            exc.failures,
        ) from exc
    done += 1
    if progress is not None:
        progress(done, total)
    if not baseline_result.success:
        raise ValueError(
            'The unperturbed (baseline) fit did not converge, so there is no reference Ka to compare against. '
            'Check the data, conditions, and bounds, and confirm a normal fit succeeds first.'
        )

    # Every later fit uses the replicates the baseline used, scored against
    # their average: a replicate the fit left out never enters a sample, and
    # every sample describes the same data.
    ms = ms.with_active(fit_replica_ids(baseline_result))
    probe_assay = ms.to_assay(assay_cls, conditions=base_conditions, use_average=True)

    # A perturbation always yields its best fit; the floor only flags it.
    floor = fit_config.min_r_squared
    # The baseline is the zero-offset sample: an estimate from one fitting
    # method beside a spread from another describes no distribution.
    zero_offset = _fit_perturbed(ms, assay_cls, x_base, base_conditions, {}, _fit_cfg())
    if zero_offset is None:
        raise ValueError(
            'The unperturbed (baseline) fit could not be worked out from the inputs as entered, so there is no '
            'reference Ka to compare against. Check the data, the conditions and the bounds, and confirm a normal '
            'fit succeeds first.'
        )
    baseline_result = _reporting(baseline_result, probe_assay, zero_offset[0])
    baseline_ka = {k: baseline_result.parameters[k].to('1/M').magnitude for k in ka_keys}
    degenerate_keys = _degenerate_keys(probe_assay, _resolve_bounds(probe_assay, fit_config.custom_bounds), baseline_ka)

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
            _next_seeds(len(offsets_list)),
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
        a_points, b_points = sobol_design(n_base, n_inputs, _SOBOL_BLOCKS, design_stream)
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

        sample_r2 = r2[:n_samples]
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
            sample_r2=sample_r2,
            floor=floor,
            n_below_floor=int(np.sum(sample_r2 < floor)),
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
        floor=floor,
        n_below_floor=int(np.sum(r2_grid < floor)),
        baseline_fit=baseline_result,
        degenerate_keys=degenerate_keys,
        stopped=counters['total'] < len(offsets_list),
    )
