"""SensitivityPanel — configure a Ka input-sensitivity run.

The panel exposes the knobs of :class:`~core.pipeline.sensitivity.SensitivityConfig`
that belong to the run itself: the analysis *mode* (Sobol indices / heatmap), the
SOBOL sample size, the two heatmap axes, and an optional fixed seed. The error sources
are stated once in
Input uncertainty (:class:`~gui.uncertainty.UncertaintyForm`), which also feeds
the interval of every fit; the owning session passes that
:class:`~core.pipeline.inputs.ErrorModel` to :meth:`SensitivityPanel.run_problems` and
:meth:`SensitivityPanel.current_config`.

It emits :attr:`run_requested` / :attr:`cancel_requested`; the owning session runs the
worker and calls :meth:`set_running` to flip the button. An assay whose signal the
analysis cannot refit (:func:`core.pipeline.varpro.projectable`) has no association
constant to report, so the whole panel is disabled with a sentence saying why.
"""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
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
from core.pipeline.inputs import ErrorModel, InputSpec, SpecKind, axis_reaches_zero
from core.pipeline.sensitivity import (
    _SOBOL_BLOCKS,
    _SOBOL_SAMPLE_SIZES,
    MAX_SEED,
    SensitivityConfig,
    SensitivityMode,
)
from core.pipeline.varpro import projectable
from core.units import Quantity
from gui.plotting.colors import INK_2
from gui.widgets.info_button import InfoButton, InfoGroupBox
from gui.widgets.numeric_inputs import NoScrollSpinBox

_SECTION_HELP_HTML = """
<h3>K<sub>a</sub> Sensitivity Analysis</h3>
<p>A fitted association constant is only as good as the <i>inputs</i> you feed
the model — the titrant concentrations and the fixed conditions
(<i>[Host]<sub>0</sub></i>, <i>[Dye]<sub>0</sub></i>, <i>K<sub>a,dye</sub></i>, …).
Each carries pipetting / calibration error, and the fit silently absorbs it by
shifting the reported K<sub>a</sub>.</p>
<p>This tool re-runs the fit many times with those inputs drawn from the
uncertainty you set under <i>Input uncertainty</i>, and shows the resulting spread
of K<sub>a</sub> and which error source it comes from. Set at least one input there to
something other than <i>fixed</i>.</p>
<p>It is a propagation of the uncertainties you stated (GUM Supplement 1): every
draw counts the same, however well or badly the fit at it follows your data. The
interval on the Fit Curve tab uses the same uncertainties but also weighs what the
data say about the inputs, so the two can differ — the spread here is the wider
where your titration itself pins an input down.</p>
<p>Every sample is one complete, deterministic fit of the averaged signal of the replicates your fit
used, so the same inputs always give the same K<sub>a</sub> and the spread you see
comes from the inputs alone. The sample at no offset at all is the fit at the inputs
you entered.</p>
<p>Where the data do not limit a K<sub>a</sub> — its fit at the entered inputs rests
on a bound, or its interval is open — or where its re-fits do not follow the inputs
smoothly, the tab gives the reason for that K<sub>a</sub> instead of its shares,
spread and elasticities.</p>
"""

_MODE_HELP_HTML = """
<h3>Mode</h3>
<ul>
  <li><b>Sensitivity indices</b> — vary every error source together and
      measure how much of the spread in K<sub>a</sub> each one is responsible
      for. You get a K<sub>a</sub> distribution plus two Sobol indices per
      source: S<sub>1</sub> (first order), its effect on its own, and
      S<sub>T</sub> (total), which also counts that source acting in
      combination with the others.</li>
  <li><b>Heatmap</b> — sweep two chosen inputs on a regular grid and fit at
      every cell, giving a 2-D K<sub>a</sub> surface.</li>
</ul>
<p>The shares are shares of the error sources you stated under <i>Input uncertainty</i>.
An error several inputs share is one source of its own, reported as one item: its share
is what re-making that one stock, or recalibrating that one pipette, would take
away.</p>
<p>S<sub>T</sub> covers S<sub>1</sub>, so it cannot really be smaller. Drawn below
S<sub>1</sub>, the source acts almost entirely on its own: the two are equal to within
sampling noise, and either can come out on top in any run, at any sample size. Where
the gap is wider than the whiskers span, take that source's two indices as unreliable.</p>
"""

