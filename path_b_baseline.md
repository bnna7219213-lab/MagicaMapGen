# 路径 B 执行基线：mapgen → Unity 引擎消费

> 本文是路径 B（mapgen 产出通用契约，Unity 只做消费端）的执行基线。
> 状态：**阶段 0 完成（双端跑通）；阶段 1 部分完成（`regions[].priority` 已落地）；阶段 2 的 Python 半边完成（`--overlay` 增量重生成 + GUI Edit 面板）；阶段 3（Unity 编辑回环）首切片完成（`MapInstanceId`+`SceneDiffer`+`OverlayReceiver`+无头往返 ROUNDTRIP_OK）；阶段 4 GUI 深化已落地两项（预览点选回填 id、设为新基线），并修复 overlay 优先级 round-trip 与 stats 两个真实缺陷；schema 现为 v4（`instances[].source` + `lineage`）。**
> schema：当前 **v3**（v2 → v3 是 `regions[].priority` 的加性变更）。
> **阶段 2 之后的路线（阶段 3 / 4 / 5，含依赖关系、优先级与下一步可执行事项）见 §4。**
> 最后更新：2026-10-12

## 0. 已核实的前置事实（与最初假设有出入，先看这里）

| 事实 | 状态 | 影响 |
|------|------|------|
| Unity 6000.0.0f1 已安装于 `C:\Program Files\Unity 6000.0.0f1\Editor\Unity.exe` | ✅ 已核实 | **C# 可以真机编译验证**，不再是"只能人工审查" |
| `UnityEngine.dll` 齐备；`ProjectData\Unity_lic.ulf` 许可证存在 | ✅ 已核实 | 可用 `-batchmode -executeMethod` 跑端到端冒烟 |
| `LowPolyCity/ProjectSettings/ProjectVersion.txt` = `6000.0.0f1 (4ff56b3ea44c)` | ✅ 精确匹配 | 无需升级/降级编辑器 |
| `dotnet` 只有 6.0.5 **runtime**，无 SDK（`--list-sdks` 为空） | ⚠️ | 不能用 `dotnet build`；编译须走 Unity 自身的 Roslyn（即 batchmode） |
| 16-bit PGM 高度图已存在 | ✅ `export/grids.py:50`（P5 / 65535 / little-endian） | 阶段 0 的 P0 从"新建"收成"加一个路径字段" |
| `moisture` 已在 `terrain.build_moisture` 算出，只进了 CSV | ✅ | 导出成本极低，性价比高 |

> ⚠️ 修正记录：`plan.md` §0 与本文档早期版本称"Unity 未安装于本环境，C# 仅能靠人工审查 + 仿真验证"。该结论**已过期**，Unity 实际可用。后续任何 C# 工作都应要求真机编译通过，而非仅静态审查。

## 1. 阶段 0 进度：让两端跑通

### 1.1 Python 端（已完成 ✅）

契约先冻结，再实现。`SCHEMA_VERSION` 提到 **2**（加性变更），新增：

| 字段 | 说明 |
|------|------|
| `grid.moisture_rle` | 0–255 量化湿度网格，`v/255` 还原；驱动 Unity 端 triplanar / 植被色调 |
| `grid.heightmap_raw_url` | 同目录 16-bit PGM 的相对 basename；无损高度场直读，规避 8-bit RLE 的 ~0.47 m 量化损失 |
| `grid.encoding.moisture`、`units.moisture_quantisation` | 编码与量化自描述 |

三条硬约束（均有回归测试）：

1. 只写相对 basename，绝不写绝对路径（跨机字节一致）。
2. 请求 `--format map` 时**必定同产** `{label}_height.pgm`，字段永不悬空。
3. 字段值由 stem 推导，**不随请求格式集变化**——4 种 format 组合下 map.json 仍逐字节一致。

已修一个真实缺陷：半完成的合并让 `grid` 局部字典构建后从未被 `return` 使用，`return` 里另有一份不含新字段的内联副本，导致 P0 字段被静默丢弃。已用
`tests/test_mapgen.py::TestEngineBridgeFields` 锁死，并校验 PGM 峰值 > 255 以证明是真 16-bit。

> **schema 版本沿革**：阶段 0 把 `SCHEMA_VERSION` 提到 **2**；随后阶段 1 的 `regions[].priority` 使其升到 **3**（同为加性变更，v2 消费端仍可读 v3 产物）。当前 `SCHEMA_VERSION = 3`。

