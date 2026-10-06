"""Command line entry point.

    python -m mapgen --theme snow --seed 20261002 --out out/
    python -m mapgen --config configs/snow_north_forest.json --out out/
    python -m mapgen --list-themes
    python -m mapgen --describe-theme snow

Exit codes (usable as a CI signal):

    0  success, theme contract passed
    1  generation ran but the theme contract hard-failed
    2  bad usage / malformed config / unknown theme or distribution
    3  I/O error writing outputs

``--out`` is required. The generator never writes next to its own source, so a
parameter experiment cannot silently overwrite a delivered map.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import List, Optional

from . import GENERATOR_VERSION
from .config import ConfigError, load_config, request_from_dict
from .contract import validate_theme_spec
from .distributions import list_distributions
from .export import FORMATS, write_outputs
from .pipeline import generate
from .schema import SCHEMA_VERSION, terrain_param_schema
from .schema import MapRequest
from .themes import get_theme, list_themes


def _force_utf8_stdout() -> None:
    """Windows consoles default to a legacy code page; theme names are Chinese."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="mapgen",
        description="主题 → 类别 → 分布 三层驱动的低多边形游戏原型地图生成器")
    p.add_argument("--theme", help="主题 id（--list-themes 可查）")
    p.add_argument("--config", help="JSON 配置文件；与命令行参数冲突时以配置文件为准")
    p.add_argument("--seed", type=int, help="随机种子；同 seed 结果逐字节一致")
    p.add_argument("--width", type=int, help="覆盖主题默认网格宽")
    p.add_argument("--height", type=int, help="覆盖主题默认网格高")
    p.add_argument("--out", help="输出目录（必填，除非只是 --list/--describe）")
    p.add_argument("--label", help="产物文件名前缀，默认 <theme>_<seed>")
    p.add_argument("--format", action="append", dest="formats",
                   choices=list(FORMATS),
                   help=f"输出格式，可重复；默认 map csv pgm report。可选 {list(FORMATS)}")
    p.add_argument("--set", action="append", dest="sets", metavar="KEY=VALUE",
                   help="覆盖 terrain 参数，如 --set sea_level=0.3（可重复）")
    p.add_argument("--list-themes", action="store_true", help="列出主题并退出")
    p.add_argument("--describe-theme", metavar="ID", help="打印主题详情并退出")
    p.add_argument("--list-distributions", action="store_true",
                   help="列出可用分布策略并退出")
    p.add_argument("--strict", action="store_true",
                   help="把契约的软警告也视为失败（退出码 1）")
    p.add_argument("--progress", metavar="PATH",
                   help="把阶段进度写成 JSON Lines 到该文件（供 GUI 进度条使用；"
                        "不进入任何产物，故不影响确定性）")
    p.add_argument("--validate", action="store_true",
                   help="用 map.schema.json 校验生成的 map.json（退出码 4 表示违规）")
    p.add_argument("--overlay", metavar="MAP_JSON",
                   help="增量编辑：以该 base map.json 为起点（必须与 --edits 配合）")
    p.add_argument("--edits", metavar="EDITS_JSON",
                   help="edits.json：实例级操作（add/move/delete/paint）")
    p.add_argument("--version", action="store_true", help="打印版本并退出")
    return p


def _apply_sets(req: MapRequest, sets: Optional[List[str]]) -> MapRequest:
    if not sets:
        return req
    from dataclasses import replace
    from typing import get_type_hints
    from .schema import TerrainParams
    field_types = get_type_hints(TerrainParams)
    overrides = dict(req.terrain_overrides)
    for item in sets:
        if "=" not in item:
            raise ConfigError(f"--set 需要 KEY=VALUE 形式，得到 {item!r}")
        key, raw = item.split("=", 1)
        key = key.strip()
        if key not in field_types:
            raise ConfigError(f"--set: {key!r} 不是 TerrainParams 字段")
        value = _coerce(raw.strip())
        expected = field_types[key]
        if expected is bool:
            valid = isinstance(value, bool)
        elif expected is int:
            valid = isinstance(value, int) and not isinstance(value, bool)
        elif expected is float:
            valid = isinstance(value, (int, float)) and not isinstance(value, bool)
            if valid:
                value = float(value)
        else:
            valid = False
        if not valid:
            expected_name = getattr(expected, "__name__", str(expected))
            raise ConfigError(f"--set: {key!r} 值类型错误；期望 {expected_name}，得到 {raw!r}")
        overrides[key] = value
    return replace(req, terrain_overrides=overrides)


