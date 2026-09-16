"""SensitivityPanel — configure a Ka input-sensitivity run.

The panel exposes the knobs of :class:`~core.pipeline.sensitivity.SensitivityConfig`:
the analysis *mode* (Sobol indices / heatmap), the SOBOL sample size, a ``±%`` variation for every perturbable input (the titrant plus each
concentration / binding-constant condition), the two heatmap axes, and an
optional fixed seed. It emits :attr:`run_requested` / :attr:`cancel_requested`;
the owning session runs the worker and calls :meth:`set_running` to flip the
button. For ``DYE_ALONE`` (no Ka to analyse) the whole panel is disabled.
"""

from __future__ import annotations

import re

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.assays.registry import ASSAY_REGISTRY, AssayType
from core.pipeline.sensitivity import (
    _SOBOL_BLOCKS,
    _SOBOL_SAMPLE_SIZES,
    TITRANT,
    InputSpec,
    ReplicateMode,
    SensitivityConfig,
    SensitivityMode,
    SpecKind,
    perturbable_inputs,
)
from core.units import Q_
from gui.widgets.assay_conditions import ASSAY_CONDITIONS
from gui.widgets.assay_config_panel import _UnitWidget
from gui.widgets.info_button import InfoButton, InfoGroupBox
from gui.widgets.numeric_inputs import NoScrollDoubleSpinBox, NoScrollSpinBox

_SECTION_HELP_HTML = """
<h3>K<sub>a</sub> Sensitivity Analysis</h3>
<p>A fitted association constant is only as good as the <i>inputs</i> you feed
the model — the titrant concentrations and the fixed conditions
(<i>[Host]<sub>0</sub></i>, <i>[Dye]<sub>0</sub></i>, <i>K<sub>a,dye</sub></i>, …).
Each carries pipetting / calibration error, and the fit silently absorbs it by
shifting the reported K<sub>a</sub>.</p>
<p>This tool re-runs the fit many times with those inputs jittered inside the
<i>±%</i> band you set below, and shows the resulting spread of K<sub>a</sub> —
so you can see how much of your uncertainty comes from the inputs rather than
the fit itself.</p>
"""

_MODE_HELP_HTML = """
<h3>Mode</h3>
<ul>
  <li><b>Sensitivity indices</b> — vary every input together and measure how
      much of the spread in K<sub>a</sub> each one is responsible for. You get
      a K<sub>a</sub> distribution plus a share per input: the <i>direct</i>
      share, and the <i>total</i> share which also counts that input acting in
      combination with the others.</li>
  <li><b>Heatmap</b> — sweep two chosen inputs on a regular grid and fit at
      every cell, giving a 2-D K<sub>a</sub> surface.</li>
</ul>
"""

_SAMPLES_HELP_HTML = f"""
<h3>Sample size</h3>
<p>How thoroughly the input space is explored. Every step up doubles the work.</p>
<p>The whisker on each share is its 95% confidence interval. It is built so that
in about 95 of every 100 analyses it contains the share you would get with
unlimited samples for the uncertainties you set. A repeat run with fresh samples
usually lands inside it, but not always.
It is worked out from {_SOBOL_BLOCKS} independent sample sets, and more samples narrow it.
It does not account for errors in the input settings or in the model.</p>
<p>The smallest size offered is {_SOBOL_SAMPLE_SIZES[0]}; choose more when a whisker is too wide
to tell two inputs apart.</p>
"""

_REPLICATES_HELP_HTML = """
<h3>Replicates &mdash; how each perturbed fit uses them</h3>
<p><b>Follow fit setting</b> uses whatever the Fit panel is set to, so the analysis
matches the fit you are studying.</p>
<p><b>Per replica</b> fits each replicate the baseline fit used separately and pools
the passing trials; a replicate the baseline fit leaves out enters no sample.
Replicates carry the measured signal scatter, so this keeps that
uncertainty in the result alongside the input error being sampled.</p>
<p><b>Average replicas</b> fits a single averaged signal. Faster, but it removes the
measured scatter before the analysis starts.</p>
"""

_DELTA_HELP_HTML = """
<h3>Input variation (±%)</h3>
<p>The relative uncertainty of each input. A value of <b>5</b> means that input
is drawn uniformly from <i>−5%</i> to <i>+5%</i> of its configured value on each
fit. Set an input to <b>0</b> to hold it fixed (exclude it from the analysis).</p>
<p>Use realistic numbers: pipetting error is often a few percent, a stated
literature K<sub>a,dye</sub> may be uncertain by 10–20%.</p>
"""

