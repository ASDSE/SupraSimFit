"""What a fit reports, read off its :class:`~core.pipeline.fit_pipeline.FitResult`.

:func:`summarize_parameters` is the single source of every reported row: the
estimate, its interval and, in per-replicate mode, the spread of the
replicates' own fits. The Fit results view, the caption of its saved figure
and the TXT/CSV exports all render from it. Beside it are the questions a view asks of
a result: whether its headline is the fit at the entered inputs
(:func:`reports_conditional`), which signal parameters ended on a bound
(:func:`parameters_on_bound`, :func:`offsets_held_at_zero`) and which
replicates it was given and used (:func:`input_replica_ids`,
:func:`fit_replica_ids`). Each reads only what the result records, so it holds
for a result imported from a file as for one fitted now.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from core.assays.registry import ASSAY_REGISTRY, AssayType, ParamKind
from core.optimizer.ensemble import describe, describe_log10
from core.pipeline.fit_pipeline import FitResult
from core.pipeline.inputs import ErrorModel
from core.pipeline.varpro import on_ka_bound
from core.units import Q_, Quantity


@dataclass(frozen=True)
class ParameterSummary:
    """One reported row: a fitted parameter, or its log₁₀ twin.

    Attributes
    ----------
    key : str
        Parameter key (e.g. ``"Ka_dye"``). A log twin repeats its source key.
    is_log : bool
        ``True`` for a log₁₀ twin row. ``estimate``, ``interval`` and
        ``replicates`` are then in log₁₀ of the parameter and carry no unit —
        but ``unit`` still names the underlying parameter's unit, so a label
        can read ``log₁₀(Ka / M⁻¹)``.
    estimate : float
        The fit's value for this row. Where *estimate_at_bound* is set this is
        the edge of the Ka box the search stopped on, not an estimate: the
        curves are drawn from it, and no view or export prints it as one.
    estimate_at_bound : str
        ``'low'`` or ``'high'`` when the fit's value of this binding constant
        sits on the lower or the upper edge of its box
        (:func:`~core.pipeline.varpro.on_ka_bound`): the data do not limit it
        on that side, so there is no estimate, only the interval. ``''``
        otherwise, on every signal parameter and on a binding constant held
        fixed by equal bounds.
    unit : str
        Unit of the underlying parameter (``""`` when it has none).
    interval : tuple[float, float] | None
        Confidence interval of this row, in the row's own scale: the interval
        of a log twin is the endpoints of the parameter's interval
        transformed, which is exact because log₁₀ is monotone. ``None`` for a
        parameter with no interval — every signal parameter, a binding
        constant held fixed, and every row of an imported result written
        before intervals were reported.
    interval_open : tuple[bool, bool]
        Per endpoint, whether the interval reaches as far as the profile goes
        rather than being closed by the data.
    interval_unsolvable : tuple[bool, bool]
        Per endpoint, whether an open side is open because the equilibrium
        model cannot be solved past it, rather than because the data leave it
        open. More data cannot close such a side.
    interval_limited_by : tuple[str, str]
        Per endpoint, the other binding constant whose bound — rather than the
        data — is what ends the profile on an open side (``''`` otherwise):
        the data would accept values further out if that constant could go
        past its bound.
    interval_split : bool
        Whether the values the data accept come in separate stretches, so the
        interval spans a gap of values they reject.
    level : float | None
        Confidence level of ``interval``; ``None`` when there is none.
    inflation : float | None
        The design effect ``interval``'s cut-off was widened by
        (:attr:`~core.pipeline.varpro.KaInterval.inflation`): one where it was
        not widened, ``None`` where there is no interval.
    degenerate : bool
        Whether the data determine this parameter only in combination with
        others.
    replicates : dict[str, float] | None
        :func:`~core.optimizer.ensemble.describe` (or ``describe_log10`` for a
        log twin) over the values the replicates the fit used give this
        parameter in their own fits, leaving out each replicate whose own fit
        of this binding constant is on an edge of its box: a bound is not an
        estimate. A signal parameter leaves out every replicate whose own fit
        put any binding constant on an edge, since its value is then that of
        a curve pushed against the bound. ``None`` below two values.
    replicates_at_bound : int
        How many of the replicates the fit used were left out of *replicates*
        for that reason.
    conditional_estimate : float | None
        This binding constant at the entered inputs, in the row's own scale.
        ``None`` on a row that is not a binding constant and on every row of a
        fit that reports its conditional fit (:func:`reports_conditional`),
        where the estimate above is already that one.
    conditional_interval : tuple[float, float] | None
        Its interval with the inputs held as entered and no error of the
        additions, in the row's own scale; ``None`` on the same rows as
        *conditional_estimate*.
    conditional_inflation : float | None
        *inflation* of *conditional_interval*; ``None`` on the same rows.
    conditional_open : tuple[bool, bool]
        Per endpoint of *conditional_interval*, whether it reaches as far as
        the profile goes rather than being closed by the data.
    conditional_split : bool
        Whether the values *conditional_interval* spans come in separate
        stretches, so it spans a gap of values the data reject.
    conditional_at_bound : str
        *estimate_at_bound* of *conditional_estimate*.
    one_step_p : float | None
        On the second binding constant of a two-step model, the p-value of the
        test of *interval* against the model without that step
        (:attr:`~core.pipeline.varpro.KaInterval.one_step_p`): above
        :data:`~core.pipeline.varpro.SECOND_STEP_LEVEL` the data do not show
        the second step, and the interval is open below. ``None`` on every
        other row.
    """

    key: str
    is_log: bool
    estimate: float
    estimate_at_bound: str
    unit: str
    interval: Optional[Tuple[float, float]]
    interval_open: Tuple[bool, bool]
    interval_unsolvable: Tuple[bool, bool]
    interval_limited_by: Tuple[str, str]
    interval_split: bool
    level: Optional[float]
    degenerate: bool
    replicates: Optional[Dict[str, float]]
    replicates_at_bound: int = 0
    conditional_estimate: Optional[float] = None
    conditional_interval: Optional[Tuple[float, float]] = None
    conditional_open: Tuple[bool, bool] = (False, False)
    conditional_split: bool = False
    conditional_at_bound: str = ''
    one_step_p: Optional[float] = None
    inflation: Optional[float] = None
    conditional_inflation: Optional[float] = None


def reports_conditional(result: FitResult) -> bool:
    """Whether *result*'s headline is its fit at the entered inputs, every input exact.

    It is unless an input was free to move (``input_shifts``) or a random error
    of each addition was stated, which widens the reported interval beyond the
    conditional one even where no input moves.
    """
    return not result.input_shifts and ErrorModel.from_dict(result.fit_config).additions is None


def _binding_constant_keys(result: FitResult) -> set[str]:
    """The binding constants of the result's assay; none for an assay type the registry does not know."""
    try:
        kinds = ASSAY_REGISTRY[AssayType[result.assay_type]].param_kinds
    except KeyError:
        return set()
    return {k for k, kind in kinds.items() if kind is ParamKind.BINDING_CONSTANT}


