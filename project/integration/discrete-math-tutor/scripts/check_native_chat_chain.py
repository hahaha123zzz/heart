"""隔离 HTTP 验收：真实宿主、原生 worker、AgentLoop 和工具；模型为本机受控 OpenAI 服务。"""
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, build_opener, ProxyHandler

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
OPENER=build_opener(ProxyHandler({}))
CALLS=[]

def port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));return sock.getsockname()[1]

def post(base,path,data):
    with OPENER.open(Request(base+path,data=json.dumps(data,ensure_ascii=False).encode(),
        headers={'Content-Type':'application/json'}),timeout=300) as response:return json.load(response)

class Model(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_POST(self):
        payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        messages=payload.get('messages') or []; tools=payload.get('tools') or []
        names=[item.get('function',{}).get('name') for item in tools]
        last_user=max((i for i,item in enumerate(messages) if item['role']=='user'),default=-1)
        # 只看本轮用户消息；历史里保留的 CHAIN_* 标记不能再次触发工具。
        current=str(messages[last_user].get('content','')) if last_user>=0 else ''
        used=any(item['role']=='tool' for item in messages[last_user+1:])
        tool_rows=[item for item in messages[last_user+1:] if item.get('role')=='tool']
        call=None
        if 'CHAIN_ASK' in current and not used and 'ask_user' in names:
            call={'id':'call-ask','type':'function','function':{'name':'ask_user','arguments':json.dumps({'questions':[{
                'id':'goal','question':'选择学习目标','options':[{'label':'基础','description':'先看基础概念'},
                {'label':'进阶','description':'分析复杂案例'}]}]},ensure_ascii=False)}}
        elif 'CHAIN_TOOL' in current and not used and 'workspace_list' in names:
            call={'id':'call-list','type':'function','function':{'name':'workspace_list','arguments':'{}'}}
        elif 'CHAIN_NOTE' in current and not used and 'list_notebook' in names:
            call={'id':'call-note','type':'function','function':{'name':'list_notebook','arguments':'{}'}}
        elif 'CHAIN_STATUS' in current and not used and 'learning_status' in names:
            call={'id':'call-status','type':'function','function':{'name':'learning_status','arguments':'{}'}}
        elif 'CHAIN_REASON' in current and not used and 'reason' in names:
            call={'id':'call-reason','type':'function','function':{'name':'reason','arguments':json.dumps({
                'query':'为什么 2+2 等于 4'},ensure_ascii=False)}}
        elif 'CHAIN_READMEM' in current and not used and 'read_memory' in names:
            call={'id':'call-readmem','type':'function','function':{'name':'read_memory','arguments':'{}'}}
        elif 'CHAIN_GOTO' in current and not used and 'reader_goto' in names:
            call={'id':'call-goto','type':'function','function':{'name':'reader_goto','arguments':'{"locator":2}'}}
        elif 'CHAIN_READ' in current and not used and 'material_outline' in names:
            call={'id':'call-outline','type':'function','function':{'name':'material_outline','arguments':'{}'}}
        elif 'CHAIN_MEMORY' in current and not used and 'write_memory' in names:
            call={'id':'call-mem','type':'function','function':{'name':'write_memory','arguments':json.dumps({
                'op':'add','text':'回答时先给结论，再给解释'},ensure_ascii=False)}}
        elif 'CHAIN_BRAINSTORM' in current and not used and 'brainstorm' in names:
            call={'id':'call-brain','type':'function','function':{'name':'brainstorm','arguments':json.dumps({
                'topic':'实验心理学的研究方法'},ensure_ascii=False)}}
        elif 'CHAIN_JOURNAL' in current and not used and 'learning_update' in names:
            call={'id':'call-journal','type':'function','function':{'name':'learning_update','arguments':json.dumps({
                'op':'add_record','insight':'先给结论再解释，更容易记住','title':'学习偏好'},ensure_ascii=False)}}
        elif 'CHAIN_FILES' in current and not used and 'kb_files' in names:
            call={'id':'call-files','type':'function','function':{'name':'kb_files','arguments':'{}'}}
        elif 'CHAIN_SKILL' in current and not used and 'read_skill' in names:
            call={'id':'call-skill','type':'function','function':{'name':'read_skill','arguments':json.dumps({
                'name':'pdf'},ensure_ascii=False)}}
        elif 'CHAIN_SOLVE' in current and not used and 'solve_plan' in names:
            call={'id':'call-solve','type':'function','function':{'name':'solve_plan','arguments':json.dumps({
                'analysis':'这是一步即可完成的算术题。','steps':[{'goal':'算出 2+2'}]},ensure_ascii=False)}}
        elif 'CHAIN_COURSE' in current and not used and 'course_overview' in names:
            call={'id':'call-course','type':'function','function':{'name':'course_overview','arguments':'{}'}}
        elif ('CHAIN_RAG' in current or 'CHAIN_SOURCE' in current) and not used and 'rag' in names:
            call={'id':'call-rag','type':'function','function':{'name':'rag','arguments':json.dumps({
                'query':'自变量和因变量的区别','kb_name':'实验心理学'},ensure_ascii=False)}}
        elif 'CHAIN_SOURCE' in current and len(tool_rows)==1 and 'read_source' in names:
            import re
            match=re.search(r'source_id=(rag-[a-f0-9]+)',str(tool_rows[-1].get('content') or ''))
            assert match,'rag did not supply source_id'
            call={'id':'call-source','type':'function','function':{'name':'read_source','arguments':json.dumps({'source_id':match[1]})}}
        text='本机受控模型已完成本轮回答。'
        system=' '.join(str(item.get('content') or '') for item in messages if item['role']=='system')
        label=chr(96)*2
        if '出题规划器' in system:
            text=label+'PLAN'+label+'\n'+json.dumps({'analysis':'区分实验变量','templates':[{
                'question_id':'q_1','topic':'自变量和因变量','question_type':'choice','difficulty':'easy'}]},ensure_ascii=False)
        elif '你正在写**一道**测验题' in system:
            text=label+'FINISH'+label+'\n'+json.dumps({'question':'实验中由研究者主动操纵的量是什么？','question_type':'choice',
                'options':{'A':'因变量','B':'自变量','C':'无关变量','D':'误差'},'correct_answer':'B',
                'explanation':'私有解析：研究者主动操纵的是自变量。'},ensure_ascii=False)
        elif '出题流程中的「探索代理」' in system:
            text=label+'FINISH'+label+'\n现在生成一道区分实验变量的练习题。'

        CALLS.append({'tools':names,'tool_call':call['function']['name'] if call else None,'saw_tool_result':used,
            'tool_chars':sum(len(str(item.get('content') or '')) for item in tool_rows),
            'tool_head':str((tool_rows[-1].get('content') if tool_rows else '') or '')[:160]})
        if payload.get('stream'):
            self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
            delta={'tool_calls':[{'index':0,**call}]} if call else {'content':text}
            chunk={'id':'fixture','object':'chat.completion.chunk','created':int(time.time()),'model':payload.get('model'),
                'choices':[{'index':0,'delta':delta,'finish_reason':None}]}
            finish={**chunk,'choices':[{'index':0,'delta':{},'finish_reason':'tool_calls' if call else 'stop'}]}
            self.wfile.write(('data: '+json.dumps(chunk,ensure_ascii=False)+'\n\ndata: '+json.dumps(finish)+
                              '\n\ndata: [DONE]\n\n').encode());self.wfile.flush()
        else:
            message={'role':'assistant','content':None if call else text}
            if call:message['tool_calls']=[call]
            result={'id':'fixture','object':'chat.completion','created':int(time.time()),'model':payload.get('model'),
                'choices':[{'index':0,'message':message,'finish_reason':'tool_calls' if call else 'stop'}],
                'usage':{'prompt_tokens':10,'completion_tokens':10,'total_tokens':20}}
            raw=json.dumps(result,ensure_ascii=False).encode();self.send_response(200)
            self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)

