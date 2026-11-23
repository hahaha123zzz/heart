"""固定教材图谱的只读版本、映射和学生状态投影。"""
from __future__ import annotations
from hashlib import sha256
import json, os
from pathlib import Path
from datetime import datetime, timezone
from fastapi import HTTPException
from knowledge.lightrag.storage import _pg_connect
from knowledge.lightrag.ingress import _contained_regular_file
from integrations.deeptutor.assessment_intake import confirmed_catalog, RULE_VERSION
from integrations.deeptutor.learning_projection import chapter_progress

ROOT = Path(__file__).parent
RELEASE = ROOT / 'graph_release.json'
MAPPINGS = ROOT / 'graph_mappings.json'
COURSE = 'experimental-psychology-3'
MAX_NODES = 200

def heading_text(value):
    if isinstance(value,dict):
        value=value.get('heading','')
    return value[:2000] if isinstance(value,str) else ''

def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()

def release(course_id=COURSE, expected=None):
    if course_id != COURSE:
        raise HTTPException(404, '课程不存在')
    try:
        record = json.loads(RELEASE.read_text('utf-8'))
        candidate = Path(os.environ['LIGHTRAG_CANDIDATE_PATH']).resolve(strict=True)
        if record['course_id'] != course_id or record['status'] not in ('published', 'approved_isolated_snapshot'):
            raise ValueError('release not approved')
        identity = {k:v for k,v in record.items() if k != 'release_id'}
        if sha256(json.dumps(identity,sort_keys=True,ensure_ascii=False).encode()).hexdigest() != record['release_id']:
            raise ValueError('release identity')
        for name, expected_hash in record['control_hashes'].items():
            path = _contained_regular_file(candidate, candidate / name, label='graph release')
            if digest(path) != expected_hash:
                raise ValueError('graph controls changed')
        if expected and expected != record['release_id']:
            raise HTTPException(409, '图谱版本已变化，请刷新后再查看')
        return record, candidate
    except HTTPException:
        raise
    except (OSError, KeyError, ValueError):
        raise HTTPException(503, '教材图谱版本不可用，请稍后重试') from None

def check_graph(conn, record):
    for table, baseline in record['graph_tables'].items():
        if table not in ('lightrag_graph_nodes', 'lightrag_graph_edges'):
            raise HTTPException(503, '图谱清单无效')
        row = conn.execute(f'select count(*),max(updated_at) from {table} where workspace=%s', (record['workspace'],)).fetchone()
        if row[0] != baseline['count'] or str(row[1]) != baseline['updated_at']:
            raise HTTPException(409, '教材图谱索引已变化，请重新核验版本')

def bindings(record):
    catalog, version = confirmed_catalog()
    try:
        mapping = json.loads(MAPPINGS.read_text('utf-8'))
    except (OSError, ValueError):
        return {}, '', False
    compatible = bool(catalog) and version == record['catalog_sha256'] == mapping.get('catalog_version') and mapping.get('graph_release_id') == record['release_id'] and mapping.get('course_id') == COURSE
    result = {}
    if compatible:
        for item in mapping.get('mappings', []):
            if item.get('status') == 'confirmed' and item.get('kc_id') in catalog:
                result.setdefault(item['entity_id'], []).append(item)
    return result, digest(MAPPINGS), compatible

def status_for(items, points, compatible, mapping_version=None, release_id=None):
    if not compatible:
        return {'kind':'version_unavailable','mapping_status':'version_unavailable'}
    if not items:
        return {'kind':'unmapped','mapping_status':'unmapped'}
    targets = {(item['kc_id'],item['objective_id']) for item in items}
    if len(targets) != 1:
        return {'kind':'ambiguous','mapping_status':'ambiguous','knowledge_point_ids':sorted({k for k,_ in targets})}
    item = items[0]; point = points.get(item['kc_id'])
    result = {'kind':'unknown','mapping_status':'confirmed','knowledge_point_id':item['kc_id'],'objective_id':item['objective_id'], 'mapping_id':item['id'], 'snapshot':None, 'sync_pending':False,'sync_blocked':False}
    if not point:
        return result
    result.update({k:point[k] for k in ('snapshot','sync_pending','sync_blocked')})
    snapshot = point['snapshot']
    if snapshot and mapping_version is not None and (snapshot.get('mapping_version') != mapping_version or snapshot.get('graph_release_id') != release_id or snapshot.get('rule_version') != RULE_VERSION):
        result.update(kind='version_unavailable', snapshot=None, version_mismatch=True)
        return result
    if snapshot:
        result['kind'] = 'mastered' if snapshot['assessed_mastered'] else 'not_mastered'
        due = snapshot.get('next_review_at')
        if due:
            try:
                if datetime.fromisoformat(due).replace(tzinfo=timezone.utc) <= datetime.now(timezone.utc):
                    result['review_due'] = True
            except (ValueError, TypeError):
                pass
    return result

