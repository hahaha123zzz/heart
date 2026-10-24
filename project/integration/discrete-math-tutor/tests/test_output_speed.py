"""提速边界：传输生命周期、来源原子提交、预算和候选排队。"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
import os
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from agents.q3_navigation import LearningTarget, SourceRef, StubLearningNavigator
from agents.q3_tools import RetrieveCourseTool
from agents.tool_protocol import ToolContext, Cancellation, CancelledError, ToolRegistry
from knowledge.lightrag.write_lock import query_ownership
from llm.execution_budget import ExecutionBudget, current_budget, BudgetExceeded
from llm import transport


class SpeedTests(unittest.TestCase):
    def tearDown(self):
        transport.close_pool()

    def test_pool_reuses_transport_but_rotation_and_proxy_change_isolate(self):
        factory=Mock(side_effect=lambda **_:Mock())
        with patch('openai.OpenAI',factory):
            with transport.borrow('fixture-key','https://fixture.invalid') as first:
                with transport.borrow('fixture-key','https://fixture.invalid') as second:
                    self.assertIs(first,second)
            with transport.borrow('rotated-fixture','https://fixture.invalid') as rotated:
                self.assertIsNot(first,rotated)
            with patch.dict(os.environ,{'HTTPS_PROXY':'http://fixture.invalid:1'}):
                with transport.borrow('fixture-key','https://fixture.invalid') as proxy:
                    self.assertIsNot(first,proxy)
            transport.close_pool()
        self.assertEqual(factory.call_count,3)
        first.close.assert_called_once()

    def test_eviction_and_shutdown_wait_for_active_borrower(self):
        with patch('openai.OpenAI',side_effect=lambda **_:Mock()), patch.object(transport,'_limit',1):
            with transport.borrow('one','https://fixture.invalid') as first:
                with transport.borrow('two','https://fixture.invalid') as second:
                    first.close.assert_not_called()
                    transport.close_pool()
                    second.close.assert_not_called()
                second.close.assert_called_once()
                first.close.assert_not_called()
            first.close.assert_called_once()

    def test_parallel_same_identity_builds_once(self):
        barrier=threading.Barrier(3)
        def get(_):
            with transport.borrow('fixture','https://fixture.invalid') as client:
                barrier.wait(3)
                return client
        with patch('openai.OpenAI',side_effect=lambda **_:Mock()) as factory:
            with ThreadPoolExecutor(3) as executor:
                values=list(executor.map(get,range(3)))
            self.assertTrue(all(v is values[0] for v in values))
            self.assertEqual(factory.call_count,1)

    def test_independent_retrievals_are_not_globally_serialized(self):
        barrier=threading.Barrier(2)
        def search(**kwargs):
            barrier.wait(2)
            return [SourceRef('s','doc','原文',location={'stub':True})]
        def invoke(number):
            ctx=ToolContext(str(number),'session',navigation=SimpleNamespace(search=search),
                            state={'learning_target':LearningTarget('target','概念')})
            return RetrieveCourseTool().run({'query':'概念'},ctx)
        with patch('knowledge.answer_media.selected_media',return_value=[]):
            with ThreadPoolExecutor(2) as executor:
                results=list(executor.map(invoke,(1,2)))
        self.assertEqual([r.sources[0]['index'] for r in results],[1,1])

    def test_same_turn_parallel_sources_dedupe_and_numbers_commit_atomically(self):
        barrier=threading.Barrier(2)
        def search(**kw):
            barrier.wait(2)
            return [SourceRef('same','doc','同一原文'),SourceRef(kw['query'],'doc','其他原文')]
        ctx=ToolContext('s','tab',navigation=SimpleNamespace(search=search),
                        state={'learning_target':LearningTarget('target','概念')})
        with patch('knowledge.answer_media.selected_media',return_value=[]):
            with ThreadPoolExecutor(2) as executor:
                rows=list(executor.map(lambda q:RetrieveCourseTool().run({'query':q},ctx),('a','b')))
        sources=[s for r in rows for s in r.sources]
        self.assertEqual(sorted(s['index'] for s in sources),[1,2,3])
        self.assertEqual(len({s['source_id'] for s in sources}),3)
        self.assertEqual(ctx.state['source_offset'],3)

    def test_timed_out_tool_does_not_commit_late_sources(self):
        ctx=ToolContext('s','tab',navigation=SimpleNamespace(search=lambda **kw:(time.sleep(.03) or [SourceRef('s','d','text')])),
                        state={'learning_target':LearningTarget('target','概念')},deadline=time.monotonic()+.01)
        with self.assertRaises(TimeoutError):RetrieveCourseTool().run({'query':'概念'},ctx)
        self.assertNotIn('seen_source_ids',ctx.state)
        self.assertNotIn('source_offset',ctx.state)

    def test_media_timeout_does_not_reserve_citations(self):
        ctx=ToolContext('s','tab',navigation=SimpleNamespace(search=lambda **kw:[SourceRef('s','doc','原文')]),
            state={'learning_target':LearningTarget('target','概念')},deadline=time.monotonic()+.02)
        with patch('knowledge.answer_media.selected_media',side_effect=lambda *_a,**_kw:(time.sleep(.04) or [])):
            with self.assertRaises(TimeoutError):RetrieveCourseTool().run({'query':'概念'},ctx)
        self.assertNotIn('seen_source_ids',ctx.state)
        self.assertNotIn('source_offset',ctx.state)

    def test_candidate_wait_cancels_without_starting_query(self):
        async def scenario(root):
            cancellation=Cancellation()
            async with query_ownership(root):
                async def waiter():
                    async with query_ownership(root,cancellation):self.fail('取消的等待不得进入')
                task=asyncio.create_task(waiter())
                await asyncio.sleep(.02);cancellation.cancel()
                with self.assertRaises(CancelledError):await task
            async with query_ownership(root):pass
        with tempfile.TemporaryDirectory() as root:asyncio.run(scenario(Path(root)))

    def test_candidate_wait_uses_same_activity_deadline(self):
        async def scenario(root):
            async with query_ownership(root):
                token=current_budget.set(ExecutionBudget(.02))
                try:
                    with self.assertRaises(BudgetExceeded):
                        async with query_ownership(root):self.fail('不得进入')
                finally:current_budget.reset(token)
        with tempfile.TemporaryDirectory() as root:asyncio.run(scenario(Path(root)))

    def test_same_size_same_mtime_change_is_rejected(self):
        from knowledge.lightrag.course_input import inventory,verify
        from knowledge.lightrag.ingress import IngressError
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'manifest.json';path.write_bytes(b'aaaa')
            expected=inventory(root);stat=path.stat();path.write_bytes(b'bbbb')
            os.utime(path,ns=(stat.st_atime_ns,stat.st_mtime_ns))
            with self.assertRaises(IngressError):verify(root,expected)

    def test_prefetch_replaces_model_tool_selection_and_keeps_publish_gate(self):
        from agents.agent_loop import LocalAgentLoop
        from tests.test_q3_agent_loop import ScriptedLLM,final_round,request
        llm=ScriptedLLM([final_round('依据原文[1]')]);registry=ToolRegistry();registry.register(RetrieveCourseTool())
        navigator=StubLearningNavigator(sources=[SourceRef('s','doc','原文')])
        gate=Mock(return_value=(True,''))
        with patch('knowledge.answer_media.selected_media',return_value=[]):
            result=LocalAgentLoop(llm).run(request(llm,registry,target=LearningTarget('t','概念'),
                navigation=navigator,requires_evidence=True,prefetch_query='概念',publish_gate=gate))
        self.assertTrue(result.completed)
        self.assertEqual(len(llm.calls),1)
        self.assertEqual(llm.calls[0]['tools'],[])
        self.assertEqual(result.sources[0]['index'],1)
        gate.assert_called_once()

    def test_combined_object_decision_replaces_separate_judge(self):
        from knowledge.lightrag.coverage import CoverageNavigator,Requirement
        from tests.test_lightrag_coverage import ref
        navigator=Mock(last_result=None);navigator.search.return_value=[ref('s1',1)]
        decide=Mock(side_effect=lambda req,rows:(rows,{'source_ids':[r.source_id for r in rows],'reason':'原文支持定义'}))
        select=Mock(side_effect=AssertionError('不得再次选证'));judge=Mock(side_effect=AssertionError('不得再次覆盖判定'))
        coverage=CoverageNavigator(navigator,question='比较',requirements=[Requirement('a','实验程序',1)],
                                  select=select,judge=judge,decide=decide)
        self.assertEqual(len(coverage.search(target=LearningTarget('t','比较'),query='比较',limit=4)),1)
        self.assertEqual(coverage.report['status'],'covered')
        self.assertEqual(decide.call_count,1)

    def test_empty_grounded_object_is_gap_not_fabricated_or_global_failure(self):
        from knowledge.grounded_citations import choose_evidence
        from knowledge.lightrag.coverage import Requirement
        llm=Mock()
        with patch('knowledge.grounded_citations.documents',return_value=[]),patch('knowledge.grounded_citations.LiveCitationIndex'):
            bundle=choose_evidence(llm,'缺失对象',[],'live',coverage=Requirement('missing','缺失对象',2))
        self.assertEqual(bundle.sources,[])
        self.assertIn('不能支持',bundle.coverage_reason)
        llm.chat_json.assert_not_called()

    def test_query_checks_content_twice_and_rejects_inflight_same_stat_change(self):
        from contextlib import ExitStack
        from unittest.mock import AsyncMock
        from knowledge.lightrag.retrieval import LightRagBackend
        from knowledge.lightrag.course_input import digest,inventory,verify_active,COURSE
        from knowledge.lightrag import retrieval
        from knowledge.lightrag.ingress import IngressError
        from knowledge.lightrag.config import HostEmbedding
        for tamper in (False,True):
            with tempfile.TemporaryDirectory() as temp, ExitStack() as stack:
                root=Path(temp);candidate=root/'candidate';candidate.mkdir()
                frozen=candidate/'input';frozen.mkdir();active=root/'active';active.mkdir()
                for directory in (frozen,active):
                    (directory/'manifest.json').write_text('original')
                (frozen/'pdf_manifest.json').write_text('[]')
                (active/'pdf_manifest.json').write_text('[]')
                manifest={'course_id':COURSE,'source_root':str(active),'files':inventory(frozen)}
                (candidate/'input_manifest.json').write_text(json.dumps(manifest))
                (candidate/'progress.json').write_text(json.dumps({'state':'candidate_complete',
                    'chapters':{str(i):{'complete':True} for i in range(1,12)}}))
                (candidate/'source_map.json').write_text('{}');(candidate/'policy.json').write_text('{"input_signature":"fixed"}')
                (candidate/'index').mkdir();(candidate/'index/core').write_text('core')
                (candidate/'index_files.json').write_text(json.dumps({'core':digest(candidate/'index/core')}))
                backend=LightRagBackend(candidate,authorized_course_ids={COURSE},allow_candidate=True,source_root=active)
                async def native(*_):
                    if tamper:
                        path=active/'manifest.json';stat=path.stat();path.write_text('replaced')
                        os.utime(path,ns=(stat.st_atime_ns,stat.st_mtime_ns))
                    return '',[]
                async def worker(job):return await job(None)
                stack.enter_context(patch.object(retrieval,'embedding_config',AsyncMock(return_value=HostEmbedding())))
                stack.enter_context(patch.object(retrieval.storage,'require_compatible_embedding'))
                stack.enter_context(patch.object(retrieval,'resolve_query_roles',return_value={}))
                stack.enter_context(patch.object(retrieval,'query_binding',return_value={}))
                stack.enter_context(patch.object(retrieval,'run_in_worker_loop',worker))
                stack.enter_context(patch.object(retrieval.engine,'build_rag',return_value=SimpleNamespace()))
                stack.enter_context(patch.object(retrieval.engine,'initialize',AsyncMock()))
                stack.enter_context(patch.object(retrieval.engine,'finalize',AsyncMock()))
                stack.enter_context(patch.object(retrieval.engine,'query_with_sources',native))
                stack.enter_context(patch.object(retrieval,'rank_sources',return_value=[]))
                stack.enter_context(patch('knowledge.lightrag.paths.bind_candidate_sidecars',return_value={}))
                stack.enter_context(patch('knowledge.lightrag.course_input.visual_inventory',return_value=({},[],{})))
                checks=stack.enter_context(patch.object(backend,'validate',wraps=backend.validate))
                host_checks=stack.enter_context(patch.object(retrieval,'verify_active',wraps=verify_active))
                if tamper:
                    with self.assertRaisesRegex(IngressError,'宿主教材'):
                        asyncio.run(backend.search('概念',course_id=COURSE))
                else:
                    self.assertEqual(asyncio.run(backend.search('概念',course_id=COURSE))['status'],'no_evidence')
                self.assertEqual(checks.call_count,2)
                self.assertEqual(host_checks.call_count,2)


if __name__=='__main__':unittest.main()
