"""Widget tests for IdentifiabilityWidget — fit attempts, Ka profile, sensitivity overlay.

Require a ``QApplication`` (the ``qapp`` fixture).
"""

import numpy as np
import pytest

pytest.importorskip('PyQt6')

from core.pipeline.fit_pipeline import FitResult  # noqa: E402
from core.pipeline.profile import ProfileResult  # noqa: E402
from core.pipeline.sensitivity import (  # noqa: E402
    TITRANT,
    InputSpec,
    ReplicateMode,
    SensitivityConfig,
    SensitivityMode,
    SensitivityResult,
)
from core.units import Q_  # noqa: E402

IDA_KEYS = ('Ka_guest', 'I0', 'I_dye_free', 'I_dye_bound')
N_ATTEMPTS = 40
N_NEGATIVE = 5
FLOOR = 0.99


def _fit(keys=IDA_KEYS, assay='IDA', *, per_replica=False, with_attempts=True):
    """A FitResult whose first ``N_NEGATIVE`` attempts fit worse than a flat line."""
    rng = np.random.default_rng(1)
    samples = {
        k: 10 ** rng.uniform(7, 10, N_ATTEMPTS) if k.startswith('Ka') else rng.uniform(0, 1, N_ATTEMPTS) for k in keys
    }
    r2 = 1.0 - 10 ** -rng.uniform(0.5, 3.0, N_ATTEMPTS)
    r2[:N_NEGATIVE] = -0.5
    return FitResult(
        parameters={k: Q_(float(v[-1]), 'dimensionless') for k, v in samples.items()},
        rmse=0.1,
        r_squared=float(r2.max()),
        n_passing=int(np.sum(r2 >= FLOOR)),
        n_total=N_ATTEMPTS,
        x_fit=Q_(np.zeros(3), 'M'),
        y_fit=Q_(np.zeros(3), 'au'),
        assay_type=assay,
        model_name='equilibrium_4param',
        fit_config={'min_r_squared': FLOOR},
        uncertainty_source='replicate' if per_replica else 'optimizer',
        attempt_samples=samples if with_attempts else None,
        attempt_quality={'rmse': np.ones(N_ATTEMPTS), 'r_squared': r2} if with_attempts else None,
    )


def _profile(*, per_replica=False, ci_open=(False, False)):
    grid = np.logspace(-8, 12, 401)

    def bump(centre, top):
        return top * np.exp(-((np.log10(grid) - centre) ** 2))

    return ProfileResult(
        ka_key='Ka_guest',
        grid=grid,
        r2=bump(8.5, 0.995),
        replica_r2={rid: bump(8.5 + 0.1 * i, 0.99 - 0.01 * i) for i, rid in enumerate('ABC')} if per_replica else None,
        best_ka=10**8.5,
        best_r2=0.995,
        level=0.95,
        ci=(1e8, 1e12 if ci_open[1] else 1e9),
        ci_open=ci_open,
        r2_threshold=0.99,
        n_points=12,
        n_params=3,
        per_replica=per_replica,
    )


N_SAMPLES = 21
NO_FIT = 10  # the sample at offset 0 produced no fit


def _sensitivity(replicate_mode=ReplicateMode.FOLLOW):
    ka = 10 ** np.linspace(8.2, 8.8, N_SAMPLES)
    r2 = np.linspace(0.97, 0.999, N_SAMPLES)
    ka[NO_FIT] = r2[NO_FIT] = np.nan
    return SensitivityResult(
        mode=SensitivityMode.SOBOL,
        assay_type='IDA',
        ka_keys=('Ka_guest',),
        baseline_ka={'Ka_guest': 10**8.5},
        histograms={'sobol': {'Ka_guest': ka}},
        x_offsets_pct=None,
        y_offsets_pct=None,
        ka_grid=None,
        n_success=N_SAMPLES - 1,
        n_total=2 * N_SAMPLES,
        config=SensitivityConfig(
            SensitivityMode.SOBOL,
            N_SAMPLES,
            {'h0': InputSpec.sigma_pct(5.0), TITRANT: InputSpec.sigma_pct(5.0)},
            replicate_mode=replicate_mode,
        ),
        sample_offsets_pct={'h0': np.linspace(-10, 10, N_SAMPLES), TITRANT: np.linspace(5, -5, N_SAMPLES)},
        sample_ka={'Ka_guest': ka},
        sample_r2=r2,
        floor=FLOOR,
        n_below_floor=int(np.sum(r2 < FLOOR)),
    )


