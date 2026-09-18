"""Widget tests for IdentifiabilityWidget — Ka profiles, joint region, sensitivity overlay.

Require a ``QApplication`` (the ``qapp`` fixture).
"""

import numpy as np
import pytest

pytest.importorskip('PyQt6')

from PyQt6.QtCore import Qt  # noqa: E402

from core.assays.registry import ASSAY_REGISTRY, AssayType, ParamKind  # noqa: E402
from core.pipeline.fit_pipeline import FitResult  # noqa: E402
from core.pipeline.profile import JointRegion, ProfileResult, ProfileSet  # noqa: E402
from core.pipeline.sensitivity import (  # noqa: E402
    TITRANT,
    InputSpec,
    SensitivityConfig,
    SensitivityMode,
    SensitivityResult,
)
from core.pipeline.varpro import KaInterval  # noqa: E402
from core.units import Q_  # noqa: E402

IDA_KEYS = ('Ka_guest', 'I0', 'I_dye_free', 'I_dye_bound')
HG2_KEYS = ('Ka_HG', 'Ka_HG2', 'I0', 'I_G', 'I_H', 'I_HG', 'I_HG2')

BEST_KA = 10**8.5
PEAK_R2 = 0.995
CUT_R2 = 0.99


def _fit(keys=IDA_KEYS, assay='IDA', *, per_replica=False):
    """A FitResult carrying only what the tab reads: the parameters, the assay and the replicate record."""
    return FitResult(
        parameters={k: Q_(1.0 if k.startswith('Ka') else 0.5, 'dimensionless') for k in keys},
        rmse=0.1,
        r_squared=PEAK_R2,
        x_fit=Q_(np.zeros(3), 'M'),
        y_fit=Q_(np.zeros(3), 'au'),
        assay_type=assay,
        model_name='equilibrium_4param',
        fit_config={'per_replicate': per_replica},
    )


def _interval(low=1e8, high=1e9, *, open_low=False, open_high=False, split=False, unsolvable=(False, False)):
    return KaInterval(
        low=low,
        high=high,
        open_low=open_low,
        open_high=open_high,
        level=0.95,
        dof=9,
        split=split,
        unsolvable_low=unsolvable[0],
        unsolvable_high=unsolvable[1],
    )


def _profile(ka_key='Ka_guest', *, per_replica=False, interval=..., centre=8.5, peak=PEAK_R2):
    """A bell-shaped profile around ``10**centre``, with its interval and cut-off.

    ``interval=None`` is a Ka pinned by equal bounds, which has none.
    """
    grid = np.logspace(-8, 12, 401)

    def bump(middle, top):
        return top * np.exp(-((np.log10(grid) - middle) ** 2))

    return ProfileResult(
        ka_key=ka_key,
        grid=grid,
        r2=bump(centre, peak),
        replica_r2={rid: bump(centre + 0.1 * i, peak - 0.005 * (i + 1)) for i, rid in enumerate('ABC')}
        if per_replica
        else None,
        best_ka=10**centre,
        best_r2=peak,
        interval=_interval() if interval is ... else interval,
        r2_threshold=CUT_R2,
        n_points=12,
        n_params=3,
        per_replica=per_replica,
    )


def _profile_set(**kwargs):
    profile = _profile(**kwargs)
    return ProfileSet(profiles={profile.ka_key: profile}, region=None)


#: log10 Ka of the two-Ka region's centre, and the radius of its accepted disc.
REGION_CENTRE = (6.0, 4.0)
REGION_THRESHOLD = 0.99


def _region_r2(x, y):
    """A paraboloid peaking at ``REGION_CENTRE``: accepted where the log10 pair lies within one unit of it."""
    lx, ly = np.log10(x)[:, None], np.log10(y)[None, :]
    return 1.0 - 0.01 * ((lx - REGION_CENTRE[0]) ** 2 + (ly - REGION_CENTRE[1]) ** 2)


def _two_ka_set():
    """A hand-built ProfileSet for a 1:2 model: a profile per binding constant and their joint region."""
    x = np.geomspace(1e5, 1e7, 16)
    y = np.geomspace(1e3, 1e5, 12)
    r2 = _region_r2(x, y)
    r2[0, 0] = np.nan  # a Ka pair the equilibrium model has no solution for
    profiles = {
        'Ka_HG': _profile('Ka_HG', centre=6.0, interval=_interval(10**5.5, 10**6.5)),
        'Ka_HG2': _profile('Ka_HG2', centre=4.0, interval=_interval(10**3.5, 10**4.5)),
    }
    region = JointRegion(
        ka_keys=('Ka_HG', 'Ka_HG2'),
        x=x,
        y=y,
        r2=r2,
        r2_threshold=REGION_THRESHOLD,
        level=0.95,
        best=(10 ** REGION_CENTRE[0], 10 ** REGION_CENTRE[1]),
    )
    return ProfileSet(profiles=profiles, region=region)


