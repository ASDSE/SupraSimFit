"""Style roundtrip test: PlotStyleWidget → PlotWidget.apply_style."""

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
        "dropped_replicas": [],
        "average": x * 1.0 + 0.015,
        "fits": [{"x": x, "y": x * 1.05 + 0.012, "label": "GDA fit", "id": "abc123"}],
    }


def test_style_signal_updates_plot_style(qapp, minimal_plot_data):
    from gui.plotting.plot_style import PlotStyleWidget
    from gui.plotting.plot_widget import PlotWidget

    pw = PlotWidget()
    pw.update_plot(minimal_plot_data)

    style_widget = PlotStyleWidget()
    style_widget.style_changed.connect(pw.apply_style)

    initial_style = style_widget.current_style()
    initial_size = initial_style["data_points"]["size"]

    # Change a parameter directly via the Parameter tree
    params = style_widget._params
    new_size = initial_size + 2
    params["Replicas", "Size"] = new_size

    # apply_style should have been called via signal; check _style updated
    assert pw._style["data_points"]["size"] == new_size


def test_apply_style_with_no_items_does_not_raise(qapp):
    """apply_style on empty plot should not raise."""
    from gui.plotting.plot_style import PlotStyleWidget
    from gui.plotting.plot_widget import PlotWidget

    pw = PlotWidget()
    style_widget = PlotStyleWidget()
    pw.apply_style(style_widget.current_style())  # must not raise
