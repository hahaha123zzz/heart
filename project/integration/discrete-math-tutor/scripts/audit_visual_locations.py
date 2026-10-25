"""扫描当前教材，不写教材、数据库或索引；结果不等于教师审核。"""
import argparse,json,time
from collections import Counter
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from knowledge.source_visuals import load_visuals
from knowledge.pdf_reader import document_for_chapter
from knowledge.visual_locations import resolve_figure

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
 if args.output.exists():parser.error('输出已存在，请使用新的审计文件名以保留全部尝试')
 start=time.perf_counter();visuals,gaps=load_visuals();rows=[]
 for visual in visuals:
  record=document_for_chapter(visual.chapter_id)
  result=resolve_figure(visual.id,visual.sha256,record['document_id'],record['version'])
  rows.append(result|{'asset_id':visual.id,'asset_sha256':visual.sha256,'chapter_id':visual.chapter_id,'kind':visual.kind,'block_index':visual.block_index,'labels':visual.labels})
 for gap in gaps:
  rows.append(gap.public()|{'asset_id':gap.visual_id,'status':'excluded' if gap.classification=='decoration' else 'missing'})
 output={'counts':dict(Counter(row['status'] for row in rows)),'available':len(visuals),'gaps':len(gaps),'chapters':len({v.chapter_id for v in visuals}),'elapsed_seconds':time.perf_counter()-start,'items':rows}
 args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({k:v for k,v in output.items() if k!='items'},ensure_ascii=False))
if __name__=='__main__':main()
