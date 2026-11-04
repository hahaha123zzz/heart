"""规则先行的单轮路由。

只把已校验的任务动作、教材目录和既有工具目的收敛成一个路由结果；
不重新解释目标，也不扩大被理解层收紧的范围。
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

from knowledge.course import chapters
from knowledge.course_navigation import _number, intent, outline
from models.input_understanding import GroundedTurn, TurnRoute

if TYPE_CHECKING:
    from models.task_context import TaskContext

_CHAPTER = re.compile(r'第([一二三四五六七八九十零\d]+)章')
_SECTION = re.compile(r'第([一二三四五六七八九十零\d]+)节')
# 裸章号/“第一章内容”是范围选择，不是某一节的概念提问。
_BARE_CHAPTER = re.compile(r'^第([一二三四五六七八九十零\d]+)章(?:的)?(?:内容|主要内容)?[。！？!?]*$')
# 只认“数量/清单”语义；内容提问（有哪些/是什么）不是文件目录。
_CATALOG = re.compile(r'(?:几[本份个]|数量|清单|列表).{0,6}(?:教材|文档|资料)|'
                      r'(?:教材|文档|资料).{0,6}(?:几[本份个]|数量|清单|列表)')
_OUTLINE = re.compile(r'目录|章节结构|有哪些小节|小节结构')
_PERSONAL = re.compile(r'记得我|我的.{0,4}(?:偏好|画像|基础)|我喜欢.{0,4}(?:讲|学)')
_READER = re.compile(r'跳转|带我到|打开.{0,6}页|定位到|翻到')
_NO_READER = re.compile(r'(?:不要|不用|不必|别|无需|不需要)(?:再)?(?:执行)?(?:教材)?(?:页面)?(?:的)?'
                        r'(?:跳转|带我到|打开|定位到|翻到)[^，。；;：:！？!?]*')
_FIGURE_QUESTION = re.compile(r'解释|讲解|说明|为什么|如何|什么|看不懂|看懂|含义|区别|步骤')
_SECTION_OVERVIEW = re.compile(r'讲什么|学什么|内容|重点|要点|框架|脉络|概览|简介|有什么|有哪些')
_UNRESOLVED = re.compile(r'(?:^|[^其])他(?!人)|她|它')
_PURE_DEICTIC = re.compile(r'(?:这个|那个|它|这些|那些|这里|那里)(?:呢|啊)?[？?。！!]*')


def reader_requested(message: str) -> bool:
    return bool(_READER.search(_NO_READER.sub('', ''.join(message.split()))))


def _query(turn: GroundedTurn) -> str:
    return (turn.tasks[0].query if turn.tasks and turn.tasks[0].query else turn.envelope.raw_text)[:4000]


def _constraints(turn: GroundedTurn) -> list:
    return list(turn.tasks[0].constraints) if turn.tasks else []


def _result(turn: GroundedTurn, *, kind, scope, chapter=None, section=None, target_id=None,
            name='', query=None, purpose='textbook', mode=None, reason='') -> TurnRoute:
    return TurnRoute(kind=kind, scope=scope, chapter_id=chapter, section_id=section,
        target_id=target_id, name=(name or '')[:200], query=(query if query is not None else _query(turn))[:4000],
        tool_purpose=purpose, navigation_mode=mode, constraints=_constraints(turn),
        source='rule', reason=reason)


def _chapter(text: str):
    match = _CHAPTER.search(text)
    if match:
        number = _number(match[1])
        return next((chapter for chapter in chapters() if chapter['id'] == number), None)
    return next((chapter for chapter in chapters() if chapter['title'] and chapter['title'] in text), None)


def _current_chapter(context) -> int | None:
    for state in (getattr(context, 'activity_target', None) or {},
                  getattr(context, 'course_navigation', None) or {}):
        if state.get('chapter_id'):
            return int(state['chapter_id'])
    return None


def _section(text: str, context):
    match = _SECTION.search(text)
    if not match:
        return None
    chapter = _chapter(text)
    chapter_id = chapter['id'] if chapter else _current_chapter(context)
    if chapter_id is None:
        return None
    number = _number(match[1])
    unit = next((item for item in outline()
                 if item['chapter_id'] == chapter_id and item['section_id'] == number), None)
    if unit is None:
        return None
    return chapter, chapter_id, number, unit['section_title']


def _chapter_query(chapter) -> str:
    return ' '.join([chapter['title'], *(section['title'] for section in chapter['sections'])])


def _figure_ref(turn: GroundedTurn):
    if not turn.tasks or not turn.tasks[0].target_ref:
        return None
    ref = next((item for item in turn.references if item.ref_id == turn.tasks[0].target_ref), None)
    return ref if ref is not None and ref.kind == 'figure' and ref.status == 'resolved' else None


def _resolved_target(turn: GroundedTurn):
    """首个内容任务的已校验目标；命中时无需再用原句猜测指代。"""
    if not turn.tasks or not turn.tasks[0].target_ref:
        return None
    ref = next((item for item in turn.references if item.ref_id == turn.tasks[0].target_ref), None)
    return ref if ref is not None and ref.status == 'resolved' else None


def classify_route(turn: GroundedTurn, context: 'TaskContext') -> TurnRoute:
    """Idempotent: an attached route is already the authoritative classification."""
    if turn.route is not None:
        return turn.route
    text = ''.join(turn.envelope.raw_text.split())
    decision = getattr(context, 'input_decision', None)
    if decision is not None and decision.status in ('clarify', 'reject'):
        kind = 'clarify' if decision.status == 'clarify' else 'reject'
        return _result(turn, kind=kind, scope='none', reason='input_decision:' + decision.reason)
    if 'mixed_state_changes' in turn.unresolved:
        return _result(turn, kind='reject', scope='none', reason='mixed_state_changes')
    if turn.resolution_status in ('ambiguous', 'missing'):
        # 指代尚未落到已校验对象；不再用正则猜目标。
        return _result(turn, kind='clarify', scope='none', reason='reference_unresolved')

    action = turn.tasks[0].action if turn.tasks else None
    if action is None:
        return _result(turn, kind='clarify', scope='none', reason='no_task')

    if action in ('propose_learning_plan', 'revise_learning_plan', 'confirm_learning_plan'):
        chapter = _chapter(text)
        if chapter:
            return _result(turn, kind='learning_plan', scope='chapter', chapter=chapter['id'],
                target_id=f"chapter:{chapter['id']}", name=chapter['title'], reason='plan_request')
        return _result(turn, kind='learning_plan', scope='none', reason='plan_request')

    if action == 'compare_content':
        return _result(turn, kind='comparison', scope='kp', target_id=_kp_id(context), reason='compare_action')

    if action == 'provide_hint':
        pending = bool(turn.tasks[0].target_ref)
        return _result(turn, kind='hint', scope='pending' if pending else 'kp',
            target_id=_pending_id(context) if pending else _kp_id(context), reason='hint_action')

    if action in ('request_practice', 'submit_student_answer'):
        pending = action == 'submit_student_answer' or bool(turn.tasks[0].target_ref)
        return _result(turn, kind='exercise', scope='pending' if pending else 'kp',
            target_id=_pending_id(context) if pending else _kp_id(context), reason='exercise_action')

    if action in ('resume_learning_activity', 'switch_learning_target', 'resume_pending_question'):
        pending = action == 'resume_pending_question'
        return _result(turn, kind='navigation', scope='pending' if pending else 'kp',
            target_id=_pending_id(context) if pending else _kp_id(context),
            mode='repeat' if pending else 'guide', reason='navigation_action')

    if action == 'propose_preference_change':
        return _result(turn, kind='personal_state', scope='none', purpose='personal_state',
            reason='preference_action')

    if action == 'clarify_reference':
        return _result(turn, kind='clarify', scope='none', reason='clarify_action')

    if action in ('chapter_overview', 'section_overview'):
        return _overview(turn, context, text, action, reason='task_action')

    if action == 'explain_content':
        return _explain(turn, context, text)

    return _result(turn, kind='concept_answer', scope='kp', target_id=_kp_id(context),
                   name=_kp_name(context), reason='fallback_action')


def _overview(turn, context, text, action, *, reason):
    chapter = _chapter(text)
    chapter_id = chapter['id'] if chapter else _current_chapter(context)
    if action == 'section_overview' or _SECTION.search(text):
        found = _section(text, context)
        if found:
            chapter, chapter_id, section_id, title = found
            return _result(turn, kind='section_overview', scope='section', chapter=chapter_id,
                section=section_id, target_id=f'section:{chapter_id}:{section_id}', name=title,
                query=title, reason=reason)
    if chapter_id is not None:
        title = chapter['title'] if chapter else _kp_name(context)
        query = _chapter_query(chapter) if chapter else _query(turn)
        return _result(turn, kind='chapter_overview', scope='chapter', chapter=chapter_id,
            target_id=f'chapter:{chapter_id}', name=title, query=query,
            mode='overview', reason=reason)
    return _result(turn, kind='chapter_overview', scope='chapter', reason=reason)


def _explain(turn, context, text):
    from agents.q5_runtime import Q5Runtime
    if Q5Runtime.is_plan_request(text):
        chapter = _chapter(text)
        return _result(turn, kind='learning_plan',
            scope='chapter' if chapter else 'none', chapter=chapter['id'] if chapter else None,
            target_id=f"chapter:{chapter['id']}" if chapter else None,
            name=chapter['title'] if chapter else '', reason='plan_request')

    target = _figure_ref(turn)
    reader_command = reader_requested(text)
    if target is not None:
        if not reader_command and (_FIGURE_QUESTION.search(text) or _NO_READER.search(text)):
            return _result(turn, kind='concept_answer', scope='figure', target_id=target.canonical_id,
                name=target.title, reason='figure_question')
        return _result(turn, kind='reader_action', scope='figure', target_id=target.canonical_id,
            name=target.title, purpose='reader_action', reason='figure_reference')

    if _CATALOG.search(text):
        return _result(turn, kind='catalog', scope='course', purpose='catalog', reason='explicit_file_list')
    if _PERSONAL.search(text):
        return _result(turn, kind='personal_state', scope='none', purpose='personal_state',
            reason='explicit_personal_state')
    if reader_command:
        return _result(turn, kind='reader_action', scope='none', purpose='reader_action', reason='reader_command')

    chapter = _chapter(text)
    if chapter and _BARE_CHAPTER.fullmatch(text):
        previous = getattr(context, 'course_navigation', None) or {}
        mode = 'repeat' if previous.get('chapter_id') == chapter['id'] else 'overview'
        return _result(turn, kind='chapter_overview', scope='chapter', chapter=chapter['id'],
            target_id=f"chapter:{chapter['id']}", name=chapter['title'], query=_chapter_query(chapter),
            mode=mode, reason='bare_chapter_scope')
    nav = intent(turn.envelope.raw_text) if not _SECTION.search(text) else None
    if nav == 'overview' and chapter:
        return _result(turn, kind='chapter_overview', scope='chapter', chapter=chapter['id'],
            target_id=f"chapter:{chapter['id']}", name=chapter['title'], query=_chapter_query(chapter),
            mode='overview', reason='course_navigation_overview')
    if nav == 'start' and chapter:
        return _result(turn, kind='chapter_overview', scope='chapter', chapter=chapter['id'],
            target_id=f"chapter:{chapter['id']}", name=chapter['title'], query=_chapter_query(chapter),
            mode='start', reason='course_navigation_start')

    found = _section(text, context)
    if found and _SECTION_OVERVIEW.search(text):
        chapter, chapter_id, section_id, title = found
        return _result(turn, kind='section_overview', scope='section', chapter=chapter_id,
            section=section_id, target_id=f'section:{chapter_id}:{section_id}', name=title,
            query=title, reason='explicit_section')

    if _OUTLINE.search(text):
        return _result(turn, kind='concept_answer', scope='chapter' if chapter else 'kp',
            chapter=chapter['id'] if chapter else None,
            target_id=f"chapter:{chapter['id']}" if chapter else _kp_id(context),
            name=chapter['title'] if chapter else _kp_name(context),
            query=_chapter_query(chapter) if chapter else None,
            purpose='outline', reason='explicit_outline')

    if _resolved_target(turn) is None and (
            _UNRESOLVED.search(text) or _PURE_DEICTIC.fullmatch(text)):
        return _result(turn, kind='clarify', scope='none', reason='unresolved_reference')

    return _result(turn, kind='concept_answer', scope='kp', target_id=_kp_id(context),
                   name=_kp_name(context), reason='concept_question')


def _kp_name(context) -> str:
    return str(getattr(context, 'knowledge_point', '') or '')


def _kp_id(context) -> str | None:
    name = _kp_name(context)
    return f'kp:{name}' if name else None


def _pending_id(context) -> str | None:
    value = getattr(context, 'pending_question_id', None) if context is not None else None
    if value:
        return f'pending:{value}'
    question = ((getattr(context, 'tutoring', None) or {}).get('progress') or {}).get('pending_question') or {}
    return f"pending:{question['question_id']}" if question.get('question_id') else None
