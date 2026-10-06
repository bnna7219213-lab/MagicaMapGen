# Batch Generation(批处理)

## 标准入口

```
Unity.exe -batchmode -quit -projectPath <工程目录> ^
  -executeMethod LowPolyWorldBuilder.Editor.Batch.BatchGenerationEntryPoint.GenerateWorld ^
  -lpwProfile "Assets/LowPolyWorldBuilder/Config/CartoonCity_4x4.asset" ^
  [-lpwOut "Assets/LowPolyWorldOutput"] [-lpwSeed 42] [-logFile build.log]
```

产物(写入 `-lpwOut` 或 Profile 的 Output Folder):
- `<worldName>.unity` — 生成的场景
- `<worldName>.report.json` — 结构化报告(Seed、版本、资产引用、校验条目)
- `<worldName>.report.txt` — 人读摘要(统计 + 每条 Info/Warning/Error)

## 退出码

| 码 | 含义 |
|---|---|
| 0 | 成功 |
| 2 | 参数校验失败或报告含 Error |
| 3 | `-lpwProfile` 缺失或资产不存在 |
| 4 | 生成过程抛异常 |

## 冒烟入口(CI 用)

`-executeMethod ...BatchGenerationEntryPoint.GenerateDefaultDemo` 无需任何
`lpw*` 参数:自动创建默认 4x4 配置并完整生成,用于"克隆仓库 → 一键验证"。

## 注意

- `-quit` 与 `EditorApplication.Exit(code)` 配合,退出码即自动化信号。
- 报告写盘在 `AssetDatabase.StartAssetEditing/StopAssetEditing` 的
  try/finally 中,异常不会把 Asset Database 留在暂停状态。
