"""Two-level (category → subtype) assay selector behaviour.

Verifies the dependent dropdowns react correctly and that exactly one
``assay_type_changed`` is emitted per selection — the contract the fitting
session and demo loader rely on.
"""

import pytest

from core.assays import AssayType
from core.assays.registry import ASSAY_REGISTRY
from gui.widgets.assay_config_panel import AssayConfigPanel


@pytest.fixture
def panel(qapp):
    return AssayConfigPanel()


def _direct_binding_types():
    return [at for at, m in ASSAY_REGISTRY.items() if m.category == 'Direct Binding']


def test_default_is_gda_without_emission(qapp):
    emitted = []
    p = AssayConfigPanel()
    p.assay_type_changed.connect(emitted.append)
    # Construction must not fire the signal (matches prior single-combo init).
    assert p.current_assay_type() is AssayType.GDA
    assert emitted == []


def test_set_assay_type_selects_category_and_subtype_once(panel):
    emitted = []
    panel.assay_type_changed.connect(emitted.append)

    panel.set_assay_type(AssayType.IDA)

    assert panel.current_assay_type() is AssayType.IDA
    assert panel._main_combo.currentData() == 'Competitive Displacement'
    assert panel._sub_combo.currentData() is AssayType.IDA
    assert emitted == [AssayType.IDA]  # exactly one emission


def test_changing_category_repopulates_subtypes_and_emits_once(panel):
    emitted = []
    panel.assay_type_changed.connect(emitted.append)

    panel._main_combo.setCurrentIndex(panel._main_combo.findData('Direct Binding'))

    direct = _direct_binding_types()
    sub_data = [panel._sub_combo.itemData(i) for i in range(panel._sub_combo.count())]
    assert sub_data == direct  # subtype combo now lists exactly the category's assays
    assert panel.current_assay_type() is direct[0]  # first subtype applied
    assert emitted == [direct[0]]  # one emission for the category switch, not two


def test_changing_subtype_within_category_emits_that_assay(panel):
    panel.set_assay_type(AssayType.DBA_HtoD)  # Direct Binding
    emitted = []
    panel.assay_type_changed.connect(emitted.append)

    panel._sub_combo.setCurrentIndex(panel._sub_combo.findData(AssayType.DBA_H2G))

    assert panel.current_assay_type() is AssayType.DBA_H2G
    assert emitted == [AssayType.DBA_H2G]
