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
    from docs.design import render as R

    seen: list[tuple[bool, bool]] = []
    snapshot = R._snapshot

    def noting_snapshot(window, scale):
        model = window.active_session().model
        seen.append((model.running(), model.profile is not None))
        return snapshot(window, scale)

    with mock.patch.object(R, '_snapshot', noting_snapshot):
        image = R.render('Ka confidence', state='demo-fitted')

    assert (image.width(), image.height()) == (1440, 900)
    assert seen == [(False, True)]


def test_the_heatmap_state_reads_the_cell_under_the_pointer(qapp):
    """``demo-heatmap`` holds a finished heatmap, and *pointer* moves the readout to the cell under it."""
    from docs.design import render as R
    from gui import sensitivity as S

    seen: list[tuple] = []
    snapshot = R._snapshot

    def noting_snapshot(window, scale):
        session = window.active_session()
        (figure,) = session._sensitivity.heatmap_figures
        hm = figure.hm
        vb = figure.main.getPlotItem().getViewBox()
        area = vb.viewRect()
        x, y = area.left() + 0.3 * area.width(), area.bottom() - 0.7 * area.height()
        ix, iy = int(abs(hm.x - x).argmin()), int(abs(hm.y - y).argmin())
        seen.append(
            (session.model.running(), figure.cell.isVisible(), figure.card.title, S.heatmap_readout(hm, ix, iy)[0])
        )
        return snapshot(window, scale)

    with mock.patch.object(R, '_snapshot', noting_snapshot):
        R.render('Sensitivity', state='demo-heatmap', pointer=(0.3, 0.7))

    ((running, outlined, title, expected),) = seen
    assert not running and outlined and title == expected
