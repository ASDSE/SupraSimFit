"""Tests for PlotStyleWidget x-axis unit handling.

The x-axis unit was removed from the ParameterTree (Axes group) in favour
of the Data panel's Display Unit combo. The style dict still exposes it
under ``axes.x_unit`` so saved style JSONs round-trip, but the value is
pushed in via :meth:`PlotStyleWidget.set_x_unit`.
"""

from __future__ import annotations

import pytest

pytest.importorskip('PyQt6')
pytest.importorskip('pyqtgraph')


def test_axes_group_does_not_expose_x_axis_unit(qapp):
    from gui.plotting.plot_style import PlotStyleWidget

    sw = PlotStyleWidget()
    axes_children = [child.name() for child in sw._params.child('Axes').children()]
    assert 'x-axis unit' not in axes_children


def test_set_x_unit_updates_style_dict(qapp):
    from gui.plotting.plot_style import PlotStyleWidget

    sw = PlotStyleWidget()
    assert sw.current_style()['axes']['x_unit'] == 'µM'

    sw.set_x_unit('nM')
    assert sw.current_style()['axes']['x_unit'] == 'nM'


def test_set_x_unit_emits_once(qapp):
    from gui.plotting.plot_style import PlotStyleWidget

    sw = PlotStyleWidget()
    received: list[dict] = []
    sw.style_changed.connect(received.append)

    sw.set_x_unit('mM')
    sw.set_x_unit('mM')  # no-op when unchanged

    assert len(received) == 1
    assert received[0]['axes']['x_unit'] == 'mM'


def test_load_style_restores_x_unit(qapp):
    from gui.plotting.plot_style import PlotStyleWidget

    sw = PlotStyleWidget()
    sw.load_style({'axes': {'x_unit': 'nM'}})
    assert sw.current_style()['axes']['x_unit'] == 'nM'


def test_axis_name_overrides_round_trip_via_load_style(qapp):
    from gui.plotting.plot_style import PlotStyleWidget

    sw = PlotStyleWidget()
    sw.load_style({'axes': {'x_name_override': 'Tryptamine', 'y_name_override': 'Fluorescence'}})
    axes = sw.current_style()['axes']
    assert axes['x_name_override'] == 'Tryptamine'
    assert axes['y_name_override'] == 'Fluorescence'
