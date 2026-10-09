"""将原Word练习导入结构化题库，按原题号和PDF题目范围核对。"""
from pathlib import Path
import copy,hashlib,json,re
import fitz
from knowledge.content import chapter_blocks
BASE=Path(__file__).resolve().parent
DEST=BASE/'knowledge'/'exercises'
DEST.mkdir(exist_ok=True)
TOP=re.compile(r'^\s*[*＊☆★]?\s*(\d+)\s*[、．.](?!\d)')
SUB=re.compile(r'^\s*[（(]\s*(\d+|l|I)\s*[)）]')
GROUP=re.compile(r'^练\s*习\s*(\d+)\s*\.\s*(\d+)\s*$')
def segtext(parts):
 return ''.join(p.get('text','') if p['type'] in ('text','symbol') else segtext(p.get('segments',[])) if 'segments' in p else '\ufffc' for p in parts)
def btext(b):return segtext(b.get('segments',[]))
def slice_segments(parts,start,end):
 out=[];at=0
 for part in parts:
  t=segtext([part]);stop=at+len(t)
  if stop>start and at<end:
   p=copy.deepcopy(part)
   if part['type'] in ('text','symbol'):p['text']=part.get('text','')[max(0,start-at):min(len(t),end-at)]
   elif 'segments' in part:p['segments']=slice_segments(part['segments'],max(0,start-at),end-at)
   out.append(p)
  at=stop
 return out

def split_inline_subparts(block):
 if block['type']!='paragraph':return [block]
 t=btext(block);top=TOP.match(t);offset=top.end() if top else 0
 candidates=list(re.finditer(r'[（(]\s*(\d+|l)\s*[)）]',t))
 if not candidates:return [block]
 first=candidates[0]
 if t[offset:first.start()].strip():return [block]
 # 同一段的连续小题号才切分；不拆正文引用。
 chosen=[first]
 n=int(first[1]) if first[1].isdigit() else 1
 for m in candidates[1:]:
  k=int(m[1]) if m[1].isdigit() else 1
  if k==n+1:chosen.append(m);n=k
 if len(chosen)==1 and not top:return [block]
 out=[]
 if top and t[:offset].strip():out.append(dict(block,segments=slice_segments(block['segments'],0,offset)))
 for i,m in enumerate(chosen):out.append(dict(block,segments=slice_segments(block['segments'],m.start(),chosen[i+1].start() if i+1<len(chosen) else len(t))))
 return out

def option_blocks(blocks):
 stem=[];opts=[];current=None
 for block in blocks:
  if block['type']!='paragraph':
   (current['blocks'] if current else stem).append(block);continue
  t=btext(block)
  matches=list(re.finditer(r'(?:^|(?<=\s))([A-H])(?:\s*[.．、:]|(?=\s*\ufffc))',t))
  if not matches:
   (current['blocks'] if current else stem).append(block);continue
  if matches[0].start()>0:
   prefix=dict(block,segments=slice_segments(block['segments'],0,matches[0].start()))
   if btext(prefix).strip():(current['blocks'] if current else stem).append(prefix)
  for i,m in enumerate(matches):
   content=dict(block,segments=slice_segments(block['segments'],m.end(),matches[i+1].start() if i+1<len(matches) else len(t)))
   current={'key':m[1],'blocks':[content]};opts.append(current)
 keys=[o['key'] for o in opts]
 if len(opts)<2 or len(set(keys))!=len(keys):return blocks,[]
 return stem,opts

def parts_for(q):
 blocks=[]
 for b in q['blocks']:blocks.extend(split_inline_subparts(b))
 shared=[];parts=[];current=None
 for b in blocks:
  m=SUB.match(btext(b)) if b['type']=='paragraph' else None
  if m:
   number=int(m[1]) if m[1].isdigit() else 1
   # 子题号重新起始通常属于该小题内部的证明步骤，保留在原子题。
   if not parts or number>parts[-1]['number']:
    current={'number':number,'blocks':[]};parts.append(current)
  (current['blocks'] if current else shared).append(b)
 if not parts:parts=[{'number':1,'blocks':blocks}];shared=[]
 title=''.join(btext(b) for b in shared)
 q['shared_blocks']=shared
 for i,p in enumerate(parts):
  text='\n'.join(btext(b) for b in p['blocks'])
  combined=title+' '+text
  stem,options=option_blocks(p['blocks']) if '选择' in title or '选择' in q['text'][:30] else (p['blocks'],[])
  kind='choice' if options else 'proof' if re.search('证明|求证|演绎',combined) else 'graph' if re.search('画出|作出.*图|构造.*图|构图|根树表示|图示|哈斯图|图来表示',combined) else 'matrix' if re.search('矩阵|真值表|列表',combined) else 'fill' if re.search('填空|填充|[_＿]{2,}',combined) else 'judgement' if re.search('真、假|真假|真或假',combined) and not re.search('说明|证明|为什么|理由',combined) else 'expression' if re.search('求|计算|表示|归纳定义|化简',combined) else 'written'
  slots=len(re.findall(r'[（(][ \u3000]+[)）]',text))
  if options and slots>1:kind='fill';stem=p['blocks']
  blanks=(slots if options and slots>1 else max(1,len(re.findall(r'[_＿]{2,}',text)) or len(re.findall(r'(?<=\S)[ \u3000]{5,}(?=\S)',text)))) if kind=='fill' else 0
  p.update({'id':f'p{i+1}','label':f'（{p["number"]}）' if len(parts)>1 or shared else '作答','type':kind,'stem_blocks':stem,'options':options,'blank_count':min(blanks,12),'multiple':bool(re.search('哪些|多选|所有正确',combined)),'grader':'ai_assisted'})
 q['parts']=parts

