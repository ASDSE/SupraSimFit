"""Sensitivity results built by hand, for the tests of Sensitivity and of what is exported from it.

Each is a :class:`~core.pipeline.sensitivity.SensitivityResult` as a run records it, with
round numbers where a test reads them back: a variance of 0.007056 decades² is a spread
of exactly 0.084 decades, and the ends of its interval, 0.006561 and 0.007569, are
exactly 0.081 and 0.087 decades.
"""

from __future__ import annotations

import time
from dataclasses import replace

import numpy as np

from core.pipeline.budget import Budget, BudgetRow
from core.pipeline.fit_pipeline import FitResult
from core.pipeline.inputs import ADDITIONS, TITRANT, AdditionError, ErrorModel, InputSpec, SharedSource, shared_key
from core.pipeline.sensitivity import SensitivityConfig, SensitivityMode, SensitivityResult
from core.pipeline.varpro import KaInterval
from core.units import Q_

INPUTS = ('Ka_dye', 'h0', TITRANT)
CONDITIONS = {'Ka_dye': Q_(1.68e7, '1/M'), 'h0': Q_(4.3e-6, 'M'), 'd0': Q_(6e-6, 'M')}


def baseline_fit() -> FitResult:
    """The IDA fit with the inputs as entered, which every sample is compared against."""
    x = np.linspace(0.0, 1e-4, 5)
    return FitResult(
        parameters={
            'Ka_guest': Q_(2e8, '1/M'),
            'I0': Q_(100.0, 'au'),
            'I_dye_free': Q_(5e9, 'au/M'),
            'I_dye_bound': Q_(7e10, 'au/M'),
        },
        rmse=10.0,
        r_squared=0.998,
        x_fit=x,
        y_fit=x,
        assay_type='IDA',
        model_name='equilibrium_4param',
        degenerate_keys=('I0', 'I_dye_free', 'I_dye_bound'),
        conditions=dict(CONDITIONS),
        intervals={'Ka_guest': KaInterval(1.5e8, 2.7e8, False, False, 0.95, 16)},
    )


VARIANCE = 0.007056
BUDGET = Budget(
    variance=VARIANCE,
    variance_ci=(0.006561, 0.007569),
    rows=(
        BudgetRow('Ka_dye', 0.05 * VARIANCE, (2e-4, 5e-4), 0.081873, (0.079, 0.084), 0.31),
        BudgetRow('h0', 0.2 * VARIANCE, (1.1e-3, 1.7e-3), 0.075132, (0.072, 0.078), -1.2),
        BudgetRow(TITRANT, 0.6 * VARIANCE, (3.8e-3, 4.7e-3), 0.053126, (0.050, 0.056), 0.95),
    ),
)
#: Every perturbable input of the IDA assay, the one that is no source of its own included.
ELASTICITY = {'Ka_dye': 0.31, 'h0': -1.2, 'd0': 0.62, TITRANT: 0.95}


