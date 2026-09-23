"""Tests for gui.plotting.labels — HTML and Unicode formatting."""

import pytest

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


def test_every_fitted_value_reads_to_three_significant_figures_with_its_zeros():
    """One reading of a value and an edge in every view: 8×10⁴ and 8.0×10⁴ are the same edge written twice."""
    from gui.plotting.labels import fmt_value

    assert fmt_value(8e4) == '8.00×10⁴'
    assert fmt_value(6.6e4) == '6.60×10⁴'
    assert fmt_value(2413.6) == '2.41×10³'
    assert fmt_value(150) == '150'
    assert fmt_value(0.012) == '0.0120'


class TestFmtBoundEstimate:
    """An estimate on an end of its search box is the box, not a measurement, and reads in words."""

    def test_an_estimate_on_the_lower_bound_reads_as_the_limit_the_data_set_above_it(self):
        from gui.plotting.labels import fmt_bound_estimate

        text = fmt_bound_estimate('low', '1.00×10⁻⁸', '2.41×10³', True, False, html=False)
        assert text == 'not limited below 2.41×10³'
        assert '10⁻⁸' not in text

    def test_an_estimate_on_the_upper_bound_reads_as_the_limit_the_data_set_below_it(self):
        from gui.plotting.labels import fmt_bound_estimate

        assert fmt_bound_estimate('high', '5.00×10⁴', '1.00×10¹²', False, True, html=False) == (
            'not limited above 5.00×10⁴'
        )

    def test_an_estimate_on_a_bound_of_an_interval_open_at_both_ends_says_nothing_is_limited(self):
        from gui.plotting.labels import fmt_bound_estimate

        assert fmt_bound_estimate('low', '1e-8', '1e12', True, True, html=False) == 'not limited by the data'

    def test_the_rich_text_form_sets_the_words_as_prose(self):
        from gui.plotting.labels import fmt_bound_estimate, plain_label

        html = fmt_bound_estimate('low', '1e-8', '2.41×10³', True, False, html=True)
        assert html == '<i>not limited below</i> 2.41×10³'
        assert plain_label(html) == 'not limited below 2.41×10³'

    def test_an_estimate_on_a_bound_with_no_interval_says_where_it_stopped_and_no_number(self):
        from gui.plotting.labels import fmt_bound_estimate

        assert fmt_bound_estimate('high', None, None, False, False, html=False) == (
            'at the upper end of its search range'
        )


class TestStatedUncertainty:
    """One notation for a stated uncertainty: σ for a standard deviation, the two ends for a range."""

    def test_a_standard_deviation_reads_sigma_in_percent_or_in_the_input_s_unit(self):
        from core.pipeline.inputs import InputSpec
        from gui.plotting.labels import stated_uncertainty

        assert stated_uncertainty(InputSpec.sigma_pct(10.0), '') == 'σ 10 %'
        assert stated_uncertainty(InputSpec.sigma_abs(2e-7), 'M') == 'σ 2.0×10⁻⁷ M'

    def test_a_range_reads_as_its_two_signed_ends(self):
        from core.pipeline.inputs import InputSpec
        from gui.plotting.labels import stated_uncertainty

        assert stated_uncertainty(InputSpec.interval_pct(-5.0, 5.0), '') == '−5 % to +5 %'
        assert stated_uncertainty(InputSpec.interval_abs(1e-6, 2e-6), 'M') == '1.0×10⁻⁶ to 2.0×10⁻⁶ M'


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


def _diagnostics(verdict, *, conditional=None, misfit=None, conflict=None, skipped=None):
    from core.pipeline.diagnostics import FitDiagnostics, Verdict

    return FitDiagnostics(
        conditional_misfit=conditional,
        misfit=misfit,
        conflict=conflict,
        verdict=Verdict(verdict),
        skipped=skipped or {},
    )


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

    def test_a_shift_that_rounds_to_zero_carries_no_sign(self):
        """−0.0 % claims a direction the digits shown do not have."""
        from gui.plotting.labels import fmt_shift

        assert fmt_shift(_shift('d0', -1.2e-10, z=-4e-9), '[Dye]₀', html=False) == '[Dye]₀ 0.0 % (0.0 σ)'
        assert fmt_shift(_shift('d0', 4e-4), '[Dye]₀', html=False) == '[Dye]₀ 0.0 %'

    def test_a_range_input_inside_its_range_claims_no_multiple_of_a_sigma_it_has_none_of(self):
        from gui.plotting.labels import fmt_shift

        assert fmt_shift(_shift('d0', -0.06), '[Dye]₀', html=False) == '[Dye]₀ −6.0 %'


