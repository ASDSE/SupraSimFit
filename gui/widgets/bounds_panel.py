"""BoundsPanel — registry-driven parameter bounds editor with dye-alone priors."""

from __future__ import annotations

import logging
import math
from pathlib import Path

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QDoubleValidator
from PyQt6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.assays.registry import ASSAY_REGISTRY, AssayType
from core.units import Q_, Quantity
from gui.parameter_descriptions import PARAMETER_DESCRIPTIONS
from gui.plotting.labels import fmt_param, fmt_param_plain
from gui.widgets.info_button import InfoButton, InfoGroupBox

logger = logging.getLogger(__name__)

_DYE_ALONE_PRIOR_HTML = """
<h3>Use Dye-Alone Priors for Signal Bounds</h3>

<p><b>What It Does</b></p>
<p>When enabled, the fitter clamps the bounds of the two signal coefficients
&mdash; <i>I<sub>0</sub></i> (baseline) and <i>I<sub>dye,free</sub></i>
(free-dye response) &mdash; to a narrow window around the values recovered
from a prior <b>Dye Alone</b> calibration. The window is the calibration
result &plusmn;&nbsp;20&nbsp;%.</p>

<p><b>Why It Helps the Fit</b></p>
<p>In IDA, DBA and GDA the three signal coefficients
(I<sub>0</sub>, I<sub>dye,free</sub>, I<sub>dye,bound</sub>) are partially
degenerate &mdash; many combinations give nearly the same curve, so the fit
reports them starred: only their combination is determined. Confining two of
them to what the dye-alone experiment measured breaks that degeneracy, which
makes all three coefficients meaningful on their own and narrows the
confidence interval of the association constant.</p>

<p><b>The Math</b></p>
<p>A dye-alone fit gives
<i>S = slope &middot; [D] + intercept</i>, so
<i>I<sub>dye,free</sub> = slope</i> and
<i>I<sub>0</sub> = intercept</i>. This panel then sets</p>
<p align="center">
  <i>I<sub>0</sub> &isin; [0.8 &middot; intercept, 1.2 &middot; intercept]</i><br>
  <i>I<sub>dye,free</sub> &isin; [0.8 &middot; slope, 1.2 &middot; slope]</i>
</p>

<p><b>How to Use It</b></p>
<ol>
  <li>Record a dye-only calibration on the same instrument and the same
      day as your titration.</li>
  <li>Click <b>Load Dye-Alone&hellip;</b>. The dialog runs a linear fit on
      the file and pushes the result into the I<sub>0</sub> and
      I<sub>dye,free</sub> rows above.</li>
  <li>Tick <b>Use dye-alone priors for signal bounds</b> to enable the
      clamp for the next fit.</li>
</ol>
<p>If you haven&rsquo;t loaded a dye-alone file, the checkbox has no
effect &mdash; the normal registry defaults apply.</p>

<p><b>See Also</b></p>
<p>Click the <i>Dye Alone</i> entry in the assay selector to read about
the calibration itself.</p>
"""


def _parse_sci(text: str) -> float | None:
    """The finite number *text* holds, or ``None``."""
    try:
        value = float(text)
    except (ValueError, TypeError):
        return None
    return value if math.isfinite(value) else None


def _bound_text(value: float) -> str:
    """What a bound box shows: the number, or nothing for no limit."""
    return f'{value:.3e}' if math.isfinite(value) else ''


