"""浏览器交付验收；--live 使用宿主配置的真实模型，否则为本机受控模型。"""
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import time
from http.server import ThreadingHTTPServer

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.check_native_chat_chain import Model,port,post


def main():
    live = '--live' in sys.argv
    reader_only = '--reader-only' in sys.argv
    memory_only = '--memory-only' in sys.argv
    if live:
        from dotenv import load_dotenv
        load_dotenv(ROOT/'.env')
        load_dotenv(ROOT/'deepseek.env')
        if not (os.getenv('DEEPSEEK_API_KEY') or os.getenv('OPENAI_API_KEY')):
            raise RuntimeError('未配置真实模型密钥')
    run=ROOT/('.runtime/native-delivery-live' if live else '.runtime/native-delivery-browser')/time.strftime('%Y%m%d-%H%M%S');run.mkdir(parents=True)
    model=None
    if not live:
        model=ThreadingHTTPServer(('127.0.0.1',0),Model);threading.Thread(target=model.serve_forever,daemon=True).start()
    hostport,workerport=port(),port();base=f'http://127.0.0.1:{hostport}'
    env=dict(os.environ,DEEPTUTOR_NATIVE_ENABLED='1',DEEPTUTOR_AUTOSTART='1',DEEPTUTOR_HOME=str(run/'home'),
        DEEPTUTOR_BACKEND_URL=f'http://127.0.0.1:{workerport}',DEEPTUTOR_HOST_URL=base,DEEPTUTOR_BRIDGE_TOKEN=secrets.token_hex(32),
        DATABASE_URL='sqlite:///'+str(run/'host.db'),COURSE_DATABASE_URL='sqlite:///'+str(run/'course.db'),
        LLM_MOCK='0' if live else '1',MEMORY_WORKER_ENABLED='0',
        CLEANUP_EXPIRED_ON_STARTUP='0',PYTHONUTF8='1',NATIVE_DELIVERY_LIVE='1' if live else '0',NATIVE_DELIVERY_READER_ONLY='1' if reader_only else '0')
    if not live:
        env.update(DEEPSEEK_MODEL='fixture-model',OPENAI_MODEL='fixture-model',DEEPSEEK_API_KEY='fixture-key',OPENAI_API_KEY='fixture-key',
            OPENAI_BASE_URL=f'http://127.0.0.1:{model.server_port}/v1',FIXED_BOOK_RETRIEVAL_ENABLED='0',RAG_RETRIEVAL_ENGINE='legacy')
    if memory_only:
        env['FIXED_BOOK_RETRIEVAL_ENABLED']='0'
    process=None
    try:
        with (run/'host.log').open('wb') as log:
            process=subprocess.Popen([sys.executable,'-X','utf8','-B','-m','uvicorn','main:app',
                '--host','127.0.0.1','--port',str(hostport)],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            deadline=time.monotonic()+300
            while True:
                try:post(base,'/api/accounts/test',{'student_id':'browser-delivery','ttl_hours':1});break
                except OSError:
                    if process.poll() is not None or time.monotonic()>deadline:raise RuntimeError('隔离宿主未就绪')
                    time.sleep(.2)
            if live and not reader_only and not memory_only:
                import json
                from urllib.request import Request
                from scripts.check_native_chat_chain import OPENER
                request=dict(student_id='browser-delivery',session_id='live-rag',request_id='real-rag',
                    message='请调用 rag 检索教材中自变量的定义，再调用 read_source 阅读其中一个来源。用一小段话说明自变量是什么，必须引用工具返回的原文，并按工具给的编号标注 [1] 等引用。不要使用网络。',
                    tools=['rag','read_source'])
                result=post(base,'/api/chat',request)
                (run/'rag.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
                assert result.get('answer_status')=='answered',result
                assert result.get('pdf_references') and result.get('textbook_sources'),'真实模型未交付正式教材引用'
                usage=result.get('native_result',{}).get('metadata',{}).get('usage_summary',{})
                assert usage.get('total_calls',0)>0 and all(c.get('model')!='fixture-model' for c in usage.get('call_details',[])),usage
                with OPENER.open(Request(base+'/api/students/browser-delivery/conversation?session_id=live-rag'),timeout=30) as response:
                    history=json.load(response)
                (run/'rag-history.json').write_text(json.dumps(history,ensure_ascii=False,indent=2),encoding='utf8')
                assert any(row.get('role')=='assistant' and row.get('pdf_references') for row in history),'历史引用丢失'
                print('real_rag_and_history_passed',flush=True)
            subprocess.run(['node',str(ROOT/('scripts/check_native_memory_browser.cjs' if memory_only else 'scripts/check_native_delivery_browser.cjs')),base,str(run)],cwd=ROOT,env=env,check=True)
    finally:
        if process and process.poll() is None:
            if os.name=='nt':subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            else:process.terminate()
            process.wait(timeout=20)
        if model:
            model.shutdown();model.server_close()
        print('browser_report',run/('memory-browser.json' if memory_only else 'browser.json'))

if __name__=='__main__':main()
