# legacy/ — 已退役的孤立源码

这里存放**不再维护、也不被任何构建引用**的历史文件。移动（而非删除）是为了可逆：本仓库没有 git，保留一份以便追溯。

## IslandMapGenerator.cs

- **状态**：孤儿代码。整个工作区没有任何 `.csproj` / `.sln`，没有东西能编译它；文件内 0 处 `UnityEngine` 引用。
- **问题**：约第 867 行**无条件**写出 `island_preview.html`——与"主交付是可导入 Houdini 的 3D 场景、不是 HTML"的当前定位直接矛盾。
- **为何保留**：作为早期 C# 岛屿生成思路的记录。请勿在新工作中引用。

## island_generator.py

- **状态**：已被 `mapgen/` 包取代。它是**单层**生成器（一个硬编码岛屿流程），没有"主题→类别→分布"三层模型、没有契约校验、`out_dir` 硬编码为 `island_out/`（无 `--out`），分布字符串是写死的标签而非可切换策略。
- **迁移去向**：其经过验证的确定性内核已**逐字提取**进 `mapgen/`——
  - `DetRandom` → `mapgen/rng.py`
  - 噪声/FBM → `mapgen/noise.py`
  - 岛屿 biome 默认值 → `mapgen/themes/island.py`
- **为何保留**：`mapgen` 的算法血缘来源；对账旧产物（`island_out/`）时仍有用。

---

当前主交付见仓库根的 `mapgen/`（README 在 `mapgen/README.md`）。
