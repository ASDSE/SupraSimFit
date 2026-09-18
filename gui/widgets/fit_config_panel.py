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
K<sub>a</sub> and R<sup>2</sup>, and the summary adds a median and a
min&ndash;max column across them. That is real replicate-to-replicate spread,
measured on your experiment.</p>

<p>Their own fits are also used to test the one assumption the average rests
on: that every replicate is describing the same binding constant. A replicate
whose own curve needs a different K<sub>a</sub> than the others agree on is
left out of the average and named, with its p-value, in the Replicates table
and in the report.</p>

<p><b>The test</b></p>
<p>Replicates are removed one at a time, worst first, and only while a
replicate is below a 1&thinsp;% level (the outlier level of ISO&nbsp;5725-2)
shared out over the replicates you gave. The test never removes half or more of
them &mdash; a majority is what defines the consensus &mdash; and it needs at
least <b>three</b> replicates to run at all: with two, nothing says which of the
two is the odd one.</p>
"""


_SECTION_HELP_HTML = """
<h3>Fit Configuration</h3>
<p>How the replicates of the loaded dataset enter the fit. The fit itself needs
no settings: the signal parameters are solved exactly inside their bounds at
every binding constant, and the binding constants are searched over the whole
range set under Parameter Bounds, so the same data and settings always give the
same answer.</p>
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
            'fit needs a different Ka than the others share (needs at least three replicates).'
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
