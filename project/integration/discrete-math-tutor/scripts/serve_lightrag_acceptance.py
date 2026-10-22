"""仅本机隔离验收宿主；复用固定主线AgentLoop/工具/Q2证据与测试数据库。"""
import argparse,asyncio,json,os,sys,time,uuid,threading
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--isolation',type=Path,required=True);parser.add_argument('--port',type=int,default=18977)
 args=parser.parse_args();out=args.isolation.resolve(strict=True);pin=json.loads((out/'isolation.json').read_text(encoding='utf-8'))
 candidate=Path(pin['candidate']);host=Path(pin['host']);db=Path(pin['database'])
 assert host.is_relative_to(out) and db.is_relative_to(out) and not (host/'.env').exists()
 for name,value in {'DATABASE_URL':'sqlite:///'+str(out/'unused.sqlite3'),'COURSE_DATABASE_URL':'sqlite:///'+str(db),
                    'TUTOR_COURSE':'experimental-psychology-3','OMP_NUM_THREADS':'2','MKL_NUM_THREADS':'2',
                    'TOKENIZERS_PARALLELISM':'false','CITATION_GROUNDING_MODE':'active','DEEPTUTOR_LLM_ENABLED':'0'}.items():os.environ[name]=value
 sys.path.insert(0,str(host))
 import knowledge
 knowledge.__path__.append(str(ROOT/'knowledge'))
 import knowledge.lightrag
 knowledge.lightrag.__path__.insert(0,str(ROOT/'knowledge/lightrag'))
 from knowledge import course_config
 course_config.PSYCHOLOGY_DIR=candidate/'input'
 from knowledge import pdf_reader
 pdf_reader.CROPS=out/'crops'
 from knowledge.lightrag.retrieval import LightRagBackend,map_chunks,as_textbook_chunk
 from knowledge.lightrag.course_input import COURSE,digest
 from knowledge.lightrag.q3_adapter import LightRagNavigator,ContextualRetrieveCourseTool
 from knowledge.lightrag import engine,storage
 from knowledge.lightrag.pipeline import embedding_config
 from knowledge.lightrag.roles import resolve_query_roles,query_binding
 from knowledge.lightrag.worker import run_in_worker_loop
 from knowledge.lightrag.write_lock import write_ownership
 from knowledge.grounded_citations import choose_evidence,settings,EvidenceBundle
 from knowledge.course_release import binding
 from agents.q3_navigation import CallbackNavigator,LearningTarget,NavigationDecision,SourceRef,source_from_chunk
 from agents.q3_tools import build_registry
 from knowledge.lightrag.coverage import CoverageNavigator,semantic_selection
 from knowledge.lightrag.relationships import append_tool_context
 from knowledge.lightrag.trace import stage
 from agents.tool_protocol import ToolContext,Cancellation
 from agents.agent_loop import LocalAgentLoop,LoopRequest
 from agents.loop_prompts import build_loop_system_prompt
 from agents.quality_checker import QualityChecker
 from agents.teaching_planner import TeachingPlan
 from memory.memory_manager import MemoryManager
 from database.database import init_db
 from knowledge.local_rag.course_retrieval import retrieve
 from knowledge.course_navigation import resolve,read_target
 from llm.client import LLMClient
 from fastapi import FastAPI
 import uvicorn
 init_db();memory=MemoryManager();backend=LightRagBackend(candidate,authorized_course_ids={COURSE},allow_candidate=True)
 source_map=json.loads((candidate/'source_map.json').read_text(encoding='utf-8'));lock=threading.Lock()

 class MeasuredClient(LLMClient):
  def __init__(self):super().__init__(mock=False);self.calls=[];self.instrumented=False
  def _client_lazy(self):
   client=super()._client_lazy()
   client.max_retries=0;client.timeout=90
   if not self.instrumented:
    create=client.chat.completions.create
    def measured(**kwargs):
     kwargs.setdefault('extra_body',{'thinking':{'type':'disabled'}})
     record={'model':kwargs.get('model'),'thinking':'disabled','started_at':time.time(),'status':'failed','transport_retries':0,'request_timeout_seconds':90};started=time.monotonic()
     record['image_inputs']=sum(1 for msg in kwargs.get('messages',[]) if isinstance(msg.get('content'),list) for part in msg['content'] if part.get('type')=='image_url')
     self.calls.append(record)
     try:
      response=create(**kwargs);record.update(status='success',finish_reason=response.choices[0].finish_reason,
         usage=response.usage.model_dump() if response.usage else {},response_model=response.model)
      return response
     except Exception as exc:
      chain=[];cause=exc.__cause__
      while cause is not None and len(chain)<4:
       chain.append({'type':type(cause).__name__,'message':str(cause).replace(self.api_key,'[REDACTED]')[:300]});cause=cause.__cause__
      record.update(error_type=type(exc).__name__,error_chain=chain);raise
     finally:record['seconds']=time.monotonic()-started
    client.chat.completions.create=measured;self.instrumented=True
   return client

 async def load():
  embedding=await embedding_config();storage.require_compatible_embedding(candidate/'index',embedding)
  roles=resolve_query_roles(None)
  expected=json.loads((candidate/'policy.json').read_text(encoding='utf-8'))
  query_binding(expected,roles)
  async def job(bridge):
   rag=engine.build_rag(candidate/'index',io_bridge=bridge,query_roles=roles,embedding_config=embedding,query_only=True)
   try:
    await engine.initialize(rag)
    return {'entities':len(await rag.chunk_entity_relation_graph.get_all_nodes()),
            'relationships':len(await rag.chunk_entity_relation_graph.get_all_edges())}
   finally:await engine.finalize(rag,cancel_pending=False)
  return await run_in_worker_loop(job)
 with write_ownership(candidate):
  backend.validate(COURSE);loaded=asyncio.run(load());backend.validate(COURSE)
 deployment={'candidate':str(candidate),'host_revision':pin['host_revision'],'course_id':COURSE,'input_signature':pin['input_signature'],
   'graph_loaded':loaded,'policy':json.loads((candidate/'policy.json').read_text(encoding='utf-8')),
   'baseline_sha256':pin['baseline_sha256'],'database':str(db),'port':args.port,'formal_switch':False,
   'files':{name:digest(candidate/name) for name in ('input_manifest.json','source_map.json','policy.json','index_files.json')},
   'release':binding(),'server_sha256':digest(Path(__file__)),'adapter_sha256':digest(ROOT/'knowledge/lightrag/q3_adapter.py'),
   'runtime_config':{k:os.getenv(k) for k in ('RAG_RERANK_MODEL','RAG_EMBED_DEVICE','RAG_RERANK_DEVICE','OPENAI_BASE_URL','DEEPSEEK_MODEL')},
   'backend_code_hashes':{name:digest(ROOT/'knowledge/lightrag'/name) for name in ('coverage.py','retrieval.py','q3_adapter.py','relationships.py','source_explorer_reuse.py','trace.py','config.py')},
   'answer_prompt_policy':'same prompt for both backends; concise answer 120-180 Chinese characters; existing 260-char gate unchanged'}
 (out/'deployment.json').write_text(json.dumps(deployment,ensure_ascii=False,indent=2),encoding='utf-8')
 app=FastAPI(title='LightRAG isolated acceptance; not production')
 @app.get('/health')
 def health():
  backend.validate(COURSE)
  assert digest(Path(pin['baseline_index']))==pin['baseline_sha256']
  return deployment
 @app.post('/turn')
 def turn(body:dict):
  with lock:
   started=time.monotonic();attempt=str(uuid.uuid4());which=body.get('backend')
   if which not in ('baseline','lightrag'):return {'error':'unsupported backend'}
   question=str(body.get('question',''));student='lr-test-'+attempt[:20]
   record={'attempt_id':attempt,'case':body.get('case'),'requested_backend':which,'fallback':False,'student_id':student,
           'question':question,'host_revision':pin['host_revision'],'input_signature':pin['input_signature'],'started_at':time.time()}
   client=MeasuredClient();navigation_calls=[];chunks_by_id={};published={};judgements=[];stages=[];coverage_nav=None;chosen=None;q5_service=None;q5_scope=None;cancellation=Cancellation()
   memory.ensure_student(student,account_type='test')
   try:
    if body.get('fault')=='source_stale':
     doc=pdf_reader.document_for_chapter(1)
     pdf_reader.resolve_selection(pdf_reader.PDFSelection(document_id=doc['document_id'],version='0'*64,kind='text',rects=[{'page':1,'x1':0.1,'y1':0.1,'x2':0.2,'y2':0.2}]))
     raise AssertionError('失效来源未拒绝')
    nav=resolve(question,cursor=body.get('cursor'))
    exact=bool(nav and nav.get('status')=='ready')
    target=LearningTarget(target_id=nav['id'],name=nav['title'],chapter_id=nav['chapter_id'],section_id=nav['section_id'],version=nav['version']) if exact else LearningTarget('query',question)
    if body.get('q5_path'):
     from agents.q5_learning import Q5LearningService,LearningScope
     from database.q5_learning import ensure_q5_schema
     ensure_q5_schema();q5_service=Q5LearningService();q5_scope=LearningScope(student,student,COURSE)
     fixture=resolve('学习第五章');assert fixture and fixture['status']=='ready'
     q5_service.bind_textbook_target(q5_scope,fixture,command_id=attempt+'-fixture')
     record['q5_before']=q5_service.status(q5_scope)
     target=q5_service.current_target(q5_scope);exact=False
    if body.get('fault')=='cancel':cancellation.cancel()
    if body.get('current_target'):
     target=LearningTarget(**body['current_target']);exact=False
    def base_search(*,target,query,limit,preferred_types=()):
     begin=time.monotonic();trace={'actual_backend':'q2_exact' if exact else 'local_llamaindex','fallback':False,'query':query,'navigation_only':exact}
     navigation_calls.append(trace)
     try:
      if exact:
       rows=read_target({'id':target.target_id,'version':target.version});result=[]
       for i,row in enumerate(rows[:limit]):
        ref=source_from_chunk(row,i);loc={**ref.location,'source':row.source,'section':row.section,'kind':row.kind,
           'asset_ids':list(row.asset_ids),'block_start':row.block_start,'block_end':row.block_end,'source_spans':list(row.source_spans)}
        result.append(SourceRef(**{**ref.to_dict(),'location':loc}));chunks_by_id[ref.source_id]=row
       return result
      from unittest.mock import patch
      from knowledge.local_rag.course_retrieval import rerank_nodes
      def observe_rerank(q,nodes,**kwargs):
       def rows_for(values):return [{'chunk_id':n.node.node_id,'chapter_id':n.node.metadata['chapter_id'],'score':n.score} for n in values]
       before=rows_for(nodes);stage(stages,'native_recall',before,before,'',backend='local_llamaindex',query=q)
       ranked=rerank_nodes(q,nodes,**kwargs);scores=rows_for(ranked)
       stage(stages,'rerank_threshold',scores,[r for r in scores if r['score'] is not None and r['score']>=.15],'below_rerank_threshold',threshold=.15)
       stage(stages,'limit',[r for r in scores if r['score'] is not None and r['score']>=.15],rows_for(ranked[:limit]),'beyond_limit',limit=limit)
       return ranked
      with patch('knowledge.local_rag.course_retrieval.rerank_nodes',observe_rerank):
       rows=retrieve(query,limit=limit,index_path=(out/'unavailable-baseline.sqlite3') if body.get('fault')=='backend_unavailable' else pin['baseline_index'],trace=trace)
      records=[{'kind':'chunk','source':f'chapter_{r.chapter_id:02d}.generated.pdf','content':r.text,'chunk_id':r.chunk_id} for r in rows]
      mapped=map_chunks(records,source_map)
      stage(stages,'original_mapping',mapped,mapped,'')
      scoped=[r for r in mapped if (target.chapter_id is None or r['chapter_id']==target.chapter_id) and (target.section_id is None or r['section_id']==target.section_id)]
      stage(stages,'scope_filter',mapped,scoped,'outside_requested_scope')
      mapped=scoped
      stage(stages,'mapping_limit',mapped,mapped[:limit],'beyond_limit',limit=limit)
      mapped=mapped[:limit]
      return [SourceRef(**{k:r[k] for k in ('source_id','document_id','version','chapter_id','section_id','text','quote','page','image_refs','location')}) for r in mapped]
     finally:trace['seconds']=time.monotonic()-begin
    base=CallbackNavigator(resolve_fn=lambda **_:NavigationDecision('teach',target),search_fn=base_search)
    class UnavailableBackend:
     async def search(self,*args,**kwargs):
      missing=LightRagBackend(out/'unavailable-candidate',authorized_course_ids={COURSE},allow_candidate=True)
      return await missing.search(*args,**kwargs)
    query_backend=UnavailableBackend() if body.get('fault')=='backend_unavailable' else backend
    chosen=LightRagNavigator(base,query_backend,cancellation=cancellation) if which=='lightrag' else base
    units={}
    class EvidenceNavigator:
     def search(self,**kwargs):
      raw=chosen.search(**kwargs)
      return select_for_query(kwargs['query'],raw)
     def tool_context(self,sources):
      return chosen.tool_context(sources) if hasattr(chosen,'tool_context') else {}
    def select_for_query(selection_query,raw,subproblem="single"):
      if not raw:return []
      chunks=[chunks_by_id[r.source_id] if r.source_id in chunks_by_id else as_textbook_chunk(r.to_dict()) for r in raw]
      bundle=choose_evidence(client,selection_query,chunks,settings());refs=[]
      stage(stages,'q2_selection',raw,[raw[i['retrieval_source_index']] for i in bundle.evidence],'not_selected_by_q2; reason_not_returned',query=selection_query,subproblem=subproblem)
      for ch,item in zip(bundle.sources,bundle.evidence):
       original=raw[item['retrieval_source_index']];sid=item['evidence_id'];units[sid]=(ch,item)
       loc={**original.location,'source_spans':list(ch.source_spans),'textbook_release':binding()['release_id'],
            'release_status':binding()['status'],'release_ready':binding()['ready'],'evidence_id':sid,
            'retrieval_source_id':original.source_id,'sdk_chunk_ids':original.location.get('sdk_chunk_ids',[]),
            'block_start':item['source_block_id'],'block_end':item['source_block_id'],
            'block_char_start':item['block_start'],'block_char_end':item['block_end']}
       refs.append(SourceRef(sid,item['document_id'],ch.text,item['document_version'],ch.chapter_id,ch.section_id,None,ch.text,list(original.image_refs),loc))
      return refs
    navigation=EvidenceNavigator()
    if body.get('coverage'):
     coverage_nav=CoverageNavigator(chosen,question=question,select=lambda req,raw:select_for_query(req.query,raw,req.id),
          judge=lambda req,refs:semantic_selection(client,req,refs),cancellation=cancellation)
     navigation=coverage_nav
    def gate(text,state):
     try:
      if not state.sources:return False,'没有教材原文，不发布正式回答'
      chosen_units=[units[r['source_id']] for r in state.sources]
      bundle=EvidenceBundle([u[0] for u in chosen_units],[u[1] for u in chosen_units],[])
      reply,sources,references=bundle.publish(text)
      excerpts='\n'.join(f'[{i}] {r["text"]}' for i,r in enumerate(state.sources,1))
      quality=QualityChecker(client).check(reply,memory.get_state(student,target.name),
          TeachingPlan(goal=question,strategy='scaffolding',action='explain',difficulty='medium'),question,
          context={'agent_loop':True,'loop_sources':state.sources},textbook_excerpts=excerpts)
      judgements.append(quality.model_dump())
      if not quality.passed or quality.issues:return False,'；'.join(quality.issues)
      published.update(reply=reply,references=references)
      return True,''
     except Exception as exc:
      judgements.append({'passed':False,'error_type':type(exc).__name__,'error':str(exc)})
      return False,str(exc)
    registry=build_registry(allow_skills=False,extra_tools=(ContextualRetrieveCourseTool(),))
    if body.get('retrieval_only'):
     context=ToolContext(student_id=student,session_id=student,navigation=navigation,state={'learning_target':target},cancellation=cancellation)
     output=registry.get('retrieve_course').run({'query':question,'limit':8},context)
     stage(stages,'tool_output',output.sources,output.sources,'')
     actual_calls=(chosen.calls if which=='lightrag' else [])+navigation_calls
     record.update(completed=False,retrieval_completed=output.success,no_answer_generated=True,
       sources=output.sources,tool_content=output.content,tool_metadata=output.metadata,
       retrieval_calls=actual_calls,trace=stages,actual_backends=sorted({c['actual_backend'] for c in actual_calls}),
       graph_context=chosen.last_result.get('graph_context',[]) if which=='lightrag' and chosen.last_result else [])
     return record
    prompt=build_loop_system_prompt(target=target,definitions=registry.definitions())+'\n必须先调用retrieve_course取得本轮教材原文，再按其编号回答；无依据明确说明，不根据图谱关系发明先修顺序。回答用120至180字，比较覆盖双方；不要长篇逐字重复来源，遵守当前宿主260字门禁。'
    loop=LocalAgentLoop(client)
    history=body.get('history') or []
    result=loop.run(LoopRequest(student_id=student,session_id=student,task_id=attempt,request_id=attempt,message=question,
       system_prompt=prompt,tools=registry,target=target,navigation=navigation,seed_messages=history,publish_gate=gate,
       max_exploration_rounds=3,max_settlement_rounds=1,max_parallel_calls=1,tool_timeout_seconds=120))
    actual_calls=(chosen.calls if which=='lightrag' else [])+navigation_calls
    record.update(completed=result.completed,error=result.error,reply=result.final_text,tool_steps=result.tool_steps,
      sources=result.sources,loop_messages=result.messages,loop_events=result.events,loop_usage=result.usage,
      retrieval_calls=actual_calls,judgements=judgements,references=published.get('references',[]),
      navigation=nav,source_mapping_passed=bool(result.sources) and bool(published),fallback=False,
      actual_backends=sorted({c['actual_backend'] for c in actual_calls if 'actual_backend' in c}))
    if which=='lightrag' and chosen.last_result:
     record['visuals']=chosen.last_result['visuals'];record['graph_context']=chosen.last_result['graph_context']
    if result.completed:
     memory.append_exchange(student,question,result.final_text,selection_ref={'pdf_references':record['references']})
    record['stored_history_rows']=len(memory.get_history(student))
   except Exception as exc:record.update(completed=False,error_type=type(exc).__name__,error=str(exc),actual_backends=[],fault_injection=body.get('fault'))
   finally:
    record.setdefault('trace',stages)
    if coverage_nav is not None:
     record.update(coverage=coverage_nav.report,coverage_trace=coverage_nav.trace)
    record['current_target_unchanged']=body.get('current_target')
    if q5_service is not None:
     record['q5_after']=q5_service.status(q5_scope)
     record['q5_unchanged']=record['q5_before']==record['q5_after']
    record['stored_history_rows']=len(memory.get_history(student))
    record.setdefault('retrieval_calls',(chosen.calls if which=='lightrag' and chosen is not None else [])+navigation_calls)
    if not record.get('actual_backends'):
     record['actual_backends']=sorted({c['actual_backend'] for c in record['retrieval_calls'] if c.get('actual_backend')})
    record.update(model_calls=client.calls,total_seconds=time.monotonic()-started,cost=None,cost_note='API未返回金额；只记录返回token，不估价')
    (out/'attempts').mkdir(exist_ok=True)
    (out/'attempts'/f'{attempt}.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    with (out/'attempts.jsonl').open('a',encoding='utf-8') as stream:stream.write(json.dumps(record,ensure_ascii=False)+'\n')
   return record
 uvicorn.run(app,host='127.0.0.1',port=args.port,workers=1)
if __name__=='__main__':main()