### 1.2 Unity 端（已完成 ✅ 2026-10-06）

三个组件已落地并**经真实 Unity batchmode 验证**：

| 组件 | 文件 | 说明 |
|------|------|------|
| `MapJsonDecoder` / `MapDocument` | `Runtime/Data/MapDocument.cs` | 忠实映射 map.json；不硬塞进 `BuildPlan` |
| `MiniJson` | `Runtime/Data/MiniJson.cs` | 自带最小 JSON 解析器 |
| `SceneAssembler.FromJson` | `Editor/Scene/SceneAssembler.cs` | 路径 B 入口，复用 root/锁机制 |
| `MapSceneBuilder` | `Editor/Scene/MapSceneBuilder.cs` | 地形按 biome 分 submesh + 海平面 + 逐实例装配 |
| `MapBatchImportEntryPoint` | `Editor/Batch/MapBatchImportEntryPoint.cs` | batchmode 扫描导入 + 验收断言 |

**验收结果**：`python unity_import_smoke.py` → `SMOKE_OK: 6/6 verified, Unity exit 0`
（2 主题 × 3 seed 的 64² 文档，场景对象数 == `stats.instance_count` 全部相符）

**关键工程决策（与原方案的偏差，理由如下）**：

1. **不映射到 `BuildPlan`/`LotData`**。`BuildPlan` 是路网/街区/地块模型，而 map.json 是瓦片网格 + 实例，没有道路也没有地块。硬塞进去等于凭空发明生成器从未产出的道路，反而丢失terrain/biome/scatter 决策。因此新增独立的 `MapDocument`，`FromJson` 直接消费。
2. **自带 `MiniJson` 而非用 `JsonUtility`**。RLE 是锯齿数组 `[[value,run],...]`，`JsonUtility` 不支持；项目也刻意不引Newtonsoft 依赖——不该为读取自己的主交付物引入第三方库。
3. **地形高度优先读 16-bit PGM**。`heightmap_raw_url` 指向的 sidecar 存在时优先使用（`HeightSource` 会记录实际来源），落实 v2 桥接字段的价值。

**过程中修掉的 3 个真实缺陷**：

| 缺陷 | 症状 | 根因 |
|------|------|------|
| `CS0102` 编译失败 | `MapDocument` 重复定义 `Height` | 字段 `Height` 与方法 `HeightAt` 命名冲突 → 改名 `HeightGrid`/`BiomeGrid`/`MoistureGrid`/`RiverGrid` |
| `CS1503` × 20 | `cannot convert from 'object' to Dictionary` | `foreach` 迭代的 `entry` 是 `object` → 新增 `Json.Obj()` 做带路径报错的窄化 |
| 验收 0/6 通过 | `no Scatter container` | `MapSceneBuilder.Build` 里 `scatter.SetParent(parent.transform)` 误用 LPW 根而非 `root.transform`，Scatter 挂到了错误层级 → 修正；并给失败信息加层级转储，让问题一次定位 |

**可重复验收**：

```powershell
python unity_import_smoke.py    # 生成文档 → 跑 Unity batchmode → 校验退出码与对象数
```

脚本同时把「任何 `error CS`」也判为失败，避免编译失败的构建被误当成导入成功。

#### 环境回归：`ALLUSERSPROFILE` 缺失导致冒烟全挂（2026-10-12）

**症状**：`unity_import_smoke.py` 报 `SMOKE_FAIL: Unity exit 1`；日志为
`Failed to resolve packages: The "path" argument must be of type string. Received undefined. No packages loaded.`。
UPM 侧 `project:resolve-packages --> 500` 仅约 4–6 ms；**不是** C# 编译失败，`executeMethod` 根本没跑到。

**根因**（用打过堆栈补丁的 UPM 副本 + `-upmIpcPath` 取到）：

```
TypeError: The "path" argument must be of type string. Received undefined
  at getDeprecatedGlobalConfigRoot   → path.join(process.env.ALLUSERSPROFILE, "Unity/config")
  at getDeprecatedGlobalConfigFilePath → getUpmConfig → initContext → resolve-packages
```

UPM 的 `getDeprecatedGlobalConfigRoot()` 在 Windows 上**只**用 `ALLUSERSPROFILE`，无 `PROGRAMDATA` 兜底。
若 shell/会话里该变量被剥掉（本机即只剩 `PROGRAMDATA=C:\ProgramData`），`path.join(undefined, …)` 必炸。

