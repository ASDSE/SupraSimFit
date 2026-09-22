"""One entry per claim the documents make, with the scenarios it rests on and the criterion it must meet.

A check names the cases it runs, the function that turns one stored row into
the numbers it judges, and the criterion those numbers are read against
(:mod:`validation.criteria`). Metric names follow two conventions the rest of
the package reads:

``~name``
    Reported, never judged. A rate or a distribution the reader wants beside
    the claim but that no criterion applies to.
``cov.KEY``
    The judged coverage of a binding constant's interval: how often it holds
    the truth, over every draw. That is the property the level promises, and
    an interval that runs to a Ka bound covers that side by telling the user
    the data do not limit Ka there. Beside it the tables report
    ``~closed_cov.KEY`` over the draws closed on both sides, ``~open.KEY``,
    ``~split.KEY``, ``~limited.KEY`` and ``~width.KEY``. None of those five is
    judged: conditioning on closure keeps the draws whose noise happened to
    make the profile steep, which is a different population from the one the
    level is about.

A check with ``derived_from`` set computes nothing. It reads the rows of the
check it names and asks a different question of them, so two claims that rest
on the same fits are stated separately without fitting twice.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Sequence

from core.pipeline.diagnostics import DIAGNOSTIC_LEVEL, Verdict
from validation import budget, legacy, reference, scenarios, sobol
from validation.criteria import AGREEMENT, COVERAGE, FALSE_ALARM, NULL_RATE, Criterion
from validation.score import joint_region_row, score

__all__ = ['CHECKS', 'Check', 'case_by_id', 'matches', 'matching_cases']

_COVERAGE_REASON = (
    'The judged rate is the coverage over every draw — how often the interval holds the true '
    'binding constant, which is what a 95 % level promises. An interval that runs to a Ka bound '
    'covers that side by telling the user the data do not limit Ka there, and the app reports it '
    "as such, so it counts as the user reads it. Bradley's liberal criterion calls a 95 % "
    'interval acceptable at a coverage of 0.925 or better, and only the anti-conservative side '
    'can fail: exact limits below 0.95 are a fail, limits at or above 0.925 a pass, a pass above '
    '0.975 is labelled conservative, and anything else is undecided. Beside the judged rate the '
    'tables report the coverage over the closed draws alone, the fractions open, split and '
    'bound-limited, and the median width — described, never judged, because conditioning on '
    'closure keeps the draws whose noise made the profile steep.'
)

_NULL_REASON = (
    'A test run at the 5 % level should reject about 5 % of data the model does describe. '
    "Bradley's liberal criterion calls a rate of 0.075 or less acceptable, and a test errs on "
    'the safe side when it is quiet: exact limits above 0.05 are a fail, limits at or below 0.075 '
    'a pass, a pass below 0.025 is labelled conservative, and anything else is undecided.'
)


@dataclass(frozen=True)
class Check:
    """One claim, the cases it rests on, and how a row is read.

    Attributes
    ----------
    name : str
        How the check is named on the command line and in the store.
    claim : str
        What a pass means, in one sentence.
    metrics : Callable[[dict], dict]
        One stored row → the numbers judged or reported for it. A boolean is a
        rate, a float a distribution, and ``None`` means the row says nothing
        about that number and is left out of it.
    cases : tuple
        What is run, each carrying a stable ``id``: a
        :class:`~validation.scenarios.Scenario`, or a
        :class:`~validation.sobol.SobolCase`.
    row : Callable[[case, int], dict] | None
        Computes one row from a case and a seed. ``None`` for a derived check.
    criterion : Criterion | None
        What every judged rate is read against. ``None``: the check reports
        its numbers and judges none of them.
    criterion_reason : str
        Why that criterion, in the reader's terms.
    stages : tuple[int, ...]
        Seeds per case, in order. Every case runs the first stage; a case goes
        on to the next unless every judged rate of it has passed.
    derived_from : str | None
        The check whose rows this one reads instead of computing its own.
    """

    name: str
    claim: str
    metrics: Callable[[dict[str, Any]], dict[str, Any]]
    cases: tuple[Any, ...] = ()
    row: Callable[[Any, int], dict[str, Any]] | None = None
    criterion: Criterion | None = None
    criterion_reason: str = ''
    stages: tuple[int, ...] = (100, 200, 400)
    derived_from: str | None = None


def case_by_id(check: Check) -> dict[str, Any]:
    """Every case of *check*, by its id."""
    return {case.id: case for case in check.cases}


def matches(case_id: str, patterns: Sequence[str] | None) -> bool:
    """Whether *case_id* is selected by *patterns*, each a regular expression searched in the id.

    Any match selects, and no pattern at all selects everything.
    """
    return not patterns or any(re.search(pattern, case_id) for pattern in patterns)


def matching_cases(check: Check, patterns: Sequence[str] | None) -> tuple[Any, ...]:
    """The cases of *check* whose id matches *patterns* — all of them when none is given."""
    return tuple(case for case in check.cases if matches(case.id, patterns))


# --------------------------------------------------------------------------
# Reading a row
# --------------------------------------------------------------------------


def _interval_metrics(row: dict[str, Any], field_name: str, prefix: str = '', judged: bool = True) -> dict[str, Any]:
    """What every binding constant's interval in *field_name* says, judged or reported.

    The coverage over every draw is the judged series. The coverage over the
    draws closed on both sides, the open, split and bound-limited fractions
    and the width are reported beside it. With *judged* false every series is
    reported, which is how the conditional interval appears beside a reported
    one.
    """
    out: dict[str, Any] = {}
    cov = f'{prefix}cov' if judged else f'~{prefix}cov'
    for key, facts in (row.get(field_name) or {}).items():
        out[f'{cov}.{key}'] = facts['covers']
        out[f'~{prefix}closed_cov.{key}'] = None if facts['open'] else facts['covers']
        out[f'~{prefix}open.{key}'] = facts['open']
        out[f'~{prefix}split.{key}'] = facts['split']
        out[f'~{prefix}limited.{key}'] = facts['limited']
        out[f'~{prefix}width.{key}'] = facts['width']
    return out


def _fit_metrics(row: dict[str, Any]) -> dict[str, Any]:
    """What the fit behind an interval met: an active coefficient bound, and an input on its range.

    A signal parameter the data determine sitting on a bound is a case the F
    test's derivation does not foresee, so how often it happens belongs beside
    every coverage rate. ``at_edge`` says nothing where no input could move and
    is left out there.
    """
    return {
        '~bound_active': row.get('bound_active'),
        '~at_edge': row.get('at_edge') if row.get('z') else None,
    }


def conditional_coverage(row: dict[str, Any]) -> dict[str, Any]:
    """The interval at the inputs as entered, which is the reported one when nothing may move."""
    return {**_interval_metrics(row, 'cond'), **_fit_metrics(row)}


def aware_coverage(row: dict[str, Any]) -> dict[str, Any]:
    """The reported interval, with the conditional one beside it."""
    return {
        **_interval_metrics(row, 'aware'),
        **_interval_metrics(row, 'cond', prefix='cond_', judged=False),
        **_fit_metrics(row),
    }


def _noise_metrics(row: dict[str, Any]) -> dict[str, Any]:
    """The share of the variance the replicates showed to grow with the signal.

    Zero is a fit weighted equally and one a fit weighted by the inverse square
    of the signal, so the distribution of this number says what the weighting
    did on a grid, beside what it did to the coverage. A single titration shows
    no law and reports nothing here.
    """
    return {'~noise_share': row.get('noise_share')}


def noise_law_conditional(row: dict[str, Any]) -> dict[str, Any]:
    """The conditional interval of a weighted fit, with the share the law read beside it."""
    return {**conditional_coverage(row), **_noise_metrics(row)}


def noise_law_aware(row: dict[str, Any]) -> dict[str, Any]:
    """The reported interval of a weighted fit, with the share the law read beside it."""
    return {**aware_coverage(row), **_noise_metrics(row)}


def _rejects(p_value: float | None) -> bool | None:
    """Whether a test rejects at the level the application runs it at."""
    return None if p_value is None else bool(p_value < DIAGNOSTIC_LEVEL)


def conflict_rate(row: dict[str, Any]) -> dict[str, Any]:
    """Whether the conflict statistic calls the entered inputs significant, over the fits that have one."""
    return {'reject': _rejects(row.get('conflict_p')), '~q': row.get('conflict_q'), '~k': row.get('conflict_k')}


def _misfit_rejects(row: dict[str, Any], kind: str) -> bool | None:
    """Whether the misfit test of *kind* rejects, or ``None`` when the fit ran another test."""
    return _rejects(row.get('misfit_p')) if row.get('misfit_kind') == kind else None


def lof_rate(row: dict[str, Any]) -> dict[str, Any]:
    """Whether the replicate lack-of-fit F test rejects."""
    return {'reject': _misfit_rejects(row, 'lack_of_fit')}


def runs_rate(row: dict[str, Any]) -> dict[str, Any]:
    """Whether the runs test rejects."""
    return {'reject': _misfit_rejects(row, 'runs')}


def misfit_power(row: dict[str, Any]) -> dict[str, Any]:
    """Both misfit tests and the verdict, on data the model does not describe."""
    return {
        '~lof_reject': _misfit_rejects(row, 'lack_of_fit'),
        '~runs_reject': _misfit_rejects(row, 'runs'),
        '~any_flag': None if row.get('verdict') is None else row['verdict'] != Verdict.CONSISTENT.value,
    }


def false_alarm(row: dict[str, Any]) -> dict[str, Any]:
    """Whether a fit of data the model describes is nonetheless blamed on the model or the inputs."""
    verdict = row.get('verdict')
    if verdict is None:
        return {'alarm': None}
    blamed = (Verdict.MODEL_INADEQUATE.value, Verdict.INPUTS_CONFLICT.value)
    return {'alarm': verdict in blamed, '~inputs_explain': verdict == Verdict.INPUTS_EXPLAIN.value}


def runtime(row: dict[str, Any]) -> dict[str, Any]:
    """How long the fit took, in seconds."""
    return {'~t_fit': row.get('t_fit'), '~t_total': row.get('t_total')}


def agreement(row: dict[str, Any]) -> dict[str, Any]:
    """Whether the engine's interval and the independent one place the same edges."""
    out: dict[str, Any] = {'~no_reference': row.get('no_reference')}
    for key, agrees in (row.get('agrees') or {}).items():
        out[f'agrees.{key}'] = agrees
        out[f'~apart.{key}'] = row['apart'][key]
    return out


