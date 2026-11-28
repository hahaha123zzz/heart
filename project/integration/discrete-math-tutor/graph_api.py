"""宿主只读图谱接口；身份复用厂家鉴权，不向浏览器开放图谱管理。

心理学走固定 LightRAG 图谱发行版；离散数学没有 LightRAG 发行版，直接由
`knowledge/pdf_sections.json` 的章—节结构生成同契约的只读图谱。
"""
from hashlib import sha256
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import FileResponse

from deeptutor.api.routers.auth import require_auth, TokenPayload
from knowledge import student_graph as graph
from knowledge.course_config import PSYCHOLOGY, ROOT

router = APIRouter(prefix='/api/graph')

SECTIONS = ROOT / 'knowledge' / 'pdf_sections.json'
PDF_DIR = ROOT / 'knowledge' / 'pdf'
DISCRETE_MAPPING = 'textbook-structure-v1'


def _identity(payload):
    if not payload or not payload.user_id or not payload.username:
        raise HTTPException(401, '请先登录')
    return payload.username, payload.user_id


def _digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _release_id() -> str:
    return _digest(SECTIONS)


def _chapter_record(chapter: int):
    records = json.loads(SECTIONS.read_text('utf-8'))
    record = next((item for item in records if int(item['id']) == chapter), None)
    if record is None:
        raise HTTPException(404, '章节不存在')
    return record


def _document(chapter: int) -> dict:
    path = PDF_DIR / f'chapter_{chapter:02d}.pdf'
    return {'id': f'chapter-{chapter:02d}', 'version': _digest(path) if path.is_file() else '0' * 64,
            'chapter': chapter}


def _discrete_payload(chapter: int, query: str, focus: str, limit: int) -> dict:
    record = _chapter_record(chapter)
    title = ''.join(str(record['title']).split())
    chapter_id = f'第{chapter}章 {title}'
    chapter_label = f'第{chapter}章{title}'
    unmapped = {'kind': 'unmapped', 'mapping_status': 'unmapped'}
    nodes = [{'id': chapter_id, 'type': 'chapter', 'description': f'第{chapter}章 {title}',
              'chapter': chapter, 'state': dict(unmapped)}]
    edges = []
    previous = chapter_id
    for section in record.get('sections') or []:
        name = ''.join(str(section['title']).split())
        if name in {chapter_label, title}:
            continue
        text = ' '.join(str(section.get('content') or '').split())
        nodes.append({'id': name, 'type': 'section', 'description': text[:200],
                      'chapter': chapter, 'state': dict(unmapped)})
        edges.append({'source': chapter_id, 'target': name, 'weight': 1.0,
                      'description': '', 'relation': 'chapter_section'})
        if previous != chapter_id:
            edges.append({'source': previous, 'target': name, 'weight': 1.0,
                          'description': '下一节', 'relation': 'sequence'})
        previous = name
    if query.strip():
        needle = query.strip().casefold()
        keep = {node['id'] for node in nodes
                if needle in node['id'].casefold() or needle in node['description'].casefold()}
        nodes = [node for node in nodes if node['id'] in keep]
        edges = [edge for edge in edges if edge['source'] in keep and edge['target'] in keep]
    if focus.strip():
        keep = {focus.strip()} | {edge['target'] for edge in edges if edge['source'] == focus.strip()} \
            | {edge['source'] for edge in edges if edge['target'] == focus.strip()}
        nodes = [node for node in nodes if node['id'] in keep]
        edges = [edge for edge in edges if edge['source'] in keep and edge['target'] in keep]
    truncated = len(nodes) > limit
    nodes = nodes[:limit]
    ids = {node['id'] for node in nodes}
    edges = [edge for edge in edges if edge['source'] in ids and edge['target'] in ids]
    edges_truncated = len(edges) > 600
    return {'course_id': 'discrete-math', 'release_id': _release_id(),
            'release_status': 'published', 'catalog_version': _release_id(),
            'mapping_version': DISCRETE_MAPPING, 'catalog_available': True,
            'nodes': nodes, 'edges': edges[:600], 'truncated': truncated,
            'edges_truncated': edges_truncated, 'limit': limit, 'chapter': chapter,
            'document': _document(chapter)}


