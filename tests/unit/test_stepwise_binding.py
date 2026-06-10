"""Forward-model and mass-balance solver tests for the stepwise 1:2 / 2:1
host-guest binding models (HG2 and H2G).

The models solve the speciation with Brent's method on a monotonic mass
balance.  These tests validate that algebra against *independent* references:

- a full 4-species ``fsolve`` of the coupled equilibria (a different solver),
- conservation laws written with explicit stoichiometry (catches a wrong
  factor of two on the doubly-bound complex),
- the limiting case where the second step is switched off, which must
  collapse onto the already-validated 1:1 DBA model,
- closed-form behaviour at zero titrant.
"""

import numpy as np
import pytest
from scipy.optimize import fsolve

from core.models.equilibrium import (
    dba_signal,
    h2g_signal,
    h2g_species,
    hg2_signal,
    hg2_species,
)

# Representative signal coefficients (a.u. and a.u./M) giving signals of
# order hundreds–thousands at µM–sub-mM concentrations.
COEFFS = dict(I0=25.0, I_G=1.0e6, I_H=0.0, I_HG=1.0e7, I_HG2=5.0e6)


class TestHG2MassBalance:
    """The 1:2 speciation must conserve both total host and total guest."""

    def test_conservation_across_titration(self):
        Ka_HG, Ka_HG2, h0 = 1.0e6, 2.0e5, 3.0e-4
        g0 = np.linspace(1e-6, 1.2e-3, 25)
        sp = hg2_species(Ka_HG, Ka_HG2, h0, g0)

        host_total = sp['H'] + sp['HG'] + sp['HG2']
        # Two guests are sequestered per HG2 — the factor of two is the point.
        guest_total = sp['G'] + sp['HG'] + 2.0 * sp['HG2']

        np.testing.assert_allclose(host_total, h0, rtol=1e-9)
        np.testing.assert_allclose(guest_total, g0, rtol=1e-7)

    def test_matches_independent_full_system(self):
        """Brent speciation agrees with an fsolve of the coupled equilibria.

        Solved in µM units for conditioning; the four unknowns are the free
        and bound species, constrained by two mass balances and the two
        stepwise association definitions.
        """
        Ka_HG, Ka_HG2, h0, g0 = 1.0e6, 2.0e5, 3.0e-4, 4.0e-4
        k1, k2 = Ka_HG * 1e-6, Ka_HG2 * 1e-6  # 1/µM
        h0u, g0u = h0 * 1e6, g0 * 1e6

        def equations(v):
            H, G, HG, HG2 = v
            return [
                H + HG + HG2 - h0u,
                G + HG + 2.0 * HG2 - g0u,
                HG - k1 * H * G,
                HG2 - k2 * HG * G,
            ]

        sol, _, ier, msg = fsolve(equations, [h0u / 2, g0u / 2, h0u / 4, h0u / 8], full_output=True, xtol=1e-13)
        assert ier == 1, f'independent solver failed: {msg}'
        H_u, G_u, HG_u, HG2_u = sol

        sp = hg2_species(Ka_HG, Ka_HG2, h0, np.array([g0]))
        assert sp['H'][0] == pytest.approx(H_u * 1e-6, rel=1e-6)
        assert sp['G'][0] == pytest.approx(G_u * 1e-6, rel=1e-6)
        assert sp['HG'][0] == pytest.approx(HG_u * 1e-6, rel=1e-6)
        assert sp['HG2'][0] == pytest.approx(HG2_u * 1e-6, rel=1e-6)


class TestH2GMassBalance:
    """The 2:1 speciation must conserve both totals, now with two hosts per
    H2G complex."""

    def test_conservation_across_titration(self):
        Ka_HG, Ka_H2G, h0 = 1.0e6, 2.0e5, 3.0e-4
        g0 = np.linspace(1e-6, 6e-4, 25)
        sp = h2g_species(Ka_HG, Ka_H2G, h0, g0)

        # Two hosts are sequestered per H2G.
        host_total = sp['H'] + sp['HG'] + 2.0 * sp['H2G']
        guest_total = sp['G'] + sp['HG'] + sp['H2G']

        np.testing.assert_allclose(host_total, h0, rtol=1e-7)
        np.testing.assert_allclose(guest_total, g0, rtol=1e-9)

    def test_matches_independent_full_system(self):
        Ka_HG, Ka_H2G, h0, g0 = 1.0e6, 2.0e5, 4.0e-4, 1.0e-4
        k1, k2 = Ka_HG * 1e-6, Ka_H2G * 1e-6
        h0u, g0u = h0 * 1e6, g0 * 1e6

        def equations(v):
            H, G, HG, H2G = v
            return [
                H + HG + 2.0 * H2G - h0u,
                G + HG + H2G - g0u,
                HG - k1 * H * G,
                H2G - k2 * HG * H,
            ]

        sol, _, ier, msg = fsolve(equations, [h0u / 2, g0u / 2, g0u / 4, g0u / 8], full_output=True, xtol=1e-13)
        assert ier == 1, f'independent solver failed: {msg}'
        H_u, G_u, HG_u, H2G_u = sol

        sp = h2g_species(Ka_HG, Ka_H2G, h0, np.array([g0]))
        assert sp['H'][0] == pytest.approx(H_u * 1e-6, rel=1e-6)
        assert sp['G'][0] == pytest.approx(G_u * 1e-6, rel=1e-6)
        assert sp['HG'][0] == pytest.approx(HG_u * 1e-6, rel=1e-6)
        assert sp['H2G'][0] == pytest.approx(H2G_u * 1e-6, rel=1e-6)


