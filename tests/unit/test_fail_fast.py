"""Fail-fast contract tests.

Verify that assay constructors and the fit reject invalid inputs immediately
with clear error messages, rather than silently corrupting.
"""

import numpy as np
import pytest

from core.assays.dba import DBAAssay
from core.assays.dye_alone import DyeAloneAssay
from core.assays.gda import GDAAssay
from core.assays.ida import IDAAssay
from core.pipeline.fit_pipeline import FitConfig, fit_assay
from core.pipeline.inputs import TITRANT, ErrorModel, InputSpec
from core.units import Q_
from tests.conftest import IDA_TRUE, _make_ida_data


class TestGDAFailFast:
    """GDA constructor rejects invalid inputs."""

    def _valid_kwargs(self):
        return dict(
            x_data=Q_(np.linspace(0, 10e-6, 5), 'M'),
            y_data=Q_(np.ones(5), 'au'),
            Ka_dye=Q_(1e6, '1/M'),
            h0=Q_(10e-6, 'M'),
            g0=Q_(5e-6, 'M'),
        )

    def test_missing_ka_dye_raises(self):
        kw = self._valid_kwargs()
        del kw['Ka_dye']
        with pytest.raises(ValueError, match='Ka_dye is required'):
            GDAAssay(**kw)

    def test_missing_h0_raises(self):
        kw = self._valid_kwargs()
        del kw['h0']
        with pytest.raises(ValueError, match='h0 is required'):
            GDAAssay(**kw)

    def test_missing_g0_raises(self):
        kw = self._valid_kwargs()
        del kw['g0']
        with pytest.raises(ValueError, match='g0 is required'):
            GDAAssay(**kw)

    def test_negative_ka_dye_raises(self):
        kw = self._valid_kwargs()
        kw['Ka_dye'] = Q_(-1e6, '1/M')
        with pytest.raises(ValueError, match='Ka_dye must be positive'):
            GDAAssay(**kw)

    def test_zero_h0_raises(self):
        kw = self._valid_kwargs()
        kw['h0'] = Q_(0.0, 'M')
        with pytest.raises(ValueError, match='h0.*must be positive'):
            GDAAssay(**kw)

    def test_negative_g0_raises(self):
        kw = self._valid_kwargs()
        kw['g0'] = Q_(-1e-6, 'M')
        with pytest.raises(ValueError, match='g0.*must be positive'):
            GDAAssay(**kw)

    def test_zero_g0_is_accepted(self):
        """g0 = 0 is legal, unlike h0 and Ka_dye.

        It is the no-competitor limit in which GDA reduces to DBA — the case
        ``test_gda_g0_zero_matches_dba`` relies on. Tightening the check to
        ``<= 0`` would make that limit unreachable through the assay.
        """
        kw = self._valid_kwargs()
        kw['g0'] = Q_(0.0, 'M')
        assay = GDAAssay(**kw)
        assert assay.g0.magnitude == 0.0

    def test_mismatched_data_shapes_raises(self):
        kw = self._valid_kwargs()
        kw['y_data'] = Q_(np.ones(3), 'au')  # Different length than x_data
        with pytest.raises(ValueError, match='same shape'):
            GDAAssay(**kw)


class TestIDAFailFast:
    """IDA constructor rejects invalid inputs."""

    def _valid_kwargs(self):
        return dict(
            x_data=Q_(np.linspace(0, 10e-6, 5), 'M'),
            y_data=Q_(np.ones(5), 'au'),
            Ka_dye=Q_(1e6, '1/M'),
            h0=Q_(10e-6, 'M'),
            d0=Q_(1e-6, 'M'),
        )

    def test_missing_ka_dye_raises(self):
        kw = self._valid_kwargs()
        del kw['Ka_dye']
        with pytest.raises(ValueError, match='Ka_dye is required'):
            IDAAssay(**kw)

    def test_missing_h0_raises(self):
        kw = self._valid_kwargs()
        del kw['h0']
        with pytest.raises(ValueError, match='h0 is required'):
            IDAAssay(**kw)

    def test_missing_d0_raises(self):
        kw = self._valid_kwargs()
        del kw['d0']
        with pytest.raises(ValueError, match='d0 is required'):
            IDAAssay(**kw)

    def test_negative_ka_dye_raises(self):
        kw = self._valid_kwargs()
        kw['Ka_dye'] = Q_(-1.0, '1/M')
        with pytest.raises(ValueError, match='Ka_dye must be positive'):
            IDAAssay(**kw)

    def test_zero_d0_raises(self):
        kw = self._valid_kwargs()
        kw['d0'] = Q_(0.0, 'M')
        with pytest.raises(ValueError, match='d0.*must be positive'):
            IDAAssay(**kw)


