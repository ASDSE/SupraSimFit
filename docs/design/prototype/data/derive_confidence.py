"""Numbers the confidence view shows, derived from demo.json with the app's own formatters."""

import json
from pathlib import Path

import numpy as np

from docs.design.prototype.common import DEMO, split_stretches
from gui.confidence import _pct
from gui.plotting.labels import fmt_r2

HERE = Path(__file__).resolve().parent

p = DEMO['profile']['profiles']['Ka_guest']
c, a = p['conditional'], p['input_aware']
ai = int(np.nanargmax(a['r2']))
h = DEMO['headline']
civ = c['interval_per_M']
out = {
    'aware': {
        'estimate': a['grid_per_M'][ai],
        'best_r2': fmt_r2(a['r2'][ai]),
        'cut': fmt_r2(a['r2_threshold']),
        'cut_levels': [fmt_r2(v) for v in sorted(set(a['r2_cut']))],
        'pct': [_pct(h['low_per_M'] / a['grid_per_M'][ai]), _pct(h['high_per_M'] / a['grid_per_M'][ai])],
    },
    'conditional': {
        'best_r2': fmt_r2(c['best_r2']),
        'cut': fmt_r2(c['r2_threshold']),
        'cut_levels': [fmt_r2(v) for v in sorted(set(c['r2_cut']))],
        'pct': [_pct(civ['low'] / c['best_ka_per_M']), _pct(civ['high'] / c['best_ka_per_M'])],
        'stretches_per_M': [list(map(float, s)) for s in split_stretches(c)],
    },
    'n_points': p['n_points'],
    'n_params': p['n_params'],
}
(HERE / 'confidence_numbers.json').write_text(json.dumps(out, indent=1, ensure_ascii=False))
print(json.dumps(out, indent=1, ensure_ascii=False))
