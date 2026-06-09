"""Tests for _display_label() base-26 replica labelling."""

from gui.widgets.replica_panel import _display_label


class TestDisplayLabel:
    def test_single_letter_range(self):
        assert _display_label(0) == 'A'
        assert _display_label(1) == 'B'
        assert _display_label(25) == 'Z'

    def test_double_letter_starts_at_26(self):
        assert _display_label(26) == 'AA'
        assert _display_label(27) == 'AB'
        assert _display_label(51) == 'AZ'
        assert _display_label(52) == 'BA'
        # Spreadsheet-standard base-26: index 100 → 'CW'
        # (100 // 26 - 1 = 2 → 'C'; 100 % 26 = 22 → 'W').
        assert _display_label(100) == 'CW'
