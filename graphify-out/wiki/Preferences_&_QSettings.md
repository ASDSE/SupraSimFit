# Preferences & QSettings

> 19 nodes · cohesion 0.16

## Key Concepts

- **_settings()** (13 connections) — `gui/preferences.py`
- **preferences.py** (7 connections) — `gui/preferences.py`
- **get_bool()** (7 connections) — `gui/preferences.py`
- **test_preferences.py** (7 connections) — `tests/unit/gui/test_preferences.py`
- **set_bool()** (5 connections) — `gui/preferences.py`
- **._distributions_export_config()** (4 connections) — `gui/fitting_session.py`
- **test_string_backed_values_are_coerced()** (4 connections) — `tests/unit/gui/test_preferences.py`
- **_isolated_settings()** (3 connections) — `tests/unit/gui/test_preferences.py`
- **test_set_and_get_bool_round_trip()** (3 connections) — `tests/unit/gui/test_preferences.py`
- **QSettings** (3 connections) — `gui/preferences.py`
- **test_get_bool_returns_default_when_unset()** (2 connections) — `tests/unit/gui/test_preferences.py`
- **Build a DistributionsExportConfig from persisted QSettings.          Used by the** (1 connections) — `gui/fitting_session.py`
- **Thin wrapper around :class:`QSettings` for persistent user preferences.  The cod** (1 connections) — `gui/preferences.py`
- **Return a QSettings bound to the currently running application.      Uses ``QSett** (1 connections) — `gui/preferences.py`
- **Return a boolean preference, falling back to *default*.** (1 connections) — `gui/preferences.py`
- **Persist a boolean preference.** (1 connections) — `gui/preferences.py`
- **Tests for :mod:`gui.preferences` round-trip and default behaviour.  These tests** (1 connections) — `tests/unit/gui/test_preferences.py`
- **Point QSettings at a throwaway application name for every test.** (1 connections) — `tests/unit/gui/test_preferences.py`
- **Some platforms store booleans as strings; the wrapper must coerce.** (1 connections) — `tests/unit/gui/test_preferences.py`

## Relationships

- [[Distributions Export Config]] (3 shared connections)
- [[Batch Artefact Export]] (2 shared connections)
- [[Export Multiple Dialog]] (2 shared connections)
- [[Save Distributions Dialog]] (2 shared connections)
- [[FittingSession Export]] (1 shared connections)
- [[App Launch & Main Window]] (1 shared connections)
- [[Style Template Persistence]] (1 shared connections)

## Source Files

- `gui/fitting_session.py`
- `gui/preferences.py`
- `tests/unit/gui/test_preferences.py`

## Audit Trail

- EXTRACTED: 62 (94%)
- INFERRED: 4 (6%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*