"""Config file loading: JSON -> MapRequest.

A config file is the designer-facing document. It names a theme, a seed, and
any overrides (terrain, per-category, per-feature, regions). Because it
deserialises into exactly the same dataclasses the generator consumes, there is
no gap between "what the config says" and "what ran" -- the resolved request is
written back into the output report.
"""

from __future__ import annotations

import json
from typing import Any, Dict

from .schema import MapRequest, RegionSpec


class ConfigError(ValueError):
    """Raised for any malformed or contradictory config file."""


def _require(d: Dict[str, Any], key: str, ctx: str) -> Any:
    if key not in d:
        raise ConfigError(f"{ctx}: 缺少必填字段 {key!r}")
    return d[key]


def request_from_dict(data: Dict[str, Any]) -> MapRequest:
    if not isinstance(data, dict):
        raise ConfigError("配置根节点必须是 JSON 对象")

    theme_id = _require(data, "theme", "config")
    seed = data.get("seed")
    if seed is None:
        raise ConfigError("config: 缺少 seed —— 主题确定但内容可复现的前提是显式 seed")
    try:
        seed = int(seed)
    except (TypeError, ValueError):
        raise ConfigError(f"config: seed 必须是整数，得到 {seed!r}") from None

    regions = []
    for i, r in enumerate(data.get("regions", []) or []):
        ctx = f"regions[{i}]"
        rid = _require(r, "id", ctx)
        shape = r.get("shape", "rect")
        if shape not in ("rect", "circle", "polygon", "all"):
            raise ConfigError(f"{ctx}: 未知 shape {shape!r}"
                              f"（可用 rect/circle/polygon/all）")
        if shape == "rect":
            b = r.get("bounds", {})
            for k in ("x0", "y0", "x1", "y1"):
                if k in b and not isinstance(b[k], (int, float)):
                    raise ConfigError(f"{ctx}: bounds.{k} 必须是数字")
            if all(k in b for k in ("x0", "x1")) and b["x0"] > b["x1"]:
                raise ConfigError(f"{ctx}: bounds.x0 > x1，区域为空")
            if all(k in b for k in ("y0", "y1")) and b["y0"] > b["y1"]:
                raise ConfigError(f"{ctx}: bounds.y0 > y1，区域为空")
        if shape == "polygon" and len(r.get("bounds", {}).get("points", [])) < 3:
            raise ConfigError(f"{ctx}: polygon 至少需要 3 个点")
        ov = r.get("overrides", {}) or {}
        if not isinstance(ov, dict):
            raise ConfigError(f"{ctx}: overrides 必须是对象")
        regions.append(RegionSpec(id=rid, shape=shape,
                                  bounds=dict(r.get("bounds", {}) or {}),
                                  overrides={k: dict(v) for k, v in ov.items()},
                                  priority=int(r.get("priority", 0) or 0)))

    fmts = data.get("formats") or ["map", "csv", "pgm", "report"]
    known_fmts = {"map", "csv", "pgm", "report", "obj"}
    bad = [f for f in fmts if f not in known_fmts]
    if bad:
        raise ConfigError(f"config: 未知的 formats {bad}；可用 {sorted(known_fmts)}")

    return MapRequest(
        theme_id=str(theme_id),
        seed=seed,
        width=data.get("width"),
        height=data.get("height"),
        terrain_overrides=dict(data.get("terrain", {}) or {}),
        category_overrides={k: dict(v) for k, v in
                            (data.get("categories", {}) or {}).items()},
        feature_overrides={k: dict(v) for k, v in
                           (data.get("features", {}) or {}).items()},
        regions=tuple(regions),
        disabled_categories=tuple(data.get("disable_categories", []) or []),
        formats=tuple(fmts),
        label=str(data.get("label", "")),
    )


def load_config(path: str) -> MapRequest:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        raise ConfigError(f"配置文件不存在: {path}") from None
    except json.JSONDecodeError as e:
        raise ConfigError(f"配置文件不是合法 JSON ({path}): {e}") from None
    return request_from_dict(data)


def request_to_dict(req: MapRequest) -> Dict[str, Any]:
    """Round-trippable form, written into every report for reproducibility."""
    return {
        "theme": req.theme_id,
        "seed": req.seed,
        "width": req.width,
        "height": req.height,
        "label": req.label,
        "terrain": dict(req.terrain_overrides),
        "categories": {k: dict(v) for k, v in req.category_overrides.items()},
        "features": {k: dict(v) for k, v in req.feature_overrides.items()},
        "disable_categories": list(req.disabled_categories),
        "formats": list(req.formats),
        "regions": [
            {"id": r.id, "shape": r.shape, "bounds": dict(r.bounds),
             "overrides": {k: dict(v) for k, v in r.overrides.items()}}
            for r in req.regions
        ],
    }
