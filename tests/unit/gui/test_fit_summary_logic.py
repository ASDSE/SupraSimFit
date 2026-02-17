"""Tests for FitSummaryWidget helpers — no QApplication required."""

import math

import pytest

from core.assays.registry import AssayType
from gui.plotting.fit_summary_widget import _fmt_value, _lookup_assay_type


# ------------------------------------------------------------------
# _lookup_assay_type
# ------------------------------------------------------------------

@pytest.mark.parametrize("assay_type", list(AssayType))
def test_lookup_all_assay_types(assay_type):
    result = _lookup_assay_type(assay_type.name)
    assert result is assay_type


def test_lookup_unknown_returns_none():
    assert _lookup_assay_type("NONEXISTENT") is None


def test_lookup_empty_string():
    assert _lookup_assay_type("") is None


# ------------------------------------------------------------------
# _fmt_value
# ------------------------------------------------------------------

def test_fmt_nan():
    assert _fmt_value(float("nan")) == "NaN"


def test_fmt_inf():
    assert _fmt_value(float("inf")) == "Inf"


def test_fmt_neg_inf():
    assert _fmt_value(float("-inf")) == "-Inf"


def test_fmt_zero():
    assert _fmt_value(0.0) == "0.0"


def test_fmt_large_value_scientific():
    result = _fmt_value(1e6)
    assert "e" in result.lower()


def test_fmt_small_value_scientific():
    result = _fmt_value(1e-5)
    assert "e" in result.lower()


def test_fmt_normal_range():
    result = _fmt_value(3.14159)
    assert "e" not in result.lower()
    assert "3.14" in result


def test_fmt_boundary_1e5_uses_scientific():
    result = _fmt_value(1e5)
    assert "e" in result.lower()


def test_fmt_boundary_1e_minus_3_normal():
    # 1e-3 is not < 1e-3, so should use normal notation
    result = _fmt_value(1e-3)
    assert "e" not in result.lower()


def test_fmt_negative_large():
    result = _fmt_value(-1e8)
    assert "e" in result.lower()
    assert result.startswith("-")
