"""对已发布讲解做有限展示投影，不建立新的学习状态或评分来源。"""
import hashlib
from copy import deepcopy
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CardText(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=100)
    body: str = Field(min_length=1, max_length=1200)
    source_indices: list[int] = Field(default_factory=list, max_length=6)


class ComparisonRow(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, str_strip_whitespace=True)
    aspect: str = Field(min_length=1, max_length=100)
    left: str = Field(min_length=1, max_length=500)
    right: str = Field(min_length=1, max_length=500)
    source_indices: list[int] = Field(default_factory=list, max_length=6)


class StepPresentation(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, str_strip_whitespace=True)
    kind: Literal['step_reveal']
    title: str = Field(min_length=1, max_length=100)
    steps: list[CardText] = Field(min_length=2, max_length=6)


class ComparisonPresentation(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, str_strip_whitespace=True)
    kind: Literal['concept_comparison']
    title: str = Field(min_length=1, max_length=100)
    labels: list[str] = Field(min_length=2, max_length=2)
    rows: list[ComparisonRow] = Field(min_length=1, max_length=6)


def presentation_arguments(arguments):
    kind = arguments.get('card_kind')
    fields = ('card_title', 'explanation_steps', 'comparison_labels', 'comparison_rows')
    if kind is None:
        if any(key in arguments for key in fields):
            raise ValueError('展示内容须指定card_kind')
        return None
    title = arguments.get('card_title') or ('分步回看' if kind == 'step_reveal' else '概念对比')
    if kind == 'step_reveal' and not any(key in arguments for key in ('comparison_labels', 'comparison_rows')):
        return StepPresentation(kind=kind, title=title, steps=arguments.get('explanation_steps')).model_dump()
    if kind == 'concept_comparison' and 'explanation_steps' not in arguments:
        result = ComparisonPresentation(kind=kind, title=title, labels=arguments.get('comparison_labels'),
                                        rows=arguments.get('comparison_rows'))
        if any(not label.strip() or len(label) > 100 for label in result.labels):
            raise ValueError('对比对象须为1—100字')
        return result.model_dump()
    raise ValueError('卡片类型或内容不匹配')


def _plain(text):
    return re.sub(r'[^\w]', '', re.sub(r'\[\d+\]', '', text)).casefold()


def presentation_text(presentation):
    """复用结构化结果发布：正文和卡片同源，避免再生成一次造成措辞漂移。"""
    def body(text):
        return re.sub(r'\[\d+\]', '', text).strip()

    def references(indices):
        return ''.join(f'[{index}]' for index in dict.fromkeys(indices))

    if presentation['kind'] == 'step_reveal':
        return '\n\n'.join([presentation['title']] + [
            f"{index}. {step['title']}\n{body(step['body'])}{references(step['source_indices'])}"
            for index, step in enumerate(presentation['steps'], 1)])
    def cell(text):
        return body(text).replace('|', r'\|').replace('\n', ' ')
    labels = presentation['labels']
    return '\n'.join([presentation['title'], '',
        f'| 比较角度 | {cell(labels[0])} | {cell(labels[1])} |', '| --- | --- | --- |'] + [
        f"| {cell(row['aspect'])} | {cell(row['left'])} | {cell(row['right'])}{references(row['source_indices'])} |"
        for row in presentation['rows']])


def published_reference_map(sources, references):
    original = {}
    for index, source in enumerate(sources, 1):
        evidence_id = ((source.get('location') or {}).get('evidence') or {}).get('evidence_id')
        if evidence_id:
            original[evidence_id] = int(source.get('index') or index)
    mapping = {}
    for ref in references:
        evidence_id = (ref.get('evidence') or {}).get('evidence_id')
        index = ref.get('source_index')
        if evidence_id in original and type(index) is int and index >= 0:
            mapping[original[evidence_id]] = index + 1
    return mapping


def build_learning_cards(teaching, sources, answer, *, reference_map=None):
    if not answer.strip() or re.fullmatch(r'(?:你好|您好|谢谢|再见)[！!。\s]*', teaching.request.message):
        return []
    request = teaching.request
    identity = request.task_id or request.request_id
    if not identity:
        return []
    base = {'schema': 'learning-cards/v1', 'revision': request.task_revision or 1,
            'objective_id': teaching.objective.id}

    def card(kind, data):
        key = hashlib.sha256(':'.join((request.student_id, request.session_id, identity, kind)).encode()).hexdigest()[:24]
        return {**base, 'card_id': key, 'kind': kind, **data}

    cards = []
    presentation = deepcopy(teaching.state.get('presentation'))
    if presentation:
        kind = presentation['kind']
        rows = presentation['steps'] if kind == 'step_reveal' else presentation['rows']
        indices = {int(source.get('index') or index) for index, source in enumerate(sources, 1)}
        if reference_map:
            indices = {reference_map.get(index, index) for index in indices}
            for row in rows:
                row['source_indices'] = [reference_map.get(index, index) for index in row['source_indices']]
        indices &= {int(value) for value in re.findall(r'\[(\d+)\]', answer)}
        published = _plain(answer)
        # 卡片只整理本轮已发布内容，不能夹带未经正文核验的新事实。
        texts = [row['body'] for row in rows] if kind == 'step_reveal' else [row[key] for row in rows for key in ('left', 'right')]
        if (all(_plain(text) and _plain(text) in published for text in texts)
                and all(set(row['source_indices']) <= indices for row in rows)):
            cards.append(card(kind, {key: value for key, value in presentation.items() if key != 'kind'}))
    evidence = [event for event in teaching.progress.learning_evidence
                if event.knowledge_point_id == teaching.objective.id and event.source == 'host_formative']
    reason = ('pending_snapshot' if teaching.progress.pending_question else
              'provisional_feedback' if evidence and evidence[-1].result in ('partial', 'incorrect') else
              'requested_support' if teaching.state.get('turn_move') == 'needs_support' else None)
    location = teaching.request.reader_location
    cards.append(card('learning_progress', {
        'title': teaching.objective.name,
        'explained': teaching.objective.id in teaching.progress.explained_objectives,
        'pending': teaching.progress.pending_question is not None,
        'formative_attempts': len(evidence),
        'evidence_label': '辅助反馈，待独立验证' if evidence else '暂无作答证据',
        'mastered': False,
        'course_id': teaching.progress.book_id, 'review_reason_code': reason,
        'location_label': f'第{location.chapter_id}章 · 第{location.section_id}节（上次学习位置）' if location else '',
    }))
    return cards
