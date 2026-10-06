# Low Poly World Builder

Unity 6 编辑器插件：参数化、可复现、可组合的低多边形场景原型生成器。
MVP 为 4x4 卡通都市街区闭环：配置 → 预览 → 生成 → 改参重建 → 保存 Scene/Prefab/报告。
铁路、地铁、港口、机场通过同一 BuildPlan / AssetCatalog 管线在后续阶段接入。

## 安装

将本包放入工程的 `Packages/com.studio.lowpoly-world-builder/`（本仓库的 `LowPolyCity`
工程已按此配置），或在 Package Manager 中 "Add package from disk"。

## 快速开始（5 分钟）

1. 菜单 `Tools > Low Poly World Builder` 打开生成窗口。
2. 点 "Create Default Profile"（生成 4x4 配置、三个分区、默认调色板）。
3. 点 "Preview (proxy)" 看代理体块；改 Seed / 参数再预览。
4. 点 "Generate" 在场景中生成正式网格。
5. 点 "Generate + Save Scene/Prefab/Report" 落地到 `Assets/LowPolyWorldOutput/`。

## 批处理

```
"C:\Program Files\Unity 6000.0.0f1\Editor\Unity.exe" -batchmode -quit ^
  -projectPath "C:\path\to\LowPolyCity" ^
  -executeMethod LowPolyWorldBuilder.Editor.Batch.BatchGenerationEntryPoint.GenerateWorld ^
  -lpwProfile "Assets/LowPolyWorldBuilder/Config/CartoonCity_4x4.asset" ^
  -lpwOut "Assets/LowPolyWorldOutput" -lpwSeed 12345 -logFile lpw.log
```

退出码：0 成功，2 校验失败，3 找不到配置，4 生成异常。
零参数冒烟入口：`...BatchGenerationEntryPoint.GenerateDefaultDemo`。

## 交通主题扩展与规模样例

运行 `LowPolyWorldBuilder.Editor.Batch.ExpansionBatchEntryPoint.GenerateExpansionPack`，会以固定 Seed 生成 City、Railway、Metro、Harbor、Airport 五种主题的 4x4 和 16x16 场景，并保存 Scene、Prefab 和 JSON/TXT 报告。

- 配置：`Assets/LowPolyWorldBuilder/Config/Expansion/{Theme}_{size}x{size}.asset`
- 输出：`Assets/LowPolyWorldOutput/Expansion/{size}x{size}/{Theme}/`
- 报告包含主题、网格规模、Seed、路段/街区/建筑原型/道具数量和生成耗时。
- 建筑形体按主题和分区抽样：Railway 有站房/列车库，Metro 有地铁站厅/阶梯高塔，Harbor 有港区仓库/筒仓/灯塔，Airport 有机库/航站楼/塔台；City 保留住宅/商业/办公混合。
- Airport 保留跑道与航站楼地块；Harbor 保留水域/码头地块；场景设施与周边建筑采用不同轮廓。

```powershell
Unity.exe -batchmode -quit -projectPath "C:\path\to\LowPolyCity" -executeMethod LowPolyWorldBuilder.Editor.Batch.ExpansionBatchEntryPoint.GenerateExpansionPack -logFile lpw-expansion.log
```

## 测试

Window > Test Runner > EditMode > LowPolyWorldBuilder.EditorTests
（固定 Seed 复现性、路网连通性、地块不重叠、随机流平台稳定性）。

## 文档

- Documentation~/GettingStarted.md
- Documentation~/AssetAuthoring.md
- Documentation~/BatchGeneration.md
