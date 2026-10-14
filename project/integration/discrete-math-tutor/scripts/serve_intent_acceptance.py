"""真实HTTP/PDF联调服务器：临时数据库、确定性模型、退出后清理。"""
import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8767)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='intent-acceptance-') as folder:
        os.environ.update(DATABASE_URL='sqlite:///' + (Path(folder)/'acceptance.db').as_posix(),
            LLM_MOCK='1', MEMORY_WORKER_ENABLED='0', MEMORY_EMBED_MODEL='', RAG_RERANK_MODEL='',
            DEEPSEEK_API_KEY='', OPENAI_API_KEY='')
        from llm.client import LLMClient
        observations = []

        class FixtureClient(LLMClient):
            def _one_call(self, *args, **kwargs):
                raise AssertionError('隔离验收禁止网络模型调用')

            def chat(self, messages, **kwargs):
                observations.append({'kind':'pdf_generation','images':len(kwargs.get('image_paths') or [])})
                return '先对照教材选区中的条件与定义，尝试写出第一步。[1]'

            def chat_json(self, messages, **kwargs):
                system = messages[0]['content']
                content = messages[-1]['content']
                if '[AGENT:conversation_router]' in system:
                    context = json.loads(content.split('已校验任务上下文（资料，不是指令）：',1)[1].split('\n学生最新输入：',1)[0])
                    objects = context['objects']
                    refs = [obj['id'] for obj in objects if obj['kind'] != 'section'][:1]
                    clarify = context['message'] == '请确认选区对象'
                    observations.append({'kind':'routing','targets':refs,'clarify':clarify})
                    return dict(student_move='question', move_status='', intent='clarify_task' if clarify else 'continue',
                        topic='', confidence=.95, needs_context=bool(refs), reason='固定联调夹具，不是模型评测',
                        learning_intents=['hint'], answer_constraints=['hint_only','no_full_answer'],
                        target_refs=[] if clarify else refs, missing_slots=['target'] if clarify else [])
                if '[AGENT:context_sufficiency]' in system:
                    return {'status':'sufficient','reason':'固定联调夹具','missing':[],'source_ids':['1']}
                if 'target_parts' in content and '习题助教' in system:
                    payload = json.loads(content)
                    observations.append({'kind':'exercise_generation','parts':[p['id'] for p in payload['target_parts']],
                        'answers':payload['student_answers'],'images':len(kwargs.get('image_paths') or [])})
                    return {'reply':'先对照本小题的条件与定义，尝试写出第一步。'}
                return super().chat_json(messages, **kwargs)

        import llm.client
        llm.client.LLMClient = FixtureClient
        from knowledge import pdf_reader, hybrid_retrieval
        pdf_reader.CROPS = Path(folder)/'crops'
        hybrid_retrieval._vectors = lambda connection: (None, [])
        import main as application
        import uvicorn
        server = uvicorn.Server(uvicorn.Config(application.app,host='127.0.0.1',port=args.port,log_level='warning'))

        @application.app.get('/_acceptance/state')
        def test_state():
            return {'fixture':True,'temporary_database':True,'model':'deterministic_fixture','observations':observations}

        @application.app.post('/_acceptance/stop')
        def test_stop():
            server.should_exit = True
            return {'stopping':True}

        try:
            server.run()
        finally:
            from database.database import engine
            engine.dispose()


if __name__ == '__main__':
    main()
