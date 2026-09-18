"""The Parameter Bounds panel refuses a bound it cannot use, in the open.

A bound the panel cannot read is named under the rows and through
:meth:`problems`, and is left out of :meth:`current_bounds`, so no fit runs on a
registry default the user did not enter. Equal bounds are readable: they pin the
parameter, and are passed on.

Requires a ``QApplication`` (the ``qapp`` fixture).
"""

from __future__ import annotations

import pytest

pytest.importorskip('PyQt6')

from core.assays.registry import AssayType  # noqa: E402


def _ida_panel():
    from gui.widgets.bounds_panel import BoundsPanel

    panel = BoundsPanel()
    panel.set_assay_type(AssayType.IDA)
    return panel


def test_defaults_are_usable_and_reported_as_untouched(qapp):
    panel = _ida_panel()

    assert panel.problems() == []
    assert panel._warning.isHidden()
    assert panel.current_bounds() is None  # nothing edited: the registry defaults apply


def test_an_unreadable_bound_is_named_and_is_not_passed_on(qapp):
    panel = _ida_panel()
    row = panel._rows['Ka_guest']

    row._lo.setText('1e')

    assert panel.problems() == ['Ka(G): the lower bound “1e” is not a number. Enter a number, such as 1e3.']
    assert not panel._warning.isHidden()
    assert panel._warning.text() == panel.problems()[0]
    assert 'Ka_guest' not in (panel.current_bounds() or {})

    row._lo.setText('')
    assert panel.problems() == ['Ka(G): the lower bound is empty. Enter a number, such as 1e3.']

    row._lo.setText('1e3')
    assert panel.problems() == []
    assert panel._warning.isHidden()
    assert 'Ka_guest' in panel.current_bounds()


def test_a_lower_bound_above_the_upper_one_is_refused(qapp):
    """A backwards search range is not a range the optimiser can use."""
    panel = _ida_panel()
    row = panel._rows['Ka_guest']

    row.set_values(1e8, 1e6)
    assert panel.problems() == ['Ka(G): the lower bound must not be above the upper bound.']
    assert 'Ka_guest' not in (panel.current_bounds() or {})


def test_equal_bounds_pin_the_parameter_and_are_passed_on(qapp):
    """Equal bounds hold a parameter at a value instead of fitting it — the Ka the
    Identifiability tab reports as fixed by its bounds — so they are carried through."""
    panel = _ida_panel()
    panel._rows['Ka_guest'].set_values(3.14e8, 3.14e8)

    assert panel.problems() == []
    lo, hi = panel.current_bounds()['Ka_guest']
    assert (lo.magnitude, hi.magnitude) == (3.14e8, 3.14e8)


def test_a_signal_parameter_has_no_upper_limit_until_one_is_entered(qapp):
    """The size of a signal coefficient follows the instrument's gain, so no finite default suits every
    titration: its upper box is empty, an empty box means no limit, and only an entered bound is passed on."""
    import math

    panel = _ida_panel()
    row = panel._rows['I_dye_bound']

    assert row._hi.text() == '' and row._hi.placeholderText() == 'no limit'
    assert row.values() == (0.0, math.inf)

    row._hi.setText('5e9')
    assert panel.problems() == []
    assert set(panel.current_bounds()) == {'I_dye_bound'}  # the rows left at their defaults are not passed on
    assert panel.current_bounds()['I_dye_bound'][1].magnitude == 5e9

    row._hi.setText('')
    assert panel.problems() == [] and panel.current_bounds() is None

    # A binding constant is searched across its bounds, so it needs both.
    panel._rows['Ka_guest']._hi.setText('')
    assert panel.problems() == ['Ka(G): the upper bound is empty. Enter a number, such as 1e3.']


def test_a_bound_box_takes_only_a_number_as_it_is_typed(qapp):
    """The validator keeps letters out of the box, so a typo cannot become a silent default."""
    from PyQt6.QtTest import QTest

    panel = _ida_panel()
    box = panel._rows['Ka_guest']._lo
    box.clear()

    QTest.keyClicks(box, '1.5e7abc')

    assert box.text() == '1.5e7'
    assert panel.problems() == []