@router.get('/release')
def current_release(response: Response, course_id: str = Query(default=graph.COURSE, max_length=80),
                    payload: TokenPayload = Depends(require_auth)):
    _identity(payload)
    if not PSYCHOLOGY:
        response.headers['Cache-Control'] = 'no-store'
        return {'course_id': 'discrete-math', 'release_id': _release_id(), 'status': 'published',
                'catalog_sha256': _release_id(), 'max_nodes': graph.MAX_NODES,
                'chapters': list(range(1, 11))}
    record, _ = graph.release(course_id)
    response.headers['Cache-Control'] = 'no-store'
    return {k: record[k] for k in ('course_id', 'release_id', 'status', 'catalog_sha256')} | \
           {'max_nodes': graph.MAX_NODES, 'chapters': list(range(1, 12))}


@router.get('/subgraph')
def subgraph(response: Response, chapter: int = Query(default=1, ge=1, le=11),
             q: str = Query(default='', max_length=64), focus: str = Query(default='', max_length=256),
             limit: int = Query(default=80, ge=1, le=graph.MAX_NODES),
             course_id: str = Query(default=graph.COURSE, max_length=80),
             release_id: str | None = Query(default=None, max_length=64),
             payload: TokenPayload = Depends(require_auth)):
    _identity(payload)
    response.headers['Cache-Control'] = 'no-store'
    if not PSYCHOLOGY:
        return _discrete_payload(chapter, q, focus, limit)
    student, vendor = _identity(payload)
    return graph._read(course_id, release_id, chapter, q.strip(), focus, limit, student, vendor)


@router.get('/node')
def node(response: Response, id: str = Query(min_length=1, max_length=256),
         chapter: int = Query(ge=1, le=11), course_id: str = Query(default=graph.COURSE, max_length=80),
         release_id: str | None = Query(default=None, max_length=64),
         payload: TokenPayload = Depends(require_auth)):
    _identity(payload)
    response.headers['Cache-Control'] = 'no-store'
    if not PSYCHOLOGY:
        payload_data = _discrete_payload(chapter, '', '', graph.MAX_NODES)
        target = next((item for item in payload_data['nodes'] if item['id'] == id), None)
        if target is None:
            raise HTTPException(404, '节点不存在')
        record = _chapter_record(chapter)
        section = next((item for item in record.get('sections') or []
                        if ''.join(str(item['title']).split()) == id), None)
        text = ' '.join(str((section or {}).get('content') or target['description']).split())[:2000]
        return payload_data | {
            'node': target,
            'sources': [{'id': f'chapter-{chapter:02d}', 'text': text,
                         'file': f'chapter_{chapter:02d}.pdf', 'heading': id}],
            'mappings': [],
        }
    student, vendor = _identity(payload)
    return graph._read(course_id, release_id, chapter, '', id, 1, student, vendor, detail=True)


@router.get('/document')
def document(chapter: int = Query(ge=1, le=11), release_id: str = Query(min_length=64, max_length=64),
             payload: TokenPayload = Depends(require_auth)):
    _identity(payload)
    if not PSYCHOLOGY:
        path = PDF_DIR / f'chapter_{chapter:02d}.pdf'
        if not path.is_file():
            raise HTTPException(404, '教材文件不存在')
        return FileResponse(path, media_type='application/pdf', headers={'Cache-Control': 'no-store'})
    record, candidate = graph.release(expected=release_id)
    name = f'chapter_{chapter:02d}.generated.pdf'
    source = json.loads((candidate / 'source_map.json').read_text('utf-8'))[name]
    path = graph._contained_regular_file(candidate / 'input', candidate / 'input/chapters' /
                                         f'chapter_{chapter:02d}' / name, label='graph textbook')
    if graph.digest(path) != source['version']:
        raise HTTPException(409, '教材文件版本已变化')
    return FileResponse(path, media_type='application/pdf', headers={'Cache-Control': 'no-store'})
