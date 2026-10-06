"""Generation report: machine-readable JSON plus a human summary.

Deliberately contains **no timestamp and no wall-clock timing**. Either would
make consecutive runs of the same seed differ byte-for-byte and destroy the
reproducibility guarantee that makes a seed worth handing to a client. Elapsed
time is printed to the console by the CLI, where it is useful but harmless.

Every stat the plan asks for is a real serialised field here -- the earlier
Unity package marked its statistics ``[NonSerialized]`` and shipped JSON
reports that silently contained none of them.
"""

from __future__ import annotations

import json
from typing import Any, Dict

from ..schema import ResolvedRequest
from ..world import World


def build_report(world: World, req: ResolvedRequest,
                 elapsed_ms: float, outputs: Dict[str, Any]) -> Dict[str, Any]:
    from .. import GENERATOR_VERSION, SCHEMA_VERSION
    from ..config import request_to_dict

    theme = req.theme
    contract = world.contract
    return {
        "schema_version": SCHEMA_VERSION,
        "generator_version": GENERATOR_VERSION,
        "label": req.request.label or f"{theme.id}_{req.seed}",
        "seed": req.seed,
        "theme": {"id": theme.id, "display_name": theme.display_name},
        "grid": {"width": world.width, "height": world.height,
                 "tile_size_meters": req.terrain.tile_size_meters,
                 "height_scale_meters": req.terrain.height_scale_meters},
        "contract": {
            "passed": contract.get("passed"),
            "checks_run": contract.get("checks_run"),
            "hard_failures": contract.get("hard_failures", []),
            "warnings": contract.get("warnings", []),
        },
        "stats": world.stats,
        "categories": world.category_summary,
        "lakes": world.lakes,
        "rivers": [{"id": r["id"], "source": r["source"],
                    "terminus": r.get("terminus"), "length": r["length"],
                    "reached_water": r["reached_water"]}
                   for r in world.rivers],
        "regions": [{"id": r.id, "shape": r.shape, "bounds": dict(r.bounds),
                     "overrides": {k: dict(v) for k, v in r.overrides.items()},
                     "cells": world.stats.get("regions", {}).get(r.id, 0)}
                    for r in req.request.regions],
        "request": request_to_dict(req.request),
        "resolved_categories": [
            {"id": c.id, "count": c.count, "distribution": c.distribution.kind,
             "params": c.distribution.params, "form": c.form}
            for c in req.categories
        ],
        "resolved_features": {k: {"kind": v.kind, "params": v.params}
                              for k, v in req.feature_distributions.items()},
        "outputs": outputs,
    }


def to_summary_text(report: Dict[str, Any]) -> str:
    c = report["contract"]
    s = report["stats"]
    lines = [
        f"map report  label={report['label']}  seed={report['seed']}  "
        f"theme={report['theme']['id']} ({report['theme']['display_name']})",
        f"generator={report['generator_version']}  "
        f"grid={report['grid']['width']}x{report['grid']['height']}",
        f"CONTRACT: {'PASSED' if c['passed'] else 'FAILED'}  "
        f"checks={c['checks_run']}  hard_failures={len(c['hard_failures'])}  "
        f"warnings={len(c['warnings'])}",
        f"land={s['land_cells']} ({s['land_fraction']})  water={s['water_cells']}  "
        f"lakes={s['lake_count']}  rivers={s['river_count']} "
        f"(reaching water {s['rivers_reaching_water']})",
        f"instances={s['instance_count']}  clusters={s['cluster_count']}",
        "biomes: " + ", ".join(f"{k}={v}" for k, v in s["biome_cells"].items()),
        "categories: " + ", ".join(
            f"{row['category']}={row['placed']}/{row['requested']}"
            f"[{row['distribution']}]"
            + (f"@{row['region']}" if row["region"] else "")
            for row in report["categories"]),
    ]
    for f in c["hard_failures"]:
        lines.append(f"  [HARD FAIL] {f['kind']}: {f['message']} :: {f['details']}")
    for w in c["warnings"]:
        lines.append(f"  [warn] {w['kind']}: {w['message']} :: {w['details']}")
    if report.get("outputs"):
        lines.append("outputs: " + ", ".join(
            f"{k}={v}" for k, v in sorted(report["outputs"].items())))
    return "\n".join(lines) + "\n"


def write_report(world: World, req: ResolvedRequest, out_dir: str, stem: str,
                 elapsed_ms: float, outputs: Dict[str, str]) -> Dict[str, str]:
    import os
    report = build_report(world, req, elapsed_ms, outputs)
    json_path = os.path.join(out_dir, f"{stem}_report.json")
    txt_path = os.path.join(out_dir, f"{stem}_report.txt")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        f.write("\n")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(to_summary_text(report))
    return {"report_json": json_path, "report_txt": txt_path}