def main():
    run=ROOT/'.runtime/native-chat-chain'/time.strftime('%Y%m%d-%H%M%S')
    run.mkdir(parents=True)
    model=ThreadingHTTPServer(('127.0.0.1',0),Model)
    threading.Thread(target=model.serve_forever,daemon=True).start()
    hostport,workerport=port(),port();base=f'http://127.0.0.1:{hostport}'
    env=dict(os.environ,DEEPTUTOR_NATIVE_ENABLED='1',DEEPTUTOR_AUTOSTART='1',
        DEEPTUTOR_HOME=str(run/'home'),DEEPTUTOR_BACKEND_URL=f'http://127.0.0.1:{workerport}',
        DEEPTUTOR_HOST_URL=base,DEEPTUTOR_BRIDGE_TOKEN=secrets.token_hex(32),
        DATABASE_URL='sqlite:///'+str(run/'host.db'),COURSE_DATABASE_URL='sqlite:///'+str(run/'psych.db'),
        DEEPSEEK_MODEL='fixture-model',OPENAI_MODEL='fixture-model',DEEPSEEK_API_KEY='fixture-key',OPENAI_API_KEY='fixture-key',
        OPENAI_BASE_URL=f'http://127.0.0.1:{model.server_port}/v1',LLM_MOCK='1',
        MEMORY_WORKER_ENABLED='0',FIXED_BOOK_RETRIEVAL_ENABLED='0',CLEANUP_EXPIRED_ON_STARTUP='0',
        RAG_RETRIEVAL_ENGINE='legacy',PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1')
    report={'scope':'本机受控模型，非外部服务或回答质量验收','checks':[]}
    process=None
    try:
        with (run/'host.log').open('wb') as log:
            process=subprocess.Popen([str(ROOT/'.venv-gpu/Scripts/python.exe'),'-X','utf8','-B','-m','uvicorn',
                'main:app','--host','127.0.0.1','--port',str(hostport)],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            deadline=time.monotonic()+85
            while True:
                try:
                    post(base,'/api/accounts/test',{'student_id':'chain-student','ttl_hours':1});break
                except OSError:
                    if process.poll() is not None or time.monotonic()>deadline:raise RuntimeError('宿主启动失败，请查看隔离日志')
                    time.sleep(.2)
            try:
                catalog=post(base,'/api/deeptutor/catalog',{'student_id':'chain-student','session_id':'chain'})
            except OSError:
                request=Request(env['DEEPTUTOR_BACKEND_URL']+'/internal/heart/native/catalog',
                    data=json.dumps({'student_id':'chain-student','session_id':'chain','course_id':'experimental-psychology-3','course_title':'实验心理学'}).encode(),
                    headers={'Content-Type':'application/json','X-Heart-Bridge-Token':env['DEEPTUTOR_BRIDGE_TOKEN']})
                try:
                    with OPENER.open(request,timeout=120) as response:report['catalog_diagnostic']=json.load(response)
                except OSError as exc:
                    report['catalog_diagnostic']={'type':type(exc).__name__,'detail':exc.read(2000).decode() if hasattr(exc,'read') else str(exc)}
                raise
            assert len(catalog['tools'])==69 and len(catalog['extensions'])==8
            assert catalog['hidden_tool_count']==31
            assert len(catalog['capabilities'])==11
            report['checks'].append('native_catalog_69_visible_tools_31_hidden_8_extensions_11_capabilities')
            def chat(message,rid,**kwargs):return post(base,'/api/chat',dict(student_id='chain-student',
                session_id='chain',request_id=rid,message=message,**kwargs))
            first=chat('CHAIN_TOOL：请查看当前工作区','tool-request')
            report['tool_result']=first
            assert first['answer_status']=='answered',first
            assert any(c['tool_call']=='workspace_list' for c in CALLS),CALLS
            assert any(c['saw_tool_result'] for c in CALLS),CALLS
            report['checks'].append('host_to_native_agentloop_workspace_list_to_saved_reply')
            count=len(CALLS);assert chat('CHAIN_TOOL：请查看当前工作区','tool-request')==first
            assert len(CALLS)==count
            report['checks'].append('request_replay_no_second_model_call')
            note=chat('CHAIN_STATUS：看看我的学习记录','status-request')
            report['status_result']=note
            assert note['answer_status']=='answered',note
            assert any(c['tool_call']=='learning_status' for c in CALLS),CALLS
            report['checks'].append('auto_mounted_tool_learning_status_executed')
            reasoned=chat('CHAIN_REASON：帮我推理一下','reason-request',tools=['reason'])
            report['reason_result']=reasoned
            assert reasoned['answer_status']=='answered',reasoned
            assert any('reason' in c['tools'] and c['tool_call']=='reason' for c in CALLS),CALLS
            report['checks'].append('user_selected_tool_reason_executed')
            solve=chat('请说出 2+2 的解题思路','solve-request',capability='deep_solve')
            report['solve_result']=solve
            assert solve['answer_status']=='answered',solve
            assert solve.get('capability')=='deep_solve',solve
            report['checks'].append('capability_deep_solve_routed_and_answered')
            reading=chat('CHAIN_READ：带我读教材这一章','reading-request',capability='immersive_reading')
            report['reading_result']=reading
            assert reading['answer_status']=='answered',reading
            assert any(c['tool_call']=='material_outline' for c in CALLS),CALLS
            report['checks'].append('capability_immersive_reading_with_course_material')
            memory=chat('CHAIN_MEMORY：请记住我的偏好','memory-request')
            report['memory_result']=memory
            assert memory['answer_status']=='answered',memory
            assert any(c['tool_call']=='write_memory' for c in CALLS),CALLS
            report['checks'].append('tool_write_memory_executed')
            recall=chat('CHAIN_READMEM：我的偏好是什么','readmem-request')
            report['readmem_result']=recall
            assert recall['answer_status']=='answered',recall
            assert any(c['tool_call']=='read_memory' for c in CALLS),CALLS
            report['checks'].append('tool_read_memory_executed')
            brain=chat('CHAIN_BRAINSTORM：帮我想想怎么学','brainstorm-request',tools=['brainstorm'])
            report['brainstorm_result']=brain
            assert brain['answer_status']=='answered',brain
            assert any(c['tool_call']=='brainstorm' for c in CALLS),CALLS
            report['checks'].append('tool_brainstorm_executed')
            journal=chat('CHAIN_JOURNAL：记下这个学习心得','journal-request')
            report['journal_result']=journal
            assert journal['answer_status']=='answered',journal
            assert any(c['tool_call']=='learning_update' for c in CALLS),CALLS
            report['checks'].append('tool_learning_update_executed')
            planned=chat('CHAIN_SOLVE：规划一下这道题','solve-plan-request',capability='deep_solve')
            report['solve_plan_result']=planned
            assert planned['answer_status']=='answered',planned
            assert any(c['tool_call']=='solve_plan' for c in CALLS),CALLS
            report['checks'].append('tool_solve_plan_executed')
            course=chat('CHAIN_COURSE：看看我的课程结构','course-request',capability='course_study')
            report['course_result']=course
            assert course['answer_status']=='answered',course
            assert any(c['tool_call']=='course_overview' for c in CALLS),CALLS
            report['checks'].append('capability_course_study_with_syllabus')
            rag_started=time.monotonic()
            rag=chat('CHAIN_RAG：教材里自变量和因变量怎么区分','rag-request',
                     knowledge_bases=['实验心理学'])
            report['rag_seconds']=round(time.monotonic()-rag_started,2)
            report['rag_result']=rag
            assert rag['answer_status']=='answered',rag
            assert any(c['tool_call']=='rag' for c in CALLS),CALLS
            assert any('教材检索结果' in c.get('tool_head','') and c.get('tool_chars',0)>200
                       for c in CALLS),CALLS
            report['checks'].append('tool_rag_reads_host_course_index')
            before_source=len(CALLS)
            source=chat('CHAIN_SOURCE：补读检索结果的完整原文','read-source-request',knowledge_bases=['实验心理学'])
            report['source_result']=source
            assert source['answer_status']=='answered',source
            assert any(c['tool_call']=='read_source' for c in CALLS[before_source:]),CALLS[before_source:]
            assert len(CALLS[before_source:])>=3,CALLS[before_source:]
            assert CALLS[-1]['tool_chars']>100 and not CALLS[-1]['tool_head'].startswith('Error:'),CALLS[before_source:]
            report['checks'].append('rag_source_index_read_source_same_turn')
            files=chat('CHAIN_FILES：教材有哪些章节','files-request',knowledge_bases=['实验心理学'])
            report['files_result']=files
            assert files['answer_status']=='answered',files
            assert any(c['tool_call']=='kb_files' for c in CALLS),CALLS
            report['checks'].append('tool_kb_files_lists_course_chapters')
            before=len(CALLS)
            skill=chat('CHAIN_SKILL：读一下 pdf 技能','skill-request')
            report['skill_result']=skill
            assert skill['answer_status']=='answered',skill
            assert any(c['tool_call']=='read_skill' for c in CALLS[before:]),CALLS[before:]
            assert any(c.get('tool_chars',0)>400 for c in CALLS[before:]),CALLS[before:]
            report['checks'].append('tool_read_skill_executed')
            quiz=chat('CHAIN_QUIZ：生成一道变量辨析选择题','quiz-delivery-request',capability='deep_question',
                config={'num_questions':1,'topic':'自变量和因变量','question_types':['choice']})
            report['quiz_result']=quiz
            assert quiz['answer_status']=='answered',quiz
            qa=quiz['native_result']['summary']['results'][0]['qa_pair']
            assert qa['question'] and len(qa['options'])==4,quiz
            assert 'correct_answer' not in qa and 'explanation' not in qa,quiz
            assert '私有解析' not in json.dumps(quiz,ensure_ascii=False),quiz
            report['checks'].append('native_question_pipeline_public_questions_without_answer_keys')
            goto=chat('CHAIN_GOTO：定位教材第二页','reader-goto-request',capability='immersive_reading',
                reading_viewport={'chapter_id':2})
            report['reader_goto_result']=goto
            assert goto['answer_status']=='answered' and goto.get('reader_actions'),goto
            assert goto['reader_actions'][0]['page']==2 and goto['reader_actions'][0]['chapter_id']==2,goto
            assert goto['reader_actions'][0]['status']=='requested',goto
            report['checks'].append('native_reader_goto_projected_to_host_saved_action')
            count=len(CALLS)
            again=chat('CHAIN_GOTO：定位教材第二页','reader-goto-request',capability='immersive_reading',
                reading_viewport={'chapter_id':2})
            assert again.get('reader_action_replay') is True and len(CALLS)==count,again
            report['checks'].append('reader_action_replay_does_not_move_again')
            question=chat('CHAIN_ASK：请先让我选择学习目标','ask-request')
            report['question']=question
            assert question['answer_status']=='awaiting_clarification',question
            answer=chat('基础','reply-request',task_id=question['task_id'],task_revision=question['task_revision'],
                selected_option=question['clarification']['options'][0]['id'])
            report['answer']=answer
            assert answer['answer_status']=='answered',answer
            assert answer['native_turn_id']==question['native_turn_id']
            report['checks'].append('native_ask_user_wait_and_same_turn_resume')
            from integrations.deeptutor.tool_policy import HIDDEN_TOOLS
            assert not any(set(call['tools']) & HIDDEN_TOOLS for call in CALLS)
            report['checks'].append('hidden_tools_absent_from_all_model_schemas')
            report['passed']=True
    finally:
        if process and process.poll() is None:
            if os.name=='nt':
                subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            else:process.terminate()
            try:process.wait(timeout=20)
            except subprocess.TimeoutExpired:process.kill();process.wait()
        model.shutdown();model.server_close()
        report['calls']=CALLS
        (run/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'report':str(run/'report.json'),'passed':report.get('passed',False),'checks':report['checks']},ensure_ascii=False))

if __name__=='__main__':main()
