"""掌握路径的受控写动作；路径、题目与版本仍由原生存储校验。"""
from typing import Literal

from pydantic import Field, model_validator

from .native_contract import NativeScopeRequest


class LearningWriteRequest(NativeScopeRequest):
    action: Literal['objective_override', 'review_settings', 'redo', 'skip_question']
    path_id: str = Field(min_length=1, max_length=200)
    objective_id: str = Field(default='', max_length=200)
    mastered: bool = False
    note: str = Field(default='', max_length=500)
    desired_retention: float = Field(default=0.9, ge=0.7, le=0.99)

    @model_validator(mode='after')
    def objective_required(self):
        if self.action == 'objective_override' and not self.objective_id:
            raise ValueError('知识点不能为空')
        return self


async def write(bridge, request: LearningWriteRequest):
    from deeptutor.api.routers import mastery_path
    from deeptutor.services.workspace.context import workspace_context

    mapped = await bridge.bind_scope(request)
    with bridge.user_scope(mapped['user_id']), workspace_context(mapped['workspace_id']):
        if request.action == 'objective_override':
            return await mastery_path.set_learner_override(
                request.path_id, request.objective_id,
                mastery_path.LearnerOverrideRequest(mastered=request.mastered, note=request.note))
        if request.action == 'review_settings':
            topic = await mastery_path.update_review_settings(
                request.path_id,
                mastery_path.ReviewSettingsRequest(desired_retention=request.desired_retention))
            retention = topic.get('desired_retention') or (topic.get('review_settings') or {}).get('desired_retention')
            return {'status': 'ok', 'desired_retention': retention,
                    'path_revision': topic.get('path_revision')}
        if request.action == 'redo':
            return await mastery_path.redo_progress(request.path_id)
        return await mastery_path.skip_pending_question(request.path_id)


def install(router, bridge):
    @router.post('/learning-write')
    async def learning_write(request: LearningWriteRequest):
        return await write(bridge, request)
