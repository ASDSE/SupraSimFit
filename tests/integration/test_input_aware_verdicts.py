"""The drawn input-aware profile and the interval cut from it give every Ka one verdict.

The interval is cut from the profile at the points it reads, and the curve is
then drawn through more of them, each continued from both sides. Where drawing
finds a lower solution at a point the interval was cut from, that solution can
fit another rank of the signal columns, and so be judged against another
cut-off, although its objective barely moved. The interval must then be cut
again with it: the reading the headline reports and the strip and readout
drawn from the curve may not disagree on whether a Ka is accepted.

The titration is the weak-binding IDA case of the input-aware-coverage check
(``K=0.1``, 30 points, 0.5 % noise, every input stated, seed 1), where the
offset reaches its bound at a Ka just inside the interval.
"""

import numpy as np
import pytest

from core.assays import ASSAY_CLASSES
from core.assays.registry import AssayType
from core.pipeline.fit_pipeline import FitConfig, fit_measurement_set
from validation.generate import dataset
from validation.scenarios import Scenario, stated_specs
from validation.score import measurement_set


@pytest.fixture(scope='module')
def aware():
    scenario = Scenario(assay='IDA', regime=0.1, n_points=30, noise=0.005, specs=stated_specs('IDA'))
    data = dataset(scenario, 1)
    result = fit_measurement_set(
        measurement_set(data),
        ASSAY_CLASSES[AssayType.IDA],
        dict(data.conditions),
        FitConfig(per_replica=False, errors=scenario.error_model),
    )
    return result.aware.profiles['Ka_guest']


def test_every_drawn_point_is_judged_as_the_interval_judges_it(aware):
    interval = aware.interval
    logs, drop = np.log10(aware.grid), aware.scaled_drop()
    low, high = np.log10(interval.low), np.log10(interval.high)
    inside = (logs > low + 1e-9) & (logs < high - 1e-9)
    outside = (logs < low - 1e-9) | (logs > high + 1e-9)
    rejected_inside = logs[inside & (drop > 1.0 + 1e-9)]
    accepted_outside = logs[outside & (drop < 1.0)]
    assert accepted_outside.size == 0, f'accepted outside the interval at log Ka {accepted_outside}'
    if interval.split:
        assert rejected_inside.size > 0, 'a split interval with no rejected Ka drawn inside it'
    else:
        assert rejected_inside.size == 0, f'rejected inside an unsplit interval at log Ka {rejected_inside}'
