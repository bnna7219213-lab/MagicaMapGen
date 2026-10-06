"""The three-tier configuration model.

    Theme  (确定性契约)  -- 雪地必须是雪地，不可随机
      └─ Category (一对多) -- 稀疏树木 / 密集树木 / 其它树木，各有数量
           └─ Distribution (可替换) -- 正态 / 泊松 / 均匀 / 网格抖动
                └─ params

Plus Region: a spatial sub-domain that overrides category settings, which is
what makes 局部物体概率化 possible.

Everything here is declarative and frozen. Generators read these specs; they
never mutate them. Config files (JSON) deserialise into exactly these types, so
what a client is shown and what the generator consumed are the same document.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

#: The single artifact-schema version for everything mapgen emits: the map.json
#: deliverable, the report, and the resolved request block embedded in map.json.
#: These evolve together (map.json round-trips the request), so they share one
#: number. Bump it whenever any emitted field changes shape or meaning.
#:
#: v1 -> v2 (additive): grid.heightmap_raw_url, grid.moisture_rle,
#: grid.encoding.moisture, units.moisture_quantisation. All new fields are
#: optional so a v1 consumer can still read a v2 file (ignoring them) and a
#: v2 consumer must tolerate their absence on v1 files.
#: v2 -> v3 (semantic): regions[].priority added. ``regions[].cells`` now counts only
#: the cells a region *owns* after priority resolution rather than every cell its mask
#: touches, so overlapping regions no longer double-count; ``cells_raw`` carries the
#: un-owned extent and ``overlaps`` flags it. Consumers should branch on
#: ``schema_version >= 3``.
SCHEMA_VERSION = 3


# --------------------------------------------------------------------------
# Tier 0: biomes -- the vocabulary a theme is allowed to speak
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class BiomeSpec:
    """One terrain class. The theme's contract is expressed over these."""

    id: int
    key: str                       # stable machine key, e.g. "snow_flat"
    name: str                      # human label, e.g. "雪原"
    color: Tuple[float, float, float]
    is_water: bool = False
    walkable: bool = True
    movement_cost: float = 1.0     # engine hint (RA2-style locomotion cost)
    buildable: bool = True         # engine hint: can a structure be placed
    material: Optional[str] = None  # OBJ material name; defaults to key


@dataclass(frozen=True)
class BiomeBand:
    """Elevation/moisture window that maps a cell onto a biome.

    Bands are evaluated in order; the first match wins. ``None`` means
    unbounded on that side.

    ``min_height_ref`` / ``max_height_ref`` may be set to ``"sea"``, in which
    case that bound is interpreted as an *offset from the resolved sea level*
    rather than an absolute height. This lets a config override ``sea_level``
    without silently invalidating every shoreline band. The two sides are
    independent, so a band can be sea-relative below and absolute above.
    """

    biome: str
    min_height: Optional[float] = None
    max_height: Optional[float] = None
    min_moisture: Optional[float] = None
    max_moisture: Optional[float] = None
    min_height_ref: Optional[str] = None
    max_height_ref: Optional[str] = None

    def resolve(self, sea_level: float) -> Tuple[Optional[float], Optional[float]]:
        lo, hi = self.min_height, self.max_height
        if self.min_height_ref == "sea" and lo is not None:
            lo = sea_level + lo
        if self.max_height_ref == "sea" and hi is not None:
            hi = sea_level + hi
        for ref, name in ((self.min_height_ref, "min_height_ref"),
                          (self.max_height_ref, "max_height_ref")):
            if ref is not None and ref != "sea":
                raise ValueError(f"band {self.biome!r}: unknown {name} {ref!r}")
        return lo, hi

    def matches(self, h: float, m: float, sea_level: float = 0.0) -> bool:
        lo, hi = self.resolve(sea_level)
        if lo is not None and h < lo:
            return False
        if hi is not None and h >= hi:
            return False
        if self.min_moisture is not None and m < self.min_moisture:
            return False
        if self.max_moisture is not None and m >= self.max_moisture:
            return False
        return True


