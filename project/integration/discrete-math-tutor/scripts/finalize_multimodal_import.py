"""整理批量多模态索引并生成本地核对页面。"""
from pathlib import Path
import hashlib
import html
import json

ROOT = Path(__file__).resolve().parents[1] / 'knowledge' / 'extracted_multimodal'

def main():
    assets = json.loads((ROOT / 'asset_catalog.json').read_text(encoding='utf-8'))
    vectors = json.loads((ROOT / 'vector_catalog.json').read_text(encoding='utf-8'))
    static = json.loads((ROOT.parent / 'figure_catalog.json').read_text(encoding='utf-8'))
    known = {item['sha256'] for item in static}
    image_chunks = []
    for item in assets:
        if item['kind'] != 'image':
            continue
        # 已核定图号的原始 PNG 使用原目录，避免同图重复引用。
        if item['sha256'] in known:
            item['review_status'] = 'duplicate'
            continue
        item['review_status'] = 'approved'
        item['caption'] = f"第{item['chapter_id']}章教材嵌入图片（图号未核定）"
    (ROOT / 'asset_catalog.json').write_text(json.dumps(assets, ensure_ascii=False, indent=2), encoding='utf-8')
    for item in vectors:
        image_chunks.append(dict(kind='image_context', chapter_id=item['chapter_id'],
            source=item['source'], section=f"第{item['chapter_id']}章教材绘图",
            text=item['caption']+'\n邻近正文：\n'+item['context'], asset_ids=[item['id']], section_id=None))
    (ROOT / 'vector_chunks.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in image_chunks),encoding='utf-8')
    chunks = [json.loads(line) for line in (ROOT / 'multimodal_chunks.jsonl').read_text(encoding='utf-8').splitlines() if line]
    summary = json.loads((ROOT / 'summary.json').read_text(encoding='utf-8'))
    report = dict(chapters=len(summary), word_tables=sum(x['tables'] for x in summary),
        formula_blocks=sum(x['formula_objects'] for x in summary),
        formula_previews=sum(x['kind']=='formula' and bool(x.get('preview_filename')) for x in assets),
        embedded_images=sum(x['kind']=='image' for x in assets), vector_anchor_previews=len(vectors),
        extra_rag_chunks=len(chunks)+len(image_chunks),
        notes=['公式以原始预览图片保存，尚未转换为 LaTeX；仅通过公式附近正文检索。',
               '绘图按 Word 锚点导出，一个预览可能包含多个图或标注；未自动认定教材图号。',
               '表格数量指 Word 表格对象，不包含图片中的表格或文本模拟的表格。'])
    (ROOT / 'import_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    cards=[]
    for item in assets+vectors:
        if not item.get('preview_filename') or item['kind']=='ole':
            continue
        caption=item.get('caption') or item.get('section') or item['id']
        cards.append('<article data-kind="'+html.escape(item['kind'])+'"><h3>'+html.escape(item['id'])+'</h3><p>'+html.escape(caption)+'</p><img loading="lazy" src="'+html.escape(item['preview_filename'])+'"><details><summary>邻近正文</summary><pre>'+html.escape(item.get('context',''))+'</pre></details></article>')
    page='''<!doctype html><meta charset="utf-8"><title>教材多模态提取核对</title>
<style>body{font:16px system-ui;margin:24px;background:#f5f5f5}main{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:16px}article{padding:16px;background:white;border-radius:8px}img{max-width:100%;max-height:260px;object-fit:contain}pre{white-space:pre-wrap}button{padding:8px 16px;margin:8px}</style>
<h1>教材多模态提取核对</h1><p>公式为原图预览；绘图对象的编号不是教材图号。</p>
<button onclick="filter('all')">全部</button><button onclick="filter('image')">插图</button><button onclick="filter('formula')">公式</button><main>'''+''.join(cards)+'''</main><script>function filter(k){document.querySelectorAll('article').forEach(a=>a.hidden=k!=='all'&&a.dataset.kind!==k)}</script>'''
    (ROOT/'review.html').write_text(page,encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()
