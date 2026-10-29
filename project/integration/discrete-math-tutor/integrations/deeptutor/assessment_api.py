"""只供持有宿主凭据的服务调用；注册/复核不对学生或LLM暴露。"""
from typing import Literal
from typing import Annotated
import asyncio

from fastapi import HTTPException
from pydantic import Field, model_validator
from deeptutor.learning.models import PendingQuestion
from deeptutor.learning.service import MasteryInteractionError
from agents.context_sufficiency import EvidenceDecision
from .native_contract import NativeTurnKey, Identifier
from .assessment_commands import AssessmentCommands
from .client import BackendUnavailable


class AssessmentKey(NativeTurnKey):
    path_id: Identifier
    question_id: Identifier


class AssessmentRegistration(NativeTurnKey):
    path_id: Identifier
    question: PendingQuestion
    reviewer_id: str = Field(min_length=1, max_length=100)
    key_version: str = Field(min_length=1, max_length=100)
    sources: list[dict] = Field(min_length=1, max_length=8)
    rubric: list[dict[str, str]] = Field(default_factory=list, max_length=8)
    evidence_decision: EvidenceDecision

    @model_validator(mode='after')
    def bounded(self):
        import json
        if len(json.dumps(self.model_dump(), ensure_ascii=False)) > 50000:
            raise ValueError('测评资料超过大小上限')
        if any(set(c) != {'id', 'description'} or len(c['description']) > 500 for c in self.rubric):
            raise ValueError('rubric格式无效')
        return self


class AssessmentAction(AssessmentKey):
    command_id: Identifier
    action: Literal['present', 'message', 'answer', 'help', 'grade', 'review', 'skip', 'defer', 'void',
                    'hypothesis', 'dismiss_hypothesis', 'resolve_hypothesis']
    text: str = Field(default='', max_length=4000)
    confidence: float | None = Field(default=None, ge=0, le=1, strict=True, allow_inf_nan=False)
    kind: Literal['hint', 'example', 'explanation', 'source_view'] = 'hint'
    level: int = Field(default=0, ge=0, le=3, strict=True)
    full_explanation: bool = False
    published: bool = False
    reviewer_id: str = Field(default='', max_length=100)
    criteria: dict[str, Literal['met', 'not_met', 'unavailable']] | None = Field(default=None, max_length=8)
    misconception_type: str = Field(default='', max_length=100)
    source_quote: str = Field(default='', max_length=1000)


class AssessmentCorrection(AssessmentKey):
    command_id: Identifier
    expected_answer: str = Field(min_length=1, max_length=20)
    reviewer_id: str = Field(min_length=1, max_length=100)
    key_version: str = Field(min_length=1, max_length=100)
    sources: list[dict] = Field(min_length=1, max_length=8)
    reason: str = Field(min_length=1, max_length=500)


class CardSupport(AssessmentKey):
    hints: list[Annotated[str, Field(min_length=1, max_length=1200)]] = Field(default_factory=list, max_length=3)
    full_explanation: str = Field(default='', max_length=4000)
    presentations: list[dict] = Field(default_factory=list, max_length=2)

    @model_validator(mode='after')
    def complete_hints(self):
        if self.hints and (len(self.hints) != 3 or any(not hint.strip() for hint in self.hints)):
            raise ValueError('提示须提供完整的三级内容')
        return self


class CardAction(AssessmentKey):
    card_id: Identifier
    command_id: Identifier
    base_revision: int = Field(ge=0, strict=True)
    action: Literal['set_expanded', 'submit_answer', 'grade', 'request_hint', 'view_explanation', 'defer', 'skip', 'return_path']
    text: str = Field(default='', max_length=4000)
    expanded: list[Annotated[int, Field(ge=0, le=6, strict=True)]] = Field(default_factory=list, max_length=7)


class ReviewAction(AssessmentKey):
    review_id: Identifier
    command_id: Identifier
    base_revision: int = Field(ge=0, strict=True)
    action: Literal['start', 'defer', 'finish', 'return']
    delay_hours: Literal[1, 24, 72] = 24


def install_assessment_api(router, bridge):
    from .learning_cards import NativeLearningCards
    from .review import NativeReviewService
    async def checked(payload, operation):
        entry = bridge.entry(payload)
        await bridge.authorize_assessment(payload, entry)
        try:
            def run():
                with bridge.learning_service(payload) as service:
                    return operation(AssessmentCommands(service))
            result = await asyncio.to_thread(run)
            await bridge.authorize_assessment(payload, entry)
            return result
        except (MasteryInteractionError, ValueError, KeyError) as exc:
            raise HTTPException(409, detail={'code': str(exc)[:200]}) from exc
        except BackendUnavailable as exc:
            permanent = getattr(exc.__cause__, 'code', None) in (400, 401, 403, 404, 409, 410, 422)
            raise HTTPException(409 if permanent else 503, detail={
                'code': 'assessment_authorization_changed' if permanent else 'assessment_authorization_unavailable'}) from exc

    @router.post('/assessment/register')
    async def register(payload: AssessmentRegistration):
        values = payload.model_dump(include={'reviewer_id', 'key_version', 'sources', 'rubric'})
        return await checked(payload, lambda commands: commands.register(payload.path_id, payload.question,
            evidence_decision=payload.evidence_decision, **values))

    @router.post('/assessment/status')
    async def status(payload: AssessmentKey):
        return await checked(payload, lambda commands: commands.status(payload.path_id, payload.question_id))

    @router.post('/assessment/action')
    async def action(payload: AssessmentAction):
        values = payload.model_dump(exclude=set(AssessmentKey.model_fields))
        return await checked(payload, lambda commands: commands.run(payload.path_id, payload.question_id, **values))

    @router.post('/assessment/correct')
    async def correct(payload: AssessmentCorrection):
        values = payload.model_dump(exclude=set(AssessmentKey.model_fields))
        return await checked(payload, lambda commands: commands.correct(payload.path_id, payload.question_id, **values))

    @router.post('/assessment/cards')
    async def cards(payload: AssessmentKey):
        return await checked(payload, lambda commands: NativeLearningCards(commands).deck(payload.path_id, payload.question_id))

    @router.post('/assessment/cards/configure')
    async def configure_cards(payload: CardSupport):
        values = payload.model_dump(exclude=set(AssessmentKey.model_fields))
        return await checked(payload, lambda commands: NativeLearningCards(commands).configure(payload.path_id, payload.question_id, **values))

    @router.post('/assessment/cards/action')
    async def card_action(payload: CardAction):
        values = payload.model_dump(exclude=set(AssessmentKey.model_fields))
        return await checked(payload, lambda commands: NativeLearningCards(commands).act(payload.path_id, payload.question_id, **values))

    @router.post('/assessment/reviews')
    async def reviews(payload: AssessmentKey):
        return await checked(payload, lambda commands: NativeReviewService(commands).queue(payload.path_id))

    @router.post('/assessment/reviews/action')
    async def review_action_endpoint(payload: ReviewAction):
        values = payload.model_dump(exclude=set(AssessmentKey.model_fields))
        return await checked(payload, lambda commands: NativeReviewService(commands).act(payload.path_id, **values))