# --------------------------------------------------------------------------
# Tier 3: distribution -- the replaceable stochastic strategy
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class DistributionSpec:
    """A named distribution plus its parameters.

    ``kind`` selects the strategy from the registry in ``mapgen.distributions``;
    ``params`` is strategy-specific and validated by that strategy.
    """

    kind: str
    params: Dict[str, Any] = field(default_factory=dict)

    def merged(self, overrides: Optional[Mapping[str, Any]]) -> "DistributionSpec":
        if not overrides:
            return self
        merged_kind = overrides.get("distribution", self.kind)
        merged_params = dict(self.params)
        for k, v in overrides.items():
            if k != "distribution":
                merged_params[k] = v
        return DistributionSpec(kind=merged_kind, params=merged_params)


# --------------------------------------------------------------------------
# Tier 2: category -- one-to-many under a theme
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class CategorySpec:
    """A population of objects (or a terrain feature) placed by a distribution.

    ``count`` is what the designer asked for; ``placement`` is what the
    contract layer will hold the result against. A category that requests 120
    objects and places 3 must produce a warning, never silence -- that is the
    failure mode this package exists to avoid.
    """

    id: str
    display_name: str
    object_type: str                 # emitted per-instance, for the engine/art
    distribution: DistributionSpec
    form: str = "conifer"            # low-poly mesh form used by the OBJ export
    count: int = 0
    allowed_biomes: Tuple[str, ...] = ()
    max_slope: float = 0.45
    min_count_ratio: float = 0.5     # contract: placed/requested must be >= this
    scale_range: Tuple[float, float] = (0.7, 1.3)
    rotation_jitter: float = 360.0
    exclusive: bool = True           # one instance per cell
    # Categories sharing an exclusion group cannot put two objects on one cell.
    # None => derived from ``form``: small ground detail (grass/reeds) may sit
    # under a tree, but two solid objects may not overlap. This is what stops
    # interpenetrating models without forcing every category to be globally
    # exclusive.
    exclusive_group: Optional[str] = None
    emit_cluster_id: bool = False
    material: Optional[str] = None

    def group(self) -> str:
        if self.exclusive is not True:
            return ""
        if self.exclusive_group is not None:
            return self.exclusive_group
        return "detail" if self.form in ("tuft", "reed") else "solid"

    def overridden(self, ov: Mapping[str, Any], area_fraction: float = 1.0) -> "CategorySpec":
        """Return a copy with region-level overrides applied."""
        if "count" in ov and "density_scale" in ov:
            raise ValueError("category override cannot combine 'count' and 'density_scale'")
        kwargs: Dict[str, Any] = {}
        if "count" in ov:
            kwargs["count"] = int(ov["count"])
        if "density_scale" in ov:
            kwargs["count"] = int(round(
                self.count * max(0.0, area_fraction) * float(ov["density_scale"])))
        for f in ("max_slope", "min_count_ratio", "exclusive", "object_type",
                  "material", "rotation_jitter"):
            if f in ov:
                kwargs[f] = ov[f]
        if "scale_range" in ov:
            kwargs["scale_range"] = tuple(ov["scale_range"])
        if "allowed_biomes" in ov:
            kwargs["allowed_biomes"] = tuple(ov["allowed_biomes"])
        # Distribution parameters come from the strategy's own declaration rather
        # than a hand-kept copy of the list: the copy had drifted and silently
        # accepted names the code never reads (``cluster_sigma``) while dropping
        # names it does (``centre_sigma``), so a region override could look
        # applied and change nothing.
        from .distributions import get_distribution
        # Validate against the *effective* distribution: an override that switches
        # ``distribution`` to poisson_disk is allowed to carry ``min_spacing`` and
        # so on, while a normal_clusters category that merely lists min_spacing
        # (a param its distribution never reads) is still rejected.
        eff_kind = ov.get("distribution", self.distribution.kind)
        known = {"count", "density_scale", "max_slope", "min_count_ratio",
                 "exclusive", "object_type", "material", "rotation_jitter",
                 "scale_range", "allowed_biomes", "distribution"}
        known |= set(get_distribution(eff_kind).params)
        unknown = sorted(set(ov) - known)
        if unknown:
            raise ValueError(
                f"category {self.id!r}: unknown override key(s) {unknown}; "
                f"allowed: {sorted(known)}")
        dist_over = {k: v for k, v in ov.items()
                     if k == "distribution" or k in self.distribution.params}
        kwargs["distribution"] = self.distribution.merged(dist_over or None)
        from dataclasses import replace
        return replace(self, **kwargs)


