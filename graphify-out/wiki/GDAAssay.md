# GDAAssay

> God node · 66 connections · `core/assays/gda.py`

**Community:** [[GDA Assay]]

## Connections by Relation

### calls
- [[_gda_assay()]] `EXTRACTED`
- [[_gda_assay()]] `EXTRACTED`
- [[.test_parameter_keys_from_registry()]] `EXTRACTED`
- [[.test_params_to_dict()]] `EXTRACTED`
- [[.test_mismatched_data_shapes_raises()]] `EXTRACTED`
- [[.test_missing_g0_raises()]] `EXTRACTED`
- [[.test_missing_h0_raises()]] `EXTRACTED`
- [[.test_missing_ka_dye_raises()]] `EXTRACTED`
- [[.test_negative_g0_raises()]] `EXTRACTED`
- [[.test_negative_ka_dye_raises()]] `EXTRACTED`
- [[.test_zero_h0_raises()]] `EXTRACTED`
- [[.test_bare_float_conditions_rejected()]] `EXTRACTED`
- [[.test_quantity_conditions_accepted()]] `EXTRACTED`
- [[.test_wrong_dimensionality_h0_raises()]] `EXTRACTED`
- [[.test_wrong_dimensionality_Ka_raises()]] `EXTRACTED`

### contains
- [[gda.py]] `EXTRACTED`

### implements
- [[Pint Quantity dimensional validation at assay boundary]] `INFERRED`
- [[Fail-fast contract (reject invalid input immediately)]] `INFERRED`

### imports
- [[test_pipeline_e2e.py]] `EXTRACTED`
- [[__init__.py]] `EXTRACTED`
- [[test_measurement_set.py]] `EXTRACTED`
- [[plotting_demo.py]] `EXTRACTED`
- [[test_fail_fast.py]] `EXTRACTED`
- [[assay_conditions.py]] `EXTRACTED`
- [[test_assay_quantity.py]] `EXTRACTED`
- [[test_pipeline_helpers.py]] `EXTRACTED`

### inherits
- [[BaseAssay]] `EXTRACTED`

### method
- [[.forward_model()]] `EXTRACTED`
- [[.get_conditions()]] `EXTRACTED`
- [[.__post_init__()]] `EXTRACTED`

### rationale_for
- [[Guest Displacement Assay data container.      Attributes     ----------     x_da]] `EXTRACTED`

### references
- [[MeasurementSet]] `INFERRED`
- [[_resolve_bounds]] `INFERRED`

### uses
- [[AssayType]] `INFERRED`
- [[BaseAssay]] `INFERRED`
- [[TestGDAFailFast]] `INFERRED`
- [[TestChainedWorkflow]] `INFERRED`
- [[TestFailureModes]] `INFERRED`
- [[TestSetConcentrations]] `INFERRED`
- [[TestIDAFailFast]] `INFERRED`
- [[TestConstruction]] `INFERRED`
- [[TestBoundsMarginEdgeCases]] `INFERRED`
- [[TestDBAEndToEnd]] `INFERRED`
- [[TestDyeAloneEndToEnd]] `INFERRED`
- [[TestFitMeasurementSet]] `INFERRED`
- [[TestIDAEndToEnd]] `INFERRED`
- [[TestGDAQuantityConditions]] `INFERRED`
- [[TestBaseAssayContracts]] `INFERRED`
- [[TestDBAFailFast]] `INFERRED`
- [[TestDataAccess]] `INFERRED`
- [[TestDBAHtoD]] `INFERRED`
- [[TestDyeAloneNoisy]] `INFERRED`
- [[TestFitConfigCustomization]] `INFERRED`

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*