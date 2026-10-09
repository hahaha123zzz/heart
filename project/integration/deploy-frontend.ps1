$ErrorActionPreference = 'Stop'

$sourceRoot = Join-Path $PSScriptRoot 'discrete-math-tutor'
$targetRoot = 'C:\Users\xinzi\Desktop\psychology-ai-tutor'
$expectedTarget = 'C:\Users\xinzi\Desktop\psychology-ai-tutor'
$targetResolved = (Resolve-Path -LiteralPath $targetRoot).Path

if ($targetResolved -ne $expectedTarget) {
    throw "Unexpected deployment target: $targetResolved"
}

$relativeFiles = @(
    'main.py',
    'web_api.py',
    'orchestrator.py',
    'agents\response_generator.py',
    'database\models.py',
    'knowledge\course.py',
    'knowledge\textbook.py',
    'frontend\index.html',
    'frontend\styles.css',
    'frontend\app.js',
    'README.md',
    '3-start-api.bat'
)

foreach ($relativePath in $relativeFiles) {
    $sourcePath = Join-Path $sourceRoot $relativePath
    $targetPath = Join-Path $targetRoot $relativePath

    if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) {
        throw "Missing staged file: $sourcePath"
    }

    $targetDirectory = Split-Path -Parent $targetPath
    New-Item -ItemType Directory -Path $targetDirectory -Force | Out-Null
    Copy-Item -LiteralPath $sourcePath -Destination $targetPath -Force

    $sourceHash = (Get-FileHash -LiteralPath $sourcePath).Hash
    $targetHash = (Get-FileHash -LiteralPath $targetPath).Hash
    if ($sourceHash -ne $targetHash) {
        throw "Verification failed after copying: $relativePath"
    }

    Write-Output "Updated $relativePath"
}

Write-Output 'Preserved .env, .venv, databases, and all non-listed project files.'
