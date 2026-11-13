"""The plot guide's headline example is the fit Demo IDA reports first.

Demo IDA states input uncertainties, so the fit it shows first is the
input-aware one, which costs seconds: this check lives here rather than beside
the guide's other example checks in ``tests/unit/gui/test_plot_guide.py``.
"""

from __future__ import annotations

import re
from pathlib import Path

_IDA_DATA = Path(__file__).resolve().parents[2] / 'data' / 'IDA_system.txt'


def test_the_headline_example_is_the_fit_demo_ida_reports():
    """The Fit results and Fit details examples quote Demo IDA's headline: its fit, interval, R², RMSE and first callout."""
    from core.assays import IDAAssay
    from core.data_processing.measurement_set import MeasurementSet
    from core.data_processing.preprocessing import get_step
    from core.io import load_measurements
    from core.pipeline.fit_pipeline import FitConfig, fit_measurement_set
    from core.pipeline.inputs import ErrorModel
    from core.pipeline.reporting import summarize_parameters
    from core.units import Q_
    from gui.fitting_session import _DEMO_UNCERTAINTIES
    from gui.plot_guide import FIT_CURVE, PLOT_GUIDE, SUMMARY
    from gui.plotting.labels import fmt_r2, fmt_value
    from gui.results import callouts

    # Demo IDA as its button fits it: Outlier Removal at its defaults, averaged, its stated uncertainties.
    ms = MeasurementSet.from_dataframe(load_measurements(str(_IDA_DATA)))
    get_step('zscore_replica_filter', {'threshold': 3.5, 'min_replicas': 3})(ms)
    conditions = {'h0': Q_(4.3e-6, 'M'), 'd0': Q_(6e-6, 'M'), 'Ka_dye': Q_(16.8e6, '1/M')}
    config = FitConfig(per_replica=False, errors=ErrorModel(specs=dict(_DEMO_UNCERTAINTIES)))
    result = fit_measurement_set(ms, IDAAssay, conditions, config)

    (row,) = [spec for spec in summarize_parameters(result) if spec.key == 'Ka_guest' and not spec.is_log]
    lo, hi = row.interval
    headline = (
        f'{row.estimate / 1e8:.2f}&times;10<sup>8</sup> M<sup>&minus;1</sup> [{lo / 1e8:.2f}&times;10<sup>8</sup>, '
        f'{hi / 1e8:.2f}&times;10<sup>8</sup>]'
    )
    (callout, *_) = callouts(result, None)

    fit_curve = re.sub(r'\s+', ' ', PLOT_GUIDE[FIT_CURVE][1])
    assert f'{headline}, R&sup2; {fmt_r2(result.r_squared)}, under the callout <i>{callout.title}</i>' in fit_curve
    summary = re.sub(r'\s+', ' ', PLOT_GUIDE[SUMMARY][1])
    assert f'RMSE {fmt_value(result.rmse)} a.u. and R&sup2; {fmt_r2(result.r_squared)}' in summary
