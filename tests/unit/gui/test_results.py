"""What Fit results states of a fit, checked without a widget (:mod:`gui.results`).

Every fixture is a hand-built :class:`FitResult`, so what the view would show is
checked against numbers written in the test rather than against whatever a fit
happened to produce.
"""

from __future__ import annotations

import math
import re
from dataclasses import replace

import numpy as np
import pytest

pytest.importorskip('PyQt6')

from core.assays.registry import AssayType  # noqa: E402
from core.data_processing.measurement_set import MeasurementSet  # noqa: E402
from core.pipeline.diagnostics import Conflict, FitDiagnostics, InputShift, MisfitTest, Verdict  # noqa: E402
from core.pipeline.fit_pipeline import ConditionalFit, FitResult  # noqa: E402
from core.pipeline.varpro import KaInterval  # noqa: E402
from core.units import Q_  # noqa: E402
from gui import results as R  # noqa: E402

THIN = ' '


def result(**overrides) -> FitResult:
    """A GDA fit of one signal: Ka with a closed interval, the signal parameters without one."""
    x = np.linspace(0, 1e-4, 20)
    fields = dict(
        parameters={
            'Ka_guest': Q_(1.24e6, '1/M'),
            'I0': Q_(100.0, 'au'),
            'I_dye_free': Q_(5e4, 'au/M'),
            'I_dye_bound': Q_(8e4, 'au/M'),
        },
        rmse=0.005,
        r_squared=0.998,
        x_fit=Q_(x, 'M'),
        y_fit=Q_(x * 1.05 + 0.01, 'au'),
        assay_type='GDA',
        model_name='equilibrium_4param',
        fit_config={'per_replicate': False, 'level': 0.95},
        intervals={'Ka_guest': KaInterval(0.7e6, 2.2e6, False, False, 0.95, 16)},
    )
    fields.update(overrides)
    return FitResult(**fields)


def aware_result(*, shifts=None, diagnostics=None, uncertainty=None, **overrides) -> FitResult:
    """An IDA fit whose entered inputs were free to move, with its conditional fit beside it."""
    shifts = {'h0': InputShift('h0', -0.041, -1.4, False)} if shifts is None else shifts
    diagnostics = diagnostics or FitDiagnostics(
        conditional_misfit=MisfitTest('lack_of_fit', 0.9, 0.55, dof=(9, 72)),
        misfit=MisfitTest('lack_of_fit', 0.8, 0.62, dof=(9, 72)),
        conflict=None,
        verdict=Verdict.CONSISTENT,
    )
    base = result(
        assay_type='IDA',
        parameters={
            'Ka_guest': Q_(1.30e6, '1/M'),
            'I0': Q_(100.0, 'au'),
            'I_dye_free': Q_(5e4, 'au/M'),
            'I_dye_bound': Q_(8e4, 'au/M'),
        },
        intervals={'Ka_guest': KaInterval(0.5e6, 3.0e6, False, False, 0.95, 16)},
        fit_config={
            'per_replicate': False,
            'level': 0.95,
            'input_uncertainty': {'h0': {'kind': 'sigma', 'sigma': 3.0, 'lo': 0.0, 'hi': 0.0, 'relative': True}}
            if uncertainty is None
            else uncertainty,
        },
        conditions={'h0': Q_(4.3e-6, 'M'), 'd0': Q_(6e-6, 'M'), 'Ka_dye': Q_(1.68e7, '1/M')},
        input_shifts=shifts,
        diagnostics=diagnostics,
        **overrides,
    )
    return replace(
        base,
        conditional=ConditionalFit(
            parameters={**base.parameters, 'Ka_guest': Q_(1.24e6, '1/M')},
            intervals={'Ka_guest': KaInterval(0.7e6, 2.2e6, False, False, 0.95, 16)},
            rmse=0.006,
            r_squared=0.997,
        ),
    )


def per_replica_result(p_values=None, excluded=(), ka_by_replicate=None) -> FitResult:
    """A per-replicate GDA fit of four replicates, each with its own fit."""
    ka_by_replicate = ka_by_replicate or {'0': 1.0e6, '1': 1.2e6, '2': 1.4e6, '3': 9.0e6}
    given = ['0', '1', '2', '3']
    used = [rid for rid in given if rid not in excluded]
    base = result(fit_config={'per_replicate': True, 'level': 0.95})
    replica_fits = [
        replace(
            base,
            parameters={**base.parameters, 'Ka_guest': Q_(ka_by_replicate[rid], '1/M')},
            r_squared=0.99 + 0.001 * i,
            intervals=None,
            metadata={'replica_id': rid, 'active_replica_ids': [rid]},
        )
        for i, rid in enumerate(given)
    ]
    metadata = {'active_replica_ids': given, 'replica_ids_fit': used}
    if excluded:
        metadata['replica_failures'] = {rid: f'Replicate {rid} needs a different Ka.' for rid in excluded}
    if p_values:
        metadata['replicate_test'] = {'level': 0.01, 'p_values': p_values}
    return replace(base, replica_fits=replica_fits, metadata=metadata)


def four_replicates() -> MeasurementSet:
    """Four replicates A–D whose levels differ, so a mean over a subset is distinguishable."""
    conc = np.linspace(1e-6, 1e-5, 8)
    signals = np.stack([1e4 * (1 + 0.2 * i) * conc / (conc + 3e-6) for i in range(4)])
    return MeasurementSet(concentrations=conc, signals=signals, replica_ids=('0', '1', '2', '3'))


def fit_on(ms: MeasurementSet, left_out=(), **overrides) -> FitResult:
    """A fit given the active replicates of *ms* that left out *left_out*, its curve through the middle of the data."""
    given = ms.active_replica_ids
    used = [rid for rid in given if rid not in left_out]
    x = np.linspace(ms.concentrations[0], ms.concentrations[-1], 60)
    fields = dict(
        x_fit=Q_(x, 'M'),
        y_fit=Q_(1.3e4 * x / (x + 3e-6), 'au'),
        metadata={'active_replica_ids': given, 'replica_ids_fit': used},
    )
    return result(**{**fields, **overrides})


# ---------------------------------------------------------------------------
# The headline
# ---------------------------------------------------------------------------


def test_the_headline_states_the_estimate_and_its_interval_with_one_power_of_ten():
    """1.24×10⁶ [0.7×10⁶, 2.2×10⁶], written as the design writes a headline: thin spaces, one shared exponent."""
    (block,) = R.ka_blocks(result())

    assert block.name == 'K<sub>a</sub> guest'
    assert block.value == f'1.24{THIN}×{THIN}10⁶'
    assert block.interval == f'0.700 – 2.20{THIN}×{THIN}10⁶ M⁻¹'
    assert block.level == f'95{THIN}% interval'


@pytest.mark.parametrize(
    ('open_low', 'open_high', 'expected'),
    [(False, True, 'no upper limit'), (True, False, 'no lower limit'), (True, True, 'not limited by the data')],
    ids=['upper-open', 'lower-open', 'both-open'],
)
def test_an_open_side_is_written_in_words_not_as_the_bound_the_search_stopped_at(open_low, open_high, expected):
    """A side the data do not close has no limit to show; printing the bound would claim one."""
    (block,) = R.ka_blocks(result(intervals={'Ka_guest': KaInterval(1e-8, 1e12, open_low, open_high, 0.95, 16)}))

    assert expected in block.interval
    assert ('10¹²' in block.interval) == (not open_high)
    assert ('10⁻⁸' in block.interval) == (not open_low)


