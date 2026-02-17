"""Widget tests for PlotWidget — requires a QApplication."""

import numpy as np
import pytest

pytest.importorskip("PyQt6")
pytest.importorskip("pyqtgraph")


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    import sys
    app = QApplication.instance() or QApplication(sys.argv)
    return app


@pytest.fixture
def minimal_plot_data():
    x = np.linspace(0, 1e-4, 20)
    return {
        "concentrations": x,
        "active_replicas": [("r1", x * 1.1 + 0.01), ("r2", x * 0.9 + 0.02)],
        "dropped_replicas": [("r3", x * 1.5)],
        "average": x * 1.0 + 0.015,
        "fits": [{"x": x, "y": x * 1.05 + 0.012, "label": "GDA fit", "id": "abc123"}],
    }


def test_update_plot_replica_count(qapp, minimal_plot_data):
    from gui.plotting.plot_widget import PlotWidget

    pw = PlotWidget()
    pw.update_plot(minimal_plot_data)

    assert len(pw._replica_items) == 2


def test_update_plot_fit_count(qapp, minimal_plot_data):
    from gui.plotting.plot_widget import PlotWidget

    pw = PlotWidget()
    pw.update_plot(minimal_plot_data)

    assert len(pw._fit_items) == 1


def test_clear_items_empties_all_lists(qapp, minimal_plot_data):
    from gui.plotting.plot_widget import PlotWidget

    pw = PlotWidget()
    pw.update_plot(minimal_plot_data)
    pw._clear_items()

    assert pw._replica_items == []
    assert pw._dropped_item is None
    assert pw._average_item is None
    assert pw._error_bar_item is None
    assert pw._fit_items == []


def test_update_plot_clears_on_second_call(qapp, minimal_plot_data):
    from gui.plotting.plot_widget import PlotWidget

    pw = PlotWidget()
    pw.update_plot(minimal_plot_data)
    pw.update_plot(minimal_plot_data)

    assert len(pw._replica_items) == 2
    assert len(pw._fit_items) == 1


def test_update_plot_no_fits(qapp):
    from gui.plotting.plot_widget import PlotWidget

    x = np.linspace(0, 1e-4, 10)
    data = {
        "concentrations": x,
        "active_replicas": [("r1", x)],
        "dropped_replicas": [],
        "average": x,
        "fits": [],
    }
    pw = PlotWidget()
    pw.update_plot(data)

    assert pw._fit_items == []
    assert len(pw._replica_items) == 1


def test_set_axis_labels_does_not_raise(qapp):
    from gui.plotting.plot_widget import PlotWidget

    pw = PlotWidget()
    pw.set_axis_labels("[Guest] / M", "Signal / a.u.")
