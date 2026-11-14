"""What Sensitivity shows of a run, and the settings of the next one, with no widget (:mod:`gui.sensitivity`).

Pins the rules a sensitivity run is shown and set by:

- the settings: the configuration carries the error model stated in Input uncertainty —
  all of it for indices, the two axes' own uncertainties for a heatmap — and the mode,
  sample size, seed, grid and span shown; a heatmap refuses an axis that is fixed, one
  used twice, one that moves only through a shared source, and one that reaches zero at
  the span chosen, naming the input and the span; a fixed seed must be a whole number;
- every number shown is the run's own: the spread from the budget, the indices and their
  whiskers, the budget's variances (which add up to the whole variance), the what-if
  from :func:`core.pipeline.budget.what_if`; an interval is printed to the figures that
  tell it from its estimate, and a spread never reads below zero;
- a constant the run withholds gets its reason in plain words and none of its numbers;
  fits on the Kₐ bounds and a stopped run are counted once, in the units the run keeps;
- the callouts: a conflict of the fit is said about the inputs together, the run is
  said not to be a confidence interval otherwise, a note hiding the run is all that is
  said of it;
- the heatmap's axes are in the inputs' units, the titrant's in percent, and the
  readout names both inputs; the CSV of the budget carries the run's floats and its
  seed, and is refused where the run gives no budget.
"""

from __future__ import annotations

import math
from dataclasses import replace

import numpy as np
import pytest

from core.pipeline.budget import Budget, BudgetRow, WhatIf
from core.pipeline.inputs import TITRANT, ErrorModel, InputSpec, SharedSource
from core.pipeline.sensitivity import _SOBOL_BLOCKS, _SOBOL_SAMPLE_SIZES, SensitivityMode
from gui import sensitivity as S
from gui.plotting.labels import THIN
from tests.unit.gui import sensitivity_results as F

_H0 = 4.3e-6
_LABELS = {'Ka_dye': 'Kₐ,dye', 'h0': '[Host]₀', 'd0': '[Dye]₀', TITRANT: 'Guest (titrant, whole series)'}
_NOMINALS = {'Ka_dye': 1.68e7, 'h0': _H0, 'd0': 6e-6}


def _plain(text: str) -> str:
    return text.replace(THIN, ' ').replace('\u00a0', ' ')


# ---------------------------------------------------------------------------
# The settings of the next run
# ---------------------------------------------------------------------------


def _heatmap(form: S.AnalysisForm, x: str, y: str, span: float = S.DEFAULT_SPAN) -> S.AnalysisForm:
    form.mode, form.x_key, form.y_key, form.x_span, form.y_span = SensitivityMode.HEATMAP, x, y, span, span
    return form


def test_the_sample_sizes_offered_are_the_ones_the_sobol_design_accepts():
    """The 8-block design needs a power of two per block, so only the sizes it can split are offered."""
    assert S.SAMPLE_SIZES == _SOBOL_SAMPLE_SIZES
    assert S.AnalysisForm().n_samples == S.SAMPLE_SIZES[0]


def test_the_config_carries_the_stated_error_model_and_the_settings_shown():
    specs = {'Ka_dye': InputSpec.sigma_pct(5.0), 'h0': InputSpec.sigma_abs(0.2e-6), 'd0': InputSpec.sigma_pct(4.0)}
    errors = ErrorModel(specs=specs, shared=(SharedSource('Host and dye stock', 4.0, ('Ka_dye', 'h0')),))
    form = S.AnalysisForm(n_samples=2048, fixed_seed=True, seed_text='7')

    config = form.config(errors, _LABELS, _NOMINALS)

    # Sensitivity indices split the spread between every source stated, so all of them go.
    assert (config.mode, config.errors, config.n_samples, config.seed) == (SensitivityMode.SOBOL, errors, 2048, 7)

    # A heatmap sweeps two inputs and holds everything else at its set value: only their own
    # uncertainties reach the run, and a source that moves several inputs at once is no axis.
    _heatmap(form, 'Ka_dye', 'h0', span=1.0)
    form.grid = 31
    config = form.config(errors, _LABELS, _NOMINALS)
    assert config.errors == ErrorModel(specs={'Ka_dye': specs['Ka_dye'], 'h0': specs['h0']})
    assert (config.x_key, config.y_key, config.n_steps, config.x_span, config.y_span) == ('Ka_dye', 'h0', 31, 1.0, 1.0)


def test_a_fixed_seed_must_be_a_whole_number_the_analysis_accepts():
    form = S.AnalysisForm(fixed_seed=True, seed_text='12.5')
    errors = ErrorModel(specs={'h0': InputSpec.sigma_pct(5.0)})

    (problem,) = form.problems(errors, _LABELS, _NOMINALS)
    assert problem == 'The fixed seed must be a whole number from 0 to 2,147,483,647.'
    with pytest.raises(ValueError, match='whole number'):
        form.config(errors, _LABELS, _NOMINALS)
    form.seed_text = '2147483647'
    assert form.config(errors, _LABELS, _NOMINALS).seed == 2**31 - 1
    form.fixed_seed = False
    assert form.config(errors, _LABELS, _NOMINALS).seed is None  # fresh draws each run


def test_a_heatmap_axis_that_is_fixed_used_twice_or_shared_only_blocks_the_run_naming_the_input():
    form = _heatmap(S.AnalysisForm(), TITRANT, 'h0')
    assert form.problems(ErrorModel(specs={TITRANT: InputSpec.sigma_pct(7.0)}), _LABELS, _NOMINALS) == [
        '[Host]₀ is a heatmap axis, so it cannot be fixed: set a σ or a range for it under Input uncertainty.'
    ]
    shared = ErrorModel(specs={TITRANT: InputSpec.sigma_pct(7.0)}, shared=(SharedSource('Stock', 3.0, ('h0', 'd0')),))
    (problem,) = form.problems(shared, _LABELS, _NOMINALS)
    assert problem.startswith('[Host]₀ varies only through a shared source')

    _heatmap(form, 'Ka_dye', 'Ka_dye')
    assert form.problems(ErrorModel(specs={'Ka_dye': InputSpec.sigma_pct(5.0)}), _LABELS, _NOMINALS) == [
        'Kₐ,dye is both heatmap axes: choose another input for one of them.'
    ]


