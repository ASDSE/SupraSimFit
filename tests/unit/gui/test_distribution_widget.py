"""Widget tests for DistributionWidget — selection, highlight, toggles, box/histogram view.

Requires a QApplication (the ``qapp`` fixture).
"""

import copy
from dataclasses import replace

import numpy as np
import pytest

pytest.importorskip('PyQt6')


@pytest.fixture
def pooled_result():
    """A FitResult carrying parameter + quality pools (average mode)."""
    from core.pipeline.fit_pipeline import FitResult
    from core.units import Q_

    n = 8
    ps = {
        'Ka_guest': np.linspace(1e6, 3e6, n),
        'I0': np.linspace(-1.0, 1.0, n),
        'I_dye_free': np.linspace(4.9e7, 5.1e7, n),
        'I_dye_bound': np.linspace(2.9e8, 3.1e8, n),
    }
    qs = {'rmse': np.linspace(0.01, 0.05, n), 'r_squared': np.linspace(0.999, 0.99, n)}
    rep = 2
    return FitResult(
        parameters={k: Q_(float(v[rep]), 'dimensionless') for k, v in ps.items()},
        rmse=0.02,
        r_squared=0.996,
        n_passing=n,
        n_total=n,
        x_fit=Q_(np.zeros(3), 'M'),
        y_fit=Q_(np.zeros(3), 'au'),
        assay_type='IDA',
        model_name='equilibrium_4param',
        parameter_samples=ps,
        quality_samples=qs,
        representative_index=rep,
    )


@pytest.fixture
def per_replica_result(pooled_result):
    """The same pool split across two replicates, '0' and '1' (per-replica mode)."""
    ps = pooled_result.parameter_samples
    halves = [{k: v[:4] for k, v in ps.items()}, {k: v[4:] for k, v in ps.items()}]
    replicas = [
        replace(pooled_result, parameter_samples=h, quality_samples=None, representative_index=None) for h in halves
    ]
    return replace(
        pooled_result,
        replica_fits=replicas,
        metadata={'active_replica_ids': ['0', '1'], 'replica_ids_fit': ['0', '1']},
    )


class _Spot:
    """Stand-in for a pyqtgraph SpotItem carrying a pool index."""

    def __init__(self, idx):
        self._idx = idx

    def data(self):
        return self._idx


def test_multi_hit_click_reports_front_most(qapp, pooled_result):
    """Regression: sigClicked hands an ndarray of ≥2 SpotItems; the handler
    must not raise (the old ``if not points`` did) and reports the front one."""
    from gui.plotting.distribution_widget import DistributionWidget

    w = DistributionWidget()
    w.update_result(pooled_result)
    captured = []
    w.representative_selected.connect(captured.append)

    w._on_point_clicked(None, np.array([_Spot(5), _Spot(3)], dtype=object))
    assert captured == [5]  # front-most (index 0 of the array)


def test_empty_click_does_not_raise(qapp, pooled_result):
    from gui.plotting.distribution_widget import DistributionWidget

    w = DistributionWidget()
    w.update_result(pooled_result)
    w._on_point_clicked(None, np.array([], dtype=object))  # must not raise


def test_strip_coords_map_the_drawn_points(qapp):
    """_draw_strip returns pool-index → (x, y) matching the values it drew."""
    import pyqtgraph as pg

    from gui.plotting.distribution_widget import DistributionWidget

    w = DistributionWidget()
    plot = pg.PlotItem()
    values = np.array([1.0, 2.0, 3.0, 4.0])
    coords = w._draw_strip(plot, values, None, 'Ka_guest', 0, [], False, [0], interactive=False)
    assert set(coords.keys()) == set(range(4))
    for i, v in enumerate(values):
        assert coords[i][1] == pytest.approx(v)  # y is the pool value (raw)


