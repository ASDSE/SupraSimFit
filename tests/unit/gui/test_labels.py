"""Tests for gui.plotting.labels — HTML and Unicode formatting."""

from gui.plotting.labels import fmt_param, fmt_unit_html, fmt_unit_pretty


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