def _coerce(raw: str):
    for cast in (int, float):
        try:
            return cast(raw)
        except ValueError:
            pass
    if raw.lower() in ("true", "false"):
        return raw.lower() == "true"
    return raw


def main(argv: Optional[List[str]] = None) -> int:
    _force_utf8_stdout()
    args = build_parser().parse_args(argv)

    if args.version:
        print(f"mapgen {GENERATOR_VERSION} (artifact schema v{SCHEMA_VERSION})")
        return 0

    if args.list_themes:
        print(json.dumps(list_themes(), ensure_ascii=False, indent=2))
        return 0

    if args.list_distributions:
        print(json.dumps(list_distributions(), ensure_ascii=False, indent=2))
        return 0

    if args.describe_theme:
        try:
            theme = get_theme(args.describe_theme)
        except KeyError as e:
            print(f"[mapgen] 错误: {e}", file=sys.stderr)
            return 2
        problems = validate_theme_spec(theme)
        print(json.dumps({
            "id": theme.id,
            "display_name": theme.display_name,
            "description": theme.description,
            "biomes": [{"id": b.id, "key": b.key, "name": b.name,
                        "is_water": b.is_water, "walkable": b.walkable,
                        "movement_cost": b.movement_cost} for b in theme.biomes],
            "categories": [{"id": c.id, "display_name": c.display_name,
                            "object_type": c.object_type, "form": c.form,
                            "count": c.count,
                            "distribution": c.distribution.kind,
                            "params": c.distribution.params,
                            "allowed_biomes": list(c.allowed_biomes),
                            "max_slope": c.max_slope} for c in theme.categories],
            "feature_distributions": {k: {"kind": v.kind, "params": v.params}
                                      for k, v in theme.feature_distributions.items()},
            "terrain": {k: v for k, v in vars(theme.terrain).items() if k != "extra"},
            # Machine-readable edit metadata (type, range, group, help) so a GUI can
            # build real controls instead of hardcoding which fields are ints. This is
            # the same table the drift guard validates against TerrainParams.
            "terrain_schema": terrain_param_schema(theme.terrain),
            "distributions": list_distributions(),
            "forbidden_biomes": list(theme.forbidden_biomes),
            "contract_checks": [{"kind": c.kind, "hard": c.hard,
                                 "params": c.params, "message": c.message}
                                for c in theme.contract],
            "spec_problems": problems,
        }, ensure_ascii=False, indent=2))
        return 2 if problems else 0

    # ---- incremental edit overlay ----------------------------------------
    if args.overlay:
        if not args.edits:
            print("[mapgen] 错误: --overlay 必须与 --edits 配合使用", file=sys.stderr)
            return 2
        if not args.out:
            print("[mapgen] 错误: 必须指定 --out（生成器不会写到源码目录旁）",
                  file=sys.stderr)
            return 2
        return _run_overlay(args)

    # ---- build the request -------------------------------------------------
    try:
        if args.config:
            req = load_config(args.config)
            if args.seed is not None:
                from dataclasses import replace
                req = replace(req, seed=args.seed)
            if args.width is not None or args.height is not None:
                from dataclasses import replace
                req = replace(req,
                              width=req.width if args.width is None else args.width,
                              height=req.height if args.height is None else args.height)
            if args.formats:
                from dataclasses import replace
                req = replace(req, formats=tuple(args.formats))
            if args.label:
                from dataclasses import replace
                req = replace(req, label=args.label)
        elif args.theme:
            if args.seed is None:
                print("[mapgen] 错误: --theme 模式需要 --seed"
                      "（可复现性要求显式种子）", file=sys.stderr)
                return 2
            req = MapRequest(theme_id=args.theme, seed=args.seed,
                             width=args.width, height=args.height,
                             formats=tuple(args.formats or
                                           ("map", "csv", "pgm", "report")),
                             label=args.label or "")
        else:
            print("[mapgen] 错误: 需要 --config 或 --theme"
                  "（或 --list-themes / --describe-theme）", file=sys.stderr)
            return 2

        req = _apply_sets(req, args.sets)

        theme = get_theme(req.theme_id)
        spec_problems = validate_theme_spec(theme)
        if spec_problems:
            print("[mapgen] 主题定义有误，拒绝生成:", file=sys.stderr)
            for p in spec_problems:
                print("  - " + p, file=sys.stderr)
            return 2

        resolved = req.resolve(theme)
    except (ConfigError, KeyError, ValueError, TypeError) as e:
        print(f"[mapgen] 配置错误: {e}", file=sys.stderr)
        return 2

    if not args.out:
        print("[mapgen] 错误: 必须指定 --out（生成器不会写到源码目录旁）",
              file=sys.stderr)
        return 2

    # ---- generate ----------------------------------------------------------
    t0 = time.time()
    progress_sink = None
    progress_file = None
    if args.progress:
        # Opened in truncate mode and line-flushed so a GUI reading it while the
        # generator runs always sees whole, current lines. It lives outside the
        # output tree on purpose: progress is a run-time observation, never an
        # artifact, so it cannot perturb byte-level reproducibility.
        try:
            progress_file = open(args.progress, "w", encoding="utf-8")
        except OSError as e:
            print(f"[mapgen] 无法写入 --progress 文件: {e}", file=sys.stderr)
            return 3

        def progress_sink(stage, done, total):
            progress_file.write(json.dumps({
                "stage": stage, "done": done, "total": total,
                "percent": round(100.0 * done / total),
            }, ensure_ascii=False) + "\n")
            progress_file.flush()

    try:
        world = generate(resolved, progress=progress_sink)
    except Exception as e:
        if progress_file is not None:
            progress_file.close()
        print(f"[mapgen] 生成失败: {type(e).__name__}: {e}", file=sys.stderr)
        return 3
    finally:
        if progress_file is not None and not progress_file.closed:
            progress_file.close()
    elapsed = (time.time() - t0) * 1000.0

    stem = resolved.request.label or f"{theme.id}_{resolved.seed}"
    out_dir = os.path.normpath(args.out)
    try:
        outputs = write_outputs(world, resolved, out_dir, stem, elapsed_ms=elapsed)
    except OSError as e:
        print(f"[mapgen] 写出失败: {e}", file=sys.stderr)
        return 3

    # ---- report ------------------------------------------------------------
    s = world.stats
    c = world.contract
    print(f"[mapgen] {theme.display_name}({theme.id}) seed={resolved.seed} "
          f"{world.width}x{world.height}  耗时 {elapsed:.0f}ms")
    print(f"  陆地 {s['land_cells']} 格 ({s['land_fraction']}) | 湖泊 {s['lake_count']} "
          f"| 河流 {s['river_count']} (入水 {s['rivers_reaching_water']})")
    print(f"  实例 {s['instance_count']} 个 | 树群 {s['cluster_count']} 个")
    print("  类别: " + ", ".join(
        f"{row['category']}={row['placed']}/{row['requested']}[{row['distribution']}]"
        for row in world.category_summary))
    print(f"  契约: {'通过' if c['passed'] else '未通过'} "
          f"(检查 {c['checks_run']} 项, 硬失败 {len(c['hard_failures'])}, "
          f"警告 {len(c['warnings'])})")
    for f in c["hard_failures"]:
        print(f"    [硬失败] {f['kind']}: {f['message']}")
        print(f"             {json.dumps(f['details'], ensure_ascii=False)[:400]}")
    for w in c["warnings"]:
        print(f"    [警告] {w['kind']}: {w['message']}")
        print(f"           {json.dumps(w['details'], ensure_ascii=False)[:400]}")
    for k, v in sorted(outputs.items()):
        print(f"  {k}: {v}")

    if args.validate and "map_json" in outputs:
        from .validate import load_schema, validate, _semantic_checks
        with open(outputs["map_json"], "r", encoding="utf-8") as f:
            document = json.load(f)
        problems = validate(document, load_schema()) + _semantic_checks(document)
        if problems:
            print("[mapgen] map.json 未通过 schema 校验:",
                  file=sys.stderr)
            for line in problems[:40]:
                print(f"  - {line}", file=sys.stderr)
            if len(problems) > 40:
                print(f"  ... 另有 {len(problems) - 40} 条", file=sys.stderr)
            return 4
        print("  schema: 通过 map.schema.json 校验")

    if not c["passed"]:
        return 1
    if args.strict and c["warnings"]:
        return 1
    return 0


