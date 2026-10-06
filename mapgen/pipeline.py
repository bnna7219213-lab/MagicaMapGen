"""Pipeline orchestration: ResolvedRequest -> World.

Stage order is load-bearing:

1. mountains   -- basin centres sampled through the theme's distribution
2. height      -- ridged FBM shaped by those basins
3. lakes       -- carved into the height field (must precede classification)
4. moisture    -- depends on final heights and lake positions
5. biomes      -- theme bands over (height, moisture)
6. slope       -- needed by every placement filter
7. rivers      -- gradient descent; needs biomes to know what water is
8. regions     -- rasterise the 局部概率化 masks
9. scatter     -- category x distribution x region
10. contract   -- validate, never silently

Each stage draws from its own forked random stream, so adding or reordering a
stage does not reshuffle the streams of the others.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple

from .contract import run_contract
from .features import carve_lakes, sample_basins, trace_rivers
from .regions import attribute_regions, build_masks, mask_cell_count, owner_counts
from .rng import DetRandom
from .scatter import place_all
from .schema import ResolvedRequest
from .terrain import build_height, build_moisture, classify, compute_slope, count_biomes
from .world import World

#: Stage labels in execution order. Emitted as progress so a GUI can show real
#: phase names instead of a fake indeterminate bar. The count is what turns those
#: into percentages.
STAGES: Tuple[str, ...] = (
    "mountains", "height", "lakes", "moisture", "biomes",
    "slope", "rivers", "regions", "scatter", "contract",
)

#: ``(stage_name, completed_stages, total_stages)`` -> None
ProgressHook = Callable[[str, int, int], None]


def generate(req: ResolvedRequest,
             progress: Optional[ProgressHook] = None) -> World:
    """Build a World from a resolved request.

    ``progress`` is called after each stage with ``(stage, done, total)``. It is a
    pure observer: it never influences the random streams, so enabling it cannot
    change the generated map. Callers that need it recorded (a GUI progress bar, a
    CI log) write it wherever they like -- it is deliberately kept out of every
    artifact, because those must stay byte-identical for a given seed.
    """
    seed = req.seed
    tp = req.terrain
    W, H = tp.width, tp.height
    total_stages = len(STAGES)
    done = 0

    def step(name: str) -> None:
        nonlocal done
        done += 1
        if progress is not None:
            progress(name, done, total_stages)

    world = World(width=W, height=H, theme_id=req.theme.id, seed=seed)
    world.height_map = [[0.0] * H for _ in range(W)]
    world.moisture = [[0.0] * H for _ in range(W)]
    world.biome = [[0] * H for _ in range(W)]
    world.slope = [[0.0] * H for _ in range(W)]
    world.river = [[0.0] * H for _ in range(W)]
    world.lake_id = [[-1] * H for _ in range(W)]
    world.lake_level = [[0.0] * H for _ in range(W)]

    basins = sample_basins(req, seed, DetRandom(seed).fork("mountains"))
    step("mountains")
    world.height_map = build_height(seed, req, basins)
    world.basins = basins  # type: ignore[attr-defined]
    step("height")

    carve_lakes(world, req, DetRandom(seed).fork("lakes"))
    step("lakes")
    world.moisture = build_moisture(seed, world, tp.sea_level)
    step("moisture")
    classify(world, req.theme, tp.sea_level)
    count_biomes(world)
    step("biomes")
    compute_slope(world)
    step("slope")
    trace_rivers(world, req, DetRandom(seed).fork("rivers"))
    step("rivers")

    regions = req.request.regions
    masks = build_masks(world, regions)
    world.region_masks = masks
    # Single-valued attribution resolved by region priority. Overlapping regions all
    # still place their own overrides; this only answers "which region owns a cell".
    world.region_owner = attribute_regions(world, regions, masks)
    step("regions")

    # Scatter deterministically. The incremental-edit overlay (see ``mapgen.edit``)
    # replays instance-level ops on top of this exact result, so the surrounding
    # map is reproduced byte-for-byte and only the edited instances differ.
    place_all(world, req, regions, masks)
    step("scatter")

    _compute_stats(world, req, masks)

    report = run_contract(world, req)
    world.contract_report = report
    world.contract = report.to_dict()
    step("contract")
    return world


def _compute_stats(world: World, req: ResolvedRequest,
                   masks: Dict[str, list]) -> None:
    theme = req.theme
    water_ids = {b.id for b in theme.biomes if b.is_water}
    key_by_id = {b.id: b.key for b in theme.biomes}
    total = world.width * world.height

    biome_cells = {key_by_id.get(b, str(b)): c
                   for b, c in sorted(world.biome_counts.items())}
    water_cells = sum(c for b, c in world.biome_counts.items() if b in water_ids)
    land_cells = total - water_cells

    by_category: Dict[str, int] = {}
    by_type: Dict[str, int] = {}
    by_region: Dict[str, int] = {}
    for inst in world.instances:
        by_category[inst["category"]] = by_category.get(inst["category"], 0) + 1
        by_type[inst["type"]] = by_type.get(inst["type"], 0) + 1
        rid = inst.get("region") or ""
        by_region[rid] = by_region.get(rid, 0) + 1

    clusters = 0
    for s in world.category_summary:
        clusters += len(s.get("clusters") or [])

    world.stats = {
        "total_cells": total,
        "land_cells": land_cells,
        "water_cells": water_cells,
        "land_fraction": round(land_cells / total, 4) if total else 0.0,
        "biome_cells": biome_cells,
        "lake_count": len(world.lakes),
        "lake_cells": sum(lk["cells"] for lk in world.lakes),
        "river_count": len(world.rivers),
        "rivers_reaching_water": sum(1 for r in world.rivers if r["reached_water"]),
        "river_cells": sum(1 for y in range(world.height)
                           for x in range(world.width)
                           if world.river[x][y] > 0.15),
        "instance_count": len(world.instances),
        "instances_by_category": by_category,
        "instances_by_type": by_type,
        "instances_by_region": by_region,
        "cluster_count": clusters,
        "basin_count": len(getattr(world, "basins", ()) or ()),
        "max_height": round(max((max(col) for col in world.height_map), default=0.0), 4),
        "regions": owner_counts(getattr(world, "region_owner", []) or []),
        "regions_raw_cells": {rid: mask_cell_count(m) for rid, m in masks.items()},
    }
