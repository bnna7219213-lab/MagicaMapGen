# Changelog

## 0.1.0 — MVP (phase 0-2)

- EditorWindow (`Tools > Low Poly World Builder`): profile editing, preview,
  generate, generate+save, clean.
- Deterministic pipeline: xorshift128+ seeded streams, sub-seeds per
  block/lot; no UnityEngine.Random usage in generators.
- Parametric grid road network with topology-derived junction kinds; single
  merged road/sidewalk/ground/marking mesh.
- Block subdivision into perimeter lots; zone profiles (residential,
  commercial, park) with weighted assignment.
- Merged-mesh procedural buildings (walls/roof/windows submeshes) with
  palette-driven materials.
- Scatter: intersection lamps and sidewalk trees, prefab override via
  AssetCatalog with footprint-fit weighted selection.
- WorldBuildMarker cleanup policy: rebuilds never touch unmarked or
  manual-locked scene content; Undo registered per operation.
- Batch entry point with -lpwProfile/-lpwOut/-lpwSeed and exit codes;
  zero-arg GenerateDefaultDemo smoke entry.
- EditMode tests: determinism, road connectivity, lot containment,
  random stream stability.
