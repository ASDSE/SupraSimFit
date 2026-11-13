"""A style saved as a template loads back into Plot appearance."""

import pytest

pytest.importorskip('PyQt6')
pytest.importorskip('pyqtgraph')


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
    old_template['distribution']['tick_font_size'] = 19
    sw.load_style(old_template)
    assert sw.current_style()['sensitivity'] == DEFAULT_STYLE['sensitivity']
    assert sw.current_style()['distribution']['tick_font_size'] == 19
