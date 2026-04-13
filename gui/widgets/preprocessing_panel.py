"""OutlierRemovalPanel — Z-Score filter configuration and execution."""

from __future__ import annotations

from PyQt6.QtCore import QLocale, pyqtSignal
from PyQt6.QtWidgets import QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QMessageBox, QPushButton, QSizePolicy, QSpinBox, QVBoxLayout, QWidget

from core.data_processing.measurement_set import MeasurementSet
from core.data_processing.preprocessing import apply_preprocessing
from gui.widgets.info_button import InfoButton

_LOCALE_EN = QLocale(QLocale.Language.English, QLocale.Country.UnitedStates)

_ZSCORE_HELP_HTML = """
<h3>Z-Score Outlier Removal</h3>

<p><b>What It Does</b></p>
<p>At every concentration point the panel compares the replicas against each
other. A replica whose signal looks <i>unusually far</i> from its siblings at
any concentration is flagged as an outlier and removed from the fit. Dropped
replicas are not deleted &mdash; they are simply ignored while fitting. You can
restore them at any time with <b>Reset</b>.</p>

<p><b>The Math (Robust / Modified Z-Score)</b></p>
<p>For each concentration <i>j</i>, let
<i>median<sub>j</sub></i> be the median of the active replicas at that point
and <i>MAD<sub>j</sub></i> their median absolute deviation. The modified
z-score of replica <i>i</i> at point <i>j</i> is:</p>
<p align="center"><i>z<sub>ij</sub> = 0.6745 &middot; |x<sub>ij</sub> &minus; median<sub>j</sub>| / MAD<sub>j</sub></i></p>
<p>The 0.6745 factor rescales MAD so the threshold has roughly the same
meaning as a classical Gaussian &sigma;. A replica is dropped when its
<b>maximum</b> z-score across all concentrations exceeds the threshold.
Median and MAD are robust to a few bad points, so one outlier does not mask
another.</p>

<p><b>Threshold (0.5&ndash;10, Default 3.5)</b></p>
<ul>
  <li><b>Lower threshold</b> (2.0&ndash;2.5) &rarr; aggressive: flags replicas
      that are even slightly off. Use with very clean data.</li>
  <li><b>Default (3.5)</b> &rarr; conservative: only clearly inconsistent
      replicas are removed.</li>
  <li><b>Higher threshold</b> (&ge; 5) &rarr; almost nothing gets dropped.</li>
</ul>

<p><b>Min Replicas</b></p>
<p>Safety floor &mdash; if fewer active replicas remain than this number, the
filter is not applied and a warning dialog is shown. This prevents the filter
from leaving you with one or zero curves to fit.</p>

<p><b>Effect on the Fit</b></p>
<p>Outlier removal shrinks the spread around the mean at each concentration,
which improves parameter uncertainties and reduces bias from a single bad
replica. If your fit looks poor, try tightening the threshold first
(e.g. 3.5 &rarr; 2.5) and rerun &mdash; but inspect which replicas get dropped
before trusting the result.</p>
"""


