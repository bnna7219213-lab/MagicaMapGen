# Houdini Island Scene

`island_houdini_scene.obj` is the editable 3D scene geometry, not a map screenshot. Open it in Houdini via **File > Import > Geometry > Wavefront OBJ** (or drag the OBJ into the viewport). Keep the companion `.mtl` beside it so its biome materials resolve. It contains terrain with nine biome groups, Gaussian-distributed inland lake surfaces, connected river ribbons, and low-poly tree/rock/grass/reed geometry. Each grove has its own `tree_cluster_XX` primitive group. Coordinates are Y-up.

To build and save a native Houdini project when Houdini is installed, run `build_houdini_hip.py` from Houdini's Python Source Editor. It imports the OBJ, creates an overview camera, and saves `Island_20261002.hip` in this folder.

The terrain uses a 256×256 deterministic height field, seed `20261002`. Lake and grove controls are recorded in `island_report.json`; per-cell lake IDs and per-tree grove IDs are in the CSV files. The HTML file is an optional map preview, not the 3D scene deliverable.
