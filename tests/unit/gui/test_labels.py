"""Tests for gui.plotting.labels — HTML and Unicode formatting."""

from gui.plotting.labels import (
    fmt_interval_html,
    fmt_interval_plain,
    fmt_param,
    fmt_r2,
    fmt_unit_html,
    fmt_unit_pretty,
    plain_label,
)


class TestFmtParam:
    def test_known_keys(self):
        assert fmt_param('Ka_guest') == '<b>K<sub>a(G)</sub></b>'
        assert fmt_param('Ka_dye') == '<b>K<sub>a(D)</sub></b>'
        assert fmt_param('I0') == '<b>I<sub>0</sub></b>'
        assert fmt_param('I_dye_free') == '<b>I<sub>D</sub></b>'
        assert fmt_param('I_dye_bound') == '<b>I<sub>HD</sub></b>'
        assert fmt_param('slope') == '<b>slope</b>'
        assert fmt_param('intercept') == '<b>intercept</b>'

    def test_unknown_falls_back(self):
        assert fmt_param('unknown_param') == 'unknown_param'


class TestFmtUnitHtml:
    def test_reciprocal(self):
        result = fmt_unit_html('1/M')
        assert 'M' in result
        assert '<sup>−1</sup>' in result

    def test_empty(self):
        assert fmt_unit_html('') == ''

    def test_signal_alias_not_garbled(self):
        """The registry's 'a.u.' y-unit alias must format like 'au', not the
        'u a' pint emits when it parses the dots as multiplication (L3)."""
        assert fmt_unit_html('a.u.') == fmt_unit_html('au')
        assert 'u a' not in fmt_unit_html('a.u.')


class TestFmtUnitPretty:
    def test_reciprocal(self):
        result = fmt_unit_pretty('1/M')
        assert 'M' in result
        assert '⁻¹' in result

    def test_empty(self):
        assert fmt_unit_pretty('') == ''

    def test_au_per_M(self):
        result = fmt_unit_pretty('au/M')
        # pint formats 'au' as 'a.u.'
        assert 'a.u.' in result or 'au' in result

    def test_signal_alias_not_garbled(self):
        """'a.u.' must format like 'au', not the 'u·a' pint emits from the dots (L3)."""
        assert fmt_unit_pretty('a.u.') == fmt_unit_pretty('au')
        assert 'u·a' not in fmt_unit_pretty('a.u.')


def test_fmt_sci_reads_plainly_at_every_magnitude():
    """Hundreds and thousands read as numbers or ×10ⁿ, never as ``1.5e+02``."""
    from gui.plotting.labels import fmt_sci

    assert fmt_sci(150) == '150'
    assert fmt_sci(999) == '1.0×10³'
    assert fmt_sci(3218.73, 3) == '3.22×10³'
    assert fmt_sci(9999) == '1.0×10⁴'
    assert fmt_sci(56800) == '5.7×10⁴'
    assert fmt_sci(0.0123) == '0.012'
    assert fmt_sci(1.7e8) == '1.7×10⁸'
    assert fmt_sci(3.3e-6) == '3.3×10⁻⁶'


class TestFmtR2:
    def test_near_one_never_reads_as_one(self):
        """An imperfect fit must not be shown as a perfect one, however close it gets."""
        assert float(fmt_r2(0.999999)) < 1.0
        assert float(fmt_r2(1.0 - 1e-13)) < 1.0

    def test_distance_below_one_stays_visible(self):
        """Two decimals of the gap to 1 survive, so 0.999984 does not flatten to 0.99998."""
        assert fmt_r2(0.999984) == '0.999984'
        assert fmt_r2(0.9908) == '0.9908'

    def test_exactly_one_reads_as_one(self):
        assert fmt_r2(1.0) == '1.0000'


