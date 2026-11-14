"""Shared GUI-test fixtures.

A single session-scoped ``qapp`` fixture lives here because ``QApplication``
is a process singleton — every GUI test in this package reuses the same
instance. The ``minimal_plot_data`` fixture is provided by the root
``tests/conftest.py`` and is used unchanged by the GUI tests.
"""

from __future__ import annotations

import gc
import os
import sys

import pytest


@pytest.fixture(scope='session')
def qapp():
    from PyQt6.QtCore import QCoreApplication, QSettings
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)
    # The preferences a test writes go to a store of this test process's own: never the user's,
    # and never that of a run going on at the same time in another worktree.
    QCoreApplication.setOrganizationName('SupraSimFit-Test')
    QCoreApplication.setApplicationName(f'gui-tests-{os.getpid()}')
    QSettings().clear()
    yield app
    QSettings().clear()


@pytest.fixture(autouse=True)
def _free_dropped_widgets(qapp):
    """Destroy the widgets a test drops, while no Qt event is being handled.

    A dropped top-level widget caught in a reference cycle outlives its test
    and still owns the items of its graphics scene. Freeing it while one of its
    own queued events is being delivered leaves Qt walking freed items, so each
    test ends by collecting garbage and draining the event queue instead.
    """
    yield
    gc.collect()
    qapp.processEvents()
    qapp.sendPostedEvents(None, 0)


@pytest.fixture(scope='session')
def demo():
    """The IDA demo fitted as the app fits it with every input exact, and the Ka profile of that fit.

    Shared by the tests of Ka confidence's rules and of its view.
    """
    import pathlib

    from core.assays import IDAAssay
    from core.data_processing.measurement_set import MeasurementSet
    from core.data_processing.preprocessing import get_step
    from core.io import load_measurements
    from core.pipeline.fit_pipeline import FitConfig, fit_measurement_set
    from core.pipeline.profile import fit_profile
    from core.units import Q_

    ms = MeasurementSet.from_dataframe(
        load_measurements(str(pathlib.Path(__file__).resolve().parents[3] / 'data' / 'IDA_system.txt'))
    )
    get_step('zscore_replica_filter', {'threshold': 3.5, 'min_replicas': 3})(ms)
    conditions = {'h0': Q_(4.3e-6, 'M'), 'd0': Q_(6e-6, 'M'), 'Ka_dye': Q_(16.8e6, '1/M')}
    config = FitConfig(per_replica=False)
    fit = fit_measurement_set(ms, IDAAssay, conditions, config)
    profile = fit_profile(ms, IDAAssay, conditions, config, **fit.profile_arguments())
    return fit, profile
