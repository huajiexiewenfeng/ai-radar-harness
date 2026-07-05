param(
  [string]$TaskName = "AI Radar Daily",
  [string]$Time = "08:30",
  [int]$SinceHours = 48,
  [int]$Limit = 30
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RunDaily = Join-Path $ScriptDir "run_daily.ps1"

if (-not (Test-Path -LiteralPath $RunDaily)) {
  throw "run_daily.ps1 not found: $RunDaily"
}

$escapedRunDaily = '"' + $RunDaily + '"'
$taskArgs = "-NoProfile -ExecutionPolicy Bypass -File $escapedRunDaily -SinceHours $SinceHours -Limit $Limit"

schtasks.exe /Create /F /SC DAILY /TN $TaskName /TR "powershell.exe $taskArgs" /ST $Time
if ($LASTEXITCODE -ne 0) {
  exit $LASTEXITCODE
}

Write-Host "Installed scheduled task '$TaskName' at $Time"