def parameters_on_bound(result: FitResult) -> Dict[str, Quantity]:
    """Signal parameters the fit ended on a bound the user entered, each with that bound.

    A signal parameter is solved inside its bounds, so one that ends on a
    bound may be held there against the data and the curve with it. Zero, the
    physical lower limit of every signal parameter, is not reported, and
    neither is a parameter held fixed by equal bounds. A binding constant on a
    bound shows as an open side of its interval instead. Read from the
    parameters and the bounds the result records — a number, or ``None`` for
    a bound with no limit — so it holds for an imported result too.
    """
    ka_keys = _binding_constant_keys(result)
    hits: Dict[str, Quantity] = {}
    for key, (lo, hi, unit) in (result.fit_config.get('custom_bounds') or {}).items():
        if key in ka_keys or key not in result.parameters or lo == hi:
            continue
        value = float(result.parameters[key].to(unit).magnitude)
        for bound in (lo, hi):
            if bound is not None and bound != 0.0 and np.isclose(value, bound, rtol=1e-12, atol=0.0):
                hits[key] = Q_(bound, unit)
    return hits


def offsets_held_at_zero(result: FitResult) -> List[str]:
    """Signal offsets the fit left on a lower bound of zero, the registry's floor for an offset.

    A zero floor is right for a signal that includes its blank, and holds the
    offset against the data when the blank was subtracted before the fit. The
    bound is the one the fit was given where the result records it, the
    registry's default otherwise; an offset pinned by equal bounds is held on
    purpose and not reported. The bounded solve clips a coefficient to its
    bound, so an offset held there is exactly zero.
    """
    try:
        meta = ASSAY_REGISTRY[AssayType[result.assay_type]]
    except KeyError:
        return []
    recorded = result.fit_config.get('custom_bounds') or {}
    held = []
    for key, kind in meta.param_kinds.items():
        if kind is not ParamKind.SIGNAL_OFFSET or key not in result.parameters:
            continue
        if key in recorded:
            lo, hi, unit = recorded[key]
        else:
            low, high = meta.default_bounds[key]
            lo, hi, unit = float(low.magnitude), float(high.magnitude), str(low.units)
        if lo == 0.0 and hi != lo and float(result.parameters[key].to(unit).magnitude) <= 0.0:
            held.append(key)
    return held


