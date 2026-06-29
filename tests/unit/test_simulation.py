"""Tests for the forward-simulation core (``core.simulation``).

Scientific contract: a simulation must reproduce the *exact* forward-model math the
fitter uses (no divergent re-implementation), for every assay type — including the
linear DYE_ALONE assay whose ``forward_model`` has a different signature.
"""

import numpy as np
import pytest

from core.assays import DBAAssay, DyeAloneAssay, GDAAssay, H2GAssay, HG2Assay, IDAAssay
from core.models.equilibrium import dba_signal, gda_signal, h2g_signal, hg2_signal, ida_signal
from core.models.linear import linear_signal
from core.simulation import build_concentration_vector, simulate_dataset, simulate_signal
from core.units import Q_
from tests.conftest import DBA_TRUE, DYE_ALONE_TRUE, GDA_TRUE, H2G_TRUE, HG2_TRUE, IDA_TRUE

# ---------------------------------------------------------------------------
# Each case: (assay_cls, conditions (Quantities), parameters, x_vector, expected y)
# `expected` is computed from the canonical model function directly, so equality
# proves the simulation reuses the same math.
# ---------------------------------------------------------------------------


def _gda_case():
    x = np.linspace(1e-7, 30e-6, 25)
    t = GDA_TRUE
    expected = gda_signal(
        I0=t['I0'],
        Ka_guest=t['Ka_guest'],
        I_dye_free=t['I_dye_free'],
        I_dye_bound=t['I_dye_bound'],
        Ka_dye=t['Ka_dye'],
        h0=t['h0'],
        d0_values=x,
        g0=t['g0'],
    )
    conditions = {'Ka_dye': Q_(t['Ka_dye'], '1/M'), 'h0': Q_(t['h0'], 'M'), 'g0': Q_(t['g0'], 'M')}
    params = {'Ka_guest': t['Ka_guest'], 'I0': t['I0'], 'I_dye_free': t['I_dye_free'], 'I_dye_bound': t['I_dye_bound']}
    return GDAAssay, conditions, params, x, expected


def _ida_case():
    x = np.linspace(0, 50e-6, 25)
    t = IDA_TRUE
    expected = ida_signal(
        I0=t['I0'],
        Ka_guest=t['Ka_guest'],
        I_dye_free=t['I_dye_free'],
        I_dye_bound=t['I_dye_bound'],
        Ka_dye=t['Ka_dye'],
        h0=t['h0'],
        d0=t['d0'],
        g0_values=x,
    )
    conditions = {'Ka_dye': Q_(t['Ka_dye'], '1/M'), 'h0': Q_(t['h0'], 'M'), 'd0': Q_(t['d0'], 'M')}
    params = {'Ka_guest': t['Ka_guest'], 'I0': t['I0'], 'I_dye_free': t['I_dye_free'], 'I_dye_bound': t['I_dye_bound']}
    return IDAAssay, conditions, params, x, expected


def _dba_case(mode):
    x = np.linspace(1e-7, 50e-6, 25)
    t = DBA_TRUE
    expected = dba_signal(
        I0=t['I0'],
        Ka_dye=t['Ka_dye'],
        I_dye_free=t['I_dye_free'],
        I_dye_bound=t['I_dye_bound'],
        x_titrant=x,
        y_fixed=t['fixed_conc'],
        mode=mode,
    )
    conditions = {'fixed_conc': Q_(t['fixed_conc'], 'M'), 'mode': mode}
    params = {'Ka_dye': t['Ka_dye'], 'I0': t['I0'], 'I_dye_free': t['I_dye_free'], 'I_dye_bound': t['I_dye_bound']}
    return DBAAssay, conditions, params, x, expected