class TestFmtInterval:
    """The one wording every reported interval uses: numbers where the data close a side, words where they do not."""

    def test_a_closed_interval_shows_both_endpoints(self):
        assert fmt_interval_plain('1.3×10⁸', '1.9×10⁸', False, False) == '[1.3×10⁸, 1.9×10⁸]'
        assert fmt_interval_html('1.3×10⁸', '1.9×10⁸', False, False) == '[1.3×10⁸, 1.9×10⁸]'

    def test_an_open_side_says_so_in_words_and_shows_no_number_there(self):
        """The endpoint of an open side is where the profile stopped, not a limit — printing it would claim one."""
        upper = fmt_interval_plain('1.3×10⁸', '1×10¹²', False, True)
        assert upper == '[1.3×10⁸, no upper limit]'
        assert '10¹²' not in upper

        lower = fmt_interval_plain('1×10⁻⁸', '1.9×10⁸', True, False)
        assert lower == '[no lower limit, 1.9×10⁸]'
        assert '10⁻⁸' not in lower

    def test_neither_side_closed_reads_as_one_statement(self):
        assert fmt_interval_plain('1e-8', '1e12', True, True) == '[not limited by the data]'

    def test_the_html_form_marks_words_as_prose_and_keeps_the_same_wording(self):
        """In a column of numbers the words have to read as words, but both forms must say the same thing."""
        from gui.plotting.labels import plain_label

        for args in (('1.3', '1.9', False, True), ('1.3', '1.9', True, False), ('1.3', '1.9', True, True)):
            html = fmt_interval_html(*args)
            assert '<i>' in html
            assert plain_label(html) == fmt_interval_plain(*args)


class TestPlainLabel:
    def test_condition_labels_of_every_assay_flatten(self):
        """Every condition label in the GUI reads as plain text with no markup left."""
        from core.assays.registry import AssayType
        from gui.widgets.assay_conditions import condition_fields

        for assay_type in AssayType:
            for field in condition_fields(assay_type):
                text = plain_label(field.label)
                assert '<' not in text and '>' not in text
                assert not any(ch in '0123456789' for ch in text), f'{field.label} kept a baseline digit'

    def test_real_labels(self):
        assert plain_label('[Host]<sub>0</sub>') == '[Host]₀'
        assert plain_label('[Dye]<sub>0</sub>') == '[Dye]₀'
        assert plain_label('K<sub>a,dye</sub>') == 'Ka,dye'

    def test_superscript_units(self):
        assert plain_label('M<sup>−1</sup>') == 'M⁻¹'

    def test_plain_text_passes_through(self):
        assert plain_label('Guest') == 'Guest'


# ---------------------------------------------------------------------------
# What the diagnostics of a fit say, in words
# ---------------------------------------------------------------------------


def _shift(key, fraction, z=None, at_edge=False):
    from core.pipeline.diagnostics import InputShift

    return InputShift(key=key, fraction=fraction, z=z, at_edge=at_edge)


def _diagnostics(verdict, *, conditional=None, misfit=None, conflict=None):
    from core.pipeline.diagnostics import FitDiagnostics, Verdict

    return FitDiagnostics(conditional_misfit=conditional, misfit=misfit, conflict=conflict, verdict=Verdict(verdict))


def _f_test(statistic, p_value, dof=(9, 72)):
    from core.pipeline.diagnostics import MisfitTest

    return MisfitTest('lack_of_fit', statistic, p_value, dof=dof)


def _runs(runs, expected, p_value):
    from core.pipeline.diagnostics import MisfitTest

    return MisfitTest('runs', float(runs), p_value, expected=expected)


_LABELS = {'h0': '[Host]₀', '__titrant__': 'Guest (titrant)'}


class TestFmtP:
    """A p-value reads as a number while its digits mean something, and as a bound below that."""

    def test_a_p_value_reads_as_two_significant_figures(self):
        from gui.plotting.labels import fmt_p

        assert fmt_p(0.55) == 'p = 0.55'
        assert fmt_p(0.41) == 'p = 0.41'
        assert fmt_p(0.0123) == 'p = 0.012'

    def test_a_p_value_below_the_floor_is_written_as_a_bound(self):
        """The references are Monte-Carlo quadratures with an error of ~5e-4, so smaller digits are noise."""
        from gui.plotting.labels import fmt_p

        assert fmt_p(0.0) == 'p < 0.001'
        assert fmt_p(3e-7) == 'p < 0.001'
        assert fmt_p(0.001) == 'p = 0.001'

    def test_a_p_value_that_would_round_to_one_is_written_as_a_bound(self):
        """'p = 1' reads as a test that is certain; what a large p says is that it found nothing."""
        from gui.plotting.labels import fmt_p

        assert fmt_p(0.9997) == 'p > 0.99'
        assert fmt_p(1.0) == 'p > 0.99'
        assert fmt_p(0.996) == 'p > 0.99'
        assert fmt_p(0.99) == 'p = 0.99'