class TestReducesToDBA:
    """With the second step switched off, both models collapse onto the
    validated 1:1 direct-binding model (dye titrated into fixed host)."""

    def test_hg2_second_step_off_matches_dba(self):
        Ka, h0 = 5.0e5, 1.0e-5
        g0 = np.linspace(1e-7, 5e-5, 20)

        hg2 = hg2_signal(
            I0=COEFFS['I0'], Ka_HG=Ka, Ka_HG2=0.0, I_G=COEFFS['I_G'], I_H=0.0, I_HG=COEFFS['I_HG'], I_HG2=1.0e9, h0=h0, g0_values=g0
        )
        dba = dba_signal(
            I0=COEFFS['I0'], Ka_dye=Ka, I_dye_free=COEFFS['I_G'], I_dye_bound=COEFFS['I_HG'], x_titrant=g0, y_fixed=h0, mode='DtoH'
        )
        np.testing.assert_allclose(hg2, dba, rtol=1e-6)

    def test_h2g_second_step_off_matches_dba(self):
        Ka, h0 = 5.0e5, 1.0e-5
        g0 = np.linspace(1e-7, 5e-5, 20)

        h2g = h2g_signal(
            I0=COEFFS['I0'], Ka_HG=Ka, Ka_H2G=0.0, I_G=COEFFS['I_G'], I_H=0.0, I_HG=COEFFS['I_HG'], I_H2G=1.0e9, h0=h0, g0_values=g0
        )
        dba = dba_signal(
            I0=COEFFS['I0'], Ka_dye=Ka, I_dye_free=COEFFS['I_G'], I_dye_bound=COEFFS['I_HG'], x_titrant=g0, y_fixed=h0, mode='DtoH'
        )
        np.testing.assert_allclose(h2g, dba, rtol=1e-6)


class TestZeroGuestBaseline:
    """At zero titrant all guest-bearing species vanish and the host is fully
    free, so the signal is the closed-form baseline I0 + I_H·h0."""

    def test_hg2_zero_guest(self):
        h0 = 2.0e-4
        sig = hg2_signal(I0=25.0, Ka_HG=1e6, Ka_HG2=2e5, I_G=1e6, I_H=3.0e5, I_HG=1e7, I_HG2=5e6, h0=h0, g0_values=np.array([0.0]))
        assert sig[0] == pytest.approx(25.0 + 3.0e5 * h0, rel=1e-12)

    def test_h2g_zero_guest(self):
        h0 = 2.0e-4
        sig = h2g_signal(I0=25.0, Ka_HG=1e6, Ka_H2G=2e5, I_G=1e6, I_H=3.0e5, I_HG=1e7, I_H2G=5e6, h0=h0, g0_values=np.array([0.0]))
        assert sig[0] == pytest.approx(25.0 + 3.0e5 * h0, rel=1e-12)


class TestSolverRobustness:
    """The Brent speciation must stay finite and physical across a wide range
    of association-constant magnitudes (guards bracket-collapse failures)."""

    @pytest.mark.parametrize('Ka1, Ka2', [(1.0, 1.0), (1e8, 1.0), (1.0, 1e8), (1e8, 1e8), (1e6, 2e5)])
    def test_hg2_species_physical(self, Ka1, Ka2):
        h0 = 3.0e-4
        g0 = np.linspace(1e-6, 1e-3, 15)
        sp = hg2_species(Ka1, Ka2, h0, g0)
        for key in ('H', 'G', 'HG', 'HG2'):
            assert np.all(np.isfinite(sp[key])), f'non-finite {key} at Ka1={Ka1:g}, Ka2={Ka2:g}'
            assert np.all(sp[key] >= -1e-18), f'negative {key} at Ka1={Ka1:g}, Ka2={Ka2:g}'
        np.testing.assert_allclose(sp['H'] + sp['HG'] + sp['HG2'], h0, rtol=1e-6)

    @pytest.mark.parametrize('Ka1, Ka2', [(1.0, 1.0), (1e8, 1.0), (1.0, 1e8), (1e8, 1e8), (1e6, 2e5)])
    def test_h2g_species_physical(self, Ka1, Ka2):
        h0 = 3.0e-4
        g0 = np.linspace(1e-6, 1e-3, 15)
        sp = h2g_species(Ka1, Ka2, h0, g0)
        for key in ('H', 'G', 'HG', 'H2G'):
            assert np.all(np.isfinite(sp[key])), f'non-finite {key} at Ka1={Ka1:g}, Ka2={Ka2:g}'
            assert np.all(sp[key] >= -1e-18), f'negative {key} at Ka1={Ka1:g}, Ka2={Ka2:g}'
        np.testing.assert_allclose(sp['G'] + sp['HG'] + sp['H2G'], g0, rtol=1e-6)
