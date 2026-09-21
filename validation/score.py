"""One stored row per (scenario, seed): the fit the application performs, scored against the truth.

Every row goes through the calls the interface makes —
:func:`~core.pipeline.fit_pipeline.fit_measurement_set` on a
:class:`~core.data_processing.measurement_set.MeasurementSet` built from the
entered titrant series and the measured replicates — so what is scored is what
ships. The row holds the truth, both intervals, where the fit put the inputs,
what the diagnostics say, and the wall time of the fit.

A fit the application refuses is stored with its message and counted as
refused; anything else that escapes is stored with its type and counted as an
error. Neither is dropped, and both are shown by ``python -m validation tables``.
"""

from __future__ import annotations

import time
from typing import Any, Callable

import numpy as np

from core.assays import ASSAY_CLASSES
from core.assays.registry import AssayType
from core.data_processing.measurement_set import MeasurementSet
from core.pipeline.fit_pipeline import FitConfig, FitResult, fit_measurement_set
from core.pipeline.profile import JointRegion, fit_profile
from core.pipeline.varpro import FitRefused, KaInterval, Projection
from validation.generate import Dataset, dataset
from validation.scenarios import Scenario

__all__ = ['guard', 'interval_facts', 'joint_region_row', 'region_excess', 'score']


def guard(work) -> dict[str, Any]:
    """Run *work* and turn a refusal or an unexpected exception into row fields.

    A :class:`~core.pipeline.varpro.FitRefused` and a ``ValueError`` are the
    application's own way of declining a fit — bounds that hold no solution,
    too few points for the parameters, an uncertainty it cannot read — and are
    stored as ``refused`` with the message a user would see. Anything else is
    stored as ``error`` with its type, which is a defect to chase rather than a
    result.
    """
    try:
        return {**work(), 'refused': None, 'error': None}
    except (FitRefused, ValueError) as refusal:
        return {'refused': f'{type(refusal).__name__}: {refusal}', 'error': None}
    except Exception as failure:  # noqa: BLE001 - a row records what went wrong instead of ending the run
        return {'refused': None, 'error': f'{type(failure).__name__}: {failure}'}


def interval_facts(
    interval: KaInterval | None,
    truth: float,
    estimate: float,
    accepts: Callable[[float], bool] | None = None,
) -> dict[str, Any]:
    """What one interval says about one binding constant.

    ``covers`` is whether the interval accepts the truth. For a connected
    interval that is the truth lying between the edges. A split interval spans
    a gap of Ka values the fit rejects, so there *accepts* — the profile the
    interval was cut from, asked at one Ka — decides, and the truth in the gap
    is recorded as not covered.

    Parameters
    ----------
    interval : KaInterval or None
        The interval; ``None`` where the fit carries none for this constant.
    truth : float
        True Ka in 1/M.
    estimate : float
        The fit's own Ka in 1/M.
    accepts : Callable[[float], bool], optional
        Whether the profile accepts a Ka. Consulted only for a split
        interval; without it a split interval is scored on its edges.

    Returns
    -------
    dict
        ``covers``, ``width`` in decades of Ka, the ``open``/``split``/
        ``limited`` flags and the two edges, with ``estimate`` beside them.
        ``None`` fields where there is no interval.
    """
    if interval is None:
        return {'covers': None, 'width': None, 'open': None, 'split': None, 'limited': None, 'estimate': estimate}
    covers = bool(interval.low <= truth <= interval.high)
    if covers and interval.split and accepts is not None:
        covers = bool(accepts(truth))
    return {
        'covers': covers,
        'width': float(np.log10(interval.high / interval.low)),
        'open': bool(interval.open_low or interval.open_high),
        'split': bool(interval.split),
        'limited': bool(interval.limited_by_low or interval.limited_by_high),
        'low': float(interval.low),
        'high': float(interval.high),
        'estimate': estimate,
    }


def _profile_accepts(profile) -> Callable[[float], bool]:
    """Whether the penalised profile of one binding constant accepts a Ka.

    The profile was solved on a grid and the interval cut from it; the same
    grid, read between its nodes, answers one Ka. A Ka past the grid, or
    between two nodes the model could not be solved at, is not accepted.
    """
    grid = np.log10(profile.grid)
    values = np.asarray(profile.objective, dtype=float)

    def accepts(ka: float) -> bool:
        t = float(np.log10(ka))
        if not grid.size or t < grid[0] or t > grid[-1]:
            return False
        i = int(np.clip(np.searchsorted(grid, t), 1, grid.size - 1))
        left, right = values[i - 1], values[i]
        if not (np.isfinite(left) and np.isfinite(right)):
            return False
        span = grid[i] - grid[i - 1]
        value = right if span == 0 else left + (right - left) * (t - grid[i - 1]) / span
        return bool(value <= profile.threshold)

    return accepts


