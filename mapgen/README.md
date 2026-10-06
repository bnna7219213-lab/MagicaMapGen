# mapgen — 主题驱动的低多边形游戏原型地图生成器

把一个游戏想法，转成可交付、可复现、引擎可消费的**设计原稿地图**。类比前后端开发里的"原型 UI"：先确定**主题**（要雪地就不能给草原），再在主题下配置**多种类别、每类多个数量**，每个类别可挂**可替换的概率分布**，并支持**局部区域**单独概率化——多层修改后输出一份定稿。

- 主交付：`*_map.json`（RA2 式瓦片网格 + 物体实例 + biome 图例，含 walkable/buildable 引擎提示）
- 3D 场景副产品：`*_scene.obj` / `.mtl` + Houdini 导入脚本
- 纯 Python 标准库，无第三方依赖

---

## 三层模型

```
主题 Theme（确定性契约）
  └── 类别 Category（一对多，可多个数量）
        └── 分布 Distribution（可替换的第三层）
              └── 参数 params
```

| 层 | 决定什么 | 举例 | 保证 |
|----|----------|------|------|
| **主题** | 出现什么 biome、允许什么类别、成品必须满足什么 | 雪地 / 岛屿 | **确定**：契约层硬校验，要雪地绝不会生成草原 |
| **类别** | 主题下的一类物体，及其数量 | 稀疏树木 / 密集树木 / 其它树木 | 一对多，每类独立数量 |
| **分布** | 这一类怎么铺开 | 正态群落 / 泊松盘 / 均匀 / 网格抖动 | **可替换**：改一个字符串即可换分布 |
| **区域** | 地图局部单独覆盖上面任意一项 | 北部密林、东部山脊 | 局部物体概率化、多层修改 |

> 概率不是定数式：分布层是随机采样，同 seed 可复现，换 seed 位置会变；但主题层是硬约束，随机永远不会突破主题。

---

## 快速开始

```bash
# 用内置主题 + 显式 seed（--out 必填，绝不写到源码目录旁）
python -m mapgen --theme snow --seed 20261002 --out deliverable/snow

# 用配置文件（推荐：设计师面对的文档就是配置）
python -m mapgen --config configs/snow_north_taiga.json --out deliverable/snow

# 探索
python -m mapgen --list-themes           # 列出主题
python -m mapgen --describe-theme snow   # 打印主题的 biome/类别/分布/契约
python -m mapgen --list-distributions    # 列出可用分布策略
python -m mapgen --version
```

**退出码**（可作 CI 信号）：`0` 成功且契约通过 · `1` 契约硬失败 · `2` 用法/配置错误 · `3` I/O 或生成异常 · `4` `map.json` 未通过 schema 校验（仅 `--validate`）。
`--strict` 把软警告也视为失败。

常用参数：`--seed` `--width` `--height` `--format`（可重复，见下）`--label`（产物文件名前缀）`--set KEY=VALUE`（覆盖单个 terrain 参数，如 `--set sea_level=0.3`，可重复）`--validate`（用 `map.schema.json` 校验产物）。

---

## 配置文件格式

配置文件反序列化成生成器实际消费的同一套 dataclass，"配置写的"与"跑出来的"之间没有缝隙；解析后的请求会原样写回报告以便复现。

```jsonc
{
  "label": "snow_north_taiga",     // 产物文件名前缀
  "theme": "snow",                 // 主题 id（必填）
  "seed": 20261002,                // 必填：主题确定 + 内容可复现的前提
  "width": 256, "height": 256,     // 覆盖主题默认网格尺寸
  "formats": ["map","csv","pgm","report","obj"],

  "terrain":   { "lake_count": 8, "river_count": 4, "island_radius": 0.46 },
  "features":  { "lakes": { "distribution": "poisson_disk", "min_spacing": 26.0 },
                 "rivers": { "distribution": "uniform" },
                 "mountains": { "distribution": "uniform" } },
  "categories": {
    "trees_dense":  { "count": 340, "distribution": "normal_clusters",
                      "cluster_count": 14, "spread": 3.4 },
    "trees_sparse": { "count": 90,  "distribution": "poisson_disk", "min_spacing": 7.0 },
    "trees_other":  { "count": 60,  "distribution": "uniform" }
  },

  "regions": [                     // 局部物体概率化：每个区域可覆盖类别/分布/数量
    { "id": "north_taiga", "shape": "rect",
      "bounds": { "x0": 0.0, "y0": 0.0, "x1": 1.0, "y1": 0.34 },
      "overrides": {
        "trees_dense":  { "count": 260, "distribution": "normal_clusters",
                          "cluster_count": 9, "spread": 4.2 },
        "trees_sparse": { "density_scale": 0.2 }
      } },
    { "id": "east_ridge", "shape": "circle",
      "bounds": { "cx": 0.74, "cy": 0.48, "r": 0.16 },
      "overrides": { "ice_boulders": { "count": 60, "distribution": "poisson_disk",
                                       "min_spacing": 4.0 } } }
  ]
}
```

