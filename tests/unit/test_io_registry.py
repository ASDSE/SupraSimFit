"""Tests for the content-sniffing reader registry.

Covers the dispatch contract introduced when multiple readers share an
extension (the JASCO/EnSight readers both target ``.csv`` alongside the
generic ``CsvReader``):

* registration preserves order
* ``get_reader`` walks candidates and honours each reader's ``can_read``
* readers without ``can_read`` are always-accepting (fallback)
* an empty candidate list (or all sniffers rejecting) raises ``ValueError``

The existing readers (TXT, XLSX, generic CSV) are still reachable through
the new dispatcher — these tests double as a regression net.
"""

from pathlib import Path

import pandas as pd
import pytest

# Importing the package (not just registry) triggers the side-effect
# registration of the built-in readers (TxtReader, CsvReader, XlsxReader)
# via core.io.__init__. Without this, running this module in isolation
# (e.g. pytest tests/unit/test_io_registry.py::TestRegistry::test_existing_extensions_still_dispatch)
# would find an empty registry and become order-dependent.
import core.io  # noqa: F401
from core.io.registry import READERS, get_reader, register_reader


@pytest.fixture
def isolated_registry(monkeypatch):
    """Snapshot READERS and restore after the test."""
    snapshot = {ext: list(candidates) for ext, candidates in READERS.items()}
    yield
    READERS.clear()
    READERS.update(snapshot)


class _Accepter:
    extensions = ('.dummy',)

    @classmethod
    def can_read(cls, path: Path) -> bool:
        return True

    def read(self, path: Path) -> pd.DataFrame:
        return pd.DataFrame({'concentration': [0.0], 'signal': [1.0], 'replica': [0]})


class _Rejecter:
    extensions = ('.dummy',)

    @classmethod
    def can_read(cls, path: Path) -> bool:
        return False

    def read(self, path: Path) -> pd.DataFrame:
        raise AssertionError('Rejecter.read should never be called')


class _Fallback:
    """No can_read → always-accepting fallback."""

    extensions = ('.dummy',)

    def read(self, path: Path) -> pd.DataFrame:
        return pd.DataFrame({'concentration': [0.0], 'signal': [2.0], 'replica': [0]})


class TestRegistry:
    def test_existing_extensions_still_dispatch(self, tmp_path):
        """Default registrations (txt, csv, xlsx) survive the rewrite."""
        p = tmp_path / 'x.txt'
        p.write_text('var\tsignal\n0.0\t100.0\n')
        reader = get_reader(p)
        assert type(reader).__name__ == 'TxtReader'

    def test_unknown_extension_raises(self, tmp_path):
        with pytest.raises(ValueError, match='No reader for'):
            get_reader(tmp_path / 'nope.unknownext')

    def test_first_matching_sniffer_wins(self, tmp_path, isolated_registry):
        register_reader(_Rejecter)
        register_reader(_Accepter)
        register_reader(_Fallback)
        p = tmp_path / 'x.dummy'
        p.touch()
        reader = get_reader(p)
        assert isinstance(reader, _Accepter)

    def test_no_can_read_acts_as_fallback(self, tmp_path, isolated_registry):
        register_reader(_Rejecter)
        register_reader(_Fallback)
        p = tmp_path / 'x.dummy'
        p.touch()
        reader = get_reader(p)
        assert isinstance(reader, _Fallback)

    def test_all_sniffers_reject_raises(self, tmp_path, isolated_registry):
        register_reader(_Rejecter)
        p = tmp_path / 'x.dummy'
        p.touch()
        with pytest.raises(ValueError, match='No registered reader accepted'):
            get_reader(p)

    def test_register_is_idempotent(self, isolated_registry):
        before = len(READERS.get('.dummy', []))
        register_reader(_Accepter)
        register_reader(_Accepter)
        after = len(READERS.get('.dummy', []))
        assert after == before + 1

    def test_registration_order_preserved(self, isolated_registry):
        register_reader(_Accepter)
        register_reader(_Rejecter)
        register_reader(_Fallback)
        assert READERS['.dummy'] == [_Accepter, _Rejecter, _Fallback]
