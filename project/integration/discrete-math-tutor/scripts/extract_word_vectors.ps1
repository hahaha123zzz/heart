$ErrorActionPreference='Stop'
$demoRoot=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$projectRoot=(Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$sourceRoot=Join-Path $projectRoot 'server\data\textbook_raw'
$outputRoot=Join-Path $demoRoot 'knowledge\extracted_multimodal'
$utf8=New-Object Text.UTF8Encoding($false)
$log=Join-Path $outputRoot 'vectors.log'
$records=New-Object Collections.Generic.List[object]
$word=New-Object -ComObject Word.Application
$word.Visible=$false; $word.DisplayAlerts=0; $word.AutomationSecurity=3
try {
foreach($file in (Get-ChildItem -LiteralPath $sourceRoot -Filter '*.doc' | Sort-Object Name)) {
$chapter=[int]([regex]::Match($file.Name,'第\s*(\d+)\s*章').Groups[1].Value)
$dir=Join-Path $outputRoot ('assets\chapter_{0:00}' -f $chapter)
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$doc=$null
try {
$doc=$word.Documents.Open($file.FullName,$false,$true,$false)
$seen=@{}; $number=9000
foreach($shape in $doc.Shapes) {
# 嵌入图片已从 Word 包提取；此处补充组合图、自选图形与文本框。
if($shape.Type -in @(7,13)) {continue}
$r=$shape.Anchor.Duplicate; [void]$r.Expand(4)
$key=[string]$r.Start
if($seen.ContainsKey($key)){continue}; $seen[$key]=$true
$number++; $id='image-{0:00}-{1:0000}' -f $chapter,$number
$filename='assets/chapter_{0:00}/{1}.emf' -f $chapter,$id
$target=Join-Path $outputRoot $filename
[IO.File]::WriteAllBytes($target,[byte[]]$r.EnhMetaFileBits)
$contextRange=$doc.Range([Math]::Max(0,$r.Start-450),[Math]::Min($doc.Content.End-1,$r.End+450))
$context=$contextRange.Text -replace '[\x00-\x08\x0b\x0c\x0e-\x1f]',''
$records.Add([pscustomobject]@{id=$id;kind='image';chapter_id=$chapter;source=($file.BaseName+'.txt');word_source=$file.Name;filename=$filename;extension='.emf';sha256=(Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant();anchor_start=$r.Start;context=$context;caption=('第'+$chapter+'章教材绘图（Word 锚点 '+$r.Start+'，图号未核定）');review_status='approved';extraction_method='Word.Range.EnhMetaFileBits'})
}
[IO.File]::AppendAllText($log,('OK|'+$file.Name+'|'+$seen.Count)+[Environment]::NewLine,$utf8)
} finally {if($doc){$doc.Close($false)}}
}
} finally {$word.Quit(); [void][Runtime.InteropServices.Marshal]::ReleaseComObject($word)}
$json=ConvertTo-Json -InputObject ([object[]]$records.ToArray()) -Depth 12
[IO.File]::WriteAllText((Join-Path $outputRoot 'vector_catalog.json'),$json,$utf8)
Write-Output ('Vector anchor previews: '+$records.Count)
