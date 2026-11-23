"""任务六：隔离 PG 图谱和可控厂家投影；测试夹具不作为真实成绩。"""
import json,hashlib,os
from pathlib import Path
from unittest.mock import patch
from contextlib import contextmanager
from types import SimpleNamespace
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

@pytest.fixture(scope='module')
def graph_db():
    from tests.pg_support import temp_databases
    with temp_databases('heart_task6_graph') as env:
        import psycopg
        def connect():return psycopg.connect(host=env['POSTGRES_HOST'],port=env['POSTGRES_PORT'],user=env['POSTGRES_USER'],password=env['POSTGRES_PASSWORD'],dbname=env['POSTGRES_DATABASE'])
        with connect() as conn:
            conn.execute('CREATE TABLE lightrag_graph_nodes(workspace text,namespace text,id text,properties jsonb,updated_at timestamptz default now())')
            conn.execute('CREATE TABLE lightrag_graph_edges(workspace text,namespace text,src_id text,tgt_id text,properties jsonb,updated_at timestamptz default now())')
            from psycopg.types.json import Jsonb
            for id,chapter in [('概念甲',1),('未映射乙',1),('百分比%',1),('第二章实体',2)]:
                conn.execute('INSERT INTO lightrag_graph_nodes(workspace,namespace,id,properties) values(%s,%s,%s,%s)',('approved','chunk_entity_relation',id,Jsonb({'file_path':f'chapter_{chapter:02d}.generated.pdf','source_id':'chunk-1','description':'真实数据接口的测试替身'})))
            conn.execute("INSERT INTO lightrag_graph_edges(workspace,namespace,src_id,tgt_id,properties) values('approved','chunk_entity_relation','概念甲','未映射乙','{}')")
            conn.execute('CREATE TABLE lightrag_doc_chunks(id text,workspace text,content text,file_path text,heading jsonb,chunk_order_index int)')
            conn.execute('INSERT INTO lightrag_doc_chunks values(%s,%s,%s,%s,%s,%s)',('chunk-1','approved','教材依据文本','chapter_01.generated.pdf',Jsonb({'level':1,'heading':'一节','parent_headings':[]}),1))
        yield connect

