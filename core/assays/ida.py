"""IDA (Indicator Displacement Assay) data container.

In IDA, guest is titrated into a solution containing host and dye (indicator).
The guest competes with the dye for binding to the host, displacing it:
    H + D ⇌ HD  (Ka_dye known from DBA)
    H + G ⇌ HG  (Ka_guest to be fitted)

Titrant: Guest (g0 varies)
Fixed: Host (h0), Dye (d0)
Target: Ka_guest (association constant for host-guest)
Signal trend: ↓ Decreases as guest binds host and displaces dye
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import numpy as np

from core.assays.base import BaseAssay
from core.assays.registry import AssayType
from core.models.equilibrium import ida_signal
from core.units import validate_association_constant, validate_concentration


@dataclass
class IDAAssay(BaseAssay):
    """Indicator Displacement Assay data container.

    Attributes
    ----------
    x_data : np.ndarray
        Guest concentrations (M) - the independent variable (titrant).
    y_data : np.ndarray
        Observed signal values.
    Ka_dye : float
        Known association constant for host-dye binding (M^-1).
    h0 : float
        Total host concentration (M) - fixed.
    d0 : float
        Total dye concentration (M) - fixed.
    name : str
        Optional identifier for this dataset.
    metadata : Dict[str, Any]
        Additional metadata.

    Example
    -------
    >>> assay = IDAAssay(
    ...     x_data=guest_conc,  # Guest concentrations in M (titrant)
    ...     y_data=signal,
    ...     Ka_dye=1e6,         # Known host-dye Ka from DBA (M^-1)
    ...     h0=10e-6,           # 10 µM host (fixed)
    ...     d0=1e-6,            # 1 µM dye (fixed)
    ... )
    >>> predicted = assay.forward_model(params)
    """

    # Required physical parameters - no defaults (fail fast)
    Ka_dye: Optional[float] = None  # Known host-dye association constant (M^-1)
    h0: Optional[float] = None  # Total host concentration (M)
    d0: Optional[float] = None  # Total dye concentration (M)

    assay_type: AssayType = field(init=False, default=AssayType.IDA)

    def __post_init__(self):
        """Validate data and conditions."""
        super().__post_init__()

        # Enforce required parameters (fail fast)
        if self.Ka_dye is None:
            raise ValueError('Ka_dye is required (known host-dye association constant)')
        if self.h0 is None:
            raise ValueError('h0 is required (total host concentration)')
        if self.d0 is None:
            raise ValueError('d0 is required (total dye concentration)')

        # Validate dimensionality (Quantity → float in SI) or positivity (float)
        self.Ka_dye = validate_association_constant(self.Ka_dye)
        self.h0 = validate_concentration(self.h0)
        self.d0 = validate_concentration(self.d0)

        if self.Ka_dye <= 0:
            raise ValueError('Ka_dye must be positive')
        if self.h0 <= 0:
            raise ValueError('h0 (host concentration) must be positive')
        if self.d0 <= 0:
            raise ValueError('d0 (dye concentration) must be positive')

    def forward_model(self, params: np.ndarray) -> np.ndarray:
        """Compute predicted signal from parameters.

        Parameters
        ----------
        params : np.ndarray
            [Ka_guest, I0, I_dye_free, I_dye_bound] where:
            - Ka_guest: guest-host association constant (M^-1)
            - I0: background signal
            - I_dye_free: signal coefficient for free dye
            - I_dye_bound: signal coefficient for host-dye complex

        Returns
        -------
        np.ndarray
            Predicted signal values.
        """
        Ka_guest, I0, I_dye_free, I_dye_bound = params

        return ida_signal(
            I0=I0,
            Ka_guest=Ka_guest,
            I_dye_free=I_dye_free,
            I_dye_bound=I_dye_bound,
            Ka_dye=self.Ka_dye,
            h0=self.h0,
            d0=self.d0,
            g0_values=self.x_data,  # Guest is the titrant
        )

    def get_conditions(self) -> Dict[str, Any]:
        """Return experimental conditions.

        Returns
        -------
        Dict[str, Any]
            {'Ka_dye': ..., 'h0': ..., 'd0': ...}
        """
        return {
            'Ka_dye': self.Ka_dye,
            'h0': self.h0,
            'd0': self.d0,
        }
