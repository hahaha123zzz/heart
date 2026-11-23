param([ValidateSet("start","stop","restart","status")][string]$Action="status")
$ErrorActionPreference="Stop"
$runtimeRoot=Split-Path -Parent $PSScriptRoot
$runtimeTools=Get-Content -LiteralPath (Join-Path $PSScriptRoot "runtime-tools.json") -Raw -Encoding UTF8 | ConvertFrom-Json
& $runtimeTools.python (Join-Path $PSScriptRoot "manage_student_local.py") $Action --root $runtimeRoot
exit $LASTEXITCODE
