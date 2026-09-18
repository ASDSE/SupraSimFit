"""Ka input-sensitivity analysis — scientific behaviour tests.

Verifies the compute layer (`core.pipeline.sensitivity`) as *behaviour*, not
implementation:

- perturbation is the only variance source (near-zero Δ → samples collapse onto
  the baseline Ka);
- larger Δ produces strictly larger Ka spread;
- the titrant and the non-fitted ``Ka_dye`` are both genuinely perturbable;
- the ``seed`` knob makes a whole run reproducible, optimiser included, and a
  run given no seed draws and reports one that repeats it;
- the heatmap axes perturb the inputs they name, and its centre cell (0 %, 0 %)
  is the baseline fit itself;
- ``estimated_fit_count`` matches the driver's actual per-mode workload;
- invalid configs fail fast with ``ValueError``, in words that name inputs the
  way the interface does;
- an assay without an exact Ka profile is refused, and a single perturbation
  that cannot be solved is one missing sample rather than a dead run;
- a perturbed fit below the R² floor is kept and flagged, never dropped;
- every sample keeps the whole fit behind its Ka, so the Fit Summary
  statistics can run over the samples, and the signal coefficients the data fix
  only in combination are named;
- the Sobol' design is made of independent scrambles, and the t-intervals the
  delete-one-block jackknife over them gives cover the analytic Ishigami
  indices at close to their stated 95 %.

Fits run on synthetic IDA data with the tight recovery bounds from ``conftest``
and a small ``n_trials`` — enough to converge reliably while keeping the
many-fit loops fast. A run carrying a ``seed`` repeats on its own; helpers that
compare *unseeded* runs pin the global RNG before each one so any difference is
attributable to the sensitivity ``seed`` alone. Runs that fit for real accept a
design of a few scrambles of two rows each, so they stay small; the accepted
sizes themselves are tested with the module's own values. Runs that need real
worker processes live in ``tests/integration/test_sensitivity_workers.py``.
"""

import ast
import os
import pathlib
import threading
from dataclasses import replace

import numpy as np
import pytest
from scipy.stats import t as student_t

import core.pipeline.sensitivity as sens
from core.assays.dba import DBAAssay
from core.assays.dye_alone import DyeAloneAssay
from core.assays.gda import GDAAssay
from core.assays.h2g import H2GAssay
from core.assays.hg2 import HG2Assay
from core.assays.ida import IDAAssay
from core.assays.registry import ASSAY_REGISTRY, AssayType
from core.data_processing.measurement_set import MeasurementSet
from core.optimizer.filters import calculate_fit_metrics
from core.optimizer.multistart import FitCancelled
from core.pipeline.fit_pipeline import (
    FitConfig,
    PerReplicaFitError,
    _resolve_bounds,
    fit_measurement_set,
    summarize_parameters,
)
from core.pipeline.profile import _design_rank, best_fit_by_profile
from core.pipeline.sensitivity import (
    TITRANT,
    InputSpec,
    ReplicateMode,
    SensitivityConfig,
    SensitivityMode,
    default_worker_count,
    estimated_fit_count,
    estimated_optimizer_runs,
    input_name,
    nominal_value,
    perturbable_inputs,
    run_sensitivity,
    sobol_design,
    sobol_indices_from_outputs,
    sobol_indices_with_ci,
    spec_bounds,
    spec_fraction,
)
from core.units import Q_
from tests.conftest import (
    DBA_RECOVERY_BOUNDS,
    DBA_TRUE,
    GDA_IDA_RECOVERY_BOUNDS,
    GDA_TRUE,
    H2G_TRUE,
    HG2_TRUE,
    IDA_TRUE,
    _make_dba_data,
    _make_dye_alone_data,
    _make_gda_data,
    _make_h2g_data,
    _make_hg2_data,
    _make_ida_data,
)

# Small but reliable: tight recovery bounds mean clean IDA data converges with
# few trials, so the sensitivity loops stay fast.
_N_TRIALS = 12
_N_POINTS = 20


@pytest.fixture
def ida_setup():
    """(ms, assay_cls, conditions, fit_config) for a clean IDA sensitivity run."""
    x, y = _make_ida_data(IDA_TRUE, n_points=_N_POINTS)
    ms = MeasurementSet(concentrations=x, signals=y.reshape(1, -1), replica_ids=('r0',))
    conditions = {
        'Ka_dye': Q_(IDA_TRUE['Ka_dye'], '1/M'),
        'h0': Q_(IDA_TRUE['h0'], 'M'),
        'd0': Q_(IDA_TRUE['d0'], 'M'),
    }
    fit_config = FitConfig(n_trials=_N_TRIALS, custom_bounds=GDA_IDA_RECOVERY_BOUNDS)
    return ms, IDAAssay, conditions, fit_config


_IDA_CONDITIONS = {
    'Ka_dye': Q_(IDA_TRUE['Ka_dye'], '1/M'),
    'h0': Q_(IDA_TRUE['h0'], 'M'),
    'd0': Q_(IDA_TRUE['d0'], 'M'),
}


def _noisy_ida_setup(n_replicas: int, *, per_replica: bool, noise_frac: float = 0.02):
    """(ms, assay_cls, conditions, fit_config) whose replicates carry independent noise.

    The noise has a constant sigma, *noise_frac* of the signal range, so the
    best fit stays well below R² = 1 and moves with every input.
    """
    x, y = _make_ida_data(IDA_TRUE, n_points=_N_POINTS)
    rng = np.random.default_rng(4)
    signals = np.vstack([y + rng.normal(0.0, noise_frac * np.ptp(y), y.size) for _ in range(n_replicas)])
    ms = MeasurementSet(concentrations=x, signals=signals, replica_ids=tuple(f'r{i}' for i in range(n_replicas)))
    fit_config = FitConfig(n_trials=20, custom_bounds=GDA_IDA_RECOVERY_BOUNDS, per_replica=per_replica)
    return ms, IDAAssay, dict(_IDA_CONDITIONS), fit_config


def _run(ida_setup, sens_config, *, global_seed=0, max_workers=1):
    """Run a sensitivity analysis after pinning the global (optimiser) RNG."""
    ms, assay_cls, conditions, fit_config = ida_setup
    np.random.seed(global_seed)
    return run_sensitivity(ms, assay_cls, conditions, fit_config, sens_config, max_workers=max_workers)


def _samples(result) -> np.ndarray:
    """The run's Ka samples, the ones that got a fit."""
    ka = result.sample_ka['Ka_guest']
    return ka[np.isfinite(ka)]


def _use_small_design(monkeypatch, n_blocks: int) -> None:
    """Let a run use *n_blocks* scrambles of two rows each, a sample size of ``2 * n_blocks``."""
    monkeypatch.setattr(sens, '_SOBOL_BLOCKS', n_blocks)
    monkeypatch.setattr(sens, '_SOBOL_SAMPLE_SIZES', (2 * n_blocks,))


def _heatmap(n_steps: int, sigma_pct: float = 10.0) -> SensitivityConfig:
    """An h0 x d0 grid, so every perturbation of the run is reported in a cell."""
    return SensitivityConfig(
        mode=SensitivityMode.HEATMAP,
        n_samples=1,
        input_specs={'h0': InputSpec.sigma_pct(sigma_pct), 'd0': InputSpec.sigma_pct(sigma_pct)},
        seed=2,
        x_key='h0',
        y_key='d0',
        n_steps=n_steps,
    )


# ---------------------------------------------------------------------------
# Perturbation is the only variance source
# ---------------------------------------------------------------------------


def test_negligible_delta_collapses_onto_baseline(ida_setup, monkeypatch):
    """A vanishingly small Δ leaves every Ka sample essentially at the baseline.

    Isolates that the *perturbation* is what moves Ka: with inputs unchanged the
    fit reproduces the unperturbed reference to well within 2 %.
    """
    _use_small_design(monkeypatch, 4)
    cfg = SensitivityConfig(
        mode=SensitivityMode.SOBOL, n_samples=8, input_specs={TITRANT: InputSpec.sigma_pct(1e-3)}, seed=1
    )
    result = _run(ida_setup, cfg)

    samples = _samples(result)
    baseline = result.baseline_ka['Ka_guest']
    assert samples.size == 2 * 8  # both Sobol' matrices
    # Every sample sits on top of the baseline; spread is negligible.
    assert np.allclose(samples, baseline, rtol=0.02)
    assert np.std(samples) / baseline < 0.02


def test_spread_grows_with_delta(ida_setup, monkeypatch):
    """Sample std at ±10 % strictly exceeds ±2 %, which strictly exceeds 0.

    Same seed for both runs so the only difference is the perturbation width.
    """
    _use_small_design(monkeypatch, 4)
    small = _run(ida_setup, SensitivityConfig(SensitivityMode.SOBOL, 8, {TITRANT: InputSpec.sigma_pct(2.0)}, seed=7))
    big = _run(ida_setup, SensitivityConfig(SensitivityMode.SOBOL, 8, {TITRANT: InputSpec.sigma_pct(10.0)}, seed=7))

    std_small = float(np.std(_samples(small)))
    std_big = float(np.std(_samples(big)))
    assert std_big > std_small > 0


# ---------------------------------------------------------------------------
# Both input paths (titrant vector and non-fitted Ka_dye) are perturbable
# ---------------------------------------------------------------------------


def test_titrant_alone_produces_spread(ida_setup, monkeypatch):
    """Varying the titrant alone yields a non-empty, non-degenerate Ka spread.

    Guards the titrant perturbation path, which rescales the concentration
    vector rather than a scalar condition.
    """
    _use_small_design(monkeypatch, 4)
    cfg = SensitivityConfig(
        mode=SensitivityMode.SOBOL, n_samples=8, input_specs={TITRANT: InputSpec.sigma_pct(8.0)}, seed=3
    )
    result = _run(ida_setup, cfg)

    samples = _samples(result)
    assert samples.size > 0
    assert np.std(samples) > 0


def test_ka_dye_alone_shifts_ka(ida_setup, monkeypatch):
    """Perturbing the non-fitted ``Ka_dye`` input alone moves the fitted Ka.

    A known binding-constant input carries its own uncertainty; the fit absorbs
    it into Ka_guest, so a sweep on Ka_dye alone must produce real spread that
    departs from the baseline.
    """
    _use_small_design(monkeypatch, 4)
    cfg = SensitivityConfig(
        mode=SensitivityMode.SOBOL, n_samples=8, input_specs={'Ka_dye': InputSpec.sigma_pct(15.0)}, seed=5
    )
    result = _run(ida_setup, cfg)

    samples = _samples(result)
    baseline = result.baseline_ka['Ka_guest']
    assert samples.size > 0
    assert np.std(samples) > 0
    # At least one perturbed fit lands meaningfully away from the baseline.
    assert np.max(np.abs(samples - baseline)) / baseline > 0.01


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_seed_makes_draws_reproducible(ida_setup, monkeypatch):
    """Identical sensitivity seed → identical samples; a different seed differs.

    The global optimiser RNG is pinned the same for all three runs, so only the
    sensitivity ``seed`` (which drives the perturbation draws) can change the
    result.
    """
    _use_small_design(monkeypatch, 4)
    cfg_a = SensitivityConfig(SensitivityMode.SOBOL, 8, {TITRANT: InputSpec.sigma_pct(5.0)}, seed=123)
    cfg_b = SensitivityConfig(SensitivityMode.SOBOL, 8, {TITRANT: InputSpec.sigma_pct(5.0)}, seed=456)

    r1 = _run(ida_setup, cfg_a)
    r2 = _run(ida_setup, cfg_a)
    r3 = _run(ida_setup, cfg_b)

    s1 = _samples(r1)
    s2 = _samples(r2)
    s3 = _samples(r3)

    np.testing.assert_array_equal(s1, s2)
    assert not np.array_equal(s1, s3)


