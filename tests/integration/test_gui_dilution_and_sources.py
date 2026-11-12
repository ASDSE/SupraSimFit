"""A titration whose additions diluted the sample, fitted with one error its two stocks share.

The two things this step adds to a fit's record are the dilution by the
titrant — a titrant stock concentration and the species that stock itself holds
— and the error sources several inputs have in common.  Both belong to the fit:
the first is part of the model its numbers come from, the second is part of what
its interval covers.  So both have to survive the round trip through a results
file: the exported fit has to verify against the data it was made on, and the
session that reads it back has to show it instead of a note saying it does not
describe what is set now.

The fit is a real one, with an input free to move, which is what makes this an
integration test.  That the dilution moves the fitted constant to where it
belongs is :mod:`tests.integration.test_dilution_recovery`; what is checked here
is the record.
"""

from __future__ import annotations

import sys
import time

import numpy as np
import pytest

pytest.importorskip('PyQt6')

from core.assays.ida import IDAAssay  # noqa: E402
from core.assays.registry import AssayType  # noqa: E402
from core.data_processing.measurement_set import MeasurementSet  # noqa: E402
from core.pipeline.fit_pipeline import FitConfig  # noqa: E402
from core.pipeline.inputs import SharedSource, shared_key  # noqa: E402
from core.pipeline.results_io import verify_imported_result  # noqa: E402
from core.units import Q_  # noqa: E402
from tests.conftest import IDA_TRUE  # noqa: E402

#: The stock the titrant was added from: ten times the last titrant
#: concentration, so the sample is at 90 % of its starting concentration by the
#: end of the titration — an ordinary titration, and far more than the fit's own
#: precision.
_STOCK = Q_(10 * 50e-6, 'M')

#: The error the host and the dye stock have in common, because both were made
#: up with the same balance.
_SHARED = SharedSource('Host and dye stock', 4.0, ('h0', 'd0'))


def _diluted_data() -> MeasurementSet:
    """Two replicates of an IDA titration the additions dilute, at 1 % noise."""
    x = np.linspace(0, 50e-6, 14)
    assay = IDAAssay(
        x_data=Q_(x, 'M'),
        y_data=Q_(np.zeros_like(x), 'au'),
        Ka_dye=Q_(IDA_TRUE['Ka_dye'], '1/M'),
        h0=Q_(IDA_TRUE['h0'], 'M'),
        d0=Q_(IDA_TRUE['d0'], 'M'),
        titrant_stock=_STOCK,
    )
    clean = assay.forward_model(
        np.array([IDA_TRUE[key] for key in ('Ka_guest', 'I0', 'I_dye_free', 'I_dye_bound')])
    ).magnitude
    rng = np.random.default_rng(0)
    signals = np.vstack([clean * (1 + 0.01 * rng.standard_normal(clean.size)) for _ in range(2)])
    return MeasurementSet(concentrations=x, signals=signals, replica_ids=('a', 'b'))


def _wait_until(qapp, condition, timeout: float = 300.0) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, 'timed out waiting for the fit'
        qapp.processEvents()
        time.sleep(0.01)


@pytest.fixture(scope='module')
def qapp():
    """The one QApplication of the process; a QWidget cannot be built without it."""
    from PyQt6.QtWidgets import QApplication

    return QApplication.instance() or QApplication(sys.argv)


@pytest.fixture
def make_session(qapp, monkeypatch):
    """A session on the diluted data, with the dilution and the shared source stated."""
    from gui.fitting_session import FittingSession

    dialogs: list = []
    monkeypatch.setattr('gui.fitting_session.QMessageBox.warning', lambda *args: dialogs.append(args))

    built = []

    def build():
        session = FittingSession()
        built.append(session)
        session._assay_panel.set_assay_type(AssayType.IDA)
        for key, value in (('Ka_dye', IDA_TRUE['Ka_dye']), ('h0', IDA_TRUE['h0']), ('d0', IDA_TRUE['d0'])):
            session._assay_panel._field_widgets[key].setValue(value)
        session._assay_panel._stock_widget.setValue(_STOCK.magnitude)
        session._assay_panel._dilution_combo.setCurrentIndex(1)
        session._input_panel._add_shared_row(_SHARED)
        session._input_panel.specs_changed.emit()
        session._fit_panel.set_config(FitConfig(per_replica=False))
        session._data_panel.data_loaded.emit(_diluted_data())
        return session, dialogs

    yield build
    for session in built:
        session.model.shutdown()


def test_a_diluted_fit_with_a_shared_source_is_read_back_as_the_fit_it_was(qapp, make_session, tmp_path):
    """Exported and imported again, the fit verifies on its own data and the session shows it."""
    from gui.session import export_results, import_results

    fitting, dialogs = make_session()
    fitting.run_fit()
    _wait_until(qapp, lambda: fitting.model.fit_results)
    (made,) = fitting.model.fit_results
    assert dialogs == [], 'nothing about the configuration stopped the fit'

    # The two facts are in the fit's own record, where every report reads them.
    assert made.conditions['titrant_stock'].to('M').magnitude == pytest.approx(_STOCK.magnitude)
    assert made.conditions['stock_contains'] == ()
    assert made.fit_config['shared_sources'] == [{'name': _SHARED.name, 'sigma_pct': 4.0, 'inputs': ['h0', 'd0']}]
    assert shared_key(_SHARED.name) in made.input_shifts

    path = tmp_path / 'diluted.json'
    export_results([made], path)
    (read_back,) = import_results(path)
    # A list in JSON, a tuple in the record, so the conditions compare equal.
    assert read_back.conditions['stock_contains'] == ()

    status, checked = verify_imported_result(read_back, _diluted_data())
    assert status == 'verified'

    # A second session, set up the same way, shows the imported fit with no note.
    other, _ = make_session()
    other.model.show_imported([checked], str(path))

    assert other.model.fit_results == [checked]
    assert other.model.hidden_results_note() is None
