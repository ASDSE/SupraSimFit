"""The same datasets through the release before the engine, for the comparison the paper draws.

Before the variable-projection engine, a fit was a search from many starting
points: what it reported was one attempt out of the pool it kept, and the
spread of that pool was what stood where an interval stands now. This check
runs that release on the same synthetic datasets and asks the one question the
two answers can be compared on — does the range the previous approach reports
hold the true binding constant, and does the interval.

The old code is not imported. It is extracted from its commit into a
directory of its own and run in a subprocess with that directory on the path,
so the comparison needs nothing but this repository and reaches for none of
the present modules.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np

from core.pipeline.varpro import Projection
from validation.generate import dataset
from validation.scenarios import Scenario
from validation.score import guard

__all__ = ['LEGACY_COMMIT', 'archive', 'row']

#: The commit the comparison runs: the last one before the present engine.
LEGACY_COMMIT = 'ccba0f1'

#: How long one fit of the previous release may take before the row says so.
TIMEOUT_SECONDS = 600

_REPO_ROOT = Path(__file__).resolve().parents[1]

#: Run in the extracted tree, with that tree alone on the path. It reads one
#: job as JSON on stdin and writes one answer as JSON on stdout: the lowest and
#: highest value of each binding constant over the pool of attempts the release
#: kept, read through its own reporting function, or the note that the pool is
#: empty.
_RUNNER = """
import json, sys
import numpy as np
from core.assays import ASSAY_CLASSES
from core.assays.registry import AssayType
from core.pipeline.fit_pipeline import FitConfig, fit_assay, summarize_parameters
from core.units import Q_

job = json.load(sys.stdin)
conditions = {k: (v if isinstance(v, str) else Q_(v[0], v[1])) for k, v in job['conditions'].items()}
assay = ASSAY_CLASSES[AssayType[job['assay']]](
    x_data=Q_(np.array(job['x']), 'M'), y_data=Q_(np.array(job['y']), 'au'), **conditions
)
result = fit_assay(assay, FitConfig(seed=job['seed']))
if not result.parameters:
    print(json.dumps({'spans': None}))
else:
    spans = {}
    for report in summarize_parameters(result):
        if not report.is_log and report.key.startswith('Ka') and report.stats is not None:
            spans[report.key] = [report.stats['min'], report.stats['max'], report.estimate]
    print(json.dumps({'spans': spans}))
"""


def archive() -> Path:
    """The extracted tree of :data:`LEGACY_COMMIT`, extracting it on first use.

    The extraction goes to a directory of its own next to the target and is
    renamed into place, so several worker processes reaching here at once end
    with one complete tree rather than a half-written one.
    """
    target = Path(tempfile.gettempdir()) / f'supra-validation-{LEGACY_COMMIT}'
    if (target / 'core' / 'pipeline' / 'fit_pipeline.py').exists():
        return target
    staging = Path(tempfile.mkdtemp(prefix=f'{target.name}-', dir=target.parent))
    subprocess.run(
        f'git -C {_REPO_ROOT} archive {LEGACY_COMMIT} | tar -x -C {staging}',
        shell=True,
        check=True,
        capture_output=True,
    )
    try:
        os.rename(staging, target)
    except OSError:
        # Another worker got there first; its tree is the same commit.
        pass
    return target


def previous_release(data, seed: int) -> dict[str, list[float]] | None:
    """Fit *data* with the previous release and return each binding constant's pool range.

    Returns
    -------
    dict[str, list[float]] | None
        ``key -> [lowest, highest, reported]`` in 1/M, or ``None`` when no
        attempt passed the release's quality filter.
    """
    job = {
        'assay': data.scenario.assay,
        'x': data.entered_x.tolist(),
        'y': data.signals.mean(axis=0).tolist(),
        'conditions': {
            key: value if isinstance(value, str) else [float(value.magnitude), str(value.units)]
            for key, value in data.conditions.items()
        },
        'seed': int(seed),
    }
    tree = archive()
    finished = subprocess.run(
        [sys.executable, '-c', _RUNNER],
        input=json.dumps(job),
        capture_output=True,
        text=True,
        cwd=tree,
        env={**os.environ, 'PYTHONPATH': str(tree)},
        timeout=TIMEOUT_SECONDS,
    )
    if finished.returncode != 0:
        raise RuntimeError(f'the previous release failed on this dataset: {finished.stderr.strip()[-400:]}')
    return json.loads(finished.stdout.splitlines()[-1])['spans']


def row(scenario: Scenario, seed: int) -> dict[str, Any]:
    """One dataset answered by both: the present interval, and the previous release's range.

    Returns
    -------
    dict
        Per binding constant, whether each holds the truth and how wide each
        is in decades of Ka, with ``no_fit`` where the previous release kept no
        attempt.
    """
    started = time.perf_counter()
    data = dataset(scenario, seed)

    def work() -> dict[str, Any]:
        projection = Projection(data.assay, data.assay.get_default_bounds())
        fit = projection.fit()
        out: dict[str, Any] = {'covers': {}, 'width': {}, 'previous_covers': {}, 'previous_width': {}}
        for key in projection.free_ka:
            interval = projection.interval(key, fit)
            out['covers'][key] = bool(interval.low <= data.truth[key] <= interval.high)
            out['width'][key] = float(np.log10(interval.high / interval.low))
        spans = previous_release(data, seed)
        out['no_fit'] = spans is None
        for key in projection.free_ka:
            span = None if spans is None else spans.get(key)
            if span is None or span[0] <= 0:
                out['previous_covers'][key] = None
                out['previous_width'][key] = None
                continue
            out['previous_covers'][key] = bool(span[0] <= data.truth[key] <= span[1])
            out['previous_width'][key] = float(np.log10(span[1] / span[0]))
        return out

    result = guard(work)
    result['t_total'] = time.perf_counter() - started
    return result
