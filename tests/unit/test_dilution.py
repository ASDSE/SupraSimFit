"""Fixed totals diluted by the titrant: one code path, one solve, and the refusals.

A sample of volume V0 holding fixed totals c_k receives a cumulative volume W_i
of titrant stock of concentration c_T.  The titrant total in the cuvette is
``x_i = c_T·W_i/(V0+W_i)``, so the dilution fraction is ``phi_i = x_i/c_T`` and a
fixed species the stock does not contain has total ``c_k·(1 - x_i/c_T)`` at point
*i*.  Only the stock concentration is needed; the data file already holds x.

The tests here fix four things: a scalar total takes exactly the arithmetic it
took before per-point totals existed (bit-identical, not merely close); a
per-point solve satisfies the mass balances and the laws of mass action it is
built from; the assay refuses a stock that cannot describe the data; and the
design the fit projects on is the same solve as the curve the app plots.
"""

import numpy as np
import pytest

from core.assays.base import TITRANT
from core.assays.dba import DBAAssay
from core.assays.dye_alone import DyeAloneAssay
from core.assays.gda import GDAAssay
from core.assays.h2g import H2GAssay
from core.assays.hg2 import HG2Assay
from core.assays.ida import IDAAssay
from core.models.equilibrium import dba_species, gda_species, h2g_species, hg2_species, ida_species
from core.pipeline.varpro import Projection
from core.units import Q_
from tests.conftest import (
    DBA_RECOVERY_BOUNDS,
    DBA_TRUE,
    GDA_IDA_RECOVERY_BOUNDS,
    IDA_TRUE,
    _make_dba_data,
    _make_ida_data,
)

# Binding strength relative to the concentration scale, from a system that
# barely binds to one that is saturated long before the first point.  The
# solvers change regime across this range (start point, cancellation form,
# stopping rule), so it is where a second code path would show.
KC = (1e-3, 1.0, 1e3, 1e6, 1e9)

_C = 1e-5  # concentration scale (M) the grids are built on


def _titration(n: int = 7) -> np.ndarray:
    """Titrant grid over the concentration scale, including zero."""
    return np.linspace(0.0, 5 * _C, n)


def _same(a: dict, b: dict) -> None:
    """Every species of two solves is the same array, NaN for NaN."""
    assert a.keys() == b.keys()
    for key in a:
        assert np.array_equal(a[key], b[key], equal_nan=True), key


# ---------------------------------------------------------------------------
# (a) One code path: a scalar total is bit-identical to the constant array
# ---------------------------------------------------------------------------


@pytest.mark.parametrize('kc', KC)
@pytest.mark.parametrize('mode', ['HtoD', 'DtoH'])
def test_dba_scalar_total_matches_constant_array(kc, mode):
    x = _titration()
    ka = kc / _C
    _same(
        dba_species(ka, x, _C, mode=mode),
        dba_species(ka, x, np.full(x.shape, _C), mode=mode),
    )


@pytest.mark.parametrize('kc', KC)
def test_ida_scalar_totals_match_constant_arrays(kc):
    x = _titration()
    ka = kc / _C
    ones = np.full(x.shape, 1.0)
    _same(
        ida_species(ka, ka, _C, 0.5 * _C, x),
        ida_species(ka, ka, _C * ones, 0.5 * _C * ones, x),
    )


@pytest.mark.parametrize('kc', KC)
def test_gda_scalar_totals_match_constant_arrays(kc):
    x = _titration()
    ka = kc / _C
    ones = np.full(x.shape, 1.0)
    _same(
        gda_species(ka, ka, _C, x, 2 * _C),
        gda_species(ka, ka, _C * ones, x, 2 * _C * ones),
    )


@pytest.mark.parametrize('kc', KC)
@pytest.mark.parametrize('solve', [hg2_species, h2g_species])
def test_stepwise_scalar_total_matches_constant_array(kc, solve):
    x = _titration()
    ka = kc / _C
    _same(
        solve(ka, 0.2 * ka, _C, x),
        solve(ka, 0.2 * ka, np.full(x.shape, _C), x),
    )