def summarize_parameters(result: FitResult) -> List[ParameterSummary]:
    """Reported rows for *result* — the single source for every display.

    The Fit results view, the caption of its saved figure and the TXT/CSV
    exports all render from this, so they cannot drift apart. A log₁₀ twin row follows each
    binding constant; its interval is the parameter's interval transformed, and
    its replicate statistics come from
    :func:`~core.optimizer.ensemble.describe_log10`, which transforms the
    replicates' values *first* — statistics of log₁₀(Ka) must come from the
    per-fit log values, because log₁₀ of a Ka spread is meaningless.

    A binding constant the fit left on an edge of its box is flagged
    (``estimate_at_bound``): the data do not limit it on that side, so the
    value is the edge and not an estimate. For the same reason the replicate
    statistics of a binding constant leave out each replicate whose own fit
    of that constant ran to an edge, and say how many they left out.

    The conditional columns are filled only where they say something the
    estimate does not: on a binding constant of a fit that let its inputs
    move or took in a stated error of the additions. Otherwise the fit above
    is the conditional one (:func:`reports_conditional`).

    Each unit comes from the parameter's own ``Quantity``, which stays correct
    even when the assay type is missing from the registry; only which
    parameters are binding constants is registry metadata.
    """
    ka_keys = _binding_constant_keys(result)
    boxes = _ka_boxes(result)
    replicates = _replicate_values(result, boxes)
    intervals = result.intervals or {}
    conditional = None if reports_conditional(result) else result.conditional
    rows: List[ParameterSummary] = []
    for key, value in result.parameters.items():
        unit = str(value.units) if isinstance(value, Quantity) else ''
        magnitude = float(value.magnitude) if isinstance(value, Quantity) else float(value)
        ci = intervals.get(key)
        pool, replicates_at_bound = replicates.get(key, (None, 0))
        entered = None if conditional is None or key not in ka_keys else conditional.parameters.get(key)
        entered_ci = None if conditional is None or key not in ka_keys else conditional.intervals.get(key)
        shared = dict(
            key=key,
            unit=unit,
            estimate_at_bound=_at_bound(value, boxes.get(key)),
            interval_open=(False, False) if ci is None else (ci.open_low, ci.open_high),
            interval_unsolvable=(False, False) if ci is None else (ci.unsolvable_low, ci.unsolvable_high),
            interval_limited_by=('', '') if ci is None else (ci.limited_by_low, ci.limited_by_high),
            interval_split=False if ci is None else ci.split,
            level=None if ci is None else ci.level,
            degenerate=key in result.degenerate_keys,
            replicates_at_bound=replicates_at_bound,
            conditional_open=(False, False) if entered_ci is None else (entered_ci.open_low, entered_ci.open_high),
            conditional_split=False if entered_ci is None else entered_ci.split,
            conditional_at_bound='' if entered is None else _at_bound(entered, boxes.get(key)),
            one_step_p=None if ci is None else ci.one_step_p,
            inflation=None if ci is None else ci.inflation,
            conditional_inflation=None if entered_ci is None else entered_ci.inflation,
        )
        rows.append(
            ParameterSummary(
                is_log=False,
                estimate=magnitude,
                interval=None if ci is None else (ci.low, ci.high),
                replicates=None if pool is None else describe(pool),
                conditional_estimate=None if entered is None else float(entered.magnitude),
                conditional_interval=None if entered_ci is None else (entered_ci.low, entered_ci.high),
                **shared,
            )
        )
        if key in ka_keys:
            rows.append(
                ParameterSummary(
                    is_log=True,
                    estimate=float(np.log10(magnitude)),
                    interval=None if ci is None else (float(np.log10(ci.low)), float(np.log10(ci.high))),
                    replicates=None if pool is None else describe_log10(pool),
                    conditional_estimate=None if entered is None else float(np.log10(entered.magnitude)),
                    conditional_interval=None
                    if entered_ci is None
                    else (float(np.log10(entered_ci.low)), float(np.log10(entered_ci.high))),
                    **shared,
                )
            )
    return rows


