"""Category / subtype metadata that drives the two-level assay menu.

Guards the GUI contract: every registered assay is menu-reachable with a
non-empty category and a subtype label that is unambiguous within its category.
A new assay added without these would silently break the selector.
"""

from collections import Counter

from core.assays.registry import ASSAY_REGISTRY


def test_every_assay_has_category_and_subtype_label():
    for assay_type, meta in ASSAY_REGISTRY.items():
        assert meta.category, f'{assay_type.name} has no category'
        assert meta.subtype_label, f'{assay_type.name} has no subtype_label'


def test_subtype_labels_unique_within_category():
    # Two assays in one category must not share a subtype label, or the sub
    # dropdown would show indistinguishable entries.
    by_category: dict[str, list[str]] = {}
    for meta in ASSAY_REGISTRY.values():
        by_category.setdefault(meta.category, []).append(meta.subtype_label)
    for category, labels in by_category.items():
        dupes = [lbl for lbl, n in Counter(labels).items() if n > 1]
        assert not dupes, f'duplicate subtype labels in {category!r}: {dupes}'
