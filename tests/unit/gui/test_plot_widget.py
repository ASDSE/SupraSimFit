"""Widget tests for PlotWidget — requires a QApplication."""

import pytest

pytest.importorskip('PyQt6')
pytest.importorskip('pyqtgraph')


def test_update_plot_clears_on_second_call(qapp, minimal_plot_data):
    from gui.plotting.plot_widget import PlotWidget

    pw = PlotWidget()
    pw.update_plot(minimal_plot_data)
    pw.update_plot(minimal_plot_data)

    assert len(pw._replica_items) == 2
    assert len(pw._fit_items) == 1


# ---------------------------------------------------------------------------
# GAP-16: _X_UNIT_SCALES concentration scaling
# ---------------------------------------------------------------------------


def test_x_unit_scales_values(qapp):
    from gui.plotting.plot_widget import _X_UNIT_SCALES

    assert _X_UNIT_SCALES['nM'] == pytest.approx(1e9)
    assert _X_UNIT_SCALES['µM'] == pytest.approx(1e6)
    assert _X_UNIT_SCALES['mM'] == pytest.approx(1e3)
    assert _X_UNIT_SCALES['M'] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# GAP-17: _format_exponent_unicode
# ---------------------------------------------------------------------------


def test_format_exponent_unicode_positive(qapp):
    from gui.plotting.plot_widget import _format_exponent_unicode

    assert _format_exponent_unicode(0) == '⁰'
    assert _format_exponent_unicode(3) == '³'
    assert _format_exponent_unicode(12) == '¹²'


def test_format_exponent_unicode_negative(qapp):
    from gui.plotting.plot_widget import _format_exponent_unicode

    assert _format_exponent_unicode(-1) == '⁻¹'
    assert _format_exponent_unicode(-3) == '⁻³'


def test_scientific_axis_no_exponent_in_normal_range(qapp):
    from gui.plotting.plot_widget import ScientificAxisItem

    axis = ScientificAxisItem(orientation='bottom')
    axis.tickStrings([1, 10, 100], scale=1, spacing=1)
    # In normal range, exponent stays None (no factoring needed)
    assert axis.exponent is None or axis.exponent == 0


def test_scientific_axis_factors_large_exponent(qapp):
    from gui.plotting.plot_widget import ScientificAxisItem

    axis = ScientificAxisItem(orientation='bottom')
    strings = axis.tickStrings([1e6, 2e6, 3e6], scale=1, spacing=1)
    assert axis.exponent == 6
    assert strings[0] == '1'
    assert strings[1] == '2'
    assert strings[2] == '3'


def test_scientific_axis_handles_zero_tick(qapp):
    from gui.plotting.plot_widget import ScientificAxisItem

    axis = ScientificAxisItem(orientation='bottom')
    strings = axis.tickStrings([0.0, 1e6, 2e6], scale=1, spacing=1)
    # One string per value, no exception, zero renders as plain '0'.
    assert len(strings) == 3
    assert strings == ['0', '1', '2']


def test_scientific_axis_handles_extreme_exponent(qapp):
    from gui.plotting.plot_widget import ScientificAxisItem

    axis = ScientificAxisItem(orientation='bottom')
    strings = axis.tickStrings([1e20, 2e20], scale=1, spacing=1)
    # Exponent factored out at 20; mantissas are finite, non-empty strings.
    assert axis.exponent == 20
    assert all(s for s in strings)
    assert strings == ['1', '2']


# ---------------------------------------------------------------------------
# Axis name overrides (user-editable name, auto-managed unit)
# ---------------------------------------------------------------------------


def _bottom_label(pw):
    return pw._pg_widget.getAxis('bottom').labelString()


def _left_label(pw):
    return pw._pg_widget.getAxis('left').labelString()


def test_default_x_label_uses_registry_name_and_x_unit(qapp, minimal_plot_data):
    from gui.plotting.plot_widget import PlotWidget

    pw = PlotWidget()
    pw.update_plot(minimal_plot_data, x_label='Guest', y_label='Signal', y_unit='a.u.')

    assert 'Guest' in _bottom_label(pw)
    assert '[µM]' in _bottom_label(pw)


def test_default_y_label_uses_registry_name_and_y_unit(qapp, minimal_plot_data):
    from gui.plotting.plot_widget import PlotWidget

    pw = PlotWidget()
    pw.update_plot(minimal_plot_data, x_label='Guest', y_label='Signal', y_unit='a.u.')

    assert 'Signal' in _left_label(pw)
    assert '[a.u.]' in _left_label(pw)


def test_x_name_override_replaces_name_but_keeps_unit(qapp, minimal_plot_data):
    from gui.plotting.plot_style import PlotStyleWidget
    from gui.plotting.plot_widget import PlotWidget

    pw = PlotWidget()
    pw.update_plot(minimal_plot_data, x_label='Guest', y_label='Signal', y_unit='a.u.')

    sw = PlotStyleWidget()
    sw.style_changed.connect(pw.apply_style)
    sw._params['Axes', 'X-axis name'] = 'Tryptamine'

    label = _bottom_label(pw)
    assert 'Tryptamine' in label
    assert 'Guest' not in label
    assert '[µM]' in label


def test_y_name_override_replaces_name_but_keeps_unit(qapp, minimal_plot_data):
    from gui.plotting.plot_style import PlotStyleWidget
    from gui.plotting.plot_widget import PlotWidget

    pw = PlotWidget()
    pw.update_plot(minimal_plot_data, x_label='Guest', y_label='Signal', y_unit='a.u.')

    sw = PlotStyleWidget()
    sw.style_changed.connect(pw.apply_style)
    sw._params['Axes', 'Y-axis name'] = 'Fluorescence'

    label = _left_label(pw)
    assert 'Fluorescence' in label
    assert '[a.u.]' in label


def test_x_unit_change_preserves_custom_name(qapp, minimal_plot_data):
    from gui.plotting.plot_style import PlotStyleWidget
    from gui.plotting.plot_widget import PlotWidget

    pw = PlotWidget()
    pw.update_plot(minimal_plot_data, x_label='Guest', y_label='Signal', y_unit='a.u.')

    sw = PlotStyleWidget()
    sw.style_changed.connect(pw.apply_style)
    sw._params['Axes', 'X-axis name'] = 'Tryptamine'
    sw.set_x_unit('nM')

    label = _bottom_label(pw)
    assert 'Tryptamine' in label
    assert '[nM]' in label
    assert '[µM]' not in label


def test_clearing_override_restores_default_name(qapp, minimal_plot_data):
    from gui.plotting.plot_style import PlotStyleWidget
    from gui.plotting.plot_widget import PlotWidget

    pw = PlotWidget()
    pw.update_plot(minimal_plot_data, x_label='Guest', y_label='Signal', y_unit='a.u.')

    sw = PlotStyleWidget()
    sw.style_changed.connect(pw.apply_style)
    sw._params['Axes', 'X-axis name'] = 'Tryptamine'
    sw._params['Axes', 'X-axis name'] = ''

    label = _bottom_label(pw)
    assert 'Guest' in label
    assert 'Tryptamine' not in label


def test_whitespace_only_override_falls_back_to_default(qapp):
    from gui.plotting.plot_widget import PlotWidget

    pw = PlotWidget()
    assert pw._compose_axis_label('Guest', '   ', 'µM') == 'Guest [µM]'
    assert pw._compose_axis_label('Guest', '', 'µM') == 'Guest [µM]'
    assert pw._compose_axis_label('Guest', 'Tryptamine', 'µM') == 'Tryptamine [µM]'
