"""What the absolute Ka uncertainty budget delivers on a titration the truth of which is known.

Two things are asked of the budget the Ka Sensitivity tab prints. The first is
whether the variance it attributes to one error source is the variance that
source really carries: for a source common to every concentration of a
direct-binding assay the answer is a closed form, because scaling every
concentration by ``1 + e`` and dividing the binding constant by it is the same
least-squares problem, so ``log₁₀(Ka)`` moves by exactly ``-log₁₀(1 + e)`` and
its variance is a one-dimensional integral. The second is whether the what-if
line — what the spread would become if one source were improved — says what a
second analysis at the improved uncertainty actually gives.

Both rows run the application's own :func:`~core.pipeline.sensitivity.run_sensitivity`
in this process, one worker, so what is measured is what ships.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, replace
from typing import Any

import numpy as np
from scipy.integrate import quad
from scipy.stats import truncnorm

from core.assays import ASSAY_CLASSES
from core.assays.registry import AssayType
from core.pipeline.budget import homogeneity_sum, what_if
from core.pipeline.fit_pipeline import FitConfig
from core.pipeline.inputs import TITRANT, ErrorModel, InputSpec, SpecKind, perturbable_inputs, shared_key
from core.pipeline.sensitivity import SensitivityConfig, SensitivityMode, run_sensitivity
from validation.generate import dataset
from validation.scenarios import (
    SHARED_STOCK,
    Scenario,
    SharedEntry,
    SpecEntry,
    concentration_inputs,
)
from validation.score import guard, measurement_set

__all__ = [
    'BudgetCase',
    'exact_cases',
    'exact_row',
    'log_variance',
    'whatif_cases',
    'whatif_row',
]

#: Base sample size of the Sobol' design each case runs. It is the smallest the
#: application offers, which is the one a user waits for.
N_SAMPLES = 1024

#: Tail of the source's own distribution left outside the quadrature range. The
#: integrand is the density times a bounded function of it, so a tail of 1e-12
#: is below the last digit either side of the comparison carries.
_QUAD_TAIL = 1e-12


@dataclass(frozen=True)
class BudgetCase:
    """One titration whose uncertainty budget is measured, and how it is measured.

    Attributes
    ----------
    scenario : Scenario
        The family of titrations the dataset is drawn from; its
        :attr:`~validation.scenarios.Scenario.error_model` is what the analysis
        samples.
    n_samples : int
        Base sample size ``N`` of the Sobol' design.
    reduce_to : float or None
        What-if ratio: the largest source's uncertainty is asked about at this
        multiple of the stated one, and a second analysis is run there.
        ``None`` for a case that asks no what-if.
    """

    scenario: Scenario
    n_samples: int = N_SAMPLES
    reduce_to: float | None = None

    @property
    def id(self) -> str:
        """Stable key of this case — the key its rows are stored under."""
        parts = [self.scenario.id, f'N={self.n_samples}']
        if self.reduce_to is not None:
            parts.append(f'r={self.reduce_to:g}')
        return ','.join(parts)


def log_variance(sigma_pct: float) -> float:
    """``Var(log₁₀(1 + e))`` of a source of *sigma_pct* percent, by quadrature.

    The source is drawn from the distribution the application samples it from:
    a normal of ``sigma_pct / 100`` truncated below at ``-1``, so the perturbed
    input stays positive. The two moments are integrated between the extreme
    quantiles of that distribution, which brackets everything but a tail of
    :data:`_QUAD_TAIL` either side.
    """
    sigma = sigma_pct / 100.0
    law = truncnorm(a=-1.0 / sigma, b=np.inf, loc=0.0, scale=sigma)
    low, high = law.ppf(_QUAD_TAIL), law.ppf(1.0 - _QUAD_TAIL)
    mean = quad(lambda e: np.log10(1 + e) * law.pdf(e), low, high)[0]
    second = quad(lambda e: np.log10(1 + e) ** 2 * law.pdf(e), low, high)[0]
    return second - mean**2


def _analysis(data, errors: ErrorModel, case: BudgetCase, seed: int):
    """Run the Sobol' analysis of *data* under *errors*, in this process."""
    return run_sensitivity(
        measurement_set(data),
        ASSAY_CLASSES[AssayType[data.scenario.assay]],
        dict(data.conditions),
        FitConfig(per_replica=False),
        SensitivityConfig(
            mode=SensitivityMode.SOBOL,
            n_samples=case.n_samples,
            errors=errors,
            seed=seed,
        ),
        max_workers=1,
    )


