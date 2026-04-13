"""Session-level helpers: JSON export/import of fit results, plot image export."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from core.assays.registry import ASSAY_REGISTRY, AssayType
from core.pipeline.fit_pipeline import FitResult
from core.units import Quantity
from gui.plotting.labels import fmt_unit_pretty

if TYPE_CHECKING:
    pass


def export_results(results: list[FitResult], path: str | Path) -> None:
    """Export a list of FitResult objects to a JSON file.

    Parameters
    ----------
    results : list[FitResult]
        Fit results to export.
    path : str or Path
        Output file path (should have ``.json`` extension).
    """
    path = Path(path)
    data = [r.to_dict() for r in results]
    path.write_text(json.dumps(data, indent=2))


def import_results(path: str | Path) -> list[FitResult]:
    """Import fit results from a JSON file created by :func:`export_results`.

    Parameters
    ----------
    path : str or Path
        Path to the JSON file.

    Returns
    -------
    list[FitResult]
        Reconstructed FitResult objects.
    """
    path = Path(path)
    raw = json.loads(path.read_text())
    if isinstance(raw, dict):
        raw = [raw]
    return [FitResult.from_dict(d) for d in raw]


def export_results_txt(results: list[FitResult], path: str | Path) -> None:
    """Export fit results as a human-readable text report.

    Parameters
    ----------
    results : list[FitResult]
        Fit results to export (typically a single-element list).
    path : str or Path
        Output file path (should have ``.txt`` extension).
    """
    path = Path(path)
    lines: list[str] = []

    lines.append('=' * 60)
    lines.append('FIT RESULTS REPORT')
    lines.append('=' * 60)
    lines.append(f'Generated: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")}')
    lines.append('')

    for i, result in enumerate(results):
        if len(results) > 1:
            lines.append(f'--- Result {i + 1} of {len(results)} ---')
            lines.append('')

        # Header
        lines.append(f'Assay type:  {result.assay_type}')
        lines.append(f'Model:       {result.model_name}')
        if result.source_file:
            lines.append(f'Source file: {result.source_file}')
        lines.append(f'Timestamp:   {result.timestamp}')
        lines.append('')

        # Resolve units from registry
        units: dict[str, str] = {}
        try:
            assay_type = AssayType[result.assay_type]
            units = ASSAY_REGISTRY[assay_type].units
        except KeyError:
            pass

        # Parameters table
        lines.append('FITTED PARAMETERS')
        lines.append('-' * 60)

        # Compute column widths
        rows: list[tuple[str, str, str, str]] = []
        for key, val in result.parameters.items():
            unc = result.uncertainties.get(key, float('nan'))
            unit_str = units.get(key, '')
            val_mag = float(val.magnitude) if isinstance(val, Quantity) else float(val)
            unc_mag = float(unc.magnitude) if isinstance(unc, Quantity) else float(unc)
            unit_display = fmt_unit_pretty(unit_str)
            rows.append((key, f'{val_mag:.4g}', f'{unc_mag:.4g}', unit_display))

        if rows:
            w_name = max(len(r[0]) for r in rows)
            w_val = max(len(r[1]) for r in rows)
            w_unc = max(len(r[2]) for r in rows)
            header = f'  {"Parameter":<{w_name}}   {"Value":>{w_val}}   {"± Uncert.":>{w_unc + 2}}   Units'
            lines.append(header)
            lines.append('  ' + '-' * (len(header) - 2))
            for name, val_s, unc_s, unit_s in rows:
                lines.append(f'  {name:<{w_name}}   {val_s:>{w_val}}   ± {unc_s:>{w_unc}}   {unit_s}')
        lines.append('')

        # Fit quality
        lines.append('FIT QUALITY')
        lines.append('-' * 60)
        lines.append(f'  RMSE:          {result.rmse:.4g} a.u.')
        lines.append(f'  R²:            {result.r_squared:.6f}')
        lines.append(f'  Fits passing:  {result.n_passing} / {result.n_total}')
        lines.append('')

        # Conditions
        if result.conditions:
            lines.append('CONDITIONS')
            lines.append('-' * 60)
            for cond_key, cond_val in result.conditions.items():
                if isinstance(cond_val, Quantity):
                    lines.append(f'  {cond_key}: {cond_val:.4g~P}')
                else:
                    lines.append(f'  {cond_key}: {cond_val}')
            lines.append('')

        if i < len(results) - 1:
            lines.append('')

    lines.append('=' * 60)

    path.write_text('\n'.join(lines), encoding='utf-8')