@pytest.mark.parametrize(
    ('span', 'spec', 'inside', 'problem'),
    [
        (2.0, InputSpec.sigma_pct(50.0), InputSpec.sigma_pct(49.9), 'runs from −2σ to +2σ: set σ below 50 %'),
        (3.0, InputSpec.sigma_pct(40.0), InputSpec.sigma_pct(33.0), 'runs from −3σ to +3σ: set σ below 33.3 %'),
        (1.0, InputSpec.sigma_pct(100.0), InputSpec.sigma_pct(60.0), 'runs from −1σ to +1σ: set σ below 100 %'),
        (
            2.0,
            InputSpec.sigma_abs(0.5 * _H0),
            InputSpec.sigma_abs(0.499 * _H0),
            'runs from −2σ to +2σ: set σ below half its set value',
        ),
        (3.0, InputSpec.interval_pct(-100.0, 10.0), InputSpec.interval_pct(-99.9, 10.0), 'set “from” above −100 %'),
        (1.0, InputSpec.interval_abs(0.0, 5e-6), InputSpec.interval_abs(0.01e-6, 5e-6), 'set “from” above 0'),
    ],
)
def test_a_heatmap_axis_reaching_zero_at_its_span_blocks_the_run_naming_it_and_the_span(span, spec, inside, problem):
    """A σ axis runs from −span·σ to +span·σ, a range axis over its range: an end at zero cannot be fitted.

    An axis stated in the input's own unit is read against the entered value, so σ =
    2.15 µM on a [Host]₀ of 4.3 µM reaches zero at ±2σ where 2.147 µM does not; σ 40 %
    stays above zero at ±2σ and reaches it at ±3σ.
    """
    form = _heatmap(S.AnalysisForm(), 'h0', 'd0', span)
    other = {'d0': InputSpec.sigma_pct(5.0)}

    (message,) = form.problems(ErrorModel(specs={'h0': spec, **other}), _LABELS, _NOMINALS)
    assert message.startswith('[Host]₀ as a heatmap axis would reach zero')
    assert problem in _plain(message)
    assert form.problems(ErrorModel(specs={'h0': inside, **other}), _LABELS, _NOMINALS) == []


def test_only_an_axis_stated_as_a_sigma_offers_a_span():
    form = _heatmap(S.AnalysisForm(), 'h0', 'Ka_dye')
    errors = ErrorModel(specs={'h0': InputSpec.sigma_pct(3.0), 'Ka_dye': InputSpec.interval_pct(-5.0, 5.0)})
    assert form.spans_shown(errors) == (True, False)


def test_the_axes_follow_the_inputs_of_the_model_chosen():
    form = S.AnalysisForm()
    form.set_inputs(list(_LABELS))
    assert (form.x_key, form.y_key) == ('Ka_dye', 'h0')
    form.x_key = TITRANT
    form.set_inputs(list(_LABELS))
    assert (form.x_key, form.y_key) == (TITRANT, 'h0'), 'an axis the model still has is kept'
    form.set_inputs(['h0', TITRANT])
    assert (form.x_key, form.y_key) == (TITRANT, 'h0')
    form.set_inputs(['fixed_conc', TITRANT])
    assert (form.x_key, form.y_key) == (TITRANT, 'fixed_conc')


def test_the_badge_names_what_the_run_shown_was_made_with_else_the_next_one():
    form = S.AnalysisForm(n_samples=4096)
    assert _plain(S.badge(None, form)) == 'Sobol’ · N = 4096'
    assert _plain(S.badge(F.heatmap_result(), form)) == 'Heatmap · 3 × 3'
    assert _plain(S.badge(F.sobol_result(), form)) == 'Sobol’ · N = 20'


def test_the_cost_of_a_sample_size_is_the_fit_count_of_the_run():
    from core.pipeline.sensitivity import SensitivityConfig, estimated_fit_count

    errors = ErrorModel(specs={k: InputSpec.sigma_pct(3.0) for k in _LABELS})
    # The perturbed fits and the refits, and the fit at the inputs as entered, as the status bar counts them.
    fits = estimated_fit_count(SensitivityConfig(SensitivityMode.SOBOL, 2048, errors), len(_LABELS)) + 1
    assert (
        S.sample_size_note(2048, 4, 4) == f'2 × N = 4,096 samples, {fits:,} fits in all. Each step up doubles the time.'
    )
    # A grid of n × n cells is n² fits and the fit at the inputs as entered, as This run counts it.
    assert [_plain(S.grid_label(n)) for n in S.GRIDS] == [
        '11 × 11 · 122 fits',
        '21 × 21 · 442 fits',
        '31 × 31 · 962 fits',
    ]
    grid = F.heatmap_result()
    fits = {s.name: s.value for s in S.this_run(grid)}['Fits']
    assert _plain(S.grid_label(grid.config.n_steps)).endswith(f'{fits.split(" of ")[1]} fits')


# ---------------------------------------------------------------------------
# The spread and the samples
# ---------------------------------------------------------------------------


def test_the_spread_is_the_budget_s_own_read_as_a_factor():
    """A variance of 0.007056 decades² is 0.084 decades, a factor of 10^0.084 = 1.21 either way.

    Its interval is the variance's read in decades: 0.006561 and 0.007569 decades² are
    0.081 and 0.087 decades.
    """
    spread = S.spread(F.sobol_result(), 'Ka_guest')

    assert _plain(spread.factor) == '×/÷ 1.21'
    assert spread.decades == '1 SD · 0.084 decades'
    assert _plain(spread.centre) == '2.00 × 10⁸ M⁻¹', 'read around the fit at the inputs as entered'
    assert '0.081 – 0.087 decades' in spread.tooltip


def test_a_spread_no_run_could_pin_down_says_so_instead_of_writing_nan():
    result = F.sobol_result()
    result.budget = {'Ka_guest': Budget(np.nan, (np.nan, np.nan), result.budget['Ka_guest'].rows)}

    spread = S.spread(result, 'Ka_guest')

    assert spread.factor == '' and spread.missing == 'Too few fits finished to work the spread out.'
    table = S.budget_table(result, 'Ka_guest')
    # With no variance there is no share for the sources to leave over: n/a, not 0.
    assert [c.value for c in table.rows[-1]] == ['Interactions', '–', '–', 'n/a', '–']


