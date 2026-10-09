$ErrorActionPreference = 'Stop'

$source = 'C:\Users\xinzi\Desktop\agent-extracted\integration\discrete-math-tutor'
$target = 'C:\Users\xinzi\Desktop\psychology-ai-tutor'
$archive = 'C:\Users\xinzi\Desktop\discrete-math-ai-tutor.zip'

$source = (Resolve-Path -LiteralPath $source).Path.TrimEnd('\')
$target = (Resolve-Path -LiteralPath $target).Path.TrimEnd('\')
if (-not (Test-Path -LiteralPath 'C:\Users\xinzi\Desktop\psychology-ai-tutor.zip' -PathType Leaf)) {
    throw 'Original backup ZIP is missing; refusing to overwrite target.'
}
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$replaceArchive = Test-Path -LiteralPath $archive
if ($replaceArchive) {
    $oldZip = [System.IO.Compression.ZipFile]::OpenRead($archive)
    try {
        $oldNames = @($oldZip.Entries | ForEach-Object { $_.FullName })
        if ($oldNames.Count -ne 65 -or
            @($oldNames | Where-Object { -not $_.StartsWith('discrete-math-ai-tutor/') }).Count -gt 0) {
            throw 'Existing archive is not the source-only archive made by this integration; refusing to overwrite it.'
        }
    }
    finally { $oldZip.Dispose() }
}

$allowed = @('.py', '.json', '.txt', '.md', '.bat')
$files = Get-ChildItem -LiteralPath $source -Recurse -File | Where-Object {
    $_.FullName -notmatch '\\__pycache__\\' -and
    ($allowed -contains $_.Extension -or $_.Name -eq '.env.example')
}
if ($files.Count -lt 50) { throw "Unexpectedly small staged release: $($files.Count) files" }

foreach ($file in $files) {
    $relative = $file.FullName.Substring($source.Length + 1)
    $destination = [System.IO.Path]::GetFullPath((Join-Path $target $relative))
    if (-not $destination.StartsWith($target + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Invalid destination: $destination"
    }
    $parent = Split-Path -Parent $destination
    if (-not (Test-Path -LiteralPath $parent -PathType Container)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }
    Copy-Item -LiteralPath $file.FullName -Destination $destination -Force
}

if ($replaceArchive) { Remove-Item -LiteralPath $archive -Force }
$stream = [System.IO.File]::Open($archive, [System.IO.FileMode]::CreateNew)
try {
    $zip = [System.IO.Compression.ZipArchive]::new($stream, [System.IO.Compression.ZipArchiveMode]::Create, $false)
    try {
        foreach ($file in $files) {
            $relative = $file.FullName.Substring($source.Length + 1).Replace('\', '/')
            $entry = $zip.CreateEntry('discrete-math-ai-tutor/' + $relative)
            $inputStream = [System.IO.File]::OpenRead($file.FullName)
            $entryStream = $entry.Open()
            try { $inputStream.CopyTo($entryStream) }
            finally { $entryStream.Dispose(); $inputStream.Dispose() }
        }
    }
    finally { $zip.Dispose() }
}
finally { $stream.Dispose() }

Write-Output "Copied $($files.Count) source files to $target"
Write-Output "Created source-only archive $archive"
