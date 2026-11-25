"""The window with Demo IDA fitted gives every painted component its room and cuts no plot header (DESIGN.md §6, §7).

Demo IDA states input uncertainties, so its fit is the input-aware one, which costs
seconds: this sweep lives here, the slow layer. Its fit is drawn at the fitted input
shifts, so the titration headers of Fit results and Plot appearance carry their
description beside the legend of eight replicates; a sensitivity run, stood in for by a
finished one, shows the index chart, the sample histogram and the budget.
"""

from __future__ import annotations

import os
import sys

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


def _wait(app, model) -> None:
    import time

    deadline = time.monotonic() + 600
    while model.running():
        assert time.monotonic() < deadline, 'the demo fit did not finish'
        app.processEvents()
        time.sleep(0.01)


def test_every_painted_component_of_the_fitted_demo_gets_its_room_and_no_plot_header_is_cut(qapp, monkeypatch):
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QMessageBox

    from gui import workers
    from gui.main_window import FittingMainWindow
    from tests.unit.gui import layout_rules
    from tests.unit.gui import sensitivity_results as F
    from tests.unit.gui.menus import settle, sweep

    monkeypatch.setattr(FittingMainWindow, '_run_update_check', lambda self, silent: None)
    monkeypatch.setattr('gui.fitting_session.QMessageBox.question', lambda *a: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(workers, 'run_sensitivity', F.fake_run(1))
    window = FittingMainWindow()
    window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    window.resize(1440, 900)
    window.show()
    session = window.active_session()
    try:
        session.load_demo_ida()
        _wait(qapp, session.model)
        session.run_sensitivity()
        _wait(qapp, session.model)
        settle(qapp)
        assert session.model.fit_results[-1].input_shifts and session.model.sensitivity_result is not None

        seen = sweep(qapp, window, check=layout_rules.check)

        assert {where: found for where, found in seen.items() if found} == {}
    finally:
        window.close()