def test_the_histogram_holds_every_sample_the_budget_rests_on_and_marks_the_middle_90_percent():
    result = F.sobol_result()
    usable = result.sample_ka['Ka_guest'][result.sample_usable['Ka_guest']]

    hist = S.histogram(result, None, 'Ka_guest')

    assert hist.counts.sum() == usable.size == 38  # sample 5 and its partner 25 are out of every estimator
    p5, p95 = np.percentile(usable, [5, 95])
    centres = 10 ** ((hist.edges[:-1] + hist.edges[1:]) / 2)
    assert np.array_equal(hist.inside, (centres >= p5) & (centres <= p95))
    assert hist.fold == f'Middle 90{THIN}% of samples span a {p95 / p5:.2f}-fold range'
    # The axis holds every sample and the interval at the inputs as entered.
    assert hist.x_range[0] < math.log10(min(usable.min(), 1.5e8)) and hist.x_range[1] > math.log10(
        max(usable.max(), 2.7e8)
    )


def test_the_histogram_marks_input_aware_only_where_the_fit_reports_it():
    """The samples centre on the inputs as entered; the reported Input-aware reading is set beside them."""
    from core.pipeline.varpro import KaInterval
    from core.units import Q_

    result = F.sobol_result()
    (entered,) = S.histogram(result, None, 'Ka_guest').markers
    assert entered.kind == 'entered' and entered.label == 'Inputs as entered 2.00  [1.50, 2.70]'
    assert entered.x == pytest.approx(math.log10(2e8))

    conditional = F.baseline_fit()
    aware = replace(
        conditional,
        parameters={**conditional.parameters, 'Ka_guest': Q_(1.6e8, '1/M')},
        intervals={'Ka_guest': KaInterval(1.1e8, 2.1e8, False, False, 0.95, 16)},
        input_shifts={'h0': 0.01},
        conditional=conditional,
    )
    markers = S.histogram(result, aware, 'Ka_guest').markers
    assert [m.kind for m in markers] == ['aware', 'entered']
    assert markers[0].label == 'Input-aware 1.60  [1.10, 2.10]'
    assert markers[0].span == pytest.approx((math.log10(1.1e8), math.log10(2.1e8)))
    # A fit taking every input as exact has no input-aware reading to mark.
    assert [m.kind for m in S.histogram(result, conditional, 'Ka_guest').markers] == ['entered']


def test_a_linear_axis_places_the_samples_at_their_ka():
    hist = S.histogram(F.sobol_result(), None, 'Ka_guest', log=False)
    assert not hist.log
    assert hist.markers[0].x == pytest.approx(2e8)
    assert hist.x_range[0] < 1.5e8 < 2.7e8 < hist.x_range[1]


# ---------------------------------------------------------------------------
# Share of the variance, by source
# ---------------------------------------------------------------------------


def test_the_chart_ranks_the_sources_by_their_first_order_index_with_the_run_s_own_whiskers():
    chart = S.index_chart(F.sobol_result(), 'Ka_guest')

    assert [r.key for r in chart.rows] == [TITRANT, 'h0', 'Ka_dye']
    titrant = chart.rows[0]
    assert (titrant.s1, titrant.s1_ci) == (0.6, (0.57, 0.7))
    assert math.isnan(titrant.st) and S.share(titrant.st) == 'n/a', 'an index too few fits pinned down reads n/a'
    # The axis reaches the farthest whisker, 0.25 + 0.2.
    assert chart.lo == 0.0 and chart.hi == pytest.approx(0.7)
    assert [S.share(v) for v in (0.44, 0.036, -0.012)] == ['0.44', '0.036', '−0.012']


@pytest.mark.parametrize(
    ('st_ci', 'expect', 'avoid'),
    [
        ((0.30, 0.45), 'agree within their whiskers', 'unreliable'),
        ((0.10, 0.20), 'wider than the whiskers span', 'agree within'),
    ],
    ids=['whiskers-overlap', 'whiskers-apart'],
)
def test_a_total_order_drawn_below_its_first_order_is_explained_by_the_whiskers(st_ci, expect, avoid):
    """A total order cannot really be below a first order: within the whiskers the source acts on its own;
    a gap wider than them is not sampling noise of one index."""
    result = F.sobol_result()
    result.sobol_s1 = {'Ka_guest': {**result.sobol_s1['Ka_guest'], 'h0': 0.40}}
    result.sobol_st = {'Ka_guest': {**result.sobol_st['Ka_guest'], 'h0': 0.30}}
    result.sobol_s1_ci = {'Ka_guest': {**result.sobol_s1_ci['Ka_guest'], 'h0': (0.35, 0.45)}}
    result.sobol_st_ci = {'Ka_guest': {**result.sobol_st_ci['Ka_guest'], 'h0': st_ci}}

    (note,) = [n for n in S.index_chart(result, 'Ka_guest').notes if 'S<sub>T</sub>' in n]

    assert note.startswith('[Host]<sub>0</sub>: S<sub>T</sub> comes out just below S<sub>1</sub>')
    assert expect in note and avoid not in note


def test_an_index_far_off_the_axis_is_cut_at_its_edge_and_said_to_need_more_samples():
    result = F.sobol_result()
    result.sobol_s1 = {'Ka_guest': {**result.sobol_s1['Ka_guest'], 'Ka_dye': 3.0}}

    chart = S.index_chart(result, 'Ka_guest')

    assert chart.hi == S.INDEX_LIMITS[1]
    assert any(n.startswith('An arrow marks an index or whisker beyond') for n in chart.notes)


def test_the_indices_say_how_many_sample_groups_they_leave_out_counted_in_the_finished_blocks():
    assert not any('sample groups' in n for n in S.index_chart(F.sobol_result(), 'Ka_guest').notes)
    result = replace(F.sobol_result(), sobol_rows_left_out={'Ka_guest': 3})
    assert 'The indices leave out 3 of the 20 sample groups' in ' '.join(S.index_chart(result, 'Ka_guest').notes)
    # A stopped run keeps three blocks of two groups; one group in them could not be completed.
    notes = ' '.join(S.index_chart(F.stopped_result(kept=3), 'Ka_guest').notes)
    assert 'leave out 1 of the 6 sample groups' in notes and 'of the 16' not in notes


