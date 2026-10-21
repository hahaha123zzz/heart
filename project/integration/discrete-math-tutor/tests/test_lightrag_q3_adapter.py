"""固定已提交宿主协议验证；不调用真实模型。"""
import os,sys,unittest,asyncio
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1]
if os.getenv('LIGHTRAG_ACCEPTANCE_HOST'):sys.path.insert(0,os.environ['LIGHTRAG_ACCEPTANCE_HOST'])
import knowledge
if str(ROOT/'knowledge') not in knowledge.__path__:knowledge.__path__.append(str(ROOT/'knowledge'))
from agents.q3_navigation import LearningTarget,NavigationDecision,SourceRef
from knowledge.lightrag.q3_adapter import LightRagNavigator

class AdapterTests(unittest.TestCase):
 def test_fault_requires_actual_failed_tool_not_model_connection_error(self):
  from scripts.check_lightrag_acceptance import fault_verified
  result={'completed':False,'fallback':False,'error':'model_unavailable'}
  self.assertFalse(fault_verified(result,'backend_unavailable','lightrag'))
  result.update(actual_backends=['lightrag'],loop_messages=[{'role':'tool','content':'retrieve_course 执行失败：FileNotFoundError: missing'}])
  self.assertTrue(fault_verified(result,'backend_unavailable','lightrag'))
  self.assertFalse(fault_verified(result,'backend_unavailable','baseline'))
  self.assertFalse(fault_verified(result,'source_stale','lightrag'))
  self.assertTrue(fault_verified({'error':'教材已更新，请重新选择内容'},'source_stale','lightrag'))

 def base(self):
  class Base:
   def resolve(self,**kwargs):return NavigationDecision('teach',LearningTarget('q2-target','Q2目标'))
   def search(self,**kwargs):return []
  return Base()
 def test_resolve_delegates(self):
  result=LightRagNavigator(self.base(),None).resolve(message='下一知识点')
  self.assertEqual(result.target.target_id,'q2-target')
 def test_exact_navigation_is_not_lightrag_success(self):
  nav=LightRagNavigator(self.base(),None)
  self.assertEqual(nav.search(target=LearningTarget('ch1:s1:b0','原文目标'),query='下一',limit=4),[])
  self.assertEqual(nav.calls[0]['actual_backend'],'q2_exact');self.assertFalse(nav.calls[0]['fallback'])
 def test_source_identity_and_release(self):
  row={'source_id':'real-block','document_id':'real-document','version':'v','chapter_id':2,'section_id':1,
       'text':'原文','quote':'原文','page':None,'image_refs':[],'location':{'source_spans':[{'block_id':3}]}}
  class Backend:
   async def search(self,*a,**k):return {'sources':[row],'status':'success','usage':{},'visuals':[]}
  nav=LightRagNavigator(self.base(),Backend())
  with patch.dict(sys.modules,{'knowledge.course_release':SimpleNamespace(binding=lambda:{'release_id':'r','status':'staging','ready':False})}):
   source=nav.search(target=LearningTarget('query','概念'),query='概念',limit=4)[0]
  self.assertIsInstance(source,SourceRef);self.assertEqual(source.version,'v')
  self.assertEqual(source.location['textbook_release'],'r');self.assertFalse(source.location['release_ready'])
  self.assertEqual(source.location['source_spans'],row['location']['source_spans'])
 def test_original_visual_stays_pending_and_not_seen(self):
  row={'source_id':'block','document_id':'doc','version':'v','chapter_id':2,'section_id':1,
       'text':'原文','quote':'原文','page':None,'image_refs':[],'location':{}}
  class Backend:
   async def search(self,*a,**k):return {'sources':[row],'status':'success','usage':{},
      'visuals':[{'id':'image','chapter_id':2,'section_id':1,'sha256':'hash'}]}
  asset=SimpleNamespace(is_valid=lambda:True,sha256='hash',public=lambda:{'id':'image','review_status':'pending'})
  modules={'knowledge.course_release':SimpleNamespace(binding=lambda:{'release_id':'r','status':'staging','ready':False}),
           'knowledge.source_visuals':SimpleNamespace(get_visual=lambda _:asset)}
  nav=LightRagNavigator(self.base(),Backend())
  with patch.dict(sys.modules,modules):ref=nav.search(target=LearningTarget('query','图'),query='图',limit=1)[0]
  self.assertEqual(ref.image_refs[0]['review_status'],'pending');self.assertFalse(ref.image_refs[0]['model_saw_pixels'])
  modules['knowledge.source_visuals']=SimpleNamespace(get_visual=lambda _:None)
  with patch.dict(sys.modules,modules):
   with self.assertRaisesRegex(ValueError,'无法映射'):nav.search(target=LearningTarget('query','图'),query='图',limit=1)
 def test_unmapped_source_is_explicit_no_evidence(self):
  class Backend:
   async def search(self,*a,**k):return {'sources':[],'status':'no_evidence','usage':{}}
  nav=LightRagNavigator(self.base(),Backend())
  with patch.dict(sys.modules,{'knowledge.course_release':SimpleNamespace(binding=lambda:{'release_id':'r','status':'staging','ready':False})}):
   self.assertEqual(nav.search(target=LearningTarget('query','概念'),query='概念',limit=1),[])
  self.assertEqual(nav.calls[0]['status'],'no_evidence');self.assertFalse(nav.calls[0]['fallback'])
 def test_failure_never_falls_back(self):
  class Backend:
   async def search(self,*a,**k):raise RuntimeError('unavailable')
  nav=LightRagNavigator(self.base(),Backend())
  with self.assertRaisesRegex(RuntimeError,'unavailable'):nav.search(target=LearningTarget('query','概念'),query='概念',limit=4)
  self.assertEqual(nav.calls[0]['status'],'failed');self.assertFalse(nav.calls[0]['fallback'])
 def test_async_cancel_uses_existing_tool_exception(self):
  from agents.tool_protocol import CancelledError
  class Backend:
   async def search(self,*a,**k):raise asyncio.CancelledError()
  nav=LightRagNavigator(self.base(),Backend())
  with self.assertRaises(CancelledError):nav.search(target=LearningTarget('query','概念'),query='概念',limit=4)
if __name__=='__main__':unittest.main()
