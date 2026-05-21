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

from PyQt6.QtWidgets import QDoubleSpinBox, QSpinBox


class NoScrollSpinBox(QSpinBox):
    def wheelEvent(self, event):  # type: ignore[override]
        event.ignore()


class NoScrollDoubleSpinBox(QDoubleSpinBox):
    def wheelEvent(self, event):  # type: ignore[override]
        event.ignore()