**为何「有的工程能开」**：缓存健康（`Library/PackageManager/ProjectCache` + `projectResolution.json` 输入哈希一致）的工程走
`Restoring resolved packages state from cache`，**不调用** `resolve-packages`，因此不踩坑；
新建工程 / 删除过 `Library/PackageManager` / lock 变更后的工程必须 resolve，于是必挂。

**修复**：`unity_import_smoke.py` 启动 Unity 前补齐环境变量：

```python
env = dict(os.environ)
if not env.get("ALLUSERSPROFILE"):
    env["ALLUSERSPROFILE"] = env.get("PROGRAMDATA") or r"C:\ProgramData"
```

**复验（2026-10-12）**：`SMOKE_OK: 6/6 verified, Unity exit 0`。

**同日修复过程中的连带操作**（勿当回归）：

- 误删的 `Library/PackageManager/projectResolution.json` 已按当时内容重建（Library 不进 git）。
- 排查时改过的 `Packages/manifest.json` / `packages-lock.json` 已 `git checkout` 恢复，与仓库一致。
- 验收前请确认本会话 `ALLUSERSPROFILE` 已设置；脚本内已兜底，但手动开 Unity 时仍可能踩同一坑。


## 2. 阶段 1：让 Unity 端表现好（🟡 部分完成）

**已完成**：`regions[].priority`（int，schema v3）—— map.json 的重叠区域已有覆盖层级，Unity 可推断归属关系。

**其余待做**（余项统一并入阶段 3 一并处理，见 §4.3）：

- `moisture_rle` 已就绪 → 接 triplanar 湿度混合与植被色调（3h）
- `regions[].priority`（int）：map.json 目前只有 `id/shape/bounds/cells/overrides`，重叠区域无覆盖层级，Unity 无法推断（0.5h）
- `instances[].cluster_hierarchy`：**只需补跨类 parent/child**（树+草同属一簇），不必从零做——已有 `instances[].cluster` + `categories[].clusters` 群心（2h）
- `MapImportWindow`：拖拽 map.json、预览元数据、选覆盖 profile（3h）
- `features.scatter_density`（每类可放置域密度图），让 Unity 可视化"为什么这里为空"（2h）

## 3. 阶段 2：编辑-反馈闭环（Python 半边 ✅ 完成 / Unity 半边 ⬜ 待做）

数据流：编辑器导出 `edits.json` → mapgen `--overlay` 重生成 → 新 map.json 回传刷新。

### 3.1 已完成：Python 半边（2026-10-06）

| 模块 | 实际落地 | 状态 |
|------|------|------|
| `mapgen/edit.py` | `edits.json` 解析（`add`/`move`/`delete`/`paint`）+ `overlay_world` | ✅ 新增 |
| `mapgen/export/mapdata.py` | `decode_rle`（与 `_rle` 对称的解码侧，GUI 与宣传片共用同一实现） | ✅ 新增 |
| `mapgen/cli.py` | `--overlay <base_map.json> --edits <edits.json>` | ✅ 新增 |
| `tools/MagicaMapGen/tools/test_overlay.py` | 空 edits 字节一致 / delete·add·move 只动脏区 / 确定性 | ✅ 5 项全绿 |
| GUI | `app/edits_panel.py`（Edit 标签页）+ `bridge.start_overlay` | ✅ 新增 |

**实现与原方案的偏差（重要，勿回退）**：原计划改 `scatter.place_all` 支持 `exclude_instances` / `frozen_instances` 来做"脏区重生成"。实测改为**确定性重生成 + 实例级后编辑**更优：用 base 自带的 request 以同 seed 重跑，产物与 base **逐字节一致**，再对实例列表施加 delete / move / add / paint。因此未编辑区域天然不变，且不必把"冻结 / 排除"状态织入 scatter 的随机流——后者会连带改变占用集与采样顺序，反而破坏字节一致性。

主要风险的处置：RLE 8-bit 的 0.47 m 量化损失 → `edits.json` 走**实例级**操作，网格 RLE 仅作视觉参考（已落地）。

**遗留缺口**：overlay 能产生 user 实例，但 map.json 里没有任何字段标明哪些实例是人工放置 / 人工移动的（消费端无法区分"可重建"与"锁定"）。这正是阶段 5 的 0 号切片，见 §4.2。

