"""章节导学：从课程目录构建章节包，校验一次模型输出，再发布已绑定来源的回答。"""
from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
import re
from uuid import uuid4

from agents.course_prompts import CHAPTER_OVERVIEW
from agents.q3_navigation import source_from_chunk
from models.learning_response import BlockSpec, ContentClaim, LearningResponse, PublishedBlock, ResponsePlan

CITATION = re.compile(r'\[(\d+)\]')
MASTERY = re.compile(r'已掌握|学会了|你已经掌握|formal_mastery')
TEXT_FIELDS = ('roadmap', 'order', 'first_concept', 'next_action')
SENTENCE = re.compile(r'[^。！？!?；;\n]+')
YEAR = re.compile(r'(?<!\d)(?:1[6-9]\d{2}|20\d{2})(?!\d)')
PERSON_ACTION = re.compile(r'[\u4e00-\u9fa5]{2,4}(?:于|提出|建立|创立|发现|认为|指出|完成|设计|报告)')
THEORY = re.compile(r'理论|效应|定律|假说|学说|范式|量表|测验|法则|定理')
STRUCTURAL_WORDS = re.compile(
    r'本章|本节|教材|目录|分为|涵盖|包括|顺序|阅读|学习|建议|内容|整体|地图|'
    r'先|再|然后|最后|首先|其次|接着|按|从|到|开始|了解|掌握|共|是|有|的|和|与|及|或|了')
STRUCTURAL_CHARS = re.compile(r'[第章节一二三四五六七八九十零\d\s，。；：、,.;:！!？?（）()【】\[\]“”"\'\-—…·+]+')


@dataclass(frozen=True)
class ChapterSection:
    section_id: int
    title: str
    first_target: str
    source_id: str | None
    unit_id: str = ''
    version: str = ''


@dataclass(frozen=True)
class ChapterPackage:
    chapter_id: int
    chapter_title: str
    sections: tuple[ChapterSection, ...]
    sources: tuple[dict, ...]
    query: str


def build_chapter_package(chapter_id: int, *, limit: int = 6) -> ChapterPackage:
    from knowledge.course import chapters
    from knowledge.course_navigation import outline
    from knowledge.psychology_retrieval import retrieve
    chapter = next((item for item in chapters() if item['id'] == chapter_id), None)
    if chapter is None:
        raise ValueError('unknown_chapter')
    units = [unit for unit in outline() if unit['chapter_id'] == chapter_id]
    first = {}
    for unit in units:
        first.setdefault(unit['section_id'], unit)
    sections = tuple(ChapterSection(
        section['id'], section['title'],
        str((first.get(section['id']) or {}).get('title') or ''),
        (first.get(section['id']) or {}).get('source'),
        str((first.get(section['id']) or {}).get('id') or ''),
        str((first.get(section['id']) or {}).get('version') or ''),
    ) for section in chapter['sections'])
    query = ' '.join([chapter['title']] + [section.title for section in sections])
    chunks = [chunk for chunk in retrieve(query, [], limit=limit)
              if getattr(chunk, 'chapter_id', None) == chapter_id]
    sources = tuple(source_from_chunk(chunk, index).to_dict() | {'index': index}
                    for index, chunk in enumerate(chunks, 1))
    return ChapterPackage(chapter_id, chapter['title'], sections, sources, query)


def _text(payload: dict) -> str:
    parts = [str(payload.get(field) or '') for field in TEXT_FIELDS]
    parts += [str(section.get('question') or '') for section in payload.get('sections') or []
              if isinstance(section, dict)]
    return '\n'.join(parts)


def _structural_body(sentence: str, package: ChapterPackage) -> str:
    body = CITATION.sub('', sentence)
    names = [package.chapter_title]
    for section in package.sections:
        names.extend((section.title, section.first_target))
    for title in names:
        if not title:
            continue
        body = body.replace(title, '').replace(title.split(' ', 1)[-1], '')
    return STRUCTURAL_WORDS.sub('', body)


def _structural_only(sentence: str, package: ChapterPackage) -> bool:
    return not STRUCTURAL_CHARS.sub('', _structural_body(sentence, package))


def _excerpt_text(package: ChapterPackage) -> str:
    lines = []
    for source in package.sources:
        header = f"[{source.get('index')}] {source.get('document_id') or '教材'}｜"
        if source.get('page'):
            header += f"第{source['page']}页"
        lines.append(header + "\n" + str(source.get('text') or ''))
    return "\n".join(lines)