def _read(course_id, expected, chapter, query, focus, limit, student, vendor, detail=False):
    record, candidate = release(course_id, expected)
    mapped, mapping_version, compatible = bindings(record)
    filename = f'chapter_{chapter:02d}.generated.pdf'
    try:
        points = {item['id']:item for item in chapter_progress(student, vendor, chapter)['points']} if compatible else {}
        with _pg_connect() as conn:
            conn.execute('SET TRANSACTION READ ONLY')
            check_graph(conn, record)
            rows = conn.execute('''select id, properties from lightrag_graph_nodes n
                where workspace=%s and namespace='chunk_entity_relation'
                and %s = any(string_to_array(coalesce(properties->>'file_path',''),'<SEP>'))
                and (%s = '' or id ilike %s escape '!')
                and (%s = '' or id=%s or exists(select 1 from lightrag_graph_edges e where e.workspace=n.workspace
                     and e.namespace='chunk_entity_relation' and ((e.src_id=%s and e.tgt_id=n.id) or (e.tgt_id=%s and e.src_id=n.id))))
                order by case when id=%s then 0 else 1 end, id limit %s''',
                (record['workspace'],filename,query,'%'+query.replace('!','!!').replace('%','!%').replace('_','!_')+'%',focus,focus,focus,focus,focus,limit+1)).fetchall()
            if detail and not any(row[0] == focus for row in rows):
                raise HTTPException(404, '本章图谱中没有该实体')
            truncated = len(rows)>limit; rows=rows[:limit];ids=[row[0] for row in rows]
            edges = conn.execute('''select src_id,tgt_id,properties from lightrag_graph_edges where workspace=%s
                and namespace='chunk_entity_relation' and src_id=any(%s) and tgt_id=any(%s)
                order by src_id,tgt_id limit 601''',(record['workspace'],ids,ids)).fetchall() if ids else []
            nodes = [{'id':entity,'type':str((props or {}).get('entity_type','')),'description':str((props or {}).get('description','')).replace('<SEP>','\n')[:6000 if detail else 600],
                'chapter':chapter,'state':status_for([m for m in mapped.get(entity,[]) if m['chapter_id']==chapter],points,compatible,mapping_version,record['release_id'])} for entity,props in rows]
            chunks=[]
            if detail:
                props=next(p for e,p in rows if e==focus)
                source_ids=str((props or {}).get('source_id','')).split('<SEP>')
                chunks=[{'id':i,'text':t[:2400],'file':f,'heading':heading_text(h)} for i,t,f,h in conn.execute('''select id,content,file_path,heading from lightrag_doc_chunks
                    where workspace=%s and id=any(%s) and file_path=%s order by chunk_order_index limit 3''',(record['workspace'],source_ids,filename)).fetchall()]
        sources=json.loads((candidate/'source_map.json').read_text('utf-8'));document=sources[filename]
        result={'course_id':COURSE,'release_id':record['release_id'],'release_status':record['status'],'catalog_version':record['catalog_sha256'],'mapping_version':mapping_version,
            'catalog_available':compatible,'nodes':nodes,'edges':[{'source':a,'target':b,'description':str((p or {}).get('description',''))[:1600],'weight':(p or {}).get('weight',1),'relation':'association'} for a,b,p in edges[:600]],
            'truncated':truncated,'edges_truncated':len(edges)>600,'limit':limit,'total_returned':len(nodes),'chapter':chapter,
            'document':{'id':document['document_id'],'version':document['version'],'chapter':chapter}}
        if detail:
            result.update(node=next(n for n in nodes if n['id']==focus),sources=chunks,mappings=mapped.get(focus,[]))
        return result
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, '图谱或学生状态暂时不可用，请重试') from None


def assessment_versions(catalog_version):
    """固定本次评估的图谱映射版本；没有兼容映射时仍可保留目录级评估。"""
    try:
        record=json.loads(RELEASE.read_text('utf-8'))
        mapping=json.loads(MAPPINGS.read_text('utf-8'))
        if record['catalog_sha256'] != catalog_version or mapping.get('catalog_version') != catalog_version or mapping.get('graph_release_id') != record['release_id']:
            return {}
        return {'graph_release_id':record['release_id'],'mapping_version':digest(MAPPINGS)}
    except (OSError,ValueError,KeyError):
        return {}
