# Unity 6 低多边形世界原型生成器 — 项目研发计划

> 目标：为 Unity 6 建立一套可参数化、可重复生成、可组合摆放的低多边形场景原型工具。它面向游戏立项、投资沟通、关卡草案、客户提案和早期产品空间展示，能从城市规模布局逐步展开到可替换的建筑、交通、港口、机场和景观模块。
>
> 工作区中的参考材料：`有基础，从几分钟到几小时出模型.pdf`。其中“低精度初稿优先、重复结构参数化、资产模板复用、外部模型作为素材入口”的建议可以迁移到本项目；本文将程序化生成聚焦于规则清晰、可组合、能反复调整的场景结构。

---

## 0. 交付转向说明（2026-10-03 更新，最高优先级）

> **本节修订下方所有内容的适用范围。** 下方 §1–§8 描述的是 Unity Editor 插件路线，现降级为**次要/遗留轨道**；**主交付已转向 `mapgen/`（纯 Python）**。

**为什么转向。** 需求澄清后，真正要的是一个**原型设计工具**：把游戏想法转成可交付、可复现的**设计原稿地图**（类比墨刀出原型 UI、红警 2 出地图），而不是又一个 Unity 建模插件。核心是显式的**三层模型**：

```
主题 Theme（确定性契约：要雪地就不能给草原）
  └── 类别 Category（一对多：稀疏树木 / 密集树木 / 其它树木，各有数量）
        └── 分布 Distribution（可替换的第三层：正态群落 / 泊松盘 / 均匀 / 网格抖动）
              └── 区域 Region（局部物体概率化 + 多层修改）
```

**主交付产物**：`*_map.json`（RA2 式瓦片网格 RLE + 物体实例 + biome 图例，含 walkable/movement_cost/buildable 引擎提示），以及 Houdini 可导入的 `*_scene.obj`/`.mtl` 作为 3D 场景副产品。

**当前状态**：`mapgen/` 已实现并通过验证——2 个主题（雪地 / 岛屿）契约零警告、87 项测试（另含 36 个子测试）实跑通过、同 seed 下 10 个产物跨目录逐字节一致；**编辑-反馈闭环的 Python 半边（`--overlay` 增量重生成 + GUI Edit 面板）已落地**。详见 `mapgen/README.md`。

**下方 Unity 计划（§1 起）的现状**：`LowPolyCity/` 包仍保留，审计发现的 C1–C4 四个缺陷均已修复（C2 地块重叠、C4 锁定绕过经 `audit_sim/` 位级仿真对账验证）；但该包不再是主交付。审计结论与修复状态见 `审计报告.md` 的"修复状态补记"。

> **更正（2026-10-06）**：本节原称"Unity 未安装于本环境，其 C# 仅能靠人工审查 + 仿真验证，无法实机编译"——该结论**已过期**。经核实 Unity 6000.0.0f1 安装于 `C:\Program Files\Unity 6000.0.0f1\Editor\Unity.exe`，`UnityEngine.dll` 齐备、许可证存在，且 `LowPolyCity/ProjectSettings/ProjectVersion.txt` 精确匹配 `6000.0.0f1 (4ff56b3ea44c)`。因此 C# **可以**用 `-batchmode -executeMethod` 真机编译与跑端到端冒烟。注意 `dotnet` 仅有 6.0.5 runtime、无 SDK，不能用 `dotnet build`，编译须走 Unity 自带 Roslyn。当前主线已转向 `mapgen/` 产出通用契约、Unity 仅作消费端，路线与优先级见 `path_b_baseline.md`。

---


### 0.1 当前进度与「阶段 2 之后」路线（摘要）

> 完整版（依赖链图、Unity 集成方案、schema v4 字段全表）见 `path_b_baseline.md` §4。此处只放状态与优先级，**三份文档口径一致**。

