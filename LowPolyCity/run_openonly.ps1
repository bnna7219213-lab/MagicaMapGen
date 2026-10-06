$unity = "C:\Program Files\Unity 6000.0.0f1\Editor\Unity.exe"
$proj  = "C:\Users\bnna7\workspace\Houdini\LowPolyCity"
$log   = "C:\Users\bnna7\workspace\Houdini\LowPolyCity\lpw_openonly.log"
if (Test-Path $log) { Remove-Item $log -Force }
$args1 = "-batchmode -quit -projectPath `"$proj`" -logFile `"$log`""
$p = Start-Process -FilePath $unity -ArgumentList $args1 -Wait -PassThru
Write-Output ("UNITY_EXIT=" + $p.ExitCode)