# ---------------------------------------------------------------------------
# (b) A diluted solve satisfies the balances and the mass-action laws
# ---------------------------------------------------------------------------

_BALANCE_RTOL = 1e-12
_ACTION_RTOL = 1e-9


def _diluted(total: float, x: np.ndarray, stock: float) -> np.ndarray:
    """Total of a fixed species the stock does not contain, per titration point."""
    return total * (1.0 - x / stock)


def test_ida_diluted_solve_closes_per_point():
    x = np.linspace(1e-7, 50e-6, 25)
    stock = 5e-4  # 10 % final dilution
    h0, d0 = _diluted(10e-6, x, stock), _diluted(5e-6, x, stock)
    kd, kg = 5e5, 2e6

    sp = ida_species(kg, kd, h0, d0, x)

    np.testing.assert_allclose(sp['H'] + sp['HD'] + sp['HG'], h0, rtol=_BALANCE_RTOL)
    np.testing.assert_allclose(sp['D'] + sp['HD'], d0, rtol=_BALANCE_RTOL)
    np.testing.assert_allclose(sp['G'] + sp['HG'], x, rtol=_BALANCE_RTOL)
    np.testing.assert_allclose(sp['HD'], kd * sp['H'] * sp['D'], rtol=_ACTION_RTOL)
    np.testing.assert_allclose(sp['HG'], kg * sp['H'] * sp['G'], rtol=_ACTION_RTOL)


def test_dba_diluted_solve_closes_per_point():
    x = np.linspace(1e-7, 50e-6, 25)
    stock = 5e-4
    h0 = _diluted(10e-6, x, stock)
    ka = 5e5

    sp = dba_species(ka, x, h0, mode='DtoH')

    np.testing.assert_allclose(sp['H'] + sp['HD'], h0, rtol=_BALANCE_RTOL)
    np.testing.assert_allclose(sp['D'] + sp['HD'], x, rtol=_BALANCE_RTOL)
    np.testing.assert_allclose(sp['HD'], ka * sp['H'] * sp['D'], rtol=_ACTION_RTOL)


def test_hg2_diluted_solve_closes_per_point():
    x = np.linspace(1e-7, 1.2e-3, 25)
    stock = 1.2e-2
    h0 = _diluted(3e-4, x, stock)
    k1, k2 = 1e6, 2e5

    sp = hg2_species(k1, k2, h0, x)

    np.testing.assert_allclose(sp['H'] + sp['HG'] + sp['HG2'], h0, rtol=_BALANCE_RTOL)
    np.testing.assert_allclose(sp['G'] + sp['HG'] + 2.0 * sp['HG2'], x, rtol=_BALANCE_RTOL)
    np.testing.assert_allclose(sp['HG'], k1 * sp['H'] * sp['G'], rtol=_ACTION_RTOL)
    np.testing.assert_allclose(sp['HG2'], k2 * sp['HG'] * sp['G'], rtol=_ACTION_RTOL)


# ---------------------------------------------------------------------------
# Assay fixtures
# ---------------------------------------------------------------------------

_X = np.linspace(0.0, 50e-6, 20)
_Y = np.linspace(1000.0, 200.0, 20)
_STOCK = 5e-4  # 10 % final dilution on _X


def _ida(**kwargs) -> IDAAssay:
    return IDAAssay(
        x_data=Q_(_X, 'M'),
        y_data=Q_(_Y, 'au'),
        Ka_dye=Q_(5e5, '1/M'),
        h0=Q_(10e-6, 'M'),
        d0=Q_(5e-6, 'M'),
        **kwargs,
    )


def _gda(**kwargs) -> GDAAssay:
    return GDAAssay(
        x_data=Q_(_X, 'M'),
        y_data=Q_(_Y, 'au'),
        Ka_dye=Q_(5e5, '1/M'),
        h0=Q_(10e-6, 'M'),
        g0=Q_(20e-6, 'M'),
        **kwargs,
    )