@pytest.fixture
def api(tmp_path,monkeypatch,graph_db):
    from knowledge import student_graph as graph
    import graph_api
    candidate=tmp_path/'candidate';candidate.mkdir()
    source={'chapter_01.generated.pdf':{'document_id':'experimental-psychology-3:chapter-01','version':'test-pdf-version'}}
    (candidate/'source_map.json').write_text(json.dumps(source),'utf-8')
    record={'schema':'heart-graph-release-v1','course_id':graph.COURSE,'workspace':'approved','status':'approved_isolated_snapshot','catalog_sha256':'catalog-v1','control_hashes':{'source_map.json':graph.digest(candidate/'source_map.json')}}
    with graph_db() as conn:
        record['graph_tables']={t:{'count':row[0],'updated_at':str(row[1])} for t in ['lightrag_graph_nodes','lightrag_graph_edges'] for row in [conn.execute(f'select count(*),max(updated_at) from {t} where workspace=%s',('approved',)).fetchone()]}
    record['release_id']=hashlib.sha256(json.dumps(record,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    release=tmp_path/'release.json';release.write_text(json.dumps(record),'utf-8')
    mappings=tmp_path/'mappings.json';mappings.write_text(json.dumps({'course_id':graph.COURSE,'graph_release_id':record['release_id'],'rule_version':graph.RULE_VERSION,'catalog_version':'catalog-v1','mappings':[{'status':'confirmed','entity_id':'概念甲','kc_id':'kc-1-1','objective_id':'kc-1-1','chapter_id':1,'id':'M001'}]}),'utf-8')
    monkeypatch.setenv('LIGHTRAG_CANDIDATE_PATH',str(candidate));monkeypatch.setattr(graph,'RELEASE',release);monkeypatch.setattr(graph,'MAPPINGS',mappings);monkeypatch.setattr(graph,'_pg_connect',graph_db)
    monkeypatch.setattr(graph,'confirmed_catalog',lambda:({'kc-1-1':{}},'catalog-v1'))
    projection=lambda student,vendor,chapter:{'points':[{'id':'kc-1-1','snapshot':{'assessed_mastered':True,'learning_stage':'mastered','next_review_at':'2000-01-01T00:00:00+00:00','synced_at':'2026-11-20T00:00:00+00:00','mapping_version':graph.digest(mappings),'graph_release_id':record['release_id'],'rule_version':graph.RULE_VERSION},'sync_pending':True,'sync_blocked':False}] if student=='a' and vendor=='vendor-a' else []}
    monkeypatch.setattr(graph,'chapter_progress',projection)
    app=FastAPI();app.include_router(graph_api.router);app.dependency_overrides[graph_api.require_auth]=lambda:SimpleNamespace(username='a',user_id='vendor-a')
    with TestClient(app) as client:yield client,app,graph_api,graph,record,mappings,candidate

def test_scope_limit_partial_and_literal_search(api):
    client,_,_,_,release,_,_=api
    data=client.get('/api/graph/subgraph?chapter=1&limit=1').json()
    assert data['truncated'] and len(data['nodes'])==1 and data['release_id']==release['release_id']
    assert client.get('/api/graph/subgraph?limit=201').status_code==422
    assert client.get('/api/graph/subgraph?chapter=12').status_code==422
    assert client.get('/api/graph/subgraph?course_id=other').status_code==404
    assert client.get('/api/graph/subgraph?release_id=old').status_code==409
    result=client.get('/api/graph/subgraph',params={'chapter':1,'q':'%'}).json()
    assert [n['id'] for n in result['nodes']]==['百分比%']
    assert client.get('/api/graph/subgraph?chapter=1').headers['cache-control']=='no-store'

def test_state_is_owner_bound_and_sync_lag_does_not_hide_previous_source(api):
    client,app,routes,_,_,_,_=api
    data=client.get('/api/graph/node',params={'id':'概念甲','chapter':1}).json()
    assert data['node']['state']['kind']=='mastered' and data['node']['state']['review_due']
    assert data['node']['state']['sync_pending'] and data['sources'][0]['text']=='教材依据文本'
    assert data['sources'][0]['heading']=='一节'
    app.dependency_overrides[routes.require_auth]=lambda:SimpleNamespace(username='b',user_id='vendor-b')
    other=client.get('/api/graph/node',params={'id':'概念甲','chapter':1}).json()
    assert other['node']['state']['kind']=='unknown' and other['node']['state']['snapshot'] is None
    unmapped=client.get('/api/graph/node',params={'id':'未映射乙','chapter':1}).json()
    assert unmapped['node']['state']['kind']=='unmapped'
    assert client.get('/api/graph/node',params={'id':'第二章实体','chapter':1}).status_code==404

def test_pending_and_ambiguous_mappings_never_project_mastery(api):
    client,_,_,_,_,path,_=api
    mapping=json.loads(path.read_text('utf-8'));mapping['mappings'][0]['status']='pending';path.write_text(json.dumps(mapping),'utf-8')
    assert client.get('/api/graph/node',params={'id':'概念甲','chapter':1}).json()['node']['state']['kind']=='unmapped'
    mapping['mappings'][0]['status']='confirmed';mapping['mappings'].append({**mapping['mappings'][0],'objective_id':'another-objective'})
    path.write_text(json.dumps(mapping),'utf-8')
    result=client.get('/api/graph/node',params={'id':'概念甲','chapter':1}).json()
    assert result['node']['state']['kind']=='ambiguous' and 'snapshot' not in result['node']['state']

def test_version_changes_fail_closed_and_no_graph_mutations(api):
    client,_,_,_,_,path,candidate=api
    mapping=json.loads(path.read_text('utf-8'));mapping['catalog_version']='old';path.write_text(json.dumps(mapping),'utf-8')
    assert client.get('/api/graph/subgraph?chapter=1').json()['catalog_available'] is False
    (candidate/'source_map.json').write_text('{}','utf-8')
    assert client.get('/api/graph/subgraph?chapter=1').status_code==503
    assert client.post('/api/graph/subgraph',json={}).status_code==405
    assert client.delete('/api/graph/node?id=x&chapter=1').status_code==405

def test_missing_identity_is_rejected(api):
    client,app,routes,_,_,_,_=api
    app.dependency_overrides[routes.require_auth]=lambda:SimpleNamespace(username='a',user_id='')
    assert client.get('/api/graph/release').status_code==401


def test_previous_mapping_results_are_not_inherited_by_a_new_mapping(api,monkeypatch):
    client,_,_,graph,_,_,_=api
    monkeypatch.setattr(graph,'chapter_progress',lambda *args:{'points':[{'id':'kc-1-1','snapshot':{'assessed_mastered':True,'mapping_version':'old','graph_release_id':'old'},'sync_pending':False,'sync_blocked':False}]})
    result=client.get('/api/graph/node',params={'id':'概念甲','chapter':1}).json()['node']['state']
    assert result['kind']=='version_unavailable' and result['snapshot'] is None and result['version_mismatch']


def test_student_state_failure_is_explicit_and_cannot_be_presented_as_unknown(api,monkeypatch):
    client,_,_,graph,_,_,_=api
    def unavailable(*args):raise RuntimeError('isolated state storage unavailable')
    monkeypatch.setattr(graph,'chapter_progress',unavailable)
    assert client.get('/api/graph/subgraph?chapter=1').status_code==503
