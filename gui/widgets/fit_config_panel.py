"""FitConfigPanel — how the replicates of a dataset enter the fit."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QHBoxLayout,
    QWidget,
)

from core.pipeline.fit_pipeline import FitConfig
from gui.widgets.info_button import InfoButton, InfoGroupBox

_PER_REPLICA_HELP_HTML = """
<h3>Fit each replicate separately</h3>

<p><b>What is fitted either way</b></p>
<p>The reported fit is always the fit of the <i>average</i> of the replicates
that are used. For replicates that scatter by the same amount, fitting them all
at once and fitting their average give the same answer, and the average of
replicates that share their binding constants is itself a model curve. The
reported R<sup>2</sup> and RMSE are measured against that average.</p>

<p><b>Off</b></p>
<p>Every replicate you have switched on goes into the average, whatever it
looks like.</p>

<p><b>On (default)</b></p>
<p>Each replicate is also fitted on its own, and those fits are reported beside
the main one: the <i>Replicates</i> table lists each replicate&rsquo;s own
K<sub>a</sub> and R<sup>2</sup>, and a line under the summary table gives the
median and range of their own K<sub>a</sub>, each fitted with the inputs as
entered. That is real replicate-to-replicate spread, measured on your
experiment.</p>

<p>Their own fits are also used to test the two assumptions the average rests
on: that every replicate is describing the same binding constant, and that
each one is about as precise as the others. A replicate whose own curve needs a
different K<sub>a</sub> than the others agree on, or whose points scatter about
its own curve far more than the others&rsquo; do, is left out of the average
and named, with the reason, in the Replicates table and in the report.</p>

<p><b>What the replicates also give the report</b></p>
<p>With two or more replicates in the fit, their scatter about their mean
measures the noise without using the model at all, and <i>Model and inputs</i>
under the summary table uses it to say whether the fitted curve misses the data
by more than that scatter allows. With a single replicate that question is
answered instead from runs of points on one side of the curve.</p>

<p><b>The test</b></p>
<p>It starts from the majority of the replicates whose own K<sub>a</sub> lie
closest to the middle of all of them, and adds back the others one at a time,
the one that agrees best with their shared fit first, until none of the rest
agrees. A replicate already in that the others then disagree with leaves again,
and the ones outside at the end are left out. Starting from that majority means that two
replicates which share a wrong K<sub>a</sub> cannot pull the shared fit their
way and push a good replicate out instead. The replicates kept are then
compared for scatter (Cochran&rsquo;s test), and one whose scatter is far larger
than the others&rsquo; is left out as well. Where you stated a random error of each
addition under <b>Input uncertainty</b> and the replicates are separate titrations,
both steps allow for each replicate&rsquo;s own additions, which move its K<sub>a</sub>
and its points apart from the others&rsquo;.</p>
<p>Both steps work at a 1&thinsp;% level (the outlier level of
ISO&nbsp;5725-2): the K<sub>a</sub> step shares it out over the replicates you
gave, Cochran&rsquo;s test over the replicates still in it. Together they never
remove half or more of them &mdash; a majority is what defines the consensus
&mdash; and the test needs at least <b>three</b> replicates to run at all: with
two, nothing says which of the two is the odd one.</p>
"""


_SECTION_HELP_HTML = """
<h3>Fit Configuration</h3>
<p>How the replicates of the loaded dataset enter the fit. The fit itself needs
no settings: the signal parameters are solved exactly inside their bounds at
every binding constant, and the binding constants are searched over the whole
range set under Parameter Bounds, so the same data and settings always give the
same answer.</p>
<p>What the reported confidence interval covers is set elsewhere, under
<b>Input uncertainty</b>: with every input fixed, as that panel starts, the
interval takes the conditions you entered as exact; state an uncertainty for one
and the fit may move it within what you stated, and the interval covers that as
well.</p>
"""


class FitConfigPanel(InfoGroupBox):
    """Editor for :class:`~core.pipeline.fit_pipeline.FitConfig`.

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
        """The configuration the panel describes."""
        return FitConfig(per_replica=self._per_replica_check.isChecked())

    def set_config(self, config: FitConfig) -> None:
        self._per_replica_check.setChecked(config.per_replica)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        form = QFormLayout(self)

        self._per_replica_check = QCheckBox()
        self._per_replica_check.setChecked(FitConfig().per_replica)
        self._per_replica_check.setToolTip(
            'Also fit every replicate on its own: report their spread, and leave out a replicate whose own '
            'fit needs a different Ka than the others share or whose scatter is far larger than theirs '
            '(needs at least three replicates).'
        )
        self._per_replica_check.toggled.connect(self.config_changed)

        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(15)
        lay.addWidget(self._per_replica_check)
        lay.addWidget(InfoButton('Fit each replicate separately', _PER_REPLICA_HELP_HTML))
        lay.addStretch(1)
        form.addRow('Fit each replicate separately:', row)
