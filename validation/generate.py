"""One synthetic dataset per (scenario, seed).

The truth is drawn inside the scenario: the concentration scale, the titrant
span, the signal coefficients and the exact binding constants that put the
model in the scenario's regime. The randomness comes only from
``np.random.default_rng``, in four independent streams — the truth, the
measurement noise, the scale factor of each replicate and the entry errors —
each seeded from the seed and a key of the scenario: the titration for the
first three (:attr:`~validation.scenarios.Scenario.data_id`) and the titration
with the uncertainties stated for its inputs for the last
(:attr:`~validation.scenarios.Scenario.entry_id`). A dataset is reproducible
from ``(scenario.id, seed)`` alone; its noise does not change when the entered
inputs start moving, and its entry errors are one draw scaled by the multiple.

The draws are those of the studies these checks come from: the fixed
concentration spans 0.3 µM to 100 µM, the titrant reaches 1.5 to 20 times it,
and the two signal states differ by two to ten orders of magnitude either way,
so a scenario stands for a wide family of titrations rather than one curve.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

import numpy as np

from core.assays import ASSAY_CLASSES
from core.assays.base import BaseAssay
from core.assays.registry import ASSAY_REGISTRY, AssayType
from core.models.equilibrium import dba_signal, gda_signal, h2g_signal, hg2_signal, ida_signal
from core.pipeline.inputs import TITRANT, TITRANT_STOCK, shared_key
from core.units import Q_
from validation.scenarios import COMPETITIVE, NOISY_FACTOR, TWO_KA, Scenario, fixed_concentrations

__all__ = ['Dataset', 'dataset', 'stream_seed']

#: Unit each entered condition is passed in.
CONDITION_UNITS = {'Ka_dye': '1/M'}

#: Lowest relative entry error: a true value of a tenth of the entered one,
#: where the binding model still has a solution. An input stated to 10 % and
#: entered three times as wrongly reaches it at three standard deviations.
LOWEST_ENTRY_ERROR = -0.9

#: The signal offset a truth that carries one gets, as a fraction of the
#: offset-free signal's range.
I0_FRACTION = 0.3


def stream_seed(key: str, seed: int) -> np.random.SeedSequence:
    """Seed sequence of one stream, from a key and the seed alone.

    The key is hashed rather than used as text so that two scenarios whose keys
    share a prefix start from unrelated states.
    """
    digest = int.from_bytes(hashlib.sha256(key.encode('utf-8')).digest()[:8], 'big')
    return np.random.SeedSequence([digest, int(seed)])


@dataclass(frozen=True)
class Dataset:
    """One synthetic titration, as generated and as the fit receives it.

    Attributes
    ----------
    scenario : Scenario
        The family this dataset was drawn from.
    seed : int
        Its seed within that family.
    truth : dict[str, float]
        Every model parameter at its true value, in canonical units (1/M, a.u.,
        a.u./M), in ``assay.parameter_keys`` order.
    fixed_conc : float
        The concentration (M) the regime refers to: the host, or the fixed
        partner of a DBA titration.
    x : np.ndarray
        True titrant concentrations (M).
    clean : np.ndarray
        The model's signal at ``truth`` on ``x``, plus any planted misfit —
        what was measured before noise.
    signals : np.ndarray
        Measured signals, shape ``(replicates, points)``.
    noise_sigma : np.ndarray
        Standard deviation of the independent noise at each point of one
        replicate; a noisy replicate (:attr:`~validation.scenarios.Scenario.noisy_rows`)
        carries :data:`~validation.scenarios.NOISY_FACTOR` times it. A
        replicate scale factor is a difference between whole replicates rather
        than noise within one, so it is not in this.
    entry_errors : dict[str, float]
        Relative error of each entered input: its true value is the entered one
        times ``1 + e``.
    entry_z : dict[str, float]
        The same errors in units of what was stated: each own error stated as a
        standard deviation, divided by it, and each shared source's draw, under
        its source key. An entry stated as a range has none. Taken before the
        floor of :data:`LOWEST_ENTRY_ERROR`, so it is the draw itself.
    entered_x : np.ndarray
        Titrant concentrations as entered.
    conditions : dict[str, Any]
        Conditions as entered, as the assay constructor takes them; a diluted
        titration carries the entered titrant stock and what it contains among
        them.
    assay : BaseAssay
        The assay built from the entered conditions and the average signal.
    """

    scenario: Scenario
    seed: int
    truth: dict[str, float]
    fixed_conc: float
    x: np.ndarray
    clean: np.ndarray
    signals: np.ndarray
    noise_sigma: np.ndarray
    entry_errors: dict[str, float]
    entry_z: dict[str, float]
    entered_x: np.ndarray
    conditions: dict[str, Any]
    assay: BaseAssay

    @property
    def ka_truth(self) -> dict[str, float]:
        """The true value of every binding constant the fit is free to move."""
        return {k: self.truth[k] for k in ka_keys(self.scenario.assay)}


def ka_keys(assay: str) -> list[str]:
    """The binding-constant keys of *assay*, in parameter order."""
    meta = ASSAY_REGISTRY[AssayType[assay]]
    return [k for k in meta.param_kinds if k.startswith('Ka')]


def _truth(
    scenario: Scenario, rng: np.random.Generator
) -> tuple[dict[str, float], dict[str, Any], float, np.ndarray, float | None]:
    """Draw the truth, the true conditions, the fixed concentration, the titrant grid and the titrant stock.

    The stock is drawn last, from the final dilution the scenario states: a
    sample whose last point is a fraction ``phi`` stock was titrated from a
    stock of ``x[-1] / phi``. A scenario that states no dilution draws nothing
    and has no stock.
    """
    assay = scenario.assay
    conc = 10 ** rng.uniform(-6.5, -4)
    span = (
        float(np.exp(rng.uniform(np.log(1.5), np.log(20.0))))
        if scenario.titrant_span is None
        else scenario.titrant_span
    )
    contrast = 10 ** rng.uniform(0.3, 1.0) * (1 if rng.integers(2) else -1)
    free = 10 ** rng.uniform(6, 8)
    bound = free * 10**contrast
    x = np.linspace(span * conc / scenario.n_points, span * conc, scenario.n_points)

    if assay in COMPETITIVE:
        ratio = float(rng.choice([0.01, 1.0, 100.0])) if scenario.ratio is None else scenario.ratio
        partner = conc * rng.uniform(0.5, 2.0)
        ka = scenario.regime / conc
        truth = {'Ka_guest': ka, 'I0': 0.0, 'I_dye_free': free, 'I_dye_bound': bound}
        conditions = {'Ka_dye': ka / ratio, 'h0': conc, 'g0' if assay == 'GDA' else 'd0': partner}
    elif assay in TWO_KA:
        k_ratio = float(rng.choice([0.01, 1.0, 100.0])) if scenario.k_ratio is None else scenario.k_ratio
        second = 'Ka_HG2' if assay == 'DBA_HG2' else 'Ka_H2G'
        last = 'I_HG2' if assay == 'DBA_HG2' else 'I_H2G'
        ka = scenario.regime / conc
        truth = {
            'Ka_HG': ka,
            second: ka / k_ratio,
            'I0': 0.0,
            'I_G': free * rng.uniform(0.0, 0.3),
            'I_H': 0.0,
            'I_HG': free * 10 ** rng.uniform(0.5, 1.2),
            last: free * 10 ** rng.uniform(-0.3, 1.5),
        }
        conditions = {'h0': conc}
    else:
        truth = {'Ka_dye': scenario.regime / conc, 'I0': 0.0, 'I_dye_free': free, 'I_dye_bound': bound}
        conditions = {'fixed_conc': conc, 'mode': assay[4:]}
    if scenario.dark_free_dye:
        truth['I_dye_free'] = 0.0
    stock = None
    if scenario.dilution is not None:
        low, high = scenario.dilution
        stock = float(x[-1] / np.exp(rng.uniform(np.log(low), np.log(high))))
    return truth, conditions, conc, x, stock


def _point_totals(scenario: Scenario, conditions: dict[str, Any], x: np.ndarray, stock: float | None) -> dict[str, Any]:
    """The true conditions at each titration point, with every diluted total spelled out per point.

    A sample of volume ``V0`` that has taken up cumulative volume ``W`` of a
    stock of concentration ``c_T`` holds ``x = c_T W / (V0 + W)`` of the
    titrant, so the dilution at that point is ``x / c_T`` and a fixed total
    ``c`` that the stock does not carry stands at ``c (1 - x / c_T)``. A total
    the stock carries at the sample's own concentration does not move, and
    without a stock nothing does: the conditions are then handed on as they
    are, value for value.
    """
    if stock is None:
        return conditions
    diluted = set(fixed_concentrations(scenario.assay)) - set(scenario.stock_contains)
    return {key: value * (1.0 - x / stock) if key in diluted else value for key, value in conditions.items()}


def _clean_signal(scenario: Scenario, truth: dict[str, float], conditions: dict[str, Any], x: np.ndarray) -> np.ndarray:
    """The model's signal at *truth* on the conditions of each titration point, with ``I0`` still zero.

    A fixed total is one value, or one value per point where the titrant
    dilutes it (:func:`_point_totals`).
    """
    assay = scenario.assay
    if assay == 'GDA':
        y = gda_signal(
            I0=0.0,
            Ka_guest=truth['Ka_guest'],
            Ka_dye=conditions['Ka_dye'],
            h0=conditions['h0'],
            g0=conditions['g0'],
            d0_values=x,
            I_dye_free=truth['I_dye_free'],
            I_dye_bound=truth['I_dye_bound'],
        )
    elif assay == 'IDA':
        y = ida_signal(
            I0=0.0,
            Ka_guest=truth['Ka_guest'],
            Ka_dye=conditions['Ka_dye'],
            h0=conditions['h0'],
            d0=conditions['d0'],
            g0_values=x,
            I_dye_free=truth['I_dye_free'],
            I_dye_bound=truth['I_dye_bound'],
        )
    elif assay in ('DBA_HtoD', 'DBA_DtoH'):
        y = dba_signal(
            I0=0.0,
            Ka_dye=truth['Ka_dye'],
            x_titrant=x,
            y_fixed=conditions['fixed_conc'],
            mode=conditions['mode'],
            I_dye_free=truth['I_dye_free'],
            I_dye_bound=truth['I_dye_bound'],
        )
    elif assay == 'DBA_HG2':
        y = hg2_signal(
            I0=0.0,
            h0=conditions['h0'],
            g0_values=x,
            Ka_HG=truth['Ka_HG'],
            Ka_HG2=truth['Ka_HG2'],
            I_G=truth['I_G'],
            I_H=truth['I_H'],
            I_HG=truth['I_HG'],
            I_HG2=truth['I_HG2'],
        )
    else:
        y = h2g_signal(
            I0=0.0,
            h0=conditions['h0'],
            g0_values=x,
            Ka_HG=truth['Ka_HG'],
            Ka_H2G=truth['Ka_H2G'],
            I_G=truth['I_G'],
            I_H=truth['I_H'],
            I_HG=truth['I_HG'],
            I_H2G=truth['I_H2G'],
        )
    return np.asarray(y, dtype=float)


def _entry_errors(scenario: Scenario, rng: np.random.Generator) -> tuple[dict[str, float], dict[str, float]]:
    """Relative error of each entered input, at the scenario's multiple of what was stated, and its standard score.

    A standard deviation draws the error Gaussian and a range draws it uniform
    over the range. Inputs named in ``shared_entries`` take the same quantile
    of their own distributions, which is one stock error stated as several
    independent ones. A stated shared source is drawn once and multiplies into
    every input it loads, so an input an own spec and a source both move ends
    up at ``(1 + own)(1 + shared) - 1`` and an input only a source moves ends
    up at the source's own draw. An error below :data:`LOWEST_ENTRY_ERROR` is
    set to it.

    The standard score of an own error stated as a standard deviation is that
    error over it, and a shared source's is its own draw over its own standard
    deviation, keyed as the fit keys the source (:func:`shared_key`).
    """
    common = rng.random()
    errors, z = {}, {}
    for entry in scenario.specs:
        own = rng.random()
        quantile = common if entry.key in scenario.shared_entries else own
        if entry.sigma > 0:
            z[entry.key] = scenario.entry_multiple * float(_normal_quantile(quantile))
            error = entry.sigma / 100 * float(_normal_quantile(quantile))
        else:
            error = (entry.lo + quantile * (entry.hi - entry.lo)) / 100
        errors[entry.key] = max(scenario.entry_multiple * error, LOWEST_ENTRY_ERROR)
    for source in scenario.shared_sources:
        draw = float(_normal_quantile(rng.random()))
        z[shared_key(source.name)] = scenario.entry_multiple * draw
        shift = scenario.entry_multiple * source.sigma / 100 * draw
        for key in source.keys:
            errors[key] = max((1 + errors.get(key, 0.0)) * (1 + shift) - 1, LOWEST_ENTRY_ERROR)
    return errors, z


def _normal_quantile(u: float) -> float:
    """Standard normal quantile of *u*, by the error function's inverse."""
    from scipy.special import ndtri

    return float(ndtri(u))


