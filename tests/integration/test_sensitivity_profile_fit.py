"""The fit a sensitivity run starts from, when the same uncertainties also widen the fit's own interval.

The uncertainties of the entered inputs do two things: the reported interval of
a fit accounts for them, and a sensitivity run samples them. The two answer
different questions, and a run that started from a fit which had already
absorbed the uncertainties would report the spread of its samples around a
point that is not the fit at the inputs as entered. These tests need real fits
of a whole grid, so they live here rather than in the fast layer.
"""

import numpy as np
import pytest

from core.assays.ida import IDAAssay
from core.data_processing.measurement_set import MeasurementSet
from core.pipeline.fit_pipeline import FitConfig, fit_measurement_set
from core.pipeline.inputs import TITRANT, ErrorModel, InputSpec
from core.pipeline.sensitivity import SensitivityConfig, SensitivityMode, run_sensitivity
from core.units import Q_
from tests.conftest import GDA_IDA_RECOVERY_BOUNDS, IDA_TRUE, _make_ida_data

_CONDITIONS = {
    'Ka_dye': Q_(IDA_TRUE['Ka_dye'], '1/M'),
    # Entered 8 % above the truth, so the fit that may move it lands elsewhere
    # than the fit that may not.
    'h0': Q_(IDA_TRUE['h0'] * 1.08, 'M'),
    'd0': Q_(IDA_TRUE['d0'], 'M'),
}
_SPECS = {'h0': InputSpec.sigma_pct(10), TITRANT: InputSpec.sigma_pct(3)}


def _ida_ms(n_points: int = 12, seed: int = 5) -> MeasurementSet:
    x, y = _make_ida_data(IDA_TRUE, n_points=n_points)
    rng = np.random.default_rng(seed)
    signals = np.vstack([y + rng.normal(0.0, 0.005 * np.ptp(y), y.size) for _ in range(3)])
    return MeasurementSet(concentrations=x, signals=signals, replica_ids=('a', 'b', 'c'))


def _heatmap(specs: dict) -> SensitivityConfig:
    """A three-by-three sweep of two inputs: the smallest run that still has a zero-offset cell."""
    return SensitivityConfig(
        mode=SensitivityMode.HEATMAP,
        n_samples=0,
        errors=ErrorModel(specs=specs),
        seed=1,
        x_key='h0',
        y_key=TITRANT,
        n_steps=3,
    )


def test_the_run_starts_from_the_fit_at_the_inputs_as_entered():
    """Its samples are the offsets from that fit, so the fit itself must hold every input where it was entered."""
    ms = _ida_ms()
    fit_config = FitConfig(custom_bounds=GDA_IDA_RECOVERY_BOUNDS, per_replica=False, errors=ErrorModel(specs=_SPECS))

    result = run_sensitivity(ms, IDAAssay, _CONDITIONS, fit_config, _heatmap(_SPECS), max_workers=1)

    fit = fit_measurement_set(ms, IDAAssay, _CONDITIONS, fit_config)
    baseline_ka = result.baseline_ka['Ka_guest']
    assert result.baseline_fit.input_shifts == {}
    assert baseline_ka == pytest.approx(float(fit.conditional.parameters['Ka_guest'].magnitude), rel=1e-12)
    # Not the reported fit, which moved the host concentration to describe the data.
    assert baseline_ka != pytest.approx(float(fit.parameters['Ka_guest'].magnitude), rel=1e-3)
    assert result.baseline_fit.intervals['Ka_guest'] == fit.conditional.intervals['Ka_guest']


def test_a_run_is_not_refused_because_the_interval_of_a_fit_would_be():
    """Sampling the inputs one value at a time asks nothing of the data that the fit at the entered inputs does not."""
    ms = _ida_ms(n_points=6)
    # Every input free within a range is one more parameter the six points have
    # to pay for; the fit has nothing left to judge Ka by.
    specs = {
        'h0': InputSpec.interval_pct(-20, 20),
        'd0': InputSpec.interval_pct(-20, 20),
        TITRANT: InputSpec.interval_pct(-5, 5),
    }
    fit_config = FitConfig(custom_bounds=GDA_IDA_RECOVERY_BOUNDS, per_replica=False, errors=ErrorModel(specs=specs))

    with pytest.raises(ValueError, match='too few to fit this model'):
        fit_measurement_set(ms, IDAAssay, _CONDITIONS, fit_config)

    result = run_sensitivity(ms, IDAAssay, _CONDITIONS, fit_config, _heatmap(specs), max_workers=1)

    assert result.n_success == result.n_total == 9
    assert np.isfinite(result.baseline_ka['Ka_guest'])
