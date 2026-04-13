"""Tests for pipeline helper functions: _resolve_bounds, _resolve_log_scale."""

import numpy as np
import pytest

from core.assays.gda import GDAAssay
from core.pipeline.fit_pipeline import _resolve_bounds, _resolve_log_scale
from core.units import Q_


def _gda_assay():
    return GDAAssay(
        x_data=Q_(np.linspace(1e-7, 50e-6, 5), 'M'),
        y_data=Q_(np.ones(5), 'au'),
        Ka_dye=Q_(5e5, '1/M'),
        h0=Q_(10e-6, 'M'),
        g0=Q_(20e-6, 'M'),
    )


class TestResolveBounds:
    def test_custom_overrides_one_param(self):
        assay = _gda_assay()
        custom = {'Ka_guest': (Q_(1.0, '1/M'), Q_(2.0, '1/M'))}
        merged = _resolve_bounds(assay, custom)

        # Ka_guest should be overridden
        lo, hi = merged['Ka_guest']
        assert lo.magnitude == pytest.approx(1.0)
        assert hi.magnitude == pytest.approx(2.0)

        # Other params should keep registry defaults
        assert 'I0' in merged
        assert 'I_dye_free' in merged
        assert 'I_dye_bound' in merged

    def test_unknown_key_raises(self):
        assay = _gda_assay()
        custom = {'bogus': (Q_(0, 'au'), Q_(1, 'au'))}
        with pytest.raises(ValueError, match='Unknown parameter'):
            _resolve_bounds(assay, custom)

    def test_none_custom_returns_defaults(self):
        assay = _gda_assay()
        merged = _resolve_bounds(assay, None)
        assert set(merged.keys()) == set(assay.parameter_keys)


class TestResolveLogScale:
    def test_none_uses_registry(self):
        assay = _gda_assay()
        indices = _resolve_log_scale(assay, None)
        # Ka_guest is index 0 in GDA parameter_keys and is in log_scale_keys
        assert 0 in indices

    def test_empty_list_overrides(self):
        assay = _gda_assay()
        indices = _resolve_log_scale(assay, [])
        assert indices == []

    def test_unknown_raises(self):
        assay = _gda_assay()
        with pytest.raises(ValueError, match='Unknown log-scale parameter'):
            _resolve_log_scale(assay, ['nonexistent'])