def _widget(fit=None, profile=None, assay='IDA'):
    from gui.plotting.identifiability_widget import IdentifiabilityWidget

    w = IdentifiabilityWidget()
    if fit is not None:
        w.update_fit(fit, profile, assay)
    return w


def _n_points(scatter):
    return len(scatter.getData()[0])


# ---------------------------------------------------------------------------
# States
# ---------------------------------------------------------------------------


def test_placeholder_before_any_fit(qapp):
    w = _widget()
    assert w._stack.currentWidget() is w._message
    assert 'Run a fit' in w._message.text()


def test_dye_alone_is_not_applicable(qapp):
    fit = _fit(keys=('slope', 'intercept'), assay='DYE_ALONE', with_attempts=False)
    w = _widget(fit, None, 'DYE_ALONE')
    assert w._stack.currentWidget() is w._message
    assert 'Not applicable' in w._message.text()


def test_unsupported_assay_shows_attempts_only(qapp):
    """Two binding constants: one attempts-only panel per Ka and a note saying why there is no line."""
    keys = ('Ka_HG', 'Ka_HG2', 'I0', 'I_G', 'I_H', 'I_HG', 'I_HG2')
    w = _widget(_fit(keys=keys, assay='DBA_HG2'), None, 'DBA_HG2')
    assert w._stack.currentWidget() is w._content
    assert set(w._items) == {'Ka_HG', 'Ka_HG2'}
    for items in w._items.values():
        assert items['average'] is None
        assert _n_points(items['attempts_passing']) + _n_points(items['attempts_below']) == N_ATTEMPTS - N_NEGATIVE
    assert 'single binding constant' in w._notes.text()


def test_supported_assay_without_profile_notes_the_missing_line(qapp):
    w = _widget(_fit(), None)
    items = w._items['Ka_guest']
    assert items['average'] is None
    assert _n_points(items['attempts_passing']) + _n_points(items['attempts_below']) == N_ATTEMPTS - N_NEGATIVE
    assert 'not available' in w._notes.text()


def test_clear_returns_to_placeholder(qapp):
    w = _widget(_fit(), _profile())
    w.update_sensitivity(_sensitivity())
    w.clear()
    assert w._stack.currentWidget() is w._message
    assert 'Run a fit' in w._message.text()
    assert w._controls.isHidden()
    assert w._items == {}


# ---------------------------------------------------------------------------
# Section 1: attempts and profile
# ---------------------------------------------------------------------------


def test_average_mode_draws_the_profile_line_and_classifies_attempts(qapp):
    fit = _fit()
    w = _widget(fit, _profile())
    items = w._items['Ka_guest']
    assert items['average'] is not None and items['replicas'] == []
    assert items['average'].opts['pen'].widthF() == 2
    r2 = fit.attempt_quality['r_squared']
    assert _n_points(items['attempts_passing']) == int(np.sum(r2 >= FLOOR))
    assert _n_points(items['attempts_below']) == int(np.sum((r2 >= 0) & (r2 < FLOOR)))


def test_per_replicate_mode_draws_one_thin_line_per_replicate(qapp):
    w = _widget(_fit(per_replica=True), _profile(per_replica=True))
    items = w._items['Ka_guest']
    assert len(items['replicas']) == 3
    assert all(c.opts['pen'].widthF() == 1 for c in items['replicas'])
    assert items['average'].opts['pen'].widthF() == 2
    assert "best fit of the replicates' average" in w._summary.text()


def test_hidden_attempts_are_counted(qapp):
    w = _widget(_fit(), _profile())
    assert f'{N_NEGATIVE} of {N_ATTEMPTS} attempts not shown' in w._notes.text()


