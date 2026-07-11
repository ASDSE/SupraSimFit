"""Shared Pint unit registry and canonical unit metadata.

Every physical value in the app flows as a ``pint.Quantity``.  The
optimizer boundary extracts ``.magnitude`` floats; forward models
and scipy operate on plain arrays for performance.

Canonical internal units: concentration in **M**, binding constants in
**1/M**, signal in **au**.  Always normalize with an explicit target,
``q.to('M').magnitude`` — never ``q.to_base_units()`` (molar's SI base
is mol/m³, which is 1000× off).

The signal unit ``au`` is given its **own base dimension** ``[signal]``
rather than being dimensionless.  This is deliberate: a dimensionless
``au`` would make ``au/M`` indistinguishable from ``1/M`` (a binding
constant), so ``Q_(x, 'au/M').to('1/M')`` would *silently* succeed and a
signal coefficient could be misread as a Ka.  With ``au = [signal]`` that
conversion raises, and the 4-parameter signal equation
``I_tot = I0 + I_dye_free·[D] + I_dye_bound·[HD]`` is dimensionally
consistent and runtime-checkable (``[signal]`` throughout).

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
Unit = pint.Unit

# Custom unit definitions
ureg.define('micromolar = 1e-6 * molar = uM = µM')
ureg.define('nanomolar = 1e-9 * molar = nM')
ureg.define('picomolar = 1e-12 * molar = pM')
ureg.define('millimolar = 1e-3 * molar = mM')
# Signal token with its OWN dimension ([signal]) so au/M stays dimensionally
# distinct from 1/M.  Keeps the display symbol 'a.u.' and the serialization
# tokens ('au', 'au / molar') unchanged.
ureg.define('au = [signal] = a.u.')

# Register as the application registry so Quantities survive pickling and stay
# compatible across modules/processes (a single canonical registry).
pint.set_application_registry(ureg)
