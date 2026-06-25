"""Tests for the DBA forward-simulation dialog (#23).

These verify the *wiring* between the parameter widgets and the shared
forward model — that the dialog reads its controls, converts units, picks
the titration direction, and plots ``dba_signal`` correctly. The model math
itself is covered by the equilibrium-model tests; here the independent check
is a direct ``dba_signal`` call with the same stated parameters plus a
model-agnostic monotonicity argument.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip('PyQt6')

from core.models.equilibrium import dba_signal
from gui.dialogs.simulator_dialog import SimulatorDialog


def _set_params(dlg, *, ka, i0, i_free, i_bound, h0_uM, d0_uM, mode_index):
    """Drive the dialog's widgets to a known state (triggers live recompute)."""
    dlg._mode.setCurrentIndex(mode_index)
    dlg._ka.setValue(ka)
    dlg._i0.setValue(i0)
    dlg._i_free.setValue(i_free)
    dlg._i_bound.setValue(i_bound)
    dlg._h0.setValue(h0_uM)
    dlg._d0.setValue(d0_uM)


class TestSimulatorWiring:
    """Plotted curve must equal the model called with the widgets' values."""

    def test_curve_matches_dba_signal_host_to_dye(self, qapp):
        dlg = SimulatorDialog()
        _set_params(dlg, ka=5e5, i0=0.0, i_free=5e7, i_bound=3e8, h0_uM=50.0, d0_uM=5.0, mode_index=0)

        x_uM, y = dlg.curve_xy()
        assert len(x_uM) > 1
        # HtoD titrates host 0 → [Host]₀ (50 µM); dye is the fixed species.
        assert np.nanmax(x_uM) == pytest.approx(50.0)
        expected = dba_signal(0.0, 5e5, 5e7, 3e8, np.asarray(x_uM) * 1e-6, 5e-6, mode='HtoD')
        np.testing.assert_allclose(y, expected, rtol=1e-9, equal_nan=True)

    def test_mode_switch_titrates_dye_and_fixes_host(self, qapp):
        dlg = SimulatorDialog()
        _set_params(dlg, ka=5e5, i0=0.0, i_free=5e7, i_bound=3e8, h0_uM=50.0, d0_uM=5.0, mode_index=1)

        x_uM, y = dlg.curve_xy()
        # DtoH titrates dye 0 → [Dye]₀ (5 µM); host (50 µM) is now fixed.
        assert np.nanmax(x_uM) == pytest.approx(5.0)
        expected = dba_signal(0.0, 5e5, 5e7, 3e8, np.asarray(x_uM) * 1e-6, 50e-6, mode='DtoH')
        np.testing.assert_allclose(y, expected, rtol=1e-9, equal_nan=True)

    def test_live_update_on_parameter_change(self, qapp):
        dlg = SimulatorDialog()
        _set_params(dlg, ka=5e5, i0=0.0, i_free=5e7, i_bound=3e8, h0_uM=50.0, d0_uM=5.0, mode_index=0)
        _x, y_before = dlg.curve_xy()

        dlg._ka.setValue(5e7)  # 100× stronger binding reshapes the curve
        _x, y_after = dlg.curve_xy()

        assert not np.allclose(y_before, y_after, equal_nan=True)

    def test_signal_rises_monotonically_when_bound_is_brighter(self, qapp):
        """Model-agnostic physics check: with the host-dye complex brighter
        than free dye, signal must rise monotonically as host saturates."""
        dlg = SimulatorDialog()
        _set_params(dlg, ka=5e5, i0=0.0, i_free=5e7, i_bound=3e8, h0_uM=50.0, d0_uM=5.0, mode_index=0)

        _x, y = dlg.curve_xy()
        y = np.asarray(y, dtype=float)
        diffs = np.diff(y[np.isfinite(y)])
        assert (diffs >= -1e-6).all()