N_SAMPLES = 21
NO_FIT = 10  # the sample at offset 0 produced no fit


def _sensitivity():
    ka = 10 ** np.linspace(8.2, 8.8, N_SAMPLES)
    r2 = np.linspace(0.97, 0.999, N_SAMPLES)
    ka[NO_FIT] = r2[NO_FIT] = np.nan
    return SensitivityResult(
        mode=SensitivityMode.SOBOL,
        assay_type='IDA',
        ka_keys=('Ka_guest',),
        baseline_ka={'Ka_guest': BEST_KA},
        x_offsets_pct=None,
        y_offsets_pct=None,
        ka_grid=None,
        n_success=N_SAMPLES - 1,
        n_total=2 * N_SAMPLES,
        config=SensitivityConfig(
            SensitivityMode.SOBOL,
            N_SAMPLES,
            {'h0': InputSpec.sigma_pct(5.0), TITRANT: InputSpec.sigma_pct(5.0)},
        ),
        seed_used=0,
        sample_offsets_pct={'h0': np.linspace(-10, 10, N_SAMPLES), TITRANT: np.linspace(5, -5, N_SAMPLES)},
        sample_ka={'Ka_guest': ka},
        sample_r2=r2,
    )


def _widget(fit=None, profile=None, assay='IDA'):
    from gui.plotting.identifiability_widget import IdentifiabilityWidget

    w = IdentifiabilityWidget()
    if fit is not None:
        w.update_fit(fit, profile, assay)
    return w


def _n_points(scatter):
    return len(scatter.getData()[0])


def _scatters(plot):
    import pyqtgraph as pg

    return [item for item in plot.items if isinstance(item, pg.ScatterPlotItem)]


# ---------------------------------------------------------------------------
# States
# ---------------------------------------------------------------------------


def test_placeholder_before_any_fit(qapp):
    w = _widget()
    assert w._stack.currentWidget() is w._message
    assert 'Run a fit' in w._message.text()


def test_dye_alone_is_not_applicable(qapp):
    w = _widget(_fit(keys=('slope', 'intercept'), assay='DYE_ALONE'), None, 'DYE_ALONE')
    assert w._stack.currentWidget() is w._message
    assert 'Not applicable' in w._message.text()


def test_a_fit_without_profiles_says_so_and_draws_nothing(qapp):
    """Without the profiles there is nothing to show: the tab says so and names what to do, rather than an empty chart."""
    w = _widget(_fit(), None)
    assert w._stack.currentWidget() is w._message
    assert 'Run the fit again' in w._message.text()
    assert w._items == {}


def test_pending_profiles_hold_the_page(qapp):
    w = _widget()
    w.show_profile_pending(_fit(), 'IDA')
    assert w._stack.currentWidget() is w._message
    assert 'Working out' in w._message.text()


def test_clear_returns_to_placeholder(qapp):
    w = _widget(_fit(), _profile_set())
    w.update_sensitivity(_sensitivity())
    w.clear()
    assert w._stack.currentWidget() is w._message
    assert 'Run a fit' in w._message.text()
    assert w._controls.isHidden()
    assert w._items == {} and w._region_items == {}


# ---------------------------------------------------------------------------
# One binding constant: the profile panel
# ---------------------------------------------------------------------------


def test_average_mode_draws_one_profile_line(qapp):
    w = _widget(_fit(), _profile_set())
    items = w._items['Ka_guest']
    assert items['average'] is not None and items['replicas'] == []
    assert items['average'].opts['pen'].widthF() == 2


def test_per_replicate_mode_draws_one_thin_line_per_replicate(qapp):
    w = _widget(_fit(per_replica=True), _profile_set(per_replica=True))
    items = w._items['Ka_guest']
    assert len(items['replicas']) == 3
    assert all(c.opts['pen'].widthF() == 1 for c in items['replicas'])
    assert items['average'].opts['pen'].widthF() == 2
    assert "best fit of the replicates' average" in w._summary.text()