class TestDBAFailFast:
    """DBA constructor rejects invalid inputs."""

    def _valid_kwargs(self):
        return dict(
            x_data=Q_(np.linspace(0, 10e-6, 5), 'M'),
            y_data=Q_(np.ones(5), 'au'),
            fixed_conc=Q_(10e-6, 'M'),
            mode='DtoH',
        )

    def test_missing_fixed_conc_raises(self):
        kw = self._valid_kwargs()
        del kw['fixed_conc']
        with pytest.raises(ValueError, match='fixed_conc is required'):
            DBAAssay(**kw)

    def test_negative_fixed_conc_raises(self):
        kw = self._valid_kwargs()
        kw['fixed_conc'] = Q_(-1e-6, 'M')
        with pytest.raises(ValueError, match='fixed_conc must be positive'):
            DBAAssay(**kw)

    def test_invalid_mode_raises(self):
        kw = self._valid_kwargs()
        kw['mode'] = 'invalid'
        with pytest.raises(ValueError, match='mode must be'):
            DBAAssay(**kw)


class TestDyeAloneFailFast:
    """DyeAlone constructor rejects invalid inputs."""

    def test_mismatched_shapes_raises(self):
        with pytest.raises(ValueError, match='same shape'):
            DyeAloneAssay(
                x_data=Q_(np.array([1, 2, 3]), 'M'),
                y_data=Q_(np.array([1, 2]), 'au'),
            )


class TestBaseAssayContracts:
    """Base assay properties and methods work correctly."""

    def test_parameter_keys_from_registry(self):
        """Assay exposes correct parameter_keys from registry."""
        assay = GDAAssay(
            x_data=Q_(np.array([1e-6]), 'M'),
            y_data=Q_(np.array([100.0]), 'au'),
            Ka_dye=Q_(1e6, '1/M'),
            h0=Q_(10e-6, 'M'),
            g0=Q_(5e-6, 'M'),
        )
        assert assay.parameter_keys == ('Ka_guest', 'I0', 'I_dye_free', 'I_dye_bound')

    def test_params_to_dict(self):
        """params_to_dict maps array values to parameter names."""
        assay = GDAAssay(
            x_data=Q_(np.array([1e-6]), 'M'),
            y_data=Q_(np.array([100.0]), 'au'),
            Ka_dye=Q_(1e6, '1/M'),
            h0=Q_(10e-6, 'M'),
            g0=Q_(5e-6, 'M'),
        )
        params = np.array([1.5e6, 50.0, 1000.0, 5000.0])
        d = assay.params_to_dict(params)
        assert d == {
            'Ka_guest': 1.5e6,
            'I0': 50.0,
            'I_dye_free': 1000.0,
            'I_dye_bound': 5000.0,
        }

    def test_residuals_correct(self):
        """Residuals = observed - predicted, hand-computed for a linear model.

        slope=1e8, intercept=100 → predictions [100, 200, 300];
        observed [100, 210, 290] → residuals [0, 10, -10].
        """
        assay = DyeAloneAssay(
            x_data=Q_(np.array([0, 1e-6, 2e-6]), 'M'),
            y_data=Q_(np.array([100.0, 210.0, 290.0]), 'au'),
        )
        params = np.array([1e8, 100.0])  # slope, intercept
        resid = assay.residuals(params)
        np.testing.assert_allclose(resid.magnitude, [0.0, 10.0, -10.0], atol=1e-9)

    def test_sum_squared_residuals(self):
        """SSR hand-computed: 0² + 10² + (-10)² = 200."""
        assay = DyeAloneAssay(
            x_data=Q_(np.array([0, 1e-6, 2e-6]), 'M'),
            y_data=Q_(np.array([100.0, 210.0, 290.0]), 'au'),
        )
        params = np.array([1e8, 100.0])
        assert assay.sum_squared_residuals(params) == pytest.approx(200.0)


