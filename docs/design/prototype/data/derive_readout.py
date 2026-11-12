"""The pointer readout the confidence view shows at one Ka, from demo.json and the app's own R² formatter.

Each profile is read as the plot draws it: R² straight between grid points in log Ka, judged
against the cut-off of the nearest grid point (the cut-off is a step function centred on them).
"""

import json
from pathlib import Path

import numpy as np

from docs.design.prototype.common import DEMO
from gui.plotting.labels import fmt_r2

HERE = Path(__file__).resolve().parent


KA = 1.70e8
p = DEMO['profile']['profiles']['Ka_guest']
out = {'ka_per_M': KA}
for key, name in (('input_aware', 'aware'), ('conditional', 'conditional')):
    prof = p[key]
    lg = np.log10(np.array(prof['grid_per_M']))
    r2 = np.array(prof['r2'], float)
    cut = np.array(prof['r2_cut'], float)
    best = float(np.nanmax(r2))
    _, first = np.unique(lg, return_index=True)  # the grid repeats a node where a search cell meets the fill
    at = float(np.interp(np.log10(KA), lg[first], r2[first]))
    level = float(cut[np.argmin(np.abs(lg - np.log10(KA)))])
    ratio = (best - at) / (best - level)
    out[name] = {'r2': fmt_r2(at), 'ratio': ratio, 'inside': bool(at >= level)}
(HERE / 'confidence_readout.json').write_text(json.dumps(out, indent=1, ensure_ascii=False))
print(json.dumps(out, indent=1, ensure_ascii=False))