def test_a_chart_with_no_index_says_why_it_is_empty():
    result = F.stopped_result(kept=0)
    missing = {'Ka_guest': dict.fromkeys(F.INPUTS, np.nan)}
    no_ci = {'Ka_guest': dict.fromkeys(F.INPUTS, (np.nan, np.nan))}
    result = replace(result, sobol_s1=missing, sobol_st=missing, sobol_s1_ci=no_ci, sobol_st_ci=no_ci)
    assert S.index_chart(result, 'Ka_guest').notes == [
        'No index: the analysis was stopped before any sample block had finished.'
    ]
    failed = replace(F.sobol_result(), sobol_s1=missing, sobol_st=missing, sobol_s1_ci=no_ci, sobol_st_ci=no_ci)
    (note,) = S.index_chart(failed, 'Ka_guest').notes
    # 39 of the 40 samples have a fit while no group has all of its fits: both counts are given together.
    assert note.startswith(
        'No index: 0 of the 20 sample groups have all of their fits, although 39 samples were fitted'
    )
    assert 'Input uncertainty' in note
    one = replace(failed, sobol_rows_left_out={'Ka_guest': 19})
    (note,) = S.index_chart(one, 'Ka_guest').notes
    assert note.startswith('No index: 1 of the 20 sample groups has all of its fits, although 39 samples')


# ---------------------------------------------------------------------------
# The variance budget
# ---------------------------------------------------------------------------


def test_the_budget_shows_the_numbers_of_the_result_it_was_given():
    """Every cell is the budget's own number in the column's power of ten: 0.05 × 0.007056 = 3.528×10⁻⁴ decades²
    for Kₐ,dye is 0.35 at ×10⁻³, the interactions 0.15 × 0.007056 = 1.06×10⁻³."""
    table = S.budget_table(F.sobol_result(), 'Ka_guest')

    assert table.headers == ('Source', 'Stated', 'Elasticity', 'Variance (×10⁻³ decades²)', 'Spread if exact (decades)')
    rows = {c[0].value: c for c in table.rows}
    assert list(rows) == ['Guest (titrant)', '[Host]<sub>0</sub>', 'K<sub>a,dye</sub>', 'Interactions']
    dye = rows['K<sub>a,dye</sub>']
    assert [_plain(c.value) for c in dye] == ['K<sub>a,dye</sub>', 'σ 5 %', '+0.31', '0.35', '0.082']
    assert [c.interval for c in dye[3:]] == ['[0.20, 0.50]', '[0.079, 0.084]']
    assert rows['[Host]<sub>0</sub>'][2].value == '−1.20', 'an input that moves Ka the other way keeps its sign'
    assert rows['Interactions'][3].value == '1.06'
    assert [table.total[3].value, table.total[3].interval] == ['7.06', '[6.56, 7.57]']


def test_the_variances_and_the_interactions_add_up_to_the_whole_variance():
    """What the sources explain alone and what they explain only together make up the spread squared."""
    result = F.sobol_result()
    rows = S.budget_csv_rows(result)
    parts = [row['Variance (decades^2)'] for row in rows if row['Kind'] in ('source', 'interactions')]
    assert sum(parts) == pytest.approx(result.budget['Ka_guest'].sd ** 2, rel=1e-12)


def test_an_interval_is_printed_to_the_figures_that_tell_it_from_its_estimate():
    """``0.050 [0.050, 0.050]`` reads as no uncertainty at all; the ends get the figures that show them."""
    result = F.sobol_result()
    first = result.budget['Ka_guest'].rows[0]
    tight = BudgetRow(first.source, first.variance, first.variance_ci, 0.05, (0.04999, 0.05001), first.elasticity)
    result.budget = {'Ka_guest': replace(result.budget['Ka_guest'], rows=(tight, *result.budget['Ka_guest'].rows[1:]))}

    rows = {c[0].value: c for c in S.budget_table(result, 'Ka_guest').rows}

    assert (rows['K<sub>a,dye</sub>'][4].value, rows['K<sub>a,dye</sub>'][4].interval) == (
        '0.05000',
        '[0.04999, 0.05001]',
    )
    assert (rows['[Host]<sub>0</sub>'][4].value, rows['[Host]<sub>0</sub>'][4].interval) == ('0.075', '[0.072, 0.078]')


def test_the_spread_column_never_shows_a_negative_standard_deviation():
    """The jackknife interval is symmetric, so on a source that explains almost everything its lower end dips
    below zero; a spread cannot be negative."""
    result = F.sobol_result()
    first = result.budget['Ka_guest'].rows[0]
    quiet = BudgetRow(first.source, first.variance, first.variance_ci, 0.004, (-0.004, 0.012), first.elasticity)
    result.budget = {'Ka_guest': replace(result.budget['Ka_guest'], rows=(quiet, *result.budget['Ka_guest'].rows[1:]))}

    rows = {c[0].value: c for c in S.budget_table(result, 'Ka_guest').rows}

    assert rows['K<sub>a,dye</sub>'][4].interval == '[0.000, 0.012]'


def test_the_budget_states_a_range_by_its_two_ends_in_percent_of_the_entered_value():
    rows = {c[0].value: c for c in S.budget_table(F.ranged_result(), 'Ka_guest').rows}

    assert _plain(rows['K<sub>a,dye</sub>'][1].value) == '−6 % to +4 %'
    # [Host]₀ is entered as 4.1–4.4 µM of 4.3 µM: −4.65 % to +2.33 % of it.
    low, high = (f'{value:+.3g}'.replace('-', '−') for value in F.H0_RANGE_PCT)
    assert _plain(rows['[Host]<sub>0</sub>'][1].value) == f'{low} % to {high} %'


def test_a_shared_source_and_the_additions_are_ranked_beside_the_inputs():
    """Both are sources of the spread: each gets a bar and a budget row. The additions are no single offset, so they
    carry no elasticity and no what-if, and a note says the reported interval holds them."""
    result = F.shared_source_result()

    names = [r.name for r in S.index_chart(result, 'Ka_guest').rows]
    assert names == ['Stock A', '[Host]<sub>0</sub>', S.ADDITIONS_LABEL]
    table = S.budget_table(result, 'Ka_guest')
    additions = next(r for r in table.rows if r[0].value == S.ADDITIONS_LABEL)
    assert additions[2].value == '–' and _plain(additions[1].value) == 'σ 1 % each addition'
    assert table.notes == [S.ADDITIONS_NOTE]
    assert S.what_if_sources(result, 'Ka_guest') == [F.SHARED, 'h0']