class TestFitRefusals:
    """The fit refuses what it cannot do, in words that name the input and the fix.

    Each refusal replaces a number the app would otherwise have to invent: a
    binding constant with no speciation, a confidence interval with no degrees
    of freedom, a search range that is not a range of binding constants.
    """

    def _ida_assay(self, n_points: int = 15, cls=IDAAssay):
        x = np.linspace(0, 50e-6, n_points)
        return cls(
            x_data=Q_(x, 'M'),
            y_data=Q_(np.linspace(3000.0, 500.0, n_points), 'au'),
            Ka_dye=Q_(5e5, '1/M'),
            h0=Q_(10e-6, 'M'),
            d0=Q_(5e-6, 'M'),
        )

    def test_a_model_with_no_solution_anywhere_in_the_bounds_is_refused(self):
        """A binding constant the model returns no speciation for has no fit at all.

        The speciation is stubbed out so the refusal is pinned on the sentinel
        itself rather than on where one arithmetic happens to give out.
        """

        class UnsolvableIDA(IDAAssay):
            def species(self, params):
                return {k: np.full(self.n_points, np.nan) for k in ('H', 'D', 'G', 'HD', 'HG')}

        with pytest.raises(ValueError, match='no solution at any association constant'):
            fit_assay(self._ida_assay(cls=UnsolvableIDA))

    def test_too_few_points_to_judge_the_fit_is_refused_with_the_counts(self):
        """Three points and four parameters leave nothing to measure a confidence interval by."""
        with pytest.raises(ValueError, match='too few to judge'):
            fit_assay(self._ida_assay(n_points=3))

    @pytest.mark.parametrize(
        'bounds',
        [(0.0, 1e12), (-1e6, 1e12), (1e9, 1e6)],
        ids=['zero', 'negative', 'inverted'],
    )
    def test_ka_bounds_that_are_not_a_range_of_binding_constants_are_refused_by_name(self, bounds):
        lo, hi = bounds
        config = FitConfig(custom_bounds={'Ka_guest': (Q_(lo, '1/M'), Q_(hi, '1/M'))})

        with pytest.raises(ValueError, match='Ka_guest'):
            fit_assay(self._ida_assay(), config)


class TestInputsTooFreeForTheData:
    """A fit that cannot be made with the inputs as free as they were stated to be is refused, not quietly narrowed."""

    @staticmethod
    def _assay(n_points: int = 6) -> IDAAssay:
        """The IDA ground truth at few points: a signal the inputs really do act on."""
        x, y = _make_ida_data(IDA_TRUE, n_points=n_points)
        return IDAAssay(
            x_data=Q_(x, 'M'),
            y_data=Q_(y, 'au'),
            Ka_dye=Q_(IDA_TRUE['Ka_dye'], '1/M'),
            h0=Q_(IDA_TRUE['h0'], 'M'),
            d0=Q_(IDA_TRUE['d0'], 'M'),
        )

    _LABELS = {'h0': '[Host]₀', 'd0': '[Dye]₀', TITRANT: 'Guest (titrant)'}

    def test_too_few_points_for_the_model_and_the_ranges_is_refused_and_names_the_inputs(self):
        """Six points, three parameters and three inputs free within a range leave nothing to judge Ka by."""
        config = FitConfig(
            per_replica=False,
            errors=ErrorModel(
                specs={
                    'h0': InputSpec.interval_pct(-20, 20),
                    'd0': InputSpec.interval_pct(-20, 20),
                    TITRANT: InputSpec.interval_pct(-5, 5),
                }
            ),
            input_labels=self._LABELS,
        )

        with pytest.raises(ValueError, match='too few to fit this model') as refused:
            fit_assay(self._assay(), config)

        message = str(refused.value)
        assert '[Host]₀' in message and 'Guest (titrant)' in message
        assert 'Input Uncertainty' in message, 'the message has to say where to change it'
        assert 'h0' not in message, 'a message shows the labels the panel writes, never a dict key'

    def test_inputs_the_data_determine_take_the_same_room_and_the_fit_is_refused(self):
        """Falling back to the interval that holds the inputs exact would report a claim nobody asked for.

        Four inputs stated to 50 % are free enough that the data, not the
        stated uncertainty, decide where they go: they use up what the six
        points had left to judge Ka by.
        """
        specs = {key: InputSpec.sigma_pct(50) for key in ('h0', 'd0', 'Ka_dye', TITRANT)}
        config = FitConfig(per_replica=False, errors=ErrorModel(specs=specs), input_labels=self._LABELS)

        with pytest.raises(ValueError, match='too few to fit this model'):
            fit_assay(self._assay(), config)

        # The same data fit once the inputs are held as entered, so the refusal is about them.
        assert fit_assay(self._assay(), FitConfig(per_replica=False)).intervals['Ka_guest'] is not None