def _dba(**kwargs) -> DBAAssay:
    return DBAAssay(x_data=Q_(_X, 'M'), y_data=Q_(_Y, 'au'), fixed_conc=Q_(10e-6, 'M'), mode='DtoH', **kwargs)


def _hg2(**kwargs) -> HG2Assay:
    return HG2Assay(x_data=Q_(_X, 'M'), y_data=Q_(_Y, 'au'), h0=Q_(3e-4, 'M'), **kwargs)


def _h2g(**kwargs) -> H2GAssay:
    return H2GAssay(x_data=Q_(_X, 'M'), y_data=Q_(_Y, 'au'), h0=Q_(3e-4, 'M'), **kwargs)


def _dye_alone(**kwargs) -> DyeAloneAssay:
    return DyeAloneAssay(x_data=Q_(_X, 'M'), y_data=Q_(_Y, 'au'), **kwargs)


BUILDERS = {
    'IDA': (_ida, {'Ka_dye', 'h0', 'd0'}),
    'GDA': (_gda, {'Ka_dye', 'h0', 'g0'}),
    'DBA': (_dba, {'fixed_conc', 'mode'}),
    'HG2': (_hg2, {'h0'}),
    'H2G': (_h2g, {'h0'}),
    'DYE_ALONE': (_dye_alone, set()),
}


# ---------------------------------------------------------------------------
# (c) fixed_total
# ---------------------------------------------------------------------------


def test_fixed_total_without_a_stock_is_the_entered_float():
    assay = _ida()
    assert assay.fixed_total('h0', _X) == 10e-6
    assert isinstance(assay.fixed_total('h0', _X), float)


def test_fixed_total_of_a_contained_species_is_the_entered_float():
    assay = _ida(titrant_stock=Q_(_STOCK, 'M'), stock_contains=('d0',))
    assert assay.fixed_total('d0', _X) == 5e-6
    assert isinstance(assay.fixed_total('d0', _X), float)


def test_fixed_total_with_a_stock_dilutes_elementwise():
    assay = _ida(titrant_stock=Q_(_STOCK, 'M'))
    np.testing.assert_array_equal(assay.fixed_total('h0', _X), 10e-6 * (1.0 - _X / _STOCK))
    np.testing.assert_array_equal(assay.fixed_total('d0', _X), 5e-6 * (1.0 - _X / _STOCK))


def test_fixed_total_follows_the_grid_it_is_asked_for():
    """A denser display grid dilutes on its own points, not on the data's."""
    assay = _ida(titrant_stock=Q_(_STOCK, 'M'))
    grid = np.linspace(0.0, 50e-6, 97)
    np.testing.assert_array_equal(assay.fixed_total('h0', grid), 10e-6 * (1.0 - grid / _STOCK))


# ---------------------------------------------------------------------------
# (d) Conditions round-trip
# ---------------------------------------------------------------------------


@pytest.mark.parametrize('name', list(BUILDERS))
def test_conditions_gain_nothing_without_a_stock(name):
    build, keys = BUILDERS[name]
    assert set(build().get_conditions()) == keys


@pytest.mark.parametrize('name', ['IDA', 'GDA', 'DBA', 'HG2', 'H2G'])
def test_conditions_gain_the_two_dilution_keys_with_a_stock(name):
    build, keys = BUILDERS[name]
    conditions = build(titrant_stock=Q_(_STOCK, 'M'), stock_contains=()).get_conditions()
    assert set(conditions) == keys | {'titrant_stock', 'stock_contains'}
    assert conditions['titrant_stock'] == Q_(_STOCK, 'M')
    assert conditions['stock_contains'] == ()


