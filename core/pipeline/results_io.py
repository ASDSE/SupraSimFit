"""A results file read back, checked against the data loaded now.

A results file holds the record of a fit (:meth:`FitResult.to_dict
<core.pipeline.fit_pipeline.FitResult.to_dict>`, read back by
:meth:`~core.pipeline.fit_pipeline.FitResult.from_dict`). Every number shown
under a fit's name must describe the data the fit was made on, so before an
imported fit is shown :func:`verify_imported_result` measures its stored
quality again on its own record — the replicates it used, its conditions, its
assay type and where it put the inputs it was free to move — and says whether
it describes the loaded data.
"""

from __future__ import annotations

import math
from dataclasses import replace
from typing import Dict, List, Literal, Mapping, Optional, Tuple

import numpy as np

from core.assays import ASSAY_CLASSES
from core.assays.base import BaseAssay
from core.assays.registry import ASSAY_REGISTRY, AssayType
from core.data_processing.measurement_set import MeasurementSet
from core.models.equilibrium import MODEL_ARITHMETIC
from core.pipeline.fit_pipeline import FitResult, fit_view
from core.pipeline.inputs import ErrorModel
from core.pipeline.reporting import fit_replica_ids, input_replica_ids

#: Relative tolerance within which a stored score counts as reproduced by the
#: arithmetic that wrote it. Scoring the same fit on the same data twice
#: reproduces every number exactly, and an equivalent evaluation of the same
#: model — the same equilibrium root found by a bracketing method at the same
#: relative tolerance — moves them by at most 5e-15. 1e-6 sits far above that
#: spread and below what other data make of them: on the fits under
#: ``tests/fixtures/results``, a 1 % change of the concentrations or of the
#: signals, or one replicate more or fewer in the average, moves the RMSE by
#: 8e-6 relative or more and the R² by 1.9e-6 or more.
_REPRODUCE_RTOL = 1e-6

#: The equilibrium solve behind the scores of a results file that records no
#: ``model_arithmetic``: per titration point, Brent's method
#: (``scipy.optimize.brentq``) on one free concentration — free host for the
#: competitive assays, free ligand for the stepwise ones — to the absolute
#: tolerance in M those releases gave it as ``xtol`` (``core/models/equilibrium.py``
#: of v1.3.0 and v1.5.0), and brentq's default relative tolerance of 4 eps
#: (:data:`_BRENT_RTOL`). Direct binding has a closed form, so its scores are
#: checked at :data:`_REPRODUCE_RTOL` alone. The slack that precision leaves
#: the scores (:func:`_unmarked_slack`) is a first-order bound, which holds to
#: within a hundredth of itself while the solve's relative error at every point
#: stays below :data:`_FIRST_ORDER`; beyond it a file cannot be checked.
_UNMARKED_SOLVE: Dict[AssayType, Tuple[str, float]] = {
    AssayType.GDA: ('H', 1e-14),
    AssayType.IDA: ('H', 1e-14),
    AssayType.DBA_HG2: ('G', 1e-15),
    AssayType.DBA_H2G: ('H', 1e-15),
}
_BRENT_RTOL = 4 * float(np.finfo(float).eps)
_FIRST_ORDER = 1e-2

ImportStatus = Literal['verified', 'rescored_legacy', 'different_data', 'unverifiable']


