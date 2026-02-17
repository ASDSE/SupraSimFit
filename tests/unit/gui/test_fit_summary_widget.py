"""Widget tests for FitSummaryWidget — requires a QApplication."""

import numpy as np
import pytest

pytest.importorskip("PyQt6")


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    import sys
    app = QApplication.instance() or QApplication(sys.argv)
    return app


@pytest.fixture
def minimal_fit_result():
    from core.pipeline.fit_pipeline import FitResult

    x = np.linspace(0, 1e-4, 20)
    return FitResult(
        parameters={"Ka_guest": 1e6, "I0": 100.0, "I_dye_free": 5e4, "I_dye_bound": 8e4},
        uncertainties={"Ka_guest": 1e5, "I0": 5.0, "I_dye_free": 2e3, "I_dye_bound": 3e3},
        rmse=0.005,
        r_squared=0.998,
        n_passing=87,
        n_total=100,
        x_fit=x,
        y_fit=x * 1.05 + 0.01,
        assay_type="GDA",
        model_name="equilibrium_4param",
    )


def test_update_result_row_count(qapp, minimal_fit_result):
    from gui.plotting.fit_summary_widget import FitSummaryWidget

    widget = FitSummaryWidget()
    widget.update_result(minimal_fit_result)

    assert widget._table.rowCount() == len(minimal_fit_result.parameters)


def test_update_result_metric_labels_nonempty(qapp, minimal_fit_result):
    from gui.plotting.fit_summary_widget import FitSummaryWidget

    widget = FitSummaryWidget()
    widget.update_result(minimal_fit_result)

    assert widget._rmse_label.text() not in ("", "—")
    assert widget._r2_label.text() not in ("", "—")
    assert widget._passing_label.text() not in ("", "—")


def test_clear_resets_state(qapp, minimal_fit_result):
    from gui.plotting.fit_summary_widget import FitSummaryWidget

    widget = FitSummaryWidget()
    widget.update_result(minimal_fit_result)
    widget.clear()

    assert widget._table.rowCount() == 0
    assert widget._rmse_label.text() == "—"
    assert widget._r2_label.text() == "—"
    assert widget._passing_label.text() == "—"


def test_unknown_assay_type_does_not_crash(qapp):
    from core.pipeline.fit_pipeline import FitResult
    from gui.plotting.fit_summary_widget import FitSummaryWidget

    x = np.linspace(0, 1e-4, 5)
    result = FitResult(
        parameters={"slope": 1.5},
        uncertainties={"slope": 0.1},
        rmse=0.01,
        r_squared=0.99,
        n_passing=1,
        n_total=1,
        x_fit=x,
        y_fit=x * 1.5,
        assay_type="UNKNOWN_TYPE",
        model_name="linear",
    )
    widget = FitSummaryWidget()
    widget.update_result(result)  # must not raise

    assert widget._table.rowCount() == 1