- **坐标归一化**到 `[0,1]`；`shape` ∈ `rect` / `circle` / `polygon` / `all`。
- **`count` 是绝对数量**；`density_scale` 按面积缩放：类别基准数量 × 地图面积倍率 × 区域占全图面积比例 × `density_scale`。全图类别覆盖的区域比例为 1。`count` 与 `density_scale` 同时指定会在生成前报错。
- 区域覆盖里 `distribution` 与主题默认不同才会被标记为"实际改写"，避免误报。

### 网格尺寸即分辨率，不是另一种世界

`--width/--height` 改变的是同一张地图的分辨率，而非换一张地图。高度场、潮湿度、湖泊/河流半径都已用归一化坐标表达，因此随网格自由缩放；唯独**长度类分布参数**以「参考分辨率下的格数」书写，再按实际网格等比缩放：

- 主题 `terrain.length_reference_cells`（默认 256）定义这个参考分辨率。
- `poisson_disk.min_spacing`、`grid_jitter.spacing`、`normal_clusters.spread` / `min_cluster_spacing` 都按 `min(W,H) / length_reference_cells` 换算成实际格距。
- 在参考分辨率下缩放因子正好为 1.0，所以 256 格的既有产物与作者直觉完全一致；缩到 128 格时所有间距自动减半，地图是同一世界的更小采样，而不是一个湖占满 20% 画面的怪异世界。

> 因此 `--width 128` 与 `--width 256` 产出的是同一张地图的不同分辨率版本，两个主题在 32 至 1024 全尺寸区间都通过各自的主题契约（见 `tests/test_mapgen.py::TestSizeInvariance`）。

### 垂直标定：`height_amplitude` / `height_base`

高度场在掩膜之前的原始高程是 `ridge * height_amplitude + height_base`（`ridge` ∈ 约 [0,1] 的脊状多重分形）。`height_amplitude` 越大，越多面积被削顶 clamp 到 1.0，主题的高程带就会把大片区域判成裸岩/冰峰——「雪原」会长成「冰山群」。这两个参数归主题所有，用于控制「高地 vs 开阔地」的比例：

- `terrain.height_amplitude`（默认 1.35）、`terrain.height_base`（默认 0.22）。
- 例如雪地主题取 `height_amplitude=1.10` 并抬高裸岩/冰峰的高程门槛，使雪原重新成为陆地主体、冰峰降到约 14%——这是让「说雪地就给雪原」在多个 seed 上稳定成立的关键。

### 按图高度归一化：`height_normalize` / `height_rank_gamma`

振幅标定能移**均值**，但压不住**方差**：脊状噪声让岛屿每张图的高地占比在 13%–71% 间剧烈摆动，植被覆盖率契约（`combined_biome_coverage ≥ 0.55`）在约 6/10 的 seed 上硬失败——用户随便选个 seed 就拿到退出码 1，工具看起来是坏的。

`height_normalize="rank"` 用**按图百分位重映射**根治：把陆地格按高程排序，第 i 名重映射到 `sea + (1-sea) * p^gamma`（`p=(i+1)/n`）。由于映射只依赖**排名**，"高于任一绝对阈值的陆地占比"对每个 seed 都**由构造恒定**——方差被彻底消除。

- 只动陆地格，**水格原样不动** → 海岸线与陆地占比逐格保留；空间**保序** → 脊线仍读作山脉，只是高程分布被标准化。
- 纯函数、不消耗 RNG → 确定性不受影响（同 seed 逐字节一致）。
- `height_rank_gamma`：`gamma>1` 把陆地质量压向低高程（开阔低地 + 更少更尖的山峰）。岛屿标定 `gamma=2.0`（35 seed 实测：植被+沙滩恒 ≥0.677、山峰约 0.14、`combined` 零失败）。
- 雪地保持 `"none"`（其振幅标定已 10/10 稳定，代码路径不变，不被波及）。

