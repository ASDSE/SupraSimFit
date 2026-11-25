"""Tests for :func:`gui.update_check.is_newer`.

Pure-function tests — no GitHub network, no Qt. Verifies version comparison
behaves sanely under the prefixes and shapes our release tags actually use
(``v1.2``, ``v1.0.1``, ``1.2.0``).
"""

from __future__ import annotations

import pytest

from gui.update_check import is_newer, newest_release


class TestIsNewer:
    """Behaviour of ``is_newer(remote_tag, local)``."""

    def test_strictly_newer_minor(self):
        assert is_newer('v1.3.0', '1.2.0') is True

    def test_equal_versions(self):
        assert is_newer('v1.2.0', '1.2.0') is False

    @pytest.mark.parametrize('bad', ['', 'garbage', 'v', 'release-2025'])
    def test_unparseable_remote_returns_false(self, bad):
        """Malformed remote tags must not raise — treat as 'not newer'."""
        assert is_newer(bad, '1.2.0') is False


def test_a_beta_build_is_offered_the_newest_published_release_beta_or_stable():
    releases = [
        {'tag_name': 'v1.5.0'},
        {'tag_name': 'v2.0.0b2'},
        {'tag_name': 'v2.0.0b3', 'draft': True},
        {'tag_name': 'preview-ka-uncertainty-framework'},
        {'tag_name': 'v2.0.0b1'},
    ]
    assert newest_release(releases)['tag_name'] == 'v2.0.0b2'
    assert newest_release([*releases, {'tag_name': 'v2.0.0'}])['tag_name'] == 'v2.0.0'
    assert is_newer('v2.0.0b2', '2.0.0b1') and is_newer('v2.0.0', '2.0.0b2')
