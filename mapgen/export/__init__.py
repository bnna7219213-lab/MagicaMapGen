"""Export dispatch: format name -> writer.

Requested formats come from the config file or ``--format`` on the CLI. An
unknown format is an error, not a silent no-op.
"""

from __future__ import annotations

import os
from typing import Dict, List

from ..schema import ResolvedRequest
from ..world import World
from . import grids, mapdata, obj, report

FORMATS = ("map", "csv", "pgm", "report", "obj")


def write_houdini_helpers(req: ResolvedRequest, out_dir: str, stem: str,
                          obj_path: str) -> Dict[str, str]:
    """Import guide + a script the user runs inside Houdini to save a .hip."""
    theme = req.theme
    tp = req.terrain
    guide = os.path.join(out_dir, f"{stem}_Houdini_Import.md")
    hip = os.path.join(out_dir, f"{stem}_build_hip.py")
    obj_name = os.path.basename(obj_path)

    with open(guide, "w", encoding="utf-8") as f:
        f.write(f"# {theme.display_name}（{theme.id}）地图场景 — Houdini 导入\n\n")
        f.write(f"`{obj_name}` 是可编辑的三维场景几何，不是截图。"
                "Houdini 中用 **File > Import > Geometry > Wavefront OBJ** 打开，"
                "或直接把 OBJ 拖进视口。同名 `.mtl` 必须放在旁边，否则材质解析不到。\n\n")
        f.write("## 场景结构\n\n")
        f.write("| object | 内容 |\n|---|---|\n")
        f.write("| `Island_Terrain` | 连续高度场网格，按 biome 分 primitive group |\n")
        f.write("| `Ocean_Surface` | 海平面单面片 |\n")
        f.write("| `Inland_Lake_Water` | 每个湖独立水平面，组名 `lake_NN` |\n")
        f.write("| `River_Network` | 相邻河流格连成的条带 |\n")
        for c in req.categories:
            f.write(f"| `Scatter_{c.id}` | {c.display_name}"
                    f"（{c.form} 低模），树群分组 `{c.id}_cluster_NN` |\n")
        f.write("\n## 坐标系与单位\n\n")
        f.write(f"- Y-up；世界尺寸 {obj.WORLD_SIZE:.0f} × {obj.WORLD_SIZE:.0f} 单位\n")
        f.write(f"- 网格 {tp.width}×{tp.height}，每格 `{tp.tile_size_meters}` 米，"
                f"高度按 `{tp.height_scale_meters}` 米映射\n")
        f.write(f"- Seed `{req.seed}`，主题 `{theme.id}`\n\n")
        f.write("## 已知限制\n\n")
        f.write("- **OBJ 不含法线与 UV**：Houdini 导入时会自动计算法线；"
                "但没有 UV 通道，MTL 只能作为纯色，要贴图需先在 DCC 里展开。\n")
        f.write("- 主交付是引擎可消费的地图数据（`*_map.json`）；"
                "OBJ 是给人看的三维稿，两者由同一次生成产出。\n\n")
        f.write("## 生成原生 .hip\n\n")
        f.write(f"本机未检测到 Houdini，无法直接产出 `.hip`。在 Houdini 的 "
                f"Python Source Editor 中运行 `{os.path.basename(hip)}`，"
                "它会导入 OBJ、建一个总览相机并保存 `.hip`。\n")

    with open(hip, "w", encoding="utf-8") as f:
        f.write('"""Run inside Houdini\'s Python Source Editor to save a .hip."""\n')
        f.write("import os\nimport hou\n\n")
        # Derive the directory from this file's own location so the script stays
        # portable and byte-identical regardless of where it was generated.
        f.write('OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))\n')
        f.write(f'OBJ_PATH = os.path.join(OUTPUT_DIR, "{obj_name}")\n')
        f.write(f'HIP_PATH = os.path.join(OUTPUT_DIR, "{stem}_scene.hip")\n\n')
        f.write("if not os.path.isfile(OBJ_PATH):\n")
        f.write('    raise RuntimeError("OBJ not found: " + OBJ_PATH)\n\n')
        f.write('obj_node = hou.node("/obj")\n')
        f.write(f'geo = obj_node.createNode("geo", "{theme.display_name}_Scene")\n')
        f.write("for child in geo.children():\n    child.destroy()\n")
        f.write('file_sop = geo.createNode("file", "Map_Geometry")\n')
        f.write('file_sop.parm("file").set(OBJ_PATH)\n')
        f.write("file_sop.setDisplayFlag(True)\nfile_sop.setRenderFlag(True)\n")
        f.write("geo.layoutChildren()\n\n")
        f.write('cam = obj_node.createNode("cam", "Overview_Camera")\n')
        f.write('cam.parmTuple("t").set((0.0, 1200.0, -2000.0))\n')
        f.write('cam.parmTuple("r").set((-31.0, 0.0, 0.0))\n')
        f.write('cam.parm("focal").set(50.0)\n')
        f.write("obj_node.layoutChildren()\n\n")
        f.write("hou.hipFile.save(HIP_PATH)\n")
        f.write('print("Saved: " + HIP_PATH)\n')

    return {"houdini_guide": guide, "houdini_hip_builder": hip}


def write_outputs(world: World, req: ResolvedRequest, out_dir: str,
                  stem: str, elapsed_ms: float = 0.0) -> Dict[str, str]:
    """Write every requested format. Returns a name -> path map."""
    unknown = [f for f in req.request.formats if f not in FORMATS]
    if unknown:
        raise ValueError(f"未知的输出格式 {unknown}；可用: {list(FORMATS)}")

    os.makedirs(out_dir, exist_ok=True)
    outputs: Dict[str, str] = {}
    formats: List[str] = list(req.request.formats)

    if "map" in formats:
        # The 16-bit PGM is co-written whenever map.json is, so that
        # grid.heightmap_raw_url is never a dangling reference. Its *name* is
        # derived from the stem and not from the requested format set, which
        # keeps map.json byte-identical no matter which formats were asked for.
        pgm_name = f"{stem}_height.pgm"
        outputs["height_pgm"] = grids.write_height_pgm(
            world, os.path.join(out_dir, pgm_name))
        outputs["map_json"] = mapdata.write_map_json(
            world, req, os.path.join(out_dir, f"{stem}_map.json"),
            heightmap_filename=pgm_name)
    if "csv" in formats or "pgm" in formats:
        if "csv" in formats:
            outputs["biomes_csv"] = grids.write_biomes_csv(
                world, req, os.path.join(out_dir, f"{stem}_biomes.csv"))
            outputs["scatter_csv"] = grids.write_scatter_csv(
                world, os.path.join(out_dir, f"{stem}_scatter.csv"))
        if "pgm" in formats and "height_pgm" not in outputs:
            outputs["height_pgm"] = grids.write_height_pgm(
                world, os.path.join(out_dir, f"{stem}_height.pgm"))
    if "obj" in formats:
        obj_path = os.path.join(out_dir, f"{stem}_scene.obj")
        info = obj.write_obj(world, req, obj_path)
        outputs["obj"] = info["obj"]
        outputs["mtl"] = info["mtl"]
        outputs.update(write_houdini_helpers(req, out_dir, stem, obj_path))

    # The report is always written: a run that produces no report cannot be
    # audited, and the contract result must reach the user either way.
    # Paths are recorded as bare filenames so the report stays byte-identical
    # no matter which directory (or which machine) it was generated in.
    report_inputs = {k: os.path.basename(v) for k, v in outputs.items()}
    outputs.update(report.write_report(world, req, out_dir, stem,
                                       elapsed_ms, report_inputs))
    return outputs
