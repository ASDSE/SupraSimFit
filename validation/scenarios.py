"""What a synthetic titration is made of, and the named grids of them.

A :class:`Scenario` fixes everything about a family of datasets except the
draw: the model, the binding regime, the design, the noise, how well the
entered inputs are said to be known and how wrongly they are entered, and any
planted misfit. The truth itself — the concentration scale, the titrant span,
the signal coefficients and the exact binding constants inside the regime — is
drawn per seed in :mod:`validation.generate`, so a scenario stands for a family
of titrations rather than one hand-picked curve.

:attr:`Scenario.id` is the store key: a stable string built from the fields, so
a row keeps its meaning across runs and across machines.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

from core.pipeline.inputs import TITRANT, InputSpec

__all__ = [
    'ASSAYS',
    'COMPETITIVE',
    'ONE_KA',
    'STATED_SIGMA',
    'TWO_KA',
    'Scenario',
    'SpecEntry',
    'conflict_grid',
    'input_aware_grid',
    'joint_grid',
    'lof_null_grid',
    'misfit_power_grid',
    'owner_grid',
    'pooling_grid',
    'range_spec_grid',
    'reference_grid',
    'robustness_grid',
    'robustness_strained_grid',
    'runs_null_grid',
    'stated_specs',
    'two_ka_weak_grid',
]

#: Assays with one binding constant and a dye whose free and bound forms both
#: emit, in the order the tables list them.
ONE_KA = ('GDA', 'IDA', 'DBA_HtoD', 'DBA_DtoH')

#: Assays with two stepwise binding constants and a dark host (``I_H`` is
#: pinned to zero by the registry, so the host contributes no signal).
TWO_KA = ('DBA_HG2', 'DBA_H2G')

#: Assays where a guest displaces a dye from the host, so the fit is given a
#: host–dye binding constant beside the concentrations.
COMPETITIVE = ('GDA', 'IDA')

ASSAYS = ONE_KA + TWO_KA

#: Stated standard deviation of each entered input, in percent of the entered
#: value: a binding constant carried over from an earlier fit is known to about
#: 10 %, and a concentration made up by weighing and pipetting to about 3 %.
#: These are the figures the shipped panel offers, and the ones every check
#: that states an uncertainty uses.
STATED_SIGMA: dict[str, float] = {'binding_constant': 10.0, 'concentration': 3.0, 'titrant': 3.0}

#: The entered inputs of each assay: the conditions the fit receives, and the
#: titrant series, which moves as one scale factor.
INPUT_KEYS: dict[str, tuple[str, ...]] = {
    'GDA': ('Ka_dye', 'h0', 'g0', TITRANT),
    'IDA': ('Ka_dye', 'h0', 'd0', TITRANT),
    'DBA_HtoD': ('fixed_conc', TITRANT),
    'DBA_DtoH': ('fixed_conc', TITRANT),
    'DBA_HG2': ('h0', TITRANT),
    'DBA_H2G': ('h0', TITRANT),
}

#: How each input key is named in an id, and which stated standard deviation it takes.
_INPUT_KIND: dict[str, str] = {'Ka_dye': 'binding_constant', TITRANT: 'titrant'}


def _kind(key: str) -> str:
    """The kind of input *key* is, which fixes its stated standard deviation."""
    return _INPUT_KIND.get(key, 'concentration')


def _short(key: str) -> str:
    """The input key as an id writes it."""
    return 'titrant' if key == TITRANT else key


@dataclass(frozen=True)
class SpecEntry:
    """One entered input and the uncertainty stated for it, in percent of the entered value.

    A positive *sigma* states a standard deviation; otherwise the entry states
    the range ``lo`` to ``hi``, which may be asymmetric. The pair is what
    :meth:`to_spec` hands the application as an
    :class:`~core.pipeline.inputs.InputSpec`.

    Attributes
    ----------
    key : str
        Input key, ``TITRANT`` for the titrant series.
    sigma : float
        Standard deviation in percent of the entered value.
    lo, hi : float
        Range in percent of the entered value.
    """

    key: str
    sigma: float = 0.0
    lo: float = 0.0
    hi: float = 0.0

    def to_spec(self) -> InputSpec:
        """The application's spec for this entry."""
        if self.sigma > 0:
            return InputSpec.sigma_pct(self.sigma)
        return InputSpec.interval_pct(self.lo, self.hi)

    @property
    def token(self) -> str:
        """This entry as an id writes it."""
        if self.sigma > 0:
            return f'{_short(self.key)}={self.sigma:g}'
        return f'{_short(self.key)}={self.lo:g}:{self.hi:g}'


