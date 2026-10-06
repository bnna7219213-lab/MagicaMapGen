@echo off
"C:\Program Files\Unity 6000.0.0f1\Editor\Unity.exe" -batchmode -quit -projectPath "C:\Users\bnna7\workspace\Houdini\LowPolyCity" -executeMethod LowPolyWorldBuilder.Editor.Batch.BatchGenerationEntryPoint.GenerateDefaultDemo -logFile "C:\Users\bnna7\workspace\Houdini\LowPolyCity\lpw_smoke.log"
echo UNITY_EXIT=%ERRORLEVEL%