def test_selection_ring_sits_on_representative_log_value(qapp, pooled_result):
    """Issue 2: the ring lands on the representative's *displayed* value —
    log₁₀(Ka) on a log-scaled Ka subplot, not the raw Ka (the old bug)."""
    import pyqtgraph as pg

    from gui.plotting.distribution_widget import DistributionWidget

    w = DistributionWidget()
    w.update_result(pooled_result)

    ka_plot = w._plot_by_key['Ka_guest'].getPlotItem()
    rings = [it for it in ka_plot.items if isinstance(it, pg.ScatterPlotItem) and it.zValue() == 1000]
    assert len(rings) == 1
    _, ys = rings[0].getData()
    rep = pooled_result.representative_index
    expected = np.log10(pooled_result.parameter_samples['Ka_guest'][rep])
    assert float(ys[0]) == pytest.approx(expected)


def test_toggle_hides_and_shows_subplots(qapp, pooled_result):
    from gui.plotting.distribution_widget import DistributionWidget

    w = DistributionWidget()
    w.update_result(pooled_result)

    # isHidden() reflects the explicit visibility flag (isVisible() is also
    # False here because the top-level window is never shown in a headless test).
    w._on_toggle('Ka_guest', False)
    assert w._plot_by_key['Ka_guest'].isHidden()
    assert 'Ka_guest' in w._hidden_keys
    assert w._stack.currentWidget() is w._plot_container  # others still shown

    for k in list(w._all_keys):
        w._on_toggle(k, False)
    assert w._stack.currentWidget() is w._all_hidden  # explicit all-hidden page

    w._on_toggle('Ka_guest', True)
    assert not w._plot_by_key['Ka_guest'].isHidden()
    assert 'Ka_guest' not in w._hidden_keys
    assert w._stack.currentWidget() is w._plot_container


# ---------------------------------------------------------------------------
# Box plot | Histogram view
# ---------------------------------------------------------------------------


def _histogram_bars(widget, key):
    """The histogram drawn in *key*'s subplot, or ``None`` when it shows a box plot.

    A histogram is one bar series whose bars all grow from a count of zero;
    a box plot draws its box(es) around the replica positions instead.
    """
    import pyqtgraph as pg

    items = [it for it in widget._plot_by_key[key].getPlotItem().items if isinstance(it, pg.BarGraphItem)]
    if len(items) != 1 or np.any(np.asarray(items[0].opts['x0']) != 0):
        return None
    return items[0]


def _counts(widget, key):
    bars = _histogram_bars(widget, key)
    return None if bars is None else np.asarray(bars.opts['width'])


def _value_span(widget, key):
    """(lowest, highest) bin edge of *key*'s histogram, on its displayed value axis."""
    opts = _histogram_bars(widget, key).opts
    return float(opts['y0'][0]), float(opts['y0'][-1] + opts['height'][-1])


def test_view_toggle_switches_view_and_survives_new_result_and_style(qapp, pooled_result):
    from gui.plotting.distribution_widget import DistributionWidget
    from gui.plotting.plot_style import DEFAULT_STYLE

    w = DistributionWidget()
    w.update_result(pooled_result)
    assert _counts(w, 'Ka_guest') is None  # box plot is the default view
    assert not w._bins_spin.isEnabled()

    w._hist_radio.setChecked(True)
    assert w._bins_spin.isEnabled()
    assert all(_counts(w, k) is not None for k in w._all_keys)

    w.update_result(replace(pooled_result, representative_index=0))
    assert w._hist_radio.isChecked()
    assert all(_counts(w, k) is not None for k in w._all_keys)
    w.apply_style(copy.deepcopy(DEFAULT_STYLE))
    assert all(_counts(w, k) is not None for k in w._all_keys)

    w._box_radio.setChecked(True)
    assert not w._bins_spin.isEnabled()
    assert all(_counts(w, k) is None for k in w._all_keys)


def test_bins_control_sets_every_histogram_and_persists(qapp, pooled_result):
    from gui.plotting.distribution_widget import DistributionWidget

    w = DistributionWidget()
    w.update_result(pooled_result)
    w._hist_radio.setChecked(True)

    w._bins_spin.setValue(12)
    assert all(len(_counts(w, k)) == 12 for k in w._all_keys)

    w.update_result(replace(pooled_result, representative_index=0))
    assert w._bins_spin.value() == 12
    assert all(len(_counts(w, k)) == 12 for k in w._all_keys)