### 3.2 待做：Unity 半边

| 模块 | 改动 | 估量 |
|------|------|------|
| Unity | `SceneDiffer`（编辑器事务监听 → edits.json） | ~4h |
| Unity | `OverlayReceiver`（调 CLI、退出码映射、场景刷新） | ~2h |

集成方案详见 §4.3。

## 4. 阶段 2 之后路线（阶段 3 / 4 / 5）

### 4.0 总览：状态、依赖与优先级

| 阶段 | 名称 | 状态 | 依赖 | 优先级 |
|---|---|---|---|---|
| 0 | 契约冻结 + 双端跑通 | ✅ 完成 | — | 已交付 |
| 1 | Unity 端表现力 | 🟡 部分（`regions[].priority` 已落地） | 0 | P1（余项并入阶段 3） |
| 2 | 编辑-反馈闭环（Python 半边） | ✅ 完成 | 0 | 已交付 |
| 3 | Unity 编辑回环贯通 | ⬜ 待做 | 2 + 5-0 | P1 |
| 4 | GUI 编辑器深化 | ⬜ 待做 | 2（仅需 Python 半边） | **P0** |
| 5 | schema v4 演进 | ⬜ 待做 | 3 / 4 的真实反馈 | P1（0 号切片可插队） |

**优先级口径**：**P0** = 直接增强主交付（`mapgen` + GUI）或被其阻塞；**P1** = 提升引擎侧完整性与契约表达力；**P2** = 远期调研。

**轨道说明**：阶段 3（Unity C#）与阶段 4（Python GUI）是**不同轨道，可并行推进**，不互相阻塞。

> **本节小节按「可开工顺序」排列，而非按阶段号**：§4.1 是阶段 4（P0，最该先做）→ §4.2 是阶段 5 的 0 号切片 → §4.3 是阶段 3（P1，被 5-0 阻塞）。阶段号本身以 §4.0 的表为准。

依赖链：

```
阶段0 ──┬─► 阶段2(Python) ──┬──► 阶段4(GUI 深化)   [P0，可立即开工]
        │                    │
        │                    └──► 阶段3(Unity 回环) ──┐
        └──► 阶段1(Unity 余项) ────────────────────┤
                                                    ▼
                              阶段5(schema v4) ◄── 真实反馈
```

### 4.1 阶段 4：GUI 编辑器深化（P0 · 主交付）

**现状**：Edit 面板已能记录 add / move / delete / paint 并触发增量重生成，但**实例 id 与坐标仍需手填**。深化方向按优先级：

1. ✅ **预览点选实例** → 自动回填 delete / move 的 id（**已完成 2026-10-13**）：`preview.py` 提取共享投影 `_projection`（渲染与命中检测同一套数学，杜绝漂移）+ 新增 `pick_instance`；`main_window` 给预览装事件过滤器，左键点选→`EditsPanel.select_instance` 回填 `del_id`/`move_id`/`move_x`/`move_y` 并切到 Edit 页；`edits_panel` 新增 `select_instance`。**验收（可重跑）**：`cd tools/MagicaMapGen && python tools/smoke_gui.py` → `RESULT: PASS`，含断言 `pick_instance OK` 与 `click-to-select filled Edit panel`。
2. **预览上拖拽移动**：拖动实例直接生成 `move` op（复用现有语义）。
3. ✅ **"设为新基线"**（**已完成 2026-10-13**）：Edit 面板新增按钮，overlay 产物生成后启用，点击即把最近一次增量重生成的结果（`overlay_map.json`）提升为新基准并清空 ops，从此可继续累积编辑（chaining 仍是显式动作，不自动串联）。`bridge._load_summary` 改为按 **mtime** 选取本次运行产物（原 `sorted()[-1]` 会在 overlay 后误选字母序靠后的 base，导致 overlay 结果从不显示）。**顺带修了两个 phase-2 overlay 真实缺陷**（均由新加的 GUI 冒烟暴露，非本次功能引入）：① `config.request_to_dict` 丢 `region.priority` → 任何多区域 base 的 overlay 重载后优先级全归 0、触发碰撞报错；② `edit.overlay_world` 未在 `_apply_edits` 后重算 `stats` → `map.json` 的 `stats.instance_count` 与删改后的实例数不符。两处均有 `tests/test_mapgen.py::TestOverlayRoundTrip` 回归覆盖。**验收**：`python tools/smoke_gui.py` → `RESULT: PASS`（含 `overlay loop OK: 191 -> 190` 与 `设为新基线 OK`）。
4. **脏区高亮**：叠加显示本次编辑影响的区域，直观解释"为什么只有这几处变了"。
5. **多方案并排对比**：同一 seed + 不同 `edits.json` 生成并排缩略图，用于评审。
6. **区域可视化编辑**：把 `bounds` 数值变成可拖拽的矩形 / 圆。
7. **操作级撤销**：跨 overlay 的撤销 / 重做（当前 GUI 无撤销栈）。

