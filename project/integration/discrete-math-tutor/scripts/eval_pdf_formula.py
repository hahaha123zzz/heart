import json, urllib.request
from pathlib import Path
from knowledge.pdf_reader import document
record=document('chapter-03')
selection={'document_id':record['document_id'],'version':record['version'],'kind':'area','rects':[{'page':8,'x1':.18,'y1':.12,'x2':.87,'y2':.16}],'text':''}
Path('artifacts/pdf-reader/formula-selection.json').write_text(json.dumps(selection),encoding='utf-8')
request=urllib.request.Request('http://127.0.0.1:8000/api/chat',data=json.dumps({'student_id':'pdf-real-formula','account_type':'test','message':'请解释我圈选的二项式展开公式，为什么每项前面有组合数？','selection':selection}).encode(),headers={'Content-Type':'application/json'})
try:
 result=json.load(urllib.request.urlopen(request,timeout=100))
 Path('artifacts/pdf-reader/formula-real-validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'reply':result['reply'],'quality':result['quality_check'],'refs':result['selection_ref']['rects']},ensure_ascii=False))
except Exception as error: print(type(error).__name__,str(error))