def test_an_open_side_runs_to_the_edge_of_an_axis_spanning_what_is_written():
    """The search box ends twenty decades out; an axis reaching it would squeeze the closed end into a point."""
    (block,) = R.ka_blocks(result(intervals={'Ka_guest': KaInterval(1e-8, 2.2e6, True, False, 0.95, 16)}))
    ((low, high),) = block.rows[0]['segments']

    assert math.log10(block.hi / block.lo) < 2
    assert low == block.lo and high == 2.2e6  # the open side is drawn to the axis's edge
    assert len(block.ticks) <= 6


def test_an_estimate_on_its_search_bound_is_written_as_the_limit_the_data_set():
    """The 1e-8 the search stopped at is the box, not a Ka; the headline says what the data do limit."""
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
    (block,) = R.ka_blocks(weak)
    cells, _tips, _note = R.parameter_rows(weak)

    assert (block.qualifier, block.value) == ('Not limited below', f'2.41{THIN}×{THIN}10³')
    assert block.rows[0]['est'] is None  # no mark for an estimate that is no number
    # In the Parameters table the words stand on a line above the number, which keeps its line.
    assert cells[0][1] == f'<i>not limited below</i><br>2.41{THIN}×{THIN}10³'
    assert all('10⁻⁸' not in text for text in (block.value, block.interval, cells[0][1]))


def test_a_binding_constant_held_fixed_has_no_interval_and_says_why():
    (block,) = R.ka_blocks(result(intervals={}))

    assert block.interval == 'fixed, not fitted'
    assert block.rows == []


def test_a_file_written_before_intervals_says_so_and_shows_none():
    """An imported legacy fit keeps its parameters; claiming an interval it never carried would be a fabrication."""
    legacy = result(intervals=None)
    (block,) = R.ka_blocks(legacy)

    assert block.interval == 'not recorded in this result'
    # What to do about it is said on screen under Parameters, not only on hover of the interval.
    assert R.LEGACY_NOTE in R.parameter_notes(legacy)
    assert R.LEGACY_NOTE not in R.parameter_notes(result())


def test_a_dye_alone_calibration_has_no_headline_constant_no_notes_and_no_noise_stat():
    x = np.linspace(0, 1e-4, 5)
    line = FitResult(
        parameters={'slope': Q_(1.5, 'au/M'), 'intercept': Q_(0.2, 'au')},
        rmse=0.01,
        r_squared=0.99,
        x_fit=Q_(x, 'M'),
        y_fit=Q_(x * 1.5, 'au'),
        assay_type='DYE_ALONE',
        model_name='linear',
    )

    assert R.ka_blocks(line) == []
    assert R.parameter_notes(line) == []
    assert R.quality(line, None).noise is None
    assert len(R.parameter_rows(line)[0]) == 2


def test_a_fit_of_exact_inputs_reports_one_reading_as_entered():
    """With every input exact the conditional fit is the headline, so the chart has one row and its badge says so."""
    fit = result()
    (block,) = R.ka_blocks(fit)

    assert R.reading(fit) == ('Inputs as entered', 'neutral')
    assert [row['label'] for row in block.rows] == ['Inputs as entered']
    assert block.rows[0]['color'] == 'text-secondary'


def test_a_fit_with_moved_inputs_reports_input_aware_beside_the_inputs_as_entered():
    fit = aware_result()
    (block,) = R.ka_blocks(fit)

    assert R.reading(fit) == ('Input-aware', 'accent')
    assert [(row['label'], row['color']) for row in block.rows] == [
        ('Input-aware', 'accent'),
        ('Inputs as entered', 'text-secondary'),
    ]
    # The headline is the Input-aware fit; the conditional one stands beside it.
    assert block.value == f'1.30{THIN}×{THIN}10⁶'
    assert block.rows[0]['text'] == '1.30  [0.500, 3.00]'
    assert block.rows[1]['text'] == '1.24  [0.700, 2.20]'
    assert block.axis_unit == f'×{THIN}10⁶ M⁻¹'


def test_a_stated_error_of_the_additions_alone_reports_input_aware_with_its_wider_interval():
    """No input moves, but the reported interval widens, so both readings are shown."""
    from core.pipeline.inputs import AdditionError, ErrorModel

    plain = result()
    entered = ConditionalFit(dict(plain.parameters), dict(plain.intervals), plain.rmse, plain.r_squared)
    fit = result(
        intervals={'Ka_guest': KaInterval(0.4e6, 3.1e6, False, False, 0.95, 16, inflation=3.2)},
        conditional=entered,
        fit_config={
            'per_replicate': False,
            'level': 0.95,
            **ErrorModel(additions=AdditionError(2.0, sequential=True)).to_dict(),
        },
    )
    (block,) = R.ka_blocks(fit)

    assert R.reading(fit)[0] == 'Input-aware'
    assert len(block.rows) == 2
    # What widened it is said where the interval is, on the headline's interval line.
    assert block.tooltip.startswith('Random error of each addition (2 %')
    assert R.interval_caption(fit, [block]).startswith('The random error of each addition you stated widens')


def test_a_split_interval_carries_the_split_badge_its_stretches_and_a_note():
    """A split interval's bracket spans rejected Ka; the chart draws the accepted stretches and the badge says Split."""

    class Curve:  # a profile whose accepted values come in two stretches
        grid = np.geomspace(1e5, 1e7, 41)
        r2 = np.where((grid < 5e5) | (grid > 2e6), 0.99, 0.5)
        r2_cut = np.full(grid.size, 0.9)

    class Profile:
        profiles = {'Ka_guest': Curve()}

    fit = result(intervals={'Ka_guest': KaInterval(1e5, 1e7, False, False, 0.95, 16, split=True)})
    (drawn,) = R.ka_blocks(fit, Profile())
    (pending,) = R.ka_blocks(fit, None, profile_running=True)

    row = drawn.rows[0]
    assert row['badge'] == 'Split'
    assert len(row['segments']) == 2
    assert row['segments'][0][1] < 5e5 < 2e6 < row['segments'][1][0]
    # What Split means is said on the chart that carries the badge.
    assert 'separate stretches' in drawn.chart_tooltip and drawn.chart_tooltip == R.SPLIT_FOOTNOTE
    assert 'separate stretches' not in drawn.tooltip
    assert pending.rows[0]['segments'] == [] and 'once the Kₐ profile is ready' in pending.rows[0]['note']


def test_an_open_side_no_more_data_could_close_says_so():
    closable = result(intervals={'Ka_guest': KaInterval(1e5, 1e12, False, True, 0.95, 16)})
    unsolvable = result(intervals={'Ka_guest': KaInterval(1e5, 1e12, False, True, 0.95, 16, unsolvable_high=True)})

    assert R.ka_blocks(closable)[0].tooltip == ''
    assert 'more measurements cannot close it' in R.ka_blocks(unsolvable)[0].tooltip


