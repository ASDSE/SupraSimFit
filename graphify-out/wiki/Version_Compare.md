# Version Compare

> 11 nodes · cohesion 0.24

## Key Concepts

- **is_newer()** (8 connections) — `gui/update_check.py`
- **TestIsNewer** (6 connections) — `tests/unit/test_update_check.py`
- **test_update_check.py** (4 connections) — `tests/unit/test_update_check.py`
- **.test_unparseable_remote_returns_false()** (3 connections) — `tests/unit/test_update_check.py`
- **.test_equal_versions()** (2 connections) — `tests/unit/test_update_check.py`
- **.test_strictly_newer_minor()** (2 connections) — `tests/unit/test_update_check.py`
- **is_newer** (2 connections) — `gui/update_check.py`
- **Return True if *remote_tag* represents a strictly newer version than *local*.** (1 connections) — `gui/update_check.py`
- **Tests for :func:`gui.update_check.is_newer`.  Pure-function tests — no GitHub ne** (1 connections) — `tests/unit/test_update_check.py`
- **Behaviour of ``is_newer(remote_tag, local)``.** (1 connections) — `tests/unit/test_update_check.py`
- **Malformed remote tags must not raise — treat as 'not newer'.** (1 connections) — `tests/unit/test_update_check.py`

## Relationships

- [[App Launch & Main Window]] (3 shared connections)
- [[Update Check Flow]] (1 shared connections)
- [[Toolbar & Update Worker]] (1 shared connections)

## Source Files

- `gui/update_check.py`
- `tests/unit/test_update_check.py`

## Audit Trail

- EXTRACTED: 30 (97%)
- INFERRED: 1 (3%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*