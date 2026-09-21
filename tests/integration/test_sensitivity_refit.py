"""What the refit behind every sample of a sensitivity run has to deliver.

A run re-fits the data once per perturbation, and the numbers it reports are
only about the inputs if each of those fits is the fit of *those* inputs, made
on the data the analysis says it describes. Two properties say so, and each
needs real fits of a whole grid, so they live here rather than in the fast
layer (that the estimates scale with the concentrations they were measured
against is ``test_homogeneity.py``):

- cell by cell, a perturbation reports what the ordinary fit of the same
  perturbed inputs reports, so the Estimate in the report and the spread around
  it come from one estimator;
- a replicate the baseline fit left out is out of every perturbed fit too, so
  every sample describes the same measurements.
"""

import numpy as np
import pytest

from core.assays.ida import IDAAssay
from core.data_processing.measurement_set import MeasurementSet
from core.pipeline.fit_pipeline import FitConfig, fit_measurement_set
from core.pipeline.sensitivity import (
    ErrorModel,
    InputSpec,
    SensitivityConfig,
    SensitivityMode,
    run_sensitivity,
)
from core.units import Q_
from tests.conftest import (
    GDA_IDA_RECOVERY_BOUNDS,
    IDA_TRUE,
    _make_ida_data,
)

_N_POINTS = 20
_CONDITIONS = {
    'Ka_dye': Q_(IDA_TRUE['Ka_dye'], '1/M'),
    'h0': Q_(IDA_TRUE['h0'], 'M'),
    'd0': Q_(IDA_TRUE['d0'], 'M'),
}


def _noisy_ida(n_replicas: int, *, per_replica: bool, noise_frac: float = 0.02):
    """(ms, conditions, fit_config) whose replicates carry independent noise.

    The noise keeps the best fit well below R² = 1, so the optimum moves with
    every input instead of sitting on an exactly reproducible curve.
    """
    x, y = _make_ida_data(IDA_TRUE, n_points=_N_POINTS)
    rng = np.random.default_rng(4)
    signals = np.vstack([y + rng.normal(0.0, noise_frac * np.ptp(y), y.size) for _ in range(n_replicas)])
    ms = MeasurementSet(concentrations=x, signals=signals, replica_ids=tuple(f'r{i}' for i in range(n_replicas)))
    return ms, dict(_CONDITIONS), FitConfig(custom_bounds=GDA_IDA_RECOVERY_BOUNDS, per_replica=per_replica)


def _grid(n_steps: int) -> SensitivityConfig:
    """An h0 × d0 heatmap, so every perturbation of the run is reported in a cell."""
    return SensitivityConfig(
        mode=SensitivityMode.HEATMAP,
        n_samples=1,
        errors=ErrorModel(specs={'h0': InputSpec.sigma_pct(10.0), 'd0': InputSpec.sigma_pct(10.0)}),
        seed=2,
        x_key='h0',
        y_key='d0',
        n_steps=n_steps,
    )


def test_every_perturbation_reports_the_fit_of_those_inputs():
    """Cell by cell, the run's Ka and R² are those of an ordinary fit of the same perturbed inputs.

    Sample and estimate come from the same engine, so they agree to the
    arithmetic rather than to a tolerance: a cell that differs is a cell fitted
    on other data, other bounds or other conditions than it claims.
    """
    ms, conditions, fit_config = _noisy_ida(3, per_replica=False, noise_frac=0.06)
    cfg = _grid(3)

    result = run_sensitivity(ms, IDAAssay, conditions, fit_config, cfg, max_workers=1)

    for iy, y_offset in enumerate(result.y_offsets_pct / 100.0):
        for ix, x_offset in enumerate(result.x_offsets_pct / 100.0):
            perturbed = {
                **conditions,
                'h0': conditions['h0'] * (1 + x_offset),
                'd0': conditions['d0'] * (1 + y_offset),
            }
            reference = fit_measurement_set(ms, IDAAssay, perturbed, fit_config)
            assert result.ka_grid['Ka_guest'][iy, ix] == pytest.approx(
                reference.parameters['Ka_guest'].magnitude, rel=1e-12
            )
            assert result.r2_grid[iy, ix] == pytest.approx(reference.r_squared, abs=1e-12)


def test_a_replicate_the_baseline_left_out_enters_no_perturbed_fit():
    """A replicate the shared-Ka test excludes is out of the data every sample is fitted on.

    One replicate of four is a titration of a three times stronger binder, so
    the baseline's replicate test drops it; from there the analysis has to
    describe the three that agree, cell for cell, as if the fourth had never
    been measured.
    """
    x, y = _make_ida_data(IDA_TRUE, n_points=_N_POINTS)
    _, odd_one_out = _make_ida_data({**IDA_TRUE, 'Ka_guest': 3 * IDA_TRUE['Ka_guest']}, n_points=_N_POINTS)
    rng = np.random.default_rng(3)
    sigma = 0.01 * np.ptp(y)
    signals = np.vstack(
        [y + rng.normal(0.0, sigma, y.size) for _ in range(3)] + [odd_one_out + rng.normal(0.0, sigma, y.size)]
    )
    fit_config = FitConfig(custom_bounds=GDA_IDA_RECOVERY_BOUNDS, per_replica=True)
    ids = ('r0', 'r1', 'r2', 'r3')
    all_four = MeasurementSet(concentrations=x, signals=signals, replica_ids=ids)
    agreeing = MeasurementSet(concentrations=x, signals=signals[:3], replica_ids=ids[:3])
    cfg = _grid(2)

    result = run_sensitivity(all_four, IDAAssay, dict(_CONDITIONS), fit_config, cfg, max_workers=1)
    without = run_sensitivity(agreeing, IDAAssay, dict(_CONDITIONS), fit_config, cfg, max_workers=1)

    assert list(result.baseline_fit.metadata['replica_failures']) == ['r3']
    np.testing.assert_array_equal(result.ka_grid['Ka_guest'], without.ka_grid['Ka_guest'])
