"""覆盖策略回归；假后端测试不冒充真实模型或页面验收。"""
import unittest,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if os.getenv("LIGHTRAG_ACCEPTANCE_HOST"):sys.path.insert(0,os.environ["LIGHTRAG_ACCEPTANCE_HOST"])
import knowledge
if str(ROOT/"knowledge") not in knowledge.__path__:knowledge.__path__.append(str(ROOT/"knowledge"))
from dataclasses import replace
from types import SimpleNamespace
# 宿主可能已有旧后端，隔离验收只覆盖当前分支的LightRAG包。
import knowledge.lightrag
knowledge.lightrag.__path__.insert(0,str(ROOT/'knowledge/lightrag'))
from agents.q3_navigation import LearningTarget,SourceRef
from agents.tool_protocol import Cancellation,CancelledError,ToolResult
from knowledge.lightrag.coverage import CoverageNavigator,requirements_for
from knowledge.lightrag.relationships import relationship_context,append_tool_context

def ref(id,chapter,text='有效对象原文内容'):
 return SourceRef(id,'doc'+str(chapter),text,'v'+str(chapter),chapter,1,quote=text,
  location={'block_start':1,'block_char_start':0,'block_char_end':len(text),
   'source_spans':[{'block_id':1,'block_start':0,'block_end':len(text)}],'sdk_chunk_ids':['chunk'+id],
   'textbook_release':'staging-id','release_status':'staging','release_ready':False})

