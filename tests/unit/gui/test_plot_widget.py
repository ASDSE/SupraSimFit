"""Widget tests for PlotWidget — requires a QApplication."""

import pytest

pytest.importorskip('PyQt6')
pytest.importorskip('pyqtgraph')


def test_building_the_fit_curve_plot_leaves_the_library_defaults_alone(qapp):
    """The plot widget styles its own view, never pyqtgraph's process-wide defaults.

    Those defaults reach every plot the application builds afterwards. With
    antialiasing switched on for the whole process, the one-pixel stroke that
    keeps a thin histogram bin visible on the Ka Sensitivity tab is drawn
    blended into the background and vanishes.
    """
    import pyqtgraph as pg

    from gui.plotting.plot_widget import PlotWidget

    keys = ('background', 'foreground', 'antialias')
    before = {key: pg.getConfigOption(key) for key in keys}

    PlotWidget()

    assert {key: pg.getConfigOption(key) for key in keys} == before


def test_the_fit_curve_plot_draws_every_curve_antialiased(qapp, minimal_plot_data):
    """Each curve carries its own antialiasing setting and paints by that, never by the view's.

    A curve left at the library's default is drawn in hard stair-steps, on
    screen and in every picture saved from the tab.
    """
    from gui.plotting.plot_widget import PlotWidget

    pw = PlotWidget()
    pw.update_plot(minimal_plot_data)

    curves = [pw._average_item, *pw._fit_items, *pw._error_cap_items]
    assert curves and all(item.opts['antialias'] for item in curves)


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


# ---------------------------------------------------------------------------
# Legend auto-placement
# ---------------------------------------------------------------------------


def _binding_plot(qapp, *, x_max=5e-5):
    """A shown PlotWidget with a saturating titration and its curve.

    The curve runs lower-left to upper-right, so the top-left and bottom-right
    regions are genuinely empty — placement has somewhere correct to go.
    """
    import numpy as np
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication

    from gui.plotting.plot_widget import PlotWidget

    def curve(c):
        return 1000 + 4000 * c / (c + x_max / 5)

    x = np.linspace(x_max / 25, x_max, 25)
    y = curve(x)
    x_dense = np.linspace(x[0], x[-1], 300)
    pw = PlotWidget()
    pw.update_plot(
        {
            'concentrations': x,
            'active_replicas': [('r1', y)],
            'dropped_replicas': [],
            'average': y,
            'fits': [{'x': x_dense, 'y': curve(x_dense), 'label': 'Simulated model', 'id': 'abc'}],
        },
        x_label='Guest',
        y_label='Signal',
    )
    pw.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    pw.resize(900, 600)
    pw.show()
    QApplication.processEvents()
    return pw


@pytest.mark.parametrize(
    'free_corner',
    ['top-left', 'top-right', 'bottom-left', 'bottom-right'],
)
def test_placement_finds_the_one_free_corner(qapp, free_corner):
    """With every region occupied but one, the search must land in that one.

    Drives ``_best_overlay_slot`` directly against a synthetic obstacle cloud,
    so it pins the search rather than the shape of any particular dataset —
    including the cases where the preferred top-right corner is unavailable.
    """
    import numpy as np

    pw = _binding_plot(qapp)
    vb = pw._pg_widget.getViewBox()
    w, h = vb.width(), vb.height()

    # A dense grid over the whole viewport, minus the quadrant left free.
    gx, gy = np.meshgrid(np.linspace(0, w, 60), np.linspace(0, h, 60))
    px, py = gx.ravel(), gy.ravel()
    left = px < w / 2
    top = py < h / 2
    free = {
        'top-left': left & top,
        'top-right': ~left & top,
        'bottom-left': left & ~top,
        'bottom-right': ~left & ~top,
    }[free_corner]
    cloud = np.column_stack((px[~free], py[~free]))

    pw._obstacle_points_px = lambda: cloud
    slot = pw._best_overlay_slot((w / 4, h / 4))
    assert slot is not None
    (fx, fy), rect = slot

    expected = {'top-left': (0.0, 0.0), 'top-right': (1.0, 0.0), 'bottom-left': (0.0, 1.0), 'bottom-right': (1.0, 1.0)}
    assert (fx, fy) == expected[free_corner]
    covered = (
        (cloud[:, 0] >= rect.left())
        & (cloud[:, 0] <= rect.right())
        & (cloud[:, 1] >= rect.top())
        & (cloud[:, 1] <= rect.bottom())
    ).sum()
    assert covered == 0


def test_degenerate_view_range_does_not_break_placement(qapp, monkeypatch):
    """A zero-width view range must yield no obstacles, not a divide-by-zero.

    Reachable with a single titration point, or an all-identical signal column.
    Patched via ``monkeypatch`` so the collapsed range is restored afterwards —
    a ViewBox left reporting it would fault on a later repaint.
    """
    pw = _binding_plot(qapp)
    vb = pw._pg_widget.getViewBox()
    monkeypatch.setattr(vb, 'viewRange', lambda: [[1.0, 1.0], [0.0, 5.0]])  # collapsed x

    points = pw._obstacle_points_px()
    assert points.shape == (0, 2)

    # Placement still answers, treating the plot as empty.
    slot = pw._best_overlay_slot((50.0, 20.0))
    assert slot is not None


# ---------------------------------------------------------------------------
# Replicates a fit left out, and replicate colours
# ---------------------------------------------------------------------------


