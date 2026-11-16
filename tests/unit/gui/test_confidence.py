"""What Ka confidence states and draws of a fit and its Ka profile, checked without a widget (:mod:`gui.confidence`).

Readings, notes and callouts are checked on hand-built fits, against numbers written in
the test. The curves are checked on real profiles — the bundled IDA demo at the inputs as
entered, and a small input-aware fit — against the property that defines them: the scaled
drop is an exact rescaling of each reading's own test, so the drawn curve meets the
cut-off line at 1 where the reported interval ends. A split interval with a stepped cut-off,
which only a model with two binding constants produces, is checked on a profile written out
in the test.
"""

from __future__ import annotations

import math
from dataclasses import replace

import numpy as np
import pytest

pytest.importorskip('PyQt6')

from core.pipeline.diagnostics import FitDiagnostics, InputShift  # noqa: E402
from core.pipeline.profile import JointRegion, ProfileResult, ProfileSet  # noqa: E402
from core.pipeline.varpro import KaInterval  # noqa: E402
from core.units import Q_  # noqa: E402
from gui import confidence as CF  # noqa: E402
from gui import results as R  # noqa: E402
from gui.plotting.labels import THIN  # noqa: E402
from tests.unit.gui.test_results import _CONFLICT, _stepwise, aware_result, per_replica_result, result  # noqa: E402

#: Width of a profile plot's data area in the default 1440 × 900 window, in px.
PLOT_PX = 760


def _crossings(curve: CF.Curve) -> np.ndarray:
    """log₁₀ Ka where the drawn polyline of *curve* crosses 1, read off its points independently."""
    out = []
    for x0, x1, y0, y1 in zip(curve.x[:-1], curve.x[1:], curve.y[:-1], curve.y[1:]):
        if np.all(np.isfinite([x0, x1, y0, y1])) and (y0 - 1.0) * (y1 - 1.0) <= 0 and y0 != y1:
            out.append(x0 + (1.0 - y0) * (x1 - x0) / (y1 - y0))
    return np.array(out)


def _pixel(plot: CF.ProfilePlot) -> float:
    return (plot.x_range[1] - plot.x_range[0]) / PLOT_PX


# ---------------------------------------------------------------------------
# The readings
# ---------------------------------------------------------------------------


@pytest.fixture(scope='module')
def stepped():
    """A fit at the inputs as entered whose interval is split by a step of the cut-off, and its profile.

    R² falls as ``0.5 (t - 6)²`` below 0.99 with ``t = log10 Ka``. The plain test allows a fall of
    0.045, so it accepts ``t`` from 5.7 to 6.3; below ``t = 5.5`` the fit holds a signal parameter
    on its bound and the test allows four times that fall, so it accepts ``t`` from 5.4 to 5.5 too.
    """
    t = np.round(np.linspace(4.0, 8.0, 401), 2)
    top, threshold, lowered = 0.99, 0.99 - 0.5 * 0.09, 0.99 - 0.5 * 0.36
    interval = KaInterval(10**5.4, 10**6.3, False, False, 0.95, 16, split=True)
    profile = ProfileResult(
        'Ka_guest', 10.0**t, top - 0.5 * (t - 6.0) ** 2, 1e6, top, interval, threshold, 20, 4, False,
        r2_cut=np.where(t < 5.5, lowered, threshold),
    )  # fmt: skip
    fit = result(parameters={**result().parameters, 'Ka_guest': Q_(1e6, '1/M')}, intervals={'Ka_guest': interval})
    return fit, ProfileSet({'Ka_guest': profile}, None)


def test_moved_inputs_give_input_aware_beside_inputs_as_entered_with_one_power_of_ten():
    (header,) = CF.headers(aware_result())
    aware, entered = header.readings

    assert (aware.label, aware.tone, aware.reported) == ('Input-aware', 'accent', True)
    assert (entered.label, entered.tone, entered.reported) == ('Inputs as entered', 'neutral', False)
    assert (aware.value, aware.interval) == (f'1.30{THIN}×{THIN}10⁶', f'0.500 – 3.00{THIN}×{THIN}10⁶ M⁻¹')
    assert (entered.value, entered.interval) == (f'1.24{THIN}×{THIN}10⁶', f'0.700 – 2.20{THIN}×{THIN}10⁶ M⁻¹')
    # 0.5 / 1.3 and 3.0 / 1.3 of the best fit, whole percent with a real minus sign.
    assert aware.reach == f'−62{THIN}% / +131{THIN}% of the best fit'


