"""Dependency-free JSON Schema checking for map.json.

The project ships a real JSON Schema (``map.schema.json``) so external tools can
validate the deliverable, but the package itself must stay pure-stdlib. This
module implements the small subset of draft 2020-12 that the schema actually
uses -- type / required / properties / enum / const / minimum / maximum /
exclusiveMinimum / items / minItems / maxItems / pattern / $ref / $defs.

It is deliberately strict about *reporting*: unknown keywords are ignored (so a
richer schema stays usable), but anything it does understand is enforced, and a
mismatch produces a path-qualified message naming the offending field.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Tuple

SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "export", "map.schema.json")

_TYPES = {
    "object": dict,
    "array": list,
    "string": str,
    "boolean": bool,
    "null": type(None),
}


def load_schema(path: str = SCHEMA_PATH) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _type_ok(value: Any, want: str) -> bool:
    if want == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if want == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if want == "boolean":
        return isinstance(value, bool)
    expected = _TYPES.get(want)
    if expected is None:
        return True
    if want == "object":
        return isinstance(value, dict)
    if want == "array":
        return isinstance(value, list)
    if want == "string":
        return isinstance(value, str)
    return isinstance(value, expected)


def _resolve(schema: Dict[str, Any], root: Dict[str, Any]) -> Dict[str, Any]:
    seen = 0
    while "$ref" in schema and seen < 16:
        ref = schema["$ref"]
        if not ref.startswith("#/"):
            return schema
        node: Any = root
        for part in ref[2:].split("/"):
            if not isinstance(node, dict) or part not in node:
                return schema
            node = node[part]
        if not isinstance(node, dict):
            return schema
        schema = node
        seen += 1
    return schema


def _check(value: Any, schema: Dict[str, Any], root: Dict[str, Any],
           path: str, errors: List[str]) -> None:
    schema = _resolve(schema, root)

    if "type" in schema:
        want = schema["type"]
        wants = want if isinstance(want, list) else [want]
        if not any(_type_ok(value, w) for w in wants):
            errors.append(f"{path or '<root>'}: expected type "
                          f"{'/'.join(wants)}, got {type(value).__name__}")
            return

    if "const" in schema and value != schema["const"]:
        errors.append(f"{path or '<root>'}: expected const "
                      f"{schema['const']!r}, got {value!r}")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path or '<root>'}: {value!r} not in {schema['enum']}")

    if isinstance(value, str) and "pattern" in schema:
        if not re.search(schema["pattern"], value):
            errors.append(f"{path or '<root>'}: {value!r} does not match "
                          f"pattern {schema['pattern']}")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path or '<root>'}: {value} < minimum "
                          f"{schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path or '<root>'}: {value} > maximum "
                          f"{schema['maximum']}")
        if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
            errors.append(f"{path or '<root>'}: {value} <= exclusiveMinimum "
                          f"{schema['exclusiveMinimum']}")

    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append(f"{path or '<root>'}: {len(value)} items < minItems "
                          f"{schema['minItems']}")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errors.append(f"{path or '<root>'}: {len(value)} items > maxItems "
                          f"{schema['maxItems']}")
        if "items" in schema:
            for i, item in enumerate(value):
                _check(item, schema["items"], root, f"{path}[{i}]", errors)

    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path or '<root>'}: missing required "
                              f"property {key!r}")
        for key, sub in schema.get("properties", {}).items():
            if key in value:
                _check(value[key], sub, root,
                       f"{path}.{key}" if path else key, errors)


def validate(document: Any, schema: Dict[str, Any] | None = None) -> List[str]:
    """Return a list of human-readable violations; empty means valid."""
    if schema is None:
        schema = load_schema()
    errors: List[str] = []
    _check(document, schema, schema, "", errors)
    return errors


def _semantic_checks(document: Dict[str, Any]) -> List[str]:
    """Checks the JSON Schema language cannot express."""
    errors: List[str] = []
    grid = document.get("grid")
    if not isinstance(grid, dict):
        return errors
    total = grid.get("width", 0) * grid.get("height", 0)
    for key in ("biome_rle", "height_rle", "river_rle", "moisture_rle"):
        runs = grid.get(key)
        if isinstance(runs, list):
            decoded = sum(r[1] for r in runs if isinstance(r, list) and len(r) == 2)
            if decoded != total:
                errors.append(f"grid.{key}: decodes to {decoded} cells, "
                              f"expected width*height = {total}")
    # The heightmap sidecar is referenced by relative name only; an absolute
    # path would break the cross-machine byte-identity guarantee.
    raw = grid.get("heightmap_raw_url")
    if isinstance(raw, str) and raw:
        if os.path.isabs(raw) or ":" in raw or raw.startswith(("/", "\\")):
            errors.append(f"grid.heightmap_raw_url must be a relative basename, "
                          f"got {raw!r}")
        if raw != os.path.basename(raw):
            errors.append(f"grid.heightmap_raw_url must be a bare filename, "
                          f"got {raw!r}")
    legend = grid.get("biome_legend")
    if isinstance(legend, list):
        known = {b.get("id") for b in legend if isinstance(b, dict)}
        emitted = {r[0] for r in grid.get("biome_rle", [])
                   if isinstance(r, list) and len(r) == 2}
        unknown = emitted - known
        if unknown:
            errors.append(f"grid.biome_rle references undeclared biome id(s) "
                          f"{sorted(unknown)}")
    insts = document.get("instances")
    if isinstance(insts, list):
        w = grid.get("width", 0)
        h = grid.get("height", 0)
        for rec in insts:
            if not isinstance(rec, dict):
                continue
            x, y = rec.get("x"), rec.get("y")
            if isinstance(x, int) and isinstance(y, int) and not (0 <= x < w and 0 <= y < h):
                errors.append(f"instances[{rec.get('id')}]: cell ({x},{y}) "
                              f"outside {w}x{h} grid")
                break
    return errors