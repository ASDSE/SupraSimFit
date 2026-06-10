"""HG2 assay: stepwise 1:2 host–guest direct binding.

Guest is titrated into a fixed host concentration; the host binds two
guests in two successive steps:
    H + G  ⇌ HG    (Ka_HG)
    HG + G ⇌ HG2   (Ka_HG2)

Titrant: Guest (g0 varies)
Fixed:   Host (h0)
Target:  Ka_HG, Ka_HG2 (stepwise association constants)

The two stepwise constants are, in general, not independently identifiable.
The fit does not hide this — it reports the spread of acceptable solutions
rather than implying a unique pair.
"""

from dataclasses import dataclass, field
from typing import Any, ClassVar, Dict, Optional

import numpy as np

from core.assays.base import BaseAssay
from core.assays.registry import AssayType
from core.models.equilibrium import hg2_signal
from core.units import Q_, Quantity


@dataclass
class HG2Assay(BaseAssay):
    """Stepwise 1:2 host–guest direct-binding assay (host binds two guests).

    Attributes
    ----------
    x_data : Quantity
        Guest concentrations (M) — the titrant.
    y_data : Quantity
        Observed signal values (au).
    h0 : Quantity
        Total (fixed) host concentration (M).
    """

    h0: Optional[Quantity] = None

    assay_type: AssayType = field(init=False, default=AssayType.DBA_HG2)
    model_name: ClassVar[str] = 'equilibrium_hg2'

    def __post_init__(self):
        """Validate data and the fixed host concentration."""
        super().__post_init__()

        if self.h0 is None:
            raise ValueError('h0 is required (total host concentration)')
        if not isinstance(self.h0, Quantity):
            raise TypeError(f'h0 must be a pint Quantity, got {type(self.h0).__name__}')

        # Normalize to base units so .magnitude is always M
        object.__setattr__(self, 'h0', self.h0.to('M'))

        if self.h0.magnitude <= 0:
            raise ValueError('h0 must be positive')

    def forward_model(self, params: np.ndarray) -> Quantity:
        """Compute predicted signal from parameters.

        Parameters
        ----------
        params : np.ndarray
            ``[Ka_HG, Ka_HG2, I0, I_G, I_H, I_HG, I_HG2]`` as bare floats
            from the optimizer, in canonical units.

        Returns
        -------
        Quantity
            Predicted signal values in au.
        """
        Ka_HG, Ka_HG2, I0, I_G, I_H, I_HG, I_HG2 = params

        result = hg2_signal(
            I0=I0,
            Ka_HG=Ka_HG,
            Ka_HG2=Ka_HG2,
            I_G=I_G,
            I_H=I_H,
            I_HG=I_HG,
            I_HG2=I_HG2,
            h0=self.h0.magnitude,
            g0_values=self.x_data.magnitude,
        )
        return Q_(result, 'au')

    def get_conditions(self) -> Dict[str, Any]:
        """Return experimental conditions.

        Returns
        -------
        Dict[str, Any]
            ``{'h0': ...}``
        """
        return {'h0': self.h0}