@pytest.mark.parametrize('fixture', ['pooled_result', 'per_replica_result'])
def test_histogram_counts_sum_to_pool_size(qapp, request, fixture):
    """One histogram of the pooled values per subplot — per replica too, with no overlays."""
    from gui.plotting.distribution_widget import DistributionWidget

    result = request.getfixturevalue(fixture)
    w = DistributionWidget()
    w._hist_radio.setChecked(True)
    w.update_result(result)

    pool_size = len(result.parameter_samples['Ka_guest'])
    for key in w._all_keys:
        assert _counts(w, key).sum() == pool_size

    pooled_note_shown = not w._hist_note.isHidden() and 'all replicates' in w._hist_note.text()
    assert pooled_note_shown == (fixture == 'per_replica_result')


def test_histogram_log10_axis_follows_ka_scale(qapp, pooled_result):
    from gui.plotting.distribution_widget import DistributionWidget
    from gui.plotting.plot_style import DEFAULT_STYLE

    ka = pooled_result.parameter_samples['Ka_guest']
    i0 = pooled_result.parameter_samples['I0']
    w = DistributionWidget()
    w.update_result(pooled_result)
    w._hist_radio.setChecked(True)

    assert _value_span(w, 'Ka_guest') == pytest.approx((np.log10(ka.min()), np.log10(ka.max())))
    assert _value_span(w, 'I0') == pytest.approx((i0.min(), i0.max()))  # not a log-scale key

    linear = copy.deepcopy(DEFAULT_STYLE)
    linear['distribution']['ka_scale'] = 'linear'
    w.apply_style(linear)
    assert _value_span(w, 'Ka_guest') == pytest.approx((ka.min(), ka.max()))


def test_hidden_parameter_stays_hidden_in_both_views(qapp, pooled_result):
    from gui.plotting.distribution_widget import DistributionWidget

    w = DistributionWidget()
    w.update_result(pooled_result)
    w._checkboxes['Ka_guest'].setChecked(False)
    assert w._plot_by_key['Ka_guest'].isHidden()

    w._hist_radio.setChecked(True)
    assert w._plot_by_key['Ka_guest'].isHidden()
    assert not w._plot_by_key['I0'].isHidden()

    w._checkboxes['Ka_guest'].setChecked(True)
    assert not w._plot_by_key['Ka_guest'].isHidden()
    assert _counts(w, 'Ka_guest') is not None

    w._checkboxes['I0'].setChecked(False)
    w._box_radio.setChecked(True)
    assert w._plot_by_key['I0'].isHidden()
    assert not w._plot_by_key['Ka_guest'].isHidden()


def test_histogram_legend_wraps_instead_of_widening_the_widget(qapp, per_replica_result):
    """The legend sits on its own wrapping line: the histogram view needs no more width than the box view."""
    from PyQt6.QtCore import Qt

    from gui.plotting.distribution_widget import DistributionWidget

    # Qt passes a row's new minimum width up to the widget only once it is
    # shown; WA_DontShowOnScreen shows it without putting it on screen.
    w = DistributionWidget()
    w.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    w.show()
    w.update_result(per_replica_result)
    # With one plot shown, the rows of controls set the widget's minimum width.
    for key, checkbox in w._checkboxes.items():
        checkbox.setChecked(key == 'Ka_guest')
    qapp.processEvents()
    box_min = w.minimumSizeHint().width()

    w._hist_radio.setChecked(True)
    qapp.processEvents()
    assert 'all replicates' in w._hist_note.text()
    assert w.minimumSizeHint().width() == box_min
    w.close()


def test_histogram_of_identical_values_is_one_bar_at_that_value(qapp, pooled_result):
    """With no spread to bin, no bar covers a band of values the pool never took."""
    import pyqtgraph as pg

    from gui.plotting.distribution_widget import DistributionWidget

    ps = {k: np.full(8, v[2]) for k, v in pooled_result.parameter_samples.items()}
    w = DistributionWidget()
    w._hist_radio.setChecked(True)
    w.update_result(replace(pooled_result, parameter_samples=ps, quality_samples=None))

    plot = w._plot_by_key['I0'].getPlotItem()
    value = ps['I0'][0]
    assert not [it for it in plot.items if isinstance(it, pg.BarGraphItem)]
    lines = [it.getData() for it in plot.items if isinstance(it, pg.PlotCurveItem)]
    assert all(np.all(y == value) for _, y in lines)  # the bar and the median line
    assert any(list(x) == [0, 8] for x, _ in lines)  # a bar eight fits long
    lo, hi = plot.vb.viewRange()[1]
    assert (lo + hi) / 2 == pytest.approx(value)


