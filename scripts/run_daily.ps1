param(
  [string]$Date = "",
  [int]$SinceHours = 48,
  [int]$Limit = 30,
  [string]$PythonExe = "python"
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Resolve-Path (Join-Path $ScriptDir "..")
$RunScript = Join-Path $Root "scripts\run_ai_radar.py"

$VendorPath = Join-Path $Root ".vendor"
$LibPath = Join-Path $Root "lib"
$env:PYTHONPATH = "$VendorPath;$LibPath"

$argsList = @($RunScript, "--since-hours", "$SinceHours", "--limit", "$Limit")
if ($Date -ne "") {
  $argsList += @("--date", $Date)
}

& $PythonExe @argsList
if ($LASTEXITCODE -ne 0) {
  exit $LASTEXITCODE
}
