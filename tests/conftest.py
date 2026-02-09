"""Shared test fixtures for synthetic assay data.

Generates clean and noisy synthetic datasets with known ground-truth
parameters so that fitted results can be compared against true values.

Tolerance Guidelines:
- Clean synthetic data: 10% tolerance
- 5% Gaussian noise: 20% tolerance

Parameter Identifiability Notes:
- Ka (association constant) is always identifiable — it controls curve shape.
- Signal coefficients (I0, I_dye_free, I_dye_bound) have structural degeneracies
  in DBA and IDA because the sum [D_free] + [HD] = const (fixed species).
  Individual signal coefficients are NOT independently recoverable.
- I0 is set to 0 in ground truth to reduce the parameter space.
- Signal coefficient bounds are kept tight (±20% of truth) to constrain the
  degenerate subspace and let Ka be recovered cleanly.
"""

import numpy as np
import pytest

from core.models.equilibrium import dba_signal, gda_signal, ida_signal
from core.models.linear import linear_signal

# ---------------------------------------------------------------------------
# True parameter values (ground truth for recovery tests)
# ---------------------------------------------------------------------------
# Signal coefficients are per-Molar, so with µM concentrations (~1e-5 M):
#   I_dye_free * [D] ≈ 5e7 * 1e-5 = 500 a.u.
#   I_dye_bound * [HD] ≈ 3e8 * 1e-5 = 3000 a.u.
# This gives realistic signal ranges (hundreds to thousands).
#
# I0 = 0 minimises I0/signal-coefficient degeneracy.

# DBA ground truth
DBA_TRUE = {
    'Ka_dye': 5e5,  # M^-1
    'I0': 0.0,
    'I_dye_free': 5e7,  # a.u./M  → ~500 at 10 µM
    'I_dye_bound': 3e8,  # a.u./M  → ~3000 at 10 µM
    'fixed_conc': 10e-6,  # 10 µM host (fixed)
}

# GDA ground truth
# g0 = 20 µM gives strong competition sensitivity for Ka_guest recovery.
GDA_TRUE = {
    'Ka_guest': 1.5e6,  # M^-1
    'I0': 0.0,
    'I_dye_free': 5e7,  # a.u./M
    'I_dye_bound': 3e8,  # a.u./M
    'Ka_dye': 5e5,  # Known from DBA (M^-1)
    'h0': 10e-6,  # 10 µM host
    'g0': 20e-6,  # 20 µM guest (high for strong competition)
}

# IDA ground truth
IDA_TRUE = {
    'Ka_guest': 2e6,  # M^-1
    'I0': 0.0,
    'I_dye_free': 5e7,  # a.u./M
    'I_dye_bound': 3e8,  # a.u./M
    'Ka_dye': 5e5,  # Known from DBA (M^-1)
    'h0': 10e-6,  # 10 µM host
    'd0': 5e-6,  # 5 µM dye
}

# DyeAlone ground truth
DYE_ALONE_TRUE = {
    'slope': 5e10,  # a.u. / M
    'intercept': 100.0,
}

# Bounds for recovery tests.
# Signal coefficient bounds are tight (±20% of truth) because individual
# signal coefficients are NOT independently identifiable in the 4-param
# nonlinear model.  Tight bounds simulate the realistic workflow where
# I_dye_free / I_dye_bound are known from a prior DBA calibration.
# Ka bounds remain wide (log-scale sampled).
RECOVERY_BOUNDS = [
    (1e-8, 1e12),  # Ka (M^-1) — wide, log-scale sampled
    (-100, 100),  # I0 — tight around 0
    (4e7, 6e7),  # I_dye_free — ±20% of 5e7
    (2.5e8, 3.5e8),  # I_dye_bound — ±20% of 3e8
]


# ---------------------------------------------------------------------------
# Reproducibility: seed the global RNG so multistart optimizer is deterministic
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _seed_rng():
    """Seed numpy global RNG before each test for reproducible optimization."""
    np.random.seed(42)


# ---------------------------------------------------------------------------
# Synthetic data generators
# ---------------------------------------------------------------------------


def _make_dba_data(true: dict, n_points: int = 30, noise_frac: float = 0.0, rng: np.random.Generator | None = None):
    """Generate synthetic DBA data (Dye→Host titration)."""
    x = np.linspace(1e-7, 50e-6, n_points)
    y_clean = dba_signal(
        I0=true['I0'],
        Ka_dye=true['Ka_dye'],
        I_dye_free=true['I_dye_free'],
        I_dye_bound=true['I_dye_bound'],
        x_titrant=x,
        y_fixed=true['fixed_conc'],
    )
    if noise_frac > 0:
        if rng is None:
            rng = np.random.default_rng(42)
        y = y_clean + rng.normal(0, noise_frac * np.abs(y_clean))
    else:
        y = y_clean
    return x, y