def test_a_replicate_curve_off_the_default_view_is_named_in_the_notes(qapp):
    """The legend promises a curve per replicate; one drawn outside the default view has to be accounted for."""
    from dataclasses import replace

    profile = _profile(per_replica=True)
    # Two replicates fit about as well as the average; the third is far worse,
    # so its whole curve lies below a view framed on the peak and the cut-off.
    curves = {'A': profile.r2, 'B': profile.r2, 'C': profile.r2 - 0.5}
    w = _widget(
        _fit(per_replica=True),
        ProfileSet(profiles={'Ka_guest': replace(profile, replica_r2=curves)}, region=None),
    )

    _, (y_lo, _) = w._items['Ka_guest']['main'].viewRange()
    assert curves['C'].max() < y_lo  # the curve really is off the default view
    assert 'each replicate on its own' in w._legend.text().replace('&nbsp;', ' ')
    assert '1 of 3 replicate curves' in w._notes.text()
    assert 'zoom out' in w._notes.text()


def test_the_profile_lines_are_drawn_antialiased(qapp):
    """Each line carries its own antialiasing setting and paints by that, never by the view's.

    A line left at the library's default is drawn in hard stair-steps, on
    screen and in every picture saved from the tab.
    """
    items = _widget(_fit(per_replica=True), _profile_set(per_replica=True))._items['Ka_guest']

    assert items['average'].opts['antialias']
    assert items['replicas'] and all(c.opts['antialias'] for c in items['replicas'])


def test_the_only_point_drawn_is_the_best_fit(qapp):
    """One fit, one point: the marker stands at the reported estimate and its R².

    Everything else on the panel is the exact profile and the range it implies,
    so no point on screen can be read as a second estimate of Ka.
    """
    w = _widget(_fit(), _profile_set())
    items = w._items['Ka_guest']

    assert _scatters(items['main']) == [items['best']]
    assert _n_points(items['best']) == 1
    assert items['best'].getData()[0][0] == pytest.approx(np.log10(BEST_KA))
    assert items['best'].getData()[1][0] == pytest.approx(PEAK_R2)


def test_confidence_interval_is_stated(qapp):
    """Best Ka 10^8.5 with an interval of 1e8 to 1e9: −68 % and +216 % of the best fit."""
    from gui.plotting.labels import fmt_interval_html, fmt_sci

    w = _widget(_fit(), _profile_set())
    text = w._summary.text()
    # The same bracket the summary table and the report write it in.
    assert f'95% CI {fmt_interval_html(fmt_sci(1e8), fmt_sci(1e9), False, False)} M<sup>−1</sup>' in text
    assert '(−68% / +216%)' in text
    assert 'open' not in text


def test_header_states_what_the_cut_off_was_worked_out_from(qapp):
    """The F test's n and p are on screen, with the bounds caveat, so the cut-off can be checked."""
    w = _widget(_fit(), _profile_set())
    text = w._summary.text()
    assert '12 data points' in text and '3 fitted parameters' in text
    assert 'reaches no further than the parameter bounds' in text


def test_a_ka_pinned_by_its_bounds_says_so_instead_of_giving_an_interval(qapp):
    """Equal Ka bounds leave nothing to estimate: the header says Ka is fixed, and quotes no interval."""
    w = _widget(_fit(), _profile_set(interval=None))
    text = w._summary.text()
    assert 'is fixed at' in text and 'so there is no interval' in text
    assert 'CI' not in text and '%' not in text
    # The chart has to agree with the header: with Ka held, the threshold is the
    # R² a one-parameter improvement would have to beat, not a CI cut-off.
    assert 'confidence interval' not in w._legend.text()
    assert 'CI cut-off' not in w._legend.text()
    items = w._items['Ka_guest']
    assert items['cut'] is None and items['band'] is None
    assert not items['main'].getAxis('right').isVisible()


def test_a_split_accepted_region_is_called_out(qapp):
    """Where the accepted Ka values come in separate stretches, the band's span is not read as one run."""
    w = _widget(_fit(), _profile_set(interval=_interval(split=True)))
    text = w._summary.text()
    assert 'separate stretches' in text and 'the band spans all of them' in text
    assert '95% CI' in text  # the interval is still quoted, as the envelope it is


def test_an_r2_a_hair_below_one_does_not_read_as_one(qapp):
    """The header's R² comes from the shared formatter, which shows as many decimals as it takes."""
    from gui.plotting.labels import fmt_r2

    w = _widget(_fit(), _profile_set(peak=1.0 - 1e-8))
    assert f'(R² {fmt_r2(1.0 - 1e-8)})' in w._summary.text()
    assert '(R² 1.0000)' not in w._summary.text()