def _stepwise(second):
    return result(
        parameters={
            'Ka_HG': Q_(2.0e5, '1/M'),
            'Ka_HG2': Q_(3.0e3, '1/M'),
            'I0': Q_(10.0, 'au'),
            'I_G': Q_(1e5, 'au/M'),
            'I_H': Q_(0.0, 'au/M'),
            'I_HG': Q_(4e7, 'au/M'),
            'I_HG2': Q_(6e7, 'au/M'),
        },
        assay_type='DBA_HG2',
        model_name='equilibrium_stepwise',
        intervals={'Ka_HG': KaInterval(1.5e5, 2.6e5, False, False, 0.95, 16), 'Ka_HG2': second},
    )


def test_two_binding_constants_stack_one_headline_each_named_by_the_glossary():
    blocks = R.ka_blocks(_stepwise(KaInterval(1.1e3, 8.0e3, False, False, 0.95, 16)))

    assert [b.name for b in blocks] == ['K<sub>a</sub> HG', 'K<sub>a</sub> HG₂']


def test_a_second_step_the_data_do_not_show_is_not_limited_below_and_says_why():
    fit = _stepwise(KaInterval(1e-8, 9.0e3, True, False, 0.95, 16, one_step_p=0.03))
    second = R.ka_blocks(fit)[1]

    assert second.interval.startswith('no lower limit') and '10⁻⁸' not in second.interval
    assert second.tooltip == (
        'Kₐ HG₂ not limited below: a model without the second binding step fits nearly as well '
        '(one-step test p = 0.03).'
    )


# ---------------------------------------------------------------------------
# Parameters and their notes
# ---------------------------------------------------------------------------


def test_degenerate_rows_are_starred_and_the_footnote_names_the_total_the_model_holds_fixed():
    """The value is one member of a family that draws the same curve; one short sentence says why, hover says more."""
    degenerate = ('I0', 'I_dye_free', 'I_dye_bound')
    cells, tips, footnote = R.parameter_rows(aware_result(degenerate_keys=degenerate))  # IDA: the dye is not titrated

    starred = [row for row in cells if row[0].endswith('*')]
    assert len(starred) == 3
    assert not cells[0][0].endswith('*')  # Ka is not starred
    assert footnote == '* Not separately determined while the dye total is fixed.'
    assert tips[1].startswith('The data fix only a combination of') and tips[0] == ''
    stepwise = _stepwise(KaInterval(1.1e3, 8.0e3, False, False, 0.95, 16))
    host_balance = ('I0', 'I_H', 'I_HG', 'I_HG2')  # I_H freed: [H] + [HG] + [HG₂] = h₀ ties all four
    assert R.parameter_rows(replace(stepwise, degenerate_keys=host_balance))[2] == (
        '* Not separately determined while the host total is fixed.'
    )
    # Starred for an unpopulated species, not by a balance: the sentence names no total.
    unpopulated = replace(stepwise, degenerate_keys=('I_G', 'I_HG', 'I_HG2'))
    assert R.parameter_rows(unpopulated)[2] == '* Not separately determined by these data.'
    assert R.parameter_rows(result(degenerate_keys=('I_dye_bound',)))[2] == '* Not separately determined by these data.'
    assert R.parameter_rows(result())[2] == ''


@pytest.mark.parametrize(
    ('assay', 'parameters', 'tied', 'total'),
    [
        ('DBA_HtoD', ('Ka_dye', 'I0', 'I_dye_free', 'I_dye_bound'), ('I0', 'I_dye_free', 'I_dye_bound'), 'dye'),
        ('DBA_H2G', ('Ka_HG', 'Ka_H2G', 'I0', 'I_G', 'I_H', 'I_HG', 'I_H2G'), ('I0', 'I_H', 'I_HG', 'I_H2G'), 'host'),
    ],
    ids=['host-to-dye', 'h2g'],
)
def test_the_footnote_names_the_total_each_model_holds_fixed(assay, parameters, tied, total):
    """Host-to-dye titrates the host into a fixed dye: [D] + [HD] = d₀ ties I0 to the dye's coefficients. In 2:1
    the host total is fixed: [H] + [HG] + 2[H₂G] = h₀ ties I0 to every species holding a host."""
    values = {key: Q_(1e5, '1/M') if key.startswith('Ka') else Q_(1e4, 'au/M') for key in parameters}
    values['I0'] = Q_(10.0, 'au')
    fit = result(
        assay_type=assay,
        parameters=values,
        intervals={key: KaInterval(5e4, 2e5, False, False, 0.95, 16) for key in parameters if key.startswith('Ka')},
        degenerate_keys=tied,
    )

    assert R.parameter_rows(fit)[2] == f'* Not separately determined while the {total} total is fixed.'
    # The balance ties every one of them: with any one not starred, no total is named.
    for key in tied:
        fewer = tuple(k for k in tied if k != key)
        assert R.parameter_rows(replace(fit, degenerate_keys=fewer))[2] == '* Not separately determined by these data.'


def test_each_parameter_reads_its_estimate_and_unit():
    cells, _tips, _note = R.parameter_rows(result())

    assert cells[0] == ['K<sub>a</sub> guest', f'1.24{THIN}×{THIN}10⁶', 'M<sup>−1</sup>']
    assert cells[1] == ['I<sub>0</sub>', '100', 'a.u.']


def test_a_fit_that_ended_on_an_entered_bound_says_so():
    config = {'per_replicate': False, 'level': 0.95, 'custom_bounds': {'I_dye_bound': [0.0, 8e4, 'au/M']}}
    notes = ' '.join(R.parameter_notes(result(fit_config=config)))

    assert 'ended on a bound entered under Binding model (' in notes
    assert '8.0×10⁴' in notes


def _verdict(verdict, reference='F'):
    rejected = verdict in (Verdict.MODEL_INADEQUATE, Verdict.MODEL_AND_INPUTS)
    test = MisfitTest(
        'lack_of_fit', 12.0 if rejected else 0.9, 1e-6 if rejected else 0.55, (16, 40), reference=reference
    )
    return FitDiagnostics(conditional_misfit=test, misfit=test, conflict=None, verdict=verdict)


def test_an_offset_held_at_zero_is_named_only_under_a_curve_that_misses_the_data():
    from gui.plotting.labels import OFFSET_AT_ZERO_NOTE

    on_zero = {**result().parameters, 'I0': Q_(0.0, 'au')}

    notes = R.parameter_notes
    assert OFFSET_AT_ZERO_NOTE in notes(result(parameters=on_zero, diagnostics=_verdict(Verdict.MODEL_INADEQUATE)))
    assert OFFSET_AT_ZERO_NOTE not in notes(result(parameters=on_zero, diagnostics=_verdict(Verdict.CONSISTENT)))
    assert OFFSET_AT_ZERO_NOTE not in notes(result(diagnostics=_verdict(Verdict.MODEL_INADEQUATE)))


# ---------------------------------------------------------------------------
# The replicates
# ---------------------------------------------------------------------------


def test_the_replicates_own_fits_are_one_line_from_the_used_ones_with_what_they_answer():
    """Median and range of the used replicates' own fits — the left-out 9.0×10⁶ describes data the fit does not."""
    line, tip = R.replicate_line(per_replica_result(excluded=('3',)))

    assert line == (
        f'Single-replicate fits (inputs as entered, 3 replicates): K<sub>a</sub> guest median 1.20{THIN}×{THIN}10⁶, '
        f'range [1.00{THIN}×{THIN}10⁶, 1.40{THIN}×{THIN}10⁶] M<sup>−1</sup>'
    )
    assert 'can fall outside it' in tip  # why they may disagree with the interval, on hover
    assert R.replicate_line(result()) == ('', '')