def test_a_run_given_no_seed_reports_the_seed_that_repeats_it(ida_setup, monkeypatch):
    """An unseeded run draws one root seed and reports it; feeding it back reproduces the run.

    Without that, a run the user did not seed could never be shown to anyone
    else, and two unseeded runs of the same data would differ with nothing to
    say why.
    """
    _use_small_design(monkeypatch, 2)
    unseeded = SensitivityConfig(SensitivityMode.SOBOL, 4, {TITRANT: InputSpec.sigma_pct(5.0)})

    first = _run(ida_setup, unseeded)
    again = _run(ida_setup, replace(unseeded, seed=first.seed_used))
    another = _run(ida_setup, unseeded)

    assert isinstance(first.seed_used, int)
    np.testing.assert_array_equal(_samples(again), _samples(first))
    assert another.seed_used != first.seed_used
    assert not np.array_equal(_samples(another), _samples(first))


def test_a_seeded_run_reports_the_seed_it_was_given(ida_setup, monkeypatch):
    """With a seed set, that seed is what the result records."""
    _use_small_design(monkeypatch, 2)
    cfg = SensitivityConfig(SensitivityMode.SOBOL, 4, {TITRANT: InputSpec.sigma_pct(5.0)}, seed=77)

    assert _run(ida_setup, cfg).seed_used == 77


# ---------------------------------------------------------------------------
# Heatmap
# ---------------------------------------------------------------------------


def test_heatmap_center_matches_baseline_and_shape(ida_setup):
    """The (0 %, 0 %) centre cell reproduces the baseline; grid is n_steps².

    Uses a titrant × h0 axis pair to exercise one axis from each perturbation
    path. On clean data every cell converges, so no NaNs appear.
    """
    cfg = SensitivityConfig(
        mode=SensitivityMode.HEATMAP,
        n_samples=1,
        input_specs={TITRANT: InputSpec.sigma_pct(5.0), 'h0': InputSpec.sigma_pct(5.0)},
        seed=0,
        x_key=TITRANT,
        y_key='h0',
        n_steps=3,
    )
    result = _run(ida_setup, cfg)

    grid = result.ka_grid['Ka_guest']
    assert grid.shape == (3, 3)
    # linspace(-d, d, 3)[1] == 0 on both axes → the centre cell is the baseline fit itself.
    assert (result.x_offsets_pct[1], result.y_offsets_pct[1]) == (0.0, 0.0)
    assert grid[1, 1] == result.baseline_ka['Ka_guest']
    assert result.n_success == 9
    assert result.n_total == 9
    assert np.all(np.isfinite(grid))


def test_heatmap_axes_perturb_the_inputs_they_name(ida_setup, monkeypatch):
    """Cell ``[iy, ix]`` is fitted with the X input at ``x_offsets_pct[ix]`` and the Y input at ``y_offsets_pct[iy]``.

    Each perturbation reports a Ka that reads off the h0 offset alone, so the
    grid has to vary along the h0 axis and be flat along the other one. Swapping
    the two axis keys, or transposing the grid, moves the variation.
    """

    def ka_from_h0_alone(ms, assay_cls, x_base, base_conditions, offsets, fit_config):
        signal = dict.fromkeys(('I0', 'I_dye_free', 'I_dye_bound'), 0.0)
        return {'Ka_guest': 1e8 * (1 + 3 * offsets.get('h0', 0.0)), **signal}, 1.0

    monkeypatch.setattr(sens, '_fit_perturbed', ka_from_h0_alone)
    cfg = SensitivityConfig(
        mode=SensitivityMode.HEATMAP,
        n_samples=1,
        input_specs={'h0': InputSpec.sigma_pct(4.0), 'd0': InputSpec.sigma_pct(10.0)},
        seed=0,
        x_key='h0',
        y_key='d0',
        n_steps=3,
    )

    result = _run(ida_setup, cfg)

    np.testing.assert_allclose(result.x_offsets_pct, [-8.0, 0.0, 8.0])  # ±2σ of the X input, h0
    np.testing.assert_allclose(result.y_offsets_pct, [-20.0, 0.0, 20.0])  # ±2σ of the Y input, d0
    along_x = 1e8 * (1 + 3 * result.x_offsets_pct / 100)
    np.testing.assert_allclose(result.ka_grid['Ka_guest'], np.tile(along_x, (3, 1)), rtol=1e-12)


# ---------------------------------------------------------------------------
# estimated_fit_count — matches the driver's per-mode workload
# ---------------------------------------------------------------------------


def test_estimated_fit_count_scales_with_inputs():
    cfg = SensitivityConfig(SensitivityMode.SOBOL, 1024, {TITRANT: InputSpec.sigma_pct(5.0)})
    assert estimated_fit_count(cfg) == 1024 * (1 + 2)


def test_estimated_fit_count_counts_only_varying_inputs():
    """Sobol' costs N x (k + 2); an input held fixed is not one of the k."""
    cfg = SensitivityConfig(
        SensitivityMode.SOBOL,
        2048,
        {
            TITRANT: InputSpec.sigma_pct(5.0),
            'h0': InputSpec.sigma_pct(5.0),
            'd0': InputSpec.sigma_pct(0.0),
        },
    )
    assert estimated_fit_count(cfg) == 2048 * (2 + 2)


def test_estimated_fit_count_heatmap_is_grid_squared():
    cfg = SensitivityConfig(
        SensitivityMode.HEATMAP,
        200,
        {TITRANT: InputSpec.sigma_pct(5.0), 'h0': InputSpec.sigma_pct(5.0)},
        x_key=TITRANT,
        y_key='h0',
        n_steps=7,
    )
    assert estimated_fit_count(cfg) == 49


# ---------------------------------------------------------------------------
# Fail-fast contracts
# ---------------------------------------------------------------------------


@pytest.mark.parametrize('n_samples', [0, 16, 256, 512, 1000, 1536, 3072, 8192, 1024.0, np.float64(2048.0), True])
def test_sample_size_outside_the_checked_range_raises(ida_setup, n_samples):
    """A SOBOL run takes the whole numbers 1024, 2048 or 4096 and rejects anything else before fitting.

    Coverage passed at 1024 and 4096; 2048 lies between them. Smaller sizes failed the check.
    """
    ms, assay_cls, conditions, fit_config = ida_setup
    cfg = SensitivityConfig(SensitivityMode.SOBOL, n_samples, {TITRANT: InputSpec.sigma_pct(5.0)})
    with pytest.raises(ValueError, match=f'must be 1024, 2048 or 4096; {n_samples} was chosen'):
        run_sensitivity(ms, assay_cls, conditions, fit_config, cfg)


def test_every_accepted_sample_size_is_a_whole_design():
    """Each accepted size splits into eight scrambles of a power-of-two count of rows."""
    assert sens._SOBOL_BLOCKS == 8
    assert sens._SOBOL_SAMPLE_SIZES == (1024, 2048, 4096)
    for n_samples in sens._SOBOL_SAMPLE_SIZES:
        a_points, b_points = sobol_design(n_samples, 2, sens._SOBOL_BLOCKS, seed=0)
        assert a_points.shape == b_points.shape == (n_samples, 2)


def test_negative_percent_raises(ida_setup):
    ms, assay_cls, conditions, fit_config = ida_setup
    cfg = SensitivityConfig(SensitivityMode.SOBOL, 1024, {TITRANT: InputSpec.sigma_pct(-5.0)})
    with pytest.raises(ValueError, match='negative'):
        run_sensitivity(ms, assay_cls, conditions, fit_config, cfg)


@pytest.mark.parametrize(
    ('key', 'spec'),
    [(TITRANT, InputSpec.interval_pct(-200.0, 0.0)), ('h0', InputSpec.interval_abs(-2e-6, 6e-6))],
    ids=['relative', 'absolute'],
)
def test_range_reaching_below_zero_raises(ida_setup, key, spec):
    """A concentration cannot go negative, so a range that takes it there is refused before any fit."""
    cfg = SensitivityConfig(SensitivityMode.SOBOL, 1024, {key: spec}, seed=3)

    with pytest.raises(ValueError, match='below zero'):
        _run(ida_setup, cfg)


def test_all_zero_percent_raises(ida_setup):
    ms, assay_cls, conditions, fit_config = ida_setup
    cfg = SensitivityConfig(SensitivityMode.SOBOL, 1024, {TITRANT: InputSpec.sigma_pct(0.0)})
    with pytest.raises(ValueError, match='vary'):
        run_sensitivity(ms, assay_cls, conditions, fit_config, cfg)


def test_heatmap_same_axis_twice_raises(ida_setup):
    ms, assay_cls, conditions, fit_config = ida_setup
    cfg = SensitivityConfig(
        SensitivityMode.HEATMAP,
        6,
        {TITRANT: InputSpec.sigma_pct(5.0), 'h0': InputSpec.sigma_pct(5.0)},
        x_key=TITRANT,
        y_key=TITRANT,
    )
    with pytest.raises(ValueError, match='different'):
        run_sensitivity(ms, assay_cls, conditions, fit_config, cfg)


@pytest.mark.parametrize(
    ('key', 'spec'),
    [
        ('Ka_dye', InputSpec.sigma_pct(50.0)),
        ('h0', InputSpec.sigma_abs(0.5 * IDA_TRUE['h0'])),
        (TITRANT, InputSpec.interval_pct(-100.0, 10.0)),
    ],
    ids=['sigma-percent', 'sigma-absolute', 'range-to-zero'],
)
def test_heatmap_axis_reaching_zero_raises_before_any_fit(ida_setup, monkeypatch, key, spec):
    """A σ axis runs over ±2σ and a range axis over its whole range, ends included: an end at zero is refused."""
    monkeypatch.setattr(sens, '_fit_perturbed', lambda *a, **k: pytest.fail('no fit may run'))
    other = 'd0'
    cfg = SensitivityConfig(
        SensitivityMode.HEATMAP, 6, {key: spec, other: InputSpec.sigma_pct(5.0)}, x_key=key, y_key=other, n_steps=3
    )
    with pytest.raises(ValueError, match='reaches zero or below'):
        _run(ida_setup, cfg)


def test_unknown_input_key_raises(ida_setup):
    ms, assay_cls, conditions, fit_config = ida_setup
    cfg = SensitivityConfig(SensitivityMode.SOBOL, 1024, {'not_an_input': InputSpec.sigma_pct(5.0)})
    with pytest.raises(ValueError, match='an input this assay does not have'):
        run_sensitivity(ms, assay_cls, conditions, fit_config, cfg)