def _row_of(budget, source: str):
    """The budget line of *source*."""
    return next(row for row in budget.rows if row.source == source)


def _bound_facts(result, ka_key: str) -> dict[str, Any]:
    """What of *result* ran to a bound of the Ka box, for one binding constant.

    ``on_bound`` is the baseline fit, ``n_on_bound`` the fits of the design. A
    row with either is one where the fits are the edge of the box rather than
    the values the stated uncertainties led to, and every check reading these
    rows has to say what it does with it.
    """
    return {
        'on_bound': bool(result.baseline_on_bound.get(ka_key, False)),
        'n_on_bound': int(result.n_on_bound.get(ka_key, 0)),
    }


def exact_row(case: BudgetCase, seed: int) -> dict[str, Any]:
    """Whether the budget's interval for a shared source holds the variance that source really carries.

    The case states one source shared by every concentration of a
    direct-binding assay. Scaling every concentration by ``1 + e`` and every
    entered binding constant by ``1 / (1 + e)`` leaves the least-squares
    problem unchanged with every fitted constant divided by ``1 + e``, so
    ``log₁₀(Ka)`` moves by ``-log₁₀(1 + e)`` exactly and the variance the
    source explains is :func:`log_variance` of its stated percent — no
    approximation, and a first-order index equal to the total one.

    The identity holds where every fit of the analysis lies strictly inside the
    Ka box. A fit that ran to a bound reports the edge of the box: the output is
    constant there, so the source's real variance is no longer
    :func:`log_variance` of its percent and the row says nothing about the
    claim. Each row therefore carries whether the baseline ran there and how
    many of the design's fits did, which is what
    :func:`~validation.checks.source_variance` reads to judge the rows the truth
    applies to.

    Returns
    -------
    dict
        ``truth``, and per binding constant whether the interval holds it, the
        estimate and its interval, the gap between the total and the
        first-order index, the homogeneity sum plus one, which is zero where
        the refits and the model agree, and the fits that ran to a Ka bound.
    """
    started = time.perf_counter()
    scenario = case.scenario
    source = shared_key(scenario.shared_sources[0].name)
    truth = log_variance(scenario.shared_sources[0].sigma)
    data = dataset(scenario, seed)

    def work() -> dict[str, Any]:
        result = _analysis(data, scenario.error_model, case, seed)
        kinds = dict(perturbable_inputs(data.conditions))
        facts = {}
        for ka_key in result.ka_keys:
            row = _row_of(result.budget[ka_key], source)
            low, high = row.variance_ci
            facts[ka_key] = {
                'covers': bool(low <= truth <= high),
                'variance': row.variance,
                'low': low,
                'high': high,
                'st_minus_s1': float(result.sobol_st[ka_key][source] - result.sobol_s1[ka_key][source]),
                'sum_rule': homogeneity_sum(result.elasticity[ka_key], kinds) + 1.0,
                **_bound_facts(result, ka_key),
            }
        return {'truth': truth, 'ka': facts, 'n_success': result.n_success, 'n_total': result.n_total}

    row = guard(work)
    row['t_total'] = time.perf_counter() - started
    return row


def _narrowed(spec: InputSpec, ratio: float) -> InputSpec:
    """*spec* at *ratio* of its width: a standard deviation scaled, a range shrunk about its centre.

    That is the reduced distribution :func:`~core.pipeline.budget.what_if`
    re-weights the samples towards, so the second analysis and the cross-check
    answer about the same source.
    """
    if spec.kind is SpecKind.SIGMA:
        return replace(spec, sigma=spec.sigma * ratio)
    middle, half = (spec.lo + spec.hi) / 2, ratio * (spec.hi - spec.lo) / 2
    return replace(spec, lo=middle - half, hi=middle + half)