def stated_specs(assay: str) -> tuple[SpecEntry, ...]:
    """Every input of *assay* stated with the standard deviation of its kind (:data:`STATED_SIGMA`)."""
    return tuple(SpecEntry(key, sigma=STATED_SIGMA[_kind(key)]) for key in INPUT_KEYS[assay])


@dataclass(frozen=True)
class Scenario:
    """One family of synthetic titrations.

    Attributes
    ----------
    assay : str
        Assay type name, one of :data:`ASSAYS`.
    regime : float
        Binding regime: the first binding constant times the fixed
        concentration the titration is run against. 0.1 is weak, 10 medium and
        1000 strong.
    n_points : int
        Titration points.
    noise : float
        Noise size as a fraction of the clean signal's range (constant) or of
        each point's own value (*proportional*).
    proportional : bool
        Noise scales with the signal instead of being constant across the
        titration.
    replicates : int
        Titrations measured; the fit is given their average and their scatter.
    ratio : float | None
        Guest to dye binding constant of a competitive assay; drawn per seed
        from ``0.01, 1, 100`` when ``None``.
    k_ratio : float | None
        First to second binding constant of a two-Ka model; drawn per seed from
        ``0.01, 1, 100`` when ``None``.
    titrant_span : float | None
        Last titrant concentration as a multiple of the fixed concentration;
        drawn per seed between 1.5 and 20 when ``None``.
    i0 : bool | None
        Whether the truth carries a signal offset; drawn per seed when ``None``.
    dark_free_dye : bool
        The free dye emits nothing, so its coefficient's lower bound is the
        truth and the fit meets an active bound.
    specs : tuple[SpecEntry, ...]
        Stated uncertainty of each entered input. Empty: every input is taken
        as exact, and the reported interval is the conditional one.
    entry_multiple : float
        Multiplies every entry error: 0 enters the inputs exactly, 1 as wrongly
        as stated, above 1 more wrongly than stated.
    shared_entries : tuple[str, ...]
        Inputs whose entry errors come from one common draw although each is
        stated on its own — a shared stock solution, stated as independent.
    misfit_sine : float
        Half-wave sine added to the clean signal of every replicate, as a
        fraction of the signal range: a departure from the model the data
        share.
    titrant_error : float
        Scale error of the entered titrant series, as a fraction, planted
        whatever the specs state.
    """

    assay: str
    regime: float = 10.0
    n_points: int = 12
    noise: float = 0.01
    proportional: bool = False
    replicates: int = 1
    ratio: float | None = None
    k_ratio: float | None = None
    titrant_span: float | None = None
    i0: bool | None = None
    dark_free_dye: bool = False
    specs: tuple[SpecEntry, ...] = ()
    entry_multiple: float = 1.0
    shared_entries: tuple[str, ...] = ()
    misfit_sine: float = 0.0
    titrant_error: float = 0.0

    def __post_init__(self) -> None:
        if self.assay not in ASSAYS:
            raise ValueError(f'{self.assay!r} is not a validated assay; they are {", ".join(ASSAYS)}.')
        unknown = {e.key for e in self.specs} - set(INPUT_KEYS[self.assay])
        if unknown:
            raise ValueError(f'{self.assay} has no input {sorted(unknown)}; its inputs are {INPUT_KEYS[self.assay]}.')
        if set(self.shared_entries) - {e.key for e in self.specs}:
            raise ValueError('shared_entries names an input that carries no spec.')

    @property
    def data_id(self) -> str:
        """Key of the titration itself: every field that fixes the truth and the measurement.

        Two scenarios that differ only in how their inputs are stated and
        entered share this key, and therefore share their truth and their
        noise: what a stated uncertainty or a wronger entry does to the fit is
        then read off the same measurements rather than off another draw.
        :attr:`entry_id` carries the same pairing into the entry errors.
        """
        parts = [self.assay, f'K={self.regime:g}', f'n={self.n_points}', f'noise={self.noise:g}']
        if self.proportional:
            parts.append('prop')
        if self.replicates != 1:
            parts.append(f'm={self.replicates}')
        if self.ratio is not None:
            parts.append(f'ratio={self.ratio:g}')
        if self.k_ratio is not None:
            parts.append(f'kr={self.k_ratio:g}')
        if self.titrant_span is not None:
            parts.append(f'span={self.titrant_span:g}')
        if self.i0 is not None:
            parts.append('I0' if self.i0 else 'noI0')
        if self.dark_free_dye:
            parts.append('dark')
        if self.misfit_sine:
            parts.append(f'sine={self.misfit_sine:g}')
        return ','.join(parts)

    @property
    def entry_id(self) -> str:
        """Key of the entry-error stream: the titration and the uncertainties stated for its inputs.

        The multiple is left out, so the standardised entry errors of the same
        titration are one draw and the entries at 2 or 5 times the stated
        uncertainty are that draw scaled. A difference between two multiples is
        then the multiple and not another draw.
        """
        parts = [self.data_id]
        if self.specs:
            parts.append('spec(' + '/'.join(e.token for e in self.specs) + ')')
            if self.shared_entries:
                parts.append('shared(' + '/'.join(_short(k) for k in self.shared_entries) + ')')
        return ','.join(parts)

    @property
    def id(self) -> str:
        """Stable, human-readable key of this scenario — the key its rows are stored under.

        The titration's own key (:attr:`data_id`), then how its inputs are
        stated and entered. ``sig`` alone stands for the assay's stated
        uncertainties (:func:`stated_specs`); anything else is spelled out
        input by input.
        """
        parts = [self.data_id]
        if self.specs:
            if self.specs == stated_specs(self.assay):
                parts.append('sig')
            else:
                parts.append('spec(' + '/'.join(e.token for e in self.specs) + ')')
            if self.entry_multiple != 1.0:
                parts.append(f'ent={self.entry_multiple:g}')
            if self.shared_entries:
                parts.append('shared(' + '/'.join(_short(k) for k in self.shared_entries) + ')')
        if self.titrant_error:
            parts.append(f'titr={self.titrant_error:g}')
        return ','.join(parts)

    @property
    def input_specs(self) -> dict[str, InputSpec]:
        """The stated uncertainties, as the fit configuration takes them."""
        return {e.key: e.to_spec() for e in self.specs}

    @property
    def exact_inputs(self) -> bool:
        """Whether every entered input is the true one."""
        return not self.specs or self.entry_multiple == 0.0


