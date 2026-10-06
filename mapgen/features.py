"""Terrain features: mountain basins, lakes, rivers.

All three take their *placement* from a selectable distribution declared by the
theme, so 山脉坐落分布 / 湖泊分布 / 河流分布 are configurable the same way
scatter is. The shaping maths (basin falloff, elliptical lake carving, gradient
descent) is carried over from the validated generator.
"""

from __future__ import annotations

import math
from typing import Dict, List, Tuple

from .distributions import Domain, get_distribution
from .rng import DetRandom
from .schema import DistributionSpec, ResolvedRequest, grid_length_scale
from .world import World


def _domain_from_predicate(W: int, H: int, pred, length_scale: float = 1.0) -> Domain:
    cells = [(x, y) for y in range(H) for x in range(W) if pred(x, y)]
    return Domain(W, H, cells, length_scale=length_scale)


def _sample(spec: DistributionSpec, rng: DetRandom, domain: Domain,
            count: int) -> List[Tuple[int, int]]:
    if count <= 0 or not len(domain):
        return []
    return get_distribution(spec.kind).sample(rng, domain, count, spec.params)


def sample_basins(req: ResolvedRequest, seed: int,
                  rng: DetRandom) -> List[Tuple[float, float, float, float]]:
    """Valley basins, in normalised coords: (cx, cy, radius, depth)."""
    tp = req.terrain
    W, H = tp.width, tp.height
    spec = req.feature("mountains") or DistributionSpec("uniform", {})
    domain = Domain(W, H, [(x, y) for y in range(H) for x in range(W)],
                    length_scale=grid_length_scale(tp))
    pts = _sample(spec, rng, domain, tp.valley_count)
    basins = []
    for x, y in pts:
        basins.append((
            (x + 0.5) / W,
            (y + 0.5) / H,
            rng.next_float(0.18, 0.38),
            rng.next_float(0.15, 0.35),
        ))
    return basins


def carve_lakes(world: World, req: ResolvedRequest,
                rng: DetRandom) -> List[Dict]:
    """Place and carve inland lakes. Returns the lake records."""
    tp = req.terrain
    W, H = world.width, world.height
    height = world.height_map
    lo = tp.sea_level + tp.lake_min_center_height_above_sea
    hi = tp.lake_max_center_height

    domain = _domain_from_predicate(
        W, H, lambda x, y: lo <= height[x][y] <= hi,
        length_scale=grid_length_scale(tp))
    spec = req.feature("lakes") or DistributionSpec("poisson_disk",
                                                    {"min_spacing": 26.0})
    centres = _sample(spec, rng, domain, tp.lake_count)

    min_radius = max(0.018, tp.lake_mean_radius - tp.lake_radius_spread * 1.8)
    max_radius = min(0.10, tp.lake_mean_radius + tp.lake_radius_spread * 1.8)

    lakes: List[Dict] = []
    for idx, (ix, iy) in enumerate(centres):
        cx = (ix + 0.5) / W
        cy = (iy + 0.5) / H
        radius = max(min_radius,
                     min(max_radius, rng.normal(tp.lake_mean_radius,
                                                tp.lake_radius_spread)))
        surface = max(tp.sea_level + 0.025,
                      height[ix][iy] - rng.next_float(0.045, 0.11))

        cells = 0
        x0, x1 = max(0, int((cx - radius) * W)), min(W, int((cx + radius) * W) + 1)
        y0, y1 = max(0, int((cy - radius) * H)), min(H, int((cy + radius) * H) + 1)
        for y in range(y0, y1):
            for x in range(x0, x1):
                q = math.sqrt(((x / W - cx) / radius) ** 2
                              + ((y / H - cy) / radius) ** 2)
                if q >= 1.0 or height[x][y] < tp.sea_level:
                    continue
                world.lake_id[x][y] = idx
                world.lake_level[x][y] = surface
                height[x][y] = min(height[x][y], surface - 0.012 - 0.045 * (1.0 - q))
                cells += 1
        if cells:
            lakes.append({"id": idx, "x": cx, "y": cy, "radius": radius,
                          "level": surface, "cells": cells,
                          "frozen": bool(tp.frozen_water)})
    world.lakes = lakes
    return lakes


