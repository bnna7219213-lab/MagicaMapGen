"""岛屿主题 (Temperate Island).

Re-expressed from the validated ``island_generator.py`` defaults: same biome
identifiers 0-8, same classification order, same elevation thresholds (now
relative to sea level so overrides stay correct). Note this is a *migration of
the configuration*, not a bit-compatible reproduction -- the pipeline now
places objects through category x distribution, which consumes the random
stream differently, so the same seed yields a different (equivalent) map.
"""

from __future__ import annotations

from ..schema import (
    BiomeBand, BiomeSpec, CategorySpec, ContractCheck, DistributionSpec,
    ThemeSpec, TerrainParams,
)

_BIOMES = (
    BiomeSpec(id=0, key="deep_water", name="深水", color=(0.035, 0.16, 0.25),
              is_water=True, walkable=False, buildable=False, movement_cost=99.0),
    BiomeSpec(id=1, key="shallow_water", name="浅水", color=(0.08, 0.39, 0.53),
              is_water=True, walkable=False, buildable=False, movement_cost=99.0),
    BiomeSpec(id=2, key="beach", name="沙滩", color=(0.88, 0.76, 0.49),
              walkable=True, movement_cost=1.3),
    BiomeSpec(id=3, key="grassland", name="草原", color=(0.38, 0.62, 0.23),
              walkable=True, movement_cost=1.0),
    BiomeSpec(id=4, key="forest", name="森林", color=(0.12, 0.34, 0.20),
              walkable=True, movement_cost=2.0),
    BiomeSpec(id=5, key="rocky", name="岩地", color=(0.39, 0.39, 0.37),
              walkable=True, movement_cost=2.4, buildable=False),
    BiomeSpec(id=6, key="peak", name="山峰", color=(0.79, 0.81, 0.77),
              walkable=False, movement_cost=99.0, buildable=False),
    BiomeSpec(id=7, key="valley_basin", name="谷地盆地", color=(0.28, 0.53, 0.32),
              walkable=True, movement_cost=1.5),
    BiomeSpec(id=8, key="inland_lake", name="内陆湖", color=(0.10, 0.42, 0.55),
              is_water=True, walkable=False, buildable=False, movement_cost=99.0),
)

# Mirrors the original classifier's ordering (deep -> shallow -> beach -> peak
# -> rocky -> valley -> forest -> grass) but tightens the forest band to
# mid-elevation: moisture peaks at low elevation in this generator, so an
# unbounded forest band swallows the coastal lowland and grassland vanishes.
_BANDS = (
    BiomeBand(biome="deep_water", max_height_ref="sea", max_height=-0.04),
    BiomeBand(biome="shallow_water", max_height_ref="sea", max_height=0.0),
    BiomeBand(biome="beach", max_height_ref="sea", max_height=0.05),
    BiomeBand(biome="peak", min_height=0.82),
    BiomeBand(biome="rocky", min_height=0.65),
    BiomeBand(biome="valley_basin", min_height_ref="sea", min_height=0.0,
              max_height_ref="sea", max_height=0.18, min_moisture=0.70),
    BiomeBand(biome="forest", min_height_ref="sea", min_height=0.12,
              max_height=0.65, min_moisture=0.55),
    BiomeBand(biome="grassland"),
)

_CATEGORIES = (
    CategorySpec(
        id="trees_sparse", display_name="稀疏树木", object_type="tree_broadleaf",
        form="broadleaf",
        count=90,
        distribution=DistributionSpec("poisson_disk",
                                      {"min_spacing": 5.0,
                                       "max_attempts_per_point": 90}),
        allowed_biomes=("grassland", "valley_basin"),
        max_slope=0.40, scale_range=(0.7, 1.25), material="tree_leaves_light",
    ),
    CategorySpec(
        id="trees_dense", display_name="密集树木", object_type="tree_forest",
        form="conifer",
        count=420,
        distribution=DistributionSpec("normal_clusters",
                                      {"cluster_count": 18,
                                       "spread": 3.1, "min_cluster_spacing": 8.0,
                                       "centre_sigma": 0.21}),
        allowed_biomes=("forest", "grassland", "valley_basin"),
        max_slope=0.45, scale_range=(0.6, 1.3),
        emit_cluster_id=True, material="tree_leaves",
    ),
    CategorySpec(
        id="trees_other", display_name="其它树木", object_type="tree_palm",
        form="palm",
        count=45,
        distribution=DistributionSpec("uniform", {"max_attempts_per_point": 60}),
        allowed_biomes=("beach", "grassland"),
        max_slope=0.30, scale_range=(0.75, 1.2), material="tree_leaves_light",
    ),
    CategorySpec(
        id="rocks", display_name="岩石", object_type="rock",
        form="boulder",
        count=150,
        distribution=DistributionSpec("poisson_disk", {"min_spacing": 5.0}),
        allowed_biomes=("rocky", "peak", "beach"),
        max_slope=0.90, scale_range=(0.6, 1.5), material="scatter_rock",
    ),
    CategorySpec(
        id="grass_details", display_name="草丛", object_type="grass_tuft",
        form="tuft",
        count=170,
        distribution=DistributionSpec("grid_jitter", {"spacing": 9.0, "jitter": 0.5}),
        allowed_biomes=("grassland", "valley_basin", "forest"),
        max_slope=0.30, scale_range=(0.6, 1.2), material="detail_grass",
    ),
    CategorySpec(
        id="reeds", display_name="芦苇", object_type="reed",
        form="reed",
        count=90,
        distribution=DistributionSpec("uniform", {}),
        allowed_biomes=("valley_basin", "beach", "inland_lake"),
        max_slope=0.25, scale_range=(0.6, 1.2), material="detail_reed",
    ),
)

