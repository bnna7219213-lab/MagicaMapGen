"""Houdini / DCC export: material-grouped low-poly OBJ + companion MTL.

Structure (stable, so a DCC pipeline can address parts by name):

    o Island_Terrain     -- continuous height mesh, faces regrouped per biome
    o Ocean_Surface      -- single quad at sea level
    o Inland_Lake_Water  -- per-lake flat surfaces, grouped lake_NN
    o River_Network      -- ribbon quads between adjacent river cells
    o Scatter_<Category> -- one object per category, groves as primitive groups

Coordinates are Y-up. Every colour comes from the theme (biome palette +
``theme.materials``); nothing is hardcoded here, so swapping the theme swaps
the whole look.

Known limitation, stated plainly: the OBJ carries **no normals and no UVs**.
Houdini computes normals on import, but the MTL entries are flat colours --
there is no UV channel to hang a texture on. Unwrap in the DCC if texturing is
needed.
"""

from __future__ import annotations

import math
import os
from typing import Dict, List, Tuple

from ..schema import ResolvedRequest
from ..world import World

WORLD_SIZE = 1200.0


def _mtl_path(obj_path: str) -> str:
    return os.path.splitext(obj_path)[0] + ".mtl"


def collect_materials(req: ResolvedRequest) -> Dict[str, Tuple[float, float, float]]:
    theme = req.theme
    mats: Dict[str, Tuple[float, float, float]] = {}
    for b in theme.biomes:
        mats[b.material or b.key] = b.color
    mats.update(theme.materials)
    for c in req.categories:
        if c.material and c.material not in mats:
            # A category named a material the theme does not define. Fall back
            # to a neutral grey rather than silently dropping the geometry, and
            # let the caller surface it.
            mats[c.material] = (0.5, 0.5, 0.5)
    return mats


def missing_materials(req: ResolvedRequest) -> List[str]:
    theme = req.theme
    known = set(theme.materials) | {(b.material or b.key) for b in theme.biomes}
    return sorted({c.material for c in req.categories
                   if c.material and c.material not in known})