def test_confidence_interval_is_stated(qapp):
    """Best Ka 10^8.5 with a CI of 1e8 to 1e9: −68 % and +216 % of the best fit."""
    w = _widget(_fit(), _profile())
    text = w._summary.text()
    assert '95% CI 1.0×10⁸ – 1.0×10⁹' in text
    assert '(−68% / +216%)' in text
    assert 'open' not in text


def test_open_interval_says_open(qapp):
    """The unit follows the number it belongs to, never the word "open"."""
    w = _widget(_fit(), _profile(ci_open=(False, True)))
    text = w._summary.text()
    assert '1.0×10⁸ M<sup>−1</sup> – open (' in text
    assert '(−68% / open)' in text
    assert 'cannot rule out a higher' in text


def test_a_drop_close_to_minus_100_percent_is_not_rounded_to_it(qapp):
    """−99.6 % shows as such: −100 % would say the interval reaches a Ka of zero."""
    from gui.plotting.identifiability_widget import _pct

    assert _pct(3.3e6 / 8.14e8) == '−99.6%'
    assert _pct(0.32) == '−68%'
    assert _pct(3.16) == '+216%'


def test_fit_attempts_far_below_the_floor_do_not_squeeze_the_view(qapp):
    """One attempt at the Ka lower bound leaves the view on the interval; the note counts every attempt out of view."""
    fit = _fit()
    ka, r2 = fit.attempt_samples['Ka_guest'], fit.attempt_quality['r_squared']
    ka[N_NEGATIVE], r2[N_NEGATIVE] = 1e-8, 0.5
    w = _widget(fit, _profile())
    (x_lo, x_hi), (y_lo, y_hi) = w._items['Ka_guest']['main'].viewRange()
    assert x_lo > 0  # the attempt at log10 Ka = −8 is out of view
    assert x_hi - x_lo < 5  # the interval (one decade) keeps a readable share of the width
    shown = r2 >= 0
    log_ka, r2 = np.log10(ka[shown]), r2[shown]
    outside = int(np.sum((log_ka < x_lo) | (log_ka > x_hi) | (r2 < y_lo) | (r2 > y_hi)))
    assert outside >= 1 and np.all(r2[(log_ka < x_lo) | (log_ka > x_hi) | (r2 < y_lo)] < FLOOR)
    assert f'{outside} of 35 attempts at' in w._notes.text()
    assert 'all below Min R², lie outside the default view; zoom out to see them' in w._notes.text()


def test_replicates_the_fit_left_out_are_named(qapp):
    fit = _fit(per_replica=True)
    fit.metadata['replica_failures'] = {'A': 'No trials passed the quality filter.'}
    w = _widget(fit, _profile(per_replica=True))
    assert 'Replicate A is left out here, as it was from the fit.' in w._notes.text()


def test_floor_and_cut_off_are_named_beside_the_plot(qapp):
    """The dashed Min R² line and the dotted cut-off are named on a right-hand axis at their heights, never over the data."""
    from PyQt6.QtCore import Qt

    profile = _profile()
    w = _widget(_fit(), profile)
    items = w._items['Ka_guest']
    assert items['floor'].pen.style() == Qt.PenStyle.DashLine and items['floor'].value() == FLOOR
    assert items['cut'].pen.style() == Qt.PenStyle.DotLine and items['cut'].value() == profile.r2_threshold
    axis = items['main'].getAxis('right')
    assert axis.isVisible()
    assert axis._tickLevels == [[(profile.r2_threshold, 'cut-off 0.9900'), (FLOOR, 'Min R² 0.99')]]
    for line in (items['floor'], items['cut']):
        assert line.zValue() < items['attempts_below'].zValue() < items['average'].zValue()


