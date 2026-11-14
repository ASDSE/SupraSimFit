"""Plot appearance offers only what a plot reads (:mod:`gui.plotting.plot_style`).

App behaviour must reflect the user's configuration exactly, so a control no plot
reads would be ignored with no word; every one must change the look of a plot.
"""

from __future__ import annotations

import pytest

pytest.importorskip('PyQt6')
pytest.importorskip('pyqtgraph')


class _Recording(dict):
    """A style dict that records every key a plot reads from it, nested sections included."""

    def __init__(self, data: dict, read: set, path: tuple = ()):
        super().__init__({k: _Recording(v, read, (*path, k)) if isinstance(v, dict) else v for k, v in data.items()})
        self.read, self.path = read, path

    def __getitem__(self, key):
        self.read.add((*self.path, key))
        return super().__getitem__(key)

    def get(self, key, default=None):
        self.read.add((*self.path, key))
        return super().get(key, default)


def _leaves(style: dict, path: tuple = ()) -> set:
    return {
        leaf
        for key, value in style.items()
        for leaf in (_leaves(value, (*path, key)) if isinstance(value, dict) else {(*path, key)})
    }


def test_every_control_of_plot_appearance_is_read_by_a_plot(qapp):
    """Each setting the panel emits is read when the Sensitivity plots draw a result."""
    from gui.plotting.plot_style import PlotStyleWidget
    from gui.plotting.sensitivity_widget import SensitivityWidget
    from tests.unit.gui.test_sensitivity_gui import _sobol_result

    style = PlotStyleWidget().current_style()
    read: set = set()
    widget = SensitivityWidget()
    widget.update_result(_sobol_result())
    widget.apply_style(_Recording(style, read))

    assert _leaves(style) <= read
    widget.close()


def test_plot_appearance_reaches_the_plots_of_the_session(qapp):
    """A change in the panel restyles Sensitivity, the plot that reads a style."""
    from gui.fitting_session import FittingSession

    session = FittingSession()
    session._style_widget._params['Analysis plots', 'Tick font size'] = 19

    assert session._sensitivity_widget._style['distribution']['tick_font_size'] == 19
    session.close()