@pytest.mark.parametrize('horizontal', [True, False], ids=['bars-grow-right', 'bars-grow-up'])
def test_histogram_bars_touch_with_a_gap_and_a_one_value_bin_stays_visible(qapp, horizontal):
    """Neighbouring bars are split by a background gap, and a bin with one value in a pool of hundreds still shows."""
    import pyqtgraph as pg
    from PyQt6.QtCore import QPointF, Qt
    from PyQt6.QtGui import QColor

    from gui.plotting.distribution_widget import draw_histogram

    bar, background = QColor('#2a78d6'), QColor('#ffffff')
    pw = pg.PlotWidget(background=background)
    pw.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    pw.resize(300, 300)
    pw.show()
    plot = pw.getPlotItem()
    # Ten bins of width 1 over [0, 10]: 400 values in the first, 200 in the second, one in the last.
    values = np.r_[np.zeros(400), np.full(200, 1.5), 10.0]
    tallest = draw_histogram(plot, values, 10, color=bar.name(), gap_color=background.name(), horizontal=horizontal)
    set_count_range, set_value_range = (
        (plot.setXRange, plot.setYRange) if horizontal else (plot.setYRange, plot.setXRange)
    )
    set_count_range(0, tallest * 1.08, padding=0)
    set_value_range(0, 10, padding=0.05)
    qapp.processEvents()
    image = pw.grab().toImage()

    def pixel(count, value, px_along_count=0, px_along_value=0):
        """Colour at (count, value), shifted by whole pixels along each axis."""
        xy = QPointF(count, value) if horizontal else QPointF(value, count)
        p = pw.mapFromScene(plot.vb.mapViewToScene(xy))
        dx, dy = (px_along_count, -px_along_value) if horizontal else (px_along_value, -px_along_count)
        return image.pixelColor(round(p.x()) + dx, round(p.y()) + dy)

    def matches(colour, reference):
        return sum(abs(a - b) for a, b in zip(colour.getRgb()[:3], reference.getRgb()[:3])) < 30

    assert tallest * 1.08 / 300 > 1  # one value spans under a pixel, so only the minimum length can show it
    assert all(matches(pixel(0, 9.5, px_along_count=k), bar) for k in (1, 2))
    assert matches(pixel(0, 5.5, px_along_count=1), background)  # empty bins draw nothing

    gap = [pixel(100, 1.0, px_along_value=k) for k in (-1, 0, 1)]
    assert any(matches(colour, background) for colour in gap)
    assert all(matches(pixel(100, 1.0, px_along_value=k), bar) for k in (-3, 3))


# ---------------------------------------------------------------------------
# Per-replicate boxes named and coloured like the loaded data (G7, G8)
# ---------------------------------------------------------------------------


def _replicate_boxes(widget, key='Ka_guest'):
    """Tick labels and the RGB of each replicate's box outline, strip and median marker in *key*'s subplot."""
    import pyqtgraph as pg

    plot = widget._plot_by_key[key].getPlotItem()
    labels = [text for _, text in plot.getAxis('bottom')._tickLevels[0]]
    boxes = [it.opts['pen'].color().getRgb()[:3] for it in plot.items if isinstance(it, pg.BarGraphItem)]
    scatters = [it for it in plot.items if isinstance(it, pg.ScatterPlotItem) and it.zValue() != 1000]
    strips = [it.opts['brush'].color().getRgb()[:3] for it in scatters if it.opts['symbol'] != 'd']
    medians = [it.opts['brush'].color().getRgb()[:3] for it in scatters if it.opts['symbol'] == 'd']
    return labels, boxes, strips, medians


