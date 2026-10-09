param([string]$CatalogName = 'asset_catalog.json')
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\knowledge\extracted_multimodal')).Path
$catalogPath = Join-Path $root $CatalogName
$catalogRoot = Get-Content -LiteralPath $catalogPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($catalogRoot -is [System.Management.Automation.PSCustomObject] -and
    $catalogRoot.PSObject.Properties.Name -contains 'value') {
  $catalog = @($catalogRoot.value)
} else {
  $catalog = @($catalogRoot)
}
foreach ($asset in $catalog) {
  if ($asset.kind -notin @('image','formula')) { continue }
  $source = Join-Path $root $asset.filename
  if (-not (Test-Path -LiteralPath $source)) { continue }
  $pngRel = [IO.Path]::ChangeExtension($asset.filename, '.png')
  $pngPath = Join-Path $root $pngRel
  if ($asset.extension -eq '.png') { $pngPath = $source; $pngRel = $asset.filename }
  else {
    $needsRender = -not (Test-Path -LiteralPath $pngPath)
    if (-not $needsRender) {
      $existing = [System.Drawing.Image]::FromFile($pngPath)
      try { $needsRender = $existing.Width -gt 2048 -or $existing.Height -gt 2048 -or (Get-Item -LiteralPath $source).LastWriteTimeUtc -gt (Get-Item -LiteralPath $pngPath).LastWriteTimeUtc } finally { $existing.Dispose() }
    }
    if ($needsRender) {
      $image = [System.Drawing.Image]::FromFile($source)
      try {
        # 限制发送预览的像素尺寸；原 WMF/EMF 完整保留。
        $scale = [Math]::Min(1.0, 2048.0 / [Math]::Max($image.Width, $image.Height))
        $width = [Math]::Max(1, [int]($image.Width * $scale))
        $height = [Math]::Max(1, [int]($image.Height * $scale))
        $bitmap = [System.Drawing.Bitmap]::new($width, $height)
        try {
          $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
          try { $graphics.Clear([System.Drawing.Color]::White); $graphics.DrawImage($image, 0, 0, $width, $height); $bitmap.Save($pngPath, [System.Drawing.Imaging.ImageFormat]::Png) } finally { $graphics.Dispose() }
        } finally { $bitmap.Dispose() }
      } finally { $image.Dispose() }
    }
  }
  $asset | Add-Member -NotePropertyName preview_filename -NotePropertyValue $pngRel -Force
  $asset | Add-Member -NotePropertyName preview_sha256 -NotePropertyValue (Get-FileHash -LiteralPath $pngPath -Algorithm SHA256).Hash.ToLowerInvariant() -Force
  $asset | Add-Member -NotePropertyName preview_media_type -NotePropertyValue 'image/png' -Force
}
$json = ConvertTo-Json -InputObject ([object[]]$catalog) -Depth 12
[System.IO.File]::WriteAllText($catalogPath, $json, (New-Object System.Text.UTF8Encoding($false)))
Write-Output ('Converted/located PNG previews: ' + @($catalog | Where-Object {$_.preview_filename}).Count)
