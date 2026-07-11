"""Save / load simulation applet settings as JSON.

The settings dict (from ``SimulationPanel.state``) is the durable provenance
record for a simulation: assay, every knob's value + bounds, the concentration
spec, and noise settings.  (The measurement writers do not persist metadata, so
this — not the exported data file — is where the ground-truth parameters live.)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def save_simulation_settings(state: dict[str, Any], path: str | Path) -> None:
    """Write *state* (from :meth:`SimulationPanel.state`) to a JSON file."""
    Path(path).write_text(json.dumps(state, indent=2), encoding='utf-8')


def load_simulation_settings(path: str | Path) -> dict[str, Any]:
    """Read a settings dict previously written by :func:`save_simulation_settings`."""
    return json.loads(Path(path).read_text(encoding='utf-8'))
