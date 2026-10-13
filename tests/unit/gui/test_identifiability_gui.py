"""Widget tests for IdentifiabilityWidget — Ka profiles, joint region, sensitivity overlay.

Require a ``QApplication`` (the ``qapp`` fixture).
"""

import numpy as np
import pytest

pytest.importorskip('PyQt6')

from PyQt6.QtCore import Qt  # noqa: E402

from core.assays.registry import ASSAY_REGISTRY, AssayType, ParamKind  # noqa: E402
from core.pipeline.diagnostics import Conflict, FitDiagnostics, InputShift, MisfitTest, Verdict  # noqa: E402
from core.pipeline.fit_pipeline import FitResult  # noqa: E402
from core.pipeline.input_aware import AwareProfile  # noqa: E402
from core.pipeline.inputs import TITRANT, InputSpec  # noqa: E402
from core.pipeline.profile import JointRegion, ProfileResult, ProfileSet  # noqa: E402
from core.pipeline.sensitivity import SensitivityConfig, SensitivityMode, SensitivityResult  # noqa: E402
from core.pipeline.varpro import KaInterval  # noqa: E402
from core.units import Q_  # noqa: E402

IDA_KEYS = ('Ka_guest', 'I0', 'I_dye_free', 'I_dye_bound')
HG2_KEYS = ('Ka_HG', 'Ka_HG2', 'I0', 'I_G', 'I_H', 'I_HG', 'I_HG2')

BEST_KA = 10**8.5
PEAK_R2 = 0.995
CUT_R2 = 0.99

#: The input-aware profile of the fixtures below: its peak sits at a Ka of its
#: own, its curve is wider — a fit free to move the inputs stays acceptable
#: further out — and it lies above the conditional curve everywhere, which is
#: what the method guarantees (the entered inputs are always available to it).
AWARE_CENTRE = 8.6
AWARE_WIDTH = 3.0  # decades of the aware bump, against one decade for the conditional one
AWARE_PEAK = 0.997
AWARE_CUT = 0.9945