def _make_gda_data(true: dict, n_points: int = 30, noise_frac: float = 0.0, rng: np.random.Generator | None = None):
    """Generate synthetic GDA data (Dye titrated into Host+Guest)."""
    d0_values = np.linspace(1e-7, 30e-6, n_points)
    y_clean = gda_signal(
        I0=true['I0'],
        Ka_guest=true['Ka_guest'],
        I_dye_free=true['I_dye_free'],
        I_dye_bound=true['I_dye_bound'],
        Ka_dye=true['Ka_dye'],
        h0=true['h0'],
        d0_values=d0_values,
        g0=true['g0'],
    )
    if noise_frac > 0:
        if rng is None:
            rng = np.random.default_rng(42)
        y = y_clean + rng.normal(0, noise_frac * np.abs(y_clean))
    else:
        y = y_clean
    return d0_values, y


def _make_ida_data(true: dict, n_points: int = 30, noise_frac: float = 0.0, rng: np.random.Generator | None = None):
    """Generate synthetic IDA data (Guest titrated into Host+Dye)."""
    g0_values = np.linspace(0, 50e-6, n_points)
    y_clean = ida_signal(
        I0=true['I0'],
        Ka_guest=true['Ka_guest'],
        I_dye_free=true['I_dye_free'],
        I_dye_bound=true['I_dye_bound'],
        Ka_dye=true['Ka_dye'],
        h0=true['h0'],
        d0=true['d0'],
        g0_values=g0_values,
    )
    if noise_frac > 0:
        if rng is None:
            rng = np.random.default_rng(42)
        y = y_clean + rng.normal(0, noise_frac * np.abs(y_clean))
    else:
        y = y_clean
    return g0_values, y


def _make_dye_alone_data(true: dict, n_points: int = 15, noise_frac: float = 0.0, rng: np.random.Generator | None = None):
    """Generate synthetic dye-alone data."""
    x = np.linspace(0, 20e-6, n_points)
    y_clean = linear_signal(true['slope'], true['intercept'], x)
    if noise_frac > 0:
        if rng is None:
            rng = np.random.default_rng(42)
        y = y_clean + rng.normal(0, noise_frac * np.abs(y_clean + 1))
    else:
        y = y_clean
    return x, y


# ---------------------------------------------------------------------------
# Fixtures: clean synthetic data (10% tolerance)
# ---------------------------------------------------------------------------


@pytest.fixture
def dba_clean():
    """DBA synthetic data with no noise."""
    x, y = _make_dba_data(DBA_TRUE)
    return x, y, DBA_TRUE


@pytest.fixture
def gda_clean():
    """GDA synthetic data with no noise."""
    x, y = _make_gda_data(GDA_TRUE)
    return x, y, GDA_TRUE


@pytest.fixture
def ida_clean():
    """IDA synthetic data with no noise."""
    x, y = _make_ida_data(IDA_TRUE)
    return x, y, IDA_TRUE


@pytest.fixture
def dye_alone_clean():
    """DyeAlone synthetic data with no noise."""
    x, y = _make_dye_alone_data(DYE_ALONE_TRUE)
    return x, y, DYE_ALONE_TRUE


# ---------------------------------------------------------------------------
# Fixtures: noisy synthetic data (20% tolerance)
# ---------------------------------------------------------------------------


@pytest.fixture
def dba_noisy():
    """DBA synthetic data with 5% Gaussian noise."""
    x, y = _make_dba_data(DBA_TRUE, noise_frac=0.05)
    return x, y, DBA_TRUE


@pytest.fixture
def gda_noisy():
    """GDA synthetic data with 5% Gaussian noise."""
    x, y = _make_gda_data(GDA_TRUE, noise_frac=0.05)
    return x, y, GDA_TRUE


@pytest.fixture
def ida_noisy():
    """IDA synthetic data with 5% Gaussian noise."""
    x, y = _make_ida_data(IDA_TRUE, noise_frac=0.05)
    return x, y, IDA_TRUE


# ---------------------------------------------------------------------------
# Helper: tolerance assertion
# ---------------------------------------------------------------------------


def assert_within_tolerance(fitted, true, tolerance, param_name='parameter'):
    """Assert fitted value is within tolerance of true value.

    Parameters
    ----------
    fitted : float
        Fitted parameter value.
    true : float
        Ground truth value.
    tolerance : float
        Fractional tolerance (e.g. 0.1 for 10%).
    param_name : str
        Parameter name for error message.
    """
    rel_error = abs(fitted - true) / abs(true)
    assert rel_error <= tolerance, f'{param_name}: fitted={fitted:.4e}, true={true:.4e}, rel_error={rel_error:.1%} > tolerance={tolerance:.0%}'
