"""Drop-in QSpinBox / QDoubleSpinBox subclasses that always ignore
mouse-wheel events.

Motivation: inside a scrollable sidebar, the stock Qt spinbox swallows
every wheel event whose cursor happens to land on it, including the ones
the user intended for the enclosing QScrollArea. That turns "scroll the
sidebar" into "accidentally change the value of whatever spinbox is
under the cursor".

A focus-gated version was tried first (forward to ``super().wheelEvent``
only when the spinbox had focus), but ``QAbstractSpinBox`` defaults to
``Qt.FocusPolicy.StrongFocus``: once the user clicks a spinbox to type a
value it keeps focus, so later wheel events delivered to it while the
cursor was elsewhere still incremented the value.

Unconditionally calling ``event.ignore()`` lets Qt propagate every wheel
event up to the parent — for our sidebar, the ``QScrollArea`` viewport —
so scrolling always scrolls. Trade-off: wheel-to-increment is gone;
values change only via typing, the up/down buttons, or arrow keys.
"""

from __future__ import annotations

import math

from PyQt6.QtCore import QLocale, Qt, pyqtSignal
from PyQt6.QtGui import QDoubleValidator
from PyQt6.QtWidgets import QDoubleSpinBox, QLineEdit, QSpinBox


def format_number(value: float, sigfigs: int = 4) -> str:
    """Human-readable float: plain for O(1) magnitudes, scientific for the rest.

    Uses ``%g`` (which already switches to exponent form outside ~[1e-4, 1e6) and
    trims trailing zeros), then tidies the exponent so ``5e+07`` reads ``5e7`` and
    ``5e-05`` reads ``5e-5``.  Purely a string formatter — no unit math — so Pint
    stays the single source of every conversion.  This is what makes a binding
    constant show as ``3.3e7`` instead of the unreadable ``33000000.0000``.
    """
    if not math.isfinite(value):
        return str(value)
    s = f'{value:.{sigfigs}g}'
    if 'e' in s:
        mantissa, exponent = s.split('e')
        s = f'{mantissa}e{int(exponent)}'
    return s


class SciLineEdit(QLineEdit):
    """Single-float entry shown in adaptive/scientific notation.

    Preferred over ``QDoubleSpinBox`` for large-magnitude quantities (binding
    constants, signal coefficients spanning ~1e3..1e11): a spinbox can't render
    them legibly, rejects ``1e8`` on entry, and loses precision because it rounds
    ``value·10^decimals`` (which overflows a double past ~1e11).  A line edit holds
    the exact text, accepts scientific input via ``QDoubleValidator``, and formats
    through :func:`format_number`.

    ``value()`` / ``setValue()`` mirror the spinbox API (``setValue`` never emits);
    ``value_changed`` fires only on an accepted user edit.
    """

    value_changed = pyqtSignal(float)

    def __init__(self, parent=None, *, allow_negative: bool = True, sigfigs: int = 4):
        super().__init__(parent)
        self._value = 0.0
        self._sigfigs = sigfigs
        validator = QDoubleValidator(self)
        validator.setNotation(QDoubleValidator.Notation.ScientificNotation)
        validator.setLocale(QLocale.c())  # dot decimal + 'e' exponent, locale-independent
        if not allow_negative:
            validator.setBottom(0.0)
        self.setValidator(validator)
        self.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.editingFinished.connect(self._commit)
        self.setText(format_number(self._value, self._sigfigs))

    def value(self) -> float:
        """The number on screen, including an edit not yet confirmed with Return or by leaving the box.

        A control that does not take focus (a toolbar button on macOS) acts before
        ``editingFinished`` fires, so the typed number is what counts. Text that is not a
        number leaves the last accepted value; :meth:`has_unreadable_edit` reports it.
        """
        if self.isModified():
            typed = _as_number(self.text())
            if typed is not None:
                return typed
        return self._value

    def has_unreadable_edit(self) -> bool:
        """Whether the user typed text that is not a number."""
        return self.isModified() and _as_number(self.text()) is None

    def setValue(self, value: float) -> None:
        """Set the shown value from code without emitting ``value_changed``."""
        self._value = float(value)
        self.setText(format_number(self._value, self._sigfigs))

    def _commit(self) -> None:
        try:
            parsed = float(self.text())
        except ValueError:  # empty or partial entry — restore the last good value
            self.setText(format_number(self._value, self._sigfigs))
            return
        self._value = parsed
        self.setText(format_number(parsed, self._sigfigs))
        self.value_changed.emit(parsed)


def _as_number(text: str) -> float | None:
    """*text* as a finite float, or ``None`` when it is not one."""
    try:
        number = float(text)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


class NoScrollSpinBox(QSpinBox):
    def wheelEvent(self, event):  # type: ignore[override]
        event.ignore()


class NoScrollDoubleSpinBox(QDoubleSpinBox):
    def wheelEvent(self, event):  # type: ignore[override]
        event.ignore()
