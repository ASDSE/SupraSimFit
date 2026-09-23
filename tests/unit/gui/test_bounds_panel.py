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


def test_a_dye_alone_file_the_data_checks_refuse_is_named_with_the_refusal_itself(qapp, tmp_path, monkeypatch):
    """The refusal names the file and the point and says what to do; a generic sentence would hide both."""
    import gui.widgets.bounds_panel as module

    path = tmp_path / 'dye_alone.csv'
    rows = [f'{c:g},{100 - 10 * i + r},{r}' for r in (0, 1) for i, c in enumerate((0, 1e-6, 2e-6, 3e-6, 4e-6))]
    path.write_text('concentration,signal,replica\n' + '\n'.join(rows) + '\n5e-6,,0\n5e-6,,1\n')
    warnings = []
    monkeypatch.setattr(module.QFileDialog, 'getOpenFileName', lambda *a, **k: (str(path), ''))
    monkeypatch.setattr(module.QMessageBox, 'warning', lambda parent, title, text: warnings.append(text))
    panel = _ida_panel()
    before = panel.current_bounds()

    panel._on_load_dye_alone()

    (text,) = warnings
    assert text.startswith('No replicate in dye_alone.csv has a signal at 5 µM')
    assert 'delete that titration point' in text and 'The signal bounds were not changed.' in text
    assert panel.current_bounds() == before
