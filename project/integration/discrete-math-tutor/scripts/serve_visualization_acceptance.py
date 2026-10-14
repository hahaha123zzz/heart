"""图组件真实 HTTP 验收：临时 SQLite，不初始化模型或真实 main。"""
import json
import os
import socket
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    with tempfile.TemporaryDirectory(prefix='visualization-acceptance-') as folder:
        os.environ.update(DATABASE_URL='sqlite:///'+(Path(folder)/'test.db').as_posix(),
            VISUALIZATION_ROLLOUT='test', LLM_MOCK='1', DEEPSEEK_API_KEY='', OPENAI_API_KEY='')
        from fastapi import FastAPI
        from fastapi.responses import HTMLResponse
        from fastapi.staticfiles import StaticFiles
        from database.database import init_db, engine
        from memory.memory_manager import MemoryManager
        from visualization_api import router
        from truth_table_api import router as table_router
        from relation_api import router as relation_router
        from web_api import conversation_history
        import uvicorn
        import re

        init_db()
        memory=MemoryManager()
        # 只满足历史接口的延迟导入，不运行教学编排或加载模型。
        sys.modules['main']=SimpleNamespace(orchestrator=SimpleNamespace(memory=memory))
        app=FastAPI();app.include_router(router);app.include_router(table_router);app.include_router(relation_router)
        app.mount('/static',StaticFiles(directory=ROOT/'frontend'))

        @app.get('/')
        def home():
            html=(ROOT/'frontend/index.html').read_text(encoding='utf-8')
            return HTMLResponse(re.sub(r'<script[^>]*(?:mathlive|type="module")[^>]*></script>', '', html))

        app.get('/api/students/{student_id}/conversation')(conversation_history)

        @app.get('/__test__/guide')
        def guide():
            from knowledge.proof_units import units_for
            from knowledge.textbook import TextbookChunk
            from visualization.textbook_guides import build_textbook_guide
            unit=units_for(9)['例9.8']
            source=TextbookChunk(unit.record['source'],unit.section['title'],unit.text,frozenset(),chapter_id=9,section_id=5)
            return build_textbook_guide('讲解例9.8 R2的传递闭包','',[source],SimpleNamespace(hint_only=False,learning_intents=['explain']),turn_id='browser-guide')

        @app.post('/__test__/forget')
        def forget(student_id: str):
            from visualization.service import POINT
            return memory.repo.forget_learning_point(student_id,POINT)

        @app.post('/__test__/shutdown')
        def shutdown():
            server.should_exit=True
            return {'ok':True}

        sock=socket.socket();sock.bind(('127.0.0.1',0));sock.listen()
        server=uvicorn.Server(uvicorn.Config(app,log_level='error'))
        print(json.dumps({'url':'http://127.0.0.1:'+str(sock.getsockname()[1])}),flush=True)
        try:server.run(sockets=[sock])
        finally:sock.close();engine.dispose()


if __name__=='__main__':main()