def test_open_interval_says_open_and_says_what_would_close_it(qapp):
    """An open side reads as the words the whole app gives it, and only the closed end gets a distance."""
    from gui.plotting.labels import fmt_interval_html, fmt_sci

    w = _widget(_fit(), _profile_set(interval=_interval(1e8, 1e12, open_high=True)))
    text = w._summary.text()
    assert f'95% CI {fmt_interval_html(fmt_sci(1e8), fmt_sci(1e12), False, True)} M<sup>−1</sup>' in text
    # The open end lies no distance from the best fit, so only the closed one is quoted.
    assert '(lower end −68%)' in text
    assert 'cannot rule out a higher' in text
    assert 'It reaches the bound of 1.0×10¹² M<sup>−1</sup>.' in text
    assert 'before the signal levels off' in text


def test_an_interval_the_data_close_at_neither_end_says_so_once(qapp):
    """Both sides open reads as one statement, not as two ends and two changes that are not numbers."""
    from gui.plotting.labels import fmt_interval_html, fmt_sci

    w = _widget(_fit(), _profile_set(interval=_interval(1e-8, 1e12, open_low=True, open_high=True)))
    text = w._summary.text()

    assert f'95% CI {fmt_interval_html(fmt_sci(1e-8), fmt_sci(1e12), True, True)}' in text
    assert '%)' not in text.split('<br>')[0]  # no change quoted for an end that is not there
    assert 'M<sup>−1</sup>]' not in text  # and no unit on a bracket holding no number


def test_an_open_lower_edge_asks_for_more_titrant(qapp):
    w = _widget(_fit(), _profile_set(interval=_interval(1e-8, 1e9, open_low=True)))
    text = w._summary.text()
    assert 'cannot rule out a lower' in text
    assert 'higher titrant concentration' in text


def test_an_edge_open_at_the_solver_wall_does_not_call_it_the_bound(qapp):
    """The last solvable Ka is neither the bound in force nor a limit the data set.

    Read as the bound, it names a number the fit was never given — with a bound
    of 1e30 the header would announce a bound of 2×10¹⁹.
    """
    interval = _interval(1e8, 1e12, open_high=True, unsolvable=(False, True))
    w = _widget(_fit(), _profile_set(interval=interval))
    text = w._summary.text()

    assert 'cannot be solved past 1.0×10¹²' in text
    assert 'reaches the bound of' not in text


def test_a_side_resting_on_the_other_constants_bound_names_it_and_gives_no_data_advice(qapp):
    """Where only the other constant's bound rejects the fit, more titration points would not close the side."""
    from dataclasses import replace

    interval = replace(_interval(2.3e3, 1e9, open_low=True), limited_by_low='Ka_HG2')
    w = _widget(_fit(), _profile_set(interval=interval))
    text = w._summary.text()

    assert 'rejected beyond 2.3×10³' in text and 'cannot go past its bound' in text
    assert 'reaches the bound of' not in text
    assert 'higher titrant concentration' not in text


def test_a_drop_close_to_minus_100_percent_is_not_rounded_to_it(qapp):
    """−99.6 % shows as such: −100 % would say the interval reaches a Ka of zero."""
    from gui.plotting.identifiability_widget import _pct

    assert _pct(3.3e6 / 8.14e8) == '−99.6%'
    assert _pct(0.32) == '−68%'
    assert _pct(3.16) == '+216%'


def test_replicates_the_fit_left_out_are_named(qapp):
    fit = _fit(per_replica=True)
    fit.metadata['replica_failures'] = {'A': 'Its own best fit needs a different Ka than the other replicates share.'}
    w = _widget(fit, _profile_set(per_replica=True))
    assert 'Replicate A is left out here, as it was from the fit.' in w._notes.text()


def test_the_cut_off_is_named_beside_the_plot(qapp):
    """The dotted cut-off is named on a right-hand axis at its height, never over the data."""
    w = _widget(_fit(), _profile_set())
    items = w._items['Ka_guest']
    assert items['cut'].pen.style() == Qt.PenStyle.DotLine and items['cut'].value() == CUT_R2
    axis = items['main'].getAxis('right')
    assert axis.isVisible()
    assert axis._tickLevels == [[(CUT_R2, 'cut-off 0.9900')]]
    assert items['cut'].zValue() < items['average'].zValue() < items['best'].zValue()


