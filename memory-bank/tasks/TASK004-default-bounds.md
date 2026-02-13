# TASK004 - Define default bounds for 4th signal parameter

**Status:** Pending  
**Added:** 2026-01-31  
**Updated:** 2026-02-13

## Original Request
After restoring 4-parameter fitting (TASK003 remediation), define reasonable default bounds for the additional signal coefficient (`I_dye_free` or `I_dye_bound`) in the ASSAY_REGISTRY.

## Context
- Legacy code fits 4 parameters: `[I0, Ka, Id, Ihd]` (now `[I0, Ka_*, I_dye_free, I_dye_bound]`)
- Current registry has bounds `I_dye_free: (0, 1e6)` and `I_dye_bound: (0, 1e6)` — too narrow for realistic per-Molar coefficients (~5e7, ~3e8)
- **Key insight from degeneracy analysis (2026-02-09)**: Signal coefficients are structurally non-identifiable in DBA/IDA. Wide bounds allow the degenerate manifold to produce arbitrarily wrong individual values while fitting perfectly. Tight bounds (±20% of expected values) constrain the manifold and improve Ka recovery.
- **Named bounds API available (2026-02-13)**: `FitConfig.custom_bounds` now accepts `Dict[str, Tuple]` with partial overrides. `bounds_from_dye_alone()` can derive `I_dye_free`/`I0` bounds from calibration. The infrastructure for users to tighten bounds is in place; this task is about setting sensible *defaults* in the registry.

## Blocked By
- TASK003 subtasks 3.17–3.23 (scientific remediation)

## Implementation Plan
1. Review legacy fitting code for existing bounds on Id/Ihd
2. Consult scientific literature for typical signal coefficient ranges
3. Update `default_bounds` in `core/assays/registry.py` for all assay types
4. Test with real data to validate bounds are reasonable

## Progress Tracking

**Overall Status:** Not Started - 0%

### Subtasks
| ID | Description | Status | Updated | Notes |
|----|-------------|--------|---------|-------|
| 4.1 | Review legacy bounds for Id/Ihd | Not Started | 2026-01-31 | Legacy `core/fitting/` deleted; review `core/assays/registry.py` instead |
| 4.2 | Update GDA default_bounds | Not Started | 2026-01-31 | Add I_dye_free, I_dye_bound |
| 4.3 | Update IDA default_bounds | Not Started | 2026-01-31 | Add I_dye_free, I_dye_bound |
| 4.4 | Update DBA default_bounds | Not Started | 2026-01-31 | Add I_dye_free, I_dye_bound |
| 4.5 | Validate with real data | Not Started | 2026-01-31 | End-to-end test |

## Progress Log
### 2026-01-31
- Task created as follow-up to TASK003 scientific remediation.
- Deferred to after 4-parameter fitting is restored.
