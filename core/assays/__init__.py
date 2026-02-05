"""Assay definitions and registry for molecular binding assays."""

from core.assays.base import BaseAssay
from core.assays.dba import DBAAssay, create_dba_dye_to_host, create_dba_host_to_dye
from core.assays.dye_alone import DyeAloneAssay
from core.assays.gda import GDAAssay
from core.assays.ida import IDAAssay
from core.assays.registry import ASSAY_REGISTRY, AssayMetadata, AssayType, get_metadata, list_assay_types

__all__ = [
    # Registry
    'AssayType',
    'AssayMetadata',
    'ASSAY_REGISTRY',
    'get_metadata',
    'list_assay_types',
    # Base class
    'BaseAssay',
    # Concrete assays
    'GDAAssay',
    'IDAAssay',
    'DBAAssay',
    'DyeAloneAssay',
    # Factory functions
    'create_dba_host_to_dye',
    'create_dba_dye_to_host',
]
