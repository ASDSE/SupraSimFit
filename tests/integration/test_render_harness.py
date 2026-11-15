"""The render harness draws Demo IDA's fitted state only once its fit and Ka profile are done.

Demo IDA states input uncertainties, so its fit is the input-aware one, which costs
seconds: this check lives here, the slow layer.
"""

from __future__ import annotations

import os
import sys
from unittest import mock

import pytest

pytest.importorskip('PyQt6')


@pytest.fixture(scope='module')
def qapp():
    """The one QApplication of the process, with a preferences store of this test process's own."""
    from PyQt6.QtCore import QCoreApplication, QSettings
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)
    QCoreApplication.setOrganizationName('SupraSimFit-Test')
    QCoreApplication.setApplicationName(f'integration-tests-{os.getpid()}')
    QSettings().clear()
    yield app
    QSettings().clear()


def test_the_fitted_state_is_drawn_after_the_fit_and_its_profile(qapp):
    from docs.design.render import render
    from gui.main_window import FittingMainWindow

    seen: list[tuple[bool, bool]] = []
    grab = FittingMainWindow.grab

    def noting_grab(window, *args):
        model = window.active_session().model
        seen.append((model.running(), model.profile is not None))
        return grab(window, *args)

    with mock.patch.object(FittingMainWindow, 'grab', noting_grab):
        image = render('Ka confidence', state='demo-fitted')

    assert (image.width(), image.height()) == (1440, 900)
    assert seen == [(False, True)]