class _BoundRow(QWidget):
    """A single row: lower QLineEdit | '—' | upper QLineEdit | info ⓘ.

    Both boxes take a number in plain or scientific notation and nothing else.
    A parameter whose default upper bound is infinite — a signal parameter — has
    no upper limit while its upper box is empty, and the box says so.
    :meth:`problem` says in one sentence why what they hold cannot be used, naming
    the parameter and the box, so no entry is quietly replaced by a default.
    """

    def __init__(self, key: str, lo: float, hi: float, parent=None):
        super().__init__(parent)
        self.key = key
        self.name = fmt_param_plain(key)
        self._may_be_unbounded = math.isinf(hi)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        self._lo = self._edit(lo)
        self._hi = self._edit(hi)
        if self._may_be_unbounded:
            self._hi.setPlaceholderText('no limit')
        row.addWidget(self._lo)
        row.addWidget(QLabel('—'))
        row.addWidget(self._hi)
        row.addStretch(1)

        title, body = PARAMETER_DESCRIPTIONS.get(
            key,
            (key, f'<p>No description available for <b>{key}</b>.</p>'),
        )
        row.addWidget(InfoButton(title, body))

    @staticmethod
    def _edit(value: float) -> QLineEdit:
        """A bound box showing *value*, accepting only a number as it is typed."""
        edit = QLineEdit(_bound_text(value))
        edit.setFixedWidth(90)
        validator = QDoubleValidator(edit)
        validator.setNotation(QDoubleValidator.Notation.ScientificNotation)
        edit.setValidator(validator)
        return edit

    def _upper(self) -> float | None:
        """The upper bound entered; infinite for an empty box of a parameter that may have no upper limit."""
        if self._may_be_unbounded and not self._hi.text().strip():
            return math.inf
        return _parse_sci(self._hi.text())

    def values(self) -> tuple[float, float] | None:
        lo = _parse_sci(self._lo.text())
        hi = self._upper()
        if lo is None or hi is None:
            return None
        return lo, hi

    def problem(self) -> str | None:
        """Why this row's bounds cannot be used, naming the parameter; ``None`` when they can."""
        for box, edge, value in ((self._lo, 'lower', _parse_sci(self._lo.text())), (self._hi, 'upper', self._upper())):
            if value is None:
                shown = box.text().strip()
                says = f'“{shown}” is not a number' if shown else 'is empty'
                return f'{self.name}: the {edge} bound {says}. Enter a number, such as 1e3.'
        lo, hi = self.values()
        # Equal bounds are a deliberate pin: the parameter is held at that value
        # and not fitted, which the Identifiability tab reports for Ka.
        if lo > hi:
            return f'{self.name}: the lower bound must not be above the upper bound.'
        return None

    def set_values(self, lo: float, hi: float) -> None:
        self._lo.setText(_bound_text(lo))
        self._hi.setText(_bound_text(hi))


_BOUNDS_SECTION_HELP_HTML = """
<h3>Parameter Bounds</h3>
<p>Lower and upper limits for each fitted parameter. Defaults come from the
assay registry; edit them to constrain the fit if you have prior
knowledge.</p>
<p>A signal parameter cannot be negative and has no upper limit unless you
enter one: leave its upper box empty for none.</p>
<p>The two kinds of parameter use their bounds differently. An association
constant is searched across its bounds, so they set the range the fit and the
confidence interval are looked for in. A signal parameter is not searched at
all: its value is solved exactly at each association constant, subject to
these bounds, so a bound the best value lies outside of holds it at that bound
&mdash; and equal lower and upper bounds pin the parameter at that value and
take it out of the fit.</p>
<p>See the <i>i</i> next to each parameter for its physical meaning.
See the <i>i</i> next to &ldquo;Use dye-alone priors&rdquo; for how
calibration data can tighten signal-coefficient bounds
automatically.</p>
<p>The confidence interval on the Identifiability tab is read inside these
bounds, and an end that reaches one is reported as open rather than as a
measured limit. The interval holds if the model is right, the conditions you
entered are right, and the scatter is independent from point to point and of
the same size at every point; it says nothing about an error in any of
those.</p>
"""


