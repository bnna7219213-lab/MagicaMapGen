#!/usr/bin/env python3
"""
Island Map Generator - Prototype design tool for game development.
Generates procedurally diverse island terrains with:
  - Multi-octave heightmap (ridged + domain-warped noise) for mountain ranges, valleys, basins
  - Inland lake centers and radii sampled from truncated normal distributions
  - Forest groves with multiple Gaussian tree clusters and adjustable density
  - Biome assignment (beach, grassland, forest, rocky peak, valley basin) by elevation + moisture
  - River network (gradient descent from random high points to sea, with probabilistic branching)
  - Scatter placement (trees, rocks, details) by biome + slope + probability
Deterministic by seed: same seed + parameters => identical result across runs.
Outputs:
  island_height.pgm  - 16-bit heightmap
  island_biomes.csv  - per-cell biome + moisture
  island_scatter.csv - placement list
  island_report.json - full stats
  island_houdini_scene.obj/.mtl - editable 3D terrain, water, rivers and scatter for Houdini
  island_preview.html - optional interactive visualization (--html-preview)
"""

import math
import json
import os
import sys
import time
from dataclasses import dataclass, field
from typing import List, Tuple

# --------------- Configuration ---------------
@dataclass
class IslandConfig:
    width: int = 256
    height: int = 256
    island_radius: float = 0.45        # 0..1 of half-min(dimension)
    mountain_frequency: float = 1.2    # ridged noise base frequency
    detail_frequency: float = 4.5
    valley_count: int = 4              # guaranteed carved basins
    river_count: int = 6               # number of river sources
    lake_count: int = 8
    lake_mean_radius: float = 0.045
    lake_radius_spread: float = 0.012
    sea_level: float = 0.22            # 0..1 normalized (lower = more land)
    tree_density: float = 0.7          # 0..1 scatter probability multiplier
    tree_cluster_count: int = 18
    trees_per_cluster: int = 42
    tree_cluster_spread: float = 0.012
    grass_density: float = 0.6
    rock_density: float = 0.4
    beach_width: float = 0.05
    warp_strength: float = 0.20
    noise_octaves: int = 5
    persistence: float = 0.55
    lacunarity: float = 2.05

# --------------- Deterministic RNG (xorshift128+) ---------------
MASK64 = (1 << 64) - 1

class DetRandom:
    def __init__(self, seed: int):
        z = ((seed & 0xFFFFFFFFFFFFFFFF) + 0x9E3779B97F4A7C15) & MASK64
        self._s0 = self._mix(z); self._s1 = self._mix(z)
        if self._s0 == 0 and self._s1 == 0:
            self._s1 = 1

    @staticmethod
    def _mix(z: int) -> int:
        z = (z + 0x9E3779B97F4A7C15) & MASK64
        x = z
        x = ((x ^ (x >> 30)) * 0xBF58476D1CE4E5B9) & MASK64
        x = ((x ^ (x >> 27)) * 0x94D049BB133111EB) & MASK64
        return (x ^ (x >> 31)) & MASK64

    def next_ulong(self) -> int:
        s1 = self._s0
        s0 = self._s1
        self._s0 = s0
        s1 = (s1 ^ ((s1 << 23) & MASK64)) & MASK64
        self._s1 = (s1 ^ s0 ^ ((s1 >> 18) & MASK64) ^ ((s0 >> 5) & MASK64)) & MASK64
        return (self._s1 + s0) & MASK64

    def next_float(self, lo: float, hi: float) -> float:
        t = (self.next_ulong() >> 11) / 9007199254740992.0
        return lo + (hi - lo) * t

    def normal(self, mean: float, sigma: float) -> float:
        """Box-Muller normal sample using this generator's reproducible stream."""
        u1 = max(1e-15, self.next_float(0.0, 1.0))
        u2 = self.next_float(0.0, 1.0)
        return mean + sigma * math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)

    def next_int(self, lo: int, hi: int) -> int:
        if hi <= lo: return lo
        span = hi - lo
        return lo + (self.next_ulong() % span)

    def chance(self, p: float) -> bool:
        return self.next_float(0, 1) < p

# --------------- Value noise + FBM ---------------
def hash2(x: int, y: int, seed: int) -> int:
    h = seed & 0xFFFFFFFF
    h ^= (x * 374761393) & 0xFFFFFFFF
    h ^= (y * 668265263) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    h ^= (h >> 16)
    return h & 0xFFFFFF

def smooth_noise(x: float, y: float, seed: int) -> float:
    ix = int(math.floor(x))
    iy = int(math.floor(y))
    fx = x - ix
    fy = y - iy
    fx = fx * fx * (3 - 2 * fx)
    fy = fy * fy * (3 - 2 * fy)
    a = hash2(ix, iy, seed) / 16777215.0
    b = hash2(ix+1, iy, seed) / 16777215.0
    c = hash2(ix, iy+1, seed) / 16777215.0
    d = hash2(ix+1, iy+1, seed) / 16777215.0
    ab = a + (b - a) * fx
    cd = c + (d - c) * fx
    return ab + (cd - ab) * fy

def fbm(x: float, y: float, seed: int, octaves: int, persistence: float, lacunarity: float) -> float:
    amp, freq, s, norm = 1.0, 1.0, 0.0, 0.0
    for o in range(octaves):
        s += amp * smooth_noise(x*freq, y*freq, seed + o*1013)
        norm += amp
        amp *= persistence
        freq *= lacunarity
    return s / norm

def ridged(x: float, y: float, seed: int, octaves: int, persistence: float, lacunarity: float) -> float:
    amp, freq, s, norm = 1.0, 1.0, 0.0, 0.0
    for o in range(octaves):
        n = smooth_noise(x*freq, y*freq, seed + o*2017)
        n = 1.0 - abs(n * 2.0 - 1.0)
        n = n * n
        s += amp * n
        norm += amp
        amp *= persistence
        freq *= lacunarity
    return s / norm

def valley_carve(u: float, v: float, basins: List[Tuple[float,float,float,float]]) -> float:
    val = 1.0
    for cx, cy, r, depth in basins:
        dx = u - cx
        dy = v - cy
        d2 = dx*dx + dy*dy
        r2 = r*r
        falloff = max(0.0, 1.0 - d2/r2)
        falloff = falloff * falloff * (3 - 2*falloff)
        val -= falloff * depth
    return max(0.0, val)

def smooth_step(a: float, b: float, x: float) -> float:
    t = max(0.0, min(1.0, (x - a) / (b - a)))
    return t * t * (3 - 2*t)

