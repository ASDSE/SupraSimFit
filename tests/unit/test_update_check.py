"""Tests for :func:`gui.update_check.is_newer`.

Pure-function tests — no GitHub network, no Qt. Verifies version comparison
behaves sanely under the prefixes and shapes our release tags actually use
(``v1.2``, ``v1.0.1``, ``1.2.0``).
"""

from __future__ import annotations

import pytest

from gui.update_check import is_newer


class TestIsNewer:
    """Behaviour of ``is_newer(remote_tag, local)``."""

    def test_strictly_newer_minor(self):
        assert is_newer('v1.3.0', '1.2.0') is True

    def test_strictly_newer_patch(self):
        assert is_newer('v1.2.1', '1.2.0') is True

    def test_equal_versions(self):
        assert is_newer('v1.2.0', '1.2.0') is False

    def test_older_version(self):
        assert is_newer('v1.1.0', '1.2.0') is False

    def test_short_vs_long_form_equal(self):
        """``v1.2`` and ``1.2.0`` normalize equal."""
        assert is_newer('v1.2', '1.2.0') is False
        assert is_newer('v1.2.0', '1.2') is False

    def test_no_v_prefix(self):
        """Leading 'v' is optional on both sides."""
        assert is_newer('1.3.0', '1.2.0') is True
        assert is_newer('1.2.0', '1.3.0') is False

    @pytest.mark.parametrize('bad', ['', 'garbage', 'v', 'release-2025'])
    def test_unparseable_remote_returns_false(self, bad):
        """Malformed remote tags must not raise — treat as 'not newer'."""
        assert is_newer(bad, '1.2.0') is False