| 阶段 | 名称 | 状态 | 依赖 | 优先级 |
|---|---|---|---|---|
| 0 | 契约冻结 + 双端跑通 | ✅ 完成 | — | 已交付 |
| 1 | Unity 端表现力 | 🟡 部分（`regions[].priority` 已落地） | 0 | P1（余项并入阶段 3） |
| 2 | 编辑-反馈闭环（Python 半边） | ✅ 完成 | 0 | 已交付 |
| 3 | Unity 编辑回环贯通 | ⬜ 待做 | 2 + 5-0 | P1 |
| 4 | GUI 编辑器深化 | ⬜ 待做 | 2（仅需 Python 半边） | **P0** |
| 5 | schema v4 演进 | ⬜ 待做 | 3 / 4 的真实反馈 | P1（0 号切片可插队） |

**优先级口径**：P0 = 直接增强主交付（`mapgen` + GUI）或被其阻塞；P1 = 提升引擎侧完整性与契约表达力；P2 = 远期调研。阶段 3（Unity C#）与阶段 4（Python GUI）属**不同轨道，可并行**。

**阶段 3 · Unity 编辑回环（P1）**：`SceneDiffer` 只对带 `MapInstanceId` 标记的对象生效，事务监听增/删/移 → `edits.json`（`move` 用 `floor(world_x / tile_size)` 反算格坐标）；`OverlayReceiver` 调 `--overlay`（必开 `--validate`），退出码语义与 GUI 一致，经 `SceneAssembler.FromJson` 刷新。因需 `instances[].source` 才能识别人工锁定对象，排在 5-0 之后。

**阶段 4 · GUI 编辑器深化（P0）**：预览点选实例回填 id → 预览拖拽移动 → "设为新基线"以累积编辑 → 脏区高亮 → 多方案并排 → 区域可视化 → 操作级撤销。仅依赖已具备的 `--overlay`，**可立即开工**。

**阶段 5 · schema v4（P1）**：0 号切片（`instances[].source` + 顶层 `lineage`）对应当前真实缺口——overlay 已能产生 user 实例却无任何标记，成本极小可插队先做；`cluster_hierarchy` / `scatter_density` / `regions[].mask_rle` 待阶段 3/4 反馈后冻结。全程只做加性变更，保持 v3 消费端可读。

**下一步可执行（有序）**：

1. [P0·GUI] 预览点选实例 → 回填 Edit 面板 id
2. [P0·GUI] "设为新基线"动作，允许以 overlay 产物累积编辑
3. [P0·schema] 5-0 号切片（`instances[].source` + `lineage`）
4. [P1·Unity] `SceneDiffer`（先用手工 `edits.json` 打通回路，再上事务监听）
5. [P1·Unity] `OverlayReceiver`
6. [P1·schema] 依据阶段 3/4 反馈冻结 v4 其余字段
7. [P2] 阶段 1 余项并入阶段 3：triplanar 湿度混合、`cluster_hierarchy`、`MapImportWindow`、`scatter_density`


## 1. 产品定义与可行性结论

### 1.1 产品是什么

它是 Unity Editor 插件加一个可选批处理入口，不是另一个通用建模软件。用户在 Unity 项目中打开生成窗口，设定世界类型、范围、密度、风格、随机种子和资产集，生成可编辑的层级场景；需要重复使用时再把模块保存为 Prefab，或把场景交给 Unity Player/演示构建流程。

首个有说服力的成果应是“可以从区域规划到可漫游的卡通城市原型”，而不是一开始就承诺自动做出所有任意产品的精细模型。

### 1.2 判断