_HEATMAP_HELP_HTML = """
<h3>Heatmap axes</h3>
<p>Choose the two inputs to sweep. Each axis runs from <i>−</i> to <i>+</i> that
input's <i>±%</i> value (set above), split into <i>Grid steps</i> points. The fit
runs once per cell — cost grows as <i>steps²</i>, so 11×11 = 121 fits is a good
starting resolution.</p>
"""

_SEED_HELP_HTML = """
<h3>Fixed seed</h3>
<p>Tick to make the random draws reproducible: the same seed always produces the
same histogram. Leave unticked for a fresh random sample each run.</p>
"""


def _plain(html_label: str) -> str:
    """Strip HTML tags so a rich condition label reads in a plain QComboBox."""
    return re.sub(r'<[^>]+>', '', html_label)


class _InputSpecRow(QWidget):
    """Kind selector plus the value fields that kind needs, for one input.

    A percentage is read against the input's nominal value; an absolute entry
    uses the input's own unit. The titrant is a series with no single nominal
    value, so it offers the percentage kinds only.
    """

    def __init__(self, field, parent=None):
        super().__init__(parent)
        self._field = field

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._kind = QComboBox()
        self._kind.addItem('± σ %', (SpecKind.SIGMA, True))
        self._kind.addItem('range %', (SpecKind.INTERVAL, True))
        if field is not None:
            self._kind.addItem('± σ', (SpecKind.SIGMA, False))
            self._kind.addItem('range', (SpecKind.INTERVAL, False))
        self._kind.setToolTip(
            'σ treats the value as one standard deviation of a Gaussian; '
            'range samples uniformly between two bounds and may be asymmetric.'
        )
        layout.addWidget(self._kind)

        self._pct_a = self._percent_spin(5.0)
        self._pct_b = self._percent_spin(5.0)
        layout.addWidget(self._pct_a)
        layout.addWidget(self._pct_b)

        self._abs_a = self._abs_widget()
        self._abs_b = self._abs_widget()
        for w in (self._abs_a, self._abs_b):
            if w is not None:
                layout.addWidget(w)

        self._kind.currentIndexChanged.connect(self._sync_visibility)
        self._sync_visibility()

    @staticmethod
    def _percent_spin(value: float) -> NoScrollDoubleSpinBox:
        spin = NoScrollDoubleSpinBox()
        spin.setRange(-100.0, 1000.0)
        spin.setDecimals(1)
        spin.setSingleStep(1.0)
        spin.setSuffix(' %')
        spin.setValue(value)
        return spin

    def _abs_widget(self):
        if self._field is None:
            return None
        widget = _UnitWidget(self._field)
        widget.setValue(self._field.default)
        return widget

    def _sync_visibility(self) -> None:
        kind, relative = self._kind.currentData()
        interval = kind is SpecKind.INTERVAL
        self._pct_a.setVisible(relative)
        self._pct_b.setVisible(relative and interval)
        if self._abs_a is not None:
            self._abs_a.setVisible(not relative)
            self._abs_b.setVisible(not relative and interval)
        if relative:
            # A σ cannot be negative; a range bound can.
            self._pct_a.setRange(-100.0 if interval else 0.0, 1000.0)
            if not interval and self._pct_a.value() < 0:
                self._pct_a.setValue(0.0)
            self._pct_a.setPrefix('' if not interval else 'from ')
            self._pct_b.setPrefix('to ')

    def spec(self) -> InputSpec:
        """The :class:`InputSpec` this row describes."""
        kind, relative = self._kind.currentData()
        if relative:
            if kind is SpecKind.SIGMA:
                return InputSpec.sigma_pct(self._pct_a.value())
            return InputSpec.interval_pct(self._pct_a.value(), self._pct_b.value())
        a = float(self._abs_a.value().magnitude)
        if kind is SpecKind.SIGMA:
            return InputSpec.sigma_abs(a)
        return InputSpec.interval_abs(a, float(self._abs_b.value().magnitude))

    def set_spec(self, spec: InputSpec) -> None:
        """Restore a previously entered spec."""
        for i in range(self._kind.count()):
            if self._kind.itemData(i) == (spec.kind, spec.relative):
                self._kind.setCurrentIndex(i)
                break
        if spec.relative:
            self._pct_a.setValue(spec.sigma if spec.kind is SpecKind.SIGMA else spec.lo)
            self._pct_b.setValue(spec.hi)
        elif self._abs_a is not None:
            self._abs_a.setValue(spec.sigma if spec.kind is SpecKind.SIGMA else spec.lo)
            self._abs_b.setValue(spec.hi)
        self._sync_visibility()


