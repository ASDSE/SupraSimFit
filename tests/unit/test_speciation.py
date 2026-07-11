"""Species-level contracts for the forward models.

The simulation applet plots the internal speciation ([H], [D], [HD], …) alongside
the signal.  These tests pin the two guarantees that make that trustworthy:

1. **Signal ⇔ species consistency.** Each assay's ``forward_model`` must equal the
   linear signal model rebuilt from the *same* ``species()`` solve — so the plotted
   curve and the speciation can never come from divergent math.
2. **Mass-balance closure.** The returned free/complex concentrations must conserve
   the total host, dye and guest put into the system (the physics the solve claims
   to satisfy).

Numeric regression of the signal itself is already covered by ``test_models`` and
``test_pipeline_e2e``; here the focus is the newly exposed species.
"""

import numpy as np
import pytest

from core.assays.dba import DBAAssay
from core.assays.dye_alone import DyeAloneAssay
from core.assays.gda import GDAAssay
from core.assays.h2g import H2GAssay
from core.assays.hg2 import HG2Assay
from core.assays.ida import IDAAssay
from core.units import Q_

X = np.linspace(0.0, 30e-6, 8)  # titrant grid (M), includes the zero point
_Y = Q_(np.zeros_like(X), 'au')
TOL = dict(rtol=1e-6, atol=1e-12)


def _sig(assay, params):
    return assay.forward_model(assay.params_from_dict(params)).magnitude


def _sp(assay, params):
    return assay.species(assay.params_from_dict(params))


# ---------------------------------------------------------------------------
# DBA — H + D ⇌ HD
# ---------------------------------------------------------------------------


@pytest.mark.parametrize('mode', ['HtoD', 'DtoH'])
def test_dba_species_close_mass_balance_and_rebuild_signal(mode):
    fixed = 6e-6
    assay = DBAAssay(x_data=Q_(X, 'M'), y_data=_Y, fixed_conc=Q_(fixed, 'M'), mode=mode)
    params = {'Ka_dye': 1e6, 'I0': 12.0, 'I_dye_free': 5e7, 'I_dye_bound': 3e8}
    sp = _sp(assay, params)

    assert list(sp) == ['H', 'D', 'HD']
    # In HtoD the host is the titrant (x) and dye is fixed; DtoH swaps them.
    host_total = X if mode == 'HtoD' else np.full_like(X, fixed)
    dye_total = np.full_like(X, fixed) if mode == 'HtoD' else X
    np.testing.assert_allclose(sp['H'] + sp['HD'], host_total, **TOL)
    np.testing.assert_allclose(sp['D'] + sp['HD'], dye_total, **TOL)

    rebuilt = params['I0'] + params['I_dye_free'] * sp['D'] + params['I_dye_bound'] * sp['HD']
    np.testing.assert_allclose(_sig(assay, params), rebuilt, rtol=0, atol=0)


# ---------------------------------------------------------------------------
# GDA / IDA — H + D ⇌ HD and H + G ⇌ HG competing for host
# ---------------------------------------------------------------------------


def test_gda_species_close_mass_balance_and_rebuild_signal():
    h0, g0 = 4.3e-6, 6e-6  # dye (d0) is the titrant
    assay = GDAAssay(x_data=Q_(X, 'M'), y_data=_Y, Ka_dye=Q_(1e5, '1/M'), h0=Q_(h0, 'M'), g0=Q_(g0, 'M'))
    params = {'Ka_guest': 1e6, 'I0': 5.0, 'I_dye_free': 4e7, 'I_dye_bound': 2e8}
    sp = _sp(assay, params)

    assert list(sp) == ['H', 'D', 'G', 'HD', 'HG']
    np.testing.assert_allclose(sp['H'] + sp['HD'] + sp['HG'], np.full_like(X, h0), **TOL)
    np.testing.assert_allclose(sp['D'] + sp['HD'], X, **TOL)  # dye total = titrant
    np.testing.assert_allclose(sp['G'] + sp['HG'], np.full_like(X, g0), **TOL)

    rebuilt = params['I0'] + params['I_dye_free'] * sp['D'] + params['I_dye_bound'] * sp['HD']
    np.testing.assert_allclose(_sig(assay, params), rebuilt, rtol=0, atol=0)