def test_r2_axis_is_linear(qapp):
    """Every point sits at its R² itself: the line, the marker and the cut-off share one linear scale."""
    profile_set = _profile_set()
    w = _widget(_fit(), profile_set)
    items = w._items['Ka_guest']
    assert not items['main'].getAxis('left').logMode
    np.testing.assert_array_equal(items['average'].getData()[1], profile_set.profiles['Ka_guest'].r2)


def test_default_view_frames_the_peak_and_the_cut_off(qapp):
    """Peak 0.995 and cut-off 0.99: the view starts one level span (0.005) below them and stops 0.6 spans above.

    The two levels keep a readable share of the height, and View All still
    reaches the full range of the drawn curve.
    """
    w = _widget(_fit(), _profile_set())
    main = w._items['Ka_guest']['main']
    (x_lo, x_hi), (y_lo, y_hi) = main.viewRange()
    assert (y_lo, y_hi) == pytest.approx((0.985, 0.998))
    assert (PEAK_R2 - CUT_R2) / (y_hi - y_lo) >= 1 / 8
    # Across: the interval with a fifth of its width on either side, so the band
    # reads as a band and the curve is seen falling below the cut-off outside it.
    assert (x_lo, x_hi) == pytest.approx((7.8, 9.2))

    main.autoRange()
    _, (all_lo, all_hi) = main.viewRange()
    assert all_lo <= 0.0 and all_hi >= PEAK_R2


def test_an_interval_open_at_both_ends_is_not_padded_past_the_drawn_curve(qapp):
    """Where the data close neither side, the view stops at the ends of the curve rather than on empty margins."""
    interval = _interval(1e-8, 1e12, open_low=True, open_high=True)
    w = _widget(_fit(), _profile_set(interval=interval))
    (x_lo, x_hi), _ = w._items['Ka_guest']['main'].viewRange()
    assert (x_lo, x_hi) == pytest.approx((-8.0, 12.0))


def test_the_main_plot_keeps_its_minimum_width_at_the_pages_minimum_width(qapp):
    """A splitter can narrow the page only to its minimum size hint, where the R² plot is still 240 px wide."""
    from gui.plotting.identifiability_widget import _MAIN_MIN_WIDTH

    w = _widget(_fit(), _profile_set())
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


#: Usable width of a 13-inch laptop screen. No tab may put the main window's
#: minimum width above this: a window wider than the screen cannot be dragged
#: back, so the fit it shows can never be read again.
_LAPTOP_SCREEN_WIDTH = 1440


def _fitted_ka_keys(assay):
    meta = ASSAY_REGISTRY[assay]
    return [key for key in meta.parameter_keys if meta.param_kinds[key] is ParamKind.BINDING_CONSTANT]


def _set_for(assay):
    """A fit of *assay* and a profile per binding constant it fits, with the joint region of a pair."""
    from dataclasses import replace

    ka_keys = _fitted_ka_keys(assay)
    profiles = {
        key: _profile(key, centre=6.0 - 2 * i, interval=_interval(10 ** (5.5 - 2 * i), 10 ** (6.5 - 2 * i)))
        for i, key in enumerate(ka_keys)
    }
    region = replace(_two_ka_set().region, ka_keys=tuple(ka_keys)) if len(ka_keys) == 2 else None
    fit = _fit(keys=ASSAY_REGISTRY[assay].parameter_keys, assay=assay.name)
    return fit, ProfileSet(profiles=profiles, region=region)


@pytest.mark.parametrize('assay', [a for a in AssayType if _fitted_ka_keys(a)], ids=lambda a: a.name)
def test_no_assay_makes_the_window_wider_than_a_laptop_screen(qapp, monkeypatch, assay):
    """Opening the tab on any fit must leave the window a size a 13-inch screen holds.

    A model with two binding constants draws three panels. Asked for in full
    they are wider than the screen, so the tab asks for one panel and the page
    scrolls over the rest — every panel still drawn at its full width.
    """
    from gui.main_window import FittingMainWindow
    from gui.plotting.identifiability_widget import _MAIN_MIN_WIDTH

    monkeypatch.setattr(FittingMainWindow, '_run_update_check', lambda self, silent: None)
    window = FittingMainWindow()
    window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    session = window.active_session()
    w = session._identifiability_widget
    w.update_fit(*_set_for(assay), assay.name)
    session._plot_tabs.setCurrentWidget(w)
    window.resize(1280, 820)
    window.show()
    for _ in range(6):
        qapp.processEvents()

    assert window.minimumSizeHint().width() <= _LAPTOP_SCREEN_WIDTH
    # And the window really goes back to that width, rather than snapping wider.
    window.resize(_LAPTOP_SCREEN_WIDTH, 800)
    for _ in range(6):
        qapp.processEvents()
    assert window.width() <= _LAPTOP_SCREEN_WIDTH
    for items in w._items.values():
        assert items['main'].getViewBox().width() >= _MAIN_MIN_WIDTH
    window.close()


