$unity = "C:\Program Files\Unity 6000.0.0f1\Editor\Unity.exe"
$proj  = "C:\Users\bnna7\workspace\Houdini\LowPolyCity"
$log   = Join-Path $proj "lpw_expansion.log"
if (Test-Path $log) { Remove-Item $log -Force }
Set-Location $proj
$p = Start-Process -FilePath $unity -ArgumentList @(
  "-batchmode","-quit",
  "-projectPath",$proj,
  "-executeMethod","LowPolyWorldBuilder.Editor.Batch.ExpansionBatchEntryPoint.GenerateExpansionPack",
  "-logFile",$log
) -Wait -PassThru
Write-Output ("UNITY_EXIT=" + $p.ExitCode)
