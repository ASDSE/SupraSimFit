"""Split data/GDA_system.txt into three run files, load them as the app does, cache what the view shows."""

import json
from pathlib import Path

import numpy as np

from core.data_processing.measurement_set import MeasurementSet
from core.data_processing.preprocessing import apply_preprocessing
from core.io import load_measurements, load_measurements_multi
from core.io.registry import get_reader

repo = Path.cwd()
out = Path(__file__).resolve().parent
src = load_measurements(repo / 'data' / 'GDA_system.txt')
paths = []
for k, (rid, block) in enumerate(src.groupby('replica', sort=True)):
    p = out / f'GDA_run{k + 1}.txt'
    lines = ['var\tsignal']
    for c, s in zip(block['concentration'], block['signal']):
        lines.append(f'{c!r}\t{s!r}')
    p.write_text('\n'.join(lines) + '\n')
    paths.append(p)

combined = load_measurements_multi(paths)
ms = MeasurementSet.from_dataframe(combined, source_file=str(paths[0]), source_files=[str(p) for p in paths])
# same grid as the original file, in molar
assert np.allclose(ms.concentrations, np.sort(src['concentration'].unique()), rtol=1e-9, atol=0)
signals = np.asarray(ms.signals)
# the step the Outlier Removal panel's Apply runs, at its defaults
active = signals
median = np.median(active, axis=0)
mad = np.median(np.abs(active - median), axis=0)
z = np.where(mad > 0, 0.6745 * np.abs(active - median) / mad, 0.0)
apply_preprocessing(ms, [{'name': 'zscore_replica_filter', 'params': {'threshold': 3.5, 'min_replicas': 3}}])
data = {
    'files': [
        {
            'name': p.name,
            'reader': type(get_reader(p)).__name__,
            'replica_id': rid,
            'points': int(ms.n_points),
            'declared_unit': 'M',
        }
        for p, rid in zip(paths, ms.replica_ids)
    ],
    'x_M': [float(v) for v in ms.concentrations],
    'x_uM_face': [float(f'{v * 1e6:.6g}') for v in ms.concentrations],
    'signals': signals.tolist(),
    'replica_ids': list(ms.replica_ids),
    'active': [bool(ms.is_active(r)) for r in ms.replica_ids],
    'max_z': z.max(axis=1).tolist(),
    'argmax_z': z.argmax(axis=1).tolist(),
    'log': ms.processing_log,
    'n_points': int(ms.n_points),
    'n_replicas': int(ms.n_replicas),
}
(out / 'measurements.json').write_text(json.dumps(data, indent=1, default=str))
print(
    json.dumps(
        {k: data[k] for k in ('files', 'replica_ids', 'active', 'max_z', 'argmax_z', 'log', 'n_points')},
        indent=1,
        default=str,
    )
)
print(data['x_uM_face'])