def test_a_chart_too_wide_for_the_tab_does_not_take_the_text_with_it(qapp, monkeypatch):
    """Only the chart scrolls sideways: a sentence a reader has to scroll to finish is not readable.

    The text is laid out under a page as wide as the chart, so it has to be held
    to the tab's width and given the height that width needs — with no room
    taken from the widget below it.
    """
    from gui.main_window import FittingMainWindow

    monkeypatch.setattr(FittingMainWindow, '_run_update_check', lambda self, silent: None)
    window = FittingMainWindow()
    window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    session = window.active_session()
    w = session._identifiability_widget
    w.update_fit(*_set_for(AssayType.DBA_HG2), 'DBA_HG2')
    session._plot_tabs.setCurrentWidget(w)
    window.resize(1100, 700)
    window.show()
    for _ in range(8):
        qapp.processEvents()

    viewport = w._content.viewport()
    assert w._content.horizontalScrollBar().maximum() > 0  # the chart really is wider than the tab
    stacked = [w._summary, w._glw, w._legend, w._notes]
    for widget in (w._summary, w._legend, w._notes):
        assert widget.width() <= viewport.width()
        assert widget.height() >= widget.heightForWidth(widget.width())  # every line of it is drawn
    for above, below in zip(stacked, stacked[1:]):
        assert above.geometry().bottom() < below.geometry().top()
    window.close()


# ---------------------------------------------------------------------------
# Two binding constants: a panel each and the joint region
# ---------------------------------------------------------------------------


def test_two_binding_constants_get_a_panel_each_and_a_joint_region(qapp):
    """Both profiles are drawn with their own interval, and the region panel fills the pairs the data support."""
    from gui.plotting.identifiability_widget import _REGION_FILL

    profile_set = _two_ka_set()
    w = _widget(_fit(keys=HG2_KEYS, assay='DBA_HG2'), profile_set, 'DBA_HG2')

    assert list(w._items) == ['Ka_HG', 'Ka_HG2']
    for key in ('Ka_HG', 'Ka_HG2'):
        items = w._items[key]
        assert items['average'] is not None and items['band'] is not None and items['cut'] is not None
    # One summary line per binding constant, each with its own interval.
    summary = w._summary.text()
    assert summary.count('95% CI') == 2
    assert '[3.2×10⁵, 3.2×10⁶]' in summary and '[3.2×10³, 3.2×10⁴]' in summary

    region = profile_set.region
    inside = np.isfinite(region.r2) & (region.r2 >= region.r2_threshold)
    assert not inside[0, 0]  # the pair the model has no solution for is out, whatever its R² compares as
    # What is painted, not only what was handed over: an image left to scale
    # itself to its own largest byte fills the region white instead of grey.
    drawn = w._region_items['region']
    drawn.render()
    painted = drawn.qimage
    assert (painted.width(), painted.height()) == region.r2.shape
    filled = np.array(
        [[painted.pixelColor(i, j).alpha() > 0 for j in range(painted.height())] for i in range(painted.width())]
    )
    np.testing.assert_array_equal(filled, inside)
    i, j = np.argwhere(inside)[0]
    assert painted.pixelColor(int(i), int(j)).getRgb() == _REGION_FILL
    # Both single-Ka intervals are shown behind it, and the best fit is marked.
    assert len(w._region_items['bands']) == 2
    best = w._region_items['best'].getData()
    assert (float(best[0][0]), float(best[1][0])) == pytest.approx(REGION_CENTRE)


def test_the_region_panel_reads_in_ka_with_a_labelled_axis_per_constant(qapp):
    """Its axes are the two binding constants, named as everywhere else and ticked in Ka, not in log10."""
    w = _widget(_fit(keys=HG2_KEYS, assay='DBA_HG2'), _two_ka_set(), 'DBA_HG2')
    plot = w._region_items['main']

    assert plot.getAxis('bottom').labelText == '<b>K<sub>a(HG)</sub></b> [M<sup>−1</sup>]'
    assert plot.getAxis('left').labelText == '<b>K<sub>a(HG₂)</sub></b> [M<sup>−1</sup>]'
    assert plot.getAxis('bottom').logMode and plot.getAxis('left').logMode
    # The drawn map covers the region's grid, each cell centred on its Ka pair.
    rect = w._region_items['region'].boundingRect()
    mapped = w._region_items['region'].mapRectToView(rect)
    step = np.log10(1e7 / 1e5) / 15
    assert mapped.left() == pytest.approx(5.0 - step / 2)
    assert mapped.right() == pytest.approx(7.0 + step / 2)