def dataset(scenario: Scenario, seed: int) -> Dataset:
    """The dataset of one (scenario, seed): the truth, the measurement and the inputs as entered.

    Parameters
    ----------
    scenario : Scenario
        The family to draw from.
    seed : int
        Which draw.

    Returns
    -------
    Dataset
        The same dataset, bit for bit, for the same ``(scenario.id, seed)``.
    """
    # The truth and the noise hang on the titration alone, so a scenario and the
    # same titration with its inputs stated or mis-entered are the same
    # measurement; the entries have a stream of their own, keyed by the
    # titration and the uncertainties stated for it but not by the multiple, so
    # the entries at 2 sigma are the entries at 1 sigma doubled.
    truth_rng, noise_rng, scale_rng = (
        np.random.default_rng(child) for child in stream_seed(scenario.data_id, seed).spawn(3)
    )
    entry_rng = np.random.default_rng(stream_seed(f'{scenario.entry_id}|entry', seed))
    truth, conditions, conc, x, stock = _truth(scenario, truth_rng)
    totals = _point_totals(scenario, conditions, x, stock)
    bare = _clean_signal(scenario, truth, totals, x)
    offset = (
        I0_FRACTION * float(np.ptp(bare)) if (truth_rng.integers(2) if scenario.i0 is None else scenario.i0) else 0.0
    )
    truth['I0'] = offset
    sine = scenario.misfit_sine * float(np.ptp(bare)) * np.sin(np.pi * x / x.max()) if scenario.misfit_sine else None
    clean = bare + offset
    if sine is not None:
        clean = clean + sine
    # A shifted replicate is the same titration on other binding constants:
    # its signal coefficients, offset and planted misfit are the others'.
    rows = np.tile(clean, (scenario.replicates, 1))
    if scenario.shifted_replicates:
        moved = {k: v * scenario.replicate_shift if k in ka_keys(scenario.assay) else v for k, v in truth.items()}
        shifted = _clean_signal(scenario, moved, totals, x) + offset
        rows[list(scenario.shifted_rows)] = shifted if sine is None else shifted + sine

    if scenario.proportional:
        sigma = scenario.noise * np.abs(clean)
        if scenario.noise_floor:
            # The two parts of the noise are independent, so they add in
            # quadrature; a floor of zero is the proportional part itself.
            sigma = np.hypot(scenario.noise_floor * float(np.ptp(clean)), sigma)
    else:
        sigma = np.full(x.size, scenario.noise * float(np.ptp(clean)))
    # One scale factor per replicate multiplies its whole clean signal, offset
    # and planted misfit included, as a lamp or gain difference between runs
    # does. Without one the factors are exactly one and the stream is not drawn
    # from at all.
    factors = (
        1.0 + scenario.replicate_scale * scale_rng.standard_normal(scenario.replicates)
        if scenario.replicate_scale
        else np.ones(scenario.replicates)
    )
    scales = np.where(np.isin(np.arange(scenario.replicates), scenario.noisy_rows), NOISY_FACTOR, 1.0)
    signals = np.vstack(
        [
            factor * row + scale * sigma * noise_rng.standard_normal(x.size)
            for factor, row, scale in zip(factors, rows, scales)
        ]
    )

    errors, entry_z = _entry_errors(scenario, entry_rng)
    titrant_factor = 1.0 + errors.get(TITRANT, 0.0)
    if scenario.titrant_error:
        titrant_factor *= 1.0 + scenario.titrant_error * float(entry_rng.choice([-1.0, 1.0]))
    entered_x = x / titrant_factor
    entered = {
        key: value / (1 + errors[key]) if key in errors else value
        for key, value in conditions.items()
        if not isinstance(value, str)
    }
    entered.update({key: value for key, value in conditions.items() if isinstance(value, str)})

    assay_cls = ASSAY_CLASSES[AssayType[scenario.assay]]
    quantities = {
        key: Q_(value, CONDITION_UNITS.get(key, 'M')) if not isinstance(value, str) else value
        for key, value in entered.items()
    }
    if stock is not None and scenario.declare_stock:
        # The titrant series and the stock come from one solution, so the error
        # of the entered titrant is the error of the entered stock: the
        # dilution x / c_T, a ratio of volumes, is entered exactly.
        quantities[TITRANT_STOCK] = Q_(stock / titrant_factor, 'M')
        quantities['stock_contains'] = scenario.stock_contains
    assay = assay_cls(x_data=Q_(entered_x, 'M'), y_data=Q_(signals.mean(axis=0), 'au'), **quantities)
    return Dataset(
        scenario=scenario,
        seed=seed,
        truth={key: truth[key] for key in assay.parameter_keys},
        fixed_conc=conc,
        x=x,
        clean=clean,
        signals=signals,
        noise_sigma=sigma,
        entry_errors=errors,
        entry_z=entry_z,
        entered_x=entered_x,
        conditions=quantities,
        assay=assay,
    )
