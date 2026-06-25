"""Regression: a reloaded Median Fit curve must match the originally drawn one.

The smooth fit line is fully determined by the fitted parameters, the assay
conditions, the assay type, and the data x-range.  Older exports (and the
linear / failed-fit paths) serialised ``x_fit``/``y_fit`` only at the measured
concentrations, so on reload the line was drawn as coarse straight segments
that did not match the dense curve a fresh fit renders.  The display path now
re-derives the dense curve from the stored parameters, so reload matches the
original regardless of the serialised resolution (issue #25).
"""

import json

import numpy as np

from core.data_processing.measurement_set import MeasurementSet
from core.data_processing.plotting import prepare_plot_data
from core.pipeline.fit_pipeline import _FIT_CURVE_POINTS, FitResult, _dense_fit_curve
from core.units import Q_
from tests.conftest import IDA_TRUE, _make_ida_data


def _ida_setup():
    """Known IDA assay + ground-truth parameter vector (no optimizer)."""
    from core.assays.ida import IDAAssay

    x, y = _make_ida_data(IDA_TRUE)
    assay = IDAAssay(
        x_data=Q_(x, 'M'),
        y_data=Q_(y, 'au'),
        Ka_dye=Q_(IDA_TRUE['Ka_dye'], '1/M'),
        h0=Q_(IDA_TRUE['h0'], 'M'),
        d0=Q_(IDA_TRUE['d0'], 'M'),
    )
    params = np.array(
        [IDA_TRUE['Ka_guest'], IDA_TRUE['I0'], IDA_TRUE['I_dye_free'], IDA_TRUE['I_dye_bound']],
        dtype=float,
    )
    return assay, x, y, params


def _ida_result(x, y, params, *, x_fit, y_fit) -> FitResult:
    """Build an IDA FitResult with caller-chosen serialised curve arrays."""
    keys = ('Ka_guest', 'I0', 'I_dye_free', 'I_dye_bound')
    units = ('1/M', 'au', 'au/M', 'au/M')
    return FitResult(
        parameters={k: Q_(float(v), u) for k, v, u in zip(keys, params, units)},
        uncertainties={k: Q_(np.nan, u) for k, u in zip(keys, units)},
        rmse=1.0,
        r_squared=0.999,
        n_passing=1,
        n_total=1,
        x_fit=x_fit,
        y_fit=y_fit,
        assay_type='IDA',
        model_name='equilibrium_4param',
        conditions={
            'Ka_dye': Q_(IDA_TRUE['Ka_dye'], '1/M'),
            'h0': Q_(IDA_TRUE['h0'], 'M'),
            'd0': Q_(IDA_TRUE['d0'], 'M'),
        },
    )


def _reload(result: FitResult) -> FitResult:
    """Round-trip through the on-disk JSON form (faithful, not regenerated)."""
    return FitResult.from_dict(json.loads(json.dumps(result.to_dict())))


def test_reloaded_curve_matches_original_smooth_curve():
    """A pre-smooth-curve (sparse) export reloads to the dense original line."""
    assay, x, y, params = _ida_setup()

    # The line a fresh fit draws: the dense forward-model curve.
    x_dense, y_dense = _dense_fit_curve(assay, params)

    # Simulate the old export: curve stored only at the measured points.
    sparse = _ida_result(x, y, params, x_fit=Q_(x, 'M'), y_fit=assay.forward_model(params))
    reloaded = _reload(sparse)
    # The serialised arrays really are sparse (precondition of the bug).
    assert len(reloaded.x_fit.magnitude) == len(x)

    ms = MeasurementSet(concentrations=x, signals=np.vstack([y]), replica_ids=('r1',))
    fit = prepare_plot_data(ms, [reloaded])['fits'][0]

    assert len(fit['x']) == _FIT_CURVE_POINTS
    np.testing.assert_allclose(fit['x'], x_dense.magnitude, rtol=1e-12, atol=0.0)
    np.testing.assert_allclose(fit['y'], y_dense.magnitude, rtol=1e-9, atol=1e-9)


def test_dense_export_curve_unchanged_after_reload():
    """A current (dense) export still renders the identical curve after reload."""
    assay, x, y, params = _ida_setup()
    x_dense, y_dense = _dense_fit_curve(assay, params)

    dense = _ida_result(x, y, params, x_fit=x_dense, y_fit=y_dense)
    reloaded = _reload(dense)

    ms = MeasurementSet(concentrations=x, signals=np.vstack([y]), replica_ids=('r1',))
    fit = prepare_plot_data(ms, [reloaded])['fits'][0]

    np.testing.assert_allclose(fit['x'], x_dense.magnitude, rtol=1e-12, atol=0.0)
    np.testing.assert_allclose(fit['y'], y_dense.magnitude, rtol=1e-12, atol=0.0)


def test_linear_fit_curve_falls_back_to_stored_arrays():
    """DYE_ALONE (linear) has no equilibrium curve to rebuild — keep stored arrays."""
    x = np.linspace(0.0, 20e-6, 12)
    y = 5e10 * x + 100.0
    result = FitResult(
        parameters={'slope': Q_(5e10, 'au/M'), 'intercept': Q_(100.0, 'au')},
        uncertainties={'slope': Q_(np.nan, 'au/M'), 'intercept': Q_(np.nan, 'au')},
        rmse=0.1,
        r_squared=1.0,
        n_passing=1,
        n_total=1,
        x_fit=Q_(x, 'M'),
        y_fit=Q_(y, 'au'),
        assay_type='DYE_ALONE',
        model_name='linear',
    )
    reloaded = _reload(result)

    ms = MeasurementSet(concentrations=x, signals=np.vstack([y]), replica_ids=('r1',))
    fit = prepare_plot_data(ms, [reloaded])['fits'][0]

    np.testing.assert_array_equal(fit['x'], x)
    np.testing.assert_array_equal(fit['y'], y)