def _four_replicates():
    """Four replicates A–D whose levels differ, so a mean over a subset is distinguishable."""
    import numpy as np

    from core.data_processing.measurement_set import MeasurementSet

    rng = np.random.default_rng(5)
    conc = np.linspace(1e-6, 1e-5, 8)
    signals = np.stack([1e4 * (1 + 0.2 * i) * conc / (conc + 3e-6) + rng.normal(0, 30, conc.size) for i in range(4)])
    return MeasurementSet(concentrations=conc, signals=signals, replica_ids=('0', '1', '2', '3'))


def _fit_leaving_out(ms, left_out):
    """A per-replicate fit given the active replicates of *ms* that left out *left_out*."""
    import numpy as np

    from core.pipeline.fit_pipeline import FitResult
    from core.units import Q_

    given = ms.active_replica_ids
    used = [rid for rid in given if rid not in left_out]
    x = np.linspace(ms.concentrations[0], ms.concentrations[-1], 60)
    rows = [ms.replica_ids.index(rid) for rid in used]
    return FitResult(
        parameters={'Ka_guest': Q_(3.1e5, '1/M'), 'I_0': Q_(100.0, 'au')},
        rmse=41.0,
        r_squared=0.9921,
        x_fit=Q_(x, 'M'),
        y_fit=Q_(np.interp(x, ms.concentrations, ms.signals[rows].mean(axis=0)), 'au'),
        assay_type='IDA',
        model_name='equilibrium_4param',
        fit_config={'per_replicate': True, 'level': 0.95},
        metadata={
            'active_replica_ids': given,
            'replica_ids_fit': used,
            'replica_failures': {
                rid: 'Its own best fit needs a different Ka than the other replicates share.' for rid in left_out
            },
        },
    )


def _replicate_colours(pw):
    """RGB of each replicate drawn in its own colour, by replicate id."""
    return {rid: item.opts['brush'].color().getRgb()[:3] for item, rid in zip(pw._replica_items, pw._replica_ids)}


def _legend_labels(pw):
    return [label.text for _, label in pw._legend.items]


@pytest.mark.parametrize('switched_off', [(), ('1',)], ids=['all-on', 'B-off-before-the-fit'])
def test_replicate_colours_and_labels_stay_when_a_fit_appears(qapp, switched_off):
    """Catches colours taken from a replicate's place among the drawn ones, which shift once B is off or A left out."""
    from core.data_processing.plotting import prepare_plot_data
    from gui.plotting.colors import REPLICA_PALETTE
    from gui.plotting.plot_widget import PlotWidget

    ms = _four_replicates()
    for rid in switched_off:
        ms.set_active(rid, False)
    pw = PlotWidget()
    pw.update_plot(prepare_plot_data(ms, show_dropped=True))
    before = _replicate_colours(pw)
    before_labels = _legend_labels(pw)

    fit = _fit_leaving_out(ms, ['0'])
    pw.update_plot(prepare_plot_data(ms, [fit], show_dropped=True))
    after = _replicate_colours(pw)

    assert before == {rid: REPLICA_PALETTE[int(rid)] for rid in ms.active_replica_ids}
    assert after == {rid: before[rid] for rid in fit.metadata['replica_ids_fit']}
    labels = _legend_labels(pw)
    assert 'A (left out of fit)' in labels
    assert [text for text in labels if len(text) == 1] == [text for text in before_labels if len(text) == 1][1:]
    assert ('B (dropped)' in labels) == bool(switched_off) == ('B (dropped)' in before_labels)


def test_mean_and_sd_cover_only_the_replicates_the_fit_used(qapp):
    """Catches Mean ± SD over every active replicate while the fit's R² is measured on fewer."""
    import numpy as np

    from core.data_processing.plotting import prepare_plot_data
    from gui.plotting.plot_widget import PlotWidget

    ms = _four_replicates()
    fit = _fit_leaving_out(ms, ['0'])
    pw = PlotWidget()
    pw.update_plot(prepare_plot_data(ms, [fit], show_dropped=True))

    _, mean = pw._average_item.getData()
    sd = pw._error_bar_item.opts['height'] / 2
    np.testing.assert_allclose(mean, ms.signals[1:].mean(axis=0), rtol=1e-15)
    np.testing.assert_allclose(sd, ms.signals[1:].std(axis=0), rtol=1e-12)
    assert pw._left_out_replica_ids == ['0']


@pytest.mark.parametrize('top', [9900.0, 10300.0, 10800.0, 12000.0, 2.4e4])
def test_the_axis_exponent_is_the_one_its_major_labels_are_written_with(qapp, top):
    """Major ticks ending at 10 000 are written plain; a minor tick past it must not put ×10⁴ on the axis.

    Every tick label is read back and multiplied by the exponent the axis
    announces: the product has to be the tick's own value.
    """
    import numpy as np
    import pyqtgraph as pg

    from gui.plotting.plot_widget import ScientificAxisItem

    axis = ScientificAxisItem(orientation='left')
    pw = pg.PlotWidget(axisItems={'left': axis})
    pw.resize(900, 560)
    pw.plot(np.linspace(0, 600, 24), np.linspace(0, top, 24))
    pw.getPlotItem().getViewBox().setYRange(0, top, padding=0)
    written = []
    original = axis.tickStrings

    def spy(values, scale, spacing):
        strings = original(values, scale, spacing)
        written.extend(zip(values, strings))
        return strings

    axis.tickStrings = spy
    pw.show()
    qapp.processEvents()
    pw.grab()
    qapp.processEvents()

    assert written
    factor = 10.0 ** (axis.exponent or 0)
    for value, text in written:
        assert float(text) * factor == pytest.approx(value, rel=1e-9, abs=1e-9)
    pw.close()