def joint_region(row: dict[str, Any]) -> dict[str, Any]:
    """Whether the joint region of the pair holds the true pair, beside the two intervals.

    The judged rate is over every draw. A region whose shadow reaches a Ka
    bound is unbounded in that direction and holds the pair by saying so, as
    an open interval does; the fraction that are unbounded is reported beside
    the rate, with the coverage over the bounded regions alone.
    """
    if row.get('inside') is None:
        return {}
    return {
        'cov.joint': row['inside'],
        '~closed_cov.joint': None if row['open'] else row['inside'],
        '~open.joint': row['open'],
        '~both_intervals': row['both_intervals'],
        '~excess': row['excess'],
    }


def scatter_kind(case_id: str) -> str:
    """Which scatter a pooling case carries, read off its id.

    ``proportional`` for noise that grows with the signal, ``shared`` for four
    replicates that share one smooth departure from the model, and
    ``independent`` for the constant-variance noise the F test assumes.
    """
    fields = case_id.split(',')
    if 'prop' in fields:
        return 'proportional'
    if any(field.startswith('sine=') for field in fields):
        return 'shared'
    return 'independent'


def pooling(row: dict[str, Any]) -> dict[str, Any]:
    """The interval of the replicates averaged, against their points pooled and against equal weights.

    Every series names the scatter the replicates carry, so the three kinds are
    separate rows of the table rather than one rate read off three different
    experiments. The averaged and the pooled interval both carry the law the
    replicates show, so what stands between them is the pooling; the
    ``equal_`` series is the same average with every point counted equally, so
    what stands between it and the averaged one is the weighting.
    """
    out: dict[str, Any] = {'~no_reference': row.get('no_reference')}
    kind = scatter_kind(row['case'])
    for key, covers in (row.get('engine_covers') or {}).items():
        out[f'~averaged_cov.{kind}.{key}'] = covers
        out[f'~pooled_cov.{kind}.{key}'] = row['ref_covers'][key]
        out[f'~equal_cov.{kind}.{key}'] = row['equal_covers'][key]
        out[f'~averaged_width.{kind}.{key}'] = row['engine_width'][key]
        out[f'~pooled_width.{kind}.{key}'] = row['ref_width'][key]
        out[f'~equal_width.{kind}.{key}'] = row['equal_width'][key]
    return out


