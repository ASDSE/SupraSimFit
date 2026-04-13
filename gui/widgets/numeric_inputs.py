"""Drop-in QSpinBox / QDoubleSpinBox subclasses that ignore mouse-wheel
events when they are not focused.

Motivation: inside a scrollable sidebar, the stock Qt spinbox swallows
every wheel event whose cursor happens to land on it, including the ones
the user intended for the enclosing QScrollArea. That turns "scroll the
sidebar" into "accidentally change the value of whatever spinbox is
under the cursor".

Calling ``event.ignore()`` (instead of ``super().wheelEvent(event)``)
when the widget has no focus lets Qt propagate the wheel event to the
parent widget, which for our sidebar is the QScrollArea viewport — so
the sidebar scrolls as expected. Clicking into the spinbox to give it
focus restores the usual wheel-to-increment behaviour.
"""

from __future__ import annotations

from PyQt6.QtWidgets import QDoubleSpinBox, QSpinBox


class NoScrollSpinBox(QSpinBox):
    def wheelEvent(self, event):  # type: ignore[override]
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


class NoScrollDoubleSpinBox(QDoubleSpinBox):
    def wheelEvent(self, event):  # type: ignore[override]
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()
