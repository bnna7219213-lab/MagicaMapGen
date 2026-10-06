"""Collect the real artifacts the promo video shows.

Nothing is staged: every map, hash and log line the video claims is produced by the
actual generator. For an internal proposal the evidence IS the product.
"""
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO))
from mapgen import cli

OUT = HERE / "_promo_assets"
CASES = [("snow", 20261002, 128), ("snow", 4242, 128),
         ("island", 20261002, 128), ("island", 88, 128),
         ("island", 7, 256)]


def generate_maps():
    shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir(parents=True)
    rows = []
    for theme, seed, size in CASES:
        sys.argv = ["mapgen", "--theme", theme, "--seed", str(seed),
                    "--width", str(size), "--height", str(size),
                    "--out", str(OUT), "--format", "map", "--format", "report"]
        try:
            cli.main()
        except SystemExit:
            pass
        path = OUT / ("%s_%d_map.json" % (theme, seed))
        doc = json.loads(path.read_text(encoding="utf-8"))
        rows.append({"theme": theme, "seed": seed, "size": size,
                     "passed": doc["contract"]["passed"],
                     "hard_failures": [f["kind"] for f in doc["contract"]["hard_failures"]],
                     "stats": doc["stats"], "schema_version": doc["schema_version"]})
        print("%-7s seed=%-9d passed=%-5s land=%.3f inst=%d fails=%s"
              % (theme, seed, doc["contract"]["passed"], doc["stats"]["land_fraction"],
                 doc["stats"]["instance_count"],
                 [f["kind"] for f in doc["contract"]["hard_failures"]]))
    return rows


def determinism_proof():
    """Same seed into two directories across three format sets; compare digests.

    This is the claim the video makes, so it is measured here, not asserted.
    """
    digests = {}
    combos = [("map",), ("map", "csv", "pgm", "report"),
              ("map", "csv", "pgm", "report", "obj")]
    for i, fmts in enumerate(combos):
        for d in ("_det_a", "_det_b"):
            shutil.rmtree(REPO / d, ignore_errors=True)
            cmd = [sys.executable, "-m", "mapgen", "--theme", "snow",
                   "--seed", "20261002", "--width", "128", "--height", "128",
                   "--out", str(REPO / d)]
            for f in fmts:
                cmd += ["--format", f]
            subprocess.run(cmd, cwd=REPO, capture_output=True)
            p = REPO / d / "snow_20261002_map.json"
            digests.setdefault(i, set()).add(
                hashlib.sha256(p.read_bytes()).hexdigest())
    same = all(len(v) == 1 for v in digests.values())
    only = sorted(next(iter(next(iter(digests.values())))))
    print("determinism: %d format combos x 2 dirs -> %s (%s)"
          % (len(combos), "identical" if same else "MISMATCH", "".join(only[:16])))
    return {"combos": len(combos), "identical": same, "sha256": "".join(only)}


def main():
    print("== generating maps ==")
    rows = generate_maps()
    print("")
    print("== determinism ==")
    det = determinism_proof()
    for d in ("_det_a", "_det_b"):
        shutil.rmtree(REPO / d, ignore_errors=True)
    (OUT / "manifest.json").write_text(
        json.dumps({"cases": rows, "determinism": det},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    print("")
    print("manifest written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
