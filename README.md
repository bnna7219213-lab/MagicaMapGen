# MagicaMapGen

**确定性游戏原型地图生成器。** 把一个游戏想法，转成可交付、可复现、引擎可消费的设计原稿地图。

- 内部立项演示视频：[`tools/MagicaMapGen/tools/MagicaMapGen_promo.mp4`](tools/MagicaMapGen/tools/MagicaMapGen_promo.mp4)（1600x900，101 秒）
- 生成器文档：[`mapgen/README.md`](mapgen/README.md)
- 路径 B 执行基线（Unity 消费端）：[`path_b_baseline.md`](path_b_baseline.md)

---

## 核心主张

市面上的随机地图生成器能产出「看起来像地图」的图，但**说不出它保证了什么**。MagicaMapGen 的定位不是又一个随机生成器，而是**一份可以被机器执行的原型规格**：

1. **主题即契约。** 说雪地绝不给草原。契约不通过时退出码非零，而不是悄悄给你一张草原图。
2. **逐字节可复现。** 同一个 seed，无论换格式集、换输出目录、换机器，产物哈希完全一致。
3. **引擎无关的交付。** 主产物是一个自描述的 `map.json`，换引擎只需要写消费端。

## 四层模型

```
Theme 主题      确定契约：说雪地绝不给草原
  Category 类别    主题下的物体与各自数量
    Distribution 分布  这一类怎么铺开：泊松盘 / 团簇 / 均匀 / 网格
      Region 区域    局部概率化：北部密林、东部山脊（优先级解决重叠归属）
```

换一层只改一个字符串；新增主题或分布只需注册表加一行，GUI 与导出会自动跟上。

## 快速开始

```bash
# 生成一份雪地地图（契约保证 + schema 校验）
python -m mapgen --theme snow --seed 20261002 --out out/

# 用配置文件（推荐：设计师面对的文档就是配置）
python -m mapgen --config configs/snow_north_taiga.json --out out/

# 查看主题会产出什么（GUI 的参数表单也由它驱动）
python -m mapgen --describe-theme snow

# 运行测试（80 项）
python tests/test_mapgen.py
```

**退出码**：`0` 成功且契约通过 · `1` 契约硬失败 · `2` 用法/配置错误 · `3` I/O 或生成异常 · `4` 产物未通过 `map.schema.json` 校验。

## 产物

| 文件 | 用途 |
|------|------|
| `*_map.json` | **主交付**：引擎可消费的地图数据（schema v3，带单位声明） |
| `*_height.pgm` | 16-bit 无损高度场，可直接进 Houdini / Gaea / 地形工具 |
| `*_scene.obj` + `.mtl` | 低多边形三维场景，附 Houdini 导入脚本 |
| `*_biomes.csv` / `*_scatter.csv` | 逐格与逐实例表格，便于 diff 与审阅 |
| `*_report.json` / `.txt` | 人类可读报告，含契约逐项判定 |

## 桌面工具

```bash
cd tools/MagicaMapGen
python -m app.main              # 启动 GUI
python tools/smoke_gui.py       # 无头冒烟 + 自动截图
python tools/make_skins.py      # 重新生成暗色奇幻边框素材
```

GUI 通过命令行调用生成器而非 import 它，因此界面看到的退出码与 CI 完全一致。

## Unity 消费端

`LowPolyCity/Packages/com.studio.lowpoly-world-builder` 包含一个已验证的导入路径：

```bash
python unity_import_smoke.py    # 6 份 map.json → Unity batchmode → 校验对象数与退出码
```

当前状态：6/6 文档导入验证通过，场景对象数与 `stats.instance_count` 完全一致，退出码 0。

## 项目结构

```
mapgen/                     生成器内核（纯标准库 Python，无第三方依赖）
  contract.py               契约层：把「说到做不到」变成非零退出码
  distributions.py          可替换的分布策略注册表
  regions.py                区域掩码与优先级归属
  export/                   产物写出 + map.schema.json
tools/MagicaMapGen/         PyQt6 桌面工具（界面即规格）
  app/                      bridge / param_form / region_editor / preview / skin
  assets/skins/             程序化生成的九宫格边框
LowPolyCity/                Unity 包（可选消费端）
tests/test_mapgen.py        80 项测试
```

## 当前状态与已知局限

- 两套主题（雪地 / 岛屿），32–1024 全尺寸区间契约零失败。
- 岛屿主题在部分 seed 会被契约拦下（如 seed 88 的 `min_biome_coverage`）——这是契约在正常工作，不是缺陷。
- 编辑反馈闭环（`edits.json` + 增量重生成）尚未实现，见 `path_b_baseline.md` 阶段 2。

## 许可

MIT，见 [LICENSE](LICENSE)。