@pytest.mark.parametrize('name', ['IDA', 'GDA', 'DBA', 'HG2', 'H2G'])
def test_assay_rebuilds_from_its_own_conditions(name):
    build, _ = BUILDERS[name]
    assay = build(titrant_stock=Q_(_STOCK, 'M'))
    rebuilt = type(assay)(x_data=assay.x_data, y_data=assay.y_data, **assay.get_conditions())

    assert rebuilt.get_conditions() == assay.get_conditions()
    np.testing.assert_array_equal(rebuilt.x_data.magnitude, assay.x_data.magnitude)
    np.testing.assert_array_equal(rebuilt.y_data.magnitude, assay.y_data.magnitude)


def test_stock_contains_from_json_is_a_tuple():
    """A results file stores the contents as a JSON list; the assay makes it a tuple."""
    assay = _ida(titrant_stock=Q_(_STOCK, 'M'), stock_contains=['d0'])
    assert assay.stock_contains == ('d0',)
    assert assay.get_conditions()['stock_contains'] == ('d0',)

    rebuilt = IDAAssay(x_data=assay.x_data, y_data=assay.y_data, **assay.get_conditions())
    assert rebuilt.get_conditions() == assay.get_conditions()


# ---------------------------------------------------------------------------
# (e) Refusals
# ---------------------------------------------------------------------------


def test_refuses_a_stock_that_is_not_positive():
    with pytest.raises(ValueError) as err:
        _ida(titrant_stock=Q_(0.0, 'M'))
    assert 'titrant stock' in str(err.value)
    assert '0 M' in str(err.value)


def test_refuses_a_stock_weaker_than_the_data():
    with pytest.raises(ValueError) as err:
        _ida(titrant_stock=Q_(10e-6, 'M'))
    message = str(err.value)
    assert '1×10⁻⁵ M' in message  # the stock
    assert '5×10⁻⁵ M' in message  # the highest titrant concentration in the data
    assert 'titrant stock' in message


def test_refuses_contents_that_are_not_a_concentration_of_the_assay():
    with pytest.raises(ValueError) as err:
        _ida(titrant_stock=Q_(_STOCK, 'M'), stock_contains=('Ka_dye',))
    assert 'Ka_dye' in str(err.value)


def test_refuses_contents_the_assay_does_not_have():
    with pytest.raises(ValueError) as err:
        _ida(titrant_stock=Q_(_STOCK, 'M'), stock_contains=('g0',))
    assert 'g0' in str(err.value)


def test_refuses_a_stock_that_contains_every_fixed_concentration():
    with pytest.raises(ValueError) as err:
        _ida(titrant_stock=Q_(_STOCK, 'M'), stock_contains=('h0', 'd0'))
    message = str(err.value)
    assert 'h0' in message and 'd0' in message
    assert 'stay constant' in message


def test_refuses_contents_without_a_stock():
    with pytest.raises(ValueError) as err:
        _ida(stock_contains=('d0',))
    assert 'd0' in str(err.value)
    assert 'titrant stock' in str(err.value)


def test_refuses_a_stock_on_an_assay_with_no_fixed_concentration():
    with pytest.raises(ValueError) as err:
        _dye_alone(titrant_stock=Q_(_STOCK, 'M'))
    assert 'DYE_ALONE' in str(err.value)


def test_a_one_concentration_assay_refuses_its_only_concentration_as_contents():
    with pytest.raises(ValueError) as err:
        _dba(titrant_stock=Q_(_STOCK, 'M'), stock_contains=('fixed_conc',))
    assert 'stay constant' in str(err.value)


# ---------------------------------------------------------------------------
# (f) with_inputs
# ---------------------------------------------------------------------------


def test_titrant_offset_scales_the_stock_and_leaves_the_dilution_alone():
    """x and c_T carry the same scale error, so phi = x/c_T — a ratio of volumes — does not move."""
    assay = _ida(titrant_stock=Q_(_STOCK, 'M'))
    moved = assay.with_inputs({TITRANT: 0.03})

    np.testing.assert_allclose(moved.x_data.magnitude, 1.03 * _X, rtol=1e-15)
    assert moved.titrant_stock.magnitude == pytest.approx(1.03 * _STOCK, rel=1e-15)
    for key in ('h0', 'd0'):
        np.testing.assert_allclose(
            moved.fixed_total(key, moved.x_data.magnitude),
            assay.fixed_total(key, _X),
            rtol=1e-15,
        )


