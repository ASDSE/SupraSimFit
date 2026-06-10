# Axis Exponent Formatting

> 14 nodes · cohesion 0.15

## Key Concepts

- **_format_exponent_unicode()** (8 connections) — `gui/plotting/plot_widget.py`
- **._on_x_exponent_changed()** (5 connections) — `gui/plotting/plot_widget.py`
- **._on_y_exponent_changed()** (5 connections) — `gui/plotting/plot_widget.py`
- **._set_axis_label()** (5 connections) — `gui/plotting/plot_widget.py`
- **_refresh_axis_label_with_exponent()** (4 connections) — `gui/plotting/distribution_widget.py`
- **._compose_axis_label()** (4 connections) — `gui/plotting/plot_widget.py`
- **test_format_exponent_unicode_negative()** (2 connections) — `tests/unit/gui/test_plot_widget.py`
- **test_format_exponent_unicode_positive()** (2 connections) — `tests/unit/gui/test_plot_widget.py`
- **Re-apply the y-axis label, appending ×10ⁿ when an exponent is set.      The base** (1 connections) — `gui/plotting/distribution_widget.py`
- **Convert an integer exponent to Unicode superscript, e.g. 5 → '⁵', -3 → '⁻³'.** (1 connections) — `gui/plotting/plot_widget.py`
- **Set an axis label, appending ×10ⁿ if *exp* is not None.** (1 connections) — `gui/plotting/plot_widget.py`
- **Compose ``"<name> [<unit>]"`` using *override* if non-empty.          The over** (1 connections) — `gui/plotting/plot_widget.py`
- **Update y-axis label reactively when the exponent changes during paint.** (1 connections) — `gui/plotting/plot_widget.py`
- **Update x-axis label reactively when the exponent changes during paint.** (1 connections) — `gui/plotting/plot_widget.py`

## Relationships

- [[Plot Style Tests]] (7 shared connections)
- [[Label Formatting]] (3 shared connections)
- [[Plot Colors & Palette]] (2 shared connections)
- [[Distribution Plot Widget]] (1 shared connections)

## Source Files

- `gui/plotting/distribution_widget.py`
- `gui/plotting/plot_widget.py`
- `tests/unit/gui/test_plot_widget.py`

## Audit Trail

- EXTRACTED: 41 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*