def test_replicate_boxes_take_the_label_and_colour_of_their_replicate(qapp, per_replica_result):
    """Catches boxes named A, B, … by their place in the fit, so replicates B and D read as A and B.

    The data holds replicates A–D; A was left out of the fit and C switched off
    before it, so the fit's two replicates are B and D.
    """
    from gui.plotting.colors import REPLICA_PALETTE
    from gui.plotting.distribution_widget import DistributionWidget

    result = replace(
        per_replica_result, metadata={'active_replica_ids': ['0', '1', '3'], 'replica_ids_fit': ['1', '3']}
    )
    w = DistributionWidget()
    w.update_result(result, replica_ids=('0', '1', '2', '3'))

    colours = [REPLICA_PALETTE[1], REPLICA_PALETTE[3]]
    assert _replicate_boxes(w) == (['B', 'D'], colours, colours, colours)

    # A style or view change redraws with the same names and colours.
    w._hist_radio.setChecked(True)
    w._box_radio.setChecked(True)
    assert _replicate_boxes(w)[:2] == (['B', 'D'], colours)


def test_replicate_colour_matches_the_fit_curve(qapp, per_replica_result):
    """A replicate is drawn in one colour on the Fit Curve and in Distributions."""
    from core.data_processing.plotting import prepare_plot_data
    from gui.plotting.distribution_widget import DistributionWidget
    from gui.plotting.plot_widget import PlotWidget
    from tests.unit.gui.test_plot_widget import _fit_leaving_out, _four_replicates, _replicate_colours

    ms = _four_replicates()
    ms.set_active('2', False)
    fit = _fit_leaving_out(ms, ['0'])
    pw = PlotWidget()
    pw.update_plot(prepare_plot_data(ms, [fit], show_dropped=True))

    result = replace(per_replica_result, metadata=fit.metadata)
    w = DistributionWidget()
    w.update_result(result, replica_ids=ms.replica_ids)

    curve = _replicate_colours(pw)
    labels, boxes, _, _ = _replicate_boxes(w)
    assert labels == ['B', 'D']
    assert boxes == [curve['1'], curve['3']]


def test_without_loaded_data_boxes_are_named_by_replicate_id(qapp, per_replica_result):
    from gui.plotting.distribution_widget import DistributionWidget

    w = DistributionWidget()
    w.update_result(per_replica_result)

    assert _replicate_boxes(w)[0] == per_replica_result.metadata['replica_ids_fit']


def test_per_replicate_fit_without_a_replicate_record_is_refused(qapp, per_replica_result):
    from gui.plotting.distribution_widget import DistributionWidget

    w = DistributionWidget()
    with pytest.raises(ValueError, match='does not record'):
        w.update_result(replace(per_replica_result, metadata={}))


def test_show_mismatch_puts_a_note_in_place_of_the_plots_until_cleared(qapp, pooled_result):
    from gui.plotting.distribution_widget import DistributionWidget
    from gui.plotting.plot_style import DEFAULT_STYLE

    w = DistributionWidget()
    w.update_result(pooled_result)
    plots = dict(w._plot_by_key)

    note = 'This fit was made with [Host]₀ = 4.3 µM, which is now 5 µM.'
    w.show_mismatch(note)
    assert w._stack.currentWidget() is w._mismatch_label
    assert w._mismatch_label.text() == note
    assert w._view_bar_host.isHidden() and w._toggle_bar_host.isHidden()

    # Redraws while hidden keep the note up.
    w.update_result(replace(pooled_result, representative_index=0))
    w.apply_style(copy.deepcopy(DEFAULT_STYLE))
    w._hist_radio.setChecked(True)
    w._box_radio.setChecked(True)
    assert w._stack.currentWidget() is w._mismatch_label

    w.update_result(pooled_result)
    w.show_mismatch(None)
    assert w._stack.currentWidget() is w._plot_container
    assert not w._view_bar_host.isHidden() and not w._toggle_bar_host.isHidden()
    assert w._plot_by_key.keys() == plots.keys()

    w.show_mismatch(note)
    w.clear()
    assert w._stack.currentWidget() is w._placeholder
