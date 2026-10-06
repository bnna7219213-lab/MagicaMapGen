import shutil, subprocess, sys, time
from pathlib import Path
ROOT = Path(r"c:\Users\bnna7\workspace\Houdini")
PROJECT = ROOT / "LowPolyCity"
DOCS = ROOT / "map_import_smoke"
LOG = ROOT / "unity_import.log"
UNITY = r"C:\Program Files\Unity 6000.0.0f1\Editor\Unity.exe"
ENTRY = "LowPolyWorldBuilder.Editor.Batch.MapBatchImportEntryPoint.ImportDirectory"
SIZES = {"snow": 64, "island": 64}
SEEDS = (20261002, 7, 999999)
def gen():
    if DOCS.exists(): shutil.rmtree(DOCS)
    DOCS.mkdir(parents=True)
    for theme, size in SIZES.items():
        for seed in SEEDS:
            cmd = [sys.executable, "-m", "mapgen", "--theme", theme, "--seed", str(seed),
                   "--width", str(size), "--height", str(size), "--out", str(DOCS),
                   "--format", "map", "--validate"]
            r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
            if r.returncode != 0:
                print("  gen FAIL", theme, seed, r.returncode); return False
    return True
def main():
    print("generating map documents...")
    if not gen():
        print("SMOKE_FAIL: document generation"); return 1
    maps = sorted(DOCS.glob("*_map.json"))
    print("  %d documents" % len(maps))
    if not Path(UNITY).exists():
        print("SMOKE_FAIL: Unity not found"); return 1
    print("launching Unity batchmode...")
    if LOG.exists(): LOG.unlink()
    args = [UNITY, "-batchmode", "-nographics", "-quit",
            "-projectPath", str(PROJECT), "-executeMethod", ENTRY,
            "-mapDir", str(DOCS), "-logFile", str(LOG)]
    t0 = time.time()
    proc = subprocess.run(args, capture_output=True, text=True, errors="replace")
    secs = time.time() - t0
    log = LOG.read_text(encoding="utf-8", errors="replace") if LOG.exists() else ""
    lines = log.splitlines()
    cerr = [l for l in lines if "error CS" in l]
    lpw = [l for l in lines if "[LPW]" in l]
    good = [l for l in lpw if " OK " in l]
    bad = [l for l in lpw if "FAILED" in l or "threw" in l]
    for l in lpw: print("  " + l)
    if cerr:
        print("\nSMOKE_FAIL: %d C# compile error(s)" % len(cerr))
        for l in cerr[:10]: print("  " + l.strip())
        return 1
    if proc.returncode != 0:
        print("\nSMOKE_FAIL: Unity exit code %s" % proc.returncode); return 1
    if bad:
        print("\nSMOKE_FAIL: %d import failure(s)" % len(bad)); return 1
    if len(good) != len(maps):
        print("\nSMOKE_FAIL: verified %d of %d" % (len(good), len(maps))); return 1
    print("\nSMOKE_OK: %d/%d verified, Unity exit 0, %.0fs" % (len(good), len(maps), secs))
    return 0
if __name__ == "__main__":
    sys.exit(main())
