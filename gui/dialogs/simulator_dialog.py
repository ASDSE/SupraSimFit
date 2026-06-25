"""DBA forward-simulation dialog.

A standalone parameter explorer for the Direct Binding Assay: the user sets
the host–dye binding constant, the signal coefficients, and the total host
and dye concentrations, and a PyQtGraph curve updates live with the predicted
titration signal. The curve is computed by the shared, tested forward model
:func:`core.models.equilibrium.dba_signal` — no model math lives here.

Two titration directions match the two DBA assay subtypes:

* **Host → Dye** (``HtoD``): dye fixed at ``[Dye]₀``; host titrated 0 → ``[Host]₀``.
* **Dye → Host** (``DtoH``): host fixed at ``[Host]₀``; dye titrated 0 → ``[Dye]₀``.

Concentrations are entered and plotted in µM; they are converted to Molar at
the boundary because the forward model works in base units.
"""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from core.models.equilibrium import dba_signal
from gui.widgets.numeric_inputs import NoScrollDoubleSpinBox

# Number of points sampled along the simulated titration curve.
_N_POINTS = 200

# (combo label, dba_signal mode, titrated-species label for the x-axis)
_MODES: tuple[tuple[str, str, str], ...] = (
    ('Host → Dye (titrate host)', 'HtoD', 'Host'),
    ('Dye → Host (titrate dye)', 'DtoH', 'Dye'),
)

_INTRO = (
    'Forward DBA simulation. Adjust the parameters to see the predicted '
    'titration curve update live. Concentrations are entered in µM.'
)


class SimulatorDialog(QDialog):
    """Live Direct-Binding-Assay titration-curve simulator.

    Parameter inputs drive a PyQtGraph curve computed by the shared forward
    model :func:`core.models.equilibrium.dba_signal`.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle('DBA Simulator')
        self.setMinimumSize(760, 480)
        self._build_ui()
        self._recompute()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QHBoxLayout(self)

        # --- left: parameter controls -----------------------------------
        side = QVBoxLayout()
        intro = QLabel(_INTRO)
        intro.setWordWrap(True)
        side.addWidget(intro)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._mode = QComboBox()
        for label, _mode, _x_species in _MODES:
            self._mode.addItem(label)

        self._ka = self._spin(0.0, 1e12, 0, 5e5, ' M⁻¹')
        self._i0 = self._spin(-1e9, 1e9, 2, 0.0, ' a.u.')
        self._i_free = self._spin(0.0, 1e12, 0, 5e7, ' a.u./M')
        self._i_bound = self._spin(0.0, 1e12, 0, 3e8, ' a.u./M')
        self._h0 = self._spin(0.0, 1e6, 3, 50.0, ' µM')
        self._d0 = self._spin(0.0, 1e6, 3, 5.0, ' µM')

        form.addRow('Titration', self._mode)
        form.addRow('Ka (host–dye)', self._ka)
        form.addRow('I₀ (baseline)', self._i0)
        form.addRow('I (free dye)', self._i_free)
        form.addRow('I (bound dye)', self._i_bound)
        form.addRow('[Host]₀', self._h0)
        form.addRow('[Dye]₀', self._d0)
        side.addLayout(form)
        side.addStretch(1)

        side_box = QWidget()
        side_box.setLayout(side)
        side_box.setFixedWidth(300)
        root.addWidget(side_box)

        # --- right: live plot --------------------------------------------
        self._plot = pg.PlotWidget()
        self._plot.setBackground('w')
        self._plot.showGrid(x=True, y=True, alpha=0.3)
        self._plot.setLabel('left', 'Signal (a.u.)')
        self._curve = self._plot.plot([], [], pen=pg.mkPen('#1f77b4', width=2))
        root.addWidget(self._plot, stretch=1)

        # Wire every control once all widgets exist (avoids firing
        # _recompute against half-built state during construction).
        self._mode.currentIndexChanged.connect(self._recompute)
        for sb in (self._ka, self._i0, self._i_free, self._i_bound, self._h0, self._d0):
            sb.valueChanged.connect(self._recompute)

    @staticmethod
    def _spin(lo: float, hi: float, decimals: int, value: float, suffix: str) -> NoScrollDoubleSpinBox:
        sb = NoScrollDoubleSpinBox()
        sb.setRange(lo, hi)
        sb.setDecimals(decimals)
        sb.setValue(value)
        sb.setSuffix(suffix)
        return sb

    # ------------------------------------------------------------------
    # Simulation
    # ------------------------------------------------------------------
    def _recompute(self) -> None:
        _label, mode, x_species = _MODES[self._mode.currentIndex()]
        h0 = self._h0.value() * 1e-6  # µM → M
        d0 = self._d0.value() * 1e-6  # µM → M

        if mode == 'HtoD':  # titrate host into fixed dye
            titrant_max, y_fixed = h0, d0
        else:  # DtoH: titrate dye into fixed host
            titrant_max, y_fixed = d0, h0

        x_titrant = np.linspace(0.0, titrant_max, _N_POINTS)
        signal = dba_signal(
            self._i0.value(),
            self._ka.value(),
            self._i_free.value(),
            self._i_bound.value(),
            x_titrant,
            y_fixed,
            mode=mode,
        )

        self._curve.setData(x_titrant * 1e6, signal)  # plot titrant in µM
        self._plot.setLabel('bottom', f'[{x_species}] (µM)')

    # ------------------------------------------------------------------
    # Introspection (used by tests)
    # ------------------------------------------------------------------
    def curve_xy(self) -> tuple[np.ndarray, np.ndarray]:
        """Return the current plotted ``(x_µM, signal)`` arrays."""
        return self._curve.getData()