def test_a_replicate_fit_that_ran_to_a_bound_is_counted_and_not_summarised():
    fit = per_replica_result(ka_by_replicate={'0': 1.0e6, '1': 1.2e6, '2': 1.4e6, '3': 1e-8})
    line, tip = R.replicate_line(fit)
    _headers, rows, _tips = R.replicate_rows(fit, None)

    assert (
        'median 1.20 × 10⁶, range [1.00 × 10⁶, 1.40 × 10⁶] M<sup>−1</sup>, 1 of 4 at a search bound'.replace(
            ' × ', f'{THIN}×{THIN}'
        )
        in line
    )
    assert 'left out of the median and range' in tip
    assert '10⁻⁸' not in line
    assert rows[3][1] == '<i>at the lower end of its search range</i>'


def test_a_line_with_no_figure_says_nothing_on_hover_about_figures():
    """Every replicate on a bound: no median or range is shown, so nothing may be said of how one relates to the interval."""
    fit = per_replica_result(ka_by_replicate={rid: 1e12 for rid in '0123'})
    line, tip = R.replicate_line(fit)

    assert line.endswith('4 of 4 at a search bound') and 'median' not in line
    # No median or range is on screen to be left out of: the count stands in for one, as too few are left.
    assert 'left out of the median' not in tip and 'too few values are left' in tip
    assert R.REPLICATES_RELATION not in tip
    # Three of four on a bound leave one value, which is no median and range either.
    _line, tip = R.replicate_line(per_replica_result(ka_by_replicate={'0': 1.0e6, '1': 1e12, '2': 1e12, '3': 1e12}))
    assert 'left out of the median' not in tip and 'too few values are left' in tip


def test_the_replicates_table_lists_every_replicate_with_its_own_fit_and_verdict(qapp):
    ms = four_replicates()
    fit = per_replica_result(p_values={'0': 0.8, '1': 0.6, '2': 0.4, '3': 0.0004}, excluded=('3',))
    headers, rows, tips = R.replicate_rows(fit, ms)

    # A header is painted as plain text, so the binding constant is named in plain text,
    # with the power of ten its column shares: 1.0 to 9.0 × 10⁶ M⁻¹ read as 1.00 to 9.00.
    assert headers == ['Replicate', 'Kₐ guest\n(10⁶ M⁻¹)', 'p']
    assert [row[0] for row in rows] == ['A', 'B', 'C', 'D<br>left out']
    assert [row[1] for row in rows] == ['1.00', '1.20', '1.40', '9.00'] and _shown(rows[3][2]) == '< 0.001'
    # The R² of each replicate's own fit, and why one was left out, on hover.
    assert tips[0] == 'R² of its own fit 0.9900.' and tips[3].startswith('Replicate 3 needs a different Ka.')
    assert R.replicate_rows(result(), ms) == ([], [], [])


@pytest.mark.parametrize(
    ('values', 'power', 'cells'),
    [
        ((2.0e3, 1.2e5, 1.4e5), 3, ['2.00', '120', '140']),  # two decades: one power still serves
        ((2.0e3, 1.2e6, 1.4e6), None, [f'2.00{THIN}×{THIN}10³', f'1.20{THIN}×{THIN}10⁶', f'1.40{THIN}×{THIN}10⁶']),
        ((1.0e3, 9.99e5, 5e5), 3, ['1.00', '999', '500']),  # three figures of the largest still fit
        ((9.9e3, 1.0e6, 5e5), None, [f'9.90{THIN}×{THIN}10³', f'1.00{THIN}×{THIN}10⁶', f'5.00{THIN}×{THIN}10⁵']),
        # 999.6 × 10³ is written 1.00 × 10⁶: under a header of 10³ it would carry a power of its own.
        ((2.0e3, 9.996e5, 5e5), None, [f'2.00{THIN}×{THIN}10³', f'1.00{THIN}×{THIN}10⁶', f'5.00{THIN}×{THIN}10⁵']),
    ],
    ids=['two-decades', 'three-decades', 'mantissa-999', 'leading-digits-three-apart', 'rounds-to-1000'],
)
def test_a_column_of_own_fits_shares_a_power_of_ten_only_where_every_value_reads_as_itself(values, power, cells):
    """A mantissa of 0.0… would be read as another number; one of up to three figures is read as written."""
    fit = per_replica_result(ka_by_replicate={'0': values[0], '1': values[1], '2': values[2], '3': values[0]})
    headers, rows, _tips = R.replicate_rows(fit, None)

    assert headers[1] == ('Kₐ guest\n(M⁻¹)' if power is None else 'Kₐ guest\n(10³ M⁻¹)')
    assert [row[1] for row in rows[:3]] == cells
    for row, value in zip(rows, values, strict=False):
        assert _read(row[1], power or 0) == pytest.approx([value], rel=5e-3)


def test_an_imported_fit_names_its_replicates_by_their_letters_without_the_data():
    """Ids '0', '1', … are file labels: '0 left out by the fit' reads as none left out. The fit records the order
    the data were loaded in, so the letters Measurements gave the replicates (A, B, …) survive without the data."""
    from core.assays.ida import IDAAssay
    from core.pipeline.fit_pipeline import fit_measurement_set
    from tests.unit.test_fit_record import _CONDITIONS, _CONFIG, _measurement_set

    ms = _measurement_set()  # a, b, c follow one Ka; odd binds ten times as tightly
    ms.set_active('b', False)
    fit = FitResult.from_dict(fit_measurement_set(ms, IDAAssay, _CONDITIONS, _CONFIG).to_dict())
    q = R.quality(fit, None)
    _headers, rows, _tips = R.replicate_rows(fit, None)

    assert (q.used, q.used_note) == ('2 of 4', 'B switched off · D left out by the fit')
    assert q.left_out.startswith('D — ')
    assert [row[0] for row in rows] == ['A', 'C', 'D<br>left out']
    assert R.badge(fit, None) == 'Inputs as entered · 2 of 4 replicates'
    # Without the recorded order no letter can be rebuilt: the ids are quoted, so none reads as a count.
    del fit.metadata['loaded_replica_ids']
    assert R.quality(fit, None).used_note == "'odd' left out by the fit"


def test_replicates_too_few_to_test_show_no_p_value_rather_than_a_made_up_one():
    _headers, rows, _tips = R.replicate_rows(per_replica_result(), None)

    assert [row[-1] for row in rows] == ['—', '—', '—', '—']


def test_a_replicate_p_value_near_one_reads_as_the_bound_every_report_writes(qapp):
    """A p of 0.997 written '1' would read as a certain test; Diagnostics and the reports write 'p > 0.99'."""
    fit = per_replica_result(p_values={'0': 0.997, '1': 0.99, '2': 0.5, '3': 0.0004})
    _headers, rows, _tips = R.replicate_rows(fit, None)

    assert [_shown(row[-1]) for row in rows] == ['> 0.99', '0.99', '0.5', '< 0.001']


def _shown(cell: str) -> str:
    """The text a rich-text table cell shows, its lines joined by a space."""
    from PyQt6.QtGui import QTextDocument

    doc = QTextDocument()
    doc.setHtml(cell)
    return ' '.join(doc.toPlainText().split())


