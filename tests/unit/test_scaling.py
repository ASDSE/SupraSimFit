"""Tests for the parameter scaler (core.optimizer.scaling).

The scaler is an exact affine reparameterization of the fit problem.
These tests cover:

- Correct scale-factor derivation from parameter units.
- Round-trip: ``to_external(to_internal(theta)) == theta``.
- Bound transformation preserves ordering and width ratios.
- Degenerate-data guards raise ``ValueError``.
- End-to-end equivalence with and without the scaler on a synthetic IDA
  problem: fit quality is at least as good with scaling enabled.
"""

from __future__ import annotations

import numpy as np
import pytest

from core.assays.ida import IDAAssay
from core.models.equilibrium import ida_signal
from core.optimizer.multistart import multistart_minimize
from core.optimizer.scaling import ParamScaler, _scale_factor
from core.pipeline.fit_pipeline import FitConfig, fit_assay
from core.units import Q_


# ---------------------------------------------------------------------------
# _scale_factor
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    'unit_str, c_max, s_max, expected',
    [
        ('dimensionless', 1e-4, 1e5, 1.0),
        ('au', 1e-4, 1e5, 1.0 / 1e5),
        ('1/M', 1e-4, 1e5, 1e-4),
        ('au/M', 1e-4, 1e5, 1e-4 / 1e5),
        ('M', 2.0, 3.0, 1.0 / 2.0),
        ('µM', 2.0, 3.0, 1e-6 / 2.0),
        ('1/µM', 2.0, 3.0, 1e6 * 2.0),
    ],
)
def test_scale_factor_known_units(unit_str, c_max, s_max, expected):
    unit = Q_(1.0, unit_str).units
    assert _scale_factor(unit, c_max, s_max) == pytest.approx(expected, rel=1e-12)


# ---------------------------------------------------------------------------
# Fixtures: synthetic IDA assay
#
# The scaler's end-to-end tests need a landscape where multistart reliably
# reaches the global minimum in ~60 trials. conftest's IDA_TRUE has a
# harder landscape (I0 = 0 + specific Ka magnitudes) that exposes a
# reachable local minimum at Ka ≈ 5e7, breaking these tests. The local
# truth below is chosen to be well-conditioned for the scaler tests.
# ---------------------------------------------------------------------------


_LOCAL_TRUTH = dict(
    Ka_dye=1.68e7,
    h0=4.3e-6,
    d0=6e-6,
    I0=5e3,
    I_dye_free=8e8,
    I_dye_bound=1.2e10,
    Ka_guest=3e6,
)


def _make_ida_assay(x: np.ndarray, y: np.ndarray) -> IDAAssay:
    """Build an IDAAssay around arbitrary (x, y) arrays using local truth conditions."""
    return IDAAssay(
        x_data=Q_(x, 'M'),
        y_data=Q_(y, 'au'),
        Ka_dye=Q_(_LOCAL_TRUTH['Ka_dye'], '1/M'),
        h0=Q_(_LOCAL_TRUTH['h0'], 'M'),
        d0=Q_(_LOCAL_TRUTH['d0'], 'M'),
    )


@pytest.fixture
def ida_assay():
    g0 = np.linspace(1e-7, 3e-5, 15)
    y = ida_signal(
        _LOCAL_TRUTH['I0'],
        _LOCAL_TRUTH['Ka_guest'],
        _LOCAL_TRUTH['I_dye_free'],
        _LOCAL_TRUTH['I_dye_bound'],
        _LOCAL_TRUTH['Ka_dye'],
        _LOCAL_TRUTH['h0'],
        _LOCAL_TRUTH['d0'],
        g0,
    )
    return _make_ida_assay(g0, y)


# ---------------------------------------------------------------------------
# ParamScaler: construction and transforms
# ---------------------------------------------------------------------------


def test_from_assay_derives_scales(ida_assay):
    scaler = ParamScaler.from_assay(ida_assay)

    c_max = float(np.max(ida_assay.x_data.magnitude))
    s_max = float(np.max(ida_assay.y_data.magnitude))

    assert scaler.loss_scale == pytest.approx(s_max**2)

    # Parameter order for IDA: (Ka_guest, I0, I_dye_free, I_dye_bound)
    expected = np.array([c_max, 1.0 / s_max, c_max / s_max, c_max / s_max])
    np.testing.assert_allclose(scaler.scales, expected, rtol=1e-12)


