import asyncio
import contextvars
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from knowledge import fixed_book


class FixedBookTests(unittest.TestCase):
    def test_tool_release_validation_uses_startup_snapshot_and_rejects_wrong_id(self):
        from knowledge.course_release import validate
        state=SimpleNamespace(release={'release_id':'frozen','ready':False,'gaps':['pending']})
        with (patch.object(fixed_book,'active',return_value=state),
              patch('knowledge.course_release.clear_cache',side_effect=AssertionError('请求不清缓存')),
              patch('knowledge.course_release.snapshot',side_effect=AssertionError('请求不扫描教材'))):
            value=validate({'release_id':'frozen'})
            value['gaps'].clear()
            self.assertEqual(state.release['gaps'],['pending'])
            with self.assertRaisesRegex(ValueError,'版本已变化'):validate({'release_id':'other'})

    def test_failed_graph_initialization_releases_partial_storage(self):
        from unittest.mock import AsyncMock
        graph=fixed_book.ResidentGraph(SimpleNamespace(candidate=Path('.')),SimpleNamespace(dim=2,max_tokens=32),{})
        rag=object()
        with (patch('knowledge.lightrag.engine.build_rag',return_value=rag),
              patch('knowledge.lightrag.engine.initialize',new=AsyncMock(side_effect=RuntimeError('启动失败'))),
              patch('knowledge.lightrag.engine.finalize',new=AsyncMock()) as cleanup):
            with self.assertRaisesRegex(RuntimeError,'启动失败'):asyncio.run(graph.start())
        cleanup.assert_awaited_once_with(rag,cancel_pending=True)
        self.assertIsNone(graph.rag)

    def test_graph_close_error_does_not_skip_worker_and_pool_cleanup(self):
        from unittest.mock import AsyncMock,Mock
        from memory.background_worker import memory_lifespan
        worker=Mock()
        async def run():
            async with memory_lifespan(SimpleNamespace(state=SimpleNamespace(memory=SimpleNamespace(repo=Mock())))):
                pass
        with (patch.dict('os.environ',MEMORY_WORKER_ENABLED='1',MEMORY_REFLECTION_LLM='0'),
              patch('memory.background_worker.MemoryWorker',return_value=worker),
              patch.object(fixed_book,'start',new=AsyncMock()),
              patch.object(fixed_book,'stop',new=AsyncMock(side_effect=RuntimeError('关闭失败'))),
              patch('llm.transport.close_pool') as close):
            with self.assertRaisesRegex(RuntimeError,'关闭失败'):asyncio.run(run())
        worker.stop.assert_called_once();close.assert_called_once()

    def test_keywords_are_snapshot_local_specific_and_cached(self):
        graph=fixed_book.ResidentGraph(SimpleNamespace(entity_terms=('科学方法','自变量','科学')),None,{})
        self.assertEqual(graph.keywords('科学方法和自变量有什么联系'),('科学方法','自变量'))
        graph.keywords('科学方法和自变量有什么联系')
        self.assertEqual(graph.keywords.cache_info().hits,1)
        other=fixed_book.ResidentGraph(SimpleNamespace(entity_terms=('因变量',)),None,{})
        self.assertEqual(other.keywords('科学方法和自变量有什么联系'),())
        self.assertEqual(other.keywords('未知问题'),())
        asyncio.run(graph.close());asyncio.run(other.close())

    def test_sdk_accepts_rule_keywords_without_model_extraction(self):
        from knowledge.lightrag import engine
        from lightrag.operate import get_keywords_from_query
        class Rag:
            async def aquery_data(self,query,param):
                self.keywords=await get_keywords_from_query(query,param,{},None)
                return {'status':'failure','metadata':{'failure_reason':'no_results'}}
        rag=Rag()
        with patch('lightrag.operate.extract_keywords_only',side_effect=AssertionError('不应调用提取模型')):
            asyncio.run(engine.query_with_sources(rag,'关系问题',keywords=('科学方法','自变量')))
        self.assertEqual(rag.keywords,(['科学方法','自变量'],['科学方法','自变量']))

    def test_startup_accepts_absent_optional_modality(self):
        from unittest.mock import AsyncMock
        with TemporaryDirectory() as folder:
            root=Path(folder);(root/'blocks.json').write_text('[]',encoding='utf8')
            rag=SimpleNamespace(full_docs=SimpleNamespace(get_by_id=AsyncMock(return_value={})))
            graph=fixed_book.ResidentGraph(SimpleNamespace(candidate=root,source_map={'chapter.pdf':{}}),
                SimpleNamespace(dim=2,max_tokens=32),{})
            with (patch('knowledge.lightrag.engine.build_rag',return_value=rag),
                  patch('knowledge.lightrag.engine.initialize',new=AsyncMock()),
                  patch('knowledge.lightrag.paths.bind_candidate_sidecars',return_value={}),
                  patch('knowledge.lightrag.ingress.load_verified_bundle',return_value=({'blocks':{'path':'blocks.json'}},root)),
                  patch('lightrag.utils_pipeline.sidecar_modality_path',return_value=str(root/'missing.json'))):
                asyncio.run(graph.start())
            self.assertEqual(graph.provenance['chapter.pdf']['modalities'],{})

    def test_unmarked_explanation_keeps_evidence_without_rewriting(self):
        from agents.agent_loop import LoopResult
        from agents.agent_loop_service import _publish_gate
        from agents.q3_navigation import LearningTarget
        result=LoopResult(sources=[{'source_id':'verified','chapter_id':2}])
        gate=_publish_gate(None,SimpleNamespace(message='再通俗一点'),LearningTarget('topic','因变量'))
        with patch.object(fixed_book,'active',return_value=object()):
            self.assertTrue(gate('因变量就是你要记录的反应。',result)[0])
        self.assertEqual(result._publication['pdf_references'],[])
        self.assertEqual(result.sources[0]['source_id'],'verified')

    def test_query_provenance_uses_preverified_bundle_without_disk_recheck(self):
        from unittest.mock import AsyncMock
        from knowledge.lightrag.retrieval import attach_provenance
        from knowledge.lightrag import engine
        name='chapter_01.generated.pdf'
        rag=SimpleNamespace(text_chunks=SimpleNamespace(get_by_id=AsyncMock(return_value={
            'full_doc_id':engine._document_id(name),'sidecar':{'refs':[{'type':'table','id':'t1'}]}})))
        prepared={name:{'raw':[{'heart_block_index':7,'heart_asset_id':'table-1'}],
            'modalities':{'tables':{'t1':{'self_ref':'blocks.json#/0'}}}}}
        records=[{'kind':'chunk','source':name,'chunk_id':'c1'}]
        with patch('knowledge.lightrag.ingress.load_verified_bundle', side_effect=AssertionError('不能重复读盘校验')):
            result=asyncio.run(attach_provenance(rag,Path('.'),records,prepared=prepared))
        self.assertEqual(result[0]['original_blocks'][0]['block_index'],7)

    def test_card_instructions_do_not_pollute_resumed_search(self):
        text='请先用问题卡确认我要简短还是详细解释自变量，等我选择后再解释。\n补充说明：简短解释'
        self.assertEqual(fixed_book.search_query(text),'自变量')

    def test_old_citation_numbers_are_not_presented_as_current_evidence(self):
        from agents.agent_loop import LocalAgentLoop, LoopRequest, LoopResult
        from agents.tool_protocol import ToolRegistry
        history=[{'role':'assistant','content':'旧回答[7]。'}]
        request=LoopRequest(student_id='a',session_id='s',task_id='t',request_id='r',
            message='继续',system_prompt='当前回合',tools=ToolRegistry(),seed_messages=history)
        messages=LocalAgentLoop(None)._initial_messages(request,None,'',LoopResult())
        self.assertNotIn('[7]',messages[1]['content'])
        self.assertEqual(history[0]['content'],'旧回答[7]。')

    def test_frozen_digest_is_startup_identity_and_missing_still_fails(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'book';path.write_bytes(b'original')
            original = fixed_book.digest(path)
            state = SimpleNamespace(ready=True, hashes={str(path.resolve()):original})
            with patch.dict('os.environ', FIXED_BOOK_RETRIEVAL_ENABLED='1'), patch.object(fixed_book, 'runtime', state):
                path.write_bytes(b'changed-after-startup')
                self.assertEqual(fixed_book.digest(path), original)
                path.unlink()
                with self.assertRaises(FileNotFoundError):fixed_book.digest(path)

    def test_resident_callbacks_use_current_request_context(self):
        async def run():
            marker=contextvars.ContextVar('test-marker', default='none')
            graph=fixed_book.ResidentGraph(None, None, {})
            dispatch=graph.dispatch('query')
            async def callback():return marker.get()
            for name in ('student-a', 'student-b'):
                token=marker.set(name)
                graph.request={'callbacks':{'query':callback}, 'context':contextvars.copy_context()}
                marker.reset(token)
                self.assertEqual(await dispatch(), name)
            graph.request=None
            with self.assertRaises(RuntimeError):await dispatch()
        asyncio.run(run())

    def test_rule_selection_has_no_model_and_deduplicates(self):
        captured={}
        def choose(llm, question, sources, index, *, selection_fn):
            self.assertIsNone(llm)
            payload={'question':question,'candidates':[
                {'evidence_id':'a','quote':'自变量由研究者操纵'},
                {'evidence_id':'duplicate','quote':'自变量由研究者操纵'},
                {'evidence_id':'b','quote':'因变量由研究者测量'}]}
            captured.update(selection_fn(payload));return captured
        with (patch.object(fixed_book, 'active', return_value=SimpleNamespace(citation_path='frozen.sqlite3')),
              patch('knowledge.grounded_citations.choose_evidence', side_effect=choose)):
            fixed_book.rule_evidence('自变量是什么', [])
        self.assertEqual(captured['evidence_ids'][0], 'a')
        self.assertNotIn('duplicate', captured['evidence_ids'])

    def test_rule_selection_keeps_retrieval_score_and_excludes_unrelated_fillers(self):
        result=fixed_book.select_evidence({'question':'钟毅平是谁','candidates':[
            {'evidence_id':'body','quote':'钟毅平等研究自我面孔识别。','retrieval_score':.899,'retrieval_source_index':0},
            {'evidence_id':'reference','quote':'钟毅平,李琎,占友龙,范伟,杨子鹿.(2016).自我面孔识别的ERPs研究.心理学报,48(11),1379-1389.',
             'retrieval_score':.677,'retrieval_source_index':1},
            {'evidence_id':'unrelated','quote':'朱湘茹,刘昌.(2008).空间数字反应编码联合效应下冲突适应过程的ERP研究。',
             'retrieval_score':.677,'retrieval_source_index':1}]})
        self.assertEqual(result['evidence_ids'],['body','reference'])

    def test_rule_evidence_forwards_scores_from_original_retrieval_sources(self):
        sources=[SimpleNamespace(location={'retrieval_score':score},to_dict=lambda:{}) for score in (.899,.677)]
        def choose(llm,question,chunks,index,*,selection_fn):
            return selection_fn({'question':question,'candidates':[
                {'evidence_id':'reference','quote':'钟毅平,李琎,占友龙,范伟等研究了面孔识别。','retrieval_source_index':1},
                {'evidence_id':'body','quote':'钟毅平等研究面孔识别。','retrieval_source_index':0}]})
        with (patch.object(fixed_book,'active',return_value=SimpleNamespace(citation_path='frozen.sqlite3')),
              patch('knowledge.lightrag.retrieval.as_textbook_chunk',return_value=None),
              patch('knowledge.grounded_citations.choose_evidence',side_effect=choose)):
            result=fixed_book.rule_evidence('钟毅平是谁',sources)
        self.assertEqual(result['evidence_ids'],['body','reference'])

    def test_rule_selection_retains_verified_target_without_keyword_overlap(self):
        result=fixed_book.select_evidence({'question':'解释这段','candidates':[
            {'evidence_id':'selected','quote':'被试应接受全部实验处理水平。','selected_target':True},
            {'evidence_id':'other','quote':'另一段比较长但是无关的内容不能挤掉用户指定的原文。'}]})
        self.assertEqual(result['evidence_ids'],['selected'])

    def test_fast_router_respects_complex_questions(self):
        from agents.course_search import CourseSearch
        search=CourseSearch(None, message='自变量是什么', llm=None)
        with patch.object(fixed_book, 'active', return_value=object()):
            self.assertTrue(search._use_fast_path('自变量'))
            search.message='自变量和因变量有什么区别'
            self.assertFalse(search._use_fast_path(search.message))

    def test_context_reads_overlap_without_sharing_sessions(self):
        import threading
        from agents.task_service import TaskService
        barrier=threading.Barrier(2)
        def read(student):
            barrier.wait(timeout=3)
            return student
        service=TaskService.__new__(TaskService)
        service.tutor=SimpleNamespace(memory=SimpleNamespace(get_profile=read, list_knowledge_points=read))
        service._read_context=lambda request, profile, points: (profile.result(), points.result())
        with patch.object(fixed_book, 'active', return_value=object()):
            self.assertEqual(service._context(SimpleNamespace(student_id='student-a')), ('student-a','student-a'))

    def test_crosschapter_subtasks_overlap_and_keep_separate_results(self):
        import threading
        from agents.q3_navigation import LearningTarget, SourceRef
        from knowledge.lightrag.coverage import CoverageNavigator, Requirement
        barrier=threading.Barrier(2)
        class Navigator:
            def __init__(self):self.last_result=None;self.calls=[]
            def fork(self):return Navigator()
            def search(self, *, target, **kwargs):
                barrier.wait(timeout=3)
                self.calls.append({'query':target.name})
                self.last_result={'usage':{'embedding_batches':1,'embedding_texts':2,'llm_calls':0,'calls':[],'stages':[]}}
                return [SourceRef(source_id=target.name, document_id=target.name, version='version',
                    chapter_id=target.chapter_id, text=target.name, location={'source_spans':[{'block_id':1}]})]
        nav=Navigator()
        coverage=CoverageNavigator(nav, question='对比', requirements=[Requirement('a','甲',1),Requirement('b','乙',2)],
            select=lambda req, refs:refs, judge=lambda req, refs:{'source_ids':[r.source_id for r in refs],'reason':'原文支持'})
        with patch.object(fixed_book, 'active', return_value=object()):
            result=coverage.search(target=LearningTarget('current','当前'), query='对比', limit=4)
        self.assertEqual({r.source_id for r in result}, {'甲','乙'})
        self.assertEqual(coverage.report['status'], 'covered')
        self.assertEqual(nav.last_result['usage']['embedding_batches'], 2)
        self.assertEqual(len(nav.calls), 2)


if __name__ == '__main__':unittest.main()