# ---------------------------------------------------------------------------
# Fit quality and the summary beside the title
# ---------------------------------------------------------------------------


def test_replicates_used_counts_against_every_loaded_one_and_says_what_happened_to_the_rest():
    """B switched off before the fit, D left out by it: 2 of the 4 loaded replicates entered the fit."""
    ms = four_replicates()
    ms.set_active('1', False)
    fit = replace(
        fit_on(ms, left_out=('3',)),
        metadata={
            'active_replica_ids': ['0', '2', '3'],
            'replica_ids_fit': ['0', '2'],
            'replica_failures': {'3': 'Its own fit needs a different Ka.'},
        },
    )
    q = R.quality(fit, ms)

    assert q.used == '2 of 4'
    assert q.used_note == 'B switched off · D left out by the fit'
    assert q.left_out == 'D — Its own fit needs a different Ka.'
    assert R.badge(fit, ms) == 'Inputs as entered · 2 of 4 replicates'
    assert R.badge(fit_on(four_replicates()), four_replicates()) == 'Inputs as entered · 4 replicates'
    assert R.badge(None, ms) is None


def test_the_rmse_reads_as_the_report_writes_it(tmp_path):
    """Three significant figures with the trailing zero kept and ``×10ⁿ``, on screen and in the file.

    1 204 000 to three figures is 1.20×10⁶ and 299.8 is 300: worked out by hand. The screen
    sets the × between thin spaces, as the design writes every number (DESIGN.md §2).
    """
    from gui.session import export_results_txt

    for rmse, shown in ((1.204e6, '1.20×10⁶ a.u.'), (299.8, '300 a.u.')):
        fit = result(rmse=rmse)
        assert R.quality(fit, None).rmse == shown.replace('×', f'{THIN}×{THIN}')
        path = tmp_path / 'report.txt'
        export_results_txt([fit], path)
        (line,) = [ln for ln in path.read_text(encoding='utf-8').splitlines() if ln.strip().startswith('RMSE:')]
        assert line.split(':', 1)[1].strip() == shown
    assert R.quality(result(), None).r2 == '0.9980'


def test_the_noise_reads_as_its_floor_and_proportional_part_with_the_law_s_sentence_on_hover():
    """0.011 of the signal and a floor of 890 a.u.: ``1.1 % + 890 a.u.``, as the law's own fields say."""
    from core.pipeline.noise import NoiseBasis, NoiseLaw

    def law(share, **fields):
        return (
            NoiseLaw(
                basis=NoiseBasis.REPLICATES,
                share=share,
                floor=890.0,
                proportional=0.011,
                reference=1.2e5,
                n_replicates=8,
            )
            if not fields
            else NoiseLaw(**fields)
        )

    mixed = R.quality(result(noise=law(0.5)), None)
    assert (mixed.noise, mixed.noise_note) == ('1.1 % + 890 a.u.', 'from replicate scatter')
    assert mixed.noise_tooltip.startswith('About 1.1 % of the signal plus 890 a.u. (scatter of 8 replicates')
    assert R.quality(result(noise=law(0.0)), None).noise == '890 a.u.'  # constant: the floor alone
    assert R.quality(result(noise=law(1.0)), None).noise == '1.1 %'  # proportional: the share of the signal
    single = R.quality(result(noise=law(0, basis=NoiseBasis.SINGLE_TITRATION)), None)
    assert (single.noise, single.noise_note) == ('Not estimated', 'one titration')
    assert single.noise_tooltip.startswith('Taken as constant')
    sparse = R.quality(result(noise=law(0, basis=NoiseBasis.TOO_FEW_POINTS, n_replicates=3)), None)
    assert (sparse.noise, sparse.noise_note) == ('Not estimated', 'too few scattered points')
    assert R.quality(result(noise=None), None).noise_note == 'not recorded in this result'


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------


_CONFLICT = FitDiagnostics(
    conditional_misfit=MisfitTest('lack_of_fit', 200.0, 1e-9, dof=(9, 72)),
    misfit=MisfitTest('lack_of_fit', 1.1, 0.4, dof=(9, 72)),
    conflict=Conflict(q=24.2, k=2, p_value=1e-5, weights=(0.3, 0.9)),
    verdict=Verdict.INPUTS_CONFLICT,
)


def test_each_test_is_marked_by_whether_the_procedure_rejects_it():
    """The conflict's p of 1e-5 rejects at 0.05/2; the misfit's 0.4 does not, and the one at the inputs as entered does."""
    rows = R.test_rows(aware_result(diagnostics=_CONFLICT))

    assert [(row.text, row.tone, row.p) for row in rows] == [
        ('Curve fits with inputs moved', 'success', 'p = 0.4'),
        ('Misfit at inputs as entered', 'warning', 'p < 0.001'),
        ('Inputs conflict', 'warning', 'p < 0.001'),
    ]
    assert [row.text for row in R.test_rows(result(diagnostics=_verdict(Verdict.CONSISTENT)))] == [
        'Curve fits at inputs as entered'
    ]
    assert R.test_rows(result()) == []


def test_a_test_that_could_not_run_reads_as_its_reason():
    diagnostics = FitDiagnostics(None, None, None, Verdict.CONSISTENT, skipped={'misfit': 'no_scatter'})
    (row,) = R.test_rows(result(diagnostics=diagnostics))

    assert row.text.startswith('Curve not tested: the data carry no scatter above rounding') and row.p == '—'
    assert row.tone == 'text-tertiary'


def test_two_skipped_misfit_tests_say_which_fit_each_is_about():
    """With the inputs free to move both fits are listed; two identical 'Curve not tested' rows tell them apart nowhere."""
    skipped = FitDiagnostics(
        None, None, None, Verdict.CONSISTENT, {'misfit': 'no_scatter', 'conflict': 'no_informed_direction'}
    )
    moved, entered, _inputs = R.test_rows(aware_result(diagnostics=skipped))

    assert moved.text != entered.text and moved.tooltip != entered.tooltip
    assert 'inputs moved' in moved.text and 'inputs as entered' in entered.text
    assert moved.tooltip.startswith('Fit with the inputs free to move')
    assert entered.tooltip.startswith('Fit with the inputs as entered')
    assert all('no scatter above rounding' in row.text for row in (moved, entered))


def test_each_test_carries_its_full_sentence_with_its_statistic():
    """The F ratio of each fit, on hover of its row: the rows show only the outcome and the p-value."""
    moved, entered, _inputs = R.test_rows(aware_result())

    assert moved.tooltip == 'Fit with the inputs free to move: lack-of-fit F(9, 72) = 0.8, p = 0.62.'
    assert entered.tooltip == 'Fit with the inputs as entered: lack-of-fit F(9, 72) = 0.9, p = 0.55.'
    (only,) = R.test_rows(result(diagnostics=_verdict(Verdict.CONSISTENT)))
    assert only.tooltip.startswith('Fit at the entered inputs: lack-of-fit F(16, 40)')


