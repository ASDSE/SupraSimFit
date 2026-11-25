"""The batch export: the helper in gui.session, and what the Export All dialog tells the user when a write fails."""

from __future__ import annotations

from pathlib import Path

import pytest

from gui.session import ExportableArtefact, export_batch


def _write_text(content: str):
    def writer(p: Path) -> None:
        p.write_text(content)

    return writer


def _raise(message: str):
    def writer(_p: Path) -> None:
        raise RuntimeError(message)

    return writer


def test_export_batch_collects_exceptions_and_continues(tmp_path: Path) -> None:
    arts = [
        ExportableArtefact(
            key='ok1',
            label='OK1',
            suffix='.txt',
            available=True,
            writer=_write_text('1'),
        ),
        ExportableArtefact(
            key='bad',
            label='Bad',
            suffix='.txt',
            available=True,
            writer=_raise('boom'),
        ),
        ExportableArtefact(
            key='ok2',
            label='OK2',
            suffix='.json',
            available=True,
            writer=_write_text('2'),
        ),
    ]
    outcomes = export_batch(arts, tmp_path, 'base')

    statuses = [(label, exc is None) for label, _p, exc in outcomes]
    assert statuses == [('OK1', True), ('Bad', False), ('OK2', True)]
    # Successful writes still happened despite the failure in between.
    assert (tmp_path / 'base.txt').read_text() == '1'
    assert (tmp_path / 'base.json').read_text() == '2'
    # The failing entry carries the original exception.
    assert isinstance(outcomes[1][2], RuntimeError)
    assert 'boom' in str(outcomes[1][2])


@pytest.fixture
def dialog(monkeypatch, tmp_path):
    """The Export All dialog of an empty session, its settings in *tmp_path* and its warnings recorded."""
    pytest.importorskip('PyQt6')
    from PyQt6.QtCore import QSettings
    from PyQt6.QtWidgets import QApplication

    from gui.dialogs import export_multiple_dialog as module
    from gui.fitting_session import FittingSession

    app = QApplication.instance() or QApplication([])  # held while the test runs, or Qt tears it down
    settings = str(tmp_path / 'settings.ini')
    monkeypatch.setattr(module, '_settings', lambda: QSettings(settings, QSettings.Format.IniFormat))
    shown: list[tuple] = []
    monkeypatch.setattr(module.QMessageBox, 'warning', lambda *args: shown.append(args))
    session = FittingSession()
    built = module.ExportMultipleDialog(session, select_all_default=True)
    built._folder_edit.setText(str(tmp_path / 'out'))
    built.warnings = shown
    yield built
    del app


def test_the_failures_of_a_batch_are_said_in_plain_words(dialog, monkeypatch):
    """A library's own message is written for a developer; a message the app wrote for the user is shown as is."""
    from gui.dialogs import export_multiple_dialog as module
    from gui.plotting.export import ExportRefused

    budget = 'The budget has no rows to write: run a Sobol’ analysis first.'
    monkeypatch.setattr(
        module,
        'export_batch',
        lambda arts, folder, base: [
            ('Fit results (JSON)', folder / 'a.json', PermissionError(13, 'Permission denied', '/out/a.json')),
            ('Ka uncertainty budget', folder / 'a.csv', ExportRefused(budget)),
            # numpy and json raise ValueError too, with their own wording.
            ('Fit results (CSV)', folder / 'a.csv', ValueError('operands could not be broadcast together')),
            ('Plot style', folder / 'a_style.json', None),
        ],
    )

    dialog._on_export()

    ((_, title, text),) = dialog.warnings
    assert title == 'Export — some artefacts failed'
    assert 'Errno' not in text and 'Permission denied' not in text
    assert '• Fit results (JSON): could not be written.' in text
    assert '• Fit results (CSV): could not be written.' in text and 'broadcast' not in text
    assert f'• Ka uncertainty budget: {budget}' in text
    assert 'Check that the folder exists and that you may write there.' in text


def test_a_folder_that_cannot_be_made_is_said_in_plain_words(dialog, monkeypatch, tmp_path):
    blocker = tmp_path / 'file'
    blocker.write_text('')
    dialog._folder_edit.setText(str(blocker / 'inside'))

    dialog._on_export()

    ((_, title, text),) = dialog.warnings
    assert title == 'Export Error'
    assert text == (
        f'Could not create the folder {blocker / "inside"}. Check the folder name and that you may write there, '
        'then export again.'
    )
    assert dialog.result() != dialog.DialogCode.Accepted