依赖：仅需阶段 2 的 `--overlay`（已具备）。**可立即开工。**

### 4.2 阶段 5：schema v4 演进（P1 · 0 号切片可插队）

v4 的完整字段应在阶段 3 / 4 暴露真实需求后再冻结，避免过早固化。但有一个**当前已存在的真实缺口**可以先做：

**0 号切片（✅ 已完成 2026-10-13；`SCHEMA_VERSION` 3→4）**

| 字段 | 目的 |
|---|---|
| `instances[].source` | 取值 `auto` / `user-added` / `user-moved`，让消费端识别人工锁定对象、重建时不覆盖。阶段 2 已能产生 user 实例却无任何标记，是当前最实际的缺口。 |
| 顶层 `lineage` | 记录 `base_map_sha256` / `edits_sha256` / `op_count`，使产物可追溯到"基于哪张图、哪次编辑"。 |

**v4 候选变更全表**（均为加性）：

| 字段 | 目的 | 来源 |
|---|---|---|
| `instances[].source` | 标注人工锁定 | 阶段 2（缺口） |
| 顶层 `lineage` | 产物血缘 | 阶段 2（缺口） |
| `instances[].cluster_hierarchy` | 跨类父子（树 + 草同属一簇） | 阶段 1 余项 |
| `features.scatter_density` | 每类可放置域密度图，解释"为什么这里空" | 阶段 1 余项 |
| `regions[].mask_rle` | 区域掩码显式化，消费端不必重算 | 可选 |

**v4 约束**（沿用 v2 → v3 经验）：

1. **只做加性变更**，不删改 v3 已有字段语义。
2. v3 消费端读 v4 产物必须不报错（多余字段忽略）。
3. `SCHEMA_VERSION` 提到 4，`map.schema.json` 同步升级；回归测试锁死"v3 必填字段在 v4 仍存在"。
4. 产物仍不得含时间戳 / 绝对路径（字节可复现是红线）。

### 4.3 阶段 3：Unity 编辑回环贯通（P1）

> ✅ **首切片已完成（2026-10-13）**：`MapInstanceId`（装配期写入 ↔ `instances[].id`）+ `SceneDiffer` + `OverlayReceiver` + 无头往返入口 + 交互式 `MapImportWindow`（Tools > Low Poly World Builder > Import Map (JSON)：载入/预览 contract+lineage+source 计数、Build、Diff→edits.json、Apply overlay→reload、退出码语义映射）。**旋转/缩放**变更现由 `SceneDiffer` 表达为 delete+add（mapgen 无 set op），已纳入无头往返（`rotate=1`→overlay `op_count=5`）。`MapDocument.MaxKnownSchema` 2→4。验收：`python unity_roundtrip_smoke.py` → `ROUNDTRIP_OK`；`unity_import_smoke.py` → 6/6。
>
> **仍留后续**：编辑器**实时事务监听**（当前是快照 diff，非 `Undo.postprocessModifications` 自动捕获）、以及"overlay 保住上一轮 user 实例"的 Python 侧一等公民化（见 §4.2 边界注记）。

**`SceneDiffer`（编辑采集端）**

- **只对带 `MapInstanceId` 标记的 GameObject 生效**：`MapSceneBuilder` 装配时写入它 ↔ `map.json` `instances[].id` 的稳定映射；不碰用户自建的其它对象。
- **机制**：Unity 编辑器事务（`ObjectChangeEvents` / `Undo.postprocessModifications`）监听增 / 删 / 移，累积为 `edits.json`。
- **坐标换算**：`move` 需把世界坐标反算回格坐标，复用 `grid.cell_to_world` 的逆运算：`cell = round(world / tile_size_meters - 0.5)`（产物约定 `world = (cell + 0.5) * tile`，故不能直接用 `floor(world/tile)`）。
- **范围限制**：mapgen 暂无"设置旋转/缩放"的 op；`SceneDiffer` 把旋转/缩放变更表达为 **delete + add**（携带新 rot/scale 与当前格），已在无头往返中覆盖（`rotate=1` 时 differ 报 delete=2/move=1/add=2）。