def test_dye_alone_has_no_ka_to_analyse():
    """DYE_ALONE has no association constant, so sensitivity does not apply."""
    x, y = _make_dye_alone_data({'slope': 5e7, 'intercept': 0.0})
    ms = MeasurementSet(concentrations=x, signals=y.reshape(1, -1), replica_ids=('r0',))
    cfg = SensitivityConfig(SensitivityMode.SOBOL, 1024, {TITRANT: InputSpec.sigma_pct(5.0)})
    with pytest.raises(ValueError, match='association constant'):
        run_sensitivity(ms, DyeAloneAssay, {}, FitConfig(n_trials=5), cfg)


@pytest.mark.parametrize(
    ('assay_cls', 'true', 'maker', 'name'),
    [
        (HG2Assay, HG2_TRUE, _make_hg2_data, 'DBA 1:2'),
        (H2GAssay, H2G_TRUE, _make_h2g_data, 'DBA 2:1'),
    ],
    ids=['HG2', 'H2G'],
)
def test_an_assay_without_an_exact_ka_profile_is_refused(monkeypatch, assay_cls, true, maker, name):
    """Two binding constants leave no exact profile, so the analysis refuses the assay before fitting anything.

    Each perturbation would have to be refitted by a multi-start search that
    lands on a different optimum from one seed to the next; its scatter would be
    read as input sensitivity, which is the one thing the analysis claims to
    separate out.
    """
    monkeypatch.setattr(sens, '_fit_perturbed', lambda *a, **k: pytest.fail('no fit may run'))
    x, y = maker(true, n_points=_N_POINTS)
    ms = MeasurementSet(concentrations=x, signals=y.reshape(1, -1), replica_ids=('r0',))
    cfg = SensitivityConfig(SensitivityMode.SOBOL, 1024, {TITRANT: InputSpec.sigma_pct(5.0)})

    with pytest.raises(ValueError, match='not available') as raised:
        run_sensitivity(ms, assay_cls, {'h0': Q_(true['h0'], 'M')}, FitConfig(n_trials=5), cfg)

    assert name in str(raised.value)


_MESSAGE_CONFIGS = {
    'negative-sigma': SensitivityConfig(SensitivityMode.SOBOL, 1024, {'h0': InputSpec.sigma_pct(-5.0)}),
    'upside-down-range': SensitivityConfig(SensitivityMode.SOBOL, 1024, {'h0': InputSpec.interval_pct(5.0, -5.0)}),
    'range-below-zero': SensitivityConfig(SensitivityMode.SOBOL, 1024, {'h0': InputSpec.interval_pct(-200.0, 0.0)}),
    'axis-to-zero': SensitivityConfig(
        SensitivityMode.HEATMAP,
        1,
        {'h0': InputSpec.sigma_pct(50.0), 'd0': InputSpec.sigma_pct(5.0)},
        x_key='h0',
        y_key='d0',
        n_steps=3,
    ),
    'absolute-titrant': SensitivityConfig(SensitivityMode.SOBOL, 1024, {TITRANT: InputSpec.sigma_abs(1e-6)}),
}


_LABELS = {'h0': '[Host]₀', 'd0': '[Dye]₀', TITRANT: 'Guest (titrant)'}


@pytest.mark.parametrize('cfg', _MESSAGE_CONFIGS.values(), ids=list(_MESSAGE_CONFIGS))
@pytest.mark.parametrize('labels', [_LABELS, None], ids=['labelled', 'unlabelled'])
def test_a_rejected_config_is_explained_without_any_internal_key(ida_setup, cfg, labels):
    """No message about an input shows a dict key or the sentinel that stands for the titrant.

    The messages reach the user unchanged, so one of those is text a chemist
    cannot act on.
    """
    ms, assay_cls, conditions, fit_config = ida_setup

    with pytest.raises(ValueError) as raised:
        run_sensitivity(ms, assay_cls, conditions, fit_config, cfg, input_labels=labels)

    message = str(raised.value)
    assert 'h0' not in message and 'd0' not in message and TITRANT not in message


@pytest.mark.parametrize('name', ['negative-sigma', 'upside-down-range', 'range-below-zero', 'axis-to-zero'])
def test_a_rejected_config_names_its_input_the_way_the_interface_does(ida_setup, name):
    """A message about a condition carries the label the user set that condition under."""
    ms, assay_cls, conditions, fit_config = ida_setup

    with pytest.raises(ValueError, match=r'\[Host\]₀'):
        run_sensitivity(ms, assay_cls, conditions, fit_config, _MESSAGE_CONFIGS[name], input_labels=_LABELS)


def test_an_input_with_no_label_is_named_in_plain_words():
    """Without labels an input is described, never keyed."""
    assert input_name(TITRANT, None) == 'the titrant'
    assert input_name(TITRANT, _LABELS) == 'Guest (titrant)'
    assert 'h0' not in input_name('h0', None)


# ---------------------------------------------------------------------------
# Reproducibility and cost
# ---------------------------------------------------------------------------


def test_seeded_run_repeats_regardless_of_global_rng(ida_setup, monkeypatch):
    """A seeded run reproduces exactly without pinning the global RNG.

    The multi-start optimiser is the other random component of a fit, so a seed
    covering only the perturbation draws would still let each pool wander and
    give a different answer on every run.
    """
    _use_small_design(monkeypatch, 2)
    ms, assay_cls, conditions, fit_config = ida_setup
    cfg = SensitivityConfig(
        mode=SensitivityMode.SOBOL,
        n_samples=4,
        input_specs={TITRANT: InputSpec.sigma_pct(5.0), 'h0': InputSpec.sigma_pct(5.0)},
        seed=11,
    )

    np.random.seed(1)
    first = _samples(run_sensitivity(ms, assay_cls, conditions, fit_config, cfg))
    np.random.seed(999)
    second = _samples(run_sensitivity(ms, assay_cls, conditions, fit_config, cfg))

    assert np.array_equal(first, second)


def _cost_config() -> SensitivityConfig:
    """A 3 x 3 heatmap: nine perturbations, enough to engage the worker pool."""
    return SensitivityConfig(
        mode=SensitivityMode.HEATMAP,
        n_samples=1,  # unused by HEATMAP; the grid sets the workload
        n_steps=3,
        input_specs={TITRANT: InputSpec.sigma_pct(4.0), 'h0': InputSpec.sigma_pct(4.0)},
        x_key=TITRANT,
        y_key='h0',
        seed=5,
    )


@pytest.mark.parametrize('max_workers', [1, 2], ids=['serial', 'parallel'])
def test_estimated_fit_count_matches_the_fits_actually_run(ida_setup, max_workers):
    """The advertised fit count matches the fits the run completes.

    Counted from the progress reports, which the run makes in this process for
    every finished fit, whether the fit ran here or in a worker. That makes the
    count valid for the parallel dispatch as well as the serial one.
    """
    ms, assay_cls, conditions, fit_config = ida_setup
    cfg = _cost_config()
    reports: list[tuple[int, int]] = []

    run_sensitivity(
        ms,
        assay_cls,
        conditions,
        fit_config,
        cfg,
        progress=lambda done, total: reports.append((done, total)),
        max_workers=max_workers,
    )

    expected = estimated_fit_count(cfg) + 1  # perturbations + the baseline
    assert len(reports) == expected
    assert reports[-1] == (expected, expected)


def test_a_run_costs_one_multistart_baseline_and_one_profile_fit_per_fitted_signal(ida_replicas_setup, monkeypatch):
    """A run does one multi-start baseline, and one profile fit per signal for it and each perturbation.

    Checked per replicate, where each perturbation fits every active
    replicate, so the estimate's replicate multiplier is exercised too. The
    fit calls are inspected here, so the run is serial: a worker process
    imports its own copy of the module, where a patch made here does not
    exist. Both dispatches call the same per-fit function.
    """
    ms, assay_cls, conditions, fit_config = ida_replicas_setup
    cfg = _cost_config()
    runs: list[int] = []
    profile_fits: list[int] = []
    real_fit, real_profile = sens.fit_measurement_set, sens.best_params_by_profile

    def counting_fit(perturbed_ms, assay, conds, config, **kwargs):
        runs.append(config.n_trials * (perturbed_ms.n_active if config.per_replica else 1))
        return real_fit(perturbed_ms, assay, conds, config, **kwargs)

    def counting_profile(assay, bounds):
        profile_fits.append(1)
        return real_profile(assay, bounds)

    monkeypatch.setattr(sens, 'fit_measurement_set', counting_fit)
    monkeypatch.setattr(sens, 'best_params_by_profile', counting_profile)
    run_sensitivity(ms, assay_cls, conditions, fit_config, cfg, max_workers=1)

    assert len(profile_fits) == (estimated_fit_count(cfg) + 1) * ms.n_active  # the baseline reports one too
    assert sum(runs) + len(profile_fits) * sens._PROFILE_FIT_RUNS == estimated_optimizer_runs(
        cfg, fit_config, ms.n_active
    )


# ---------------------------------------------------------------------------
# Replicate handling
# ---------------------------------------------------------------------------


@pytest.fixture
def ida_replicas_setup():
    """(ms, assay_cls, conditions, fit_config) with three near-clean replicas."""
    x, y = _make_ida_data(IDA_TRUE, n_points=_N_POINTS)
    rng = np.random.default_rng(0)
    signals = np.vstack([y * (1 + rng.normal(0.0, 0.002, y.size)) for _ in range(3)])
    ms = MeasurementSet(concentrations=x, signals=signals, replica_ids=('r0', 'r1', 'r2'))
    conditions = {
        'Ka_dye': Q_(IDA_TRUE['Ka_dye'], '1/M'),
        'h0': Q_(IDA_TRUE['h0'], 'M'),
        'd0': Q_(IDA_TRUE['d0'], 'M'),
    }
    fit_config = FitConfig(n_trials=_N_TRIALS, custom_bounds=GDA_IDA_RECOVERY_BOUNDS, per_replica=True)
    return ms, IDAAssay, conditions, fit_config


def _signal_name(ms, y) -> str:
    """Which of *ms*'s signals *y* is: ``'average'`` or a replica id."""
    if np.array_equal(y, ms.average_signal(active_only=True)):
        return 'average'
    return next(rid for rid in ms.replica_ids if np.array_equal(y, ms.get_replica_signal(rid)))


def _fitted_signals(setup, replicate_mode, monkeypatch) -> list[list[str]]:
    """Run a one-sample analysis; list, per fit, the signals it fitted.

    Each entry holds the ids of the replicates one fit used separately, or
    ``['average']`` when it fitted the averaged signal.
    """
    ms, assay_cls, conditions, fit_config = setup
    _use_small_design(monkeypatch, 1)
    cfg = SensitivityConfig(
        mode=SensitivityMode.SOBOL,
        n_samples=2,
        input_specs={'h0': InputSpec.sigma_pct(3.0)},
        seed=3,
        replicate_mode=replicate_mode,
    )
    seen: list[list[str]] = []
    real_fit, real_params = sens._fit_by_profile, sens.best_params_by_profile

    def fit_spy(*args):
        seen.append([])
        return real_fit(*args)

    def params_spy(assay, bounds):
        seen[-1].append(_signal_name(ms, assay.y_data.magnitude))
        return real_params(assay, bounds)

    monkeypatch.setattr(sens, '_fit_by_profile', fit_spy)
    monkeypatch.setattr(sens, 'best_params_by_profile', params_spy)

    run_sensitivity(ms, assay_cls, conditions, fit_config, cfg, max_workers=1)
    return seen


