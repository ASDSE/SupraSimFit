"""Widget tests for IdentifiabilityWidget — fit attempts, Ka profile, sensitivity overlay.

Require a ``QApplication`` (the ``qapp`` fixture).
"""

import numpy as np
import pytest

pytest.importorskip('PyQt6')

from core.pipeline.fit_pipeline import FitResult  # noqa: E402
from core.pipeline.profile import ProfileResult  # noqa: E402
from core.pipeline.sensitivity import (  # noqa: E402
    TITRANT,
    InputSpec,
    ReplicateMode,
    SensitivityConfig,
    SensitivityMode,
    SensitivityResult,
)
from core.units import Q_  # noqa: E402

IDA_KEYS = ('Ka_guest', 'I0', 'I_dye_free', 'I_dye_bound')
N_ATTEMPTS = 40
N_NEGATIVE = 5
FLOOR = 0.99


def _fit(keys=IDA_KEYS, assay='IDA', *, per_replica=False, with_attempts=True):
    """A FitResult whose first ``N_NEGATIVE`` attempts fit worse than a flat line."""
    rng = np.random.default_rng(1)
    samples = {
        k: 10 ** rng.uniform(7, 10, N_ATTEMPTS) if k.startswith('Ka') else rng.uniform(0, 1, N_ATTEMPTS) for k in keys
    }
    r2 = 1.0 - 10 ** -rng.uniform(0.5, 3.0, N_ATTEMPTS)
    r2[:N_NEGATIVE] = -0.5
    return FitResult(
        parameters={k: Q_(float(v[-1]), 'dimensionless') for k, v in samples.items()},
        rmse=0.1,
        r_squared=float(r2.max()),
        n_passing=int(np.sum(r2 >= FLOOR)),
        n_total=N_ATTEMPTS,
        x_fit=Q_(np.zeros(3), 'M'),
        y_fit=Q_(np.zeros(3), 'au'),
        assay_type=assay,
        model_name='equilibrium_4param',
        fit_config={'min_r_squared': FLOOR},
        uncertainty_source='replicate' if per_replica else 'optimizer',
        attempt_samples=samples if with_attempts else None,
        attempt_quality={'rmse': np.ones(N_ATTEMPTS), 'r_squared': r2} if with_attempts else None,
    )


def _profile(*, per_replica=False, ci_open=(False, False)):
    grid = np.logspace(-8, 12, 401)

    def bump(centre, top):
        return top * np.exp(-((np.log10(grid) - centre) ** 2))

    return ProfileResult(
        ka_key='Ka_guest',
        grid=grid,
        r2=bump(8.5, 0.995),
        replica_r2={rid: bump(8.5 + 0.1 * i, 0.99 - 0.01 * i) for i, rid in enumerate('ABC')} if per_replica else None,
        best_ka=10**8.5,
        best_r2=0.995,
        level=0.95,
        ci=(1e8, 1e12 if ci_open[1] else 1e9),
        ci_open=ci_open,
        r2_threshold=0.99,
        n_points=12,
        n_params=3,
        per_replica=per_replica,
    )


N_SAMPLES = 21
NO_FIT = 10  # the sample at offset 0 produced no fit


def _sensitivity(replicate_mode=ReplicateMode.FOLLOW):
    ka = 10 ** np.linspace(8.2, 8.8, N_SAMPLES)
    r2 = np.linspace(0.97, 0.999, N_SAMPLES)
    ka[NO_FIT] = r2[NO_FIT] = np.nan
    return SensitivityResult(
        mode=SensitivityMode.SOBOL,
        assay_type='IDA',
        ka_keys=('Ka_guest',),
        baseline_ka={'Ka_guest': 10**8.5},
        histograms={'sobol': {'Ka_guest': ka}},
        x_offsets_pct=None,
        y_offsets_pct=None,
        ka_grid=None,
        n_success=N_SAMPLES - 1,
        n_total=2 * N_SAMPLES,
        config=SensitivityConfig(
            SensitivityMode.SOBOL,
            N_SAMPLES,
            {'h0': InputSpec.sigma_pct(5.0), TITRANT: InputSpec.sigma_pct(5.0)},
            replicate_mode=replicate_mode,
        ),
        sample_offsets_pct={'h0': np.linspace(-10, 10, N_SAMPLES), TITRANT: np.linspace(5, -5, N_SAMPLES)},
        sample_ka={'Ka_guest': ka},
        sample_r2=r2,
        floor=FLOOR,
        n_below_floor=int(np.sum(r2 < FLOOR)),
    )


