"""Assay definitions and registry for molecular binding assays."""

from core.assays.base import BaseAssay
from core.assays.dba import DBAAssay, create_dba_dye_to_host, create_dba_host_to_dye
from core.assays.dye_alone import DyeAloneAssay
from core.assays.gda import GDAAssay
from core.assays.h2g import H2GAssay
from core.assays.hg2 import HG2Assay
from core.assays.ida import IDAAssay
from core.assays.registry import ASSAY_REGISTRY, AssayMetadata, AssayType, get_metadata, list_assay_types

#: The class that builds each assay type. Both DBA directions share one class;
#: the ``mode`` condition selects the direction.
ASSAY_CLASSES: dict[AssayType, type[BaseAssay]] = {
    AssayType.GDA: GDAAssay,
    AssayType.IDA: IDAAssay,
    AssayType.DBA_HtoD: DBAAssay,
    AssayType.DBA_DtoH: DBAAssay,
    AssayType.DYE_ALONE: DyeAloneAssay,
    AssayType.DBA_HG2: HG2Assay,
    AssayType.DBA_H2G: H2GAssay,
}

__all__ = [
    # Registry
    'AssayType',
    'AssayMetadata',
    'ASSAY_REGISTRY',
    'ASSAY_CLASSES',
    'get_metadata',
    'list_assay_types',
    # Base class
    'BaseAssay',
    # Concrete assays
    'GDAAssay',
    'IDAAssay',
    'DBAAssay',
    'DyeAloneAssay',
    'HG2Assay',
    'H2GAssay',
    # Factory functions
    'create_dba_host_to_dye',
    'create_dba_dye_to_host',
]