def verify_imported_result(result: FitResult, ms: Optional[MeasurementSet]) -> Tuple[ImportStatus, FitResult]:
    """Check an imported *result* against the loaded data *ms* before it is shown.

    With data loaded, the result's stored RMSE and R² are measured again on its
    own record: the replicates it used, its conditions, its assay type and the
    shifts it reports for the inputs it was free to move — the fit is scored
    where it was made, not at the entered inputs it moved away from.

    ``model_arithmetic`` names the equilibrium arithmetic a file's scores were
    computed with. A file that names the present one is checked to a relative
    ``_REPRODUCE_RTOL`` (1e-6). A file that records none was written by a
    release that solved the competitive and stepwise equilibria by Brent's
    method to an absolute ``xtol`` on the free concentration, 1e-14 M or
    1e-15 M (:data:`_UNMARKED_SOLVE`): its scores are checked against the
    present arithmetic within 1e-6 plus what that documented precision allows
    them to differ by on this fit and these data (:func:`_unmarked_slack`).
    A file that names an arithmetic this version does not have cannot be
    checked at all.

    ``'verified'``
        The data carry the fit's fingerprint, or the file records none, and
        every stored RMSE and R² is reproduced. The returned copy keeps every
        number the file stores and records the loaded data's fingerprint and
        the ``quality_scored_on`` marker. A fit of the average whose file does
        not record its replicates is scored on the replicates active in *ms*
        now, and the copy records them.
    ``'rescored_legacy'``
        A per-replicate file without the ``quality_scored_on`` marker whose
        reported RMSE and R² reproduce when scored against every replicate it
        was given, left-out ones included. The copy keeps its parameters and
        measures RMSE, R² and curve again on the replicates the fit used, with
        the present arithmetic, which its ``model_arithmetic`` then names.
    ``'different_data'``
        The fingerprints differ, the data lack a replicate the fit names, or
        the stored quality reproduces neither way. *result* is returned
        unchanged. A recorded ``data_fingerprint`` equal to the data's tells
        numbers that do not reproduce on these data from a fit made on other
        data.
    ``'unverifiable'``
        No data are loaded, the result holds no fitted parameters to score, it
        names an equilibrium arithmetic this version cannot compute with, or
        the solve that wrote its scores left some free concentration less
        precise than ``_FIRST_ORDER`` of itself. *result* is returned
        unchanged.

    *ms* itself, including which replicates are active, is never changed.

    Parameters
    ----------
    result : FitResult
        A result read from a results file.
    ms : MeasurementSet or None
        The data loaded now.

    Returns
    -------
    tuple[str, FitResult]
        The status and the result to show: a checked copy for ``'verified'``
        and ``'rescored_legacy'``, *result* otherwise.
    """
    if ms is None or not result.parameters or result.metadata.get('model_arithmetic') not in (None, MODEL_ARITHMETIC):
        return 'unverifiable', result
    fingerprint = ms.fingerprint()
    recorded = result.metadata.get('data_fingerprint')
    if recorded is not None and recorded != fingerprint:
        return 'different_data', result

    used = fit_replica_ids(result)
    metadata = dict(result.metadata)
    if used is None:
        used = ms.active_replica_ids
        metadata['active_replica_ids'] = list(used)
    if not set(used) <= set(ms.replica_ids):
        return 'different_data', result
    metadata['data_fingerprint'] = fingerprint
    metadata['quality_scored_on'] = 'fitted_replicates'
    assay = _record_assay(ms, result, used)

    vector = _parameter_vector(result, assay)
    offsets = _fitted_offsets(result)
    reproduced = _reproduces(result, assay, vector, offsets)
    if reproduced is None:
        return 'unverifiable', result
    if reproduced:
        return 'verified', replace(result, metadata=metadata)

    given = _legacy_input_ids(result, used, ms)
    if given is None or not _reproduces(result, _record_assay(ms, result, given), vector, offsets):
        return 'different_data', result
    rmse, r_squared, x_fit, y_fit = fit_view(assay, vector, offsets)
    metadata['model_arithmetic'] = MODEL_ARITHMETIC
    return 'rescored_legacy', replace(
        result, rmse=rmse, r_squared=r_squared, x_fit=x_fit, y_fit=y_fit, metadata=metadata
    )


def _record_assay(ms: MeasurementSet, result: FitResult, replica_ids: List[str]) -> BaseAssay:
    """Average of *replica_ids* in *ms*, with *result*'s conditions and assay type."""
    assay_cls = ASSAY_CLASSES[AssayType[result.assay_type]]
    return ms.with_active(replica_ids).to_assay(assay_cls, conditions=result.conditions, use_average=True)


def _fitted_offsets(result: FitResult) -> Dict[str, float]:
    """Where *result* put each input its fit moved, as a fraction of the entered value.

    ``input_shifts`` holds the offset of every error source; the error model
    the fit recorded turns them into the offsets of the inputs.
    """
    fractions = {key: shift.fraction for key, shift in result.input_shifts.items()}
    return ErrorModel.from_dict(result.fit_config).input_offsets(fractions, result.conditions)


