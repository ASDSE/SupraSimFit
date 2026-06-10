# DBA Datasets & Txt Reader

> 15 nodes · cohesion 0.15

## Key Concepts

- **txt.py** (10 connections) — `core/io/formats/txt.py`
- **.read()** (5 connections) — `core/io/formats/txt.py`
- **DBA HtoD Tryptamine 424 dataset** (4 connections) — `data/DBA_HtoD_tryptamine_424.txt`
- **DBA System Host-to-Dye dataset** (4 connections) — `data/DBA_system_host_to_dye.txt`
- **._is_header()** (3 connections) — `core/io/formats/txt.py`
- **TxtWriter** (3 connections) — `core/io/formats/txt.py`
- **.write()** (3 connections) — `core/io/formats/txt.py`
- **Direct Binding Assay (Ka_dye)** (2 connections) — `core/assays/dba.py`
- **Path** (2 connections) — `core/io/formats/txt.py`
- **DataFrame** (1 connections) — `core/io/formats/txt.py`
- **TXT format reader and writer for tab-separated measurement data.  File Format --** (1 connections) — `core/io/formats/txt.py`
- **Writer for tab-separated fit results.** (1 connections) — `core/io/formats/txt.py`
- **Write fit results as tab-separated text.          Parameters         ----------** (1 connections) — `core/io/formats/txt.py`
- **Read tab-separated measurement file.          Handles multi-replica files where** (1 connections) — `core/io/formats/txt.py`
- **Check if a row is a header row.** (1 connections) — `core/io/formats/txt.py`

## Relationships

- [[Txt Reader Round-trip]] (3 shared connections)
- [[Assay Base & Registry Metadata]] (2 shared connections)
- [[Core Domain Init]] (1 shared connections)
- [[Measurement Writer]] (1 shared connections)
- [[Reader Registry Dispatch]] (1 shared connections)
- [[MeasurementReader Base]] (1 shared connections)
- [[BMG Workbook Parsing]] (1 shared connections)

## Source Files

- `core/assays/dba.py`
- `core/io/formats/txt.py`
- `data/DBA_HtoD_tryptamine_424.txt`
- `data/DBA_system_host_to_dye.txt`

## Audit Trail

- EXTRACTED: 29 (69%)
- INFERRED: 13 (31%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*