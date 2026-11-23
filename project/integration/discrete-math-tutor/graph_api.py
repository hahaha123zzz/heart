"""宿主只读图谱接口；身份复用厂家鉴权，不向浏览器开放图谱管理。"""
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from deeptutor.api.routers.auth import require_auth, TokenPayload
from knowledge import student_graph as graph
router=APIRouter(prefix='/api/graph')

def _identity(payload):
    if not payload or not payload.user_id or not payload.username:
        raise HTTPException(401,'请先登录')
    return payload.username,payload.user_id

@router.get('/release')
def current_release(response:Response,course_id:str=Query(default=graph.COURSE,max_length=80),payload:TokenPayload=Depends(require_auth)):
    _identity(payload);record,_=graph.release(course_id)
    response.headers['Cache-Control']='no-store'
    return {k:record[k] for k in ('course_id','release_id','status','catalog_sha256')} | {'max_nodes':graph.MAX_NODES,'chapters':list(range(1,12))}

@router.get('/subgraph')
def subgraph(response:Response,chapter:int=Query(default=1,ge=1,le=11),q:str=Query(default='',max_length=64),focus:str=Query(default='',max_length=256),limit:int=Query(default=80,ge=1,le=graph.MAX_NODES),course_id:str=Query(default=graph.COURSE,max_length=80),release_id:str|None=Query(default=None,max_length=64),payload:TokenPayload=Depends(require_auth)):
    student,vendor=_identity(payload);response.headers['Cache-Control']='no-store'
    return graph._read(course_id,release_id,chapter,q.strip(),focus,limit,student,vendor)

@router.get('/node')
def node(response:Response,id:str=Query(min_length=1,max_length=256),chapter:int=Query(ge=1,le=11),course_id:str=Query(default=graph.COURSE,max_length=80),release_id:str|None=Query(default=None,max_length=64),payload:TokenPayload=Depends(require_auth)):
    student,vendor=_identity(payload);response.headers['Cache-Control']='no-store'
    return graph._read(course_id,release_id,chapter,'',id,1,student,vendor,detail=True)


@router.get('/document')
def document(chapter:int=Query(ge=1,le=11),release_id:str=Query(min_length=64,max_length=64),payload:TokenPayload=Depends(require_auth)):
    from fastapi.responses import FileResponse
    import json
    _identity(payload);record,candidate=graph.release(expected=release_id)
    name=f'chapter_{chapter:02d}.generated.pdf'
    source=json.loads((candidate/'source_map.json').read_text('utf-8'))[name]
    path=graph._contained_regular_file(candidate/'input',candidate/'input/chapters'/f'chapter_{chapter:02d}'/name,label='graph textbook')
    if graph.digest(path)!=source['version']:
        raise HTTPException(409,'教材文件版本已变化')
    return FileResponse(path,media_type='application/pdf',headers={'Cache-Control':'no-store'})