def test_r2_axis_is_linear(qapp):
    """Every point sits at its R² itself: the line, the attempts and the levels share one linear scale."""
    fit = _fit()
    profile = _profile()
    w = _widget(fit, profile)
    items = w._items['Ka_guest']
    assert not items['main'].getAxis('left').logMode
    np.testing.assert_array_equal(items['average'].getData()[1], profile.r2)
    r2 = fit.attempt_quality['r_squared']
    drawn = np.concatenate([items['attempts_below'].getData()[1], items['attempts_passing'].getData()[1]])
    np.testing.assert_array_equal(np.sort(drawn), np.sort(r2[r2 >= 0]))


def test_default_view_frames_the_attempts_and_the_floor(qapp):
    fit = _fit()
    w = _widget(fit, _profile())
    (x_lo, x_hi), (y_lo, y_hi) = w._items['Ka_guest']['main'].viewRange()
    shown = fit.attempt_quality['r_squared'] >= 0
    log_ka = np.log10(fit.attempt_samples['Ka_guest'][shown])
    assert x_lo <= log_ka.min() and log_ka.max() <= x_hi
    assert y_lo <= FLOOR <= y_hi


def test_default_r2_view_separates_the_levels_from_what_lies_inside_the_ka_view(qapp):
    """Peak 0.995, cut-off and floor 0.99: the view starts one level span (0.005) below them, at R² 0.985.

    It reaches the best attempt in view and stops just above R² = 1. Attempts
    outside the Ka view never move it, and View All still reaches the full range.
    """
    fit = _fit()
    w = _widget(fit, _profile())
    main = w._items['Ka_guest']['main']
    (x_lo, x_hi), (y_lo, y_hi) = main.viewRange()
    assert y_lo == pytest.approx(0.985)
    ka, r2 = fit.attempt_samples['Ka_guest'], fit.attempt_quality['r_squared']
    in_view = (np.log10(ka) >= x_lo) & (np.log10(ka) <= x_hi) & (r2 >= 0)
    assert r2[in_view].max() <= y_hi <= 1.001
    # The peak-to-floor span keeps a readable share of the height.
    assert (0.995 - FLOOR) / (y_hi - y_lo) > 0.25

    # A poor attempt far outside the Ka view (the old framing let it pull the view down to R² ≈ 0).
    ka[N_NEGATIVE], r2[N_NEGATIVE] = 1e-8, 0.01
    moved = _widget(fit, _profile())._items['Ka_guest']['main'].viewRange()
    np.testing.assert_allclose(moved, [[x_lo, x_hi], [y_lo, y_hi]])

    main.autoRange()
    _, (all_lo, all_hi) = main.viewRange()
    assert all_lo <= 0.0 and all_hi >= r2.max()


@pytest.mark.parametrize(('floor', 'in_view'), [(0.985, True), (0.9999, True), (0.95, False), (0.9, False)])
def test_a_min_r2_far_from_the_peak_and_cut_off_never_squeezes_them_together(qapp, floor, in_view):
    """Peak 0.995 and cut-off 0.99 keep at least an eighth of the view's height between them, whatever the Min R².

    A Min R² within two peak-to-cut-off gaps of them stays in the default view; one further out is left
    out of it, and a note says where it is.
    """
    fit = _fit()
    fit.fit_config = {'min_r_squared': floor}
    w = _widget(fit, _profile())
    _, (y_lo, y_hi) = w._items['Ka_guest']['main'].viewRange()
    assert (0.995 - 0.99) / (y_hi - y_lo) >= 1 / 8
    assert (y_lo <= floor <= y_hi) is in_view
    note = f'The Min R² line ({floor:g}) lies outside the default view; zoom out to see it.'
    assert (note in w._notes.text()) is not in_view