def test_a_fit_of_exact_inputs_has_the_one_reading_as_entered():
    (header,) = CF.headers(result())

    assert [(r.label, r.tone) for r in header.readings] == [('Inputs as entered', 'neutral')]


def test_an_estimate_on_its_search_bound_reads_not_limited_below_and_no_percentage_of_it():
    from core.units import Q_

    weak = result(
        assay_type='DBA_HtoD',
        parameters={
            'Ka_dye': Q_(1e-8, '1/M'),
            'I0': Q_(100.0, 'au'),
            'I_dye_free': Q_(5e4, 'au/M'),
            'I_dye_bound': Q_(2.37e19, 'au/M'),
        },
        intervals={'Ka_dye': KaInterval(1e-8, 2413.6, True, False, 0.95, 16)},
    )
    ((reading,),) = [h.readings for h in CF.headers(weak)]

    assert (reading.qualifier, reading.value) == ('Not limited below', f'2.41{THIN}×{THIN}10³')
    assert reading.reach == '' and '10⁻⁸' not in reading.interval


def test_a_drop_close_to_minus_100_percent_is_not_rounded_to_it():
    """−100 % would read as a Ka of zero."""
    assert CF.reach(1.0, '', (0.004, 2.0), (False, False)) == f'−99.6{THIN}% / +100{THIN}% of the best fit'
    assert CF.reach(1.0, '', (0.5, 2.0), (False, True)) == f'lower end −50{THIN}% of the best fit'


# ---------------------------------------------------------------------------
# The curves
# ---------------------------------------------------------------------------


def test_the_drawn_curve_meets_the_cut_off_line_where_the_reported_interval_ends(demo):
    """Exact rescaling: every closed edge is a crossing of 1 by the drawn line, within a pixel at the default size."""
    fit, profile = demo
    plot = CF.profile_plot(fit, profile.profiles['Ka_guest'])
    (entered,) = plot.curves
    interval = fit.intervals['Ka_guest']

    crossings = _crossings(entered)
    for edge in (interval.low, interval.high):
        assert np.min(np.abs(crossings - math.log10(edge))) < _pixel(plot)
    assert entered.estimate == (math.log10(fit.parameters['Ka_guest'].magnitude), 0.0)
    # The view frames both ends and the estimate, with room either side to see the curve leave the line.
    assert plot.x_range[0] < math.log10(interval.low) and math.log10(interval.high) < plot.x_range[1]


def test_a_split_interval_draws_its_stretches_and_the_step_of_the_cut_off_as_a_riser(stepped):
    """Below the step the fit holds a signal parameter on its bound, the test allows a larger drop and the curve
    steps down."""
    fit, profile = stepped
    plot = CF.profile_plot(fit, profile.profiles['Ka_guest'])
    (entered,) = plot.curves
    interval = fit.intervals['Ka_guest']

    assert interval.split and len(entered.stretches) == 2
    (first, second) = entered.stretches
    assert first[0] == interval.low and second[1] == interval.high and first[1] < second[0]
    # The curve breaks at the step and a riser carries it across, from above the line down to below it.
    assert plot.stepped and np.isnan(entered.y).sum() == len(entered.risers) >= 1
    assert any(y0 < 1.0 < y1 or y1 < 1.0 < y0 for _x, y0, y1 in entered.risers)
    # Every drawn point inside a stretch is at or under the line, every one between them over it.
    finite = np.isfinite(entered.x)
    ka = 10.0 ** entered.x[finite]
    y = entered.y[finite]
    gap = (ka > first[1]) & (ka < second[0])
    assert np.all(y[gap] > 1.0)
    for lo, hi in entered.stretches:
        assert np.all(y[(ka >= lo) & (ka <= hi)] <= 1.0 + 1e-6)