# --------------------------------------------------------------------------
# Named grids. Each is a plain function returning a list of scenarios; a check
# names one, and the check's claim is about exactly these scenarios.
# --------------------------------------------------------------------------

#: The two noise sizes every grid spans: half a percent of the signal range is
#: a clean plate reader, three percent a demanding measurement.
NOISE = (0.005, 0.03)


def owner_grid() -> list[Scenario]:
    """Every assay across the three regimes, five designs and both noise sizes, inputs exact.

    The grid the conditional interval is claimed on: 6 assays x weak, medium
    and strong binding x 5, 8, 12, 20 and 30 points x low and high noise.
    """
    return [
        Scenario(assay=assay, regime=regime, n_points=n, noise=noise)
        for assay in ASSAYS
        for regime in (0.1, 10.0, 1000.0)
        for n in (5, 8, 12, 20, 30)
        for noise in NOISE
    ]


def two_ka_weak_grid() -> list[Scenario]:
    """The weak two-Ka regime: both stepwise models, a dark host, inputs exact.

    ``K1*h0`` of 0.3, 1 and 3 against first-to-second ratios of 10, 100 and
    1000, at 12 and 30 points and three noise sizes — the scenarios of the
    weak-regime study, where the interval was found to undercover.
    """
    return [
        Scenario(assay=assay, regime=regime, k_ratio=k_ratio, n_points=n, noise=noise)
        for assay in TWO_KA
        for regime in (0.3, 1.0, 3.0)
        for k_ratio in (10.0, 100.0, 1000.0)
        for n in (12, 30)
        for noise in (0.005, 0.01, 0.03)
    ]


def input_aware_grid() -> list[Scenario]:
    """Every assay with its inputs stated and entered as wrongly as stated."""
    return [
        Scenario(assay=assay, regime=regime, n_points=n, noise=noise, specs=stated_specs(assay))
        for assay in ASSAYS
        for regime in (0.1, 10.0, 1000.0)
        for n in (8, 12, 20, 30)
        for noise in NOISE
    ]