_SAMPLES_HELP_HTML = f"""
<h3>Sample size</h3>
<p>How thoroughly the input space is explored. A run fits
<i>sample size × (k + 2)</i> samples for <i>k</i> error sources that vary, plus two
refits per input for the elasticities, so every step up doubles the work.</p>
<p>The whisker on each index is its 95% confidence interval. It is built so that
in about 95 of every 100 analyses it contains the index you would get with
unlimited samples for the uncertainties you set. A repeat run with fresh samples
usually lands inside it, but not always.
It is worked out from {_SOBOL_BLOCKS} independent sample sets, which costs accuracy:
index by index, an index at {_SOBOL_SAMPLE_SIZES[0]} carries up to about five times the error
of one undivided set of the same size. {_SOBOL_SAMPLE_SIZES[1]} and {_SOBOL_SAMPLE_SIZES[2]}
narrow them.
It does not account for errors in the input settings or in the model.</p>
<p>Whiskers that clearly stand apart settle which of two inputs matters more.
Overlapping whiskers are a conservative sign: two 95% intervals can overlap while the
difference between the indices is still significant, so their order may hold —
a larger sample size decides it.</p>
"""

_HEATMAP_HELP_HTML = """
<h3>Heatmap axes</h3>
<p>Choose two different inputs to sweep; every other input keeps its set value. An axis
set as a range runs from its <i>from</i> to its <i>to</i>. An axis set as a σ runs
from −2σ to +2σ, so its σ must stay below half the set value (50 %) for the axis to
stay above zero. A heatmap axis cannot be <i>fixed</i> under <i>Input uncertainty</i>.</p>
<p>Each axis is split into <i>Grid steps</i> points and the fit runs once per cell —
cost grows as <i>steps²</i>, so 11×11 = 121 fits is a good starting resolution.</p>
"""

_SEED_HELP_HTML = """
<h3>Fixed seed</h3>
<p>Tick to make the random draws reproducible: the same seed always produces the
same histogram. Leave unticked for a fresh random sample each run.</p>
"""


