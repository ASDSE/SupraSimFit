"""Linear model for dye-alone calibration.

This module provides a simple linear model for dye-alone measurements,
where signal is linearly proportional to dye concentration.

Signal = slope * [Dye] + intercept
"""

import numpy as np


def linear_signal(
    slope: float,
    intercept: float,
    x: np.ndarray,
) -> np.ndarray:
    """Compute linear signal.

    Parameters
    ----------
    slope : float
        Slope of the linear relationship (signal per unit concentration).
    intercept : float
        Y-intercept (background signal at zero concentration).
    x : np.ndarray
        Independent variable values (concentrations).

    Returns
    -------
    np.ndarray
        Predicted signal values.
    """
    return slope * x + intercept
