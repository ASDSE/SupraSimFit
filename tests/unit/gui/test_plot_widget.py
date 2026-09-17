"""Widget tests for PlotWidget — requires a QApplication."""

from dataclasses import replace

import pytest

pytest.importorskip('PyQt6')
pytest.importorskip('pyqtgraph')


def test_building_the_fit_curve_plot_leaves_the_library_defaults_alone(qapp):
    """The Fit Curve tab styles its own view, never pyqtgraph's process-wide defaults.

    Those defaults reach every plot the application builds afterwards. With
    antialiasing switched on for the whole process, the one-pixel stroke that
    keeps a histogram bin of a single fit visible on the Distributions tab is
    drawn blended into the background and vanishes.
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


# ---------------------------------------------------------------------------
# Fit-summary annotation: content and auto-placement
# ---------------------------------------------------------------------------


def _binding_plot(qapp, *, x_max=5e-5, pool=True):
    """A shown PlotWidget with a saturating titration and one fit annotated.

    The curve runs lower-left to upper-right, so the top-left and bottom-right
    regions are genuinely empty — placement has somewhere correct to go.
    """
    import numpy as np
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication

    from core.pipeline.fit_pipeline import FitResult
    from core.units import Q_
    from gui.plotting.plot_widget import PlotWidget

    def curve(c):
        return 1000 + 4000 * c / (c + x_max / 5)

    rng = np.random.default_rng(0)
    x = np.linspace(x_max / 25, x_max, 25)
    y = curve(x)
    # The pipeline reports a dense (300-point) display curve; use the same here
    # so the curve is a real obstacle for placement rather than a sparse one.
    x_dense = np.linspace(x[0], x[-1], 300)
    y_dense = curve(x_dense)

    pw = PlotWidget()
    pw.update_plot(
        {
            'concentrations': x,
            'active_replicas': [('r1', y)],
            'dropped_replicas': [],
            'average': y,
            'fits': [{'x': x_dense, 'y': y_dense, 'label': 'IDA fit', 'id': 'abc'}],
        },
        x_label='Guest',
        y_label='Signal',
    )
    samples = None
    if pool:
        samples = {
            'Ka_guest': rng.normal(1.24e6, 9e4, 60).clip(1e5),
            'I_0': rng.normal(1000.0, 20.0, 60),
        }
    result = FitResult(
        parameters={'Ka_guest': Q_(1.24e6, '1/M'), 'I_0': Q_(1000.0, 'au')},
        rmse=12.3,
        r_squared=0.9962,
        n_passing=60 if pool else 1,
        n_total=100,
        x_fit=Q_(x_dense, 'M'),
        y_fit=Q_(y_dense, 'au'),
        assay_type='IDA',
        model_name='equilibrium_4param',
        parameter_samples=samples,
    )
    pw.set_fit_results([result])
    pw.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    pw.resize(900, 600)
    pw.show()
    QApplication.processEvents()
    return pw


def _annotation_rect(pw):
    from PyQt6.QtCore import QRectF

    item = pw._annotation_item
    return QRectF(item.pos(), item.boundingRect().size())


def _ka_line(text):
    """The Ka parameter line of the annotation."""
    return next(line for line in text.split('\n') if line.startswith('Ka'))


def _with_attempts(result, shown, *, per_replicate=True, replica_fits=True):
    """*result* with a 60-attempt pool, showing attempt *shown*.

    Attempt 0 has the pool's highest R². As a per-replicate fit its replicates
    hold attempts 0-29 and 30-59, led by attempts 7 and 30; attempt 7 fits the
    averaged signal better, so the fit chose attempt 7.
    """
    import numpy as np

    r2 = np.linspace(0.99, 0.98, 60)
    r2[0], r2[7] = 0.999, 0.995
    replicas = [
        replace(
            result, parameter_samples={k: v[s] for k, v in result.parameter_samples.items()}, representative_index=i
        )
        for s, i in ((slice(0, 30), 7), (slice(30, 60), 0))
    ]
    return replace(
        result,
        uncertainty_source='replicate' if per_replicate else 'optimizer',
        quality_samples={'r_squared': r2, 'rmse': 1.0 - r2},
        replica_fits=replicas if per_replicate and replica_fits else None,
        representative_index=shown,
    )


@pytest.mark.parametrize(
    ('make', 'heading'),
    [
        (lambda r: _with_attempts(r, 7), "one replicate's best fit (range over 60"),
        (lambda r: _with_attempts(r, 40), 'picked fit (range over 60'),
        (lambda r: _with_attempts(r, 7, per_replicate=False), 'picked fit (range over 60'),
        (lambda r: _with_attempts(r, 7, replica_fits=False), 'shown fit (range over 60'),
        (
            lambda r: replace(r, representative_index=7, metadata={'fitted_representative_index': 3}),
            'picked fit (range over 60',
        ),
    ],
    ids=['per-replicate-choice', 'per-replicate-pick', 'single-fit-pick', 'choice-unknown', 'recorded-pick'],
)
def test_annotation_names_a_fit_that_is_not_the_pool_best(qapp, make, heading):
    pw = _binding_plot(qapp)
    pw.set_fit_results([make(pw._fit_results[0])])
    text = pw._annotation_item.textItem.toPlainText()

    assert heading in text
    assert '— best fit' not in text


def test_annotation_calls_a_single_fit_s_own_choice_the_best_fit(qapp):
    pw = _binding_plot(qapp)
    pw.set_fit_results([_with_attempts(pw._fit_results[0], 0, per_replicate=False)])

    assert '— best fit (range over 60' in pw._annotation_item.textItem.toPlainText()


def test_annotation_reports_estimate_and_range(qapp):
    """Each parameter reads 'Estimate (min, max)' over the accepted pool."""
    import re

    import numpy as np

    pw = _binding_plot(qapp)
    text = pw._annotation_item.textItem.toPlainText()
    pool = pw._fit_results[0].parameter_samples['Ka_guest']

    assert 'best fit (range over 60 accepted fits)' in text
    assert '±' not in text, 'the ± spread should be gone'
    assert 'RMSE' not in text, 'RMSE duplicates the Fit Quality panel'
    assert 'R²: 0.9962' in text

    # The bracketed pair is the pool's own extremes, not a symmetric spread:
    # parse the two numbers back out and compare to numpy.
    lo, hi = re.search(r'\(([\d.]+)×10(\d+), ([\d.]+)×10(\d+)\)', _ka_line(text)).group(1, 3)
    assert float(lo) == pytest.approx(np.min(pool) / 1e6, abs=0.01)
    assert float(hi) == pytest.approx(np.max(pool) / 1e6, abs=0.01)


def test_annotation_r2_never_reads_as_meeting_the_floor_it_misses(qapp):
    """A fit a hair below its own Min R² reads below it, from the one shared R² formatter."""
    from dataclasses import replace

    from gui.plotting.labels import fmt_r2

    pw = _binding_plot(qapp)
    below = replace(pw._fit_results[0], r_squared=0.98999, fit_config={'min_r_squared': 0.99})
    pw.set_fit_results([below])
    text = pw._annotation_item.textItem.toPlainText()
    assert f'R²: {fmt_r2(0.98999, 0.99)}' in text
    assert 'R²: 0.9900' not in text


def test_annotation_without_pool_states_no_range(qapp):
    """A result with no stored pool shows the estimate and says why, not a fake range."""
    pw = _binding_plot(qapp, pool=False)
    text = pw._annotation_item.textItem.toPlainText()

    assert 'no fit pool stored' in text
    # A range would render as "(lo, hi)" — the comma is the tell (the parameter
    # label itself contains parentheses).
    assert ',' not in _ka_line(text)
    assert '±' not in text


def test_annotation_is_placed_clear_of_data_and_legend(qapp):
    """The regression this whole placement search exists for."""
    pw = _binding_plot(qapp)
    rect = _annotation_rect(pw)
    points = pw._obstacle_points_px()

    covered = (
        (points[:, 0] >= rect.left())
        & (points[:, 0] <= rect.right())
        & (points[:, 1] >= rect.top())
        & (points[:, 1] <= rect.bottom())
    ).sum()
    assert covered == 0, 'annotation was placed on top of plotted data'

    legend_rect = pw._legend_rect_px()
    assert legend_rect is not None
    assert not legend_rect.intersects(rect), 'annotation overlaps the legend'


def test_annotation_lives_in_viewbox_pixel_space(qapp):
    """Parented to the ViewBox, not its childGroup — so data ranges can't move it."""
    pw = _binding_plot(qapp)
    vb = pw._pg_widget.getViewBox()

    assert pw._annotation_item.parentItem() is vb
    assert pw._annotation_item not in vb.addedItems  # stays out of autoRange


