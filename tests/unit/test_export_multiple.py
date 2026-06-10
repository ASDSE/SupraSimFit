"""Tests for the batch-export helpers in gui.session (no Qt required)."""

from __future__ import annotations

from pathlib import Path

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
