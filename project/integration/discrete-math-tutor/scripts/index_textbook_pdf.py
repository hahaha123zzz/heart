"""核对 Word 分页与 PDF 正文，生成可回溯的教材页码清单。"""
from pathlib import Path
import hashlib, json, re
import fitz
from knowledge.course import get_chapter
ROOT = Path(__file__).resolve().parents[1] / 'knowledge' / 'pdf'
def norm(text): return re.sub(r'\s+', '', text)
def build():
    manifest = []
    for chapter_id in range(1, 11):
        path = ROOT / f'chapter_{chapter_id:02d}.pdf'
        word = json.loads(path.with_suffix('.word.json').read_text(encoding='utf-8'))
        with fitz.open(path) as doc:
            pages = [{'page': i+1, 'width': p.rect.width, 'height': p.rect.height,
                      'text': p.get_text(), 'blocks': [list(b[:5]) for b in p.get_text('blocks') if b[6] == 0]} for i,p in enumerate(doc)]
            sections = []
            for item in word['sections']:
                target = norm(item['title'])
                matches = []
                for page in pages:
                    for block in page['blocks']:
                        if target in norm(block[4]):
                            # 用逐行文字取得标题本身的位置，避免大段合并块导致偏移。
                            p=doc[page['page']-1]
                            for native_block in p.get_text('dict')['blocks']:
                                for line in native_block.get('lines',[]):
                                    value=''.join(span['text'] for span in line['spans'])
                                    if norm(value)==target:
                                        matches.append((page['page'],line['bbox'][1]/page['height']))
                if item['id'] == 1:
                    page, y = 1, 0
                else:
                    preferred = [m for m in matches if m[0] == item.get('page')]
                    if not preferred and len(matches) != 1:
                        raise ValueError(f"章节 {chapter_id} 小节 {item['title']} 无法核对页码: {matches}")
                    page, y = (preferred or matches)[0]
                    if item.get('page') and page != item['page']:
                        raise ValueError(f"Word/PDF 页码不一致: {chapter_id} {item['title']}")
                sections.append({**item, 'page':page, 'y':y, 'verified':True})
            record = {'document_id':f'chapter-{chapter_id:02d}', 'chapter_id':chapter_id,
                      'title':get_chapter(chapter_id)['title'], 'source':word['source'],
                      'source_sha256':word['source_sha256'], 'version':hashlib.sha256(path.read_bytes()).hexdigest(),
                      'page_count':len(doc), 'sections':sections, 'pages':pages}
            manifest.append(record)
    (ROOT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False),encoding='utf-8')
    print(json.dumps([{'chapter':m['chapter_id'],'pages':m['page_count'],'sections':len(m['sections'])} for m in manifest],ensure_ascii=False))
if __name__ == '__main__': build()
