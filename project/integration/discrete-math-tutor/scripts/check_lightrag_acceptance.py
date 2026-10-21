"""同模型/同教材HTTP对照；保留每次尝试，不以导航或fallback充当LightRAG成功。"""
import argparse,json,time,os
from pathlib import Path
import requests

def fault_verified(result,case,backend):
 if result.get('completed') or result.get('fallback') or not result.get('error'):return False
 if case=='source_stale':return '教材已更新' in result['error']
 expected='lightrag' if backend=='lightrag' else 'local_llamaindex'
 return expected in result.get('actual_backends',[]) and any(
  m.get('role')=='tool' and 'retrieve_course 执行失败：FileNotFoundError' in str(m.get('content',''))
  for m in result.get('loop_messages',[]))

def main():
 p=argparse.ArgumentParser();p.add_argument('--url',default='http://127.0.0.1:18977');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 a.output.mkdir(parents=True,exist_ok=True);run_id=str(time.time_ns());rows=[]
 health=requests.get(a.url+'/health',timeout=60);health.raise_for_status();pin=health.json()
 (a.output/f'health-{run_id}.json').write_text(json.dumps(pin,ensure_ascii=False,indent=2),encoding='utf-8')
 cases=[('concept','什么是自变量？请依据教材简要解释。'),('synonym','操作定义是什么意思？'),
        ('comparison','被试内设计和被试间设计有什么区别？'),('cross_chapter','第一章的实验程序和第二章的自变量控制有哪些联系？'),
        ('previous_relation','与前面学过的自变量知识有什么关系？请解释如何在实验程序中控制它。'),
        ('first_chapter','学习第一章'),('next_target','下一知识点'),('figure','图1-1液体守恒实验说明了什么？'),
        ('no_hit','火星表面玄武岩的晶体结构是什么？'),('source_stale','核对已失效的教材来源'),('backend_unavailable','什么是自变量？')]
 cursors={}
 for case,question in cases:
  for which in ('baseline','lightrag'):
   body={'case':case,'backend':which,'question':question}
   if case=='next_target':body['cursor']=cursors.get(which)
   if case=='previous_relation':body['history']=[{'role':'user','content':'我们前面学习的主题是自变量。'}]
   if case in ('source_stale','backend_unavailable'):body['fault']=case
   started=time.monotonic()
   try:
    response=requests.post(a.url+'/turn',json=body,timeout=300);response.raise_for_status();result=response.json()
    if case=='first_chapter' and result.get('navigation'):cursors[which]={**result['navigation'],'explained':bool(result.get('completed'))}
    actual=result.get('actual_backends',[])
    tokens=sum((c.get('usage') or {}).get('total_tokens',0) for c in result.get('model_calls',[]))
    tokens+=sum(c.get('usage',{}).get('usage',{}).get('total_tokens',0) for c in result.get('retrieval_calls',[]))
    retrieval_seconds=sum(c.get('seconds',0) for c in result.get('retrieval_calls',[]) if c.get('actual_backend')!='q2_exact')
    fault_pass=fault_verified(result,case,which)
    quality_pass=bool(result.get('completed') and result.get('source_mapping_passed') and result.get('references'))
    if which=='lightrag' and case not in ('first_chapter','next_target','source_stale','backend_unavailable'):
     quality_pass=quality_pass and actual==['lightrag']
    if case=='no_hit':quality_pass=not result.get('completed') and not result.get('sources') and not result.get('fallback')
    if case in ('source_stale','backend_unavailable'):quality_pass=fault_pass
    row={'case':case,'backend':which,'attempt_id':result.get('attempt_id'),'passed':quality_pass,
      'scope':'fault injection' if body.get('fault') else 'Q2 navigation only' if case in ('first_chapter','next_target') else 'real model and retrieval',
      'actual_backends':actual,'fallback':result.get('fallback'),'completed':result.get('completed'),
      'source_count':len(result.get('sources',[])),'reference_count':len(result.get('references',[])),
      'retrieval_seconds':retrieval_seconds,'turn_seconds':result.get('total_seconds'),'http_seconds':time.monotonic()-started,
      'model_attempts':len(result.get('model_calls',[]))+sum(c.get('usage',{}).get('llm_calls',0) for c in result.get('retrieval_calls',[])),'returned_total_tokens':tokens,'cost':None,
      'error':result.get('error'),'judgements':result.get('judgements',[]),
      'model_image_inputs':sum(c.get('image_inputs',0) for c in result.get('model_calls',[]))}
    if case=='cross_chapter':
     chapters={r.get('chapter_id') for r in result.get('sources',[])};row['required_chapters']=[1,2];row['returned_chapters']=sorted(ch for ch in chapters if ch is not None)
     row['passed']=row['passed'] and {1,2}.issubset(chapters)
    if case=='next_target':
     previous=body.get('cursor') or {};current=result.get('navigation') or {}
     row.update(navigation_from_id=previous.get('id'),navigation_to_id=current.get('id'),
        navigation_advanced=bool(previous.get('id') and current.get('id') and previous['id']!=current['id']),
        first_turn_published=bool(previous.get('explained')))
     row['passed']=row['passed'] and row['navigation_advanced']
     row['two_turn_workflow_passed']=row['passed'] and row['first_turn_published']
    if case=='figure':
     row['visual_count']=len(result.get('visuals',[]));row['visual_identity_only']=True
     row['visual_interpretation_verified']=False
     media=[m for s in result.get('sources',[]) for m in s.get('image_refs',[])]
     row['requested_figure_bound']=any('图1-1' in str(m.get('caption','')) for m in media)
     if which=='lightrag':row['passed']=row['passed'] and row['requested_figure_bound']
   except Exception as exc:row={'case':case,'backend':which,'passed':False,'error_type':type(exc).__name__,'error':str(exc),'http_seconds':time.monotonic()-started}
   rows.append(row)
   report={'run_id':run_id,'isolation':pin,'rows':rows,'passed':all(r['passed'] for r in rows),
     'production_switch':False,'page_acceptance':'not run','tool_chain':'existing LocalAgentLoop -> RetrieveCourseTool -> Navigator -> backend -> Q2 evidence -> existing QualityChecker',
     'limits':['figure pixel interpretation not verified; public visual wiring belongs to UX4','navigation success is not retrieval quality improvement']}
   (a.output/f'comparison-{run_id}.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
   print(json.dumps({k:row.get(k) for k in ('case','backend','passed','attempt_id','error','actual_backends','turn_seconds')},ensure_ascii=False),flush=True)
 return 0 if report['passed'] else 1
if __name__=='__main__':
 if os.name=='nt':
  import ctypes
  ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
 try:raise SystemExit(main())
 finally:
  if os.name=='nt':ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
