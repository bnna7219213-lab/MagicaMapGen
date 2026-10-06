"""Grid exports: per-cell CSV and 16-bit PGM height field.

The CSV is the diff-friendly companion to map.json -- same data, one row per
cell, so a reviewer can open it in a spreadsheet or diff two seeds line by
line. The PGM is a standard greyscale height field importable by Houdini,
Gaea, World Machine or any engine terrain tool.
"""

from __future__ import annotations

from typing import Dict

from ..schema import ResolvedRequest
from ..world import World


def write_biomes_csv(world: World, req: ResolvedRequest, path: str) -> str:
    theme = req.theme
    key_by_id = {b.id: b.key for b in theme.biomes}
    # Attribution now comes from the priority-resolved owner grid, so the CSV and
    # map.json always agree about which region a cell belongs to.
    owner = getattr(world, "region_owner", None)
    use_owner = bool(owner) and len(owner) == world.width and len(owner[0]) == world.height
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("x,y,height,moisture,slope,biome_id,biome_key,lake_id,"
                "lake_level,river,region\n")
        for y in range(world.height):
            for x in range(world.width):
                lid = world.lake_id[x][y]
                if use_owner:
                    region = owner[x][y]
                else:
                    region = ""
                    for rid, mask in world.region_masks.items():
                        if mask[x][y]:
                            region = rid
                            break
                f.write("%d,%d,%.4f,%.4f,%.4f,%d,%s,%d,%.4f,%.4f,%s\n" % (
                    x, y,
                    world.height_map[x][y], world.moisture[x][y], world.slope[x][y],
                    world.biome[x][y], key_by_id.get(world.biome[x][y], "?"),
                    lid, world.lake_level[x][y], world.river[x][y], region))
    return path


def write_scatter_csv(world: World, path: str) -> str:
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("x,y,u,v,height,category,type,scale,rotation,region,cluster_id\n")
        for inst in world.instances:
            f.write("%d,%d,%.6f,%.6f,%.4f,%s,%s,%.4f,%.2f,%s,%d\n" % (
                inst["x"], inst["y"], inst["u"], inst["v"], inst["z"],
                inst["category"], inst["type"], inst["scale"], inst["rotation"],
                inst.get("region") or "", inst.get("cluster_id", -1)))
    return path


def write_height_pgm(world: World, path: str) -> str:
    """16-bit little-endian PGM, row-major (y outer, x inner)."""
    W, H = world.width, world.height
    with open(path, "wb") as f:
        f.write(f"P5\n{W} {H}\n65535\n".encode("ascii"))
        for y in range(H):
            row = bytearray()
            for x in range(W):
                v = int(max(0.0, min(1.0, world.height_map[x][y])) * 65535.0)
                row += v.to_bytes(2, "little")
            f.write(row)
    return path


def write_all(world: World, req: ResolvedRequest, out_dir: str,
              stem: str) -> Dict[str, str]:
    import os
    return {
        "biomes_csv": write_biomes_csv(
            world, req, os.path.join(out_dir, f"{stem}_biomes.csv")),
        "scatter_csv": write_scatter_csv(
            world, os.path.join(out_dir, f"{stem}_scatter.csv")),
        "height_pgm": write_height_pgm(
            world, os.path.join(out_dir, f"{stem}_height.pgm")),
    }
