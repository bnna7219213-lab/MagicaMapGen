$unity = "C:\Program Files\Unity 6000.0.0f1\Editor\Unity.exe"
$proj  = "C:\Users\bnna7\workspace\Houdini\testproj3"
$log   = "C:\Users\bnna7\workspace\Houdini\testproj3\open.log"
Set-Location "C:\"
$p = Start-Process -FilePath $unity -ArgumentList "-batchmode","-quit","-projectPath",$proj,"-logFile",$log -Wait -PassThru
Write-Output ("UNITY_EXIT=" + $p.ExitCode)
