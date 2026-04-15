"""FitConfigPanel — optimizer configuration (n_trials, RMSE factor, min R²)."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QWidget,
)

from core.pipeline.fit_pipeline import FitConfig
from gui.widgets.info_button import InfoButton
from gui.widgets.numeric_inputs import NoScrollDoubleSpinBox, NoScrollSpinBox

_TRIALS_HELP_HTML = """
<h3>Trials &mdash; Multi-Start Optimization Budget</h3>

<p><b>What It Does</b></p>
<p>The fitter is a multi-start L-BFGS-B optimiser: it samples many random
starting points in the parameter space, runs a local optimisation from
each one, and then aggregates the best results. <b>Trials</b> sets how
many of those starting points are tried.</p>

<p><b>Why It Matters</b></p>
<p>A single L-BFGS-B run only finds the <i>local</i> minimum nearest the
starting point. For non-convex problems (most binding models) the
global minimum can hide behind a wall, and one run easily gets stuck.
Sampling many starts makes it very likely that at least one of them
lands in the basin of the true minimum.</p>

<p><b>Practical Values</b></p>
<ul>
  <li><b>50</b> &mdash; fast, usually fine for clean data with a single
      fitted K<sub>a</sub>.</li>
  <li><b>100</b> (default) &mdash; robust for most IDA/DBA/GDA fits.</li>
  <li><b>500&ndash;1000</b> &mdash; noisy data, degenerate parameters,
      or an unreliable landscape.</li>
  <li><b>&gt; 1000</b> &mdash; diminishing returns; prefer tightening
      bounds or supplying dye-alone priors instead.</li>
</ul>

<p><b>When to Increase</b></p>
<p>If repeated runs give noticeably different K<sub>a</sub> values, or
if the aggregate report shows very few surviving trials, raise this
value before doing anything else. If it's already high and the fit
still looks bad, the issue is the bounds or the data &mdash; not the
budget.</p>
"""

_RMSE_HELP_HTML = """
<h3>RMSE Factor &mdash; Trial Acceptance Filter</h3>

<p><b>What It Does</b></p>
<p>After all multi-start trials finish, each one is ranked by its
root-mean-squared error to the data. Trials whose RMSE is worse than
<i>best_RMSE &times; factor</i> are discarded before the median/MAD
aggregation step. This removes local-minimum trials that clearly
didn&rsquo;t find a reasonable solution.</p>

<p><b>The Rule</b></p>
<p align="center"><i>keep trial if RMSE<sub>i</sub> &le; factor &middot; best_RMSE</i></p>

<p><b>Practical Values</b></p>
<ul>
  <li><b>1.0</b> &mdash; extremely strict, keeps only trials tied with
      the best. Almost always too tight; the aggregate uncertainty
      collapses.</li>
  <li><b>1.5</b> (default) &mdash; keeps trials within 50&nbsp;% of the
      best RMSE. A good balance.</li>
  <li><b>3.0&ndash;5.0</b> &mdash; permissive; useful when the landscape
      is very flat and many trials are reasonable.</li>
</ul>

<p><b>When to Change It</b></p>
<p>If the reported K<sub>a</sub> uncertainty looks implausibly small,
loosen the factor &mdash; the trial population was too small to estimate
it. If the aggregate parameter is clearly wrong but the plot looks okay,
tighten the factor to weed out partial-convergence runs.</p>
"""

_RESCALE_HELP_HTML = """
<h3>Rescale &mdash; Parameter Conditioning for the Optimiser</h3>

<p><b>What It Does</b></p>
<p>Before each fit, every parameter is multiplied by a data-derived
factor so all of them are on the same numerical scale (roughly
order&nbsp;1). After the optimiser has converged, the parameters are
transformed back to physical units for display. You always see
results in M<sup>&minus;1</sup>, a.u., etc.</p>

<p><b>Why It Matters</b></p>
<p>L-BFGS-B converges faster and more reliably when all parameters
live on a similar scale. In raw units K<sub>a</sub> (~10<sup>7</sup>
M<sup>&minus;1</sup>) and I<sub>0</sub> (~10<sup>3</sup> a.u.) differ
by many orders of magnitude &mdash; a badly conditioned problem where
one gradient direction dominates and the optimiser wastes steps. After
rescaling, more multi-start trials succeed and the robust median
estimate is tighter.</p>

<p><b>Why It&rsquo;s Safe</b></p>
<p>The rescaling is an exact, invertible affine transform. It doesn&rsquo;t
change what is being fit &mdash; only the numerical coordinates the
optimiser sees. Your bounds, parameter values, and uncertainties are
identical in meaning to an unrescaled fit; they are simply reported in
the same physical units you entered them in.</p>

<p><b>When to Turn It Off</b></p>
<p>Leave it on by default. Disable only for a direct comparison with a
raw-space fit.</p>
"""


_R2_HELP_HTML = """
<h3>Min R<sup>2</sup> &mdash; Minimum Coefficient of Determination</h3>

