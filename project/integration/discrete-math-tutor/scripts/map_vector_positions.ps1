param([int]$Chapter=0)
$ErrorActionPreference='Stop'
$demoRoot=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$sourceRoot=Join-Path $demoRoot '..\..\server\data\textbook_raw'
$catalog=Get-Content -LiteralPath (Join-Path $demoRoot 'knowledge\extracted_multimodal\vector_catalog.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$mapped=New-Object Collections.Generic.List[object]
if($Chapter -gt 0) {
 $previous=Get-Content -LiteralPath (Join-Path $demoRoot 'knowledge/extracted_multimodal/vector_positions.json') -Raw -Encoding UTF8 | ConvertFrom-Json
 foreach($item in $previous) {if($item.chapter_id -ne $Chapter){$mapped.Add($item)}}
 $catalog=@($catalog | Where-Object {$_.chapter_id -eq $Chapter})
}
$word=New-Object -ComObject Word.Application
$word.Visible=$false; $word.DisplayAlerts=0; $word.AutomationSecurity=3
try {
 foreach($group in ($catalog | Group-Object word_source)) {
  $doc=$null
  try {
   $doc=$word.Documents.Open((Join-Path $sourceRoot $group.Name),$false,$true,$false)
   foreach($item in $group.Group) {
    $name='Rag_'+($item.id -replace '-','_')
    $r=$doc.Range([int]$item.anchor_start,[int]$item.anchor_start)
    [void]$doc.Bookmarks.Add($name,$r)
   }
   # 仅在内存中添加定位书签；不保存、不修改源教材。
   [xml]$xml=$doc.WordOpenXML
   $ns=New-Object Xml.XmlNamespaceManager($xml.NameTable)
   $ns.AddNamespace('pkg','http://schemas.microsoft.com/office/2006/xmlPackage')
   $ns.AddNamespace('w','http://schemas.openxmlformats.org/wordprocessingml/2006/main')
   $body=$xml.SelectSingleNode('//pkg:part[@pkg:name="/word/document.xml"]/pkg:xmlData/w:document/w:body',$ns)
   $positions=@{}; $index=0
   foreach($block in $body.ChildNodes) {
    if($block.LocalName -eq 'bookmarkStart') {$positions[$block.GetAttribute('name','http://schemas.openxmlformats.org/wordprocessingml/2006/main')]=$index; continue}
    if($block.LocalName -eq 'bookmarkEnd'){continue}
    foreach($bookmark in $block.SelectNodes('.//w:bookmarkStart',$ns)) {
     $positions[$bookmark.GetAttribute('name','http://schemas.openxmlformats.org/wordprocessingml/2006/main')]=$index
    }
    $index++
   }
   foreach($item in $group.Group) {
    $name='Rag_'+($item.id -replace '-','_')
    if(-not $positions.ContainsKey($name)){throw ('Missing bookmark '+$name)}
    $mapped.Add([pscustomobject]@{id=$item.id;chapter_id=$item.chapter_id;block_index=$positions[$name];body_block_count=$index;method='Word in-memory bookmark'})
   }
   [IO.File]::WriteAllText((Join-Path $demoRoot 'knowledge\extracted_multimodal\vector_positions.json'),(ConvertTo-Json -InputObject ([object[]]$mapped.ToArray()) -Depth 8),(New-Object Text.UTF8Encoding($false)))
   Write-Output ('Mapped '+$group.Name+' blocks='+$index)
  } finally {if($doc){$doc.Close($false)}}
 }
} finally {$word.Quit();[void][Runtime.InteropServices.Marshal]::ReleaseComObject($word)}
[IO.File]::WriteAllText((Join-Path $demoRoot 'knowledge\extracted_multimodal\vector_positions.json'),(ConvertTo-Json -InputObject ([object[]]$mapped.ToArray()) -Depth 8),(New-Object Text.UTF8Encoding($false)))