def test_a_shared_source_name_from_the_user_is_escaped():
    from core.pipeline.inputs import shared_key

    assert S.source_label(None, shared_key('<b>A & B</b>')) == '&lt;b&gt;A &amp; B&lt;/b&gt;'


# ---------------------------------------------------------------------------
# What if one source were known better
# ---------------------------------------------------------------------------

_KNOWN = WhatIf(sd=0.056, sd_reweighted=0.057, effective_samples=1111.4, largest_after='h0')


def test_the_what_if_leads_with_the_re_weighted_answer_and_asks_for_a_share_of_what_was_stated(monkeypatch):
    asked = []
    monkeypatch.setattr(S, 'what_if', lambda result, key, source, ratio: asked.append((key, source, ratio)) or _KNOWN)

    answer = S.what_if_answer(F.sobol_result(), 'Ka_guest', 'Ka_dye', 0.25)

    assert asked == [('Ka_guest', 'Ka_dye', 0.25)]
    assert (_plain(answer.before), _plain(answer.after)) == ('×/÷ 1.21', f'×/÷ {10**0.057:.2f}')
    assert answer.lead == 'and the spread of K<sub>a</sub> guest shrinks from'
    assert answer.detail == (
        '0.084 → 0.057 decades; [Host]<sub>0</sub> would then be the largest item. Read from the samples '
        're-weighted to the narrower uncertainty (1,111 effective samples); the first-order formula gives 0.056.'
    )


def test_the_what_if_says_why_no_cross_check_backs_it(monkeypatch):
    """Too few samples carrying weight and a source made exact are different reasons, and read as different ones."""
    answers = iter(
        [
            replace(_KNOWN, sd_reweighted=None, effective_samples=31.0),
            replace(_KNOWN, sd_reweighted=None, effective_samples=None),
        ]
    )
    monkeypatch.setattr(S, 'what_if', lambda *args: next(answers))

    few = S.what_if_answer(F.sobol_result(), 'Ka_guest', 'Ka_dye', 0.25)
    exact = S.what_if_answer(F.sobol_result(), 'Ka_guest', 'Ka_dye', 0.0)

    assert few.detail.startswith('0.084 → 0.056 decades')  # the formula states the spread
    assert few.detail.endswith('too few samples carry weight at this reduction to read it from them.')
    assert exact.detail.endswith('with the source exact there is no sample left to re-weight.')


def test_the_what_if_offers_reductions_of_what_was_stated_for_one_source():
    """A range is reduced by shrinking it about its centre, so it is asked for as ± half its width."""
    assert [_plain(t) for _r, t in S.what_if_targets(F.sobol_result(), 'Ka_dye')] == [
        'σ 3.75 %',
        'σ 2.5 %',
        'σ 1.25 %',
        'Exact',
    ]
    assert [_plain(t) for _r, t in S.what_if_targets(F.ranged_result(), 'Ka_dye')][:2] == ['±3.75 %', '±2.5 %']


def test_the_what_if_answers_from_the_run_without_a_fit():
    """Exact is the budget's own spread with the source known exactly: its row's spread if exact."""
    result = F.sobol_result()
    answer = S.what_if_answer(result, 'Ka_guest', TITRANT, 0.0)
    row = next(r for r in result.budget['Ka_guest'].rows if r.source == TITRANT)
    left = math.sqrt(F.VARIANCE - row.variance)  # the whole variance less what the source explains alone
    assert answer.detail.startswith(f'0.084 → {left:.3f} decades')


# ---------------------------------------------------------------------------
# Withheld constants, fits on the bounds, stopped runs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ('reason', 'words'),
    [
        ('baseline_on_bound', 'ran to the edge of its bounds'),
        ('open_interval', 'no upper or lower limit at the inputs as entered'),
        ('homogeneity', 'do not follow the inputs smoothly'),
    ],
)
def test_a_withheld_constant_gets_its_reason_and_none_of_its_numbers(reason, words):
    result = F.sobol_result()
    result.withheld = {'Ka_guest': reason}
    result.homogeneity = {'Ka_guest': -0.2}

    (block,) = S.ka_blocks(result, None)

    (callout,) = block.callouts
    assert callout.tone == 'warning' and words in callout.body
    assert 'no share, spread or elasticity is given for Kₐ guest' in callout.body
    assert block.chart is None and block.budget is None and block.what_if == []
    assert block.spread.factor == '' and block.histogram is not None, 'the samples stay on show, no number read'
    (row,) = S.budget_csv_rows(result)
    assert (row['Kind'], row['Item']) == ('note', callout.body)
    assert all(row[column] == '' for column in S.BUDGET_CSV_COLUMNS)


def test_an_open_interval_note_names_the_side_the_data_leave_open():
    from core.pipeline.varpro import KaInterval

    result = F.sobol_result()
    result.withheld = {'Ka_guest': 'open_interval'}
    result.baseline_fit.intervals = {'Ka_guest': KaInterval(1.5e8, 9e9, False, True, 0.95, 16)}
    assert 'no upper limit at the inputs as entered' in S.withheld_note(result, 'Ka_guest')


def test_one_withheld_constant_leaves_the_other_its_numbers():
    result = F.two_ka_result()
    result.withheld = {'Ka_HG2': 'open_interval'}
    first, second = S.ka_blocks(result, None)
    assert first.budget is not None and first.chart is not None and not first.callouts
    assert second.budget is None and second.callouts


def test_fits_on_the_ka_bounds_are_counted_above_the_numbers_they_inflate():
    result = F.sobol_result()
    assert S.on_bound_note(result, 'Ka_guest') is None, 'a clean run carries no note'
    total = result.config.n_samples * (len(result.sources) + 2)  # every matrix of the design, 100 fits

    result.n_on_bound = {'Ka_guest': 1}
    one = S.on_bound_note(result, 'Ka_guest')
    assert one.startswith(f'In 1 of {total} fits (1{THIN}%) Kₐ guest ran to the edge of its bounds; that fit jumps')
    result.n_on_bound = {'Ka_guest': 1234}
    result.config = replace(result.config, n_samples=4096)
    assert 'In 1,234 of 20,480 fits' in S.on_bound_note(result, 'Ka_guest')
    (block,) = S.ka_blocks(result, None)
    assert block.callouts[0].title == 'Fits on the Kₐ bounds' and block.budget is not None