def _legacy_input_ids(result: FitResult, used: List[str], ms: MeasurementSet) -> Optional[List[str]]:
    """The replicates a per-replicate file without the ``quality_scored_on`` marker may have scored against.

    Every replicate it was given, left-out ones included, when that differs
    from the replicates it used and *ms* holds them all; otherwise None.
    """
    if not result.per_replica or 'quality_scored_on' in result.metadata:
        return None
    given = input_replica_ids(result)
    if given is None or set(given) == set(used) or not set(given) <= set(ms.replica_ids):
        return None
    return given


def _parameter_vector(result: FitResult, assay: BaseAssay) -> np.ndarray:
    """*result*'s reported parameters in *assay*'s order and canonical units."""
    units = ASSAY_REGISTRY[assay.assay_type].units
    return np.array([result.parameters[k].to(units[k]).magnitude for k in assay.parameter_keys], dtype=float)


def _reproduces(
    result: FitResult, assay: BaseAssay, vector: np.ndarray, offsets: Mapping[str, float]
) -> Optional[bool]:
    """Whether *result*'s stored RMSE and R² are those of *vector*, at the inputs *offsets* put them, on *assay*.

    Each score is reproduced within ``_REPRODUCE_RTOL`` of the stored value,
    plus, for a file that records no ``model_arithmetic``, the slack the solve
    that wrote it leaves (:func:`_unmarked_slack`); ``None`` where that solve
    leaves no bound.
    """
    rmse, r_squared, _, _ = fit_view(assay, vector, offsets)
    stored = (result.rmse, result.r_squared)
    slack = (0.0, 0.0) if 'model_arithmetic' in result.metadata else _unmarked_slack(assay, vector, offsets, rmse)
    if slack is None:
        return None
    return all(
        abs(score - value) <= _REPRODUCE_RTOL * abs(value) + s
        for score, value, s in zip((rmse, r_squared), stored, slack)
    )


def _unmarked_slack(
    assay: BaseAssay, vector: np.ndarray, offsets: Mapping[str, float], rmse: float
) -> Optional[Tuple[float, float]]:
    """How far the RMSE and the R² of a file without ``model_arithmetic`` may lie from the present ones.

    The solve that wrote such a file (:data:`_UNMARKED_SOLVE`) returned each
    point's free concentration ``f`` within ``xtol + 4 eps·f`` of the root,
    a relative error ``e = xtol/f + 4 eps`` (zero where ``f`` is, which that
    solve returned exactly). Every species is a product of the totals and
    fractions of ``f``, and to first order carries at most ``e`` (competitive)
    or ``2e`` (stepwise, whose doubly bound complex goes with ``f²``) of it, so
    the signal at the point is off by at most ``d = 2e·Σ|I_k|·[S_k]`` over its
    signal coefficients. By the triangle inequality the RMSE then moves by at
    most ``‖d‖/√n``, and the residual sum of squares by at most
    ``2‖r‖‖d‖ + ‖d‖²`` with ``‖r‖ = rmse·√n``, which divided by the total sum of
    squares bounds the move of R². Both are zero for an assay that solves no
    iteration (:data:`_UNMARKED_SOLVE` does not list it). ``None`` where ``e``
    reaches ``_FIRST_ORDER`` at a point, or a species is not a number, which
    leaves no first-order bound.
    """
    solve = _UNMARKED_SOLVE.get(assay.assay_type)
    if solve is None:
        return 0.0, 0.0
    free_key, xtol = solve
    moved = assay.with_inputs(offsets) if offsets else assay
    species = moved.species(vector)
    coefficients = dict(zip(assay.parameter_keys, vector))
    signal = sum(abs(coefficients[c]) * species[s] for c, s in ASSAY_REGISTRY[assay.assay_type].signal_species.items())
    free = species[free_key]
    relative = np.divide(xtol, free, out=np.zeros_like(free), where=free > 0.0) + _BRENT_RTOL
    if not np.all(relative < _FIRST_ORDER) or not np.all(np.isfinite(signal)):
        return None
    shift = float(np.linalg.norm(2.0 * relative * signal))
    y = assay.y_data.magnitude
    n = y.size
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r_squared_slack = (2.0 * rmse * math.sqrt(n) * shift + shift**2) / ss_tot if ss_tot > 0.0 else 0.0
    return shift / math.sqrt(n), r_squared_slack
