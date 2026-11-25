"""Plot data preparation helpers.

Prepares structured data from a ``MeasurementSet`` and optional
``FitResult`` objects.  Returns plain dicts/arrays — **no matplotlib
dependency** — so callers (GUI, scripts) can render with their own
styling.

Usage::

    from core.data_processing.plotting import prepare_plot_data

    plot_data = prepare_plot_data(ms, fit_results=[result], show_dropped=True)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np

from core.data_processing.measurement_set import MeasurementSet
from core.pipeline.fit_pipeline import FitResult
from core.pipeline.reporting import fit_replica_ids


def prepare_plot_data(
    ms: MeasurementSet,
    fit_results: Optional[List[FitResult]] = None,
    *,
    show_dropped: bool = False,
) -> Dict[str, Any]:
    """Gather plot-ready data from a MeasurementSet and optional fits.

    With fits given, the mean is taken over the replicates the last of them
    (the fit the summary panel reports) used: the same average its RMSE and R²
    are measured against. Active replicates that fit left out are listed
    apart, so they are never drawn as data the curve describes.

    Parameters
    ----------
    ms : MeasurementSet
        Source measurement data.
    fit_results : list[FitResult], optional
        Fit results to overlay as curves, each made on the data as it is now.
    show_dropped : bool
        If ``True``, include inactive replicas in the output
        (default ``False``).

    Returns
    -------
    dict[str, Any]
        Keys:

        - ``"concentrations"`` — ``np.ndarray``, shared x-axis.
        - ``"active_replicas"`` — list of ``(replica_id, signal)`` tuples:
          the replicates the mean is taken over — those the last fit used, or
          every active replicate when no fit is given.
        - ``"left_out_replicas"`` — list of ``(replica_id, signal)`` tuples:
          active replicates the last fit left out.
        - ``"dropped_replicas"`` — list of ``(replica_id, signal)`` tuples
          for inactive replicates (empty unless *show_dropped* is ``True``).
        - ``"all_replica_ids"`` — every replicate id of *ms* in order; a
          replicate's position here gives its label and colour.
        - ``"average"`` — ``np.ndarray``, mean of ``"active_replicas"``, or
          ``None`` when there are none.
        - ``"fits"`` — list of ``{"x": ndarray, "y": ndarray, "label": str,
          "id": str, "replica_ids": tuple[str, ...]}`` dicts, one per
          ``FitResult``; ``"replica_ids"`` are the replicates that fit used.

    Raises
    ------
    ValueError
        If a fit does not record the replicates it used, or used one that is
        not active in *ms*: its curve would be drawn over data it was not made on.
    """
    active_ids = ms.active_replica_ids

    fits: list[Dict[str, Any]] = []
    for fr in fit_results or ():
        used = fit_replica_ids(fr)
        if used is None:
            raise ValueError('A fit to plot does not record which replicates it was made on.')
        not_active = [rid for rid in used if rid not in active_ids]
        if not_active:
            raise ValueError(f'A fit to plot used replicates {not_active} that are not active in the data.')
        fits.append(
            {
                'x': fr.x_fit.magnitude,
                'y': fr.y_fit.magnitude,
                'label': 'Fit',
                'id': fr.id,
                'replica_ids': tuple(used),
            }
        )

    mean_ids = set(fits[-1]['replica_ids']) if fits else set(active_ids)
    active: list[tuple[str, np.ndarray]] = []
    left_out: list[tuple[str, np.ndarray]] = []
    for rid, sig in ms.iter_replicas(active_only=True):
        (active if rid in mean_ids else left_out).append((rid, sig.copy()))

    dropped: list[tuple[str, np.ndarray]] = []
    if show_dropped:
        for rid in ms.dropped_replica_ids:
            dropped.append((rid, ms.get_replica_signal(rid).copy()))

    avg = ms.with_active(mean_ids).average_signal(active_only=True) if active else None

    return {
        'concentrations': np.array(ms.concentrations),
        'active_replicas': active,
        'left_out_replicas': left_out,
        'dropped_replicas': dropped,
        'all_replica_ids': tuple(ms.replica_ids),
        'average': avg,
        'fits': fits,
    }