def _reported_accepts(result: FitResult) -> dict[str, Callable[[float], bool]]:
    """One acceptance test per binding constant of the reported interval.

    The fit carries the penalised profile it cut the interval from, which is
    the plain profile where no input may move, so the test is the interval's
    own definition rather than a second computation of it.
    """
    aware = result.aware
    return {} if aware is None else {key: _profile_accepts(profile) for key, profile in aware.profiles.items()}


def _entered_accepts(data: Dataset) -> Callable[[str], Callable[[float], bool]]:
    """A factory of acceptance tests for the interval at the inputs as entered.

    That interval is the profile interval of the entered inputs, so a
    projection of the same assay and bounds re-cuts the profile it came from.
    The projection is built on the first call, which only a split interval
    makes.
    """
    held: dict[str, Any] = {}

    def for_key(key: str) -> Callable[[float], bool]:
        def accepts(ka: float) -> bool:
            if not held:
                projection = Projection(data.assay, data.assay.get_default_bounds())
                held['projection'] = projection
                held['threshold'] = projection.threshold(projection.fit())
            return bool(held['projection'].profile(key)(ka) <= held['threshold'])

        return accepts

    return for_key


def measurement_set(data: Dataset) -> MeasurementSet:
    """The measured data as the application loads them: the entered titrant series and every replicate."""
    return MeasurementSet(
        concentrations=data.entered_x,
        signals=data.signals,
        replica_ids=tuple(f'r{i}' for i in range(data.signals.shape[0])),
    )


def _bound_active(result, data: Dataset) -> bool:
    """Whether a signal parameter the data determine sits on a bound at the reported fit."""
    bounds = data.assay.get_default_bounds()
    units = data.assay.registry_metadata.units
    for key, value in result.parameters.items():
        if key.startswith('Ka') or key in result.degenerate_keys:
            continue
        low, high = (float(b.to(units[key]).magnitude) for b in bounds[key])
        if low == high:
            continue
        magnitude = float(value.to(units[key]).magnitude)
        if magnitude <= low or magnitude >= high:
            return True
    return False


def score(scenario: Scenario, seed: int) -> dict[str, Any]:
    """Generate one dataset, fit it as the application does, and score the fit against its truth.

    Returns
    -------
    dict
        One JSON row: ``truth`` per binding constant, ``aware`` and ``cond``
        holding :func:`interval_facts` of the reported and the conditional
        interval, ``z`` per input the fit was free to move, the diagnostics,
        and the wall time. ``refused`` or ``error`` instead of the fit's fields
        when the fit did not happen.

    ``truth``, ``z``, ``rmse``, ``r_squared``, ``cond_misfit_p`` and
    ``conflict_k`` are provenance: they are stored so a row can be read back
    and questioned, and no check reads them today.
    """
    started = time.perf_counter()
    data = dataset(scenario, seed)

    def work() -> dict[str, Any]:
        config = FitConfig(per_replica=False, input_specs=scenario.input_specs)
        fit_started = time.perf_counter()
        result = fit_measurement_set(
            measurement_set(data),
            ASSAY_CLASSES[AssayType[scenario.assay]],
            {k: v for k, v in data.conditions.items()},
            config,
        )
        t_fit = time.perf_counter() - fit_started
        truth = data.ka_truth
        conditional = result.conditional
        reported_accepts = _reported_accepts(result)
        entered_accepts = _entered_accepts(data)
        row: dict[str, Any] = {
            'truth': truth,
            'aware': {
                key: interval_facts(
                    (result.intervals or {}).get(key),
                    value,
                    float(result.parameters[key].to('1/M').magnitude),
                    reported_accepts.get(key),
                )
                for key, value in truth.items()
            },
            'cond': {
                key: interval_facts(
                    None if conditional is None else conditional.intervals.get(key),
                    value,
                    float(conditional.parameters[key].to('1/M').magnitude) if conditional else float('nan'),
                    entered_accepts(key),
                )
                for key, value in truth.items()
            },
            'z': {key: shift.z for key, shift in result.input_shifts.items()},
            'at_edge': any(shift.at_edge for shift in result.input_shifts.values()),
            'bound_active': _bound_active(result, data),
            'rmse': result.rmse,
            'r_squared': result.r_squared,
            't_fit': t_fit,
        }
        diagnostics = result.diagnostics
        misfit = None if diagnostics is None else diagnostics.misfit
        conditional_misfit = None if diagnostics is None else diagnostics.conditional_misfit
        inputs = None if diagnostics is None else diagnostics.conflict
        row.update(
            {
                'misfit_kind': None if misfit is None else misfit.kind,
                'misfit_p': None if misfit is None else misfit.p_value,
                'cond_misfit_p': None if conditional_misfit is None else conditional_misfit.p_value,
                'conflict_p': None if inputs is None else inputs.p_value,
                'conflict_q': None if inputs is None else inputs.q,
                'conflict_k': None if inputs is None else inputs.k,
                'verdict': None if diagnostics is None else diagnostics.verdict.value,
            }
        )
        return row

    row = guard(work)
    row['t_total'] = time.perf_counter() - started
    return row


