"""Dye-alone calibration assay.

This is a simple linear calibration where signal is proportional to
dye concentration:
    Signal = slope * [Dye] + intercept

Used to establish the linear response range of the dye.
"""

from dataclasses import dataclass, field
from typing import Any, Dict

import numpy as np

from core.assays.base import BaseAssay
from core.assays.registry import AssayType
from core.models.linear import linear_signal


@dataclass
class DyeAloneAssay(BaseAssay):
    """Dye-alone calibration data container.

    Attributes
    ----------
    x_data : np.ndarray
        Dye concentrations (M).
    y_data : np.ndarray
        Observed signal values.
    name : str
        Optional identifier for this dataset.
    metadata : Dict[str, Any]
        Additional metadata.

    Example
    -------
    >>> assay = DyeAloneAssay(
    ...     x_data=dye_conc,  # Dye concentrations in M
    ...     y_data=signal,
    ... )
    >>> slope, intercept, r2, rmse = assay.fit_linear()
    """

    assay_type: AssayType = field(init=False, default=AssayType.DYE_ALONE)

    def forward_model(self, params: np.ndarray) -> np.ndarray:
        """Compute predicted signal from parameters.

        Parameters
        ----------
        params : np.ndarray
            [slope, intercept]

        Returns
        -------
        np.ndarray
            Predicted signal values.
        """
        slope, intercept = params
        return linear_signal(slope, intercept, self.x_data)

    def get_conditions(self) -> Dict[str, Any]:
        """Return experimental conditions.

        Returns
        -------
        Dict[str, Any]
            Empty dict for dye-alone (no fixed conditions).
        """
        return {}

    def fit_linear(self):
        """Fit linear model using simple linear regression.

        Returns
        -------
        Tuple[float, float, float, float]
            (slope, intercept, r_squared, rmse)
        """
        from core.optimizer.linear_fit import linear_regression

        return linear_regression(self.x_data, self.y_data)
