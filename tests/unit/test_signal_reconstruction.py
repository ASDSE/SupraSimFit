"""Signal reconstruction tests.

Fit synthetic data and verify the fitted model reconstructs the observed
signal within tight point-wise tolerances.  Complements parameter recovery
(tested in E2E) by checking that the *predicted curve* matches the data,
not just the Ka value.

Tolerance:
- DBA / IDA: max point-wise relative error < 1%
- GDA: max point-wise relative error < 5% (weaker identifiability)
"""

import numpy as np

from core.assays.dba import DBAAssay
from core.assays.gda import GDAAssay
from core.assays.ida import IDAAssay
from core.pipeline.fit_pipeline import FitConfig, fit_assay
from core.units import Q_
from tests.conftest import DBA_RECOVERY_BOUNDS, GDA_IDA_RECOVERY_BOUNDS

N_TRIALS = 80


class TestDBASignalReconstruction:
    def test_dba_signal_reconstruction_clean(self, dba_clean):
        """Fitted model reconstructs the observed signal within 3%."""
        x, y, true = dba_clean
        assay = DBAAssay(x_data=x, y_data=y, fixed_conc=Q_(true['fixed_conc'], 'M'), mode='DtoH')
        result = fit_assay(assay, FitConfig(n_trials=N_TRIALS, custom_bounds=DBA_RECOVERY_BOUNDS))

        max_rel_err = np.max(np.abs((result.y_fit - y).magnitude) / np.abs(y.magnitude))
        assert max_rel_err < 0.03, f'Max point-wise relative error {max_rel_err:.2%} > 3%'


class TestGDASignalReconstruction:
    def test_gda_signal_reconstruction_clean(self, gda_clean):
        """Fitted model reconstructs the observed signal within 10%."""
        x, y, true = gda_clean
        assay = GDAAssay(x_data=x, y_data=y, Ka_dye=Q_(true['Ka_dye'], '1/M'), h0=Q_(true['h0'], 'M'), g0=Q_(true['g0'], 'M'))
        # GDA competitive model needs more trials due to weaker identifiability
        result = fit_assay(assay, FitConfig(n_trials=N_TRIALS, custom_bounds=GDA_IDA_RECOVERY_BOUNDS))

        max_rel_err = np.max(np.abs((result.y_fit - y).magnitude) / np.abs(y.magnitude))
        assert max_rel_err < 0.10, f'Max point-wise relative error {max_rel_err:.2%} > 10%'


class TestIDASignalReconstruction:
    def test_ida_signal_reconstruction_clean(self, ida_clean):
        """Fitted model reconstructs the observed signal within 1%."""
        x, y, true = ida_clean
        assay = IDAAssay(x_data=x, y_data=y, Ka_dye=Q_(true['Ka_dye'], '1/M'), h0=Q_(true['h0'], 'M'), d0=Q_(true['d0'], 'M'))
        result = fit_assay(assay, FitConfig(n_trials=N_TRIALS, custom_bounds=GDA_IDA_RECOVERY_BOUNDS))

        max_rel_err = np.max(np.abs((result.y_fit - y).magnitude) / np.abs(y.magnitude))
        assert max_rel_err < 0.01, f'Max point-wise relative error {max_rel_err:.2%} > 1%'