def _grounding_issues(payload: dict, package: ChapterPackage) -> list[str]:
    issues = []
    from knowledge.citation_guard import citation_issues
    for issue in citation_issues(_text(payload), _excerpt_text(package)):
        issues.append('citation_guard:' + issue)
    for field in ('roadmap', 'order', 'first_concept'):
        for sentence in SENTENCE.findall(str(payload.get(field) or '')):
            body = _structural_body(sentence, package)
            if CITATION.search(sentence) or not STRUCTURAL_CHARS.sub('', body):
                continue
            # Minimum guard: dates/numbers and theory names need [n]. Person names
            # in the roadmap are orientation; the first_concept carries the cited facts.
            if YEAR.search(body) or THEORY.search(body):
                issues.append('uncited_fact:' + sentence.strip()[:40])
    return issues


def validate_overview(payload: dict, package: ChapterPackage, *,
                      require_citations: bool = True,
                      max_questions: int = 1) -> tuple[bool, list[str]]:
    """Return concrete error codes so the handler can run one repair attempt."""
    if not isinstance(payload, dict):
        return False, ['payload_invalid']
    errors = []
    text = _text(payload)
    if package.chapter_title not in text:
        errors.append('chapter_title_missing')
    listed = [section for section in payload.get('sections') or [] if isinstance(section, dict)]
    expected = {section.section_id for section in package.sections}
    covered = {section.get('section_id') for section in listed}
    omitted = set(payload.get('omitted_sections') or [])
    unknown = sorted((covered | omitted) - expected, key=str)
    if unknown:
        errors.append('section_unknown:' + ','.join(map(str, unknown)))
    if not expected <= covered | omitted:
        errors.append('section_coverage_missing')
    if covered & omitted:
        errors.append('section_coverage_conflict')
    allowed = {int(source.get('index') or 0) for source in package.sources}
    cited = {int(number) for number in CITATION.findall(text)}
    unbound = sorted(cited - allowed)
    if unbound:
        errors.append('citation_unbound:' + ','.join(map(str, unbound)))
    first_concept = str(payload.get('first_concept') or '').strip()
    if require_citations:
        if not package.sources:
            errors.append('citation_without_sources')
        if not cited:
            errors.append('citation_missing')
        if not first_concept:
            errors.append('first_concept_missing')
        errors.extend(_grounding_issues(payload, package))
    else:
        if cited:
            errors.append('citation_without_sources')
        if first_concept:
            errors.append('first_concept_without_sources')
    if MASTERY.search(text):
        errors.append('mastery_claim')
    marks = text.count('?') + text.count('？')
    next_action = str(payload.get('next_action') or '')
    if marks > max_questions or (marks == 1 and max_questions == 1
            and '?' not in next_action and '？' not in next_action):
        errors.append('question_limit')
    return not errors, errors


def _structure_payload(package: ChapterPackage) -> dict:
    return {
        'roadmap': f"本章是{package.chapter_title}，按教材目录分为{len(package.sections)}节。",
        'sections': [{'section_id': section.section_id, 'title': section.title,
                      'question': f"{section.title}讲什么"} for section in package.sections],
        'order': '先按目录顺序阅读各节。',
        'first_concept': '',
        'next_action': '从第一节开始；本次没有可取正文，不补充教材事实。',
    }


def _messages(package: ChapterPackage, constraints=()) -> list[dict]:
    outline = {'chapter_title': package.chapter_title,
               'sections': [{'section_id': section.section_id, 'title': section.title,
                             'first_target': section.first_target}
                            for section in package.sections]}
    excerpts = [{'index': source.get('index'), 'page': source.get('page'),
                 'text': source.get('text')} for source in package.sources]
    content = json.dumps({'outline': outline, 'excerpts': excerpts,
                          'constraints': list(constraints)}, ensure_ascii=False)
    return [{'role': 'system', 'content': CHAPTER_OVERVIEW}, {'role': 'user', 'content': content}]


def _coverage(payload: dict, package: ChapterPackage) -> bool:
    covered = {section.get('section_id') for section in payload.get('sections') or []
               if isinstance(section, dict)}
    return {section.section_id for section in package.sections} <= covered


def _render_reply(payload: dict, package: ChapterPackage) -> str:
    by_id = {section.get('section_id'): section for section in payload.get('sections') or []
             if isinstance(section, dict)}
    lines = [f"本章：{package.chapter_title}"]
    if payload.get('roadmap'):
        lines.append('本章地图：' + str(payload['roadmap']).strip())
    questions = []
    for section in package.sections:
        question = str((by_id.get(section.section_id) or {}).get('question') or '').strip()
        questions.append(f"- {section.title}：{question or '本节核心问题待补充'}")
    if questions:
        lines.append('逐节核心问题：\n' + '\n'.join(questions))
    if payload.get('order'):
        lines.append('建议顺序：' + str(payload['order']).strip())
    if payload.get('first_concept'):
        lines.append('先讲第一个概念：' + str(payload['first_concept']).strip())
    if not payload.get('first_concept'):
        lines.append('本次没有可取正文，只提供目录结构；不补充教材事实。')
    if payload.get('next_action'):
        lines.append('下一步：' + str(payload['next_action']).strip())
    return '\n\n'.join(lines)