class TestFmtShift:
    """Where the fit put one input: the percentage it moved, and how that compares with the stated uncertainty."""

    def test_a_sigma_input_reads_as_a_percentage_and_a_multiple_of_its_sigma(self):
        from gui.plotting.labels import fmt_shift

        assert fmt_shift(_shift('h0', -0.114, z=-3.8), '[Host]₀', html=False) == '[Host]₀ −11.4 % (3.8 σ)'
        assert fmt_shift(_shift('h0', 0.093, z=3.1), '[Host]₀', html=False) == '[Host]₀ +9.3 % (3.1 σ)'

    def test_an_input_stated_as_a_range_says_when_it_rests_on_an_end_of_it(self):
        from gui.plotting.labels import fmt_shift

        text = fmt_shift(_shift('d0', -0.06, at_edge=True), '[Dye]₀', html=False)
        assert text == '[Dye]₀ −6.0 % (at the edge of its range)'

    def test_a_range_input_inside_its_range_claims_no_multiple_of_a_sigma_it_has_none_of(self):
        from gui.plotting.labels import fmt_shift

        assert fmt_shift(_shift('d0', -0.06), '[Dye]₀', html=False) == '[Dye]₀ −6.0 %'


class TestVerdictSentence:
    """The four verdicts, in the words design section 3 fixes."""

    def test_consistent_quotes_the_test_that_passed(self):
        from gui.plotting.labels import verdict_sentence

        d = _diagnostics('consistent', conditional=_f_test(0.9, 0.55), misfit=_f_test(0.9, 0.55))
        assert verdict_sentence(d, {}, _LABELS, html=False) == (
            'The model and the entered inputs describe the data (lack-of-fit F(9, 72) = 0.9, p = 0.55).'
        )

    def test_consistent_with_one_signal_quotes_the_runs_test(self):
        from gui.plotting.labels import verdict_sentence

        d = _diagnostics('consistent', conditional=_runs(6, 7.0, 0.41), misfit=_runs(6, 7.0, 0.41))
        assert verdict_sentence(d, {}, _LABELS, html=False) == (
            'The model and the entered inputs describe the data (runs test: 6 runs, 7.0 expected, p = 0.41).'
        )

    def test_inputs_explain_names_the_shifts_largest_first(self):
        from gui.plotting.labels import verdict_sentence

        d = _diagnostics('inputs_explain', conditional=_f_test(200.0, 1e-9), misfit=_f_test(1.1, 0.4))
        shifts = {
            '__titrant__': _shift('__titrant__', 0.030, z=1.0),
            'h0': _shift('h0', -0.041, z=-1.4),
        }
        assert verdict_sentence(d, shifts, _LABELS, html=False) == (
            'At the entered inputs the model misses the data (F(9, 72) = 200, p < 0.001). '
            'It fits once the inputs move within their stated uncertainties: '
            '[Host]₀ −4.1 % (1.4 σ), Guest (titrant) +3.0 % (1.0 σ). '
            'The interval includes these shifts.'
        )

    def test_inputs_conflict_says_the_inputs_are_judged_together_and_names_no_culprit(self):
        """With one informed direction per stated input the data do tell them apart, so no confounding is claimed."""
        from core.pipeline.diagnostics import Conflict
        from gui.plotting.labels import verdict_sentence

        d = _diagnostics(
            'inputs_conflict',
            conditional=_f_test(200.0, 1e-9),
            misfit=_f_test(1.1, 0.4),
            conflict=Conflict(q=24.2, k=2, p_value=1e-5, weights=(0.3, 0.9)),
        )
        shifts = {'h0': _shift('h0', -0.114, z=-3.8), '__titrant__': _shift('__titrant__', 0.093, z=3.1)}
        assert verdict_sentence(d, shifts, _LABELS, html=False) == (
            'The data fit only with the inputs, taken together, further from their entered values than their '
            'stated uncertainties allow (q = 24.2, p < 0.001). '
            'The fit put the correction here: [Host]₀ −11.4 % (3.8 σ), Guest (titrant) +9.3 % (3.1 σ) — '
            'the statistic weighs them together, so it does not say which of them is off. '
            'Check the values you entered for them. The interval assumes the shifts are real.'
        )

    def test_a_conflict_over_one_input_reads_in_the_singular(self):
        """One input free to move is one input to name, and no others for the statistic to have weighed it against.

        Naming it is not naming the cause: the clause after the shift says the
        correction landed there because there was nowhere else for it to go.
        """
        from core.pipeline.diagnostics import Conflict
        from gui.plotting.labels import verdict_sentence

        d = _diagnostics(
            'inputs_conflict',
            conditional=_f_test(200.0, 1e-9),
            misfit=_f_test(1.1, 0.4),
            conflict=Conflict(q=15.6, k=1, p_value=7e-5, weights=(0.92,)),
        )
        assert verdict_sentence(d, {'h0': _shift('h0', -0.197, z=-3.9)}, _LABELS, html=False) == (
            'The data fit only with [Host]₀ further from the value you entered than the uncertainty you '
            'stated allows (q = 15.6, p < 0.001). '
            'The fit put the correction here: [Host]₀ −19.7 % (3.9 σ) — this is the only input the fit was '
            'free to move, so the correction landed there whatever its real cause. '
            'Check the value you entered for it. The interval assumes the shift is real.'
        )

    def test_inputs_conflict_claims_the_inputs_are_confounded_only_where_the_weights_say_so(self):
        """Two inputs and one direction the data inform: the correction landed where that direction points."""
        from core.pipeline.diagnostics import Conflict
        from gui.plotting.labels import verdict_sentence

        d = _diagnostics(
            'inputs_conflict',
            conditional=_f_test(200.0, 1e-9),
            misfit=_f_test(1.1, 0.4),
            conflict=Conflict(q=24.2, k=1, p_value=1e-5, weights=(0.9,)),
        )
        shifts = {'h0': _shift('h0', -0.114, z=-3.8), '__titrant__': _shift('__titrant__', 0.093, z=3.1)}
        text = verdict_sentence(d, shifts, _LABELS, html=False)

        assert 'the data see only one combination of these 2 inputs' in text
        assert 'so the correction landed where that combination points' in text

    def test_a_conflict_counts_only_the_inputs_the_statistic_tested(self):
        """An input stated as a range carries no z and never enters q, so the sentence does not count it."""
        from core.pipeline.diagnostics import Conflict
        from gui.plotting.labels import verdict_sentence

        d = _diagnostics(
            'inputs_conflict',
            conditional=_f_test(200.0, 1e-9),
            misfit=_f_test(1.1, 0.4),
            conflict=Conflict(q=24.2, k=1, p_value=1e-5, weights=(0.9,)),
        )
        shifts = {'h0': _shift('h0', -0.114, z=-3.8), 'd0': _shift('d0', -0.06, at_edge=True)}
        text = verdict_sentence(d, shifts, {**_LABELS, 'd0': '[Dye]₀'}, html=False)

        # One input was stated with a σ, so it is the only input the statistic
        # judged, and the sentence says the fit had no other it could move.
        assert 'this is the only input the fit was free to move' in text
        assert 'these 2 inputs' not in text

    def test_the_advice_of_a_conflict_names_the_inputs_that_moved_and_no_others(self):
        """A carried-over constant is not a stock, and the fit that moved it is not told to check one."""
        from core.pipeline.diagnostics import Conflict
        from gui.plotting.labels import verdict_sentence

        d = _diagnostics(
            'inputs_conflict',
            conditional=_f_test(200.0, 1e-9),
            misfit=_f_test(1.1, 0.4),
            conflict=Conflict(q=24.2, k=1, p_value=1e-5, weights=(0.9,)),
        )
        shifts = {'Ka_dye': _shift('Ka_dye', 0.4, z=4.0)}
        text = verdict_sentence(d, shifts, {'Ka_dye': 'Ka,dye'}, html=False)

        assert 'Check the value you entered for it.' in text
        assert 'stock' not in text

    def test_model_inadequate_with_inputs_free_says_the_shifts_did_not_rescue_it(self):
        from gui.plotting.labels import verdict_sentence

        d = _diagnostics('model_inadequate', conditional=_f_test(200.0, 1e-9), misfit=_f_test(12.0, 1e-9))
        shifts = {'h0': _shift('h0', -0.041, z=-1.4)}
        assert verdict_sentence(d, shifts, _LABELS, html=False) == (
            'The model does not describe the data even with the inputs free to move within their uncertainties '
            '(F(9, 72) = 12, p < 0.001 after the shifts). '
            'The interval assumes a model the data reject; try another binding model or check the data.'
        )

    def test_model_inadequate_with_nothing_varying_points_at_the_input_uncertainty_panel(self):
        from gui.plotting.labels import verdict_sentence

        d = _diagnostics('model_inadequate', conditional=_f_test(200.0, 1e-9), misfit=_f_test(200.0, 1e-9))
        assert verdict_sentence(d, {}, _LABELS, html=False) == (
            'The model does not describe the data at the entered inputs (F(9, 72) = 200, p < 0.001). '
            'The interval assumes a model the data reject; try another binding model or check the data. '
            'Enter the uncertainty of the inputs under Input Uncertainty to test whether the inputs explain it.'
        )

    def test_a_single_moved_input_is_not_named_as_the_cause(self):
        """The statistic judges the inputs together; one shift does not identify the input that is off."""
        from core.pipeline.diagnostics import Conflict
        from gui.plotting.labels import verdict_sentence

        d = _diagnostics(
            'inputs_conflict',
            conditional=_f_test(200.0, 1e-9),
            misfit=_f_test(1.1, 0.4),
            conflict=Conflict(q=16.0, k=1, p_value=1e-4, weights=(0.9,)),
        )
        text = verdict_sentence(d, {'h0': _shift('h0', -0.114, z=-3.8)}, _LABELS, html=False)
        assert '[Host]₀ −11.4 % (3.8 σ)' in text
        assert 'is the one that is off' not in text
        assert 'whatever its real cause' in text

    def test_no_test_possible_claims_nothing_about_the_model(self):
        from gui.plotting.labels import verdict_sentence

        d = _diagnostics('consistent')
        text = verdict_sentence(d, {}, _LABELS, html=False)
        assert 'describe the data (' not in text
        assert 'too few' in text

    def test_the_html_form_escapes_the_less_than_of_a_small_p(self):
        """A rich-text label would swallow a bare '<' and everything after it."""
        from gui.plotting.labels import verdict_sentence

        d = _diagnostics('model_inadequate', conditional=_f_test(200.0, 1e-9), misfit=_f_test(200.0, 1e-9))
        html = verdict_sentence(d, {}, _LABELS, html=True)
        assert 'p &lt; 0.001' in html
        assert 'p < 0.001' not in html


