"""Region masks -- the 局部概率化 layer.

A region is a normalised spatial sub-domain. Categories can be overridden
inside a region (different count, different distribution, different params),
which is how one map ends up with, say, a dense poisson-sampled pine belt in
the north and sparse uniformly-scattered trees elsewhere.
"""

from __future__ import annotations

import math
from typing import Dict, Iterable, List, Sequence

from .schema import RegionSpec
from .world import World


def build_masks(world: World, regions: Sequence[RegionSpec]) -> Dict[str, List[List[bool]]]:
    """Rasterise every region into a per-cell boolean mask.

    A cell belongs to the region when its *centre* does, which is exactly the
    predicate ``RegionSpec.contains`` uses. Deriving the rect range any other
    way makes the fast path and ``contains`` disagree by one cell at each edge.

    Regions are visited in descending priority (declaration order breaking ties) so
    the returned mapping is ordered by precedence. Every consumer that walks masks in
    order therefore sees the same winner for a cell in several masks.
    """
    W, H = world.width, world.height
    masks: Dict[str, List[List[bool]]] = {}
    for r in ordered_by_priority(regions):
        mask = [[False] * H for _ in range(W)]
        if r.shape == "rect":
            b = r.bounds
            x0f = float(b.get("x0", 0.0))
            x1f = float(b.get("x1", 1.0))
            y0f = float(b.get("y0", 0.0))
            y1f = float(b.get("y1", 1.0))
            # cell x is inside iff x0f <= (x+0.5)/W <= x1f
            xa = max(0, math.ceil(x0f * W - 0.5))
            xb = min(W - 1, math.floor(x1f * W - 0.5))
            ya = max(0, math.ceil(y0f * H - 0.5))
            yb = min(H - 1, math.floor(y1f * H - 0.5))
            for y in range(ya, yb + 1):
                for x in range(xa, xb + 1):
                    mask[x][y] = True
        elif r.shape == "all":
            for x in range(W):
                for y in range(H):
                    mask[x][y] = True
        else:
            for y in range(H):
                v = (y + 0.5) / H
                for x in range(W):
                    if r.contains((x + 0.5) / W, v):
                        mask[x][y] = True
        masks[r.id] = mask
    return masks


def ordered_by_priority(regions: Sequence[RegionSpec]) -> List[RegionSpec]:
    """Regions sorted by descending priority, declaration order breaking ties.

    ``MapRequest.resolve`` rejects duplicate priorities, so ties should not reach
    here; the sort is written to be stable regardless, so that any caller using these
    helpers directly still gets a deterministic order rather than one that depends on
    dict or set iteration.
    """
    return sorted(regions, key=lambda r: -int(getattr(r, "priority", 0) or 0))


def attribute_regions(world: World, regions: Sequence[RegionSpec],
                      masks: Dict[str, List[List[bool]]]) -> List[List[str]]:
    """Per-cell owning region id ("" when the cell is in no region).

    Overlapping regions all still apply their own category overrides; this answers
    the separate, single-valued question of attribution: which region a cell belongs
    to. Highest priority wins, ties break on declaration order.
    """
    W, H = world.width, world.height
    owner: List[List[str]] = [[""] * H for _ in range(W)]
    # Walk in ascending precedence so the strongest region writes last and wins.
    for r in reversed(ordered_by_priority(regions)):
        mask = masks.get(r.id)
        if mask is None:
            continue
        for x in range(W):
            col_o, col_m = owner[x], mask[x]
            for y in range(H):
                if col_m[y]:
                    col_o[y] = r.id
    return owner


def owner_counts(owner: Sequence[Sequence[str]]) -> Dict[str, int]:
    """Cell count per owning region id, from an attribution grid."""
    counts: Dict[str, int] = {}
    for col in owner:
        for rid in col:
            if rid:
                counts[rid] = counts.get(rid, 0) + 1
    return counts


def mask_cell_count(mask: List[List[bool]]) -> int:
    return sum(1 for col in mask for v in col if v)


def union(masks: Iterable[List[List[bool]]]) -> List[List[bool]]:
    """OR several masks together (used to carve regions out of the base area)."""
    masks = list(masks)
    if not masks:
        return []
    W = len(masks[0])
    H = len(masks[0][0])
    out = [[False] * H for _ in range(W)]
    for m in masks:
        for x in range(W):
            col_o, col_m = out[x], m[x]
            for y in range(H):
                if col_m[y]:
                    col_o[y] = True
    return out
