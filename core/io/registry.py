"""Format registry for I/O dispatch.

Simple dict-based registry — no decorators, no magic.
Readers and writers register themselves on module import.
"""

from pathlib import Path
from typing import Dict, Type

from core.io.base import MeasurementReader, ResultWriter

# Explicit registries — format implementations register on import
READERS: Dict[str, Type[MeasurementReader]] = {}
WRITERS: Dict[str, Type[ResultWriter]] = {}


def register_reader(reader_cls: Type[MeasurementReader]) -> Type[MeasurementReader]:
    """Register a reader class for its supported extensions.

    Parameters
    ----------
    reader_cls : Type[MeasurementReader]
        Reader class with `extensions` attribute.

    Returns
    -------
    Type[MeasurementReader]
        The same class (allows use as decorator).
    """
    for ext in reader_cls.extensions:
        READERS[ext.lower()] = reader_cls
    return reader_cls


def register_writer(writer_cls: Type[ResultWriter]) -> Type[ResultWriter]:
    """Register a writer class for its supported extensions.

    Parameters
    ----------
    writer_cls : Type[ResultWriter]
        Writer class with `extensions` attribute.

    Returns
    -------
    Type[ResultWriter]
        The same class (allows use as decorator).
    """
    for ext in writer_cls.extensions:
        WRITERS[ext.lower()] = writer_cls
    return writer_cls


def get_reader(path: Path) -> MeasurementReader:
    """Get a reader instance for the given file path.

    Parameters
    ----------
    path : Path
        File path to read.

    Returns
    -------
    MeasurementReader
        Reader instance for the file's extension.

    Raises
    ------
    ValueError
        If no reader is registered for the file extension.
    """
    ext = path.suffix.lower()
    if ext not in READERS:
        supported = list(READERS.keys())
        raise ValueError(f"No reader for '{ext}'. Supported: {supported}")
    return READERS[ext]()


def get_writer(path: Path) -> ResultWriter:
    """Get a writer instance for the given file path.

    Parameters
    ----------
    path : Path
        File path to write.

    Returns
    -------
    ResultWriter
        Writer instance for the file's extension.

    Raises
    ------
    ValueError
        If no writer is registered for the file extension.
    """
    ext = path.suffix.lower()
    if ext not in WRITERS:
        supported = list(WRITERS.keys())
        raise ValueError(f"No writer for '{ext}'. Supported: {supported}")
    return WRITERS[ext]()


__all__ = ['register_reader', 'register_writer', 'get_reader', 'get_writer']
