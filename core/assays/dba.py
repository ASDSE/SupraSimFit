"""DBA (Direct Binding Assay) data containers.

DBA measures direct binding between host and dye:
    H + D ⇌ HD  (Ka_dye to be fitted)

Two titration modes:
- Host→Dye (DBA_HtoD): Host is titrated into fixed dye concentration
- Dye→Host (DBA_DtoH): Dye is titrated into fixed host concentration

Titrant: Dye (d0 varies)
Fixed: Host (h0)
Target: Ka_dye (association constant for host-dye)
Signal trend: ↑ Increases as dye binds host
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import numpy as np

from core.assays.base import BaseAssay
from core.assays.registry import AssayType
from core.models.equilibrium import dba_signal
from core.units import validate_concentration


@dataclass
class DBAAssay(BaseAssay):
    """Direct Binding Assay data container.

    This class handles both Host→Dye and Dye→Host titrations.
    The mode is determined by the assay_type attribute.

    Attributes
    ----------
    x_data : np.ndarray
        Titrant concentrations (M) - host for HtoD, dye for DtoH.
    y_data : np.ndarray
        Observed signal values.
    fixed_conc : float
        Fixed component concentration (M) - dye for HtoD, host for DtoH.
    mode : str
        Titration mode: 'HtoD' or 'DtoH'.
    name : str
        Optional identifier for this dataset.
    metadata : Dict[str, Any]
        Additional metadata.

    Example
    -------
    >>> assay = DBAAssay(
    ...     x_data=dye_conc,    # Dye concentrations in M (titrant)
    ...     y_data=signal,
    ...     fixed_conc=10e-6,   # 10 µM host (fixed)
    ...     mode='DtoH',
    ... )
    >>> predicted = assay.forward_model(params)
    """

    # Required physical parameters - no defaults (fail fast)
    fixed_conc: Optional[float] = None  # Fixed concentration (M)
    mode: str = 'DtoH'  # 'HtoD' or 'DtoH' (default: Dye→Host)

    assay_type: AssayType = field(init=False)

    def __post_init__(self):
        """Validate data and set assay type based on mode."""
        super().__post_init__()

        # Enforce required parameters (fail fast)
        if self.fixed_conc is None:
            raise ValueError('fixed_conc is required (fixed component concentration)')

        # Validate dimensionality (Quantity → float in M) or keep float
        self.fixed_conc = validate_concentration(self.fixed_conc)

        if self.fixed_conc <= 0:
            raise ValueError('fixed_conc must be positive')

        if self.mode == 'HtoD':
            object.__setattr__(self, 'assay_type', AssayType.DBA_HtoD)
        elif self.mode == 'DtoH':
            object.__setattr__(self, 'assay_type', AssayType.DBA_DtoH)
        else:
            raise ValueError(f"mode must be 'HtoD' or 'DtoH', got '{self.mode}'")

    def forward_model(self, params: np.ndarray) -> np.ndarray:
        """Compute predicted signal from parameters.

        Parameters
        ----------
        params : np.ndarray
            [Ka_dye, I0, I_dye_free, I_dye_bound] where:
            - Ka_dye: association constant for host-dye (M^-1)
            - I0: background signal
            - I_dye_free: signal coefficient for free dye
            - I_dye_bound: signal coefficient for host-dye complex

        Returns
        -------
        np.ndarray
            Predicted signal values.
        """
        Ka_dye, I0, I_dye_free, I_dye_bound = params

        return dba_signal(
            I0=I0,
            Ka_dye=Ka_dye,
            I_dye_free=I_dye_free,
            I_dye_bound=I_dye_bound,
            x_titrant=self.x_data,
            y_fixed=self.fixed_conc,
        )

    def get_conditions(self) -> Dict[str, Any]:
        """Return experimental conditions.

        Returns
        -------
        Dict[str, Any]
            {'fixed_conc': ..., 'mode': ...}
        """
        return {
            'fixed_conc': self.fixed_conc,
            'mode': self.mode,
        }


# Convenience factory functions for clearer API
def create_dba_host_to_dye(
    host_conc: np.ndarray,
    signal: np.ndarray,
    dye_conc: float,
    **kwargs,
) -> DBAAssay:
    """Create DBA assay for host-to-dye titration.

    Parameters
    ----------
    host_conc : np.ndarray
        Host concentrations (M) - the titrant.
    signal : np.ndarray
        Observed signal values.
    dye_conc : float
        Fixed dye concentration (M).
    **kwargs
        Additional arguments passed to DBAAssay.

    Returns
    -------
    DBAAssay
        Configured for HtoD mode.
    """
    return DBAAssay(
        x_data=host_conc,
        y_data=signal,
        fixed_conc=dye_conc,
        mode='HtoD',
        **kwargs,
    )


def create_dba_dye_to_host(
    dye_conc: np.ndarray,
    signal: np.ndarray,
    host_conc: float,
    **kwargs,
) -> DBAAssay:
    """Create DBA assay for dye-to-host titration.

    Parameters
    ----------
    dye_conc : np.ndarray
        Dye concentrations (M) - the titrant.
    signal : np.ndarray
        Observed signal values.
    host_conc : float
        Fixed host concentration (M).
    **kwargs
        Additional arguments passed to DBAAssay.

    Returns
    -------
    DBAAssay
        Configured for DtoH mode.
    """
    return DBAAssay(
        x_data=dye_conc,
        y_data=signal,
        fixed_conc=host_conc,
        mode='DtoH',
        **kwargs,
    )