def region_excess(region: JointRegion, pair: tuple[float, float]) -> float:
    """Residual excess of the drawn region at one Ka pair, read off its grid as the region is drawn.

    The region is the set of grid cells with ``r2 >= r2_cut``, the cut-off
    taking one value per cell. In residual sum of squares, which is what the
    cut-off cuts, that reads ``(1 - r2) / (1 - r2_cut) <= 1``; this ratio is
    the surface read here. A pair inside the box takes the bilinear value of
    its cell; a pair outside the box, or in a cell the equilibrium model could
    not be solved in, is outside the region and comes back as ``nan``.

    Parameters
    ----------
    region : JointRegion
        The region the profiles were cut into.
    pair : tuple[float, float]
        Ka of the two constants in 1/M, in ``region.ka_keys`` order.

    Returns
    -------
    float
        The excess at *pair* (at most 1 inside the region), or ``nan``.
    """
    surface = (1.0 - region.r2) / (1.0 - region.r2_cut)
    axes = (np.log10(region.x), np.log10(region.y))
    at = (float(np.log10(pair[0])), float(np.log10(pair[1])))
    cell = []
    for axis, value in zip(axes, at):
        if value < axis[0] or value > axis[-1]:
            return float('nan')
        i = int(np.clip(np.searchsorted(axis, value), 1, axis.size - 1))
        span = axis[i] - axis[i - 1]
        cell.append((i, 0.0 if span == 0 else (value - axis[i - 1]) / span))
    (i, s), (j, t) = cell
    corners = np.array([[surface[i - 1, j - 1], surface[i - 1, j]], [surface[i, j - 1], surface[i, j]]])
    if not np.isfinite(corners).all():
        return float('nan')
    weights = np.array([[(1 - s) * (1 - t), (1 - s) * t], [s * (1 - t), s * t]])
    return float((corners * weights).sum())


def joint_region_row(scenario: Scenario, seed: int) -> dict[str, Any]:
    """Whether the joint region of a two-constant model holds the true pair.

    The row goes through :func:`~core.pipeline.profile.fit_profile`, the call
    the Identifiability tab makes, and asks the
    :class:`~core.pipeline.profile.JointRegion` it returns whether the true
    pair lies in it — the same surface, the same cut-off per cell and the same
    bounding box the tab draws, so a region the tab would draw wrongly is a
    region this check scores wrongly.

    Returns
    -------
    dict
        ``inside`` — the true pair lies in the region — with the pair's excess
        over the threshold in residual sum of squares beside it, and whether
        each one-dimensional interval holds its own truth.
    """
    started = time.perf_counter()
    data = dataset(scenario, seed)

    def work() -> dict[str, Any]:
        profiles = fit_profile(
            measurement_set(data),
            ASSAY_CLASSES[AssayType[scenario.assay]],
            dict(data.conditions),
            FitConfig(per_replica=False),
        )
        region = profiles.region
        if region is None:
            return {'inside': None}
        pair = tuple(data.truth[key] for key in region.ka_keys)
        excess = region_excess(region, pair)
        intervals = {key: profile.interval for key, profile in profiles.profiles.items()}
        return {
            'inside': bool(np.isfinite(excess) and excess <= 1.0),
            'excess': None if not np.isfinite(excess) else excess,
            # A region whose one-dimensional shadow reaches a Ka bound is
            # unbounded in that direction, as an open interval is.
            'open': any(ci is not None and (ci.open_low or ci.open_high) for ci in intervals.values()),
            'both_intervals': all(
                ci is not None and ci.low <= data.truth[key] <= ci.high for key, ci in intervals.items()
            ),
        }

    row = guard(work)
    row['t_total'] = time.perf_counter() - started
    return row