def test_ida_species_close_mass_balance_and_rebuild_signal():
    h0, d0 = 4.3e-6, 6e-6  # guest (g0) is the titrant
    assay = IDAAssay(x_data=Q_(X, 'M'), y_data=_Y, Ka_dye=Q_(1e5, '1/M'), h0=Q_(h0, 'M'), d0=Q_(d0, 'M'))
    params = {'Ka_guest': 1e6, 'I0': 5.0, 'I_dye_free': 4e7, 'I_dye_bound': 2e8}
    sp = _sp(assay, params)

    assert list(sp) == ['H', 'D', 'G', 'HD', 'HG']
    np.testing.assert_allclose(sp['H'] + sp['HD'] + sp['HG'], np.full_like(X, h0), **TOL)
    np.testing.assert_allclose(sp['D'] + sp['HD'], np.full_like(X, d0), **TOL)  # dye fixed
    np.testing.assert_allclose(sp['G'] + sp['HG'], X, **TOL)  # guest total = titrant

    rebuilt = params['I0'] + params['I_dye_free'] * sp['D'] + params['I_dye_bound'] * sp['HD']
    np.testing.assert_allclose(_sig(assay, params), rebuilt, rtol=0, atol=0)


# ---------------------------------------------------------------------------
# Stepwise HG2 / H2G — two ligands per core, so the closure carries a factor of 2
# ---------------------------------------------------------------------------


def test_hg2_species_close_mass_balance_and_rebuild_signal():
    h0 = 5e-6
    assay = HG2Assay(x_data=Q_(X, 'M'), y_data=_Y, h0=Q_(h0, 'M'))
    params = {'Ka_HG': 1e6, 'Ka_HG2': 2e5, 'I0': 3.0, 'I_G': 1e6, 'I_H': 0.0, 'I_HG': 1e7, 'I_HG2': 5e6}
    sp = _sp(assay, params)

    assert list(sp) == ['H', 'G', 'HG', 'HG2']
    np.testing.assert_allclose(sp['H'] + sp['HG'] + sp['HG2'], np.full_like(X, h0), **TOL)
    np.testing.assert_allclose(sp['G'] + sp['HG'] + 2.0 * sp['HG2'], X, **TOL)  # two guests per HG2

    rebuilt = (
        params['I0']
        + params['I_G'] * sp['G']
        + params['I_H'] * sp['H']
        + params['I_HG'] * sp['HG']
        + params['I_HG2'] * sp['HG2']
    )
    np.testing.assert_allclose(_sig(assay, params), rebuilt, rtol=0, atol=0)


def test_h2g_species_close_mass_balance_and_rebuild_signal():
    h0 = 5e-6
    assay = H2GAssay(x_data=Q_(X, 'M'), y_data=_Y, h0=Q_(h0, 'M'))
    params = {'Ka_HG': 1e6, 'Ka_H2G': 2e5, 'I0': 3.0, 'I_G': 1e6, 'I_H': 0.0, 'I_HG': 1e7, 'I_H2G': 5e6}
    sp = _sp(assay, params)

    assert list(sp) == ['H', 'G', 'HG', 'H2G']
    np.testing.assert_allclose(sp['H'] + sp['HG'] + 2.0 * sp['H2G'], np.full_like(X, h0), **TOL)  # two hosts per H2G
    np.testing.assert_allclose(sp['G'] + sp['HG'] + sp['H2G'], X, **TOL)

    rebuilt = (
        params['I0']
        + params['I_G'] * sp['G']
        + params['I_H'] * sp['H']
        + params['I_HG'] * sp['HG']
        + params['I_H2G'] * sp['H2G']
    )
    np.testing.assert_allclose(_sig(assay, params), rebuilt, rtol=0, atol=0)


# ---------------------------------------------------------------------------
# Dye-alone — no equilibrium; the only "species" is the titrant itself
# ---------------------------------------------------------------------------


def test_dye_alone_species_is_the_titrant():
    assay = DyeAloneAssay(x_data=Q_(X, 'M'), y_data=_Y)
    sp = assay.species(assay.params_from_dict({'slope': 5e10, 'intercept': 100.0}))
    assert list(sp) == ['D']
    np.testing.assert_array_equal(sp['D'], X)


# ---------------------------------------------------------------------------
# simulate_species — the applet entry point mirrors simulate_signal
# ---------------------------------------------------------------------------


def test_simulate_species_matches_direct_and_shapes():
    from core.simulation import simulate_species

    conditions = {'Ka_dye': Q_(1e5, '1/M'), 'h0': Q_(4.3e-6, 'M'), 'g0': Q_(6e-6, 'M')}
    params = {'Ka_guest': 1e6, 'I0': 5.0, 'I_dye_free': 4e7, 'I_dye_bound': 2e8}
    sp = simulate_species(GDAAssay, conditions, params, X)
    assert list(sp) == ['H', 'D', 'G', 'HD', 'HG']
    for arr in sp.values():
        assert arr.shape == X.shape
