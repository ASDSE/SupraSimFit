"""Base class for assay data containers.

This module defines the abstract base class for all assay types. Each assay
holds experimental data and knows how to compute predicted signals via its
forward model.

The BaseAssay class is a data container, not a fitter. Fitting is handled
by the optimizer module.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

import numpy as np

from core.assays.registry import AssayMetadata, AssayType, get_metadata


@dataclass
class BaseAssay(ABC):
    """Abstract base class for assay data containers.

    Subclasses must implement:
    - assay_type: class attribute defining the AssayType
    - forward_model: compute predicted signal from parameters and conditions
    - get_conditions: return experimental conditions needed for forward model

    Attributes
    ----------
    x_data : np.ndarray
        Independent variable (e.g., titrant concentration in M).
    y_data : np.ndarray
        Observed signal values.
    name : str
        Optional identifier for this dataset.
    metadata : Dict[str, Any]
        Additional metadata (source file, date, etc.).
    """

    x_data: np.ndarray
    y_data: np.ndarray
    name: str = ''
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Subclasses must define this class attribute
    assay_type: AssayType = field(init=False)

    def __post_init__(self):
        """Validate data after initialization."""
        self.x_data = np.asarray(self.x_data)
        self.y_data = np.asarray(self.y_data)
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
    def forward_model(self, params: np.ndarray) -> np.ndarray:
        """Compute predicted signal from parameters.

        Parameters
        ----------
        params : np.ndarray
            Parameter values in the order defined by parameter_keys.

        Returns
        -------
        np.ndarray
            Predicted signal values, same shape as y_data.
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

    def residuals(self, params: np.ndarray) -> np.ndarray:
        """Compute residuals (observed - predicted).

        Parameters
        ----------
        params : np.ndarray
            Parameter values.

        Returns
        -------
        np.ndarray
            Residual values.
        """
        return self.y_data - self.forward_model(params)

    def sum_squared_residuals(self, params: np.ndarray) -> float:
        """Compute sum of squared residuals (SSR) for optimization.

        Parameters
        ----------
        params : np.ndarray
            Parameter values.

        Returns
        -------
        float
            Sum of squared residuals.
        """
        resid = self.residuals(params)
        return float(np.sum(resid**2))

    def get_default_bounds(self) -> Dict[str, Tuple[float, float]]:
        """Get default parameter bounds as a name-keyed dictionary.

        Returns the ``default_bounds`` dictionary from the assay registry,
        keyed by parameter name.

        Returns
        -------
        Dict[str, Tuple[float, float]]
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
