"""正式教材只读抽检；不调用模型，不导入服务入口或学生数据库。"""
import json,sys,os,argparse
from pathlib import Path
parser=argparse.ArgumentParser();parser.add_argument('--assets-root',required=True,type=Path);parser.add_argument('--output',required=True,type=Path);args=parser.parse_args()
HOME=args.output.parent;HOME.mkdir(parents=True,exist_ok=True)
APP=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(APP));os.environ['TUTOR_COURSE']='experimental-psychology-3'
import knowledge.course_config as cc
cc.PSYCHOLOGY_DIR=args.assets_root.resolve()
from knowledge.pdf_reader import documents
from knowledge.course_release import binding
from agents.tools.first_wave import ReadBinding
from agents.tools.first_wave_services import CourseReadService
service=CourseReadService();release=binding();docs=documents()
b=ReadBinding('isolated','isolated','isolated',cc.COURSE_ID,release['release_id'],tuple((d['document_id'],d['version']) for d in docs))
service.check(b);raw_units=service._units(b);service._units=lambda binding:raw_units;units=service.outline(b);rows=[]
for doc in docs:
 row={'chapter_id':doc['chapter_id'],'version':doc['version']}
 try:
  value,sources=service.read_material(b,dict(document_id=doc['document_id'],version=doc['version'],page=1),lambda:None)
  for source in sources:service.verify_source(b,source)
  row['page_chars']=len(value['text'])
  unit=next(u for u in units if u['chapter_id']==doc['chapter_id'])
  value,sources=service.read_material(b,dict(unit_id=unit['id']),lambda:None)
  for source in sources:service.verify_source(b,source)
  row.update(unit_id=unit['id'],sources=len(sources),range_kind=value.get('range_kind','exact'),unit_read_complete=value.get('unit_read_complete',True),passed=True)
 except Exception as e:row.update(passed=False,error=str(e))
 rows.append(row)
report={'release':release,'documents':len(service.files(b)),'targets':len(units),'chapters':rows}
args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(report,ensure_ascii=False));assert all(r['passed'] for r in rows)