def range_spec_grid() -> list[Scenario]:
    """Inputs stated as a range rather than a standard deviation.

    A binding constant carried over from an earlier fit arrives as a range; the
    concentration beside it is stated narrowly. The entered values are drawn
    uniformly over the stated range, which is what the range claims.
    """
    grid = []
    for assay in ASSAYS:
        keys = INPUT_KEYS[assay]
        wide = keys[0]
        narrow = keys[1] if len(keys) > 2 else TITRANT
        specs = (SpecEntry(wide, lo=-20.0, hi=20.0), SpecEntry(narrow, lo=-5.0, hi=5.0))
        for regime in (0.1, 10.0, 1000.0):
            for n in (12, 30):
                grid.append(Scenario(assay=assay, regime=regime, n_points=n, noise=0.01, specs=specs))
    return grid


def conflict_grid(multiples: tuple[float, ...]) -> list[Scenario]:
    """Inputs stated and entered at each of *multiples* times the stated uncertainty.

    At 1 the inputs are entered as wrongly as stated and a rejection is a false
    alarm; above 1 the stated uncertainty is too small and a rejection is the
    test doing its job. The null rate and the power curve are read off this one
    grid, so the rows they compare are the same designs at different multiples.
    Its designs at multiple 1 are also designs of :func:`input_aware_grid`, and
    the two carry the same ids, so ``conflict-null`` reads them from there.
    """
    return [
        Scenario(
            assay=assay,
            regime=regime,
            n_points=n,
            noise=noise,
            specs=stated_specs(assay),
            entry_multiple=multiple,
        )
        for multiple in multiples
        for assay in ASSAYS
        for regime in (0.1, 10.0, 1000.0)
        for n in (8, 20)
        for noise in NOISE
    ]


def lof_null_grid() -> list[Scenario]:
    """Replicated titrations the model does describe: the lack-of-fit F test should not fire.

    With two or more replicates the fit is measured against the scatter of the
    data themselves, which is the test with power to see a departure.
    """
    return [
        Scenario(assay=assay, regime=regime, n_points=n, noise=0.01, replicates=m, specs=stated_specs(assay))
        for assay in ONE_KA
        for regime in (0.1, 10.0, 1000.0)
        for m in (2, 3, 8)
        for n in (8, 20)
    ]


def runs_null_grid() -> list[Scenario]:
    """Single titrations the model does describe: the runs test should not fire.

    With one signal there is no scatter to measure against, and what is left is
    whether the residuals change sign as often as a fit of this model to noise
    would.
    """
    return [
        Scenario(assay=assay, regime=regime, n_points=n, noise=0.01, specs=stated_specs(assay))
        for assay in ONE_KA
        for regime in (0.1, 10.0, 1000.0)
        for n in (8, 12, 20, 30)
    ]


def misfit_power_grid() -> list[Scenario]:
    """Data the model does not describe: a smooth departure, and a titrant series off by 15 %.

    The sine is two percent of the signal range and shared by every replicate,
    which is what a systematic departure looks like; the titrant error scales
    the whole series, which no signal parameter can absorb.
    """
    grid = [
        Scenario(
            assay=assay,
            regime=regime,
            n_points=n,
            noise=0.01,
            replicates=m,
            misfit_sine=0.02,
            specs=stated_specs(assay),
        )
        for assay in ONE_KA
        for regime in (0.1, 10.0, 1000.0)
        for n, m in ((12, 4), (20, 4), (20, 1), (30, 1))
    ]
    grid += [
        Scenario(
            assay=assay,
            regime=regime,
            n_points=n,
            noise=0.005,
            titrant_error=0.15,
            specs=stated_specs(assay),
        )
        for assay in ONE_KA
        for regime in (0.1, 10.0, 1000.0)
        for n in (12, 20, 30)
    ]
    return grid


