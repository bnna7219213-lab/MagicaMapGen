"""mapgen test suite.

Run with:  python -m unittest discover -s tests -v
       or: python tests/test_mapgen.py

The rule this suite exists to enforce: **a test that does not run is worse than
no test**, because it creates the appearance of a quality gate. Every test here
is executed by the accompanying runner and the output is checked.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mapgen
from mapgen import MapRequest, get_theme, generate, list_themes
from mapgen.config import ConfigError, request_from_dict
from mapgen.contract import validate_theme_spec
from mapgen.distributions import (Distribution, Domain, get_distribution,
                                  list_distributions, REGISTRY)
from mapgen.export.mapdata import build_map_data
from mapgen.schema import SCHEMA_VERSION
from mapgen.rng import DetRandom
from mapgen.schema import RegionSpec

SMALL = 96
SEED = 20261002


def make(theme_id, seed=SEED, size=None, **kw):
    theme = get_theme(theme_id)
    req = MapRequest(theme_id=theme_id, seed=seed,
                     width=size, height=size, **kw).resolve(theme)
    return req, generate(req)


class TestDeterminism(unittest.TestCase):
    """同 seed 逐字节一致；换 seed 内容变化但主题不变。"""

    def test_same_seed_produces_identical_map_data(self):
        req_a, w_a = make("snow", size=SMALL)
        req_b, w_b = make("snow", size=SMALL)
        a = json.dumps(build_map_data(w_a, req_a, {}), ensure_ascii=False,
                       sort_keys=True)
        b = json.dumps(build_map_data(w_b, req_b, {}), ensure_ascii=False,
                       sort_keys=True)
        self.assertEqual(a, b, "同一 seed 必须产出完全一致的地图数据")

    def test_same_seed_identical_instances_and_biomes(self):
        _, w_a = make("island", size=SMALL)
        _, w_b = make("island", size=SMALL)
        self.assertEqual(w_a.biome, w_b.biome)
        self.assertEqual(len(w_a.instances), len(w_b.instances))
        for ia, ib in zip(w_a.instances, w_b.instances):
            self.assertEqual((ia["x"], ia["y"], ia["category"]),
                             (ib["x"], ib["y"], ib["category"]))

    def test_different_seed_changes_content_but_not_theme(self):
        """A different seed must move the world, not merely shuffle a counter.

        The previous assertion was ``assertNotEqual(A == B and C == D)`` on the lake
        count and positions, which passes as soon as the *count* differs -- so a
        generator that returned the same map with one extra lake would have passed.
        These checks compare actual geometry.
        """
        _, a = make("snow", seed=1, size=SMALL)
        _, b = make("snow", seed=2, size=SMALL)
        self.assertEqual(a.theme_id, b.theme_id)

        self.assertNotEqual(a.biome, b.biome, "换 seed 必须改变地表")

        # Lake centres must be at genuinely different places, not merely a different
        # number of lakes.
        self.assertNotEqual([(l["x"], l["y"]) for l in a.lakes],
                            [(l["x"], l["y"]) for l in b.lakes],
                            "换 seed 必须移动湖泊位置")
        for la, lb in zip(a.lakes, b.lakes):
            self.assertGreater((la["x"] - lb["x"]) ** 2 + (la["y"] - lb["y"]) ** 2,
                               1e-9, "同名湖泊不应落在同一格")

        # Terrain must differ over the land surface. Comparing every cell would be
        # dominated by open water, which is the same deep water in both maps and so
        # would mask a generator that returned an identical landscape.
        water_ids = {bi.id for bi in get_theme("snow").biomes if bi.is_water}
        land_cells = 0
        differing = 0
        for y in range(a.height):
            for x in range(a.width):
                ba, bb = a.biome[x][y], b.biome[x][y]
                if ba in water_ids and bb in water_ids:
                    continue
                land_cells += 1
                if ba != bb:
                    differing += 1
        self.assertGreater(land_cells, 0, "样本里没有陆地格子，无法比较")
        self.assertGreater(differing / land_cells, 0.5,
                           f"仅 {differing}/{land_cells} 格不同，说明换 seed 几乎没生效")

        # Instances must land in different places.
        self.assertNotEqual([(i["x"], i["y"]) for i in a.instances],
                            [(i["x"], i["y"]) for i in b.instances],
                            "换 seed 必须改变实例分布")

    def test_rng_stream_is_stable_across_instances(self):
        r1, r2 = DetRandom(999), DetRandom(999)
        for _ in range(200):
            self.assertEqual(r1.next_int(0, 10 ** 6), r2.next_int(0, 10 ** 6))
            self.assertEqual(r1.next_float(-1, 1), r2.next_float(-1, 1))

    def test_fork_is_key_order_independent(self):
        """fork(key) must depend only on the key, never on the order keys were taken.

        The old version of this test forked the same key twice and compared, then
        forked a *different* key and compared that against a fresh stream. Neither
        assertion touched ordering, so the property in the name was never actually
        checked. Here the same key is drawn from two independently-ordered key
        sequences: if fork were order-sensitive the streams would diverge.
        """
        keys_a = ["cat:trees_dense", "cat:trees_sparse", "region:north",
                  "feature:lakes", "cat:trees_other"]
        keys_b = list(reversed(keys_a))

        def draw(keys):
            return {k: [DetRandom(SEED).fork(k).next_int(0, 10 ** 6)
                        for _ in range(5)] for k in keys}

        self.assertEqual(draw(keys_a), draw(keys_b),
                         "fork 的结果不应依赖 key 的取出顺序")

        # Repeating a key must give the same stream, and a fresh generator with the
        # same key must equal it.
        first = DetRandom(SEED).fork("cat:trees_dense")
        again = DetRandom(SEED).fork("cat:trees_dense")
        self.assertEqual([first.next_int(0, 999) for _ in range(50)],
                         [again.next_int(0, 999) for _ in range(50)])

        # Distinct keys must NOT collide, otherwise every category would share a
        # stream and the "independent fork" guarantee would be worthless.
        dense = DetRandom(SEED).fork("cat:trees_dense")
        sparse = DetRandom(SEED).fork("cat:trees_sparse")
        self.assertNotEqual([dense.next_int(0, 10 ** 9) for _ in range(8)],
                            [sparse.next_int(0, 10 ** 9) for _ in range(8)],
                            "不同 key 必须派生不同的流")


class TestThemeContract(unittest.TestCase):
    """主题是确定性契约：说雪地就必须是雪地。"""

    def test_shipped_theme_specs_are_valid(self):
        for t in list_themes():
            self.assertEqual(validate_theme_spec(get_theme(t["id"])), [],
                             f"主题 {t['id']} 定义有问题")

    def test_snow_never_emits_a_forbidden_biome(self):
        _, w = make("snow")
        keys = {b.id: b.key for b in get_theme("snow").biomes}
        emitted = {keys[b] for b in w.biome_counts}
        forbidden = set(get_theme("snow").forbidden_biomes)
        self.assertEqual(emitted & forbidden, set(),
                         f"雪地出现了被禁止的地表: {emitted & forbidden}")
        self.assertNotIn("grassland", emitted)
        self.assertNotIn("forest", emitted)
        self.assertNotIn("beach", emitted)

    def test_island_never_emits_snow(self):
        _, w = make("island")
        keys = {b.id: b.key for b in get_theme("island").biomes}
        emitted = {keys[b] for b in w.biome_counts}
        self.assertEqual(emitted & set(get_theme("island").forbidden_biomes), set())
        self.assertNotIn("snow_flat", emitted)

    def test_snow_is_mostly_snow(self):
        """The actual complaint: 我要雪地，不能给我大草原。"""
        _, w = make("snow")
        land = w.stats["land_cells"]
        bc = w.stats["biome_cells"]
        snowy = sum(bc.get(k, 0) for k in
                    ("snow_flat", "snow_forest", "tundra", "ice_shore",
                     "peak_ice", "rock_snow"))
        self.assertGreaterEqual(snowy / land, 0.95,
                                "雪地表象应覆盖几乎全部陆地")
        self.assertGreaterEqual(bc.get("snow_flat", 0) / land, 0.15,
                                "必须有开阔雪原")

    def test_both_themes_pass_their_own_contract(self):
        for tid in ("snow", "island"):
            _, w = make(tid)
            self.assertTrue(w.contract["passed"],
                            f"{tid} 契约未通过: "
                            f"{json.dumps(w.contract['hard_failures'], ensure_ascii=False)}")

    def test_every_emitted_biome_id_is_declared(self):
        for tid in ("snow", "island"):
            _, w = make(tid, size=SMALL)
            declared = set(get_theme(tid).biome_ids())
            self.assertTrue(set(w.biome_counts) <= declared,
                            f"{tid} 产出了未声明的 biome")

    def test_all_instances_are_on_legal_cells(self):
        """放置规则必须真的被遵守，而不是只在配置里写着。"""
        theme = get_theme("island")
        req = MapRequest(theme_id="island", seed=SEED).resolve(theme)
        w = generate(req)
        by_key = {b.key: b.id for b in theme.biomes}
        cats = {c.id: c for c in req.categories}
        self.assertGreater(len(w.instances), 0)
        # Occupancy is shared per exclusion group, not globally: grass may sit
        # under a tree, but two solid objects may not share a cell.
        seen = {}
        for inst in w.instances:
            cat = cats[inst["category"]]
            bid = w.biome[inst["x"]][inst["y"]]
            self.assertIn(bid, {by_key[k] for k in cat.allowed_biomes},
                          f"{cat.id} 落在了不允许的 biome 上")
            self.assertLess(w.slope[inst["x"]][inst["y"]], cat.max_slope,
                            f"{cat.id} 落在了超坡度格上")
            group = cat.group()
            if group:
                key = (group, inst["x"], inst["y"])
                self.assertNotIn(key, seen,
                                 f"同一格出现了两个 {group} 组的物体: "
                                 f"{seen.get(key)} 与 {cat.id}")
                seen[key] = cat.id

    def test_no_two_solid_objects_share_a_cell_in_either_theme(self):
        for tid in ("snow", "island"):
            req, w = make(tid, size=SMALL)
            cats = {c.id: c for c in req.categories}
            solid = {}
            for inst in w.instances:
                if cats[inst["category"]].group() != "solid":
                    continue
                key = (inst["x"], inst["y"])
                self.assertNotIn(key, solid,
                                 f"{tid}: {key} 上有两个实体物体互相穿插")
                solid[key] = inst["category"]


class TestDistributions(unittest.TestCase):
    """第三层：分布可替换，且各自的统计特征必须成立。"""

    def _domain(self, n=200, seed=7):
        rng = DetRandom(seed)
        cells = set()
        while len(cells) < n * 40:
            cells.add((rng.next_int(0, n), rng.next_int(0, n)))
        return Domain(n, n, sorted(cells))

    def test_registry_exposes_the_documented_strategies(self):
        """The four shipped strategies must exist and be wired up.

        Deliberately not asserting the registry is *exactly* these four. An earlier
        revision did, which meant adding a fifth distribution turned the suite red
        for no good reason -- the test was guarding a number, not the behaviour.
        What actually matters is that every registered strategy is usable and
        self-describing.
        """
        shipped = {"grid_jitter", "normal_clusters", "poisson_disk", "uniform"}
        self.assertTrue(shipped.issubset(set(REGISTRY)),
                        f"缺少内置分布: {sorted(shipped - set(REGISTRY))}")

        # Extensibility: a strategy added later must work without touching the
        # pipeline, which means it has an id, declares its params, and samples.
        class Probe(Distribution):
            id = "test_probe_strategy"
            params = ("alpha",)
            grouped = False

            def sample_groups(self, rng, domain, count, params):
                return [list(domain.cells[:count])]

        REGISTRY[Probe.id] = Probe()
        try:
            self.assertIn(Probe.id, REGISTRY)
            dom = self._domain()
            out = get_distribution(Probe.id).sample(DetRandom(1), dom, 5, {})
            self.assertLessEqual(len(out), 5)
            described = {d["id"] for d in list_distributions()}
            self.assertIn(Probe.id, described,
                          "新分布必须自动出现在 --list-distributions 里")
        finally:
            del REGISTRY[Probe.id]
        self.assertNotIn(Probe.id, REGISTRY, "注册表不应残留测试策略")

    def test_every_registered_strategy_declares_itself(self):
        """Each strategy needs a non-empty id and a describe() the CLI can print."""
        for key, dist in REGISTRY.items():
            with self.subTest(distribution=key):
                self.assertEqual(dist.id, key,
                                 "注册表的键必须与策略的 id 一致")
                described = dist.describe()
                self.assertEqual(described["id"], key)
                self.assertIn("grouped", described)
                self.assertIsInstance(described["params"], str)

    def test_poisson_disk_honours_min_spacing(self):
        spacing = 5.0
        dom = self._domain()
        pts = get_distribution("poisson_disk").sample(
            DetRandom(3), dom, 120, {"min_spacing": spacing})
        self.assertGreater(len(pts), 20, "泊松采样应能放出可观数量")
        for i, (ax, ay) in enumerate(pts):
            for bx, by in pts[i + 1:]:
                self.assertGreaterEqual(math.hypot(ax - bx, ay - by), spacing,
                                        "泊松盘最小间距被违反")

    def test_normal_clusters_is_more_clustered_than_uniform(self):
        """正态团块的平均最近邻距离必须显著小于均匀分布。"""
        def mean_nn(pts):
            if len(pts) < 2:
                return float("inf")
            total = 0.0
            for i, (ax, ay) in enumerate(pts):
                best = min(math.hypot(ax - bx, ay - by)
                           for j, (bx, by) in enumerate(pts) if j != i)
                total += best
            return total / len(pts)

        params = {"cluster_count": 6, "spread": 2.0, "min_cluster_spacing": 12.0}
        clu = mean_nn(get_distribution("normal_clusters").sample(
            DetRandom(11), self._domain(), 180, params))
        uni = mean_nn(get_distribution("uniform").sample(
            DetRandom(11), self._domain(), 180, {}))
        self.assertLess(clu, uni * 0.85,
                        f"团块分布({clu:.2f})未比均匀分布({uni:.2f})更聚集")

    def test_grid_jitter_is_roughly_regular(self):
        dom = Domain(120, 120, [(x, y) for y in range(120) for x in range(120)])
        pts = get_distribution("grid_jitter").sample(
            DetRandom(5), dom, 100, {"spacing": 12.0, "jitter": 0.2})
        self.assertGreater(len(pts), 50)
        nn = []
        for i, (ax, ay) in enumerate(pts):
            nn.append(min(math.hypot(ax - bx, ay - by)
                          for j, (bx, by) in enumerate(pts) if j != i))
        mean = sum(nn) / len(nn)
        spread = (max(nn) - min(nn)) / mean
        self.assertGreater(mean, 6.0, "网格抖动不应退化成随机撒点")
        self.assertLess(spread, 1.2, "网格抖动的间距应大致规律")

    def test_uniform_respects_the_domain(self):
        dom = Domain(64, 64, [(x, y) for y in range(10, 20) for x in range(10, 20)])
        pts = get_distribution("uniform").sample(DetRandom(1), dom, 40, {})
        self.assertTrue(pts)
        for p in pts:
            self.assertIn(p, dom.index, "均匀分布采样越出了合法域")

    def test_empty_domain_yields_nothing_rather_than_raising(self):
        dom = Domain(16, 16, [])
        for kind in REGISTRY:
            self.assertEqual(get_distribution(kind).sample(DetRandom(1), dom, 50, {}),
                             [], f"{kind} 在空域上应返回空列表")

    def test_unknown_distribution_raises(self):
        with self.assertRaises(KeyError):
            get_distribution("gaussian_mixture_that_does_not_exist")

    def test_theme_feature_distributions_are_resolvable(self):
        for tid in ("snow", "island"):
            theme = get_theme(tid)
            for key, spec in theme.feature_distributions.items():
                self.assertIn(key, ("mountains", "lakes", "rivers"))
                get_distribution(spec.kind)   # must not raise


class TestRegions(unittest.TestCase):
    """局部物体概率化：区域覆盖必须产生可观测的差异。"""

    CFG = {
        "theme": "snow", "seed": SEED, "width": SMALL, "height": SMALL,
        "regions": [{
            "id": "north", "shape": "rect",
            "bounds": {"x0": 0.0, "y0": 0.0, "x1": 1.0, "y1": 0.4},
            "overrides": {"trees_dense": {"count": 200,
                                          "distribution": "poisson_disk",
                                          "min_spacing": 3.0}},
        }],
    }

    def test_region_instances_are_labelled_and_inside_the_region(self):
        req = request_from_dict(dict(self.CFG)).resolve(get_theme("snow"))
        w = generate(req)
        inside = [i for i in w.instances if i.get("region") == "north"]
        self.assertGreater(len(inside), 0, "区域覆盖没有产生任何实例")
        for i in inside:
            self.assertEqual(i["category"], "trees_dense")
            self.assertLessEqual(i["v"], 0.4 + 1e-9,
                                 "标记为 north 的实例落在了区域外")

    def test_region_override_actually_changes_the_distribution(self):
        req = request_from_dict(dict(self.CFG)).resolve(get_theme("snow"))
        w = generate(req)
        rows = {(s["category"], s["region"]): s for s in w.category_summary}
        self.assertEqual(rows[("trees_dense", "north")]["distribution"],
                         "poisson_disk")
        self.assertEqual(rows[("trees_dense", "")]["distribution"],
                         "normal_clusters",
                         "区域外应仍用主题默认分布")

    def test_base_population_is_excluded_from_overriding_regions(self):
        req = request_from_dict(dict(self.CFG)).resolve(get_theme("snow"))
        w = generate(req)
        base = [i for i in w.instances
                if i["category"] == "trees_dense" and not i.get("region")]
        self.assertTrue(base)
        for i in base:
            self.assertGreater(i["v"], 0.4,
                               "基础群落不应落在被区域覆盖的范围内")

    def test_regions_effective_check_flags_a_dead_region(self):
        cfg = {
            "theme": "snow", "seed": SEED, "width": SMALL, "height": SMALL,
            "regions": [{"id": "corner", "shape": "rect",
                         "bounds": {"x0": 0.0, "y0": 0.0, "x1": 0.02, "y1": 0.02},
                         "overrides": {"trees_dense": {"count": 50}}}],
        }
        req = request_from_dict(cfg).resolve(get_theme("snow"))
        w = generate(req)
        check = next(r for r in w.contract["results"]
                     if r["kind"] == "regions_effective")
        self.assertFalse(check["passed"],
                         "几乎全是海洋的角落区域应被标记为未生效")

    def test_circle_and_polygon_regions_rasterise(self):
        for shape, bounds in (("circle", {"cx": 0.5, "cy": 0.5, "r": 0.2}),
                              ("polygon", {"points": [[0.3, 0.3], [0.7, 0.3],
                                                      [0.5, 0.7]]})):
            r = RegionSpec(id="r", shape=shape, bounds=bounds)
            self.assertTrue(r.contains(0.5, 0.45), f"{shape} 未覆盖其内部点")
            self.assertFalse(r.contains(0.02, 0.02), f"{shape} 覆盖了外部点")


class TestContractTeeth(unittest.TestCase):
    """契约必须真的有牙齿：能抓到人为破坏，而不是恒真。"""

    def test_check_is_not_vacuous_for_full_biome_sets(self):
        theme = get_theme("snow")
        land_keys = [b.key for b in theme.biomes if not b.is_water]
        from mapgen.schema import ContractCheck
        req = MapRequest(theme_id="snow", seed=SEED, width=SMALL,
                         height=SMALL).resolve(theme)
        w = generate(req)
        from mapgen.contract import run_contract, CheckResult
        from dataclasses import replace
        bogus = replace(theme, contract=(
            ContractCheck(kind="combined_biome_coverage", hard=True,
                          params={"biomes": tuple(land_keys),
                                  "min_fraction_of_land": 0.5}),))
        bogus_req = replace(req, theme=bogus)
        rep = run_contract(w, bogus_req)
        vac = [r for r in rep.results if r.details.get("vacuous")]
        self.assertTrue(vac, "覆盖全部陆地 biome 的检查必须被判为无效")
        self.assertFalse(vac[0].passed)

    def test_empty_biome_coverage_set_fails(self):
        theme = get_theme("snow")
        from mapgen.schema import ContractCheck
        from mapgen.contract import run_contract
        from dataclasses import replace
        req = MapRequest(theme_id="snow", seed=SEED,
                         width=SMALL, height=SMALL).resolve(theme)
        world = generate(req)
        bogus = replace(theme, contract=(ContractCheck(
            kind="combined_biome_coverage", params={"biomes": [],
                                                    "min_fraction_of_land": 0.0}),))
        result = run_contract(world, replace(req, theme=bogus)).results[0]
        self.assertFalse(result.passed)
        self.assertTrue(result.details["empty"])

    def test_unknown_check_kind_fails_loudly(self):
        theme = get_theme("snow")
        from mapgen.schema import ContractCheck
        from mapgen.contract import run_contract
        from dataclasses import replace
        req = MapRequest(theme_id="snow", seed=SEED,
                         width=SMALL, height=SMALL).resolve(theme)
        w = generate(req)
        bogus = replace(theme, contract=(
            ContractCheck(kind="totally_made_up_check", hard=True),))
        rep = run_contract(w, replace(req, theme=bogus))
        self.assertFalse(rep.passed)
        self.assertIn("totally_made_up_check",
                      rep.hard_failures[0].message)

    def test_injected_foreign_biome_is_caught(self):
        """Simulate the failure mode found in the earlier Unity audit.

        Uses an id the theme never declares. (Both shipped themes reuse biome
        ids 0-8, so injecting *another theme's* id would be a valid biome here
        and the check would correctly stay silent.)
        """
        req, w = make("snow", size=SMALL)
        foreign_id = 99
        self.assertNotIn(foreign_id, get_theme("snow").biome_ids())
        for y in range(0, 4):
            for x in range(0, 4):
                w.biome[x][y] = foreign_id
        from mapgen.terrain import count_biomes
        from mapgen.contract import run_contract
        count_biomes(w)
        rep = run_contract(w, req)
        kinds = {r.kind for r in rep.results if not r.passed}
        self.assertIn("all_biomes_known", kinds,
                      "注入外来 biome 必须被 all_biomes_known 抓到")
        self.assertFalse(rep.passed, "注入外来 biome 必须导致契约硬失败")
        detail = next(r for r in rep.results if r.kind == "all_biomes_known")
        self.assertIn(foreign_id, detail.details["stray_biome_ids"])

    def test_lake_level_never_exceeds_the_theme_ceiling(self):
        """The mountaintop-lake artefact from the previous implementation."""
        for tid in ("snow", "island"):
            req, w = make(tid)
            ceiling = req.terrain.lake_max_center_height
            for lk in w.lakes:
                self.assertLessEqual(lk["level"], ceiling + 1e-9,
                                     f"{tid} 湖 {lk['id']} 水位 {lk['level']:.3f} "
                                     f"超过上限 {ceiling}")
            self.assertEqual(len(w.lakes), req.terrain.lake_count,
                             f"{tid} 湖泊数与请求不符")

    def test_every_river_reaches_water(self):
        for tid in ("snow", "island"):
            req, w = make(tid)
            self.assertEqual(len(w.rivers), req.terrain.river_count,
                             f"{tid} 请求 {req.terrain.river_count} 条河流，"
                             f"实际只产出 {len(w.rivers)} 条")
            for r in w.rivers:
                self.assertTrue(r["reached_water"],
                                f"{tid} 河流 {r['id']} 未汇入水体")
                self.assertGreaterEqual(r["length"], 6, "河流过短，实为水坑")

    def test_category_shortfall_is_reported_not_swallowed(self):
        theme = get_theme("snow")
        # Demand far more trees than any land could hold.
        req = MapRequest(theme_id="snow", seed=SEED, width=SMALL, height=SMALL,
                         category_overrides={"trees_dense": {"count": 100000}},
                         ).resolve(theme)
        w = generate(req)
        check = next(r for r in w.contract["results"]
                     if r["kind"] == "categories_placed")
        self.assertFalse(check["passed"], "无法完成的请求必须被报告")
        short = {s["category"] for s in check["details"]["shortfalls"]}
        self.assertIn("trees_dense", short)


class TestConfig(unittest.TestCase):
    def test_missing_seed_is_rejected(self):
        with self.assertRaises(ConfigError):
            request_from_dict({"theme": "snow"})

    def test_missing_theme_is_rejected(self):
        with self.assertRaises(ConfigError):
            request_from_dict({"seed": 1})

    def test_bad_region_shape_is_rejected(self):
        with self.assertRaises(ConfigError):
            request_from_dict({"theme": "snow", "seed": 1, "regions": [
                {"id": "r", "shape": "banana", "bounds": {}}]})

    def test_inverted_rect_is_rejected(self):
        with self.assertRaises(ConfigError):
            request_from_dict({"theme": "snow", "seed": 1, "regions": [
                {"id": "r", "shape": "rect",
                 "bounds": {"x0": 0.8, "x1": 0.2}}]})

    def test_degenerate_polygon_is_rejected(self):
        with self.assertRaises(ConfigError):
            request_from_dict({"theme": "snow", "seed": 1, "regions": [
                {"id": "r", "shape": "polygon",
                 "bounds": {"points": [[0, 0], [1, 1]]}}]})

    def test_unknown_format_is_rejected(self):
        with self.assertRaises(ConfigError):
            request_from_dict({"theme": "snow", "seed": 1, "formats": ["pdf"]})

    def test_unknown_theme_raises_keyerror(self):
        with self.assertRaises(KeyError):
            get_theme("atlantis")

    def test_area_scaling_is_applied_and_explicit_count_is_absolute(self):
        theme = get_theme("snow")
        base = MapRequest(theme_id="snow", seed=SEED).resolve(theme)
        half = MapRequest(theme_id="snow", seed=SEED, width=128,
                          height=128).resolve(theme)
        base_cat = next(c for c in base.categories if c.id == "trees_dense")
        half_cat = next(c for c in half.categories if c.id == "trees_dense")
        self.assertAlmostEqual(half_cat.count / base_cat.count, 0.25, delta=0.02,
                               msg="128x128 的类别数量应按面积缩放到 1/4")

        pinned = MapRequest(theme_id="snow", seed=SEED, width=128, height=128,
                            category_overrides={"trees_dense": {"count": 77}},
                            ).resolve(theme)
        self.assertEqual(next(c for c in pinned.categories
                              if c.id == "trees_dense").count, 77,
                         "显式 count 必须是绝对值，不被面积缩放")

    def test_unknown_feature_override_is_rejected(self):
        theme = get_theme("snow")
        with self.assertRaises(KeyError):
            MapRequest(theme_id="snow", seed=SEED,
                       feature_overrides={"volcanoes": {}}).resolve(theme)

    def test_invalid_dimensions_and_category_ids_fail_during_resolve(self):
        theme = get_theme("snow")
        for value in (0, -1):
            with self.subTest(width=value), self.assertRaises(ValueError):
                MapRequest(theme_id="snow", seed=SEED, width=value).resolve(theme)
        with self.assertRaises(ValueError):
            MapRequest(theme_id="snow", seed=SEED,
                       category_overrides={"typo_category": {"count": 2}}).resolve(theme)
        with self.assertRaises(ValueError):
            MapRequest(theme_id="snow", seed=SEED, regions=(
                RegionSpec(id="same"), RegionSpec(id="same"))).resolve(theme)

    def test_region_density_scale_uses_region_area(self):
        theme = get_theme("snow")
        base = MapRequest(theme_id="snow", seed=SEED, width=SMALL,
                          height=SMALL).resolve(theme)
        cat = next(c for c in base.categories if c.id == "trees_dense")
        half_count = cat.overridden({"density_scale": 0.5}, area_fraction=0.5).count
        self.assertEqual(half_count, round(cat.count * 0.25))

    def test_count_and_density_scale_conflict_is_rejected(self):
        with self.assertRaises(ValueError):
            MapRequest(theme_id="snow", seed=SEED,
                       category_overrides={"trees_dense":
                                           {"count": 2, "density_scale": 0.5}}
                       ).resolve(get_theme("snow"))

    def test_set_values_are_type_checked(self):
        from mapgen.cli import _apply_sets
        req = MapRequest(theme_id="snow", seed=SEED)
        with self.assertRaises(ConfigError):
            _apply_sets(req, ["frozen_water=0.5"])
        with self.assertRaises(ConfigError):
            _apply_sets(req, ["lake_count=1.5"])

    def test_cli_rejects_invalid_dimensions_and_set_types_with_usage_exit(self):
        import contextlib
        import io
        import tempfile
        from mapgen.cli import main
        with tempfile.TemporaryDirectory(prefix="mapgen_invalid_cli_") as out_dir:
            for args in (("--theme", "snow", "--seed", "1", "--width", "0",
                          "--out", out_dir),
                         ("--theme", "snow", "--seed", "1", "--set",
                          "frozen_water=0.5", "--out", out_dir),
                         ("--theme", "snow", "--seed", "1", "--set",
                          "extra=bad", "--out", out_dir)):
                with self.subTest(args=args), contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(main(list(args)), 2)

    def test_config_file_round_trips(self):
        """The shipped example config must stay loadable.

        This used to ``skipTest`` when the file was missing, so deleting or renaming
        it turned the test silently green on CI. A shipped sample is part of the
        contract with users, so absence is a failure.
        """
        path = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "configs", "snow_north_taiga.json")
        self.assertTrue(os.path.isfile(path),
                        f"示例配置缺失，README 与文档都引用了它: {path}")
        req = mapgen.load_config(path)
        self.assertEqual(req.theme_id, "snow")
        self.assertEqual(len(req.regions), 3)


class TestExport(unittest.TestCase):
    def test_map_json_is_self_describing_and_rle_decodes(self):
        req, w = make("snow", size=SMALL)
        data = build_map_data(w, req, {})
        g = data["grid"]
        self.assertEqual(g["width"], SMALL)
        self.assertEqual(g["scan_order"].split()[0], "row-major,")
        self.assertIn("cell_to_world", g)

        legend = {row["id"]: row for row in g["biome_legend"]}
        flat = []
        for value, run in g["biome_rle"]:
            self.assertIn(value, legend, "RLE 中出现图例外的 biome id")
            flat.extend([value] * run)
        self.assertEqual(len(flat), SMALL * SMALL, "RLE 解码长度必须等于格数")

        # Row-major (y outer, x inner) must match the internal [x][y] grid.
        for y in range(SMALL):
            for x in range(SMALL):
                self.assertEqual(flat[y * SMALL + x], w.biome[x][y],
                                 f"({x},{y}) 的 RLE 解码与网格不一致")

    def test_artifacts_have_verifiable_content(self):
        """Read the artifacts back and check they describe this map.

        Byte-equality across runs is necessary but not sufficient: every format could
        be empty and still be perfectly reproducible. These assertions confirm the
        table, the raster and the geometry actually carry the generated content.
        """
        from dataclasses import replace
        import shutil
        import tempfile
        from mapgen.export import write_outputs

        req, w = make("snow", size=SMALL)
        d = tempfile.mkdtemp(prefix="mapgen_content_")
        try:
            req = replace(req, request=replace(req.request,
                formats=("map", "csv", "pgm", "report", "obj")))
            outs = write_outputs(w, req, d, "c", elapsed_ms=1.0)
            doc = build_map_data(w, req, {})

            # ---- CSV: one row per cell, values agree with the grid ----------
            with open(outs["biomes_csv"], "r", encoding="utf-8") as f:
                lines = f.read().strip().split("\n")
            header = lines[0].split(",")
            self.assertEqual(len(lines) - 1, SMALL * SMALL, "biomes.csv 应每格一行")
            for col in ("x", "y", "height", "biome_id", "biome_key", "region"):
                self.assertIn(col, header)
            cx, cy = header.index("x"), header.index("y")
            ch, ck = header.index("height"), header.index("biome_key")
            first = lines[1].split(",")
            self.assertEqual((int(first[cx]), int(first[cy])), (0, 0), "CSV 应以 (0,0) 开头")
            probe = lines[1 + 5 * SMALL + 7].split(",")
            self.assertEqual((int(probe[cx]), int(probe[cy])), (7, 5),
                             "CSV 必须行优先 (y 外层, x 内层)")
            self.assertAlmostEqual(float(probe[ch]), w.height_map[7][5], places=3)
            legend = {b["key"]: b["id"] for b in doc["grid"]["biome_legend"]}
            self.assertEqual(int(probe[header.index("biome_id")]), legend.get(probe[ck]),
                             "biome_id 与 biome_key 必须一致")

            # ---- PGM: 16-bit, right size, and genuinely lossless ------------
            with open(outs["height_pgm"], "rb") as f:
                blob = f.read()
            self.assertTrue(blob.startswith(b"P5"), "PGM 魔数必须是 P5")
            end = blob.index(b"65535\n") + len(b"65535\n")
            dims = blob[:end].split()
            self.assertEqual(int(dims[1]), SMALL, "PGM 宽应等于网格宽")
            self.assertEqual(int(dims[2]), SMALL, "PGM 高应等于网格高")
            self.assertEqual(int(dims[3]), 65535, "maxval 必须是 65535（无损）")
            payload = blob[end:]
            self.assertEqual(len(payload), SMALL * SMALL * 2, "16-bit 每样本 2 字节")
            peak = max(int.from_bytes(payload[i:i + 2], "little")
                       for i in range(0, len(payload), 2))
            self.assertGreater(peak, 255, "峰值应超过 8-bit 上限，否则高度被截断")
            at = (5 * SMALL + 7) * 2
            self.assertAlmostEqual(
                int.from_bytes(payload[at:at + 2], "little") / 65535.0,
                w.height_map[7][5], places=3,
                msg="16-bit PGM 应比 8-bit RLE 更接近真实高度")

            # ---- OBJ: named objects, basename material ref, real geometry ---
            with open(outs["obj"], "r", encoding="utf-8") as f:
                obj_text = f.read()
            with open(outs["mtl"], "r", encoding="utf-8") as f:
                mtl_text = f.read()

            self.assertIn("mtllib c_scene.mtl", obj_text, "OBJ 必须以 basename 引用材质库")
            self.assertNotIn(d.replace("\\", "/"), obj_text, "OBJ 不得包含绝对路径")
            for name in ("Island_Terrain", "Ocean_Surface",
                         "Inland_Lake_Water", "River_Network"):
                self.assertIn("o " + name, obj_text, "OBJ 缺少 object " + name)
            for cat in doc["categories"]:
                self.assertIn("o Scatter_" + cat["category"], obj_text,
                              "OBJ 缺少类别 object Scatter_" + cat["category"])

            verts = sum(1 for l in obj_text.splitlines() if l.startswith("v "))
            faces = sum(1 for l in obj_text.splitlines() if l.startswith("f "))
            self.assertGreater(verts, SMALL, "OBJ 顶点过少，地形没有真正生成")
            # A (W-1)x(H-1) quad grid needs at least 2 triangles per cell.
            self.assertGreaterEqual(faces, 2 * (SMALL - 1) * (SMALL - 1),
                                    "OBJ 面数不足，地形网格不完整")
            self.assertIn("newmtl", mtl_text, "MTL 应声明材质")
            used = {l.split()[1] for l in obj_text.splitlines() if l.startswith("usemtl ")}
            declared = {l.split()[1] for l in mtl_text.splitlines() if l.startswith("newmtl ")}
            self.assertTrue(used, "OBJ 没有任何 usemtl")
            self.assertTrue(used.issubset(declared),
                            "OBJ 引用了 MTL 未声明的材质: %r" % sorted(used - declared))
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_map_json_has_no_timestamp(self):
        """No wall-clock value may reach the artifact, whatever the field is called.

        The old version blacklisted the substrings "timestamp", "generated_at" and
        "created". That only stops someone *naming* a field that way -- an ISO date
        stored under a key like "built" sails straight through, which is exactly the
        failure byte-identity depends on. So this inspects the values, not the names.
        """
        req, w = make("snow", size=SMALL)
        doc = build_map_data(w, req, {})

        patterns = [
            (r"\d{4}-\d{2}-\d{2}", "ISO date"),
            (r"\d{2}:\d{2}:\d{2}", "clock time"),
            (r"\b1[6-9]\d{8}\b", "epoch seconds"),
            (r"\b1[6-9]\d{11}\b", "epoch millis"),
        ]
        offenders = []

        def walk(node, path):
            if isinstance(node, dict):
                for k, v in node.items():
                    walk(v, path + "." + str(k))
            elif isinstance(node, list):
                for i, v in enumerate(node):
                    walk(v, "%s[%d]" % (path, i))
            elif isinstance(node, str):
                for pattern, label in patterns:
                    if re.search(pattern, node):
                        offenders.append((path, node[:40], label))
            elif isinstance(node, float) and node > 1.5e9:
                offenders.append((path, node, "epoch seconds"))

        walk(doc, "")
        self.assertEqual(offenders, [],
                         "产物中出现疑似时间值，会破坏逐字节可复现: %r" % (offenders[:5],))

        # Structural half: no run-time bookkeeping may appear at all.
        raw = json.dumps(doc, ensure_ascii=False)
        for bad in ("timestamp", "generated_at", "elapsed", "duration"):
            self.assertNotIn(bad, raw, "map.json 不应含运行期字段 %r" % bad)

    def test_every_category_appears_in_the_summary(self):
        req, w = make("island", size=SMALL)
        data = build_map_data(w, req, {})
        summarised = {c["category"] for c in data["categories"]}
        self.assertEqual(summarised, {c.id for c in req.categories})

    def test_instances_carry_engine_consumable_fields(self):
        req, w = make("island", size=SMALL)
        data = build_map_data(w, req, {})
        self.assertTrue(data["instances"])
        for inst in data["instances"][:50]:
            for key in ("id", "cat", "type", "x", "y", "world", "rot", "scale"):
                self.assertIn(key, inst)
            self.assertEqual(len(inst["world"]), 3)

    def test_theme_palette_drives_every_material(self):
        """No hardcoded colours in the exporter (a fault in the old pipeline)."""
        from mapgen.export.obj import collect_materials, missing_materials
        for tid in ("snow", "island"):
            req = MapRequest(theme_id=tid, seed=SEED).resolve(get_theme(tid))
            mats = collect_materials(req)
            theme = get_theme(tid)
            declared = set(theme.materials) | {(b.material or b.key)
                                               for b in theme.biomes}
            self.assertEqual(set(mats), declared,
                             f"{tid} 导出了主题未声明的材质")
            self.assertEqual(missing_materials(req), [],
                             f"{tid} 有类别引用了主题未定义的材质")
            neutral = [(k, v) for k, v in mats.items() if v == (0.5, 0.5, 0.5)]
            self.assertEqual(neutral, [], f"{tid} 出现灰色兜底材质: {neutral}")


class TestPortability(unittest.TestCase):
    """产物必须与生成它的机器/目录无关，否则无法交付给客户端。"""

    def test_artifacts_are_identical_in_two_different_directories(self):
        import shutil
        import tempfile
        from mapgen.export import write_outputs

        theme = get_theme("snow")
        req = MapRequest(theme_id="snow", seed=SEED, width=SMALL, height=SMALL,
                         formats=("map", "csv", "pgm", "obj")).resolve(theme)
        dirs = [tempfile.mkdtemp(prefix="mapgen_a_"),
                tempfile.mkdtemp(prefix="mapgen_b_")]
        try:
            digests = []
            for d in dirs:
                w = generate(req)
                outs = write_outputs(w, req, d, "m", elapsed_ms=1234.5)
                blob = {}
                for name, path in sorted(outs.items()):
                    with open(path, "rb") as f:
                        blob[name] = hashlib.sha256(f.read()).hexdigest()
                digests.append(blob)
            self.assertEqual(digests[0], digests[1],
                             "同 seed 在不同输出目录必须产出逐字节一致的产物")
        finally:
            for d in dirs:
                shutil.rmtree(d, ignore_errors=True)

    def test_no_absolute_paths_or_wall_clock_in_serialised_output(self):
        """No machine-specific path may appear in the artifact.

        The previous check searched for "C:\\\\", "/home/" and friends. Those literals
        are *this* machine's prefixes, so on another platform or another drive the
        test silently passed while an absolute path sat in the output. This looks for
        the shape of an absolute path instead, which is machine-independent.
        """
        req, w = make("snow", size=SMALL)
        doc = build_map_data(w, req, {})

        # Shape-based, not literal-based: a drive letter, a UNC path, or a POSIX
        # absolute path in any value.
        shapes = [
            re.compile(r"\b[A-Za-z]:[\\/]"),          # C:\ or C:/
            re.compile(r"\\\\[A-Za-z0-9_.-]+\\"),    # UNC \\server\share
            re.compile(r"(?<![\w.])/(?:home|Users|usr|var|tmp|opt|mnt|media)/"),
            re.compile(r"(?<![\w.])/(?:etc|proc|sys|dev)/"),
        ]
        offenders = []

        def walk(node, path):
            if isinstance(node, dict):
                for k, v in node.items():
                    walk(v, path + "." + str(k))
            elif isinstance(node, list):
                for i, v in enumerate(node):
                    walk(v, "%s[%d]" % (path, i))
            elif isinstance(node, str):
                for rx in shapes:
                    if rx.search(node):
                        offenders.append((path, node[:60]))
                        break

        walk(doc, "")
        self.assertEqual(offenders, [],
                         "map.json 含机器相关路径，无法跨机复现: %r" % (offenders[:5],))

        # The positive statement of the same property: recorded artifact names must
        # be bare basenames, which is what makes them relocatable.
        for region in doc.get("regions", []):
            self.assertNotIn("/", region.get("id", ""))
        raw = json.dumps(doc, ensure_ascii=False)
        for bad in ("elapsed", "timestamp"):
            self.assertNotIn(bad, raw)
        # And this machine's real prefix must genuinely be absent, now that the
        # shape-based check above is the primary guard.
        self.assertNotIn(os.path.abspath("."), raw)

    def test_elapsed_time_does_not_leak_into_stats(self):
        """Run duration must not reach the artifact through any key.

        The old assertion checked two hardcoded key names, so it passed no matter
        what ``stats`` actually contained -- a genuine leak under a different name
        would have sailed through. Now every key and every value is inspected.
        """
        req, w = make("snow", size=SMALL)
        stats = w.stats

        duration_words = ("elapsed", "duration", "took", "seconds", "millis",
                          "runtime", "timing", "generated_at", "timestamp")
        bad_keys = [k for k in stats
                    if any(word in str(k).lower() for word in duration_words)]
        self.assertEqual(bad_keys, [],
                         f"stats 出现了运行期字段: {bad_keys}")

        # Stats must be made only of countable things: numbers and nested counters.
        for key, value in stats.items():
            with self.subTest(stat=key):
                self.assertIsInstance(
                    value, (int, float, dict),
                    f"stats[{key!r}] = {value!r} 不是可复现的量（{type(value).__name__}）")

        # And the documented core keys must all be present, so the check above
        # cannot pass on an empty or gutted stats dict.
        for key in ("total_cells", "land_cells", "water_cells", "land_fraction",
                    "instance_count"):
            self.assertIn(key, stats, f"stats 缺少核心字段 {key!r}")

    def test_map_bytes_ignore_format_set_and_output_directory(self):
        import shutil
        import tempfile
        from dataclasses import replace
        from mapgen.export import write_outputs

        theme = get_theme("snow")
        base = MapRequest(theme_id="snow", seed=SEED, width=SMALL,
                          height=SMALL).resolve(theme)
        world = generate(base)
        combinations = (("map",), ("map", "csv"), ("map", "pgm"),
                        ("map", "obj"), ("map", "csv", "pgm", "report", "obj"))
        dirs = [tempfile.mkdtemp(prefix="mapgen_matrix_a_"),
                tempfile.mkdtemp(prefix="mapgen_matrix_b_")]
        try:
            hashes = []
            for formats in combinations:
                for out_dir in dirs:
                    req = replace(base, request=replace(base.request, formats=formats))
                    outputs = write_outputs(world, req, out_dir, "matrix", elapsed_ms=1234.5)
                    with open(outputs["map_json"], "rb") as f:
                        hashes.append(hashlib.sha256(f.read()).hexdigest())
            self.assertEqual(len(set(hashes)), 1,
                             "5 种 format 组合 × 2 个目录必须得到相同 map.json")
        finally:
            for out_dir in dirs:
                shutil.rmtree(out_dir, ignore_errors=True)


class TestSizeInvariance(unittest.TestCase):
    """地图尺寸是同一 world 的不同分辨率，而非另一种世界 (P1-5)。"""

    SIZES = (32, 48, 64, 96, 128, 192, 256, 384, 512, 768, 1024)

    def _passes(self, theme_id, size):
        req, w = make(theme_id, size=size)
        return w.contract["passed"], w.contract.get("hard_failures", [])

    def test_theme_contract_holds_across_grid_sizes(self):
        for tid in ("snow", "island"):
            for s in self.SIZES:
                passed, fails = self._passes(tid, s)
                self.assertTrue(
                    passed,
                    f"{tid} 在 {s}x{s} 自身契约失败: {[f['kind'] for f in fails]}")

    def test_reference_grid_is_scale_one(self):
        from dataclasses import replace
        from mapgen.schema import grid_length_scale
        tp = get_theme("snow").terrain
        self.assertEqual(grid_length_scale(tp), 1.0,
                         "参考分辨率下长度缩放必须为 1，否则 256 产物会漂移")
        half = replace(tp, width=128, height=128)
        self.assertAlmostEqual(grid_length_scale(half), 0.5, places=6,
                               msg="半分辨率下长度应减半")

    def test_lake_window_guard_rejects_unreachable_sea_level(self):
        from mapgen.config import ConfigError
        req = MapRequest(theme_id="snow", seed=SEED, width=SMALL, height=SMALL,
                         terrain_overrides={"sea_level": 0.95})
        with self.assertRaises((ValueError, ConfigError)):
            req.resolve(get_theme("snow"))

    def test_region_override_param_must_match_distribution(self):
        # trees_dense 是 normal_clusters，没有 min_spacing；只写 min_spacing 不改
        # 分布应被当成写错键而拒绝，而不是静默忽略。
        cat = get_theme("snow").category("trees_dense")
        with self.assertRaises(ValueError):
            cat.overridden({"min_spacing": 5.0})
        # 改成 poisson_disk 后 min_spacing 才合法。
        self.assertIsNotNone(
            cat.overridden({"distribution": "poisson_disk", "min_spacing": 5.0}))


class TestHeightNormalization(unittest.TestCase):
    """按图高度归一化：消除岛屿主题的 seed 方差（高地占比曾 13%-71% 摆动）。"""

    def test_snow_keeps_raw_field_island_uses_rank(self):
        # 雪地靠手标 amplitude 已 10/10 稳定，必须保持 "none"（代码路径不变）；
        # 岛屿用 rank 归一化。两者分野是显式的，防止误改波及雪地。
        self.assertEqual(get_theme("snow").terrain.height_normalize, "none")
        self.assertEqual(get_theme("island").terrain.height_normalize, "rank")

    def test_normalize_rank_preserves_water_order_and_is_deterministic(self):
        from mapgen.terrain import _normalize_rank
        sea = 0.22
        # height[x][y]; 混合水陆
        field = [[0.10, 0.50, 0.90],
                 [0.20, 0.22, 0.70],
                 [0.05, 0.40, 1.00]]
        before = [row[:] for row in field]
        f1 = [row[:] for row in before]
        f2 = [row[:] for row in before]
        _normalize_rank(f1, sea, 2.0)
        _normalize_rank(f2, sea, 2.0)
        field = f1
        # 确定性：同输入两次结果一致
        self.assertEqual(f1, f2)
        # 水格（< sea）原样不动 -> 海岸线/陆地占比逐格保留
        for x in range(3):
            for y in range(3):
                if before[x][y] < sea:
                    self.assertAlmostEqual(field[x][y], before[x][y], places=9,
                                           msg=f"水格 ({x},{y}) 被改动")
        # 陆格全部 >= sea，且严格高于 sea（最低陆格 p=(1/n)>0）
        land_before = [(before[x][y], x, y) for x in range(3) for y in range(3)
                       if before[x][y] >= sea]
        for _h, x, y in land_before:
            self.assertGreaterEqual(field[x][y], sea)
            self.assertGreater(field[x][y], sea - 1e-12)
        # 保序：原始最高的陆格归一化后仍最高（脊线结构不被打乱）
        ranked = sorted(land_before)
        self.assertLess(field[ranked[0][1]][ranked[0][2]],
                        field[ranked[-1][1]][ranked[-1][2]])

    def test_island_highland_fraction_is_seed_invariant(self):
        # 归一化前 peak 占比在 0.13-0.71 间摆动；归一化后应被钉在窄带内。
        peaks, vegs = [], []
        VEG = {"grassland", "forest", "valley_basin", "beach"}
        for seed in (1, 42, 314159, 7, 555, 20261002):
            _req, w = make("island", seed=seed, size=SMALL)
            land = w.stats["land_cells"] or 1
            bc = w.stats["biome_cells"]
            peaks.append(bc.get("peak", 0) / land)
            vegs.append(sum(bc.get(k, 0) for k in VEG) / land)
        self.assertLess(max(peaks) - min(peaks), 0.12,
                        f"peak 占比仍随 seed 剧烈摆动: {peaks}")
        self.assertLess(max(peaks), 0.35, f"某 seed 冰峰过多: {max(peaks):.2f}")
        self.assertGreaterEqual(min(vegs), 0.55,
                                f"植被+沙滩低于契约下限: {min(vegs):.3f}")

    def test_island_contract_passes_across_seeds(self):
        # 直接回归用户的诉求：随便选 seed 都不应退出码 1。
        for seed in (1, 42, 314159, 999983, 7, 12345, 555, 8888):
            _req, w = make("island", seed=seed, size=SMALL)
            self.assertTrue(
                w.contract["passed"],
                f"island seed={seed} 契约失败: "
                f"{[f['kind'] for f in w.contract['hard_failures']]}")


class TestOutputContract(unittest.TestCase):
    """产物契约：版本单一来源、单位自描述、实例字段齐全、schema 可校验。"""

    def test_version_constants_are_not_duplicated(self):
        from mapgen import schema as schema_mod
        from mapgen.export import mapdata
        self.assertFalse(hasattr(mapdata, "MAP_SCHEMA_VERSION"),
                         "map.json 必须复用 schema.SCHEMA_VERSION，避免两处漂移")
        self.assertIsInstance(schema_mod.SCHEMA_VERSION, int)
        self.assertGreaterEqual(schema_mod.SCHEMA_VERSION, 1)

    def test_map_and_report_share_one_schema_version(self):
        import shutil
        import tempfile
        from mapgen.export import write_outputs
        from mapgen.schema import SCHEMA_VERSION

        req, w = make("snow", size=SMALL)
        d = tempfile.mkdtemp(prefix="mapgen_ver_")
        try:
            outs = write_outputs(w, req, d, "v", elapsed_ms=1.0)
            with open(outs["map_json"], "r", encoding="utf-8") as f:
                map_v = json.load(f)["schema_version"]
            with open(outs["report_json"], "r", encoding="utf-8") as f:
                rep_v = json.load(f)["schema_version"]
            self.assertEqual(map_v, SCHEMA_VERSION)
            self.assertEqual(rep_v, SCHEMA_VERSION,
                             "map.json 与 report.json 的 schema 版本必须一致")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_units_block_declares_every_ambiguous_field(self):
        req, w = make("snow", size=SMALL)
        units = build_map_data(w, req, {})["units"]
        for key in ("length", "angle", "scale", "instance_rot",
                    "height_quantisation", "instance_water_depth"):
            self.assertTrue(units.get(key), f"units 缺少 {key} 的单位声明")
        self.assertEqual(units["angle"], "degree")
        self.assertEqual(units["length"], "meter")

    def test_instances_carry_biome_slope_and_water_depth(self):
        for tid in ("snow", "island"):
            req, w = make(tid, size=SMALL)
            data = build_map_data(w, req, {})
            self.assertTrue(data["instances"], f"{tid} 没有实例可供检查")
            keys = {b.key for b in get_theme(tid).biomes}
            for rec in data["instances"]:
                self.assertIn("biome", rec)
                self.assertIn("slope", rec)
                self.assertIn("water_depth", rec)
                self.assertIn(rec["biome"], keys,
                              f"{tid}: 实例 biome {rec['biome']!r} 不在主题图例中")
                self.assertGreaterEqual(rec["water_depth"], 0.0)

    def test_generated_map_passes_its_own_schema(self):
        from mapgen.validate import load_schema, validate, _semantic_checks
        schema = load_schema()
        for tid in ("snow", "island"):
            req, w = make(tid, size=SMALL)
            data = build_map_data(w, req, {})
            errors = validate(data, schema) + _semantic_checks(data)
            self.assertEqual(errors, [], f"{tid} 产物不满足 map.schema.json: {errors[:3]}")

    def test_validator_catches_a_broken_map(self):
        import copy
        from mapgen.validate import load_schema, validate, _semantic_checks
        schema = load_schema()
        req, w = make("snow", size=SMALL)
        data = build_map_data(w, req, {})

        missing = copy.deepcopy(data)
        del missing["instances"][0]["water_depth"]
        self.assertTrue(validate(missing, schema),
                        "删掉必填字段必须被 schema 抓到")

        negative = copy.deepcopy(data)
        negative["instances"][0]["water_depth"] = -1.0
        self.assertTrue(validate(negative, schema),
                        "负的水深必须被 schema 抓到")

        skewed = copy.deepcopy(data)
        skewed["grid"]["biome_rle"][0][1] += 3
        self.assertTrue(_semantic_checks(skewed),
                        "RLE 解码长度与 width*height 不符必须被语义检查抓到")


class TestEngineBridgeFields(unittest.TestCase):
    """面向引擎消费的桥接字段 (schema v2)：湿度网格 + 无损高度图旁挂文件。

    回归背景：这些字段曾因一次半完成的合并而被构建后丢弃——`grid` 局部字典
    建好却没被 return 使用，return 里另有一份不含该字段的内联副本。下面第一个
    测试专门锁死这个坑。
    """

    def _write(self, tmpdir, stem="b"):
        from mapgen.export import write_outputs
        req, w = make("snow", size=SMALL)
        return write_outputs(w, req, tmpdir, stem, elapsed_ms=1.0)

    def test_heightmap_raw_url_is_present_and_resolvable(self):
        import os
        import shutil
        import tempfile
        from mapgen.export.mapdata import build_map_data

        d = tempfile.mkdtemp(prefix="mapgen_bridge_")
        try:
            outputs = self._write(d)
            with open(outputs["map_json"], "r", encoding="utf-8") as f:
                doc = json.load(f)
            grid = doc["grid"]
            self.assertIn("heightmap_raw_url", grid,
                          "map.json 必须指向 16-bit PGM，否则 Unity 只能读 8-bit RLE")
            ref = grid["heightmap_raw_url"]
            self.assertEqual(ref, os.path.basename(ref),
                             "只允许写相对 basename，绝对路径会破坏跨机字节一致")
            self.assertTrue(os.path.isfile(os.path.join(d, ref)),
                            f"heightmap_raw_url 指向的 {ref} 必须真实存在")

            # PGM 必须是真 16-bit，否则"无损"名不副实。
            with open(os.path.join(d, ref), "rb") as f:
                blob = f.read()
            self.assertTrue(blob.startswith(b"P5"), "PGM 魔数/格式不对")
            header, rest = blob.split(b"65535\n", 1)
            w, h = (int(v) for v in header.split()[1:3])
            self.assertEqual((w, h), (SMALL, SMALL))
            self.assertEqual(len(rest), w * h * 2, "16-bit 每样本 2 字节")
            peak = max(int.from_bytes(rest[i:i + 2], "little")
                       for i in range(0, len(rest), 2))
            self.assertGreater(peak, 255,
                               "PGM 峰值应超过 8-bit 上限，否则高度未被真正保真")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_moisture_rle_decodes_to_the_full_grid(self):
        req, w = make("snow", size=SMALL)
        grid = build_map_data(w, req, {})["grid"]
        self.assertIn("moisture_rle", grid, "v2 必须导出逐格湿度")
        self.assertEqual(sum(r[1] for r in grid["moisture_rle"]),
                         grid["width"] * grid["height"])
        # 逐格解码后应与内存中的湿度一致（8-bit 量化误差内）。
        flat = []
        for value, run in grid["moisture_rle"]:
            flat.extend([value] * run)
        worst = 0.0
        for y in range(grid["height"]):
            for x in range(grid["width"]):
                want = w.moisture[x][y]
                got = flat[y * grid["width"] + x] / 255.0
                worst = max(worst, abs(want - got))
        self.assertLessEqual(worst, 1.0 / 255.0 + 1e-9,
                             f"湿度量化误差 {worst} 超出 8-bit 精度")

    def test_bridge_fields_survive_every_format_combination(self):
        import hashlib
        import shutil
        import tempfile
        from dataclasses import replace
        from mapgen.export import write_outputs

        base = MapRequest(theme_id="snow", seed=SEED, width=SMALL,
                          height=SMALL).resolve(get_theme("snow"))
        world = generate(base)
        combos = (("map",), ("map", "obj"), ("map", "csv"),
                  ("map", "csv", "pgm", "report", "obj"))
        digests = set()
        for formats in combos:
            for tag in ("a", "b"):
                d = tempfile.mkdtemp(prefix=f"mapgen_fmt_{tag}_")
                try:
                    req = replace(base, request=replace(base.request, formats=formats))
                    outputs = write_outputs(world, req, d, "m", elapsed_ms=1.0)
                    with open(outputs["map_json"], "rb") as f:
                        digests.add(hashlib.sha256(f.read()).hexdigest())
                finally:
                    shutil.rmtree(d, ignore_errors=True)
        self.assertEqual(len(digests), 1,
                         "新增桥接字段后 map.json 仍必须与请求格式集无关")

    def test_validator_rejects_a_bad_heightmap_reference(self):
        import copy
        from mapgen.validate import _semantic_checks
        req, w = make("snow", size=SMALL)
        from mapgen.export.mapdata import build_map_data
        doc = build_map_data(w, req, {}, heightmap_filename="snow_height.pgm")
        self.assertEqual(_semantic_checks(doc), [])
        bad = copy.deepcopy(doc)
        bad["grid"]["heightmap_raw_url"] = "C:/abs/snow_height.pgm"
        self.assertTrue(_semantic_checks(bad),
                        "绝对路径的高度图引用必须被语义检查拒绝")


class TestRegionPriority(unittest.TestCase):
    """regions[].priority: overlap attribution must be explicit, not insertion luck."""

    @staticmethod
    def _cfg(**kw):
        base = {
            "theme": "snow", "seed": SEED, "width": 64, "height": 64,
            "regions": [
                {"id": "low", "shape": "rect", "priority": 0,
                 "bounds": {"x0": 0.0, "y0": 0.0, "x1": 0.6, "y1": 0.6}},
                {"id": "high", "shape": "rect", "priority": 10,
                 "bounds": {"x0": 0.3, "y0": 0.3, "x1": 0.9, "y1": 0.9}},
            ],
        }
        base.update(kw)
        return base

    def test_higher_priority_wins_the_overlap(self):
        req = request_from_dict(self._cfg()).resolve(get_theme("snow"))
        w = generate(req)
        owner = w.region_owner
        # A cell inside both masks must be attributed to "high".
        x, y = 40, 40
        self.assertTrue(req.request.regions[0].id == "low")
        self.assertEqual(owner[x][y], "high",
                         "the higher-priority region must own the contested cell")
        # A cell only in the low region stays with it.
        self.assertEqual(owner[5][5], "low")

    def test_owner_counts_do_not_double_count(self):
        req = request_from_dict(self._cfg()).resolve(get_theme("snow"))
        w = generate(req)
        stats = w.stats["regions"]
        raw = w.stats["regions_raw_cells"]
        self.assertEqual(sorted(stats), ["high", "low"])
        self.assertEqual(set(stats), set(raw), "both count maps must cover the same ids")
        for rid in stats:
            self.assertLessEqual(stats[rid], raw[rid],
                                 "owned cells can never exceed the raw mask extent")
        self.assertEqual(sum(stats.values()),
                         sum(1 for col in w.region_owner for v in col if v),
                         "owner counts must partition the attributed cells exactly")
        # The contested band is non-empty, so at least one region must be shadowed.
        self.assertLess(stats["low"], raw["low"], "expected the low region to be shadowed")

    def test_csv_and_map_json_agree_on_attribution(self):
        import os
        import shutil
        import tempfile
        from mapgen.export import write_outputs
        from mapgen.export.mapdata import build_map_data

        req = request_from_dict(self._cfg()).resolve(get_theme("snow"))
        w = generate(req)
        doc = build_map_data(w, req, {})
        emitted = {r["id"]: r for r in doc["regions"]}
        self.assertEqual(emitted["low"]["priority"], 0)
        self.assertEqual(emitted["high"]["priority"], 10)
        self.assertTrue(emitted["low"]["overlaps"], "low is shadowed and must say so")
        self.assertEqual(emitted["low"]["cells_raw"] >= emitted["low"]["cells"], True)
        self.assertEqual(doc["schema_version"], SCHEMA_VERSION)

        d = tempfile.mkdtemp(prefix="mapgen_prio_")
        try:
            outs = write_outputs(w, req, d, "p", elapsed_ms=1.0)
            with open(outs["biomes_csv"], "r", encoding="utf-8") as f:
                lines = f.read().strip().split("\n")
            header = lines[0].split(",")
            col = header.index("region")
            rows = [ln.split(",") for ln in lines[1:]]
            rx, ry = 40, 40
            csv_region = rows[ry * 64 + rx][col]
            self.assertEqual(csv_region, w.region_owner[rx][ry],
                             "CSV attribution must match the owner grid")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_duplicate_priorities_are_rejected(self):
        cfg = self._cfg()
        cfg["regions"][1]["priority"] = 0
        with self.assertRaises(ValueError):
            request_from_dict(cfg).resolve(get_theme("snow"))

    def test_non_integer_priority_is_rejected(self):
        cfg = self._cfg()
        cfg["regions"][0]["priority"] = "high"
        with self.assertRaises((ValueError, TypeError)):
            request_from_dict(cfg).resolve(get_theme("snow"))




class TestCLIExitCodes(unittest.TestCase):
    WARN_WORD = '\u8b66\u544a'
    """The CLI is what the GUI and CI both invoke, so its exit codes are a
    real interface rather than an implementation detail. Exit codes were
    previously covered only in fragments, and --strict/--validate not at all."""

    def run_cli(self, args):
        import contextlib
        import io
        from mapgen.cli import main
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(list(args))
        return code, out.getvalue(), err.getvalue()

    def _out(self):
        import tempfile
        return tempfile.mkdtemp(prefix='mapgen_cli_')

    def test_two_on_every_configuration_error(self):
        import shutil
        d = self._out()
        cases = [
            (['--theme', 'snow', '--out', d], 'missing seed'),
            (['--theme', 'no_such_theme', '--seed', '1', '--out', d], 'unknown theme'),
            (['--theme', 'snow', '--seed', '1', '--width', '0', '--out', d], 'width 0'),
            (['--theme', 'snow', '--seed', '1', '--out', d, '--set', 'bogus=1'], 'unknown set key'),
            (['--theme', 'snow', '--seed', '1', '--out', d, '--set', 'lake_count=1.5'], 'wrong set type'),
            (['--theme', 'snow', '--seed', '1', '--out', d, '--set', 'nokey'], 'set without equals'),
            (['--theme', 'snow', '--seed', '1', '--set', 'lake_count=2'], 'missing --out'),
            (['--seed', '1', '--out', d], 'neither theme nor config'),
        ]
        for args, why in cases:
            with self.subTest(case=why):
                self.assertEqual(self.run_cli(args)[0], 2,
                                 'config error must exit 2: ' + why)
        shutil.rmtree(d, ignore_errors=True)

    def test_one_on_contract_failure_and_names_the_check(self):
        import shutil
        d = self._out()
        try:
            code, out, _ = self.run_cli([
                '--theme', 'island', '--seed', '88',
                '--width', '128', '--height', '128',
                '--out', d, '--format', 'map', '--format', 'report'])
            self.assertEqual(code, 1, 'a hard contract failure must exit 1')
            self.assertIn('min_biome_coverage', out,
                          'the summary must name the failing check')
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_four_on_schema_violation_detected_by_validate(self):
        import shutil
        from mapgen.export import mapdata
        d = self._out()
        original = mapdata.build_map_data

        def broken(world, req, request_dict=None, **kw):
            doc = original(world, req, request_dict or {}, **kw)
            doc['instances'][0]['water_depth'] = -5.0
            return doc

        try:
            mapdata.build_map_data = broken
            code, _, err = self.run_cli([
                '--theme', 'snow', '--seed', str(SEED),
                '--width', '64', '--height', '64',
                '--out', d, '--format', 'map', '--validate'])
        finally:
            mapdata.build_map_data = original
            shutil.rmtree(d, ignore_errors=True)
        self.assertEqual(code, 4, 'a schema violation must exit 4')
        self.assertIn('water_depth', err,
                      'the error must point at the offending field')

    def test_validate_passes_on_a_clean_run(self):
        import shutil
        d = self._out()
        try:
            code, out, _ = self.run_cli([
                '--theme', 'snow', '--seed', str(SEED),
                "--width", "64", "--height", "64", "--out", d,
                '--format', 'map', '--validate'])
            self.assertEqual(code, 0)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_strict_promotes_soft_warnings_to_failure(self):
        import shutil
        base_dir = self._out()
        cfg = os.path.join(base_dir, "r.json")
        with open(cfg, "w", encoding="utf-8") as f:
            json.dump({
                "theme": "snow",
                "seed": SEED,
                "width": 64, "height": 64,
                "regions": [{
                    "id": "pin",
                    "shape": "rect",
                    "bounds": {"x0": 0.0, "y0": 0.0,
                               "x1": 0.02, "y1": 0.02},
                    "overrides": {"trees_dense": {"count": 5}},
                }],
            }, f, ensure_ascii=False)
        try:
            # A region covering a sliver of open ocean changes nothing, which trips
            # the soft regions_effective check. A real warning, so --strict has
            # something to promote.
            plain_dir = os.path.join(base_dir, "plain")
            strict_dir = os.path.join(base_dir, "strict")
            def args_for(out_dir, extra):
                return ["--config", cfg, "--out", out_dir,
                        "--format", "map",
                        "--format", "report"] + extra

            plain_code, _, _ = self.run_cli(args_for(plain_dir, []))
            strict_code, _, _ = self.run_cli(args_for(strict_dir, ["--strict"]))
            self.assertEqual(plain_code, 0,
                             "sanity: without --strict a soft warning is not a failure")
            self.assertEqual(strict_code, 1,
                             "--strict must turn a soft warning into exit 1")

            # Prove the warning is real by reading the report rather than trusting
            # the console line, which always prints a warning count even at zero.
            for out_dir, expect_fail in ((plain_dir, False), (strict_dir, True)):
                report = [f for f in os.listdir(out_dir) if f.endswith("_report.json")][0]
                with open(os.path.join(out_dir, report), "r", encoding="utf-8") as f:
                    doc = json.load(f)
                self.assertTrue(doc["contract"]["warnings"],
                                "the scenario must really warn")
                self.assertFalse(doc["contract"]["hard_failures"],
                                 "warnings only; no hard failure here")
                del expect_fail
        finally:
            shutil.rmtree(base_dir, ignore_errors=True)

if __name__ == "__main__":
    unittest.main(verbosity=2)