**技术上可行，适合作为分阶段的 Unity 编辑器工具研发。** Unity 6 提供编辑器窗口、Mesh 创建、Prefab/场景资产保存和命令行批处理所需的基础能力。[EditorWindow](https://docs.unity3d.com/6000.0/Documentation/ScriptReference/EditorWindow.html)、[PrefabUtility.SaveAsPrefabAsset](https://docs.unity3d.com/6000.0/Documentation/ScriptReference/PrefabUtility.SaveAsPrefabAsset.html)、[MeshData](https://docs.unity3d.com/6000.0/Documentation/ScriptReference/Mesh.MeshData.html)、[命令行参数](https://docs.unity3d.com/6000.0/Documentation/Manual/EditorCommandLineArguments.html)。

**范围必须分成两种造型路径：**

- 规则几何：道路、路口、地块、楼体盒型、窗格、屋顶、桥梁段、围栏、站台、跑道标线、地形块、树木等，由参数和种子直接生成。
- 复杂语义资产：火车、飞机、车辆、机械、人物、细节丰富的工厂设备等，以用户导入的低模 Prefab/网格模板为主，由规则系统选型、变体、缩放、旋转、着色和布置。
- 可选外部生成/导入：AI 生成、Blender/Houdini、Asset Store 等作为素材来源；不是首版必须依赖的服务，也不把外部服务的效果作为插件能力保证。

这样可以支持“任意场景主题的原型搭建”，但不会假称规则参数可以自动创建任意真实产品的专业模型。卡通低模降低了几何细节和材质门槛，却仍需要资产库、空间规则、审美预设和人工挑选。

### 1.3 商业与研发价值

早期项目往往需要先看空间比例、布局关系、动线、视觉风格和内容密度，再讨论制作方向。本工具可以把这些讨论变量变成可编辑参数和可复现的场景种子，缩短“想法—可视原型—反馈—修订”循环。可交付价值不只在模型数量，而在于：一键搭出可读的空间原型、随时改布局、保留生成配置、支持替换客户资产并重复导出。

### 1.4 主要风险

| 风险 | 影响 | 应对 |
|---|---|---|
| “任何东西都能自动建模”的预期过宽 | 项目变成无限扩张的建模器 | 明确生成器负责结构和布局；复杂物体走模板/导入接口 |
| 场景规模太大导致编辑器卡顿 | 生成时间、视口帧率和迭代速度下降 | 分区/分块生成、实例复用、按需细节、对象数预算、先预览后落地 |
| 随机生成不可复现或覆盖人工修改 | 客户反馈无法稳定复现，编辑成果丢失 | 固定 Seed、配置版本号、生成根节点标记、预览与正式生成分离、覆盖前提供策略 |
| 各种交通与基础设施有领域约束 | 仅靠随机摆放容易“像玩具拼图” | 先建立道路/轨道/地块图和连接端口，再放置模块并做规则校验 |
| Unity/渲染管线差异 | 材质、着色器和包兼容风险 | 核心使用 Unity 6 基础 Mesh/Material 接口；URP 风格包作为可选适配层 |
| 资产版权与一致性 | 发布或客户使用时有风险 | 用户自有资产优先；附带样例只用原创或明确许可素材 |

## 2. 目标用户和首批使用方式

- 游戏制作人、关卡设计师：搭建可玩的城市布局和交通骨架，做立项讨论。
- 独立开发者/原型团队：以小资产包快速组合村庄、工厂区、港区和城市街区。
- 客户提案/投资沟通：生成可漫游的概念场景或截图，讨论规模和方向。
- 美术/场景设计师：批量变体和重复摆放，再人工精修有价值的局部。
- 任何需要空间型产品原型的团队：展馆、主题乐园、商业综合体、基地/园区等，通过模板和规则扩展，而不是承诺机械 CAD 级精度。

首版先服务 Unity Editor 中的设计者。以后可增加生成任务命令行、团队资产包规范、Web 配置器或运行时编辑能力；它们不作为第一阶段的前置条件。

## 3. 首版范围（MVP）

首版选一个完整的“低多边形都市街区”纵切面，避免先做十几类互不连通的生成器。

### 3.1 MVP 必须包含

1. **Unity Editor 生成窗口**：世界配置、区域尺寸、街区尺寸、道路宽度、密度、建筑高度区间、风格调色板、随机种子、预览/正式生成/清理。
2. **道路与地块**：规则网格道路、十字/丁字/转角路口、街区切分、地块分配；路口连接类型由拓扑判断，不靠独立随机摆件。
3. **建筑生成器**：低模基础楼体、屋顶、楼层线、窗格/阳台等可选模块；住宅、商业、办公、工厂使用配置和模块组合出变体。
4. **基础环境**：地面、水面、简单高差、树木、路灯、标识和少量道具。
5. **资产模板**：允许将用户 Prefab 指派为建筑/车辆/树木等类别，指定尺寸范围、连接点、适用地块、权重和变体标签。
6. **可编辑和可重建**：生成内容有清晰层级，固定 Seed 生成稳定结果；用户可选择全量重建、只重建选定分区或把节点标为“人工锁定”。
7. **结果保存**：把参数配置保存为 ScriptableObject；可选择保存生成 Prefab 与 Scene；生成报告记录 Seed、生成器版本、资产引用与统计。
8. **演示输出**：生成一张默认摄像机视图或可构建的漫游场景，用来给客户/投资人看比例和布局。

### 3.2 首版暂不承诺

- 自动生成可信的高精度车辆、飞机、人物和复杂机械模型。
- 满足真实道路工程、铁路信号、航管、港口物流或消防规范的施工设计。
- 大型开放世界运行时无缝流送。
- 在线 AI 模型生成、云端资产交易和团队协同服务。
- 任意 CAD/建筑 BIM 的完整导入与语义理解。
- 一键把随机地图自动变成可玩关卡或完整商业游戏。

这些方向后续可通过额外模块、用户资产库或行业规则包加入。

## 4. 使用流程

1. 在目标 Unity 6 项目安装/导入插件。
2. 打开 **Tools > Low Poly World Builder**，选一个模板：都市、村庄、港口、机场、工业园或自定义。
3. 指定规模、道路/轨道选项、区域分区、建筑类别比例、风格与 Seed；也可载入现有低模 Prefab 资产目录。
4. 点击“预览”：只生成轻量代理物/线框，不保存正式资产。
5. 在 Scene 视图确认道路、街区和分区；修改参数并重新预览。
6. 点击“生成”：生成正式网格/Prefab 实例，按街区分组，保存配置和报告。
7. 手工替换重点资产、调整构图；可锁定人工调整区域。
8. 导出 Scene/Prefab 或使用项目既有 Build Profile 构建演示版本。

## 5. 技术架构

### 5.1 分层

- **配置层**：ScriptableObject 保存世界类型、尺寸、规则、调色板、资产集、Seed 和版本。JSON 导入/导出可用于版本控制或外部批处理参数。
- **规则/领域层**：纯数据结构表示道路图、地块、分区、轨道/河道连接与生成计划；随机数来自显式 Seed，生成器不直接读取全局随机状态。
- **几何层**：从简单参数构造 Mesh（顶点、三角形、UV、法线、子网格和材质），尽量按可复用模块创建。
- **资产层**：Prefab/ScriptableObject 模板目录，包含分类、尺寸、连接端口、标签、LOD/碰撞体提示和权重。
- **场景组装层**：根据生成计划实例化模板、生成网格、放到分区根节点下；提供清理、重生成和人工锁定边界。
- **Editor UI 层**：EditorWindow + UI Toolkit，显示配置、警告、统计、进度和操作按钮；Scene 视图辅助可视化地块/连接图。
- **批处理层**：静态入口参数化读取配置，在 Unity Editor 的 `-batchmode -executeMethod` 下生成/导出场景和 JSON 报告。Unity 的命令行模式可以调用项目中的静态方法，异常/非零退出码可用于自动化反馈。[官方命令行参数](https://docs.unity3d.com/6000.0/Documentation/Manual/EditorCommandLineArguments.html)。

### 5.2 算法建议

- **网格街区**：先依据道路宽度与街区间距划分道路/街区，再把街区切成地块；用尺寸、区划用途和资产适配条件做候选过滤。
- **道路网络**：第一版采用参数化网格图，路段以端口连接；之后支持简单曲线、路口编辑与道路拓扑导入。每种路口由相邻道路端口集合推导。
- **建筑**：模块化生成“基座 + 楼层段 + 顶部 + 屋顶 + 配件”；用离散参数和受限变体保持统一风格。重复窗格等可合并为单个 Mesh，而不是每个窗都是 GameObject。
- **交通/轨道**：后续用样条线或中心线 + 轨道截面生成铁轨/道路几何；站台、桥梁、车辆按标准连接端口放置。列车和飞机本身优先用资产模板。
- **景观**：高度图或分块高度场定义地形；树/石/灯等以实例散布并受坡度、道路边界、地块类型约束。
- **大场景组织**：按固定尺寸街区/瓦片生成，每块拥有独立随机子种子和资产预算，可只重建发生变化的分区。先实现编辑器稳定性，再考虑 Jobs/Burst 或 Entities；早期不增加 DOTS 学习与包兼容负担。

### 5.3 生成确定性与覆盖保护

- Seed + 配置内容 + 生成器版本共同确定结果；配置中的 `schemaVersion` 支持迁移。
- 生成根节点保存 `WorldBuildMarker`，记录配置 GUID、Seed、区域键、插件版本及生成对象标识。
- 预览对象放在临时根节点，取消或参数更新可整体清理。
- 正式重建提供“只重建本工具生成内容”与“保留标记为锁定内容”策略；不可按名字删除整个场景节点。
- 一次操作包装 Undo；大规模批处理的 Undo 可以选择整块操作或提供生成前保存点，不能注册上百万个细粒度操作。
- 可用校验报告指出缺失 Prefab、尺寸不匹配、道路断口、地块冲突和对象预算超限。

## 6. 建议代码与包结构

建议做成 UPM 包，第一阶段可直接放入 Unity 工程的 `Packages/com.studio.lowpoly-world-builder/`，便于版本管理；如先做单项目验证，也可放入 `Assets/LowPolyWorldBuilder/`，代码依赖方向不变。工具代码放置为 Editor-only Assembly Definition，避免将编辑器代码编进最终 Player。Unity Assembly Definition 可将代码组织成独立程序集，并对 Editor 平台做限制。[官方程序集定义说明](https://docs.unity3d.com/6000.0/Documentation/Manual/assembly-definitions-intro.html)。

~~~text
com.studio.lowpoly-world-builder/
├── package.json
├── README.md
├── CHANGELOG.md
├── Runtime/
│   ├── LowPolyWorldBuilder.Runtime.asmdef
│   ├── Config/
│   │   ├── WorldBuildProfile.cs
│   │   ├── ZoneProfile.cs
│   │   ├── StylePalette.cs
│   │   └── AssetCatalog.cs
│   ├── Data/
│   │   ├── RoadGraph.cs
│   │   ├── CityBlock.cs
│   │   ├── LotData.cs
│   │   ├── BuildPlan.cs
│   │   └── WorldBuildReport.cs
│   ├── Generation/
│   │   ├── IWorldGenerator.cs
│   │   ├── DeterministicRandom.cs
│   │   ├── RoadNetworkGenerator.cs
│   │   ├── BlockSubdivisionGenerator.cs
│   │   ├── BuildingGenerator.cs
│   │   ├── TerrainGenerator.cs
│   │   └── ScatterGenerator.cs
│   ├── Geometry/
│   │   ├── MeshBuilder.cs
│   │   ├── BuildingMeshBuilder.cs
│   │   ├── RoadMeshBuilder.cs
│   │   └── MeshChunk.cs
│   └── Placement/
│       ├── AssetSelector.cs
│       ├── PortCompatibility.cs
│       └── PlacementRules.cs
├── Editor/
│   ├── LowPolyWorldBuilder.Editor.asmdef
│   ├── UI/
│   │   ├── WorldBuilderWindow.cs
│   │   ├── WorldBuilderWindow.uxml
│   │   └── WorldBuilderWindow.uss
│   ├── Preview/
│   │   ├── PreviewController.cs
│   │   └── WorldGizmoDrawer.cs
│   ├── Scene/
│   │   ├── SceneAssembler.cs
│   │   ├── GeneratedRootManager.cs
│   │   └── PrefabAssetWriter.cs
│   ├── Batch/
│   │   ├── BatchGenerationEntryPoint.cs
│   │   └── CommandLineOptions.cs
│   └── Validation/
│       ├── ProfileValidator.cs
│       └── AssetCatalogValidator.cs
├── Samples~/
│   ├── CityBlock/
│   ├── Port/
│   └── Art/
└── Documentation~/
    ├── GettingStarted.md
    ├── AssetAuthoring.md
    └── BatchGeneration.md
~~~

### 6.1 核心接口草案

~~~csharp
public interface IWorldGenerator<TInput, TOutput>
{
    TOutput Generate(TInput input, GenerationContext context);
}

public sealed class GenerationContext
{
    public int Seed { get; init; }
    public string RegionKey { get; init; }
    public WorldBuildReport Report { get; }
    // 随机流、取消标记、进度回调、预算和资产目录由实现提供。
}

public sealed class WorldBuildProfile : ScriptableObject
{
    public int schemaVersion = 1;
    public int seed = 12345;
    public Vector2Int blockCount = new(8, 8);
    public float blockSize = 80f;
    public float roadWidth = 12f;
    public ZoneProfile[] zones;
    public StylePalette palette;
    public AssetCatalog catalog;
}

public static class BatchGenerationEntryPoint
{
    // 由 -executeMethod 调用；从命令行参数取得 profile 与输出目录。
    public static void GenerateWorld();
}
~~~

接口只是边界草图；编码时按 Unity 6000.0 所用 C# 语言级别和目标平台检查语法，不把较新语言特性当作兼容性前提。项目目标编辑器由用户给出的可执行文件路径配置，例如 `C:\Program Files\Unity 6000.0.0f1\Editor\Unity.exe`；Unity 项目根目录、Package 目录、输出目录分别配置，避免把 Editor 安装目录误当成项目。

### 6.2 资产保存与编辑器交互

- 场景对象由 Editor 程序集通过 `PrefabUtility.SaveAsPrefabAsset`、`AssetDatabase` 和场景管理 API 保存；Prefab API 支持从 GameObject 层级创建 Prefab 资产。[PrefabUtility 文档](https://docs.unity3d.com/6000.0/Documentation/ScriptReference/PrefabUtility.SaveAsPrefabAsset.html)
- 用户触发的编辑器生成操作按粒度注册 Undo；Unity 为新建对象提供 `Undo.RegisterCreatedObjectUndo`。[Undo 文档](https://docs.unity3d.com/6000.0/Documentation/ScriptReference/Undo.RegisterCreatedObjectUndo.html)
- 批量修改资源时，若使用 `AssetDatabase.StartAssetEditing`，必须通过 `try/finally` 确保停止批处理导入，否则异常可能使 Asset Database 留在暂停状态。[AssetDatabase 文档](https://docs.unity3d.com/6000.0/Documentation/ScriptReference/AssetDatabase.StartAssetEditing.html)
- 几何构造先用易维护的 Mesh API；确实遇到生成开销瓶颈，再考虑 `MeshData`/Job System。Unity 6 的 MeshData 支持为 Mesh 分配和写入顶点/索引缓冲，索引格式及目标设备限制需要在生成器中校验。[MeshData 文档](https://docs.unity3d.com/6000.0/Documentation/ScriptReference/Mesh.MeshData.html)

## 7. 研发阶段与交付门槛

| 阶段 | 重点 | 可评审交付 |
|---|---|---|
| 0. 需求与风格基线 | 选定示例项目、色板、单位比例、典型屏幕/电脑性能预算，定义配置字段 | 产品范围、灰盒布局图、Unity 6 空包 |
| 1. 技术纵切面 | EditorWindow、配置资产、固定 Seed、网格道路、街区划分、基础建筑生成 | 一键生成一个 4×4 街区并可重复重建 |
| 2. 可交互原型 | 预览/正式生成、分区层级、道路/地块校验、建筑变体、地面树灯 | 一张可漫游/可评审的卡通街区场景 |
| 3. 资产模板工作流 | 用户 Prefab 分类、尺寸/端口规则、替换资产、样例资产 | 能用外部住宅/工厂/交通 Prefab 替换默认模块 |
| 4. 城市组合 | 多区块、村庄/工业区/商业区/住宅区，基础水系和简单高差 | 一张数公里尺度的代理城市布局，按块生成 |
| 5. 交通基础设施 | 曲线道路、铁路/地铁/单轨骨架、桥梁/隧道代理、站点与连接校验 | 可读的综合交通规划原型 |
| 6. 港口与机场 | 港池/码头、跑道/滑行道/航站楼地块、停机位、物流区规则 | 港口或机场专题模板 |
| 7. 性能与生产化 | 分区重建、实例化/合并策略、取消/进度、配置迁移、批处理日志与失败码、文档 | UPM 包候选版本和可复现演示流程 |

**工时量级仅用于立项讨论**：单人有 Unity/C# 编辑器工具经验时，阶段 0–2 的可展示 MVP 通常是数周级工作；覆盖多种交通、港口、机场、资产导入规则与稳定批处理则是数月级。实际工作量主要由样例资产品质、编辑交互复杂度、性能目标和需要的领域规则决定，不应只按代码行数估算。

### 阶段验收指标（MVP）

- 同一配置与 Seed 重建后，拓扑、位置、尺寸和变体选择一致。
- 生成器不会删除用户未标记为生成内容的场景对象。
- 参数范围无效或资产缺失时，先给出可读报告，再终止/跳过有问题的部分。
- 4×4 街区规模能在目标开发机上交互迭代；更大规模采用分区生成，具体目标时间需在阶段 0 实测确定。
- 生成的道路连通、地块不重叠；道路边界、地块和建筑可在 Unity 中单独选取或按区域组管理。
- 打开/关闭示例项目后仍能从配置重建结果，不依赖未提交的临时 Editor 状态。
- 需要人工编辑的关键 Prefab 能替换，而不要求改动生成器代码。

## 8. 测试与质量策略

研发时建立自动化检查（不是本计划阶段执行的验证）：

- 编辑器程序集编译检查及支持 Unity 版本检查。
- 固定 Seed 快照/属性测试：尺寸边界、路网连接、地块冲突、资产引用缺失。
- Mesh 检查：顶点索引范围、法线/边界、材质子网格对应、32 位索引的平台提示。
- Editor 场景检查：生成根节点与配置关联、重复生成清理范围、Undo/取消行为。
- 批处理冒烟生成：从命令行打开项目、调用静态入口、确认输出 Scene/Prefab/报告和退出码。
- 人工视口评审：风格一致、道路可读、相机视角能表达空间尺度。

## 9. 近期研发顺序（建议）

第一步不要做完整大都市。先在目标 Unity 6 项目中建立可安装的 Editor 包，做一套原创、简单但统一的低模样例资产和 `WorldBuildProfile`。紧接着完成 4×4 网格街区的“生成—预览—改参数—重生成—保存场景”闭环。这个闭环通过评审后，再把路网抽象成可接入铁路、地铁、单轨和道路变体的连接图，最后逐步加入港口、机场和大地形。

插件首版需确保：没有额外付费服务也能工作；能用内置程序几何展示；能引用用户自己的 Prefab；Seed 和配置可以交给另一位团队成员复现。

## 10. 参考资料

- 用户提供的本地背景材料：`有基础，从几分钟到几小时出模型.pdf`（参数化建模、低精度先行、资产拼装与复用）。
- Unity 6 EditorWindow：<https://docs.unity3d.com/6000.0/Documentation/ScriptReference/EditorWindow.html>
- Unity 6 Assembly Definitions：<https://docs.unity3d.com/6000.0/Documentation/Manual/assembly-definitions-intro.html>
- Unity 6 MeshData：<https://docs.unity3d.com/6000.0/Documentation/ScriptReference/Mesh.MeshData.html>
- Unity 6 PrefabUtility.SaveAsPrefabAsset：<https://docs.unity3d.com/6000.0/Documentation/ScriptReference/PrefabUtility.SaveAsPrefabAsset.html>
- Unity 6 AssetDatabase.StartAssetEditing：<https://docs.unity3d.com/6000.0/Documentation/ScriptReference/AssetDatabase.StartAssetEditing.html>
- Unity 6 Editor 命令行参数：<https://docs.unity3d.com/6000.0/Documentation/Manual/EditorCommandLineArguments.html>
- Unity 6 Undo.RegisterCreatedObjectUndo：<https://docs.unity3d.com/6000.0/Documentation/ScriptReference/Undo.RegisterCreatedObjectUndo.html>

---
状态：研发计划与代码骨架草案；尚未创建 Unity 包代码或样例场景。

