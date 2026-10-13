"""Absolute variance budget of a binding constant under the stated error sources, and the elasticities beside it.

A SOBOL run of :func:`~core.pipeline.sensitivity.run_sensitivity` estimates,
per fitted binding constant, how the variance of log₁₀(Ka) splits over the
stated error sources (:class:`~core.pipeline.sensitivity.SobolEstimate`). This
module turns that estimate into the budget the Ka Sensitivity tab prints and
answers the questions asked of it, making no fit:

- :func:`budget_of` → :class:`Budget`: the variance of log₁₀(Ka) and one
  :class:`BudgetRow` per source — the variance it explains alone, the spread
  left once it is known exactly, and its elasticity.
- :func:`what_if` → :class:`WhatIf`: the spread if one source's uncertainty
  were reduced, by the first-order formula and, as a cross-check that assumes
  no model, by re-weighting the run's own samples.
- The elasticity of Ka to every input, from two refits a step either side of
  the entered value (:func:`elasticity_perturbations`, :func:`elasticities`),
  and the homogeneity identity those elasticities obey
  (:func:`homogeneity_sum`, with :func:`identity_applies` saying when it holds
  and :func:`homogeneity_tolerance` how closely refits can show it).

Layering: this module must not import from ``gui.*``; the runner imports it,
never the reverse.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Mapping, Optional

import numpy as np
from scipy.stats import truncnorm

from core.assays.registry import ASSAY_REGISTRY, ParamKind
from core.pipeline.fit_pipeline import FitConfig, FitResult, _resolve_bounds
from core.pipeline.inputs import (
    ADDITIONS,
    InputSpec,
    SpecKind,
    _to_fraction,
    nominal_value,
    perturbable_inputs,
    source_name,
    spec_bounds,
)
from core.pipeline.varpro import _LOG_KA_XTOL

if TYPE_CHECKING:
    from core.pipeline.sensitivity import SensitivityResult, SobolEstimate


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
        One row per reported source, in the order of
        :attr:`~core.pipeline.sensitivity.SensitivityResult.sources`.
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


def budget_of(
    estimate: SobolEstimate,
    sources: tuple[str, ...],
    elasticity: Mapping[str, float],
    powers: Mapping[str, Mapping[str, float]],
) -> Budget:
    """The budget of one binding constant from the Sobol' estimate of its log₁₀.

    Parameters
    ----------
    estimate : SobolEstimate
        :func:`~core.pipeline.sensitivity.sobol_indices_with_ci` on log₁₀ of
        the constant, one item per entry of *sources*.
    sources : tuple[str, ...]
        Reported source keys, in the order of the estimate's items.
    elasticity : Mapping[str, float]
        Input key → ``d ln Ka / d ln input`` of the constant (:func:`elasticities`).
    powers : Mapping[str, Mapping[str, float]]
        Source key → input key → the power that source moves the input by
        (:meth:`~core.pipeline.inputs.ErrorModel.powers`); the entry of
        ``ADDITIONS``, which is no single offset, is not read.
    """
    return Budget(
        variance=estimate.variance,
        variance_ci=estimate.variance_ci,
        rows=tuple(
            BudgetRow(
                source=source,
                variance=float(estimate.source_variance[i]),
                variance_ci=tuple(map(float, estimate.source_variance_ci[i])),
                sd_if_exact=float(estimate.sd_if_exact[i]),
                sd_if_exact_ci=tuple(map(float, estimate.sd_if_exact_ci[i])),
                # To first order a source moves Ka by the sum of what the
                # inputs it moves do, each by the power it moves it by.
                elasticity=None
                if source == ADDITIONS
                else sum(power * elasticity[moved] for moved, power in powers[source].items()),
            )
            for i, source in enumerate(sources)
        ),
    )


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
#: the cross-check is less certain than the first-order formula it checks (the
#: `what-if-accuracy` check measures the formula's relative error against a second
#: analysis at the reduced uncertainty at an rms of 5–15 %, the re-weighted
#: value's above 200 effective samples at 0.9–1.5 %).
_MIN_EFFECTIVE_SAMPLES = 200


def _density_ratio(
    spec: InputSpec, nominal: Optional[float], name: str, offsets: np.ndarray, ratio: float
) -> np.ndarray:
    """Density of a source reduced to *ratio* of its width over the density it was sampled from, at *offsets*.

    The sampled density is the one :func:`~core.pipeline.inputs.spec_fraction` draws from: a normal
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
    budget was built from (:attr:`~core.pipeline.sensitivity.SensitivityResult.sample_usable`) by
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


def elasticity_perturbations(base_conditions: Mapping) -> list[tuple[dict[str, float], None]]:
    """The refits behind the elasticities: one step up and one step down for every perturbable input.

    The inputs come in the order of :func:`~core.pipeline.inputs.perturbable_inputs`,
    and each refit is ``(input offsets, None)``, a perturbation as
    :func:`~core.pipeline.sensitivity.run_sensitivity` fits it, with no error
    of the additions.
    """
    return [
        ({key: sign * _ELASTICITY_STEP}, None) for key, _ in perturbable_inputs(base_conditions) for sign in (1.0, -1.0)
    ]


def elasticities(base_conditions: Mapping, ka: Mapping[str, np.ndarray]) -> dict[str, dict[str, float]]:
    """ka key → input key → ``d ln Ka / d ln input`` from the fits of :func:`elasticity_perturbations`, in their order."""
    keys = [key for key, _ in perturbable_inputs(base_conditions)]
    return {
        ka_key: {
            key: float(np.log(values[2 * i]) - np.log(values[2 * i + 1])) / _ELASTICITY_SPAN
            for i, key in enumerate(keys)
        }
        for ka_key, values in ka.items()
    }


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


def identity_applies(
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
