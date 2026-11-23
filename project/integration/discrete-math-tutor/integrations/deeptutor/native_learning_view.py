"""学习页面只读取原生Journal及掌握路径公开投影。"""
from typing import Literal
from fastapi import HTTPException, Response
from pydantic import Field
from .native_contract import NativeScopeRequest

class LearningReadRequest(NativeScopeRequest):
    view: Literal['journal', 'topics', 'board', 'objective'] = 'journal'
    path_id: str = Field(default='', max_length=200)
    objective_id: str = Field(default='', max_length=200)

async def read(bridge, request: LearningReadRequest):
    from deeptutor.api.routers import learning_journal, mastery_path
    from deeptutor.services.workspace.context import workspace_context
    mapped = await bridge.bind_scope(request)
    with bridge.user_scope(mapped['user_id']), workspace_context(mapped['workspace_id']):
        if request.view == 'journal':
            return learning_journal.overview(Response(), limit=20, offset=0)
        if request.view == 'topics':
            result = await mastery_path.list_topics()
            listed = {item['path_id'] for item in result['topics']}
            # 原生聊天的临时路径没有topic_meta；仍通过原生progress与公开投影读取。
            progress = await mastery_path.list_all_progress()
            for item in progress['summaries']:
                if item['book_id'] in listed or not item['modules_count']:
                    continue
                topic = await mastery_path.get_topic(item['book_id'])
                if topic['metadata']['status'] == 'active':
                    result['topics'].append(topic)
            return result
        mastery_path._validate_book_id(request.path_id)
        # 原生board端点会get_or_create；页面只允许读已有路径。
        if not mastery_path.LearningStore().exists(request.path_id):
            raise HTTPException(404, '掌握路径不存在')
        if request.view == 'board':
            return await mastery_path.get_progress_board(request.path_id)
        return await mastery_path.get_objective_report(request.path_id, request.objective_id)

def install(router, bridge):
    @router.post('/learning-view')
    async def learning_view(request: LearningReadRequest):
        return await read(bridge, request)