# --------------------------------------------------------------------------
# Region -- the 局部概率化 layer
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class RegionSpec:
    """A spatial sub-domain with per-category overrides.

    Coordinates are normalised 0..1 so a region definition survives a change of
    map resolution. ``shape`` is one of rect / circle / polygon / all.

    ``priority`` resolves *overlap attribution*. Overlapping regions already both
    apply their own category overrides -- that is useful and stays unchanged. What
    needed a rule was the single-valued question "which region does this cell belong
    to?", which until now silently fell back to declaration order. Higher priority
    wins, and priorities must be distinct so the winner is always explicit.
    """

    id: str
    shape: str = "rect"
    bounds: Dict[str, Any] = field(default_factory=dict)
    overrides: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    priority: int = 0

    def contains(self, u: float, v: float) -> bool:
        b = self.bounds
        if self.shape == "all":
            return True
        if self.shape == "rect":
            return (b.get("x0", 0.0) <= u <= b.get("x1", 1.0)
                    and b.get("y0", 0.0) <= v <= b.get("y1", 1.0))
        if self.shape == "circle":
            cx, cy = b.get("cx", 0.5), b.get("cy", 0.5)
            r = b.get("r", 0.25)
            dx, dy = u - cx, v - cy
            aspect = b.get("aspect", 1.0)
            return (dx * dx * aspect + dy * dy) <= r * r
        if self.shape == "polygon":
            return _point_in_polygon(u, v, b.get("points", []))
        raise ValueError(f"region {self.id!r}: unknown shape {self.shape!r}")


def _point_in_polygon(u: float, v: float, pts: Sequence[Sequence[float]]) -> bool:
    inside = False
    n = len(pts)
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        xi, yi = pts[i][0], pts[i][1]
        xj, yj = pts[j][0], pts[j][1]
        if ((yi > v) != (yj > v)) and (u < (xj - xi) * (v - yi) / (yj - yi + 1e-18) + xi):
            inside = not inside
        j = i
    return inside


# --------------------------------------------------------------------------
# Terrain parameters -- theme-owned, so 雪地 and 岛屿 diverge here
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class TerrainParams:
    width: int = 256
    height: int = 256
    # World scale handed to the engine: one grid cell is this many metres, and
    # the normalised 0..1 height field maps onto this many metres of elevation.
    tile_size_meters: float = 8.0
    height_scale_meters: float = 120.0
    # Reference resolution for length-valued distribution parameters
    # (``min_spacing`` / ``spacing`` / ``spread`` / ``min_cluster_spacing``).
    # They are authored in *cells at this grid size* and rescaled to the grid
    # actually being generated, so a 128-cell map is a smaller picture of the
    # same world rather than a world where one lake is 20% of the map wide.
    # At the reference size the scale is exactly 1.0, so authoring is unchanged.
    length_reference_cells: int = 256
    island_radius: float = 0.42
    # Vertical shaping of the height field. ``ridge * amplitude + base`` is the
    # pre-mask elevation. A large amplitude pushes the ridged multifractal into
    # the 0..1 clamp so broad areas saturate at the ceiling and get classified as
    # bare peaks; themes tune these to control how much of the land reads as
    # high mountain vs open ground. Defaults reproduce the original constants.
    height_amplitude: float = 1.35
    height_base: float = 0.22
    # Per-map height normalization. "none" keeps the raw ridged field (snow,
    # whose amplitude is hand-calibrated and already stable). "rank" remaps
    # land-cell elevations onto a fixed target curve by percentile rank, so the
    # fraction of land above any absolute band threshold becomes seed-invariant
    # by construction. This is what stops the island theme's vegetation contract
    # from swinging with the ridged noise (highland fraction varied 13%-71%
    # across seeds before). Water cells are left untouched, so the coastline and
    # land fraction are preserved exactly; only land elevations are redistributed.
    height_normalize: str = "none"
    # Exponent of the rank->elevation target curve when height_normalize="rank":
    # normalized = sea + (1-sea) * p**gamma, p = percentile rank in (0,1].
    # gamma>1 pushes land mass toward low elevation (broad lowlands, fewer but
    # sharper peaks); gamma=1 is a uniform hypsometry.
    height_rank_gamma: float = 1.0
    mountain_frequency: float = 0.9
    detail_frequency: float = 4.5
    valley_count: int = 3
    river_count: int = 5
    # How many shallow uphill steps a river trace may take to escape a noise
    # pit. Zero reverts to pure steepest descent, which strands most traces.
    river_escape_budget: int = 10
    sea_level: float = 0.22
    beach_width: float = 0.05
    warp_strength: float = 0.20
    noise_octaves: int = 5
    persistence: float = 0.55
    lacunarity: float = 2.05
    lake_count: int = 8
    lake_mean_radius: float = 0.045
    lake_radius_spread: float = 0.012
    # Guards against the "lake on a mountaintop" artefact: a lake centre must
    # not be higher than this, or it reads as a bug rather than an alpine lake.
    lake_max_center_height: float = 0.72
    lake_min_center_height_above_sea: float = 0.07
    # Theme-specific knobs consumed by the biome classifier and contract layer.
    snow_line: float = 0.52          # above this height, snow/ice biomes take over
    frozen_water: bool = False       # lakes render as ice rather than open water
    extra: Dict[str, Any] = field(default_factory=dict)


