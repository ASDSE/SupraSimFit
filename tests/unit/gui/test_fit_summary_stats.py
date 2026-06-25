"""FitSummaryWidget: the Median ± MAD and Mean ± STDEV stat pairs.

Math correctness of the aggregation lives in ``test_filters_mean_std.py``;
here we verify the widget wiring — that the pool feeds the classical pair, the
robust pair comes from the stored median/MAD, and the mode caption is right.
"""

import numpy as np
import pytest

pytest.importorskip('PyQt6')


def _make_result(**overrides):
    from core.pipeline.fit_pipeline import FitResult

    x = np.linspace(0, 1e-4, 10)
    base = dict(
        parameters={'Ka_guest': 2.0, 'I0': 100.0},
        uncertainties={'Ka_guest': 0.5, 'I0': 5.0},
        rmse=0.01,
        r_squared=0.99,
        n_passing=3,
        n_total=10,
        x_fit=x,
        y_fit=x,
        assay_type='GDA',
        model_name='equilibrium_4param',
        parameter_samples={
            'Ka_guest': np.array([1.0, 2.0, 3.0]),
            'I0': np.array([95.0, 100.0, 105.0]),
        },
    )
    base.update(overrides)
    return FitResult(**base)


def test_table_has_two_stat_pair_columns(qapp):
    from gui.plotting.fit_summary_widget import FitSummaryWidget

    widget = FitSummaryWidget()
    widget.update_result(_make_result())

    headers = [widget._table.horizontalHeaderItem(c).text() for c in range(widget._table.columnCount())]
    assert headers == ['Parameter', 'Median ± MAD', 'Mean ± STDEV', 'Units']
    assert widget._table.rowCount() == 2


def test_stat_pairs_reflect_pool_and_stored_values(qapp):
    """UNKNOWN_TYPE has no registry units, so values format as plain %.3g and we
    can assert the exact cell text. Median/MAD come from the stored Quantities;
    Mean/STDEV are computed from the pool [1,2,3] -> mean 2, sample STDEV 1."""
    from gui.plotting.fit_summary_widget import FitSummaryWidget

    widget = FitSummaryWidget()
    widget.update_result(
        _make_result(
            assay_type='UNKNOWN_TYPE',
            parameters={'p': 2.0},
            uncertainties={'p': 0.5},
            parameter_samples={'p': np.array([1.0, 2.0, 3.0])},
        )
    )

    assert widget._table.cellWidget(0, 1).text() == '2 ± 0.5'  # Median ± MAD
    assert widget._table.cellWidget(0, 2).text() == '2 ± 1'  # Mean ± STDEV


def test_mean_stdev_unavailable_without_pool(qapp):
    from gui.plotting.fit_summary_widget import FitSummaryWidget

    widget = FitSummaryWidget()
    widget.update_result(_make_result(parameter_samples=None))

    # No pool -> classical pair cannot be computed; robust pair still shows.
    assert widget._table.cellWidget(0, 2).text() == '—'
    assert '±' in widget._table.cellWidget(0, 1).text()


def test_caption_distinguishes_modes(qapp):
    from gui.plotting.fit_summary_widget import FitSummaryWidget

    widget = FitSummaryWidget()

    widget.update_result(_make_result())
    assert 'average mode' in widget._caption.text()

    widget.update_result(
        _make_result(
            uncertainty_source='replicate',
            metadata={'pool_size': 9, 'n_replicas_fit': 3},
        )
    )
    caption = widget._caption.text()
    assert 'per-replica mode' in caption
    assert '9' in caption and '3' in caption


def test_clear_resets_caption(qapp):
    from gui.plotting.fit_summary_widget import FitSummaryWidget

    widget = FitSummaryWidget()
    widget.update_result(_make_result())
    widget.clear()

    assert widget._table.rowCount() == 0
    assert widget._caption.text() == ''
