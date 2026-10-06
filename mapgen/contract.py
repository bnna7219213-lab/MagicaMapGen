"""Theme contract validation.

This module exists because of a specific failure found in the earlier Unity
package: a zoning system that silently no-opped while every report said
"success, zero warnings". The rule here is that **a check that cannot fail is
not a check**, and **no failure mode may be silent**.

Two kinds of check run:

*Static* -- validated against the theme spec itself, so a misconfigured band is
caught even before generation (``no_forbidden_biomes`` inspects the bands, not
just the output, because a runtime-only check would be vacuous: a theme can
only ever emit biomes it declares).

*Runtime* -- validated against the finished map, so a classifier bug or an
over-strict placement filter is caught (``all_biomes_known``, coverage bands,
``categories_placed``, ``regions_effective``).

Hard failures abort with a non-zero exit code. Soft failures are recorded as
warnings. Both are written into every report and printed to the console.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Set

from .schema import ContractCheck, ResolvedRequest, ThemeSpec
from .world import World


@dataclass
class CheckResult:
    kind: str
    passed: bool
    hard: bool
    message: str
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"kind": self.kind, "passed": self.passed,
                "severity": "hard" if self.hard else "soft",
                "message": self.message, "details": self.details}


@dataclass
class ContractReport:
    theme_id: str
    results: List[CheckResult] = field(default_factory=list)

    @property
    def hard_failures(self) -> List[CheckResult]:
        return [r for r in self.results if not r.passed and r.hard]

    @property
    def warnings(self) -> List[CheckResult]:
        return [r for r in self.results if not r.passed and not r.hard]

    @property
    def passed(self) -> bool:
        return not self.hard_failures

    def to_dict(self) -> Dict[str, Any]:
        return {
            "theme_id": self.theme_id,
            "passed": self.passed,
            "checks_run": len(self.results),
            "hard_failures": [r.to_dict() for r in self.hard_failures],
            "warnings": [r.to_dict() for r in self.warnings],
            "results": [r.to_dict() for r in self.results],
        }


def _water_ids(theme: ThemeSpec) -> Set[int]:
    return {b.id for b in theme.biomes if b.is_water}


def _coverage(world: World, theme: ThemeSpec, keys) -> Dict[str, float]:
    by_key = {b.key: b.id for b in theme.biomes}
    water = _water_ids(theme)
    land = 0
    hits: Dict[str, int] = {k: 0 for k in keys}
    ids = {k: by_key[k] for k in keys if k in by_key}
    for y in range(world.height):
        for x in range(world.width):
            b = world.biome[x][y]
            if b in water:
                continue
            land += 1
            for k, bid in ids.items():
                if b == bid:
                    hits[k] += 1
    return {k: (hits[k] / land if land else 0.0) for k in keys} | {"__land": land}


def run_contract(world: World, req: ResolvedRequest) -> ContractReport:
    theme = req.theme
    report = ContractReport(theme_id=theme.id)
    known_ids = set(theme.biome_ids())
    key_by_id = {b.id: b.key for b in theme.biomes}
    water = _water_ids(theme)

    for chk in theme.contract:
        p = chk.params
        if chk.kind == "all_biomes_known":
            emitted = set(world.biome_counts.keys())
            stray = sorted(emitted - known_ids)
            report.results.append(CheckResult(
                kind=chk.kind, passed=not stray, hard=chk.hard,
                message=chk.message or "所有 biome 均属主题声明",
                details={"stray_biome_ids": stray,
                         "stray_biome_keys": [key_by_id.get(s, "?") for s in stray]}))

        elif chk.kind == "no_forbidden_biomes":
            # Static: the theme must not be *able* to emit a forbidden biome.
            band_refs = {b.biome for b in theme.bands}
            static_bad = sorted(band_refs & set(theme.forbidden_biomes))
            if theme.default_biome in theme.forbidden_biomes:
                static_bad.append(theme.default_biome + " (default_biome)")
            # Runtime: defensive, catches a classifier that ignores the bands.
            emitted_keys = {key_by_id.get(b) for b in world.biome_counts}
            runtime_bad = sorted(emitted_keys & set(theme.forbidden_biomes))
            ok = not static_bad and not runtime_bad
            report.results.append(CheckResult(
                kind=chk.kind, passed=ok, hard=chk.hard,
                message=chk.message or "主题未产出被禁止的地表",
                details={"forbidden_declared": list(theme.forbidden_biomes),
                         "reachable_via_bands": static_bad,
                         "present_in_output": runtime_bad}))

        elif chk.kind in ("min_biome_coverage", "max_biome_coverage",
                          "combined_biome_coverage"):
            keys = list(p.get("biomes", ())) or [p.get("biome")]
            keys = [k for k in keys if k]
            cov = _coverage(world, theme, keys)
            land = cov.pop("__land")
            got = sum(cov.get(k, 0.0) for k in keys)
            if chk.kind == "min_biome_coverage":
                need = float(p.get("min_fraction_of_land", 0.0))
                ok = got >= need
                verb, req_key = "required_min", need
            elif chk.kind == "max_biome_coverage":
                need = float(p.get("max_fraction_of_land", 1.0))
                ok = got <= need
                verb, req_key = "required_max", need
            else:
                need = float(p.get("min_fraction_of_land", 0.0))
                ok = got >= need
                verb, req_key = "required_min", need
            # A coverage check over *every* land biome of the theme sums to 1.0
            # by construction and can never fail. Refuse to report it as a pass.
            land_keys = {b.key for b in theme.biomes if not b.is_water}
            vacuous = set(keys) >= land_keys
            empty = not keys
            detail = {"biomes": {k: round(cov.get(k, 0.0), 4) for k in keys},
                      "combined_fraction_of_land": round(got, 4),
                      verb: req_key, "land_cells": land}
            report.results.append(CheckResult(
                kind=chk.kind, passed=False if (vacuous or empty) else ok, hard=chk.hard,
                message=("契约检查无效：biomes 覆盖集合为空" if empty else
                         "契约检查无效：覆盖集合包含了主题的全部陆地 biome，"
                         "该检查恒为真，不构成任何保证" if vacuous
                         else (chk.message or "")),
                details=detail | {"vacuous": vacuous, "empty": empty}))

        elif chk.kind == "min_land_fraction":
            total = world.width * world.height
            land = sum(c for b, c in world.biome_counts.items() if b not in water)
            frac = land / total if total else 0.0
            lo, hi = float(p.get("min", 0.0)), float(p.get("max", 1.0))
            report.results.append(CheckResult(
                kind=chk.kind, passed=lo <= frac <= hi, hard=chk.hard,
                message=chk.message,
                details={"land_fraction": round(frac, 4), "min": lo, "max": hi,
                         "land_cells": land, "total_cells": total}))

        elif chk.kind == "categories_placed":
            shortfalls = []
            for s in world.category_summary:
                want = s["requested"]
                got = s["placed"]
                cat = req.theme.category(s["category"])
                ratio = float(p.get("min_ratio",
                                    cat.min_count_ratio if cat else 0.5))
                if want > 0 and got < want * ratio:
                    shortfalls.append({
                        "category": s["category"], "region": s["region"],
                        "requested": want, "placed": got,
                        "ratio": round(got / want, 3) if want else 0.0,
                        "required_min_ratio": ratio,
                        "legal_cells": s["legal_cells"],
                        "distribution": s["distribution"],
                    })
            report.results.append(CheckResult(
                kind=chk.kind, passed=not shortfalls, hard=chk.hard,
                message=chk.message, details={"shortfalls": shortfalls}))

        elif chk.kind == "regions_effective":
            problems = []
            for r in req.request.regions:
                for cat_id, ov in r.overrides.items():
                    rows = [s for s in world.category_summary
                            if s["category"] == cat_id and s["region"] == r.id]
                    if not rows:
                        problems.append({"region": r.id, "category": cat_id,
                                         "problem": "未产生任何实例（区域被覆盖但无落点）"})
                        continue
                    row = rows[0]
                    # Only flag a *mismatch*. Restating the base distribution in
                    # a region override is legal and must not look like a fault.
                    if "distribution" in ov and row["distribution"] != ov["distribution"]:
                        problems.append({
                            "region": r.id, "category": cat_id,
                            "problem": f"请求分布 {ov['distribution']!r}，"
                                       f"实际为 {row['distribution']!r}"})
                    if row["placed"] == 0:
                        problems.append({"region": r.id, "category": cat_id,
                                         "problem": "区域内放置数为 0",
                                         "legal_cells": row["legal_cells"]})
                    elif row["legal_cells"] == 0:
                        problems.append({"region": r.id, "category": cat_id,
                                         "problem": "区域内没有合法格（可能整片是水或坡度超限）"})
            report.results.append(CheckResult(
                kind=chk.kind, passed=not problems, hard=chk.hard,
                message=chk.message, details={"problems": problems}))

        elif chk.kind == "lakes_on_land":
            bad = []
            for lk in world.lakes:
                ix = min(world.width - 1, int(lk["x"] * world.width))
                iy = min(world.height - 1, int(lk["y"] * world.height))
                if not (0 <= ix < world.width and 0 <= iy < world.height):
                    bad.append({"lake": lk["id"], "problem": "中心越界"})
                elif lk["level"] > req.terrain.lake_max_center_height:
                    bad.append({"lake": lk["id"], "level": round(lk["level"], 4),
                                "problem": "水位高于主题允许的最高湖心高度"})
                elif lk["cells"] == 0:
                    bad.append({"lake": lk["id"], "problem": "未覆盖任何格子"})
            wanted = int(req.terrain.lake_count)
            got = len(world.lakes)
            count_ok = got >= wanted * float(p.get("min_count_ratio", 0.75))
            report.results.append(CheckResult(
                kind=chk.kind, passed=not bad and count_ok, hard=chk.hard,
                message=chk.message,
                details={"bad_lakes": bad, "requested": wanted, "produced": got,
                         "count_ok": count_ok}))

        elif chk.kind == "rivers_reach_water":
            total = len(world.rivers)
            reached = sum(1 for r in world.rivers if r["reached_water"])
            wanted = int(req.terrain.river_count)
            need = float(p.get("min_ratio", 0.6))
            frac = reached / total if total else 1.0
            # Comparing only the ratio of *emitted* rivers would hide a shortfall
            # in how many were produced, so the requested count is checked too.
            count_frac = (total / wanted) if wanted else 1.0
            ok = frac >= need and count_frac >= need
            report.results.append(CheckResult(
                kind=chk.kind, passed=ok, hard=chk.hard,
                message=chk.message,
                details={"requested": wanted, "rivers": total,
                         "reached_water": reached,
                         "reach_ratio": round(frac, 3),
                         "count_ratio": round(count_frac, 3),
                         "required_min": need,
                         "traces_rejected": getattr(world, "river_trace_rejected", 0)}))

        else:
            # An unknown check kind is itself a failure: silently ignoring it
            # would recreate exactly the problem this module prevents.
            report.results.append(CheckResult(
                kind=chk.kind, passed=False, hard=True,
                message=f"未知的契约检查类型 {chk.kind!r}",
                details={"known": sorted(_KNOWN_KINDS)}))

    return report


_KNOWN_KINDS = {
    "all_biomes_known", "no_forbidden_biomes", "min_biome_coverage",
    "max_biome_coverage", "combined_biome_coverage", "min_land_fraction",
    "categories_placed", "regions_effective", "lakes_on_land",
    "rivers_reach_water",
}


def validate_theme_spec(theme: ThemeSpec) -> List[str]:
    """Static spec validation, runnable without generating anything.

    Returns a list of human-readable problems; empty means the spec is sound.
    """
    problems: List[str] = []
    keys = {b.key for b in theme.biomes}
    ids = [b.id for b in theme.biomes]
    if len(ids) != len(set(ids)):
        problems.append(f"主题 {theme.id}: biome id 重复")
    if theme.default_biome not in keys:
        problems.append(f"主题 {theme.id}: default_biome {theme.default_biome!r} 未声明")
    if theme.lake_biome and theme.lake_biome not in keys:
        problems.append(f"主题 {theme.id}: lake_biome {theme.lake_biome!r} 未声明")
    for band in theme.bands:
        if band.biome not in keys:
            problems.append(f"主题 {theme.id}: band 引用未声明的 biome {band.biome!r}")
        for ref, name in ((band.min_height_ref, "min_height_ref"),
                          (band.max_height_ref, "max_height_ref")):
            if ref is not None and ref != "sea":
                problems.append(f"主题 {theme.id}: band {band.biome!r} 的 {name} "
                                f"{ref!r} 无效（仅支持 'sea'）")
        if band.min_height_ref == "sea" and band.min_height is None:
            problems.append(f"主题 {theme.id}: band {band.biome!r} 声明了 "
                            f"min_height_ref 但没有 min_height")
        if band.max_height_ref == "sea" and band.max_height is None:
            problems.append(f"主题 {theme.id}: band {band.biome!r} 声明了 "
                            f"max_height_ref 但没有 max_height")
    for cat in theme.categories:
        for b in cat.allowed_biomes:
            if b not in keys:
                problems.append(f"主题 {theme.id}: 类别 {cat.id!r} 允许未声明的 biome {b!r}")
    for chk in theme.contract:
        if chk.kind not in _KNOWN_KINDS:
            problems.append(f"主题 {theme.id}: 未知契约检查 {chk.kind!r}")
    for key in theme.feature_distributions:
        if key not in ("mountains", "lakes", "rivers"):
            problems.append(f"主题 {theme.id}: 未知的 feature 分布键 {key!r}")
    return problems
