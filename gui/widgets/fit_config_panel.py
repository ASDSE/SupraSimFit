"""FitConfigPanel — optimizer configuration (trials, RMSE factor, min R², per-replicate fitting, seed)."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QHBoxLayout,
    QWidget,
)

from core.pipeline.fit_pipeline import MAX_SEED, FitConfig
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
<p>The reported <i>(min, max)</i> range spans the trials that pass the acceptance
filter, so with very few trials it says little: a handful of starting points can all
land in the same spot and show a range far narrower than the data support.</p>

<p><b>When to Increase</b></p>
<p>If repeated runs give noticeably different K<sub>a</sub> values, or
if the aggregate report shows very few surviving trials, raise this
value before doing anything else. If it's already high and the fit
still looks bad, the issue is the bounds or the data &mdash; not the
budget.</p>
"""

_RMSE_HELP_HTML = """
<h3>Trim by RMSE factor &mdash; optional pool tightening</h3>

<p><b>What it does</b></p>
<p>Off by default. The Min&nbsp;R<sup>2</sup> floor is the primary quality
gate and already keeps only good fits. Tick this to <i>additionally</i>
drop valid fits whose RMSE exceeds <i>best&nbsp;RMSE &times; factor</i> —
useful only to tighten an unusually scattered pool.</p>

<p align="center"><i>keep fit if RMSE<sub>i</sub> &le; factor &middot; best_RMSE</i></p>

<p><b>Note</b></p>
<p>This only narrows the spread reported for the ensemble; it never changes
the reported best-fit value or the plotted curve. Leave it off unless you
have a specific reason to prune.</p>
"""

_PER_REPLICA_HELP_HTML = """
<h3>Fit per replicate &mdash; pooled passing trials</h3>

<p><b>Average mode (off)</b></p>
<p>All active replicates are averaged into a single curve, then the
fitter runs one multi-start optimisation on that average. Every
starting point that produces an acceptable fit (low RMSE, high
R<sup>2</sup>) is kept. The reported value is the <i>best</i> of those
acceptable fits and the &plusmn; value is the spread of the pool (MAD by
default). This tells you how tight the optimiser landscape is &mdash;
<b>not</b> how reproducible your experiment is.</p>

<p><b>Per-replicate mode (default, on)</b></p>
<p>Every active replicate is fit on its own with a full multi-start
run. From each replicate, every trial that passes the acceptance
filter (R<sup>2</sup>, RMSE) is retained. All those passing trials from
all replicates are then <b>pooled into one flat collection</b>. The
reported value is one replicate's best fit &mdash; of each replicate's best
fit, the one with the highest R&sup2; against the average of the replicates it
used &mdash; and the &plusmn; value is the pool's spread (MAD by default). A
replicate with no acceptable fit is left out, and its signal plays no part in
the reported R&sup2; or RMSE. This captures both the optimiser spread
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
  <li>The plot curve labelled <i>Fit</i> is the forward model evaluated
      at the representative fit shown in the Representative selector.</li>
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
      fail to converge or miss the Min R&sup2; floor. Those replicates are left
      out of the fit and of its R&sup2; and RMSE, and listed in a warning so
      you know exactly which ones dropped out.</li>
  <li><b>Slower</b>: each replicate runs its own multi-start, so the
      fit takes roughly <i>N</i> times longer. Usually still seconds.</li>
  <li><b>Fit curve looks the same</b>: when your replicates agree well,
      the representative fit in per-replicate mode is very close to the
      average-mode one, so the plotted curve may look unchanged. The real
      difference shows up in the reported range and spread, not in the
      curve shape.</li>
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
  <li><b>0.99</b> (default) &mdash; clean fluorescence titrations, where a
      trial that misses a point visibly falls below it.</li>
  <li><b>0.999+</b> &mdash; very clean data with a large dynamic range;
      keeps only the trials that track every point.</li>
  <li><b>0.90&ndash;0.95</b> &mdash; noisy data or a small dynamic range.
      Loosen to here if the fitter reports &ldquo;no trials accepted&rdquo;.</li>
</ul>

<p><b>Per-replicate fits</b></p>
<p>With <i>Fit per replicate</i> on, each trial is judged on the signal of the
replicate it was fitted to, so this floor applies replicate by replicate. The
R<sup>2</sup> reported afterwards is measured on the average of the replicates the
fit used, and can differ from any single replicate&rsquo;s.</p>

<p><b>When to Change It</b></p>
<p>If the aggregator keeps rejecting every trial, lower this threshold
first &mdash; it&rsquo;s the most common cause of that failure. If you
lower it and the fit plot still doesn&rsquo;t match the data, the
problem is elsewhere (wrong model, wrong bounds, or a systematic error
in the measurement).</p>
"""