def robustness_grid() -> list[Scenario]:
    """Strains the interval is still claimed to hold under.

    Entries half as wrong as stated, a truth whose free dye is dark and whose
    offset is zero so the coefficient bounds are active, and noise that scales
    with the signal instead of being constant. In each the stated uncertainty
    still covers the entry error, so the interval's premise holds.
    """
    grid = [
        Scenario(assay=assay, regime=regime, n_points=12, noise=noise, specs=stated_specs(assay), entry_multiple=0.5)
        for assay in ASSAYS
        for regime in (0.1, 10.0, 1000.0)
        for noise in NOISE
    ]
    grid += [
        Scenario(
            assay=assay,
            regime=regime,
            n_points=12,
            noise=0.01,
            i0=False,
            dark_free_dye=True,
            specs=stated_specs(assay),
        )
        for assay in ONE_KA
        for regime in (0.1, 10.0, 1000.0)
    ]
    grid += [
        Scenario(
            assay=assay,
            regime=regime,
            n_points=12,
            noise=0.02,
            proportional=True,
            specs=stated_specs(assay),
        )
        for assay in ASSAYS
        for regime in (0.1, 10.0, 1000.0)
    ]
    return grid


def robustness_strained_grid() -> list[Scenario]:
    """Strains that break the interval's premise, so its behaviour is described rather than judged.

    Entries twice as wrong as stated, and one stock error shared by two inputs
    that were each stated on their own: in both the stated uncertainty is not
    the uncertainty the entries actually carry.
    """
    grid = [
        Scenario(assay=assay, regime=regime, n_points=12, noise=noise, specs=stated_specs(assay), entry_multiple=2.0)
        for assay in ASSAYS
        for regime in (0.1, 10.0, 1000.0)
        for noise in NOISE
    ]
    for assay in ASSAYS:
        keys = INPUT_KEYS[assay]
        shared = (keys[1], TITRANT) if len(keys) > 2 else (keys[0], TITRANT)
        for regime in (0.1, 10.0, 1000.0):
            for noise in NOISE:
                grid.append(
                    Scenario(
                        assay=assay,
                        regime=regime,
                        n_points=12,
                        noise=noise,
                        specs=stated_specs(assay),
                        shared_entries=shared,
                    )
                )
    return grid


def reference_grid() -> list[Scenario]:
    """Small designs solved twice: by the engine and by an independent profile.

    Short titrations of every assay, inputs exact, where the reference's own
    grid-and-root-finding profile is cheap enough to run on every seed.
    """
    return [
        Scenario(assay=assay, regime=regime, n_points=n, noise=0.01)
        for assay in ASSAYS
        for regime in (0.1, 10.0, 1000.0)
        for n in (8, 12)
    ]


def pooling_grid() -> list[Scenario]:
    """Replicated titrations, for the interval of their average against the interval of their points pooled.

    Three kinds of scatter: independent noise of constant size, which the F
    test assumes; noise that grows with the signal; and four replicates sharing
    one smooth departure from the model, which is the case the averaging is
    there for.
    """
    grid = []
    for assay in ONE_KA:
        for regime in (0.1, 10.0, 1000.0):
            common = dict(assay=assay, regime=regime, n_points=12, replicates=4)
            grid.append(Scenario(noise=0.02, **common))
            grid.append(Scenario(noise=0.02, proportional=True, **common))
            grid.append(Scenario(noise=0.02, misfit_sine=0.02, **common))
    return grid


def joint_grid() -> list[Scenario]:
    """Two-constant models across the regimes, for the joint region of the pair."""
    return [
        Scenario(assay=assay, regime=regime, k_ratio=k_ratio, n_points=n, noise=0.01)
        for assay in TWO_KA
        for regime in (0.3, 1.0, 10.0, 1000.0)
        for k_ratio in (10.0, 100.0, 1000.0)
        for n in (12, 30)
    ]


def before_after_grid() -> list[Scenario]:
    """Designs run through both the present engine and the previous release's search."""
    return [
        Scenario(assay=assay, regime=regime, n_points=n, noise=noise)
        for assay in ONE_KA
        for regime in (0.1, 10.0, 1000.0)
        for n in (8, 12, 20)
        for noise in NOISE
    ]


def all_scenarios() -> Iterator[Scenario]:
    """Every scenario of every named grid, for the uniqueness check."""
    for grid in (
        owner_grid,
        two_ka_weak_grid,
        input_aware_grid,
        range_spec_grid,
        lof_null_grid,
        runs_null_grid,
        misfit_power_grid,
        robustness_grid,
        robustness_strained_grid,
        reference_grid,
        pooling_grid,
        joint_grid,
        before_after_grid,
    ):
        yield from grid()
    yield from conflict_grid((1.0,))
    yield from conflict_grid((2.0, 3.0, 5.0))
