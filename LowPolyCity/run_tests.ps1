$unity = "C:\Program Files\Unity 6000.0.0f1\Editor\Unity.exe"
$proj  = "C:\Users\bnna7\workspace\Houdini\LowPolyCity"
$log   = Join-Path $proj "lpw_tests.log"
$res   = Join-Path $proj "lpw_tests.xml"
if (Test-Path $log) { Remove-Item $log -Force }
if (Test-Path $res) { Remove-Item $res -Force }
# Unity 6000.0.0f1 quirk: -projectPath is resolved against the PROCESS CWD;
# cd into the project before launching to avoid a doubled path.
Set-Location $proj
# NOTE: do NOT pass -quit together with -runTests; Unity would shut down before
# the Test Runner executes and silently produce no results XML (exit 0, no tests).
$p = Start-Process -FilePath $unity -ArgumentList @(
  "-batchmode",
  "-projectPath",$proj,
  "-runTests",
  "-testPlatform","EditMode",
  "-testResults",$res,
  "-logFile",$log
) -Wait -PassThru
Write-Output ("UNITY_EXIT=" + $p.ExitCode)
if (Test-Path $res) {
  [xml]$x = Get-Content $res
  $run = $x.'test-run'
  if ($run) {
    Write-Output ("TESTS total=" + $run.total + " passed=" + $run.passed + " failed=" + $run.failed + " skipped=" + $run.skipped)
  } else {
    Write-Output "No test-run element found in results XML (tests may not have run)."
  }
} else {
  Write-Output "No test results XML produced."
}
