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
from gui.widgets.info_button import InfoButton, InfoGroupBox
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

_PER_REPLICATE_HELP_HTML = """
<h3>Fit per replicate &mdash; pooled passing trials</h3>

<p><b>Average mode (default, off)</b></p>
<p>All active replicates are averaged into a single curve, then the
fitter runs one multi-start optimisation on that average. Every
starting point that produces an acceptable fit (low RMSE, high
R<sup>2</sup>) is kept. The reported parameter is the <i>median</i> of
those acceptable fits and the &plusmn; value is their spread (MAD).
This tells you how tight the optimiser landscape is &mdash; <b>not</b>
how reproducible your experiment is.</p>

<p><b>Per-replicate mode (on)</b></p>
<p>Every active replicate is fit on its own with a full multi-start
run. From each replicate, every trial that passes the acceptance
filter (R<sup>2</sup>, RMSE) is retained. All those passing trials from
all replicates are then <b>pooled into one flat collection</b>. The
reported parameter is the median of that pool and the &plusmn; value
is the MAD of the same pool. This captures both the optimiser spread
<i>and</i> the experimental spread across replicates in one honest
distribution &mdash; the kind you can quote in a paper or draw
box-and-whisker plots from.</p>

<p><b>What this means in practice</b></p>
<ul>
  <li>A replicate with many acceptable fits contributes proportionally
      more samples to the pool. This is the intended behaviour: a
      well-converging replicate carries more information than a barely
      converging one.</li>
  <li>The pool contains every passing trial, not per-replicate
      summaries &mdash; so box-whiskers, histograms, and confidence
      intervals drawn from it are statistically meaningful rather than
      based on just N&nbsp;= (number of replicates) points.</li>
  <li>The plot curve labelled <i>Median Fit</i> is the forward model
      evaluated at the pooled median parameters.</li>
</ul>

<p><b>When to use per-replicate mode</b></p>
<ul>
  <li>You want a defensible uncertainty estimate on K<sub>a</sub> and
      the signal coefficients.</li>
  <li>You suspect one replicate may disagree with the rest &mdash;
      per-replicate fitting exposes this (the disagreeing replicate
      shows up as a cluster in the pool), while averaging hides it.</li>
  <li>You will produce per-parameter distribution plots downstream.</li>
</ul>

<p><b>What to watch out for</b></p>
<ul>
  <li><b>Few replicates</b>: the pool is built from N replicates. With
      only one or two, the pool reflects mostly optimiser spread on
      each individual trace. Three replicates is a good minimum; four
      or more is better.</li>
  <li><b>Noisy individual traces</b>: a very noisy single replicate may
      fail to converge. Those replicates are skipped and listed in a
      warning so you know exactly which ones dropped out.</li>
  <li><b>Slower</b>: each replicate runs its own multi-start, so the
      fit takes roughly <i>N</i> times longer. Usually still seconds.</li>
  <li><b>Fit curve looks the same</b>: when your replicates agree well,
      the median parameter values in per-replicate mode are very close
      to the average-mode values, so the plotted curve may look
      unchanged. The real difference shows up in the reported
      &plusmn;&nbsp;uncertainty, not in the curve shape.</li>
</ul>
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


_SECTION_HELP_HTML = """
<h3>Fit Configuration</h3>
<p>Controls for the multi-start optimiser: how many trials to run, how
strictly to filter them, and whether to fit each replicate
independently. See the <i>i</i> next to each setting for details.</p>
"""


class FitConfigPanel(InfoGroupBox):
    """Editor for :class:`~core.pipeline.fit_pipeline.FitConfig` parameters.

    Signals
    -------
    config_changed()
        Emitted whenever any field value changes.
    """

    config_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__("Fit Configuration", "Fit Configuration", _SECTION_HELP_HTML, parent)
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
            per_replicate=self._per_replicate_check.isChecked(),
        )

    def set_config(self, config: FitConfig) -> None:
        self._trials_spin.setValue(config.n_trials)
        self._rmse_spin.setValue(config.rmse_threshold_factor)
        self._r2_spin.setValue(config.min_r_squared)
        self._rescale_check.setChecked(config.rescale_parameters)
        self._per_replicate_check.setChecked(config.per_replicate)

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

        self._per_replicate_check = QCheckBox()
        self._per_replicate_check.setChecked(FitConfig().per_replicate)
        self._per_replicate_check.setToolTip(
            "Fit each replicate independently; uncertainties reflect replicate-to-replicate spread."
        )
        self._per_replicate_check.toggled.connect(self.config_changed)
        form.addRow(
            "Fit per replicate:",
            self._with_info(self._per_replicate_check, "Fit per replicate", _PER_REPLICATE_HELP_HTML),
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
        lay.setSpacing(15)
        if not isinstance(widget, QCheckBox):
            widget.setFixedWidth(120)
        lay.addWidget(widget)
        lay.addWidget(InfoButton(title, html))
        lay.addStretch(1)
        return row
