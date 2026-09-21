"""Base class for assay data containers.

This module defines the abstract base class for all assay types. Each assay
holds experimental data and knows how to compute predicted signals via its
forward model, and the speciation that signal is built from.

The BaseAssay class is a data container: it evaluates the model, and
:mod:`core.pipeline` fits it. The fit reads the species of :meth:`BaseAssay.species`
as the columns its signal parameters multiply, which the registry's
``signal_species`` names, so both methods must come from one equilibrium solve.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from typing import Any, ClassVar, Dict, Mapping, Optional, Tuple

import numpy as np
import pint

from core.assays.registry import AssayMetadata, AssayType, get_metadata
from core.units import Quantity

# Sentinel input key for the titrant (the varying x-axis concentration vector).
TITRANT = '__titrant__'

# Condition key of the titrant stock concentration.  It is a condition, not an
# input: its error is the titrant's own (x = c_T·phi), so it moves with the
# titrant rather than on its own.
TITRANT_STOCK = 'titrant_stock'


def _conc(value: float) -> str:
    """A concentration in M, as a message states it: ``5×10⁻⁶ M``.

    Pint's pretty format, which is how every value the app shows is written;
    a message a caller of the API reads should not be the one place that says
    ``5e-06``.
    """
    return f'{Quantity(value, "M"):.4g~P}'


def _and_list(keys) -> str:
    """Condition keys as a message lists them: 'a', 'a and b', 'a, b and c'."""
    keys = list(keys)
    if len(keys) <= 1:
        return ''.join(keys)
    return f'{", ".join(keys[:-1])} and {keys[-1]}'


@dataclass
class BaseAssay(ABC):
    """Abstract base class for assay data containers.

    Subclasses must implement:
    - assay_type: class attribute defining the AssayType
    - forward_model: compute predicted signal from parameters and conditions
    - get_conditions: return experimental conditions needed for forward model

    Attributes
    ----------
    x_data : Quantity
        Independent variable (e.g., titrant concentration in M).
    y_data : Quantity
        Observed signal values (in au).
    name : str
        Optional identifier for this dataset.
    metadata : Dict[str, Any]
        Additional metadata (source file, date, etc.).
    titrant_stock : Quantity, optional
        Concentration of the stock the titrant was added from (M).  Given, the
        sample is diluted by each addition and every fixed total falls with it
        (:meth:`fixed_total`); left out, the totals are the same at every point.
    stock_contains : Tuple[str, ...]
        Condition keys of the fixed concentrations the titrant stock holds at
        the sample's own concentration, which the additions therefore do not
        dilute.
    """

    x_data: Quantity
    y_data: Quantity
    name: str = ''
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Keyword-only, so every subclass keeps the positional order of its own
    # conditions.
    titrant_stock: Optional[Quantity] = field(default=None, kw_only=True)
    stock_contains: Tuple[str, ...] = field(default=(), kw_only=True)

    # Subclasses must define this class attribute
    assay_type: AssayType = field(init=False)

    # Model identifier recorded on fit results; overridden per assay family
    # (e.g. ``'linear'`` for dye-alone, ``'equilibrium_hg2'`` for HG2).
    model_name: ClassVar[str] = 'equilibrium_4param'

    def __post_init__(self):
        """Validate data after initialization."""
        if not isinstance(self.x_data, Quantity):
            raise TypeError(f'x_data must be a pint Quantity, got {type(self.x_data).__name__}')
        if not isinstance(self.y_data, Quantity):
            raise TypeError(f'y_data must be a pint Quantity, got {type(self.y_data).__name__}')

        # Normalize to canonical units so .magnitude is always M / au. Give a
        # domain-clear error (x is a concentration, y is a signal) rather than a
        # bare pint DimensionalityError. The ``au = [signal]`` dimension means a
        # dimensionless or wrong-dimension y_data now fails here instead of being
        # silently accepted as a signal.
        try:
            object.__setattr__(self, 'x_data', self.x_data.to('M'))
        except pint.DimensionalityError as err:
            raise ValueError(
                f"x_data must be a concentration (e.g. M, µM, nM); got units '{self.x_data.units}'."
            ) from err
        try:
            object.__setattr__(self, 'y_data', self.y_data.to('au'))
        except pint.DimensionalityError as err:
            raise ValueError(f"y_data must be a signal in au; got units '{self.y_data.units}'.") from err

        if self.x_data.shape != self.y_data.shape:
            raise ValueError(f'x_data and y_data must have same shape, got {self.x_data.shape} and {self.y_data.shape}')

    @property
    def registry_metadata(self) -> AssayMetadata:
        """Get metadata from the assay registry."""
        return get_metadata(self.assay_type)

    @property
    def parameter_keys(self) -> Tuple[str, ...]:
        """Parameter names for this assay type."""
        return self.registry_metadata.parameter_keys

    @property
    def n_params(self) -> int:
        """Number of parameters to fit."""
        return len(self.parameter_keys)

    @property
    def n_points(self) -> int:
        """Number of data points."""
        return len(self.x_data)

    @abstractmethod
    def forward_model(self, params: np.ndarray, x: np.ndarray | None = None) -> Quantity:
        """Compute predicted signal from parameters.

        Parameters
        ----------
        params : np.ndarray
            Parameter values in the order defined by parameter_keys.
        x : np.ndarray, optional
            Titrant concentrations (M) to evaluate at. Defaults to the assay's
            own ``x_data`` (the measured points); pass a denser grid to render
            a smooth curve without changing the fit.

        Returns
        -------
        Quantity
            Predicted signal as a ``pint.Quantity`` in signal units — an
            implementation MUST return ``Q_(values, 'au')``, not a bare ndarray.
            Because ``au`` carries the ``[signal]`` dimension, :meth:`residuals`
            subtracts this from the ``au`` ``y_data``; returning a bare array
            raises a ``DimensionalityError`` there.
        """
        pass

    @abstractmethod
    def species(self, params: np.ndarray) -> Dict[str, np.ndarray]:
        """Equilibrium speciation across ``x_data`` from the same solve as the signal.

        Returns the per-species free/complex concentrations underlying the
        forward model — e.g. ``{'H', 'D', 'HD'}`` for direct binding, or
        ``{'H', 'D', 'G', 'HD', 'HG'}`` for competitive assays.  Insertion order
        is the intended plotting/legend order.  Implementations MUST reuse the
        model's own ``*_species`` solve (the one the signal is built from) so the
        speciation and the plotted signal can never disagree.  The fit builds its
        design matrix from these arrays — one column per signal coefficient, named
        by the registry's ``signal_species`` — so ``forward_model`` and this method
        describe the same state of the solution or the fit describes neither.

        Parameters
        ----------
        params : np.ndarray
            Parameter values in ``parameter_keys`` order (as for
            :meth:`forward_model`).

        Returns
        -------
        Dict[str, np.ndarray]
            Species name → concentration array (M magnitudes), each the same
            length as ``x_data``; NaN where the equilibrium solve fails.
        """
        pass

    @abstractmethod
    def get_conditions(self) -> Dict[str, Any]:
        """Return experimental conditions needed for the forward model.

        Returns
        -------
        Dict[str, Any]
            Conditions like fixed concentrations, known binding constants, etc.
        """
        pass

    # ------------------------------------------------------------------
    # Dilution of the fixed totals by the titrant
    # ------------------------------------------------------------------

    def fixed_total(self, key: str, x: np.ndarray) -> float | np.ndarray:
        """Total concentration (M) of the fixed species *key* at the titrant concentrations *x*.

        A sample of volume ``V0`` that has received a cumulative volume ``W_i``
        of stock holds ``x_i = c_T·W_i/(V0+W_i)`` of titrant, so the fraction of
        the final volume that came from the stock is ``x_i/c_T`` and a species
        the stock does not contain is left at ``c_k·(1 - x_i/c_T)``.  Only the
        stock concentration is needed, because the data hold ``x``.

        Parameters
        ----------
        key : str
            Condition key of a fixed concentration, e.g. ``'h0'``.
        x : np.ndarray
            Titrant concentrations (M) the model is being evaluated at — the
            measured points, or the denser grid of a display curve.

        Returns
        -------
        float or np.ndarray
            The entered value when no stock is declared or the stock contains
            this species, one value per point in *x* otherwise.
        """
        value = getattr(self, key).magnitude
        if self.titrant_stock is None or key in self.stock_contains:
            return value
        return value * (1.0 - x / self.titrant_stock.magnitude)

    def dilution_conditions(self) -> Dict[str, Any]:
        """The two dilution conditions, or nothing when the totals stay constant."""
        if self.titrant_stock is None:
            return {}
        return {TITRANT_STOCK: self.titrant_stock, 'stock_contains': self.stock_contains}

    def _concentration_keys(self) -> Tuple[str, ...]:
        """Condition keys of the fixed concentrations, in declaration order."""
        return tuple(
            key
            for key, value in self.get_conditions().items()
            if key != TITRANT_STOCK and isinstance(value, Quantity) and value.is_compatible_with('M')
        )

    def _check_dilution(self) -> None:
        """Normalise the dilution conditions and refuse a stock that cannot describe the data.

        Called as the last statement of every subclass ``__post_init__``: the
        checks read the assay's own concentrations, which the subclass has
        normalised by then.
        """
        object.__setattr__(self, 'stock_contains', tuple(self.stock_contains))
        fixed = self._concentration_keys()

        if self.titrant_stock is None:
            if self.stock_contains:
                raise ValueError(
                    f'The titrant stock was said to contain {_and_list(self.stock_contains)}, but no titrant '
                    'stock concentration was given. Enter the stock concentration, or choose that the '
                    'concentrations stay constant.'
                )
            return

        try:
            stock = self.titrant_stock.to('M')
        except (AttributeError, pint.DimensionalityError) as err:
            raise ValueError(
                f'The titrant stock concentration must be a concentration (e.g. M, mM, µM); got {self.titrant_stock!r}.'
            ) from err
        object.__setattr__(self, 'titrant_stock', stock)

        if not stock.magnitude > 0:
            raise ValueError(
                f'The titrant stock concentration must be greater than zero; it is '
                f'{_conc(stock.magnitude)}. Enter the '
                'concentration of the stock the titrant was added from, or choose that the concentrations '
                'stay constant.'
            )

        if not fixed:
            raise ValueError(
                f'The {self.assay_type.name} assay has no fixed concentration for the titrant to dilute, so a '
                'titrant stock concentration has no effect here. Choose that the concentrations stay constant.'
            )

        unknown = [key for key in self.stock_contains if key not in fixed]
        if unknown:
            raise ValueError(
                f'The titrant stock cannot contain {_and_list(unknown)}: the {self.assay_type.name} assay has no '
                f'such concentration. Its fixed concentrations are {_and_list(fixed)}.'
            )

        if set(self.stock_contains) == set(fixed):
            raise ValueError(
                f'The titrant stock was said to contain every fixed concentration ({_and_list(fixed)}), so '
                'nothing is diluted. Choose that the concentrations stay constant instead of entering a '
                'titrant stock.'
            )

        finite = self.x_data.magnitude[np.isfinite(self.x_data.magnitude)]
        if finite.size and float(finite.max()) >= stock.magnitude:
            raise ValueError(
                f'The titrant stock ({_conc(stock.magnitude)}) must be more concentrated than the highest '
                f'titrant concentration in the data ({_conc(float(finite.max()))}): a sample cannot hold more '
                'titrant than the stock it was made from. Check the stock concentration and its unit.'
            )

    def with_inputs(self, offsets: Mapping[str, float]) -> 'BaseAssay':
        """The same data with some entered inputs moved by a relative offset.

        Parameters
        ----------
        offsets : Mapping[str, float]
            Offset per input as a fraction of its entered value: ``TITRANT``
            scales every titrant concentration by ``1 + offset``, any other key
            names a Quantity condition of :meth:`get_conditions` and scales it
            the same way.  ``TITRANT`` carries the titrant stock with it —
            ``x = c_T·phi`` with ``phi`` a ratio of volumes, so a scale error of
            the titrant *is* the stock's concentration error and the dilution
            of the fixed totals does not move.  The stock is therefore not an
            input of its own and is refused as a key.

        Returns
        -------
        BaseAssay
            A copy built through the constructor, so the subclass validates the
            moved conditions like entered ones.

        Raises
        ------
        ValueError
            For a key that is neither ``TITRANT`` nor a Quantity condition, and
            from the subclass for a condition the offset leaves non-positive.
        """
        conditions = self.get_conditions()
        changes = {}
        for key, offset in offsets.items():
            if key == TITRANT:
                changes['x_data'] = self.x_data * (1.0 + offset)
                if self.titrant_stock is not None:
                    changes[TITRANT_STOCK] = self.titrant_stock * (1.0 + offset)
            elif key != TITRANT_STOCK and isinstance(conditions.get(key), Quantity):
                changes[key] = conditions[key] * (1.0 + offset)
            else:
                inputs = [k for k, v in conditions.items() if k != TITRANT_STOCK and isinstance(v, Quantity)]
                raise ValueError(
                    f'{key!r} is not an input of the {self.assay_type.name} assay; its inputs are '
                    f'{inputs} and the titrant.'
                )
        return replace(self, **changes)

    def residuals(self, params: np.ndarray) -> Quantity:
        """Compute residuals (observed - predicted).

        Parameters
        ----------
        params : np.ndarray
            Parameter values as bare floats, in ``parameter_keys`` order.

        Returns
        -------
        Quantity
            Residual values in signal units.
        """
        return self.y_data - self.forward_model(params)

    def sum_squared_residuals(self, params: np.ndarray) -> float:
        """Compute sum of squared residuals (SSR) for optimization.

        Parameters
        ----------
        params : np.ndarray
            Parameter values as bare floats, in ``parameter_keys`` order.

        Returns
        -------
        float
            Sum of squared residuals (dimensionless).
        """
        resid = self.residuals(params)
        return float(np.sum(resid.magnitude**2))

    def get_default_bounds(self) -> Dict[str, Tuple[Quantity, Quantity]]:
        """Get default parameter bounds as a name-keyed dictionary.

        Returns the ``default_bounds`` dictionary from the assay registry,
        keyed by parameter name.  Values are Quantity tuples.

        Returns
        -------
        Dict[str, Tuple[Quantity, Quantity]]
            ``{param_name: (lower, upper), ...}``
        """
        return dict(self.registry_metadata.default_bounds)

    def params_to_dict(self, params: np.ndarray) -> Dict[str, float]:
        """Convert parameter array to named dictionary.

        Parameters
        ----------
        params : np.ndarray
            Parameter values in standard order.

        Returns
        -------
        Dict[str, float]
            Parameter names mapped to values.
        """
        return dict(zip(self.parameter_keys, params))

    def params_from_dict(self, param_dict: Dict[str, float]) -> np.ndarray:
        """Convert named dictionary to parameter array.

        Parameters
        ----------
        param_dict : Dict[str, float]
            Parameter names mapped to values.

        Returns
        -------
        np.ndarray
            Parameter values in standard order.
        """
        return np.array([param_dict[k] for k in self.parameter_keys])
