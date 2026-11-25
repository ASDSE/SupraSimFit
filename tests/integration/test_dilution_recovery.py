"""Recovery of the binding constants from data a titration actually produces.

Every fixed total falls as titrant is added.  These tests generate the signal
of a titration whose sample is diluted to 90 % of its starting volume by the
last point, from an equilibrium solve written here — ``scipy.optimize.brentq``
on the free-host or the free-ligand mass balance, per point, with the totals of
that point — so the data owe nothing to :mod:`core.models`.  A fit that is told
the titrant stock concentration must return the constants the data were made
with; a fit that holds the totals constant must not, or the declaration would
be decoration.
"""

import numpy as np
import pytest
from scipy.optimize import brentq

from core.assays.dba import DBAAssay
from core.assays.gda import GDAAssay
from core.assays.h2g import H2GAssay
from core.assays.hg2 import HG2Assay
from core.assays.ida import IDAAssay
from core.pipeline.fit_pipeline import FitConfig, fit_assay
from core.units import Q_
from tests.conftest import (
    DBA_RECOVERY_BOUNDS,
    DBA_TRUE,
    GDA_IDA_RECOVERY_BOUNDS,
    GDA_TRUE,
    H2G_RECOVERY_BOUNDS,
    H2G_TRUE,
    HG2_RECOVERY_BOUNDS,
    HG2_TRUE,
    IDA_TRUE,
)

# Fraction of the final volume that is titrant stock: the sample is at 90 % of
# its starting concentration at the last point.  Large enough that a fit which
# ignores it is wrong by far more than the tolerance, small enough to be an
# ordinary titration.
DILUTION = 0.10

# brentq at the tightest relative tolerance it accepts: the root is then within
# a few eps of the exact one and the generated signal is exact to rounding.
_BRENT = {'xtol': 1e-300, 'rtol': 4 * np.finfo(float).eps, 'maxiter': 400}

# Decades the fit may miss the truth by.  A one-Ka fit of noise-free data lands
# on the generating constant to the precision of the equilibrium solves; the
# stepwise pair trades off along a valley, so its optimum is found to fewer
# digits.
ONE_KA_TOL = 1e-6
TWO_KA_TOL = 1e-4

# How many times the exact model's own miss a constant-totals fit must be wrong
# by for the declaration to be doing work.  The size of the bias is a property
# of the system, not of the method — at this 10 % dilution it is 0.0023 decades
# for the IDA ground truth, 0.057 for GDA and 0.29 for DBA host-to-dye — so what
# is asserted is that it dwarfs what the exact model leaves, and not a number
# one design happens to produce.
BIAS_FACTOR = 100


# ---------------------------------------------------------------------------
# Independent equilibrium solves
# ---------------------------------------------------------------------------


def _competitive_free_host(ka_guest: float, ka_dye: float, h0: float, d0: float, g0: float) -> float:
    """Free host of H/D/G competition: the root of h + [HD] + [HG] - h0."""
    if h0 <= 0.0:
        return 0.0

    def balance(h: float) -> float:
        return h + d0 * ka_dye * h / (1.0 + ka_dye * h) + g0 * ka_guest * h / (1.0 + ka_guest * h) - h0

    return brentq(balance, 0.0, h0, **_BRENT)


def _binary_free_host(ka: float, h_total: float, d_total: float) -> float:
    """Free host of H + D <=> HD: the root of h + [HD] - h_total."""
    if h_total <= 0.0:
        return 0.0

    def balance(h: float) -> float:
        return h + d_total * ka * h / (1.0 + ka * h) - h_total

    return brentq(balance, 0.0, h_total, **_BRENT)


def _stepwise_free_ligand(k1: float, k2: float, core_total: float, ligand_total: float) -> float:
    """Free ligand of a stepwise 1:2 system: the root of l + [CL] + 2[CL2] - ligand_total."""
    if ligand_total <= 0.0:
        return 0.0

    def balance(ligand: float) -> float:
        a = k1 * ligand
        b = a * (k2 * ligand)
        return ligand + core_total * (a + 2.0 * b) / (1.0 + a + b) - ligand_total

    return brentq(balance, 0.0, ligand_total, **_BRENT)


def _dye_signal(true: dict, ka_dye: float, h_free: np.ndarray, d_total: np.ndarray) -> np.ndarray:
    """Signal of a dye whose free and bound forms both emit."""
    bound_fraction = ka_dye * h_free / (1.0 + ka_dye * h_free)
    return (
        true['I0']
        + true['I_dye_free'] * d_total * (1.0 - bound_fraction)
        + true['I_dye_bound'] * d_total * bound_fraction
    )