def _hg2_case():
    x = np.linspace(0, 1.2e-3, 25)
    t = HG2_TRUE
    expected = hg2_signal(
        I0=t['I0'],
        Ka_HG=t['Ka_HG'],
        Ka_HG2=t['Ka_HG2'],
        I_G=t['I_G'],
        I_H=t['I_H'],
        I_HG=t['I_HG'],
        I_HG2=t['I_HG2'],
        h0=t['h0'],
        g0_values=x,
    )
    conditions = {'h0': Q_(t['h0'], 'M')}
    params = {k: t[k] for k in ('Ka_HG', 'Ka_HG2', 'I0', 'I_G', 'I_H', 'I_HG', 'I_HG2')}
    return HG2Assay, conditions, params, x, expected


def _h2g_case():
    x = np.linspace(0, 6e-4, 25)
    t = H2G_TRUE
    expected = h2g_signal(
        I0=t['I0'],
        Ka_HG=t['Ka_HG'],
        Ka_H2G=t['Ka_H2G'],
        I_G=t['I_G'],
        I_H=t['I_H'],
        I_HG=t['I_HG'],
        I_H2G=t['I_H2G'],
        h0=t['h0'],
        g0_values=x,
    )
    conditions = {'h0': Q_(t['h0'], 'M')}
    params = {k: t[k] for k in ('Ka_HG', 'Ka_H2G', 'I0', 'I_G', 'I_H', 'I_HG', 'I_H2G')}
    return H2GAssay, conditions, params, x, expected


def _dye_alone_case():
    x = np.linspace(0, 20e-6, 25)
    t = DYE_ALONE_TRUE
    expected = linear_signal(t['slope'], t['intercept'], x)
    return DyeAloneAssay, {}, {'slope': t['slope'], 'intercept': t['intercept']}, x, expected


ALL_CASES = {
    'GDA': _gda_case(),
    'IDA': _ida_case(),
    'DBA_DtoH': _dba_case('DtoH'),
    'DBA_HtoD': _dba_case('HtoD'),
    'HG2': _hg2_case(),
    'H2G': _h2g_case(),
    'DYE_ALONE': _dye_alone_case(),
}


@pytest.mark.parametrize('name', list(ALL_CASES))
def test_simulate_signal_matches_forward_model(name):
    """simulate_signal reproduces the canonical model math exactly, for every assay."""
    assay_cls, conditions, params, x, expected = ALL_CASES[name]
    got = simulate_signal(assay_cls, conditions, params, x)
    assert got.shape == x.shape
    np.testing.assert_allclose(got, np.asarray(expected, dtype=float), rtol=1e-9, atol=0)


def test_dye_alone_is_exact_line():
    """DYE_ALONE (no-`x` forward_model) is the closed-form slope*x + intercept."""
    x = np.linspace(0, 1e-4, 11)
    got = simulate_signal(DyeAloneAssay, {}, {'slope': 5e10, 'intercept': 100.0}, x)
    np.testing.assert_allclose(got, 5e10 * x + 100.0, rtol=1e-12)


# ---------------------------------------------------------------------------
# build_concentration_vector
# ---------------------------------------------------------------------------


def test_linear_mode_is_uniformly_spaced():
    v = build_concentration_vector('linear', start=0.0, stop=1e-4, n=11)
    assert (v[0], v[-1], len(v)) == (0.0, 1e-4, 11)
    diffs = np.diff(v)
    assert np.allclose(diffs, diffs[0])  # uniform spacing


def test_step_mode_has_constant_step():
    v = build_concentration_vector('step', start=1e-6, step=2e-6, n=5)
    assert v[0] == 1e-6 and len(v) == 5
    assert np.allclose(np.diff(v), 2e-6)


def test_log_mode_is_geometrically_spaced():
    v = build_concentration_vector('log', start=1e-8, stop=1e-4, n=9)
    assert (v[0], v[-1], len(v)) == (1e-8, 1e-4, 9)
    ratios = v[1:] / v[:-1]
    assert np.allclose(ratios, ratios[0])  # constant ratio = geometric


