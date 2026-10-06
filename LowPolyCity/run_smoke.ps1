$unity = "C:\Program Files\Unity 6000.0.0f1\Editor\Unity.exe"
$proj  = "C:\Users\bnna7\workspace\Houdini\LowPolyCity"
$log   = Join-Path $proj "lpw_smoke.log"
if (Test-Path $log) { Remove-Item $log -Force }
# Unity 6000.0.0f1 quirk: -projectPath is resolved against the PROCESS CWD;
# when launched from an unrelated cwd the path gets doubled. cd into the
# project (or any neutral dir) before launching.
Set-Location $proj
$p = Start-Process -FilePath $unity -ArgumentList @(
  "-batchmode","-quit",
  "-projectPath",$proj,
  "-executeMethod","LowPolyWorldBuilder.Editor.Batch.BatchGenerationEntryPoint.GenerateDefaultDemo",
  "-logFile",$log
) -Wait -PassThru
Write-Output ("UNITY_EXIT=" + $p.ExitCode)
