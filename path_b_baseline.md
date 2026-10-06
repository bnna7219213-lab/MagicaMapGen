# 路径 B 执行基线：mapgen → Unity 引擎消费

> 本文是路径 B（mapgen 产出通用契约，Unity 只做消费端）的执行基线。
> 状态：阶段 0 的 Python 半边已完成并通过测试；Unity 半边待做。
> 最后更新：2026-10-06

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


## 2. 阶段 1：让 Unity 端表现好（~10h）

- `moisture_rle` 已就绪 → 接 triplanar 湿度混合与植被色调（3h）
- `regions[].priority`（int）：map.json 目前只有 `id/shape/bounds/cells/overrides`，重叠区域无覆盖层级，Unity 无法推断（0.5h）
- `instances[].cluster_hierarchy`：**只需补跨类 parent/child**（树+草同属一簇），不必从零做——已有 `instances[].cluster` + `categories[].clusters` 群心（2h）
- `MapImportWindow`：拖拽 map.json、预览元数据、选覆盖 profile（3h）
- `features.scatter_density`（每类可放置域密度图），让 Unity 可视化"为什么这里为空"（2h）

## 3. 阶段 2：编辑-反馈闭环（~12h，可滚动交付）

数据流：Unity 导出 `edits.json` → mapgen `--overlay` 只重生成脏区 → 新 map.json 回传刷新。

| 模块 | 改动 | 估量 |
|------|------|------|
| `mapdata.py` | `read_map_json` / `decode_rle`，反向还原网格与实例 | 3h |
| `scatter.py` | `place_all` 支持 `exclude_instances` / `frozen_instances` | 3h |
| `cli.py` | `--overlay edits.json --incremental`：load base → apply → 脏区重生成 | 5h |
| Unity | `SceneDiffer`（事务监听 → edits.json）+ `OverlayReceiver`（调 CLI、轮询、刷新） | 6h |

主要风险：RLE 8-bit 的 0.47 m 量化损失 → `edits.json` 走**实例级**操作，网格 RLE 仅作视觉参考；`DetRandom.fork` 链已支持确定性分叉，增量模式挂 seed 链即可隔离未编辑区。

## 4. 为什么不选路径 A（就地修 Unity）

| | 路径 A | 路径 B |
|---|---|---|
| 独立可交付性 | Unity 是唯一生成端 | mapgen 独立产出，Unity 只是可选消费端 |
| 确定性内核 | 算法已验证但 C# 未实机确认 | mapgen 已生产级验证，Unity 只消费结果 |
| 新主题/新分布 | 改 C# | 改 Python（已有注册表，已验证） |
| 跨引擎复用 | 无 | map.json 为通用契约，换引擎只写消费端 |

## 5. 未采用的原方案条目

- `heightmap_raw_url` 改为**引用**已有 PGM，而非新建高度图产出。
- 集群层级复用既有 `cluster` / `clusters`，只补跨类父子关系。
- `moisture_rle` 从原 P1 **提前进阶段 0**：数据已在内存，导出 ~30 分钟，却直接解锁 Unity 端湿度混合。
- map.json 顶层实际有 15 个块（远超"6 大类"），扩展点须先对齐 schema，避免与 `stats` / `contract` 撞语义。
