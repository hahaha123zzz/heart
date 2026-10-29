"""固定上游提示组装器的请求级适配；不增加循环、画像库或模型调用。"""
from contextlib import contextmanager
from contextvars import ContextVar
import hashlib
import json
from pathlib import Path

from agents.teaching_policy import resolve_teaching_mode, teaching_mode_instructions
from models.interaction_preferences import InteractionPreferences, style_instructions, turn_style_overrides
from .client import BackendUnavailable

_style = ContextVar('heart_native_teaching_style', default=None)


def teaching_snapshot(message, preferences=None):
    return {'mode': resolve_teaching_mode(message),
            'preferences': {**(preferences or {}), **turn_style_overrides(message)}}


def install_teaching_prompt_adapter():
    from deeptutor.agents.loop.prompt_blocks import LoopPromptAssembler, PromptBlock
    from .learning_tool_adapter import current_learning_context
    from .worker import VENDOR_ROOT

    original = LoopPromptAssembler.blocks
    if getattr(original, '_heart_teaching_adapter', False):
        return
    source = VENDOR_ROOT / 'deeptutor/agents/loop/prompt_blocks.py'
    pin = json.loads((VENDOR_ROOT / 'UPSTREAM_SNAPSHOT.json').read_text(encoding='utf-8'))
    if (original.__module__ != 'deeptutor.agents.loop.prompt_blocks'
            or Path(original.__code__.co_filename).resolve() != source.resolve()
            or hashlib.sha256(source.read_bytes()).hexdigest() != pin['files']['deeptutor/agents/loop/prompt_blocks.py']):
        raise BackendUnavailable('原生提示组装器与固定上游源码不一致')

    def blocks(assembler, *, context, **kwargs):
        current = current_learning_context()
        snapshot = _style.get()
        if current is None:
            return original(assembler, context=context, **kwargs)
        if snapshot is None or context.session_id != current.session_id:
            raise BackendUnavailable('原生教学偏好缺少本轮会话上下文')
        result = original(assembler, context=context, **kwargs)
        text = '\n'.join((
            '以下仅约束本轮讲法；不改变outline/study/review路径模式、来源核验、私有答案权限或正式测评规则。',
            teaching_mode_instructions(snapshot['mode']),
            style_instructions(snapshot['preferences']),
            '学生询问重点或知识关系时，区分教材明确内容、已提供的考纲或教师标注和教学建议；没有考纲或教师依据不得声称考试重点或分值。教材明确关系应附来源，推断的联系注明是教学分析，不冒充原文或先修事实。',
            '复习到期仅提供选择，不强制切换当前讲解；只有可靠的近期证据或学生明确选择才调整讲法。调度器排序/回忆估计是启发式，不是校准的掌握概率；历史策略效果只是观察线索，不声称因果最优。',
        ))
        return [*result, PromptBlock('host_teaching_style', text)]

    blocks._heart_teaching_adapter = True
    LoopPromptAssembler.blocks = blocks


@contextmanager
def teaching_prompt_scope(entry):
    install_teaching_prompt_adapter()
    snapshot = json.loads(entry.get('teaching_style') or '{}')
    mode = snapshot.get('mode', 'auto')
    if mode not in ('auto', 'direct', 'guided', 'practice', 'review'):
        raise BackendUnavailable('原生教学模式记录无效')
    values = InteractionPreferences.model_validate(snapshot.get('preferences') or {}).model_dump(exclude_none=True)
    token = _style.set({'mode': mode, 'preferences': values})
    try:
        yield
    finally:
        _style.reset(token)