def test_the_readout_reads_each_curve_as_drawn_and_judges_it_by_its_stretches(stepped):
    fit, profile = stepped
    plot = CF.profile_plot(fit, profile.profiles['Ka_guest'])
    (entered,) = plot.curves
    (first, second) = entered.stretches
    in_gap = math.log10(math.sqrt(first[1] * second[0]))
    inside = math.log10(fit.parameters['Ka_guest'].magnitude)

    (gap_row,) = CF.readout(plot, in_gap)
    (best_row,) = CF.readout(plot, inside)

    assert (gap_row.label, gap_row.verdict) == ('Inputs as entered', 'rejected') and float(gap_row.value) > 1.0
    assert (best_row.verdict, best_row.value) == ('accepted', '0.00')
    assert plot.readout_title(inside).startswith('Scaled drop at ') and plot.readout_title(inside).endswith('M⁻¹')


def test_the_input_aware_curve_is_drawn_through_its_edges_on_its_own_scale():
    """A small input-aware fit: its penalised profile, as drawn, crosses 1 within a pixel of each reported edge."""
    from tests.unit.test_input_aware import _IDA_SIGMAS, _aware, _ida

    assay, projection = _ida(15, 0.01, 2)
    fit, aware = _aware(assay, projection, _IDA_SIGMAS)
    profile = aware.profiles['Ka_guest']
    interval = profile.interval
    drawn = CF.curve('Input-aware', 'accent', profile, aware.fit.ka['Ka_guest'], '', (interval.low, interval.high))

    pixel = max(math.log10(interval.high / interval.low) * (1 + 2 * CF.X_PAD), CF.MIN_SPAN) / PLOT_PX
    crossings = _crossings(drawn)
    for edge in (interval.low, interval.high):
        assert np.min(np.abs(crossings - math.log10(edge))) < pixel
    assert drawn.stretches == [(interval.low, interval.high)]


def _bump_profile(interval: KaInterval | None) -> ProfileResult:
    grid = np.logspace(4, 8, 81)
    r2 = 0.99 * np.exp(-((np.log10(grid) - 6.0) ** 2))
    return ProfileResult('Ka_guest', grid, r2, 1e6, 0.99, interval, 0.98, 12, 3, False)


def test_a_constant_its_bounds_fix_has_no_profile_plot():
    fit = result(intervals={})

    assert CF.profile_plot(fit, _bump_profile(None)) is None


# ---------------------------------------------------------------------------
# The joint region
# ---------------------------------------------------------------------------


def test_the_joint_region_is_the_pairs_at_or_over_their_own_cut_off_with_the_best_fit_and_both_bands():
    x, y = np.geomspace(1e5, 1e7, 16), np.geomspace(1e3, 1e5, 12)
    lx, ly = np.log10(x)[:, None], np.log10(y)[None, :]
    r2 = 1.0 - 0.01 * ((lx - 6.0) ** 2 + (ly - 4.0) ** 2)
    r2[0, 0] = np.nan  # a pair the model has no solution for
    cut = np.full(r2.shape, 0.99)
    cut[:5] = 0.98  # where the fits hold a signal parameter on its bound
    intervals = {'Ka_HG': KaInterval(10**5.5, 10**6.5, False, False, 0.95, 9), 'Ka_HG2': None}
    region = JointRegion(('Ka_HG', 'Ka_HG2'), x, y, r2, 0.99, 0.95, (1e6, 1e4), cut, 1.0, intervals)

    class Profiles:
        pass

    profiles = Profiles()
    profiles.region = region
    fit = _stepwise(KaInterval(1.1e3, 8.0e3, False, False, 0.95, 16))
    drawn = CF.joint_region(fit, profiles)

    assert np.array_equal(drawn.accepted, np.isfinite(r2) & (r2 >= cut)) and not drawn.accepted[0, 0]
    assert drawn.accepted[:5].sum() > 0 and drawn.best == (6.0, 4.0)
    # The cells are centred on the grid: the map reaches half a cell past its first and last values.
    half = 0.5 * (np.log10(x[1]) - np.log10(x[0]))
    assert drawn.extent[0] == pytest.approx(5.0 - half) and drawn.extent[1] == pytest.approx(7.0 + half)
    assert drawn.bands == [('x', 5.5, 6.5)]
    # Two decades share no power of ten: each tick is written in full and the title states the unit alone.
    assert drawn.x_title == 'Kₐ HG (M⁻¹, log scale)' and drawn.description == ''


