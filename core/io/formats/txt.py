"""TXT format reader and writer for tab-separated measurement data.

File Format
-----------
Tab-separated values with header row. Multiple replicas are separated
by repeated headers:

    var\tsignal
    0.0\t506.246
    2.985e-05\t1064.85
    ...
    var\tsignal
    0.0\t103.734
    2.985e-05\t1145.26
    ...

The reader detects repeated headers and assigns replica indices.
"""

from datetime import datetime
from pathlib import Path

import pandas as pd

from core.io.registry import register_reader, register_writer


class TxtReader:
    """Reader for tab-separated measurement files with multi-replica support."""

    extensions = ('.txt',)

    def read(self, path: Path) -> pd.DataFrame:
        """Read tab-separated measurement file.

        Handles multi-replica files where each replica block starts with
        a header row (e.g., 'var\\tsignal').

        Parameters
        ----------
        path : Path
            Path to input file.

        Returns
        -------
        pd.DataFrame
            Long-format DataFrame with columns:
            - concentration: titrant concentration (M)
            - signal: measured signal value
            - replica: replica index (0, 1, 2, ...)
        """
        with open(path, 'r') as f:
            lines = f.readlines()

        # Parse into replica blocks
        replicas = []
        current_block = []
        header_seen = False

        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            # Detect header row (contains 'var' or non-numeric first field)
            parts = line.split('\t')
            is_header = self._is_header(parts)

            if is_header:
                # Save previous block if exists
                if current_block and header_seen:
                    replicas.append(current_block)
                current_block = []
                header_seen = True
            elif header_seen:
                # Data row
                current_block.append(parts)

        # Don't forget last block
        if current_block:
            replicas.append(current_block)

        # Convert to DataFrame
        dfs = []
        for i, block in enumerate(replicas):
            df = pd.DataFrame(block, columns=['concentration', 'signal'])
            df['concentration'] = pd.to_numeric(df['concentration'], errors='coerce')
            df['signal'] = pd.to_numeric(df['signal'], errors='coerce')
            df['replica'] = i
            dfs.append(df)

        if not dfs:
            raise ValueError(f'No data found in {path}')

        result = pd.concat(dfs, ignore_index=True)
        return result.dropna()

    def _is_header(self, parts: list[str]) -> bool:
        """Check if a row is a header row."""
        if len(parts) < 2:
            return False
        # Header if first field is non-numeric or contains common header names
        first = parts[0].lower()
        if first in ('var', 'concentration', 'conc', 'x'):
            return True
        try:
            float(parts[0])
            return False  # Numeric = data row
        except ValueError:
            return True  # Non-numeric = header row


class TxtWriter:
    """Writer for tab-separated fit results."""

    extensions = ('.txt',)

    def write(self, results: dict, path: Path) -> None:
        """Write fit results as tab-separated text.

        Parameters
        ----------
        results : dict
            Fit results dictionary with keys like 'Ka_dye', 'I0', etc.
        path : Path
            Output file path.
        """
        lines = [
            '# Fit Results',
            f'# Generated: {datetime.now().isoformat()}',
            '#',
            'parameter\tvalue\tuncertainty',
        ]

        for key, value in results.items():
            if key.endswith('_uncertainty'):
                continue  # Skip uncertainty keys, they're paired
            uncertainty = results.get(f'{key}_uncertainty', '')
            if isinstance(value, float):
                lines.append(f'{key}\t{value:.6e}\t{uncertainty}')
            else:
                lines.append(f'{key}\t{value}\t{uncertainty}')

        path.write_text('\n'.join(lines))


# Register on import
register_reader(TxtReader)
register_writer(TxtWriter)
