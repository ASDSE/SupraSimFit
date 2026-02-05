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


def strip_units(value: 'pint.Quantity', target_unit: str = 'M') -> float:
    """Strip units from a quantity, converting to target unit first.

    Parameters
    ----------
    value : Quantity
        A pint Quantity with concentration units.
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


def ensure_quantity(value, default_unit: str = 'M') -> 'pint.Quantity':
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