def _reduced(errors: ErrorModel, source: str, ratio: float) -> ErrorModel:
    """*errors* with *source*'s stated uncertainty reduced to *ratio* of its width."""
    shared = tuple(
        replace(s, sigma_pct=s.sigma_pct * ratio) if shared_key(s.name) == source else s for s in errors.shared
    )
    specs = {key: _narrowed(spec, ratio) if key == source else spec for key, spec in errors.specs.items()}
    return replace(errors, specs=specs, shared=shared)


def whatif_row(case: BudgetCase, seed: int) -> dict[str, Any]:
    """What the what-if line promises against what a second analysis at the reduced uncertainty gives.

    The largest source of the first binding constant's budget is the one asked
    about, since that is the one a user would work on. Both analyses run on the
    same dataset at the same seed, so the design is the same and the difference
    between them is the source's stated uncertainty alone.

    A fit that ran to a Ka bound is the edge of the box rather than a value the
    data chose, and it sits decades from the rest, so both the spread the
    what-if starts from and the one the second analysis measures carry it. Each
    row records whether the first analysis' baseline ran there and how many of
    its design's fits did, so the errors of the rows with none can be read
    apart from the rest.

    Returns
    -------
    dict
        The source asked about, and per binding constant the relative error of
        the first-order formula and of the re-weighted cross-check against the
        second analysis' own spread, with the effective sample size the
        cross-check carried and the fits that ran to a Ka bound.
    """
    started = time.perf_counter()
    scenario = case.scenario
    ratio = case.reduce_to
    data = dataset(scenario, seed)

    def work() -> dict[str, Any]:
        errors = scenario.error_model
        result = _analysis(data, errors, case, seed)
        first = result.ka_keys[0]
        source = max(result.budget[first].rows, key=lambda row: row.variance).source
        reduced = _analysis(data, _reduced(errors, source, ratio), case, seed)
        facts = {}
        for ka_key in result.ka_keys:
            answer = what_if(result, ka_key, source, ratio)
            measured = reduced.budget[ka_key].sd
            facts[ka_key] = {
                'sd': answer.sd,
                'sd_reweighted': answer.sd_reweighted,
                'sd_measured': measured,
                'formula_err': answer.sd / measured - 1.0 if measured > 0 else None,
                'reweighted_err': (
                    None if answer.sd_reweighted is None or not measured > 0 else answer.sd_reweighted / measured - 1.0
                ),
                'effective': answer.effective_samples,
                **_bound_facts(result, ka_key),
            }
        return {'source': source, 'ka': facts, 'n_success': result.n_success, 'n_total': result.n_total}

    row = guard(work)
    row['t_total'] = time.perf_counter() - started
    return row


def exact_cases() -> list[BudgetCase]:
    """Direct binding in both directions, at two regimes, with one source behind both concentrations.

    Each input carries three percent of its own and one source of four percent
    moves the fixed concentration and the titrant together. Direct binding is
    where the identity bites: a source common to every concentration is exactly
    the direction the data cannot see, so the variance it explains is the
    closed form and nothing else.
    """
    keys = ('fixed_conc', TITRANT)
    return [
        BudgetCase(
            scenario=Scenario(
                assay=assay,
                regime=regime,
                n_points=12,
                noise=0.005,
                specs=tuple(SpecEntry(key, sigma=3.0) for key in keys),
                shared_sources=(SharedEntry(SHARED_STOCK, 4.0, keys),),
            )
        )
        for assay in ('DBA_HtoD', 'DBA_DtoH')
        for regime in (10.0, 1000.0)
    ]


def whatif_cases() -> list[BudgetCase]:
    """Three assays whose concentrations each carry five percent, the largest source improved to 40 %.

    Five percent on every concentration leaves no source dominant enough for
    the answer to be a foregone conclusion, and forty percent is a real
    improvement — a stock made up by weighing rather than by eye — without
    emptying the re-weighted cross-check of samples.
    """
    return [
        BudgetCase(
            scenario=Scenario(
                assay=assay,
                regime=10.0,
                n_points=12,
                noise=0.005,
                specs=tuple(SpecEntry(key, sigma=5.0) for key in concentration_inputs(assay)),
            ),
            reduce_to=0.4,
        )
        for assay in ('IDA', 'GDA', 'DBA_DtoH')
    ]
