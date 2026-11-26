"""生成每章占位 PDF（正文与 document.json 一致），更新 pdf_manifest/pdf_locations。"""
import json, hashlib, fitz
from pathlib import Path

COURSE = Path('knowledge/courses/experimental-psychology-3')
WIDTH, HEIGHT = 595, 842  # A4 pt

def wrap(text, chars_per_line=34):
    lines=[]
    buf=''
    for ch in text:
        buf+=ch
        if len(buf)>=chars_per_line or ch in '\n。！？；':
            lines.append(buf); buf=''
    if buf: lines.append(buf)
    return lines

records=[]
for n in range(1,12):
    ch_dir=COURSE/'chapters'/f'chapter_{n:02d}'
    doc=json.loads((ch_dir/'document.json').read_text(encoding='utf-8'))
    loc=json.loads((ch_dir/'pdf_locations.json').read_text(encoding='utf-8'))
    pdf=fitz.open()
    pdf.new_page(width=WIDTH,height=HEIGHT)
    pages={}
    blocks=doc['blocks']
    # 将 blocks 顺序铺到页上：按 section 分组，每组 3 页
    bi=0
    for s in range(1,9):
        sb=[b for b in blocks if b.get('section_id')==s]
        for j,b in enumerate(sb):
            page_no=3*(s-1)+min(j,2)+1  # 该块所在页（1-based）
            pages.setdefault(page_no,[]).append(b['text'])
    while len(pdf) < 30:
        pdf.new_page(width=WIDTH,height=HEIGHT)
    for page_no, texts in pages.items():
        page=pdf[page_no-1]
        y=60
        for t in texts:
            for line in wrap(t):
                if y>HEIGHT-60:
                    break
                page.insert_text((60,y),line,fontsize=11,fontname='china-s')
                y+=16
            y+=10
    data=pdf.tobytes()
    pdf.close()
    (ch_dir / ('chapter_%02d.generated.pdf' % n)).write_bytes(data)
    version=hashlib.sha256(data).hexdigest()
    for s in loc['sections']:
        s['generated_page']=3*s['id']
    record={'document_id':f'chapter-{n:02d}','chapter_id':n,'version':version,
            'page_count':30,'course_id':'experimental-psychology-3',
            'title':doc['source'].split('/')[-1],
            'source':f'chapters/chapter_{n:02d}/chapter_{n:02d}.generated.pdf',
            'sections':[{'id':s['id'],'title':s['title'],'page':s['generated_page']} for s in loc['sections']]}
    records.append(record)
    (ch_dir/'pdf_locations.json').write_text(json.dumps(loc,ensure_ascii=False),encoding='utf-8')
    print(f'chapter {n:02d}: pdf {len(data)//1024}KB version {version[:8]}')
(COURSE/'pdf_manifest.json').write_text(json.dumps(records,ensure_ascii=False),encoding='utf-8')
print('pdf_manifest updated')