def write_obj(world: World, req: ResolvedRequest, path: str) -> Dict[str, object]:
    theme = req.theme
    tp = req.terrain
    W, H = world.width, world.height
    height_scale = tp.height_scale_meters
    cell = WORLD_SIZE / max(W, H)
    x0 = -WORLD_SIZE * 0.5
    z0 = -WORLD_SIZE * 0.5

    mats = collect_materials(req)
    mtl_path = _mtl_path(path)
    with open(mtl_path, "w", encoding="utf-8", newline="\n") as mtl:
        mtl.write(f"# Materials for theme {theme.id!r} ({theme.display_name})\n")
        mtl.write(f"# Generated deterministically from seed {req.seed}. No textures;\n")
        mtl.write("# the OBJ carries no UV channel, so these are flat colours.\n\n")
        for name in sorted(mats):
            r, g, b = mats[name]
            mtl.write(f"newmtl {name}\nKa 0.18 0.18 0.18\n")
            mtl.write("Kd %.4f %.4f %.4f\n" % (r, g, b))
            mtl.write("Ks 0.04 0.04 0.04\nNs 12\nillum 2\n\n")

    key_by_id = {b.id: (b.material or b.key) for b in theme.biomes}
    group_by_id = {b.id: b.key for b in theme.biomes}
    water_ids = {b.id for b in theme.biomes if b.is_water}
    lake_key = theme.lake_biome
    lake_mat = theme.materials.get("lake_water",
                                   theme.biome(lake_key).color if lake_key else (0.1, 0.4, 0.6))
    river_mat = theme.materials.get("river_water", lake_mat)

    vertex_count = 0
    face_count = 0
    with open(path, "w", encoding="utf-8", newline="\n") as obj:
        obj.write(f"# {theme.display_name} ({theme.id}) prototype map, seed {req.seed}\n")
        obj.write("# Y-up. Import: File > Import > Geometry > Wavefront OBJ.\n")
        obj.write("# No normals/UVs are emitted; normals are computed on import.\n")
        obj.write(f"mtllib {os.path.basename(mtl_path)}\n")

        def vertex(x: float, y: float, z: float) -> int:
            nonlocal vertex_count
            vertex_count += 1
            obj.write("v %.5f %.5f %.5f\n" % (x, y, z))
            return vertex_count

        def face(*idx: int) -> None:
            nonlocal face_count
            face_count += 1
            obj.write("f " + " ".join(str(i) for i in idx) + "\n")

        # ---- terrain -----------------------------------------------------
        obj.write("\no Island_Terrain\n")
        grid: List[List[int]] = []
        for y in range(H + 1):
            sy = min(y, H - 1)
            row = []
            for x in range(W + 1):
                sx = min(x, W - 1)
                row.append(vertex(x0 + x * cell,
                                  world.height_map[sx][sy] * height_scale,
                                  z0 + y * cell))
            grid.append(row)

        for b in sorted(theme.biomes, key=lambda z: z.id):
            present = world.biome_counts.get(b.id, 0)
            if not present:
                continue
            obj.write(f"g biome_{group_by_id[b.id]}\n")
            obj.write(f"usemtl {key_by_id[b.id]}\n")
            for y in range(H):
                for x in range(W):
                    if world.biome[x][y] != b.id:
                        continue
                    a, bb = grid[y][x], grid[y][x + 1]
                    c, d = grid[y + 1][x + 1], grid[y + 1][x]
                    face(a, d, bb)
                    face(bb, d, c)

        # ---- ocean -------------------------------------------------------
        ocean_mat = key_by_id.get(min(water_ids) if water_ids else 0, "water")
        obj.write(f"\no Ocean_Surface\ng ocean_surface\nusemtl {ocean_mat}\n")
        wy = tp.sea_level * height_scale
        corners = [vertex(x0, wy, z0), vertex(x0 + WORLD_SIZE, wy, z0),
                   vertex(x0 + WORLD_SIZE, wy, z0 + WORLD_SIZE),
                   vertex(x0, wy, z0 + WORLD_SIZE)]
        face(corners[0], corners[3], corners[2], corners[1])

        # ---- lakes -------------------------------------------------------
        lake_mat_name = "lake_water" if "lake_water" in mats else ocean_mat
        obj.write(f"\no Inland_Lake_Water\ng lake_surfaces\nusemtl {lake_mat_name}\n")
        for y in range(H):
            for x in range(W):
                lid = world.lake_id[x][y]
                if lid < 0:
                    continue
                obj.write(f"g lake_surfaces lake_{lid:02d}\n")
                lw = world.lake_level[x][y] * height_scale
                a = vertex(x0 + x * cell, lw, z0 + y * cell)
                bb = vertex(x0 + (x + 1) * cell, lw, z0 + y * cell)
                c = vertex(x0 + (x + 1) * cell, lw, z0 + (y + 1) * cell)
                d = vertex(x0 + x * cell, lw, z0 + (y + 1) * cell)
                face(a, d, bb)
                face(bb, d, c)

        # ---- rivers ------------------------------------------------------
        lake_id_val = theme.biome(lake_key).id if lake_key else -1
        river_cells = {(x, y) for y in range(H) for x in range(W)
                       if world.river[x][y] > 0.15
                       and world.biome[x][y] not in water_ids}
        river_mat_name = "river_water" if "river_water" in mats else lake_mat_name
        obj.write(f"\no River_Network\ng rivers\nusemtl {river_mat_name}\n")
        neighbours = ((1, 0), (0, 1), (1, 1), (-1, 1))
        segments = 0
        for x, y in sorted(river_cells, key=lambda it: (it[1], it[0])):
            for dx, dy in neighbours:
                other = (x + dx, y + dy)
                if other not in river_cells:
                    continue
                segments += 1
                ax, az = x0 + (x + 0.5) * cell, z0 + (y + 0.5) * cell
                bx, bz = x0 + (other[0] + 0.5) * cell, z0 + (other[1] + 0.5) * cell
                length = math.hypot(bx - ax, bz - az) or 1.0
                width = cell * (0.12 + 0.22 * min(1.0, world.river[x][y]))
                px = -(bz - az) / length * width
                pz = (bx - ax) / length * width
                ya = world.height_map[x][y] * height_scale + 0.22
                yb = world.height_map[other[0]][other[1]] * height_scale + 0.22
                v1 = vertex(ax + px, ya, az + pz)
                v2 = vertex(ax - px, ya, az - pz)
                v3 = vertex(bx - px, yb, bz - pz)
                v4 = vertex(bx + px, yb, bz + pz)
                face(v1, v2, v3, v4)

        # ---- scatter -----------------------------------------------------
        by_cat: Dict[str, List[Dict]] = {}
        for inst in world.instances:
            by_cat.setdefault(inst["category"], []).append(inst)
        form_by_cat = {c.id: c.form for c in req.categories}

        for cat in req.categories:
            items = by_cat.get(cat.id)
            if not items:
                continue
            obj.write(f"\no Scatter_{cat.id}\ng {cat.id}\n")
            for item in items:
                cid = item.get("cluster_id", -1)
                if cid is not None and cid >= 0:
                    obj.write(f"g {cat.id} {cat.id}_cluster_{cid:02d}\n")
                _emit_form(obj, vertex, face, form_by_cat.get(cat.id, "conifer"),
                           item, world, cell, height_scale, x0, z0, W, H,
                           cat.material or "scatter_rock", mats)

    return {"obj": path, "mtl": mtl_path, "vertices": vertex_count,
            "faces": face_count, "river_segments": segments,
            "missing_materials": missing_materials(req)}