class CoverageTests(unittest.TestCase):
 def test_single_empty_reports_missing_and_copies_native_trace(self):
  event={'stage':'scope_filter','rows':[{'source_id':'outside','accepted':False}]}
  backend=SimpleNamespace(search=lambda **kw:[],last_result={'trace':[event]})
  nav=CoverageNavigator(backend,question='被试反应',select=self.selector,judge=self.judge)
  self.assertEqual(nav.search(target=self.target(),query='被试反应',limit=6),[])
  self.assertEqual(nav.report['status'],'no_evidence')
  self.assertEqual(nav.report['missing'][0]['id'],'single')
  self.assertEqual(nav.trace[0]['stage'],'scope_filter')
  self.assertNotIn('subproblem',event)
  self.assertNotIn('subproblems',event['rows'][0])
 def target(self):return LearningTarget('ch5:s1:b2','路径中目标',chapter_id=5,section_id=1)
 def navigator(self,search):return SimpleNamespace(search=search,resolve=lambda **kw:kw)
 def selector(self,req,rows):return rows
 def judge(self,req,rows):return {'source_ids':[r.source_id for r in rows if req.query.replace('控制','') in r.text],'reason':'对象内容须相关'}
 def test_explicit_chapters_and_same_chapter_comparison(self):
  rs=requirements_for('第一章的实验程序和第二章的自变量控制有哪些联系？')
  self.assertEqual([(r.chapter_id,r.query) for r in rs],[(1,'实验程序'),(2,'自变量控制')])
  rs=requirements_for('第二章的自变量和因变量有什么区别？')
  self.assertEqual([(r.chapter_id,r.query) for r in rs],[(2,'自变量'),(2,'因变量')])
 def test_single_no_extra_retrieval_or_judge(self):
  calls=[]
  def search(**kw):calls.append(kw);return [ref('a',5)]
  nav=CoverageNavigator(self.navigator(search),question='什么是自变量？',select=self.selector,judge=lambda *a:1/0)
  self.assertEqual(len(nav.search(target=self.target(),query='自变量',limit=6)),1)
  self.assertEqual(len(calls),1);self.assertEqual(calls[0]['target'],self.target())
 def test_cross_chapter_scopes_override_cursor_without_mutation(self):
  calls=[];target=self.target()
  def search(**kw):calls.append(kw);r=kw['target'];return [ref(str(r.chapter_id),r.chapter_id,r.name+'的原文')]
  nav=CoverageNavigator(self.navigator(search),question='第一章的实验程序和第二章的自变量控制有哪些联系？',select=self.selector,judge=self.judge)
  refs=nav.search(target=target,query='改写后的混合问题',limit=2)
  self.assertEqual({r.chapter_id for r in refs},{1,2});self.assertEqual(len(calls),2)
  self.assertEqual(target.chapter_id,5);self.assertEqual(nav.report['missing'],[])
 def test_limit_preserves_each_object_with_many_candidates(self):
  def search(**kw):
   t=kw['target'];return [replace(ref(t.name+str(i),t.chapter_id,t.name+'原文'),location={**ref('x',t.chapter_id).location,'source_spans':[{'block_id':i,'block_start':0,'block_end':10}]}) for i in range(8)]
  nav=CoverageNavigator(self.navigator(search),question='第一章的实验程序和第二章的自变量控制有哪些联系？',select=self.selector,judge=self.judge)
  rows=nav.search(target=self.target(),query='比较',limit=4)
  self.assertEqual({r.chapter_id for r in rows},{1,2});self.assertEqual(nav.report['status'],'covered')
 def test_wrong_topic_same_chapter_rejected_and_missing_only_retried(self):
  calls=[]
  def search(**kw):
   calls.append(kw);r=kw['target'];return [ref(str(r.chapter_id),r.chapter_id,'实验程序的原文' if r.chapter_id==1 else '玄武岩矿物')]
  nav=CoverageNavigator(self.navigator(search),question='第一章的实验程序和第二章的自变量控制有哪些联系？',select=self.selector,judge=self.judge)
  rows=nav.search(target=self.target(),query='比较',limit=4)
  self.assertEqual([r.chapter_id for r in rows],[1]);self.assertEqual(len(calls),3)
  self.assertEqual([r['chapter_id'] for r in nav.report['missing']],[2]);self.assertEqual(nav.report['supplemental_calls'],1)
 def test_dedupe_balanced_merge_and_source_identity(self):
  a=ref('a',2,'自变量与因变量的有效原文')
  def search(**kw):return [a,a]
  nav=CoverageNavigator(self.navigator(search),question='第二章的自变量和因变量有什么区别？',select=self.selector,judge=self.judge)
  rows=nav.search(target=self.target(),query='比较',limit=2)
  self.assertEqual(len(rows),1);self.assertEqual(len(rows[0].location['retrieval_requirements']),2)
  self.assertEqual(rows[0].version,'v2')
 def test_cancellation_failure_and_stale_fail_closed(self):
  token=Cancellation();token.cancel()
  nav=CoverageNavigator(self.navigator(lambda **k:[]),question='自变量和因变量有什么区别？',select=self.selector,judge=self.judge,cancellation=token)
  with self.assertRaises(CancelledError):nav.search(target=self.target(),query='比较',limit=6)
  for error in [RuntimeError('后端不可用'),ValueError('来源已失效')]:
   def search(**kw):raise error
   nav=CoverageNavigator(self.navigator(search),question='自变量和因变量有什么区别？',select=self.selector,judge=self.judge)
   with self.assertRaises(type(error)):nav.search(target=self.target(),query='比较',limit=6)
 def test_insufficient_output_budget_rejected(self):
  nav=CoverageNavigator(self.navigator(lambda **k:[]),question='自变量和因变量有什么区别？',select=self.selector,judge=self.judge)
  with self.assertRaises(ValueError):nav.search(target=self.target(),query='比较',limit=1)
 def test_semantic_model_cannot_invent_ids(self):
  nav=CoverageNavigator(self.navigator(lambda **k:[ref('a',2)]),question='自变量和因变量有什么区别？',select=self.selector,judge=lambda *a:{'source_ids':['forged'],'reason':'假的'})
  with self.assertRaises(ValueError):nav.search(target=self.target(),query='比较',limit=4)
 def test_relationship_budget_prioritizes_supported_edges(self):
  a=ref('a',2)
  records=[{'kind':'entity','entity_id':'e'+str(i),'source_id':'missing','content':'无支持实体'} for i in range(20)]
  records.append({'kind':'relationship','relation_id':'edge','src_id':'x','tgt_id':'y','source_id':'chunka','content':'有链接关系'})
  output=relationship_context(records,[a],limit=1)
  self.assertEqual(output['associations'][0]['id'],'edge')
 def test_cancel_after_selection_does_not_publish_partial_success(self):
  token=Cancellation()
  def select(req,rows):token.cancel();return rows
  nav=CoverageNavigator(self.navigator(lambda **k:[ref('a',2)]),question='自变量和因变量有什么区别？',select=select,judge=self.judge,cancellation=token)
  with self.assertRaises(CancelledError):nav.search(target=self.target(),query='比较',limit=4)
 def test_backend_failure_keeps_available_metrics_and_original_exception(self):
  from knowledge.lightrag.q3_adapter import LightRagNavigator
  error=ConnectionError('transport failure');error.lightrag_audit={'trace':[{'stage':'native_recall','rows':[]}],'usage':{'llm_calls':1,'calls':[{'status':'failed'}]}}
  class Backend:
   async def search(self,*a,**kw):raise error
  nav=LightRagNavigator(self.navigator(lambda **k:[]),Backend())
  with self.assertRaises(ConnectionError):nav.search(target=LearningTarget('query','对象'),query='对象',limit=4)
  self.assertEqual(nav.calls[0]['usage']['llm_calls'],1);self.assertEqual(nav.calls[0]['status'],'failed')
 def test_trace_duplicates_have_explicit_exclusion(self):
  from knowledge.lightrag.trace import stage
  a=ref('a',2);trace=[];stage(trace,'dedupe',[a,a],[a],'duplicate_original_identity')
  self.assertEqual([r['accepted'] for r in trace[0]['rows']],[True,False])
  self.assertEqual(trace[0]['rows'][1]['exclusion_reason'],'duplicate_original_identity')
 def test_actual_tool_keeps_citations_and_dedup_contract(self):
  from knowledge.lightrag.q3_adapter import ContextualRetrieveCourseTool
  from agents.tool_protocol import ToolContext
  a=ref('a',2);nav=self.navigator(lambda **k:[a]);nav.trace=[]
  nav.tool_context=lambda sources:relationship_context([{'kind':'relationship','relation_id':'edge','src_id':'x','tgt_id':'y','source_id':'chunka','content':'关系摘要'}],sources)
  context=ToolContext('test','test',navigation=nav,state={'learning_target':self.target()})
  tool=ContextualRetrieveCourseTool();result=tool.run({'query':'自变量'},context)
  self.assertEqual(result.sources[0]['index'],1);self.assertEqual(result.sources[0]['source_id'],'a')
  self.assertEqual(len(result.sources),1);self.assertIn('关联候选',result.content)
  self.assertEqual(result.metadata['retrieval_context']['associations'][0]['id'],'edge')
  duplicate=tool.run({'query':'自变量'},context)
  self.assertFalse(duplicate.success);self.assertTrue(duplicate.metadata['duplicate_retrieval'])
 def test_relationships_separate_bounded_and_no_new_sources(self):
  a=ref('a',2)
  records=[{'kind':'relationship','relation_id':'r1','src_id':'自变量','tgt_id':'因变量','source_id':'chunka','content':'关联摘要'},
           {'kind':'entity','entity_id':'无支持实体','source_id':'missing','content':'无原文'}]
  graph=relationship_context(records,[a]);self.assertEqual(len(graph['associations']),2)
  self.assertEqual(graph['associations'][0]['source_links'][0]['version'],'v2')
  self.assertFalse(graph['associations'][0]['evidence_eligible']);self.assertEqual(graph['associations'][1]['status'],'requires_original_lookup')
  original=ToolResult(content='[1] 正文',sources=[a.to_dict()]);out=append_tool_context(original,graph)
  self.assertEqual(out.sources,original.sources);self.assertEqual(original.content,'[1] 正文');self.assertIn('关联候选',out.content)
  import json
  bounded=relationship_context(records*100,[a],max_chars=1100)
  self.assertLessEqual(len(json.dumps(bounded,ensure_ascii=False)),1100)
if __name__=='__main__':unittest.main()
