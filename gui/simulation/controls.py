"""Reusable live controls for the simulation applet.

These are generic and assay-agnostic — they render whatever :class:`SimKnob` /
concentration / noise configuration they are given, so the same widgets serve
every assay.

* :class:`ParameterControl` — one knob: a slider with user-editable [min, max]
  bounds and an exact-value field.  Log slider for association constants, linear
  otherwise; a nM/µM/mM/M selector for concentrations; negatives allowed for
  signal coefficients (e.g. a calibration intercept).
* :class:`ConcentrationInput` — the titrant vector, via explicit / linear /
  start-step / log modes.
* :class:`NoiseControl` — optional Gaussian measurement noise (fraction of the
  signal range) with replicas and a seed.
"""

from __future__ import annotations

import math

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSlider,
    QWidget,
)

from core.units import Q_
from gui.simulation.sim_knob import SimKnob
from gui.widgets.numeric_inputs import NoScrollDoubleSpinBox, NoScrollSpinBox

_SLIDER_STEPS = 1000

# nM/µM/mM/M selector for concentration knobs/inputs.  The label set is a UI
# choice; the conversion factors are always derived from Pint (_display_factor),
# never hardcoded.
_CONC_LABELS: tuple[str, ...] = ('nM', 'µM', 'mM', 'M')
_CONC_DEFAULT = 'µM'


def _new_spin(*, decimals: int = 4, vmin: float = -1e15, vmax: float = 1e15) -> NoScrollDoubleSpinBox:
    sb = NoScrollDoubleSpinBox()
    sb.setDecimals(decimals)
    sb.setRange(vmin, vmax)
    sb.setKeyboardTracking(False)
    sb.setMinimumWidth(96)
    return sb


