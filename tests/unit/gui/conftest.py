"""Shared GUI-test fixtures.

A single session-scoped ``qapp`` fixture lives here because ``QApplication``
is a process singleton — every GUI test in this package reuses the same
instance. The ``minimal_plot_data`` fixture is provided by the root
``tests/conftest.py`` and is used unchanged by the GUI tests.
"""

from __future__ import annotations

import gc
import sys

import pytest


@pytest.fixture(scope='session')
def qapp():
    from PyQt6.QtWidgets import QApplication

    return QApplication.instance() or QApplication(sys.argv)


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
