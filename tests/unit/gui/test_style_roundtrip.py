"""Style roundtrip test: PlotStyleWidget → PlotWidget.apply_style."""

import pytest

pytest.importorskip('PyQt6')
pytest.importorskip('pyqtgraph')


def test_style_signal_updates_plot_style(qapp, minimal_plot_data):
    from gui.plotting.plot_style import PlotStyleWidget
    from gui.plotting.plot_widget import PlotWidget

    pw = PlotWidget()
    pw.update_plot(minimal_plot_data)

    style_widget = PlotStyleWidget()
    style_widget.style_changed.connect(pw.apply_style)

    initial_style = style_widget.current_style()
    initial_size = initial_style['data_points']['size']

    # Change a parameter directly via the Parameter tree
    params = style_widget._params
    new_size = initial_size + 2
    params['Replicas', 'Size'] = new_size

    # apply_style should have been called via signal; check _style updated
    assert pw._style['data_points']['size'] == new_size


def test_apply_style_with_no_items_does_not_raise(qapp):
    """apply_style on empty plot should not raise."""
    from gui.plotting.plot_style import PlotStyleWidget
    from gui.plotting.plot_widget import PlotWidget

    pw = PlotWidget()
    style_widget = PlotStyleWidget()
    pw.apply_style(style_widget.current_style())  # must not raise


_BASELINE_STYLE = {'sensitivity': {'baseline_line_width': 4.0, 'baseline_line_color': (10, 120, 30, 255)}}


def test_baseline_line_style_round_trips_through_a_saved_template(qapp, tmp_path):
    """The Ka Sensitivity baseline keys survive save → load into a fresh widget."""
    from gui.plotting.plot_style import PlotStyleWidget, load_style_json, save_style_json

    source = PlotStyleWidget()
    source.load_style(_BASELINE_STYLE)
    assert source.current_style()['sensitivity'] == _BASELINE_STYLE['sensitivity']

    path = tmp_path / 'style.json'
    save_style_json(source.current_style(), path)
    target = PlotStyleWidget()
    target.load_style(load_style_json(path))
    assert target.current_style()['sensitivity'] == _BASELINE_STYLE['sensitivity']


def test_template_without_baseline_keys_keeps_the_default_baseline_style(qapp):
    """A template saved before the Ka Sensitivity group existed loads with the default baseline look."""
    from gui.plotting.plot_style import DEFAULT_STYLE, PlotStyleWidget

    sw = PlotStyleWidget()
    old_template = {k: v for k, v in sw.current_style().items() if k != 'sensitivity'}
    old_template['distribution']['median_line_color'] = (0, 0, 255, 255)
    sw.load_style(old_template)
    assert sw.current_style()['sensitivity'] == DEFAULT_STYLE['sensitivity']
    assert sw.current_style()['distribution']['median_line_color'] == (0, 0, 255, 255)