def test_a_conflict_is_one_statement_about_the_inputs_together():
    shifts = {
        'h0': InputShift('h0', -0.114, -3.8, False),
        '__titrant__': InputShift('__titrant__', 0.093, 3.1, False),
    }
    fit = aware_result(shifts=shifts, diagnostics=_CONFLICT)
    conflict = R.test_rows(fit)[-1]
    rows = R.shift_rows(fit)

    assert 'q = 24.2 across 2 directions' in conflict.tooltip
    assert '[Host]₀ −11.4 % (3.8 σ)' in conflict.tooltip
    assert conflict.tooltip.endswith('not which input is wrong.')
    # Largest |z| first, every report in the same order.
    assert [row.name for row in rows] == ['[Host]₀', 'Guest (titrant, whole series)']
    assert [row.tooltip for row in rows] == ['−3.8 σ', '+3.1 σ']
    assert R.shifts_footnote(rows).endswith('not which input is wrong.')


def test_a_shared_source_is_named_with_the_inputs_it_moves():
    from core.pipeline.inputs import ErrorModel, SharedSource, shared_key

    key = shared_key('Host and dye stock')
    fit = aware_result(shifts={key: InputShift(key, -0.041, -1.02, False)}, uncertainty={})
    fit.fit_config.update(ErrorModel(shared=(SharedSource('Host and dye stock', 4.0, ('h0', 'd0')),)).to_dict())

    assert R.shift_rows(fit)[0].name == 'Host and dye stock (shared by [Host]₀, [Dye]₀)'


def test_an_input_stated_as_a_range_reports_its_end_and_no_sigma():
    fit = aware_result(
        shifts={'d0': InputShift('d0', -0.06, None, True)},
        uncertainty={'d0': {'kind': 'interval', 'sigma': 0.0, 'lo': -6.0, 'hi': 10.0, 'relative': True}},
    )
    conflict = R.test_rows(fit)[-1]
    (row,) = R.shift_rows(fit)

    assert (
        conflict.text.startswith('Inputs not tested:') and 'there is nothing to test a shift against' in conflict.text
    )
    assert row.z is None and row.percent == '−6.0 %'
    assert 'no σ' in row.tooltip and 'at the edge of its range' in row.tooltip


def test_sigma_inputs_the_data_cannot_check_are_said_to_be_unchecked():
    diagnostics = FitDiagnostics(
        conditional_misfit=MisfitTest('runs', 6.0, 0.41, expected=7.0),
        misfit=MisfitTest('runs', 6.0, 0.41, expected=7.0),
        conflict=None,
        verdict=Verdict.CONSISTENT,
    )
    conflict = R.test_rows(aware_result(diagnostics=diagnostics))[-1]

    assert conflict.text.startswith('Inputs not tested:') and 'cannot check' in conflict.text
    assert conflict.p == '—' and 'q =' not in conflict.tooltip


def test_a_simulated_lack_of_fit_p_value_says_so():
    (simulated,) = R.test_rows(result(diagnostics=_verdict(Verdict.CONSISTENT, reference='bootstrap')))
    (exact,) = R.test_rows(result(diagnostics=_verdict(Verdict.CONSISTENT)))

    assert 'p = 0.55, simulated from the fitted curve and the noise law' in simulated.tooltip
    assert 'simulated' not in exact.tooltip


# ---------------------------------------------------------------------------
# Callouts
# ---------------------------------------------------------------------------


def test_a_hidden_fit_shows_its_note_and_nothing_else():
    note = 'This fit was made on replicates B–D. Replicate B is now off.'
    conflict = FitDiagnostics(None, None, Conflict(24.2, 1, 1e-5, (0.9,)), Verdict.INPUTS_CONFLICT)

    assert R.callouts(aware_result(diagnostics=conflict), note) == [R.CalloutSpec('neutral', 'Results hidden', note)]


def test_a_conflict_is_called_out_about_the_inputs_together_with_the_way_to_review_it():
    conflict = FitDiagnostics(
        conditional_misfit=MisfitTest('lack_of_fit', 200.0, 1e-9, dof=(9, 72)),
        misfit=MisfitTest('lack_of_fit', 1.1, 0.4, dof=(9, 72)),
        conflict=Conflict(q=24.2, k=1, p_value=1e-5, weights=(0.9,)),
        verdict=Verdict.INPUTS_CONFLICT,
    )
    (callout,) = R.callouts(aware_result(diagnostics=conflict), None)

    assert (callout.tone, callout.title, callout.action) == ('warning', 'Inputs conflict', R.REVIEW)
    assert '[Host]' not in callout.body and 'Together' in callout.body


def test_a_curve_that_misses_the_data_is_called_out_and_a_fit_that_passes_is_not():
    (misses,) = R.callouts(result(diagnostics=_verdict(Verdict.MODEL_INADEQUATE)), None)

    assert (misses.tone, misses.title) == ('warning', 'Curve misses the data')
    assert R.callouts(result(diagnostics=_verdict(Verdict.CONSISTENT)), None) == []


def test_a_misfit_the_moved_inputs_explain_is_called_out_at_the_inputs_as_entered():
    explain = FitDiagnostics(
        conditional_misfit=MisfitTest('lack_of_fit', 200.0, 1e-9, dof=(9, 72)),
        misfit=MisfitTest('lack_of_fit', 0.8, 0.62, dof=(9, 72)),
        conflict=Conflict(q=1.0, k=1, p_value=0.3, weights=(0.9,)),
        verdict=Verdict.INPUTS_EXPLAIN,
    )
    (callout,) = R.callouts(aware_result(diagnostics=explain), None)

    assert callout.title == 'Misfit at inputs as entered'


def test_numbers_no_data_could_check_and_fits_not_drawn_are_noted():
    notes = R.callouts(result(), None, unchecked=True, others_hidden='1 of the 2 fits is hidden.')

    assert [(c.tone, c.body) for c in notes] == [
        ('neutral', R.UNCHECKED_NOTE),
        ('neutral', '1 of the 2 fits is hidden.'),
    ]


# ---------------------------------------------------------------------------
# The titration plot
# ---------------------------------------------------------------------------


def test_the_mean_and_sd_cover_only_the_replicates_the_fit_used_and_the_rest_are_crosses():
    """B switched off, A left out by the fit: only C and D are replicates the curve describes."""
    ms = four_replicates()
    ms.set_active('1', False)
    fit = fit_on(ms, left_out=('0',))
    plot = R.titration(ms, [fit], AssayType.GDA)

    assert plot.data.active == [False, False, True, True]
    assert plot.data.mean_sd and len(plot.data.curves) == 1
    # One entry per replicate, named by its letter and marked by its place in the data, so it
    # takes the colour its points are drawn in; the ones not used keep theirs, drawn as ×.
    assert plot.data.replicate_ids == ['0', '1', '2', '3']
    assert plot.legend == [
        ('cross', 'A left out by the fit', 0),
        ('cross', 'B switched off', 1),
        ('dots', 'C', 2),
        ('dots', 'D', 3),
        ('mean', 'Mean ± SD'),
        ('line', 'Fit'),
    ]


def test_with_no_fit_shown_every_active_replicate_is_drawn_and_no_curve():
    ms = four_replicates()
    plot = R.titration(ms, [], AssayType.IDA)

    assert plot.data.active == [True] * 4 and plot.data.curves == []
    assert plot.data.x_name == 'Guest'
    assert ('line', 'Fit') not in plot.legend


def test_overlaid_fits_on_different_replicates_are_noted():
    ms = four_replicates()
    every, some = fit_on(ms), fit_on(ms, left_out=('0',))

    assert R.titration(ms, [every, some], AssayType.GDA).replicates_note == (
        'Mean ± SD is over replicates B–D, the ones the reported fit used. Another fit shown used replicates A–D.'
    )
    assert R.titration(ms, [some, some], AssayType.GDA).replicates_note is None


