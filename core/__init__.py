"""Core domain logic for molecular binding assay fitting.

Main entry points:
- core.assays: Assay data containers (GDAAssay, IDAAssay, DBAAssay, DyeAloneAssay)
- core.pipeline: Fitting orchestration (fit_assay, FitResult, FitConfig)
- core.io: File I/O (load_measurements, save_results)
"""

from core.io import load_measurements, save_results

__all__ = [
    'load_measurements',
    'save_results',
]