class TestVerdictSentence:
    """The four verdicts, in the words design section 3 fixes."""

    def test_consistent_quotes_the_test_that_passed(self):
        from gui.plotting.labels import verdict_sentence

        d = _diagnostics('consistent', conditional=_f_test(0.9, 0.55), misfit=_f_test(0.9, 0.55))
        assert verdict_sentence(d, {}, _LABELS, html=False) == (
            'No test found evidence against the model or the entered inputs (lack-of-fit F(9, 72) = 0.9, p = 0.55).'
        )

    def test_consistent_with_one_signal_quotes_the_runs_test(self):
        from gui.plotting.labels import verdict_sentence

        d = _diagnostics('consistent', conditional=_runs(6, 7.0, 0.41), misfit=_runs(6, 7.0, 0.41))
        assert verdict_sentence(d, {}, _LABELS, html=False) == (
            'No test found evidence against the model or the entered inputs '
            '(runs test: 6 runs, 7.0 expected, p = 0.41).'
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
        """An input stated as a range carries no z and never enters q, so the sentence neither counts nor blames it.

        One σ input and one range that moved: the sentence may not call the σ
        input the only one the fit could move, and the range is reported as
        moved inside what was stated, not further than it allows.
        """
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

        assert text == (
            'The data fit only with [Host]₀ further from the value you entered than the uncertainty you stated '
            'allows (q = 24.2, p < 0.001). The fit put the correction here: [Host]₀ −11.4 % (3.8 σ) — this is the '
            'only input stated with a standard deviation, so the correction landed there whatever its real cause. '
            'Inside the range you stated it also moved [Dye]₀ −6.0 % (at the edge of its range). An input at the '
            'edge of its range is one the data would have moved further. Check the values you entered for all the '
            'inputs listed, ranges included. The interval assumes the shifts are real.'
        )
        assert 'only input the fit was free to move' not in text

    @pytest.mark.parametrize(
        ('sigmas', 'ranges', 'k'),
        [(1, 0, 1), (1, 1, 1), (1, 2, 1), (2, 0, 1), (2, 0, 2), (2, 1, 1), (2, 1, 2), (3, 1, 1), (3, 2, 2)],
        ids=lambda v: str(v),
    )
    def test_every_count_of_a_conflict_is_the_count_of_inputs_it_names(self, sigmas, ranges, k):
        """Every mix of σ and range inputs: the inputs the correction is read from are the σ ones, and so is every count.

        The list after "correction here" names exactly the inputs stated with a
        standard deviation; "these N inputs" and the singular or plural of the
        advice agree with that list; every range is named once, as moved inside
        its range.
        """
        import re

        from core.pipeline.diagnostics import Conflict
        from gui.plotting.labels import verdict_sentence

        keys_sigma = [f's{i}' for i in range(sigmas)]
        keys_range = [f'r{i}' for i in range(ranges)]
        labels = {key: f'IN{key.upper()}' for key in keys_sigma + keys_range}
        shifts = {key: _shift(key, -0.05 * (i + 1), z=-(i + 3.0)) for i, key in enumerate(keys_sigma)}
        shifts |= {key: _shift(key, 0.02 * (i + 1), at_edge=i == 0) for i, key in enumerate(keys_range)}
        d = _diagnostics(
            'inputs_conflict',
            conditional=_f_test(200.0, 1e-9),
            misfit=_f_test(1.1, 0.4),
            conflict=Conflict(q=24.2, k=k, p_value=1e-5, weights=tuple([0.9] * k)),
        )
        text = verdict_sentence(d, shifts, labels, html=False)

        correction = text.split('The fit put the correction here: ', 1)[1].split(' — ', 1)[0]
        assert sorted(re.findall(r'IN[SR]\d', correction)) == sorted(labels[key] for key in keys_sigma)
        named = re.findall(r'these (\d+) inputs', text)
        assert all(int(n) == sigmas for n in named)
        # The advice covers every input that moved: a range resting on its edge may be the one that is off.
        assert ('Check the value you entered for it.' in text) == (sigmas == 1 and not ranges)
        assert ('Check the values you entered for them.' in text) == (sigmas > 1 and not ranges)
        assert ('for all the inputs listed, ranges included.' in text) == bool(ranges)
        if ranges:
            inside = text.split('you stated it also moved ', 1)[1].split('. Check', 1)[0]
            assert sorted(re.findall(r'IN[SR]\d', inside)) == sorted(labels[key] for key in keys_range)
        else:
            assert 'also moved' not in text
        assert 'the only input the fit was free to move' not in text or (sigmas == 1 and not ranges)

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

    def test_both_tests_rejecting_name_the_inputs_first_and_the_model_after(self):
        """An input that is off can by itself make the curve miss, so a rejected model is not blamed first."""
        from core.pipeline.diagnostics import Conflict
        from gui.plotting.labels import verdict_sentence

        d = _diagnostics(
            'model_and_inputs',
            conditional=_f_test(300.0, 1e-9),
            misfit=_f_test(40.0, 1e-9),
            conflict=Conflict(q=30.1, k=2, p_value=1e-6, weights=(0.4, 0.9)),
        )
        shifts = {'h0': _shift('h0', -0.2, z=-4.0), '__titrant__': _shift('__titrant__', 0.1, z=3.3)}
        text = verdict_sentence(d, shifts, _LABELS, html=False)

        assert text.startswith(
            'The data fit only with the inputs, taken together, further from their entered values than their '
            'stated uncertainties allow (q = 30.1, p < 0.001), and even with them moved the model misses the '
            'data (F(9, 72) = 40, p < 0.001 after the shifts).'
        )
        assert text.index('Check first the values you entered for them:') < text.index('try another binding model')
        assert 'the statistic weighs them together' in text

    @pytest.mark.parametrize(
        ('skipped', 'expected'),
        [
            ({'misfit': 'no_scatter'}, 'The curve was not tested against the data: the data carry no scatter'),
            ({'misfit': 'too_few_dof'}, 'The curve was not tested against the data: the data leave too few points'),
        ],
        ids=['no-scatter', 'too-few-points'],
    )
    def test_a_misfit_test_that_could_not_run_is_named_with_its_reason(self, skipped, expected):
        """No evidence against a fit no test could look at is not the verdict of a test that passed."""
        from gui.plotting.labels import verdict_sentence

        text = verdict_sentence(_diagnostics('consistent', skipped=skipped), {}, _LABELS, html=False)

        assert text.startswith('No test could be run on this fit, so nothing here speaks for or against it.')
        assert expected in text
        assert 'No test found evidence' not in text

    @pytest.mark.parametrize(
        ('reason', 'shift', 'expected'),
        [
            ('no_informed_direction', _shift('h0', -0.01, z=-0.2), 'do not determine any combination'),
            ('no_uncertainty', _shift('h0', -0.05, at_edge=True), 'every uncertainty is stated as a range'),
        ],
        ids=['uninformed', 'ranges-only'],
    )
    def test_a_conflict_test_that_could_not_run_is_named_with_its_reason(self, reason, shift, expected):
        from gui.plotting.labels import verdict_sentence

        d = _diagnostics(
            'consistent', conditional=_f_test(0.9, 0.55), misfit=_f_test(0.8, 0.6), skipped={'conflict': reason}
        )
        text = verdict_sentence(d, {'h0': shift}, _LABELS, html=False)

        assert text.startswith('No test found evidence against the model or the entered inputs (lack-of-fit')
        assert 'The entered inputs were not tested against what you stated: ' in text
        assert expected in text

    def test_inputs_taken_as_exact_are_not_said_to_have_gone_untested(self):
        """With nothing stated there is no statistic to run; the misfit test at the entered inputs tests them."""
        from gui.plotting.labels import verdict_sentence

        d = _diagnostics(
            'consistent',
            conditional=_f_test(0.9, 0.55),
            misfit=_f_test(0.9, 0.55),
            skipped={'conflict': 'no_uncertainty'},
        )
        assert 'not tested' not in verdict_sentence(d, {}, _LABELS, html=False)

    def test_a_consistent_verdict_quotes_the_conflict_statistic_it_ran(self):
        from core.pipeline.diagnostics import Conflict
        from gui.plotting.labels import verdict_sentence

        d = _diagnostics(
            'consistent',
            conditional=_f_test(0.9, 0.55),
            misfit=_f_test(0.8, 0.6),
            conflict=Conflict(q=1.2, k=1, p_value=0.27, weights=(0.9,)),
        )
        text = verdict_sentence(d, {'h0': _shift('h0', -0.02, z=-1.1)}, _LABELS, html=False)
        assert text == (
            'No test found evidence against the model or the entered inputs '
            '(lack-of-fit F(9, 72) = 0.8, p = 0.6; inputs q = 1.2, p = 0.27).'
        )

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

    def test_no_report_can_print_a_statistic_that_is_not_a_number(self):
        """fmt_stat is the one place a statistic becomes text, so it refuses rather than writing 'inf'."""
        import math

        import pytest

        from gui.plotting.labels import fmt_stat

        for value in (math.inf, -math.inf, math.nan):
            with pytest.raises(ValueError):
                fmt_stat(value)


class TestFmtSpread:
    """A spread of log₁₀(Ka) reads as decades and as the factor Ka spreads by."""

    def test_decades_and_the_factor_they_mean(self):
        """10**0.084 = 1.2131…, so a standard deviation of 0.084 decades is a factor of 1.21 either way."""
        from gui.plotting.labels import fmt_spread

        assert fmt_spread(0.084, html=False) == '0.084 decades (×/÷ 1.21)'

    def test_the_rich_text_form_keeps_the_factor_on_one_line(self):
        """Only the space before the factor differs, so both forms read the same."""
        from gui.plotting.labels import fmt_spread

        html = fmt_spread(0.084, html=True)
        assert html == '0.084 decades (×/÷&nbsp;1.21)'
        assert html.replace('&nbsp;', ' ') == fmt_spread(0.084, html=False)

    def test_a_wide_spread_reads_in_plain_digits(self):
        """10**1.5 = 31.62…: the factor is written out, never as an exponent of e."""
        from gui.plotting.labels import fmt_spread

        text = fmt_spread(1.5, html=False)
        assert text == '1.5 decades (×/÷ 31.6)'
        assert 'e+' not in text and 'E+' not in text

    def test_no_spread_at_all_is_a_factor_of_one(self):
        from gui.plotting.labels import fmt_spread

        assert fmt_spread(0.0, html=False) == '0 decades (×/÷ 1.00)'

    def test_what_is_not_a_standard_deviation_is_refused(self):
        """A spread is finite and not negative; anything else is said in words by the caller, not written out."""
        import math

        import pytest

        from gui.plotting.labels import fmt_spread

        for value in (math.nan, math.inf, -0.1):
            with pytest.raises(ValueError):
                fmt_spread(value, html=False)


def test_plain_label_gives_back_the_characters_html_escaped():
    """A source named by the user reaches a label escaped; flattening it has to undo that, not print '&amp;'."""
    assert plain_label('Host &amp; dye stock') == 'Host & dye stock'
    assert plain_label('a &lt; b') == 'a < b'


class TestVerdictHeadline:
    """The few words above the table and on the plot, and the tone they are shown in."""

    @pytest.mark.parametrize(
        ('verdict', 'tone'),
        [
            ('consistent', 'neutral'),
            ('inputs_explain', 'amber'),
            ('inputs_conflict', 'red'),
            ('model_inadequate', 'red'),
            ('model_and_inputs', 'red'),
        ],
    )
    def test_every_verdict_has_a_headline_and_a_tone(self, verdict, tone):
        from core.pipeline.diagnostics import Conflict
        from gui.plotting.labels import VERDICT_TONES, verdict_headline

        d = _diagnostics(
            verdict,
            conditional=_f_test(0.9, 0.55),
            misfit=_f_test(0.9, 0.55),
            conflict=Conflict(q=24.2, k=1, p_value=1e-5, weights=(0.9,)),
        )
        text, got = verdict_headline(d)
        assert got == tone and got in VERDICT_TONES
        assert text and '[' not in text, 'a headline names no input'

    def test_a_fit_no_test_could_look_at_is_not_headlined_as_passing(self):
        from gui.plotting.labels import verdict_headline

        text, tone = verdict_headline(_diagnostics('consistent', skipped={'misfit': 'no_scatter'}))
        assert text.startswith('Not tested')
        assert tone == 'neutral'


class TestReplicateSummary:
    """Single-replicate fits beside the interval, with bound-valued fits counted, not summarised."""

    @staticmethod
    def _row(replicates, at_bound=0):
        from types import SimpleNamespace

        return SimpleNamespace(key='Ka_guest', replicates=replicates, replicates_at_bound=at_bound)

    def test_the_median_and_range_of_the_replicates_own_fits_and_what_they_are_beside_the_interval(self):
        from gui.plotting.labels import replicate_summary

        stats = {'median': 4.56e4, 'min': 4.49e4, 'max': 8.16e4}
        text = replicate_summary([self._row(stats)], 3, lambda spec: 'Ka(G)', lambda spec: 'M⁻¹')

        assert text.startswith(
            'Single-replicate fits (inputs as entered): Ka(G) median 4.56×10⁴, range [4.49×10⁴, 8.16×10⁴] M⁻¹.'
        )
        assert 'can fall outside it' in text

    def test_fits_that_ran_to_a_bound_are_counted_and_not_summarised(self):
        from gui.plotting.labels import replicate_summary

        stats = {'median': 4.56e4, 'min': 4.49e4, 'max': 4.6e4}
        text = replicate_summary([self._row(stats, at_bound=1)], 3, lambda spec: 'Ka(G)', lambda spec: 'M⁻¹')

        assert '1 of 3 single-replicate fits of Ka(G) ran to a bound of its search range' in text
        assert 'left out of these figures' in text

    def test_nothing_to_say_says_nothing(self):
        from gui.plotting.labels import replicate_summary

        assert replicate_summary([self._row(None)], 1, lambda spec: 'Ka(G)', lambda spec: 'M⁻¹') == ''