def grid_length_scale(tp: "TerrainParams") -> float:
    """Multiply an authored length (in reference cells) to get real cells.

    Height, moisture and every lake/basin radius are already expressed in
    normalised 0..1 space and therefore scale with the map for free. Length
    parameters handed to distributions (``min_spacing`` and friends) are cell
    counts, so they are the one thing that would silently change meaning when
    the grid resolution changes. Routing every read through this function is
    what makes ``--width128`` a smaller picture of the same world instead of a
    different world.
    """
    return min(tp.width, tp.height) / float(tp.length_reference_cells)


# --------------------------------------------------------------------------
# Parameter metadata -- the single source of truth for "how to edit this"
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class ParamMeta:
    """How a GUI should present one terrain parameter.

    Exposed through ``--describe-theme`` so a front end can build a real control
    instead of guessing. The guess is the dangerous part: an earlier revision of this
    project carried a category override key that the code never read, and it failed
    silently for months because nothing validated the name against the consumer.
    Publishing type and range from the same table the generator validates against
    removes that whole class of bug.
    """

    key: str
    kind: str                      # "int" | "float" | "bool" | "choice"
    group: str = "General"
    label: str = ""
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    step: Optional[float] = None
    choices: Tuple[str, ...] = ()
    help: str = ""
    advanced: bool = False