def test_explicit_mode_preserves_values():
    v = build_concentration_vector('explicit', values=[0.0, 3e-6, 1e-5])
    np.testing.assert_array_equal(v, [0.0, 3e-6, 1e-5])


@pytest.mark.parametrize(
    'mode,kwargs',
    [
        ('linear', dict(start=-1e-6, stop=1e-5, n=5)),  # negative start
        ('step', dict(start=-2e-6, step=1e-6, n=2)),  # produces negatives
        ('explicit', dict(values=[1e-6, -2e-6])),  # explicit negative
    ],
)
def test_rejects_negative_concentrations(mode, kwargs):
    with pytest.raises(ValueError, match='negative'):
        build_concentration_vector(mode, **kwargs)


@pytest.mark.parametrize(
    'mode,kwargs',
    [
        ('linear', dict(start=1e-5, stop=1e-5, n=5)),  # stop == start
        ('linear', dict(start=0.0, stop=1e-4, n=1)),  # n < 2
        ('step', dict(start=0.0, step=0.0, n=5)),  # non-positive step
        ('log', dict(start=0.0, stop=1e-4, n=5)),  # log start <= 0
        ('explicit', dict(values=[])),  # empty
        ('bogus', dict()),  # unknown mode
    ],
)
def test_invalid_specs_raise(mode, kwargs):
    with pytest.raises(ValueError):
        build_concentration_vector(mode, **kwargs)


# ---------------------------------------------------------------------------
# simulate_dataset
# ---------------------------------------------------------------------------


def test_dataset_shapes_and_clean():
    assay_cls, conditions, params, x, expected = ALL_CASES['IDA']
    ms = simulate_dataset(assay_cls, conditions, params, x, n_replicas=3)
    assert ms.signals.shape == (3, x.size)
    assert ms.concentrations.shape == x.shape
    # No noise → every replica equals the clean signal.
    for row in ms.signals:
        np.testing.assert_allclose(row, np.asarray(expected, dtype=float), rtol=1e-9)


def test_noise_is_seed_reproducible_and_scaled():
    assay_cls, conditions, params, x, expected = ALL_CASES['IDA']
    a = simulate_dataset(assay_cls, conditions, params, x, noise_frac=0.05, n_replicas=4, rng=np.random.default_rng(7))
    b = simulate_dataset(assay_cls, conditions, params, x, noise_frac=0.05, n_replicas=4, rng=np.random.default_rng(7))
    np.testing.assert_array_equal(a.signals, b.signals)
    # Different seed → different draw.
    c = simulate_dataset(assay_cls, conditions, params, x, noise_frac=0.05, n_replicas=4, rng=np.random.default_rng(8))
    assert not np.array_equal(a.signals, c.signals)
    # Residual scatter scales roughly with noise_frac * signal span.
    clean = np.asarray(expected, dtype=float)
    span = clean.max() - clean.min()
    resid_sd = np.std(a.signals - clean)
    assert 0.2 * 0.05 * span < resid_sd < 5 * 0.05 * span


def test_dataset_roundtrips_through_writer(tmp_path):
    """Exported simulated data re-loads to a MeasurementSet of the same shape/values."""
    from core.data_processing.measurement_set import MeasurementSet
    from core.io import load_measurements
    from core.io.formats.measurement_writer import write_measurements_txt

    assay_cls, conditions, params, x, _ = ALL_CASES['GDA']
    ms = simulate_dataset(assay_cls, conditions, params, x, n_replicas=2)
    path = tmp_path / 'sim.txt'
    write_measurements_txt(ms, path)

    df = load_measurements(str(path))
    reloaded = MeasurementSet.from_dataframe(df)
    assert reloaded.signals.shape == ms.signals.shape
    np.testing.assert_allclose(reloaded.concentrations, ms.concentrations, rtol=1e-5)
    np.testing.assert_allclose(np.sort(reloaded.signals, axis=0), np.sort(ms.signals, axis=0), rtol=1e-5)
