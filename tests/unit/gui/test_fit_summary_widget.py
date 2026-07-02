"""Widget tests for FitSummaryWidget — requires a QApplication."""

import numpy as np
import pytest

pytest.importorskip('PyQt6')


@pytest.fixture
def minimal_fit_result():
    from core.pipeline.fit_pipeline import FitResult

    x = np.linspace(0, 1e-4, 20)
    return FitResult(
        parameters={'Ka_guest': 1e6, 'I0': 100.0, 'I_dye_free': 5e4, 'I_dye_bound': 8e4},
        uncertainties={'Ka_guest': 1e5, 'I0': 5.0, 'I_dye_free': 2e3, 'I_dye_bound': 3e3},
        rmse=0.005,
        r_squared=0.998,
        n_passing=87,
        n_total=100,
        x_fit=x,
        y_fit=x * 1.05 + 0.01,
        assay_type='GDA',
        model_name='equilibrium_4param',
    )


def test_update_result_metric_labels_nonempty(qapp, minimal_fit_result):
    from gui.plotting.fit_summary_widget import FitSummaryWidget

    widget = FitSummaryWidget()
    widget.update_result(minimal_fit_result)

    assert widget._rmse_label.text() not in ('', '—')
    assert widget._r2_label.text() not in ('', '—')
    assert widget._passing_label.text() not in ('', '—')


def test_clear_resets_state(qapp, minimal_fit_result):
    from gui.plotting.fit_summary_widget import FitSummaryWidget

    widget = FitSummaryWidget()
    widget.update_result(minimal_fit_result)
    widget.clear()

    assert widget._table.rowCount() == 0
    assert widget._rmse_label.text() == '—'
    assert widget._r2_label.text() == '—'
    assert widget._passing_label.text() == '—'


def test_unknown_assay_type_does_not_crash(qapp):
    from core.pipeline.fit_pipeline import FitResult
    from gui.plotting.fit_summary_widget import FitSummaryWidget

    x = np.linspace(0, 1e-4, 5)
    result = FitResult(
        parameters={'slope': 1.5},
        uncertainties={'slope': 0.1},
        rmse=0.01,
        r_squared=0.99,
        n_passing=1,
        n_total=1,
        x_fit=x,
        y_fit=x * 1.5,
        assay_type='UNKNOWN_TYPE',
        model_name='linear',
    )
    widget = FitSummaryWidget()
    widget.update_result(result)  # must not raise

    assert widget._table.rowCount() == 1


@pytest.fixture
def full_fit_result():
    """A FitResult carrying the ensemble pool (parameter + quality samples)."""
    from core.pipeline.fit_pipeline import FitResult

    x = np.linspace(0, 1e-4, 20)
    samples = {
        'Ka_guest': np.array([1.0e6, 1.1e6, 0.9e6]),
        'I0': np.array([100.0, 90.0, 110.0]),
        'I_dye_free': np.array([5.0e4, 5.1e4, 4.9e4]),
        'I_dye_bound': np.array([8.0e4, 8.1e4, 7.9e4]),
    }
    quality = {
        'rmse': np.array([0.006, 0.005, 0.007]),
        'r_squared': np.array([0.997, 0.998, 0.996]),
    }
    return FitResult(
        # Representative = index 1 (best RMSE / R²).
        parameters={'Ka_guest': 1.1e6, 'I0': 90.0, 'I_dye_free': 5.1e4, 'I_dye_bound': 8.1e4},
        uncertainties={'Ka_guest': 1e5, 'I0': 10.0, 'I_dye_free': 1e3, 'I_dye_bound': 1e3},
        rmse=0.005,
        r_squared=0.998,
        n_passing=3,
        n_total=10,
        x_fit=x,
        y_fit=x * 1.05,
        assay_type='GDA',
        model_name='equilibrium_4param',
        parameter_samples=samples,
        quality_samples=quality,
        representative_index=1,
        statistics_mode='median',
    )


def test_seven_columns_with_stats_populated(qapp, full_fit_result):
    from gui.plotting.fit_summary_widget import _COLUMN_HEADERS, FitSummaryWidget

    widget = FitSummaryWidget()
    widget.update_result(full_fit_result)

    assert widget._table.columnCount() == 7
    headers = [widget._table.horizontalHeaderItem(c).text() for c in range(7)]
    assert headers == list(_COLUMN_HEADERS)
    # Median / MAD / Mean / STDEV cells are populated (not the '—' placeholder).
    for col in (2, 3, 4, 5):
        cell = widget._table.cellWidget(0, col)
        assert cell is not None and cell.text() not in ('', '—')


def test_statistics_mode_toggle_emits(qapp, full_fit_result):
    from gui.plotting.fit_summary_widget import FitSummaryWidget

    widget = FitSummaryWidget()
    widget.update_result(full_fit_result)
    captured = []
    widget.statistics_mode_changed.connect(captured.append)

    widget._stats_combo.setCurrentIndex(widget._stats_combo.findData('mean'))
    assert captured == ['mean']


def test_representative_selector_emits_pool_index(qapp, full_fit_result):
    from gui.plotting.fit_summary_widget import FitSummaryWidget

    widget = FitSummaryWidget()
    widget.update_result(full_fit_result)
    captured = []
    widget.representative_selected.connect(captured.append)

    # Items are ordered best-first by RMSE (argsort -> pool indices [1, 0, 2]);
    # selecting the 3rd item reports pool index 2.
    widget._rep_combo.setCurrentIndex(2)
    assert captured == [2]