#: Every parameter a front end may edit. Kept exhaustive on purpose: a field that is
#: absent here simply is not offered for editing, rather than appearing with no
#: metadata and forcing the UI to invent a widget.
TERRAIN_META: Tuple[ParamMeta, ...] = (
    # -- world scale ----------------------------------------------------
    ParamMeta("tile_size_meters", "float", "World", "Tile size (m)", 0.1, 1000.0, 0.5,
              help="Metres per grid cell."),
    ParamMeta("height_scale_meters", "float", "World", "Elevation range (m)", 1.0, 10000.0, 10.0,
              help="The normalised 0..1 height field maps onto this many metres."),
    ParamMeta("length_reference_cells", "int", "World", "Length reference", 16, 4096, 16,
              help="Resolution that length parameters (min_spacing etc.) are authored at."),
    # -- landmass -------------------------------------------------------
    ParamMeta("island_radius", "float", "Landmass", "Island radius", 0.05, 1.5, 0.01,
              help="Radius of the landmass mask. Larger means more land."),
    ParamMeta("sea_level", "float", "Landmass", "Sea level", 0.0, 0.95, 0.01,
              help="Heights below this become water."),
    ParamMeta("height_normalize", "choice", "Landmass", "Height normalisation", 0.0, None, None,
              choices=("none", "rank"),
              help="'rank' makes the fraction of land above any elevation seed-invariant.",
              advanced=True),
    ParamMeta("height_rank_gamma", "float", "Landmass", "Rank gamma", 0.25, 4.0, 0.05,
              help="Exponent of the rank curve. >1 flattens lowlands, sharpens peaks.",
              advanced=True),
    # -- mountains ------------------------------------------------------
    ParamMeta("mountain_frequency", "float", "Mountains", "Mountain frequency", 0.1, 4.0, 0.05),
    ParamMeta("height_amplitude", "float", "Mountains", "Height amplitude", 0.2, 3.0, 0.05,
              help="Higher values saturate ridges into broad high plateaus."),
    ParamMeta("height_base", "float", "Mountains", "Height base", 0.0, 0.6, 0.01),
    ParamMeta("detail_frequency", "float", "Mountains", "Detail frequency", 0.5, 12.0, 0.1,
              advanced=True),
    ParamMeta("warp_strength", "float", "Mountains", "Domain warp", 0.0, 0.8, 0.02,
              advanced=True),
    ParamMeta("noise_octaves", "int", "Mountains", "Noise octaves", 1, 8, 1, advanced=True),
    ParamMeta("persistence", "float", "Mountains", "Persistence", 0.1, 0.95, 0.05, advanced=True),
    ParamMeta("lacunarity", "float", "Mountains", "Lacunarity", 1.2, 3.5, 0.05, advanced=True),
    ParamMeta("valley_count", "int", "Mountains", "Valleys", 0, 24, 1),
    # -- water ----------------------------------------------------------
    ParamMeta("lake_count", "int", "Water", "Lakes", 0, 64, 1),
    ParamMeta("lake_mean_radius", "float", "Water", "Lake radius", 0.005, 0.2, 0.005,
              help="Normalised to the map's smaller dimension."),
    ParamMeta("lake_radius_spread", "float", "Water", "Lake radius spread", 0.0, 0.1, 0.005,
              advanced=True),
    ParamMeta("lake_max_center_height", "float", "Water", "Max lake centre height", 0.05, 1.0, 0.01,
              advanced=True),
    ParamMeta("lake_min_center_height_above_sea", "float", "Water", "Min lake centre above sea",
              0.0, 0.5, 0.01, advanced=True),
    ParamMeta("frozen_water", "bool", "Water", "Freeze water", 0.0, None, None),
    # -- rivers ---------------------------------------------------------
    ParamMeta("river_count", "int", "Rivers", "Rivers", 0, 32, 1),
    ParamMeta("river_escape_budget", "int", "Rivers", "Uphill escape budget", 0, 40, 1,
              help="Shallow uphill steps a river may take to escape a noise pit.",
              advanced=True),
    # -- decoration -----------------------------------------------------
    ParamMeta("beach_width", "float", "Decoration", "Beach width", 0.0, 0.3, 0.005),
    ParamMeta("snow_line", "float", "Decoration", "Snow line", 0.0, 1.5, 0.01),
)


def terrain_param_schema(terrain: Optional["TerrainParams"] = None) -> List[Dict[str, Any]]:
    """Machine-readable edit schema for terrain parameters.

    Each entry merges the declared metadata with the theme's current value, so a UI
    can render controls pre-filled with the theme defaults. Raises if the table names
    a field that does not exist, which is the drift guard.
    """
    known = {f.name for f in dataclasses.fields(TerrainParams)}
    out: List[Dict[str, Any]] = []
    seen = set()
    for meta in TERRAIN_META:
        if meta.key not in known:
            raise ValueError(
                f"TERRAIN_META names {meta.key!r}, which is not a TerrainParams field")
        if meta.key in seen:
            raise ValueError(f"TERRAIN_META lists {meta.key!r} twice")
        seen.add(meta.key)
        current = getattr(terrain, meta.key, None) if terrain is not None else None
        entry: Dict[str, Any] = {
            "key": meta.key,
            "kind": meta.kind,
            "group": meta.group,
            "label": meta.label or meta.key.replace("_", " ").capitalize(),
            "default": current,
            "help": meta.help,
            "advanced": meta.advanced,
        }
        if meta.minimum is not None:
            entry["minimum"] = meta.minimum
        if meta.maximum is not None:
            entry["maximum"] = meta.maximum
        if meta.step is not None:
            entry["step"] = meta.step
        if meta.choices:
            entry["choices"] = list(meta.choices)
        out.append(entry)
    return out


# --------------------------------------------------------------------------
# Contract -- what the theme *guarantees*
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class ContractCheck:
    """A declarative assertion about the finished map.

    ``kind`` is resolved by ``mapgen.contract``. Failing a check marked
    ``hard=True`` aborts the run with a non-zero exit code; a soft failure is
    recorded as a warning. Either way it is *never* silent.
    """

    kind: str
    params: Dict[str, Any] = field(default_factory=dict)
    hard: bool = True
    message: str = ""


