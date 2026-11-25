"""BoundsPanel — registry-driven parameter bounds editor with dye-alone priors."""

from __future__ import annotations

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
from gui.plotting.labels import fmt_param, plain_label
from gui.widgets.info_button import InfoButton, InfoGroupBox

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
degenerate &mdash; many combinations give nearly the same curve. Fixing two
of them from the dye-alone experiment breaks that degeneracy and lets the
optimiser concentrate its budget on K<sub>a,guest</sub> (or
K<sub>a,dye</sub>). In practice this substantially improves both
convergence speed and the uncertainty on the association constant.</p>

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
    try:
        return float(text)
    except (ValueError, TypeError):
        return None


class _BoundRow(QWidget):
    """A single row: lower QLineEdit | '—' | upper QLineEdit | info ⓘ.

    Both boxes take a number in plain or scientific notation and nothing else.
    :meth:`problem` says in one sentence why what they hold cannot be used, naming
    the parameter and the box, so no entry is quietly replaced by a default.
    """

    def __init__(self, key: str, lo: float, hi: float, parent=None):
        super().__init__(parent)
        self.key = key
        self.name = plain_label(fmt_param(key))
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        self._lo = self._edit(lo)
        self._hi = self._edit(hi)
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
        edit = QLineEdit(f'{value:.3e}')
        edit.setFixedWidth(90)
        validator = QDoubleValidator(edit)
        validator.setNotation(QDoubleValidator.Notation.ScientificNotation)
        edit.setValidator(validator)
        return edit

    def values(self) -> tuple[float, float] | None:
        lo = _parse_sci(self._lo.text())
        hi = _parse_sci(self._hi.text())
        if lo is None or hi is None:
            return None
        return lo, hi

    def problem(self) -> str | None:
        """Why this row's bounds cannot be used, naming the parameter; ``None`` when they can."""
        for box, edge in ((self._lo, 'lower'), (self._hi, 'upper')):
            if _parse_sci(box.text()) is None:
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
        self._lo.setText(f'{lo:.3e}')
        self._hi.setText(f'{hi:.3e}')


_BOUNDS_SECTION_HELP_HTML = """
<h3>Parameter Bounds</h3>
<p>Lower and upper limits for each fitted parameter. The optimiser
searches only within these bounds. Defaults come from the assay
registry; edit them to constrain the search if you have prior
knowledge.</p>
<p>See the <i>i</i> next to each parameter for its physical meaning.
See the <i>i</i> next to &ldquo;Use dye-alone priors&rdquo; for how
calibration data can tighten signal-coefficient bounds
automatically.</p>
<p>These bounds also limit the confidence interval on the Identifiability tab,
which is searched inside them. That interval holds if the model is right, the
conditions you entered are right, and the scatter is independent from point to point
and of the same size at every point; it says nothing about an error in any of those.</p>
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

    def current_bounds(self) -> dict[str, tuple[Quantity, Quantity]] | None:
        """Return custom Quantity bounds or None if all match defaults.

        A row :meth:`problems` names is left out; the panel shows why.
        """
        result_floats = {}
        for key, row in self._rows.items():
            vals = row.values()
            if vals is None or row.problem() is not None:
                continue
            result_floats[key] = vals
        # If all values equal defaults, return None (use registry defaults)
        if result_floats == self._defaults:
            return None
        if not result_floats:
            return None
        # Wrap floats as Quantities
        result = {}
        for key, (lo, hi) in result_floats.items():
            unit = self._units.get(key, 'dimensionless')
            result[key] = (Q_(lo, unit), Q_(hi, unit))
        return result

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
        from core.io.registry import READERS

        exts = ' '.join(f'*{e}' for e in sorted(READERS.keys()))
        path, _ = QFileDialog.getOpenFileName(
            self, 'Load Dye-Alone Data', '', f'Measurement files ({exts});;All files (*)'
        )
        if not path:
            return
        try:
            from core.assays import DyeAloneAssay
            from core.data_processing.measurement_set import MeasurementSet
            from core.io import load_measurements
            from core.pipeline.fit_pipeline import bounds_from_dye_alone, fit_linear_assay

            df = load_measurements(path)
            ms = MeasurementSet.from_dataframe(df)
            assay = ms.to_assay(DyeAloneAssay, conditions={})
            result = fit_linear_assay(assay)
            bounds = bounds_from_dye_alone(result, margin=0.2)
            self.apply_dye_alone_bounds(bounds)
            QMessageBox.information(
                self,
                'Dye-Alone Loaded',
                'Signal coefficient bounds updated from dye-alone fit.',
            )
        except Exception as exc:
            QMessageBox.warning(self, 'Dye-Alone Error', str(exc))
