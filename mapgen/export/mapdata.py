"""map.json -- the primary deliverable: engine-consumable map data.

This is the "prototype UI file" of the pipeline: the document a game developer
loads to build a playable level from, analogous to a .tmf/.map in an RTS.

Design rules:

* **Self-describing.** The biome legend, coordinate convention and RLE decoding
  order are all in the file, so no out-of-band knowledge is needed to load it.
* **Reproducible.** ``request`` is the resolved configuration round-tripped
  verbatim; theme + seed + request regenerate this exact map.
* **No timestamp.** A timestamp would make the file differ on every run and
  destroy byte-level reproducibility, which is the whole point of a seed.
* **Compact but not opaque.** Grids are run-length encoded; instances keep
  readable keys.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Sequence, Tuple

from ..schema import SCHEMA_VERSION, ResolvedRequest
from ..world import World

# Single source of truth lives in schema.SCHEMA_VERSION; report.json and
# map.json must never drift apart.


def _rle(values: Sequence[int]) -> List[List[int]]:
    """Run-length encode a flat sequence as [[value, run_length], ...]."""
    out: List[List[int]] = []
    for v in values:
        if out and out[-1][0] == v:
            out[-1][1] += 1
        else:
            out.append([v, 1])
    return out


def _flatten_row_major(grid: List[List[Any]], W: int, H: int) -> List[Any]:
    """Grids are stored [x][y]; maps are consumed row-major (y outer, x inner)."""
    return [grid[x][y] for y in range(H) for x in range(W)]


def build_map_data(world: World, req: ResolvedRequest,
                   request_dict: Dict[str, Any],
                   heightmap_filename: str | None = None) -> Dict[str, Any]:
    """Build the map.json document.

    ``heightmap_filename`` is the relative name of the 16-bit PGM sidecar that
    sits next to this map.json (``{stem}_height.pgm``). When provided, it is
    recorded in ``grid.heightmap_raw_url`` so engines can load lossless terrain
    instead of the 8-bit height RLE. Callers that write map.json should always
    co-export that PGM and pass its basename here.
    """
    from ..config import request_to_dict  # local import: avoid cycle at load

    theme = req.theme
    tp = req.terrain
    W, H = world.width, world.height

    legend = [
        {
            "id": b.id,
            "key": b.key,
            "name": b.name,
            "color_hex": "#%02x%02x%02x" % tuple(
                max(0, min(255, int(round(c * 255)))) for c in b.color),
            "is_water": b.is_water,
            "walkable": b.walkable,
            "buildable": b.buildable,
            "movement_cost": b.movement_cost,
        }
        for b in sorted(theme.biomes, key=lambda x: x.id)
    ]

    biome_flat = _flatten_row_major(world.biome, W, H)
    # Quantise height to 8 bits: 120 m / 256 ~= 0.47 m per step, well inside
    # what a prototype level needs, and it keeps the file small. Engines that
    # care about that step should load grid.heightmap_raw_url instead (16-bit).
    height_q = [max(0, min(255, int(round(h * 255.0))))
                for h in _flatten_row_major(world.height_map, W, H)]
    river_q = [max(0, min(255, int(round(r * 255.0))))
               for r in _flatten_row_major(world.river, W, H)]
    moisture_q = [max(0, min(255, int(round(m * 255.0))))
                  for m in _flatten_row_major(world.moisture, W, H)]

    instances = []
    # Water depth lets an engine decide "is this tree standing in water" without
    # re-deriving sea/lake levels and re-reading the height RLE. biome/slope save
    # the consumer a second grid lookup for the same cell.
    biome_key_by_id = {b.id: b.key for b in theme.biomes}
    water_ids = {b.id for b in theme.biomes if b.is_water}
    for i, inst in enumerate(world.instances):
        ix, iy = inst["x"], inst["y"]
        h_norm = world.height_map[ix][iy]
        if world.lake_id[ix][iy] >= 0:
            surface = world.lake_level[ix][iy]
        elif world.biome[ix][iy] in water_ids:
            surface = tp.sea_level
        else:
            surface = h_norm
        rec = {
            "id": i,
            "cat": inst["category"],
            "type": inst["type"],
            "x": ix,
            "y": iy,
            "world": [
                round((ix + 0.5) * tp.tile_size_meters, 3),
                round(h_norm * tp.height_scale_meters, 3),
                round((iy + 0.5) * tp.tile_size_meters, 3),
            ],
            "rot": round(inst["rotation"], 2),
            "scale": round(inst["scale"], 4),
            "biome": biome_key_by_id[world.biome[ix][iy]],
            "slope": round(world.slope[ix][iy], 4),
            "water_depth": round(max(0.0, (surface - h_norm) * tp.height_scale_meters), 3),
        }
        if inst.get("region"):
            rec["region"] = inst["region"]
        if inst.get("cluster_id", -1) >= 0:
            rec["cluster"] = inst["cluster_id"]
        instances.append(rec)

    rivers = []
    for r in world.rivers:
        rivers.append({
            "id": r["id"],
            "source": r["source"],
            "terminus": r.get("terminus"),
            "length": r["length"],
            "reached_water": r["reached_water"],
            "path": [[p[0], p[1]] for p in r["path"]],
        })

    lakes = [{
        "id": lk["id"],
        "center_norm": [round(lk["x"], 6), round(lk["y"], 6)],
        "radius_norm": round(lk["radius"], 6),
        "level": round(lk["level"], 6),
        "level_meters": round(lk["level"] * tp.height_scale_meters, 3),
        "cells": lk["cells"],
        "frozen": lk.get("frozen", False),
    } for lk in world.lakes]

    owner_counts = dict(world.stats.get("regions", {}) or {})
    raw_counts = dict(world.stats.get("regions_raw_cells", {}) or {})
    regions = [{
        "id": r.id,
        "shape": r.shape,
        "priority": int(getattr(r, "priority", 0) or 0),
        "bounds": dict(r.bounds),
        # Cells this region owns after priority resolution, plus its raw extent. The
        # two differ only when regions overlap, and reporting both makes that visible
        # instead of silently double-counting.
        "cells": owner_counts.get(r.id, 0),
        "cells_raw": raw_counts.get(r.id, owner_counts.get(r.id, 0)),
        "overlaps": bool(raw_counts.get(r.id, 0) - owner_counts.get(r.id, 0)),
        "overrides": {k: dict(v) for k, v in r.overrides.items()},
    } for r in req.request.regions]

    categories = []
    for s in world.category_summary:
        categories.append({
            "category": s["category"],
            "display_name": s["display_name"],
            "object_type": s["object_type"],
            "distribution": s["distribution"],
            "params": s["params"],
            "requested": s["requested"],
            "placed": s["placed"],
            "legal_cells": s["legal_cells"],
            "region": s["region"] or None,
            "clusters": [
                {"cluster_id": c["cluster_id"],
                 "center": [round(c["x"], 2), round(c["y"], 2)],
                 "count": c["count"]}
                for c in (s.get("clusters") or [])
            ] or None,
        })

    map_request = request_to_dict(req.request)
    # Output selection controls packaging, not map content. Omitting it keeps
    # the primary artifact byte-identical when callers request different
    # export format sets.
    map_request.pop("formats", None)

    grid: Dict[str, Any] = {
            "width": W,
            "height": H,
            "axis": "y_up",
            "tile_size_meters": tp.tile_size_meters,
            "height_scale_meters": tp.height_scale_meters,
            "cell_to_world": ("world_x = (x + 0.5) * tile_size_meters; "
                              "world_y = height_norm * height_scale_meters; "
                              "world_z = (y + 0.5) * tile_size_meters"),
            "scan_order": "row-major, y outer then x (index = y * width + x)",
            "encoding": {
                "biome": "rle_pairs_[value,run]",
                "height": "rle_pairs_[quantised_0_255,run]",
                "river": "rle_pairs_[quantised_0_255,run]",
                "moisture": "rle_pairs_[quantised_0_255,run]",
            },
            "biome_legend": legend,
            "biome_rle": _rle(biome_flat),
            "height_rle": _rle(height_q),
            "river_rle": _rle(river_q),
            "moisture_rle": _rle(moisture_q),
        }
    if heightmap_filename:
        # Relative to the map.json itself; never an absolute path, so the
        # artifact stays byte-identical across machines.
        grid["heightmap_raw_url"] = heightmap_filename

    return {
        "schema_version": SCHEMA_VERSION,
        "generator_version": _generator_version(),
        "label": req.request.label or f"{theme.id}_{req.seed}",
        "seed": req.seed,
        # Structured unit declarations. Previously the only hints were a prose
        # cell_to_world string and the OBJ exporter's private assumptions, so a
        # consumer had to guess whether `rot` was degrees and what `scale` was
        # relative to. Every numeric field's unit is now stated in the file.
        "units": {
            "schema": "mapgen artifact schema v%d" % SCHEMA_VERSION,
            "length": "meter",
            "angle": "degree",
            "scale": "uniform multiplier on the object type's authored size",
            "world_up": "+Y",
            "world_forward": "+Z",
            "grid_axis": "x right, z forward; stored index = y_cell * width + x_cell",
            "cell_to_world_xz": "world_x = (x + 0.5) * grid.tile_size_meters; "
                                "world_z = (y + 0.5) * grid.tile_size_meters",
            "cell_to_world_y": "world_y = height_norm * grid.height_scale_meters",
            "height_quantisation": "height_rle value v in [0,255] -> height_norm = v / 255",
            "river_quantisation": "river_rle value v in [0,255] -> normalised flow = v / 255",
            "moisture_quantisation": "moisture_rle value v in [0,255] -> moisture_norm = v / 255",
            "instance_rot": "rotation about +Y, degrees, clockwise viewed from +Y",
            "instance_slope": "unitless gradient magnitude (dimensionless height per cell)",
            "instance_water_depth": "meters; 0 on land, sea_level or lake_level minus terrain height",
            "biome_legend": "grid.biome_legend[i].id indexes grid.biome_rle values",
        },
        "theme": {
            "id": theme.id,
            "display_name": theme.display_name,
            "description": theme.description,
            "forbidden_biomes": list(theme.forbidden_biomes),
        },
        "contract": world.contract,
        "request": map_request,
        "resolved": {
            "terrain": {k: v for k, v in vars(tp).items() if k != "extra"},
            "feature_distributions": {
                k: {"kind": v.kind, "params": v.params}
                for k, v in req.feature_distributions.items()
            },
            "categories": [
                {"id": c.id, "display_name": c.display_name, "count": c.count,
                 "distribution": c.distribution.kind,
                 "params": c.distribution.params,
                 "allowed_biomes": list(c.allowed_biomes),
                 "max_slope": c.max_slope}
                for c in req.categories
            ],
        },
        "grid": grid,
        "features": {
            "sea_level": tp.sea_level,
            "sea_level_meters": round(tp.sea_level * tp.height_scale_meters, 3),
            "lakes": lakes,
            "rivers": rivers,
        },
        "regions": regions,
        "categories": categories,
        "instances": instances,
        "stats": world.stats,
    }


def _generator_version() -> str:
    from .. import GENERATOR_VERSION
    return GENERATOR_VERSION


def write_map_json(world: World, req: ResolvedRequest, path: str,
                   request_dict: Dict[str, Any] | None = None,
                   heightmap_filename: str | None = None) -> str:
    data = build_map_data(world, req, request_dict or {},
                          heightmap_filename=heightmap_filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=False)
        f.write("\n")
    return path