# ---------------------------------------------------------------------------
# Callouts and notes
# ---------------------------------------------------------------------------


def _conflicted():
    shifts = {
        'h0': InputShift('h0', -0.114, -3.8, False),
        '__titrant__': InputShift('__titrant__', 0.093, 3.1, False),
    }
    return aware_result(shifts=shifts, diagnostics=_CONFLICT)


def test_the_conflict_callout_opens_the_shifts_here_and_a_hidden_fit_says_only_why():
    (conflict,) = CF.callouts(_conflicted(), None)
    hidden = CF.callouts(_conflicted(), 'Replicate B is now off.')

    assert (conflict.title, conflict.action) == ('Inputs conflict', CF.SHOW_SHIFTS)
    assert [(c.tone, c.body) for c in hidden] == [('neutral', 'Replicate B is now off.')]
    assert CF.callouts(_conflicted(), None, pending=True)[-1].body == CF.PENDING


def test_the_conflict_note_lists_where_the_correction_went_and_names_no_input_as_its_cause():
    (section, *_rest) = CF.notes(_conflicted())

    assert (section.title, section.flag, section.trailing) == ('Inputs conflict', True, 'p < 0.001')
    assert [row.name for row in section.shifts] == ['[Host]₀', 'Guest (titrant, whole series)']
    note = section.paragraphs[1]
    # Two inputs, both seen by the data (k = 2): the statistic weighs them together.
    assert note.startswith('The statistic weighs them together, so it does not say which of them is off.')
    assert note.endswith('The interval assumes the shifts are real.')
    assert '[Host]' not in note and 'Guest' not in note


def test_moved_inputs_without_a_conflict_list_their_shifts_unflagged():
    fit = aware_result(diagnostics=FitDiagnostics(None, None, None, aware_result().diagnostics.verdict))
    (section, *_rest) = CF.notes(fit)

    assert (section.title, section.flag, [r.name for r in section.shifts]) == ('Input shifts', False, ['[Host]₀'])


def _titles(fit, profile=None) -> dict[str, list[str]]:
    return {s.title: s.paragraphs for s in CF.notes(fit, profile)}


def test_an_open_side_says_what_it_stops_at_and_what_would_close_it():
    bound = _stepwise(KaInterval(1.1e3, 8.0e3, False, True, 0.95, 16))
    unsolvable = _stepwise(KaInterval(1.1e3, 8.0e3, False, True, 0.95, 16, unsolvable_high=True))
    limited = _stepwise(KaInterval(1.1e3, 8.0e3, False, True, 0.95, 16, limited_by_high='Ka_HG'))

    (text,) = _titles(bound)['Open sides']
    assert text.startswith('Kₐ HG₂: the data cannot rule out a higher value. It reaches the bound of 8.00')
    assert text.endswith('or a lower fixed concentration, would pin it down.')
    (text,) = _titles(unsolvable)['Open sides']
    assert 'cannot be solved past' in text and 'pin it down' not in text
    (text,) = _titles(limited)['Open sides']
    assert 'only because Kₐ HG cannot go past its bound' in text and 'pin it down' not in text


def test_the_second_step_is_said_either_way_and_a_lower_side_it_opened_is_not_called_a_reach_of_the_data():
    unshown = _stepwise(KaInterval(1e-8, 9.0e3, True, False, 0.95, 16, one_step_p=0.03))
    supported = _stepwise(KaInterval(1.1e3, 8.0e3, False, False, 0.95, 16, one_step_p=1e-5))

    notes = _titles(unshown)
    assert 'Open sides' not in notes
    assert notes['Second binding step'][0] == (
        'Kₐ HG₂ not limited below: a model without the second binding step fits nearly as well '
        '(one-step test p = 0.03).'
    )
    assert _titles(supported)['Second binding step'][0] == (
        'Kₐ HG₂: second binding step supported (one-step model rejected at p ≤ 0.001).'
    )
    assert f'p ≤ {CF.SECOND_STEP_LEVEL:g}' in notes['Second binding step'][-1]


