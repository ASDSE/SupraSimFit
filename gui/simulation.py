"""What the Simulation window states and draws, with no widget (DESIGN.md §8, Simulation window).

:class:`SimulationForm` holds the settings of the window — the binding model chosen in two
steps, one :class:`Knob` per input of that model (its binding constants, fixed totals and
signal coefficients, each a value between two slider ends), the titrant concentrations
(*Even steps* or a *Custom list*), whether the additions dilute the fixed totals (the
titrant stock, as Binding model states it), the noise (the two-part law ``var(y) = floor² +
(proportional·y)²`` of :data:`core.simulation.NOISE_MODELS`, the replicates and the seed)
and a measurement file laid over the model — and :meth:`SimulationForm.simulate` turns them
into a :class:`Simulation`: the model drawn continuously, its species, and the simulated
replicates at the measurement points. Every number comes from the fitter's own forward model
(:mod:`core.simulation`), the dilution by a stated stock included (``BaseAssay.fixed_total``).

:meth:`SimulationForm.carry_to` hands a session the simulated data exactly as shown, named
after the simulation, and the conditions of the model with the titrant stock; the values of
what a fit searches for (the binding constants and signal coefficients it fits) stay here, so
the fit searches as it does with measured data.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any

import numpy as np

from core.assays.base import TITRANT_STOCK
from core.assays.registry import ASSAY_REGISTRY, KIND_UNIT, AssayType, ParamKind
from core.data_processing.measurement_set import MeasurementSet
from core.pipeline.noise import MIN_REPLICATES, noise_law
from core.simulation import build_concentration_vector, simulate_signal, simulate_species, two_part_sd
from core.units import Q_
from gui.binding import CATEGORIES
from gui.plotting.labels import THIN, fmt_species, fmt_value, plain_label, superscript
from gui.widgets.assay_conditions import ASSAY_NAMES, DBA_MODES, UNIT_CHOICES, assay_class, condition_fields

if TYPE_CHECKING:
    from gui.session_model import SessionModel

#: The concentration units a fixed total and the titrant are shown in.
CONCENTRATION_UNITS = UNIT_CHOICES['concentration'][0]

#: Points of the continuous model curve and its species.
DENSE_POINTS = 361

#: The noise model the window states: the two-part law the fitter reads off replicates.
NOISE_MODEL = 'two-part'

#: The titrant stock a model offers when dilution is chosen, as a multiple of the highest titrant
#: concentration of its even grid; shown in :data:`STOCK_UNIT`.
STOCK_FACTOR = 100
STOCK_UNIT = 'mM'

#: The noise floor a model opens with, as a share of its default curve's range.
NOISE_FLOOR_SHARE = 0.005

#: Version of a saved settings file.
SETTINGS_VERSION = 2

#: Each species' colour token, by partner (DESIGN.md §2): the dye and its complex, the guest and
#: its first complex, the free host, the second-step complex of the stepwise models.
SPECIES_TOKENS = {
    'D': 'species-dye',
    'HD': 'species-dye',
    'G': 'species-guest',
    'HG': 'species-guest',
    'H': 'species-host',
    'HG2': 'species-step2',
    'H2G': 'species-step2',
}

#: The species in a complex; every other species is free.
COMPLEXES = ('HD', 'HG', 'HG2', 'H2G')


@dataclass(frozen=True)
class _ParamDefault:
    label: str
    default: float
    lo: float
    hi: float


#: Each fitted parameter's value and slider ends when a model is chosen, in its base unit.
PARAM_DEFAULTS: dict[str, _ParamDefault] = {
    'Ka_guest': _ParamDefault('K<sub>a,guest</sub>', 1e6, 1e3, 1e9),
    'Ka_dye': _ParamDefault('K<sub>a,dye</sub>', 5e5, 1e3, 1e9),
    'Ka_HG': _ParamDefault('K<sub>a,HG</sub>', 1e6, 1e3, 1e9),
    'Ka_HG2': _ParamDefault('K<sub>a,HG₂</sub>', 2e5, 1e3, 1e9),
    'Ka_H2G': _ParamDefault('K<sub>a,H₂G</sub>', 2e5, 1e3, 1e9),
    'I0': _ParamDefault('I<sub>0</sub>', 0.0, -1e3, 1e3),
    'I_dye_free': _ParamDefault('I<sub>dye,free</sub>', 5e7, 0.0, 5e8),
    'I_dye_bound': _ParamDefault('I<sub>dye,bound</sub>', 3e8, 0.0, 1e9),
    'I_G': _ParamDefault('I<sub>G</sub>', 1e6, 0.0, 1e8),
    'I_H': _ParamDefault('I<sub>H</sub>', 0.0, 0.0, 1e8),
    'I_HG': _ParamDefault('I<sub>HG</sub>', 1e7, 0.0, 1e8),
    'I_HG2': _ParamDefault('I<sub>HG₂</sub>', 5e6, 0.0, 1e8),
    'I_H2G': _ParamDefault('I<sub>H₂G</sub>', 5e6, 0.0, 1e8),
    'slope': _ParamDefault('slope', 5e10, 0.0, 1e11),
    'intercept': _ParamDefault('intercept', 100.0, -1e4, 1e4),
}

#: Where a model's own values differ from :data:`PARAM_DEFAULTS`: the IDA demo's fit, so the
#: window opens on the curve of a real titration.
MODEL_DEFAULTS: dict[AssayType, dict[str, _ParamDefault]] = {
    AssayType.IDA: {
        'Ka_dye': _ParamDefault('K<sub>a,dye</sub>', 1.68e7, 1e4, 1e10),
        'Ka_guest': _ParamDefault('K<sub>a,guest</sub>', 2.81e8, 1e5, 1e11),
        'I0': _ParamDefault('I<sub>0</sub>', 9510.0, 0.0, 1e4),
        'I_dye_free': _ParamDefault('I<sub>dye,free</sub>', 5.09e8, 0.0, 1e9),
        'I_dye_bound': _ParamDefault('I<sub>dye,bound</sub>', 6.09e10, 0.0, 1e11),
    },
}

#: The highest titrant concentration of each model's even grid, in M.
TITRANT_STOP: dict[AssayType, float] = {
    AssayType.GDA: 30e-6,
    AssayType.IDA: 9e-6,
    AssayType.DBA_HtoD: 50e-6,
    AssayType.DBA_DtoH: 50e-6,
    AssayType.DYE_ALONE: 20e-6,
    AssayType.DBA_HG2: 1.2e-3,
    AssayType.DBA_H2G: 6e-4,
}

_SUPER_DIGITS = '⁰¹²³⁴⁵⁶⁷⁸⁹⁻'
_FROM_SUPER = str.maketrans(_SUPER_DIGITS, '0123456789-')
_DECADE = re.compile(rf'^10([{_SUPER_DIGITS}]+)$')


#: The help the toolbar's Help button opens.
class SimulationProblem(ValueError):
    """A setting the window cannot take, with a sentence written for the user."""


# ── Numbers as the window writes and reads them ─────────────────────────────────────


def parse_number(text: str) -> float | None:
    """The number *text* states as typed or as shown — ``1.68e7``, ``1.68 × 10⁷``, ``10¹¹``, ``9 510`` —
    or ``None``."""
    t = re.sub(r'[\s  ]', '', text).replace('−', '-')
    decade = _DECADE.match(t)
    if decade:
        t = '1e' + decade.group(1).translate(_FROM_SUPER)
    t = t.replace('×10', 'e').translate(_FROM_SUPER)
    try:
        value = float(t)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def value_text(value: float) -> str:
    """A value as a field shows it: ``9 510``, ``4.3``, ``1.68 × 10⁷``, with every figure it holds up to six."""
    if value == 0:
        return '0'
    a = abs(value)
    if 1e-2 <= a < 1e5:
        text = f'{value:.6g}'
        if 'e' not in text and a >= 1000:
            whole, _, frac = text.partition('.')
            sign = '−' if whole.startswith('-') else ''
            digits = whole.lstrip('-')
            groups = []
            while digits:
                groups.insert(0, digits[-3:])
                digits = digits[:-3]
            text = sign + THIN.join(groups) + (f'.{frac}' if frac else '')
        return text.replace('-', '−')
    e = math.floor(math.log10(a))
    mantissa = f'{value / 10.0**e:.6g}'.replace('-', '−')
    return f'{mantissa}{THIN}×{THIN}10{superscript(e)}'


def end_text(value: float) -> str:
    """A slider end as it stands beside the slider: ``10⁴`` for a decade from 10⁴ up, else as a field shows it."""
    if value > 0:
        e = math.log10(value)
        if abs(e - round(e)) < 1e-12 and round(e) >= 4:
            return f'10{superscript(round(e))}'
    return value_text(value)


def _three_figures(value: float) -> float:
    """*value* to three significant figures: what a slider sets, so the field shows the very value used."""
    return float(f'{value:.3g}')


def unit_text(unit: str) -> str:
    """A base unit as the window writes it."""
    return {'1/M': 'M⁻¹', 'M⁻¹': 'M⁻¹', 'au': 'a.u.', 'au/M': 'a.u./M', 'M': 'M'}[unit]


# ── Knobs ───────────────────────────────────────────────────────────────────────────


@dataclass
class Knob:
    """One input of the model: its value between two slider ends, in its base unit.

    *kind* is ``'binding'`` (an association constant, on a log slider), ``'concentration'``
    (a fixed total, shown in *unit*) or ``'signal'`` (a signal offset or coefficient).
    *condition* says whether the model takes it as an entered condition (a fixed total, or
    a binding constant the user knows, like Kₐ,dye of an IDA) rather than a parameter a fit
    searches for.
    """

    key: str
    label: str
    kind: str
    base_unit: str
    value: float
    lo: float
    hi: float
    condition: bool
    unit: str = ''

    @property
    def log(self) -> bool:
        return self.kind == 'binding'

    @property
    def scale(self) -> float:
        """One shown unit in the base unit."""
        if self.kind != 'concentration':
            return 1.0
        return float(Q_(1.0, self.unit).to('M').magnitude)

    @property
    def shown_unit(self) -> str:
        return self.unit if self.kind == 'concentration' else unit_text(self.base_unit)

    def pos(self) -> float:
        """Where the value sits between the ends, 0 to 1."""
        if self.log:
            return (math.log10(self.value) - math.log10(self.lo)) / (math.log10(self.hi) - math.log10(self.lo))
        return (self.value - self.lo) / (self.hi - self.lo)

    def decades(self) -> int:
        """The decade ticks of a log slider whose ends are whole decades apart; 0 otherwise."""
        if not self.log:
            return 0
        span = math.log10(self.hi / self.lo)
        return round(span) if abs(span - round(span)) < 1e-9 and round(span) <= 12 else 0

    def at(self, pos: float) -> float:
        """The value at *pos* on the slider, to three significant figures."""
        pos = min(max(pos, 0.0), 1.0)
        if self.log:
            raw = 10.0 ** (math.log10(self.lo) + pos * (math.log10(self.hi) - math.log10(self.lo)))
        else:
            raw = self.lo + pos * (self.hi - self.lo)
        return min(max(_three_figures(raw) if raw else 0.0, self.lo), self.hi)

    def value_text(self) -> str:
        return value_text(self.value / self.scale)

    def end_texts(self) -> tuple[str, str]:
        return end_text(self.lo / self.scale), end_text(self.hi / self.scale)

    def name(self) -> str:
        """The input's name in plain text, for a sentence or an accessible name."""
        return plain_label(self.label)