def test_a_curve_drawn_at_moved_inputs_says_so_and_one_at_the_entered_inputs_does_not():
    ms = four_replicates()
    moved = fit_on(ms, input_shifts={'h0': InputShift('h0', -0.194, -3.9, False)})

    assert R.titration(ms, [moved], AssayType.GDA).description == R.SHIFTED_CURVE_NOTE
    assert R.titration(ms, [fit_on(ms)], AssayType.GDA).description == ''


def test_the_display_choice_shows_replicates_mean_or_both():
    ms = four_replicates()
    fit = fit_on(ms)
    both, mean_only, replicates_only = (R.titration(ms, [fit], AssayType.GDA, i) for i in range(3))

    assert (both.data.replicates, both.data.mean_sd) == (True, True)
    assert (mean_only.data.replicates, mean_only.data.mean_sd) == (False, True)
    assert (replicates_only.data.replicates, replicates_only.data.mean_sd) == (True, False)
    assert [kind for kind, _ in mean_only.legend] == ['mean', 'line']


def test_without_data_the_shown_curves_are_drawn_alone():
    plot = R.titration(None, [result()], AssayType.GDA)

    assert plot.data.signals.shape[0] == 0 and len(plot.data.curves) == 1
    assert R.titration(None, [], AssayType.GDA).data is None


def test_the_empty_view_says_what_to_do_with_the_platform_shortcut():
    assert (
        R.empty_sentence(False, '⌘R')
        == 'No fit yet. Add your titration files with Load data, then choose Run fit (⌘R).'
    )
    assert 'Run fit (Ctrl+R)' in R.empty_sentence(True, 'Ctrl+R')


# ---------------------------------------------------------------------------
# Numbers read for what they are
# ---------------------------------------------------------------------------

_UNSUPER = str.maketrans('⁰¹²³⁴⁵⁶⁷⁸⁹⁻', '0123456789-')
_SUP = '⁻⁰¹²³⁴⁵⁶⁷⁸⁹'
_NUMBER = re.compile(rf'(?:(\d+(?:\.\d+)?)\s?×\s?|(?<![\d.]))10([{_SUP}]+)|(\d+(?:\.\d+)?)')


def _read(text: str, power: int | None = None) -> list[float]:
    """The numbers of *text* as a reader takes them.

    A number written with its own ``× 10ⁿ`` is that; a bare mantissa takes *power*, or with
    none given, the power written after the last number of the same run (``0.700 – 2.20 ×
    10⁶`` is 0.7×10⁶ to 2.2×10⁶).
    """
    found = [
        (float(bare), None) if bare else (float(m or 1), int(p.translate(_UNSUPER)))
        for m, p, bare in _NUMBER.findall(text)
    ]
    trailing = next((p for _m, p in reversed(found) if p is not None), 0)
    return [m * 10.0 ** (p if p is not None else (trailing if power is None else power)) for m, p in found]


@pytest.mark.parametrize(
    ('low', 'high'),
    [(0.7e6, 2.2e6), (1.5e5, 2.6e5), (2.0e3, 5.0e8), (8.9e5, 2.5e8), (17541.0, 1.70e6)],
    ids=['one-decade', 'narrow', 'five-decades', 'wide', 'two-decades'],
)
def test_every_number_of_a_headline_and_its_chart_reads_as_the_value_it_states(low, high):
    """A shared power of ten must never turn the low end of a wide interval into a different number."""
    estimate = math.sqrt(low * high)
    fit = result(
        parameters={**result().parameters, 'Ka_guest': Q_(estimate, '1/M')},
        intervals={'Ka_guest': KaInterval(low, high, False, False, 0.95, 16)},
    )
    (block,) = R.ka_blocks(fit)

    assert _read(block.interval) == pytest.approx([low, high], rel=5e-3)
    (row,) = block.rows
    assert _read(row['text'], block.exponent or 0) == pytest.approx([estimate, low, high], rel=5e-3)
    for value, label in block.ticks:  # each tick reads as its value on the axis's unit
        assert _read(label, block.exponent or 0) == pytest.approx([value], rel=1e-6)


def test_an_interval_axis_carries_two_to_six_ticks_whatever_it_spans():
    """More than six crowd the labels together; fewer than two give no scale."""
    rng = np.random.default_rng(7)
    lo = 10.0 ** rng.uniform(-2, 12, 3000)
    hi = lo * 10.0 ** rng.uniform(math.log10(1.5625), 8, 3000)  # an axis spans its rows × 1.25 each side
    for a, b in zip(lo, hi, strict=True):
        ticks = R.nice_ticks(a, b)
        assert 2 <= len(ticks) <= 6, (a, b, ticks)
        assert all(a <= t <= b for t in ticks) and ticks == sorted(set(ticks)), (a, b, ticks)


def test_an_interval_chart_never_draws_two_tick_labels_into_each_other(qapp):
    """Labels written in full (``2×10⁵``) are wide; at the chart's width a label that would touch another is left out."""
    from PyQt6.QtGui import QFontMetrics

    from gui.design import components as C
    from gui.design.appearance import theme
    from gui.design.tokens import font, space

    rng = np.random.default_rng(11)
    lo = 10.0 ** rng.uniform(-2, 12, 400)
    hi = lo * 10.0 ** rng.uniform(math.log10(1.5625), 4, 400)
    rows = [{'label': 'Input-aware', 'color': 'accent', 'segments': [], 'est': None, 'text': '1.00'}]
    fm = QFontMetrics(font('small-number'))
    charts = [
        (C.IntervalChart(theme(), rows, 1.0, 10.0, [], ''), (420, 470, 560)),
        (C.CompactIntervals(theme(), rows, 1.0, 10.0, []), (200, 260, 320)),
    ]
    for a, b in zip(lo, hi, strict=True):
        e = R.shared_power([a * 1.25, b / 1.25])
        ticks = [(v, R.tick_label(v, e)) for v in R.nice_ticks(a, b)]
        for chart, widths in charts:
            if isinstance(chart, C.IntervalChart):
                chart.set_rows(rows, a, b, ticks, 'M⁻¹')
            else:
                chart.set_rows(rows, a, b, ticks)
            for width in widths:
                chart.resize(width, chart.height())
                left, right = chart.tick_room()
                drawn = sorted((rect.left(), rect.right(), text) for text, rect in chart.tick_rects())
                assert len(drawn) >= 2, (a, b, width, ticks)
                assert all(left <= start and end <= right for start, end, _text in drawn), (a, b, width, drawn)
                assert all(nxt[0] - prev[1] >= space(2) for prev, nxt in zip(drawn, drawn[1:])), (a, b, width, drawn)
                assert all(fm.horizontalAdvance(text) <= end - start for start, end, text in drawn)


def test_a_p_value_at_the_floor_of_its_simulation_reads_as_that_bound_everywhere():
    """One test, one p-value: the row and the sentence under it say the same, a bound and not an exact value."""
    from core.pipeline.diagnostics import LOF_BOOTSTRAP_DRAWS

    floor = 1.0 / (LOF_BOOTSTRAP_DRAWS + 1)
    test = MisfitTest('lack_of_fit', 389.0, floor, dof=(9, 60), reference='bootstrap')
    fit = result(diagnostics=FitDiagnostics(test, test, None, Verdict.MODEL_INADEQUATE))
    (row,) = R.test_rows(fit)

    assert row.p == f'p ≤ {floor:g}'
    assert f'{row.p},' in row.tooltip


