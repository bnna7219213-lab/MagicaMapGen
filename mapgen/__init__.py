"""mapgen -- schema-driven prototype map generator.

Three-tier model:

    Theme (deterministic contract)  ->  Category (one-to-many)
        ->  Distribution (replaceable)  ->  params

See ``mapgen/schema.py`` for the dataclasses and ``mapgen/contract.py`` for the
guarantees a theme must honour.
"""

from __future__ import annotations

__version__ = "1.0.0"
GENERATOR_VERSION = __version__

from .config import ConfigError, load_config, request_from_dict, request_to_dict
from .pipeline import generate
from .schema import (
    SCHEMA_VERSION, BiomeBand, BiomeSpec, CategorySpec, ContractCheck,
    DistributionSpec, MapRequest, RegionSpec, ResolvedRequest, TerrainParams,
    ThemeSpec,
)
from .themes import REGISTRY as THEMES, get_theme, list_themes

__all__ = [
    "__version__", "GENERATOR_VERSION", "SCHEMA_VERSION",
    "ConfigError", "load_config", "request_from_dict", "request_to_dict",
    "generate", "get_theme", "list_themes", "THEMES",
    "BiomeBand", "BiomeSpec", "CategorySpec", "ContractCheck",
    "DistributionSpec", "MapRequest", "RegionSpec", "ResolvedRequest",
    "TerrainParams", "ThemeSpec",
]