<p><b>What It Does</b></p>
<p>A hard acceptance floor on how well a trial must explain the data.
Any trial with <i>R<sup>2</sup> &lt; min&nbsp;R<sup>2</sup></i> is thrown
away regardless of how it compares to the other trials.</p>

<p><b>The Math</b></p>
<p align="center">
  <i>R<sup>2</sup> = 1 &minus; SS<sub>res</sub> / SS<sub>tot</sub></i>
</p>
<p>where <i>SS<sub>res</sub></i> is the sum of squared residuals and
<i>SS<sub>tot</sub></i> is the total variance of the data. Values near
1 mean the fit tracks the data; values near 0 or negative mean the fit
is no better than a flat line through the mean.</p>

<p><b>Practical Values</b></p>
<ul>
  <li><b>0.90</b> (default) &mdash; sensible baseline for clean
      fluorescence titrations.</li>
  <li><b>0.95+</b> &mdash; high-quality data; rejects anything that
      visibly misses points.</li>
  <li><b>0.70&ndash;0.85</b> &mdash; noisy data or small dynamic range.
      Loosen if the fitter reports &ldquo;no trials accepted&rdquo;.</li>
</ul>

<p><b>When to Change It</b></p>
<p>If the aggregator keeps rejecting every trial, lower this threshold
first &mdash; it&rsquo;s the most common cause of that failure. If you
lower it and the fit plot still doesn&rsquo;t match the data, the
problem is elsewhere (wrong model, wrong bounds, or a systematic error
in the measurement).</p>
"""


class FitConfigPanel(QGroupBox):
    """Editor for :class:`~core.pipeline.fit_pipeline.FitConfig` parameters.

    Signals
    -------
    config_changed()
        Emitted whenever any field value changes.
    """

    config_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__("Fit Configuration", parent)
        self._setup_ui()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def current_config(self) -> FitConfig:
        return FitConfig(
            n_trials=self._trials_spin.value(),
            rmse_threshold_factor=self._rmse_spin.value(),
            min_r_squared=self._r2_spin.value(),
            rescale_parameters=self._rescale_check.isChecked(),
        )

    def set_config(self, config: FitConfig) -> None:
        self._trials_spin.setValue(config.n_trials)
        self._rmse_spin.setValue(config.rmse_threshold_factor)
        self._r2_spin.setValue(config.min_r_squared)
        self._rescale_check.setChecked(config.rescale_parameters)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        form = QFormLayout(self)

        self._trials_spin = NoScrollSpinBox()
        self._trials_spin.setRange(10, 10_000)
        self._trials_spin.setSingleStep(10)
        self._trials_spin.setValue(100)
        self._trials_spin.setToolTip("Number of multi-start L-BFGS-B optimization trials.")
        self._trials_spin.valueChanged.connect(self.config_changed)
        form.addRow("Trials:", self._with_info(self._trials_spin, "Trials", _TRIALS_HELP_HTML))

        self._rmse_spin = NoScrollDoubleSpinBox()
        self._rmse_spin.setRange(1.0, 10.0)
        self._rmse_spin.setSingleStep(0.1)
        self._rmse_spin.setDecimals(2)
        self._rmse_spin.setValue(1.5)
        self._rmse_spin.setToolTip(
            "Trials with RMSE > (best_RMSE × factor) are discarded before aggregation."
        )
        self._rmse_spin.valueChanged.connect(self.config_changed)
        form.addRow("RMSE factor:", self._with_info(self._rmse_spin, "RMSE factor", _RMSE_HELP_HTML))

        self._r2_spin = NoScrollDoubleSpinBox()
        self._r2_spin.setRange(0.0, 1.0)
        self._r2_spin.setSingleStep(0.01)
        self._r2_spin.setDecimals(2)
        self._r2_spin.setValue(0.90)
        self._r2_spin.setToolTip("Minimum R² for a trial to pass the acceptance filter.")
        self._r2_spin.valueChanged.connect(self.config_changed)
        form.addRow("Min R²:", self._with_info(self._r2_spin, "Min R²", _R2_HELP_HTML))

        self._rescale_check = QCheckBox()
        self._rescale_check.setChecked(FitConfig().rescale_parameters)
        self._rescale_check.setToolTip(
            "Rescale parameters to O(1) for the optimiser; results are shown in physical units."
        )
        self._rescale_check.toggled.connect(self.config_changed)
        form.addRow(
            "Rescale parameters:",
            self._with_info(self._rescale_check, "Rescale parameters for fitting", _RESCALE_HELP_HTML),
        )

    @staticmethod
    def _with_info(widget: QWidget, title: str, html: str) -> QWidget:
        """Wrap ``widget`` in an HBox together with a trailing info button.

        The spinbox gets a uniform fixed width so the three Fit Config
        rows line up vertically regardless of the label column width,
        and the trailing stretch keeps the (spinbox, info-button) pair
        pinned to the left of the field column.
        """
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        widget.setFixedWidth(120)
        lay.addWidget(widget)
        lay.addWidget(InfoButton(title, html))
        lay.addStretch(1)
        return row