def test_marginal_histograms_count_attempts_in_forty_bins_across_the_view(qapp):
    """Both histograms bin the attempts in view into 40 equal bins, below-floor then passing, and rebin on zoom."""
    from PyQt6.QtCore import Qt

    fit = _fit()
    w = _widget(fit, _profile())
    # Linked ranges line up by pixel, so the histograms need a laid-out widget.
    w.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    w.resize(1100, 800)
    w.show()
    qapp.processEvents()
    items = w._items['Ka_guest']
    top, right = items['marginals']
    assert top.getAxis('left').labelText == 'attempts' and right.getAxis('bottom').labelText == 'attempts'
    ka, r2 = fit.attempt_samples['Ka_guest'], fit.attempt_quality['r_squared']
    shown = r2 >= 0
    values = {'hist_ka': np.log10(ka[shown]), 'hist_r2': r2[shown]}
    below_floor = r2[shown] < FLOOR

    def check():
        qapp.processEvents()
        (x_lo, x_hi), (y_lo, y_hi) = items['main'].viewRange()
        assert top.viewRange()[0] == pytest.approx([x_lo, x_hi]) and right.viewRange()[1] == pytest.approx([y_lo, y_hi])
        for key, (lo, hi), edges_key, counts_key in (
            ('hist_ka', (x_lo, x_hi), 'x', 'y'),
            ('hist_r2', (y_lo, y_hi), 'y', 'x'),
        ):
            below, stacked = items[key]
            starts, ends = stacked.opts[f'{edges_key}0'], stacked.opts[f'{edges_key}1']
            np.testing.assert_allclose(ends - starts, (hi - lo) / 40)
            assert starts[0] <= lo and ends[-1] >= hi and len(starts) <= 41
            inside = (values[key] >= starts[0]) & (values[key] < ends[-1])
            assert stacked.opts[f'{counts_key}1'].sum() == inside.sum()
            assert below.opts[f'{counts_key}1'].sum() == (inside & below_floor).sum()

    check()
    items['main'].setXRange(8.3, 8.7, padding=0)
    items['main'].setYRange(0.99, 1.0, padding=0)
    check()
    w.close()


def test_legend_and_notes_start_below_the_ka_axis_label_in_the_default_window(qapp, monkeypatch):
    """In the 1280×820 main window the page scrolls, so the text under the chart never runs over its axis label."""
    from PyQt6.QtCore import Qt

    from gui.main_window import FittingMainWindow

    monkeypatch.setattr(FittingMainWindow, '_run_update_check', lambda self, silent: None)
    window = FittingMainWindow()
    window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    session = window.active_session()
    w = session._identifiability_widget
    fit = _fit(per_replica=True)
    fit.metadata['replica_failures'] = {'A': 'No trials passed the quality filter.'}
    w.update_fit(fit, _profile(per_replica=True), 'IDA')
    w.update_sensitivity(_sensitivity())
    session._plot_tabs.setCurrentWidget(w)
    window.resize(1280, 820)
    window.show()
    for _ in range(5):
        qapp.processEvents()

    page, canvas = w._content.widget(), w._glw
    axis = w._items['Ka_guest']['main'].getAxis('bottom')
    label = axis.label.mapRectToScene(axis.label.boundingRect())
    label_bottom = canvas.mapTo(page, canvas.mapFromScene(label.bottomLeft())).y()
    assert w._notes.text().count('<br>') >= 3
    assert canvas.height() >= canvas.minimumHeight()
    assert label_bottom <= w._legend.geometry().top() <= w._notes.geometry().top()
    window.close()


@pytest.mark.parametrize('size', [(1280, 820), (1600, 1000)])
def test_the_whole_chart_is_in_view_without_scrolling_in_the_default_windows(qapp, monkeypatch, size):
    """The chart takes the tab's height, down to its minimum: its K<sub>a</sub> axis title never needs a scroll.

    Where the tab has room, the legend below the chart is in view too.
    """
    from PyQt6.QtCore import Qt

    from gui.main_window import FittingMainWindow
    from gui.plotting.identifiability_widget import _CANVAS_MIN_HEIGHT

    monkeypatch.setattr(FittingMainWindow, '_run_update_check', lambda self, silent: None)
    window = FittingMainWindow()
    window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    session = window.active_session()
    w = session._identifiability_widget
    w.update_fit(_fit(), _profile(), 'IDA')
    w.update_sensitivity(_sensitivity())
    session._plot_tabs.setCurrentWidget(w)
    window.resize(*size)
    window.show()
    for _ in range(5):
        qapp.processEvents()

    viewport, canvas = w._content.viewport(), w._glw
    axis = w._items['Ka_guest']['main'].getAxis('bottom')
    title = axis.label.mapRectToScene(axis.label.boundingRect())
    assert w._content.verticalScrollBar().value() == 0
    assert canvas.mapTo(viewport, canvas.mapFromScene(title.bottomLeft())).y() <= viewport.height()
    assert canvas.height() >= _CANVAS_MIN_HEIGHT
    if size == (1600, 1000):
        assert canvas.height() > _CANVAS_MIN_HEIGHT
        assert w._legend.mapTo(viewport, w._legend.rect().bottomLeft()).y() <= viewport.height()
    window.close()


