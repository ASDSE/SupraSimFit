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


def prepare_plot_data(
    ms: MeasurementSet,
    fit_results: Optional[List[FitResult]] = None,
    *,
    show_dropped: bool = False,
) -> Dict[str, Any]:
    """Gather plot-ready data from a MeasurementSet and optional fits.

    Parameters
    ----------
    ms : MeasurementSet
        Source measurement data.
    fit_results : list[FitResult], optional
        Fit results to overlay as curves.
    show_dropped : bool
        If ``True``, include inactive replicas in the output
        (default ``False``).

    Returns
    -------
    dict[str, Any]
        Keys:

        - ``"concentrations"`` — ``np.ndarray``, shared x-axis.
        - ``"active_replicas"`` — list of ``(replica_id, signal)`` tuples.
        - ``"dropped_replicas"`` — list of ``(replica_id, signal)`` tuples
          (empty unless *show_dropped* is ``True``).
        - ``"average"`` — ``np.ndarray``, mean of active replicas.
        - ``"fits"`` — list of ``{"x": ndarray, "y": ndarray,
          "label": str, "id": str}`` dicts, one per ``FitResult``.
    """
    active = [(rid, sig.copy()) for rid, sig in ms.iter_replicas(active_only=True)]

    dropped: list[tuple[str, np.ndarray]] = []
    if show_dropped:
        for rid in ms.dropped_replica_ids:
            dropped.append((rid, ms.get_replica_signal(rid).copy()))

    avg = ms.average_signal(active_only=True) if ms.n_active > 0 else None

    fits: list[Dict[str, Any]] = []
    if fit_results:
        for fr in fit_results:
            label = 'Median Fit'
            x = fr.x_fit.magnitude
            y = fr.y_fit.magnitude
            fits.append(
                {
                    'x': x,
                    'y': y,
                    'label': label,
                    'id': fr.id,
                }
            )

    return {
        'concentrations': np.array(ms.concentrations),
        'active_replicas': active,
        'dropped_replicas': dropped,
        'all_replica_ids': tuple(ms.replica_ids),
        'average': avg,
        'fits': fits,
    }