def before_after(row: dict[str, Any]) -> dict[str, Any]:
    """The present interval and the previous release's range, on the same dataset."""
    out: dict[str, Any] = {'~no_fit': row.get('no_fit')}
    for key, covers in (row.get('covers') or {}).items():
        out[f'~cov.{key}'] = covers
        out[f'~width.{key}'] = row['width'][key]
        out[f'~previous_cov.{key}'] = row['previous_covers'].get(key)
        out[f'~previous_width.{key}'] = row['previous_width'].get(key)
    return out


def sobol_coverage(row: dict[str, Any]) -> dict[str, Any]:
    """Whether the jackknife interval holds each analytically known index, and how far the estimate lies from it.

    ``~err.{label}`` is the signed error of one design. Its median over the
    designs is the estimator's bias and its root mean square the scatter the
    interval has to cover, so the two numbers the interval is judged against
    are printed beside the coverage rate.
    """
    out: dict[str, Any] = {}
    for label, covered in (row.get('cov') or {}).items():
        out[f'cov.{label}'] = covered
        out[f'~halfwidth.{label}'] = row['halfwidth'][label]
        out[f'~err.{label}'] = row['err'][label]
    return out


def dilution_ignored(row: dict[str, Any]) -> dict[str, Any]:
    """What a diluted titration fitted with constant totals gives: the coverage and the signed error.

    Nothing is judged. The interval is not claimed to hold a truth the model
    the fit used does not describe; what the rows say is how far the estimate
    lands from it and how often the interval still reaches it, which is the
    price of leaving the titrant stock out.
    """
    out: dict[str, Any] = {}
    for key, facts in (row.get('cond') or {}).items():
        out[f'~cov.{key}'] = facts['covers']
        out[f'~width.{key}'] = facts['width']
    for key, error in (row.get('err') or {}).items():
        out[f'~err.{key}'] = error
    return {**out, **_fit_metrics(row)}


