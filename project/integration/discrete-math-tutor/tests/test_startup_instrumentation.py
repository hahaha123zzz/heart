"""固定教材启动的四个内部时间点：入口、self.ready、start 完成、失败时不补零。"""
import asyncio
from contextlib import ExitStack, nullcontext
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from knowledge import fixed_book, startup_trace
import knowledge.course_release  # 先按真实教材目录导入，启动阶段才能替换其 validate


def rows(folder):
    written = list(Path(folder).glob('*.jsonl'))
    assert len(written) == 1, written
    return {row['stage']: row for row in
            (json.loads(line) for line in written[0].read_text(encoding='utf-8').splitlines())}


class FixedBookStartupTraceTests(unittest.TestCase):
    def setUp(self):
        startup_trace.reset()
        fixed_book.runtime = None

    tearDown = setUp

    def test_start_records_entry_ready_and_complete(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'policy.json').write_text('{}', encoding='utf-8')
            backend = SimpleNamespace(candidate=root, source_map={}, manifest={}, resident=None,
                                      entity_terms=(), validate=lambda *args, **kwargs: {},
                                      load_source_map=lambda: {})
            async def worker(call):
                result = call(None)
                return await result if asyncio.iscoroutine(result) else result
            async def embedding_config(*args):
                return SimpleNamespace(model='fixture-embed', dim=8, signature=lambda: 'sig')
            class Graph:
                def __init__(self, *args):
                    self.rag = SimpleNamespace(chunk_entity_relation_graph=SimpleNamespace(
                        get_all_labels=lambda: []))
                async def start(self):
                    return None
            role = SimpleNamespace(config=SimpleNamespace(client=SimpleNamespace(api_key='k', base_url='u')))
            replacements = {
                'knowledge.lightrag.retrieval.LightRagBackend': MagicMock(return_value=backend),
                'knowledge.lightrag.roles.resolve_query_roles': MagicMock(return_value={'query': role}),
                'knowledge.lightrag.roles.query_binding': MagicMock(return_value={}),
                'knowledge.lightrag.pipeline.embedding_config': embedding_config,
                'knowledge.lightrag.course_input.visual_inventory': MagicMock(return_value=([], [], {})),
                'knowledge.lightrag.course_input.inventory': MagicMock(return_value={'a': 'b'}),
                'knowledge.course_release.validate': MagicMock(return_value={'release_id': 'r', 'status': 's',
                    'ready': True, 'gaps': []}),
                'knowledge.course_navigation.outline': MagicMock(return_value=[]),
                'knowledge.source_visuals.load_visuals': MagicMock(return_value=([], [])),
                'knowledge.grounded_citations.settings': MagicMock(return_value=None),
                'knowledge.fixed_book.ResidentGraph': Graph,
                'knowledge.lightrag.storage.require_compatible_embedding': MagicMock(),
                'knowledge.lightrag.worker.run_in_worker_loop': worker,
                'knowledge.local_rag.course_retrieval.warm': MagicMock(),
                'knowledge.hybrid_retrieval._reranker_on_device': MagicMock(),
                'knowledge.local_rag.course_retrieval.retrieve': MagicMock(),
                'llm.transport.borrow': MagicMock(return_value=nullcontext(None)),
                'knowledge.figures.load_figures': MagicMock(return_value=[]),
                'knowledge.textbook.terms_for': MagicMock(return_value=set()),
            }
            with ExitStack() as stack:
                stack.enter_context(patch.dict(os.environ, STARTUP_ID='startup-start', STARTUP_SERVICE='host',
                    STARTUP_TRACE_DIR=folder, LIGHTRAG_CANDIDATE_PATH=str(root),
                    FIXED_BOOK_RETRIEVAL_ENABLED='1'))
                for target, value in replacements.items():
                    stack.enter_context(patch(target, new=value))
                asyncio.run(fixed_book.start())
            recorded = rows(folder)
            self.assertEqual(recorded['fixed_book.entry']['parent'], 'fixed_book')
            self.assertEqual(recorded['fixed_book.ready_flag']['parent'], 'fixed_book')
            self.assertEqual(recorded['fixed_book.start.complete']['status'], 'ok')
            self.assertGreaterEqual(recorded['fixed_book.start.complete']['seconds'],
                                    recorded['fixed_book.ready_flag']['seconds'])
            self.assertEqual(recorded['fixed_book.hashes']['fields']['files'], 1)
            self.assertIsNotNone(fixed_book.runtime)

    def test_early_failure_keeps_only_traversed_stages(self):
        with TemporaryDirectory() as folder:
            with (patch.dict(os.environ, STARTUP_ID='startup-fail', STARTUP_SERVICE='host',
                             STARTUP_TRACE_DIR=folder, LIGHTRAG_CANDIDATE_PATH='x',
                             FIXED_BOOK_RETRIEVAL_ENABLED='1'),
                  patch('knowledge.lightrag.retrieval.LightRagBackend', side_effect=RuntimeError('fixture'))):
                with self.assertRaisesRegex(RuntimeError, 'fixture'):
                    asyncio.run(fixed_book.start())
            recorded = rows(folder)
            self.assertEqual(recorded['fixed_book.entry']['status'], 'ok')
            self.assertEqual(recorded['fixed_book.start.failed']['status'], 'failed')
            self.assertEqual(recorded['fixed_book.start.failed']['fields']['error'], 'RuntimeError')
            self.assertNotIn('fixed_book.start.complete', recorded)
            self.assertIsNone(fixed_book.runtime)


if __name__ == '__main__':
    unittest.main()