def test_annotation_is_replaced_for_a_new_dataset(qapp):
    """A second fit over a very different range must re-place, not reuse a stale spot."""
    from PyQt6.QtWidgets import QApplication

    pw = _binding_plot(qapp, x_max=5e-5)
    first = _annotation_rect(pw)

    # Concentrations 1000x larger: a position carried over from the previous
    # dataset would land outside the new view.
    pw2 = _binding_plot(qapp, x_max=5e-2)
    QApplication.processEvents()
    second = _annotation_rect(pw2)

    vb = pw2._pg_widget.getViewBox()
    assert 0 <= second.left() and second.right() <= vb.width() + 1
    assert 0 <= second.top() and second.bottom() <= vb.height() + 1
    assert first.isValid() and second.isValid()


def test_user_drag_survives_a_rebuild(qapp):
    """Auto-placement applies until the user moves the box; then it stays put."""
    from PyQt6.QtCore import QPointF

    pw = _binding_plot(qapp)
    dropped = QPointF(123.0, 45.0)
    pw._annotation_item.setPos(dropped)
    pw._on_annotation_moved(dropped)  # what mouseReleaseEvent reports

    pw.set_fit_results(pw._fit_results)  # style change / re-report → rebuild

    assert pw._annotation_item.pos() == dropped


