"""Format registry for I/O dispatch.

Each extension can have one or more registered readers. When dispatching a
file path, ``get_reader`` walks the candidates in registration order and
returns the first one whose ``can_read(path)`` classmethod returns True.
Readers without a ``can_read`` method are treated as always-accepting and
serve as fallbacks (e.g., the generic ``CsvReader`` after JASCO/EnSight
sniffers for ``.csv``).

Register format-specific sniffers *before* generic fallbacks at import time.
"""

from pathlib import Path
from typing import Dict, List, Type

from core.io.base import MeasurementReader, ResultWriter

# Extension → ordered list of candidate readers; first matching sniffer wins.
READERS: Dict[str, List[Type[MeasurementReader]]] = {}
WRITERS: Dict[str, Type[ResultWriter]] = {}


def register_reader(reader_cls: Type[MeasurementReader]) -> Type[MeasurementReader]:
    """Register a reader class for its supported extensions.

    Multiple readers may share an extension; dispatch is content-sniffed via
    each reader's ``can_read`` classmethod at lookup time. Registration order
    is preserved — register specific sniffers before generic fallbacks.
    """
    for ext in reader_cls.extensions:
        candidates = READERS.setdefault(ext.lower(), [])
        if reader_cls not in candidates:
            candidates.append(reader_cls)
    return reader_cls


def register_writer(writer_cls: Type[ResultWriter]) -> Type[ResultWriter]:
    """Register a writer class for its supported extensions."""
    for ext in writer_cls.extensions:
        WRITERS[ext.lower()] = writer_cls
    return writer_cls


def get_reader(path: Path) -> MeasurementReader:
    """Get a reader instance for the given file path.

    Walks the registered candidates for the file's extension and returns
    the first one whose ``can_read(path)`` returns True. Readers without
    ``can_read`` are treated as always-accepting (fallback behaviour).

    Raises
    ------
    ValueError
        If no reader is registered for the extension, or every candidate's
        sniffer rejected the file.
    """
    ext = path.suffix.lower()
    candidates = READERS.get(ext)
    if not candidates:
        raise ValueError(f"No reader for '{ext}'. Supported: {sorted(READERS)}")

    for cls in candidates:
        sniffer = getattr(cls, 'can_read', None)
        if sniffer is None or sniffer(path):
            return cls()

    names = [cls.__name__ for cls in candidates]
    raise ValueError(f"No registered reader accepted '{path.name}'. Tried (in order): {names}.")


def get_writer(path: Path) -> ResultWriter:
    """Get a writer instance for the given file path."""
    ext = path.suffix.lower()
    if ext not in WRITERS:
        raise ValueError(f"No writer for '{ext}'. Supported: {sorted(WRITERS)}")
    return WRITERS[ext]()


__all__ = ['register_reader', 'register_writer', 'get_reader', 'get_writer']
