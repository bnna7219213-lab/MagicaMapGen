# Getting Started

1. 打开 `Tools > Low Poly World Builder`。
2. 点击 "Create Default Profile":在 `Assets/LowPolyWorldBuilder/Config/` 下创建
   - `CartoonCity_4x4.asset`(WorldBuildProfile,4x4 街区、80m 街区、12m 道路)
   - `DefaultPalette.asset`(卡通调色板)
   - `Zone_Residential / Zone_Commercial / Zone_Park.asset`(分区权重与高度区间)
   - `DefaultCatalog.asset`(空资产目录,用于接入你自己的 Prefab)
3. "Preview (proxy)":以半透明体块快速查看布局,不产生任何资产。
4. 修改参数(Seed、街区数、道路宽度、密度、高度区间),再次预览。
5. "Generate":生成正式网格,层级为
   `LPW_world > Roads / Blocks > block_x_y > b_* / Scatter`。
6. "Generate + Save":将根节点存为 Prefab、场景存为 .unity、报告存为
   `.report.json/.txt`,输出目录由 Profile 的 Output Folder 决定。

## 交通主题与大规模样例

包内提供 City、Railway、Metro、Harbor、Airport 的 4x4 / 16x16 配置。批量重建请运行
`LowPolyWorldBuilder.Editor.Batch.ExpansionBatchEntryPoint.GenerateExpansionPack`；固定配置与 Seed 位于
`Assets/LowPolyWorldBuilder/Config/Expansion/`，生成 Scene、Prefab 和规模/耗时报告位于
`Assets/LowPolyWorldOutput/Expansion/`。

各主题会选择不同的建筑原型，而非只改变道路设施或配色：铁路区组合站房与多轨车库，地铁区组合入口站厅与阶梯式塔楼，港区组合装卸仓库、筒仓和灯塔，机场区组合大跨机库、航站楼和塔台；构建报告会列出每种建筑原型的数量。

## 手工修改保护

- 重建只清理带 `WorldBuildMarker` 的生成内容;你自己放进场景的物体绝不会被删。
- 想保留某个生成块不被重建:选中该块节点,在 `WorldBuildMarker` 上勾选
  `Manual Lock`(Scene 视图中显示锁图标)。

## 复现性

同一 Profile(内容不变)+ 同一 Seed + 同一插件版本 => 结果完全一致。
把 Profile 资产和插件版本交给同事即可复现。