@dataclass(frozen=True)
class ThemeSpec:
    """Tier 1. The deterministic identity of a map."""

    id: str
    display_name: str
    description: str
    biomes: Tuple[BiomeSpec, ...]
    bands: Tuple[BiomeBand, ...]
    default_biome: str
    terrain: TerrainParams
    categories: Tuple[CategorySpec, ...]
    contract: Tuple[ContractCheck, ...] = ()
    forbidden_biomes: Tuple[str, ...] = ()
    # Assigned by the lake pass directly, never by band matching (a band with no
    # constraints would otherwise swallow every cell).
    lake_biome: str = ""
    # Terrain features also get a selectable distribution, so 山脉坐落 /
    # 湖泊位置 / 河流源头 are configurable the same way scatter is.
    # Keys: "mountains", "lakes", "rivers".
    feature_distributions: Dict[str, DistributionSpec] = field(default_factory=dict)
    # Non-biome palette entries (bark, foliage, rock, water...). The theme owns
    # its entire palette so nothing downstream has to hardcode a colour.
    materials: Dict[str, Tuple[float, float, float]] = field(default_factory=dict)

    def biome(self, key: str) -> BiomeSpec:
        for b in self.biomes:
            if b.key == key:
                return b
        raise KeyError(f"theme {self.id!r} has no biome {key!r}")

    def biome_ids(self) -> Tuple[int, ...]:
        return tuple(b.id for b in self.biomes)

    def category(self, cid: str) -> Optional[CategorySpec]:
        for c in self.categories:
            if c.id == cid:
                return c
        return None

    def material_for(self, key: str) -> str:
        b = self.biome(key)
        return b.material or b.key


