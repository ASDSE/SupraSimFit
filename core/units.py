"""Shared Pint unit registry and canonical unit metadata.

Every physical value in the app flows as a ``pint.Quantity``.  The
optimizer boundary extracts ``.magnitude`` floats; forward models
and scipy operate on plain arrays for performance.

Example
-------
>>> from core.units import Q_, ureg
>>> conc = Q_(10, 'µM')
>>> conc.to('M').magnitude
1e-05
"""

from __future__ import annotations

import pint

# ---------------------------------------------------------------------------
# Single shared UnitRegistry
# ---------------------------------------------------------------------------
ureg = pint.UnitRegistry()
Q_ = ureg.Quantity
Quantity = pint.Quantity

# Custom unit definitions
ureg.define('micromolar = 1e-6 * molar = uM = µM')
ureg.define('nanomolar = 1e-9 * molar = nM')
ureg.define('picomolar = 1e-12 * molar = pM')
ureg.define('millimolar = 1e-3 * molar = mM')
ureg.define('au = [] = a.u.')  # arbitrary-unit token for signal