def sobol_result() -> SensitivityResult:
    """Three varied inputs, 40 A+B samples, sample 5 unfitted; S₁ ranks the titrant, [Host]₀, Kₐ,dye."""
    rng = np.random.default_rng(0)
    n = 40
    offsets = {key: rng.normal(0.0, 5.0, n) for key in INPUTS}
    ka = 2e8 * (1 + 0.01 * offsets[TITRANT])
    ka[5] = np.nan
    r2 = np.where(np.arange(n) % 3 == 0, 0.95, 0.995)
    r2[5] = np.nan
    s1 = {'Ka_dye': 0.05, 'h0': 0.2, TITRANT: 0.6}
    st = {'Ka_dye': 0.08, 'h0': 0.25, TITRANT: np.nan}
    return SensitivityResult(
        mode=SensitivityMode.SOBOL,
        assay_type='IDA',
        ka_keys=('Ka_guest',),
        baseline_ka={'Ka_guest': 2e8},
        x_offsets_pct=None,
        y_offsets_pct=None,
        ka_grid=None,
        n_success=n - 1,
        n_total=n,
        config=SensitivityConfig(
            SensitivityMode.SOBOL, n // 2, ErrorModel(specs={k: InputSpec.sigma_pct(5.0) for k in INPUTS}), seed=0
        ),
        seed_used=0,
        sobol_s1={'Ka_guest': s1},
        sobol_st={'Ka_guest': st},
        sobol_s1_ci={'Ka_guest': {k: (v - 0.03, v + 0.1) for k, v in s1.items()}},
        sobol_st_ci={'Ka_guest': {k: (v - 0.04, v + 0.2) for k, v in st.items()}},
        sample_offsets_pct=offsets,
        sample_ka={'Ka_guest': ka},
        # As a run records it: the A and the B sample of a design row are kept
        # or dropped together, so sample 5 takes its partner 25 with it.
        sample_usable={'Ka_guest': np.tile(np.isfinite(ka[: n // 2]) & np.isfinite(ka[n // 2 :]), 2)},
        sample_r2=r2,
        baseline_fit=baseline_fit(),
        sample_params={'Ka_guest': ka},
        degenerate_keys=('I0', 'I_dye_free', 'I_dye_bound'),
        budget={'Ka_guest': BUDGET},
        elasticity={'Ka_guest': ELASTICITY},
        sources=INPUTS,
        source_inputs={key: (key,) for key in INPUTS},
        n_planned=n * (len(INPUTS) + 2) + 2 * len(INPUTS),
        n_blocks_finished=8,
    )


H0_RANGE_PCT = (100 * (4.1e-6 / 4.3e-6 - 1), 100 * (4.4e-6 / 4.3e-6 - 1))


def ranged_result() -> SensitivityResult:
    """Kₐ,dye entered as the range −6 % to +4 %, [Host]₀ as 4.1–4.4 µM of 4.3 µM, the titrant as σ 5 %."""
    rng = np.random.default_rng(1)
    base = sobol_result()
    specs = {
        'Ka_dye': InputSpec.interval_pct(-6.0, 4.0),
        'h0': InputSpec.interval_abs(4.1e-6, 4.4e-6),
        TITRANT: InputSpec.sigma_pct(5.0),
    }
    offsets = {
        'Ka_dye': rng.uniform(-6.0, 4.0, 40),
        'h0': rng.uniform(*H0_RANGE_PCT, 40),
        TITRANT: base.sample_offsets_pct[TITRANT],
    }
    return replace(base, config=replace(base.config, errors=ErrorModel(specs=specs)), sample_offsets_pct=offsets)


def stopped_result(kept: int) -> SensitivityResult:
    """A run of 16 sample groups in eight blocks of two, stopped with *kept* blocks finished.

    As a run records it: every sample of an unfinished block reads as having no fit, and
    inside the finished ones the A sample of group 1 could not be fitted, which takes
    that group out of the indices.
    """
    result = sobol_result()
    n_base, per_block = 16, 2
    finished = np.arange(n_base) < kept * per_block
    fitted = np.tile(finished, 2)
    fitted[1] = False
    ka = np.where(fitted, 2e8, np.nan)
    left_out = int(n_base - finished.sum()) + 1
    return replace(
        result,
        config=replace(result.config, n_samples=n_base),
        sample_ka={'Ka_guest': ka},
        sample_r2=np.where(fitted, 0.99, np.nan),
        sample_usable={'Ka_guest': np.tile(fitted[:n_base] & fitted[n_base:], 2)},
        sample_offsets_pct={key: values[: 2 * n_base] for key, values in result.sample_offsets_pct.items()},
        sample_params=None,
        sobol_rows_left_out={'Ka_guest': left_out},
        stopped=True,
        n_blocks_finished=kept,
        n_success=int(fitted.sum()),
        n_total=int(fitted.sum()) + 1,
    )


SHARED = shared_key('Stock A')


def shared_source_result() -> SensitivityResult:
    """An IDA run over [Host]₀'s own error, a stock both concentrations share, and the additions."""
    rng = np.random.default_rng(3)
    n = 40
    sources = ('h0', SHARED, ADDITIONS)
    offsets = {'h0': rng.normal(0.0, 4.0, n), SHARED: rng.normal(0.0, 3.0, n)}
    ka = 2e8 * (1 + 0.01 * offsets['h0'])
    s1 = {'h0': 0.3, SHARED: 0.5, ADDITIONS: 0.1}
    variance = 0.01
    return replace(
        sobol_result(),
        config=SensitivityConfig(
            SensitivityMode.SOBOL,
            n // 2,
            ErrorModel(
                specs={'h0': InputSpec.sigma_pct(4.0)},
                shared=(SharedSource('Stock A', 3.0, ('h0', 'd0')),),
                additions=AdditionError(1.0, sequential=False),
            ),
            seed=0,
        ),
        sobol_s1={'Ka_guest': s1},
        sobol_st={'Ka_guest': s1},
        sobol_s1_ci={'Ka_guest': {k: (v - 0.05, v + 0.05) for k, v in s1.items()}},
        sobol_st_ci={'Ka_guest': {k: (v - 0.05, v + 0.05) for k, v in s1.items()}},
        sample_offsets_pct=offsets,
        sample_ka={'Ka_guest': ka},
        sample_usable={'Ka_guest': np.ones(n, dtype=bool)},
        sample_r2=np.full(n, 0.99),
        sample_params={'Ka_guest': ka},
        budget={
            'Ka_guest': Budget(
                variance=variance,
                variance_ci=(0.008, 0.012),
                rows=(
                    BudgetRow('h0', 0.3 * variance, (0.002, 0.004), 0.0837, (0.08, 0.087), -1.2),
                    BudgetRow(SHARED, 0.5 * variance, (0.004, 0.006), 0.0707, (0.067, 0.074), -0.6),
                    BudgetRow(ADDITIONS, 0.1 * variance, (0.0005, 0.0015), 0.0949, (0.092, 0.097), None),
                ),
            )
        },
        elasticity={'Ka_guest': {'h0': -1.2, 'd0': 0.6, 'Ka_dye': 0.3, TITRANT: 0.95}},
        sources=sources,
        source_inputs={'h0': ('h0',), SHARED: ('h0', 'd0'), ADDITIONS: ()},
    )


def heatmap_result() -> SensitivityResult:
    """[Host]₀ (σ 5 %, X) against the titrant (σ 5 %, Y) on a 3 × 3 grid, one cell with no fit."""
    x = np.linspace(-10.0, 10.0, 3)
    y = np.linspace(-10.0, 10.0, 3)
    grid = np.array([[1.8e8, 1.9e8, 2.0e8], [1.9e8, 2.0e8, 2.1e8], [2.0e8, np.nan, 2.2e8]])
    r2 = np.array([[0.95, 0.995, 0.995], [0.995, 0.995, 0.995], [0.995, np.nan, 0.95]])
    return SensitivityResult(
        mode=SensitivityMode.HEATMAP,
        assay_type='IDA',
        ka_keys=('Ka_guest',),
        baseline_ka={'Ka_guest': 2e8},
        x_offsets_pct=x,
        y_offsets_pct=y,
        ka_grid={'Ka_guest': grid},
        n_success=8,
        n_total=9,
        config=SensitivityConfig(
            SensitivityMode.HEATMAP,
            1,
            ErrorModel(specs={TITRANT: InputSpec.sigma_pct(5.0), 'h0': InputSpec.sigma_pct(5.0)}),
            x_key='h0',
            y_key=TITRANT,
            n_steps=3,
        ),
        seed_used=0,
        r2_grid=r2,
        baseline_fit=baseline_fit(),
        n_planned=9,
    )


TWO_KA_INPUTS = ('h0', TITRANT)


def two_ka_result() -> SensitivityResult:
    """A host–guest 1:2 run: the analysis reports both binding constants of the model."""
    rng = np.random.default_rng(2)
    n = 20
    keys = ('Ka_HG', 'Ka_HG2')
    baseline = {'Ka_HG': 1e6, 'Ka_HG2': 3e4}
    fit = replace(
        baseline_fit(),
        assay_type='DBA_HG2',
        parameters={'Ka_HG': Q_(1e6, '1/M'), 'Ka_HG2': Q_(3e4, '1/M'), 'I0': Q_(100.0, 'au')},
        degenerate_keys=(),
        conditions={'h0': Q_(4.3e-6, 'M')},
        intervals={},
    )
    offsets = {key: rng.normal(0.0, 5.0, n) for key in TWO_KA_INPUTS}
    indices = {key: {input_key: 0.4 for input_key in TWO_KA_INPUTS} for key in keys}
    budget = Budget(
        variance=0.01,
        variance_ci=(0.008, 0.012),
        rows=(
            BudgetRow('h0', 0.004, (0.003, 0.005), 0.0775, (0.07, 0.085), 0.4),
            BudgetRow(TITRANT, 0.004, (0.003, 0.005), 0.0775, (0.07, 0.085), 0.4),
        ),
    )
    return SensitivityResult(
        mode=SensitivityMode.SOBOL,
        assay_type='DBA_HG2',
        ka_keys=keys,
        baseline_ka=baseline,
        x_offsets_pct=None,
        y_offsets_pct=None,
        ka_grid=None,
        n_success=n,
        n_total=n,
        config=SensitivityConfig(
            SensitivityMode.SOBOL,
            n // 2,
            ErrorModel(specs={key: InputSpec.sigma_pct(5.0) for key in TWO_KA_INPUTS}),
            seed=7,
        ),
        seed_used=7,
        sobol_s1=indices,
        sobol_st=indices,
        sobol_s1_ci={key: {k: (0.3, 0.5) for k in TWO_KA_INPUTS} for key in keys},
        sobol_st_ci={key: {k: (0.3, 0.5) for k in TWO_KA_INPUTS} for key in keys},
        sample_offsets_pct=offsets,
        sample_ka={key: value * (1 + 0.01 * offsets[TITRANT]) for key, value in baseline.items()},
        sample_usable={key: np.ones(n, dtype=bool) for key in keys},
        sample_r2=np.full(n, 0.99),
        baseline_fit=fit,
        sample_params={key: value * (1 + 0.01 * offsets[TITRANT]) for key, value in baseline.items()},
        budget={key: budget for key in keys},
        elasticity={key: dict.fromkeys(TWO_KA_INPUTS, 0.5) for key in keys},
        sources=TWO_KA_INPUTS,
        source_inputs={key: (key,) for key in TWO_KA_INPUTS},
        n_blocks_finished=8,
    )


def made_on(result: SensitivityResult, ms, conditions) -> SensitivityResult:
    """*result* with its baseline fit recording *ms* and *conditions*, as a real run's baseline does."""
    record = {'data_fingerprint': ms.fingerprint(), 'active_replica_ids': ms.active_replica_ids}
    return replace(result, baseline_fit=replace(result.baseline_fit, conditions=dict(conditions), metadata=record))


def fake_run(n_fits: int, pause: float = 0.0):
    """Stand-in for ``run_sensitivity`` reporting *n_fits* finished fits, then a Sobol' result made on its inputs.

    The result carries the configuration it was asked to run, as a real run's does: the
    session checks a held run against the uncertainties it records.
    """

    def run(ms, assay_cls, conditions, _fit_config, sens_config, *args, progress, **kwargs):
        for done in range(1, n_fits + 1):
            time.sleep(pause)
            progress(done, n_fits)
        result = replace(sobol_result(), config=sens_config)
        return result if ms is None else made_on(result, ms, conditions)

    return run