class ParameterControl(QWidget):
    """A single live knob: slider + editable bounds + exact value.

    Internals are kept in **base units** (M / M⁻¹ / au / au·M⁻¹); for concentration
    knobs a unit selector only rescales the *display*.  ``changed`` fires on every
    user adjustment.
    """

    changed = pyqtSignal()

    def __init__(self, knob: SimKnob, parent=None):
        super().__init__(parent)
        self._knob = knob
        self._log = knob.log
        self._value = float(knob.default)
        self._vmin = float(knob.vmin)
        self._vmax = float(knob.vmax)
        self._scale = _display_factor(_CONC_DEFAULT, knob.unit) if knob.is_concentration else 1.0

        grid = QGridLayout(self)
        grid.setContentsMargins(0, 2, 0, 6)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(2)

        # Row 0: label, value, unit (combo for concentration, static label else).
        name = QLabel(knob.label)
        name.setTextFormat(Qt.TextFormat.RichText)
        name.setToolTip(knob.tooltip)
        self._value_spin = _new_spin()
        self._value_spin.setToolTip(knob.tooltip)
        grid.addWidget(name, 0, 0)
        grid.addWidget(self._value_spin, 0, 1)
        if knob.is_concentration:
            self._unit_combo: QComboBox | None = QComboBox()
            self._unit_combo.addItems(list(_CONC_LABELS))
            self._unit_combo.setCurrentText(_CONC_DEFAULT)
            self._unit_combo.currentTextChanged.connect(self._on_unit_changed)
            grid.addWidget(self._unit_combo, 0, 2)
        else:
            self._unit_combo = None
            grid.addWidget(QLabel(f'{knob.unit:~P}'), 0, 2)

        # Row 1: min, slider, max.  Concentrations/association constants stay ≥ 0;
        # signal coefficients (incl. a calibration intercept) may go negative.
        floor = -1e15 if knob.allows_negative else 0.0
        self._min_spin = _new_spin(vmin=floor)
        self._max_spin = _new_spin(vmin=floor)
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, _SLIDER_STEPS)
        grid.addWidget(self._min_spin, 1, 0)
        grid.addWidget(self._slider, 1, 1)
        grid.addWidget(self._max_spin, 1, 2)

        self._sync_all()

        self._slider.valueChanged.connect(self._on_slider)
        self._value_spin.valueChanged.connect(self._on_value_edit)
        self._min_spin.valueChanged.connect(self._on_bounds_edit)
        self._max_spin.valueChanged.connect(self._on_bounds_edit)

    # -- public API ----------------------------------------------------------

    def value(self) -> float:
        """Current value in the base unit (M / M⁻¹ / au / au·M⁻¹)."""
        return self._value

    def quantity(self):
        """Current value as a pint Quantity (for assay conditions)."""
        return Q_(self._value, self._knob.unit)

    def state(self) -> dict:
        """Serializable knob state for settings save."""
        return {'value': self._value, 'min': self._vmin, 'max': self._vmax}

    def load_state(self, state: dict) -> None:
        self._vmin = float(state.get('min', self._vmin))
        self._vmax = float(state.get('max', self._vmax))
        self._value = _clamp(float(state.get('value', self._value)), self._vmin, self._vmax)
        self._sync_all()
        self.changed.emit()

    # -- slider <-> value mapping -------------------------------------------

    def _pos_to_value(self, pos: int) -> float:
        f = pos / _SLIDER_STEPS
        if self._log and self._vmin > 0 and self._vmax > self._vmin:
            lo, hi = math.log10(self._vmin), math.log10(self._vmax)
            return 10 ** (lo + f * (hi - lo))
        return self._vmin + f * (self._vmax - self._vmin)

    def _value_to_pos(self, v: float) -> int:
        if self._vmax <= self._vmin:
            return 0
        if self._log and self._vmin > 0 and self._vmax > self._vmin:
            lo, hi = math.log10(self._vmin), math.log10(self._vmax)
            f = (math.log10(max(v, self._vmin)) - lo) / (hi - lo)
        else:
            f = (v - self._vmin) / (self._vmax - self._vmin)
        return int(round(_clamp(f, 0.0, 1.0) * _SLIDER_STEPS))

    # -- sync helpers (block signals to avoid feedback loops) ---------------

    def _sync_all(self) -> None:
        self._sync_bounds_spins()
        self._sync_value_spin()
        self._sync_slider()

    def _sync_value_spin(self) -> None:
        self._value_spin.blockSignals(True)
        self._value_spin.setValue(self._value / self._scale)
        self._value_spin.blockSignals(False)

    def _sync_bounds_spins(self) -> None:
        for sb, val in ((self._min_spin, self._vmin), (self._max_spin, self._vmax)):
            sb.blockSignals(True)
            sb.setValue(val / self._scale)
            sb.blockSignals(False)

    def _sync_slider(self) -> None:
        self._slider.blockSignals(True)
        self._slider.setValue(self._value_to_pos(self._value))
        self._slider.blockSignals(False)

    # -- slots ---------------------------------------------------------------

    def _on_slider(self, pos: int) -> None:
        self._value = self._pos_to_value(pos)
        self._sync_value_spin()
        self.changed.emit()

    def _on_value_edit(self, shown: float) -> None:
        self._value = _clamp(shown * self._scale, self._vmin, self._vmax)
        self._sync_slider()
        self.changed.emit()

    def _on_bounds_edit(self) -> None:
        vmin = self._min_spin.value() * self._scale
        vmax = self._max_spin.value() * self._scale
        if self._log:
            vmin = max(vmin, 1e-12)  # log slider needs a positive floor
        if vmax <= vmin:
            vmax = vmin * 10 if self._log else vmin + abs(vmin or 1.0)
        self._vmin, self._vmax = vmin, vmax
        self._value = _clamp(self._value, vmin, vmax)
        self._sync_all()
        self.changed.emit()

    def _on_unit_changed(self, label: str) -> None:
        self._scale = _display_factor(label, self._knob.unit)
        self._sync_value_spin()
        self._sync_bounds_spins()