def _ka_boxes(result: FitResult) -> Dict[str, Tuple[Quantity, Quantity]]:
    """The box every binding constant of *result* was searched in, as the result records it.

    The bounds the fit was given where it records them, the registry's
    defaults otherwise; a binding constant held fixed by equal bounds, and one
    whose recorded box has no limit on a side, has no box to reach an edge of.
    """
    try:
        defaults = ASSAY_REGISTRY[AssayType[result.assay_type]].default_bounds
    except KeyError:
        return {}
    recorded = result.fit_config.get('custom_bounds') or {}
    boxes = {}
    for key in _binding_constant_keys(result):
        lo, hi = defaults[key]
        if key in recorded:
            low, high, unit = recorded[key]
            if low is None or high is None:
                continue
            lo, hi = Q_(low, unit), Q_(high, unit)
        if lo != hi:
            boxes[key] = (lo, hi)
    return boxes


def _at_bound(value: Quantity, box: Optional[Tuple[Quantity, Quantity]]) -> str:
    """``'low'`` or ``'high'`` when *value* sits on that edge of the Ka *box* (:func:`on_ka_bound`), else ``''``."""
    if box is None:
        return ''
    unit = value.units
    ka = float(value.magnitude)
    lo, hi = (float(bound.to(unit).magnitude) for bound in box)
    if not on_ka_bound(ka, (lo, hi)):
        return ''
    return 'low' if np.log10(ka) - np.log10(lo) <= np.log10(hi) - np.log10(ka) else 'high'


def _replicate_values(
    result: FitResult, boxes: Dict[str, Tuple[Quantity, Quantity]]
) -> Dict[str, Tuple[Optional[np.ndarray], int]]:
    """Each parameter's values across the own fits of the replicates *result* used, and how many were left out.

    A replicate whose own fit put a binding constant on an edge of its box
    (*boxes*) is left out of that constant's values: a bound is not an
    estimate. The replicate's fit of another binding constant still counts:
    it is a value of that constant. A signal parameter's values leave out a
    replicate with any binding constant on an edge, since they are those of a
    curve pushed against it. The values are ``None`` unless at least two
    remain, and there are none at all unless at least two of the replicates
    the fit was given entered its average: one value is
    the fit itself seen again, and a replicate the fit left out describes data
    the fit does not.
    """
    used = set(result.metadata.get('replica_ids_fit') or ())
    fits = [rf for rf in result.replica_fits or () if rf.metadata.get('replica_id') in used]
    if len(fits) < 2:
        return {}
    on_edge = [
        {k for k, box in boxes.items() if k in rf.parameters and _at_bound(rf.parameters[k], box)} for rf in fits
    ]
    ka_keys = _binding_constant_keys(result)
    pooled = {}
    for key in result.parameters:
        if not all(key in rf.parameters for rf in fits):
            continue
        keep = [rf for rf, edges in zip(fits, on_edge) if not (key in edges if key in ka_keys else edges)]
        values = np.array([float(rf.parameters[key].magnitude) for rf in keep]) if len(keep) >= 2 else None
        pooled[key] = (values, len(fits) - len(keep))
    return pooled


def fit_replica_ids(result: FitResult) -> Optional[List[str]]:
    """Replicates *result* was fitted on, whose average its quality is measured against.

    A per-replicate fit's ``replica_ids_fit`` (the replicates that entered the
    average), otherwise the ``active_replica_ids`` a fit of the average was
    given.

    Returns
    -------
    list[str] | None
        The replicate ids, or None when the result does not record them.
    """
    used = result.metadata.get('replica_ids_fit', result.metadata.get('active_replica_ids'))
    return None if used is None else list(used)


def input_replica_ids(result: FitResult) -> Optional[List[str]]:
    """Replicates *result* was given: the ones it used and the ones it left out.

    ``active_replica_ids`` when recorded; otherwise, for a per-replicate fit,
    the replicates it used followed by those in ``replica_failures``.

    Returns
    -------
    list[str] | None
        The replicate ids, or None when the result does not record them.
    """
    given = result.metadata.get('active_replica_ids')
    if given is not None:
        return list(given)
    used = result.metadata.get('replica_ids_fit')
    if used is None:
        return None
    return list(used) + [rid for rid in result.metadata.get('replica_failures') or {} if rid not in used]


def replica_order(result: FitResult, loaded: Optional[Sequence[str]] = None) -> Optional[List[str]]:
    """The replicates in the order the app names them A, B, …: *loaded*, the data's, else the order *result* records.

    A fit made from data records ``loaded_replica_ids``, so its replicates keep their
    letters where the data are not loaded.

    Returns
    -------
    list[str] | None
        The replicate ids in order, or None when neither is known.
    """
    if loaded is not None:
        return list(loaded)
    order = result.metadata.get('loaded_replica_ids')
    return None if order is None else list(order)