def _fit(keys=IDA_KEYS, assay='IDA', *, per_replica=False, diagnostics=None, shifts=None):
    """A FitResult carrying only what the tab reads: the parameters, the assay and the replicate record."""
    return FitResult(
        # A binding constant inside its search box, in the unit a fit reports it in.
        parameters={k: Q_(BEST_KA, '1/M') if k.startswith('Ka') else Q_(0.5, 'au') for k in keys},
        rmse=0.1,
        r_squared=PEAK_R2,
        x_fit=Q_(np.zeros(3), 'M'),
        y_fit=Q_(np.zeros(3), 'au'),
        assay_type=assay,
        model_name='equilibrium_4param',
        fit_config={'per_replicate': per_replica},
        diagnostics=diagnostics,
        input_shifts=shifts or {},
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


def _bump(grid, middle, top, width=1.0):
    """A bell of height *top* peaking at ``10**middle``, *width* decades across."""
    return top * np.exp(-(((np.log10(grid) - middle) / width) ** 2))


def _aware_profile(
    ka_key='Ka_guest',
    *,
    grid=None,
    centre=AWARE_CENTRE,
    peak=AWARE_PEAK,
    cut=AWARE_CUT,
    interval=...,
):
    """The penalised profile of one Ka: what the fit reaches with the inputs free within their uncertainties.

    Its objective is the engine's own ``n log S`` of an inflated residual sum of
    squares, whose R² reading is ``1 - exp(P/n)/SS_tot``; the numbers here are
    written for ``SS_tot = 1`` and twelve points, so the two are consistent.
    """
    grid = np.logspace(-8, 12, 401) if grid is None else grid
    n = 12
    r2 = _bump(grid, centre, peak, AWARE_WIDTH)
    return AwareProfile(
        ka_key=ka_key,
        grid=grid,
        objective=n * np.log(1.0 - r2),
        r2=r2,
        offsets=np.zeros((grid.size, 1)),
        threshold=float(n * np.log(1.0 - cut)),
        r2_threshold=cut,
        interval=_interval(10**7.8, 10**9.4) if interval is ... else interval,
    )


def _profile(ka_key='Ka_guest', *, per_replica=False, interval=..., centre=8.5, peak=PEAK_R2, aware=None):
    """A bell-shaped profile around ``10**centre``, with its interval and cut-off.

    ``interval=None`` is a Ka pinned by equal bounds, which has none; *aware* is
    the same profile with the inputs free to move, ``None`` where every input
    was entered as exact.
    """
    grid = np.logspace(-8, 12, 401)

    return ProfileResult(
        ka_key=ka_key,
        grid=grid,
        r2=_bump(grid, centre, peak),
        replica_r2={rid: _bump(grid, centre + 0.1 * i, peak - 0.005 * (i + 1)) for i, rid in enumerate('ABC')}
        if per_replica
        else None,
        best_ka=10**centre,
        best_r2=peak,
        interval=_interval() if interval is ... else interval,
        r2_threshold=CUT_R2,
        n_points=12,
        n_params=3,
        per_replica=per_replica,
        aware=aware,
    )


def _profile_set(*, weighted=False, **kwargs):
    profile = _profile(**kwargs)
    return ProfileSet(profiles={profile.ka_key: profile}, region=None, weighted=weighted)


#: log10 Ka of the two-Ka region's centre, and the radius of its accepted disc.
REGION_CENTRE = (6.0, 4.0)
REGION_THRESHOLD = 0.99
#: Cut-off over the low-Ka_HG third of the region's grid, where the fits hold a signal parameter on its bound.
REGION_STEPPED_CUT = 0.98


def _region_r2(x, y):
    """A paraboloid peaking at ``REGION_CENTRE``: accepted where the log10 pair lies within one unit of it."""
    lx, ly = np.log10(x)[:, None], np.log10(y)[None, :]
    return 1.0 - 0.01 * ((lx - REGION_CENTRE[0]) ** 2 + (ly - REGION_CENTRE[1]) ** 2)


def _two_ka_set(*, aware=False):
    """A hand-built ProfileSet for a 1:2 model: a profile per binding constant and their joint region.

    With *aware*, each constant also carries the profile it has with the inputs
    free to move within the uncertainties stated for them.
    """
    x = np.geomspace(1e5, 1e7, 16)
    y = np.geomspace(1e3, 1e5, 12)
    r2 = _region_r2(x, y)
    r2[0, 0] = np.nan  # a Ka pair the equilibrium model has no solution for
    profiles = {
        'Ka_HG': _profile(
            'Ka_HG',
            centre=6.0,
            interval=_interval(10**5.5, 10**6.5),
            aware=_aware_profile('Ka_HG', centre=6.1, interval=_interval(10**5.3, 10**6.7)) if aware else None,
        ),
        'Ka_HG2': _profile(
            'Ka_HG2',
            centre=4.0,
            interval=_interval(10**3.5, 10**4.5),
            aware=_aware_profile('Ka_HG2', centre=4.1, interval=_interval(10**3.3, 10**4.7)) if aware else None,
        ),
    }
    r2_cut = np.full(r2.shape, REGION_THRESHOLD)
    r2_cut[: x.size // 3] = REGION_STEPPED_CUT
    region = JointRegion(
        ka_keys=('Ka_HG', 'Ka_HG2'),
        x=x,
        y=y,
        r2=r2,
        r2_threshold=REGION_THRESHOLD,
        level=0.95,
        best=(10 ** REGION_CENTRE[0], 10 ** REGION_CENTRE[1]),
        r2_cut=r2_cut,
    )
    return ProfileSet(profiles=profiles, region=region)


N_SAMPLES = 21
NO_FIT = 10  # the sample at offset 0 produced no fit


def _sensitivity():
    ka = 10 ** np.linspace(8.2, 8.8, N_SAMPLES)
    # The cloud sits on the profiles' own scale, which the run records beside
    # the unweighted R² each sample's fit reports as its quality.
    profile_r2 = np.linspace(0.97, 0.999, N_SAMPLES)
    r2 = profile_r2 - 0.02
    ka[NO_FIT] = r2[NO_FIT] = profile_r2[NO_FIT] = np.nan
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
        sample_profile_r2=profile_r2,
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
    from gui.plotting.labels import fmt_interval_html, fmt_value

    w = _widget(_fit(), _profile_set())
    text = w._summary.text()
    # The same bracket the summary table and the report write it in.
    assert f'95% CI {fmt_interval_html(fmt_value(1e8), fmt_value(1e9), False, False)} M<sup>−1</sup>' in text
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
    from gui.plotting.labels import fmt_interval_html, fmt_value

    w = _widget(_fit(), _profile_set(interval=_interval(1e8, 1e12, open_high=True)))
    text = w._summary.text()
    assert f'95% CI {fmt_interval_html(fmt_value(1e8), fmt_value(1e12), False, True)} M<sup>−1</sup>' in text
    # The open end lies no distance from the best fit, so only the closed one is quoted.
    assert '(lower end −68%)' in text
    assert 'cannot rule out a higher' in text
    assert 'It reaches the bound of 1.00×10¹² M<sup>−1</sup>.' in text
    assert 'before the signal levels off' in text


def test_an_interval_the_data_close_at_neither_end_says_so_once(qapp):
    """Both sides open reads as one statement, not as two ends and two changes that are not numbers."""
    from gui.plotting.labels import fmt_interval_html, fmt_value

    w = _widget(_fit(), _profile_set(interval=_interval(1e-8, 1e12, open_low=True, open_high=True)))
    text = w._summary.text()

    assert f'95% CI {fmt_interval_html(fmt_value(1e-8), fmt_value(1e12), True, True)}' in text
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

    assert 'cannot be solved past 1.00×10¹²' in text
    assert 'reaches the bound of' not in text


def test_a_side_resting_on_the_other_constants_bound_names_it_and_gives_no_data_advice(qapp):
    """Where only the other constant's bound rejects the fit, more titration points would not close the side."""
    from dataclasses import replace

    interval = replace(_interval(2.3e3, 1e9, open_low=True), limited_by_low='Ka_HG2')
    w = _widget(_fit(), _profile_set(interval=interval))
    text = w._summary.text()

    assert 'rejected beyond 2.30×10³' in text and 'cannot go past its bound' in text
    assert 'reaches the bound of' not in text
    assert 'higher titrant concentration' not in text


def test_an_estimate_on_its_search_bound_is_the_limit_the_data_set_and_no_percentage_of_it(qapp):
    """A Ka the search stopped at the bound of its box is the box: no view reads it as an estimate.

    The interval's closed end is what the data say — Ka lies below it — and a
    percentage of the bound (+24 135 990 455 885 %) would describe the box.
    """
    from dataclasses import replace

    fit = _fit()
    fit = replace(fit, parameters={**fit.parameters, 'Ka_guest': Q_(1e-8, '1/M')})
    profile_set = _profile_set(interval=_interval(1e-8, 2413.6, open_low=True))
    profile = profile_set.profiles['Ka_guest']
    profile.best_ka = 1e-8
    w = _widget(fit, profile_set)
    text = w._summary.text()

    assert '<i>not limited below</i> 2.41×10³ M<sup>−1</sup>' in text
    assert '95% CI [<i>no lower limit</i>, 2.41×10³] M<sup>−1</sup>' in text
    assert 'upper end' not in text and '%)' not in text
    # The bound is named once, as the bound the open side reaches.
    assert text.count('10⁻⁸') == 1 and 'It reaches the bound of 1.00×10⁻⁸' in text


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
    assert items['cut'].opts['pen'].style() == Qt.PenStyle.DotLine
    assert np.all(items['cut'].getData()[1] == CUT_R2)
    axis = items['main'].getAxis('right')
    assert axis.isVisible()
    assert axis._tickLevels == [[(CUT_R2, 'cut-off 0.9900')]]
    assert items['cut'].zValue() < items['average'].zValue() < items['best'].zValue()


def test_the_cut_off_line_steps_where_the_profile_says_a_signal_parameter_reaches_its_bound(qapp):
    """One level per profile point, stepping midway between two points; the axis names the level nothing is held at."""
    profile_set = _profile_set()
    profile = profile_set.profiles['Ka_guest']
    held = profile.grid < 10**8.2
    profile.r2_cut = np.where(held, CUT_R2 - 0.004, CUT_R2)
    w = _widget(_fit(), profile_set)
    items = w._items['Ka_guest']
    steps, levels = items['cut'].getData()
    np.testing.assert_array_equal(levels, profile.r2_cut)
    assert items['cut'].opts['stepMode'] == 'center' and steps.size == levels.size + 1
    log_grid = np.log10(profile.grid)
    last_held = int(np.flatnonzero(held)[-1])
    assert steps[last_held + 1] == pytest.approx(0.5 * (log_grid[last_held] + log_grid[last_held + 1]))
    assert (steps[0], steps[-1]) == (log_grid[0], log_grid[-1])
    # Two levels are drawn and the axis names one of them in plain words; what
    # the step is, is said in the legend and in the axis's hover text.
    axis = items['main'].getAxis('right')
    assert axis._tickLevels == [[(CUT_R2, 'cut-off 0.9900')]]
    assert 'steps down' in axis.toolTip()
    assert 'lower where a signal parameter sits on its bound' in w._legend.text().replace('&nbsp;', ' ')


def test_a_cut_off_at_one_level_names_no_step(qapp):
    w = _widget(_fit(), _profile_set())
    axis = w._items['Ka_guest']['main'].getAxis('right')

    assert axis._tickLevels == [[(CUT_R2, 'cut-off 0.9900')]]
    assert 'steps down' not in axis.toolTip()
    assert 'bound' not in w._legend.text()


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


def test_default_view_holds_every_step_of_the_cut_off_inside_its_ka_span(qapp):
    """A step three level spans below the constant cut-off is framed where it is in view, and only there."""
    profile_set = _profile_set()
    profile = profile_set.profiles['Ka_guest']
    span = PEAK_R2 - CUT_R2
    profile.r2_cut = np.where(profile.grid < 10**8.2, CUT_R2 - 3 * span, CUT_R2)
    (x_lo, _), (y_lo, y_hi) = _widget(_fit(), profile_set)._items['Ka_guest']['main'].viewRange()
    assert x_lo < 8.2 and y_lo < CUT_R2 - 3 * span < PEAK_R2 < y_hi

    # The same step at Ka the default view does not show leaves the view on the peak and the constant cut-off.
    profile.r2_cut = np.where(profile.grid < 10**6.0, CUT_R2 - 3 * span, CUT_R2)
    _, y_range = _widget(_fit(), profile_set)._items['Ka_guest']['main'].viewRange()
    assert y_range == pytest.approx((0.985, 0.998))


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


def test_a_chart_too_wide_for_the_tab_does_not_take_the_text_with_it(qapp):
    """Only the chart scrolls sideways: a sentence a reader has to scroll to finish is not readable.

    The text is laid out under a page as wide as the chart, so it has to be held
    to the tab's width and given the height that width needs — with no room
    taken from the widget below it. A tab narrower than one panel is the case
    where even panels standing one per row are wider than the page.
    """
    w = _widget(*_set_for(AssayType.DBA_HG2), 'DBA_HG2')
    w.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    w.resize(320, 700)
    w.show()
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
    w.close()


# ---------------------------------------------------------------------------
# Input uncertainties: the second curve, the conditional line, the verdict
# ---------------------------------------------------------------------------


def _aware_set(**kwargs):
    """A one-Ka ProfileSet whose profile also carries its input-aware twin."""
    return _profile_set(aware=_aware_profile(), **kwargs)


def test_stated_input_uncertainties_draw_a_second_curve_with_its_own_band_and_cut_off(qapp):
    """The headline band and cut-off are the input-aware ones; the conditional interval stays underneath."""
    profile_set = _aware_set()
    aware = profile_set.profiles['Ka_guest'].aware
    w = _widget(_fit(), profile_set)
    items = w._items['Ka_guest']

    np.testing.assert_allclose(items['aware'].getData()[0], np.log10(aware.grid))
    np.testing.assert_array_equal(items['aware'].getData()[1], aware.r2)
    # Two lines on one R² axis are told apart by colour, and both are drawn smooth.
    assert items['aware'].opts['pen'].color() != items['average'].opts['pen'].color()
    assert items['aware'].opts['antialias']
    assert items['aware_band'].getRegion() == pytest.approx((7.8, 9.4))
    assert np.all(items['aware_cut'].getData()[1] == AWARE_CUT)
    assert items['cut'] is None  # one cut-off is drawn: the one the headline band is cut at
    axis = items['main'].getAxis('right')
    assert axis._tickLevels == [[(AWARE_CUT, f'cut-off {AWARE_CUT:.4f}')]]
    # The conditional interval is still on screen, fainter and underneath.
    assert items['band'].getRegion() == pytest.approx((8.0, 9.0))
    assert items['band'].zValue() < items['aware_band'].zValue()
    assert items['band'].brush.color().alpha() < items['aware_band'].brush.color().alpha()
    legend = w._legend.text().replace('&nbsp;', ' ')
    assert 'with input uncertainties' in legend and 'at the entered inputs' in legend


def test_the_input_aware_estimate_is_marked_beside_the_conditional_one(qapp):
    """Two curves, two estimates: each peak carries the marker of its own curve, in its own colour."""
    w = _widget(_fit(), _aware_set())
    items = w._items['Ka_guest']

    assert items['best'].getData()[0][0] == pytest.approx(np.log10(BEST_KA))
    assert items['best'].getData()[1][0] == pytest.approx(PEAK_R2)
    assert items['aware_best'].getData()[0][0] == pytest.approx(AWARE_CENTRE)
    assert items['aware_best'].getData()[1][0] == pytest.approx(AWARE_PEAK)
    assert items['aware_best'].opts['brush'].color() == items['aware'].opts['pen'].color()


def test_without_stated_uncertainties_there_is_one_curve_and_no_conditional_line(qapp):
    """Nothing varying: the tab is s2's — one curve, one band, one cut-off, no second reading to explain."""
    w = _widget(_fit(), _profile_set())
    items = w._items['Ka_guest']

    assert (items['aware'], items['aware_band'], items['aware_cut'], items['aware_best']) == (None,) * 4
    assert np.all(items['cut'].getData()[1] == CUT_R2)
    assert 'with input uncertainties' not in w._legend.text().replace('&nbsp;', ' ')
    assert 'Conditional on the entered inputs' not in w._summary.text()


def test_the_headline_interval_is_the_input_aware_one_and_the_conditional_one_follows(qapp):
    """Both readings are on screen, the input-aware one first: it is what the fit reports."""
    from gui.plotting.labels import fmt_interval_html, fmt_value

    w = _widget(_fit(), _aware_set())
    text = w._summary.text()

    headline = f'95% CI {fmt_interval_html(fmt_value(10**7.8), fmt_value(10**9.4), False, False)} M<sup>−1</sup>'
    conditional = f'95% CI {fmt_interval_html(fmt_value(1e8), fmt_value(1e9), False, False)} M<sup>−1</sup>'
    assert text.index(headline) < text.index('Conditional on the entered inputs') < text.index(conditional)
    # Each reading is quoted with the estimate it belongs to.
    assert text.index(fmt_value(10**AWARE_CENTRE)) < text.index(fmt_value(BEST_KA))
    # The widening is what usually happens, not what always happens.
    assert 'usually' in text


def test_an_input_aware_side_the_data_leave_open_says_so_and_names_its_edge(qapp):
    """The open-side reading follows the headline interval, while the conditional one is closed at both ends."""
    from gui.plotting.labels import fmt_value

    aware = _aware_profile(interval=_interval(10**7.8, 1e12, open_high=True))
    w = _widget(_fit(), _profile_set(aware=aware))
    text = w._summary.text()

    assert text.count('Open: the data cannot rule out') == 1
    assert 'a higher K<sub>a</sub>' in text
    assert f'It reaches the bound of {fmt_value(1e12)}' in text
    assert 'no upper limit' in text


def test_the_default_view_frames_both_peaks_and_the_cut_off(qapp):
    """Four levels now decide the reading — two peaks and two cut-offs — and the view holds all of them."""
    w = _widget(_fit(), _aware_set())
    (x_lo, x_hi), (y_lo, y_hi) = w._items['Ka_guest']['main'].viewRange()

    span = AWARE_PEAK - CUT_R2  # the lowest and the highest of the four levels
    # Upwards the view stops a tenth of a span above R² = 1, short of the 0.6
    # spans over the highest level it would take on a curve further from 1.
    assert (y_lo, y_hi) == pytest.approx((CUT_R2 - span, 1.0 + 0.1 * span))
    assert y_lo < CUT_R2 < AWARE_CUT < PEAK_R2 < AWARE_PEAK < y_hi
    # Across: both intervals and both estimates, with a fifth of that span on either side.
    assert (x_lo, x_hi) == pytest.approx((7.8 - 0.32, 9.4 + 0.32))


def test_the_verdict_on_the_model_and_the_inputs_is_shown_under_the_intervals(qapp):
    """What the fit found out about the model and the entered inputs is reported here too, in the panel's words."""
    from gui.plotting.labels import verdict_sentence

    shifts = {'h0': InputShift(key='h0', fraction=-0.041, z=-1.4, at_edge=False)}
    diagnostics = FitDiagnostics(
        conditional_misfit=MisfitTest(kind='runs', statistic=4.0, p_value=0.004, expected=7.0),
        misfit=MisfitTest(kind='runs', statistic=7.0, p_value=0.55, expected=7.0),
        conflict=Conflict(q=1.9, k=1, p_value=0.17, weights=(0.9,)),
        verdict=Verdict.INPUTS_EXPLAIN,
    )
    labels = {'h0': '[Host]₀'}  # the plain name an IDA fit's host concentration is reported by
    w = _widget(_fit(diagnostics=diagnostics, shifts=shifts), _aware_set())
    text = w._summary.text()

    sentence = verdict_sentence(diagnostics, shifts, labels, html=True)
    assert sentence in text
    assert text.index('Conditional on the entered inputs') < text.index(sentence)
    assert '[Host]₀ −4.1 % (1.4 σ)' in text
    # A result that carries no verdict — one read from a file written before the
    # fit tested its inputs — says nothing about the model instead of inventing it.
    untested = _widget(_fit(), _aware_set())
    silent = untested._summary.text()
    assert text.startswith(silent) and len(text) > len(silent)


def test_the_verdict_names_a_shared_source_with_the_inputs_it_moves(qapp):
    """The shift is against the source, so the tab has to say which inputs that source moved."""
    from core.pipeline.inputs import ErrorModel, SharedSource, shared_key

    key = shared_key('Host and dye stock')
    shifts = {key: InputShift(key=key, fraction=-0.041, z=-1.4, at_edge=False)}
    diagnostics = FitDiagnostics(
        conditional_misfit=MisfitTest(kind='runs', statistic=4.0, p_value=0.004, expected=7.0),
        misfit=MisfitTest(kind='runs', statistic=7.0, p_value=0.55, expected=7.0),
        conflict=Conflict(q=1.9, k=1, p_value=0.17, weights=(0.9,)),
        verdict=Verdict.INPUTS_EXPLAIN,
    )
    fit = _fit(diagnostics=diagnostics, shifts=shifts)
    fit.fit_config.update(ErrorModel(shared=(SharedSource('Host and dye stock', 4.0, ('h0', 'd0')),)).to_dict())

    w = _widget(fit, _aware_set())

    assert 'Host and dye stock (shared by [Host]₀, [Dye]₀) −4.1 % (1.4 σ)' in w._summary.text()


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
    assert '[3.16×10⁵, 3.16×10⁶]' in summary and '[3.16×10³, 3.16×10⁴]' in summary

    region = profile_set.region
    inside = np.isfinite(region.r2) & (region.r2 >= region.r2_cut)
    assert not inside[0, 0]  # the pair the model has no solution for is out, whatever its R² compares as
    # Each pair is judged against the cut-off of its own fit: where that steps down, pairs
    # below the first level are in the region.
    assert np.any(inside & (region.r2 < region.r2_threshold))
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


def test_two_binding_constants_with_input_uncertainties_draw_both_curves_over_a_conditional_region(qapp):
    """Each constant gets its two curves; the pair region is the one at the inputs as entered, and says so."""
    plain = _widget(_fit(keys=HG2_KEYS, assay='DBA_HG2'), _two_ka_set(), 'DBA_HG2')
    assert plain._region_items['main'].titleLabel.text == ''

    w = _widget(_fit(keys=HG2_KEYS, assay='DBA_HG2'), _two_ka_set(aware=True), 'DBA_HG2')

    for key, centre in (('Ka_HG', 6.1), ('Ka_HG2', 4.1)):
        items = w._items[key]
        assert items['aware'] is not None and items['aware_band'] is not None and items['cut'] is None
        assert items['aware_best'].getData()[0][0] == pytest.approx(centre)
    assert 'entered inputs' in w._region_items['main'].titleLabel.text
    # The bands behind the region are the two conditional intervals it is drawn with.
    edges = ((5.5, 6.5), (3.5, 4.5))
    assert all(band.getRegion() == pytest.approx(r) for band, r in zip(w._region_items['bands'], edges))
    assert 'entered inputs' in w._notes.text()
    assert w._summary.text().count('Conditional on the entered inputs') == 2


def test_one_binding_constant_has_no_region_panel(qapp):
    w = _widget(_fit(), _profile_set())
    assert w._region_items == {}


def test_what_every_interval_rests_on_is_said_once_for_the_fit(qapp):
    """The counts and the bounds hold for the whole fit; repeating them per binding constant buries the numbers."""
    w = _widget(_fit(keys=HG2_KEYS, assay='DBA_HG2'), _two_ka_set(aware=True), 'DBA_HG2')
    text = w._summary.text()

    assert text.count('parameter bounds this fit was given') == 1
    assert text.count('12 data points') == 1 and text.count('3 fitted parameters') == 1
    assert text.count('free to move within the uncertainty you stated') == 1
    # Each constant still carries its own estimate and both of its intervals.
    assert text.count('Conditional on the entered inputs') == 2
    # And the shared line comes after them, not between a constant and its interval.
    assert text.index('K<sub>a(HG₂)</sub>') < text.index('12 data points')


def test_the_pair_panel_drops_below_the_others_where_the_three_do_not_fit_side_by_side(qapp):
    """At 1440x900 the three panels do not fit across the tab, and the pair is the one that falls off the edge.

    Below the other two it is in view whole — title, axes and all — and the
    page no longer scrolls sideways over it.
    """
    from gui.plotting.identifiability_widget import _MAIN_MIN_HEIGHT, _MAIN_MIN_WIDTH

    w = _widget(_fit(keys=HG2_KEYS, assay='DBA_HG2'), _two_ka_set(aware=True), 'DBA_HG2')
    w.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    w.resize(1560, 720)  # room enough for the three side by side
    w.show()
    for _ in range(8):
        qapp.processEvents()
    assert w._arrangement == 'row'

    w.resize(1044, 573)  # the Identifiability tab of a 1440x900 window
    for _ in range(10):
        qapp.processEvents()

    assert w._arrangement == 'pair_below'
    assert w._content.horizontalScrollBar().maximum() == 0
    region = w._region_items['main']
    box = region.getViewBox()
    assert box.width() >= _MAIN_MIN_WIDTH and box.height() >= _MAIN_MIN_HEIGHT
    assert region.titleLabel.isVisible() and 'entered inputs' in region.titleLabel.text
    # Below both Ka panels, and inside the page rather than past its right edge.
    pair = region.mapRectToScene(region.boundingRect())
    for items in w._items.values():
        assert items['main'].mapRectToScene(items['main'].boundingRect()).bottom() <= pair.top()
        assert items['main'].getViewBox().width() >= _MAIN_MIN_WIDTH
    assert pair.right() <= w._glw.width()

    w.resize(1560, 720)
    for _ in range(10):
        qapp.processEvents()
    assert w._arrangement == 'row'  # back beside them once there is room again
    w.close()


@pytest.mark.parametrize('size', [(933, 546), (1044, 573)], ids=['native-1440x900', 'offscreen-1440x900'])
def test_the_joint_region_is_in_view_without_scrolling_sideways_in_a_laptop_window(qapp, size):
    """The Identifiability tab of a 1440×900 window, measured on the native style and offscreen.

    Every panel is in the page's width — the pair included — and no axis label,
    cut-off label or legend entry is cut off.
    """
    from gui.plotting.identifiability_widget import _MAIN_MIN_WIDTH

    w = _widget(_fit(keys=HG2_KEYS, assay='DBA_HG2'), _two_ka_set(aware=True), 'DBA_HG2')
    w.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    w.resize(*size)
    w.show()
    for _ in range(10):
        qapp.processEvents()

    assert w._content.horizontalScrollBar().maximum() == 0
    region = w._region_items['main']
    pair = region.mapRectToScene(region.boundingRect())
    assert pair.right() <= w._glw.width()
    assert region.getViewBox().width() >= _MAIN_MIN_WIDTH
    for plot in [items['main'] for items in w._items.values()] + [region]:
        for name in ('left', 'bottom', 'right'):
            axis = plot.getAxis(name)
            if not axis.isVisible():
                continue
            box = axis.mapRectToScene(axis.boundingRect())
            assert box.left() >= 0 and box.right() <= w._glw.width() + 0.5, (name, box)
        label = plot.getAxis('bottom').label
        assert label.isVisible() and label.mapRectToScene(label.boundingRect()).bottom() <= w._glw.height()
    legend = w._legend
    assert legend.heightForWidth(legend.width()) <= legend.height()
    w.close()


def test_a_tab_too_narrow_for_two_panels_stands_every_panel_on_a_row_of_its_own(qapp):
    """Where even the two Ka panels do not fit side by side, each takes a row, and nothing scrolls sideways."""
    from gui.plotting.identifiability_widget import _MAIN_MIN_HEIGHT, _MAIN_MIN_WIDTH

    w = _widget(_fit(keys=HG2_KEYS, assay='DBA_HG2'), _two_ka_set(), 'DBA_HG2')
    w.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    w.resize(738, 406)  # the Identifiability tab of an 1100x700 window
    w.show()
    for _ in range(10):
        qapp.processEvents()

    assert w._arrangement == 'column'
    assert w._content.horizontalScrollBar().maximum() == 0
    plots = [items['main'] for items in w._items.values()] + [w._region_items['main']]
    boxes = [plot.mapRectToScene(plot.boundingRect()) for plot in plots]
    for upper, lower in zip(boxes, boxes[1:]):
        assert upper.bottom() <= lower.top()
    for plot in plots:
        assert plot.getViewBox().width() >= _MAIN_MIN_WIDTH and plot.getViewBox().height() >= _MAIN_MIN_HEIGHT
    w.close()


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


def test_the_cloud_is_drawn_on_the_scale_the_profiles_are_drawn_on(qapp):
    """A sample scored on another scale would sit above or below the curve for no reason the reader can see."""
    sens = _sensitivity()
    w = _widget(_fit(), _profile_set())
    w.update_sensitivity(sens)
    drawn = w._items['Ka_guest']['samples'].getData()[1]
    kept = np.isfinite(sens.sample_profile_r2)

    assert np.allclose(drawn, sens.sample_profile_r2[kept])
    assert not np.allclose(drawn, sens.sample_r2[kept])


# ---------------------------------------------------------------------------
# Which R² the page is showing
# ---------------------------------------------------------------------------


def _r2_names(w):
    """Every place this page names its vertical scale, with the legend's hard spaces read as spaces."""
    places = {
        'axis': w._items['Ka_guest']['main'].getAxis('left').labelText,
        'caption': w._summary.text(),
        'legend': w._legend.text(),
        'tooltip': w.toolTip(),
        'note': w._notes.text(),
    }
    return {place: text.replace('&nbsp;', ' ') for place, text in places.items()}


@pytest.mark.parametrize('weighted', [False, True])
def test_every_place_the_page_names_its_scale_says_which_r2_it_is(qapp, weighted):
    """The axis, the caption, the legend, the hover text and the hidden-samples note are one name.

    A page that calls the weighted profile R² on the axis and the unweighted one
    in the caption invites the reader to compare two different numbers.
    """
    from gui.plotting.identifiability_widget import _WEIGHTED_R2_NOTE

    w = _widget(_fit(), _profile_set(weighted=weighted))
    w.update_sensitivity(_sensitivity())
    named = _r2_names(w)

    assert '1 of 21 sensitivity samples not shown' in named['note']
    for place, text in named.items():
        # The one sentence that explains the two names is the one place both
        # appear; everywhere else the page names its own scale and no other.
        text = text.replace(_WEIGHTED_R2_NOTE, '')
        if weighted:
            assert 'weighted R²' in text, place
            assert 'R²' not in text.replace('weighted R²', ''), place
        else:
            assert 'R²' in text, place
            assert 'weighted' not in text, place


def test_the_caption_says_what_the_weighted_r2_means_only_where_the_page_shows_one(qapp):
    """One plain sentence, so a reader comparing it with Fit Quality knows why the two differ."""
    from gui.plotting.identifiability_widget import _WEIGHTED_R2_NOTE

    weighted = _widget(_fit(), _profile_set(weighted=True))
    unweighted = _widget(_fit(), _profile_set())

    assert _WEIGHTED_R2_NOTE in weighted._summary.text()
    assert _WEIGHTED_R2_NOTE not in unweighted._summary.text()


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


def test_renders_a_real_input_aware_fit_beside_its_conditional_one(qapp):
    """Two replicates of the synthetic IDA truth, the host stated to 5 %: the tab shows the fit's own working.

    The marked estimate is the Ka the fit reports, the quoted intervals are the
    two the fit made, and the drawn input-aware curve lies above the
    conditional one at every Ka — a fit free to move the host within its
    uncertainty can always leave it where it was entered.
    """
    from core.assays.ida import IDAAssay
    from core.data_processing.measurement_set import MeasurementSet
    from core.pipeline.fit_pipeline import FitConfig, fit_measurement_set
    from core.pipeline.inputs import ErrorModel, InputSpec
    from core.pipeline.profile import fit_profile
    from gui.plotting.labels import fmt_value, verdict_sentence
    from gui.widgets.assay_conditions import result_input_labels
    from tests.conftest import IDA_TRUE, _make_ida_data

    rng = np.random.default_rng(0)
    x, y = _make_ida_data(IDA_TRUE, n_points=14)
    ms = MeasurementSet(
        concentrations=x,
        signals=np.vstack([y * (1 + 0.01 * rng.standard_normal(y.size)) for _ in range(2)]),
        replica_ids=('A', 'B'),
    )
    conditions = {
        'Ka_dye': Q_(IDA_TRUE['Ka_dye'], '1/M'),
        'h0': Q_(IDA_TRUE['h0'], 'M'),
        'd0': Q_(IDA_TRUE['d0'], 'M'),
    }
    config = FitConfig(per_replica=False, errors=ErrorModel(specs={'h0': InputSpec.sigma_pct(5.0)}))
    fit = fit_measurement_set(ms, IDAAssay, conditions, config)
    profile_set = fit_profile(ms, IDAAssay, conditions, config, **fit.profile_arguments())
    profile = profile_set.profiles['Ka_guest']

    w = _widget(fit, profile_set)
    items = w._items['Ka_guest']

    reported = fit.parameters['Ka_guest'].to('1/M').magnitude
    assert items['aware_best'].getData()[0][0] == pytest.approx(np.log10(reported), abs=1e-6)
    assert items['best'].getData()[0][0] == pytest.approx(np.log10(profile.best_ka))
    # Freeing the host cannot fit worse than leaving it as entered.
    aware_x, aware_y = items['aware'].getData()
    conditional = np.interp(aware_x, *items['average'].getData())
    assert np.all(aware_y >= conditional - 1e-9)
    # Both readings quoted are the fit's own.
    text = w._summary.text()
    headline, entered = fit.intervals['Ka_guest'], fit.conditional.intervals['Ka_guest']
    head, _, conditional_line = text.partition('Conditional on the entered inputs')
    assert f'95% CI [{fmt_value(headline.low)}, {fmt_value(headline.high)}]' in head
    assert f'95% CI [{fmt_value(entered.low)}, {fmt_value(entered.high)}]' in conditional_line
    # The verdict this fit reached on the model and the inputs is here too.
    # Named from the fit's own assay, which is where the tab takes its names from.
    labels = result_input_labels(fit.assay_type, fit.fit_config)
    assert verdict_sentence(fit.diagnostics, fit.input_shifts, labels, html=True) in conditional_line


def test_a_stated_error_of_the_additions_draws_the_reported_interval_on_the_same_curve(qapp):
    """No input moves, so the reported reading is the one curve under the wider cut-off the additions imply."""
    from core.assays.ida import IDAAssay
    from core.data_processing.measurement_set import MeasurementSet
    from core.pipeline.fit_pipeline import FitConfig, fit_measurement_set
    from core.pipeline.inputs import AdditionError, ErrorModel
    from core.pipeline.profile import fit_profile
    from gui.plotting.labels import fmt_value
    from tests.conftest import IDA_TRUE, _make_ida_data

    x, y = _make_ida_data(IDA_TRUE, n_points=15)
    signal = y + np.random.default_rng(2).normal(0.0, 0.002 * np.ptp(y), y.size)
    ms = MeasurementSet(concentrations=x, signals=signal[np.newaxis], replica_ids=('A',))
    conditions = {
        'Ka_dye': Q_(IDA_TRUE['Ka_dye'], '1/M'),
        'h0': Q_(IDA_TRUE['h0'], 'M'),
        'd0': Q_(IDA_TRUE['d0'], 'M'),
    }
    config = FitConfig(per_replica=False, errors=ErrorModel(additions=AdditionError(3.0, sequential=True)))
    fit = fit_measurement_set(ms, IDAAssay, conditions, config)
    profile_set = fit_profile(ms, IDAAssay, conditions, config, **fit.profile_arguments())
    profile = profile_set.profiles['Ka_guest']

    assert profile.interval == fit.conditional.intervals['Ka_guest']
    assert profile.aware.interval == fit.intervals['Ka_guest']
    np.testing.assert_array_equal(profile.aware.r2, profile.r2)
    w = _widget(fit, profile_set)
    text = ' '.join(w._summary.text().split())
    reported = fit.intervals['Ka_guest']
    assert f'95% CI [{fmt_value(reported.low)}, {fmt_value(reported.high)}]' in text
    assert 'The reported interval allows for the random error of each addition you stated' in text
    assert 'free to move' not in text
    assert 'Without the error of the additions:' in text
    # One curve and one best fit, not the same curve drawn twice under two names.
    items = w._items['Ka_guest']
    assert items['aware'] is None and items['aware_best'] is None
    legend = w._legend.text().replace('&nbsp;', ' ')
    assert 'CI without the error of the additions' in legend
    assert 'confidence interval with the error of the additions' in legend
    assert 'with the inputs as entered' not in legend


def test_renders_a_real_ida_fit_and_its_profile(qapp):
    """The IDA demo data: the drawn curve is the profile's own, and the header quotes its interval."""
    from core.assays.ida import IDAAssay
    from core.data_processing.measurement_set import MeasurementSet
    from core.io import load_measurements
    from core.pipeline.fit_pipeline import FitConfig, fit_measurement_set
    from core.pipeline.profile import fit_profile
    from gui.plotting.labels import fmt_value

    ms = MeasurementSet.from_dataframe(load_measurements('data/IDA_system.txt'))
    conditions = {'Ka_dye': Q_(16.8e6, '1/M'), 'h0': Q_(4.3e-6, 'M'), 'd0': Q_(6e-6, 'M')}
    config = FitConfig(per_replica=False)
    fit = fit_measurement_set(ms, IDAAssay, conditions, config)
    profile_set = fit_profile(ms, IDAAssay, conditions, config, **fit.profile_arguments())
    profile = profile_set.profiles['Ka_guest']

    w = _widget(fit, profile_set)
    items = w._items['Ka_guest']
    assert len(items['average'].getData()[0]) == profile.grid.size
    assert items['best'].getData()[0][0] == pytest.approx(np.log10(profile.best_ka))
    interval = profile.interval
    assert f'95% CI [{fmt_value(interval.low)}, {fmt_value(interval.high)}]' in w._summary.text()


def _filtered_demo():
    """Demo IDA as the guide describes it: the bundled data through Outlier Removal at its defaults."""
    from core.data_processing.measurement_set import MeasurementSet
    from core.data_processing.preprocessing import get_step
    from core.io import load_measurements

    ms = MeasurementSet.from_dataframe(load_measurements('data/IDA_system.txt'))
    get_step('zscore_replica_filter', {'threshold': 3.5, 'min_replicas': 3})(ms)
    conditions = {'Ka_dye': Q_(16.8e6, '1/M'), 'h0': Q_(4.3e-6, 'M'), 'd0': Q_(6e-6, 'M')}
    return ms, conditions


def test_a_cut_off_below_the_plain_f_tests_says_why(qapp):
    """The replicates of the demo leave their noise law uncertain, and the tab says what that does to the cut-off.

    The plain F test's cut-off follows from the counts the tab quotes alone:
    ``R²_cut = 1 - (1 - R²_best)(1 + F(1, n - p)/(n - p))``. Where the drawn
    cut-off lies below it, the counts no longer explain it, and the reader is
    told why and by how much.
    """
    from scipy.stats import f as f_dist

    from core.assays.ida import IDAAssay
    from core.pipeline.fit_pipeline import FitConfig, fit_measurement_set
    from core.pipeline.profile import fit_profile

    ms, conditions = _filtered_demo()
    config = FitConfig(per_replica=False)
    fit = fit_measurement_set(ms, IDAAssay, conditions, config)
    profile_set = fit_profile(ms, IDAAssay, conditions, config, **fit.profile_arguments())
    profile = profile_set.profiles['Ka_guest']
    dof = profile.n_points - profile.n_params
    plain = 1.0 - (1.0 - profile.best_r2) * (1.0 + f_dist.ppf(0.95, 1, dof) / dof)
    assert profile.r2_threshold < plain - 1e-6, 'the demo no longer widens its cut-off: pick data that do'

    w = _widget(fit, profile_set)
    text = ' '.join(w._summary.text().split())
    assert 'leave the noise law uncertain' in text
    assert 'times what the scatter of the data alone implies' in text


@pytest.mark.parametrize('sequential, wider', [(True, False), (False, True)])
def test_the_error_of_the_additions_is_called_wider_only_where_the_interval_is(qapp, sequential, wider):
    """A stated error of each addition is allowed for in the interval; the tab says *widen* only where it is wider.

    With the noise law already widening the cut-off, the additions take over
    part of the scatter the law carries, and the interval allowing for both
    need not be the wider one: on the demo, 3 % sequential additions on
    repeated reads of one titration leave it narrower than the interval
    without them, 3 % separate samples make it wider. The tab makes no
    comparison the two intervals themselves do not bear out.
    """
    from core.assays.ida import IDAAssay
    from core.pipeline.fit_pipeline import FitConfig, fit_measurement_set
    from core.pipeline.inputs import AdditionError, ErrorModel
    from core.pipeline.profile import fit_profile

    ms, conditions = _filtered_demo()
    additions = AdditionError(3.0, sequential=sequential, separate_titrations=False)
    config = FitConfig(per_replica=False, errors=ErrorModel(additions=additions))
    fit = fit_measurement_set(ms, IDAAssay, conditions, config)
    profile_set = fit_profile(ms, IDAAssay, conditions, config, **fit.profile_arguments())
    profile = profile_set.profiles['Ka_guest']
    reported, without = profile.aware.interval, profile.interval
    assert (reported.high / reported.low > without.high / without.low) is wider, 'pick additions that do'

    w = _widget(fit, profile_set)
    text = ' '.join(w._summary.text().split())
    assert 'The reported interval allows for the random error of each addition you stated' in text
    assert ('widen' in text) is wider
    if not wider:
        assert 'allows for the random error of each addition (3 %, sequential' in text
        assert 'of the noise law alone, since part of the scatter is put down to the additions' in text


def _two_ka_set_with_second(interval: KaInterval):
    """:func:`_two_ka_set` with the second constant's interval at the entered inputs replaced by *interval*."""
    from dataclasses import replace

    profile_set = _two_ka_set()
    profiles = dict(profile_set.profiles)
    profiles['Ka_HG2'] = replace(profiles['Ka_HG2'], interval=interval)
    return replace(profile_set, profiles=profiles)


def test_a_second_step_the_data_do_not_show_reads_as_not_limited_below_and_why(qapp):
    """The lower side is open because the one-step model fits nearly as well, not because the profile ran out.

    So the line gives that reason and not the advice to measure at a higher
    titrant concentration, nor the bound the side runs to as if the data reached it.
    """
    from dataclasses import replace

    opened = replace(_interval(1e-8, 10**4.5, open_low=True), one_step_p=0.03)
    w = _widget(_fit(keys=HG2_KEYS, assay='DBA_HG2'), _two_ka_set_with_second(opened), 'DBA_HG2')
    text = w._summary.text()

    assert (
        'not limited below: a model without the second binding step fits nearly as well (one-step test p = 0.03).'
    ) in text
    assert 'cannot rule out a lower' not in text
    assert 'It reaches the bound of 1.00×10⁻⁸' not in text


def test_a_second_step_the_data_support_says_at_what_p_the_one_step_model_was_rejected(qapp):
    from dataclasses import replace

    closed = replace(_interval(10**3.5, 10**4.5), one_step_p=2e-5)
    w = _widget(_fit(keys=HG2_KEYS, assay='DBA_HG2'), _two_ka_set_with_second(closed), 'DBA_HG2')
    text = w._summary.text()

    assert 'second binding step supported (one-step model rejected at p ≤ 0.001).' in text
    # The first constant has no such test, so it is said once.
    assert text.count('one-step') == 1


def test_with_inputs_free_the_one_step_test_at_the_entered_inputs_is_said_beside_the_headline_s(qapp):
    """The joint region is drawn at the entered inputs, so their one-step test is on the tab as well as the headline's.

    The two tests can disagree (the inputs may explain part of what the
    second step did), and each sentence says which interval it belongs to.
    """
    from dataclasses import replace

    from gui.plotting.labels import fmt_param

    profile_set = _two_ka_set(aware=True)
    profiles = dict(profile_set.profiles)
    second = profiles['Ka_HG2']
    profiles['Ka_HG2'] = replace(
        second,
        interval=replace(_interval(1e-8, 10**4.5, open_low=True), one_step_p=0.03),
        aware=replace(second.aware, interval=replace(second.aware.interval, one_step_p=2e-5)),
    )
    w = _widget(_fit(keys=HG2_KEYS, assay='DBA_HG2'), replace(profile_set, profiles=profiles), 'DBA_HG2')
    text = w._summary.text()

    assert 'second binding step supported (one-step model rejected at p ≤ 0.001).' in text
    assert (
        f'At the entered inputs, {fmt_param("Ka_HG2")} not limited below: a model without the second binding step '
        'fits nearly as well (one-step test p = 0.03).'
    ) in text
    assert text.count('one-step') == 2
