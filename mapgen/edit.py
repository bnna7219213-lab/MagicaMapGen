"""Incremental edit overlay: edits.json + dirty-region regeneration.

A designer hand-edits a generated map (move / delete / add instances, or paint
"no-scatter" cells) and records the changes as an ``edits.json`` of instance-level
operations. ``overlay_world`` replays those on top of a fresh, deterministic
regeneration of the same seed: the surrounding map reproduces byte-for-byte, so
only the edited region differs. This is phase 2 of ``path_b_baseline.md`` -- the
engine-agnostic half; the consuming editor (Unity ``SceneDiffer`` or the PyQt6
``Edits`` panel) only has to emit ops and call ``--overlay``.

Why instance-level and not grid-level: the biome/height grids are RLE-quantised to
8 bits (~0.47 m per step), so editing them loses precision the moment it is
re-encoded. Instances carry exact cell coordinates, so they round-trip cleanly.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

from .config import request_from_dict
from .pipeline import generate
from .schema import ResolvedRequest
from .themes import get_theme

#: Operation kinds understood by the overlay pass.
OP_ADD = "add"
OP_MOVE = "move"
OP_DELETE = "delete"
OP_PAINT = "paint"   # paint: exclude these cells from scatter

EDITS_SCHEMA_VERSION = 1

#: ``(stage, done, total)`` -> None, same shape as the pipeline progress hook.
ProgressHook = Callable[[str, int, int], None]


class EditError(ValueError):
    """Raised for malformed edits.json or ops that cannot be applied."""


def parse_edits(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and normalise an edits.json document into typed op buckets.

    Returns ``{"deleted", "moved", "added", "painted"}`` where ``deleted`` is a
    set of instance ids, ``moved`` maps id -> (x, y), ``added`` is a list of
    world-instance dicts, and ``painted`` is a list of (x, y) cells.
    """
    if not isinstance(data, dict):
        raise EditError("edits.json root must be an object")
    ops = data.get("ops")
    if not isinstance(ops, list):
        raise EditError("edits.json must contain an 'ops' list")

    deleted: set = set()
    moved: Dict[int, Tuple[int, int]] = {}
    added: List[Dict[str, Any]] = []
    painted: List[Tuple[int, int]] = []

    for i, op in enumerate(ops):
        if not isinstance(op, dict) or "op" not in op:
            raise EditError(f"ops[{i}] is missing an 'op' field")
        kind = op["op"]
        if kind == OP_DELETE:
            if "id" not in op:
                raise EditError(f"ops[{i}] delete is missing 'id'")
            deleted.add(int(op["id"]))
        elif kind == OP_MOVE:
            if "id" not in op or "x" not in op or "y" not in op:
                raise EditError(f"ops[{i}] move needs id, x, y")
            moved[int(op["id"])] = (int(op["x"]), int(op["y"]))
        elif kind == OP_ADD:
            for field in ("cat", "type", "x", "y"):
                if field not in op:
                    raise EditError(f"ops[{i}] add needs cat, type, x, y")
            added.append({
                "category": str(op["cat"]),
                "type": str(op["type"]),
                "x": int(op["x"]),
                "y": int(op["y"]),
                "scale": float(op.get("scale", 1.0)),
                "rotation": float(op.get("rot", op.get("rotation", 0.0))),
                "region": "",
                "cluster_id": -1,
            })
        elif kind == OP_PAINT:
            cells = op.get("cells")
            if not isinstance(cells, list):
                raise EditError(f"ops[{i}] paint needs a 'cells' list")
            for c in cells:
                if not (isinstance(c, (list, tuple)) and len(c) == 2):
                    raise EditError(f"ops[{i}] paint cell must be [x, y]")
                painted.append((int(c[0]), int(c[1])))
        else:
            raise EditError(f"ops[{i}] has unknown op kind {kind!r}")
    return {"deleted": deleted, "moved": moved, "added": added, "painted": painted}


