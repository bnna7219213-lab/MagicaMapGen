# Asset Authoring(资产模板规范)

复杂语义资产(火车、飞机、车辆、精细建筑)不程序化生成,而是通过
`AssetCatalog` 以 Prefab 模板进入世界。

## 条目字段

| 字段 | 含义 |
|---|---|
| prefab | 你的低模 Prefab(项目资产) |
| category | 类别键:`building.house`、`vehicle.train`、`prop.tree`、`prop.lamp` 等 |
| size | 模板近似尺寸(米),用于地块适配与缩放 |
| weight | 加权随机权重 |
| variantTags | 变体过滤标签 |
| ports | 连接端口名(铁路头、码头边、登机口…),供阶段 5-6 的连接校验 |
| allowScaleVariation | 允许 ±10% 尺寸变化 |

## 方向约定

Prefab 的 +Z 轴应朝向"街道正面"。放置时生成器会把 +Z 旋转到地块临街方向。

## 分区绑定

在 `ZoneProfile.assetCategories` 中填写类别键;该分区的地块将从目录中做
"尺寸适配 + 加权随机"选型。目录中没有合适条目时自动回退到程序几何,
并在报告中给出 Warning(不会静默失败)。

## 端口兼容

`PortCompatibility.CanConnect(a, b)` 按端口名字符串匹配。铁路/港口/机场
模块在放置前必须用连接图 + 端口校验,避免"玩具拼图"式断口。
