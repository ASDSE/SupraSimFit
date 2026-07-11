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

from PyQt6.QtWidgets import QDoubleSpinBox, QSpinBox


def decimals_for_scale(scale: float, min_scale: float, base_decimals: int = 3) -> int:
    """Spinbox decimals so a value resolvable in the finest offered unit survives display here.

    The finest offered unit (``min_scale``, the smallest scale-to-base factor) is shown
    with ``base_decimals`` places; a coarser unit (larger ``scale``) widens by one decimal
    per decade, so converting a nonzero quantity into it never rounds to ``0``.

    Single source of the decimal policy shared by every unit-aware numeric field — the
    fitting conditions form (``_UnitWidget``) and the simulation applet's concentration
    inputs — so the fix lives in one place.
    """
    if min_scale <= 0:
        return base_decimals
    extra = round(math.log10(scale / min_scale))
    return base_decimals + max(0, extra)


class NoScrollSpinBox(QSpinBox):
    def wheelEvent(self, event):  # type: ignore[override]
        event.ignore()


class NoScrollDoubleSpinBox(QDoubleSpinBox):
    def wheelEvent(self, event):  # type: ignore[override]
        event.ignore()
