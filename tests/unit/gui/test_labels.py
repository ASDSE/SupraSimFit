"""Tests for gui.plotting.labels — HTML and Unicode formatting."""

from gui.plotting.labels import fmt_param, fmt_r2, fmt_unit_html, fmt_unit_pretty, plain_label


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
    def test_below_the_floor_reads_below_it(self):
        """A fit short of the Min R² must not read as the floor it misses."""
        text = fmt_r2(0.98996, 0.99)
        assert float(text) < 0.99

    def test_at_or_above_the_floor_reads_so(self):
        """The same guard the other way: a fit that clears the floor keeps reading cleared."""
        text = fmt_r2(0.990004, 0.99)
        assert float(text) >= 0.99

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