class BoundsPanel(InfoGroupBox):
    """Registry-driven parameter bounds editor.

    Auto-populates from ``ASSAY_REGISTRY[assay_type].default_bounds`` when the
    assay type changes.  Supports loading dye-alone priors to constrain the
    signal coefficient parameters. A bound that cannot be used is named under the
    rows and reported by :meth:`problems`.

    Signals
    -------
    bounds_changed()
        Emitted when any bound field is edited.
    dye_alone_requested()
        Emitted when the user clicks 'Load Dye-Alone…'.
    """

    bounds_changed = pyqtSignal()
    dye_alone_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__('Parameter Bounds', 'Parameter Bounds', _BOUNDS_SECTION_HELP_HTML, parent)
        self._rows: dict[str, _BoundRow] = {}
        self._defaults: dict[str, tuple[float, float]] = {}
        self._units: dict[str, str] = {}  # key -> unit string for Quantity wrapping
        self._setup_ui()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_assay_type(self, assay_type: AssayType) -> None:
        meta = ASSAY_REGISTRY[assay_type]
        # Extract magnitudes and units from Quantity bounds
        self._defaults = {}
        self._units = dict(meta.units)
        for key, (lo, hi) in meta.default_bounds.items():
            lo_f = float(lo.magnitude) if isinstance(lo, Quantity) else float(lo)
            hi_f = float(hi.magnitude) if isinstance(hi, Quantity) else float(hi)
            self._defaults[key] = (lo_f, hi_f)
        self._rebuild_form(self._defaults)

    def problems(self) -> list[str]:
        """Why the bounds shown cannot be used, one sentence per row naming the parameter; empty when they can.

        The same sentences are shown in the panel as the user types. Check this
        before running a fit: a row with a problem carries no bounds into
        :meth:`current_bounds`, so the fit would search the registry defaults there.
        """
        return [problem for row in self._rows.values() if (problem := row.problem())]

    def shown_bounds(self) -> dict[str, tuple[Quantity, Quantity] | None]:
        """Every row's bounds as Quantities in the parameter's unit; ``None`` for a row :meth:`problems` names."""
        shown: dict[str, tuple[Quantity, Quantity] | None] = {}
        for key, row in self._rows.items():
            unit = self._units.get(key, 'dimensionless')
            values = None if row.problem() is not None else row.values()
            shown[key] = None if values is None else (Q_(values[0], unit), Q_(values[1], unit))
        return shown

    def current_bounds(self) -> dict[str, tuple[Quantity, Quantity]] | None:
        """The bounds that differ from the registry defaults, as Quantities; ``None`` when none does.

        A row :meth:`problems` names is left out; the panel shows why.
        """
        changed = {
            key: bounds
            for key, bounds in self.shown_bounds().items()
            if bounds is not None and (bounds[0].magnitude, bounds[1].magnitude) != self._defaults[key]
        }
        return changed or None

    def apply_dye_alone_bounds(self, bounds: dict[str, tuple[Quantity, Quantity]]) -> None:
        """Apply dye-alone–derived bounds to I0 and I_dye_free rows."""
        for key, (lo, hi) in bounds.items():
            lo_f = float(lo.magnitude) if isinstance(lo, Quantity) else float(lo)
            hi_f = float(hi.magnitude) if isinstance(hi, Quantity) else float(hi)
            if key in self._rows:
                self._rows[key].set_values(lo_f, hi_f)
        self.bounds_changed.emit()

    def reset_to_defaults(self) -> None:
        for key, (lo, hi) in self._defaults.items():
            if key in self._rows:
                self._rows[key].set_values(lo, hi)
        self.bounds_changed.emit()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Form area
        self._form_widget = QWidget()
        self._form_layout = QFormLayout(self._form_widget)
        self._form_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._form_widget)

        # Names every bound that cannot be used, as it is typed.
        self._warning = QLabel()
        self._warning.setWordWrap(True)
        self._warning.setStyleSheet('color: #b42318;')
        self._warning.hide()
        layout.addWidget(self._warning)
        self.bounds_changed.connect(self._refresh_warning)

        # Reset defaults button — compact, centred
        reset_row = QHBoxLayout()
        reset_btn = QPushButton('Reset to Defaults')
        reset_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        reset_btn.clicked.connect(self.reset_to_defaults)
        reset_row.addStretch(1)
        reset_row.addWidget(reset_btn)
        reset_row.addStretch(1)
        layout.addLayout(reset_row)

        # Dye-alone section with its own info button
        self._dye_alone_cb = QCheckBox('Use dye-alone priors for signal bounds')
        self._dye_alone_cb.toggled.connect(self._on_dye_alone_toggled)
        dye_cb_row = QHBoxLayout()
        dye_cb_row.setContentsMargins(0, 0, 0, 0)
        dye_cb_row.addWidget(self._dye_alone_cb)
        dye_cb_row.addWidget(InfoButton('Dye-alone priors', _DYE_ALONE_PRIOR_HTML))
        dye_cb_row.addStretch(1)
        layout.addLayout(dye_cb_row)

        # Load dye-alone button — compact, centred
        dye_btn_row = QHBoxLayout()
        self._dye_alone_btn = QPushButton('Load Dye-Alone…')
        self._dye_alone_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._dye_alone_btn.setEnabled(False)
        self._dye_alone_btn.clicked.connect(self._on_load_dye_alone)
        dye_btn_row.addStretch(1)
        dye_btn_row.addWidget(self._dye_alone_btn)
        dye_btn_row.addStretch(1)
        layout.addLayout(dye_btn_row)

    def _rebuild_form(self, default_bounds: dict) -> None:
        self._rows.clear()
        while self._form_layout.rowCount():
            self._form_layout.removeRow(0)

        for key, (lo, hi) in default_bounds.items():
            row = _BoundRow(key, lo, hi)
            row._lo.textChanged.connect(self.bounds_changed)
            row._hi.textChanged.connect(self.bounds_changed)
            self._form_layout.addRow(fmt_param(key) + ':', row)
            self._rows[key] = row
        self._refresh_warning()

    def _refresh_warning(self) -> None:
        """Show every problem the rows report, or nothing when there are none."""
        text = '\n'.join(self.problems())
        self._warning.setText(text)
        self._warning.setVisible(bool(text))

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_dye_alone_toggled(self, checked: bool) -> None:
        self._dye_alone_btn.setEnabled(checked)

    def _on_load_dye_alone(self) -> None:
        from core.assays import DyeAloneAssay
        from core.data_processing.measurement_set import InvalidData, MeasurementSet
        from core.io import load_measurements
        from core.io.registry import READERS
        from core.pipeline.fit_pipeline import bounds_from_dye_alone, fit_linear_assay

        exts = ' '.join(f'*{e}' for e in sorted(READERS.keys()))
        path, _ = QFileDialog.getOpenFileName(
            self, 'Load Dye-Alone Data', '', f'Measurement files ({exts});;All files (*)'
        )
        if not path:
            return
        try:
            ms = MeasurementSet.from_dataframe(load_measurements(path), source_file=path)
            assay = ms.to_assay(DyeAloneAssay, conditions={})
            result = fit_linear_assay(assay)
            bounds = bounds_from_dye_alone(result, margin=0.2)
            self.apply_dye_alone_bounds(bounds)
            QMessageBox.information(
                self,
                'Dye-Alone Loaded',
                'Signal coefficient bounds updated from dye-alone fit.',
            )
        except InvalidData as exc:
            # Written for the user: it names the file, the replicate and the point, and the fix.
            QMessageBox.warning(self, 'Dye-Alone Error', f'{exc} The signal bounds were not changed.')
        except Exception:
            logger.exception('Could not fit the dye-alone data in %s', path)
            QMessageBox.warning(
                self,
                'Dye-Alone Error',
                f'Could not fit a straight line to the dye-alone data in {Path(path).name}. Check that the file '
                'is a measurement of the dye alone, with its concentrations, then load it again. The signal bounds '
                'were not changed.',
            )