# --------------------------------------------------------------------------
# Request -- one generation, fully described
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class MapRequest:
    """Everything needed to reproduce a map: theme + seed + overrides."""

    theme_id: str
    seed: int
    width: Optional[int] = None       # overrides theme default when set
    height: Optional[int] = None
    terrain_overrides: Dict[str, Any] = field(default_factory=dict)
    category_overrides: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    feature_overrides: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    regions: Tuple[RegionSpec, ...] = ()
    disabled_categories: Tuple[str, ...] = ()
    formats: Tuple[str, ...] = ("map", "csv", "pgm", "report")
    label: str = ""

    def resolve(self, theme: ThemeSpec) -> "ResolvedRequest":
        """Bind this request against a concrete theme spec."""
        from dataclasses import replace
        from typing import get_type_hints

        tp = theme.terrain
        base_w, base_h = tp.width, tp.height
        for name, value in (("width", self.width), ("height", self.height)):
            if value is not None and (isinstance(value, bool) or not isinstance(value, int)
                                      or value < 1):
                raise ValueError(f"{name} must be an integer >= 1, got {value!r}")
        tp = replace(tp,
                     width=tp.width if self.width is None else self.width,
                     height=tp.height if self.height is None else self.height)
        terrain_types = get_type_hints(type(tp))
        for k, v in self.terrain_overrides.items():
            if k not in terrain_types:
                raise ValueError(f"terrain override {k!r} is not a TerrainParams field")
            expected = terrain_types[k]
            default = getattr(theme.terrain, k)
            if isinstance(default, bool):
                valid = isinstance(v, bool)
            elif isinstance(default, int):
                valid = isinstance(v, int) and not isinstance(v, bool)
            elif isinstance(default, float):
                valid = isinstance(v, (int, float)) and not isinstance(v, bool)
            elif isinstance(default, dict):
                valid = isinstance(v, dict)
            else:
                valid = isinstance(v, expected)
            if not valid:
                raise ValueError(f"terrain override {k!r} has wrong type: {v!r}")
            tp = replace(tp, **{k: v})

        if tp.width < 1 or tp.height < 1:
            raise ValueError(f"width and height must be >= 1, got {tp.width}x{tp.height}")

        # A lake centre must sit strictly above sea level, so once sea_level
        # climbs past lake_max_center_height the placement window is empty and the
        # run would silently yield zero lakes (then fail lakes_on_land with a
        # confusing message). Catch it here, before any generation happens.
        lake_lo = tp.sea_level + tp.lake_min_center_height_above_sea
        if tp.lake_count > 0 and lake_lo > tp.lake_max_center_height:
            raise ValueError(
                f"lake window is empty: sea_level({tp.sea_level}) + "
                f"lake_min_center_height_above_sea({tp.lake_min_center_height_above_sea}) "
                f"= {lake_lo:.4f} exceeds lake_max_center_height({tp.lake_max_center_height}); "
                f"lower sea_level or raise lake_max_center_height")

        region_ids = [r.id for r in self.regions]
        if any(not isinstance(rid, str) or not rid.strip() for rid in region_ids):
            raise ValueError("region ids must be non-empty strings")
        if len(region_ids) != len(set(region_ids)):
            raise ValueError("region ids must be unique")
        for r in self.regions:
            if isinstance(r.priority, bool) or not isinstance(r.priority, int):
                raise ValueError(f"region {r.id!r}: priority must be an integer, "
                                 f"got {r.priority!r}")
        # Duplicate priorities are rejected rather than warned about. Ties do resolve
        # deterministically (declaration order), so this is not a correctness hole --
        # but two regions fighting over the same cells with equal standing is a
        # design mistake, and failing here points the designer at it immediately
        # instead of letting mapgen quietly pick a winner. Override with distinct
        # priorities to say which one you meant.
        seen_priorities: Dict[int, str] = {}
        for r in self.regions:
            if r.priority in seen_priorities:
                raise ValueError(
                    f"regions {seen_priorities[r.priority]!r} and {r.id!r} share "
                    f"priority {r.priority}; overlapping regions need distinct "
                    f"priorities so the winner is explicit")
            seen_priorities[r.priority] = r.id

        known_categories = {c.id for c in theme.categories}
        unknown_categories = (set(self.category_overrides) | set(self.disabled_categories)) - known_categories
        if unknown_categories:
            raise ValueError(f"unknown category id(s): {sorted(unknown_categories)}")
        for cid, ov in self.category_overrides.items():
            if "count" in ov and "density_scale" in ov:
                raise ValueError(f"category {cid!r}: count and density_scale conflict")
        for region in self.regions:
            unknown = set(region.overrides) - known_categories
            if unknown:
                raise ValueError(f"region {region.id!r}: unknown category id(s): {sorted(unknown)}")
            for cid, ov in region.overrides.items():
                if "count" in ov and "density_scale" in ov:
                    raise ValueError(f"region {region.id!r}, category {cid!r}: count and density_scale conflict")

        # Theme category counts are authored against the theme's default
        # resolution. Rescale them when the map size changes, so a 128x128 map
        # is not left with 256x256's object density (or vice versa). An explicit
        # ``count`` in category_overrides is always treated as absolute.
        area_scale = (tp.width * tp.height) / float(base_w * base_h)

        cats = []
        for c in theme.categories:
            if c.id in self.disabled_categories:
                continue
            ov = self.category_overrides.get(c.id, {})
            if "count" not in ov:
                c = replace(c, count=max(0, int(round(c.count * area_scale))))
            cats.append(c.overridden(ov))

        feats: Dict[str, DistributionSpec] = {}
        for key, spec in theme.feature_distributions.items():
            feats[key] = spec.merged(self.feature_overrides.get(key))
        for key in self.feature_overrides:
            if key not in feats:
                raise KeyError(
                    f"feature override {key!r} is not declared by theme "
                    f"{theme.id!r}; known: {sorted(feats)}")

        return ResolvedRequest(request=self, theme=theme, terrain=tp,
                               categories=tuple(cats),
                               feature_distributions=feats)


@dataclass(frozen=True)
class ResolvedRequest:
    request: MapRequest
    theme: ThemeSpec
    terrain: TerrainParams
    categories: Tuple[CategorySpec, ...]
    feature_distributions: Dict[str, DistributionSpec] = field(default_factory=dict)

    @property
    def seed(self) -> int:
        return self.request.seed

    @property
    def width(self) -> int:
        return self.terrain.width

    @property
    def height(self) -> int:
        return self.terrain.height

    def feature(self, key: str) -> Optional[DistributionSpec]:
        return self.feature_distributions.get(key)