def trace_rivers(world: World, req: ResolvedRequest,
                 rng: DetRandom) -> List[Dict]:
    """Gradient-descent rivers from sampled highland sources to water.

    Sources come from the theme's ``rivers`` distribution, but are oversampled
    and filtered: a trace that dead-ends in a local minimum is discarded rather
    than emitted as a stub. Without that filter every river on a pitted height
    field terminates inland, which is what an earlier revision did.

    Returns polylines as well as filling the normalised flow grid, so an engine
    can consume rivers either as a per-cell field or as vector paths.
    """
    tp = req.terrain
    W, H = world.width, world.height
    height = world.height_map
    water_ids = {b.id for b in req.theme.biomes if b.is_water}

    domain = _domain_from_predicate(
        W, H,
        lambda x, y: height[x][y] > 0.55 and world.biome[x][y] not in water_ids,
        length_scale=grid_length_scale(tp))
    spec = req.feature("rivers") or DistributionSpec("uniform", {})
    wanted = max(0, tp.river_count)
    # Oversample: gradient descent only reaches water from some starting cells.
    sources = _sample(spec, rng, domain, wanted * 10 if wanted else 0)

    flow = [[0.0] * H for _ in range(W)]
    rivers: List[Dict] = []
    rejected = 0
    # A pure steepest-descent walk strands in the first noise pit it meets, so
    # most candidate rivers never reach the sea. Real water cuts through shallow
    # barriers; model that with a bounded uphill escape budget. Without it a
    # 5-river request yields 2 and the map reads as having almost no drainage.
    escape_budget = int(tp.river_escape_budget)
    escape_tolerance = 0.02
    # The "is this a real river" test was a fixed 6 cells at the 256 reference;
    # scale it with the grid so small maps do not reject every tributary and
    # large maps do not admit one-step dribbles.
    min_path = max(3, int(round(6 * grid_length_scale(tp))))

    for sx, sy in sources:
        if len(rivers) >= wanted:
            break
        cx, cy = sx, sy
        path: List[Tuple[int, int]] = []
        reached_water = False
        visited = set()
        escapes = escape_budget
        for _ in range(W + H):
            if (cx, cy) in visited:
                break
            visited.add((cx, cy))
            path.append((cx, cy))
            if height[cx][cy] < tp.sea_level or world.lake_id[cx][cy] >= 0:
                reached_water = True
                break

            here = height[cx][cy]
            nx, ny, lowest = cx, cy, here
            best_up, up_x, up_y = None, cx, cy
            for oy in (-1, 0, 1):
                for ox in (-1, 0, 1):
                    if ox == 0 and oy == 0:
                        continue
                    tx, ty = cx + ox, cy + oy
                    if not (0 <= tx < W and 0 <= ty < H):
                        continue
                    ngh = height[tx][ty] + rng.next_float(0, 0.003)
                    if ngh < lowest:
                        lowest, nx, ny = ngh, tx, ty
                    if ngh < here + escape_tolerance and (best_up is None or ngh < best_up):
                        best_up, up_x, up_y = ngh, tx, ty

            if (nx, ny) == (cx, cy):
                if escapes <= 0 or best_up is None:
                    break
                escapes -= 1
                nx, ny = up_x, up_y
            cx, cy = nx, ny

        # A river must actually run somewhere, but a short tributary that flows
        # into a nearby lake is still a river. An earlier threshold of 12 cells
        # rejected 30 of 50 valid traces on the island theme, leaving a
        # 5-river request with 2 rivers.
        if not reached_water or len(path) < min_path:
            rejected += 1
            continue

        for px, py in path:
            flow[px][py] += 1.0
        rivers.append({"id": len(rivers), "source": [sx, sy],
                       "reached_water": reached_water, "length": len(path),
                       "path": path,
                       "terminus": list(path[-1])})

    max_flow = max((flow[x][y] for y in range(H) for x in range(W)), default=0.0) or 1.0
    for y in range(H):
        for x in range(W):
            world.river[x][y] = flow[x][y] / max_flow
    world.rivers = rivers
    world.river_trace_rejected = rejected  # type: ignore[attr-defined]
    return rivers
