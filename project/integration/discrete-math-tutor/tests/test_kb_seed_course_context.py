import asyncio
from types import SimpleNamespace

from deeptutor.agents.loop.pipeline import AgenticLoopPipeline


class Stream:
    async def sources(self, *args, **kwargs):
        pass


def _context(message='自变量是什么', skip=False):
    return SimpleNamespace(user_message=message, metadata={'heart_skip_kb_seed': skip})


def _pipeline(heart_tool=True):
    tool = SimpleNamespace()
    if heart_tool:
        tool._heart_course_rag = True
    seen = {}

    async def execute(name, args, **kwargs):
        seen.update(args)
        return {'success': True, 'result_text': '教材原文 [1]', 'sources': [{'index': 1}], 'metadata': {}}

    pipeline = SimpleNamespace(event_source='chat', event_stage='exploring',
                               tool_lookup={'rag': tool}, _execute_tool_call=execute,
                               _t=lambda key, default=None: default or key)
    return pipeline, seen


def test_heart_tool_receives_turn_context():
    pipeline, seen = _pipeline()
    context = _context()
    text, sources = asyncio.run(AgenticLoopPipeline._seed_search_one_kb(
        pipeline, 'kb', '自变量是什么', Stream(), context))
    assert seen['_heart_context'] is context
    assert text == '教材原文 [1]'
    assert sources == [{'index': 1}]


def test_other_rag_tool_gets_no_private_context():
    pipeline, seen = _pipeline(heart_tool=False)
    asyncio.run(AgenticLoopPipeline._seed_search_one_kb(pipeline, 'kb', 'q', Stream(), _context()))
    assert '_heart_context' not in seen


def test_skip_flag_returns_empty_without_search():
    class Pipeline:
        event_source = 'chat'
        event_stage = 'exploring'

        @staticmethod
        def _coexisting_rag_kbs(context):
            return ['kb']

        @staticmethod
        def _capability_skips_kb_seed(context):
            return False

        async def _seed_search_one_kb(self, *args):
            raise AssertionError('skip flag must prevent retrieval')

    assert asyncio.run(AgenticLoopPipeline._retrieve_kb_seed_block(
        Pipeline(), _context(skip=True), Stream())) == ''
