"""Shared GUI-test fixtures.

A single session-scoped ``qapp`` fixture lives here because ``QApplication``
is a process singleton — every GUI test in this package reuses the same
instance. The ``minimal_plot_data`` fixture is provided by the root
``tests/conftest.py`` and is used unchanged by the GUI tests.
"""

from __future__ import annotations

import sys

import pytest


@pytest.fixture(scope="session")
def qapp():
    from PyQt6.QtWidgets import QApplication

    return QApplication.instance() or QApplication(sys.argv)
