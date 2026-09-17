"""The perturbed fit of a sensitivity run against a full multi-start search.

Each perturbation of a run is fitted through the exact Ka profile, which is what
makes the analysis affordable and makes every sample repeatable. What it has to
deliver is the fit a full multi-start search of the same perturbed data finds:
the same Ka and the same R², cell by cell, whether the run fits the averaged
signal or every replicate separately. These are real fits of every cell twice
over, so they live here rather than in the fast layer.
"""

from dataclasses import replace

import numpy as np
import pytest

from core.assays.ida import IDAAssay
from core.data_processing.measurement_set import MeasurementSet
from core.pipeline.fit_pipeline import FitConfig, fit_measurement_set
from core.pipeline.sensitivity import InputSpec, SensitivityConfig, SensitivityMode, run_sensitivity
from core.units import Q_
from tests.conftest import GDA_IDA_RECOVERY_BOUNDS, IDA_TRUE, _make_ida_data

_N_POINTS = 20
_CONDITIONS = {
    'Ka_dye': Q_(IDA_TRUE['Ka_dye'], '1/M'),
    'h0': Q_(IDA_TRUE['h0'], 'M'),
    'd0': Q_(IDA_TRUE['d0'], 'M'),
}


def _noisy_ida(n_replicas: int, *, per_replica: bool, noise_frac: float = 0.02):
    """(ms, conditions, fit_config) whose replicates carry independent noise.

    The noise keeps the best fit well below R² = 1, so the optimum moves with
    every input instead of sitting on an exactly reproducible curve, and it makes
    the replicates disagree, so fitting them separately is a different fit from
    fitting their average.
    """
    x, y = _make_ida_data(IDA_TRUE, n_points=_N_POINTS)
    rng = np.random.default_rng(4)
    signals = np.vstack([y + rng.normal(0.0, noise_frac * np.ptp(y), y.size) for _ in range(n_replicas)])
    ms = MeasurementSet(concentrations=x, signals=signals, replica_ids=tuple(f'r{i}' for i in range(n_replicas)))
    fit_config = FitConfig(
        n_trials=20, custom_bounds=GDA_IDA_RECOVERY_BOUNDS, per_replica=per_replica, min_r_squared=0.9
    )
    return ms, dict(_CONDITIONS), fit_config


def _grid(n_steps: int) -> SensitivityConfig:
    """An h0 × d0 heatmap, so every perturbation of the run is reported in a cell."""
    return SensitivityConfig(
        mode=SensitivityMode.HEATMAP,
        n_samples=1,
        input_specs={'h0': InputSpec.sigma_pct(10.0), 'd0': InputSpec.sigma_pct(10.0)},
        seed=2,
        x_key='h0',
        y_key='d0',
        n_steps=n_steps,
    )


@pytest.mark.parametrize(
    ('n_replicas', 'per_replica', 'n_steps', 'noise_frac'),
    [(1, False, 3, 0.02), (4, True, 2, 0.06)],
    ids=['average', 'per_replicate'],
)
def test_every_perturbation_reports_the_fit_a_multistart_search_finds(n_replicas, per_replica, n_steps, noise_frac):
    """Cell by cell, the run's Ka and R² are those of a multi-start fit of the same perturbed inputs.

    Per replicate the reference is ``fit_measurement_set_per_replica``, which
    reports the replica best fit that best fits the averaged signal. The data
    carry independent noise per replicate, so fitting the averaged signal
    instead gives a different Ka — checked, so that agreement here means the
    run applies the same rule and not merely a similar one.
    """
    ms, conditions, fit_config = _noisy_ida(n_replicas, per_replica=per_replica, noise_frac=noise_frac)
    cfg = _grid(n_steps)

    result = run_sensitivity(ms, IDAAssay, conditions, fit_config, cfg, max_workers=1)

    deep = replace(fit_config, n_trials=60, min_r_squared=-np.inf, seed=7)
    for iy, y_offset in enumerate(result.y_offsets_pct / 100.0):
        for ix, x_offset in enumerate(result.x_offsets_pct / 100.0):
            perturbed = {
                **conditions,
                'h0': conditions['h0'] * (1 + x_offset),
                'd0': conditions['d0'] * (1 + y_offset),
            }
            reference = fit_measurement_set(ms, IDAAssay, perturbed, deep)
            assert result.ka_grid['Ka_guest'][iy, ix] == pytest.approx(
                reference.parameters['Ka_guest'].magnitude, rel=0.01
            )
            assert result.r2_grid[iy, ix] == pytest.approx(reference.r_squared, abs=1e-6)

    if per_replica:
        averaged = run_sensitivity(ms, IDAAssay, conditions, replace(fit_config, per_replica=False), cfg, max_workers=1)
        ratio = averaged.ka_grid['Ka_guest'] / result.ka_grid['Ka_guest']
        assert np.max(np.abs(ratio - 1)) > 0.01