def test_a_stopped_run_is_said_once_in_the_blocks_it_kept():
    text = S.stopped_sentence(F.stopped_result(kept=3))
    assert text == (
        f'The analysis was stopped after 3 of {_SOBOL_BLOCKS} sample blocks had finished: everything here rests on '
        'the 6 sample groups of those blocks.'
    )
    assert S.stopped_sentence(F.sobol_result()) == ''
    assert S.stopped_sentence(F.stopped_result(kept=0)).startswith(
        f'The analysis was stopped before any of its {_SOBOL_BLOCKS} sample blocks had finished'
    )


# ---------------------------------------------------------------------------
# Callouts
# ---------------------------------------------------------------------------


def _conflicted():
    """A fit whose stated inputs conflict with the data, as its diagnostics judge it."""
    from core.pipeline.diagnostics import Conflict, FitDiagnostics, Verdict

    conflict = Conflict(q=30.0, k=3, p_value=1e-6, weights=(0.5, 0.8, 0.9))
    diagnostics = FitDiagnostics(
        conditional_misfit=None, misfit=None, conflict=conflict, verdict=Verdict.INPUTS_CONFLICT
    )
    return replace(F.baseline_fit(), diagnostics=diagnostics)


def test_a_conflict_of_the_fit_is_said_about_the_inputs_together():
    result = F.sobol_result()
    specs = S.callouts(result, _conflicted(), None)
    (conflict,) = [s for s in specs if s.title == 'Inputs conflict']
    assert conflict.tone == 'warning' and conflict.action == 'Review in Ka confidence'
    assert conflict.body.startswith('Together, the inputs moved further from their entered values than you stated.')
    assert 'The samples centre on the inputs as entered' in conflict.body
    assert not any(name in conflict.body for name in ('[Host]', '[Dye]', 'Kₐ,dye', 'titrant'))
    # Without a conflict the run is said to be no confidence interval, with the way to the one there is.
    (note,) = S.callouts(result, F.baseline_fit(), None)
    assert (note.title, note.action) == ('Not a confidence interval', S.COMPARE)


def test_a_note_hiding_the_run_is_all_that_is_said_of_it():
    assert S.callouts(F.sobol_result(), _conflicted(), 'The input uncertainties have changed.') == [
        S.R.CalloutSpec('neutral', 'Results hidden', 'The input uncertainties have changed.')
    ]


def test_before_a_run_the_refusal_to_vary_nothing_is_said_where_the_results_would_be():
    (spec,) = S.callouts(None, None, None, nothing_varies=True)
    assert (spec.title, spec.body, spec.action) == ('Nothing to vary', S.NOTHING_VARIES, S.EDIT_INPUTS)
    assert S.callouts(None, None, None, nothing_varies=True, running=True) == []
    (failed,) = S.callouts(None, None, None, error='The analysis stopped because one of the re-fits failed.')
    assert (failed.tone, failed.title) == ('warning', 'Analysis failed')


# ---------------------------------------------------------------------------
# The heatmap
# ---------------------------------------------------------------------------


def test_a_heatmap_puts_each_axis_in_its_input_s_unit_and_the_titrant_in_percent():
    (hm,) = S.heatmaps(F.heatmap_result(), {'h0': 'µM'})

    assert hm.x_title == '[Host]₀ (µM)'
    np.testing.assert_allclose(hm.x, [4.3 * 0.9, 4.3, 4.3 * 1.1])
    assert hm.y_title == 'Guest (titrant), change (%)'
    np.testing.assert_allclose(hm.y, [-10.0, 0.0, 10.0])
    assert hm.entered == pytest.approx((4.3, 0.0))
    assert math.isnan(hm.values[2, 1]), 'a cell with no fit stays empty'
    assert hm.values[1, 1] == pytest.approx(math.log10(2e8)) and hm.lo < hm.values[1, 1] < hm.hi


def test_the_heatmap_readout_names_both_inputs_and_reads_ka_its_change_and_r2():
    (hm,) = S.heatmaps(F.heatmap_result(), {'h0': 'µM'})

    title, rows = S.heatmap_readout(hm, 2, 0)
    assert _plain(title) == '[Host]₀ 4.73 µM · Guest (titrant) −10 %'
    assert [(n, _plain(v)) for n, v in rows] == [
        ('Kₐ guest', '2.00 × 10⁸ M⁻¹'),
        ('Change from entered', '0 %'),
        ('R²', '0.9950'),
    ]
    assert S.heatmap_readout(hm, 1, 2)[1] == [('Kₐ guest', 'no fit')]


def test_a_linear_colour_scale_reads_ka_itself():
    (hm,) = S.heatmaps(F.heatmap_result(), {'h0': 'µM'}, log=False)
    assert hm.values[0, 0] == 1.8e8 and hm.lo == 1.8e8 and hm.hi == 2.2e8
    assert hm.bar_title == 'Kₐ guest (10⁸ M⁻¹)'


# ---------------------------------------------------------------------------
# The facts of the run, Kₐ against each source, the CSV
# ---------------------------------------------------------------------------


def test_this_run_counts_the_samples_and_fits_and_names_the_seed():
    stats = {s.name: s for s in S.this_run(F.sobol_result(), seconds=8.2, workers=15)}
    assert stats['Samples fitted'].value == '39 of 40'
    assert stats['Fits'].note == f'8 of {_SOBOL_BLOCKS} sample blocks'
    assert stats['Duration'].value == '8 s' and stats['Duration'].note == '15 worker processes'
    assert S.seed_stat(F.sobol_result()).note == 'Enter it under Fixed seed to repeat this run exactly.'
    stopped = {s.name: s for s in S.this_run(F.stopped_result(kept=3))}
    # The fits counted include those of the block the stop cut short: the note says they are all the fits made,
    # not the fits of the blocks that finished.
    assert stopped['Fits'].note == f'every fit made before the stop; 3 of {_SOBOL_BLOCKS} sample blocks finished'
    assert 'Stopped' in stopped
    assert S.seed_stat(F.heatmap_result()) is None, 'a heatmap draws nothing at random'
    grid = {s.name: s for s in S.this_run(F.heatmap_result())}
    assert grid['Fits'].note == '1 cell with no fit, and the fit at the inputs as entered'