class TestFmtMisfit:
    def test_the_f_test_is_named_where_the_sentence_does_not_name_it(self):
        from gui.plotting.labels import fmt_misfit

        assert fmt_misfit(_f_test(0.9, 0.55)) == 'lack-of-fit F(9, 72) = 0.9, p = 0.55'
        assert fmt_misfit(_f_test(0.9, 0.55), named=False) == 'F(9, 72) = 0.9, p = 0.55'

    def test_the_runs_test_names_itself_either_way(self):
        from gui.plotting.labels import fmt_misfit

        assert fmt_misfit(_runs(6, 7.0, 0.41), named=False) == 'runs test: 6 runs, 7.0 expected, p = 0.41'
        assert fmt_misfit(_runs(1, 1.0, 0.9)) == 'runs test: 1 run, 1.0 expected, p = 0.9'

    def test_a_large_statistic_reads_as_a_number_not_as_exponent_notation(self):
        from gui.plotting.labels import fmt_misfit

        assert 'e+' not in fmt_misfit(_f_test(1234.5, 1e-9))
        assert 'F(9, 72) = 1230' in fmt_misfit(_f_test(1234.5, 1e-9))

    def test_an_f_ratio_with_no_finite_reading_is_said_in_words(self):
        """The ratio is infinite exactly where the replicates carry no scatter, and that is what the reader needs."""
        import math

        from gui.plotting.labels import fmt_misfit

        text = fmt_misfit(_f_test(math.inf, 0.0))

        assert text == (
            'lack-of-fit: the replicates agree exactly at every point, so any distance from the curve '
            'counts against the model'
        )
        assert 'inf' not in text
        assert fmt_misfit(_f_test(math.inf, 0.0), named=False).startswith('the replicates agree exactly')

    def test_no_report_can_print_a_statistic_that_is_not_a_number(self):
        """fmt_stat is the one place a statistic becomes text, so it refuses rather than writing 'inf'."""
        import math

        import pytest

        from gui.plotting.labels import fmt_stat

        for value in (math.inf, -math.inf, math.nan):
            with pytest.raises(ValueError):
                fmt_stat(value)