class PreprocessingPanel(QGroupBox):
    """Configure and apply outlier removal to a MeasurementSet.

    Exposes the Z-Score replica filter.  If the configured minimum replica
    count cannot be met, the user is notified via a dialog — the filter is
    never silently skipped.

    Signals
    -------
    preprocessing_applied()
        Emitted after a step is applied (MeasurementSet modified in-place).
    preprocessing_reset()
        Emitted after ``ms.reset_active()`` is called.
    """

    preprocessing_applied = pyqtSignal()
    preprocessing_reset = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__('Outlier Removal', parent)
        self._ms: MeasurementSet | None = None
        self._setup_ui()
        self.setEnabled(False)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_measurement_set(self, ms: MeasurementSet) -> None:
        self._ms = ms
        self.setEnabled(True)
        self._status_label.setText('')

    def current_steps(self) -> list[dict]:
        """Return preprocessing step configuration list for :func:`apply_preprocessing`."""
        return [
            {
                'name': 'zscore_replica_filter',
                'params': {
                    'threshold': self._threshold_spin.value(),
                    'min_replicas': self._min_rep_spin.value(),
                },
            }
        ]

    def apply(self) -> bool:
        """Programmatically apply the current preprocessing steps.

        Unlike the interactive Apply button, this does not show warning
        dialogs — the caller is responsible for ensuring preconditions.

        Returns
        -------
        bool
            True if preprocessing was applied, False otherwise.
        """
        if self._ms is None:
            return False

        n_active = self._ms.n_active
        min_rep = self._min_rep_spin.value()
        if n_active < min_rep:
            return False

        apply_preprocessing(self._ms, self.current_steps())

        log = self._ms.processing_log
        if log:
            entry = log[-1]
            status = entry.get('status')
            if status == 'applied':
                dropped = entry.get('dropped', [])
                if dropped:
                    self._status_label.setText(f'Dropped: {", ".join(dropped)}')
                else:
                    self._status_label.setText('No replicas dropped.')
            else:
                return False
        self.preprocessing_applied.emit()
        return True

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        form = QFormLayout()

        # Z-Score threshold with inline info button
        self._threshold_spin = QDoubleSpinBox()
        self._threshold_spin.setLocale(_LOCALE_EN)
        self._threshold_spin.setRange(0.5, 10.0)
        self._threshold_spin.setSingleStep(0.5)
        self._threshold_spin.setValue(3.5)
        self._threshold_spin.setDecimals(1)
        self._threshold_spin.setToolTip('Modified z-score threshold.  Replicas where any point exceeds this threshold are deactivated.  Typical range: 2.5–4.0.')

        thr_row = QWidget()
        thr_lay = QHBoxLayout(thr_row)
        thr_lay.setContentsMargins(0, 0, 0, 0)
        thr_lay.setSpacing(6)
        thr_lay.addWidget(self._threshold_spin, 1)
        thr_lay.addWidget(InfoButton('Z-score outlier removal', _ZSCORE_HELP_HTML))
        form.addRow('Z-score threshold:', thr_row)

        # Min replicas
        self._min_rep_spin = QSpinBox()
        self._min_rep_spin.setLocale(_LOCALE_EN)
        self._min_rep_spin.setRange(2, 20)
        self._min_rep_spin.setValue(3)
        self._min_rep_spin.setToolTip('Minimum number of active replicas required to apply the filter.')
        form.addRow('Min replicas:', self._min_rep_spin)

        layout.addLayout(form)

        # Buttons — compact, hug their labels
        btn_row = QHBoxLayout()
        apply_btn = QPushButton('Apply')
        apply_btn.setToolTip('Apply Z-score outlier filter to active replicas')
        apply_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        apply_btn.clicked.connect(self._on_apply)
        reset_btn = QPushButton('Reset')
        reset_btn.setToolTip('Re-activate all replicas')
        reset_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        reset_btn.clicked.connect(self._on_reset)
        btn_row.addWidget(apply_btn)
        btn_row.addWidget(reset_btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        # Status line
        self._status_label = QLabel('')
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_apply(self) -> None:
        if self._ms is None:
            return

        n_active = self._ms.n_active
        min_rep = self._min_rep_spin.value()
        if n_active < min_rep:
            QMessageBox.warning(
                self,
                'Cannot Apply Outlier Filter',
                f'Outlier removal requires at least <b>{min_rep}</b> active replicas, '
                f'but only <b>{n_active}</b> are currently active.<br><br>'
                f'To resolve this: lower <i>Min replicas</i> to {n_active} '
                f'or re-activate replicas using <i>Reset</i>.',
            )
            return

        apply_preprocessing(self._ms, self.current_steps())

        log = self._ms.processing_log
        if log:
            entry = log[-1]
            status = entry.get('status')
            if status == 'applied':
                dropped = entry.get('dropped', [])
                if dropped:
                    self._status_label.setText(f'Dropped: {", ".join(dropped)}')
                else:
                    self._status_label.setText('No replicas dropped.')
            else:
                # Unexpected state — surface it to the user
                reason = entry.get('reason', 'unknown reason')
                QMessageBox.warning(
                    self,
                    'Outlier Filter Not Applied',
                    f'The filter was not applied: {reason}\n\nCheck your configuration and try again.',
                )
                return
        self.preprocessing_applied.emit()

    def _on_reset(self) -> None:
        if self._ms is None:
            return
        self._ms.reset_active()
        self._status_label.setText('All replicas activated.')
        self.preprocessing_reset.emit()
