"""test_overlay.py - verify the phase-2 incremental edit closed loop.

Covers, against a real generated base map:
  * empty edits -> byte-identical to a plain regeneration (no-op overlay)
  * delete op   -> one instance removed, everything else reproduces exactly
  * add op      -> one instance injected, everything else reproduces exactly
  * move op     -> position changed in place, count and the rest unchanged
  * determinism -> same edits twice -> identical overlay output
The CLI flags (--overlay/--edits) are exercised for the byte-identity and
determinism checks so the path the editor actually calls is what gets tested.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

import mapgen  # noqa: E402
from mapgen.edit import load_base_request, overlay_world, parse_edits  # noqa: E402


def _run(*args) -> int:
    return subprocess.run(
        [sys.executable, "-m", "mapgen", *args],
        cwd=str(REPO), capture_output=True, text=True,
        encoding="utf-8").returncode


def _sig(inst) -> tuple:
    """A comparable signature for one instance, normalising base vs world keys."""
    if "category" in inst:  # world schema
        return (inst["x"], inst["y"], inst["category"], inst["type"],
                round(float(inst["scale"]), 4), round(float(inst["rotation"]), 4))
    return (int(inst["x"]), int(inst["y"]), inst["cat"], inst["type"],
            round(float(inst.get("scale", 1.0)), 4),
            round(float(inst.get("rot", 0.0)), 4))


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="mmg_overlay_"))
    out_base = tmp / "base_out"
    out_ov = tmp / "overlay_out"

    # 1) generate a real base map (small grid for speed).
    rc = _run("--theme", "snow", "--seed", "777", "--width", "64", "--height", "64",
              "--out", str(out_base), "--label", "base", "--validate")
    if rc != 0:
        print("FAIL: base generation exited %d" % rc)
        return 1
    base_map = out_base / "base_map.json"
    doc = json.loads(base_map.read_text(encoding="utf-8"))
    base_insts = doc["instances"]
    print("base instances: %d" % len(base_insts))

    # 2) CLI byte-identity: empty edits must reproduce the base exactly.
    (tmp / "empty.json").write_text(json.dumps({"ops": []}), encoding="utf-8")
    rc = _run("--overlay", str(base_map), "--edits", str(tmp / "empty.json"),
              "--out", str(out_ov), "--label", "base", "--validate")
    if rc != 0:
        print("FAIL: empty overlay exited %d" % rc)
        return 1
    identical = (base_map.read_text(encoding="utf-8")
                 == (out_ov / "base_map.json").read_text(encoding="utf-8"))
    if not identical:
        print("FAIL: empty overlay is not byte-identical to the base")
        return 1
    print("PASS: no-op overlay reproduces the base byte-for-byte")

    # A reference world regenerated in-process (full float precision) is the
    # correct yardstick -- comparing against the serialised base would trip on the
    # 2-decimal rotation rounding in map.json. The overlay reconstructs the same
    # world for empty edits, so this is the untouched baseline.
    ref_world, _ = overlay_world(doc, parse_edits({"ops": []}))

    # 3) delete one instance via the in-process API.
    del_id = base_insts[0]["id"]
    world, _ = overlay_world(doc, parse_edits({"ops": [{"op": "delete", "id": del_id}]}))
    if len(world.instances) != len(ref_world.instances) - 1:
        print("FAIL: delete did not remove exactly one instance")
        return 1
    if any(i["id"] == del_id for i in world.instances):
        print("FAIL: deleted instance still present")
        return 1
    ref_rest = sorted(_sig(i) for i in ref_world.instances if i["id"] != del_id)
    new_rest = sorted(_sig(i) for i in world.instances)
    if ref_rest != new_rest:
        print("FAIL: instances other than the deleted one drifted")
        return 1
    print("PASS: delete removes exactly the targeted instance; rest unchanged")

    # 4) add one instance of the first category.
    cat = doc["categories"][0]["category"]
    type_ = doc["categories"][0]["object_type"]
    add_op = {"op": "add", "cat": cat, "type": type_, "x": 10, "y": 20,
              "scale": 1.2, "rot": 45.0}
    world, _ = overlay_world(doc, parse_edits({"ops": [add_op]}))
    if len(world.instances) != len(ref_world.instances) + 1:
        print("FAIL: add did not add exactly one instance")
        return 1
    added = [i for i in world.instances
             if i["x"] == 10 and i["y"] == 20 and i["type"] == type_]
    if len(added) != 1:
        print("FAIL: added instance not found at the requested cell")
        return 1
    if added[0]["scale"] != 1.2 or round(added[0]["rotation"], 2) != 45.0:
        print("FAIL: added instance did not keep its scale/rotation")
        return 1
    ref_all = sorted(_sig(i) for i in ref_world.instances)
    new_sigs = sorted(_sig(i) for i in world.instances
                      if not (i["x"] == 10 and i["y"] == 20 and i["type"] == type_))
    if ref_all != new_sigs:
        print("FAIL: instances other than the added one drifted")
        return 1
    print("PASS: add injects exactly the requested instance; rest unchanged")

    # 5) move one instance.
    src = base_insts[1]
    move_op = {"op": "move", "id": src["id"], "x": 33, "y": 44}
    world, _ = overlay_world(doc, parse_edits({"ops": [move_op]}))
    moved = [i for i in world.instances if i["id"] == src["id"]]
    if len(moved) != 1 or moved[0]["x"] != 33 or moved[0]["y"] != 44:
        print("FAIL: moved instance not relocated")
        return 1
    if len(world.instances) != len(base_insts):
        print("FAIL: move changed the instance count")
        return 1
    print("PASS: move relocates the targeted instance in place")

    # 6) determinism: the same add edits produce identical output from the CLI.
    (tmp / "add.json").write_text(json.dumps({"ops": [add_op]}), encoding="utf-8")
    a_dir, b_dir = tmp / "det_a", tmp / "det_b"
    for d in (a_dir, b_dir):
        rc = _run("--overlay", str(base_map), "--edits", str(tmp / "add.json"),
                  "--out", str(d), "--label", "base")
        if rc != 0:
            print("FAIL: deterministic overlay exited %d" % rc)
            return 1
    if ((a_dir / "base_map.json").read_text(encoding="utf-8")
            != (b_dir / "base_map.json").read_text(encoding="utf-8")):
        print("FAIL: same edits produced different overlay output")
        return 1
    print("PASS: identical edits -> identical overlay output")

    print("ALL OVERLAY TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
