"""The mutable world state produced by the pipeline.

Grids are indexed ``[x][y]`` (column-major), matching the original generator so
height/biome arrays stay directly comparable against ``island_biomes.csv``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple


@dataclass
class World:
    width: int
    height: int
    theme_id: str
    seed: int

    height_map: List[List[float]] = field(default_factory=list)
    moisture: List[List[float]] = field(default_factory=list)
    biome: List[List[int]] = field(default_factory=list)
    slope: List[List[float]] = field(default_factory=list)
    river: List[List[float]] = field(default_factory=list)
    lake_id: List[List[int]] = field(default_factory=list)
    lake_level: List[List[float]] = field(default_factory=list)

    lakes: List[Dict] = field(default_factory=list)
    rivers: List[Dict] = field(default_factory=list)
    instances: List[Dict] = field(default_factory=list)
    region_masks: Dict[str, List[List[bool]]] = field(default_factory=dict)
    # Per-cell owning region id, resolved by RegionSpec.priority. Declared here
    # rather than attached dynamically so type checkers and dataclasses.fields()
    # can see it.
    region_owner: List[List[str]] = field(default_factory=list)

    stats: Dict[str, object] = field(default_factory=dict)
    biome_counts: Dict[int, int] = field(default_factory=dict)
    category_summary: List[Dict] = field(default_factory=list)

    # Filled in by the contract layer; exported into every report.
    contract: Dict[str, object] = field(default_factory=dict)
    # The live ContractReport object (not serialised) for callers that need to
    # branch on hard failures vs warnings.
    contract_report: object = None

    @property
    def W(self) -> int:
        return self.width

    @property
    def H(self) -> int:
        return self.height

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def slope_at(self, x: int, y: int) -> float:
        """Central-difference gradient magnitude, same estimator as the original."""
        hl = self.height_map[max(0, x - 1)][y]
        hr = self.height_map[min(self.width - 1, x + 1)][y]
        hd = self.height_map[x][max(0, y - 1)]
        hu = self.height_map[x][min(self.height - 1, y + 1)]
        return ((hr - hl) ** 2 + (hu - hd) ** 2) ** 0.5 * 0.5

    def land_cells(self, water_ids: Tuple[int, ...]) -> int:
        return sum(1 for y in range(self.height) for x in range(self.width)
                   if self.biome[x][y] not in water_ids)