def _stepwise_signal(true: dict, k1: float, k2: float, free_ligand, core_total, second: str) -> np.ndarray:
    """Signal of a core that binds two ligands, from the free-ligand root."""
    a = k1 * free_ligand
    b = a * (k2 * free_ligand)
    denom = 1.0 + a + b
    core, cl, cl2 = core_total / denom, core_total * (a / denom), core_total * (b / denom)
    if second == 'HG2':  # core = host, ligand = guest
        free_host, free_guest, hg, hg2 = core, free_ligand, cl, cl2
    else:  # H2G: core = guest, ligand = host
        free_host, free_guest, hg, hg2 = free_ligand, core, cl, cl2
    return (
        true['I0'] + true['I_G'] * free_guest + true['I_H'] * free_host + true['I_HG'] * hg + true[f'I_{second}'] * hg2
    )


# ---------------------------------------------------------------------------
# Titrations
# ---------------------------------------------------------------------------


def _titration(stop: float, start: float = 0.0, n: int = 30) -> tuple[np.ndarray, float]:
    """Titrant grid and the stock concentration that dilutes it by ``DILUTION``."""
    x = np.linspace(start, stop, n)
    return x, stop / DILUTION


def _generate(name: str, dilute_dye: bool = True) -> tuple[np.ndarray, np.ndarray, float]:
    """Titrant grid, the signal of the diluted titration, and the titrant stock it took."""
    if name == 'IDA':
        x, stock = _titration(50e-6)
        keep = 1.0 - x / stock
        h0 = IDA_TRUE['h0'] * keep
        d0 = IDA_TRUE['d0'] * (keep if dilute_dye else np.ones_like(x))
        h = np.array(
            [
                _competitive_free_host(IDA_TRUE['Ka_guest'], IDA_TRUE['Ka_dye'], hi, di, gi)
                for hi, di, gi in zip(h0, d0, x)
            ]
        )
        return x, _dye_signal(IDA_TRUE, IDA_TRUE['Ka_dye'], h, d0), stock

    if name == 'GDA':
        x, stock = _titration(30e-6, start=1e-7)
        keep = 1.0 - x / stock
        h0, g0 = GDA_TRUE['h0'] * keep, GDA_TRUE['g0'] * keep
        h = np.array(
            [
                _competitive_free_host(GDA_TRUE['Ka_guest'], GDA_TRUE['Ka_dye'], hi, di, gi)
                for hi, di, gi in zip(h0, x, g0)
            ]
        )
        return x, _dye_signal(GDA_TRUE, GDA_TRUE['Ka_dye'], h, x), stock

    if name in ('DBA_HtoD', 'DBA_DtoH'):
        x, stock = _titration(50e-6, start=1e-7)
        fixed = DBA_TRUE['fixed_conc'] * (1.0 - x / stock)
        h_total, d_total = (x, fixed) if name == 'DBA_HtoD' else (fixed, x)
        h = np.array([_binary_free_host(DBA_TRUE['Ka_dye'], ht, dt) for ht, dt in zip(h_total, d_total)])
        return x, _dye_signal(DBA_TRUE, DBA_TRUE['Ka_dye'], h, d_total), stock

    if name == 'HG2':
        x, stock = _titration(1.2e-3)
        h0 = HG2_TRUE['h0'] * (1.0 - x / stock)
        g = np.array([_stepwise_free_ligand(HG2_TRUE['Ka_HG'], HG2_TRUE['Ka_HG2'], hi, gi) for hi, gi in zip(h0, x)])
        y = _stepwise_signal(HG2_TRUE, HG2_TRUE['Ka_HG'], HG2_TRUE['Ka_HG2'], g, h0, 'HG2')
        return x, y, stock

    if name == 'H2G':
        x, stock = _titration(6e-4)
        h0 = H2G_TRUE['h0'] * (1.0 - x / stock)
        h = np.array([_stepwise_free_ligand(H2G_TRUE['Ka_HG'], H2G_TRUE['Ka_H2G'], gi, hi) for hi, gi in zip(h0, x)])
        y = _stepwise_signal(H2G_TRUE, H2G_TRUE['Ka_HG'], H2G_TRUE['Ka_H2G'], h, x, 'H2G')
        return x, y, stock

    raise AssertionError(name)


