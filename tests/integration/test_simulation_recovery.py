"""End-to-end: data simulated by the applet's core is recoverable by the fitter.

This is the round-trip that justifies "no divergent math" — generate a titration
with a known Ka via :func:`core.simulation.simulate_dataset`, fit it back with the
real pipeline, and confirm Ka returns within the clean-data tolerance, with the
truth inside the reported interval. Kept to two representative assays.
"""

from core.assays.gda import GDAAssay
from core.assays.ida import IDAAssay
from core.pipeline.fit_pipeline import FitConfig, fit_measurement_set, summarize_parameters
from core.simulation import build_concentration_vector, simulate_dataset
from core.units import Q_
from tests.conftest import (
    GDA_IDA_RECOVERY_BOUNDS,
    GDA_TRUE,
    IDA_TRUE,
    assert_within_tolerance,
)

_CLEAN_TOL = 0.10


def _params(true: dict) -> dict:
    return {k: true[k] for k in ('Ka_guest', 'I0', 'I_dye_free', 'I_dye_bound')}


def _covers(result, truth: float) -> bool:
    """Whether the reported interval of Ka_guest holds the value the data were simulated with."""
    row = next(r for r in summarize_parameters(result) if r.key == 'Ka_guest' and not r.is_log)
    return row.interval[0] <= truth <= row.interval[1]


def test_simulated_gda_recovers_ka():
    conditions = {
        'Ka_dye': Q_(GDA_TRUE['Ka_dye'], '1/M'),
        'h0': Q_(GDA_TRUE['h0'], 'M'),
        'g0': Q_(GDA_TRUE['g0'], 'M'),
    }
    x = build_concentration_vector('linear', start=1e-7, stop=30e-6, n=30)
    ms = simulate_dataset(GDAAssay, conditions, _params(GDA_TRUE), x)  # clean

    result = fit_measurement_set(ms, GDAAssay, conditions, FitConfig(custom_bounds=GDA_IDA_RECOVERY_BOUNDS))

    assert_within_tolerance(result.parameters['Ka_guest'], GDA_TRUE['Ka_guest'], _CLEAN_TOL, 'Ka_guest')
    assert _covers(result, GDA_TRUE['Ka_guest'])


def test_simulated_ida_recovers_ka():
    conditions = {
        'Ka_dye': Q_(IDA_TRUE['Ka_dye'], '1/M'),
        'h0': Q_(IDA_TRUE['h0'], 'M'),
        'd0': Q_(IDA_TRUE['d0'], 'M'),
    }
    x = build_concentration_vector('linear', start=0.0, stop=50e-6, n=30)
    ms = simulate_dataset(IDAAssay, conditions, _params(IDA_TRUE), x)  # clean

    result = fit_measurement_set(ms, IDAAssay, conditions, FitConfig(custom_bounds=GDA_IDA_RECOVERY_BOUNDS))

    assert_within_tolerance(result.parameters['Ka_guest'], IDA_TRUE['Ka_guest'], _CLEAN_TOL, 'Ka_guest')
    assert _covers(result, IDA_TRUE['Ka_guest'])