def _knobs(assay_type: AssayType) -> dict[str, Knob]:
    """The inputs of *assay_type*: its conditions, then its fitted parameters, with their default values."""
    meta = ASSAY_REGISTRY[assay_type]
    own = MODEL_DEFAULTS.get(assay_type, {})
    knobs: dict[str, Knob] = {}
    unit = UNIT_CHOICES['concentration'][1]
    for f in condition_fields(assay_type):
        if f.unit_type == 'binding_constant':
            d = own.get(f.key, _ParamDefault(f.label, f.default, f.default / 1e3, f.default * 1e3))
            knobs[f.key] = Knob(f.key, f.label, 'binding', '1/M', d.default, d.lo, d.hi, True)
        else:
            knobs[f.key] = Knob(f.key, f.label, 'concentration', 'M', f.default, 0.0, 5 * f.default, True, unit)
    for key in meta.parameter_keys:
        d = own.get(key, PARAM_DEFAULTS[key])
        kind = meta.param_kinds[key]
        if kind is ParamKind.BINDING_CONSTANT:
            knobs[key] = Knob(key, d.label, 'binding', '1/M', d.default, d.lo, d.hi, False)
        else:
            knobs[key] = Knob(key, d.label, 'signal', KIND_UNIT[kind], d.default, d.lo, d.hi, False)
    return knobs


