"""Compute the Simulation view's numbers with the repo's own forward model.

Run from the repo (for its venv), after ``dump_conditional.py``:
    uv run python -m docs.design.prototype.data.compute_simulation

The values are one consistent set: the IDA demo's entered conditions with the fit made
at those inputs (``FitResult.conditional`` in ``conditional_fit.json``), each rounded to
the three figures the window shows, as a user would type them. Writes
``simulation.json`` next to this file: a dense model curve and its speciation
(``simulate_signal`` / ``simulate_species``), the simulated measurement on the even grid
and on IDA_system.txt's own grid (``simulate_dataset``, Gaussian noise, fixed seed), and
the IDA_system.txt replicates read through the app's loader for the overlay.

The noise is stated as one σ in signal units, held fixed while the curve changes. Here
it is passed to ``simulate_dataset`` as ``noise_frac = σ / span``, with the span of the
clean signal at the same points, which is the σ it then draws with. The window needs an
absolute-σ option in ``simulate_dataset`` to do this without the division.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from core.assays.registry import AssayType
from core.data_processing.measurement_set import MeasurementSet
from core.io import load_measurements
from core.simulation import build_concentration_vector, simulate_dataset, simulate_signal, simulate_species
from core.units import Q_
from gui.widgets.assay_conditions import assay_class

HERE = Path(__file__).resolve().parent
REPO = Path.cwd()
FIT = json.loads((HERE / 'conditional_fit.json').read_text())


def fig3(v: float) -> float:
    return float(f'{v:.3g}')


CONDITIONS = {
    'Ka_dye': Q_(fig3(FIT['conditions']['Ka_dye']), '1/M'),
    'h0': Q_(fig3(FIT['conditions']['h0']), 'M'),
    'd0': Q_(fig3(FIT['conditions']['d0']), 'M'),
}
PARAMETERS = {k: fig3(v) for k, v in FIT['conditional'].items()}
START, STOP, POINTS = 0.0, 9e-6, 24
# One σ in a.u.: the scatter of the demo's replicates (rms SD 1 237 a.u.), as typed.
NOISE_SD, REPLICAS, SEED = 1200.0, 3, 0
DENSE = 361  # the drawn curve: every 0.025 µM

cls = assay_class(AssayType.IDA)


def noisy(x: np.ndarray) -> tuple[list, float]:
    span = float(np.ptp(simulate_signal(cls, CONDITIONS, PARAMETERS, x)))
    ms = simulate_dataset(
        cls,
        CONDITIONS,
        PARAMETERS,
        x,
        noise_frac=NOISE_SD / span,
        n_replicas=REPLICAS,
        rng=np.random.default_rng(SEED),
    )
    return [s.tolist() for s in ms.signals], span


x_pts = build_concentration_vector('linear', start=START, stop=STOP, n=POINTS)
x_dense = build_concentration_vector('linear', start=START, stop=STOP, n=DENSE)
y_dense = simulate_signal(cls, CONDITIONS, PARAMETERS, x_dense)
species = simulate_species(cls, CONDITIONS, PARAMETERS, x_dense)
simulated, span = noisy(x_pts)

src = REPO / 'data' / 'IDA_system.txt'
data = MeasurementSet.from_dataframe(load_measurements(str(src)), source_file=str(src))
x_file = np.asarray(data.concentrations, dtype=float)
simulated_file, span_file = noisy(x_file)

out = {
    'conditions': {k: float(v.magnitude) for k, v in CONDITIONS.items()},
    'parameters': PARAMETERS,
    'grid': {'start_M': START, 'stop_M': STOP, 'points': POINTS},
    'noise': {
        'sd_au': NOISE_SD,
        'replicas': REPLICAS,
        'seed': SEED,
        'span_au': span,
        'pct_of_span': 100 * NOISE_SD / span,
    },
    'x_dense_M': x_dense.tolist(),
    'y_dense': y_dense.tolist(),
    'species_M': {k: np.asarray(v, dtype=float).tolist() for k, v in species.items()},
    'x_points_M': x_pts.tolist(),
    'simulated': simulated,
    'overlay': {
        'file': src.name,
        'x_M': x_file.tolist(),
        'replica_ids': list(data.replica_ids),
        'signals': [np.asarray(s, dtype=float).tolist() for s in data.signals],
        'simulated': simulated_file,
        'pct_of_span': 100 * NOISE_SD / span_file,
    },
}
(HERE / 'simulation.json').write_text(json.dumps(out, indent=1))
print('parameters', PARAMETERS, 'conditions', out['conditions'])
print('signal', y_dense.min(), y_dense.max(), 'span', span, 'sd', NOISE_SD, f'{100 * NOISE_SD / span:.2f} %')
print('overlay', data.n_replicas, 'x', x_file * 1e6, 'span', span_file)
for i, x in enumerate(x_file):
    model = float(simulate_signal(cls, CONDITIONS, PARAMETERS, np.array([x]))[0])
    print(f'  {x * 1e6:4.1f} µM  model {model:9.0f}  data mean {np.mean([s[i] for s in data.signals]):9.0f}')
i = int(np.argmin(abs(x_dense - 3e-6)))
print('at', x_dense[i], {k: float(v[i]) for k, v in species.items()}, y_dense[i])
