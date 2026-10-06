"""Scatter placement: category x distribution x (optional) region.

This is the module that makes the three-tier model actually run. For each
category it builds the legal domain (allowed biomes + slope limit + region
mask), hands it to the category's distribution strategy, and turns the returned
cells into engine-consumable instances.

Nothing here is allowed to fail quietly: if a category requests N objects and
places far fewer, the shortfall is recorded in the summary and picked up by the
contract layer.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from .distributions import Domain, get_distribution
from .rng import DetRandom
from .schema import (CategorySpec, RegionSpec, ResolvedRequest, ThemeSpec,
                     grid_length_scale)
from .world import World


def legal_cells(world: World, theme: ThemeSpec, cat: CategorySpec,
                mask: Optional[Sequence[Sequence[bool]]] = None,
                exclude: Optional[Sequence[Sequence[bool]]] = None) -> List[tuple]:
    """Cells where this category is allowed to appear."""
    by_key = {b.key: b.id for b in theme.biomes}
    unknown = [k for k in cat.allowed_biomes if k not in by_key]
    if unknown:
        raise KeyError(
            f"category {cat.id!r} of theme {theme.id!r} allows unknown biome(s) "
            f"{unknown}; known: {sorted(by_key)}")
    allowed = {by_key[k] for k in cat.allowed_biomes}

    out = []
    biome, slope = world.biome, world.slope
    for y in range(world.height):
        for x in range(world.width):
            if biome[x][y] not in allowed:
                continue
            if slope[x][y] >= cat.max_slope:
                continue
            if mask is not None and not mask[x][y]:
                continue
            if exclude is not None and exclude[x][y]:
                continue
            out.append((x, y))
    return out


def place_category(world: World, req: ResolvedRequest, cat: CategorySpec,
                   rng: DetRandom, mask=None, exclude=None,
                   region_id: str = "", occupied: Optional[set] = None) -> Dict:
    cells = legal_cells(world, req.theme, cat, mask, exclude)
    if occupied is not None:
        # Drop cells another category in the same exclusion group already took.
        cells = [c for c in cells if c not in occupied]
    domain = Domain(world.width, world.height, cells, occupied=occupied,
                    length_scale=grid_length_scale(req.terrain))
    dist = get_distribution(cat.distribution.kind)
    groups = dist.sample_groups(rng, domain, cat.count, cat.distribution.params)

    W, H = world.width, world.height
    lo, hi = cat.scale_range
    placed = 0
    centroids: List[Dict] = []
    for cid, group in enumerate(groups):
        sx = sy = 0.0
        for x, y in group:
            world.instances.append({
                "x": x, "y": y,
                "u": (x + 0.5) / W, "v": (y + 0.5) / H,
                "z": world.height_map[x][y],
                "category": cat.id,
                "type": cat.object_type,
                "scale": rng.next_float(lo, hi),
                "rotation": rng.next_float(0.0, cat.rotation_jitter),
                "region": region_id,
                "cluster_id": cid if cat.emit_cluster_id else -1,
            })
            placed += 1
            sx += x
            sy += y
        if cat.emit_cluster_id and group:
            centroids.append({"cluster_id": cid,
                              "x": sx / len(group), "y": sy / len(group),
                              "count": len(group)})

    return {
        "category": cat.id,
        "display_name": cat.display_name,
        "object_type": cat.object_type,
        "distribution": cat.distribution.kind,
        "params": dict(cat.distribution.params),
        "requested": cat.count,
        "placed": placed,
        "legal_cells": len(cells),
        "region": region_id,
        "clusters": centroids,
    }


def place_all(world: World, req: ResolvedRequest,
              regions: Sequence[RegionSpec],
              masks: Dict[str, List[List[bool]]]) -> List[Dict]:
    """Run every category, applying region overrides where declared.

    Semantics: a category's base ``count`` applies to the area *outside* every
    region that overrides it; each overriding region then places its own
    separately-counted population inside its mask. This keeps the numbers a
    designer writes in the config predictable.
    """
    from .regions import union

    # One occupancy set per exclusion group, shared across every category (and
    # across each category's base + per-region placements) in that group.
    occupancy: Dict[str, set] = {}

    def group_set(cat: CategorySpec) -> Optional[set]:
        g = cat.group()
        if not g:
            return None
        return occupancy.setdefault(g, set())

    summaries: List[Dict] = []
    for cat in req.categories:
        overriding = [r for r in regions if cat.id in r.overrides]
        rng = DetRandom(req.seed).fork(f"cat:{cat.id}")

        if overriding:
            excluded = union([masks[r.id] for r in overriding if r.id in masks])
            summaries.append(place_category(world, req, cat, rng,
                                            exclude=excluded, region_id="",
                                            occupied=group_set(cat)))
            for r in overriding:
                mask = masks.get(r.id)
                region_area = (sum(sum(1 for cell in column if cell) for column in mask)
                               / float(world.width * world.height)) if mask else 0.0
                rc = cat.overridden(r.overrides[cat.id], area_fraction=region_area)
                r_rng = DetRandom(req.seed).fork(f"cat:{cat.id}@region:{r.id}")
                summaries.append(place_category(world, req, rc, r_rng,
                                                mask=mask,
                                                region_id=r.id,
                                                occupied=group_set(rc)))
        else:
            summaries.append(place_category(world, req, cat, rng, region_id="",
                                            occupied=group_set(cat)))

    world.category_summary = summaries
    return summaries