def test_the_stock_is_not_an_input_of_its_own():
    assay = _ida(titrant_stock=Q_(_STOCK, 'M'))
    with pytest.raises(ValueError) as err:
        assay.with_inputs({'titrant_stock': 0.03})
    assert 'titrant_stock' in str(err.value)


# ---------------------------------------------------------------------------
# (g) Homogeneity with dilution declared
# ---------------------------------------------------------------------------


@pytest.mark.parametrize('c', [0.5, 2.0])
def test_ida_species_are_homogeneous_with_dilution(c):
    assay = _ida(titrant_stock=Q_(_STOCK, 'M'))
    scaled = IDAAssay(
        x_data=Q_(_X * c, 'M'),
        y_data=Q_(_Y, 'au'),
        Ka_dye=Q_(5e5 / c, '1/M'),
        h0=Q_(10e-6 * c, 'M'),
        d0=Q_(5e-6 * c, 'M'),
        titrant_stock=Q_(_STOCK * c, 'M'),
    )
    base = assay.species(np.array([2e6, 0.0, 0.0, 0.0]))
    moved = scaled.species(np.array([2e6 / c, 0.0, 0.0, 0.0]))
    for key in base:
        np.testing.assert_allclose(moved[key], c * base[key], rtol=1e-12)


@pytest.mark.parametrize('c', [0.5, 2.0])
def test_hg2_species_are_homogeneous_with_dilution(c):
    assay = _hg2(titrant_stock=Q_(_STOCK, 'M'))
    scaled = HG2Assay(
        x_data=Q_(_X * c, 'M'),
        y_data=Q_(_Y, 'au'),
        h0=Q_(3e-4 * c, 'M'),
        titrant_stock=Q_(_STOCK * c, 'M'),
    )
    base = assay.species(np.array([1e6, 2e5, 0.0, 0.0, 0.0, 0.0, 0.0]))
    moved = scaled.species(np.array([1e6 / c, 2e5 / c, 0.0, 0.0, 0.0, 0.0, 0.0]))
    for key in base:
        np.testing.assert_allclose(moved[key], c * base[key], rtol=1e-12)


# ---------------------------------------------------------------------------
# (h) The fit's design and the plotted model are one solve
# ---------------------------------------------------------------------------


def _residual_agrees(assay, bounds) -> None:
    projection = Projection(assay, bounds)
    fit = projection.fit()
    params = projection.params(fit)
    direct = (assay.y_data - assay.forward_model(params)).magnitude
    span = float(np.ptp(assay.y_data.magnitude))
    np.testing.assert_allclose(projection.residual(fit.ka), direct, atol=1e-12 * span, rtol=0)


def test_ida_projection_residual_is_the_model_residual_with_dilution():
    x, y = _make_ida_data(IDA_TRUE)
    assay = IDAAssay(
        x_data=Q_(x, 'M'),
        y_data=Q_(y, 'au'),
        Ka_dye=Q_(IDA_TRUE['Ka_dye'], '1/M'),
        h0=Q_(IDA_TRUE['h0'], 'M'),
        d0=Q_(IDA_TRUE['d0'], 'M'),
        titrant_stock=Q_(float(x.max()) / 0.1, 'M'),
    )
    _residual_agrees(assay, GDA_IDA_RECOVERY_BOUNDS)


def test_dba_projection_residual_is_the_model_residual_with_dilution():
    x, y = _make_dba_data(DBA_TRUE)
    assay = DBAAssay(
        x_data=Q_(x, 'M'),
        y_data=Q_(y, 'au'),
        fixed_conc=Q_(DBA_TRUE['fixed_conc'], 'M'),
        mode='DtoH',
        titrant_stock=Q_(float(x.max()) / 0.1, 'M'),
    )
    _residual_agrees(assay, DBA_RECOVERY_BOUNDS)