# ── What the window draws ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Overlay:
    """A measurement file laid over the model: its name, concentrations (M) and replicates."""

    name: str
    x: np.ndarray
    signals: np.ndarray


@dataclass(frozen=True)
class Simulation:
    """What the window draws: the replicates at the measurement points, the model, its species."""

    x: np.ndarray
    signals: np.ndarray
    x_dense: np.ndarray
    y_dense: np.ndarray
    species: dict[str, np.ndarray]


@dataclass
class Grid:
    """The titrant concentrations: an even grid from *start* to *stop* (M) in *points*, or a custom list."""

    mode: str = 'even'
    start: float = 0.0
    stop: float = 9e-6
    points: int = 24
    unit: str = 'µM'
    values: list[float] = field(default_factory=list)
    source: str = ''  # the overlaid file the custom list was taken from


@dataclass
class Noise:
    """The noise drawn: ``var(y) = floor² + (proportional·y)²`` (floor in a.u., proportional a fraction)."""

    on: bool = True
    floor: float = 0.0
    proportional: float = 0.0
    replicates: int = 3
    seed: int = 0


class SimulationForm:
    """The settings of the Simulation window and the rules of stating them; see the module docstring."""

    def __init__(self, assay_type: AssayType = AssayType.IDA) -> None:
        self.overlay: Overlay | None = None
        self.set_assay(assay_type)

    # The model ---------------------------------------------------------------------
    def set_assay(self, assay_type: AssayType) -> None:
        """Choose *assay_type* with a fresh form: its default inputs, even grid and noise, the totals
        constant; an overlay stays.

        The noise opens with a floor of :data:`NOISE_FLOOR_SHARE` of the default curve's range,
        to two figures, so every model opens with scatter that reads on its own signal scale.
        """
        self.assay_type = assay_type
        self.knobs = _knobs(assay_type)
        stop = TITRANT_STOP[assay_type]
        self.grid = Grid(stop=stop, unit='mM' if stop >= 1e-4 else 'µM')
        self.diluted = False
        self.stock, self.stock_unit = STOCK_FACTOR * stop, STOCK_UNIT
        self.contains: set[str] = set()
        clean = simulate_signal(assay_class(assay_type), self.conditions(), self.parameters(), self.points())
        self.noise = Noise(floor=float(f'{NOISE_FLOOR_SHARE * float(np.ptp(clean)):.2g}'))
        if self.overlay is not None:
            self.take_overlay_grid()

    @property
    def category(self) -> str:
        return ASSAY_REGISTRY[self.assay_type].category

    def choose_category(self, category: str) -> None:
        if category != self.category:
            self.set_assay(CATEGORIES[category][0])

    def choose_model(self, assay_type: AssayType) -> None:
        if assay_type is not self.assay_type:
            self.set_assay(assay_type)

    def section(self, kind: str) -> list[Knob]:
        """The knobs of one section: ``'binding'``, ``'concentration'`` or ``'signal'``."""
        return [k for k in self.knobs.values() if k.kind == kind]

    # Knobs ---------------------------------------------------------------------------
    def set_value(self, key: str, text: str) -> None:
        """Take *text* as the value of *key* in the unit shown; a value past an end moves that end to it.

        Raises
        ------
        SimulationProblem
            When *text* is no number, or one the input cannot take.
        """
        knob = self.knobs[key]
        shown = parse_number(text)
        if shown is None:
            raise SimulationProblem(f'{knob.name()} needs a number. It keeps {knob.value_text()} {knob.shown_unit}.')
        value = shown * knob.scale
        if knob.log and value <= 0:
            raise SimulationProblem(f'{knob.name()} must be above 0 M⁻¹. It keeps {knob.value_text()} M⁻¹.')
        if knob.kind == 'concentration' and value < 0:
            raise SimulationProblem(
                f'{knob.name()} cannot be negative. It keeps {knob.value_text()} {knob.shown_unit}.'
            )
        knob.value = value
        knob.lo, knob.hi = min(knob.lo, value), max(knob.hi, value)

    def slide(self, key: str, pos: float) -> None:
        """Set *key* to the value at *pos* on its slider."""
        knob = self.knobs[key]
        knob.value = knob.at(pos)

    def set_end(self, key: str, high: bool, text: str) -> None:
        """Take *text* as the low or *high* end of *key*'s slider; the value stays inside the ends.

        Raises
        ------
        SimulationProblem
            When *text* is no number, or would put the ends in the wrong order or a log end at or below 0.
        """
        knob = self.knobs[key]
        which = 'upper' if high else 'lower'
        shown = parse_number(text)
        if shown is None:
            raise SimulationProblem(f'The {which} end of {knob.name()} needs a number.')
        value = shown * knob.scale
        lo, hi = (knob.lo, value) if high else (value, knob.hi)
        if knob.log and lo <= 0:
            raise SimulationProblem(f'The ends of {knob.name()} must be above 0 M⁻¹.')
        if knob.kind == 'concentration' and lo < 0:
            raise SimulationProblem(f'The ends of {knob.name()} cannot be negative.')
        if not lo < hi:
            raise SimulationProblem(f'The lower end of {knob.name()} must be below the upper end.')
        knob.lo, knob.hi = lo, hi
        knob.value = min(max(knob.value, lo), hi)

    def set_unit(self, key: str, unit: str) -> None:
        """Show fixed total *key* in *unit*: the same concentration."""
        self.knobs[key].unit = unit

    # Dilution ------------------------------------------------------------------------
    @property
    def offers_dilution(self) -> bool:
        """Whether there is a fixed total for the additions to dilute."""
        return bool(self.section('concentration'))

    @property
    def offers_contains(self) -> bool:
        """Whether the stock can hold some fixed totals and not others: with one, holding it is the constant case."""
        return len(self.section('concentration')) > 1

    def set_diluted(self, diluted: bool) -> None:
        """State that the additions dilute the sample (*diluted*), or that the totals stay constant."""
        self.diluted = diluted and self.offers_dilution

    @property
    def stock_scale(self) -> float:
        """One unit of the stock as shown, in M."""
        return float(Q_(1.0, self.stock_unit).to('M').magnitude)

    def stock_text(self) -> str:
        return value_text(self.stock / self.stock_scale)

    def set_stock(self, text: str) -> None:
        """Take *text* as the titrant stock concentration in the unit shown.

        Raises
        ------
        SimulationProblem
            When *text* is no number, or not above 0.
        """
        shown = parse_number(text)
        if shown is None or shown <= 0:
            raise SimulationProblem(
                f'The titrant stock needs a concentration above 0. It keeps {self.stock_text()} {self.stock_unit}.'
            )
        self.stock = shown * self.stock_scale

    def set_stock_unit(self, unit: str) -> None:
        """Show the stock in *unit*: the same concentration."""
        self.stock_unit = unit

    def set_contains(self, key: str, on: bool) -> None:
        """State that the stock holds fixed total *key* at the sample's own concentration, or not.

        Raises
        ------
        SimulationProblem
            When the stock would hold every fixed total, leaving nothing to dilute.
        """
        held = (self.contains | {key}) if on else (self.contains - {key})
        if held >= {k.key for k in self.section('concentration')}:
            raise SimulationProblem(
                'The titrant stock cannot hold every fixed total: nothing would be left for the additions to '
                'dilute. Choose “Stay constant” instead.'
            )
        self.contains = held

    # Titrant -------------------------------------------------------------------------
    @property
    def x_name(self) -> str:
        return ASSAY_REGISTRY[self.assay_type].x_label

    def set_grid_mode(self, mode: str) -> None:
        """Use the even grid (``'even'``) or a custom list, which starts from the points of the even grid."""
        if mode == 'custom' and not self.grid.values:
            self.grid.values = list(self._even_points())
        self.grid.mode = mode

    def set_even(self, start: str, stop: str, points: str) -> None:
        """Take the even grid from *start* and *stop* in the grid's unit and *points*.

        Raises
        ------
        SimulationProblem
            When a value is no number, the range is empty or negative, or there are fewer than 2 points.
        """
        scale = float(Q_(1.0, self.grid.unit).to('M').magnitude)
        a, b, n = parse_number(start), parse_number(stop), parse_number(points)
        if a is None or b is None or n is None:
            raise SimulationProblem('The concentrations need a number in From, To and Points.')
        if n != int(n) or n < 2:
            raise SimulationProblem('Points must be a whole number of at least 2.')
        if a < 0:
            raise SimulationProblem('Concentrations cannot be negative: From must be 0 or more.')
        if not b > a:
            raise SimulationProblem('To must be above From.')
        self.grid.start, self.grid.stop, self.grid.points = a * scale, b * scale, int(n)

    def set_grid_unit(self, unit: str) -> None:
        self.grid.unit = unit

    def set_point(self, index: int, text: str) -> None:
        """Take *text* (M) as point *index* of the custom list.

        Raises
        ------
        SimulationProblem
            When it is no number or below 0.
        """
        value = parse_number(text)
        if value is None or value < 0:
            raise SimulationProblem(f'Point {index + 1} needs a concentration of 0 M or more. It keeps its value.')
        self.grid.values[index] = value

    def set_custom(self, values: list[float]) -> None:
        """Use *values* (M) as the custom list.

        Raises
        ------
        SimulationProblem
            When there are fewer than two, or one is negative or no number.
        """
        arr = np.asarray(values, dtype=float)
        if arr.size < 2 or not np.all(np.isfinite(arr)) or np.any(arr < 0):
            raise SimulationProblem('A concentration list needs at least two concentrations, each 0 M or more.')
        self.grid.mode, self.grid.values, self.grid.source = 'custom', arr.tolist(), ''

    def _even_points(self) -> np.ndarray:
        g = self.grid
        return build_concentration_vector('linear', start=g.start, stop=g.stop, n=g.points)

    def points(self) -> np.ndarray:
        """The titrant concentrations the replicates are simulated at, in M."""
        if self.grid.mode == 'custom':
            return np.asarray(self.grid.values, dtype=float)
        return self._even_points()

    # Noise ---------------------------------------------------------------------------
    def set_noise(self, **changes: Any) -> None:
        """Change the noise: ``on``, ``floor`` (a.u.), ``proportional`` (a fraction), ``replicates``, ``seed``."""
        self.noise = replace(self.noise, **changes)

    def set_noise_text(self, name: str, text: str) -> None:
        """Take *text* as the floor (a.u.), the proportional part (%), the replicates or the seed.

        Raises
        ------
        SimulationProblem
            When it is no number, a negative one, or not a whole number where one is needed.
        """
        words = {
            'floor': 'The floor',
            'proportional': 'The proportional part',
            'replicates': 'Replicates',
            'seed': 'The seed',
        }
        value = parse_number(text)
        if value is None or value < 0:
            raise SimulationProblem(f'{words[name]} needs a number of 0 or more.')
        if name in ('replicates', 'seed') and value != int(value):
            raise SimulationProblem(f'{words[name]} must be a whole number.')
        if name == 'replicates' and value < 1:
            raise SimulationProblem('Replicates must be at least 1.')
        self.set_noise(
            **{
                name: value / 100.0
                if name == 'proportional'
                else (int(value) if name in ('replicates', 'seed') else value)
            }
        )

    def new_draw(self) -> None:
        """Draw new noise: the seed moves on by one."""
        self.set_noise(seed=self.noise.seed + 1)

    def replicates(self) -> int:
        """The replicates simulated: one where no noise is drawn, as identical copies would add nothing."""
        return self.noise.replicates if self.noise_drawn() else 1

    def noise_drawn(self) -> bool:
        return self.noise.on and (self.noise.floor > 0 or self.noise.proportional > 0)

    # Overlay -------------------------------------------------------------------------
    def set_overlay(self, overlay: Overlay | None) -> None:
        """Lay *overlay* over the model and simulate at its concentrations; ``None`` removes it, the grid kept."""
        self.overlay = overlay
        if overlay is not None:
            self.take_overlay_grid()

    def take_overlay_grid(self) -> None:
        self.grid.mode, self.grid.values, self.grid.source = 'custom', self.overlay.x.tolist(), self.overlay.name

    def read_noise_refusal(self) -> str | None:
        """Why *Read from overlaid data* cannot be used now; ``None`` when it can."""
        if self.overlay is None:
            return 'Overlay a measurement file with two or more replicates to read its noise.'
        if len(self.overlay.signals) < MIN_REPLICATES:
            return f'{self.overlay.name} has one replicate; its noise can be read from two or more.'
        return None

    def read_noise(self) -> None:
        """Take the floor and the proportional part from the noise law the fitter reads off the overlay.

        Raises
        ------
        SimulationProblem
            When no law can be read from the overlaid replicates, saying why.
        """
        law = noise_law(self.overlay.signals)
        if not law.estimated:
            reason = law.describe().split('—', 1)[-1].strip().rstrip('.')
            raise SimulationProblem(
                f'No noise law could be read from {self.overlay.name}: {reason}. The noise settings are unchanged.'
            )
        self.set_noise(on=True, floor=float(f'{law.floor:.2g}'), proportional=float(f'{law.proportional:.2g}'))

    # Simulating ----------------------------------------------------------------------
    def conditions(self) -> dict[str, Any]:
        """The model's conditions as the assay takes them, with a direct binding assay's mode.

        With dilution stated they also carry ``titrant_stock`` and ``stock_contains`` (the totals the
        stock holds, in model order), as :meth:`gui.binding.BindingForm.conditions` states them; with
        the totals constant neither key is there.
        """
        out: dict[str, Any] = {k.key: Q_(k.value, k.base_unit) for k in self.knobs.values() if k.condition}
        if self.assay_type in DBA_MODES:
            out['mode'] = DBA_MODES[self.assay_type]
        if self.diluted:
            out[TITRANT_STOCK] = Q_(self.stock, 'M')
            out['stock_contains'] = tuple(k.key for k in self.section('concentration') if k.key in self.contains)
        return out

    def parameters(self) -> dict[str, float]:
        return {k.key: k.value for k in self.knobs.values() if not k.condition}

    def simulate(self) -> Simulation:
        """The model, its species and the simulated replicates at the measurement points.

        Raises
        ------
        SimulationProblem
            When the model cannot be computed at these settings.
        """
        cls, cond, par = assay_class(self.assay_type), self.conditions(), self.parameters()
        x = self.points()
        if self.diluted and float(x.max()) >= self.stock:
            highest = value_text(float(x.max()) / self.stock_scale)
            raise SimulationProblem(
                f'The titrant stock ({self.stock_text()} {self.stock_unit}) must be more concentrated than the '
                f'highest titrant concentration ({highest} {self.stock_unit}): a sample cannot hold more titrant '
                'than the stock it was made from.'
            )
        x_dense = np.linspace(float(x.min()), float(x.max()), DENSE_POINTS)
        try:
            y = simulate_signal(cls, cond, par, x)
            y_dense = simulate_signal(cls, cond, par, x_dense)
            species = simulate_species(cls, cond, par, x_dense)
        except Exception as exc:
            raise SimulationProblem(
                'The model cannot be computed with these settings. Check that the concentrations and binding '
                'constants are above zero.'
            ) from exc
        if not (np.all(np.isfinite(y)) and np.all(np.isfinite(y_dense))):
            raise SimulationProblem(
                'The model cannot be computed with these settings. Check that the concentrations and binding '
                'constants are above zero.'
            )
        rows = np.tile(y, (self.replicates(), 1))
        if self.noise_drawn():
            sd = two_part_sd(y, floor=self.noise.floor, proportional=self.noise.proportional)
            rng = np.random.default_rng(self.noise.seed)
            rows = rows + rng.normal(0.0, 1.0, size=rows.shape) * sd[None, :]
        return Simulation(x, rows, x_dense, np.asarray(y_dense, dtype=float), dict(species))

    def measurement_set(self, sim: Simulation) -> MeasurementSet:
        """The simulated replicates of *sim* as data a session fits, exactly as drawn."""
        return MeasurementSet(
            concentrations=sim.x.copy(),
            signals=sim.signals.copy(),
            replica_ids=tuple(f'sim{i + 1}' for i in range(len(sim.signals))),
            metadata={'source_file': 'simulation', 'assay_type': self.assay_type.name},
        )

    def carry_to(self, model: SessionModel, sim: Simulation) -> None:
        """Give *model* the data of *sim* exactly as drawn, named after the simulation (``Simulated IDA``),
        and the binding model with its conditions.

        Only the conditions travel — the fixed totals and the binding constants the model takes
        as entered, and the titrant stock with the totals it holds where dilution is stated —
        each in the unit shown here. The values of what a fit searches for stay here: the fit
        starts as it does on measured data.
        """
        form = model.binding
        form.set_assay(self.assay_type)
        for knob in self.knobs.values():
            if knob.condition:
                if knob.kind == 'concentration':
                    form.set_unit(knob.key, knob.unit)
                form.set_value(knob.key, knob.value)
        form.set_diluted(self.diluted)
        if self.diluted:
            form.set_unit(TITRANT_STOCK, self.stock_unit)
            form.set_value(TITRANT_STOCK, self.stock)
            for key in self.contains:
                form.set_contains(key, True)
        model.binding_edited()
        model.load(self.measurement_set(sim), None)
        model.set_custom_name(f'Simulated {ASSAY_NAMES[self.assay_type][0]}')

    # What the window says ----------------------------------------------------------
    def binding_constants(self) -> int:
        return len(self.section('binding'))

    def badge(self) -> str:
        """``IDA · 24 points · 3 replicates``."""
        n, r = len(self.points()), self.replicates()
        return f'{ASSAY_NAMES[self.assay_type][0]} · {n} points · {r} replicate{"s" if r != 1 else ""}'

    def noise_text(self) -> str:
        """The noise in a few words: ``Noise 0.5 % + 1 200 a.u.``, ``No noise``."""
        if not self.noise_drawn():
            return 'No noise'
        parts = []
        if self.noise.proportional > 0:
            parts.append(f'{value_text(100 * self.noise.proportional)} %')
        if self.noise.floor > 0:
            parts.append(f'{value_text(self.noise.floor)} a.u.')
        return 'Noise ' + ' + '.join(parts)

    def model_line(self) -> list[str]:
        """What the status bar says is simulated."""
        n = self.binding_constants()
        return [ASSAY_NAMES[self.assay_type][1], f'{n} binding constant{"s" if n != 1 else ""}', self.noise_text()]

    def signal_formula(self) -> str:
        """``Signal = I₀ + I_dye,free·[D] + I_dye,bound·[HD]`` in rich text, from the registry."""
        meta = ASSAY_REGISTRY[self.assay_type]
        offset = [k for k in self.section('signal') if meta.param_kinds[k.key] is ParamKind.SIGNAL_OFFSET]
        coefficients = [k for k in self.section('signal') if meta.param_kinds[k.key] is ParamKind.SIGNAL_COEFFICIENT]
        terms = [k.label for k in offset]
        for k in coefficients:
            species = meta.signal_species.get(k.key, 'D')
            terms.append(f'{k.label}·{fmt_species(species)}')
        return 'Signal = ' + ' + '.join(terms)

    # Settings files ----------------------------------------------------------------
    def to_dict(self) -> dict:
        """Every value, slider end and unit, the concentrations, the dilution and the noise, as a settings
        file holds them."""
        g, n = self.grid, self.noise
        return {
            'version': SETTINGS_VERSION,
            'assay_type': self.assay_type.name,
            'knobs': {k.key: {'value': k.value, 'lo': k.lo, 'hi': k.hi, 'unit': k.unit} for k in self.knobs.values()},
            'grid': {
                'mode': g.mode,
                'start': g.start,
                'stop': g.stop,
                'points': g.points,
                'unit': g.unit,
                'values': g.values,
            },
            'dilution': {
                'diluted': self.diluted,
                'stock': self.stock,
                'unit': self.stock_unit,
                'contains': sorted(self.contains),
            },
            'noise': {
                'model': NOISE_MODEL,
                'on': n.on,
                'floor': n.floor,
                'proportional': n.proportional,
                'replicates': n.replicates,
                'seed': n.seed,
            },
        }

    def load_dict(self, d: dict) -> None:
        """Take the settings a settings file holds.

        Raises
        ------
        SimulationProblem
            When *d* is not a settings file this version reads.
        """
        try:
            if d['version'] != SETTINGS_VERSION or d['noise']['model'] != NOISE_MODEL:
                raise ValueError
            assay_type = AssayType[d['assay_type']]
            knobs = _knobs(assay_type)
            for key, k in d['knobs'].items():
                knob = knobs[key]
                knob.value, knob.lo, knob.hi = float(k['value']), float(k['lo']), float(k['hi'])
                if knob.kind == 'concentration':
                    if k['unit'] not in CONCENTRATION_UNITS:
                        raise ValueError
                    knob.unit = k['unit']
            g = d['grid']
            grid = Grid(
                g['mode'],
                float(g['start']),
                float(g['stop']),
                int(g['points']),
                g['unit'],
                [float(v) for v in g['values']],
            )
            if grid.mode not in ('even', 'custom') or grid.unit not in CONCENTRATION_UNITS:
                raise ValueError
            n = d['noise']
            noise = Noise(
                bool(n['on']), float(n['floor']), float(n['proportional']), int(n['replicates']), int(n['seed'])
            )
            dil = d['dilution']
            diluted, stock, stock_unit, held = (
                bool(dil['diluted']),
                float(dil['stock']),
                dil['unit'],
                set(dil['contains']),
            )
            fixed = {k.key for k in knobs.values() if k.kind == 'concentration'}
            if stock_unit not in CONCENTRATION_UNITS or not stock > 0 or not held <= fixed or (held and held == fixed):
                raise ValueError
        except (KeyError, TypeError, ValueError) as exc:
            raise SimulationProblem('not settings saved by this window') from exc
        self.assay_type, self.knobs, self.grid, self.noise = assay_type, knobs, grid, noise
        self.diluted, self.stock, self.stock_unit, self.contains = diluted and bool(fixed), stock, stock_unit, held


def species_groups(species: dict[str, np.ndarray]) -> list[tuple[str, list[str]]]:
    """The species under the readout's two words: ``Complexes`` (solid) and ``Free`` (dashed), each in model
    order with the free host last."""
    complexes = [k for k in species if k in COMPLEXES]
    free = sorted((k for k in species if k not in COMPLEXES), key=lambda k: k == 'H')  # the free host last
    return [(word, keys) for word, keys in (('Complexes', complexes), ('Free', free)) if keys]


def readout_value(value: float) -> str:
    """A concentration in the species readout: three significant figures."""
    return f'{value:#.3g}'.rstrip('.') if math.isfinite(value) else '–'


def tag_text(signal: float) -> str:
    """The signal at the pointer: ``1.14 × 10⁵ a.u.``."""
    return f'{fmt_value(signal).replace("×", f"{THIN}×{THIN}")} a.u.'