def test_replicates_the_fit_left_out_are_named_with_what_the_intervals_rest_on():
    rest = _titles(per_replica_result(excluded=('3',)))['What the intervals rest on']

    assert 'Replicate 3 is left out here, as it was from the fit.' in rest
    assert rest[0].startswith('Every input was taken as entered.')
    assert rest[0].endswith('No interval reaches further than the parameter bounds this fit was given.')


def test_a_split_interval_names_the_ka_it_rejects_between_its_stretches(stepped):
    fit, profile = stepped
    (first, second) = CF.profile_plot(fit, profile.profiles['Ka_guest']).curves[0].stretches

    split = _titles(fit, profile)['Split interval']

    gap = f'from {R.fmt_value(first[1])} to {R.fmt_value(second[0])} M⁻¹ is rejected.'
    assert split[0].startswith('Inputs as entered: the range ') and split[0].endswith(gap)
    assert split[-1] == CF.split_explained(drawn=True) and 'strip under the plot' in split[-1]


def test_a_split_interval_without_a_profile_names_no_plot_or_strip(stepped):
    """While the profile is computed, after it failed, or for an imported fit, no plot or strip is drawn."""
    fit, _profile = stepped

    split = ' '.join(_titles(fit)['Split interval'])

    assert 'has a gap.' in split and 'plot' not in split and 'strip' not in split


def test_the_badge_is_a_neutral_summary_of_the_method_and_level():
    assert CF.badge(result()) == f'Profile likelihood · 95{THIN}%'
    assert CF.badge(None) is None
    assert CF.badge(replace(result(), assay_type='DYE_ALONE', intervals={})) is None


# ---------------------------------------------------------------------------
# What a reading states where the fit records no interval
# ---------------------------------------------------------------------------


def test_a_result_that_records_no_interval_says_so_as_fit_results_does():
    """A file written before intervals were recorded: no interval, no profile-likelihood badge, never 'fixed'."""
    fit = result(intervals=None)
    ((reading,),) = [h.readings for h in CF.headers(fit)]
    (block,) = R.ka_blocks(fit)

    assert (reading.interval, reading.tooltip) == (block.interval, R.LEGACY_NOTE)
    assert 'fixed' not in reading.interval and reading.reach == ''
    assert CF.badge(fit) is None


def test_a_ka_its_bounds_fix_is_said_to_be_fixed_and_quotes_no_interval():
    ((reading,),) = [h.readings for h in CF.headers(result(intervals={}))]

    assert reading.interval == 'fixed, not fitted'
    assert reading.reach == '' and '–' not in reading.interval and '%' not in reading.interval


def test_an_interval_no_data_can_close_says_so_on_hover():
    unsolvable = KaInterval(0.7e6, 2.2e6, False, True, 0.95, 16, unsolvable_high=True)
    ((reading,),) = [h.readings for h in CF.headers(result(intervals={'Ka_guest': unsolvable}))]

    assert R.UNSOLVABLE_NOTE[1:] in reading.tooltip


# ---------------------------------------------------------------------------
# The Input-aware curve beside Inputs as entered
# ---------------------------------------------------------------------------