def test_the_main_plot_keeps_its_minimum_width_at_the_pages_minimum_width(qapp):
    """A splitter can narrow the page only to its minimum size hint, where the R² plot is still 240 px wide."""
    from PyQt6.QtCore import Qt

    from gui.plotting.identifiability_widget import _MAIN_MIN_WIDTH

    w = _widget(_fit(), _profile())
    w.update_sensitivity(_sensitivity())
    w._colour_combo.setCurrentIndex(w._colour_combo.findText('[Host]₀'))
    w.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    w.show()
    w.resize(w.minimumSizeHint().width(), 700)
    for _ in range(5):
        qapp.processEvents()
    assert _MAIN_MIN_WIDTH == 240
    assert w._items['Ka_guest']['main'].getViewBox().width() >= _MAIN_MIN_WIDTH
    assert w._content.horizontalScrollBar().maximum() == 0
    w.clear()
    assert w.minimumSizeHint().width() < _MAIN_MIN_WIDTH
    w.close()


# ---------------------------------------------------------------------------
# Section 2: sensitivity overlay
# ---------------------------------------------------------------------------


def test_sensitivity_samples_are_a_translucent_cloud_behind_the_attempts_and_lines(qapp):
    """One colour at about 30 % opacity, no ring, below the floor or not; above the band, under everything else."""
    from PyQt6.QtCore import Qt

    sens = _sensitivity()
    w = _widget(_fit(per_replica=True), _profile(per_replica=True))
    w.update_sensitivity(sens)
    assert not w._controls.isHidden()
    assert [w._colour_combo.itemText(i) for i in range(w._colour_combo.count())] == [
        'None',
        '[Host]₀',
        'Guest (titrant)',
    ]
    items = w._items['Ka_guest']
    scatter = items['samples']
    assert _n_points(scatter) == N_SAMPLES - 1
    assert items['colour_bar'] is None
    fill = scatter.opts['brush'].color()
    assert fill.name() == '#2a78d6' and 0.25 <= fill.alphaF() <= 0.35
    assert scatter.opts['pen'].style() == Qt.PenStyle.NoPen
    band = next(item for item in items['main'].items if type(item).__name__ == 'LinearRegionItem')
    lines = [items['average'], *items['replicas'], items['floor'], items['cut']]
    attempts = [items['attempts_below'], items['attempts_passing']]
    assert band.zValue() < scatter.zValue() < min(item.zValue() for item in lines + attempts)
    assert '1 of 21 sensitivity samples not shown' in w._notes.text()
    assert 'Min R² of' not in w._notes.text()


def test_a_run_with_another_quality_floor_is_noted(qapp):
    sens = _sensitivity()
    sens.floor = 0.95
    w = _widget(_fit(), _profile())
    w.update_sensitivity(sens)
    assert "flagged its samples against a Min R² of 0.95; the dashed line is this fit's Min R² of 0.99" in (
        w._notes.text()
    )


