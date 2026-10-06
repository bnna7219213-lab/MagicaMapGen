# 雪地（snow）地图场景 — Houdini 导入

`snow_north_taiga_scene.obj` 是可编辑的三维场景几何，不是截图。Houdini 中用 **File > Import > Geometry > Wavefront OBJ** 打开，或直接把 OBJ 拖进视口。同名 `.mtl` 必须放在旁边，否则材质解析不到。

## 场景结构

| object | 内容 |
|---|---|
| `Island_Terrain` | 连续高度场网格，按 biome 分 primitive group |
| `Ocean_Surface` | 海平面单面片 |
| `Inland_Lake_Water` | 每个湖独立水平面，组名 `lake_NN` |
| `River_Network` | 相邻河流格连成的条带 |
| `Scatter_trees_sparse` | 稀疏树木（conifer 低模），树群分组 `trees_sparse_cluster_NN` |
| `Scatter_trees_dense` | 密集树木（conifer 低模），树群分组 `trees_dense_cluster_NN` |
| `Scatter_trees_other` | 其它树木（broadleaf 低模），树群分组 `trees_other_cluster_NN` |
| `Scatter_ice_boulders` | 冰岩（boulder 低模），树群分组 `ice_boulders_cluster_NN` |
| `Scatter_snow_drifts` | 雪堆（drift 低模），树群分组 `snow_drifts_cluster_NN` |
| `Scatter_frozen_reeds` | 枯芦苇（reed 低模），树群分组 `frozen_reeds_cluster_NN` |

## 坐标系与单位

- Y-up；世界尺寸 1200 × 1200 单位
- 网格 256×256，每格 `8.0` 米，高度按 `120.0` 米映射
- Seed `20261002`，主题 `snow`

## 已知限制

- **OBJ 不含法线与 UV**：Houdini 导入时会自动计算法线；但没有 UV 通道，MTL 只能作为纯色，要贴图需先在 DCC 里展开。
- 主交付是引擎可消费的地图数据（`*_map.json`）；OBJ 是给人看的三维稿，两者由同一次生成产出。

## 生成原生 .hip

本机未检测到 Houdini，无法直接产出 `.hip`。在 Houdini 的 Python Source Editor 中运行 `snow_north_taiga_build_hip.py`，它会导入 OBJ、建一个总览相机并保存 `.hip`。
