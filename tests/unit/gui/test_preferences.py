"""Tests for :mod:`gui.preferences` round-trip and default behaviour.

These tests isolate themselves by giving each test a unique
``QCoreApplication.applicationName`` so their QSettings stores never
collide with each other or with a real user profile.
"""

from __future__ import annotations

import uuid

import pytest

pytest.importorskip('PyQt6')

from PyQt6.QtCore import QCoreApplication, QSettings


@pytest.fixture(autouse=True)
def _isolated_settings():
    """Point QSettings at a throwaway application name for every test."""
    suffix = uuid.uuid4().hex[:8]
    QCoreApplication.setOrganizationName('SupraSimFit-Test')
    QCoreApplication.setApplicationName(f'fitting_app_test_{suffix}')
    QSettings().clear()
    QSettings().sync()
    yield
    QSettings().clear()
    QSettings().sync()


def test_get_bool_returns_default_when_unset():
    from gui.preferences import get_bool

    assert get_bool('bmg/skip_import_prompt', default=False) is False
    assert get_bool('bmg/skip_import_prompt', default=True) is True


def test_set_and_get_bool_round_trip():
    from gui.preferences import BMG_SKIP_IMPORT_PROMPT, get_bool, set_bool

    set_bool(BMG_SKIP_IMPORT_PROMPT, True)
    assert get_bool(BMG_SKIP_IMPORT_PROMPT) is True

    set_bool(BMG_SKIP_IMPORT_PROMPT, False)
    assert get_bool(BMG_SKIP_IMPORT_PROMPT) is False


def test_string_backed_values_are_coerced():
    """Some platforms store booleans as strings; the wrapper must coerce."""
    from gui.preferences import get_bool

    s = QSettings()
    s.setValue('bmg/skip_import_prompt', 'true')
    s.sync()
    assert get_bool('bmg/skip_import_prompt') is True