def test_show_samples_checkbox_hides_the_cloud_and_keeps_the_view(qapp):
    """Unticking hides the cloud, its colour bar, colour control, legend entries and notes; the zoom stays as it was."""
    w = _widget(_fit(), _profile())
    w.update_sensitivity(_sensitivity())
    w._colour_combo.setCurrentIndex(w._colour_combo.findText('[Host]₀'))
    items = w._items['Ka_guest']
    assert 'sample&nbsp;best&nbsp;fit' in w._legend.text() and 'than&nbsp;entered' in w._legend.text()
    items['main'].setRange(xRange=(8.4, 8.6), yRange=(0.99, 0.995), padding=0)
    zoomed = items['main'].viewRange()

    assert '1 of 21 sensitivity samples not shown' in w._notes.text()

    w._show_samples.setChecked(False)
    assert 'sensitivity samples' not in w._notes.text()
    assert not items['samples'].isVisible() and not items['colour_bar'].isVisible()
    assert w._colour_combo.isHidden() and w._colour_label.isHidden() and not w._controls.isHidden()
    assert 'sample&nbsp;best&nbsp;fit' not in w._legend.text() and 'than&nbsp;entered' not in w._legend.text()
    assert w._items['Ka_guest'] is items and items['main'].viewRange() == zoomed

    w._show_samples.setChecked(True)
    assert '1 of 21 sensitivity samples not shown' in w._notes.text()
    assert items['samples'].isVisible() and items['colour_bar'].isVisible() and not w._colour_combo.isHidden()
    assert 'sample&nbsp;best&nbsp;fit' in w._legend.text() and 'than&nbsp;entered' in w._legend.text()
    assert items['main'].viewRange() == zoomed


def test_colour_by_input_uses_the_diverging_scale(qapp):
    w = _widget(_fit(), _profile())
    w.update_sensitivity(_sensitivity())
    w._colour_combo.setCurrentIndex(w._colour_combo.findText('[Host]₀'))
    items = w._items['Ka_guest']
    assert items['colour_bar'] is not None
    brushes = items['samples'].data['brush']
    # h0 runs from −10 % (first sample) to +10 % (last): blue to red, more opaque than the one-colour cloud.
    assert brushes[0].color().getRgb() == (42, 120, 214, 153)
    assert brushes[N_SAMPLES - 2].color().getRgb() == (227, 73, 72, 153)

    # Restyling keeps the chosen input.
    from gui.plotting.plot_style import DEFAULT_STYLE

    w.apply_style(DEFAULT_STYLE)
    assert w._colour_combo.currentText() == '[Host]₀'
    assert w._items['Ka_guest']['colour_bar'] is not None


def test_replicate_handling_mismatch_is_noted(qapp):
    w = _widget(_fit(), _profile())
    w.update_sensitivity(_sensitivity(ReplicateMode.FOLLOW))
    assert 'different signals' not in w._notes.text()
    w.update_sensitivity(_sensitivity(ReplicateMode.PER_REPLICA))
    assert 'fitted each replicate separately but this fit used their average' in w._notes.text()


# ---------------------------------------------------------------------------
# Real objects
# ---------------------------------------------------------------------------


def test_renders_a_real_ida_fit_and_its_profile(qapp):
    """The IDA demo data: every non-negative attempt drawn, the CI stated from the profile."""
    from core.assays.ida import IDAAssay
    from core.data_processing.measurement_set import MeasurementSet
    from core.io import load_measurements
    from core.pipeline.fit_pipeline import FitConfig, fit_measurement_set
    from core.pipeline.profile import fit_profile
    from gui.plotting.labels import fmt_sci

    ms = MeasurementSet.from_dataframe(load_measurements('data/IDA_system.txt'))
    conditions = {'Ka_dye': Q_(16.8e6, '1/M'), 'h0': Q_(4.3e-6, 'M'), 'd0': Q_(6e-6, 'M')}
    config = FitConfig(per_replica=False, n_trials=20, seed=1)
    fit = fit_measurement_set(ms, IDAAssay, conditions, config)
    profile = fit_profile(ms, IDAAssay, conditions, config)

    w = _widget(fit, profile)
    items = w._items['Ka_guest']
    r2 = fit.attempt_quality['r_squared']
    assert _n_points(items['attempts_passing']) + _n_points(items['attempts_below']) == int(np.sum(r2 >= 0))
    assert len(items['average'].getData()[0]) == profile.grid.size
    assert f'95% CI {fmt_sci(profile.ci[0])} – {fmt_sci(profile.ci[1])}' in w._summary.text()
