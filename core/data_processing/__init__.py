"""Data processing: containers, preprocessing, and plot helpers.

Public API
----------
- :class:`MeasurementSet` — multi-replica data container.
- :func:`apply_preprocessing` — run a pipeline of named steps.
- :func:`register_step` / :func:`get_step` — preprocessing registry.
- :func:`prepare_plot_data` — GUI-friendly plot data preparation.
"""

from core.data_processing.measurement_set import MeasurementSet
from core.data_processing.plotting import prepare_plot_data

# Import preprocessing to auto-register built-in steps (e.g. zscore)
from core.data_processing.preprocessing import PREPROCESSING_STEPS, PreprocessingStep, apply_preprocessing, get_step, register_step  # noqa: F401

__all__ = [
    'MeasurementSet',
    'PreprocessingStep',
    'PREPROCESSING_STEPS',
    'register_step',
    'get_step',
    'apply_preprocessing',
    'prepare_plot_data',
]