def _on_bound(facts: dict[str, Any]) -> bool:
    """Whether any fit behind this binding constant's row ran to a bound of the Ka box.

    The baseline or any fit of the design. On a bound the fit reports the edge
    of the box instead of a value the data chose, and the output is constant
    there, so what the budget splits is no longer the movement of the inputs.
    """
    return bool(facts.get('on_bound', False) or facts.get('n_on_bound', 0))


def source_variance(row: dict[str, Any]) -> dict[str, Any]:
    """Whether the budget's interval for the shared source holds the variance the identity gives it.

    The identity the truth rests on — scale every concentration by ``1 + e``
    and the fitted constant is divided by it — holds only where every fit of
    the analysis lies strictly inside the Ka box. Where one ran to a bound the
    output is constant there instead, the variance the source really carries is
    not the one the quadrature gives, and the row is left out of the judged
    rate; ``~on_bound`` is the share of rows that were.

    ``~st_minus_s1`` is the gap between the total and the first-order index of
    that source, which the identity puts at zero, and ``~sum_rule`` is the
    homogeneity sum plus one, which it puts at zero as well: both say whether
    the refits behind the budget are the refits the algebra describes.
    """
    out: dict[str, Any] = {'~truth': row.get('truth')}
    for key, facts in (row.get('ka') or {}).items():
        on_bound = _on_bound(facts)
        out[f'cov.{key}'] = None if on_bound else facts['covers']
        out[f'~on_bound.{key}'] = on_bound
        out[f'~variance.{key}'] = facts['variance']
        out[f'~st_minus_s1.{key}'] = facts['st_minus_s1']
        out[f'~sum_rule.{key}'] = facts['sum_rule']
    return out


def whatif_accuracy(row: dict[str, Any]) -> dict[str, Any]:
    """How far the what-if line lands from a second analysis run at the reduced uncertainty.

    Both errors are relative to that second analysis' own spread, so a reader
    sees what the printed sentence would have been wrong by. A fit that ran to
    a bound of the Ka box reports that edge, decades from the rest, and both
    spreads carry it, so the errors are reported a second time over the rows
    where no fit did (``~formula_err_clean``, ``~reweighted_err_clean``) beside
    the share of rows where one did.
    """
    out: dict[str, Any] = {}
    for key, facts in (row.get('ka') or {}).items():
        clean = not _on_bound(facts)
        out[f'~formula_err.{key}'] = facts['formula_err']
        out[f'~reweighted_err.{key}'] = facts['reweighted_err']
        out[f'~formula_err_clean.{key}'] = facts['formula_err'] if clean else None
        out[f'~reweighted_err_clean.{key}'] = facts['reweighted_err'] if clean else None
        out[f'~on_bound.{key}'] = not clean
        out[f'~effective.{key}'] = facts['effective']
    return out


def sobol_error(row: dict[str, Any]) -> dict[str, Any]:
    """The error of each index on one design; its root-mean-square is the price of blocking."""
    return {f'~err.{label}': value for label, value in (row.get('err') or {}).items()}


# --------------------------------------------------------------------------
# The registry
# --------------------------------------------------------------------------