def _assay(name: str, x: np.ndarray, y: np.ndarray, **dilution):
    """The registered assay for *name* on the given titration."""
    data = {'x_data': Q_(x, 'M'), 'y_data': Q_(y, 'au')}
    if name == 'IDA':
        return IDAAssay(
            **data,
            Ka_dye=Q_(IDA_TRUE['Ka_dye'], '1/M'),
            h0=Q_(IDA_TRUE['h0'], 'M'),
            d0=Q_(IDA_TRUE['d0'], 'M'),
            **dilution,
        )
    if name == 'GDA':
        return GDAAssay(
            **data,
            Ka_dye=Q_(GDA_TRUE['Ka_dye'], '1/M'),
            h0=Q_(GDA_TRUE['h0'], 'M'),
            g0=Q_(GDA_TRUE['g0'], 'M'),
            **dilution,
        )
    if name in ('DBA_HtoD', 'DBA_DtoH'):
        return DBAAssay(**data, fixed_conc=Q_(DBA_TRUE['fixed_conc'], 'M'), mode=name.split('_')[1], **dilution)
    if name == 'HG2':
        return HG2Assay(**data, h0=Q_(HG2_TRUE['h0'], 'M'), **dilution)
    if name == 'H2G':
        return H2GAssay(**data, h0=Q_(H2G_TRUE['h0'], 'M'), **dilution)
    raise AssertionError(name)


# Assay → the constants to check and the bounds the fit runs under.
EXPECTED = {
    'IDA': (('Ka_guest',), GDA_IDA_RECOVERY_BOUNDS, IDA_TRUE),
    'GDA': (('Ka_guest',), GDA_IDA_RECOVERY_BOUNDS, GDA_TRUE),
    'DBA_HtoD': (('Ka_dye',), DBA_RECOVERY_BOUNDS, DBA_TRUE),
    'DBA_DtoH': (('Ka_dye',), DBA_RECOVERY_BOUNDS, DBA_TRUE),
    'HG2': (('Ka_HG', 'Ka_HG2'), HG2_RECOVERY_BOUNDS, HG2_TRUE),
    'H2G': (('Ka_HG', 'Ka_H2G'), H2G_RECOVERY_BOUNDS, H2G_TRUE),
}

ASSAYS = list(EXPECTED)


def _decades_off(result, key: str, true: dict) -> float:
    return abs(np.log10(result.parameters[key].magnitude) - np.log10(true[key]))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize('name', ASSAYS)
def test_declared_stock_recovers_the_generating_constants(name):
    """With the stock declared the fit solves the same equilibria the data came from."""
    keys, bounds, true = EXPECTED[name]
    x, y, stock = _generate(name)
    assay = _assay(name, x, y, titrant_stock=Q_(stock, 'M'))

    result = fit_assay(assay, FitConfig(custom_bounds=bounds, per_replica=False))

    tolerance = ONE_KA_TOL if len(keys) == 1 else TWO_KA_TOL
    for key in keys:
        assert _decades_off(result, key, true) < tolerance, key


@pytest.mark.parametrize('name', ['IDA', 'GDA', 'DBA_HtoD'])
def test_constant_totals_miss_what_the_declaration_recovers(name):
    """The same data, fitted with and without the stock: only the declaration returns the truth."""
    keys, bounds, true = EXPECTED[name]
    x, y, stock = _generate(name)
    config = FitConfig(custom_bounds=bounds, per_replica=False)

    declared = fit_assay(_assay(name, x, y, titrant_stock=Q_(stock, 'M')), config)
    constant = fit_assay(_assay(name, x, y), config)

    exact = max(_decades_off(declared, keys[0], true), ONE_KA_TOL)
    assert _decades_off(constant, keys[0], true) > BIAS_FACTOR * exact


def test_a_stock_containing_the_dye_leaves_the_dye_alone():
    """A stock made up in the dye solution dilutes the host only, and the fit is told which."""
    x, y, stock = _generate('IDA', dilute_dye=False)
    assay = _assay('IDA', x, y, titrant_stock=Q_(stock, 'M'), stock_contains=('d0',))

    result = fit_assay(assay, FitConfig(custom_bounds=GDA_IDA_RECOVERY_BOUNDS, per_replica=False))

    assert _decades_off(result, 'Ka_guest', IDA_TRUE) < ONE_KA_TOL
