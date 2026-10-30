param([string]$CourseId = 'experimental-psychology-3', [switch]$AllChapters)
$ErrorActionPreference = 'Stop'
if ($CourseId -ne 'experimental-psychology-3') { throw '课程ID不符合预期' }
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$course = Join-Path $root 'knowledge\courses\experimental-psychology-3'
$manifest = Get-Content -LiteralPath (Join-Path $course 'manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if ($AllChapters) {
 if ($manifest.full_import.chapters.Count -ne 11) { throw '请先完成11章原始资源导入' }
 $jobs = @($manifest.full_import.chapters)
} else {
 $jobs = @(@{chapter_id=4;docx='sample\第4章被试间设计.docx'})
}
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
$word.AutomationSecurity = 3
$word.Options.UpdateLinksAtOpen = $false
try {
 foreach ($job in $jobs) {
  $number = [int]$job.chapter_id
  $source = Join-Path $course $job.docx
  $folder = Split-Path -Parent $source
  $pdf = Join-Path $folder ('chapter_{0:d2}.generated.pdf' -f $number)
  $chapter = $manifest.chapters | Where-Object { $_.id -eq $number }
  $doc = $null
  try {
   Write-Output ('OPEN|' + $number)
   $doc = $word.Documents.Open([string]$source, $false, $true, $false)
   $doc.Repaginate()
   $lookup = @{}
   foreach ($s in $chapter.sections) { $lookup[($s.title -replace '\s','')] = $s }
   $records = @()
   foreach ($line in $doc.Content.Text.Split([char]13)) {
    $text = ($line -replace '[\x00-\x1f]','').Trim()
    $key = $text -replace '\s',''
    if ($lookup.ContainsKey($key)) {
     $range = $doc.Content.Duplicate
     try {
      $range.Find.ClearFormatting();$range.Find.Text = $text;$range.Find.Wrap = 0;$range.Find.MatchWildcards = $false
      if (!$range.Find.Execute()) { throw ('节标题无法定位：' + $text) }
      $records += @{id=$lookup[$key].id;title=$lookup[$key].title;generated_page=[int]$range.Information(3);word_start=[int]$range.Start}
      $lookup.Remove($key)
     } finally { [void][Runtime.InteropServices.Marshal]::ReleaseComObject($range) }
    }
   }
   if ($lookup.Count -ne 0) { throw ('第' + $number + '章节标题定位不完整') }
   $doc.ExportAsFixedFormat([string]$pdf,17)
   $payload = @{course_id=$manifest.course_id;chapter_id=$number;status='requires_visual_verification';source_sha256=(Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLower();pdf_sha256=(Get-FileHash -LiteralPath $pdf -Algorithm SHA256).Hash.ToLower();page_policy='generated_pdf_pages';sections=$records}
   [IO.File]::WriteAllText((Join-Path $folder 'word_pages.json'),($payload | ConvertTo-Json -Depth 6),[Text.UTF8Encoding]::new($false))
   Write-Output ('OK|' + $number + '|' + $records.Count)
  } finally {
   if ($null -ne $doc) { $doc.Close($false); [void][Runtime.InteropServices.Marshal]::ReleaseComObject($doc) }
  }
 }
} finally {
 $word.Quit();[void][Runtime.InteropServices.Marshal]::ReleaseComObject($word)
}