def test_ka_against_each_source_plots_every_fitted_sample_against_its_draw():
    result = F.sobol_result()
    plots, note = S.source_plots(result, 'Ka_guest')

    assert [p.key for p in plots] == [TITRANT, 'h0', 'Ka_dye']
    titrant = plots[0]
    assert titrant.x.size == titrant.y.size == 39  # every sample with a fit, sample 5 left out
    np.testing.assert_array_equal(titrant.x, np.delete(result.sample_offsets_pct[TITRANT], 5))
    assert note == ''
    _plots, note = S.source_plots(F.shared_source_result(), 'Ka_guest')
    assert note.startswith(f'{S.ADDITIONS_LABEL} is not plotted: each sample draws one error per addition')


def test_the_csv_carries_the_run_s_floats_and_its_seed_and_never_reads_nan():
    result = F.sobol_result()
    result.seed_used = 1234
    rows = S.budget_csv_rows(result)

    assert all(row['Seed'] == 1234 for row in rows)
    source = next(r for r in rows if r['Kind'] == 'source' and r['Item'] == 'Kₐ,dye')
    assert source['S1'] == 0.05 and source['Variance (decades^2)'] == pytest.approx(0.05 * F.VARIANCE)
    assert source['Stated uncertainty'] == 'σ 5 %'
    inputs = {r['Item']: r['Elasticity'] for r in rows if r['Kind'] == 'input'}
    assert inputs == {'Kₐ,dye': 0.31, '[Host]₀': -1.2, '[Dye]₀': 0.62, 'Guest (titrant)': 0.95}
    titrant = next(r for r in rows if r['Kind'] == 'source' and r['Item'] == 'Guest (titrant)')
    assert titrant['S1'] == 0.6
    result.budget = {'Ka_guest': Budget(np.nan, (np.nan, np.nan), result.budget['Ka_guest'].rows)}
    assert all(
        value != 'nan' and not (isinstance(value, float) and math.isnan(value))
        for r in S.budget_csv_rows(result)
        for value in r.values()
    )


def test_the_budget_is_refused_as_a_csv_where_the_run_gives_none():
    assert S.budget_refusal(F.sobol_result()) is None
    assert S.budget_refusal(F.heatmap_result()).startswith('The analysis shown is a heatmap.')
    withheld = F.sobol_result()
    withheld.withheld = {'Ka_guest': 'open_interval'}
    assert 'says why its numbers are withheld' in S.budget_refusal(withheld)
    empty = F.sobol_result()
    empty.budget = {'Ka_guest': Budget(np.nan, (np.nan, np.nan), empty.budget['Ka_guest'].rows)}
    assert 'too few of its samples have a fit' in S.budget_refusal(empty)


def test_the_sources_listed_are_the_ones_the_run_varies():
    errors = ErrorModel(
        specs={'h0': InputSpec.sigma_pct(3.0), 'd0': InputSpec.sigma_pct(0.0)},
        shared=(SharedSource('Stock', 2.0, ('h0', 'd0')),),
    )
    listed = [(s.name, _plain(s.stated)) for s in S.stated_sources(errors, _LABELS, {'h0': 'M', 'd0': 'M'})]
    assert listed == [('[Host]₀', 'σ 3 %'), ('Stock', 'σ 2 %')]


# ---------------------------------------------------------------------------
# Rules a review found unpinned
# ---------------------------------------------------------------------------


def test_a_withheld_constant_keeps_its_samples_with_no_figure_read_off_them():
    """Its refits describe the bounds of the search, so no spread, fold or middle 90 % is read off its samples."""
    result = F.sobol_result()
    result.withheld = {'Ka_guest': 'open_interval'}

    hist = S.histogram(result, None, 'Ka_guest')

    assert hist.counts.sum() == 38, 'every sample stays on show'
    assert not any(ch.isdigit() for ch in hist.fold)
    assert hist.inside.all(), 'no middle 90 % is marked off'


@pytest.mark.parametrize(
    'seed',
    ['²', '０١', '-1', '2147483648', '9' * 5000],
    ids=['superscript', 'other-script', 'negative', 'big', 'paste'],
)
def test_a_seed_that_is_no_whole_number_in_range_is_refused_not_raised(seed):
    """Digits int() cannot read, digits of another script and numbers out of range are all refused in words,
    however many digits are pasted (int() refuses more than 4,300)."""
    form = S.AnalysisForm(fixed_seed=True, seed_text=seed)
    assert form.seed() is None
    assert form.problems(ErrorModel(specs={'h0': InputSpec.sigma_pct(5.0)}), _LABELS, _NOMINALS) == [
        'The fixed seed must be a whole number from 0 to 2,147,483,647.'
    ]


def test_a_heatmap_axis_stated_in_its_own_unit_against_a_zero_value_is_left_to_input_uncertainty():
    """[Host]₀ entered as 0 with σ in µM has no value to read the σ against: Input uncertainty says so, and the
    axis check raises nothing while the user types."""
    form = _heatmap(S.AnalysisForm(), 'h0', 'd0')
    errors = ErrorModel(specs={'h0': InputSpec.sigma_abs(2e-7), 'd0': InputSpec.sigma_pct(5.0)})
    assert form.problems(errors, _LABELS, {**_NOMINALS, 'h0': 0.0}) == []
    assert form.problems(errors, _LABELS, {k: v for k, v in _NOMINALS.items() if k != 'h0'}) == []


def test_a_stopped_run_counts_its_samples_in_the_blocks_it_kept():
    """Three of eight blocks of two groups kept: 12 samples, one of them unfitted. The dropped blocks are no
    failed fits, so 32 samples is no count of this run."""
    stats = {s.name: s for s in S.this_run(F.stopped_result(kept=3))}
    assert stats['Samples fitted'].value == '11 of 12'
    assert not any('32' in s.value for s in stats.values())
    # Stopped before any block: there are no samples to count, and the stop says so.
    stats = {s.name: s for s in S.this_run(F.stopped_result(kept=0))}
    assert 'Samples fitted' not in stats and 'Stopped' in stats


def test_one_run_counts_its_baseline_fit_wherever_its_fits_are_counted():
    """The status bar, the cost dialog and the progress count the fit at the inputs as entered: so do the Sample
    size note and This run."""
    result = F.sobol_result()
    assert {s.name: s.value for s in S.this_run(result)}['Fits'] == f'{result.n_success + 1:,}'
    grid = F.heatmap_result()
    assert {s.name: s.value for s in S.this_run(grid)}['Fits'] == f'{grid.n_success + 1} of {grid.n_planned + 1}'
    # A run with nothing to vary is refused, so no fit count is quoted for it.
    assert 'fits' not in S.sample_size_note(1024, 0, 4)