def test_follow_mode_keeps_the_configured_replicate_handling(ida_replicas_setup, monkeypatch):
    """A per-replica fit stays per-replica inside the sensitivity run.

    Replicates are the measured signal scatter; collapsing them to an average
    would drop that uncertainty from an analysis whose whole subject is
    uncertainty.
    """
    seen = _fitted_signals(ida_replicas_setup, ReplicateMode.FOLLOW, monkeypatch)

    assert seen
    assert all(signals == ['r0', 'r1', 'r2'] for signals in seen)


def test_average_mode_collapses_the_replicates(ida_replicas_setup, monkeypatch):
    """Averaging is available, but only when it is asked for."""
    seen = _fitted_signals(ida_replicas_setup, ReplicateMode.AVERAGE, monkeypatch)

    assert seen
    assert all(signals == ['average'] for signals in seen)


def test_per_replica_mode_overrides_the_fit_setting(ida_replicas_setup, monkeypatch):
    ms, assay_cls, conditions, fit_config = ida_replicas_setup
    averaging = replace(fit_config, per_replica=False)
    seen = _fitted_signals((ms, assay_cls, conditions, averaging), ReplicateMode.PER_REPLICA, monkeypatch)

    assert seen
    assert all(signals == ['r0', 'r1', 'r2'] for signals in seen)


def test_deactivated_replicas_stay_out_of_every_perturbed_fit(ida_replicas_setup, monkeypatch):
    """A replica switched off in the GUI must not reappear under perturbation."""
    ms, assay_cls, conditions, fit_config = ida_replicas_setup
    ms.set_active('r1', False)

    seen = _fitted_signals((ms, assay_cls, conditions, fit_config), ReplicateMode.FOLLOW, monkeypatch)

    assert seen
    assert all(signals == ['r0', 'r2'] for signals in seen)


# ---------------------------------------------------------------------------
# Input uncertainty specification
# ---------------------------------------------------------------------------


def test_inputs_are_ordered_with_the_titrant_last():
    """Conditions come first in declaration order, the titrant after them."""
    conditions = {
        'Ka_dye': Q_(IDA_TRUE['Ka_dye'], '1/M'),
        'h0': Q_(IDA_TRUE['h0'], 'M'),
        'd0': Q_(IDA_TRUE['d0'], 'M'),
    }
    keys = [key for key, _kind in perturbable_inputs(AssayType.IDA, conditions)]

    assert keys == ['Ka_dye', 'h0', 'd0', TITRANT]


def test_absolute_interval_spans_the_given_values():
    """An interval in the input's own unit maps onto those exact values.

    A binding constant carried over from an earlier fit arrives as an estimate
    with a low and a high bound, so the bounds are values, not offsets.
    """
    nominal = 1.68e7
    spec = InputSpec.interval_abs(1.2e7, 2.1e7)

    lo, hi = spec_bounds(spec, nominal, 'Ka_dye')

    assert nominal * (1 + lo) == pytest.approx(1.2e7)
    assert nominal * (1 + hi) == pytest.approx(2.1e7)
    # The quantile sweep stays inside those bounds.
    for q in (0.0, 0.25, 0.5, 0.75, 1.0):
        value = nominal * (1 + spec_fraction(spec, nominal, 'Ka_dye', q))
        assert 1.2e7 <= value <= 2.1e7


def test_relative_sigma_is_one_standard_deviation():
    """A 10 % sigma puts the 1-sigma quantile at ~10 % of nominal."""
    spec = InputSpec.sigma_pct(10.0)

    # 0.8413 is the standard normal CDF at +1 sigma.
    assert spec_fraction(spec, 1.0, 'h0', 0.8413447460685429) == pytest.approx(0.10, abs=1e-3)
    assert spec_fraction(spec, 1.0, 'h0', 0.5) == pytest.approx(0.0, abs=1e-9)


def test_sigma_never_drives_an_input_to_zero_or_below():
    """Truncation keeps a perturbed concentration physical.

    An untruncated Gaussian this wide would put a large share of its draws at
    or below zero, which is not a concentration.
    """
    spec = InputSpec.sigma_pct(60.0)

    fractions = [spec_fraction(spec, 1.0, 'h0', q) for q in np.linspace(1e-9, 1 - 1e-9, 200)]

    assert all(f > -1.0 for f in fractions)


def test_titrant_rejects_an_absolute_spec():
    """The titrant is a series, so it has no nominal value to measure against."""
    with pytest.raises(ValueError, match='titrant'):
        spec_bounds(InputSpec.sigma_abs(1e-6), nominal_value(TITRANT, {}), TITRANT)


# ---------------------------------------------------------------------------
# Sobol' index estimation
# ---------------------------------------------------------------------------


def _ishigami(points: np.ndarray) -> np.ndarray:
    """Ishigami function on points drawn from the unit hypercube."""
    x = -np.pi + 2 * np.pi * points
    return np.sin(x[..., 0]) + 7 * np.sin(x[..., 1]) ** 2 + 0.1 * x[..., 2] ** 4 * np.sin(x[..., 0])


def test_sobol_indices_match_the_ishigami_analytic_values():
    """The estimators reproduce a function whose indices are known exactly.

    Ishigami is the standard benchmark: its third input has zero first-order
    effect yet a substantial total effect, so a wrong estimator or a correlated
    sample pair shows up immediately rather than looking plausible.
    """
    n_base, n_inputs = 2**14, 3
    a_points, b_points = sobol_design(n_base, n_inputs, 16, seed=1)
    f_ab = []
    for column in range(n_inputs):
        mixed = a_points.copy()
        mixed[:, column] = b_points[:, column]
        f_ab.append(_ishigami(mixed))

    s1, st = sobol_indices_from_outputs(_ishigami(a_points), _ishigami(b_points), f_ab)

    assert s1 == pytest.approx([0.3139, 0.4424, 0.0], abs=0.02)
    assert st == pytest.approx([0.5576, 0.4424, 0.2437], abs=0.02)


def test_sobol_indices_agree_with_scipy():
    """The estimators give what scipy.stats.sobol_indices gives for the same outputs.

    scipy implements the same Saltelli first-order and Jansen total-order
    formulas on centred outputs, so an independent maintained implementation
    pins every term of ours.
    """
    from scipy.stats import sobol_indices

    f_a, f_b, f_ab = _ishigami_outputs(2**10, seed=3)
    s1, st = sobol_indices_from_outputs(f_a, f_b, f_ab)

    reference = sobol_indices(
        func={'f_A': f_a[np.newaxis], 'f_B': f_b[np.newaxis], 'f_AB': np.asarray(f_ab)[:, np.newaxis]},
        n=f_a.size,
    )
    np.testing.assert_allclose(s1, np.ravel(reference.first_order), rtol=1e-12, atol=1e-12)
    np.testing.assert_allclose(st, np.ravel(reference.total_order), rtol=1e-12, atol=1e-12)


def test_sobol_indices_do_not_depend_on_the_outputs_mean():
    """Adding a constant to every output changes nothing, however large the constant.

    log10(Ka) of a real run sits near 8 with a spread of a few tenths; the
    first-order indices must come out as they would for outputs centred on zero.
    """
    f_a, f_b, f_ab = _ishigami_outputs(2**8)
    shift = 1e3

    centred = sobol_indices_from_outputs(f_a, f_b, f_ab)
    shifted = sobol_indices_from_outputs(f_a + shift, f_b + shift, [ab + shift for ab in f_ab])

    np.testing.assert_allclose(shifted, centred, atol=1e-9)


def test_sobol_design_a_and_b_are_uncorrelated():
    """A and B must be uncorrelated, or the index estimators are meaningless."""
    a_points, b_points = sobol_design(2**12, 3, 16, seed=2)

    for column in range(3):
        assert abs(float(np.corrcoef(a_points[:, column], b_points[:, column])[0, 1])) < 0.05


def test_sobol_run_reports_an_index_per_varied_input(ida_setup, monkeypatch):
    """A real run attributes Ka spread across exactly the inputs that varied."""
    _use_small_design(monkeypatch, 4)
    ms, assay_cls, conditions, fit_config = ida_setup
    cfg = SensitivityConfig(
        mode=SensitivityMode.SOBOL,
        n_samples=8,
        input_specs={TITRANT: InputSpec.sigma_pct(4.0), 'h0': InputSpec.sigma_pct(4.0)},
        seed=9,
    )

    result = _run(ida_setup, cfg)

    assert set(result.sobol_s1) == set(result.ka_keys)
    assert set(result.sobol_s1['Ka_guest']) == {TITRANT, 'h0'}
    assert set(result.sobol_st['Ka_guest']) == {TITRANT, 'h0'}
    assert result.n_total == estimated_fit_count(cfg)


# ---------------------------------------------------------------------------
# Running the work across processes
# ---------------------------------------------------------------------------


def test_default_worker_count_is_usable_on_any_machine():
    """At least one worker, and never every core, whatever the machine has."""
    workers = default_worker_count()
    total = os.cpu_count() or 1

    assert workers >= 1
    assert workers <= max(1, total - 1)


def _ida_setup_with_ka(scale: float):
    """A clean IDA setup whose true Ka_guest is *scale* times the shared one."""
    true = {**IDA_TRUE, 'Ka_guest': IDA_TRUE['Ka_guest'] * scale}
    x, y = _make_ida_data(true, n_points=_N_POINTS)
    ms = MeasurementSet(concentrations=x, signals=y.reshape(1, -1), replica_ids=('r0',))
    return ms, IDAAssay, dict(_IDA_CONDITIONS), FitConfig(n_trials=6, custom_bounds=GDA_IDA_RECOVERY_BOUNDS)


