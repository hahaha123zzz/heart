"""拆分教材正文与原版练习，保留原页面坐标用于圈选引用。"""
from pathlib import Path
import hashlib,json,re
import fitz
BASE=Path(__file__).resolve().parent
OUT=BASE/'frontend'/'textbook'
OUT.mkdir(exist_ok=True)
manifest=json.loads((BASE/'knowledge/pdf/manifest.json').read_text(encoding='utf-8'))
results={}
for record in manifest:
 chapter=record['chapter_id']
 source=BASE/'knowledge/pdf'/f'chapter_{chapter:02d}.pdf'
 pdf=fitz.open(source)
 lines=[]
 for p,page in enumerate(pdf):
  for b in page.get_text('dict')['blocks']:
   for l in b.get('lines',[]):
    t=''.join(s['text'] for s in l['spans']).strip()
    compact=re.sub(r'\s+','',t).lstrip('*＊')
    lines.append((p,l['bbox'][1],l['bbox'][3],compact,t))
 starts=[l for l in lines if re.fullmatch(rf'练习{chapter}\.\d+',l[3])]
 assert starts, f'第{chapter}章无练习标题'
 groups=[]
 for start in starts:
  unit=int(start[3].split('.')[-1])
  ends=[l for l in lines if (l[0],l[1])>(start[0],start[1]) and re.match(rf'^{chapter}\.{unit+1}(?![.\d])[\u4e00-\u9fff]',l[3])]
  end=ends[0] if ends else (len(pdf),0,0,'','')
  if unit!=len(starts): assert ends, f'第{chapter}章练习{unit}结束标题缺失'
  groups.append({'title':start[4],'start_page':start[0]+1,'start_y':start[1]-1,'end_page':end[0]+1,'end_y':end[1]-1})
 def ranges(page_index):
  p=page_index+1;h=pdf[page_index].rect.height
  return [(max(0,g['start_y']) if p==g['start_page'] else 0,min(h,g['end_y']) if p==g['end_page'] else h) for g in groups if g['start_page']<=p<=g['end_page'] and (p!=g['end_page'] or g['end_y']>0)]
 def redact(page,ys):
  for y1,y2 in ys:
   if y2>y1:page.add_redact_annot(fitz.Rect(0,y1,page.rect.width,y2),fill=(1,1,1))
  # 位图仅清除覆盖部分；跨边界图形保留未覆盖部分，文字完整删除。
  page.apply_redactions(images=2,graphics=1,text=0)
 reading=fitz.open();exercises=fitz.open();mapping=[];exercise_mapping=[]
 for p,page in enumerate(pdf):
  ys=ranges(p);h=page.rect.height
  # 全页练习不用放进正文，避免阅读出现整页空白。
  if not any(y1<=0 and y2>=h for y1,y2 in ys):
   reading.insert_pdf(pdf,from_page=p,to_page=p)
   redact(reading[-1],ys)
   # 部分练习末页只剩页眉，删除无正文的空页。
   body=reading[-1].get_text(clip=fitz.Rect(0,65,page.rect.width,h-50)).strip()
   has_images=bool(reading[-1].get_images())
   if body or has_images:mapping.append(p+1)
   else:reading.delete_page(len(reading)-1)
  if ys:
   exercises.insert_pdf(pdf,from_page=p,to_page=p)
   gaps=[];prev=0
   for y1,y2 in sorted(ys):
    if y1>prev:gaps.append((prev,y1))
    prev=max(prev,y2)
   if prev<h:gaps.append((prev,h))
   redact(exercises[-1],gaps)
   # 练习摘页裁掉正文空白，原版图片和公式保持矢量/位图原貌。
   exercises[-1].set_cropbox(fitz.Rect(0,max(0,min(y[0] for y in ys)-8),page.rect.width,min(h,max(y[1] for y in ys)+8)))
   exercise_mapping.append(p+1)
 # 任何目录标题被误删都阻止输出。
 for s in record['sections']:
  assert s['page'] in mapping, (chapter,s['title'],'原页不存在')
  if s['y']:
   page=reading[mapping.index(s['page'])]
   title=re.sub(r'\s+','',s['title'])
   text=re.sub(r'\s+','',page.get_text())
   assert title in text, (chapter,s['title'],'正文标题丢失')
 for page in reading:assert not re.search(rf'^练\s*习\s*{chapter}\s*\.\d+\s*$',page.get_text(),re.M),(chapter,'正文残留练习')
 reading.save(OUT/f'chapter-{chapter:02d}-reading.pdf',garbage=4,deflate=True)
 exercises.save(OUT/f'chapter-{chapter:02d}-exercises.pdf',garbage=4,deflate=True)
 for g in groups:g['pdf_page']=exercise_mapping.index(g['start_page'])+1
 results[str(chapter)]={'source_version':record['version'],'reading_url':f'/static/textbook/chapter-{chapter:02d}-reading.pdf','page_map':mapping,'exercise_url':f'/static/textbook/chapter-{chapter:02d}-exercises.pdf','exercise_page_map':exercise_mapping,'groups':groups}
 print(chapter,'正文',len(reading),'练习',len(exercises),'组',len(groups))
 if chapter==2:
  reading[mapping.index(6)].get_pixmap(matrix=fitz.Matrix(1,1)).save(str(OUT/'split-reading-check.png'))
  exercises[0].get_pixmap(matrix=fitz.Matrix(1,1)).save(str(OUT/'split-exercise-check.png'))
(OUT/'manifest.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
