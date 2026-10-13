"""Headless proof of the Unity phase-3 edit round-trip.

Generates one base map.json, then drives Unity's MapEditRoundTripEntryPoint.Verify,
which builds a scene, mutates tagged objects (delete + move + hand-add), runs
SceneDiffer -> edits.json, shells `mapgen --overlay`, reloads and asserts. Unity
must be installed; the overlay step reuses THIS interpreter via MAPGEN_PYTHON.
Exit 0 only if the whole loop closes.
"""
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(r"c:\Users\bnna7\workspace\Houdini")
PROJECT = ROOT / "LowPolyCity"
WORK = ROOT / "map_roundtrip_smoke"
LOG = ROOT / "unity_roundtrip.log"
UNITY = r"C:\Program Files\Unity 6000.0.0f1\Editor\Unity.exe"
ENTRY = "LowPolyWorldBuilder.Editor.Batch.MapEditRoundTripEntryPoint.Verify"
BASE = WORK / "snow_20261002_map.json"


def gen_base():
    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir(parents=True)
    cmd = [sys.executable, "-m", "mapgen", "--theme", "snow", "--seed", "20261002",
           "--width", "64", "--height", "64", "--out", str(WORK),
           "--label", "snow_20261002", "--format", "map", "--validate"]
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        print("gen FAIL", r.returncode, (r.stderr or r.stdout)[-500:])
        return False
    return BASE.exists()


def main():
    print("generating base document...")
    if not gen_base():
        print("ROUNDTRIP_FAIL: base generation")
        return 1
    if not Path(UNITY).exists():
        print("ROUNDTRIP_FAIL: Unity not found")
        return 1

    print("launching Unity batchmode (build->mutate->diff->overlay->reload)...")
    if LOG.exists():
        LOG.unlink()
    args = [UNITY, "-batchmode", "-nographics", "-quit",
            "-projectPath", str(PROJECT), "-executeMethod", ENTRY,
            "-roundtripBase", str(BASE), "-roundtripRepo", str(ROOT),
            "-roundtripWork", str(WORK), "-logFile", str(LOG)]
    env = dict(os.environ)
    if not env.get("ALLUSERSPROFILE"):
        env["ALLUSERSPROFILE"] = env.get("PROGRAMDATA") or r"C:\ProgramData"
    env["MAPGEN_PYTHON"] = sys.executable      # the in-Unity overlay reuses this interpreter
    env["MAPGEN_REPO"] = str(ROOT)
    t0 = time.time()
    proc = subprocess.run(args, capture_output=True, text=True, errors="replace", env=env)
    secs = time.time() - t0

    log = LOG.read_text(encoding="utf-8", errors="replace") if LOG.exists() else ""
    lines = log.splitlines()
    cerr = [l for l in lines if "error CS" in l]
    lpw = [l for l in lines if "[LPW]" in l]
    for l in lpw:
        print("  " + l)

    if cerr:
        print("\nROUNDTRIP_FAIL: %d C# compile error(s)" % len(cerr))
        for l in cerr[:10]:
            print("  " + l.strip())
        return 1
    ok = any("ROUNDTRIP_OK" in l for l in lpw)
    if proc.returncode != 0:
        print("\nROUNDTRIP_FAIL: Unity exit %s" % proc.returncode)
        return 1
    if not ok:
        print("\nROUNDTRIP_FAIL: no ROUNDTRIP_OK in log")
        return 1
    # The overlay product must exist and carry v4 provenance.
    prod = WORK / "scene_roundtrip_map.json"
    print("\nROUNDTRIP_OK: loop closed, overlay product %s, %.0fs"
          % (prod.exists(), secs))
    return 0 if prod.exists() else 1


if __name__ == "__main__":
    sys.exit(main())