def _draggable(on_moved):
    from gui.plotting.plot_widget import _DraggableTextItem

    item = _DraggableTextItem(html='<div>x</div>', anchor=(0, 0), on_moved=on_moved)
    item.setFlag(item.GraphicsItemFlag.ItemIsMovable)
    return item


def test_click_without_dragging_does_not_pin_the_annotation(qapp):
    """A click that moves nothing must leave auto-placement in charge.

    Reporting a move on every mouse release would latch `_annotation_pos` on a
    stray click, freezing the box for the rest of the session.
    """
    moved = []
    item = _draggable(moved.append)
    item._press_pos = item.pos()  # what mousePressEvent records

    item._report_if_moved()

    assert moved == []


def test_drag_reports_the_drop_position(qapp):
    """Press → move → release does report, so a drag wins over auto-placement."""
    from PyQt6.QtCore import QPointF

    moved = []
    item = _draggable(moved.append)
    item._press_pos = item.pos()
    item.setPos(QPointF(50.0, 60.0))  # what Qt's ItemIsMovable does on drag

    item._report_if_moved()

    assert moved == [QPointF(50.0, 60.0)]


def test_release_without_a_recorded_press_reports_nothing(qapp):
    """Unpaired release → stay auto-placed; latching an unchosen spot is worse."""
    moved = []
    item = _draggable(moved.append)

    item._report_if_moved()

    assert moved == []


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


