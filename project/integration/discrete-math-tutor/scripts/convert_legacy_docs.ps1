$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$demoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$sourceRoot = Join-Path $projectRoot 'server\data\textbook_raw'
$outputRoot = Join-Path $demoRoot 'knowledge\imported_wordopenxml'
$logPath = Join-Path $outputRoot 'conversion.log'
New-Item -ItemType Directory -Force -Path $outputRoot | Out-Null
$utf8 = New-Object System.Text.UTF8Encoding($false)
function Log([string]$line) { [System.IO.File]::AppendAllText($logPath, $line + [Environment]::NewLine, $utf8) }
$errors = New-Object System.Collections.Generic.List[string]
Log 'BEGIN'
$word = New-Object -ComObject Word.Application
Log 'WORD_READY'
$word.Visible = $false; $word.DisplayAlerts = 0; $word.AutomationSecurity = 3
try {
  $files = Get-ChildItem -LiteralPath $sourceRoot -Filter '*.doc' | Sort-Object Name
  foreach ($file in $files) {
    $dst = Join-Path $outputRoot ($file.BaseName + '.flatopc.xml')
    if ((Test-Path -LiteralPath $dst) -and (Get-Item -LiteralPath $dst).LastWriteTimeUtc -ge $file.LastWriteTimeUtc) { Log ('SKIP|' + $file.Name); continue }
    Log ('START|' + $file.Name)
    $doc = $null
    try {
      $doc = $word.Documents.Open($file.FullName, $false, $true, $false)
      Log ('OPEN|' + $file.Name)
      $xml = $doc.WordOpenXML
      [System.IO.File]::WriteAllText($dst, $xml, $utf8)
      Log ('OK|' + $file.Name + '|' + (Get-Item -LiteralPath $dst).Length)
    } catch { $errors.Add($file.Name); Log ('ERROR|' + $file.Name + '|' + $_.Exception.Message) }
    finally { if ($null -ne $doc) { $doc.Close($false); [void][Runtime.InteropServices.Marshal]::ReleaseComObject($doc) } }
  }
} finally { $word.Quit(); [void][Runtime.InteropServices.Marshal]::ReleaseComObject($word) }
Log 'DONE'
if ($errors.Count -gt 0) { exit 2 }