CHECKS: dict[str, Check] = {
    'conditional-coverage': Check(
        name='conditional-coverage',
        claim=(
            'The interval reported when every entered input is taken as exact holds the true binding '
            'constant as often as its 95 % level says, across every assay, regime, design and noise '
            'size, over every draw — with the fraction of draws in which the data limit Ka on both '
            'sides beside it.'
        ),
        metrics=conditional_coverage,
        cases=tuple(scenarios.owner_grid()),
        row=score,
        criterion=COVERAGE,
        criterion_reason=_COVERAGE_REASON,
    ),
    'two-ka-weak': Check(
        name='two-ka-weak',
        claim=(
            'What the interval does for the two stepwise models in the weak regime, where the host is '
            'dark and the two binding constants are separated by one to three orders of magnitude: how '
            'often the interval holds a constant, and how often the data limit it on both sides at all.'
        ),
        metrics=conditional_coverage,
        cases=tuple(scenarios.two_ka_weak_grid()),
        row=score,
        criterion=COVERAGE,
        criterion_reason=_COVERAGE_REASON,
    ),
    'input-aware-coverage': Check(
        name='input-aware-coverage',
        claim=(
            'The reported interval, which lets every entered input move within the uncertainty stated '
            'for it, holds the true binding constant as often as its level says when the inputs are '
            'entered exactly as wrongly as stated.'
        ),
        metrics=aware_coverage,
        cases=tuple(scenarios.input_aware_grid()),
        row=score,
        criterion=COVERAGE,
        criterion_reason=_COVERAGE_REASON,
    ),
    'range-spec-coverage': Check(
        name='range-spec-coverage',
        claim=(
            'The same holds when an input is stated as a range rather than a standard deviation, with the '
            'entered value drawn uniformly over that range.'
        ),
        metrics=aware_coverage,
        cases=tuple(scenarios.range_spec_grid()),
        row=score,
        criterion=COVERAGE,
        criterion_reason=_COVERAGE_REASON,
    ),
    'conflict-null': Check(
        name='conflict-null',
        claim=(
            'On the grid conflict-power runs, the check on the entered inputs calls them in conflict '
            'about as often as its level allows when they are entered exactly as wrongly as stated, '
            'over the fits whose data inform an input direction at all.'
        ),
        metrics=conflict_rate,
        cases=tuple(scenarios.conflict_grid((1.0,))),
        criterion=NULL_RATE,
        criterion_reason=_NULL_REASON,
        derived_from='input-aware-coverage',
    ),
    'conflict-power': Check(
        name='conflict-power',
        claim=(
            'How often the same check fires when the inputs are entered two, three and five times as '
            'wrongly as stated, on the grid its null rate is measured on — what a user gains from it, '
            'reported rather than required.'
        ),
        metrics=conflict_rate,
        cases=tuple(scenarios.conflict_grid((2.0, 3.0, 5.0))),
        row=score,
        stages=(200,),
    ),
    'lof-null': Check(
        name='lof-null',
        claim=(
            'The replicate lack-of-fit F test calls the model inadequate about as often as its level '
            'allows on replicated data the model does describe.'
        ),
        metrics=lof_rate,
        cases=tuple(scenarios.lof_null_grid()),
        row=score,
        criterion=NULL_RATE,
        criterion_reason=_NULL_REASON,
    ),
    'runs-null': Check(
        name='runs-null',
        claim=(
            'The runs test on the residuals fires about as often as its level allows on single '
            'titrations the model does describe.'
        ),
        metrics=runs_rate,
        cases=tuple(scenarios.runs_null_grid()),
        row=score,
        criterion=NULL_RATE,
        criterion_reason=(
            _NULL_REASON + ' The runs test counts sign changes, a statistic with few distinct values at '
            'short titrations, so its realised level lands on coarse steps and a case of it is more '
            'often left undecided than the F test is.'
        ),
    ),
    'misfit-power': Check(
        name='misfit-power',
        claim=(
            'How often the misfit tests see a departure the model cannot follow: a smooth sine of 2 % of '
            'the signal range shared by every replicate, and a titrant series entered 15 % off.'
        ),
        metrics=misfit_power,
        cases=tuple(scenarios.misfit_power_grid()),
        row=score,
        stages=(200,),
    ),
    'verdict-false-alarm': Check(
        name='verdict-false-alarm',
        claim=(
            'A fit of data the model describes, with the inputs entered as wrongly as stated, is blamed '
            'on the model or on the inputs in at most one fit in seven.'
        ),
        metrics=false_alarm,
        criterion=FALSE_ALARM,
        criterion_reason=(
            'The verdict is the first of several tests that fires, so its false-alarm rate is the union '
            'of their levels rather than any one of them: two misfit tests and the conflict statistic at '
            '5 % each bound it near 15 %. It is an upper limit and not a level, so exact limits at or '
            'below 0.15 are a pass and limits above it a fail, with nothing to call conservative: a '
            'verdict that never fires on good data is what is wanted, and the power checks say whether '
            'it still fires on bad.'
        ),
        derived_from='input-aware-coverage',
    ),
    'robustness': Check(
        name='robustness',
        claim=(
            'The reported interval still holds its level when the entries are half as wrong as stated, '
            'when the truth puts a signal coefficient on its bound (a dark free dye and no offset), and '
            'when the noise scales with the signal instead of being constant.'
        ),
        metrics=aware_coverage,
        cases=tuple(scenarios.robustness_grid()),
        row=score,
        criterion=COVERAGE,
        criterion_reason=(
            _COVERAGE_REASON + " Each of these strains leaves the interval's premise intact — the stated "
            'uncertainty still covers the entry error, and the noise is still independent between points '
            '— so the same criterion applies as on the plain grid.'
        ),
    ),
    'robustness-strained': Check(
        name='robustness-strained',
        claim=(
            'What the interval does when its premise is broken: entries twice as wrong as stated, and one '
            'stock error shared by two inputs that were each stated on their own. Described, not required.'
        ),
        metrics=aware_coverage,
        cases=tuple(scenarios.robustness_strained_grid()),
        row=score,
        stages=(200,),
    ),
    'reference-agreement': Check(
        name='reference-agreement',
        claim=(
            'The engine places both edges of its interval where an independent profile — its own design, '
            'its own search and its own root finding — places them, to a ten-thousandth of a decade of Ka.'
        ),
        metrics=agreement,
        cases=tuple(scenarios.reference_grid()),
        row=reference.agreement_row,
        criterion=AGREEMENT,
        criterion_reason=(
            'The two computations answer the same definition on the same data, so every dataset should '
            'agree; the claim is 0.99 rather than 1 so that one numerically awkward dataset in a hundred '
            'is a finding to look at rather than a failed run. Exact limits at or above 0.99 are a pass '
            'and limits below it a fail. Where the two were measured they agreed to about 1e-8 decades, '
            'far inside the ten-thousandth of a decade an agreement is counted at. A run in which the '
            'two always agree passes at 400 datasets and cannot at 100, which is where the ladder ends.'
        ),
        stages=(50, 100, 400),
    ),
    'joint-region': Check(
        name='joint-region',
        claim=(
            'The joint confidence region of a two-constant model holds the true pair as often as its '
            'level says — the reading the Identifiability tab offers where the two constants trade off '
            'against each other and neither interval alone settles the pair.'
        ),
        metrics=joint_region,
        cases=tuple(scenarios.joint_grid()),
        row=joint_region_row,
        criterion=COVERAGE,
        criterion_reason=_COVERAGE_REASON,
    ),
    'replicate-pooling': Check(
        name='replicate-pooling',
        claim=(
            'What the app gains by fitting the average of the replicates rather than pooling their '
            'points, and what weighting the points by the law the replicates show buys: the coverage and '
            'the width of the averaged interval, of the pooled one — both carrying that same law — and '
            'of the same average fitted with every point counted equally, on the same data, under '
            'independent noise, under noise that grows with the signal, and under one departure the '
            'replicates share. Reported, not required — under a shared departure none of the three holds '
            'its level, which is the point.'
        ),
        metrics=pooling,
        cases=tuple(scenarios.pooling_grid()),
        row=reference.pooling_row,
        stages=(200,),
    ),
    'before-after': Check(
        name='before-after',
        claim=(
            'What the same datasets gave before the engine: how often the range spanned by the pool of '
            'attempts the previous release kept held the truth, how wide it was, and how often it kept no '
            'attempt at all, beside the present interval on the same data.'
        ),
        metrics=before_after,
        cases=tuple(scenarios.before_after_grid()),
        row=legacy.row,
        stages=(100,),
    ),
    'sobol-coverage': Check(
        name='sobol-coverage',
        claim=(
            "The 95 % interval the Ka sensitivity analysis draws around a Sobol' index holds the "
            'analytically known index of two test functions as often as it says.'
        ),
        metrics=sobol_coverage,
        cases=tuple(sobol.coverage_cases()),
        row=sobol.coverage_row,
        criterion=COVERAGE,
        criterion_reason=(
            _COVERAGE_REASON + ' The interval is a t interval on eight blocks rather than an exact one, so '
            'this criterion is what says whether that approximation is good enough to print.'
        ),
        stages=(200, 400),
    ),
    'dilution-coverage': Check(
        name='dilution-coverage',
        claim=(
            'The interval holds the true binding constant as often as its 95 % level says when the '
            'titrant dilutes the fixed totals of the sample and the titrant stock is declared, across '
            'every assay, regime and noise size, at final dilutions of two to twenty percent.'
        ),
        metrics=conditional_coverage,
        cases=tuple(scenarios.dilution_grid()),
        row=score,
        criterion=COVERAGE,
        criterion_reason=(
            _COVERAGE_REASON + ' The inputs are entered exactly here, so the reported interval is the '
            'conditional one and what the rate measures is the dilution-aware model rather than any '
            'statement about the inputs.'
        ),
    ),
    'dilution-ignored': Check(
        name='dilution-ignored',
        claim=(
            'What the same diluted titrations give when the titrant stock is not declared and the fit '
            'holds the totals constant: how far log10 of the binding constant lands from the truth, and '
            'how often the interval still reaches it. Reported, not required — it is the cost the '
            'dilution option removes.'
        ),
        metrics=dilution_ignored,
        cases=tuple(scenarios.dilution_ignored_grid()),
        row=score,
        stages=(200,),
    ),
    'shared-source-coverage': Check(
        name='shared-source-coverage',
        claim=(
            'The reported interval holds its level when one error of four percent is common to every '
            'concentration of the sample — one stock behind the host, the fixed partner and the '
            'titrant — the entries are drawn from exactly that model and the fit is told it.'
        ),
        metrics=aware_coverage,
        cases=tuple(scenarios.shared_source_grid()),
        row=score,
        criterion=COVERAGE,
        criterion_reason=(
            _COVERAGE_REASON + ' A shared source is a penalty row like any other stated uncertainty, so '
            'the same criterion applies; what this grid adds is that the entries carry exactly the '
            "correlation the fit is told about, which is the model's own premise."
        ),
    ),
    'noise-law-coverage': Check(
        name='noise-law-coverage',
        claim=(
            'The interval reported when every entered input is taken as exact holds the true binding '
            'constant as often as its 95 % level says on replicated titrations, whatever the noise does '
            'along them: constant, growing with the signal, the two together, at two, three and four '
            'replicates, and with whole replicates differing by a scale factor of three percent.'
        ),
        metrics=noise_law_conditional,
        cases=tuple(scenarios.noise_law_grid()),
        row=score,
        criterion=COVERAGE,
        criterion_reason=(
            _COVERAGE_REASON + ' The weights the fit uses are read off the same replicates the interval '
            'is computed from, so a law read too eagerly — or read off differences between whole '
            'replicates that are not noise about the curve at all — shows up here as an interval that '
            'no longer holds its level. The share each fit read is reported beside the rate.'
        ),
    ),
    'noise-law-lof-null': Check(
        name='noise-law-lof-null',
        claim=(
            'On the same replicated titrations, every one of which the model does describe, the '
            'lack-of-fit F test calls the model inadequate about as often as its level allows — with the '
            'fit weighted by the law the replicates show and the pure error taken as their scatter about '
            'their own image of the mean curve.'
        ),
        metrics=lof_rate,
        cases=tuple(scenarios.noise_law_grid()),
        criterion=NULL_RATE,
        criterion_reason=(
            _NULL_REASON + ' Both halves of this F ratio are affected by the weights: a law that '
            'misweights the points inflates the numerator, and a pure error that counted the difference '
            'between whole replicates as noise inflates the denominator until the test cannot fire at '
            'all. The rate says whether the two are the quantities the F distribution describes.'
        ),
        derived_from='noise-law-coverage',
    ),
    'noise-law-aware': Check(
        name='noise-law-aware',
        claim=(
            'The reported interval, which lets every entered input move within the uncertainty stated '
            'for it, holds its level on replicated titrations whose noise grows with the signal, with '
            'and without a constant floor under it, when the inputs are entered exactly as wrongly as '
            'stated.'
        ),
        metrics=noise_law_aware,
        cases=tuple(scenarios.noise_law_aware_grid()),
        row=score,
        criterion=COVERAGE,
        criterion_reason=(
            _COVERAGE_REASON + ' The weights reach more than the profile here: the residual scale the '
            'stated uncertainties are penalised against and the degrees of freedom left to the interval '
            'are both read in the weighted space, so the reported interval needs saying separately from '
            'the conditional one.'
        ),
    ),
    'noise-law-conflict-null': Check(
        name='noise-law-conflict-null',
        claim=(
            'On the same fits, the check on the entered inputs calls them in conflict about as often as '
            'its level allows when they are entered exactly as wrongly as stated and the noise grows '
            'with the signal.'
        ),
        metrics=conflict_rate,
        cases=tuple(scenarios.noise_law_aware_grid()),
        criterion=NULL_RATE,
        criterion_reason=(
            _NULL_REASON + ' The reference the statistic is read against assumes residual rows of equal '
            'variance. Weighting by the law the replicates show is what makes that true of data whose '
            'noise grows with the signal, and this rate is what says so.'
        ),
        derived_from='noise-law-aware',
    ),
    'conflict-single-proportional': Check(
        name='conflict-single-proportional',
        claim=(
            'How often the same check fires on single titrations whose noise grows with the signal. One '
            'curve cannot show how the noise varies along it, so the fit takes the noise as constant and '
            'the statistic is read against a reference that assumes it. Reported, not required: it is '
            'the rate that stays where no law can be estimated, and the summary and the plot guide say '
            'the noise was taken as constant.'
        ),
        metrics=conflict_rate,
        cases=tuple(case for case in scenarios.robustness_grid() if case.proportional),
        derived_from='robustness',
    ),
    'budget-coverage': Check(
        name='budget-coverage',
        claim=(
            'The 95 % intervals the Ka uncertainty budget draws — around the variance of the output, '
            'around the variance one source explains, around the spread left once that source is exact, '
            'and around the two indices of a group of inputs taken together — hold the analytically '
            'known values of two test functions as often as they say.'
        ),
        metrics=sobol_coverage,
        cases=tuple(sobol.coverage_cases()),
        row=sobol.budget_row,
        criterion=COVERAGE,
        criterion_reason=(
            _COVERAGE_REASON + ' Every one of these quantities comes from the same delete-one-block '
            'jackknife as the indices, and the variance and the spread are not indices at all, so each '
            'needs saying separately whether its t interval on eight blocks is good enough to print.'
        ),
        stages=(200, 400),
    ),
    'source-variance-exact': Check(
        name='source-variance-exact',
        claim=(
            'On a direct-binding titration, where one error common to every concentration moves log10 of '
            "the binding constant by exactly minus log10 of itself, the budget's 95 % interval for that "
            "source's variance holds the value the identity gives it. The identity holds where every fit "
            'of the analysis lies strictly inside the Ka bounds; a draw where one ran to a bound reports '
            'the edge of the box, where the output is constant, and is left out of the rate and counted '
            'beside it.'
        ),
        metrics=source_variance,
        cases=tuple(budget.exact_cases()),
        row=budget.exact_row,
        criterion=COVERAGE,
        criterion_reason=(
            _COVERAGE_REASON + ' The truth here is a one-dimensional integral rather than a simulated '
            'rate, so the only question the rows answer is whether the Monte Carlo interval of the '
            'budget reaches it as often as it claims.'
        ),
    ),
    'what-if-accuracy': Check(
        name='what-if-accuracy',
        claim=(
            'How far the what-if line lands from the truth: the first-order formula and the re-weighted '
            'cross-check against a second analysis run at the reduced uncertainty on the same data and '
            'the same design, with the effective sample size the cross-check carried. Both errors are '
            'given again over the draws where no fit ran to a Ka bound, since a fit that did reports the '
            'edge of the box rather than a spread of the inputs.'
        ),
        metrics=whatif_accuracy,
        cases=tuple(budget.whatif_cases()),
        row=budget.whatif_row,
        stages=(30,),
    ),
    'sobol-blocking': Check(
        name='sobol-blocking',
        claim=(
            'What splitting one budget into independently scrambled blocks costs: the root-mean-square '
            'error of each index, block count by block count, at a fixed budget. Reported, not required.'
        ),
        metrics=sobol_error,
        cases=tuple(sobol.blocking_cases()),
        row=sobol.blocking_row,
        stages=(200,),
    ),
    'runtime': Check(
        name='runtime',
        claim='How long one fit takes, per assay family: the median, the 99th percentile and the worst seen.',
        metrics=runtime,
        derived_from='input-aware-coverage',
    ),
}