def _emit_form(obj, vertex, face, form: str, item: Dict, world: World,
               cell: float, height_scale: float, x0: float, z0: float,
               W: int, H: int, material: str, mats: Dict) -> None:
    px = min(W - 1, max(0, item["x"]))
    py = min(H - 1, max(0, item["y"]))
    cx = x0 + (item["x"] + 0.5) * cell
    cz = z0 + (item["y"] + 0.5) * cell
    cy = world.height_map[px][py] * height_scale + 0.2
    size = cell * item["scale"] * 3.0
    ang = math.radians(item["rotation"])
    cos, sin = math.cos(ang), math.sin(ang)
    bark = "tree_bark" if "tree_bark" in mats else material

    def tp_(lx, ly, lz):
        return (cx + lx * cos - lz * sin, cy + ly, cz + lx * sin + lz * cos)

    def cone(cyy, radius, hgt, sides, mat, phase=0.0):
        obj.write(f"usemtl {mat}\n")
        base = []
        for i in range(sides):
            a = 2.0 * math.pi * i / sides + phase
            base.append(vertex(*tp_(math.cos(a) * radius, cyy - cy,
                                    math.sin(a) * radius)))
        apex = vertex(cx, cyy + hgt, cz)
        for i in range(sides):
            face(base[i], base[(i + 1) % sides], apex)

    def trunk(hgt, radius, mat):
        obj.write(f"usemtl {mat}\n")
        sides = 5
        lo, hi = [], []
        for i in range(sides):
            a = 2.0 * math.pi * i / sides
            lo.append(vertex(*tp_(math.cos(a) * radius, 0.0, math.sin(a) * radius)))
            hi.append(vertex(*tp_(math.cos(a) * radius * 0.68, hgt,
                                  math.sin(a) * radius * 0.68)))
        for i in range(sides):
            face(lo[i], lo[(i + 1) % sides], hi[(i + 1) % sides], hi[i])
        return hgt

    if form == "conifer":
        th = trunk(size * 0.72, size * 0.09, bark)
        cone(cy + th * 0.72, size * 0.39, size * 0.76, 7, material, ang * 0.1)
        cone(cy + th + size * 0.26, size * 0.31, size * 0.68, 7, material, ang * 0.1)
        cone(cy + th + size * 0.65, size * 0.22, size * 0.61, 7, material, ang * 0.1)
    elif form == "broadleaf":
        th = trunk(size * 0.55, size * 0.10, bark)
        cone(cy + th * 0.80, size * 0.46, size * 0.52, 6, material, ang * 0.1)
        cone(cy + th + size * 0.30, size * 0.33, size * 0.44, 6, material, ang * 0.1)
    elif form == "palm":
        th = trunk(size * 0.95, size * 0.07, bark)
        obj.write(f"usemtl {material}\n")
        for i in range(6):      # fronds as crossed slanted triangles
            a = ang + i * (math.pi / 3.0)
            ux, uz = math.cos(a), math.sin(a)
            base_l = vertex(*tp_(-ux * size * 0.06, th, -uz * size * 0.06))
            base_r = vertex(*tp_(ux * size * 0.06, th, uz * size * 0.06))
            tip = vertex(*tp_(ux * size * 0.62, th - size * 0.22, uz * size * 0.62))
            face(base_l, base_r, tip)
    elif form == "boulder":
        obj.write(f"usemtl {material}\n")
        ring = [(0.0, 0.72, 0.0)]
        for i in range(6):
            a = 2.0 * math.pi * i / 6.0 + ang
            var = 0.78 + 0.18 * ((i * 37 + px * 13 + py * 7) % 5) / 4.0
            ring.append((math.cos(a) * size * 0.45 * var,
                         size * (0.12 + 0.12 * ((i * 3 + px) % 4) / 3.0),
                         math.sin(a) * size * 0.45 * var))
        ring.append((0.0, size * 0.82, 0.0))
        pts = [vertex(*tp_(lx, ly, lz)) for lx, ly, lz in ring]
        for i in range(6):
            face(pts[0], pts[1 + i], pts[1 + (i + 1) % 6])
            face(pts[7], pts[1 + (i + 1) % 6], pts[1 + i])
    elif form == "drift":
        obj.write(f"usemtl {material}\n")
        sides = 7
        base = []
        for i in range(sides):
            a = 2.0 * math.pi * i / sides + ang
            rx = size * (0.55 + 0.12 * ((i * 5 + px) % 3))
            rz = size * (0.34 + 0.09 * ((i * 7 + py) % 3))
            base.append(vertex(*tp_(math.cos(a) * rx, 0.0, math.sin(a) * rz)))
        apex = vertex(cx, cy + size * 0.20, cz)
        for i in range(sides):
            face(base[i], base[(i + 1) % sides], apex)
    else:  # "tuft" and "reed": crossed blades
        obj.write(f"usemtl {material}\n")
        blade_h = size * (0.80 if form == "reed" else 0.56)
        blade_w = size * 0.13
        for blade in range(3):
            a = ang + blade * (math.pi / 3.0)
            ux, uz = math.cos(a) * blade_w, math.sin(a) * blade_w
            bl = vertex(*tp_(-ux, 0.0, -uz))
            br = vertex(*tp_(ux, 0.0, uz))
            tip = vertex(*tp_(ux * 0.3, blade_h * (0.84 + 0.08 * blade), uz * 0.3))
            face(bl, br, tip)