class SensitivityPanel(InfoGroupBox):
    """Configuration panel for a :class:`SensitivityConfig` run.

    Signals
    -------
    run_requested()
        Emitted when the user clicks *Run* (panel idle).
    cancel_requested()
        Emitted when the user clicks the button while a run is in progress.
    """

    run_requested = pyqtSignal()
    cancel_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__('Ka Sensitivity', 'Ka Sensitivity Analysis', _SECTION_HELP_HTML, parent)
        self._assay_type: AssayType = AssayType.GDA
        self._running = False
        # input key -> its ±% spinbox; rebuilt per assay type.
        self._rows: dict[str, _InputSpecRow] = {}
        # Entries survive an assay switch so a user does not retype them.
        self._remembered: dict[str, InputSpec] = {}
        self._setup_ui()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_assay_type(self, assay_type: AssayType) -> None:
        """Rebuild the ±% rows and heatmap axis combos for ``assay_type``.

        Disables the whole panel for ``DYE_ALONE`` (no association constant to
        analyse).
        """
        self._assay_type = assay_type
        self._rebuild_inputs(assay_type)
        self.setEnabled(assay_type is not AssayType.DYE_ALONE and bool(self._rows))

    def current_config(self) -> SensitivityConfig:
        """Build a :class:`SensitivityConfig` from the current widget state."""
        mode: SensitivityMode = self._mode_combo.currentData()
        specs = {key: row.spec() for key, row in self._rows.items()}
        input_specs = {key: spec for key, spec in specs.items() if spec.varies}
        seed = int(self._seed_spin.value()) if self._seed_check.isChecked() else None
        return SensitivityConfig(
            mode=mode,
            n_samples=self._samples_combo.currentData(),
            input_specs=input_specs,
            seed=seed,
            x_key=self._x_combo.currentData(),
            y_key=self._y_combo.currentData(),
            n_steps=self._steps_spin.value(),
            replicate_mode=self._replicates_combo.currentData(),
        )

    def set_running(self, running: bool) -> None:
        """Flip the Run/Cancel button and lock the inputs while a run is live."""
        self._running = running
        self._run_btn.setText('Cancel' if running else 'Run Sensitivity Analysis')
        for w in self._input_widgets():
            w.setEnabled(not running)
        if not running:
            # Seed value follows its checkbox once inputs are re-enabled.
            self._seed_spin.setEnabled(self._seed_check.isChecked())

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)

        self._mode_combo = QComboBox()
        self._mode_combo.addItem('Sensitivity indices', SensitivityMode.SOBOL)
        self._mode_combo.addItem('Heatmap', SensitivityMode.HEATMAP)
        self._mode_combo.currentIndexChanged.connect(self._update_mode_visibility)
        form.addRow('Mode:', self._with_info(self._mode_combo, 'Mode', _MODE_HELP_HTML))

        self._samples_combo = QComboBox()
        for size in _SOBOL_SAMPLE_SIZES:
            self._samples_combo.addItem(str(size), size)
        self._samples_combo.setCurrentIndex(0)
        self._samples_combo.setToolTip('How thoroughly the input space is explored. Each step up doubles the work.')
        self._samples_row = self._with_info(
            self._samples_combo, 'Sample size', _SAMPLES_HELP_HTML, label='Sample size:'
        )
        form.addRow(self._samples_row)

        self._replicates_combo = QComboBox()
        self._replicates_combo.addItem('Follow fit setting', ReplicateMode.FOLLOW)
        self._replicates_combo.addItem('Per replica', ReplicateMode.PER_REPLICA)
        self._replicates_combo.addItem('Average replicas', ReplicateMode.AVERAGE)
        self._replicates_combo.setToolTip(
            'How each perturbed fit uses the replicates. Averaging them removes the '
            'measured signal scatter from the analysis.'
        )
        form.addRow('Replicates:', self._with_info(self._replicates_combo, 'Replicates', _REPLICATES_HELP_HTML))
        layout.addLayout(form)

        # ±% variation rows — rebuilt per assay type.
        self._delta_group = InfoGroupBox('Input variation (±%)', 'Input variation', _DELTA_HELP_HTML)
        self._delta_form = QFormLayout(self._delta_group)
        self._delta_form.setContentsMargins(8, 4, 8, 8)
        layout.addWidget(self._delta_group)

        # Heatmap axis selectors — only visible in Heatmap mode.
        self._heatmap_group = InfoGroupBox('Heatmap axes', 'Heatmap axes', _HEATMAP_HELP_HTML)
        hm_form = QFormLayout(self._heatmap_group)
        hm_form.setContentsMargins(8, 4, 8, 8)
        self._x_combo = QComboBox()
        self._y_combo = QComboBox()
        self._steps_spin = NoScrollSpinBox()
        self._steps_spin.setRange(3, 101)
        self._steps_spin.setValue(11)
        self._steps_spin.setToolTip('Grid points per axis (fits ≈ steps²).')
        hm_form.addRow('X axis:', self._x_combo)
        hm_form.addRow('Y axis:', self._y_combo)
        hm_form.addRow('Grid steps:', self._steps_spin)
        layout.addWidget(self._heatmap_group)

        # Fixed-seed row.
        self._seed_check = QCheckBox('Fixed seed')
        self._seed_check.setToolTip('Reproducible draws — the same seed gives the same result.')
        self._seed_spin = NoScrollSpinBox()
        self._seed_spin.setRange(0, 2_147_483_647)
        self._seed_spin.setValue(0)
        self._seed_spin.setEnabled(False)
        self._seed_check.toggled.connect(self._seed_spin.setEnabled)
        seed_row = QWidget()
        seed_lay = QHBoxLayout(seed_row)
        seed_lay.setContentsMargins(0, 0, 0, 0)
        seed_lay.setSpacing(8)
        seed_lay.addWidget(self._seed_check)
        self._seed_spin.setFixedWidth(140)
        seed_lay.addWidget(self._seed_spin)
        seed_lay.addWidget(InfoButton('Fixed seed', _SEED_HELP_HTML))
        seed_lay.addStretch(1)
        layout.addWidget(seed_row)

        self._run_btn = QPushButton('Run Sensitivity Analysis')
        self._run_btn.clicked.connect(self._on_run_clicked)
        layout.addWidget(self._run_btn)

        self._rebuild_inputs(self._assay_type)
        self._update_mode_visibility()

    def _rebuild_inputs(self, assay_type: AssayType) -> None:
        """Rebuild the ±% rows and heatmap axis combos for ``assay_type``."""
        self._remembered.update({key: row.spec() for key, row in self._rows.items()})
        self._rows.clear()
        while self._delta_form.rowCount():
            self._delta_form.removeRow(0)

        fields = ASSAY_CONDITIONS[assay_type][1]
        # Perturbable-input classification lives in the core layer; feed it the
        # condition Quantities so titrant/concentration/binding order is canonical.
        base = {f.key: Q_(f.default, f.unit) for f in fields if f.unit_type in ('concentration', 'binding_constant')}
        labels = {f.key: f.label for f in fields}
        labels[TITRANT] = f'{ASSAY_REGISTRY[assay_type].x_label} (titrant)'
        inputs = perturbable_inputs(assay_type, base)

        by_key = {f.key: f for f in fields}
        self._x_combo.clear()
        self._y_combo.clear()
        for key, _kind in inputs:
            row = _InputSpecRow(by_key.get(key))
            remembered = self._remembered.get(key)
            if remembered is not None:
                row.set_spec(remembered)
            lbl = QLabel(labels[key])
            lbl.setTextFormat(Qt.TextFormat.RichText)
            self._delta_form.addRow(lbl, row)
            self._rows[key] = row

            self._x_combo.addItem(_plain(labels[key]), key)
            self._y_combo.addItem(_plain(labels[key]), key)

        # Default heatmap axes: first two distinct perturbable inputs.
        if self._y_combo.count() > 1:
            self._y_combo.setCurrentIndex(1)

    # ------------------------------------------------------------------
    # Slots / helpers
    # ------------------------------------------------------------------

    def _update_mode_visibility(self) -> None:
        is_heatmap = self._mode_combo.currentData() is SensitivityMode.HEATMAP
        self._samples_row.setVisible(not is_heatmap)
        self._heatmap_group.setVisible(is_heatmap)

    def _on_run_clicked(self) -> None:
        if self._running:
            self.cancel_requested.emit()
        else:
            self.run_requested.emit()

    def _input_widgets(self) -> list[QWidget]:
        """Every control that must lock while a run is in progress."""
        return [
            self._mode_combo,
            self._samples_combo,
            self._seed_check,
            self._seed_spin,
            self._x_combo,
            self._y_combo,
            self._steps_spin,
            *self._rows.values(),
        ]

    @staticmethod
    def _with_info(widget: QWidget, title: str, html: str, *, label: str | None = None) -> QWidget:
        """Wrap ``widget`` (optionally with a leading label) plus a trailing info button."""
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        if label is not None:
            lay.addWidget(QLabel(label))
        lay.addWidget(widget)
        lay.addWidget(InfoButton(title, html))
        lay.addStretch(1)
        return row
