# MeasurementSet DataFrame

> 20 nodes · cohesion 0.11

## Key Concepts

- **.to_assay()** (7 connections) — `core/data_processing/measurement_set.py`
- **.get_replica_signal()** (5 connections) — `core/data_processing/measurement_set.py`
- **._replica_index()** (5 connections) — `core/data_processing/measurement_set.py`
- **ndarray** (4 connections) — `core/data_processing/measurement_set.py`
- **.average_signal()** (4 connections) — `core/data_processing/measurement_set.py`
- **.from_dataframe()** (4 connections) — `core/data_processing/measurement_set.py`
- **.is_active()** (4 connections) — `core/data_processing/measurement_set.py`
- **Any** (3 connections) — `core/data_processing/measurement_set.py`
- **.iter_replicas()** (3 connections) — `core/data_processing/measurement_set.py`
- **.set_active()** (3 connections) — `core/data_processing/measurement_set.py`
- **BaseAssay** (2 connections) — `core/data_processing/measurement_set.py`
- **DataFrame** (2 connections) — `core/data_processing/measurement_set.py`
- **Build a MeasurementSet from a long-form DataFrame.          The DataFrame must c** (1 connections) — `core/data_processing/measurement_set.py`
- **Return the row index for *replica_id*, or raise ValueError.** (1 connections) — `core/data_processing/measurement_set.py`
- **Set the active state of a single replica.          Parameters         ----------** (1 connections) — `core/data_processing/measurement_set.py`
- **Check whether *replica_id* is currently active.** (1 connections) — `core/data_processing/measurement_set.py`
- **Iterate over replicas as ``(replica_id, signal_view)`` pairs.          Parameter** (1 connections) — `core/data_processing/measurement_set.py`
- **Return the signal array (read-only view) for a single replica.          Paramete** (1 connections) — `core/data_processing/measurement_set.py`
- **Compute the mean signal across replicas.          Parameters         ----------** (1 connections) — `core/data_processing/measurement_set.py`
- **Construct a :class:`BaseAssay` from this measurement set.          Parameters** (1 connections) — `core/data_processing/measurement_set.py`

## Relationships

- [[MeasurementSet & FitResult]] (8 shared connections)
- [[BaseAssay Interface]] (4 shared connections)

## Source Files

- `core/data_processing/measurement_set.py`

## Audit Trail

- EXTRACTED: 50 (93%)
- INFERRED: 4 (7%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*