def _claim(text: str, package: ChapterPackage) -> ContentClaim | None:
    ids = []
    for number in CITATION.findall(text):
        source = next((item for item in package.sources
                       if int(item.get('index') or 0) == int(number)), None)
        if source and str(source.get('source_id')):
            ids.append(str(source['source_id']))
    if not ids:
        return None
    return ContentClaim(text=text, source_ids=list(dict.fromkeys(ids))[:8], provenance='paraphrase')


def _section_question(payload: dict, section: ChapterSection) -> str:
    row = next((item for item in payload.get('sections') or []
                if isinstance(item, dict) and item.get('section_id') == section.section_id), None)
    return str((row or {}).get('question') or '').strip()


def _learning_response(payload: dict, package: ChapterPackage, reply: str, status: str) -> dict:
    entries = [
        ('roadmap', str(payload.get('roadmap') or '').strip()),
        ('section_map', '\n'.join(f"- {section.title}：{_section_question(payload, section)}"
                                  for section in package.sections)),
        ('explanation', str(payload.get('first_concept') or '').strip()),
    ]
    specs, blocks = [], []
    for semantic_type, text in entries:
        if not text:
            continue
        block_id = f'b{len(specs) + 1}'
        specs.append(BlockSpec(block_id=block_id, semantic_type=semantic_type))
        claim = _claim(text, package)
        blocks.append(PublishedBlock(block_id=block_id, semantic_type=semantic_type,
            claims=[claim] if claim else [], rendered_text=text,
            content_origin='generated' if claim else 'host_snapshot',
            authority_ref=None if claim else f'course_outline:chapter:{package.chapter_id}'))
    plan = ResponsePlan(plan_id=hashlib.sha256(
        f'chapter_overview:{package.chapter_id}:{package.chapter_title}'.encode('utf-8')).hexdigest()[:24],
        target_id=f'chapter:{package.chapter_id}', strategy='chapter_overview', blocks=specs)
    return LearningResponse(response_id=uuid4().hex, plan=plan,
                            status='complete' if status == 'answered' else 'partial',
                            blocks=blocks, reply=reply).model_dump()


def _navigation_cursor(package: ChapterPackage) -> dict:
    """Point at the first section target so "下一部分" can continue."""
    if not package.sections:
        return {'status': 'clarify', 'mode': 'overview',
                'chapter_id': package.chapter_id, 'chapter_title': package.chapter_title}
    first = package.sections[0]
    return {'status': 'ready', 'mode': 'overview', 'path_kind': 'textbook_heading_order',
            'id': first.unit_id, 'version': first.version,
            'chapter_id': package.chapter_id, 'section_id': first.section_id,
            'title': first.first_target or first.title, 'section_title': first.title,
            'chapter_title': package.chapter_title, 'explained': False, 'covered': False}


def _result(payload: dict, package: ChapterPackage, *, coverage_ok: bool, content_ok: bool,
            kind: str) -> dict:
    answer_status = 'answered' if coverage_ok and content_ok else 'partial'
    reply = _render_reply(payload, package)
    sections = [section for section in payload.get('sections') or [] if isinstance(section, dict)]
    return {
        'reply': reply,
        'answer_status': answer_status,
        'result_type': kind,
        'learning_response': _learning_response(payload, package, reply, answer_status),
        'chapter_overview': {'chapter_id': package.chapter_id,
                             'chapter_title': package.chapter_title,
                             'section_ids': sorted({section.get('section_id') for section in sections}),
                             'coverage_ok': coverage_ok, 'content_ok': content_ok},
        'course_navigation': _navigation_cursor(package),
        'pdf_references': [],
        'textbook_sources': sorted({str(source.get('location', {}).get('source_file')
                                       or source.get('document_id') or '')
                                    for source in package.sources} - {''}),
        'sources': list(package.sources),
        'step_advanced': False,
    }


def _clarify(kind: str) -> dict:
    return {'reply': '请说明要导学的教材章号或完整章节名称。',
            'answer_status': 'clarify', 'result_type': kind,
            'chapter_overview': {'coverage_ok': False, 'content_ok': False},
            'course_navigation': {'status': 'clarify', 'mode': 'overview'},
            'pdf_references': [], 'textbook_sources': [], 'sources': [], 'step_advanced': False}