def _run_overlay(args: argparse.Namespace) -> int:
    """Apply an edits.json onto a base map.json and re-emit the deliverable.

    The base map.json carries its own resolved request, so --theme/--seed/--config
    are irrelevant here; only --out, --edits and (optionally) --format/--validate
    apply. The surrounding map regenerates from the base seed and reproduces
    byte-for-byte, so the diff is exactly the edited region.
    """
    from dataclasses import replace
    from .edit import EditError, load_base_request, overlay_world, parse_edits
    from .export import FORMATS, write_outputs

    try:
        base_doc = json.loads(Path(args.overlay).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"[mapgen] 无法读取 base map.json: {e}", file=sys.stderr)
        return 2
    try:
        edits_doc = json.loads(Path(args.edits).read_text(encoding="utf-8"))
        parsed = parse_edits(edits_doc)
    except (OSError, json.JSONDecodeError) as e:
        print(f"[mapgen] 无法读取 edits.json: {e}", file=sys.stderr)
        return 2
    except EditError as e:
        print(f"[mapgen] edits.json 非法: {e}", file=sys.stderr)
        return 2

    try:
        resolved = load_base_request(base_doc)
    except EditError as e:
        print(f"[mapgen] base map.json 非法: {e}", file=sys.stderr)
        return 2
    theme = resolved.theme

    progress_sink = None
    progress_file = None
    if args.progress:
        try:
            progress_file = open(args.progress, "w", encoding="utf-8")
        except OSError as e:
            print(f"[mapgen] 无法写入 --progress 文件: {e}", file=sys.stderr)
            return 3

        def progress_sink(stage, done, total):
            progress_file.write(json.dumps({
                "stage": stage, "done": done, "total": total,
                "percent": round(100.0 * done / total),
            }, ensure_ascii=False) + "\n")
            progress_file.flush()

    t0 = time.time()
    try:
        world, resolved = overlay_world(base_doc, parsed, progress=progress_sink)
    except EditError as e:
        if progress_file is not None:
            progress_file.close()
        print(f"[mapgen] 编辑应用失败: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        if progress_file is not None:
            progress_file.close()
        print(f"[mapgen] 增量重生成失败: {type(e).__name__}: {e}", file=sys.stderr)
        return 3
    finally:
        if progress_file is not None and not progress_file.closed:
            progress_file.close()
    elapsed = (time.time() - t0) * 1000.0

    if args.formats:
        resolved = replace(resolved,
                          request=replace(resolved.request,
                                          formats=tuple(args.formats)))
    label = args.label or base_doc.get("label") or f"{theme.id}_{resolved.seed}"
    resolved = replace(resolved,
                      request=replace(resolved.request, label=label))
    out_dir = os.path.normpath(args.out)
    stem = label
    try:
        outputs = write_outputs(world, resolved, out_dir, stem, elapsed_ms=elapsed)
    except OSError as e:
        print(f"[mapgen] 写出失败: {e}", file=sys.stderr)
        return 3

    print(f"[mapgen] overlay {theme.display_name}({theme.id}) seed={resolved.seed} "
          f" 耗时 {elapsed:.0f}ms")
    print(f"  实例 {len(world.instances)} 个（含 {len(parsed['added'])} 新增 / "
          f"{len(parsed['deleted'])} 删除 / {len(parsed['moved'])} 移动 / "
          f"{len(parsed['painted'])} 涂抹格）")
    for k, v in sorted(outputs.items()):
        print(f"  {k}: {v}")

    if args.validate and "map_json" in outputs:
        from .validate import load_schema, validate, _semantic_checks
        with open(outputs["map_json"], "r", encoding="utf-8") as f:
            document = json.load(f)
        problems = validate(document, load_schema()) + _semantic_checks(document)
        if problems:
            print("[mapgen] map.json 未通过 schema 校验:", file=sys.stderr)
            for line in problems[:40]:
                print(f"  - {line}", file=sys.stderr)
            if len(problems) > 40:
                print(f"  ... 另有 {len(problems) - 40} 条", file=sys.stderr)
            return 4
        print("  schema: 通过 map.schema.json 校验")

    if not world.contract.get("passed", False):
        return 1
    if args.strict and world.contract.get("warnings"):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
