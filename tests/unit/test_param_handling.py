"""P5: Parameter-handling tests.

Validates the named bounds / log-scale API introduced in the parameter-
handling refactor:
- Partial bound overrides merge correctly with registry defaults.
- Unknown parameter names raise ValueError.
- log_scale_params semantics: None → assay default, [] → linear, names → indices.
- bounds_from_dye_alone() helper.
"""

import numpy as np
import pytest

from core.assays.dba import DBAAssay
from core.assays.dye_alone import DyeAloneAssay
from core.assays.gda import GDAAssay
from core.assays.registry import ASSAY_REGISTRY, AssayType
from core.pipeline.fit_pipeline import FitConfig, FitResult, _resolve_bounds, _resolve_log_scale, bounds_from_dye_alone, fit_linear_assay

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_dba_assay() -> DBAAssay:
    """Minimal DBA assay for unit tests (data values don't matter)."""
    x = np.linspace(1e-7, 50e-6, 10)
    return DBAAssay(x_data=x, y_data=np.ones_like(x), fixed_conc=10e-6, mode='DtoH')


def _make_gda_assay() -> GDAAssay:
    """Minimal GDA assay for unit tests."""
    x = np.linspace(1e-7, 30e-6, 10)
    return GDAAssay(x_data=x, y_data=np.ones_like(x), Ka_dye=1e6, h0=10e-6, g0=5e-6)


# ---------------------------------------------------------------------------
# _resolve_bounds
# ---------------------------------------------------------------------------


class TestResolveBounds:
    """Tests for the named-bounds merge logic."""

    def test_none_returns_registry_defaults(self):
        """custom_bounds=None → use full registry defaults."""
        assay = _make_dba_assay()
        bounds = _resolve_bounds(assay, None)

        default = assay.get_default_bounds()
        expected = [default[k] for k in assay.parameter_keys]
        assert bounds == expected

    def test_partial_override_merges(self):
        """Override one param; others keep defaults."""
        assay = _make_dba_assay()
        override = {'I0': (-50, 50)}
        bounds = _resolve_bounds(assay, override)

        default = assay.get_default_bounds()
        idx_I0 = list(assay.parameter_keys).index('I0')

        assert bounds[idx_I0] == (-50, 50)
        # Other params untouched
        for i, k in enumerate(assay.parameter_keys):
            if k != 'I0':
                assert bounds[i] == default[k]

    def test_full_override(self):
        """Override all params → no defaults used."""
        assay = _make_dba_assay()
        custom = {
            'Ka_dye': (1e2, 1e10),
            'I0': (-10, 10),
            'I_dye_free': (1e6, 1e8),
            'I_dye_bound': (1e7, 1e9),
        }
        bounds = _resolve_bounds(assay, custom)
        expected = [custom[k] for k in assay.parameter_keys]
        assert bounds == expected

    def test_unknown_key_raises(self):
        """Typo or wrong param name raises ValueError."""
        assay = _make_dba_assay()
        with pytest.raises(ValueError, match='Unknown parameter'):
            _resolve_bounds(assay, {'Ka_gust': (1, 2)})

    def test_empty_dict_returns_defaults(self):
        """Empty dict is the same as None."""
        assay = _make_dba_assay()
        assert _resolve_bounds(assay, {}) == _resolve_bounds(assay, None)

    def test_gda_uses_correct_ka_key(self):
        """GDA assay uses Ka_guest, not Ka_dye, as the Ka key."""
        assay = _make_gda_assay()

        # Override Ka_guest (should work)
        bounds = _resolve_bounds(assay, {'Ka_guest': (1e4, 1e8)})
        idx = list(assay.parameter_keys).index('Ka_guest')
        assert bounds[idx] == (1e4, 1e8)

        # Ka_dye is not a fitted parameter for GDA → error
        with pytest.raises(ValueError, match='Unknown parameter'):
            _resolve_bounds(assay, {'Ka_dye': (1, 2)})


# ---------------------------------------------------------------------------
# _resolve_log_scale
# ---------------------------------------------------------------------------


class TestResolveLogScale:
    """Tests for log-scale parameter name resolution."""

    def test_none_uses_assay_default(self):
        """None → assay-level default from registry."""
        assay = _make_dba_assay()
        indices = _resolve_log_scale(assay, None)
        # DBA default: ('Ka_dye',) → index 0
        assert indices == [0]

    def test_none_gda_default(self):
        """GDA default: Ka_guest → index 0."""
        assay = _make_gda_assay()
        indices = _resolve_log_scale(assay, None)
        assert indices == [0]

    def test_empty_list_forces_linear(self):
        """[] → no log-scale parameters."""
        assay = _make_dba_assay()
        indices = _resolve_log_scale(assay, [])
        assert indices == []

    def test_explicit_names_converted(self):
        """Named list converts to correct indices."""
        assay = _make_dba_assay()
        indices = _resolve_log_scale(assay, ['Ka_dye', 'I_dye_free'])
        assert indices == [0, 2]

    def test_unknown_name_raises(self):
        """Typo in log-scale name raises ValueError."""
        assay = _make_dba_assay()
        with pytest.raises(ValueError, match='Unknown log-scale parameter'):
            _resolve_log_scale(assay, ['Ka_gust'])

    def test_dye_alone_default_is_empty(self):
        """DyeAlone has no log-scale defaults."""
        x = np.linspace(0, 20e-6, 10)
        assay = DyeAloneAssay(x_data=x, y_data=np.ones_like(x))
        indices = _resolve_log_scale(assay, None)
        assert indices == []