_SEED_HELP_HTML = """
<h3>Fixed seed</h3>

<p>Every fit records the seed of the random starting points it used, and an
exported result carries it, so the fit can be repeated exactly.</p>

<p>Leave the box unticked to draw a fresh seed for each fit: repeating one then
shows how much the starting points move the result. Tick it and enter a seed to
repeat the same fit &mdash; the same data and settings with that seed give the
same accepted trials and the same reported range.</p>
"""


_SECTION_HELP_HTML = """
<h3>Fit Configuration</h3>
<p>Controls for the multi-start optimiser: how many trials to run, how
strictly to filter them, whether to fit each replicate independently, and
which random starting points it uses. See the <i>i</i> next to each setting
for details.</p>
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
        super().__init__('Fit Configuration', 'Fit Configuration', _SECTION_HELP_HTML, parent)
        self._setup_ui()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def current_config(self) -> FitConfig:
        """The configuration the panel describes.

        ``seed`` is the fixed seed when the box is ticked, and ``None`` otherwise,
        which leaves the session to draw one and record it with the fit.
        """
        return FitConfig(
            n_trials=self._trials_spin.value(),
            rmse_threshold_factor=(self._rmse_spin.value() if self._rmse_check.isChecked() else None),
            min_r_squared=self._r2_spin.value(),
            rescale_parameters=self._rescale_check.isChecked(),
            per_replica=self._per_replica_check.isChecked(),
            seed=int(self._seed_spin.value()) if self._seed_check.isChecked() else None,
        )

    def set_config(self, config: FitConfig) -> None:
        self._trials_spin.setValue(config.n_trials)
        factor = config.rmse_threshold_factor
        self._rmse_check.setChecked(factor is not None)
        self._rmse_spin.setEnabled(factor is not None)
        if factor is not None:
            self._rmse_spin.setValue(factor)
        self._r2_spin.setValue(config.min_r_squared)
        self._rescale_check.setChecked(config.rescale_parameters)
        self._per_replica_check.setChecked(config.per_replica)
        self._seed_check.setChecked(config.seed is not None)
        self._seed_spin.setEnabled(config.seed is not None)
        if config.seed is not None:
            self._seed_spin.setValue(int(config.seed))

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        form = QFormLayout(self)

        self._trials_spin = NoScrollSpinBox()
        self._trials_spin.setRange(1, 10_000)
        self._trials_spin.setSingleStep(10)
        self._trials_spin.setValue(100)
        self._trials_spin.setToolTip('Number of multi-start L-BFGS-B optimization trials.')
        self._trials_spin.valueChanged.connect(self.config_changed)
        form.addRow('Trials:', self._with_info(self._trials_spin, 'Trials', _TRIALS_HELP_HTML))

        # Optional RMSE trim — off by default; the R² floor is the primary gate.
        self._rmse_check = QCheckBox()
        self._rmse_check.setChecked(FitConfig().rmse_threshold_factor is not None)  # default: off
        self._rmse_check.setToolTip('Optionally trim the valid pool by RMSE relative to the best fit (off by default).')
        self._rmse_spin = NoScrollDoubleSpinBox()
        self._rmse_spin.setRange(1.0, 10.0)
        self._rmse_spin.setSingleStep(0.1)
        self._rmse_spin.setDecimals(2)
        self._rmse_spin.setValue(1.5)
        self._rmse_spin.setEnabled(self._rmse_check.isChecked())
        self._rmse_spin.setToolTip('Drop valid fits with RMSE > (best_RMSE × factor). Only applied when enabled.')
        self._rmse_check.toggled.connect(self._rmse_spin.setEnabled)
        self._rmse_check.toggled.connect(self.config_changed)
        self._rmse_spin.valueChanged.connect(self.config_changed)
        form.addRow('Trim by RMSE factor:', self._rmse_trim_row())

        self._r2_spin = NoScrollDoubleSpinBox()
        self._r2_spin.setRange(0.0, 1.0)
        self._r2_spin.setSingleStep(0.01)
        self._r2_spin.setDecimals(2)
        self._r2_spin.setValue(0.99)
        self._r2_spin.setToolTip('Minimum R² for a trial to pass the acceptance filter.')
        self._r2_spin.valueChanged.connect(self.config_changed)
        form.addRow('Min R²:', self._with_info(self._r2_spin, 'Min R²', _R2_HELP_HTML))

        self._rescale_check = QCheckBox()
        self._rescale_check.setChecked(FitConfig().rescale_parameters)
        self._rescale_check.setToolTip(
            'Rescale parameters to O(1) for the optimiser; results are shown in physical units.'
        )
        self._rescale_check.toggled.connect(self.config_changed)
        form.addRow(
            'Rescale parameters:',
            self._with_info(self._rescale_check, 'Rescale parameters for fitting', _RESCALE_HELP_HTML),
        )

        self._per_replica_check = QCheckBox()
        self._per_replica_check.setChecked(FitConfig().per_replica)
        self._per_replica_check.setToolTip(
            'Fit each replicate independently; uncertainties reflect replicate-to-replicate spread.'
        )
        self._per_replica_check.toggled.connect(self.config_changed)
        form.addRow(
            'Fit per replicate:',
            self._with_info(self._per_replica_check, 'Fit per replicate', _PER_REPLICA_HELP_HTML),
        )

        # Fixed seed — unticked, the session draws a seed per fit and records it.
        self._seed_check = QCheckBox()
        self._seed_check.setToolTip('Repeat the same fit: the same seed gives the same starting points.')
        self._seed_spin = NoScrollSpinBox()
        self._seed_spin.setRange(0, MAX_SEED)
        self._seed_spin.setValue(0)
        self._seed_spin.setEnabled(False)
        self._seed_spin.setToolTip('The seed to repeat. Every fit records the seed it used.')
        self._seed_check.toggled.connect(self._seed_spin.setEnabled)
        self._seed_check.toggled.connect(self.config_changed)
        self._seed_spin.valueChanged.connect(self.config_changed)
        form.addRow('Fixed seed:', self._seed_row())

    def _seed_row(self) -> QWidget:
        """Row: [enable checkbox] [seed spinbox] [info] for the optional fixed seed."""
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(15)
        lay.addWidget(self._seed_check)
        self._seed_spin.setFixedWidth(120)
        lay.addWidget(self._seed_spin)
        lay.addWidget(InfoButton('Fixed seed', _SEED_HELP_HTML))
        lay.addStretch(1)
        return row

    def _rmse_trim_row(self) -> QWidget:
        """Row: [enable checkbox] [factor spinbox] [info] for the optional trim."""
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(15)
        lay.addWidget(self._rmse_check)
        self._rmse_spin.setFixedWidth(120)
        lay.addWidget(self._rmse_spin)
        lay.addWidget(InfoButton('RMSE factor', _RMSE_HELP_HTML))
        lay.addStretch(1)
        return row

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