# --------------- Main Generation ---------------
def generate(seed: int, cfg: IslandConfig):
    rng = DetRandom(seed)
    W, H = cfg.width, cfg.height

    height = [[0.0]*H for _ in range(W)]
    moisture = [[0.0]*H for _ in range(W)]
    biome = [[0]*H for _ in range(W)]
    river = [[0.0]*H for _ in range(W)]
    lake_id = [[-1]*H for _ in range(W)]
    lake_level = [[0.0]*H for _ in range(W)]
    scatter: List[dict] = []
    lake_centers = []
    tree_clusters = []

    # Pass 1: valley basins (deterministic from seed)
    basins = []
    for _ in range(cfg.valley_count):
        basins.append((
            rng.next_float(0.25, 0.75),
            rng.next_float(0.25, 0.75),
            rng.next_float(0.18, 0.38),
            rng.next_float(0.15, 0.35)
        ))

    # Pass 2: heightmap
    max_h = 0.0
    for y in range(H):
        for x in range(W):
            u = x / W
            v = y / H

            # domain warp
            wx = fbm(u * cfg.mountain_frequency, v * cfg.mountain_frequency, seed+7, 4, 0.5, 2.0)
            wy = fbm(u * cfg.mountain_frequency+5.2, v * cfg.mountain_frequency+1.3, seed+19, 4, 0.5, 2.0)
            wu = u + (wx - 0.5) * cfg.warp_strength
            wv = v + (wy - 0.5) * cfg.warp_strength

            # ridged mountains with higher amplitude
            ridge = ridged(wu * cfg.mountain_frequency*3.0, wv * cfg.mountain_frequency*3.0,
                           seed+31, cfg.noise_octaves, cfg.persistence, cfg.lacunarity)

            # secondary depression noise for valley carving
            valley = valley_carve(u, v, basins)

            # Combine: boost ridge to overcome sea level, apply valley depressions
            h = ridge * 1.35 + 0.22  # boost so peaks exceed 0.65/0.82 for rocky/peak biomes
            h *= valley

            # fine detail
            h += smooth_noise(u * cfg.detail_frequency*8, v * cfg.detail_frequency*8, seed+777) * 0.05
            h += smooth_noise(u*35, v*35, seed+9999) * 0.010

            # island mask with coastline warp
            nx = (x / W - 0.5) * 2
            ny = (y / H - 0.5) * 2
            cwarp = fbm(u*2.5 + wx*0.3, v*2.5 + wy*0.3, seed+444, 3, 0.6, 2.0)
            dist = math.sqrt(nx*nx + ny*ny)
            dist += (cwarp - 0.5) * 0.30
            mask = 1.0 - smooth_step(cfg.island_radius*0.65, cfg.island_radius*1.10, dist)

            h *= mask
            h = max(0.0, min(1.0, h))
            height[x][y] = h
            if h > max_h: max_h = h

    # Inland lake centers are sampled from a truncated bivariate normal around
    # the island core, with normal-distributed sizes and minimum spacing.
    min_radius = max(0.018, cfg.lake_mean_radius - cfg.lake_radius_spread * 1.8)
    max_radius = min(0.10, cfg.lake_mean_radius + cfg.lake_radius_spread * 1.8)
    for lake_index in range(max(0, cfg.lake_count)):
        chosen = None
        for _ in range(500):
            cx = max(0.12, min(0.88, rng.normal(0.5, 0.17)))
            cy = max(0.12, min(0.88, rng.normal(0.5, 0.17)))
            radius = max(min_radius, min(max_radius, rng.normal(cfg.lake_mean_radius, cfg.lake_radius_spread)))
            ix, iy = min(W-1, int(cx*W)), min(H-1, int(cy*H))
            if height[ix][iy] < cfg.sea_level + 0.07:
                continue
            if any(math.hypot((cx-p["x"])*W, (cy-p["y"])*H) < (radius+p["radius"])*min(W,H)*0.72
                   for p in lake_centers):
                continue
            chosen = (cx, cy, radius, ix, iy)
            break
        if chosen is None:
            continue

        cx, cy, radius, ix, iy = chosen
        surface = max(cfg.sea_level + 0.025, height[ix][iy] - rng.next_float(0.045, 0.11))
        lake = {"id": lake_index, "x": cx, "y": cy, "radius": radius,
                "level": surface, "cells": 0}
        x0, x1 = max(0, int((cx-radius)*W)), min(W, int((cx+radius)*W)+1)
        y0, y1 = max(0, int((cy-radius)*H)), min(H, int((cy+radius)*H)+1)
        for y in range(y0, y1):
            for x in range(x0, x1):
                q = math.sqrt(((x/W-cx)/radius)**2 + ((y/H-cy)/radius)**2)
                if q >= 1.0 or height[x][y] < cfg.sea_level:
                    continue
                lake_id[x][y] = lake_index
                lake_level[x][y] = surface
                height[x][y] = min(height[x][y], surface - 0.012 - 0.045*(1.0-q))
                lake["cells"] += 1
        if lake["cells"]:
            lake_centers.append(lake)

    # Pass 3: moisture
    for y in range(H):
        for x in range(W):
            hgt = height[x][y]
            m = 1.0 if lake_id[x][y] >= 0 else (0.7 if hgt < cfg.sea_level else 1.0 - smooth_step(0, 1, hgt))
            u = x / W
            v = y / H
            m += smooth_noise(u*5, v*5, seed+5555) * 0.25
            moisture[x][y] = max(0.0, min(1.0, m))

    # Pass 4: biome assignment
    beach_boundary = cfg.sea_level + cfg.beach_width
    for y in range(H):
        for x in range(W):
            h = height[x][y]
            m = moisture[x][y]
            if lake_id[x][y] >= 0:         b = 8   # InlandLake
            elif h < cfg.sea_level - 0.04: b = 0   # DeepWater
            elif h < cfg.sea_level:        b = 1   # ShallowWater
            elif h < beach_boundary:       b = 2   # Beach
            elif h > 0.82:                 b = 6   # Peak
            elif h > 0.65:                 b = 5   # Rocky
            elif h < cfg.sea_level + 0.18 and m > 0.5: b = 7  # ValleyBasin
            elif m > 0.45 and h < 0.65:    b = 4   # Forest
            else:                          b = 3   # Grassland
            biome[x][y] = b

    # Pass 5: rivers
    flow = [[0.0]*H for _ in range(W)]
    accepted = 0
    for attempt in range(max(cfg.river_count*4, 12)):
        if accepted >= cfg.river_count: break
        best_x, best_y, best_h = -1, -1, 0.0
        for _ in range(60):
            px = rng.next_int(4, W-4)
            py = rng.next_int(4, H-4)
            hgt = height[px][py]
            if hgt > 0.55 and hgt > best_h and biome[px][py] not in (0, 1):
                best_h = hgt; best_x = px; best_y = py
        if best_x < 0: continue

        cx, cy = best_x, best_y
        reached_sea = False
        step = 0
        for step in range(W + H):
            flow[cx][cy] += 1.0
            if height[cx][cy] < cfg.sea_level:
                reached_sea = True
                break
            nx, ny = cx, cy
            lowest = height[cx][cy]
            for oy in (-1, 0, 1):
                for ox in (-1, 0, 1):
                    if ox == 0 and oy == 0: continue
                    tx, ty = cx+ox, cy+oy
                    if tx < 0 or ty < 0 or tx >= W or ty >= H: continue
                    ngh = height[tx][ty] + rng.next_float(0, 0.003)
                    if ngh < lowest:
                        lowest = ngh; nx = tx; ny = ty
            if nx == cx and ny == cy: break
            cx, cy = nx, ny
            if rng.chance(0.06):
                bx = cx + rng.next_int(-1, 2)
                by = cy + rng.next_int(-1, 2)
                if 0 <= bx < W and 0 <= by < H:
                    flow[bx][by] += 0.4
        if reached_sea and step > 20:
            accepted += 1

    max_flow = max(flow[x][y] for y in range(H) for x in range(W)) or 1.0
    for y in range(H):
        for x in range(W):
            river[x][y] = flow[x][y] / max_flow

    # Pass 6: forests grow as many distinct Gaussian clumps, like classic RTS
    # map generators. Cluster centers are repeatably sampled from valid land.
    def local_slope(x, y):
        hl = height[max(0,x-1)][y]
        hr = height[min(W-1,x+1)][y]
        hd = height[x][max(0,y-1)]
        hu = height[x][min(H-1,y+1)]
        return math.sqrt((hr-hl)**2 + (hu-hd)**2) * 0.5

    eligible_tree_cells = [(x, y) for y in range(H) for x in range(W)
                           if biome[x][y] in (3, 4, 7) and local_slope(x, y) < 0.45]
    occupied_tree_cells = set()
    cluster_std = max(1.0, cfg.tree_cluster_spread * min(W, H))
    cluster_target = min(max(0, cfg.tree_cluster_count),
                         max(1, len(eligible_tree_cells)//24)) if eligible_tree_cells else 0
    scatter_items = []
    for cluster_id in range(cluster_target):
        center = None
        for _ in range(250):
            cx = max(0, min(W-1, int(rng.normal(W*0.5, W*0.21))))
            cy = max(0, min(H-1, int(rng.normal(H*0.5, H*0.21))))
            if biome[cx][cy] in (3, 4, 7) and local_slope(cx, cy) < 0.45:
                separated = all(math.hypot(cx-p["cell_x"], cy-p["cell_y"]) >= cluster_std*2.2
                                for p in tree_clusters)
                if separated:
                    center = (cx, cy)
                    break
        if center is None:
            center = eligible_tree_cells[rng.next_int(0, len(eligible_tree_cells))]
        cx, cy = center
        requested = max(4, int(round(rng.normal(
            cfg.trees_per_cluster * cfg.tree_density,
            max(2.0, cfg.trees_per_cluster * 0.18)))))
        before, attempts = len(scatter_items), 0
        while len(scatter_items)-before < requested and attempts < requested*60:
            attempts += 1
            x = int(round(rng.normal(cx, cluster_std)))
            y = int(round(rng.normal(cy, cluster_std)))
            if x < 0 or y < 0 or x >= W or y >= H or (x, y) in occupied_tree_cells:
                continue
            if biome[x][y] not in (3, 4, 7) or local_slope(x, y) >= 0.45:
                continue
            occupied_tree_cells.add((x, y))
            scatter_items.append({"x": (x+0.5)/W, "y": (y+0.5)/H, "type": 0,
                                  "scale": rng.next_float(0.6, 1.3),
                                  "rotation": rng.next_float(0, 360), "cluster_id": cluster_id})
        tree_clusters.append({"id": cluster_id, "cell_x": cx, "cell_y": cy,
                              "x": (cx+0.5)/W, "y": (cy+0.5)/H,
                              "trees": len(scatter_items)-before})

    # Fill the remaining budget with sparse individual trees, rocks and details.
    total_budget = max(len(scatter_items), int(W * H * 0.018))
    placed = len(scatter_items)
    for _ in range(total_budget * 20):
        if placed >= total_budget: break
        x = rng.next_int(0, W)
        y = rng.next_int(0, H)
        b = biome[x][y]
        hgt = height[x][y]

        # slope estimate
        hl = height[max(0,x-1)][y]
        hr = height[min(W-1,x+1)][y]
        hd = height[x][max(0,y-1)]
        hu = height[x][min(H-1,y+1)]
        slope = math.sqrt(((hr-hl)**2 + (hu-hd)**2)) * 0.5

        if b == 4 and slope < 0.4:
            p, t = 0.18 * cfg.tree_density, 0
        elif b == 3 and slope < 0.3:
            p = 0.7 * cfg.grass_density if rng.chance(0.5) else 0.12 * cfg.tree_density
            t = 2 if rng.chance(0.5) else 0
        elif b in (5, 6):
            p, t = 0.85 * cfg.rock_density, 1
        elif b == 7:
            p = 0.6 * cfg.grass_density * 1.2
            t = 3 if rng.chance(0.4) else 2
        elif b == 2:
            p, t = 0.1, 1
        elif b in (0, 1, 8):
            continue
        else:
            continue

        if river[x][y] > 0.3 and t != 1 and rng.chance(0.4):
            t = 3  # reed

        if not rng.chance(p): continue
        scatter_items.append({
            "x": x / W, "y": y / H, "type": t,
            "scale": rng.next_float(0.6, 1.3),
            "rotation": rng.next_float(0, 360), "cluster_id": -1
        })
        placed += 1

    # Stats
    water = sum(1 for y in range(H) for x in range(W) if biome[x][y] in (0,1,8))
    lake_cells = sum(1 for y in range(H) for x in range(W) if lake_id[x][y] >= 0)
    beach = sum(1 for y in range(H) for x in range(W) if biome[x][y] == 2)
    grass = sum(1 for y in range(H) for x in range(W) if biome[x][y] == 3)
    forest = sum(1 for y in range(H) for x in range(W) if biome[x][y] == 4)
    rock = sum(1 for y in range(H) for x in range(W) if biome[x][y] == 5)
    peak = sum(1 for y in range(H) for x in range(W) if biome[x][y] == 6)
    river_cells = sum(1 for y in range(H) for x in range(W) if river[x][y] > 0.15)
    trees = sum(1 for s in scatter_items if s["type"] == 0)
    rocks_n = sum(1 for s in scatter_items if s["type"] == 1)
    details_n = len(scatter_items) - trees - rocks_n

    return {
        "seed": seed,
        "config": cfg,
        "height": height,
        "moisture": moisture,
        "biome": biome,
        "river": river,
        "lake_id": lake_id,
        "lake_level": lake_level,
        "lakes": lake_centers,
        "tree_clusters": tree_clusters,
        "scatter": scatter_items,
        "stats": {
            "water": water, "beach": beach, "grass": grass,
            "forest": forest, "rock": rock, "peak": peak,
            "lake_count": len(lake_centers), "lake_cells": lake_cells,
            "tree_cluster_count": len(tree_clusters),
            "clustered_tree_count": sum(c["trees"] for c in tree_clusters),
            "river_cells": river_cells, "scatter_count": len(scatter_items),
            "trees": trees, "rocks": rocks_n, "details": details_n,
            "max_height": max_h
        }
    }

# --------------- Output writers ---------------
def write_pgm(island, path):
    W, H = island["config"].width, island["config"].height
    with open(path, 'wb') as f:
        f.write(f"P5\n{W} {H}\n65535\n".encode())
        for y in range(H):
            for x in range(W):
                v = min(65535, max(0, int(island["height"][x][y] * 65535)))
                f.write(bytes([(v >> 8) & 0xFF, v & 0xFF]))

def write_biomes_csv(island, path):
    W, H = island["config"].width, island["config"].height
    with open(path, 'w') as f:
        f.write("x,y,height,moisture,biome_id,lake_id,lake_level,river\n")
        for y in range(H):
            for x in range(W):
                f.write(f"{x},{y},{island['height'][x][y]:.4f},{island['moisture'][x][y]:.4f},{island['biome'][x][y]},{island['lake_id'][x][y]},{island['lake_level'][x][y]:.4f},{island['river'][x][y]:.4f}\n")

def write_scatter_csv(island, path):
    with open(path, 'w') as f:
        f.write("x,y,type,scale,rotation,cluster_id\n")
        for s in island["scatter"]:
            f.write(f"{s['x']:.5f},{s['y']:.5f},{s['type']},{s['scale']:.3f},{s['rotation']:.1f},{s.get('cluster_id', -1)}\n")

def write_report(island, path):
    cfg = island["config"]
    st = island["stats"]
    report = {
        "seed": island["seed"],
        "width": cfg.width,
        "height": cfg.height,
        "island_radius": cfg.island_radius,
        "mountain_frequency": cfg.mountain_frequency,
        "valley_count": cfg.valley_count,
        "river_count": cfg.river_count,
        "lake_count_requested": cfg.lake_count,
        "lake_mean_radius": cfg.lake_mean_radius,
        "lake_radius_spread": cfg.lake_radius_spread,
        "lake_position_distribution": "truncated_normal",
        "lake_position_mean": [0.5, 0.5],
        "lake_position_sigma": [0.17, 0.17],
        "tree_cluster_count_requested": cfg.tree_cluster_count,
        "trees_per_cluster_mean": cfg.trees_per_cluster,
        "tree_cluster_spread": cfg.tree_cluster_spread,
        "tree_position_distribution": "normal_per_cluster",
        "sea_level": cfg.sea_level,
        "lakes": island["lakes"],
        "tree_clusters": island["tree_clusters"],
        "stats": {
            "total_cells": cfg.width * cfg.height,
            "water_cells": st["water"],
            "lake_count": st["lake_count"],
            "lake_cells": st["lake_cells"],
            "beach_cells": st["beach"],
            "grass_cells": st["grass"],
            "forest_cells": st["forest"],
            "rock_cells": st["rock"],
            "peak_cells": st["peak"],
            "river_cells": st["river_cells"],
            "scatter_count": st["scatter_count"],
            "tree_count": st["trees"],
            "tree_cluster_count": st["tree_cluster_count"],
            "clustered_tree_count": st["clustered_tree_count"],
            "rock_count": st["rocks"],
            "detail_count": st["details"],
            "max_height": st["max_height"]
        }
    }
    with open(path, 'w') as f:
        json.dump(report, f, indent=2)

def write_html_preview(island, path):
    W, H = island["config"].width, island["config"].height
    height_flat = []
    biome_flat = []
    river_flat = []
    for y in range(H):
        for x in range(W):
            height_flat.append(f"{island['height'][x][y]:.4f}")
            biome_flat.append(str(island['biome'][x][y]))
            river_flat.append(f"{island['river'][x][y]:.4f}")
    scatter_flat = []
    for s in island["scatter"]:
        scatter_flat.append(f"{s['x']:.4f},{s['y']:.4f},{s['type']},{s['scale']:.3f},{s['rotation']:.1f}")

    st = island["stats"]
    total = W * H
    sea = island["config"].sea_level

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Island Map Generator - Prototype</title>
<style>
body{{margin:0;background:#1a1a2e;color:#eee;font-family:system-ui,sans-serif;font-size:13px}}
#wrap{{display:grid;grid-template-columns:1fr 320px;gap:12px;padding:12px;height:100vh;box-sizing:border-box;background:#0a0a1a}}
#canvasWrap{{position:relative;background:#000;border:1px solid #333;display:flex;align-items:center;justify-content:center;overflow:hidden;border-radius:6px}}
canvas{{image-rendering:pixelated;max-width:100%;max-height:100%}}
#panel{{background:#16213e;padding:14px;border-radius:6px;overflow-y:auto}}
h2{{margin-top:0;color:#e94560;font-size:16px}}
h3{{color:#53a8d8;font-size:13px;margin:14px 0 6px}}
label{{display:block;margin:4px 0}}
button{{background:#e94560;color:#fff;border:0;padding:6px 14px;border-radius:4px;cursor:pointer;margin-top:8px}}
.stat-row{{display:flex;justify-content:space-between;border-bottom:1px dashed #2a3a5a;padding:2px 0}}
.badge{{display:inline-block;padding:1px 6px;border-radius:3px;font-size:11px;margin-right:4px}}
.b-water{{background:#1a3a6a}} .b-beach{{background:#dcd2a0;color:#333}}
.b-grass{{background:#78b45a}} .b-forest{{background:#287a3c}}
.b-rock{{background:#827473}} .b-peak{{background:#dde1eb;color:#333}}
#legend{{margin-top:10px;padding-top:8px;border-top:1px solid #2a3a5a}}
</style></head><body>
<div id="wrap">
<div id="canvasWrap"><canvas id="cw"></canvas></div>
<div id="panel">
<h2>Island Map Generator</h2>
<b>Seed:</b> {island["seed"]}<br>
<b>Size:</b> {W} x {H}<br>
<b>Max Height:</b> {st["max_height"]:.3f}<hr>
<h3>Controls</h3>
<label><input type="checkbox" id="toggleRiver" checked> Show Rivers</label>
<label><input type="checkbox" id="toggleScatter" checked> Show Scatter</label>
<button id="regen">Random Seed</button>
<h3>Biome Distribution</h3>
<div id="stats"></div>
</div>
</div>
<script>
const heightData = [{','.join(height_flat)}];
const biomeData = [{','.join(biome_flat)}];
const riverData = [{','.join(river_flat)}];
const scatterData = [{';'.join(scatter_flat)}];

const W = {W}, H = {H};
const heightMap = [];
const biomeMap = [];
const riverMap = [];
for (let y = 0; y < H; y++) {{
  heightMap[y] = []; biomeMap[y] = []; riverMap[y] = [];
  for (let x = 0; x < W; x++) {{
    const idx = y*W + x;
    heightMap[y][x] = heightData[idx];
    biomeMap[y][x] = biomeData[idx];
    riverMap[y][x] = riverData[idx];
  }}
}}
const scatter = scatterData.split(';').filter(s => s.length > 3).map(s => {{
  const p = s.split(',');
  return {{ x: parseFloat(p[0]), y: parseFloat(p[1]), t: parseInt(p[2]), s: parseFloat(p[3]), r: parseFloat(p[4]) }};
}});

const biomeColors = [
  [20,40,80],[40,90,150],[220,210,160],[120,180,90],
  [40,120,60],[130,120,115],[220,225,235],[70,130,80],[30,105,155]
];

const canvas = document.getElementById('cw');
const ctx = canvas.getContext('2d');
canvas.width = W; canvas.height = H;

function render() {{
  const showRivers = document.getElementById('toggleRiver').checked;
  const showScatter = document.getElementById('toggleScatter').checked;
  const img = ctx.createImageData(W, H);
  const d = img.data;
  for (let y = 0; y < H; y++) {{
    for (let x = 0; x < W; x++) {{
      const h = heightMap[y][x];
      const c = biomeColors[biomeMap[y][x]];
      const r = riverMap[y][x];
      const shade = 0.55 + h * 0.65;
      let R = c[0]*shade, G = c[1]*shade, B = c[2]*shade;
      if (showRivers && r > 0.15) {{
        const f = Math.min(1, r * 1.3);
        R = R*(1-f*0.6) + 30*f; G = G*(1-f*0.6) + 110*f; B = B*(1-f*0.6) + 200*f;
      }}
      const idx = (y*W + x) * 4;
      d[idx] = R|0; d[idx+1] = G|0; d[idx+2] = B|0; d[idx+3] = 255;
    }}
  }}
  ctx.putImageData(img, 0, 0);

  if (showScatter) {{
    for (const s of scatter) {{
      const px = s.x * W, py = s.y * H;
      ctx.save();
      ctx.translate(px, py);
      if (s.t === 0) {{
        ctx.fillStyle = '#2d5a2d';
        ctx.beginPath(); ctx.arc(0, 0, 2.2*s.s, 0, 7); ctx.fill();
      }} else if (s.t === 1) {{
        ctx.fillStyle = '#777';
        ctx.fillRect(-1.5*s.s, -1.5*s.s, 3*s.s, 3*s.s);
      }} else if (s.t === 2) {{
        ctx.strokeStyle = '#6a8'; ctx.lineWidth = 0.7;
        ctx.beginPath(); ctx.moveTo(0, 2); ctx.lineTo(0, -2); ctx.stroke();
      }} else if (s.t === 3) {{
        ctx.fillStyle = '#5a7a4a';
        ctx.beginPath(); ctx.arc(0, 0, 1.5, 0, 7); ctx.fill();
      }} else {{
        ctx.fillStyle = '#aaa'; ctx.fillRect(-1, -1, 2, 2);
      }}
      ctx.restore();
    }}
  }}
}}

function showStats() {{
  const total = W * H;
  const wPct = ({st['water']}*100/total).toFixed(1);
  const bPct = ({st['beach']}*100/total).toFixed(1);
  const gPct = ({st['grass']}*100/total).toFixed(1);
  const fPct = ({st['forest']}*100/total).toFixed(1);
  const rPct = ({st['rock']}*100/total).toFixed(1);
  const pPct = ({st['peak']}*100/total).toFixed(1);
  document.getElementById('stats').innerHTML =
    '<div class="stat-row"><span><span class="badge b-water"></span>Water</span><span>{st["water"]} (' + wPct + '%)</span></div>' +
    '<div class="stat-row"><span><span class="badge b-beach"></span>Beach</span><span>{st["beach"]} (' + bPct + '%)</span></div>' +
    '<div class="stat-row"><span><span class="badge b-grass"></span>Grassland</span><span>{st["grass"]} (' + gPct + '%)</span></div>' +
    '<div class="stat-row"><span><span class="badge b-forest"></span>Forest</span><span>{st["forest"]} (' + fPct + '%)</span></div>' +
    '<div class="stat-row"><span><span class="badge b-rock"></span>Rocky</span><span>{st["rock"]} (' + rPct + '%)</span></div>' +
    '<div class="stat-row"><span><span class="badge b-peak"></span>Peaks</span><span>{st["peak"]} (' + pPct + '%)</span></div>' +
    '<div class="stat-row"><span>Inland lakes</span><span>{st["lake_count"]} / {st["lake_cells"]} cells</span></div>' +
    '<div class="stat-row"><span>Tree clusters</span><span>{st["tree_cluster_count"]} / {st["clustered_tree_count"]} trees</span></div>' +
    '<div class="stat-row"><span><b>Rivers</b></span><span><b>{st["river_cells"]}</b> cells</span></div>' +
    '<hr style="border:0;border-top:1px dashed #2a3a5a;margin:8px 0">' +
    '<div class="stat-row"><span>Trees</span><span>{st["trees"]}</span></div>' +
    '<div class="stat-row"><span>Rocks</span><span>{st["rocks"]}</span></div>' +
    '<div class="stat-row"><span>Details</span><span>{st["details"]}</span></div>';
}}

render();
showStats();

document.getElementById('regen').onclick = function() {{
  alert('Re-run the generator with --seed <new_seed>');
}};
document.getElementById('toggleRiver').onchange = render;
document.getElementById('toggleScatter').onchange = render;
</script>
</body></html>"""
    with open(path, 'w') as f:
        f.write(html)

def write_houdini_obj(island, path):
    """Write the generated island as a real, material-grouped 3D OBJ scene.

    Coordinates are Houdini-friendly Y-up, with an explicit ocean surface,
    connected river ribbons, biome material groups and low-poly scatter meshes.
    The companion MTL is written beside the OBJ.
    """
    W, H = island["config"].width, island["config"].height
    sea_level = island["config"].sea_level
    height_scale = 105.0
    world_size = 1200.0
    cell = world_size / max(W, H)
    x_origin = -world_size * 0.5
    z_origin = -world_size * 0.5
    mtl_path = os.path.splitext(path)[0] + ".mtl"
    mtl_name = os.path.basename(mtl_path)

    materials = {
        "biome_deep_water": (0.035, 0.16, 0.25),
        "biome_shallow_water": (0.08, 0.39, 0.53),
        "biome_beach": (0.88, 0.76, 0.49),
        "biome_grassland": (0.38, 0.62, 0.23),
        "biome_forest": (0.12, 0.34, 0.20),
        "biome_rocky": (0.39, 0.39, 0.37),
        "biome_peak": (0.79, 0.81, 0.77),
        "biome_valley_basin": (0.28, 0.53, 0.32),
        "biome_lake_bed": (0.055, 0.22, 0.32),
        "lake_water": (0.055, 0.43, 0.66),
        "river_water": (0.045, 0.34, 0.61),
        "tree_bark": (0.25, 0.13, 0.065),
        "tree_leaves": (0.16, 0.39, 0.11),
        "tree_leaves_light": (0.34, 0.57, 0.16),
        "scatter_rock": (0.36, 0.39, 0.40),
        "detail_grass": (0.60, 0.72, 0.28),
        "detail_reed": (0.45, 0.51, 0.17),
    }
    biome_names = {
        0: "biome_deep_water", 1: "biome_shallow_water", 2: "biome_beach",
        3: "biome_grassland", 4: "biome_forest", 5: "biome_rocky",
        6: "biome_peak", 7: "biome_valley_basin", 8: "biome_lake_bed",
    }
    biome_groups = {
        0: "deep_water_bed", 1: "shallow_water_bed", 2: "beach",
        3: "grassland", 4: "forest", 5: "rocky_slope", 6: "mountain_peak",
        7: "valley_basin", 8: "lake_bed",
    }

    with open(mtl_path, "w", encoding="utf-8") as mtl:
        for name, color in materials.items():
            mtl.write(f"newmtl {name}\n")
            mtl.write("Ka 0.18 0.18 0.18\n")
            mtl.write("Kd %.4f %.4f %.4f\n" % color)
            mtl.write("Ks 0.04 0.04 0.04\nNs 12\nillum 2\n\n")

    vertex_count = 0
    with open(path, "w", encoding="utf-8", newline="\n") as obj:
        obj.write("# Deterministic cartoon island generated from seed %d\n" % island["seed"])
        obj.write("# Y-up; import with File > Import > Geometry > Wavefront OBJ in Houdini.\n")
        obj.write("mtllib %s\n" % mtl_name)

        def vertex(x, y, z):
            nonlocal vertex_count
            vertex_count += 1
            obj.write("v %.5f %.5f %.5f\n" % (x, y, z))
            return vertex_count

        def face(*indices):
            obj.write("f " + " ".join(str(index) for index in indices) + "\n")

        # Continuous height mesh. Faces are regrouped by cell biome so Houdini
        # imports useful primitive groups alongside the explicit MTL shading.
        obj.write("\no Island_Terrain\n")
        grid = []
        for y in range(H + 1):
            row = []
            sy = min(y, H - 1)
            for x in range(W + 1):
                sx = min(x, W - 1)
                row.append(vertex(x_origin + x * cell,
                                  island["height"][sx][sy] * height_scale,
                                  z_origin + y * cell))
            grid.append(row)
        for biome_id in range(9):
            obj.write("g biome_%s\n" % biome_groups[biome_id])
            obj.write("usemtl %s\n" % biome_names[biome_id])
            for y in range(H):
                for x in range(W):
                    if island["biome"][x][y] != biome_id:
                        continue
                    a, b = grid[y][x], grid[y][x + 1]
                    c, d = grid[y + 1][x + 1], grid[y + 1][x]
                    # Winding points normals upward in Houdini's Y-up space.
                    face(a, d, b)
                    face(b, d, c)

        # A separate ocean surface makes the sea level visually coherent while
        # retaining the complete underwater height field for editing.
        obj.write("\no Ocean_Surface\ng ocean_surface\nusemtl biome_deep_water\n")
        water_y = sea_level * height_scale
        water_corners = [
            vertex(x_origin, water_y, z_origin),
            vertex(x_origin + world_size, water_y, z_origin),
            vertex(x_origin + world_size, water_y, z_origin + world_size),
            vertex(x_origin, water_y, z_origin + world_size),
        ]
        face(water_corners[0], water_corners[3], water_corners[2], water_corners[1])

        # Inland lakes have their own flat water surface above the lowered bed.
        obj.write("\no Inland_Lake_Water\ng lake_surfaces\nusemtl lake_water\n")
        for y in range(H):
            for x in range(W):
                lake_index = island["lake_id"][x][y]
                if lake_index < 0:
                    continue
                obj.write("g lake_surfaces lake_%02d\n" % lake_index)
                ywater = island["lake_level"][x][y]
                a = vertex(x_origin+x*cell, ywater, z_origin+y*cell)
                b = vertex(x_origin+(x+1)*cell, ywater, z_origin+y*cell)
                c = vertex(x_origin+(x+1)*cell, ywater, z_origin+(y+1)*cell)
                d = vertex(x_origin+x*cell, ywater, z_origin+(y+1)*cell)
                face(a, d, b)
                face(b, d, c)

        # Turn adjacent above-threshold river cells into continuous polygon
        # ribbons rather than painting the map preview into a flat texture.
        river_cells = set()
        for y in range(H):
            for x in range(W):
                if island["river"][x][y] > 0.15 and island["biome"][x][y] not in (0, 1, 8):
                    river_cells.add((x, y))
        obj.write("\no River_Network\ng rivers\nusemtl river_water\n")
        neighbors = ((1, 0), (0, 1), (1, 1), (-1, 1))
        for x, y in sorted(river_cells, key=lambda item: (item[1], item[0])):
            for dx, dy in neighbors:
                other = (x + dx, y + dy)
                if other not in river_cells:
                    continue
                x1, z1 = x_origin + (x + 0.5) * cell, z_origin + (y + 0.5) * cell
                x2, z2 = x_origin + (other[0] + 0.5) * cell, z_origin + (other[1] + 0.5) * cell
                length = math.hypot(x2 - x1, z2 - z1) or 1.0
                width = cell * (0.12 + 0.22 * min(1.0, island["river"][x][y]))
                px, pz = -(z2 - z1) / length * width, (x2 - x1) / length * width
                y1 = island["height"][x][y] * height_scale + 0.22
                y2 = island["height"][other[0]][other[1]] * height_scale + 0.22
                v1 = vertex(x1 + px, y1, z1 + pz)
                v2 = vertex(x1 - px, y1, z1 - pz)
                v3 = vertex(x2 - px, y2, z2 - pz)
                v4 = vertex(x2 + px, y2, z2 + pz)
                face(v1, v2, v3, v4)

        def transformed_point(cx, cy, cz, lx, ly, lz, cosine, sine):
            return (cx + lx * cosine - lz * sine, cy + ly,
                    cz + lx * sine + lz * cosine)

        def cone(cx, cy, cz, radius, height, sides, material, cosine, sine, apex_offset=0.0):
            obj.write("usemtl %s\n" % material)
            base = []
            for i in range(sides):
                angle = (2.0 * math.pi * i / sides) + apex_offset
                point = transformed_point(cx, cy, cz, math.cos(angle) * radius, 0,
                                          math.sin(angle) * radius, cosine, sine)
                base.append(vertex(*point))
            apex = vertex(cx, cy + height, cz)
            for i in range(sides):
                face(base[i], base[(i + 1) % sides], apex)

        # Low-poly but real geometry for every deterministic scatter entry.
        scatter = island["scatter"]
        scatter_groups = {0: ("Trees", "trees"), 1: ("Rocks", "rocks"),
                          2: ("Grass_Details", "grass_details"), 3: ("Reeds", "reeds")}
        for kind, (object_name, group_name) in scatter_groups.items():
            obj.write("\no Scatter_%s\ng %s\n" % (object_name, group_name))
            for item in (entry for entry in scatter if entry["type"] == kind):
                if kind == 0:
                    cluster_id = item.get("cluster_id", -1)
                    tree_group = "tree_cluster_%02d" % cluster_id if cluster_id >= 0 else "single_trees"
                    obj.write("g trees %s\n" % tree_group)
                px = min(W - 1, max(0, int(item["x"] * W)))
                py = min(H - 1, max(0, int(item["y"] * H)))
                cx = x_origin + item["x"] * world_size
                cz = z_origin + item["y"] * world_size
                cy = island["height"][px][py] * height_scale + 0.2
                size = cell * item["scale"]
                angle = math.radians(item["rotation"])
                cosine, sine = math.cos(angle), math.sin(angle)

                if kind == 0:  # Trunk plus three layered polygon crowns.
                    obj.write("usemtl tree_bark\n")
                    sides = 5
                    trunk_r, trunk_h = size * 0.09, size * 0.72
                    lower, upper = [], []
                    for i in range(sides):
                        a = 2.0 * math.pi * i / sides
                        lower.append(vertex(*transformed_point(cx, cy, cz, math.cos(a)*trunk_r, 0, math.sin(a)*trunk_r, cosine, sine)))
                        upper.append(vertex(*transformed_point(cx, cy, cz, math.cos(a)*trunk_r*0.68, trunk_h, math.sin(a)*trunk_r*0.68, cosine, sine)))
                    for i in range(sides):
                        face(lower[i], lower[(i+1)%sides], upper[(i+1)%sides], upper[i])
                    obj.write("usemtl tree_leaves\n")
                    cone(cx, cy + trunk_h*0.72, cz, size*0.39, size*0.76, 7, "tree_leaves", cosine, sine, angle*0.1)
                    cone(cx, cy + trunk_h + size*0.26, cz, size*0.31, size*0.68, 7, "tree_leaves_light", cosine, sine, angle*0.1)
                    cone(cx, cy + trunk_h + size*0.65, cz, size*0.22, size*0.61, 7, "tree_leaves", cosine, sine, angle*0.1)
                elif kind == 1:  # Faceted irregular boulder.
                    obj.write("usemtl scatter_rock\n")
                    pts = []
                    ring = [(0.0, 0.72, 0.0)]
                    for i in range(6):
                        a = 2.0 * math.pi * i / 6.0 + angle
                        variation = 0.78 + 0.18 * ((i * 37 + px * 13 + py * 7) % 5) / 4.0
                        ring.append((math.cos(a)*size*0.45*variation,
                                     size*(0.12 + 0.12*((i*3+px)%4)/3.0),
                                     math.sin(a)*size*0.45*variation))
                    ring.append((0.0, size*0.82, 0.0))
                    for lx, ly, lz in ring:
                        pts.append(vertex(*transformed_point(cx, cy, cz, lx, ly, lz, cosine, sine)))
                    for i in range(6):
                        face(pts[0], pts[1+i], pts[1+(i+1)%6])
                        face(pts[7], pts[1+(i+1)%6], pts[1+i])
                else:  # Crossed triangular grass blades/reeds.
                    obj.write("usemtl %s\n" % ("detail_reed" if kind == 3 else "detail_grass"))
                    blade_h = size * (0.8 if kind == 3 else 0.56)
                    blade_w = size * 0.13
                    for blade in range(3):
                        a = angle + blade * (math.pi / 3.0)
                        ux, uz = math.cos(a) * blade_w, math.sin(a) * blade_w
                        base_l = transformed_point(cx, cy, cz, -ux, 0, -uz, cosine, sine)
                        base_r = transformed_point(cx, cy, cz, ux, 0, uz, cosine, sine)
                        tip = transformed_point(cx, cy, cz, ux*0.3, blade_h*(0.84+0.08*blade), uz*0.3, cosine, sine)
                        face(vertex(*base_l), vertex(*base_r), vertex(*tip))

    return {"obj": path, "mtl": mtl_path, "vertices": vertex_count,
            "river_segments": sum(1 for x, y in river_cells for dx, dy in neighbors if (x+dx, y+dy) in river_cells)}

def write_houdini_import_guide(island, out_dir):
    guide_path = os.path.join(out_dir, "Houdini_Import.md")
    hip_builder_path = os.path.join(out_dir, "build_houdini_hip.py")
    cfg = island["config"]
    out_literal = os.path.abspath(out_dir).replace("\\", "/")
    with open(hip_builder_path, "w", encoding="utf-8") as script:
        script.write(f'''"""Run this file inside Houdini to create and save a native .hip scene."""
import os
import hou

OUTPUT_DIR = r"{out_literal}"
OBJ_PATH = os.path.join(OUTPUT_DIR, "island_houdini_scene.obj")
HIP_PATH = os.path.join(OUTPUT_DIR, "Island_{island['seed']}.hip")

if not os.path.isfile(OBJ_PATH):
    raise RuntimeError("Island OBJ not found: " + OBJ_PATH)

obj = hou.node("/obj")
island_geo = obj.createNode("geo", "Island_Scene")
for child in island_geo.children():
    child.destroy()
file_sop = island_geo.createNode("file", "Island_Geometry")
file_sop.parm("file").set(OBJ_PATH)
file_sop.setDisplayFlag(True)
file_sop.setRenderFlag(True)
file_sop.setSelected(True, clear_all_selected=True)
island_geo.layoutChildren()

camera = obj.createNode("cam", "Island_Camera")
camera.parmTuple("t").set((0.0, 1200.0, -2000.0))
camera.parmTuple("r").set((-31.0, 0.0, 0.0))
camera.parm("focal").set(50.0)
obj.layoutChildren()

hou.hipFile.save(HIP_PATH)
print("Saved native Houdini island scene: " + HIP_PATH)
''')
    with open(guide_path, "w", encoding="utf-8") as guide:
        guide.write(f"""# Houdini Island Scene

`island_houdini_scene.obj` is the editable 3D scene geometry, not a map screenshot. Open it in Houdini via **File > Import > Geometry > Wavefront OBJ** (or drag the OBJ into the viewport). Keep the companion `.mtl` beside it so its biome materials resolve. It contains terrain with nine biome groups, Gaussian-distributed inland lake surfaces, connected river ribbons, and low-poly tree/rock/grass/reed geometry. Each grove has its own `tree_cluster_XX` primitive group. Coordinates are Y-up.

To build and save a native Houdini project when Houdini is installed, run `build_houdini_hip.py` from Houdini's Python Source Editor. It imports the OBJ, creates an overview camera, and saves `Island_{island['seed']}.hip` in this folder.

The terrain uses a {cfg.width}×{cfg.height} deterministic height field, seed `{island['seed']}`. Lake and grove controls are recorded in `island_report.json`; per-cell lake IDs and per-tree grove IDs are in the CSV files. The HTML file is an optional map preview, not the 3D scene deliverable.
""")
    return guide_path, hip_builder_path

# --------------- CLI ---------------
def main():
    import argparse
    parser = argparse.ArgumentParser(description="Island Map Generator")
    parser.add_argument("--seed", type=int, default=20261002)
    parser.add_argument("--width", type=int, default=256)
    parser.add_argument("--height", type=int, default=256)
    parser.add_argument("--island-radius", type=float, default=0.42)
    parser.add_argument("--mountains", type=float, default=0.9)
    parser.add_argument("--valleys", type=int, default=3)
    parser.add_argument("--rivers", type=int, default=5)
    parser.add_argument("--lakes", type=int, default=8, help="requested inland lake count")
    parser.add_argument("--lake-mean-radius", type=float, default=0.045)
    parser.add_argument("--lake-radius-spread", type=float, default=0.012)
    parser.add_argument("--tree-density", type=float, default=0.6)
    parser.add_argument("--tree-clusters", type=int, default=18)
    parser.add_argument("--trees-per-cluster", type=int, default=42)
    parser.add_argument("--tree-cluster-spread", type=float, default=0.012)
    parser.add_argument("--html-preview", action="store_true",
                        help="also write the optional browser map preview")
    args = parser.parse_args()

    cfg = IslandConfig(
        width=args.width, height=args.height,
        island_radius=args.island_radius,
        mountain_frequency=args.mountains,
        valley_count=args.valleys,
        river_count=args.rivers,
        lake_count=args.lakes,
        lake_mean_radius=args.lake_mean_radius,
        lake_radius_spread=args.lake_radius_spread,
        tree_density=args.tree_density,
        tree_cluster_count=args.tree_clusters,
        trees_per_cluster=args.trees_per_cluster,
        tree_cluster_spread=args.tree_cluster_spread
    )

    print(f"[IslandGenerator] seed={args.seed} {args.width}x{args.height} radius={args.island_radius} mountains={args.mountains} valleys={args.valleys} rivers={args.rivers}")

    t0 = time.time()
    island = generate(args.seed, cfg)
    elapsed = (time.time() - t0) * 1000

    st = island["stats"]
    print(f"[IslandGenerator] Done in {elapsed:.0f}ms")
    print(f"  Water: {st['water']} | Beach: {st['beach']} | Grass: {st['grass']} | Forest: {st['forest']} | Rocky: {st['rock']} | Peaks: {st['peak']}")
    print(f"  Lakes: {st['lake_count']} ({st['lake_cells']} cells) | Rivers: {st['river_cells']} cells")
    print(f"  Tree clusters: {st['tree_cluster_count']} ({st['clustered_tree_count']} clustered trees)")
    print(f"  Scatter: {st['scatter_count']} items (Trees:{st['trees']}, Rocks:{st['rocks']}, Detail:{st['details']})")

    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "island_out")
    os.makedirs(out_dir, exist_ok=True)

    write_pgm(island, os.path.join(out_dir, "island_height.pgm"))
    write_biomes_csv(island, os.path.join(out_dir, "island_biomes.csv"))
    write_scatter_csv(island, os.path.join(out_dir, "island_scatter.csv"))
    write_report(island, os.path.join(out_dir, "island_report.json"))
    scene_path = os.path.join(out_dir, "island_houdini_scene.obj")
    scene = write_houdini_obj(island, scene_path)
    guide_path, hip_builder_path = write_houdini_import_guide(island, out_dir)
    if args.html_preview:
        write_html_preview(island, os.path.join(out_dir, "island_preview.html"))

    print(f"  Houdini scene: {scene['obj']} ({scene['vertices']} vertices, {scene['river_segments']} river segments)")
    print(f"  Companion materials: {scene['mtl']}")
    print(f"  Houdini project builder: {hip_builder_path}")
    print(f"  Import guide: {guide_path}")
    print(f"[IslandGenerator] Output: {out_dir}")
    return out_dir

if __name__ == "__main__":
    main()