def test_an_input_the_fit_took_to_the_edge_of_its_range_is_said_in_the_panel_not_only_on_hover():
    """A range has no σ to draw: whether the fit rests the input on an end is the one thing to see."""
    fit = aware_result(
        shifts={'h0': InputShift('h0', -0.05, None, True), 'd0': InputShift('d0', 0.01, None, False)},
        uncertainty={
            'h0': {'kind': 'interval', 'sigma': 0.0, 'lo': -5.0, 'hi': 5.0, 'relative': True},
            'd0': {'kind': 'interval', 'sigma': 0.0, 'lo': -5.0, 'hi': 5.0, 'relative': True},
        },
    )
    rows = {row.name: row for row in R.shift_rows(fit)}

    assert rows['[Host]₀'].note == 'at the edge of its range'
    assert rows['[Dye]₀'].note == 'inside its range'


def test_the_shift_footnote_speaks_of_bars_only_where_one_is_drawn():
    """An input stated as a range has no σ, so no bar; the footnote must not explain bars that are not there."""
    ranges = aware_result(
        shifts={'h0': InputShift('h0', -0.05, None, True)},
        uncertainty={'h0': {'kind': 'interval', 'sigma': 0.0, 'lo': -5.0, 'hi': 5.0, 'relative': True}},
    )
    footnotes = {
        name: R.shifts_footnote(R.shift_rows(fit)) for name, fit in (('ranges', ranges), ('sigma', aware_result()))
    }

    assert 'σ' not in footnotes['ranges'] and 'Bar' not in footnotes['ranges']
    assert 'σ' in footnotes['sigma']
    assert all(text.endswith('not which input is wrong.') for text in footnotes.values())
    assert 'moved none' in R.shifts_footnote([])


def test_every_fit_drawn_is_told_apart_and_each_one_s_numbers_are_given():
    """Two curves under one 'Fit' leave the other one unexplained; its numbers must be on screen and in the figure."""
    ms = four_replicates()
    other = fit_on(ms, parameters={**result().parameters, 'Ka_guest': Q_(3.3e5, '1/M')}, r_squared=0.9871)
    reported = fit_on(ms)
    plot = R.titration(ms, [other, reported], AssayType.GDA)

    assert len(plot.data.curves) == 1 and len(plot.data.other_curves) == 1
    assert ('line', 'Reported fit') in plot.legend and ('line-other', 'Other fit') in plot.legend
    assert f'3.30{THIN}×{THIN}10⁵' in plot.others_note and 'R² 0.9871' in plot.others_note
    assert [c.title for c in R.callouts(reported, None, others_note=plot.others_note)] == ['Other fits shown']
    reported_line, other_line = plot.data.caption
    assert reported_line.startswith('Reported fit: Kₐ guest 1.24') and 'R² 0.9980' in reported_line
    assert other_line.startswith('Other fit 1 (dashed): Kₐ guest 3.30')
    single = R.titration(ms, [reported], AssayType.GDA)
    assert single.others_note is None and single.legend[-1] == ('line', 'Fit')


def test_the_caption_of_a_saved_figure_states_the_interval_and_that_the_curve_is_drawn_at_moved_inputs():
    ms = four_replicates()
    moved = fit_on(ms, input_shifts={'h0': InputShift('h0', -0.04, -1.3, False)})
    (line,) = R.titration(ms, [moved], AssayType.GDA).data.caption

    assert f'95{THIN}% interval 0.700 – 2.20{THIN}×{THIN}10⁶ M⁻¹' in line
    assert line.endswith(R.SHIFTED_CURVE_NOTE)
    assert R.SHIFTED_CURVE_NOTE not in R.titration(ms, [fit_on(ms)], AssayType.GDA).data.caption[0]


def test_numbers_in_fit_details_are_written_with_thin_spaces_around_the_times_sign():
    """DESIGN.md §2: 1.59 × 10⁸, as the headline beside them writes it."""
    from core.pipeline.noise import NoiseBasis, NoiseLaw

    fit = per_replica_result(ka_by_replicate={'0': 2.0e3, '1': 1.2e6, '2': 1.4e6, '3': 9.0e6})
    sources = {
        'parameters': [cell for row in R.parameter_rows(fit)[0] for cell in row],
        'replicates': [cell for row in R.replicate_rows(fit, None)[1] for cell in row],
        'rmse': [R.quality(result(rmse=1.204e6), None).rmse],
        'single-replicate line': [R.replicate_line(fit)[0]],
        'noise': [R.quality(result(noise=NoiseLaw(NoiseBasis.REPLICATES, floor=1.5e5, reference=1e6)), None).noise],
        'diagnostics': [
            row.tooltip
            for row in R.test_rows(
                aware_result(
                    diagnostics=FitDiagnostics(
                        conditional_misfit=MisfitTest('lack_of_fit', 2.5e5, 1e-9, dof=(14, 42)),
                        misfit=MisfitTest('lack_of_fit', 0.8, 0.62, dof=(14, 42)),
                        conflict=None,
                        verdict=Verdict.MODEL_INADEQUATE,
                    ),
                )
            )
        ],
    }
    for name, texts in sources.items():
        written = [text for text in texts if '×' in text]
        assert written, name
        assert not any(re.search(f'[^{THIN}]×|×[^{THIN}]', text) for text in written), name


def test_a_conditional_estimate_on_its_search_bound_is_written_in_words_on_its_own_row():
    """Each reading writes its own estimate: words where it ran onto the box, a number where it did not."""
    base = aware_result()
    conditional = replace(
        base.conditional,
        parameters={**base.conditional.parameters, 'Ka_guest': Q_(1e-8, '1/M')},
        intervals={'Ka_guest': KaInterval(1e-8, 2.2e6, True, False, 0.95, 16)},
    )
    (block,) = R.ka_blocks(replace(base, conditional=conditional))
    aware, entered = block.rows

    assert entered['text'].startswith('not limited below') and entered['est'] is None
    assert not aware['text'].startswith('not limited') and aware['est'] == pytest.approx(1.30e6)


def test_a_split_input_aware_reading_draws_the_stretches_of_its_own_penalised_profile():
    """The Input-aware bars come from the penalised profile; the conditional profile accepts other stretches."""

    def curve(gap):
        class Curve:
            grid = np.geomspace(1e5, 1e7, 81)
            r2 = np.where((grid < gap[0]) | (grid > gap[1]), 0.99, 0.5)
            r2_cut = np.full(grid.size, 0.9)

        return Curve()

    conditional_curve = curve((3e5, 4e5))
    conditional_curve.aware = curve((1.0e6, 1.5e6))

    class Profile:
        profiles = {'Ka_guest': conditional_curve}

    base = aware_result()
    fit = replace(base, intervals={'Ka_guest': KaInterval(1.5e5, 4e6, False, False, 0.95, 16, split=True)})
    aware_row = R.ka_blocks(fit, Profile())[0].rows[0]
    (first, second) = aware_row['segments']

    assert aware_row['label'] == 'Input-aware'
    assert first[1] < 1.0e6 < 1.5e6 < second[0]  # the gap of the penalised profile, not 3–4×10⁵
