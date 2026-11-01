"""Isolated HTTP/model acceptance; key stays in process memory, snapshots are not modified."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def configure(key_file,output,model):
    from dotenv import dotenv_values
    values=dotenv_values(key_file)
    raw=key_file.read_text(encoding='utf-8-sig').strip().strip('\"\'')
    key=values.get('DEEPSEEK_API_KEY') or values.get('OPENAI_API_KEY')
    if not key:
        key=raw if raw.startswith('sk-') and not any(c.isspace() for c in raw) else next(
            (v.strip().strip('\"\'') for v in values.values() if isinstance(v,str) and v.strip().strip('\"\'').startswith('sk-')),None)
    if not key: raise ValueError('API key format unsupported; no values printed')
    os.environ.update(DEEPSEEK_API_KEY=key,OPENAI_BASE_URL='https://api.deepseek.com',OPENAI_MODEL=model,
        DEEPSEEK_MODEL=model,OPENAI_VISION_MODEL=model,LLM_MOCK='0',TUTOR_COURSE='experimental-psychology-3',
        DATABASE_URL='sqlite:///'+str(output/'unused-legacy.db'),COURSE_DATABASE_URL='sqlite:///'+str(output/'live.db'),
        MEMORY_WORKER_ENABLED='0',CLEANUP_EXPIRED_ON_STARTUP='0',LOCAL_AGENT_LOOP_ENABLED='1',
        ADAPTIVE_TUTORING_ENABLED='1',SELECTED_TEXT_AGENT_LOOP_ENABLED='1',INPUT_UNDERSTANDING_MODE='active',
        INPUT_UNDERSTANDING_SEMANTIC_ENABLED='0',LABELS_POLICY='1',LABELS_STRUCTURE='1',LABELS_TURN='1',
        Q5_LEARNING_ENABLED='0',FIXED_BOOK_RETRIEVAL_ENABLED='0',Q3_RETRIEVAL_MODE='stub',
        DEEPTUTOR_NATIVE_ENABLED='0',VISUALIZATION_ON_DEMAND='off',NO_PROXY='*')
    for name in ('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy'):
        os.environ.pop(name,None)


def selection():
    import fitz
    from knowledge.pdf_reader import document_for_chapter,pdf_path
    record=document_for_chapter(2)
    candidates=[]
    with fitz.open(pdf_path(record)) as doc:
        for page in doc:
            for b in page.get_text('blocks'):
                text=b[4]
                if '自变量' in text and '因变量' in text and 40<len(text)<2000:
                    candidates.append((len(text),page.number,dict(page=page.number+1,
                        x1=max(0,b[0]-1)/page.rect.width,y1=max(0,b[1]-1)/page.rect.height,
                        x2=min(page.rect.width,b[2]+1)/page.rect.width,y2=min(page.rect.height,b[3]+1)/page.rect.height)))
    assert candidates,'No verified variable passage in chapter 2'
    _,_,rect=min(candidates)
    return {'document_id':record['document_id'],'version':record['version'],'kind':'text','rects':[rect],'text':'服务端应忽略此预览，读取实际PDF'}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--key-file',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--model',default='deepseek-flash')
    parser.add_argument('--run-id',default='initial')
    parser.add_argument('--phase',choices=('prepare','practice','resume','legacy'),required=True)
    args=parser.parse_args(); args.output=args.output.resolve();args.output.mkdir(parents=True,exist_ok=True)
    configure(args.key_file,args.output,args.model)
    if args.phase=='legacy':
        os.environ.update(LOCAL_AGENT_LOOP_ENABLED='0',SELECTED_TEXT_AGENT_LOOP_ENABLED='0')
    from fastapi.testclient import TestClient
    from main import app
    meta=args.output/'session.json'
    state=json.loads(meta.read_text(encoding='utf-8')) if meta.exists() else {
        'student_id':'strategy-release-live','session_id':'strategy-release-session','selection':selection(),'cases':[],'model':args.model}
    def save(): meta.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
    def run(client,name,message):
        payload={'student_id':state['student_id'],'session_id':state['session_id'],
            'request_id':args.run_id+'-'+args.phase+'-'+name,'selection':state['selection'],'message':message}
        started=time.monotonic(); print('START '+name,flush=True)
        response=client.post('/api/chat',json=payload);response.raise_for_status(); data=response.json()
        (args.output/(name+'.json')).write_text(json.dumps({'request':payload,'response':data},ensure_ascii=False,indent=2),encoding='utf-8')
        teaching=data.get('teaching') or {}; plan=teaching.get('strategy_plan') or data.get('teaching_strategy_plan') or {}
        case={'name':name,'seconds':round(time.monotonic()-started,2),'status':data.get('answer_status'),
            'strategy':plan.get('primary_strategy'),'receipt':plan.get('publication_receipt'),
            'rounds':(data.get('loop_summary') or {}).get('rounds'),'source_count':len(data.get('sources') or data.get('pdf_references') or []),
            'pending_question':bool(teaching.get('pending_check')),'formal_mastery':teaching.get('formal_mastery')}
        state['cases'].append(case);save();print(json.dumps(case,ensure_ascii=True),flush=True)
        assert data.get('answer_status')=='answered',str(data.get('reply'))
        assert plan.get('policy_version')=='teaching-v2' and plan.get('publication_receipt')
        if teaching:
            assert teaching.get('formal_mastery') is False
        assert not data.get('step_advanced')
        assert data.get('sources') or data.get('pdf_references'),'No actual textbook sources'
        def check_public(value):
            if isinstance(value,dict):
                assert not {'check_expected_answer','expected_answer','accepted_answers'} & value.keys()
                for item in value.values(): check_public(item)
            elif isinstance(value,list):
                for item in value: check_public(item)
        check_public(data)
        return data,payload
    def practice(client):
        check,_=run(client,'check','考考我，围绕选区只出一道开放式题。')
        pending=check['teaching']['pending_check'];assert pending
        state['pending']=pending;save()
        hint,_=run(client,'hint','只给第一级提示，不要替我作答。')
        assert hint['teaching']['pending_check']==pending
        assert hint['teaching']['strategy_plan']['primary_strategy'] in ('hint','scaffolding')
    with TestClient(app) as client:
        if args.phase=='legacy':
            client.post('/api/accounts/test',json={'student_id':state['student_id']}).raise_for_status()
            direct,_=run(client,'legacy-direct','直接解释选区中自变量和因变量的区别，不要出题，也不要问我。')
            assert direct['teaching_strategy_plan']['primary_strategy']=='direct_explanation'
            assert '?' not in direct['reply'] and '？' not in direct['reply']
            hint,_=run(client,'legacy-hint','只给一个理解这段话的提示，不要替我作答。')
            assert hint['teaching_strategy_plan']['primary_strategy']=='hint'
            state['legacy_consumer_passed']=True;save()
        elif args.phase=='prepare':
            client.post('/api/accounts/test',json={'student_id':state['student_id']}).raise_for_status()
            first,payload=run(client,'direct','直接解释选区中自变量和因变量的区别，不要出题，也不要问我。')
            assert first['teaching']['strategy_plan']['primary_strategy']=='direct_explanation'
            assert '?' not in first['reply'] and '？' not in first['reply']
            replay=client.post('/api/chat',json=payload);replay.raise_for_status()
            repeated=replay.json()
            (args.output/'http-replay.json').write_text(json.dumps(repeated,ensure_ascii=False,indent=2),encoding='utf-8')
            assert repeated.pop('reader_action_replay') is True,'Replay must suppress duplicate reader actions'
            assert repeated=={k:v for k,v in first.items() if k!='reader_action_replay'},'HTTP replay changed published result'
            support,_=run(client,'support','我还是不懂，请用一个简单的生活例子解释，不要出题。')
            assert support['teaching']['strategy_plan']['primary_strategy'] in ('worked_example','scaffolding')
            practice(client)
        elif args.phase=='practice':
            client.post('/api/accounts/test',json={'student_id':state['student_id']}).raise_for_status()
            practice(client)
        else:
            assert state.get('pending'),'Run prepare in a separate process first'
            result,_=run(client,'resume','回到刚才的小检查，原样显示题目，不要给答案。')
            assert result['teaching']['pending_check']==state['pending']
            assert result['reply'].rstrip().endswith(state['pending']['prompt'])
            assert (result.get('loop_summary') or {}).get('rounds')==0,'Saved question unexpectedly called model'
            state['restart_recovery_passed']=True;save()
    print(args.phase.upper()+' PASSED',flush=True)


if __name__=='__main__': main()
