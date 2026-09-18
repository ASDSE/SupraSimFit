"""What the refit behind every sample of a sensitivity run has to deliver.

A run re-fits the data once per perturbation, and the numbers it reports are
only about the inputs if each of those fits is the fit of *those* inputs, made
on the data the analysis says it describes. Three properties say so, and each
needs real fits of a whole grid, so they live here rather than in the fast
layer:

- cell by cell, a perturbation reports what the ordinary fit of the same
  perturbed inputs reports, so the Estimate in the report and the spread around
  it come from one estimator;
- the estimates scale with the concentrations they were measured against.
  Multiplying every concentration of an experiment by a factor is a change of
  the unit the association constants are expressed in, nothing else, so each of
  them must scale by the inverse of that factor exactly. Measured by a central
  difference through the refit, that identity holds whatever the model or the
  data, and it fails as soon as a refit answers to an input it should not or a
  search stops short of the optimum;
- a replicate the baseline fit left out is out of every perturbed fit too, so
  every sample describes the same measurements.
"""

import numpy as np
import pytest

from core.assays.hg2 import HG2Assay
from core.assays.ida import IDAAssay
from core.data_processing.measurement_set import MeasurementSet
from core.pipeline.fit_pipeline import FitConfig, fit_measurement_set
from core.pipeline.sensitivity import (
    TITRANT,
    InputSpec,
    SensitivityConfig,
    SensitivityMode,
    _fit_perturbed,
    run_sensitivity,
)
from core.units import Q_
from tests.conftest import (
    GDA_IDA_RECOVERY_BOUNDS,
    HG2_RECOVERY_BOUNDS,
    HG2_TRUE,
    IDA_TRUE,
    _make_hg2_data,
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
        input_specs={'h0': InputSpec.sigma_pct(10.0), 'd0': InputSpec.sigma_pct(10.0)},
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


#: Step of the central difference below, as a relative offset of every input it
#: moves. One percent is far above the 1e-7 decades the search resolves a
#: binding constant to, and small enough to leave the signal coefficients well
#: inside the bounds the recovery fixtures clamp them to: they have to take up
#: the concentration factor, and a step that pushes one against its bound would
#: break the invariance being measured rather than measure it.
_STEP = 0.01

#: The identity is exact along this direction, so what a measurement of it
#: carries is the resolution of the search alone: measured 2e-6 for the
#: one-dimensional search (its refinement stops at 1e-7 decades) and 1e-12 for
#: the two-dimensional one, well inside the 5e-3 the analysis is required to
#: hold the identity to.
_TOLERANCE = 1e-4


def _scaling_sensitivity(setup, concentration_keys, inverse_keys=()) -> dict[str, float]:
    """``d ln K / d ln λ`` per binding constant, λ the factor every concentration input carries.

    A central difference through the refit over the direction that scales every
    concentration of the experiment together. ``inverse_keys`` are the inputs
    that are binding constants themselves and therefore scale by ``1/λ``.

    Along this one direction ``ln K`` is exactly linear in ``ln λ``, so the
    difference has no truncation error to trade against the step: measuring the
    sensitivities one input at a time and adding them up afterwards would leave
    one, of order a percent where the estimate reacts to an input as steeply as
    a 1:2 model's does.
    """
    ms, assay_cls, conditions, fit_config = setup
    x_base = np.asarray(ms.concentrations)
    fits = {}
    for sign in (1, -1):
        factor = 1 + sign * _STEP
        offsets = {key: factor - 1 for key in concentration_keys}
        offsets.update({key: 1 / factor - 1 for key in inverse_keys})
        fits[sign], _ = _fit_perturbed(ms, assay_cls, x_base, conditions, offsets, fit_config)
    span = np.log(1 + _STEP) - np.log(1 - _STEP)
    ka_keys = ms.to_assay(assay_cls, conditions=conditions).registry_metadata.log_scale_keys
    return {key: float((np.log(fits[1][key]) - np.log(fits[-1][key])) / span) for key in ka_keys}


def _ida_setup():
    x, y = _make_ida_data(IDA_TRUE, n_points=_N_POINTS)
    ms = MeasurementSet(concentrations=x, signals=y.reshape(1, -1), replica_ids=('r0',))
    return ms, IDAAssay, dict(_CONDITIONS), FitConfig(custom_bounds=GDA_IDA_RECOVERY_BOUNDS)


def _hg2_setup():
    x, y = _make_hg2_data(HG2_TRUE, n_points=_N_POINTS)
    ms = MeasurementSet(concentrations=x, signals=y.reshape(1, -1), replica_ids=('r0',))
    return ms, HG2Assay, {'h0': Q_(HG2_TRUE['h0'], 'M')}, FitConfig(custom_bounds=HG2_RECOVERY_BOUNDS)


def test_the_ida_estimate_scales_with_the_concentrations_it_was_measured_against():
    """Host, dye and titrant a factor larger, the known Ka_dye that factor smaller: Ka_guest follows.

    That is the same experiment with its concentrations expressed in another
    unit, which divides every association constant by the factor and changes
    nothing else — the known ``Ka_dye`` input included, which is why it moves
    the other way. The fitted ``Ka_guest`` has to follow exactly, however the
    data happen to constrain it.
    """
    sensitivity = _scaling_sensitivity(_ida_setup(), ('h0', 'd0', TITRANT), ('Ka_dye',))

    assert sensitivity['Ka_guest'] == pytest.approx(-1.0, abs=_TOLERANCE)


def test_both_stepwise_constants_scale_with_the_concentrations_they_were_measured_against():
    """For the 1:2 model, host and titrant a factor larger divides each stepwise constant by it.

    Both steps are association constants in 1/M, so both follow the same change
    of concentration unit — a two-dimensional search has to satisfy the identity
    in each of its coordinates, and a search that stopped in a flat valley short
    of the optimum would satisfy it in neither.
    """
    sensitivity = _scaling_sensitivity(_hg2_setup(), ('h0', TITRANT))

    assert set(sensitivity) == {'Ka_HG', 'Ka_HG2'}
    for key, value in sensitivity.items():
        assert value == pytest.approx(-1.0, abs=_TOLERANCE), (key, sensitivity)


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
