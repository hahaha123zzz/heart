"""仅离线剖析原文定位；不调用模型，不作为端到端验收。传入完整宿主应用目录。"""
import sys,json,time,cProfile,pstats,io,os
from pathlib import Path
app=Path(sys.argv[1]);os.chdir(app);sys.path.insert(0,str(app))
from knowledge.grounded_citations import choose_evidence
from knowledge.citation_index import _live_document
from knowledge.course_config import PSYCHOLOGY_DIR
from knowledge.textbook import TextbookChunk,terms_for
registry=json.loads((PSYCHOLOGY_DIR/'pdf_manifest.json').read_text('utf8'))
sources=[]
for chapter in [1,2,4,2,9,2]:
 doc=json.loads((PSYCHOLOGY_DIR/'chapters'/f'chapter_{chapter:02d}'/'document.json').read_text('utf8'))
 block=next(b for b in doc['blocks'] if b['kind']=='paragraph' and 50<len(b['text'])<200)
 sources.append(TextbookChunk(doc['source'],block['section'],block['text'],terms_for(block['text']),chapter_id=chapter,section_id=block['section_id'],block_start=block['block_index'],block_end=block['block_index']))
class Selection:
 def chat_json(self,messages,**kwargs):
  value=json.loads(messages[-1]['content']);return {'evidence_ids':[value['candidates'][0]['evidence_id']]}
profile=cProfile.Profile();start=time.monotonic();profile.enable()
try:result=choose_evidence(Selection(),'比较教材观点',sources,'live')
finally:
 profile.disable();out=io.StringIO();pstats.Stats(profile,stream=out).strip_dirs().sort_stats('cumtime').print_stats(18)
 print(json.dumps({'seconds':time.monotonic()-start,'cache':str(_live_document.cache_info()),'sources':len(sources)}));print(out.getvalue())