def test_one_binding_constant_has_no_region_panel(qapp):
    w = _widget(_fit(), _profile_set())
    assert w._region_items == {}


# ---------------------------------------------------------------------------
# Layout and export
# ---------------------------------------------------------------------------


def test_export_image_writes_the_whole_tab(tmp_path, qapp):
    """The picture carries the header text and the chart, and an empty tab says there is nothing to save.

    Only PNG: Qt's SVG painter drops the clip each plot keeps its curves inside,
    so the profile curve would be drawn across the legend and the notes.
    """
    w = _widget()
    with pytest.raises(ValueError, match='Run a fit'):
        w.export_image(str(tmp_path / 'empty.png'))

    w = _widget(_fit(keys=HG2_KEYS, assay='DBA_HG2'), _two_ka_set(), 'DBA_HG2')
    w.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    w.resize(1100, 700)
    w.show()
    qapp.processEvents()
    path = tmp_path / 'chart.png'
    w.export_image(str(path))
    assert path.stat().st_size > 0
    for unsupported in ('chart.svg', 'chart.pdf'):
        with pytest.raises(ValueError, match='cannot be written'):
            w.export_image(str(tmp_path / unsupported))
    w.close()


def test_a_short_tab_keeps_the_whole_chart_in_view_and_puts_the_text_below_it(qapp):
    """On a short window the chart and its Ka axis fit the viewport; the legend and notes go below the fold.

    A first view of the tab showing a chart cut off above its axis is the one
    thing the page must not do: without the axis a point's Ka cannot be read, and
    nothing on screen says the rest is a scroll away.
    """
    w = _widget(_fit(per_replica=True), _profile_set(per_replica=True))
    w.update_sensitivity(_sensitivity())
    w.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    w.resize(728, 340)  # the Identifiability tab of an 1100x700 window
    w.show()
    qapp.processEvents()

    viewport = w._content.viewport()
    assert w._glw.geometry().bottom() <= viewport.height()  # the chart and its Ka axis are in view
    # What is left below the fold is the legend and the notes, and nothing else.
    below = w._content.widget().height() - viewport.height()
    assert 0 < below <= w._legend.height() + w._notes.height() + 16
    w.close()


def test_the_saved_picture_leaves_the_sample_controls_out(tmp_path, qapp):
    """The check box and the drop-down are not painted into the file, and come back afterwards.

    They change what the chart shows, which a saved picture cannot do, and on
    macOS Qt draws neither of them outside a window: the file would carry their
    text with no box and no frame around it.
    """
    from PyQt6.QtGui import QColor, QImage, QPalette

    marker = QColor(255, 0, 255)
    w = _widget(_fit(per_replica=True), _profile_set(per_replica=True))
    w.update_sensitivity(_sensitivity())
    palette = w._controls.palette()
    palette.setColor(QPalette.ColorRole.Window, marker)
    w._controls.setPalette(palette)
    w._controls.setAutoFillBackground(True)  # marks the strip the picture must not show
    w.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    w.resize(900, 700)
    w.show()
    qapp.processEvents()
    assert not w._controls.isHidden()

    path = tmp_path / 'chart.png'
    w.export_image(str(path))

    image = QImage(str(path))
    assert not image.isNull()
    painted = {image.pixelColor(x, y).rgb() for y in range(image.height()) for x in range(0, image.width(), 40)}
    assert marker.rgb() not in painted
    assert not w._controls.isHidden()  # still there for the next click
    assert w._show_samples.isChecked()
    w.close()


def test_legend_and_notes_start_below_the_ka_axis_label_in_the_default_window(qapp, monkeypatch):
    """In the 1280×820 main window the page scrolls, so the text under the chart never runs over its axis label."""
    from gui.main_window import FittingMainWindow

    monkeypatch.setattr(FittingMainWindow, '_run_update_check', lambda self, silent: None)
    window = FittingMainWindow()
    window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    session = window.active_session()
    w = session._identifiability_widget
    fit = _fit(per_replica=True)
    fit.metadata['replica_failures'] = {'A': 'Its own best fit needs a different Ka than the other replicates share.'}
    w.update_fit(fit, _profile_set(per_replica=True), 'IDA')
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
    assert w._notes.text().count('<br>') >= 2
    assert canvas.height() >= canvas.minimumHeight()
    assert label_bottom <= w._legend.geometry().top() <= w._notes.geometry().top()
    window.close()


