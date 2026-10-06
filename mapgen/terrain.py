"""Terrain: height field, moisture, and theme-driven biome classification.

The height field maths is carried over unchanged from the validated generator
(domain-warped ridged FBM + valley basins + island mask). What is new is that
biome classification is driven entirely by the theme's ``bands`` and
``default_biome``, so the same height field yields snow or temperate terrain
purely by swapping the theme.
"""

from __future__ import annotations

import math
from typing import List, Sequence, Tuple

from .noise import fbm, ridged, smooth_noise, smooth_step, valley_carve
from .schema import ResolvedRequest, ThemeSpec
from .world import World


def build_height(seed: int, req: ResolvedRequest,
                 basins: Sequence[Tuple[float, float, float, float]]) -> List[List[float]]:
    """Domain-warped ridged FBM, depressed by the supplied valley basins."""
    tp = req.terrain
    W, H = tp.width, tp.height
    height = [[0.0] * H for _ in range(W)]
    for y in range(H):
        v = y / H
        for x in range(W):
            u = x / W

            wx = fbm(u * tp.mountain_frequency, v * tp.mountain_frequency,
                     seed + 7, 4, 0.5, 2.0)
            wy = fbm(u * tp.mountain_frequency + 5.2, v * tp.mountain_frequency + 1.3,
                     seed + 19, 4, 0.5, 2.0)
            wu = u + (wx - 0.5) * tp.warp_strength
            wv = v + (wy - 0.5) * tp.warp_strength

            ridge = ridged(wu * tp.mountain_frequency * 3.0,
                           wv * tp.mountain_frequency * 3.0,
                           seed + 31, tp.noise_octaves, tp.persistence, tp.lacunarity)
            h = ridge * tp.height_amplitude + tp.height_base
            h *= valley_carve(u, v, basins)
            h += smooth_noise(u * tp.detail_frequency * 8,
                              v * tp.detail_frequency * 8, seed + 777) * 0.05
            h += smooth_noise(u * 35, v * 35, seed + 9999) * 0.010

            nx = (u - 0.5) * 2
            ny = (v - 0.5) * 2
            cwarp = fbm(u * 2.5 + wx * 0.3, v * 2.5 + wy * 0.3, seed + 444, 3, 0.6, 2.0)
            dist = math.sqrt(nx * nx + ny * ny) + (cwarp - 0.5) * 0.30
            mask = 1.0 - smooth_step(tp.island_radius * 0.65,
                                     tp.island_radius * 1.10, dist)
            height[x][y] = max(0.0, min(1.0, h * mask))

    if tp.height_normalize == "rank":
        _normalize_rank(height, tp.sea_level, tp.height_rank_gamma)
    elif tp.height_normalize != "none":
        raise ValueError(
            f"unknown height_normalize {tp.height_normalize!r} (use 'none' or 'rank')")
    return height


def _normalize_rank(height: List[List[float]], sea_level: float,
                    gamma: float) -> None:
    """Remap land-cell elevations onto a fixed target curve by percentile rank.

    Deterministic and RNG-free: cells are sorted by ``(height, x, y)`` so ties
    break identically every run, then the i-th ranked land cell is assigned
    ``sea + (1-sea) * ((i+1)/n)**gamma``. Because the mapping depends only on
    *rank*, the fraction of land above any absolute threshold is the same for
    every seed -- which is exactly the seed-variance the island contract kept
    tripping on. Water cells (below sea level) are left untouched, so the
    coastline and land fraction are preserved bit-for-bit; the spatial ordering
    of the ridged noise is also preserved, so ridges still read as ridges.
    """
    W = len(height)
    H = len(height[0]) if W else 0
    land = [(height[x][y], x, y)
            for x in range(W) for y in range(H) if height[x][y] >= sea_level]
    n = len(land)
    if n < 2:
        return
    land.sort()
    span = 1.0 - sea_level
    for i, (_h, x, y) in enumerate(land):
        p = (i + 1) / n            # in (0, 1]; lowest land cell stays just above sea
        height[x][y] = sea_level + span * (p ** gamma)


def build_moisture(seed: int, world: World, sea_level: float) -> List[List[float]]:
    W, H = world.width, world.height
    moisture = [[0.0] * H for _ in range(W)]
    for y in range(H):
        v = y / H
        for x in range(W):
            u = x / W
            hgt = world.height_map[x][y]
            if world.lake_id[x][y] >= 0:
                m = 1.0
            elif hgt < sea_level:
                m = 0.7
            else:
                m = 1.0 - smooth_step(0, 1, hgt)
            m += smooth_noise(u * 5, v * 5, seed + 5555) * 0.25
            moisture[x][y] = max(0.0, min(1.0, m))
    return moisture


def classify(world: World, theme: ThemeSpec, sea_level: float) -> None:
    """Assign a biome id per cell from the theme's ordered bands."""
    by_key = {b.key: b.id for b in theme.biomes}
    default_id = by_key[theme.default_biome]
    lake_id = by_key.get(theme.lake_biome, -1) if theme.lake_biome else -1
    bands = theme.bands

    for y in range(world.height):
        for x in range(world.width):
            if lake_id >= 0 and world.lake_id[x][y] >= 0:
                world.biome[x][y] = lake_id
                continue
            h = world.height_map[x][y]
            m = world.moisture[x][y]
            chosen = default_id
            for band in bands:
                if band.matches(h, m, sea_level):
                    chosen = by_key[band.biome]
                    break
            world.biome[x][y] = chosen


def compute_slope(world: World) -> None:
    """Precompute the gradient grid once; every category filter reuses it."""
    W, H = world.width, world.height
    h = world.height_map
    slope = [[0.0] * H for _ in range(W)]
    for y in range(H):
        ym = y - 1 if y > 0 else 0
        yp = y + 1 if y < H - 1 else H - 1
        for x in range(W):
            xm = x - 1 if x > 0 else 0
            xp = x + 1 if x < W - 1 else W - 1
            dh = h[xp][y] - h[xm][y]
            dv = h[x][yp] - h[x][ym]
            slope[x][y] = math.sqrt(dh * dh + dv * dv) * 0.5
    world.slope = slope


def count_biomes(world: World) -> None:
    counts: dict = {}
    for y in range(world.height):
        for x in range(world.width):
            b = world.biome[x][y]
            counts[b] = counts.get(b, 0) + 1
    world.biome_counts = counts