def _content_ok(payload: dict, package: ChapterPackage) -> bool:
    first_concept = str(payload.get('first_concept') or '').strip()
    if not first_concept or not package.sources:
        return False
    allowed = {int(source.get('index') or 0) for source in package.sources}
    return bool({int(number) for number in CITATION.findall(first_concept)} & allowed)


def _apply_constraints(payload: dict, max_questions: int) -> dict:
    """no_questions is a hard constraint: render statements, never a prompt."""
    if max_questions > 0 or not isinstance(payload, dict):
        return payload
    value = dict(payload)
    for field in TEXT_FIELDS:
        value[field] = str(value.get(field) or '').replace('？', '。').replace('?', '。')
    value['sections'] = [dict(item, question=str(item.get('question') or '')
                              .replace('？', '。').replace('?', '。'))
                         if isinstance(item, dict) else item
                         for item in value.get('sections') or []]
    return value


def _structure_result(package: ChapterPackage, kind: str, max_questions: int = 1) -> dict:
    """Structure-only fallback: outline facts only, never an invented [n]."""
    payload = _structure_payload(package)
    ok, _ = validate_overview(payload, package, require_citations=False,
                              max_questions=max_questions)
    if not ok:
        return _quality_rejected(package, kind, payload)
    return _result(payload, package, coverage_ok=_coverage(payload, package),
                   content_ok=False, kind=kind)


def _quality_rejected(package: ChapterPackage, kind: str, payload: dict) -> dict:
    return {'reply': '章节导学没有通过内容校验，本次不发布未经核实的内容，请稍后重试。',
            'answer_status': 'quality_rejected', 'result_type': kind,
            'chapter_overview': {'chapter_id': package.chapter_id,
                                 'chapter_title': package.chapter_title,
                                 'section_ids': [], 'coverage_ok': _coverage(payload, package),
                                 'content_ok': False},
            'course_navigation': {'status': 'clarify', 'mode': 'overview'},
            'pdf_references': [], 'textbook_sources': [], 'sources': [],
            'step_advanced': False}


def run_chapter_overview(context, request, llm, *, package: ChapterPackage | None = None) -> dict:
    route = getattr(context, 'turn_route', None) or {}
    kind = route.get('kind') if route.get('kind') in ('chapter_overview', 'section_overview') \
        else 'chapter_overview'
    if package is None:
        chapter_id = route.get('chapter_id')
        if chapter_id is None:
            return _clarify(kind)
        try:
            package = build_chapter_package(int(chapter_id))
        except ValueError:
            return _clarify(kind)
    if kind == 'section_overview' and route.get('section_id') is not None:
        sections = tuple(section for section in package.sections
                         if section.section_id == route['section_id'])
        if not sections:
            return _clarify(kind)
        package = replace(package, sections=sections)
    constraints = tuple(route.get('constraints') or ())
    max_questions = 0 if 'no_questions' in constraints else 1
    if not package.sources:
        return _structure_result(package, kind, max_questions)
    messages = _messages(package, constraints)
    messages.append({'role': 'user', 'content': request.message})
    from agents.teaching_skills import prepare_teaching_skills
    skill_policy, skill_receipts = prepare_teaching_skills(llm, messages)
    messages.append({'role': 'system', 'content': skill_policy +
        '\n本次使用既有章节JSON字段传输内容，教法以已读技能为准；'
        '教材目录、引用和掌握状态的真实性检查仍须遵守。'})
    payload, errors, raised = {}, [], 0
    ok = False
    for attempt in range(2):
        if attempt:
            messages = messages + [{'role': 'user', 'content':
                '上一次输出未通过校验：' + json.dumps(errors, ensure_ascii=False)
                + '。请只按约定JSON重写。'}]
        from llm.client import LLMError, answer_max_tokens
        try:
            payload = llm.chat_json(messages, temperature=0.2,
                                    max_tokens=answer_max_tokens(), retries=0)
        except LLMError:
            raised += 1
            errors = ['model_output_invalid']
            payload = {}
            continue
        payload = _apply_constraints(payload, max_questions)
        ok, errors = validate_overview(payload, package, max_questions=max_questions)
        if ok:
            break
    if not ok:
        # Never publish the rejected generated text; a structure-only partial is
        # safer and more useful than a 32-character refusal.
        result = _structure_result(package, kind, max_questions)
        result['teaching_skills'] = skill_receipts
        return result
    omitted = bool(payload.get('omitted_sections'))
    coverage_ok = _coverage(payload, package) and not omitted
    result = _result(payload, package, coverage_ok=coverage_ok,
                     content_ok=_content_ok(payload, package), kind=kind)
    result['teaching_skills'] = skill_receipts
    return result