def load_base_request(base_doc: Dict[str, Any]) -> ResolvedRequest:
    """Rebuild a resolved request from a base map.json's round-tripped block."""
    req_dict = base_doc.get("request")
    if not isinstance(req_dict, dict):
        raise EditError("base map.json is missing its 'request' block")
    req = request_from_dict(req_dict)
    theme = get_theme(req.theme_id)
    from .contract import validate_theme_spec
    problems = validate_theme_spec(theme)
    if problems:
        raise EditError("base theme no longer validates: " + "; ".join(problems))
    return req.resolve(theme)


def _finalize_instance(world: Any, inst: Dict[str, Any]) -> Dict[str, Any]:
    """Backfill the derived fields exporters read directly off each instance.

    Auto instances already carry ``u`` / ``v`` / ``z``; hand-edited (moved/added)
    ones are built from sparse op data and need them filled from the regenerated
    grids so the scatter CSV and report stay consistent.
    """
    x, y = int(inst["x"]), int(inst["y"])
    inst["u"] = (x + 0.5) / world.width
    inst["v"] = (y + 0.5) / world.height
    inst["z"] = world.height_map[x][y] if (0 <= x < world.width and 0 <= y < world.height) else 0.0
    owner = world.region_owner
    inst["region"] = ""
    if owner and 0 <= x < len(owner) and 0 <= y < len(owner[x]):
        inst["region"] = owner[x][y]
    return inst


def _apply_edits(world: Any, parsed: Dict[str, Any]) -> None:
    """Apply parsed ops onto an already-generated world, in place.

    The world was regenerated from the base seed, so its instance list is
    byte-identical to the base up to ordering. We tag each with a provisional id
    matching the base export (same seed -> same order), then delete / move / add /
    paint. Everything untouched reproduces exactly.
    """
    deleted = parsed["deleted"]
    moved = parsed["moved"]
    added = parsed["added"]
    painted_set = set(parsed["painted"])

    for i, inst in enumerate(world.instances):
        inst["id"] = i  # matches base export ids (deterministic order)

    if painted_set:
        world.instances = [i for i in world.instances
                           if (int(i["x"]), int(i["y"])) not in painted_set]
    if deleted:
        world.instances = [i for i in world.instances
                           if int(i.get("id", -1)) not in deleted]

    protected: List[Dict[str, Any]] = []
    if moved:
        for inst in world.instances:
            iid = int(inst.get("id", -1))
            if iid in moved:
                nx, ny = moved[iid]
                if not (0 <= nx < world.width and 0 <= ny < world.height):
                    raise EditError(f"move target ({nx}, {ny}) is out of bounds")
                inst["x"], inst["y"] = nx, ny
                _finalize_instance(world, inst)
                protected.append(inst)
    for a in added:
        inst = dict(a)
        _finalize_instance(world, inst)
        world.instances.append(inst)
        protected.append(inst)
    # Drop any auto instance that collides with a moved/added cell so the edit is
    # visible (otherwise a re-scattered object would sit on top of the hand edit).
    if protected:
        occupied = {(int(p["x"]), int(p["y"])) for p in protected}
        world.instances = [i for i in world.instances
                          if (i in protected)
                          or (int(i["x"]), int(i["y"])) not in occupied]


def overlay_world(base_doc: Dict[str, Any], parsed: Dict[str, Any],
                  progress: Optional[ProgressHook] = None
                  ) -> Tuple[Any, ResolvedRequest]:
    """Replay edits onto a deterministic regeneration of the base map.

    Returns ``(world, resolved_request)``. The base is regenerated from its own
    seed, which reproduces every unedited instance exactly; the ops then delete,
    relocate, add, or paint over instances locally. Only the edited region differs
    from a plain generation of the base request.
    """
    resolved = load_base_request(base_doc)
    theme = resolved.theme
    known_categories = {c.id for c in theme.categories}
    for add in parsed["added"]:
        if add["category"] not in known_categories:
            raise EditError(
                f"added op category {add['category']!r} is not in theme "
                f"{theme.id!r}; known: {sorted(known_categories)}")

    world = generate(resolved, progress=progress)
    _apply_edits(world, parsed)
    return world, resolved