def test_the_input_aware_curve_is_drawn_beside_inputs_as_entered_with_its_own_estimate_and_interval():
    """A real penalised profile: drawn as the second curve, crossing 1 at the reported edges, marked at its own estimate."""
    from core.pipeline.fit_pipeline import ConditionalFit
    from core.units import Q_
    from tests.unit.test_input_aware import _IDA_SIGMAS, _aware, _ida

    assay, projection = _ida(15, 0.01, 2)
    _fit, aware = _aware(assay, projection, _IDA_SIGMAS)
    own = aware.profiles['Ka_guest']
    reported = own.interval
    estimate = aware.fit.ka['Ka_guest']
    # Inputs as entered: a narrower reading of its own, centred away from the Input-aware estimate.
    entered_estimate = 1.5 * estimate
    centre = math.log10(entered_estimate)
    entered = KaInterval(10 ** (centre - 0.1), 10 ** (centre + 0.1), False, False, 0.95, 16)
    grid = np.logspace(centre - 2, centre + 2, 161)
    conditional = ProfileResult(
        'Ka_guest', grid, 0.99 * np.exp(-((np.log10(grid) - centre) ** 2)), entered_estimate, 0.99,
        entered, 0.98, 15, 3, False, aware=own,
    )  # fmt: skip
    base = aware_result()
    fit = replace(
        base,
        parameters={**base.parameters, 'Ka_guest': Q_(estimate, '1/M')},
        intervals={'Ka_guest': reported},
        conditional=ConditionalFit(
            parameters={**base.parameters, 'Ka_guest': Q_(entered_estimate, '1/M')},
            intervals={'Ka_guest': entered},
            rmse=0.006,
            r_squared=0.997,
        ),
    )

    plot = CF.profile_plot(fit, conditional)
    as_entered, input_aware = plot.curves

    assert (as_entered.label, input_aware.label) == (R.AS_ENTERED, R.INPUT_AWARE)
    assert input_aware.color == 'accent' and as_entered.color == 'text-secondary'
    crossings = _crossings(input_aware)
    for edge in (reported.low, reported.high):
        assert np.min(np.abs(crossings - math.log10(edge))) < _pixel(plot)
    assert input_aware.estimate == (math.log10(estimate), 0.0)
    assert as_entered.estimate == (math.log10(entered_estimate), 0.0)
    assert input_aware.stretches == [(reported.low, reported.high)]
    assert plot.band == (math.log10(reported.low), math.log10(reported.high))
    # The view frames both readings.
    assert plot.x_range[0] < math.log10(min(reported.low, entered.low))
    assert math.log10(max(reported.high, entered.high)) < plot.x_range[1]


# ---------------------------------------------------------------------------
# What Notes says of the inputs, the curves and what the intervals rest on
# ---------------------------------------------------------------------------


def test_moved_inputs_whose_test_could_not_run_say_they_were_not_tested_and_why():
    """A test that could not run never reads as one that passed, however far an input moved."""
    from gui.plotting.labels import NOT_RUN

    skipped = FitDiagnostics(
        aware_result().diagnostics.conditional_misfit,
        aware_result().diagnostics.misfit,
        None,
        aware_result().diagnostics.verdict,
        skipped={'conflict': 'no_informed_direction'},
    )
    fit = aware_result(shifts={'h0': InputShift('h0', -0.078, -2.6, False)}, diagnostics=skipped)
    (section, *_rest) = CF.notes(fit)
    text = ' '.join(section.paragraphs)

    assert section.title == 'Input shifts' and not section.flag
    assert 'not tested against what you stated' in text and NOT_RUN[('conflict', 'no_informed_direction')] in text
    assert 'inside what you stated' not in text
    no_diagnostics = ' '.join(CF.notes(replace(fit, diagnostics=None))[0].paragraphs)
    # A results file that records no diagnostics says nothing of whether the test ran.
    assert 'is not recorded in this result' in no_diagnostics and 'not tested' not in no_diagnostics
    assert 'inside what you stated' not in no_diagnostics


def test_moved_inputs_the_test_did_not_reject_quote_the_test_not_a_bound():
    """A σ is not a bound: an input at 1.8 σ is not 'inside what you stated', the joint test is what was judged."""
    from core.pipeline.diagnostics import Conflict

    base = aware_result().diagnostics
    passed = FitDiagnostics(base.conditional_misfit, base.misfit, Conflict(3.1, 1, 0.08, (1.0,)), base.verdict)
    fit = aware_result(shifts={'h0': InputShift('h0', -0.054, -1.8, False)}, diagnostics=passed)
    (section, *_rest) = CF.notes(fit)
    text = ' '.join(section.paragraphs)

    assert section.title == 'Input shifts' and section.trailing == 'p = 0.08'
    assert 'p = 0.08' in text and 'inside what you stated' not in text


