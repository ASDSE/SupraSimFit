"""Shared unit registry for physical quantities.

This module provides a single pint UnitRegistry instance used throughout the
fitting toolkit. All concentration values, binding constants, and other physical
quantities should be created using Q_ from this module.

Boundary Stripping Strategy
---------------------------
- Internal: concentrations and constants as pint.Quantity
- Optimizer boundary: strip to .magnitude before passing to scipy
- Plotter boundary: strip to .magnitude arrays with unit labels in metadata
- I/O boundary: write magnitude + unit string, reconstruct on read

Example
-------
>>> from core.units import Q_, ureg
>>> conc = Q_(10, 'micromolar')
>>> conc.to('molar').magnitude
1e-05
>>> K_D = Q_(1e-6, 'M')
>>> K_D.magnitude
1e-06
"""

from __future__ import annotations

import numpy as np
import pint

# Single shared UnitRegistry for the entire application
ureg = pint.UnitRegistry()

# Convenience alias for creating quantities
Q_ = ureg.Quantity

# Common unit definitions for binding assays
ureg.define('micromolar = 1e-6 * molar = uM = µM')
ureg.define('nanomolar = 1e-9 * molar = nM')
ureg.define('picomolar = 1e-12 * molar = pM')

# Type alias for type hints (using string for forward reference)
Quantity = pint.Quantity

# ---------------------------------------------------------------------------
# Canonical unit string constants — single source of truth
# ---------------------------------------------------------------------------
MOLAR = 'M'  # base concentration unit
PER_MOLAR = '1/M'  # association constant unit  (Ka)
AU = 'dimensionless'  # arbitrary units (signals)


def strip_units(value: pint.Quantity, target_unit: str = 'M') -> float:
    """Strip units from a quantity, converting to target unit first.

    Parameters
    ----------
    value : Quantity
        A pint Quantity with compatible units.
    target_unit : str
        The unit to convert to before stripping (default: 'M' for molar).

    Returns
    -------
    float
        The magnitude in the target unit.

    Example
    -------
    >>> conc = Q_(10, 'uM')
    >>> strip_units(conc)
    1e-05
    """
    return value.to(target_unit).magnitude


def ensure_quantity(value, default_unit: str = 'M') -> pint.Quantity:
    """Ensure a value is a Quantity, adding default units if needed.

    Parameters
    ----------
    value : float or Quantity
        A numeric value or Quantity.
    default_unit : str
        Unit to apply if value is not already a Quantity.

    Returns
    -------
    Quantity
        The value as a pint Quantity.

    Example
    -------
    >>> ensure_quantity(1e-6)
    <Quantity(1e-06, 'molar')>
    >>> ensure_quantity(Q_(10, 'uM'))
    <Quantity(10, 'micromolar')>
    """
    if isinstance(value, Quantity):
        return value
    return Q_(value, default_unit)


# ---------------------------------------------------------------------------
# Dimensionality validation helpers
# ---------------------------------------------------------------------------


def validate_concentration(value) -> float:
    """Validate that *value* is a concentration and return its magnitude in M.

    Accepts a ``pint.Quantity`` with concentration dimensionality **or** a
    bare ``float`` (assumed to be in M for backward compatibility).

    Parameters
    ----------
    value : float or Quantity
        Concentration value.

    Returns
    -------
    float
        Magnitude in molar (M).

    Raises
    ------
    pint.DimensionalityError
        If *value* is a Quantity but not a concentration.
    """
    if isinstance(value, Quantity):
        return value.to(MOLAR).magnitude
    return float(value)


def validate_association_constant(value) -> float:
    """Validate that *value* is an association constant and return magnitude in M⁻¹.

    Accepts a ``pint.Quantity`` with ``1/[concentration]`` dimensionality
    **or** a bare ``float`` (assumed to be in M⁻¹ for backward compatibility).

    Parameters
    ----------
    value : float or Quantity
        Association constant value.

    Returns
    -------
    float
        Magnitude in M⁻¹.

    Raises
    ------
    pint.DimensionalityError
        If *value* is a Quantity but not ``1/[concentration]``.
    """
    if isinstance(value, Quantity):
        return value.to(PER_MOLAR).magnitude
    return float(value)


def to_base_units(value, expected_unit: str) -> float:
    """Convert *value* to *expected_unit* and return the bare magnitude.

    If *value* is already a plain number it is returned unchanged.

    Parameters
    ----------
    value : float, np.ndarray, or Quantity
        The value to convert.
    expected_unit : str
        The pint-parseable target unit string (e.g. ``'M'``, ``'1/M'``).

    Returns
    -------
    float or np.ndarray
        The magnitude in *expected_unit*.

    Raises
    ------
    pint.DimensionalityError
        If *value* is a Quantity with incompatible dimensionality.
    """
    if isinstance(value, Quantity):
        return value.to(expected_unit).magnitude
    return value
