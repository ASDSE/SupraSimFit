"""Tests for gui.plotting.colors — no QApplication required."""

import pytest

from gui.plotting.colors import (
    AVERAGE_LINE_COLOR,
    DROPPED_REPLICA_COLOR,
    ERROR_BAR_COLOR,
    FIT_PALETTE,
    REPLICA_PALETTE,
    rgba,
)


def test_palette_rgb_bounds():
    for palette in (REPLICA_PALETTE, FIT_PALETTE):
        for color in palette:
            assert len(color) == 3
            for channel in color:
                assert 0 <= channel <= 255, f"channel out of range: {channel}"


def test_scalar_colors_rgb_bounds():
    for color in (DROPPED_REPLICA_COLOR, AVERAGE_LINE_COLOR, ERROR_BAR_COLOR):
        assert len(color) == 3
        for channel in color:
            assert 0 <= channel <= 255


def test_rgba_default_alpha():
    rgb = (31, 119, 180)
    result = rgba(rgb)
    assert result == (31, 119, 180, 255)


def test_rgba_custom_alpha():
    rgb = (255, 0, 0)
    result = rgba(rgb, alpha=128)
    assert result == (255, 0, 0, 128)


def test_rgba_zero_alpha():
    rgb = (0, 255, 0)
    result = rgba(rgb, alpha=0)
    assert result == (0, 255, 0, 0)