def test_a_conflict_lists_as_its_correction_only_the_inputs_it_judged():
    """An input stated as a range is said to have moved inside its range, not listed as part of the correction."""
    shifts = {
        'h0': InputShift('h0', -0.114, -3.8, False),
        '__titrant__': InputShift('__titrant__', 0.093, 3.1, False),
        'd0': InputShift('d0', 0.02, None, False),
    }
    (section, *_rest) = CF.notes(aware_result(shifts=shifts, diagnostics=_CONFLICT))

    assert [row.name for row in section.shifts] == ['[Host]₀', 'Guest (titrant, whole series)']
    assert all(row.z is not None for row in section.shifts)
    assert '[Dye]₀' in section.paragraphs[1] and 'range' in section.paragraphs[1]


def test_without_a_profile_notes_describe_no_curve_and_no_count_they_do_not_have():
    """While the profile is computed, after it failed, or for an imported fit, the canvas has no plot."""
    rest = _titles(result())['What the intervals rest on']

    assert 'Reading the curves' not in _titles(result())
    assert rest[0] == (
        'Every input was taken as entered. No interval reaches further than the parameter bounds this fit was given.'
    )


def test_a_stated_error_of_the_additions_names_no_curve_without_a_profile(demo):
    """With no input free the reported interval is the entered curve's under a wider cut-off: said only where drawn."""
    fit, profile = demo
    additions = {**fit.fit_config, 'titrant_additions': {'sigma_pct': 1.0, 'sequential': False}}
    stated = replace(fit, fit_config=additions, input_shifts=None)

    assert 'curve' not in _titles(stated)['What the intervals rest on'][0]
    assert 'on the same curve' in _titles(stated, profile)['What the intervals rest on'][0]


def test_with_a_profile_notes_say_how_many_points_and_parameters_the_intervals_rest_on(demo):
    fit, profile = demo
    first = next(iter(profile.profiles.values()))
    notes = _titles(fit, profile)

    assert (
        f'from {first.n_points} data points and {first.n_params} fitted parameters.'
        in notes['What the intervals rest on'][0]
    )
    assert notes['Reading the curves'][-1] == 'Point at the plot to read every curve at any Kₐ.'


def test_with_inputs_free_each_reading_says_its_own_one_step_test_and_open_side():
    """Input-aware supports the second step; at the entered inputs it is not shown and that reading is open below."""
    from core.pipeline.fit_pipeline import ConditionalFit

    supported = KaInterval(1.1e3, 8.0e3, False, False, 0.95, 16, one_step_p=2e-5)
    unshown = KaInterval(1e-8, 9.0e3, True, False, 0.95, 16, one_step_p=0.03)
    base = _stepwise(supported)
    fit = replace(
        base,
        input_shifts={'h0': InputShift('h0', -0.02, -0.7, False)},
        conditional=ConditionalFit(
            parameters=base.parameters,
            intervals={'Ka_HG': base.intervals['Ka_HG'], 'Ka_HG2': unshown},
            rmse=0.006,
            r_squared=0.997,
        ),
    )

    steps = _titles(fit)['Second binding step']

    assert steps[0] == 'Input-aware: Kₐ HG₂: second binding step supported (one-step model rejected at p ≤ 0.001).'
    assert steps[1] == (
        'Inputs as entered: Kₐ HG₂ not limited below: a model without the second binding step fits nearly as well '
        '(one-step test p = 0.03).'
    )


def test_an_open_lower_side_asks_for_points_at_a_higher_titrant_concentration():
    """A weak binding the data cannot bound below is seen only where more titrant is added."""
    (text,) = _titles(_stepwise(KaInterval(1.1e3, 8.0e3, True, False, 0.95, 16)))['Open sides']

    assert text.startswith('Kₐ HG₂: the data cannot rule out a lower value. It reaches the bound of 1.10')
    assert text.endswith('Points at a higher titrant concentration would pin it down.')