**`OverlayReceiver`（回灌端）**

- **动作**：`Process` 调 `python -m mapgen --overlay <base> --edits <edits.json> --out <dir>`（必开 `--validate`），按退出码给出可操作提示（0/1/2/3/4 语义与 GUI 完全一致），完成后经 `SceneAssembler.FromJson` 刷新场景，沿用现有 root / 锁机制。
- **验收**：复用 `unity_import_smoke.py` 的断言风格（场景对象数 == `stats.instance_count`、`error CS` 即失败），并新增"编辑前后 diff 只落在脏区"的断言。

**依赖**：阶段 2 的 `--overlay`（已具备）+ 阶段 5 的 `instances[].source`（否则 Unity 无法识别人工锁定对象）。因此建议执行顺序是 **5-0 号切片 → 阶段 3**。

### 4.4 下一步可执行事项（有序）

1. ✅ **[P0 · GUI]** 预览点选实例 → 自动回填 Edit 面板的 id（`preview.py` hit-test + 面板联动）。见 §4.1-1。**已完成**，验收 `python tools/smoke_gui.py` → PASS。
2. ✅ **[P0 · GUI]** "设为新基线"动作，允许以 overlay 产物继续累积编辑。见 §4.1-3。**已完成**（并修复 overlay 优先级 round-trip + stats 两个真实缺陷），验收 `python tools/smoke_gui.py` → PASS。
3. ✅ **[P0 · schema]** 5-0 号切片：`instances[].source` + 顶层 `lineage`（加性、v3 兼容），带回归测试。见 §4.2。**已完成**（`SCHEMA_VERSION` 3→4，`map.schema.json` + `validate` 语义强制，`TestSchemaV4` 回归覆盖，overlay 产物带 user-* 标记与 base/edits 哈希）。
4. ✅ **[P1 · Unity]** `SceneDiffer`：先用手工 `edits.json` 喂 `--overlay` 的端到端脚本打通回路（不改 C# 即可验证），再上编辑器事务监听。见 §4.3。**已完成首切片**（快照 diff + 无头往返 `unity_roundtrip_smoke.py` → ROUNDTRIP_OK）；事务监听为后续项。
5. ✅ **[P1 · Unity]** `OverlayReceiver`：调 CLI + 退出码映射 + 场景刷新。见 §4.3。**已完成**（`Process` 调 `mapgen --overlay --validate`，MAPGEN_PYTHON 复用同解释器；reload 断言通过）。
6. **[P1 · schema]** 冻结 v4 其余字段（`cluster_hierarchy` / `scatter_density` / `mask_rle`），依据阶段 3 / 4 的真实反馈。见 §4.2。
7. **[P2]** 阶段 1 余项并入阶段 3 一并处理：triplanar 湿度混合、`cluster_hierarchy` 跨类父子、`MapImportWindow`、`scatter_density`。

## 5. 为什么不选路径 A（就地修 Unity）

| | 路径 A | 路径 B |
|---|---|---|
| 独立可交付性 | Unity 是唯一生成端 | mapgen 独立产出，Unity 只是可选消费端 |
| 确定性内核 | 算法已验证但 C# 未实机确认 | mapgen 已生产级验证，Unity 只消费结果 |
| 新主题/新分布 | 改 C# | 改 Python（已有注册表，已验证） |
| 跨引擎复用 | 无 | map.json 为通用契约，换引擎只写消费端 |

## 6. 未采用的原方案条目

- `heightmap_raw_url` 改为**引用**已有 PGM，而非新建高度图产出。
- 集群层级复用既有 `cluster` / `clusters`，只补跨类父子关系。
- `moisture_rle` 从原 P1 **提前进阶段 0**：数据已在内存，导出 ~30 分钟，却直接解锁 Unity 端湿度混合。
- map.json 顶层实际有 15 个块（远超"6 大类"），扩展点须先对齐 schema，避免与 `stats` / `contract` 撞语义。