def pdf_anchors(chapter,group,pdf):
 anchors=[]
 for pn in range(group['start_page'],min(group['end_page'],len(pdf))+1):
  for b in pdf[pn-1].get_text('dict')['blocks']:
   for l in b.get('lines',[]):
    x,y,_,y2=l['bbox'];t=''.join(s['text'] for s in l['spans']).strip()
    if pn==group['start_page'] and y<group['start_y']:continue
    if pn==group['end_page'] and y>=group['end_y']:continue
    m=TOP.match(t)
    if m and x<125:anchors.append({'number':int(m[1]),'page':pn,'y':y,'text':t})
 return sorted(anchors,key=lambda a:(a['page'],a['y']))

catalog=[];audit=[]
split=json.loads((BASE/'frontend/textbook/manifest.json').read_text(encoding='utf-8'))
for chapter in range(1,11):
 document=json.loads((BASE/'knowledge/pdf/manifest.json').read_text(encoding='utf-8'))[chapter-1]
 pdf=fitz.open(BASE/'knowledge/pdf'/f'chapter_{chapter:02d}.pdf')
 groups=[];active=None;q=None
 for sid,blocks in chapter_blocks(chapter).items():
  for block in blocks:
   block=copy.deepcopy(block)
   text=btext(block).strip()
   if block.get('list_kind')=='decimal' and re.match(r'^[（(]%[1-9][）)]$',block.get('list_format','')) and not SUB.match(text):
    block['segments'].insert(0,{'type':'text','text':f"（{block['list_number']}）"});text=btext(block).strip()
   compact=re.sub(r'\s+','',text).lstrip('*＊')
   match=GROUP.match(text)
   if match:
    active={'id':f'{chapter}.{int(match[2])}','title':f'练习{chapter}.{int(match[2])}','chapter_id':chapter,'section_id':sid,'questions':[]}
    groups.append(active);q=None;continue
   if active and re.match(rf'^{chapter}\.{int(active["id"].split(".")[1])+1}(?![.\d])[\u4e00-\u9fff]',compact):active=None;q=None
   if not active:continue
   top=TOP.match(text)
   generic=bool(re.fullmatch(r'(?:选择题|填空题|填充题)[：:]?',text))
   automatic=block.get('list_id') and block.get('list_level',0)==0 and block.get('list_kind')=='decimal' and not SUB.match(text) and not re.match(r'^[A-H]\s*[.．、]',text)
   if top or generic or automatic or q is None:
    number=int(top[1]) if top else (q['number']+1 if q else 1)
    q={'number':number,'blocks':[]};active['questions'].append(q)
   q['blocks'].append(block)
 for gi,g in enumerate(groups):
  source=split[str(chapter)]['groups'][gi];anchors=pdf_anchors(chapter,source,pdf)
  word_nums=[q['number'] for q in g['questions']];pdf_nums=[a['number'] for a in anchors]
  audit.append({'group':g['id'],'word_numbers':word_nums,'pdf_numbers':pdf_nums,'match':word_nums==pdf_nums})
  for qi,q in enumerate(g['questions']):
   q.update({'id':f'ex-{chapter:02d}-{gi+1:02d}-{qi+1:03d}','chapter_id':chapter,'group_id':g['id'],'section_id':g['section_id'],'text':'\n'.join(btext(b) for b in q['blocks']), 'knowledge_point':next(s['title'] for s in document['sections'] if s['id']==g['section_id']),'source_version':document['version']})
   q['source']={'document_id':document['document_id'],'page':source['start_page'],'y':source['start_y']/pdf[source['start_page']-1].rect.height}
   if word_nums==pdf_nums:
    a=anchors[qi];end=anchors[qi+1] if qi+1<len(anchors) else {'page':source['end_page'],'y':source['end_y']}
    q['source'].update({'page':a['page'],'y':a['y']/pdf[a['page']-1].rect.height,'end_page':end['page'],'end_y':end['y']})
   parts_for(q)
  catalog.extend(g['questions'])
 print(chapter,len(groups),sum(len(g['questions']) for g in groups),sum(len(q['parts']) for g in groups for q in g['questions']))
if any(not a['match'] for a in audit):
 raise RuntimeError('题号核对失败，拒绝发布题库')
(DEST/'catalog.json').write_text(json.dumps({'version':hashlib.sha256(json.dumps(catalog,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),'questions':catalog},ensure_ascii=False),encoding='utf-8')
(DEST/'import_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
print('TOTAL',len(catalog),'PARTS',sum(len(q['parts']) for q in catalog),'MISMATCHES',[a['group'] for a in audit if not a['match']])