# ---------------------------------------------------------------------------
# FitConfig dataclass
# ---------------------------------------------------------------------------


class TestFitConfig:
    """FitConfig dataclass defaults and type contracts."""

    def test_defaults(self):
        cfg = FitConfig()
        assert cfg.n_trials == 100
        assert cfg.log_scale_params is None
        assert cfg.custom_bounds is None

    def test_dict_bounds_accepted(self):
        cfg = FitConfig(custom_bounds={'Ka_guest': (1e4, 1e8)})
        assert cfg.custom_bounds == {'Ka_guest': (1e4, 1e8)}

    def test_named_log_scale_accepted(self):
        cfg = FitConfig(log_scale_params=['Ka_guest'])
        assert cfg.log_scale_params == ['Ka_guest']


# ---------------------------------------------------------------------------
# bounds_from_dye_alone
# ---------------------------------------------------------------------------


class TestBoundsFromDyeAlone:
    """Tests for the dye-alone → signal bounds helper."""

    def _make_linear_result(self, slope: float = 5e7, intercept: float = 100.0) -> FitResult:
        """Create a minimal successful linear FitResult."""
        return FitResult(
            parameters={'slope': slope, 'intercept': intercept},
            uncertainties={'slope': 0.0, 'intercept': 0.0},
            rmse=0.0,
            r_squared=1.0,
            n_passing=1,
            n_total=1,
            x_fit=np.array([0]),
            y_fit=np.array([0]),
            assay_type='DYE_ALONE',
            model_name='linear',
        )

    def test_default_margin(self):
        """20% margin around slope and intercept."""
        r = self._make_linear_result(slope=5e7, intercept=100.0)
        bounds = bounds_from_dye_alone(r)

        assert bounds['I_dye_free'] == pytest.approx((4e7, 6e7))
        assert bounds['I0'] == pytest.approx((80.0, 120.0))

    def test_custom_margin(self):
        """Non-default margin scales proportionally."""
        r = self._make_linear_result(slope=1e8, intercept=200.0)
        bounds = bounds_from_dye_alone(r, margin=0.1)

        assert bounds['I_dye_free'] == pytest.approx((9e7, 1.1e8))
        assert bounds['I0'] == pytest.approx((180.0, 220.0))

    def test_negative_intercept_clamped_to_zero(self):
        """Negative intercept gets both bounds clamped to 0."""
        r = self._make_linear_result(slope=5e7, intercept=-50.0)
        bounds = bounds_from_dye_alone(r, margin=0.2)

        lo, hi = bounds['I0']
        assert lo == 0.0
        assert hi == 0.0

    def test_all_lower_bounds_non_negative(self):
        """Signal intensities are physical quantities — lower bounds ≥ 0."""
        r = self._make_linear_result(slope=5e7, intercept=100.0)
        bounds = bounds_from_dye_alone(r)

        for key, (lo, _hi) in bounds.items():
            assert lo >= 0.0, f'{key} lower bound {lo} is negative'

    def test_non_linear_model_raises(self):
        """Rejects non-linear FitResults."""
        r = self._make_linear_result()
        r = FitResult(**{**r.__dict__, 'model_name': 'equilibrium_4param'})
        with pytest.raises(ValueError, match='linear'):
            bounds_from_dye_alone(r)

    def test_failed_fit_raises(self):
        """Rejects failed fits (n_passing=0)."""
        r = self._make_linear_result()
        r = FitResult(**{**r.__dict__, 'n_passing': 0})
        with pytest.raises(ValueError, match='failed fit'):
            bounds_from_dye_alone(r)

    def test_result_mergeable_with_custom_bounds(self):
        """bounds_from_dye_alone output can merge into FitConfig.custom_bounds."""
        r = self._make_linear_result()
        priors = bounds_from_dye_alone(r)
        combined = {**priors, 'Ka_guest': (1e4, 1e8)}

        assert 'I_dye_free' in combined
        assert 'I0' in combined
        assert 'Ka_guest' in combined

    def test_integration_with_fit_linear_assay(self, dye_alone_clean):
        """End-to-end: fit dye alone → derive bounds → validate keys."""
        x, y, true = dye_alone_clean
        assay = DyeAloneAssay(x_data=x, y_data=y)
        result = fit_linear_assay(assay)

        priors = bounds_from_dye_alone(result, margin=0.3)
        assert 'I_dye_free' in priors
        assert 'I0' in priors
        # Bounds should bracket the true slope
        lo, hi = priors['I_dye_free']
        assert lo < true['slope'] < hi


# ---------------------------------------------------------------------------
# log_scale_keys registry coverage
# ---------------------------------------------------------------------------


class TestLogScaleKeysRegistry:
    """Ensure every assay type has correctly-typed log_scale_keys."""

    @pytest.mark.parametrize('assay_type', list(AssayType))
    def test_log_scale_keys_are_valid_param_names(self, assay_type):
        """Every log_scale_key must be in parameter_keys."""
        meta = ASSAY_REGISTRY[assay_type]
        for key in meta.log_scale_keys:
            assert key in meta.parameter_keys, f"{assay_type.name}: log_scale_key '{key}' not in parameter_keys {meta.parameter_keys}"

    @pytest.mark.parametrize('assay_type', list(AssayType))
    def test_default_bounds_keys_match_param_keys(self, assay_type):
        """default_bounds keys must match parameter_keys exactly."""
        meta = ASSAY_REGISTRY[assay_type]
        assert set(meta.default_bounds.keys()) == set(meta.parameter_keys)