@pytest.mark.parametrize('size', [(1280, 820), (1600, 1000)])
def test_the_whole_chart_is_in_view_without_scrolling_in_the_default_windows(qapp, monkeypatch, size):
    """The chart takes the tab's height, down to its minimum: its K<sub>a</sub> axis title never needs a scroll.

    Where the tab has room, the legend below the chart is in view too.
    """
    from gui.main_window import FittingMainWindow
    from gui.plotting.identifiability_widget import _CANVAS_MIN_HEIGHT

    monkeypatch.setattr(FittingMainWindow, '_run_update_check', lambda self, silent: None)
    window = FittingMainWindow()
    window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    session = window.active_session()
    w = session._identifiability_widget
    w.update_fit(_fit(), _profile_set(), 'IDA')
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


def test_the_saved_picture_leaves_the_guide_pointer_out(tmp_path, qapp, monkeypatch):
    """The note pointing at the guide button belongs to the live tab, not to a picture read on its own."""
    from gui.plotting import export
    from gui.plotting.identifiability_widget import _READING_POINTER

    w = _widget(_fit(), _profile_set())
    assert _READING_POINTER in w._notes.text()
    seen = []
    monkeypatch.setattr(export, 'export_widget', lambda widget, path, **kwargs: seen.append(w._notes.text()))

    w.export_image(str(tmp_path / 'tab.png'))

    assert seen and _READING_POINTER not in seen[0]
    assert _READING_POINTER in w._notes.text()


# ---------------------------------------------------------------------------
# Sensitivity overlay
# ---------------------------------------------------------------------------


def test_sensitivity_samples_are_a_translucent_cloud_behind_the_curves(qapp):
    """One colour at about 30 % opacity, no ring; above the band, under every line and marker."""
    w = _widget(_fit(per_replica=True), _profile_set(per_replica=True))
    w.update_sensitivity(_sensitivity())
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
    above = [items['average'], *items['replicas'], items['cut'], items['best']]
    assert items['band'].zValue() < scatter.zValue() < min(item.zValue() for item in above)
    assert '1 of 21 sensitivity samples not shown' in w._notes.text()


def test_show_samples_checkbox_hides_the_cloud_and_keeps_the_view(qapp):
    """Unticking hides the cloud, its colour bar, colour control, legend entries and notes; the zoom stays as it was."""
    w = _widget(_fit(), _profile_set())
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
    w = _widget(_fit(), _profile_set())
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


def test_a_run_for_another_assay_is_not_drawn(qapp):
    sens = _sensitivity()
    sens.assay_type = 'GDA'
    w = _widget(_fit(), _profile_set())
    w.update_sensitivity(sens)
    assert w._items['Ka_guest']['samples'] is None
    assert 'another assay type' in w._notes.text()


# ---------------------------------------------------------------------------
# Real objects
# ---------------------------------------------------------------------------


def test_renders_a_real_ida_fit_and_its_profile(qapp):
    """The IDA demo data: the drawn curve is the profile's own, and the header quotes its interval."""
    from core.assays.ida import IDAAssay
    from core.data_processing.measurement_set import MeasurementSet
    from core.io import load_measurements
    from core.pipeline.fit_pipeline import FitConfig, fit_measurement_set
    from core.pipeline.profile import fit_profile
    from gui.plotting.labels import fmt_sci

    ms = MeasurementSet.from_dataframe(load_measurements('data/IDA_system.txt'))
    conditions = {'Ka_dye': Q_(16.8e6, '1/M'), 'h0': Q_(4.3e-6, 'M'), 'd0': Q_(6e-6, 'M')}
    config = FitConfig(per_replica=False)
    fit = fit_measurement_set(ms, IDAAssay, conditions, config)
    profile_set = fit_profile(ms, IDAAssay, conditions, config)
    profile = profile_set.profiles['Ka_guest']

    w = _widget(fit, profile_set)
    items = w._items['Ka_guest']
    assert len(items['average'].getData()[0]) == profile.grid.size
    assert items['best'].getData()[0][0] == pytest.approx(np.log10(profile.best_ka))
    interval = profile.interval
    assert f'95% CI [{fmt_sci(interval.low)}, {fmt_sci(interval.high)}]' in w._summary.text()
