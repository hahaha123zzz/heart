param([switch]$Reindex, [switch]$ForceExport)
$ErrorActionPreference = 'Stop'
$demoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$sourceRoot = (Resolve-Path (Join-Path $demoRoot '..\..\server\data\textbook_raw')).Path
$outputRoot = Join-Path $demoRoot 'knowledge\pdf'
New-Item -ItemType Directory -Force -Path $outputRoot | Out-Null
$chapters = Get-Content -LiteralPath (Join-Path $demoRoot 'knowledge\pdf_sections.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$utf8 = New-Object System.Text.UTF8Encoding($false)
function Normalize([string]$value) { return ($value -replace '\s', '') }
$word = New-Object -ComObject Word.Application
$word.Visible = $false; $word.DisplayAlerts = 0; $word.AutomationSecurity = 3
try {
 foreach ($chapter in $chapters) {
  $file = Get-ChildItem -LiteralPath $sourceRoot -Filter '*.doc' | Where-Object { $_.Name -match ('^第' + $chapter.id + '章') } | Select-Object -First 1
  $pdf = Join-Path $outputRoot ('chapter_{0:d2}.pdf' -f [int]$chapter.id)
  $map = Join-Path $outputRoot ('chapter_{0:d2}.word.json' -f [int]$chapter.id)
  $sourceHash = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLower()
  $previous = $null
  if (Test-Path -LiteralPath $map) { $previous = Get-Content -LiteralPath $map -Raw -Encoding UTF8 | ConvertFrom-Json }
  $needsExport = $ForceExport -or !(Test-Path -LiteralPath $pdf) -or $null -eq $previous -or $previous.source_sha256 -ne $sourceHash
  if (!$Reindex -and !$needsExport) { Write-Output ('SKIP|' + $chapter.id); continue }
  $doc = $null
  try {
   Write-Output ('START|' + $file.Name)
   $doc = $word.Documents.Open($file.FullName, $false, $true, $false)
   $doc.Repaginate()
   $sections = @{}
   foreach ($s in $chapter.sections) { $sections[(Normalize $s.title)] = $s }
   $found = @{}
   Write-Output ('PAGINATED|' + $chapter.id)
   $storyText = $doc.Content.Text
   $cursor = 0
   foreach ($line in $storyText.Split([char]13)) {
    $key = Normalize ($line -replace '[\x00-\x1f]', '')
    if ($sections.ContainsKey($key) -and !$found.ContainsKey($key)) {
     $s = $sections[$key]
     $range = $doc.Content.Duplicate
     $range.Find.ClearFormatting()
     $range.Find.Text = ($line -replace '[\x00-\x1f]', '').Trim()
     $range.Find.Wrap = 0
     $range.Find.MatchWildcards = $false
     if (!$range.Find.Execute()) { throw ('Word 标题查找失败: ' + $s.title) }
     $found[$key] = @{ id=[int]$s.id; title=$s.title; page=[int]$range.Information(3); word_start=[int]$range.Start; method='Word Find heading pagination' }
     [void][Runtime.InteropServices.Marshal]::ReleaseComObject($range)
    }
    $cursor += $line.Length + 1
   }
   Write-Output ('MAPPED|' + $chapter.id)
   $records = @()
   foreach ($s in $chapter.sections) {
    $key = Normalize $s.title
    if ($found.ContainsKey($key)) { $records += $found[$key] }
    elseif ($s.id -eq 1) { $records += @{id=[int]$s.id;title=$s.title;page=1;word_start=0;method='chapter start'} }
    else { $records += @{id=[int]$s.id;title=$s.title;page=$null;method='requires PDF verification'} }
   }
   Write-Output ('EXPORT|' + $pdf)
   if ($needsExport) {
    $stagedPDF = Join-Path $outputRoot ('chapter_{0:d2}.export.pdf' -f [int]$chapter.id)
    $doc.ExportAsFixedFormat([string]$stagedPDF, 17, $false, 0, 0, 1, 1, 0, $false, $false, 0, $true, $true, $false)
    Move-Item -LiteralPath $stagedPDF -Destination $pdf -Force
   }
   $payload = @{chapter_id=[int]$chapter.id; source=$file.Name; source_sha256=$sourceHash; sections=$records}
   [System.IO.File]::WriteAllText($map, ($payload | ConvertTo-Json -Depth 6), $utf8)
   Write-Output ('OK|' + $chapter.id)
  } finally { if ($null -ne $doc) { $doc.Close($false); [void][Runtime.InteropServices.Marshal]::ReleaseComObject($doc) } }
 }
} finally { $word.Quit(); [void][Runtime.InteropServices.Marshal]::ReleaseComObject($word) }