def _widget(fit=None, profile=None, assay='IDA'):
    from gui.plotting.identifiability_widget import IdentifiabilityWidget

    w = IdentifiabilityWidget()
    if fit is not None:
        w.update_fit(fit, profile, assay)
    return w


def _n_points(scatter):
    return len(scatter.getData()[0])


def _contrast(colour, other) -> float:
    """WCAG contrast ratio of two colours."""
    from PyQt6.QtGui import QColor

    def luminance(c):
        c = QColor(c)
        channels = [
            v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in (c.redF(), c.greenF(), c.blueF())
        ]
        return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]

    high, low = sorted((luminance(colour), luminance(other)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def _point_colour(scatter, i):
    """Colour a point shows: its fill, or its ring when drawn hollow."""
    brush = scatter.data['brush'][i]
    if brush.color().name() == '#fcfcfb':
        return scatter.data['pen'][i].color()
    return brush.color()


# ---------------------------------------------------------------------------
# States
# ---------------------------------------------------------------------------


def test_placeholder_before_any_fit(qapp):
    w = _widget()
    assert w._stack.currentWidget() is w._message
    assert 'Run a fit' in w._message.text()


def test_dye_alone_is_not_applicable(qapp):
    fit = _fit(keys=('slope', 'intercept'), assay='DYE_ALONE', with_attempts=False)
    w = _widget(fit, None, 'DYE_ALONE')
    assert w._stack.currentWidget() is w._message
    assert 'Not applicable' in w._message.text()


def test_unsupported_assay_shows_attempts_only(qapp):
    """Two binding constants: one attempts-only panel per Ka and a note saying why there is no line."""
    keys = ('Ka_HG', 'Ka_HG2', 'I0', 'I_G', 'I_H', 'I_HG', 'I_HG2')
    w = _widget(_fit(keys=keys, assay='DBA_HG2'), None, 'DBA_HG2')
    assert w._stack.currentWidget() is w._content
    assert set(w._items) == {'Ka_HG', 'Ka_HG2'}
    for items in w._items.values():
        assert items['average'] is None
        assert _n_points(items['attempts_passing']) + _n_points(items['attempts_below']) == N_ATTEMPTS - N_NEGATIVE
    assert 'single binding constant' in w._notes.text()


def test_supported_assay_without_profile_notes_the_missing_line(qapp):
    w = _widget(_fit(), None)
    items = w._items['Ka_guest']
    assert items['average'] is None
    assert _n_points(items['attempts_passing']) + _n_points(items['attempts_below']) == N_ATTEMPTS - N_NEGATIVE
    assert 'not available' in w._notes.text()


def test_clear_returns_to_placeholder(qapp):
    w = _widget(_fit(), _profile())
    w.update_sensitivity(_sensitivity())
    w.clear()
    assert w._stack.currentWidget() is w._message
    assert 'Run a fit' in w._message.text()
    assert w._controls.isHidden()
    assert w._items == {}


# ---------------------------------------------------------------------------
# Section 1: attempts and profile
# ---------------------------------------------------------------------------


def test_average_mode_draws_the_profile_line_and_classifies_attempts(qapp):
    fit = _fit()
    w = _widget(fit, _profile())
    items = w._items['Ka_guest']
    assert items['average'] is not None and items['replicas'] == []
    assert items['average'].opts['pen'].widthF() == 2
    r2 = fit.attempt_quality['r_squared']
    assert _n_points(items['attempts_passing']) == int(np.sum(r2 >= FLOOR))
    assert _n_points(items['attempts_below']) == int(np.sum((r2 >= 0) & (r2 < FLOOR)))


def test_per_replicate_mode_draws_one_thin_line_per_replicate(qapp):
    w = _widget(_fit(per_replica=True), _profile(per_replica=True))
    items = w._items['Ka_guest']
    assert len(items['replicas']) == 3
    assert all(c.opts['pen'].widthF() == 1 for c in items['replicas'])
    assert items['average'].opts['pen'].widthF() == 2
    assert "replicate's own thin line" in w._notes.text()
    assert "best fit of the replicates' average" in w._summary.text()
    assert 'look more certain than it is' in w._notes.text()


def test_hidden_attempts_are_counted(qapp):
    w = _widget(_fit(), _profile())
    assert f'{N_NEGATIVE} of {N_ATTEMPTS} attempts not shown' in w._notes.text()


def test_confidence_interval_is_stated(qapp):
    """Best Ka 10^8.5 with a CI of 1e8 to 1e9: −68 % and +216 % of the best fit."""
    w = _widget(_fit(), _profile())
    text = w._summary.text()
    assert '95% CI 1.0×10⁸ – 1.0×10⁹' in text
    assert '(−68% / +216%)' in text
    assert 'open' not in text


def test_open_interval_says_open(qapp):
    """The unit follows the number it belongs to, never the word "open"."""
    w = _widget(_fit(), _profile(ci_open=(False, True)))
    text = w._summary.text()
    assert '1.0×10⁸ M<sup>−1</sup> – open (' in text
    assert '(−68% / open)' in text
    assert 'cannot rule out a higher' in text


def test_a_drop_close_to_minus_100_percent_is_not_rounded_to_it(qapp):
    """−99.6 % shows as such: −100 % would say the interval reaches a Ka of zero."""
    from gui.plotting.identifiability_widget import _pct

    assert _pct(3.3e6 / 8.14e8) == '−99.6%'
    assert _pct(0.32) == '−68%'
    assert _pct(3.16) == '+216%'


def test_fit_attempts_far_below_the_floor_do_not_squeeze_the_view(qapp):
    """One attempt at the Ka lower bound leaves the view on the interval, and the note counts it."""
    fit = _fit()
    ka, r2 = fit.attempt_samples['Ka_guest'], fit.attempt_quality['r_squared']
    ka[N_NEGATIVE], r2[N_NEGATIVE] = 1e-8, 0.5
    w = _widget(fit, _profile())
    (x_lo, x_hi), _ = w._items['Ka_guest']['main'].viewRange()
    assert x_lo > 0  # the attempt at log10 Ka = −8 is out of view
    assert x_hi - x_lo < 5  # the interval (one decade) keeps a readable share of the width
    assert '1 of 35 attempts' in w._notes.text()
    assert 'zoom out to see them' in w._notes.text()


def test_replicates_the_fit_left_out_are_named(qapp):
    fit = _fit(per_replica=True)
    fit.metadata['replica_failures'] = {'A': 'No trials passed the quality filter.'}
    w = _widget(fit, _profile(per_replica=True))
    assert 'Replicate A is left out here, as it was from the fit.' in w._notes.text()


def test_floor_label_has_a_surface_background(qapp):
    """The floor's label sits on a surface-coloured box above the dots, so no dot runs through its text."""
    import pyqtgraph as pg

    w = _widget(_fit(), _profile())
    main = w._items['Ka_guest']['main']
    (line,) = [item for item in main.items if isinstance(item, pg.InfiniteLine) and item.label is not None]
    assert line.label.fill.color().name() == '#fcfcfb'
    assert line.zValue() > w._items['Ka_guest']['attempts_passing'].zValue()


def test_default_view_frames_the_attempts_and_the_floor(qapp):
    from gui.plotting.identifiability_widget import _r2_to_y

    fit = _fit()
    w = _widget(fit, _profile())
    (x_lo, x_hi), (y_lo, y_hi) = w._items['Ka_guest']['main'].viewRange()
    shown = fit.attempt_quality['r_squared'] >= 0
    log_ka = np.log10(fit.attempt_samples['Ka_guest'][shown])
    assert x_lo <= log_ka.min() and log_ka.max() <= x_hi
    assert y_lo <= _r2_to_y(FLOOR) <= y_hi


def test_r2_axis_reads_in_r2(qapp):
    from gui.plotting.identifiability_widget import _r2_label, _R2Axis

    assert [_r2_label(y) for y in (0.0, 1.0, 2.0, 3.0)] == ['0', '0.9', '0.99', '0.999']
    assert _r2_label(2.0 - np.log10(5.0)) == '0.95'
    majors = _R2Axis('left').tickValues(0.0, 3.0, 300)[0][1]
    assert majors == [0.0, 1.0, 2.0, 3.0]


@pytest.mark.parametrize('y_range', [(1.47, 2.25), (2.0, 2.05), (1.2, 2.6), (3.1, 3.12)])
def test_r2_axis_ticks_are_round_on_a_narrow_range(qapp, y_range):
    """At least three ticks, each at an R² its label states exactly (0.97, 0.993 — never 0.9937)."""
    from gui.plotting.identifiability_widget import _r2_label, _R2Axis

    axis = _R2Axis('left')
    ys = [y for _, values in axis.tickValues(*y_range, 400) for y in values]
    assert len(ys) >= 3
    for y in ys:
        assert float(_r2_label(y)) == pytest.approx(1.0 - 10.0 ** (-y), abs=1e-12)


# ---------------------------------------------------------------------------
# Section 2: sensitivity overlay
# ---------------------------------------------------------------------------


def test_sensitivity_samples_overlay_in_one_colour(qapp):
    sens = _sensitivity()
    w = _widget(_fit(), _profile())
    w.update_sensitivity(sens)
    assert not w._controls.isHidden()
    assert [w._colour_combo.itemText(i) for i in range(w._colour_combo.count())] == [
        'None',
        '[Host]₀',
        'Guest (titrant)',
    ]
    scatter = w._items['Ka_guest']['samples']
    assert _n_points(scatter) == N_SAMPLES - 1
    assert w._items['Ka_guest']['colour_bar'] is None
    assert {_point_colour(scatter, i).name() for i in range(N_SAMPLES - 1)} == {'#2a78d6'}
    n_hollow = sum(scatter.data['brush'][i].color().name() == '#fcfcfb' for i in range(N_SAMPLES - 1))
    assert n_hollow == sens.n_below_floor
    assert f'the {sens.n_below_floor} below the quality floor are hollow' in w._notes.text()
    assert '1 not shown' in w._notes.text()


def test_colour_by_input_uses_the_diverging_scale(qapp):
    w = _widget(_fit(), _profile())
    w.update_sensitivity(_sensitivity())
    w._colour_combo.setCurrentIndex(w._colour_combo.findText('[Host]₀'))
    items = w._items['Ka_guest']
    assert items['colour_bar'] is not None
    scatter = items['samples']
    # h0 runs from −10 % (first sample) to +10 % (last): blue to red.
    assert _point_colour(scatter, 0).getRgb()[:3] == (42, 120, 214)
    assert _point_colour(scatter, N_SAMPLES - 2).getRgb()[:3] == (227, 73, 72)
    # Every dot's outline stands out from the surface, the near-zero ones included.
    assert min(_contrast(pen.color(), '#fcfcfb') for pen in scatter.data['pen']) >= 3.0

    # Restyling keeps the chosen input.
    from gui.plotting.plot_style import DEFAULT_STYLE

    w.apply_style(DEFAULT_STYLE)
    assert w._colour_combo.currentText() == '[Host]₀'
    assert w._items['Ka_guest']['colour_bar'] is not None


def test_replicate_handling_mismatch_is_noted(qapp):
    w = _widget(_fit(), _profile())
    w.update_sensitivity(_sensitivity(ReplicateMode.FOLLOW))
    assert 'different signals' not in w._notes.text()
    w.update_sensitivity(_sensitivity(ReplicateMode.PER_REPLICA))
    assert 'fitted each replicate separately but this fit used their average' in w._notes.text()


# ---------------------------------------------------------------------------
# Real objects
# ---------------------------------------------------------------------------


def test_renders_a_real_ida_fit_and_its_profile(qapp):
    """The IDA demo data: every non-negative attempt drawn, the CI stated from the profile."""
    from core.assays.ida import IDAAssay
    from core.data_processing.measurement_set import MeasurementSet
    from core.io import load_measurements
    from core.pipeline.fit_pipeline import FitConfig, fit_measurement_set
    from core.pipeline.profile import fit_profile
    from gui.plotting.labels import fmt_sci

    ms = MeasurementSet.from_dataframe(load_measurements('data/IDA_system.txt'))
    conditions = {'Ka_dye': Q_(16.8e6, '1/M'), 'h0': Q_(4.3e-6, 'M'), 'd0': Q_(6e-6, 'M')}
    config = FitConfig(per_replica=False, n_trials=20, seed=1)
    fit = fit_measurement_set(ms, IDAAssay, conditions, config)
    profile = fit_profile(ms, IDAAssay, conditions, config)

    w = _widget(fit, profile)
    items = w._items['Ka_guest']
    r2 = fit.attempt_quality['r_squared']
    assert _n_points(items['attempts_passing']) + _n_points(items['attempts_below']) == int(np.sum(r2 >= 0))
    assert len(items['average'].getData()[0]) == profile.grid.size
    assert f'95% CI {fmt_sci(profile.ci[0])} – {fmt_sci(profile.ci[1])}' in w._summary.text()