> 注：契约是**硬保证**，任何 seed 下不达标都会以退出码 1 报出。振幅标定把雪地稳定到全 seed 通过；rank 归一化把岛屿的植被契约稳定到 40/40 seed 通过。归一化**刻意保留海岸线**，所以陆地**面积**仍随 seed 自然变化（约 0.03–0.11）——这是岛屿大小的自然差异，不是缺陷；`min_land_fraction` 下限因此标定在自然区间**之下**（0.03），只对真正退化的近空地图报警，不会误杀小而有效的岛。

---

## 内置主题

| 主题 | id | 类别（一对多） | 禁止 biome |
|------|----|----------------|-----------|
| 雪地 | `snow` | trees_sparse / trees_dense / trees_other / ice_boulders / snow_drifts / frozen_reeds | grassland, forest, beach, valley_basin, inland_lake |
| 岛屿 | `island` | 稀疏/密集/其它树木 + 岩石 + 草簇 + 芦苇 | 全部雪地 biome |

`--describe-theme <id>` 打印完整定义（biome 表、类别、分布、terrain、契约检查、静态校验问题）。

---

## 分布策略

| id | 用途 | 参数 | 产出群落 |
|----|------|------|:--------:|
| `normal_clusters` | 树林群落（RTS 经典观感），围绕若干中心高斯散布 | `cluster_count`, `spread`, `min_cluster_spacing`（以上长度单位为参考格）, `centre_sigma` | 是（带 cluster_id + 群心） |
| `poisson_disk` | 蓝噪声：均匀但互不小于 `min_spacing` | `min_spacing`（参考格）, `max_attempts_per_point` | 否 |
| `uniform` | 平坦基线随机 | `max_attempts_per_point` | 否 |
| `grid_jitter` | 规则网格 + 抖动：可读作"人工种植"（果园、行道树、雷区） | `spacing`（参考格）, `jitter`, `search_radius` | 否 |

> 长度参数（`*_spacing` / `spread`）的单位是「参考分辨率下的格数」，运行时按实际网格等比缩放（见上节）。区域覆盖里为某类别改分布时，只允许写该分布声明的参数；写错键（例如给 `normal_clusters` 类别写 `min_spacing`）会在生成前抛错，而非静默忽略。

换分布 = 改类别里的一个 `"distribution"` 字符串。新增分布：继承 `mapgen/distributions.py:Distribution`，实现 `sample_groups`，注册进 `REGISTRY`——管线其余部分不变。

---

## 契约层（主题确定性保证）

`mapgen/contract.py` 在生成后运行主题声明的检查，把"说到做不到"变成硬失败而非静默通过：

- **静态校验** `validate_theme_spec`：主题定义本身有误（未声明 biome、空类别等）→ 拒绝生成，退出码 2。
- **运行时检查**：禁止 biome 出现、陆地/水域占比、类别落地率下限、河流入水数等。硬失败 → 退出码 1。
- **反空检查探测器**：若某个覆盖率检查把全部 biome 都算进去（构造上恒为 1.0、永远不会失败），契约层会**判定它失败**——正是审计 Unity 包时批评过的"空检查"反模式，这里从机制上杜绝。
- 未知检查类型 → 大声报错，绝不静默跳过。

---

## 输出产物

`--format` 可选：`map` `csv` `pgm` `report` `obj`（默认前四个）。

| 文件 | 内容 |
|------|------|
| `*_map.json` | **主交付**：schema/generator 版本、seed、`units` 单位声明块、主题、契约结果、解析后请求、网格（RLE 编码 biome/height/river + `cell_to_world` + biome 图例含 walkable/movement_cost/buildable）、特征（湖泊、河流折线）、区域、类别（含群心）、实例（含 world 坐标、biome、slope、water_depth）、统计 |
| `*_biomes.csv` / `*_scatter.csv` | biome 网格表 / 物体散布表 |
| `*_height.pgm` | 高度场灰度图 |
| `*_scene.obj` / `.mtl` | Y-up 低多边形 3D 场景，按 biome 分组、主题调色板驱动材质 |
| `*_report.json` / `.txt` | 人类可读报告 |
| `*_Houdini_Import.md` / `*_build_hip.py` | Houdini 导入指引 + `.hip` 构建脚本 |

### 产物契约：schema、单位与版本

主交付 `map.json` 有一份正式的 JSON Schema：`mapgen/export/map.schema.json`（draft 2020-12）。项目坚持纯标准库，因此 `mapgen/validate.py` 实现了该 schema 实际用到的那一小段子集（type/required/properties/enum/const/min/max/items/$ref…），外加 JSON Schema 表达不了的语义检查（RLE 解码长度是否等于 `width*height`、biome_rle 是否只引用图例里声明的 id、实例格是否越界）。