_CONTRACT = (
    ContractCheck(kind="no_forbidden_biomes", hard=True,
                  message="岛屿主题不得出现雪地/冰原等地表"),
    ContractCheck(kind="all_biomes_known", hard=True,
                  message="产出了主题未声明的 biome"),
    ContractCheck(kind="min_biome_coverage", hard=True,
                  params={"biome": "grassland", "min_fraction_of_land": 0.02},
                  message="草原过少，温带岛屿特征不成立"),
    ContractCheck(kind="combined_biome_coverage", hard=True,
                  params={"biomes": ("grassland", "forest", "valley_basin", "beach"),
                          "min_fraction_of_land": 0.55},
                  message="植被/沙滩总覆盖不足，看起来不像温带岛屿"),
    ContractCheck(kind="max_biome_coverage", hard=False,
                  params={"biome": "rocky", "max_fraction_of_land": 0.50},
                  message="裸岩过多，岛屿宜居感被削弱"),
    # Degenerate-map guard, not a quality bar. Rank normalization stabilizes
    # biome *composition* but deliberately preserves the coastline, so land
    # *size* still varies naturally (~0.03-0.11 of the grid across seeds). The
    # floor sits just below that natural range so it only fires on a genuinely
    # near-empty map (bad island_radius/sea_level), never on a small-but-valid
    # island. Lowered 0.04 -> 0.03 accordingly.
    ContractCheck(kind="min_land_fraction", hard=True,
                  params={"min": 0.03, "max": 0.85},
                  message="陆地占比超出合理范围，检查 island_radius/sea_level"),
    ContractCheck(kind="categories_placed", hard=False,
                  message="有类别放置数远低于请求数，检查 allowed_biomes/坡度是否过严"),
    ContractCheck(kind="regions_effective", hard=False,
                  message="区域覆盖未产生可观测差异，局部概率化实际未生效"),
    ContractCheck(kind="lakes_on_land", hard=True,
                  message="湖泊中心落在水体或地图外"),
    ContractCheck(kind="rivers_reach_water", hard=False,
                  message="有河流未能汇入水体，河网存在断头"),
)

_FEATURES = {
    # 山脉坐落：团块状，形成 1-2 条主山脊而非均匀散布（单位：格）
    "mountains": DistributionSpec("normal_clusters",
                                  {"cluster_count": 2, "spread": 40.0,
                                   "centre_sigma": 0.18, "min_cluster_spacing": 46.0}),
    "lakes": DistributionSpec("poisson_disk",
                              {"min_spacing": 26.0, "max_attempts_per_point": 200}),
    "rivers": DistributionSpec("uniform", {"max_attempts_per_point": 60}),
}

_MATERIALS = {
    "tree_bark": (0.25, 0.13, 0.065),
    "tree_leaves": (0.16, 0.39, 0.11),
    "tree_leaves_light": (0.34, 0.57, 0.16),
    "scatter_rock": (0.36, 0.39, 0.40),
    "detail_grass": (0.60, 0.72, 0.28),
    "detail_reed": (0.45, 0.51, 0.17),
    "lake_water": (0.055, 0.43, 0.66),
    "river_water": (0.045, 0.34, 0.61),
}

THEME = ThemeSpec(
    id="island",
    display_name="岛屿",
    description="温带海岛：沙滩海岸、草原与森林、河谷盆地、岩壁山峰、内陆湖与河网。"
                "主题契约保证植被与沙滩占陆地 55% 以上，绝不产出雪地或冰原。",
    biomes=_BIOMES,
    bands=_BANDS,
    default_biome="grassland",
    lake_biome="inland_lake",
    terrain=TerrainParams(
        width=256, height=256,
        island_radius=0.42,
        mountain_frequency=0.9,
        detail_frequency=4.5,
        valley_count=3,
        river_count=5,
        sea_level=0.22,
        beach_width=0.05,
        warp_strength=0.20,
        noise_octaves=5,
        persistence=0.55,
        lacunarity=2.05,
        lake_count=8,
        lake_mean_radius=0.045,
        lake_radius_spread=0.012,
        snow_line=1.01,      # above every possible height => never snows
        frozen_water=False,
        # Per-map rank normalization of land elevations. The ridged noise made
        # the highland fraction swing 13%-71% across seeds, so the vegetation
        # contract (combined_biome_coverage >= 0.55) failed on ~6/10 seeds.
        # Remapping land cells onto sea + (1-sea)*p**gamma by percentile rank
        # makes the fraction above any absolute band threshold seed-invariant.
        # gamma=2.0 calibrated over 35 seeds: veg+beach >= 0.677 always, peak
        # ~0.14 (mountains stay prominent), 0 combined-coverage failures.
        height_normalize="rank",
        height_rank_gamma=2.0,
    ),
    categories=_CATEGORIES,
    contract=_CONTRACT,
    feature_distributions=_FEATURES,
    materials=_MATERIALS,
    forbidden_biomes=("snow_flat", "snow_forest", "tundra", "ice_shore",
                      "peak_ice", "frozen_lake"),
)
