"""Example input-data template generator.

Emits a small measurement file that demonstrates the exact format the
app's readers accept, so a user can fill in their own numbers by example.
The output round-trips cleanly through :func:`core.io.load_measurements`.

Format is chosen by file extension:

* ``.csv`` → long-format ``concentration,signal,replica`` (read by
  :class:`~core.io.formats.csv_reader.CsvReader`).
* anything else (``.txt``) → tab-separated repeated-header blocks, one
  ``var<TAB>signal`` header per replica (read by
  :class:`~core.io.formats.txt.TxtReader`).

The example is **assay-agnostic**: it shows the (concentration → signal)
layout shared by every assay, not any particular binding model. Signal
values are obviously-synthetic placeholders, not real measurements.

The reader-accepted column names are duplicated here rather than imported,
but :func:`tests.unit.test_io_template` round-trips the output through the
real readers, so any drift from the readers' contract fails the suite.
"""

from __future__ import annotations

from pathlib import Path

# A few titration points (Molar) shared by every replica, plus three
# replicas of plausible rising signal with small per-replica variation.
# Hard-coded — no RNG — so the emitted template is reproducible.
_CONCENTRATIONS_M: tuple[float, ...] = (0.0, 1e-6, 2e-6, 5e-6, 1e-5, 2e-5)
_REPLICA_SIGNALS: tuple[tuple[float, ...], ...] = (
    (100.0, 255.0, 402.0, 651.0, 848.0, 1001.0),
    (102.0, 249.0, 398.0, 640.0, 855.0, 996.0),
    (98.0, 252.0, 405.0, 648.0, 851.0, 1004.0),
)

_TXT_HEADER = (
    '# SupraSimFit input-data template — replace the example rows below with your own data.\n'
    '#\n'
    "# Tab-separated. Each replica is a 'var<TAB>signal' header followed by\n"
    '# concentration<TAB>signal rows. Concentrations are in Molar (M).\n'
    "# Lines starting with '#' are ignored. Add or remove replica blocks as needed."
)


def _txt_template() -> str:
    """Build a tab-separated, repeated-header TXT template (``TxtReader``)."""
    lines = [_TXT_HEADER]
    for signals in _REPLICA_SIGNALS:
        lines.append('var\tsignal')
        lines.extend(f'{conc:g}\t{sig:g}' for conc, sig in zip(_CONCENTRATIONS_M, signals))
    return '\n'.join(lines) + '\n'


def _csv_template() -> str:
    """Build a long-format ``concentration,signal,replica`` CSV (``CsvReader``).

    No ``#`` comments: ``CsvReader`` parses with ``pandas.read_csv`` and no
    comment character, so comment lines would be mis-read as data.
    """
    lines = ['concentration,signal,replica']
    for replica, signals in enumerate(_REPLICA_SIGNALS):
        lines.extend(f'{conc:g},{sig:g},{replica}' for conc, sig in zip(_CONCENTRATIONS_M, signals))
    return '\n'.join(lines) + '\n'


def write_data_template(path: str | Path) -> Path:
    """Write an example input file demonstrating the reader-accepted format.

    Parameters
    ----------
    path : str or Path
        Destination. A ``.csv`` suffix emits long-format CSV; any other
        suffix emits tab-separated TXT.

    Returns
    -------
    Path
        The path that was written.
    """
    path = Path(path)
    content = _csv_template() if path.suffix.lower() == '.csv' else _txt_template()
    path.write_text(content)
    return path