- 生成时加 `--validate` 会对 `map.json` 做校验，违规时打印字段级错误并以**退出码 4** 返回。
- 库调用可用 `mapgen.validate.validate(doc)` 与 `_semantic_checks(doc)`，两者返回人类可读的错误列表（空表示通过）。

**单位语义自描述。** 过去单位只能靠 `cell_to_world` 散文串和 OBJ 导出器的私有假设推断（`rot` 是度还是弧度？`scale` 是相对倍率还是绝对尺寸？）。现在产物内含结构化 `units` 块，逐项声明：`length=meter`、`angle=degree`、`scale=uniform multiplier`、`instance_rot=绕 +Y 顺时针度数`、`height_quantisation=v/255`、`instance_water_depth=米，陆地恒为 0`，以及网格→世界的换算公式。

**每实例自带判定依据。** 每个实例新增 `biome`（所在格的 biome key）、`slope`（该格地形梯度）、`water_depth`（水面高出地形多少米，陆地为 0）——引擎不必再解一遍高度 RLE、也不必自己判断「这棵树是不是泡在水里」。

**版本单一来源。** `schema.SCHEMA_VERSION` 是 map.json 与 report.json 共用的唯一产物 schema 版本（两者内嵌同一份 request，一起演进）；`--version` 现打印 `mapgen <generator> (artifact schema vN)`，不再拿包版本冒充 schema 版本。`TestOutputContract` 会断言 `mapdata` 不再自带 `MAP_SCHEMA_VERSION` 常量以防漂移回归。

### schema v2：面向引擎的桥接字段

`SCHEMA_VERSION = 2` 为**加性变更**，消费者应按 `schema_version >= 2` 分支，而不是嗅探字段是否存在。

| 字段 | 内容 | 引擎用途 |
|------|------|----------|
| `grid.moisture_rle` | 0–255 量化湿度网格，`v/255` 还原 | triplanar 混合、植被色调、按湿度选物种 |
| `grid.heightmap_raw_url` | 同目录 16-bit PGM 的**相对 basename** | 无损高度场直读 TerrainData，规避 8-bit RLE 的 ~0.47 m 量化损失 |
| `grid.encoding.moisture` / `units.moisture_quantisation` | 编码与量化声明 | 自描述 |

关于 `heightmap_raw_url` 的三条硬约束（均有测试锁定）：

1. **只写相对 basename**，绝不写绝对路径——否则破坏跨机字节一致；`validate.py` 的语义检查会拒绝绝对路径或带目录的引用。
2. **写 `map` 必定同产 PGM**：请求 `--format map` 时会自动一并写出 `{label}_height.pgm`，使该字段永不指向不存在的文件。代价是 `--format map` 会多一个 128 KB（256²）的旁挂文件，这是有意为之的诚实性代价。
3. **不随请求格式集变化**：字段值由 stem 推导，因此 4 种 format 组合下 map.json 仍逐字节一致（`test_bridge_fields_survive_every_format_combination`）。

> 该字段曾因一次半完成的合并而被构建后丢弃（局部 `grid` 字典建好却未用于 `return`，`return` 里另有一份不含该字段的内联副本），导致 P0 目标静默失效。`test_heightmap_raw_url_is_present_and_resolvable` 专门锁死这个坑，并校验 PGM 峰值 > 255 以证明是真 16-bit 而非被截断的 8-bit。

---

## 确定性保证

- **同 seed 逐字节一致**：不含时间戳、不含耗时、不含绝对路径。已在两个不同输出目录验证 10 个产物全部字节相同。
- 每个类别使用 `DetRandom.fork(key)` 的独立流，互不干扰采样顺序。
- 耗时只打印到控制台，不写进任何产物。

---

## 扩展主题

新增 `mapgen/themes/<name>.py`，定义一个 `ThemeSpec`（biome 词汇、terrain 参数、类别、契约、调色板、禁止 biome），在 `mapgen/themes/__init__.py:REGISTRY` 加一行即可。管线、分布、导出层都无需改动。

---

## 测试与验证

```bash
python tests/test_mapgen.py        # 50 项，全部实跑通过
node audit_sim/sim_c2.js           # Unity 侧 CarveEdge 重叠对账（历史遗留包）
```

测试覆盖：确定性、契约（含反空检查）、分布可替换性、区域掩码边界、排他组去重、导出字节一致性等。