@pytest.mark.parametrize('reason', ['baseline_on_bound', 'open_interval', 'homogeneity'])
def test_each_withheld_reason_is_one_sentence_that_reads_on(reason):
    result = F.sobol_result()
    result.withheld = {'Ka_guest': reason}
    result.homogeneity = {'Ka_guest': -0.2}
    note = S.withheld_note(result, 'Ka_guest')
    assert ': so' not in note and ', so no share, spread or elasticity is given' in note


def test_the_homogeneity_reason_states_the_identity_by_a_factor():
    """Concentrations × c and binding constants × 1/c give Kₐ / c: a factor, not a percentage either way."""
    result = F.sobol_result()
    result.withheld = {'Ka_guest': 'homogeneity'}
    result.homogeneity = {'Ka_guest': -0.2}
    note = S.withheld_note(result, 'Ka_guest')
    assert 'multiplying every concentration by a factor' in note
    assert 'dividing every entered binding constant by it' in note and 'by exactly that factor' in note
    assert 'percentage' not in note


def test_a_run_stopped_during_its_elasticity_refits_shows_no_nan_and_says_only_that_it_stopped(monkeypatch):
    """Stopped after the baseline and two refits, before the first sample block: the refits a stop leaves unrun did
    not fail, so nothing says Kₐ jumps, and an elasticity with no value reads as none, never ``nan``."""
    import core.pipeline.sensitivity as sens
    from core.assays.ida import IDAAssay
    from core.data_processing.measurement_set import MeasurementSet
    from core.pipeline.fit_pipeline import FitConfig
    from core.pipeline.sensitivity import SensitivityConfig
    from core.units import Q_
    from tests.conftest import IDA_TRUE, _make_ida_data

    def fake_fit(ms, assay_cls, x_base, base_conditions, offsets, fit_config, *_):
        signal = dict.fromkeys(('I0', 'I_dye_free', 'I_dye_bound'), 0.0)
        return {'Ka_guest': 10.0 ** (8 + offsets.get('h0', 0.0)), **signal}, 1.0, 1.0

    monkeypatch.setattr(sens, '_fit_perturbed', fake_fit)
    x, y = _make_ida_data(IDA_TRUE, n_points=20)
    ms = MeasurementSet(concentrations=x, signals=y.reshape(1, -1), replica_ids=('r0',))
    conditions = {k: Q_(IDA_TRUE[k], u) for k, u in (('Ka_dye', '1/M'), ('h0', 'M'), ('d0', 'M'))}
    finished: list[int] = []
    result = sens.run_sensitivity(
        ms,
        IDAAssay,
        conditions,
        FitConfig(),
        SensitivityConfig(SensitivityMode.SOBOL, 1024, ErrorModel(specs={'h0': InputSpec.sigma_pct(3.0)}), seed=1),
        max_workers=1,
        progress=lambda done, total: finished.append(done),
        should_cancel=lambda: len(finished) >= 3,  # the baseline and two refits
    )
    assert (result.stopped, result.n_blocks_finished) == (True, 0)

    (block,) = S.ka_blocks(result, None)
    cells = [cell.value for row in block.budget.rows for cell in row]
    assert not any('nan' in value for value in cells)
    texts = [*block.chart.notes, *(c.body for c in block.callouts), *(c.body for c in S.callouts(result, None, None))]
    assert any(t.startswith('No index: the analysis was stopped before any sample block') for t in texts)
    assert not any('smoothly' in t or 'gave no fit' in t for t in texts)


def test_each_source_plot_opens_on_the_range_entered_and_labels_both_its_ends():
    """A range opens on exactly its ends, an absolute one in percent of the entered value, both ends labelled
    however narrow; a σ, which has no ends, opens on ± its farthest sample with round ticks only."""
    result = F.ranged_result()
    plots = {p.key: p for p in S.source_plots(result, 'Ka_guest')[0]}

    assert plots['Ka_dye'].x_range == pytest.approx((-6.0, 4.0))
    assert {'−6', '4'} <= {text for _v, text in plots['Ka_dye'].x_ticks}
    assert plots['h0'].x_range == pytest.approx(F.H0_RANGE_PCT)
    assert {'−4.65', '2.33'} <= {text for _v, text in plots['h0'].x_ticks}
    reach = float(np.max(np.abs(result.sample_offsets_pct[TITRANT])))
    assert plots[TITRANT].x_range == pytest.approx((-reach, reach))
    assert all(float(text.replace('−', '-')) == round(v) for v, text in plots[TITRANT].x_ticks)


def test_the_saved_figure_states_what_qualifies_each_constant_s_numbers():
    """A withheld constant's reason, fits on the Kₐ bounds and the chart's notes travel with the figure, and its
    caption reads as a sentence whatever the spread."""
    result = F.sobol_result()
    result.withheld = {'Ka_guest': 'baseline_on_bound'}
    (block,) = S.ka_blocks(result, None)
    caption = S.figure_caption(result, block)
    assert 'callout' not in caption and 'Not given' not in caption
    assert any('ran to the edge of its bounds' in note for note in S.figure_notes(block))

    result = F.sobol_result()
    result.n_on_bound = {'Ka_guest': 7}
    result.sobol_rows_left_out = {'Ka_guest': 3}
    (block,) = S.ka_blocks(result, None)
    notes = S.figure_notes(block)
    assert any(n.startswith('Fits on the Kₐ bounds') for n in notes)
    assert any('leave out 3 of the 20 sample groups' in n for n in notes)


def test_a_new_run_going_is_said_only_where_run_state_shows():
    """The last result stays on show under its own callouts; no callout says a run is going."""
    titles = [c.title for c in S.callouts(F.sobol_result(), None, None, running=True)]
    assert titles == ['Not a confidence interval']


def test_the_empty_canvas_names_only_the_steps_still_to_take():
    """A session with data and a varying source is told to run, not to state what it already stated."""
    assert S.empty_sentence(True, True, '⌘R') == 'No analysis yet. Choose Run analysis (⌘R).'
    assert 'Input uncertainty' in S.empty_sentence(True, False, '⌘R')
    no_data = S.empty_sentence(False, True, '⌘R')
    assert 'Load data' in no_data and 'Input uncertainty' not in no_data