def test_two_runs_at_once_in_one_process_keep_their_own_data():
    """Two analyses running side by side answer for their own measurements.

    The application runs each analysis in its own thread and can have more than
    one going — two tabs, or a new run started while the last is draining. With
    no worker processes the fits happen in this process, and one run reaching
    the other's data would report a Ka distribution belonging to different
    measurements, labelled with these ones.
    """
    setups = {scale: _ida_setup_with_ka(scale) for scale in (1.0, 4.0)}
    cfg = _heatmap(2, sigma_pct=5.0)
    alone = {scale: _run(setup, cfg) for scale, setup in setups.items()}
    together: dict[float, object] = {}

    threads = [
        threading.Thread(target=lambda s=scale: together.__setitem__(s, _run(setups[s], cfg))) for scale in setups
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert alone[4.0].ka_grid['Ka_guest'].min() > alone[1.0].ka_grid['Ka_guest'].max()
    for scale in setups:
        np.testing.assert_allclose(together[scale].ka_grid['Ka_guest'], alone[scale].ka_grid['Ka_guest'], rtol=1e-9)


def test_a_serial_run_leaves_no_state_behind_in_this_process():
    """The per-worker state belongs to worker processes; a run without them fills nothing here."""
    sens._WORKER_STATE.clear()

    _run(_ida_setup_with_ka(1.0), _heatmap(2, sigma_pct=5.0))

    assert sens._WORKER_STATE == {}


def test_the_thread_cap_is_lifted_from_this_process_again(monkeypatch):
    """The cap belongs to the worker processes started under it, never to the application.

    A library reads the variables as it loads, so they have to be in the
    environment a worker inherits; leaving them set afterwards would make this
    application's own numerical work single-threaded from the first analysis on.
    """
    monkeypatch.delenv('OMP_NUM_THREADS', raising=False)
    monkeypatch.setenv('MKL_NUM_THREADS', '4')

    with sens._thread_capped_children():
        inside = {name: os.environ.get(name) for name in sens._THREAD_LIMIT_VARS}

    assert inside['OMP_NUM_THREADS'] == '1'
    assert inside['MKL_NUM_THREADS'] == '4'  # a choice already made is left alone
    assert os.environ.get('OMP_NUM_THREADS') is None
    assert os.environ.get('MKL_NUM_THREADS') == '4'


def test_a_run_leaves_the_environment_as_it_found_it():
    """A whole analysis changes none of the thread-cap variables of this process."""
    before = {name: os.environ.get(name) for name in sens._THREAD_LIMIT_VARS}

    _run(_ida_setup_with_ka(1.0), _heatmap(2, sigma_pct=5.0))

    assert {name: os.environ.get(name) for name in sens._THREAD_LIMIT_VARS} == before


def _assert_identical(a, b) -> None:
    """Every reported number of two SOBOL results is bit-identical."""
    for field in ('sobol_s1', 'sobol_st', 'sobol_s1_ci', 'sobol_st_ci'):
        assert getattr(a, field) == getattr(b, field), field
    assert a.sample_offsets_pct.keys() == b.sample_offsets_pct.keys()
    for key in a.sample_offsets_pct:
        assert np.array_equal(a.sample_offsets_pct[key], b.sample_offsets_pct[key])
    assert np.array_equal(a.sample_ka['Ka_guest'], b.sample_ka['Ka_guest'], equal_nan=True)
    assert np.array_equal(a.sample_r2, b.sample_r2, equal_nan=True)
    assert (a.n_success, a.n_total, a.n_below_floor, a.floor) == (b.n_success, b.n_total, b.n_below_floor, b.floor)
    assert a.sample_params.keys() == b.sample_params.keys()
    for key in a.sample_params:
        assert np.array_equal(a.sample_params[key], b.sample_params[key], equal_nan=True)
    assert a.degenerate_keys == b.degenerate_keys
    assert a.sobol_rows_left_out == b.sobol_rows_left_out
    assert a.baseline_fit.parameters == b.baseline_fit.parameters
    assert a.baseline_fit.r_squared == b.baseline_fit.r_squared


def test_parallel_and_serial_produce_the_same_answer(ida_setup, monkeypatch):
    """Spreading the fits over processes must not change the result.

    Each fit carries its own seed, so the outcome cannot depend on which worker
    happened to run it or in what order the results came back. Twenty-four
    perturbations clear the minimum batch size, so the worker pool really runs,
    and four scrambles give every index a finite interval to compare.
    """
    _use_small_design(monkeypatch, 4)
    ms, assay_cls, conditions, fit_config = ida_setup
    fast = replace(fit_config, n_trials=6)
    cfg = SensitivityConfig(
        mode=SensitivityMode.SOBOL,
        n_samples=8,
        input_specs={TITRANT: InputSpec.sigma_pct(5.0)},
        seed=21,
    )
    assert estimated_fit_count(cfg) >= sens._PARALLEL_MIN_JOBS

    serial = run_sensitivity(ms, assay_cls, conditions, fast, cfg, max_workers=1)
    parallel = run_sensitivity(ms, assay_cls, conditions, fast, cfg, max_workers=2)

    assert np.all(np.isfinite(list(serial.sobol_s1_ci['Ka_guest'][TITRANT])))
    _assert_identical(serial, parallel)


def test_entry_point_calls_freeze_support_before_importing_the_interface():
    """A packaged build starts each worker by re-executing the entry point.

    Without ``freeze_support`` the worker launches a second copy of the whole
    application instead, which then does the same again; and every import made
    ahead of it the worker pays for, Qt included, because ``freeze_support``
    returns only in the process the user started. Neither shows up outside a
    frozen build, so nothing else in the suite would catch it.
    """
    entry_point = pathlib.Path(__file__).resolve().parents[2] / 'run_app.py'
    tree = ast.parse(entry_point.read_text())
    guard = next(node for node in tree.body if isinstance(node, ast.If))
    steps = [ast.unparse(node) for node in guard.body]

    assert not [step for step in map(ast.unparse, tree.body) if step.startswith(('import gui', 'from gui'))]
    freeze = steps.index('multiprocessing.freeze_support()')
    gui_import = next(i for i, step in enumerate(steps) if step.startswith('from gui.'))
    assert freeze < gui_import


# ---------------------------------------------------------------------------
# The profile fit against a multi-start search of the same signal
# ---------------------------------------------------------------------------


_DEMO_PATH = pathlib.Path(__file__).resolve().parents[2] / 'data' / 'IDA_system.txt'


@pytest.mark.parametrize('seed', [9, 13])
def test_profile_path_reports_the_per_replicate_fit_on_the_demo_data(seed):
    """The eight measured replicates of the IDA demo give the Ka the per-replicate fit reports.

    Real replicates scatter far more than synthetic ones, so near-optimal
    attempts of one replicate often fit the averaged signal a little better than
    any replicate's best fit. The perturbations are ones where picking among
    every pooled trial lands up to 1.5 % away from the best-fit rule.
    """
    from core.io import load_measurements

    ms = MeasurementSet.from_dataframe(load_measurements(_DEMO_PATH))
    rng = np.random.default_rng(500 + seed)
    scale = [1 + rng.uniform(-0.1, 0.1) for _ in range(4)]
    perturbed = MeasurementSet(
        concentrations=ms.concentrations * scale[0], signals=ms.signals, replica_ids=ms.replica_ids
    )
    conditions = {
        'Ka_dye': Q_(16.8e6 * scale[1], '1/M'),
        'h0': Q_(4.3e-6 * scale[2], 'M'),
        'd0': Q_(6e-6 * scale[3], 'M'),
    }
    config = FitConfig(per_replica=True, min_r_squared=-np.inf, n_trials=40, seed=seed)

    fast, fast_r2 = sens._fit_by_profile(perturbed, IDAAssay, conditions, config)
    multistart = fit_measurement_set(perturbed, IDAAssay, conditions, config)

    assert fast['Ka_guest'] == pytest.approx(multistart.parameters['Ka_guest'].magnitude, rel=1e-3)
    assert fast_r2 == pytest.approx(multistart.r_squared, abs=1e-6)


@pytest.mark.parametrize(('n_replicas', 'per_replica'), [(1, False), (4, True)], ids=['average', 'per_replicate'])
def test_baseline_is_the_unperturbed_sample(n_replicas, per_replica):
    """The baseline is the fit a sample with no input offset gets.

    The grid's centre cell holds the inputs as entered, so its Ka reads no
    change against the baseline, and the report's Estimate comes from the
    fitting method its spread comes from.
    """
    setup = _noisy_ida_setup(n_replicas, per_replica=per_replica)
    result = _run(setup, _heatmap(3))

    assert (result.x_offsets_pct[1], result.y_offsets_pct[1]) == (0.0, 0.0)
    assert result.ka_grid['Ka_guest'][1, 1] == result.baseline_ka['Ka_guest']
    assert result.r2_grid[1, 1] == pytest.approx(result.baseline_fit.r_squared, abs=1e-12)
    ms, assay_cls, conditions, fit_config = setup
    unperturbed, _ = sens._fit_by_profile(ms, assay_cls, conditions, fit_config)
    assert {key: value.magnitude for key, value in result.baseline_fit.parameters.items()} == unperturbed
    assert result.baseline_fit.parameter_samples is None


@pytest.mark.parametrize('per_replica', [False, True], ids=['average', 'per_replicate'])
def test_baseline_and_normal_fit_record_the_replicates_they_used(per_replica):
    """Both fits name the active replicates, so a display can tell when they were made on different ones."""
    ms, assay_cls, conditions, fit_config = _noisy_ida_setup(3, per_replica=per_replica)
    ms.set_active('r1', False)

    fit = fit_measurement_set(ms, assay_cls, conditions, fit_config)
    result = _run((ms, assay_cls, conditions, fit_config), _heatmap(1))

    assert fit.metadata['active_replica_ids'] == ['r0', 'r2']
    assert result.baseline_fit.metadata['active_replica_ids'] == ['r0', 'r2']


def _noise_replicate_setup(*, per_replica: bool = True):
    """(ms, assay_cls, conditions, fit_config) whose replicate 'r2' is pure noise.

    'r0' and 'r1' carry slight noise and clear the R² floor; 'r2' holds no
    titration curve, so a per-replicate fit leaves it out.
    """
    x, y = _make_ida_data(IDA_TRUE, n_points=_N_POINTS)
    rng = np.random.default_rng(11)
    good = [y + rng.normal(0.0, 0.002 * np.ptp(y), y.size) for _ in range(2)]
    noise = rng.normal(float(np.mean(y)), 0.3 * np.ptp(y), y.size)
    ms = MeasurementSet(concentrations=x, signals=np.vstack([*good, noise]), replica_ids=('r0', 'r1', 'r2'))
    fit_config = FitConfig(n_trials=8, custom_bounds=GDA_IDA_RECOVERY_BOUNDS, per_replica=per_replica)
    return ms, IDAAssay, dict(_IDA_CONDITIONS), fit_config


def test_baseline_keeps_the_record_of_the_replicates_it_used_and_scores_on_them():
    """The baseline names the replicate it left out, and its R² is measured on the average of the others.

    The zero-offset sample is the baseline, so it too describes the used set.
    """
    ms, assay_cls, conditions, fit_config = setup = _noise_replicate_setup()
    result = _run(setup, _heatmap(3))

    baseline = result.baseline_fit
    assert baseline.metadata['replica_ids_fit'] == ['r0', 'r1']
    assert list(baseline.metadata['replica_failures']) == ['r2']
    assay = ms.to_assay(assay_cls, conditions=conditions)
    model = assay.forward_model(np.array([baseline.parameters[k].magnitude for k in assay.parameter_keys])).magnitude
    _, used_r2 = calculate_fit_metrics(ms.signals[:2].mean(axis=0), model)
    _, all_r2 = calculate_fit_metrics(ms.signals.mean(axis=0), model)
    assert baseline.r_squared == pytest.approx(used_r2, abs=1e-12)
    assert abs(all_r2 - used_r2) > 1e-3
    assert result.ka_grid['Ka_guest'][1, 1] == result.baseline_ka['Ka_guest']
    assert result.r2_grid[1, 1] == pytest.approx(baseline.r_squared, abs=1e-12)


def test_samples_use_the_replicates_the_baseline_used(monkeypatch):
    """A replicate the baseline fit left out enters no perturbed fit, so every sample describes the same data."""
    ms, assay_cls, conditions, fit_config = setup = _noise_replicate_setup()
    real = sens.best_params_by_profile
    seen: list[str] = []

    def spy(assay, bounds):
        seen.append(_signal_name(ms, assay.y_data.magnitude))
        return real(assay, bounds)

    monkeypatch.setattr(sens, 'best_params_by_profile', spy)
    result = _run(setup, _heatmap(2))

    assert result.baseline_fit.metadata['replica_ids_fit'] == ['r0', 'r1']
    assert len(seen) == 2 * 5  # the two replicates of the zero-offset baseline and of the four cells
    assert set(seen) == {'r0', 'r1'}


@pytest.mark.parametrize('unsolvable', ['raises', 'scores-nothing'], ids=['the-solve-raises', 'no-ka-is-solvable'])
def test_a_perturbation_that_cannot_be_solved_is_one_missing_sample(monkeypatch, unsolvable):
    """A perturbed fit with no solution is NaN in the grid; the other cells are unaffected.

    A perturbed set of inputs can produce a design the exact profile cannot
    solve, and discarding thousands of finished fits over one of them would
    leave the user with nothing. The profile reports that two ways: the solve
    raises, or it returns its fallback — the coefficients at their lower bounds
    at a Ka the model cannot be evaluated at, which scores nothing. Neither is a
    fit, so neither may be counted as a sample.
    """
    setup = _noisy_ida_setup(1, per_replica=False)
    real = sens.best_params_by_profile
    unsolvable_ka = np.inf  # no association constant the model can be evaluated at

    def no_solution_for_a_shrunken_host(assay, bounds):
        if assay.h0.magnitude >= IDA_TRUE['h0']:
            return real(assay, bounds)
        if unsolvable == 'raises':
            raise np.linalg.LinAlgError('SVD did not converge in Linear Least Squares')
        return np.array([unsolvable_ka, 0.0, 0.0, 0.0])

    monkeypatch.setattr(sens, 'best_params_by_profile', no_solution_for_a_shrunken_host)
    result = _run(setup, _heatmap(3))

    assert unsolvable_ka not in result.ka_grid['Ka_guest']  # no fabricated Ka reported as a fit

    lost = np.isnan(result.r2_grid)
    assert lost.tolist() == [[True, False, False]] * 3  # h0 is the x axis, so its lowest step is one column
    assert np.array_equal(np.isnan(result.ka_grid['Ka_guest']), lost)
    assert (result.n_success, result.n_total, result.stopped) == (6, 9, False)


def test_a_baseline_no_replicate_could_be_fitted_reports_each_replicate_s_reason():
    """The analysis explains a failed baseline the way the ordinary fit does.

    The same data and settings must not say 'did not converge' here and name the
    failing replicates in the Fit Curve tab: the reasons are what the user acts on.
    """
    ms, assay_cls, conditions, fit_config = _noisy_ida_setup(2, per_replica=True)
    unreachable_floor = replace(fit_config, min_r_squared=1.0)

    with pytest.raises(PerReplicaFitError) as raised:
        run_sensitivity(ms, assay_cls, conditions, unreachable_floor, _heatmap(3), max_workers=1)

    assert set(raised.value.failures) == set(ms.active_replica_ids)
    assert 'no reference Ka' in str(raised.value)


@pytest.mark.parametrize('cancel_at', [0, 3], ids=['before-the-baseline', 'during-the-baseline'])
def test_a_run_stopped_before_it_has_a_baseline_ends_as_stopped(cancel_at):
    """Stopping during the reference fit ends the run rather than reporting a result without one.

    Every sample is compared against the baseline fit, so a run that never
    finished one has nothing to show, and the multi-start baseline is long
    enough on real data that a user can stop inside it.
    """
    ms, assay_cls, conditions, fit_config = _noisy_ida_setup(1, per_replica=False)
    checks = iter(range(100))

    with pytest.raises(FitCancelled):
        run_sensitivity(
            ms,
            assay_cls,
            conditions,
            fit_config,
            _heatmap(3),
            max_workers=1,
            should_cancel=lambda: next(checks) >= cancel_at,
        )


def test_a_run_stopped_early_says_so():
    """Cells the run never reached are NaN like failed ones; ``stopped`` tells the two apart."""
    ms, assay_cls, conditions, fit_config = _noisy_ida_setup(1, per_replica=False)
    finished: list[int] = []  # one entry per finished fit, the baseline first

    stopped = run_sensitivity(
        ms,
        assay_cls,
        conditions,
        fit_config,
        _heatmap(3),
        max_workers=1,
        progress=lambda done, total: finished.append(done),
        should_cancel=lambda: len(finished) > 4,
    )
    full = _run((ms, assay_cls, conditions, fit_config), _heatmap(3))

    assert (stopped.stopped, stopped.n_total, stopped.n_success) == (True, 4, 4)
    assert int(np.sum(np.isnan(stopped.ka_grid['Ka_guest']))) == 5
    assert (full.stopped, full.n_total) == (False, 9)


# ---------------------------------------------------------------------------
# Perturbed fits below the floor are kept and flagged
# ---------------------------------------------------------------------------


def _with_floor(setup, floor):
    ms, assay_cls, conditions, fit_config = setup
    return ms, assay_cls, conditions, replace(fit_config, min_r_squared=floor)


def _floor_among(setup, r2: np.ndarray) -> float:
    """A floor the baseline clears, with some of the fits in *r2* below it.

    On noisy data a perturbation can fit better than the nominal inputs, so
    the floor is the median of the fits worse than the unperturbed one.
    """
    ms, assay_cls, conditions, fit_config = setup
    baseline_r2 = fit_measurement_set(ms, assay_cls, conditions, fit_config).r_squared
    worse = r2[r2 < baseline_r2]
    assert worse.size >= 2
    return float(np.median(worse))


def test_sobol_keeps_and_flags_fits_below_the_floor(monkeypatch):
    """A floor between the perturbed fits flags some of them and drops none.

    The floor sits among the R² values of a first run, so some samples fall
    below it. The second run must return exactly the same fits and count those
    below the floor, with every one of them still among the samples.
    """
    _use_small_design(monkeypatch, 2)
    setup = _noisy_ida_setup(1, per_replica=False)
    cfg = SensitivityConfig(
        mode=SensitivityMode.SOBOL,
        n_samples=4,
        input_specs={'h0': InputSpec.sigma_pct(10.0), 'd0': InputSpec.sigma_pct(10.0)},
        seed=5,
    )
    probe = _run(_with_floor(setup, 0.5), cfg)
    floor = _floor_among(setup, probe.sample_r2)

    flagged = _run(_with_floor(setup, floor), cfg)

    assert flagged.floor == floor
    assert flagged.n_success == flagged.n_total == estimated_fit_count(cfg)
    np.testing.assert_array_equal(flagged.sample_ka['Ka_guest'], probe.sample_ka['Ka_guest'])
    np.testing.assert_array_equal(flagged.sample_r2, probe.sample_r2)
    assert flagged.n_below_floor == int(np.sum(flagged.sample_r2 < floor))
    assert 0 < flagged.n_below_floor < flagged.sample_r2.size
    assert _samples(flagged).size == flagged.sample_r2.size


def test_heatmap_keeps_and_flags_fits_below_the_floor():
    """Every heatmap cell keeps its best fit and its R², flagged against the floor."""
    setup = _noisy_ida_setup(1, per_replica=False)
    cfg = _heatmap(3)
    probe = _run(_with_floor(setup, 0.5), cfg)
    floor = _floor_among(setup, probe.r2_grid.ravel())

    flagged = _run(_with_floor(setup, floor), cfg)

    assert flagged.r2_grid.shape == flagged.ka_grid['Ka_guest'].shape == (3, 3)
    assert flagged.n_success == flagged.n_total == 9
    assert np.all(np.isfinite(flagged.ka_grid['Ka_guest']))
    np.testing.assert_array_equal(flagged.ka_grid['Ka_guest'], probe.ka_grid['Ka_guest'])
    np.testing.assert_array_equal(flagged.r2_grid, probe.r2_grid)
    assert flagged.n_below_floor == int(np.sum(flagged.r2_grid < floor))
    assert 0 < flagged.n_below_floor < 9


def test_baseline_below_the_floor_stops_the_run():
    """The unperturbed fit keeps the floor: when it fails, the run fails as the user's fit would."""
    setup = _with_floor(_noisy_ida_setup(1, per_replica=False), 0.999999)
    cfg = SensitivityConfig(SensitivityMode.SOBOL, 1024, {'h0': InputSpec.sigma_pct(5.0)}, seed=1)

    with pytest.raises(ValueError, match='baseline'):
        _run(setup, cfg)


# ---------------------------------------------------------------------------
# Per-sample outputs
# ---------------------------------------------------------------------------


def _record_designs(monkeypatch) -> list[tuple[np.ndarray, np.ndarray]]:
    """Every ``(A, B)`` design a run draws, in order."""
    designs = []
    real = sens.sobol_design

    def spy(*args, **kwargs):
        designs.append(real(*args, **kwargs))
        return designs[-1]

    monkeypatch.setattr(sens, 'sobol_design', spy)
    return designs


def test_samples_are_aligned_with_the_sobol_points(ida_setup, monkeypatch):
    """Sample *i* holds the offsets of Sobol' row *i* (A, then B) and the fit at those offsets."""
    _use_small_design(monkeypatch, 2)
    designs = _record_designs(monkeypatch)
    ms, assay_cls, conditions, fit_config = ida_setup
    specs = {'h0': InputSpec.sigma_pct(5.0), TITRANT: InputSpec.interval_pct(-8.0, 4.0)}
    cfg = SensitivityConfig(SensitivityMode.SOBOL, 4, specs, seed=13)

    result = _run(ida_setup, cfg)

    ((a_points, b_points),) = designs
    assert a_points.shape == b_points.shape == (4, 2)
    points = np.vstack([a_points, b_points])
    assert set(result.sample_offsets_pct) == set(specs)
    for column, key in enumerate(specs):
        expected = [100 * spec_fraction(specs[key], nominal_value(key, conditions), key, q) for q in points[:, column]]
        np.testing.assert_allclose(result.sample_offsets_pct[key], expected, rtol=1e-12)
    assert result.sample_ka['Ka_guest'].shape == result.sample_r2.shape == (8,)

    for i in (0, 4):  # the first A row and the first B row
        h0_off = result.sample_offsets_pct['h0'][i] / 100
        titrant_off = result.sample_offsets_pct[TITRANT][i] / 100
        perturbed = {**conditions, 'h0': conditions['h0'] * (1 + h0_off)}
        assay = IDAAssay(
            x_data=Q_(ms.concentrations * (1 + titrant_off), 'M'), y_data=Q_(ms.signals[0], 'au'), **perturbed
        )
        ka, r2 = best_fit_by_profile(assay, _resolve_bounds(assay, fit_config.custom_bounds))
        assert result.sample_ka['Ka_guest'][i] == pytest.approx(ka, rel=1e-9)
        assert result.sample_r2[i] == pytest.approx(r2, abs=1e-12)


# ---------------------------------------------------------------------------
# Whole fits per sample, the summary across the samples and degenerate coefficients
# ---------------------------------------------------------------------------


def test_every_sample_keeps_the_whole_fit_behind_its_ka(monkeypatch):
    """Sample *i*'s parameters are the one fit that produced its Ka and its R².

    Its Ka entries are ``sample_ka`` itself, and the model evaluated with all of
    its parameters at the sample's perturbed inputs reproduces the reported R²,
    so the coefficients belong to the same fit as the Ka.
    """
    _use_small_design(monkeypatch, 1)
    setup = _noisy_ida_setup(1, per_replica=False)
    ms, _, conditions, _ = setup
    specs = {'h0': InputSpec.sigma_pct(5.0), TITRANT: InputSpec.sigma_pct(5.0)}

    result = _run(setup, SensitivityConfig(SensitivityMode.SOBOL, 2, specs, seed=8))

    assert tuple(result.sample_params) == ASSAY_REGISTRY[AssayType.IDA].parameter_keys
    np.testing.assert_array_equal(result.sample_params['Ka_guest'], result.sample_ka['Ka_guest'])
    y = ms.average_signal(active_only=True)
    for i in range(result.sample_r2.size):
        offsets = {key: result.sample_offsets_pct[key][i] / 100 for key in specs}
        assay = IDAAssay(
            x_data=Q_(ms.concentrations * (1 + offsets[TITRANT]), 'M'),
            y_data=Q_(y, 'au'),
            **{**conditions, 'h0': conditions['h0'] * (1 + offsets['h0'])},
        )
        params = np.array([result.sample_params[key][i] for key in assay.parameter_keys])
        _, r2 = calculate_fit_metrics(y, assay.forward_model(params).magnitude)
        assert r2 == pytest.approx(result.sample_r2[i], abs=1e-12)


def test_fit_summary_statistics_run_over_the_samples(ida_setup, monkeypatch):
    """The Fit Summary rows computed over the samples keep the baseline estimate and the samples' spread."""
    _use_small_design(monkeypatch, 4)
    cfg = SensitivityConfig(SensitivityMode.SOBOL, 8, {TITRANT: InputSpec.sigma_pct(5.0)}, seed=11)
    result = _run(ida_setup, cfg)

    rows = summarize_parameters(replace(result.baseline_fit, parameter_samples=result.sample_params))

    assert {row.key for row in rows} == set(result.sample_params)
    ka = result.sample_ka['Ka_guest']
    linear, log = (next(r for r in rows if r.key == 'Ka_guest' and r.is_log is flag) for flag in (False, True))
    assert linear.estimate == result.baseline_ka['Ka_guest']
    assert (linear.stats['min'], linear.stats['max']) == (ka.min(), ka.max())
    assert linear.stats['median'] == pytest.approx(np.median(ka), rel=1e-12)
    assert log.stats['median'] == pytest.approx(np.median(np.log10(ka)), rel=1e-12)


def _single_ka_setup(assay_type: AssayType):
    """(ms, assay_cls, conditions, fit_config) of clean synthetic data for a single-Ka assay."""
    if assay_type is AssayType.IDA:
        (x, y), assay_cls, conditions = _make_ida_data(IDA_TRUE, n_points=_N_POINTS), IDAAssay, dict(_IDA_CONDITIONS)
    elif assay_type is AssayType.GDA:
        x, y = _make_gda_data(GDA_TRUE, n_points=_N_POINTS)
        assay_cls = GDAAssay
        conditions = {key: Q_(GDA_TRUE[key], '1/M' if key == 'Ka_dye' else 'M') for key in ('Ka_dye', 'h0', 'g0')}
    else:
        mode = 'HtoD' if assay_type is AssayType.DBA_HtoD else 'DtoH'
        x, y = _make_dba_data(DBA_TRUE, n_points=_N_POINTS, mode=mode)
        assay_cls, conditions = DBAAssay, {'fixed_conc': Q_(DBA_TRUE['fixed_conc'], 'M'), 'mode': mode}
    bounds = DBA_RECOVERY_BOUNDS if assay_cls is DBAAssay else GDA_IDA_RECOVERY_BOUNDS
    ms = MeasurementSet(concentrations=x, signals=y.reshape(1, -1), replica_ids=('r0',))
    return ms, assay_cls, conditions, FitConfig(n_trials=_N_TRIALS, custom_bounds=bounds)


_DYE_SIGNAL = ('I0', 'I_dye_free', 'I_dye_bound')


@pytest.mark.parametrize(
    ('assay_type', 'expected'),
    [(AssayType.IDA, _DYE_SIGNAL), (AssayType.DBA_HtoD, _DYE_SIGNAL), (AssayType.GDA, ()), (AssayType.DBA_DtoH, ())],
)
def test_degenerate_coefficients_are_those_the_design_rank_leaves_open(assay_type, expected, monkeypatch):
    """A fixed dye total makes the offset and both dye coefficients trade off; a titrated dye does not.

    Free plus bound dye add up to the dye total at every point, so when that
    total is fixed (IDA, host into dye) the three signal columns are linearly
    dependent: the design loses one rank and all three coefficients are named.
    With the dye titrated (GDA, dye into host) the design has full rank.
    """
    _use_small_design(monkeypatch, 1)
    ms, assay_cls, conditions, fit_config = _single_ka_setup(assay_type)
    cfg = SensitivityConfig(SensitivityMode.SOBOL, 2, {TITRANT: InputSpec.sigma_pct(2.0)}, seed=1)

    result = run_sensitivity(ms, assay_cls, conditions, fit_config, cfg, max_workers=1)

    assert result.degenerate_keys == expected
    assay = ms.to_assay(assay_cls, conditions=conditions, use_average=True)
    rank = _design_rank(assay, _resolve_bounds(assay, fit_config.custom_bounds), result.baseline_ka[result.ka_keys[0]])
    assert len(_DYE_SIGNAL) - rank == (1 if expected else 0)


def test_named_ida_coefficients_move_without_changing_the_signal(ida_setup, monkeypatch):
    """Raising I0 by c·d0 and lowering both dye coefficients by c leaves the IDA curve unchanged.

    That is the trade-off naming them degenerate claims: the data fix their
    combination at the baseline fit, not each coefficient.
    """
    _use_small_design(monkeypatch, 1)
    ms, assay_cls, conditions, _ = ida_setup
    cfg = SensitivityConfig(SensitivityMode.SOBOL, 2, {TITRANT: InputSpec.sigma_pct(2.0)}, seed=1)
    result = _run(ida_setup, cfg)
    assay = ms.to_assay(assay_cls, conditions=conditions, use_average=True)
    fit = np.array([result.baseline_fit.parameters[key].magnitude for key in assay.parameter_keys])
    c = 0.1 * fit[2]
    shifted = fit + np.array([0.0, c * conditions['d0'].magnitude, -c, -c])

    assert result.degenerate_keys == _DYE_SIGNAL
    np.testing.assert_allclose(assay.forward_model(shifted).magnitude, assay.forward_model(fit).magnitude, rtol=1e-9)


@pytest.mark.parametrize(
    ('free_host_signal', 'expected'), [(False, ()), (True, ('I0', 'I_H', 'I_HG', 'I_HG2'))], ids=['pinned', 'free']
)
def test_hg2_degeneracy_holds_both_binding_constants_at_the_fit(free_host_signal, expected):
    """Host is conserved (free + HG + HG2 = h0), so a fitted free-host signal trades off with the offset.

    Pinned at zero, the registry default, it leaves every fitted coefficient
    determined; once it is fitted, the offset and the three host coefficients
    are known only in combination.
    """
    x, y = _make_hg2_data(HG2_TRUE, n_points=_N_POINTS)
    assay = HG2Assay(x_data=Q_(x, 'M'), y_data=Q_(y, 'au'), h0=Q_(HG2_TRUE['h0'], 'M'))
    custom = {'I_H': (Q_(0, 'au/M'), Q_(1e12, 'au/M'))} if free_host_signal else {}
    binding = {key: HG2_TRUE[key] for key in ('Ka_HG', 'Ka_HG2')}

    assert sens._degenerate_keys(assay, _resolve_bounds(assay, custom), binding) == expected


# ---------------------------------------------------------------------------
# Replicated Sobol' designs and the jackknife intervals of the indices
# ---------------------------------------------------------------------------


def _ishigami_truth() -> tuple[np.ndarray, np.ndarray]:
    """Analytic first- and total-order indices of the Ishigami function (a = 7, b = 0.1)."""
    a, b = 7.0, 0.1
    v1 = 0.5 * (1 + b * np.pi**4 / 5) ** 2
    v2 = a**2 / 8
    v13 = 8 * b**2 * np.pi**8 / 225
    variance = v1 + v2 + v13
    return np.array([v1, v2, 0.0]) / variance, np.array([v1 + v13, v2, v13]) / variance


def _ishigami_outputs(n_base: int, seed: int = 1):
    a_points, b_points = sobol_design(n_base, 3, 16, seed=seed)
    f_ab = []
    for column in range(3):
        mixed = a_points.copy()
        mixed[:, column] = b_points[:, column]
        f_ab.append(_ishigami(mixed))
    return _ishigami(a_points), _ishigami(b_points), f_ab


def test_design_blocks_are_independent_scrambles():
    """Each block is a whole scrambled Sobol' point set of its own, and no two blocks coincide.

    The first 2^m points of a scrambled Sobol' sequence put exactly one point in
    each of 2^m equal bins of every coordinate. Each 16-row block does so in all
    four columns of A beside B, block by block in row order; the 64 rows
    together do not, as one 64-point sequence would, so the blocks are separate
    scrambles rather than one sequence cut into pieces.
    """
    n_blocks, per_block = 4, 16
    a_points, b_points = sobol_design(n_blocks * per_block, 2, n_blocks, seed=3)
    points = np.hstack([a_points, b_points])

    blocks = points.reshape(n_blocks, per_block, 4)
    for block in blocks:
        for column in block.T:
            assert np.array_equal(np.sort(np.floor(column * per_block)), np.arange(per_block))
    for column in points.T:
        assert not np.array_equal(np.sort(np.floor(column * n_blocks * per_block)), np.arange(n_blocks * per_block))
    for i in range(n_blocks):
        for j in range(i + 1, n_blocks):
            assert not np.any(np.isclose(blocks[i], blocks[j]).all(axis=1))


def test_design_reproduces_from_its_seed():
    """The same seed gives the same design, as an int or a fresh SeedSequence; another seed changes every block."""
    first = sobol_design(32, 3, 16, seed=5)
    again = sobol_design(32, 3, 16, seed=5)
    from_sequence = sobol_design(32, 3, 16, seed=np.random.SeedSequence(5))
    other = sobol_design(32, 3, 16, seed=6)

    for matrix in range(2):
        np.testing.assert_array_equal(first[matrix], again[matrix])
        np.testing.assert_array_equal(first[matrix], from_sequence[matrix])
    moved = np.hstack(first).reshape(16, 2, 6) != np.hstack(other).reshape(16, 2, 6)
    assert np.all(moved.any(axis=(1, 2)))


@pytest.mark.parametrize(('n_base', 'n_blocks'), [(16, 16), (48, 16), (40, 4), (0, 4), (6, 1)])
def test_design_size_must_be_blocks_times_a_power_of_two(n_base, n_blocks):
    with pytest.raises(ValueError, match='power of two'):
        sobol_design(n_base, 2, n_blocks, seed=0)


@pytest.mark.parametrize('n_blocks', [0, -8])
def test_design_needs_at_least_one_block(n_blocks):
    with pytest.raises(ValueError, match=f'at least one block; {n_blocks} was given'):
        sobol_design(1024, 2, n_blocks, seed=0)


def _toy_outputs():
    """Twelve rows of correlated outputs for two inputs, in four blocks of three."""
    rng = np.random.default_rng(0)
    f_a, f_b = rng.normal(size=12), rng.normal(size=12)
    f_ab = np.array([f_a + 0.5 * rng.normal(size=12), 0.3 * f_a + f_b + 0.2 * rng.normal(size=12)])
    return f_a, f_b, f_ab


def _jackknife_by_loop(f_a, f_b, f_ab, rows_by_block, level=0.95):
    """Pooled indices and their t-intervals, written out block by block.

    Returns ``(S1 and S_total concatenated, their intervals)``.
    """

    def indices(rows):
        s1, st = sobol_indices_from_outputs(f_a[rows], f_b[rows], [ab[rows] for ab in f_ab])
        return np.concatenate([s1, st])

    estimate = indices([row for rows in rows_by_block for row in rows])
    n = len(rows_by_block)
    left_out = []
    for j in range(n):
        left_out.append(indices([row for i, rows in enumerate(rows_by_block) if i != j for row in rows]))
    mean = sum(left_out) / n
    se = np.sqrt((n - 1) / n * sum((theta - mean) ** 2 for theta in left_out))
    half = student_t.ppf((1 + level) / 2, n - 1) * se
    return estimate, np.column_stack([estimate - half, estimate + half])


def _check_against_loop(result, expected) -> None:
    s1, s1_ci, st, st_ci = result
    estimate, interval = expected
    np.testing.assert_allclose(np.concatenate([s1, st]), estimate, rtol=1e-12, atol=1e-15)
    np.testing.assert_allclose(np.vstack([s1_ci, st_ci]), interval, rtol=1e-12, atol=1e-15)


@pytest.mark.parametrize('level', [0.95, 0.9])
def test_jackknife_interval_matches_a_plain_loop(level):
    """Estimate from all rows pooled, SE from leaving out each block, ± the t quantile with B − 1 degrees of freedom.

    Written out as a loop over the blocks, at two coverage levels.
    """
    f_a, f_b, f_ab = _toy_outputs()

    result = sobol_indices_with_ci(f_a, f_b, list(f_ab), 4, level=level)

    rows_by_block = [[0, 1, 2], [3, 4, 5], [6, 7, 8], [9, 10, 11]]
    _check_against_loop(result, _jackknife_by_loop(f_a, f_b, f_ab, rows_by_block, level))
    assert np.all(np.diff(np.vstack([result[1], result[3]]), axis=1) > 0)


def test_non_finite_rows_are_left_out_of_every_matrix():
    """A row with a missing output in any matrix drops out of A, B and every AB_i alike."""
    f_a, f_b, f_ab = _toy_outputs()
    f_ab[1, 4] = np.nan
    f_b[9] = np.inf

    result = sobol_indices_with_ci(f_a, f_b, list(f_ab), 4)

    _check_against_loop(result, _jackknife_by_loop(f_a, f_b, f_ab, [[0, 1, 2], [3, 5], [6, 7, 8], [10, 11]]))


def test_a_block_without_usable_rows_leaves_the_jackknife():
    """An empty block is not a replicate: the jackknife runs over the other three with two degrees of freedom."""
    f_a, f_b, f_ab = _toy_outputs()
    f_a[3:6] = np.nan

    result = sobol_indices_with_ci(f_a, f_b, list(f_ab), 4)

    _check_against_loop(result, _jackknife_by_loop(f_a, f_b, f_ab, [[0, 1, 2], [6, 7, 8], [9, 10, 11]]))


def test_fewer_than_three_usable_blocks_give_no_interval():
    """Two replicates cannot support a t-interval; fewer than two rows cannot support an index."""
    f_a, f_b, f_ab = _toy_outputs()

    two_blocks = sobol_indices_with_ci(f_a, f_b, list(f_ab), 2)
    emptied = f_a.copy()
    emptied[3:9] = np.nan
    two_left = sobol_indices_with_ci(emptied, f_b, list(f_ab), 4)
    emptied[1:] = np.nan
    one_row = sobol_indices_with_ci(emptied, f_b, list(f_ab), 4)

    for s1, s1_ci, st, st_ci in (two_blocks, two_left):
        assert np.all(np.isfinite(s1)) and np.all(np.isfinite(st))
        assert np.all(np.isnan(s1_ci)) and np.all(np.isnan(st_ci))
    assert all(np.all(np.isnan(part)) for part in one_row)
    assert one_row[1].shape == one_row[3].shape == (2, 2)


def test_interval_covers_the_ishigami_indices_at_its_stated_level():
    """Every 95 % interval holds its Ishigami index 90 to 99 % of the time.

    The designs are 300 independent ones of 1024 rows in ``_SOBOL_BLOCKS`` scrambles.

    Coverage of a calibrated interval over 300 designs scatters by about 1.3 %,
    so the bounds sit about four standard errors below and three above 95 %:
    an interval that ignores most of the scatter of the estimate falls below the
    band, and one that treats the rows of a scrambled block as independent
    draws, and so comes out several times too wide, covers every time.
    """
    n_designs, n_base = 300, 1024
    s1_true, st_true = _ishigami_truth()
    designs = [sobol_design(n_base, 3, sens._SOBOL_BLOCKS, seed=seed) for seed in range(n_designs)]
    a_points = np.stack([a for a, _ in designs])
    b_points = np.stack([b for _, b in designs])
    f_a, f_b = _ishigami(a_points), _ishigami(b_points)
    f_ab = []
    for column in range(3):
        mixed = a_points.copy()
        mixed[..., column] = b_points[..., column]
        f_ab.append(_ishigami(mixed))
    f_ab = np.stack(f_ab, axis=1)

    s1_hits = np.zeros(3)
    st_hits = np.zeros(3)
    for design in range(n_designs):
        _, s1_ci, _, st_ci = sobol_indices_with_ci(f_a[design], f_b[design], f_ab[design], sens._SOBOL_BLOCKS)
        s1_hits += (s1_ci[:, 0] <= s1_true) & (s1_true <= s1_ci[:, 1])
        st_hits += (st_ci[:, 0] <= st_true) & (st_true <= st_ci[:, 1])

    coverage = np.concatenate([s1_hits, st_hits]) / n_designs
    assert np.all((coverage >= 0.90) & (coverage <= 0.99)), coverage


def test_sobol_indices_split_the_variance_of_log_ka(ida_setup, monkeypatch):
    """The indices describe log10(Ka), whose spread a multiplicative input effect makes additive.

    Each perturbation returns ``log10 Ka = 40 x_h0 + 20 x_d0`` for offsets drawn
    uniformly in ±10 %, so Ka spans six decades and log10(Ka) is linear in the
    offsets: the analytic first-order indices are 0.8 and 0.2 and there is no
    interaction. On the raw Ka scale the few largest values would dominate the
    variance instead.
    """

    def fake_fit(ms, assay_cls, x_base, base_conditions, offsets, fit_config):
        signal = dict.fromkeys(('I0', 'I_dye_free', 'I_dye_bound'), 0.0)
        ka = 10.0 ** (8 + 40 * offsets.get('h0', 0.0) + 20 * offsets.get('d0', 0.0))  # no offset: the baseline
        return {'Ka_guest': ka, **signal}, 1.0

    monkeypatch.setattr(sens, '_fit_perturbed', fake_fit)
    cfg = SensitivityConfig(
        SensitivityMode.SOBOL,
        1024,
        {'h0': InputSpec.interval_pct(-10.0, 10.0), 'd0': InputSpec.interval_pct(-10.0, 10.0)},
        seed=4,
    )

    result = _run(ida_setup, cfg)

    for indices in (result.sobol_s1['Ka_guest'], result.sobol_st['Ka_guest']):
        assert indices['h0'] == pytest.approx(0.8, abs=0.02)
        assert indices['d0'] == pytest.approx(0.2, abs=0.02)


def test_run_intervals_leave_out_rows_without_a_fit(ida_setup, monkeypatch):
    """A perturbation without a fit takes its design row out of the run's indices and intervals.

    Each perturbation reports ``log10 Ka = 8 + 40 x_h0 + 20 x_d0`` and no fit
    where the h0 offset exceeds +8 %. The run's indices and intervals must be
    those of log10(Ka) over its own design in row order, over its
    ``_SOBOL_BLOCKS`` scrambles, with those rows left out.
    """
    designs = _record_designs(monkeypatch)
    specs = {'h0': InputSpec.interval_pct(-10.0, 10.0), 'd0': InputSpec.interval_pct(-10.0, 10.0)}

    def log_ka(h0, d0):
        return 8 + 40 * h0 + 20 * d0

    def fake_fit(ms, assay_cls, x_base, base_conditions, offsets, fit_config):
        h0, d0 = offsets.get('h0', 0.0), offsets.get('d0', 0.0)
        if h0 > 0.08:
            return None
        return {'Ka_guest': 10.0 ** log_ka(h0, d0), **dict.fromkeys(('I0', 'I_dye_free', 'I_dye_bound'), 0.0)}, 1.0

    monkeypatch.setattr(sens, '_fit_perturbed', fake_fit)
    cfg = SensitivityConfig(SensitivityMode.SOBOL, 1024, specs, seed=4)

    result = _run(ida_setup, cfg)

    ((a_points, b_points),) = designs
    conditions = ida_setup[2]
    eps = sens._QUANTILE_EPS

    def outputs(points):
        h0, d0 = (
            np.array(
                [
                    spec_fraction(specs[key], nominal_value(key, conditions), key, float(np.clip(q, eps, 1 - eps)))
                    for q in points[:, column]
                ]
            )
            for column, key in enumerate(specs)
        )
        return np.where(h0 > 0.08, np.nan, np.log10(10.0 ** log_ka(h0, d0)))

    mixed = []
    for column in range(2):
        points = a_points.copy()
        points[:, column] = b_points[:, column]
        mixed.append(outputs(points))
    s1, s1_ci, st, st_ci = sobol_indices_with_ci(outputs(a_points), outputs(b_points), mixed, sens._SOBOL_BLOCKS)
    without_fit = ~np.all(np.isfinite([outputs(a_points), outputs(b_points), *mixed]), axis=0)

    assert 0 < result.n_success < result.n_total
    assert result.sobol_rows_left_out == {'Ka_guest': int(without_fit.sum())}
    assert 0 < result.sobol_rows_left_out['Ka_guest'] < 1024
    assert np.all(np.isfinite(s1_ci)) and np.all(np.isfinite(st_ci))
    for column, key in enumerate(specs):
        assert result.sobol_s1['Ka_guest'][key] == pytest.approx(s1[column], rel=1e-12)
        assert result.sobol_st['Ka_guest'][key] == pytest.approx(st[column], rel=1e-12)
        np.testing.assert_allclose(result.sobol_s1_ci['Ka_guest'][key], s1_ci[column], rtol=1e-12)
        np.testing.assert_allclose(result.sobol_st_ci['Ka_guest'][key], st_ci[column], rtol=1e-12)