class ConcentrationInput(QWidget):
    """Titrant concentration vector with selectable input modes.

    ``spec()`` returns ``(mode, kwargs)`` (concentrations in M) ready for
    :func:`core.simulation.build_concentration_vector`.
    """

    changed = pyqtSignal()

    _MODES = [
        ('Linear (start, stop, N)', 'linear'),
        ('Start, step, N', 'step'),
        ('Log (start, stop, N)', 'log'),
        ('Explicit vector', 'explicit'),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        # The titrant vector is always Molar; the selector only rescales the display.
        self._scale = _display_factor(_CONC_DEFAULT, 'M')

        form = QFormLayout(self)
        form.setContentsMargins(0, 0, 0, 0)

        self._mode = QComboBox()
        for label, key in self._MODES:
            self._mode.addItem(label, userData=key)
        self._mode.currentIndexChanged.connect(self._on_mode_changed)

        self._unit = QComboBox()
        self._unit.addItems(list(_CONC_LABELS))
        self._unit.setCurrentText(_CONC_DEFAULT)
        self._unit.currentTextChanged.connect(self._on_unit_changed)
        mode_row = QWidget()
        mr = QHBoxLayout(mode_row)
        mr.setContentsMargins(0, 0, 0, 0)
        mr.addWidget(self._mode, 1)
        mr.addWidget(self._unit)
        form.addRow('Mode', mode_row)

        self._start = _new_spin(vmin=0.0)
        self._stop = _new_spin(vmin=0.0)
        self._step = _new_spin(vmin=0.0)
        self._n = NoScrollSpinBox()
        self._n.setRange(2, 100000)
        self._n.setValue(11)
        self._explicit = QLineEdit()
        self._explicit.setPlaceholderText('e.g. 0, 1, 2.5, 5, 10')

        # Rows are shown/hidden per mode.
        self._row_start = self._add_row(form, 'Start', self._start)
        self._row_stop = self._add_row(form, 'Stop', self._stop)
        self._row_step = self._add_row(form, 'Step', self._step)
        self._row_n = self._add_row(form, 'Points (N)', self._n)
        self._row_explicit = self._add_row(form, 'Values', self._explicit)

        for sb in (self._start, self._stop, self._step):
            sb.valueChanged.connect(self.changed)
        self._n.valueChanged.connect(self.changed)
        self._explicit.textChanged.connect(self.changed)

        self._apply_mode_visibility('linear')

    @staticmethod
    def _add_row(form: QFormLayout, label: str, w: QWidget):
        lbl = QLabel(label)
        form.addRow(lbl, w)
        return (lbl, w)

    def current_mode(self) -> str:
        return self._mode.currentData()

    def set_linear(self, start_m: float, stop_m: float, n: int) -> None:
        """Programmatically set a linear range (Molar). Used on assay change."""
        self._mode.blockSignals(True)
        self._mode.setCurrentIndex(0)
        self._mode.blockSignals(False)
        self._apply_mode_visibility('linear')
        for sb, val in ((self._start, start_m), (self._stop, stop_m)):
            sb.blockSignals(True)
            sb.setValue(val / self._scale)
            sb.blockSignals(False)
        self._n.blockSignals(True)
        self._n.setValue(int(n))
        self._n.blockSignals(False)
        self.changed.emit()

    def spec(self) -> tuple[str, dict]:
        mode = self.current_mode()
        s = self._scale
        if mode == 'linear':
            return mode, {'start': self._start.value() * s, 'stop': self._stop.value() * s, 'n': self._n.value()}
        if mode == 'step':
            return mode, {'start': self._start.value() * s, 'step': self._step.value() * s, 'n': self._n.value()}
        if mode == 'log':
            return mode, {'start': self._start.value() * s, 'stop': self._stop.value() * s, 'n': self._n.value()}
        return mode, {'values': [v * s for v in _parse_floats(self._explicit.text())]}

    def load_spec(self, mode: str, kwargs: dict) -> None:
        idx = next((i for i, (_, k) in enumerate(self._MODES) if k == mode), 0)
        self._mode.blockSignals(True)
        self._mode.setCurrentIndex(idx)
        self._mode.blockSignals(False)
        self._apply_mode_visibility(mode)
        s = self._scale
        if mode in ('linear', 'log'):
            self._set_silent(self._start, kwargs.get('start', 0.0) / s)
            self._set_silent(self._stop, kwargs.get('stop', 0.0) / s)
            self._set_n(kwargs.get('n', 11))
        elif mode == 'step':
            self._set_silent(self._start, kwargs.get('start', 0.0) / s)
            self._set_silent(self._step, kwargs.get('step', 0.0) / s)
            self._set_n(kwargs.get('n', 11))
        else:
            self._explicit.blockSignals(True)
            self._explicit.setText(', '.join(f'{v / s:g}' for v in kwargs.get('values', [])))
            self._explicit.blockSignals(False)
        self.changed.emit()

    # -- internals -----------------------------------------------------------

    @staticmethod
    def _set_silent(sb: NoScrollDoubleSpinBox, val: float) -> None:
        sb.blockSignals(True)
        sb.setValue(val)
        sb.blockSignals(False)

    def _set_n(self, n) -> None:
        self._n.blockSignals(True)
        self._n.setValue(int(n))
        self._n.blockSignals(False)

    def _on_mode_changed(self) -> None:
        self._apply_mode_visibility(self.current_mode())
        self.changed.emit()

    def _on_unit_changed(self) -> None:
        self._scale = _display_factor(self._unit.currentText(), 'M')
        self.changed.emit()

    def _apply_mode_visibility(self, mode: str) -> None:
        show = {
            'linear': {'start', 'stop', 'n'},
            'step': {'start', 'step', 'n'},
            'log': {'start', 'stop', 'n'},
            'explicit': {'explicit'},
        }[mode]
        for key, (lbl, w) in {
            'start': self._row_start,
            'stop': self._row_stop,
            'step': self._row_step,
            'n': self._row_n,
            'explicit': self._row_explicit,
        }.items():
            visible = key in show
            lbl.setVisible(visible)
            w.setVisible(visible)


class NoiseControl(QWidget):
    """Optional Gaussian measurement noise: enable, fraction-of-range, replicas, seed."""

    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        form = QFormLayout(self)
        form.setContentsMargins(0, 0, 0, 0)

        self._enable = QCheckBox('Add measurement noise')
        self._enable.toggled.connect(self._on_toggle)
        form.addRow(self._enable)

        self._frac = NoScrollDoubleSpinBox()
        self._frac.setRange(0.0, 100.0)
        self._frac.setDecimals(2)
        self._frac.setValue(5.0)
        self._frac.setSuffix(' %')
        self._frac.valueChanged.connect(self.changed)
        form.addRow('Noise', self._frac)

        self._replicas = NoScrollSpinBox()
        self._replicas.setRange(1, 50)
        self._replicas.setValue(3)
        self._replicas.valueChanged.connect(self.changed)
        form.addRow('Replicas', self._replicas)

        self._seed = NoScrollSpinBox()
        self._seed.setRange(0, 1_000_000)
        self._seed.setValue(0)
        self._seed.valueChanged.connect(self.changed)
        form.addRow('Seed', self._seed)

        self._on_toggle(False)

    def _on_toggle(self, on: bool) -> None:
        for w in (self._frac, self._replicas, self._seed):
            w.setEnabled(on)
        self.changed.emit()

    def settings(self) -> dict:
        return {
            'enabled': self._enable.isChecked(),
            'frac': self._frac.value() / 100.0,
            'replicas': self._replicas.value(),
            'seed': self._seed.value(),
        }

    def load_settings(self, s: dict) -> None:
        for w, val in (
            (self._enable, bool(s.get('enabled', False))),
            (self._frac, float(s.get('frac', 0.05)) * 100.0),
            (self._replicas, int(s.get('replicas', 3))),
            (self._seed, int(s.get('seed', 0))),
        ):
            w.blockSignals(True)
            w.setChecked(val) if w is self._enable else w.setValue(val)
            w.blockSignals(False)
        self._on_toggle(self._enable.isChecked())


# ---------------------------------------------------------------------------
# Module helpers
# ---------------------------------------------------------------------------


def _display_factor(label: str, base) -> float:
    """Pint-derived scale: magnitude of ``1 <label>`` expressed in ``base`` units.

    ``base`` is a pint ``Unit`` (a knob's canonical unit) or a unit string. The
    shared registry (``core.units``) is the single source of every factor.
    """
    return float(Q_(1, label).to(base).magnitude)


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _parse_floats(text: str) -> list[float]:
    """Parse a comma/space-separated list of floats; raise ValueError if any token is bad."""
    tokens = [t for t in text.replace(',', ' ').split() if t]
    if not tokens:
        return []
    try:
        return [float(t) for t in tokens]
    except ValueError as exc:
        raise ValueError(f'Invalid concentration value in: {text!r}') from exc