def test_placement_avoids_a_blocked_rect(qapp):
    """An already-placed overlay is dodged even when its slot is otherwise empty."""
    import numpy as np

    pw = _binding_plot(qapp)
    vb = pw._pg_widget.getViewBox()
    w, h = vb.width(), vb.height()
    size = (w / 4, h / 4)

    pw._obstacle_points_px = lambda: np.empty((0, 2))
    (fx, fy), free_rect = pw._best_overlay_slot(size)
    assert (fx, fy) == (1.0, 0.0)  # no obstacles at all → preferred corner

    blocked = pw._best_overlay_slot(size, blocked=(free_rect,))[1]
    assert not blocked.intersects(free_rect)


# ---------------------------------------------------------------------------
# Replicates a fit left out, replicate colours, and hiding a fit (G7)
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
        n_passing=1,
        n_total=1,
        x_fit=Q_(x, 'M'),
        y_fit=Q_(np.interp(x, ms.concentrations, ms.signals[rows].mean(axis=0)), 'au'),
        assay_type='IDA',
        model_name='equilibrium_4param',
        metadata={
            'active_replica_ids': given,
            'replica_ids_fit': used,
            'replica_failures': {rid: 'None of its fit attempts reached the minimum R².' for rid in left_out},
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
    pw.set_fit_results([fit])
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
    _, _, sd = pw._last_error_bar_data
    np.testing.assert_allclose(mean, ms.signals[1:].mean(axis=0), rtol=1e-15)
    np.testing.assert_allclose(sd, ms.signals[1:].std(axis=0), rtol=1e-12)
    assert pw._left_out_replica_ids == ['0']
    assert pw._note.isHidden()


def test_show_mismatch_hides_the_fit_until_it_matches_again(qapp):
    """A hidden fit draws no curve or annotation through later redraws, and comes back exactly as it was."""
    import numpy as np

    from core.data_processing.plotting import prepare_plot_data
    from gui.plotting.plot_style import DEFAULT_STYLE
    from gui.plotting.plot_widget import PlotWidget

    ms = _four_replicates()
    fit = _fit_leaving_out(ms, ['0'])
    pw = PlotWidget()
    pw.update_plot(prepare_plot_data(ms, [fit], show_dropped=True))
    pw.set_fit_results([fit])
    shown_text = pw._annotation_item.textItem.toPlainText()

    note = 'This fit was made on replicates B–D. Replicate B is now off.'
    pw.show_mismatch(note)
    assert pw._fit_items == [] and pw._annotation_item is None
    assert pw._note.text() == note and not pw._note.isHidden()
    assert pw._replica_ids == ['0', '1', '2', '3'] and pw._left_out_replica_ids == []
    np.testing.assert_allclose(pw._average_item.getData()[1], ms.signals.mean(axis=0), rtol=1e-15)

    # Later calls with the fit do not bring it back while it is hidden.
    pw.update_plot(prepare_plot_data(ms, [fit], show_dropped=True))
    pw.set_fit_results([fit])
    style = {**DEFAULT_STYLE, 'axes': {**DEFAULT_STYLE['axes'], 'x_unit': 'nM'}}
    pw.apply_style(style)
    assert pw._fit_items == [] and pw._annotation_item is None
    assert pw._note.text() == note

    pw.show_mismatch(None)
    assert len(pw._fit_items) == 1
    assert pw._annotation_item.textItem.toPlainText() == shown_text
    assert pw._left_out_replica_ids == ['0'] and pw._note.isHidden()


def test_overlaid_fits_on_different_replicates_are_noted(qapp):
    from core.data_processing.plotting import prepare_plot_data
    from gui.plotting.plot_widget import PlotWidget

    ms = _four_replicates()
    every, some = _fit_leaving_out(ms, []), _fit_leaving_out(ms, ['0'])
    pw = PlotWidget()

    pw.update_plot(prepare_plot_data(ms, [every, some], show_dropped=True))
    assert pw._note.text() == (
        'Mean ± SD is over replicates B–D, the ones the fit in the summary used. Another fit shown used replicates A–D.'
    )

    pw.update_plot(prepare_plot_data(ms, [some, some], show_dropped=True))
    assert pw._note.isHidden()