def _unavailable_reason(assay_type: AssayType) -> str:
    """Why the analysis cannot be run for *assay_type*, in one plain sentence."""
    return (
        f'{ASSAY_REGISTRY[assay_type].subtype_label} has no association constant, so there is nothing to analyse here.'
    )


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
        # input key -> the plain display name a message calls it by, as Input uncertainty names it
        # (UncertaintyForm.input_labels).
        self._labels: dict[str, str] = {}
        # Condition key -> its set value in the base unit; an axis stated in the input's
        # own unit is read against it.
        self._nominals: dict[str, float] = {}
        self._setup_ui()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_assay_type(self, assay_type: AssayType) -> None:
        """Open or close the panel for ``assay_type``.

        An assay the analysis cannot refit — one whose signal the engine cannot
        project onto binding constants, such as Dye Alone — disables the whole
        panel and shows a sentence saying why.
        """
        self._assay_type = assay_type
        available = projectable(assay_type)
        self.setEnabled(available)
        self._unavailable.setVisible(not available)
        if not available:
            self._unavailable.setText(_unavailable_reason(assay_type))

    def set_inputs(self, labels: dict[str, str]) -> None:
        """Offer these inputs as heatmap axes, named as Input uncertainty names them.

        *labels* maps each input key to its plain display name, the titrant included
        (:meth:`~gui.uncertainty.UncertaintyForm.input_labels`).
        The axes default to the first two inputs.
        """
        self._labels = dict(labels)
        self._x_combo.clear()
        self._y_combo.clear()
        for key, name in self._labels.items():
            self._x_combo.addItem(name, key)
            self._y_combo.addItem(name, key)
        if self._y_combo.count() > 1:
            self._y_combo.setCurrentIndex(1)

    def set_nominal_values(self, conditions: dict[str, Quantity]) -> None:
        """Take the conditions' set values, which an axis stated in the input's own unit is read against."""
        self._nominals = {
            key: float(value.magnitude) for key, value in conditions.items() if isinstance(value, Quantity)
        }

    def run_problems(self, errors: ErrorModel) -> list[str]:
        """Why the analysis cannot run on *errors* as stated, one sentence per problem; empty when it can.

        *errors* is the stated error model
        (:meth:`~gui.uncertainty.UncertaintyForm.errors`);
        whether each source can be read at all is that form's own check. Sensitivity
        indices split the spread of Ka between the sources, so at least one must vary. A
        heatmap sweeps two inputs on a grid and holds everything else at its set value,
        so only the two axes are checked here.
        """
        if not self._labels:
            raise RuntimeError('set_inputs() must name the assay’s inputs before the analysis is configured.')
        if self._mode_combo.currentData() is not SensitivityMode.HEATMAP:
            if errors.varies:
                return []
            return [
                'No input varies, so there is no spread to split. Set an uncertainty for at least one input '
                'under Input uncertainty.'
            ]
        x_key, y_key = self._x_combo.currentData(), self._y_combo.currentData()
        if x_key == y_key:
            return [f'{self._labels[x_key]} is both heatmap axes: choose another input for one of them.']
        return [problem for key in (x_key, y_key) if (problem := self._axis_problem(key, errors.specs.get(key)))]

    def current_config(self, errors: ErrorModel) -> SensitivityConfig:
        """Build a :class:`SensitivityConfig` for *errors* from the current widget state.

        Sensitivity indices take the whole model. A heatmap is a grid over two inputs,
        so it takes those two inputs' own uncertainties and nothing else: a source
        several inputs share moves them together and is no axis of a grid.

        Raises
        ------
        ValueError
            When :meth:`run_problems` finds a reason the analysis cannot run.
        """
        problems = self.run_problems(errors)
        if problems:
            raise ValueError(' '.join(problems))
        mode: SensitivityMode = self._mode_combo.currentData()
        x_key, y_key = self._x_combo.currentData(), self._y_combo.currentData()
        used = (
            ErrorModel(specs={key: errors.specs[key] for key in (x_key, y_key)})
            if mode is SensitivityMode.HEATMAP
            else errors
        )
        seed = int(self._seed_spin.value()) if self._seed_check.isChecked() else None
        return SensitivityConfig(
            mode=mode,
            n_samples=self._samples_combo.currentData(),
            errors=used,
            seed=seed,
            x_key=x_key,
            y_key=y_key,
            n_steps=self._steps_spin.value(),
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

        # Shown in place of a usable panel for an assay the analysis cannot refit.
        self._unavailable = QLabel()
        self._unavailable.setWordWrap(True)
        self._unavailable.setStyleSheet(f'color: {INK_2};')
        self._unavailable.hide()
        layout.addWidget(self._unavailable)

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
        layout.addLayout(form)

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
        self._seed_spin.setRange(0, MAX_SEED)
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

        self._update_mode_visibility()

    # ------------------------------------------------------------------
    # Slots / helpers
    # ------------------------------------------------------------------

    def _axis_problem(self, key: str, spec: InputSpec | None) -> str | None:
        """Why the input *key* cannot be a heatmap axis with *spec*; ``None`` when it can.

        An axis runs over the whole range, or from −2σ to +2σ, both ends included, so
        an end at −100 % would fit the model with the input at zero.
        """
        name = self._labels[key]
        if spec is None:
            return (
                f'{name} is a heatmap axis, so it cannot be fixed: set a σ or a range for it under Input uncertainty.'
            )
        if not axis_reaches_zero(spec, self._nominals.get(key), name):
            return None
        if spec.kind is SpecKind.SIGMA:
            limit = '50 %' if spec.relative else 'half its set value'
            return (
                f'{name} as a heatmap axis would reach zero or below, since the axis runs from −2σ to +2σ: '
                f'set σ below {limit}, or use a range.'
            )
        return f'{name} as a heatmap axis would reach zero: set “from” above {"−100 %" if spec.relative else "0"}.'

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
