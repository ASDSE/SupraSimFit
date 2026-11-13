"""Stating a session's binding model in a test, as a user does in Binding model."""

from __future__ import annotations

from core.units import Quantity


def _magnitude(value, unit: str) -> float:
    return float(value.to(unit).magnitude) if isinstance(value, Quantity) else float(value)


def state_binding(session, *, assay_type=None, conditions=None, bounds=None, per_replica=None) -> None:
    """Choose *assay_type*, enter *conditions* and *bounds*, and set the replicate mode, in one finished edit.

    Conditions and bounds are Quantities, or floats in the condition's base unit and the
    parameter's unit.
    """
    form = session.model.binding
    if assay_type is not None:
        form.set_assay(assay_type)
    for key, value in (conditions or {}).items():
        form.set_value(key, _magnitude(value, form.entry(key).field.unit))
    for key, (lo, hi) in (bounds or {}).items():
        unit = form.bound_entries[key].unit
        form.set_bounds(key, _magnitude(lo, unit), _magnitude(hi, unit))
    if per_replica is not None:
        form.set_per_replica(per_replica)
    session.model.binding_edited()


def state_dilution(session, stock: float | None, contains: tuple[str, ...] = ()) -> None:
    """Say that the additions dilute the sample, from a stock of *stock* M holding *contains*; ``None`` says they do not."""
    form = session.model.binding
    if stock is not None:
        form.set_value('titrant_stock', stock)
    form.contains = set(contains)
    form.set_diluted(stock is not None)
    session.model.binding_edited()