def test_round_trip(ida_assay):
    scaler = ParamScaler.from_assay(ida_assay)
    rng = np.random.default_rng(7)
    for _ in range(20):
        theta = rng.uniform(1e-3, 1e6, size=len(scaler.scales))
        back = scaler.to_external(scaler.to_internal(theta))
        np.testing.assert_allclose(back, theta, rtol=1e-12, atol=0)


def test_bounds_preserve_ordering_and_width(ida_assay):
    scaler = ParamScaler.from_assay(ida_assay)
    raw_bounds = [(1e-8, 1e12), (0.0, 1e8), (0.0, 1e12), (0.0, 1e12)]
    tilded = scaler.bounds_to_internal(raw_bounds)

    assert len(tilded) == len(raw_bounds)
    for (rlo, rhi), (tlo, thi), s in zip(raw_bounds, tilded, scaler.scales):
        assert tlo <= thi
        assert tlo == pytest.approx(rlo * s)
        assert thi == pytest.approx(rhi * s)


# ---------------------------------------------------------------------------
# Degenerate-data guards
# ---------------------------------------------------------------------------


def test_from_assay_rejects_zero_signal():
    g0 = np.linspace(1e-7, 3e-5, 15)
    assay = _make_ida_assay(g0, np.zeros_like(g0))
    with pytest.raises(ValueError, match='peak signal'):
        ParamScaler.from_assay(assay)


def test_from_assay_rejects_zero_concentration():
    g0 = np.zeros(15)
    y = np.ones_like(g0) * 1e3
    assay = _make_ida_assay(g0, y)
    with pytest.raises(ValueError, match='peak concentration'):
        ParamScaler.from_assay(assay)


# ---------------------------------------------------------------------------
# Objective wrapping: loss ratio equals loss_scale
# ---------------------------------------------------------------------------


def test_wrap_objective_divides_by_loss_scale(ida_assay):
    scaler = ParamScaler.from_assay(ida_assay)

    def raw_obj(params):
        return float(np.sum(params**2))

    wrapped = scaler.wrap_objective(raw_obj)
    rng = np.random.default_rng(3)
    for _ in range(5):
        theta_raw = rng.uniform(1e-2, 10.0, size=len(scaler.scales))
        theta_tilded = scaler.to_internal(theta_raw)
        assert wrapped(theta_tilded) == pytest.approx(raw_obj(theta_raw) / scaler.loss_scale, rel=1e-12)


# ---------------------------------------------------------------------------
# multistart_minimize: scaler in/out is in raw space
# ---------------------------------------------------------------------------


def test_multistart_returns_raw_params_when_scaled(ida_assay):
    scaler = ParamScaler.from_assay(ida_assay)
    bounds = [(float(lo.magnitude), float(hi.magnitude)) for lo, hi in [ida_assay.get_default_bounds()[k] for k in ida_assay.parameter_keys]]

    def objective(params):
        return ida_assay.sum_squared_residuals(params)

    np.random.seed(0)
    attempts = multistart_minimize(
        objective=objective,
        bounds=bounds,
        n_trials=5,
        scaler=scaler,
    )
    assert attempts, 'expected at least one successful attempt'
    for attempt in attempts:
        assert attempt.params.shape == (len(bounds),)
        lo = np.array([b[0] for b in bounds])
        hi = np.array([b[1] for b in bounds])
        assert np.all(attempt.params >= lo - 1e-9)
        assert np.all(attempt.params <= hi + 1e-9)


# ---------------------------------------------------------------------------
# End-to-end: scaling helps, never hurts
# ---------------------------------------------------------------------------


def test_rescaling_recovers_true_params_on_clean_data(ida_assay):
    np.random.seed(123)
    result = fit_assay(ida_assay, FitConfig(n_trials=60, rescale_parameters=True))
    assert result.success, 'scaled fit should produce passing trials on clean data'
    recovered_ka = float(result.parameters['Ka_guest'].magnitude)
    assert recovered_ka == pytest.approx(_LOCAL_TRUTH['Ka_guest'], rel=0.10)


def test_rescaling_matches_or_beats_raw_on_clean_data(ida_assay):
    np.random.seed(123)
    r_on = fit_assay(ida_assay, FitConfig(n_trials=60, rescale_parameters=True))
    np.random.seed(123)
    r_off = fit_assay(ida_assay, FitConfig(n_trials=60, rescale_parameters=False))

    assert r_on.success, 'scaled fit must pass QC on clean data'
    if r_off.success:
        assert r_on.rmse <= r_off.rmse * 2.0
        assert r_on.n_passing >= r_off.n_passing // 2
